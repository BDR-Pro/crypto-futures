"""Strategy discovery: LLMs write candidate strategies as code, a fast evaluator scores them.

Compute and tokens are cheap, data is not, so the search is built so that cheap trials cannot leak
into the verdict. Everything below is fixed before any search runs:

* Search data: spot daily candles of 43 coins including the dead ones. Candidates are scored on
  2018-01-01 .. 2023-06-30 only, and the panel they are run on is physically cut at the search end.
* Holdout: 2023-07-01 .. today, spot and futures (with funding). It is evaluated once, at the end,
  for the pre-registered pick (best search score) and the next few distinct candidates, so the pick
  cannot be chosen on the holdout.
* Look-ahead check: every candidate is re-run on truncated history; if any past position changes,
  it used future data and is rejected.
* Coins are anonymised (except BTC) and rows are a plain day counter, so code cannot hard-code dates
  or famous coins. Year-like literals and calendar attributes are rejected.
* Every valid trial is counted for the deflated Sharpe ratio and the PBO.

Candidate code is screened (no imports, dunders, file/OS access) and run in a separate process with
a timeout and memory limit. That keeps honest LLM output contained; it is not a security boundary
against deliberately hostile code.
"""
from __future__ import annotations

import ast
import hashlib
import json
import logging
import math
import multiprocessing as mp
import random
import re
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import LLMConfig
from .data import MarketData
from .overfit import deflated_sharpe, expected_max_sharpe, pbo_cscv

log = logging.getLogger(__name__)

SEARCH_START, SEARCH_END, HOLDOUT_START = "2018-01-01", "2023-06-30", "2023-07-01"
COST = 0.0007                      # taker fee 0.05% + slippage 0.02% per unit of traded weight
FIELDS = {"open": "open", "high": "high", "low": "low", "close": "close",
          "volume": "quote_volume", "taker_buy": "taker_buy_quote"}
PERIOD_LABELS = ["P1 bear then recovery", "P2 crash then big bull", "P3 top, bear, early recovery"]

# --------------------------------------------------------------------------------------------- data


@dataclass
class Panel:
    """Daily candles of many coins: one DataFrame per field, rows = days (UTC), columns = anonymised coins."""
    fields: dict[str, pd.DataFrame]
    funding: pd.DataFrame | None        # daily funding rate sum per coin (futures only)
    names: dict[str, str]               # anonymised column -> real symbol

    @property
    def dates(self) -> pd.DatetimeIndex:
        return self.fields["close"].index

    def upto(self, end) -> Panel:
        end = pd.Timestamp(end, tz="UTC")
        cut = {k: v.loc[:end] for k, v in self.fields.items()}
        return replace(self, fields=cut, funding=None if self.funding is None else self.funding.loc[:end])

    def inputs(self) -> dict[str, pd.DataFrame]:
        """What a candidate sees: plain day counter instead of dates."""
        return {k: v.reset_index(drop=True) for k, v in self.fields.items()}


def anonymise(symbols: list[str], seed: int = 0) -> dict[str, str]:
    """Symbol -> column name. BTC keeps its name (a market proxy); others become c01.. in shuffled order."""
    others = sorted(s for s in symbols if s != "BTCUSDT")
    random.Random(seed).shuffle(others)
    out = {"BTCUSDT": "BTC"} if "BTCUSDT" in symbols else {}
    out.update({s: f"c{i + 1:02d}" for i, s in enumerate(others)})
    return out


def load_panel(data_dir: str, symbols: list[str], market: str = "spot") -> Panel:
    md = MarketData(data_dir, "1d", market)
    alias = anonymise([s.removeprefix("1000") for s in symbols])
    candles, funding = {}, {}
    for s in symbols:
        name = alias[s.removeprefix("1000")]
        candles[name] = md.candles(s)     # futures quote 1000SHIB; the price scale is irrelevant to returns
        if market == "futures":
            f = md.funding(s)
            funding[name] = f.resample("1D").sum() if len(f) else pd.Series(dtype=float)
    idx = sorted(set().union(*(df.index for df in candles.values())))
    idx = pd.DatetimeIndex(idx)
    cols = sorted(candles, key=lambda c: (c != "BTC", c))
    fields = {k: pd.DataFrame({c: candles[c][src].reindex(idx) for c in cols}) for k, src in FIELDS.items()}
    fund = None
    if market == "futures":
        fund = pd.DataFrame({c: funding[c].reindex(idx) for c in cols}).fillna(0.0)
    return Panel(fields, fund, {v: k for k, v in alias.items()})


# ----------------------------------------------------------------------------------------- sandbox

class CodeRejected(ValueError):
    pass


SAFE_BUILTINS = {n: __builtins__[n] if isinstance(__builtins__, dict) else getattr(__builtins__, n) for n in (
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float", "int", "isinstance", "len",
    "list", "map", "max", "min", "pow", "range", "reversed", "round", "set", "slice", "sorted", "str", "sum",
    "tuple", "zip", "Exception", "ValueError", "KeyError", "IndexError", "ZeroDivisionError")}
SAFE_BUILTINS["print"] = lambda *a, **k: None
BANNED_NAMES = {"eval", "exec", "compile", "open", "globals", "locals", "vars", "getattr", "setattr", "delattr",
                "input", "breakpoint", "exit", "quit", "memoryview", "type", "object", "super", "help", "dir"}
BANNED_ATTRS = {
    # I/O and OS
    "to_csv", "to_pickle", "to_parquet", "to_json", "to_excel", "to_sql", "to_hdf", "to_feather", "to_clipboard",
    "to_html", "to_latex", "to_markdown", "to_stata", "to_xml", "read_csv", "read_pickle", "read_parquet",
    "read_json", "read_excel", "read_sql", "read_hdf", "read_feather", "read_table", "read_fwf", "read_html",
    "read_xml", "read_clipboard", "load", "loadtxt", "save", "savez", "savez_compressed", "savetxt", "tofile",
    "fromfile", "memmap", "genfromtxt", "fromregex", "system", "popen", "eval", "query", "ctypeslib", "lib",
    "os", "sys", "io", "testing", "api", "options", "set_option", "random",
    # calendar / date logic
    "year", "month", "quarter", "day", "dayofyear", "day_of_year", "isocalendar", "date", "strftime",
    "timestamp", "Timestamp", "to_datetime", "DatetimeIndex", "date_range", "datetime", "Period", "period_range"}
YEAR_RE = re.compile(r"(19|20)\d\d")


def check_code(code: str) -> None:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise CodeRejected(f"syntax error: {e}") from None
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise CodeRejected("imports are not allowed (np, pd and math are provided)")
        if isinstance(node, (ast.With, ast.AsyncWith, ast.AsyncFunctionDef, ast.Await)):
            raise CodeRejected(f"{type(node).__name__} is not allowed")
        if isinstance(node, ast.Name) and (node.id in BANNED_NAMES or node.id.startswith("__")):
            raise CodeRejected(f"name {node.id!r} is not allowed")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr in BANNED_ATTRS):
            raise CodeRejected(f"attribute .{node.attr} is not allowed")
        if isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, str) and YEAR_RE.search(v):
                raise CodeRejected("date-like string literals are not allowed")
            if isinstance(v, int) and not isinstance(v, bool) and 2009 <= v <= 2030:
                raise CodeRejected(f"year-like constant {v} is not allowed")
    if not any(isinstance(n, ast.FunctionDef) and n.name == "strategy" for n in tree.body):
        raise CodeRejected("define a top-level function `strategy(data)`")


def compile_strategy(code: str):
    check_code(code)
    g = {"__builtins__": SAFE_BUILTINS, "np": np, "pd": pd, "math": math}
    exec(compile(code, "<candidate>", "exec"), g)      # noqa: S102 - screened above, run in a child process
    return g["strategy"]


def normalise_positions(pos, close: pd.DataFrame) -> np.ndarray:
    if isinstance(pos, np.ndarray) and pos.shape == close.shape:
        pos = pd.DataFrame(pos, index=close.index, columns=close.columns)
    if not isinstance(pos, pd.DataFrame):
        raise TypeError(f"strategy must return a DataFrame shaped like data['close'], got {type(pos).__name__}")
    arr = pos.reindex(index=close.index, columns=close.columns).to_numpy(dtype=float)
    arr = np.clip(np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0), -1.0, 1.0)
    arr[np.isnan(close.to_numpy(dtype=float))] = 0.0
    return arr


def _child(code: str, inputs: dict, cuts: list[int], conn, mem_gb: float) -> None:
    try:
        import resource
        lim = int(mem_gb * 2 ** 30)
        resource.setrlimit(resource.RLIMIT_AS, (lim, lim))
    except Exception:            # noqa: BLE001 - best effort on platforms without rlimits
        pass
    try:
        fn = compile_strategy(code)
        outs = []
        for n in [None, *cuts]:
            d = {k: (v if n is None else v.iloc[:n]).copy() for k, v in inputs.items()}
            outs.append(normalise_positions(fn(d), d["close"]).astype(np.float64))
        conn.send(("ok", outs))
    except CodeRejected as e:
        conn.send(("rejected", str(e)))
    except Exception as e:       # noqa: BLE001 - any failure of candidate code is reported back to the LLM
        tb = traceback.extract_tb(e.__traceback__)
        where = next((f"line {f.lineno}: {f.line}" for f in reversed(tb) if f.filename == "<candidate>"), "")
        conn.send(("error", f"{type(e).__name__}: {str(e)[:400]} {where}".strip()))
    finally:
        conn.close()


_CTX = None


def run_candidate(code: str, inputs: dict, cuts: list[int] | None = None, timeout: float = 60,
                  mem_gb: float = 4.0) -> tuple[str, object]:
    """Run candidate code in a fresh process. Returns ("ok", [positions, *truncated]) or (status, message)."""
    global _CTX
    if _CTX is None:
        _CTX = mp.get_context("forkserver")
    parent, child = _CTX.Pipe(duplex=False)
    p = _CTX.Process(target=_child, args=(code, inputs, cuts or [], child, mem_gb), daemon=True)
    p.start()
    child.close()
    try:
        if parent.poll(timeout):
            status, payload = parent.recv()
        else:
            status, payload = "timeout", f"no result within {timeout:.0f}s - make it faster (vectorise)"
    except EOFError:
        status, payload = "error", "process died (out of memory?)"
    finally:
        p.join(2)
        if p.is_alive():
            p.kill()
            p.join()
    return status, payload


def leak_check(full: np.ndarray, truncated: list[np.ndarray]) -> str | None:
    for t in truncated:
        n = len(t)
        diff = np.abs(full[:n] - t)
        if (diff > 1e-6).any():
            row = int(np.argwhere(diff > 1e-6)[0][0])
            return (f"look-ahead: positions for day {row} changed when history was cut after day {n - 1} "
                    "(uses future rows, centred windows, bfill or full-sample statistics)")
    return None


# --------------------------------------------------------------------------------------- evaluation

def portfolio_returns(pos: np.ndarray, panel: Panel, mask: np.ndarray | None = None,
                      cost: float = COST) -> pd.Series:
    """Daily returns of the equal-slot portfolio. pos[t] is set at the close of day t, earns day t+1.

    Each trading coin gets 1/N of capital (N = coins trading that day, within mask); its weight is
    position / N, so gross exposure <= 1. Costs on every change of weight; futures pay/receive funding.
    A coin that stops trading is exited at its last close.
    """
    close = panel.fields["close"].to_numpy(dtype=float)
    alive = ~np.isnan(close)
    if mask is not None:
        alive = alive & mask[None, :]
    n_alive = alive.sum(axis=1, keepdims=True)
    w = np.where(alive, pos, 0.0) / np.maximum(n_alive, 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        fwd = close[1:] / close[:-1] - 1.0
    fwd = np.nan_to_num(fwd, nan=0.0, posinf=0.0, neginf=0.0)
    turnover = np.abs(np.diff(np.vstack([np.zeros((1, w.shape[1])), w]), axis=0)).sum(axis=1)
    pnl = (w[:-1] * fwd).sum(axis=1) - cost * turnover[:-1]
    if panel.funding is not None:
        pnl -= (w[:-1] * panel.funding.to_numpy(dtype=float)[1:]).sum(axis=1)
    return pd.Series(pnl, index=panel.dates[1:])


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 2:
        return {"sharpe": 0.0, "cagr": 0.0, "total": 0.0, "max_dd": 0.0, "vol": 0.0}
    eq = (1 + r).cumprod()
    sd = r.std(ddof=1)
    years = len(r) / 365
    return {"sharpe": float(r.mean() / sd * math.sqrt(365)) if sd > 0 else 0.0,
            "cagr": float(eq.iloc[-1] ** (1 / years) - 1) if eq.iloc[-1] > 0 else -1.0,
            "total": float(eq.iloc[-1] - 1), "max_dd": float((eq / eq.cummax() - 1).min()),
            "vol": float(sd * math.sqrt(365))}


class Scorer:
    """Search fitness: Sharpe in 6 cells (2 disjoint coin halves x 3 periods); score = mean - 0.5 * std."""

    def __init__(self, panel: Panel, start: str = SEARCH_START, end: str = SEARCH_END, seed: int = 0):
        self.panel = panel.upto(end)
        self.start, self.end = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
        cols = list(self.panel.fields["close"].columns)
        rng = random.Random(seed)
        order = cols[1:]
        rng.shuffle(order)
        half_a = {cols[0], *order[: len(order) // 2]}
        self.masks = [np.array([c in half_a for c in cols]), np.array([c not in half_a for c in cols])]
        days = self.panel.dates[(self.panel.dates >= self.start) & (self.panel.dates <= self.end)]
        self.periods = [(chunk[0], chunk[-1]) for chunk in np.array_split(days, 3)]
        self.inputs = self.panel.inputs()
        n = len(self.panel.dates)
        first = int(np.searchsorted(self.panel.dates, self.start))
        self.cuts = sorted({first + 120, (first + n) // 2, n - 90})

    def score(self, pos: np.ndarray) -> tuple[dict, pd.Series]:
        full = portfolio_returns(pos, self.panel).loc[self.start:self.end]
        cells = []
        for m in self.masks:
            r = portfolio_returns(pos, self.panel, mask=m)
            cells += [stats(r.loc[a:b])["sharpe"] for a, b in self.periods]
        cells = np.array(cells)
        close = self.panel.fields["close"].to_numpy(dtype=float)
        alive = ~np.isnan(close)
        live_pos = np.where(alive, pos, np.nan)
        rows = (self.panel.dates >= self.start) & (self.panel.dates <= self.end)
        n_alive = np.maximum(alive.sum(1, keepdims=True), 1)
        w = np.where(alive, pos, 0) / n_alive
        m = {"score": float(cells.mean() - 0.5 * cells.std()), "cells": [round(float(c), 3) for c in cells],
             **stats(full),
             "exposure": float(np.nanmean(np.abs(live_pos[rows]))),
             "net_long": float(np.nanmean(live_pos[rows])),
             "turnover_per_year": float(np.abs(np.diff(w[rows], axis=0)).sum(1).mean() * 365)}
        return m, full


def evaluate(code: str, scorer: Scorer, timeout: float = 60) -> dict:
    """Screen, run with look-ahead check, score on the search window."""
    try:
        check_code(code)
    except CodeRejected as e:
        return {"status": "rejected", "error": str(e)}
    status, payload = run_candidate(code, scorer.inputs, scorer.cuts, timeout=timeout)
    if status != "ok":
        return {"status": status, "error": payload}
    full, *truncated = payload
    leak = leak_check(full, truncated)
    if leak:
        return {"status": "lookahead", "error": leak}
    metrics, returns = scorer.score(full)
    if metrics["exposure"] < 0.05:
        return {"status": "inactive", "error": f"average exposure {metrics['exposure']:.1%} - trades almost never",
                "metrics": metrics}
    return {"status": "ok", "metrics": metrics, "returns": returns}


# -------------------------------------------------------------------------------------------- seeds

SEEDS = {
    "buy_and_hold": '''
def strategy(data):
    # Long every coin that trades: the passive benchmark.
    return data["close"].notna().astype(float)
''',
    "donchian_20": '''
def strategy(data):
    # Turtle breakout: long above the prior 20-day high, short below the prior 20-day low, else keep state.
    close, high, low = data["close"], data["high"], data["low"]
    upper = high.rolling(20).max().shift(1)
    lower = low.rolling(20).min().shift(1)
    signal = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    signal[close > upper] = 1.0
    signal[close < lower] = -1.0
    return signal.ffill().fillna(0.0)
''',
    "ema_trend": '''
def strategy(data):
    # EMA20/EMA50 cross filtered by the 200-day EMA: long in uptrends, short in downtrends, flat otherwise.
    close = data["close"]
    fast = close.ewm(span=20, adjust=False).mean()
    slow = close.ewm(span=50, adjust=False).mean()
    trend = close.ewm(span=200, adjust=False).mean()
    up = (fast > slow) & (close > trend)
    down = (fast < slow) & (close < trend)
    return up.astype(float) - down.astype(float)
''',
}

FAMILIES = [
    "cross-sectional momentum or reversal (rank coins against each other)",
    "volatility targeting / risk parity sizing of an existing signal",
    "market breadth regimes (share of coins in uptrends, new highs vs new lows)",
    "BTC-led regime filters for altcoins",
    "order-flow: taker buy share of volume, volume shocks",
    "listing age effects (new coins vs established)",
    "cross-coin dispersion or correlation regimes",
    "drawdown or crash protection rules (risk-off after shocks)",
    "relative value: coins vs BTC (ratio trends or mean reversion)",
    "multi-horizon trend ensembles with graded position sizes",
    "volatility breakout / range compression then expansion",
    "low-volatility or anti-lottery (avoid coins with extreme recent spikes)",
    "liquidity tiers (dollar volume) and their different behaviour",
    "short-term reversal inside a long-term trend (buy dips in uptrends)",
    "an idea of your own that is none of the above",
]

SYSTEM = """You are a quantitative researcher discovering systematic trading strategies for a portfolio of crypto coins (USDT pairs, daily candles). You write each strategy as Python code that is backtested automatically.

API
def strategy(data):
    data: dict of pandas DataFrames; rows = days (integer index 0..T-1, oldest first), columns = coins.
      'open', 'high', 'low', 'close': prices.  'volume': USDT volume.  'taker_buy': USDT volume bought by takers (aggressive buyers).
      Column 'BTC' is Bitcoin. Other columns are anonymous coins c01..c42 (names hidden on purpose).
      Values are NaN before a coin lists and after it is delisted. Coins list and die over time; some collapse to ~0.
    returns: DataFrame shaped like data['close'] (same index and columns) with the target position of each coin
      in [-1, 1] (+1 long, -1 short, 0 flat, fractions allowed). Row t is decided at the close of day t using rows 0..t
      only, and is held from the close of day t to the close of day t+1.

Portfolio: each day capital is split equally across the coins that trade that day; coin weight = position / number of
trading coins, so total gross exposure <= 1 (no leverage). Costs: 0.07% of traded notional on every weight change.
Score: annualised Sharpe ratio of daily portfolio returns in 6 cells (2 disjoint halves of the coins x 3 periods:
P1 bear then recovery, P2 crash then big bull, P3 top, bear and early recovery); score = mean - 0.5 * std of the
6 cells. Consistency across coins and regimes matters more than one great period.

Hard rules (checked automatically; violations are rejected):
- Causal only. Never use future rows: no shift(-k), no centred windows, no bfill, no statistics over the whole
  history (global mean/std/quantile/rank over time). Every candidate is re-run on truncated history and rejected if
  any past position changes. Cross-sectional operations within the same row (e.g. rank across coins) are fine.
- No imports: np, pd and math are available. No file, network or OS access. No randomness.
- No dates, calendars or hard-coded row numbers.
- Must finish in under 20 seconds on ~2,200 days x 43 coins: prefer vectorised pandas/numpy.
- Handle NaN (coins not trading). Return a DataFrame.

Prefer few parameters and round values (e.g. 20, 50, 100 days); every extra knob makes a lucky fit more likely.
Ideas must make sense as persistent market behaviour, not as a fit to this sample.

Example (Donchian breakout, a known benchmark):
```python
def strategy(data):
    close, high, low = data["close"], data["high"], data["low"]
    upper = high.rolling(20).max().shift(1)
    lower = low.rolling(20).min().shift(1)
    signal = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    signal[close > upper] = 1.0
    signal[close < lower] = -1.0
    return signal.ffill().fillna(0.0)
```

Answer format, exactly:
IDEA: <short name, max 8 words>
HYPOTHESIS: <1-3 sentences: the market behaviour exploited and why it should persist>
```python
def strategy(data):
    ...
```"""


# ------------------------------------------------------------------------------------------- search

def _fmt_metrics(m: dict) -> str:
    return (f"score {m['score']:+.3f} | cells {m['cells']} | Sharpe {m['sharpe']:.2f} | CAGR {m['cagr']:+.1%} | "
            f"maxDD {m['max_dd']:.1%} | exposure {m['exposure']:.2f} | net long {m['net_long']:+.2f} | "
            f"turnover/yr {m['turnover_per_year']:.1f}")


def parse_answer(text: str) -> tuple[str, str, str | None]:
    idea = re.search(r"IDEA:\s*(.+)", text)
    hyp = re.search(r"HYPOTHESIS:\s*(.+?)(?:\n\s*\n|```)", text, re.S)
    blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    code = next((b for b in reversed(blocks) if "def strategy" in b), None)
    return ((idea.group(1).strip()[:80] if idea else "unnamed"),
            (hyp.group(1).strip()[:600] if hyp else ""), code)


class Discovery:
    """LLM-driven evolutionary search. State lives in out_dir (candidates.jsonl + returns/), so runs resume."""

    def __init__(self, panel: Panel, out_dir: Path, models: list[str], budget_usd: float = 25.0,
                 llm_concurrency: int = 6, eval_workers: int = 3, seed: int = 0, reasoning: str = "medium"):
        self.scorer = Scorer(panel)
        self.out = Path(out_dir)
        (self.out / "returns").mkdir(parents=True, exist_ok=True)
        self.models, self.budget, self.reasoning = models, budget_usd, reasoning
        self.llm_concurrency = llm_concurrency
        self.eval_sem = threading.Semaphore(eval_workers)
        self.lock = threading.Lock()
        self.rng = random.Random(seed)
        self.records: list[dict] = []
        self.returns: dict[str, pd.Series] = {}
        self.spent = 0.0
        self._load()

    # -- state
    def _load(self) -> None:
        path = self.out / "candidates.jsonl"
        if not path.exists():
            return
        for line in path.read_text().splitlines():
            rec = json.loads(line)
            self.records.append(rec)
            self.spent += rec.get("cost", 0.0)
            f = self.out / "returns" / f"{rec['id']}.csv"
            if rec["status"] == "ok" and f.exists():
                s = pd.read_csv(f, index_col=0).iloc[:, 0]
                s.index = pd.to_datetime(s.index, utc=True)
                self.returns[rec["id"]] = s
        log.info("resumed %d candidates, $%.2f spent", len(self.records), self.spent)

    def _save(self, rec: dict, returns: pd.Series | None) -> None:
        with self.lock:
            rec["id"] = f"c{len(self.records):04d}"
            self.records.append(rec)
            if returns is not None:
                self.returns[rec["id"]] = returns
                returns.rename("r").to_csv(self.out / "returns" / f"{rec['id']}.csv")
            with open(self.out / "candidates.jsonl", "a") as fh:
                fh.write(json.dumps(rec) + "\n")

    def ok(self) -> list[dict]:
        return sorted((r for r in self.records if r["status"] == "ok"), key=lambda r: -r["metrics"]["score"])

    def seed(self) -> None:
        have = {r["code_hash"] for r in self.records}
        for name, code in SEEDS.items():
            h = _hash(code)
            if h in have:
                continue
            res = evaluate(code, self.scorer)
            self._save({"model": "seed", "mode": "seed", "parents": [], "idea": name, "hypothesis": "known baseline",
                        "code": code, "code_hash": h, "status": res["status"], "error": res.get("error"),
                        "metrics": res.get("metrics"), "cost": 0.0}, res.get("returns"))

    # -- prompts
    def _archive_table(self, k: int = 10) -> str:
        rows = [f"- {r['id']} [{r['idea']}] {_fmt_metrics(r['metrics'])}" for r in self.ok()[:k]]
        return "\n".join(rows) or "(empty)"

    def _recent(self, k: int = 40) -> str:
        rows = []
        for r in self.records[-k:]:
            tail = f"score {r['metrics']['score']:+.3f}" if r["status"] == "ok" else r["status"]
            rows.append(f"- {r['idea']} -> {tail}")
        return "\n".join(rows)

    def _pick_parent(self, exclude: str | None = None) -> dict:
        pool = [r for r in self.ok()[:20] if r["id"] != exclude] or self.ok()
        weights = [1.0 / (i + 2) for i in range(len(pool))]
        return self.rng.choices(pool, weights=weights)[0]

    def make_prompt(self) -> tuple[str, str, list[str]]:
        with self.lock:
            bh = next((r for r in self.records if r["idea"] == "buy_and_hold" and r["status"] == "ok"), None)
            head = (f"Benchmark buy-and-hold: {_fmt_metrics(bh['metrics'])}\n\n" if bh else "")
            head += f"Best strategies so far:\n{self._archive_table()}\n\nRecently tried (avoid repeating):\n{self._recent()}\n\n"
            roll = self.rng.random()
            if roll < 0.4 or len(self.ok()) < 4:
                fam = self.rng.choice(FAMILIES)
                return "novel", head + (
                    f"Task: propose a NEW strategy that is materially different from the ones above. "
                    f"Explore this direction: {fam}. It may be combined with a trend or risk filter if that is "
                    f"essential to the idea."), []
            p1 = self._pick_parent()
            if roll < 0.75:
                return "improve", head + (
                    f"Parent {p1['id']} [{p1['idea']}]: {p1['hypothesis']}\n{_fmt_metrics(p1['metrics'])}\n"
                    f"```python\n{p1['code'].strip()}\n```\n\n"
                    "Task: improve the parent's score with a structural change (better exit, sizing, filter, or "
                    "fixing its weakest cell). Do not just nudge parameters."), [p1["id"]]
            p2 = self._pick_parent(exclude=p1["id"])
            corr = self._corr(p1["id"], p2["id"])
            return "combine", head + (
                f"Parent A {p1['id']} [{p1['idea']}]: {_fmt_metrics(p1['metrics'])}\n```python\n{p1['code'].strip()}\n```\n"
                f"Parent B {p2['id']} [{p2['idea']}]: {_fmt_metrics(p2['metrics'])}\n```python\n{p2['code'].strip()}\n```\n"
                f"Correlation of their daily returns: {corr:.2f}\n\n"
                "Task: combine the two into one strategy that is better than both (e.g. blend positions, use one as "
                "a filter for the other, or switch by regime)."), [p1["id"], p2["id"]]

    def _corr(self, a: str, b: str) -> float:
        if a in self.returns and b in self.returns:
            return float(self.returns[a].corr(self.returns[b]))
        return float("nan")

    # -- LLM
    def _chat(self, model: str, messages: list[dict]) -> tuple[str, float]:
        from .strategies.llm import LLMClient
        client = LLMClient(LLMConfig(base_url="https://openrouter.ai/api/v1", model=model, timeout=600))
        payload = {"model": model, "messages": messages, "max_tokens": 16000, "temperature": 0.9,
                   "usage": {"include": True}}
        if self.reasoning:
            payload["reasoning"] = {"effort": self.reasoning}
        resp = client._post("https://openrouter.ai/api/v1/chat/completions", payload,
                            {"Authorization": f"Bearer {client.api_key()}"}, attempts=5)
        if resp.status_code == 402:
            raise BudgetExhausted("OpenRouter credit exhausted (HTTP 402)")
        resp.raise_for_status()
        body = resp.json()
        cost = float((body.get("usage") or {}).get("cost") or 0.0)
        msg = body["choices"][0]["message"]
        return msg.get("content") or "", cost

    def step(self, model: str) -> dict | None:
        mode, prompt, parents = self.make_prompt()
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
        total_cost = 0.0
        for attempt in range(2):                     # one repair round on failure
            text, cost = self._chat(model, messages)
            total_cost += cost
            idea, hyp, code = parse_answer(text)
            if code is None:
                res = {"status": "no_code", "error": "answer contained no ```python block with def strategy"}
                h = None
            else:
                h = _hash(code)
                with self.lock:
                    dup = next((r for r in self.records if r.get("code_hash") == h), None)
                if dup:
                    res = {"status": "duplicate", "error": f"identical to {dup['id']}"}
                else:
                    with self.eval_sem:
                        res = evaluate(code, self.scorer)
            if res["status"] in ("ok", "duplicate") or attempt == 1:
                break
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": f"That failed: {res['status']}: {res['error']}\n"
                                                     "Fix it and answer again in the same format."}]
        rec = {"model": model, "mode": mode, "parents": parents, "idea": idea, "hypothesis": hyp, "code": code,
               "code_hash": h, "status": res["status"], "error": res.get("error"), "metrics": res.get("metrics"),
               "cost": total_cost, "repaired": attempt == 1}
        if res["status"] == "ok":
            rets = res["returns"]
            with self.lock:
                corrs = {k: float(rets.corr(v)) for k, v in self.returns.items()}
            if corrs:
                near = max(corrs, key=corrs.get)
                rec["max_corr"] = [near, round(corrs[near], 3)]
        self._save(rec, res.get("returns"))
        with self.lock:
            self.spent += total_cost
        return rec

    def run(self, n_candidates: int) -> None:
        self.seed()
        target = len(self.records) + n_candidates
        stop = threading.Event()

        def worker(i: int) -> None:
            k = i
            while not stop.is_set():
                with self.lock:
                    if len(self.records) >= target or self.spent >= self.budget:
                        stop.set()
                        return
                model = self.models[k % len(self.models)]
                k += self.llm_concurrency
                try:
                    rec = self.step(model)
                except BudgetExhausted as e:
                    log.warning("%s", e)
                    stop.set()
                    return
                except Exception as e:        # noqa: BLE001 - keep the search alive on transient API errors
                    log.warning("%s failed: %s", model, e)
                    time.sleep(10)
                    continue
                m = rec.get("metrics") or {}
                best = self.ok()[0]
                log.info("%s %-22s %-8s %-10s %-45s %s | best %s %.3f | $%.2f", rec["id"], model.split("/")[-1][:22],
                         rec["mode"], rec["status"], rec["idea"][:45],
                         f"{m['score']:+.3f}" if rec["status"] == "ok" else "", best["id"], best["metrics"]["score"],
                         self.spent)

        with ThreadPoolExecutor(self.llm_concurrency) as ex:
            list(ex.map(worker, range(self.llm_concurrency)))


class BudgetExhausted(RuntimeError):
    pass


def _hash(code: str) -> str:
    norm = "\n".join(line.rstrip() for line in code.strip().splitlines() if line.strip() and not line.strip().startswith("#"))
    return hashlib.sha1(norm.encode()).hexdigest()[:16]


# ------------------------------------------------------------------------------------------- report

def holdout_eval(code: str, panel: Panel, start: str = HOLDOUT_START) -> dict:
    status, payload = run_candidate(code, panel.inputs(), timeout=120)
    if status != "ok":
        return {"status": status, "error": payload}
    r = portfolio_returns(payload[0], panel).loc[pd.Timestamp(start, tz="UTC"):]
    return {"status": "ok", **stats(r), "returns": r}


def btc_hold(panel: Panel, start: str) -> dict:
    close = panel.fields["close"]["BTC"]
    r = close.pct_change().loc[pd.Timestamp(start, tz="UTC"):].dropna()
    return {"status": "ok", **stats(r), "returns": r}


def finalize(out_dir: Path, spot: Panel, futures: Panel | None, top_k: int = 5, max_corr: float = 0.9) -> str:
    """Overfitting statistics on the search window, then the one-time holdout for the pre-registered pick."""
    d = Discovery.__new__(Discovery)
    d.out, d.records, d.returns, d.spent = Path(out_dir), [], {}, 0.0
    d._load()
    ok = [r for r in d.ok() if r["model"] != "seed"]
    seeds = {r["idea"]: r for r in d.records if r["model"] == "seed" and r["status"] == "ok"}
    status_counts = pd.Series([r["status"] for r in d.records if r["model"] != "seed"]).value_counts().to_dict()
    # Distinct finalists: walk down the search ranking, skip near-copies of an already chosen one.
    finalists = []
    for r in ok:
        if all(abs(d.returns[r["id"]].corr(d.returns[f["id"]])) < max_corr for f in finalists):
            finalists.append(r)
        if len(finalists) == top_k:
            break
    # Overfitting statistics over every valid LLM candidate (the trials).
    rets = pd.DataFrame({r["id"]: d.returns[r["id"]] for r in ok})
    srs = np.array([rets[c].mean() / rets[c].std() for c in rets.columns])
    sr0 = expected_max_sharpe(srs, len(srs))
    best = finalists[0]
    pbo = pbo_cscv(rets, n_blocks=16, max_splits=2000) if rets.shape[1] > 2 else {}
    overfit = {"trials": len(srs), "luck_threshold_sharpe_annual": sr0 * math.sqrt(365),
               "pick_sharpe_annual": best["metrics"]["sharpe"],
               "deflated_sharpe_prob": deflated_sharpe(d.returns[best["id"]].to_numpy(), sr0), **pbo}
    # One-time holdout.
    rows = []
    entries = [(f"**{f['id']}** {f['idea']}" + (" (pick)" if i == 0 else ""), f) for i, f in enumerate(finalists)]
    entries += [(f"seed: {k}", seeds[k]) for k in ("buy_and_hold", "donchian_20", "ema_trend") if k in seeds]
    for label, r in entries:
        row = {"strategy": label, "search score": r["metrics"]["score"], "search Sharpe": r["metrics"]["sharpe"]}
        for tag, panel in (("spot", spot), ("futures", futures)):
            if panel is None:
                continue
            h = holdout_eval(r["code"], panel)
            if h["status"] == "ok":
                row.update(_holdout_cols(tag, h))
        rows.append(row)
    btc = {"strategy": "BTC hold"}
    for tag, panel in (("spot", spot), ("futures", futures)):
        if panel is not None:
            btc.update(_holdout_cols(tag, btc_hold(panel, HOLDOUT_START)))
    rows.append(btc)
    table = pd.DataFrame(rows)
    # Diagnostic, not used for picking: does a better search score predict a better holdout at all?
    with ThreadPoolExecutor(3) as ex:
        hs = list(ex.map(lambda r: holdout_eval(r["code"], spot), ok))
    allh = pd.DataFrame([{"id": r["id"], "model": r["model"], "idea": r["idea"], "search_score": r["metrics"]["score"],
                          "search_sharpe": r["metrics"]["sharpe"], "holdout_sharpe": h.get("sharpe"),
                          "holdout_cagr": h.get("cagr"), "holdout_max_dd": h.get("max_dd")} for r, h in zip(ok, hs)])
    allh.to_csv(d.out / "holdout_all_candidates.csv", index=False)
    bh_sharpe = holdout_eval(seeds["buy_and_hold"]["code"], spot)["sharpe"] if "buy_and_hold" in seeds else float("nan")
    v = allh.dropna(subset=["holdout_sharpe"])
    top = v.nlargest(max(len(v) // 10, 1), "search_score")
    diag = {"spearman_search_score_vs_holdout_sharpe": float(v.search_score.rank().corr(v.holdout_sharpe.rank())),
            "median_holdout_sharpe_all": float(v.holdout_sharpe.median()),
            "median_holdout_sharpe_top10pct_by_search": float(top.holdout_sharpe.median()),
            "buy_and_hold_holdout_sharpe": float(bh_sharpe),
            "share_beating_buy_and_hold_sharpe_all": float((v.holdout_sharpe > bh_sharpe).mean()),
            "share_beating_buy_and_hold_sharpe_top10pct": float((top.holdout_sharpe > bh_sharpe).mean())}
    by_model = pd.DataFrame([{"model": r["model"], "status": r["status"],
                              "score": (r.get("metrics") or {}).get("score")} for r in d.records if r["model"] != "seed"])
    model_tbl = by_model.groupby("model").agg(candidates=("status", "size"),
                                             valid=("status", lambda s: (s == "ok").sum()),
                                             best_score=("score", "max"), median_score=("score", "median"))
    report = {"finalists": [{k: f[k] for k in ("id", "idea", "hypothesis", "model", "metrics", "code")}
                            for f in finalists],
              "overfit": overfit, "holdout_diagnostic": diag, "status_counts": status_counts, "spent_usd": d.spent}
    (d.out / "report.json").write_text(json.dumps(report, indent=2, default=float))
    md = [f"# Strategy discovery {d.out.name}", "",
          f"{sum(status_counts.values())} LLM candidates, {len(ok)} valid, ${d.spent:.2f} spent. "
          f"Status: {status_counts}", "",
          f"Search window {SEARCH_START} .. {SEARCH_END} (spot, 43 coins incl. dead ones). "
          f"Holdout {HOLDOUT_START} .. latest, evaluated once below.", "",
          "## Holdout (pick = best search score, fixed before the holdout was run)", "",
          _md_table(table), "",
          "## Does the search score predict the holdout? (all valid candidates, spot; not used for picking)", "",
          "\n".join(f"- {k}: {v:.3f}" for k, v in diag.items()), "",
          "## Overfitting statistics over all valid candidates (search window)", "",
          "\n".join(f"- {k}: {v:.3f}" if isinstance(v, float) else f"- {k}: {v}" for k, v in overfit.items()), "",
          "## Candidates by model", "", _md_table(model_tbl.reset_index()), "",
          "## Finalists", ""]
    for f in finalists:
        md += [f"### {f['id']} {f['idea']} ({f['model']})", "", f["hypothesis"], "", _fmt_metrics(f["metrics"]), "",
               "```python", f["code"].strip(), "```", ""]
    text = "\n".join(md)
    (d.out / "report.md").write_text(text)
    return text


def _holdout_cols(tag: str, h: dict) -> dict:
    return {f"{tag} Sharpe": h["sharpe"], f"{tag} CAGR": h["cagr"], f"{tag} maxDD": h["max_dd"], f"{tag} vol": h["vol"]}


def _md_table(df: pd.DataFrame) -> str:
    def fmt(c, v):
        if isinstance(v, float):
            if math.isnan(v):
                return ""
            return f"{v:+.1%}" if any(k in c for k in ("total", "DD", "CAGR", "vol")) else f"{v:.2f}"
        return str(v)
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(fmt(c, row[c]) for c in cols) + " |" for _, row in df.iterrows()]
    return "\n".join(lines)


def default_out_dir() -> Path:
    return Path("results") / f"discovery_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
