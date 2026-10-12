"""Decision interface shared by the LLM agent and the rule-based baselines."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass

import pandas as pd

from ..features import FeatureStore

LONG, SHORT, FLAT, HOLD = "LONG", "SHORT", "FLAT", "HOLD"
ACTIONS = (LONG, SHORT, FLAT, HOLD)


@dataclass
class Decision:
    action: str                 # LONG | SHORT | FLAT (close/stay out) | HOLD (keep whatever is open)
    confidence: float = 1.0     # 0..1
    leverage: int | None = None # requested leverage (risk manager clamps it)
    sl_pct: float | None = None # stop-loss distance from entry, fraction (0.02 = 2%)
    tp_pct: float | None = None # take-profit distance from entry, fraction
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Strategy(ABC):
    name: str = "strategy"
    use_stops: bool = True              # False = no SL/TP (passive benchmarks)
    fixed_leverage: int | None = None   # override model/default leverage
    lookback: int = 1                   # decisions a live trader must replay (stateful rules need > 1)

    @abstractmethod
    def decide(self, symbol: str, store: FeatureStore, times: pd.DatetimeIndex) -> pd.DataFrame:
        """Return a DataFrame indexed by decision time with Decision fields as columns."""


def decisions_frame(times: pd.DatetimeIndex, decisions: list[Decision]) -> pd.DataFrame:
    df = pd.DataFrame([d.to_dict() for d in decisions], index=times)
    df.index.name = "time"
    return df
