"""Rule-based baselines. The LLM agent must beat these to be worth running."""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from ..features import FeatureStore
from .base import FLAT, HOLD, LONG, SHORT, Strategy


def _aligned_bars(store: FeatureStore, times: pd.DatetimeIndex) -> pd.DataFrame:
    """Indicator row of the last closed decision bar for each decision time."""
    bar_open = times - pd.Timedelta(hours=store.decision_hours)
    return store.bars.reindex(bar_open).set_axis(times)


def _frame(times, actions, confidence=1.0, sl_pct=None, tp_pct=None, reason="") -> pd.DataFrame:
    df = pd.DataFrame({"action": actions, "confidence": confidence, "leverage": None,
                       "sl_pct": sl_pct, "tp_pct": tp_pct, "reason": reason}, index=times)
    df.index.name = "time"
    return df


class BuyAndHold(Strategy):
    """Always long. With leverage=1 and no SL this is the passive benchmark."""
    name = "buy_and_hold"
    use_stops = False
    fixed_leverage = 1

    def decide(self, symbol, store, times):
        return _frame(times, LONG, sl_pct=np.nan, tp_pct=np.nan, reason="hold")


class Flat(Strategy):
    name = "flat"

    def decide(self, symbol, store, times):
        return _frame(times, FLAT)


class RandomStrategy(Strategy):
    """Coin flip direction - the skill floor. Any real model should clear this."""
    name = "random"

    def __init__(self, seed: int = 7):
        self.seed = seed

    def decide(self, symbol, store, times):
        rng = np.random.default_rng(zlib.crc32(f"{symbol}:{self.seed}".encode()))
        return _frame(times, rng.choice([LONG, SHORT, FLAT], size=len(times), p=[0.4, 0.4, 0.2]))


class EmaTrend(Strategy):
    """Trend following: EMA20/EMA50 cross filtered by EMA200 and ADX."""
    name = "ema_trend"

    def decide(self, symbol, store, times):
        b = _aligned_bars(store, times)
        up = (b["ema20"] > b["ema50"]) & (b["close"] > b["ema200"]) & (b["adx14"] > 20)
        dn = (b["ema20"] < b["ema50"]) & (b["close"] < b["ema200"]) & (b["adx14"] > 20)
        actions = np.where(up, LONG, np.where(dn, SHORT, FLAT))
        return _frame(times, actions, confidence=0.7, reason="ema trend")


class DonchianBreakout(Strategy):
    """Classic turtle-style breakout of the prior 20-bar range."""
    name = "donchian_breakout"
    lookback = 120   # breakout state carries over between bars

    def decide(self, symbol, store, times):
        b = _aligned_bars(store, times)
        prev_hh = store.bars["hh20"].shift(1).reindex(times - pd.Timedelta(hours=store.decision_hours)).values
        prev_ll = store.bars["ll20"].shift(1).reindex(times - pd.Timedelta(hours=store.decision_hours)).values
        close = b["close"].values
        state, out = FLAT, []
        for c, hh, ll in zip(close, prev_hh, prev_ll):
            if np.isnan(hh):
                out.append(FLAT)
                continue
            if c > hh:
                state = LONG
            elif c < ll:
                state = SHORT
            out.append(state)
        return _frame(times, out, confidence=0.7, reason="breakout")


class RsiReversion(Strategy):
    """Mean reversion: fade RSI extremes in ranging (low ADX) markets."""
    name = "rsi_reversion"

    def decide(self, symbol, store, times):
        b = _aligned_bars(store, times)
        ranging = b["adx14"] < 25
        actions = np.where(ranging & (b["rsi14"] < 30), LONG,
                           np.where(ranging & (b["rsi14"] > 70), SHORT, HOLD))
        # Positions exit via SL/TP; non-extreme bars keep whatever is open.
        return _frame(times, actions, confidence=0.6, reason="rsi reversion")


BASELINES = {cls.name: cls for cls in (BuyAndHold, Flat, RandomStrategy, EmaTrend, DonchianBreakout, RsiReversion)}
