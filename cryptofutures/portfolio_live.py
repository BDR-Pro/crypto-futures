"""Live paper trading for discovered portfolio strategies (code written by `cryptofutures discover`).

Runs a strategy exactly the way the discovery evaluator scored it: once a day, after the UTC daily close, the code
sees daily candles of the whole universe (same anonymised columns, BTC named) and returns a position per coin;
each coin's target weight is position / number of trading coins, and the book is rebalanced at the live price,
paying fee + slippage on the traded notional. Perpetual funding is charged every 8 hours when enabled.
Public market data only: no API keys, no real orders.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .discover import COST, FIELDS, anonymise, run_candidate

log = logging.getLogger(__name__)
TICKER_ALIASES = {"MATICPOLUSDT": "POL"}


def spot_symbol(symbol: str) -> str:
    base = TICKER_ALIASES.get(symbol, symbol.removesuffix("USDT"))
    return f"{base}/USDT"


def perp_symbol(symbol: str) -> str:
    return f"{spot_symbol(symbol)}:USDT"


class PortfolioPaperTrader:
    def __init__(self, code: str, symbols: list[str], exchange: str = "binance", state_path: str = "results/live_disc/state.json",
                 log_path: str = "results/live_disc/rebalances.csv", initial_equity: float = 10_000.0,
                 history_days: int = 800, funding: bool = True, poll_seconds: int = 60, name: str = "discovered"):
        import ccxt  # lazily: only live trading needs it
        opts: dict = {"enableRateLimit": True}
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if proxy:
            opts["httpsProxy"] = proxy
        self.ex = getattr(ccxt, exchange)(opts)
        self.perp = getattr(ccxt, {"binance": "binanceusdm"}.get(exchange, exchange))(opts) if funding else None
        self.code, self.name = code, name
        self.alias = anonymise([s.removeprefix("1000") for s in symbols])
        self.symbols = [s.removeprefix("1000") for s in symbols]
        self.history_days, self.poll = history_days, poll_seconds
        self.state_path, self.log_path = Path(state_path), Path(log_path)
        self.cash, self.units = initial_equity, {}
        self.last_rebalance: str | None = None
        self.last_funding: str | None = None
        if "taker_buy" in code and self.ex.id != "binance":
            log.warning("this strategy reads taker-buy volume, which only Binance publishes; on %s it is set to 50%%",
                        self.ex.id)
        self._load()

    # ---- state ------------------------------------------------------------------------------
    def _load(self) -> None:
        if self.state_path.exists():
            st = json.loads(self.state_path.read_text())
            self.cash, self.units = st["cash"], st["units"]
            self.last_rebalance, self.last_funding = st.get("last_rebalance"), st.get("last_funding")
            log.info("resumed: cash %.2f, %d positions", self.cash, len(self.units))

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({"cash": self.cash, "units": self.units, "last_rebalance": self.last_rebalance,
                                               "last_funding": self.last_funding}, indent=2))

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash + sum(u * prices.get(s, 0.0) for s, u in self.units.items())

    # ---- data -------------------------------------------------------------------------------
    def _daily(self, symbol: str, since_ms: int) -> pd.DataFrame:
        rows, sym = [], spot_symbol(symbol)
        while True:
            if self.ex.id == "binance":     # raw klines carry taker-buy quote volume
                raw = self.ex.publicGetKlines({"symbol": sym.replace("/", ""), "interval": "1d", "startTime": since_ms,
                                               "limit": 1000})
                chunk = [[int(k[0]), *map(float, (k[1], k[2], k[3], k[4], k[7], k[10]))] for k in raw]
            else:
                raw = self.ex.fetch_ohlcv(sym, "1d", since=since_ms, limit=300)
                chunk = [[k[0], k[1], k[2], k[3], k[4], k[5] * k[4], k[5] * k[4] / 2] for k in raw]
            if not chunk:
                break
            rows += chunk
            nxt = chunk[-1][0] + 86_400_000
            if nxt <= since_ms or nxt > time.time() * 1000:
                break
            since_ms = nxt
        df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "quote_volume", "taker_buy_quote"])
        df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
        return df.drop_duplicates("time").set_index("time")

    def panel_inputs(self, today: pd.Timestamp) -> tuple[dict[str, pd.DataFrame], pd.DatetimeIndex]:
        since = int((today - pd.Timedelta(days=self.history_days)).timestamp() * 1000)
        frames = {}
        for s in self.symbols:
            try:
                df = self._daily(s, since)
            except Exception as e:  # noqa: BLE001 - coin not listed on this venue
                log.debug("%s unavailable: %s", s, e)
                continue
            frames[self.alias[s]] = df[df.index < today]          # closed days only
        idx = pd.DatetimeIndex(sorted(set().union(*(f.index for f in frames.values()))))
        cols = sorted(self.alias.values(), key=lambda c: (c != "BTC", c))
        data = {k: pd.DataFrame({c: (frames[c][src].reindex(idx) if c in frames else np.nan) for c in cols},
                                index=idx).reset_index(drop=True) for k, src in FIELDS.items()}
        return data, idx

    def prices(self) -> dict[str, float]:
        tick = self.ex.fetch_tickers([spot_symbol(s) for s in self.symbols if spot_symbol(s) in self.ex.markets])
        return {s: float(tick[spot_symbol(s)]["last"]) for s in self.symbols if spot_symbol(s) in tick}

    # ---- trading ----------------------------------------------------------------------------
    def rebalance(self, today: pd.Timestamp) -> None:
        data, idx = self.panel_inputs(today)
        status, payload = run_candidate(self.code, data, timeout=120)
        if status != "ok":
            raise RuntimeError(f"strategy failed: {status}: {payload}")
        pos = payload[0][-1]
        last_close = data["close"].iloc[-1]
        alive = last_close.notna().to_numpy()
        weights = np.where(alive, pos, 0.0) / max(int(alive.sum()), 1)
        prices = self.prices()
        eq = self.equity(prices)
        by_alias = {a: s for s, a in self.alias.items()}
        rows, traded = [], 0.0
        for col, w in zip(data["close"].columns, weights):
            s = by_alias[col]
            if s not in prices:
                continue
            px = prices[s]
            cur = self.units.get(s, 0.0) * px
            delta = w * eq - cur
            if abs(delta) < 1e-6 * eq:
                continue
            fee = abs(delta) * COST
            self.units[s] = self.units.get(s, 0.0) + delta / px
            self.cash -= delta + fee
            traded += abs(delta)
            rows.append({"time": str(pd.Timestamp.now(tz="UTC")), "symbol": s, "price": px, "weight": round(float(w), 5),
                         "traded": round(delta, 2), "fee": round(fee, 4)})
        self.units = {s: u for s, u in self.units.items() if abs(u * prices.get(s, 0)) > 1e-6 * eq}
        if rows:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            new = not self.log_path.exists()
            with open(self.log_path, "a", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]))
                if new:
                    w.writeheader()
                w.writerows(rows)
        gross = sum(abs(u * prices.get(s, 0)) for s, u in self.units.items()) / eq
        net = sum(u * prices.get(s, 0) for s, u in self.units.items()) / eq
        log.info("REBALANCE %s on %s closed days: traded %.0f (%.0f%% of equity), gross %.0f%%, net %+.0f%%, %d coins",
                 self.name, idx[-1].date(), traded, 100 * traded / eq, 100 * gross, 100 * net, len(self.units))

    def apply_funding(self, prices: dict[str, float]) -> None:
        for s, u in self.units.items():
            try:
                rate = float(self.perp.fetch_funding_rate(perp_symbol(s)).get("fundingRate") or 0.0)
            except Exception:  # noqa: BLE001 - no perpetual for this coin
                continue
            self.cash -= u * prices.get(s, 0.0) * rate       # longs pay positive funding, shorts receive it

    def step(self) -> None:
        if not self.ex.markets:
            self.ex.load_markets()
        now = pd.Timestamp.now(tz="UTC")
        today = now.floor("1D")
        if self.last_rebalance != str(today.date()) and now - today > pd.Timedelta(minutes=5):
            self.rebalance(today)
            self.last_rebalance = str(today.date())
        prices = self.prices()
        slot = now.floor("8h")
        if self.perp is not None and str(slot) != self.last_funding:
            if self.last_funding is not None:
                self.apply_funding(prices)
            self.last_funding = str(slot)
        self._save()
        long_ = sum(1 for u in self.units.values() if u > 0)
        log.info("equity %.2f | cash %.2f | %d long, %d short", self.equity(prices), self.cash, long_,
                 len(self.units) - long_)

    def run(self) -> None:
        log.info("paper trading %s on %d coins via %s (daily rebalance after 00:05 UTC)", self.name, len(self.symbols),
                 self.ex.id)
        while True:
            try:
                self.step()
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001 - keep running through network errors
                log.exception("step failed: %s", exc)
            time.sleep(self.poll)
