"""Turns a model decision into a concrete order: leverage, SL/TP and size.

The model proposes; the risk manager disposes. Every number the model emits is
clamped here so a bad answer can never blow up the account.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .config import ExchangeConfig, RiskConfig

LIQ_BUFFER = 0.002  # keep the stop at least 0.2% inside the liquidation price


@dataclass
class OrderPlan:
    side: int            # +1 long, -1 short
    leverage: int
    notional: float
    sl_pct: float | None
    tp_pct: float | None


def _valid(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x)) and x > 0


def plan_order(side: int, decision: dict, atr_pct: float, equity: float, free_margin: float,
               risk: RiskConfig, ex: ExchangeConfig, use_stops: bool = True,
               fixed_leverage: int | None = None) -> OrderPlan | None:
    lev = fixed_leverage or decision.get("leverage")
    lev = int(lev) if _valid(lev) else risk.default_leverage
    lev = max(1, min(risk.max_leverage, lev))

    sl = tp = None
    if use_stops:
        atr_sl = risk.atr_sl_mult * (atr_pct if _valid(atr_pct) else 0.01)
        if risk.sl_source == "model" and _valid(decision.get("sl_pct")):
            sl = float(decision["sl_pct"])
        else:
            sl = atr_sl
        sl = min(max(sl, risk.min_sl_pct), risk.max_sl_pct)
        if risk.sl_source == "model" and _valid(decision.get("tp_pct")):
            tp = max(float(decision["tp_pct"]), 0.5 * sl)
        else:
            tp = risk.reward_risk * sl
        # Stop must trigger before liquidation: 1/lev - mmr is the liquidation distance.
        max_lev_for_sl = math.floor(1 / (sl + ex.maint_margin_rate + LIQ_BUFFER))
        lev = max(1, min(lev, max_lev_for_sl))

    if risk.sizing == "risk" and sl:
        notional = equity * risk.risk_per_trade / sl
        notional = min(notional, equity * risk.margin_per_trade * lev)
    else:
        notional = equity * risk.margin_per_trade * lev

    margin = notional / lev
    if margin > free_margin:
        notional = max(free_margin, 0) * lev
    if notional < 10:  # exchange minimum notional
        return None
    return OrderPlan(side=side, leverage=lev, notional=notional, sl_pct=sl, tp_pct=tp)
