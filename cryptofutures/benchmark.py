"""Benchmark suite: run several strategies on identical data, rank them, and keep
a running history so every prompt / model / risk change can be compared."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .backtest import Workbench, make_strategy
from .config import Config
from .metrics import per_symbol

log = logging.getLogger(__name__)

COLUMNS = ["strategy", "total_return", "cagr", "sharpe", "sortino", "max_drawdown", "calmar", "trades",
           "win_rate", "profit_factor", "avg_leverage", "liquidations", "directional_accuracy", "final_equity"]
PCT = {"total_return", "cagr", "max_drawdown", "win_rate", "directional_accuracy"}


def format_table(df: pd.DataFrame) -> str:
    cols = [c for c in COLUMNS if c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df[cols].iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, str):
                cells.append(v)
            elif v is None or v != v:
                cells.append("-")
            elif c in PCT:
                cells.append(f"{v * 100:.1f}%")
            elif c in ("trades", "liquidations"):
                cells.append(f"{int(v)}")
            else:
                cells.append(f"{v:.2f}")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def run_benchmark(cfg: Config, strategies: list[str], start: str, end: str, out_dir: str | Path = "results",
                  tag: str = "", rank_by: str = "sharpe") -> tuple[pd.DataFrame, Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = Path(out_dir) / f"{stamp}{'_' + tag if tag else ''}"
    run_dir.mkdir(parents=True, exist_ok=True)
    wb = Workbench(cfg)
    rows, curves = [], {}
    for name in strategies:
        strat = make_strategy(name, cfg)
        log.info("running %s on %d symbols %s -> %s", strat.name, len(wb.symbols), start, end)
        res, m = wb.run(strat, start=start, end=end)
        rows.append({"strategy": strat.name, **m})
        curves[strat.name] = res.equity
        safe = strat.name.replace("/", "_").replace(":", "_").replace("|", "_")
        if not res.trades.empty:
            res.trades.to_csv(run_dir / f"trades_{safe}.csv", index=False)
            per_symbol(res.trades).to_csv(run_dir / f"symbols_{safe}.csv")
        pd.concat([d.assign(symbol=s) for s, d in res.decisions.items()]).to_csv(run_dir / f"decisions_{safe}.csv")

    board = pd.DataFrame(rows).sort_values(rank_by, ascending=False).reset_index(drop=True)
    board.to_csv(run_dir / "leaderboard.csv", index=False)
    pd.DataFrame(curves).resample("1D").last().to_csv(run_dir / "equity_daily.csv")
    header = (f"# Benchmark {stamp}{' - ' + tag if tag else ''}\n\n"
              f"Period: {start} -> {end} | Symbols: {', '.join(wb.symbols)} | "
              f"Decision every {cfg.risk.decision_hours}h | Start equity {cfg.exchange.initial_equity:,.0f} USDT\n\n"
              f"Risk: {json.dumps(asdict(cfg.risk))}\n\n")
    (run_dir / "leaderboard.md").write_text(header + format_table(board) + "\n")
    _plot(curves, run_dir / "equity.png")

    with open(Path(out_dir) / "history.jsonl", "a") as fh:
        for r in rows:
            fh.write(json.dumps({"run": run_dir.name, "start": start, "end": end, "symbols": wb.symbols,
                                 "risk": asdict(cfg.risk), "llm_model": cfg.llm.model, **r}, default=float) + "\n")
    return board, run_dir


def load_history(out_dir: str | Path = "results") -> pd.DataFrame:
    path = Path(out_dir) / "history.jsonl"
    if not path.exists():
        return pd.DataFrame()
    return pd.DataFrame([json.loads(line) for line in path.read_text().splitlines() if line.strip()])


def _plot(curves: dict[str, pd.Series], path: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for name, s in curves.items():
        s.resample("1D").last().plot(ax=ax, label=name, lw=1.4)
    ax.set_ylabel("equity (USDT)")
    ax.set_title("Paper-trading equity")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def leverage_sweep(cfg: Config, strategies: list[str], levels: list[int], guards: list[str], start: str, end: str,
                   out_dir: str | Path = "results", tag: str = "") -> tuple[pd.DataFrame, Path]:
    """Replay each strategy's decisions at forced leverage levels and liquidation-guard modes.

    Decisions are computed once (cached for model strategies), so the sweep costs no model calls.
    """
    from .config import with_risk
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = Path(out_dir) / f"leverage_{stamp}{'_' + tag if tag else ''}"
    run_dir.mkdir(parents=True, exist_ok=True)
    wb = Workbench(cfg)
    rows, curves = [], {}
    initial = cfg.exchange.initial_equity
    for name in strategies:
        strat = make_strategy(name, cfg)
        decisions = wb.decisions(strat, start, end)
        for guard in guards:
            for lev in levels:
                c = with_risk(cfg, leverage_override=lev, max_leverage=max(lev, cfg.risk.max_leverage), liq_guard=guard)
                res, m = wb.run(strat, decisions=decisions, cfg=c, start=start, end=end)
                eq = res.equity
                rows.append({"strategy": strat.name, "guard": guard, "leverage": lev,
                             "total_return": m.get("total_return"), "max_drawdown": m.get("max_drawdown"),
                             "sharpe": m.get("sharpe"), "trades": m.get("trades", 0),
                             "liquidations": m.get("liquidations", 0), "stop_losses": m.get("stop_losses", 0),
                             "avg_leverage": m.get("avg_leverage"), "min_equity_pct": float(eq.min() / initial),
                             "blown_up": bool(eq.min() < 0.1 * initial)})
                curves[f"{strat.name} {guard} {lev}x"] = eq
                log.info("%s %s %dx: %+.1f%%", strat.name, guard, lev, 100 * (m.get("total_return") or 0))
    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "leverage_sweep.csv", index=False)
    pd.DataFrame(curves).resample("1D").last().to_csv(run_dir / "equity_daily.csv")
    (run_dir / "leverage_sweep.md").write_text(format_leverage_table(df) + "\n")
    _plot_leverage(df, run_dir / "leverage.png")
    return df, run_dir


def format_leverage_table(df: pd.DataFrame) -> str:
    lines = ["| strategy | guard | leverage | return | max DD | Sharpe | trades | liquidations | lowest equity |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in df.itertuples():
        lines.append(f"| {r.strategy} | {r.guard} | {r.leverage}x | {r.total_return * 100:+.1f}% | "
                     f"{r.max_drawdown * 100:.1f}% | {r.sharpe:.2f} | {r.trades} | {r.liquidations} | "
                     f"{r.min_equity_pct * 100:.0f}%{' (blown up)' if r.blown_up else ''} |")
    return "\n".join(lines)


def _plot_leverage(df: pd.DataFrame, path: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for (strat, guard), g in df.groupby(["strategy", "guard"]):
        label = f"{strat} | {guard}"
        axes[0].plot(g.leverage, g.total_return * 100, marker="o", label=label)
        axes[1].plot(g.leverage, g.max_drawdown * 100, marker="o", label=label)
    for ax, title in zip(axes, ["Total return (%)", "Max drawdown (%)"]):
        ax.set_xscale("log")
        ax.set_xticks(sorted(df.leverage.unique()))
        ax.set_xticklabels([f"{x}x" for x in sorted(df.leverage.unique())])
        ax.axhline(0, color="grey", lw=0.8)
        ax.set_title(title)
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def quarterly_report(cfg: Config, strategies: list[str], start: str, end: str, freq: str = "QE") -> pd.DataFrame:
    """Return per calendar quarter (or any pandas period) for each strategy, plus whole-period stats."""
    from .metrics import compute_metrics
    wb = Workbench(cfg)
    rows = {}
    for name in strategies:
        strat = make_strategy(name, cfg)
        res, m = wb.run(strat, start=start, end=end)
        eq = res.equity.resample("1D").last().dropna()
        q = eq.resample(freq).last()
        prev = pd.concat([pd.Series([cfg.exchange.initial_equity], index=[eq.index[0] - pd.Timedelta(days=1)]), q])
        rets = (q / prev.shift(1).iloc[1:].values - 1)
        rets.index = [str(d.year) if freq.startswith("Y") else f"{d.year}Q{(d.month - 1) // 3 + 1}"
                      for d in rets.index]
        rows[strat.name] = {**{k: float(v) for k, v in rets.items()}, "TOTAL": m["total_return"],
                            "Sharpe": m["sharpe"], "max DD": m["max_drawdown"]}
    return pd.DataFrame(rows)


def format_quarterly(df: pd.DataFrame, benchmark: str = "buy_and_hold") -> str:
    cols = list(df.columns)
    lines = ["| period | " + " | ".join(cols) + " |", "|" + "---|" * (len(cols) + 1)]
    for idx, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if idx == "Sharpe":
                cells.append(f"{v:.2f}")
            else:
                beat = (idx not in ("max DD",) and c != benchmark and benchmark in df.columns
                        and v > row[benchmark])
                cells.append(f"{'**' if beat else ''}{v * 100:+.1f}%{'**' if beat else ''}")
        lines.append(f"| {idx} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
