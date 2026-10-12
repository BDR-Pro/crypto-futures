"""Glue between data, features, strategies and the paper exchange."""
from __future__ import annotations

import logging
from dataclasses import replace

import pandas as pd

from .config import Config, utc
from .data import MarketData
from .engine import BacktestResult, run_backtest
from .features import FeatureStore
from .metrics import compute_metrics, directional_accuracy
from .strategies import BASELINES, JevStrategy, LLMStrategy, Strategy

log = logging.getLogger(__name__)


def make_strategy(name: str, cfg: Config) -> Strategy:
    """'llm' / 'llm:<model>[@<prompt_version>]' (generative LLM, [llm] config),
    'jev' / 'jev:<model>[@<question_set>]' (Jev-style decision model, [jev] config), or a baseline name."""
    if name.startswith("jev"):
        jev_cfg = cfg.jev
        if ":" in name:
            model, _, qset = name.split(":", 1)[1].partition("@")
            jev_cfg = replace(jev_cfg, model=model or jev_cfg.model, question_set=qset or jev_cfg.question_set)
        return JevStrategy(jev_cfg, max_leverage=cfg.risk.max_leverage, decision_hours=cfg.risk.decision_hours)
    if name.startswith("llm"):
        llm_cfg = cfg.llm
        if ":" in name:
            spec = name.split(":", 1)[1]
            model, _, version = spec.partition("@")
            llm_cfg = replace(llm_cfg, model=model or llm_cfg.model, prompt_version=version or llm_cfg.prompt_version)
        return LLMStrategy(llm_cfg, max_leverage=cfg.risk.max_leverage, decision_hours=cfg.risk.decision_hours)
    if name not in BASELINES:
        raise KeyError(f"unknown strategy {name!r}; choose from jev, llm, {', '.join(BASELINES)}")
    return BASELINES[name]()


class Workbench:
    """Loads market data once and runs any number of strategies / risk settings on it."""

    def __init__(self, cfg: Config, symbols: list[str] | None = None):
        self.cfg = cfg
        self.symbols = symbols or cfg.data.symbols
        md = MarketData(cfg.data.data_dir, cfg.data.base_interval)
        self.candles = {s: md.candles(s) for s in self.symbols}
        self.funding = {s: md.funding(s) for s in self.symbols}
        self.stores = {s: FeatureStore(self.candles[s], cfg.risk.decision_hours, self.funding[s]) for s in self.symbols}

    def decision_times(self, symbol: str, start=None, end=None) -> pd.DatetimeIndex:
        times = self.stores[symbol].decision_times(start, end)
        if end is not None:
            times = times[times < utc(end)]
        return times

    def atr_at(self, symbol: str, times: pd.DatetimeIndex) -> pd.Series:
        store = self.stores[symbol]
        bars = store.bars["atr_pct"].reindex(times - pd.Timedelta(hours=store.decision_hours))
        return pd.Series(bars.values, index=times)

    def decisions(self, strategy: Strategy, start=None, end=None) -> dict[str, pd.DataFrame]:
        out = {}
        for s in self.symbols:
            out[s] = strategy.decide(s, self.stores[s], self.decision_times(s, start, end))
        if isinstance(strategy, (LLMStrategy, JevStrategy)):
            log.info("%s stats: %s", strategy.name, strategy.stats)
        return out

    def run(self, strategy: Strategy, decisions: dict[str, pd.DataFrame] | None = None, cfg: Config | None = None,
            start=None, end=None) -> tuple[BacktestResult, dict]:
        cfg = cfg or self.cfg
        if decisions is None:
            decisions = self.decisions(strategy, start, end)
        atr = {s: self.atr_at(s, d.index) for s, d in decisions.items()}
        first = min((d.index.min() for d in decisions.values() if len(d)), default=None)
        res = run_backtest(cfg, self.candles, self.funding, decisions, atr, name=strategy.name,
                           use_stops=strategy.use_stops, fixed_leverage=strategy.fixed_leverage,
                           start=start or first, end=end)
        metrics = compute_metrics(res.equity, res.trades, cfg.exchange.initial_equity)
        metrics.update(directional_accuracy(decisions, self.candles, cfg.risk.decision_hours))
        return res, metrics
