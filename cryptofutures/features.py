"""Technical indicators and the leak-free market snapshot fed to decision models.

All features at decision time T are computed from candles whose open_time < T,
i.e. only fully closed bars. The higher-timeframe frames are resampled from the
hourly base so they share the same guarantee.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import utc


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = atr(df, 1)
    atr_n = tr.ewm(alpha=1 / n, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr_n
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr_n
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean().fillna(0)


def resample(df: pd.DataFrame, hours: int) -> pd.DataFrame:
    """Resample hourly candles; bars are labelled by their open time."""
    rule = f"{hours}h"
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
           "quote_volume": "sum", "taker_buy_quote": "sum"}
    out = df.resample(rule, label="left", closed="left", origin="epoch").agg(agg).dropna(subset=["close"])
    # Drop a trailing bar that is not yet complete.
    expected_end = out.index[-1] + pd.Timedelta(hours=hours)
    if df.index[-1] + pd.Timedelta(hours=1) < expected_end:
        out = out.iloc[:-1]
    return out


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c = out["close"]
    out["ema20"], out["ema50"], out["ema200"] = ema(c, 20), ema(c, 50), ema(c, 200)
    out["rsi14"] = rsi(c, 14)
    macd = ema(c, 12) - ema(c, 26)
    out["macd_hist"] = macd - ema(macd, 9)
    out["atr14"] = atr(out, 14)
    out["atr_pct"] = out["atr14"] / c
    mid, sd = c.rolling(20).mean(), c.rolling(20).std()
    out["bb_pos"] = (c - (mid - 2 * sd)) / (4 * sd)          # 0 = lower band, 1 = upper band
    out["adx14"] = adx(out, 14)
    out["vol_ratio"] = out["quote_volume"] / out["quote_volume"].rolling(20).mean()
    out["taker_buy_ratio"] = out["taker_buy_quote"] / out["quote_volume"].replace(0, np.nan)
    out["hh20"] = out["high"].rolling(20).max()
    out["ll20"] = out["low"].rolling(20).min()
    for k in (1, 6, 30):
        out[f"ret{k}"] = c.pct_change(k)
    return out


class FeatureStore:
    """Per-symbol indicator frames at decision and daily resolution, aligned to decision times."""

    def __init__(self, hourly: pd.DataFrame, decision_hours: int, funding: pd.Series | None = None):
        self.hourly = hourly
        self.decision_hours = decision_hours
        self.bars = add_indicators(resample(hourly, decision_hours))
        self.daily = add_indicators(resample(hourly, 24))
        self.funding = funding if funding is not None else pd.Series(dtype=float)

    def decision_times(self, start=None, end=None) -> pd.DatetimeIndex:
        """Times T at which a decision is made = close of each decision bar."""
        times = self.bars.index + pd.Timedelta(hours=self.decision_hours)
        times = times[200:]  # warm-up for EMA200
        if start is not None:
            times = times[times >= utc(start)]
        if end is not None:
            times = times[times <= utc(end)]
        return times

    def snapshot(self, t: pd.Timestamp) -> dict | None:
        """Features using only bars that closed at or before t."""
        bars = self.bars.loc[: t - pd.Timedelta(hours=self.decision_hours)]
        daily = self.daily.loc[: t - pd.Timedelta(hours=24)]
        if len(bars) < 200 or len(daily) < 30:
            return None
        b, d = bars.iloc[-1], daily.iloc[-1]
        price = float(b["close"])
        recent = bars.iloc[-12:]
        fund = self.funding.loc[: t - pd.Timedelta(seconds=1)]
        return {
            "time": t,
            "price": price,
            "tf_hours": self.decision_hours,
            "atr_pct": float(b["atr_pct"]),
            "rsi": float(b["rsi14"]),
            "macd_hist_pct": float(b["macd_hist"] / price),
            "adx": float(b["adx14"]),
            "bb_pos": float(b["bb_pos"]),
            "ema20_dist": float(price / b["ema20"] - 1),
            "ema50_dist": float(price / b["ema50"] - 1),
            "ema200_dist": float(price / b["ema200"] - 1),
            "ema20_gt_ema50": bool(b["ema20"] > b["ema50"]),
            "ret_1": float(b["ret1"]),
            "ret_6": float(b["ret6"]),
            "ret_30": float(b["ret30"]),
            "vol_ratio": float(b["vol_ratio"]),
            "taker_buy_ratio": float(b["taker_buy_ratio"]),
            "dist_hh20": float(price / b["hh20"] - 1),
            "dist_ll20": float(price / b["ll20"] - 1),
            "d_rsi": float(d["rsi14"]),
            "d_ema50_dist": float(d["close"] / d["ema50"] - 1),
            "d_ema200_dist": float(d["close"] / d["ema200"] - 1),
            "d_ret_7": float(d["close"] / daily["close"].iloc[-8] - 1) if len(daily) > 8 else 0.0,
            "d_ret_30": float(d["ret30"]),
            "d_adx": float(d["adx14"]),
            "funding_rate": float(fund.iloc[-1]) if len(fund) else 0.0,
            "recent_closes": [round(float(x), 6) for x in recent["close"]],
            "recent_ranges_pct": [round(float((r.high - r.low) / r.close) * 100, 2) for r in recent.itertuples()],
        }
