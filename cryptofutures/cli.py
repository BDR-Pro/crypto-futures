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
        sp.add_argument("--decision-hours", type=int)
        sp.add_argument("--max-leverage", type=int)
        if period:
            sp.add_argument("--start", default="2026-01-01")
            sp.add_argument("--end", default=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d"))

    sp = sub.add_parser("download", help="download historical futures candles + funding (Binance Vision)")
    sp.add_argument("--symbols")
    sp.add_argument("--start")
    sp.add_argument("--end")
    sp.add_argument("--force", action="store_true")

    sp = sub.add_parser("backtest", help="run one strategy")
    common(sp)
    sp.add_argument("--strategy", default="llm")

    sp = sub.add_parser("benchmark", help="run several strategies on the same data and rank them")
    common(sp)
    sp.add_argument("--strategies", default="llm,buy_and_hold,ema_trend,donchian_breakout,rsi_reversion,random")
    sp.add_argument("--tag", default="")
    sp.add_argument("--rank-by", default="sharpe")

    sp = sub.add_parser("optimize", help="walk-forward tuning of SL/TP/leverage/confidence on cached decisions")
    common(sp)
    sp.add_argument("--strategy", default="llm")
    sp.add_argument("--folds", type=int, default=4)
    sp.add_argument("--trials", type=int, default=60)
    sp.add_argument("--objective", default="sharpe", choices=["sharpe", "sortino", "calmar", "total_return", "return_dd"])

    sp = sub.add_parser("history", help="show every benchmark run so far, best first")
    sp.add_argument("--rank-by", default="sharpe")
    sp.add_argument("--top", type=int, default=20)

    sp = sub.add_parser("paper", help="live paper trading on real-time prices (no real orders)")
    common(sp, period=False)
    sp.add_argument("--strategy", default="llm")
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
        MarketData(cfg.data.data_dir, cfg.data.base_interval).download(
            syms, a.start or cfg.data.start, a.end or pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d"), a.force)
        print(f"downloaded {len(syms)} symbols into {cfg.data.data_dir}/")

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
        print("Recommended [risk] settings (paste into config.toml):")
        print(json.dumps(rep["recommended"], indent=2))

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
