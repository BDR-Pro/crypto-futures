"""Backtest-overfitting statistics: how much of the best result is selection luck?

When many strategy variants are tried on one history, the best one looks good partly by chance.
Two standard corrections (Bailey, Borwein, López de Prado & Zhu):

* PBO - probability of backtest overfitting, via combinatorially symmetric cross-validation
  (CSCV). The daily-return history of every variant is cut into S blocks; for many ways of
  choosing S/2 blocks as "in-sample", the variant with the best in-sample Sharpe is located in
  the out-of-sample ranking. PBO is the share of splits where it lands in the bottom half.
* DSR - deflated Sharpe ratio: the probability that the best variant's true Sharpe is above
  zero, after raising the bar to the Sharpe the best of N random variants would reach by luck,
  and allowing for skewed / fat-tailed returns.
"""
from __future__ import annotations

import itertools
import math
import random
from statistics import NormalDist

import numpy as np
import pandas as pd

EULER_GAMMA = 0.5772156649015329
_N = NormalDist()


def sharpe(r: np.ndarray) -> float:
    sd = r.std(ddof=1)
    return float(r.mean() / sd) if sd > 0 else 0.0


def pbo_cscv(returns: pd.DataFrame, n_blocks: int = 16, max_splits: int = 2000, seed: int = 0) -> dict:
    """returns: T x N daily returns, one column per variant."""
    r = returns.dropna(how="all").fillna(0.0).to_numpy()
    t, n = r.shape
    blocks = np.array_split(np.arange(t), n_blocks)
    combos = list(itertools.combinations(range(n_blocks), n_blocks // 2))
    if len(combos) > max_splits:
        combos = random.Random(seed).sample(combos, max_splits)
    logits, oos_of_best, degradation = [], [], []
    for is_blocks in combos:
        is_idx = np.concatenate([blocks[b] for b in is_blocks])
        oos_idx = np.concatenate([blocks[b] for b in range(n_blocks) if b not in is_blocks])
        is_sr = np.array([sharpe(r[is_idx, j]) for j in range(n)])
        oos_sr = np.array([sharpe(r[oos_idx, j]) for j in range(n)])
        best = int(is_sr.argmax())
        rank = (oos_sr < oos_sr[best]).sum() + 0.5 * ((oos_sr == oos_sr[best]).sum() - 1)
        w = (rank + 0.5) / n                       # relative OOS rank in (0, 1)
        logits.append(math.log(w / (1 - w)))
        oos_of_best.append(oos_sr[best])
        degradation.append(is_sr[best] - oos_sr[best])
    logits = np.array(logits)
    return {"pbo": float((logits <= 0).mean()), "splits": len(combos), "variants": n,
            "median_oos_sharpe_of_is_best_daily": float(np.median(oos_of_best)),
            "share_is_best_positive_oos": float((np.array(oos_of_best) > 0).mean()),
            "median_sharpe_degradation_daily": float(np.median(degradation))}


def expected_max_sharpe(sharpes: np.ndarray, n_trials: int | None = None) -> float:
    """Sharpe the best of N skill-less variants would reach by chance (same dispersion as observed)."""
    n = n_trials or len(sharpes)
    sd = float(np.std(sharpes, ddof=1)) if len(sharpes) > 1 else 0.0
    if n < 2 or sd == 0:
        return 0.0
    return sd * ((1 - EULER_GAMMA) * _N.inv_cdf(1 - 1 / n) + EULER_GAMMA * _N.inv_cdf(1 - 1 / (n * math.e)))


def deflated_sharpe(r: np.ndarray, sr0: float) -> float:
    """P(true Sharpe > sr0) for daily returns r, adjusted for skew and kurtosis (Bailey & López de Prado)."""
    r = r[~np.isnan(r)]
    t = len(r)
    sr = sharpe(r)
    if t < 3:
        return float("nan")
    z = (r - r.mean()) / r.std(ddof=1)
    skew, kurt = float((z ** 3).mean()), float((z ** 4).mean())
    denom = math.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr ** 2, 1e-12))
    return _N.cdf((sr - sr0) * math.sqrt(t - 1) / denom)


def overfit_report(returns: pd.DataFrame, n_trials: int | None = None, **pbo_kw) -> dict:
    """PBO across all variants plus the deflated Sharpe of the best one."""
    r = returns.dropna(how="all").fillna(0.0)
    srs = np.array([sharpe(r[c].to_numpy()) for c in r.columns])
    best = r.columns[int(srs.argmax())]
    sr0 = expected_max_sharpe(srs, n_trials)
    return {"best_variant": str(best), "best_sharpe_annual": float(srs.max() * math.sqrt(365)),
            "luck_threshold_sharpe_annual": float(sr0 * math.sqrt(365)), "trials": n_trials or len(srs),
            "deflated_sharpe_prob": deflated_sharpe(r[best].to_numpy(), sr0),
            "share_variants_positive": float((srs > 0).mean()),
            **pbo_cscv(r, **pbo_kw)}


# Risk settings combined with the "trend" mode (the hybrid runs without stops, like buy-and-hold).
RISK_VARIANTS = {
    "tp2": {"sl_source": "atr", "atr_sl_mult": 1.5, "reward_risk": 2.0},      # take-profit at 2x the stop
    "ride15": {"sl_source": "atr", "atr_sl_mult": 1.5, "reward_risk": 100.0},  # no take-profit, 1.5x-ATR stop
    "ride3": {"sl_source": "atr", "atr_sl_mult": 3.0, "reward_risk": 100.0},   # no take-profit, 3x-ATR stop
}
SIGNAL_GRID = {"emas": [(10, 30), (20, 50), (50, 100)], "long": [100, 200], "adx_min": [0, 20, 30]}


def variant_grid(cfg, start: str, end: str, log_every: int = 10) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run every variant of the trend family; return (daily returns T x N, summary per variant)."""
    import logging

    from .backtest import Workbench
    from .config import with_risk
    from .strategies.baselines import BuyAndHold, EmaTrendParam
    log = logging.getLogger(__name__)
    wb = Workbench(cfg)
    specs = []
    for (fast, slow), long, adx in itertools.product(SIGNAL_GRID["emas"], SIGNAL_GRID["long"], SIGNAL_GRID["adx_min"]):
        for rname, risk in RISK_VARIANTS.items():
            specs.append((EmaTrendParam(fast, slow, long, adx, "trend"), rname, risk))
        specs.append((EmaTrendParam(fast, slow, long, adx, "hybrid"), "nostops", {}))
    rets, rows = {}, []
    for i, (strat, rname, risk) in enumerate(specs, 1):
        res, m = wb.run(strat, cfg=with_risk(cfg, **risk), start=start, end=end)
        key = f"{strat.name}|{rname}"
        eq = res.equity.resample("1D").last().dropna()
        rets[key] = eq.pct_change()
        rows.append({"variant": key, "total_return": m["total_return"], "sharpe": m["sharpe"],
                     "max_drawdown": m["max_drawdown"], "trades": m["trades"]})
        if i % log_every == 0:
            log.info("variant %d/%d done", i, len(specs))
    bh_res, bh = wb.run(BuyAndHold(), start=start, end=end)
    rets["buy_and_hold"] = bh_res.equity.resample("1D").last().dropna().pct_change()
    rows.append({"variant": "buy_and_hold", "total_return": bh["total_return"], "sharpe": bh["sharpe"],
                 "max_drawdown": bh["max_drawdown"], "trades": bh["trades"]})
    return pd.DataFrame(rets).iloc[1:], pd.DataFrame(rows).sort_values("sharpe", ascending=False)
