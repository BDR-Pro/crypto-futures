"""Walk-forward tuning of the risk layer (SL/TP, leverage, confidence filter, sizing).

Decisions are computed once (LLM answers are cached), then many risk settings are
replayed over them. Parameters are picked on a training window and scored on the
following, unseen window, so the reported improvement is out-of-sample.
"""
from __future__ import annotations

import itertools
import json
import logging
import random
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .backtest import Workbench, make_strategy
from .config import Config, utc, with_risk

log = logging.getLogger(__name__)

SEARCH_SPACE = {
    "sl_source": ["model", "atr"],
    "atr_sl_mult": [1.0, 1.5, 2.0, 3.0, 4.0],
    "reward_risk": [1.0, 1.5, 2.0, 3.0, 100.0],   # 100 = effectively no take-profit (let winners run)
    "max_leverage": [1, 2, 3, 5, 10],
    "min_confidence": [0.0, 0.55, 0.65, 0.75],
    "margin_per_trade": [0.04, 0.08, 0.15],
    "flat_closes": [True, False],
}


def score(m: dict, objective: str, min_trades: int) -> float:
    if m.get("trades", 0) < min_trades:
        return float("-inf")
    if objective == "return_dd":   # return per unit of drawdown, robust to short windows
        return m["total_return"] / max(abs(m["max_drawdown"]), 0.02)
    return m.get(objective, float("-inf"))


def _slice(decisions: dict[str, pd.DataFrame], start, end) -> dict[str, pd.DataFrame]:
    s, e = utc(start), utc(end)
    return {k: d[(d.index >= s) & (d.index < e)] for k, d in decisions.items()}


def _candidates(n_trials: int, seed: int, uses_model_stops: bool) -> list[dict]:
    space = dict(SEARCH_SPACE)
    if not uses_model_stops:
        space["sl_source"] = ["atr"]
    grid = [dict(zip(space, combo)) for combo in itertools.product(*space.values())]
    rng = random.Random(seed)
    rng.shuffle(grid)
    return grid[:n_trials]


def walk_forward(cfg: Config, strategy_name: str, start: str, end: str, folds: int = 4, n_trials: int = 60,
                 objective: str = "sharpe", min_trades: int = 10, seed: int = 0,
                 out_dir: str | Path = "results") -> dict:
    wb = Workbench(cfg)
    strat = make_strategy(strategy_name, cfg)
    log.info("computing decisions for %s once (cached for LLMs)", strat.name)
    decisions = wb.decisions(strat, start, end)
    edges = pd.date_range(utc(start), utc(end), periods=folds + 1)
    candidates = _candidates(n_trials, seed, uses_model_stops=strat.name.startswith(("llm", "jev", "nimble")))
    base_risk = asdict(cfg.risk)

    def evaluate(params: dict, a, b) -> dict:
        c = with_risk(cfg, **params)
        _, m = wb.run(strat, decisions=_slice(decisions, a, b), cfg=c, start=a, end=b)
        return m

    report = {"strategy": strat.name, "objective": objective, "folds": []}
    for k in range(1, folds):
        tr_a, tr_b, te_a, te_b = edges[0], edges[k], edges[k], edges[k + 1]   # expanding train window
        scored = []
        for p in candidates:
            m = evaluate(p, tr_a, tr_b)
            scored.append((score(m, objective, min_trades), p, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        best_p = scored[0][1]
        test_best = evaluate(best_p, te_a, te_b)
        test_default = evaluate({}, te_a, te_b)
        fold = {"train": [str(tr_a), str(tr_b)], "test": [str(te_a), str(te_b)], "best_params": best_p,
                "train_score": scored[0][0], "test_tuned": test_best, "test_default": test_default}
        report["folds"].append(fold)
        log.info("fold %d: train %s..%s best %s=%.3f | test tuned %s=%.3f vs default %.3f", k, tr_a.date(), tr_b.date(),
                 objective, scored[0][0], objective, score(test_best, objective, 0), score(test_default, objective, 0))

    report["oos_summary"] = oos = _oos_summary(report["folds"], objective)
    # Only trust tuning that also won on unseen data; otherwise keep the current settings.
    tuning_helps = (oos["tuned"][f"mean_{objective}"] > oos["default"][f"mean_{objective}"]
                    and oos["tuned"]["compounded_return"] > oos["default"]["compounded_return"])
    report["tuning_helps_out_of_sample"] = tuning_helps
    if tuning_helps:
        # Re-tune on the whole period for the setting to use going forward.
        final = sorted(((score(evaluate(p, edges[0], edges[-1]), objective, min_trades), p) for p in candidates),
                       key=lambda x: x[0], reverse=True)
        report["recommended"] = {**base_risk, **final[0][1]}
    else:
        log.warning("tuned settings did not beat the defaults out-of-sample (overfitting) - keeping current [risk]")
        report["recommended"] = base_risk

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe = strat.name.replace(":", "_").replace("|", "_").replace("/", "_")
    (out / f"optimize_{safe}.json").write_text(json.dumps(report, indent=2, default=float))
    toml = "[risk]\n" + "\n".join(f"{k} = {_toml(v)}" for k, v in report["recommended"].items()) + "\n"
    (out / f"best_risk_{safe}.toml").write_text(toml)
    return report


def _oos_summary(folds: list[dict], objective: str) -> dict:
    def agg(key):
        rets = [f[key]["total_return"] for f in folds]
        compounded = 1.0
        for r in rets:
            compounded *= 1 + r
        return {"compounded_return": compounded - 1,
                f"mean_{objective}": sum(score(f[key], objective, 0) for f in folds) / len(folds),
                "worst_drawdown": min(f[key]["max_drawdown"] for f in folds)}
    return {"tuned": agg("test_tuned"), "default": agg("test_default")}


def _toml(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return json.dumps(v)
    return repr(v)
