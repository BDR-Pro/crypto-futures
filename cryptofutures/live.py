"""Live paper trading: real-time prices from an exchange (via ccxt, public data only,
no API keys, no real orders) driving the same Account / risk layer as the backtester."""
from __future__ import annotations

import csv
import json
import logging
import os
import time
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .config import Config
from .data import fetch_live_candles, to_ccxt_symbol
from .engine import FUNDING_HOURS, Account, Position, _act
from .features import FeatureStore
from .strategies import Strategy

log = logging.getLogger(__name__)
HISTORY_HOURS = 5200   # enough for EMA200 on the daily timeframe


class LivePaperTrader:
    def __init__(self, cfg: Config, strategy: Strategy, poll_seconds: int = 30):
        import ccxt  # imported lazily: only live trading needs it
        self.cfg = cfg
        self.strategy = strategy
        self.poll = poll_seconds
        opts: dict = {"enableRateLimit": True}
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if proxy:  # ccxt ignores proxy env vars unless told
            opts["httpsProxy"] = proxy
        self.exchange = getattr(ccxt, cfg.live.exchange)(opts)
        self.symbols = cfg.data.symbols
        self.state_path = Path(cfg.live.state_path)
        self.log_path = Path(cfg.live.log_path)
        self.account = Account(cfg=cfg, cash=cfg.exchange.initial_equity)
        self.last_decision: pd.Timestamp | None = None
        self.last_funding: pd.Timestamp | None = None
        self.candles: dict[str, pd.DataFrame] = {}
        self._load_state()

    # ---- persistence -------------------------------------------------------
    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        st = json.loads(self.state_path.read_text())
        self.account.cash = st["cash"]
        for sym, p in st["positions"].items():
            p["opened_at"] = pd.Timestamp(p["opened_at"])
            self.account.positions[sym] = Position(**p)
        self.last_decision = pd.Timestamp(st["last_decision"]) if st.get("last_decision") else None
        self.last_funding = pd.Timestamp(st["last_funding"]) if st.get("last_funding") else None
        log.info("resumed: cash %.2f, %d open positions", self.account.cash, len(self.account.positions))

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        st = {"cash": self.account.cash,
              "positions": {s: {**asdict(p), "opened_at": str(p.opened_at)} for s, p in self.account.positions.items()},
              "last_decision": str(self.last_decision) if self.last_decision is not None else None,
              "last_funding": str(self.last_funding) if self.last_funding is not None else None}
        self.state_path.write_text(json.dumps(st, indent=2, default=str))

    def _log_new_trades(self, n_before: int) -> None:
        new = self.account.trades[n_before:]
        if not new:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.log_path.exists()
        with open(self.log_path, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(asdict(new[0]).keys()))
            if not exists:
                w.writeheader()
            for tr in new:
                w.writerow(asdict(tr))
                log.info("CLOSED %s %s pnl %.2f (%s)", tr.side, tr.symbol, tr.pnl, tr.exit_reason)

    # ---- market data -------------------------------------------------------
    def _refresh_candles(self, symbol: str) -> pd.DataFrame:
        now = pd.Timestamp.now(tz="UTC").floor("h")
        have = self.candles.get(symbol)
        if have is None:
            frames, since = [], int((now - pd.Timedelta(hours=HISTORY_HOURS)).timestamp() * 1000)
            while since < now.timestamp() * 1000:
                chunk = fetch_live_candles(self.exchange, symbol, "1h", limit=1000, since=since)
                if chunk.empty:
                    break
                frames.append(chunk)
                since = int(chunk.index[-1].timestamp() * 1000) + 3_600_000
            df = pd.concat(frames)
        else:
            df = pd.concat([have, fetch_live_candles(self.exchange, symbol, "1h", limit=10)])
        df = df[~df.index.duplicated(keep="last")].sort_index()
        df = df[df.index < now]          # closed candles only
        self.candles[symbol] = df.iloc[-HISTORY_HOURS:]
        return self.candles[symbol]

    def _prices(self) -> dict[str, float]:
        tickers = self.exchange.fetch_tickers([to_ccxt_symbol(s) for s in self.symbols])
        return {s: float(tickers[to_ccxt_symbol(s)]["last"]) for s in self.symbols if to_ccxt_symbol(s) in tickers}

    # ---- main loop ---------------------------------------------------------
    def step(self) -> None:
        now = pd.Timestamp.now(tz="UTC")
        prices = self._prices()
        n_before = len(self.account.trades)

        for s, px in prices.items():           # stops / targets / liquidation on the live price
            self.account.process_bar(s, now, px, px, px)

        fund_slot = now.floor("8h")
        if self.cfg.exchange.use_funding and fund_slot.hour in FUNDING_HOURS and fund_slot != self.last_funding:
            for s in list(self.account.positions):
                try:
                    rate = float(self.exchange.fetch_funding_rate(to_ccxt_symbol(s)).get("fundingRate") or 0)
                except Exception:
                    rate = 0.0
                self.account.apply_funding(s, rate, prices.get(s, 0))
            self.last_funding = fund_slot

        slot = now.floor(f"{self.cfg.risk.decision_hours}h")
        if slot != self.last_decision:
            for s in self.symbols:
                if s not in prices:
                    continue
                hourly = self._refresh_candles(s)
                store = FeatureStore(hourly, self.cfg.risk.decision_hours)
                times = store.decision_times()
                times = times[times <= slot][-self.strategy.lookback:]
                if len(times) == 0 or times[-1] != slot:
                    continue
                d = self.strategy.decide(s, store, times).iloc[-1].to_dict()
                atr = store.bars["atr_pct"].iloc[-1]
                pos = self.account.positions.get(s)
                _act(self.account, s, d, prices[s], now, atr, prices, self.strategy.use_stops,
                     self.strategy.fixed_leverage)
                new = self.account.positions.get(s)
                if new is not None and new is not pos:
                    log.info("OPEN %s %s x%d @ %.6g sl %s tp %s | %s", "LONG" if new.side > 0 else "SHORT", s,
                             new.leverage, new.entry, f"{new.sl:.6g}" if new.sl else "-",
                             f"{new.tp:.6g}" if new.tp else "-", d.get("reason", ""))
            self.last_decision = slot

        self._log_new_trades(n_before)
        self._save_state()
        eq = self.account.equity(prices)
        log.info("equity %.2f | cash %.2f | open: %s", eq, self.account.cash,
                 ", ".join(f"{s}{'+' if p.side > 0 else '-'}x{p.leverage}" for s, p in self.account.positions.items()) or "none")

    def run(self) -> None:
        log.info("paper trading %s on %s with %s", ", ".join(self.symbols), self.cfg.live.exchange, self.strategy.name)
        while True:
            try:
                self.step()
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                log.exception("step failed: %s", exc)
            time.sleep(self.poll)
