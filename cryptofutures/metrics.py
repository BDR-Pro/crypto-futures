"""Performance metrics for a backtest result."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_metrics(equity: pd.Series, trades: pd.DataFrame, initial: float) -> dict:
    if equity.empty:
        return {}
    daily = equity.resample("1D").last().dropna()
    rets = daily.pct_change().dropna()
    days = max((equity.index[-1] - equity.index[0]).total_seconds() / 86400, 1)
    final = float(equity.iloc[-1])
    total_ret = final / initial - 1
    cagr = (final / initial) ** (365 / days) - 1 if final > 0 else -1.0
    vol = rets.std() * np.sqrt(365)
    sharpe = rets.mean() / rets.std() * np.sqrt(365) if rets.std() > 0 else 0.0
    downside = rets[rets < 0].std()
    sortino = rets.mean() / downside * np.sqrt(365) if downside and downside > 0 else 0.0
    peak = equity.cummax()
    max_dd = float((equity / peak - 1).min())
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0

    m = {
        "final_equity": round(final, 2),
        "total_return": total_ret,
        "cagr": cagr,
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": max_dd,
        "calmar": float(calmar),
        "volatility": float(vol) if vol == vol else 0.0,
        "trades": int(len(trades)),
    }
    if len(trades):
        wins, losses = trades[trades.pnl > 0], trades[trades.pnl <= 0]
        gross_loss = -losses.pnl.sum()
        m.update({
            "win_rate": len(wins) / len(trades),
            "profit_factor": float(wins.pnl.sum() / gross_loss) if gross_loss > 0 else float("inf"),
            "avg_trade_pnl": float(trades.pnl.mean()),
            "expectancy_on_margin": float(trades.return_on_margin.mean()),
            "avg_leverage": float(trades.leverage.mean()),
            "avg_hold_hours": float(((trades.exit_time - trades.entry_time).dt.total_seconds() / 3600).mean()),
            "long_share": float((trades.side == "LONG").mean()),
            "liquidations": int((trades.exit_reason == "liquidation").sum()),
            "stop_losses": int((trades.exit_reason == "stop_loss").sum()),
            "take_profits": int((trades.exit_reason == "take_profit").sum()),
            "fees_paid": float(trades.fees.sum()),
            "funding_paid": float(trades.funding.sum()),
        })
    return m


def per_symbol(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    g = trades.groupby("symbol")
    return pd.DataFrame({
        "trades": g.size(),
        "pnl": g.pnl.sum().round(2),
        "win_rate": g.apply(lambda x: (x.pnl > 0).mean()).round(3),
        "avg_lev": g.leverage.mean().round(1),
    }).sort_values("pnl", ascending=False)


def directional_accuracy(decisions: dict[str, pd.DataFrame], candles: dict[str, pd.DataFrame],
                         horizon_hours: int) -> dict:
    """Did the price move in the called direction over the next decision interval?

    Isolates the model's forecasting skill from the risk layer (SL/TP/sizing).
    """
    hits_all, conf_all = [], []
    for sym, d in decisions.items():
        if d.empty:
            continue
        opens = candles[sym]["open"]
        direction = d["action"].map({"LONG": 1, "SHORT": -1}).astype(float).to_numpy()
        p0 = opens.reindex(d.index).to_numpy()
        p1 = opens.reindex(d.index + pd.Timedelta(hours=horizon_hours)).to_numpy()
        valid = ~np.isnan(direction) & ~np.isnan(p0) & ~np.isnan(p1)
        hits_all.append((np.sign(p1 / p0 - 1) == direction)[valid])
        conf = pd.to_numeric(d["confidence"], errors="coerce").fillna(1.0).to_numpy()
        conf_all.append(conf[valid])
    hits = np.concatenate(hits_all) if hits_all else np.array([], dtype=bool)
    conf = np.concatenate(conf_all) if conf_all else np.array([])
    out = {"directional_calls": int(len(hits)),
           "directional_accuracy": float(hits.mean()) if len(hits) else float("nan")}
    if len(hits):
        hi = conf >= np.median(conf)
        out["accuracy_high_conf"] = float(hits[hi].mean())
    return out
