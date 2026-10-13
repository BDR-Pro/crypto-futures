"""Randomized robustness tests: is a result skill, or luck?

A single backtest number says little: one window, one coin set, one path. These tests
reuse a strategy's (cached) decisions and re-run the paper exchange many times:

* timing permutation - shuffle each coin's decisions in time, keeping the exact mix of
  LONG/SHORT/FLAT calls, confidences, leverage and stops. If the real ordering doesn't beat
  most shuffles, the model's timing carries no information (p-value = share of shuffles
  that do at least as well).
* trade bootstrap - resample the realised trades with replacement for a confidence
  interval on total PnL.
* random windows - many random sub-periods and random coin subsets; how often does the
  strategy beat buy-and-hold on the very same window and coins?
* risk perturbation - random risk settings around the current ones; a result that only
  holds for one exact setting is fragile.

The champion file keeps the best robust result so far, so each new model, prompt or risk
setting is judged against it on the same randomized tests.
"""
from __future__ import annotations

import json
import random
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import Workbench, make_strategy
from .config import Config, utc, with_risk
from .metrics import compute_metrics
from .optimize import SEARCH_SPACE
from .strategies.baselines import BuyAndHold


def shuffle_decisions(decisions: dict[str, pd.DataFrame], rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    """Permute each coin's decision rows in time; keeps the decision mix, changes only timing."""
    out = {}
    for sym, d in decisions.items():
        perm = rng.permutation(len(d))
        out[sym] = pd.DataFrame(d.to_numpy()[perm], index=d.index, columns=d.columns)
    return out


def bootstrap_trades(trades: pd.DataFrame, initial: float, n: int = 2000, seed: int = 0) -> dict:
    if trades.empty:
        return {"n_trades": 0}
    rng = np.random.default_rng(seed)
    pnl = trades["pnl"].to_numpy()
    sums = pnl[rng.integers(0, len(pnl), size=(n, len(pnl)))].sum(axis=1) / initial
    return {"n_trades": int(len(pnl)), "return_p05": float(np.percentile(sums, 5)),
            "return_p50": float(np.percentile(sums, 50)), "return_p95": float(np.percentile(sums, 95)),
            "prob_positive": float((sums > 0).mean())}


def _slice(decisions: dict[str, pd.DataFrame], start, end, symbols=None) -> dict[str, pd.DataFrame]:
    s, e = utc(start), utc(end)
    return {k: d[(d.index >= s) & (d.index < e)] for k, d in decisions.items() if symbols is None or k in symbols}


class RobustnessSuite:
    def __init__(self, cfg: Config, start: str, end: str, seed: int = 0):
        self.cfg, self.start, self.end, self.seed = cfg, start, end, seed
        self.wb = Workbench(cfg)
        self.bh = BuyAndHold()
        self.bh_decisions = self.wb.decisions(self.bh, start, end)

    def _ret(self, strat, decisions, cfg=None, start=None, end=None) -> dict:
        _, m = self.wb.run(strat, decisions=decisions, cfg=cfg, start=start or self.start, end=end or self.end)
        return m

    def evaluate(self, spec: str, n_perm: int = 200, n_windows: int = 60, window_days: int = 30,
                 coin_fraction: float = 0.6, n_risk: int = 30) -> dict:
        strat = make_strategy(spec, self.cfg)
        decisions = self.wb.decisions(strat, self.start, self.end)
        res, base = self.wb.run(strat, decisions=decisions, start=self.start, end=self.end)
        rng = np.random.default_rng(self.seed)
        initial = self.cfg.exchange.initial_equity

        # 1) timing permutation test
        null = np.array([self._ret(strat, shuffle_decisions(decisions, rng))["total_return"] for _ in range(n_perm)])
        perm = {"observed": base["total_return"], "null_mean": float(null.mean()), "null_p05": float(np.percentile(null, 5)),
                "null_p95": float(np.percentile(null, 95)),
                "p_value": float((1 + (null >= base["total_return"]).sum()) / (1 + n_perm))}

        # 2) trade bootstrap
        boot = bootstrap_trades(res.trades, initial, seed=self.seed)

        # 3) random windows x random coin subsets, against buy-and-hold on the same slice
        s0, s1 = utc(self.start), utc(self.end)
        span = (s1 - s0).days - window_days
        excess, wins = [], 0
        syms = list(decisions)
        k = max(1, round(coin_fraction * len(syms)))
        prng = random.Random(self.seed)
        for _ in range(n_windows if span > 0 else 0):
            a = s0 + pd.Timedelta(days=prng.randint(0, span))
            b = a + pd.Timedelta(days=window_days)
            subset = prng.sample(syms, k)
            r = self._ret(strat, _slice(decisions, a, b, subset), start=a, end=b)["total_return"]
            r_bh = self._ret(self.bh, _slice(self.bh_decisions, a, b, subset), start=a, end=b)["total_return"]
            excess.append(r - r_bh)
            wins += r > r_bh
        excess = np.array(excess)
        windows = {"n": int(len(excess)), "window_days": window_days, "coins_per_window": k,
                   "beat_buy_hold_share": float(wins / len(excess)) if len(excess) else float("nan"),
                   "excess_median": float(np.median(excess)) if len(excess) else float("nan"),
                   "excess_p10": float(np.percentile(excess, 10)) if len(excess) else float("nan"),
                   "excess_p90": float(np.percentile(excess, 90)) if len(excess) else float("nan")}

        # 4) risk-setting perturbation
        rets = []
        for _ in range(n_risk):
            params = {key: prng.choice(vals) for key, vals in SEARCH_SPACE.items()}
            if not spec.startswith(("llm", "jev", "nimble")):
                params["sl_source"] = "atr"
            rets.append(self._ret(strat, decisions, cfg=with_risk(self.cfg, **params))["total_return"])
        rets = np.array(rets)
        risk = {"n": int(len(rets)), "return_median": float(np.median(rets)), "return_p10": float(np.percentile(rets, 10)),
                "return_p90": float(np.percentile(rets, 90)), "positive_share": float((rets > 0).mean())}

        bh = self._ret(self.bh, self.bh_decisions)
        return {"strategy": strat.name, "spec": spec, "period": [self.start, self.end],
                "symbols": syms, "risk": asdict(self.cfg.risk), "seed": self.seed,
                "metrics": {k: base.get(k) for k in ("total_return", "sharpe", "max_drawdown", "trades", "win_rate",
                                                      "avg_leverage", "directional_accuracy")},
                "buy_and_hold_return": bh["total_return"],
                "timing_permutation": perm, "trade_bootstrap": boot, "random_windows": windows,
                "risk_perturbation": risk, "robust_score": robust_score(perm, windows)}


def robust_score(perm: dict, windows: dict) -> float:
    """Median excess return over buy-and-hold on random windows, halved unless timing is significant."""
    score = windows.get("excess_median", float("nan"))
    if score != score:
        return float("-inf")
    return score if perm["p_value"] <= 0.10 or score <= 0 else score * 0.5


# ---- champion / challenger --------------------------------------------------------------

def load_champion(path: str | Path = "results/champion.json") -> dict | None:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def update_champion(reports: list[dict], path: str | Path = "results/champion.json") -> tuple[dict, bool]:
    """Promote the best report if it beats the current champion's robust score."""
    best = max(reports, key=lambda r: r["robust_score"])
    current = load_champion(path)
    promoted = current is None or best["robust_score"] > current["robust_score"]
    if promoted:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({**best, "crowned": datetime.now(timezone.utc).isoformat()}, indent=2,
                                         default=float))
    return (best if promoted else current), promoted


def format_report(reports: list[dict]) -> str:
    rows = ["| strategy | return | vs B&H | timing p-value | shuffled median | bootstrap 5–95% | "
            "beats B&H in random windows | median excess | risk-perturbed median | robust score |",
            "|" + "---|" * 10]
    for r in sorted(reports, key=lambda x: x["robust_score"], reverse=True):
        m, p, b, w, k = r["metrics"], r["timing_permutation"], r["trade_bootstrap"], r["random_windows"], r["risk_perturbation"]
        ci = f"{b['return_p05']*100:+.1f}% … {b['return_p95']*100:+.1f}%" if b.get("n_trades") else "-"
        rows.append(f"| {r['strategy']} | {m['total_return']*100:+.1f}% | {(m['total_return']-r['buy_and_hold_return'])*100:+.1f} pts "
                    f"| {p['p_value']:.3f} | {p['null_mean']*100:+.1f}% | {ci} | {w['beat_buy_hold_share']*100:.0f}% "
                    f"| {w['excess_median']*100:+.1f} pts | {k['return_median']*100:+.1f}% | {r['robust_score']*100:+.2f} |")
    return "\n".join(rows)
