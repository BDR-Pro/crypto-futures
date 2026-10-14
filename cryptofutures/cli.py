"""Command line entry point: `python -m cryptofutures <command>`."""
from __future__ import annotations

import argparse
import json
import logging
import sys

import pandas as pd

from .config import load_config


def _overrides(a: argparse.Namespace) -> dict:
    o: dict = {}
    if getattr(a, "symbols", None):
        o.setdefault("data", {})["symbols"] = [s.strip().upper() for s in a.symbols.split(",")]
    for key, section, field in [("model", "llm", "model"), ("prompt", "llm", "prompt_version"),
                                ("base_url", "llm", "base_url"), ("concurrency", "llm", "concurrency"),
                                ("cache_only", "llm", "cache_only"),
                                ("jev_url", "jev", "base_url"), ("jev_model", "jev", "model"),
                                ("decision_hours", "risk", "decision_hours"), ("max_leverage", "risk", "max_leverage"),
                                ("exchange", "live", "exchange")]:
        val = getattr(a, key, None)
        if val is not None:
            o.setdefault(section, {})[field] = val
    return o


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="cryptofutures", description="LLM-driven crypto futures paper trading")
    p.add_argument("-c", "--config", default="config.toml" if __import__("os").path.exists("config.toml") else None)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, period=True):
        sp.add_argument("--symbols", help="comma separated, default: top 10 from config")
        sp.add_argument("--model", help="LLM model name on your local server, e.g. gpt-oss:20b, qwen3:8b")
        sp.add_argument("--prompt", help="prompt version (v1, v2)")
        sp.add_argument("--base-url", help="OpenAI-compatible endpoint, e.g. http://localhost:11434/v1")
        sp.add_argument("--concurrency", type=int)
        sp.add_argument("--cache-only", action="store_true", default=None,
                        help="use cached LLM answers only; never call the model (misses become FLAT)")
        sp.add_argument("--jev-url", help="Jev-style decision model endpoint, e.g. http://127.0.0.1:8081/v1")
        sp.add_argument("--jev-model", help="model name on the Jev-style server")
        sp.add_argument("--decision-hours", type=int)
        sp.add_argument("--max-leverage", type=int)
        if period:
            sp.add_argument("--start", default="2026-01-01")
            sp.add_argument("--end", default=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d"))

    sp = sub.add_parser("download", help="download historical futures candles + funding (Binance Vision)")
    sp.add_argument("--symbols")
    sp.add_argument("--market", choices=["futures", "spot"], help="default from [data] market")
    sp.add_argument("--interval", help="candle interval, e.g. 1h or 1d (default from [data] base_interval)")
    sp.add_argument("--data-dir", help="default from [data] data_dir")
    sp.add_argument("--start")
    sp.add_argument("--end")
    sp.add_argument("--force", action="store_true")

    sp = sub.add_parser("backtest", help="run one strategy")
    common(sp)
    sp.add_argument("--strategy", default="nimble")

    sp = sub.add_parser("benchmark", help="run several strategies on the same data and rank them")
    common(sp)
    sp.add_argument("--strategies", default="nimble,jev,llm,buy_and_hold,ema_trend,donchian_breakout,rsi_reversion,random")
    sp.add_argument("--tag", default="")
    sp.add_argument("--rank-by", default="sharpe")

    sp = sub.add_parser("optimize", help="walk-forward tuning of SL/TP/leverage/confidence on cached decisions")
    common(sp)
    sp.add_argument("--strategy", default="nimble")
    sp.add_argument("--folds", type=int, default=4)
    sp.add_argument("--trials", type=int, default=60)
    sp.add_argument("--objective", default="sharpe", choices=["sharpe", "sortino", "calmar", "total_return", "return_dd"])

    sp = sub.add_parser("robustness", help="randomized skill-vs-luck tests; keeps the best result as champion")
    common(sp)
    sp.add_argument("--strategies", default="nimble,buy_and_hold,ema_trend")
    sp.add_argument("--permutations", type=int, default=200, help="timing shuffles per strategy")
    sp.add_argument("--windows", type=int, default=60, help="random sub-windows x coin subsets")
    sp.add_argument("--window-days", type=int, default=30)
    sp.add_argument("--risk-draws", type=int, default=30, help="random risk settings to try")
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--tag", default="")

    sp = sub.add_parser("leverage", help="replay strategies at forced leverage levels (incl. extreme) per guard mode")
    common(sp)
    sp.add_argument("--strategies", default="nimble,buy_and_hold")
    sp.add_argument("--levels", default="1,2,3,5,10,20,50,100")
    sp.add_argument("--guards", default="reduce_leverage,tighten_stop,off")
    sp.add_argument("--tag", default="")

    sp = sub.add_parser("quarters", help="per-quarter returns per strategy vs buy-and-hold (bold = beat it)")
    common(sp)
    sp.add_argument("--strategies", default="buy_and_hold,ema_trend")
    sp.add_argument("--yearly", action="store_true", help="calendar years instead of quarters")

    sp = sub.add_parser("overfit", help="72-variant trend family: PBO (CSCV) and deflated Sharpe vs buy-and-hold")
    common(sp)
    sp.add_argument("--blocks", type=int, default=16)
    sp.add_argument("--splits", type=int, default=2000)
    sp.add_argument("--trials", type=int, default=0, help="trials to deflate for (default: number of variants)")
    sp.add_argument("--tag", default="")

    sp = sub.add_parser("history", help="show every benchmark run so far, best first")
    sp.add_argument("--rank-by", default="sharpe")
    sp.add_argument("--top", type=int, default=20)

    sp = sub.add_parser("paper", help="live paper trading on real-time prices (no real orders)")
    common(sp, period=False)
    sp.add_argument("--strategy", default="nimble")
    sp.add_argument("--exchange", help="ccxt exchange id: binanceusdm, okx, bybit, ...")
    sp.add_argument("--poll", type=int, default=30)

    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    cfg = load_config(a.config, _overrides(a))

    if a.cmd == "download":
        from .data import MarketData
        syms = [s.upper() for s in a.symbols.split(",")] if a.symbols else cfg.data.symbols
        MarketData(a.data_dir or cfg.data.data_dir, a.interval or cfg.data.base_interval,
                   a.market or cfg.data.market).download(
            syms, a.start or cfg.data.start, a.end or pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d"), a.force)
        print(f"downloaded {len(syms)} symbols into {a.data_dir or cfg.data.data_dir}/")

    elif a.cmd == "backtest":
        from .backtest import Workbench, make_strategy
        from .metrics import per_symbol
        wb = Workbench(cfg)
        res, m = wb.run(make_strategy(a.strategy, cfg), start=a.start, end=a.end)
        print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()}, indent=2))
        if not res.trades.empty:
            print(per_symbol(res.trades).to_string())

    elif a.cmd == "benchmark":
        from .benchmark import format_table, run_benchmark
        board, run_dir = run_benchmark(cfg, [s.strip() for s in a.strategies.split(",")], a.start, a.end,
                                       tag=a.tag, rank_by=a.rank_by)
        print(format_table(board))
        print(f"\nresults: {run_dir}/")

    elif a.cmd == "optimize":
        from .optimize import walk_forward
        rep = walk_forward(cfg, a.strategy, a.start, a.end, folds=a.folds, n_trials=a.trials, objective=a.objective)
        oos = rep["oos_summary"]
        print(f"Out-of-sample ({a.folds - 1} folds) tuned vs default risk settings for {rep['strategy']}:")
        for k in ("tuned", "default"):
            print(f"  {k:8s} " + ", ".join(f"{n}={v:.3f}" for n, v in oos[k].items()))
        if not rep["tuning_helps_out_of_sample"]:
            print("Tuning did NOT beat the current settings on unseen data (it overfit) - keep your current [risk].")
        print("Recommended [risk] settings (also in results/best_risk_*.toml):")
        print(json.dumps(rep["recommended"], indent=2))

    elif a.cmd == "robustness":
        from datetime import datetime, timezone
        from pathlib import Path

        from .robustness import RobustnessSuite, format_report, update_champion
        suite = RobustnessSuite(cfg, a.start, a.end, seed=a.seed)
        reports = [suite.evaluate(spec.strip(), n_perm=a.permutations, n_windows=a.windows,
                                  window_days=a.window_days, n_risk=a.risk_draws)
                   for spec in a.strategies.split(",")]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out = Path("results") / f"robustness_{stamp}{'_' + a.tag if a.tag else ''}"
        out.mkdir(parents=True, exist_ok=True)
        table = format_report(reports)
        (out / "report.json").write_text(json.dumps(reports, indent=2, default=float))
        (out / "report.md").write_text(f"# Robustness {a.start} -> {a.end}\n\n{table}\n")
        champ, promoted = update_champion(reports)
        print(table)
        print(f"\nchampion: {champ['strategy']} (robust score {champ['robust_score']*100:+.2f})"
              + (" - NEW" if promoted else " - unchanged"))
        print(f"results: {out}/")

    elif a.cmd == "leverage":
        from .benchmark import format_leverage_table, leverage_sweep
        df, run_dir = leverage_sweep(cfg, [x.strip() for x in a.strategies.split(",")],
                                     [int(x) for x in a.levels.split(",")], [g.strip() for g in a.guards.split(",")],
                                     a.start, a.end, tag=a.tag)
        print(format_leverage_table(df))
        print(f"\nresults: {run_dir}/")

    elif a.cmd == "quarters":
        from .benchmark import format_quarterly, quarterly_report
        print(format_quarterly(quarterly_report(cfg, [x.strip() for x in a.strategies.split(",")], a.start, a.end,
                                                freq="YE" if a.yearly else "QE")))

    elif a.cmd == "overfit":
        from datetime import datetime, timezone
        from pathlib import Path

        from .overfit import overfit_report, variant_grid
        rets, summary = variant_grid(cfg, a.start, a.end)
        variants = rets.drop(columns=["buy_and_hold"])
        rep = overfit_report(variants, n_trials=a.trials or None, n_blocks=a.blocks, max_splits=a.splits)
        bh = summary[summary.variant == "buy_and_hold"].iloc[0]
        rep["variants_beating_buy_and_hold_sharpe"] = float((summary[summary.variant != "buy_and_hold"].sharpe
                                                             > bh.sharpe).mean())
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out = Path("results") / f"overfit_{stamp}{'_' + a.tag if a.tag else ''}"
        out.mkdir(parents=True, exist_ok=True)
        rets.to_csv(out / "daily_returns.csv")
        summary.to_csv(out / "variants.csv", index=False)
        (out / "report.json").write_text(json.dumps(rep, indent=2, default=float))
        print(summary.head(12).to_string(index=False))
        print("...\n" + summary.tail(4).to_string(index=False))
        print(json.dumps(rep, indent=2, default=float))
        print(f"results: {out}/")

    elif a.cmd == "history":
        from .benchmark import format_table, load_history
        h = load_history()
        if h.empty:
            print("no benchmark runs yet - run `cryptofutures benchmark` first")
            return
        h = h.sort_values(a.rank_by, ascending=False).head(a.top)
        h["strategy"] = h["run"] + " " + h["strategy"]
        print(format_table(h))

    elif a.cmd == "paper":
        from .backtest import make_strategy
        from .live import LivePaperTrader
        LivePaperTrader(cfg, make_strategy(a.strategy, cfg), poll_seconds=a.poll).run()


if __name__ == "__main__":
    sys.exit(main())
