"""Paper futures exchange: isolated-margin USDT perpetuals with fees, slippage,
funding, stop-loss / take-profit and liquidation, simulated on hourly candles.

Timing convention (no look-ahead): a decision made at time T only sees candles
that closed by T, and is filled at the open of the candle starting at T.
Within a candle, if both the stop and the target could have been hit, the stop
(adverse outcome) is assumed to happen first.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from .config import Config, utc
from .risk import plan_order
from .strategies.base import FLAT, HOLD, LONG, SHORT

FUNDING_HOURS = (0, 8, 16)


@dataclass
class Position:
    symbol: str
    side: int
    qty: float
    entry: float
    leverage: int
    margin: float
    sl: float | None
    tp: float | None
    liq: float
    opened_at: pd.Timestamp
    fees: float = 0.0
    funding: float = 0.0
    confidence: float = 0.0
    reason: str = ""


@dataclass
class Trade:
    symbol: str
    side: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry: float
    exit: float
    qty: float
    leverage: int
    margin: float
    pnl: float              # net of fees and funding
    fees: float
    funding: float
    exit_reason: str
    confidence: float
    entry_reason: str

    @property
    def return_on_margin(self) -> float:
        return self.pnl / self.margin if self.margin else 0.0


@dataclass
class Account:
    cfg: Config
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)

    # ---- valuation -------------------------------------------------------
    def unrealized(self, marks: dict[str, float]) -> float:
        total = 0.0
        for sym, p in self.positions.items():
            pnl = p.side * p.qty * (marks.get(sym, p.entry) - p.entry)
            total += max(pnl, -p.margin)  # isolated margin caps the loss
        return total

    def equity(self, marks: dict[str, float]) -> float:
        return self.cash + self.unrealized(marks)

    def free_margin(self, marks: dict[str, float]) -> float:
        used = sum(p.margin for p in self.positions.values())
        return self.equity(marks) - used

    # ---- order handling --------------------------------------------------
    def open(self, symbol: str, plan, price: float, t: pd.Timestamp, confidence: float, reason: str) -> None:
        ex = self.cfg.exchange
        fill = price * (1 + plan.side * ex.slippage)
        qty = plan.notional / fill
        fee = plan.notional * ex.taker_fee
        self.cash -= fee
        liq = fill * (1 - plan.side * (1 / plan.leverage - ex.maint_margin_rate))
        self.positions[symbol] = Position(
            symbol=symbol, side=plan.side, qty=qty, entry=fill, leverage=plan.leverage,
            margin=plan.notional / plan.leverage,
            sl=fill * (1 - plan.side * plan.sl_pct) if plan.sl_pct else None,
            tp=fill * (1 + plan.side * plan.tp_pct) if plan.tp_pct else None,
            liq=liq, opened_at=t, fees=fee, confidence=confidence, reason=reason)

    def close(self, symbol: str, price: float, t: pd.Timestamp, reason: str, slip: bool = True) -> Trade:
        ex = self.cfg.exchange
        p = self.positions.pop(symbol)
        if reason == "liquidation":
            fill, gross = p.liq, -p.margin
            fee = 0.0
        else:
            fill = price * (1 - p.side * ex.slippage) if slip else price
            gross = max(p.side * p.qty * (fill - p.entry), -p.margin)
            fee = p.qty * fill * ex.taker_fee
        self.cash += gross - fee
        trade = Trade(symbol=symbol, side=LONG if p.side > 0 else SHORT, entry_time=p.opened_at, exit_time=t,
                      entry=p.entry, exit=fill, qty=p.qty, leverage=p.leverage, margin=p.margin,
                      pnl=gross - p.fees - fee - p.funding, fees=p.fees + fee, funding=p.funding,
                      exit_reason=reason, confidence=p.confidence, entry_reason=p.reason)
        self.trades.append(trade)
        return trade

    def process_bar(self, symbol: str, t: pd.Timestamp, o: float, h: float, l: float) -> None:
        """Check liquidation / SL / TP against one candle. Gaps fill at the open."""
        p = self.positions.get(symbol)
        if p is None:
            return
        s = p.side
        # Price levels that act against the position, nearest first.
        stop = p.sl if p.sl is not None and s * (p.sl - p.liq) > 0 else None
        worst = l if s > 0 else h
        best = h if s > 0 else l
        if stop is not None and s * (o - stop) <= 0:
            self.close(symbol, o, t, "stop_loss")
        elif s * (o - p.liq) <= 0:
            self.close(symbol, o, t, "liquidation")
        elif p.tp is not None and s * (o - p.tp) >= 0:
            self.close(symbol, o, t, "take_profit", slip=False)
        elif stop is not None and s * (worst - stop) <= 0:
            self.close(symbol, stop, t, "stop_loss")
        elif s * (worst - p.liq) <= 0:
            self.close(symbol, p.liq, t, "liquidation")
        elif p.tp is not None and s * (best - p.tp) >= 0:
            self.close(symbol, p.tp, t, "take_profit", slip=False)

    def apply_funding(self, symbol: str, rate: float, mark: float) -> None:
        p = self.positions.get(symbol)
        if p is None or not rate:
            return
        payment = p.side * p.qty * mark * rate   # longs pay positive funding
        self.cash -= payment
        p.funding += payment


@dataclass
class BacktestResult:
    name: str
    equity: pd.Series
    trades: pd.DataFrame
    decisions: dict[str, pd.DataFrame]
    config: Config

    def to_dict(self) -> dict:
        return {"name": self.name, "risk": asdict(self.config.risk)}


def run_backtest(cfg: Config, candles: dict[str, pd.DataFrame], funding: dict[str, pd.Series],
                 decisions: dict[str, pd.DataFrame], atr: dict[str, pd.Series], name: str = "",
                 use_stops: bool = True, fixed_leverage: int | None = None,
                 start=None, end=None) -> BacktestResult:
    """Simulate the account over hourly candles, acting on precomputed decisions.

    decisions[sym] is indexed by decision time T; atr[sym] gives the ATR% known at T.
    """
    risk = cfg.risk
    acct = Account(cfg=cfg, cash=cfg.exchange.initial_equity)
    index = sorted(set().union(*[c.index for c in candles.values()]))
    index = pd.DatetimeIndex(index)
    if start is not None:
        index = index[index >= utc(start)]
    if end is not None:
        index = index[index < utc(end)]

    arrays = {s: c.reindex(index)[["open", "high", "low", "close"]].to_numpy() for s, c in candles.items()}
    fund = {s: f.reindex(index).to_numpy() if len(f) else np.full(len(index), np.nan) for s, f in funding.items()}
    dec_lookup = {s: d.to_dict("index") for s, d in decisions.items()}
    atr_lookup = {s: a.to_dict() for s, a in atr.items()}
    marks: dict[str, float] = {}
    eq = np.empty(len(index))

    for i, t in enumerate(index):
        opens = {s: a[i, 0] for s, a in arrays.items() if not np.isnan(a[i, 0])}
        # 1) funding settles at the start of 00/08/16 UTC candles
        if cfg.exchange.use_funding and t.hour in FUNDING_HOURS:
            for s in list(acct.positions):
                r = fund.get(s, np.full(len(index), np.nan))[i]
                if s in opens and not np.isnan(r):
                    acct.apply_funding(s, r, opens[s])
        # 2) act on decisions made at T, filled at this candle's open
        for s, price in opens.items():
            d = dec_lookup.get(s, {}).get(t)
            if d is None:
                continue
            marks.update(opens)
            _act(acct, s, d, price, t, atr_lookup.get(s, {}).get(t, np.nan), marks, use_stops, fixed_leverage)
        # 3) intra-candle SL / TP / liquidation
        for s in list(acct.positions):
            a = arrays[s][i]
            if not np.isnan(a[0]):
                acct.process_bar(s, t, a[0], a[1], a[2])
        for s, a in arrays.items():
            if not np.isnan(a[i, 3]):
                marks[s] = a[i, 3]
        eq[i] = acct.equity(marks)

    # Close anything still open at the final mark so PnL is realized.
    for s in list(acct.positions):
        acct.close(s, marks[s], index[-1], "end_of_test")
    if len(eq):
        eq[-1] = acct.cash

    trades = pd.DataFrame([{**asdict(tr), "return_on_margin": tr.return_on_margin} for tr in acct.trades])
    return BacktestResult(name=name, equity=pd.Series(eq, index=index, name="equity"),
                          trades=trades, decisions=decisions, config=cfg)


def _act(acct: Account, s: str, d: dict, price: float, t, atr_pct: float, marks: dict,
         use_stops: bool, fixed_leverage: int | None) -> None:
    risk = acct.cfg.risk
    action = d.get("action", HOLD)
    if action == HOLD:
        return
    conf = d.get("confidence", 1.0)
    conf = 1.0 if conf is None or conf != conf else float(conf)
    pos = acct.positions.get(s)
    if action == FLAT:
        if pos is not None and risk.flat_closes:
            acct.close(s, price, t, "signal_flat")
        return
    side = 1 if action == LONG else -1
    if pos is not None:
        if pos.side == side:
            return                       # already positioned that way: let it run
        acct.close(s, price, t, "signal_reverse")
    if conf < risk.min_confidence:
        return                           # not confident enough to open
    if len(acct.positions) >= risk.max_open_positions:
        return
    plan = plan_order(side, d, atr_pct, acct.equity(marks), acct.free_margin(marks),
                      risk, acct.cfg.exchange, use_stops, fixed_leverage)
    if plan is not None:
        acct.open(s, plan, price, t, conf, str(d.get("reason", ""))[:200])
