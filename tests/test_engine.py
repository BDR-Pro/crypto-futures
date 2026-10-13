import numpy as np
import pandas as pd
import pytest

from cryptofutures.config import Config, ExchangeConfig, RiskConfig, with_risk
from cryptofutures.engine import Account, run_backtest
from cryptofutures.features import FeatureStore, resample
from cryptofutures.risk import plan_order
from cryptofutures.strategies.llm import parse_response


def candles(prices, start="2025-01-01", spread=0.0):
    """Hourly candles; each row is (open, high, low, close) or a single price."""
    idx = pd.date_range(start, periods=len(prices), freq="h", tz="UTC")
    rows = [p if isinstance(p, tuple) else (p, p * (1 + spread), p * (1 - spread), p) for p in prices]
    df = pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"])
    df["volume"] = 1.0
    df["quote_volume"] = df["close"]
    df["taker_buy_quote"] = df["close"] / 2
    return df


def decisions(times, action, **kw):
    row = {"action": action, "confidence": 1.0, "leverage": kw.get("leverage", 5),
           "sl_pct": kw.get("sl_pct", 0.02), "tp_pct": kw.get("tp_pct", 0.04), "reason": ""}
    return pd.DataFrame([row] * len(times), index=pd.DatetimeIndex(times))


def no_cost_cfg(**risk) -> Config:
    cfg = Config(exchange=ExchangeConfig(taker_fee=0.0, slippage=0.0, use_funding=False))
    return with_risk(cfg, sl_source="model", min_confidence=0.0, **risk)


def run(cfg, c, d, **kw):
    atr = {"X": pd.Series(0.01, index=d.index)}
    return run_backtest(cfg, {"X": c}, {"X": pd.Series(dtype=float)}, {"X": d}, atr, **kw)


def test_long_take_profit_pnl():
    c = candles([100, 100, 101, (101, 105, 101, 104), 104])
    d = decisions([c.index[1]], "LONG")
    res = run(no_cost_cfg(margin_per_trade=0.1), c, d)
    tr = res.trades.iloc[0]
    assert tr.exit_reason == "take_profit"
    assert tr.exit == pytest.approx(104.0)
    # notional = 10_000 * 0.1 * 5 = 5000 at 100 -> 50 units * +4 = +200
    assert tr.pnl == pytest.approx(200.0)
    assert res.equity.iloc[-1] == pytest.approx(10_200.0)


def test_stop_assumed_before_target_in_same_candle():
    c = candles([100, 100, (100, 106, 97, 100), 100])
    res = run(no_cost_cfg(), c, decisions([c.index[1]], "LONG"))
    assert res.trades.iloc[0].exit_reason == "stop_loss"
    assert res.trades.iloc[0].exit == pytest.approx(98.0)


def test_short_stop_gap_fills_at_open():
    c = candles([100, 100, (110, 111, 109, 110), 110])
    res = run(no_cost_cfg(), c, decisions([c.index[1]], "SHORT"))
    tr = res.trades.iloc[0]
    assert tr.side == "SHORT" and tr.exit_reason == "stop_loss"
    assert tr.exit == pytest.approx(110.0)      # gapped through the 102 stop


def test_liquidation_without_stop_loses_exactly_margin():
    c = candles([100, 100, (100, 100, 70, 72), 72])
    res = run(no_cost_cfg(margin_per_trade=0.1), c, decisions([c.index[1]], "LONG", leverage=5),
              use_stops=False)
    tr = res.trades.iloc[0]
    assert tr.exit_reason == "liquidation"
    assert tr.pnl == pytest.approx(-1000.0)     # whole isolated margin, nothing more
    assert res.equity.iloc[-1] == pytest.approx(9000.0)


def test_fees_and_slippage_are_charged():
    cfg = Config(exchange=ExchangeConfig(taker_fee=0.001, slippage=0.0, use_funding=False))
    cfg = with_risk(cfg, min_confidence=0.0)
    c = candles([100] * 6)
    d = decisions([c.index[1], c.index[3]], "LONG")
    d.iloc[1, d.columns.get_loc("action")] = "FLAT"
    res = run(cfg, c, d)
    tr = res.trades.iloc[0]
    assert tr.exit_reason == "signal_flat"
    assert tr.pnl == pytest.approx(-2 * 0.001 * 10_000 * 0.08 * 5)


def test_funding_long_pays_positive_rate():
    acct = Account(cfg=no_cost_cfg(), cash=1000)
    plan = plan_order(1, {"leverage": 2}, 0.01, 1000, 1000, RiskConfig(margin_per_trade=0.5), ExchangeConfig(slippage=0))
    acct.open("X", plan, 100.0, pd.Timestamp("2025-01-01", tz="UTC"), 1.0, "")
    cash = acct.cash
    acct.apply_funding("X", 0.0001, 100.0)
    assert acct.cash == pytest.approx(cash - 1000 * 0.0001)


def test_risk_layer_keeps_stop_inside_liquidation():
    risk = RiskConfig(max_leverage=50, sl_source="model", max_sl_pct=0.08)
    plan = plan_order(1, {"leverage": 50, "sl_pct": 0.05, "tp_pct": 0.1}, 0.01, 10_000, 10_000, risk, ExchangeConfig())
    liq_distance = 1 / plan.leverage - ExchangeConfig().maint_margin_rate
    assert plan.sl_pct < liq_distance
    assert plan.leverage <= 50


def test_risk_layer_clamps_crazy_model_output():
    risk = RiskConfig(max_leverage=10, max_sl_pct=0.08, min_sl_pct=0.004)
    plan = plan_order(-1, {"leverage": 125, "sl_pct": 0.9, "tp_pct": None}, 0.01, 10_000, 10_000, risk, ExchangeConfig())
    assert plan.leverage <= 10 and plan.sl_pct == pytest.approx(0.08)
    assert plan.tp_pct == pytest.approx(risk.reward_risk * 0.08)


def test_low_confidence_does_not_open():
    cfg = no_cost_cfg()
    cfg = with_risk(cfg, min_confidence=0.6)
    c = candles([100] * 5)
    d = decisions([c.index[1]], "LONG")
    d["confidence"] = 0.3
    assert run(cfg, c, d).trades.empty


def test_features_have_no_lookahead():
    rng = np.random.default_rng(0)
    prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 24 * 260)))
    c = candles(list(prices), spread=0.002)
    t = c.index[24 * 250]
    snap = FeatureStore(c, 4).snapshot(t)
    future_changed = c.copy()
    future_changed.loc[t:, ["open", "high", "low", "close"]] *= 3   # wildly different future
    snap2 = FeatureStore(future_changed, 4).snapshot(t)
    for k in snap:
        assert snap[k] == snap2[k], k


def test_resample_drops_incomplete_bar():
    c = candles([100] * 10)              # 10 hours -> two complete 4h bars, one partial
    assert len(resample(c, 4)) == 2


@pytest.mark.parametrize("text,action,sl", [
    ('{"action":"long","confidence":0.7,"leverage":3,"stop_loss_pct":2,"take_profit_pct":4,"reason":"x"}', "LONG", 0.02),
    ('<think>hmm</think>\nSure: {"action":"SHORT","confidence":80,"leverage":2,"stop_loss_pct":1.5,"take_profit_pct":3}', "SHORT", 0.015),
    ('{"action":"BUY","confidence":0.9}', "FLAT", None),
])
def test_parse_response(text, action, sl):
    d = parse_response(text)
    assert d.action == action
    assert 0 <= d.confidence <= 1
    assert (d.sl_pct == pytest.approx(sl)) if sl else d.sl_pct is None


def test_directional_accuracy():
    from cryptofutures.metrics import directional_accuracy
    c = candles([100, 101, 102, 101, 100, 99])
    d = pd.DataFrame({"action": ["LONG", "SHORT", "FLAT"], "confidence": [0.9, 0.6, 0.5]},
                     index=c.index[[0, 2, 3]])
    m = directional_accuracy({"X": d}, {"X": c}, horizon_hours=1)
    assert m["directional_calls"] == 2
    assert m["directional_accuracy"] == pytest.approx(1.0)   # 100->101 up, 102->101 down


def test_jev_option_probabilities_renormalise_letters():
    from cryptofutures.strategies.jev import build_prompt, option_probabilities
    top = {" B": -0.084, " C": -3.71, " A": -4.12, "\n\n": -6.3}
    p = option_probabilities(top, 2)
    assert sum(p) == pytest.approx(1.0)
    assert p[1] == pytest.approx(0.983, abs=0.002)        # 'positive' in the model card example
    p3 = option_probabilities({" A": -0.1}, 3)            # missing letters get negligible mass
    assert p3[0] > 0.98
    prompt = build_prompt("state", "q?", ["x", "y"])
    assert prompt.endswith("[Options]\nA. x\nB. y\n\nAnswer:")


def test_nimble_prompt_matches_bespoke_format():
    import json as _json
    from cryptofutures.strategies.nimble import MARKER, SCHEMAS, softmax, user_content
    schema = {k: (d.format(tf=4), o) for k, (d, o) in SCHEMAS["n1"].items()}
    content = user_content("BTC <up>", schema)
    body, requested = content.split("\n\nRequested field: ")
    assert requested == MARKER
    assert "<" not in body                                    # escaped like Bespoke's safe_json
    obj = _json.loads(body)
    assert obj["context"] == "BTC <up>"
    pos = obj["schema"][0]
    assert pos["name"] == "position" and [c["code"] for c in pos["choices"]] == ["A", "B", "C"]
    assert [c["value"] for c in pos["choices"]] == ["LONG", "SHORT", "FLAT"]
    p = softmax([2.0, 1.0, 0.0], 1.0)
    assert sum(p) == pytest.approx(1.0) and p[0] > p[1] > p[2]


def test_openrouter_key_only_sent_to_openrouter(monkeypatch):
    from cryptofutures.config import LLMConfig
    from cryptofutures.strategies.llm import LLMClient
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    assert LLMClient(LLMConfig(base_url="https://openrouter.ai/api/v1")).api_key() == "sk-or-test"
    assert LLMClient(LLMConfig(base_url="http://127.0.0.1:8080/v1")).api_key() == "local"
    assert LLMClient(LLMConfig(base_url="https://openrouter.ai.evil.com/v1")).api_key() == "local"
    monkeypatch.delenv("OPENROUTER_API_KEY")   # network-secret setup: proxy swaps the placeholder
    assert LLMClient(LLMConfig(base_url="https://openrouter.ai/api/v1")).api_key() == "proxy-injected"


def test_shuffle_keeps_decision_mix_but_changes_timing():
    from cryptofutures.robustness import shuffle_decisions
    idx = pd.date_range("2025-01-01", periods=50, freq="D", tz="UTC")
    d = pd.DataFrame({"action": ["LONG"] * 30 + ["SHORT"] * 15 + ["FLAT"] * 5,
                      "confidence": np.linspace(0.5, 1, 50)}, index=idx)
    s = shuffle_decisions({"X": d}, np.random.default_rng(1))["X"]
    assert (s.index == d.index).all()
    assert s.action.value_counts().to_dict() == d.action.value_counts().to_dict()
    assert sorted(s.confidence) == sorted(d.confidence)
    assert not (s.action == d.action).all()


def test_bootstrap_trades_bounds():
    from cryptofutures.robustness import bootstrap_trades
    t = pd.DataFrame({"pnl": [100.0] * 20})
    b = bootstrap_trades(t, 10_000)
    assert b["return_p05"] == pytest.approx(0.2) and b["prob_positive"] == 1.0
    mixed = bootstrap_trades(pd.DataFrame({"pnl": [100.0, -100.0] * 20}), 10_000)
    assert mixed["return_p05"] < 0 < mixed["return_p95"]
    assert bootstrap_trades(pd.DataFrame(columns=["pnl"]), 10_000) == {"n_trades": 0}


def test_robust_score_and_champion(tmp_path):
    from cryptofutures.robustness import robust_score, update_champion
    windows = {"excess_median": 0.04}
    assert robust_score({"p_value": 0.05}, windows) == pytest.approx(0.04)
    assert robust_score({"p_value": 0.5}, windows) == pytest.approx(0.02)      # not significant: halved
    assert robust_score({"p_value": 0.5}, {"excess_median": -0.03}) == pytest.approx(-0.03)
    path = tmp_path / "champion.json"
    setup = {"period": ["2026-01-01", "2026-04-01"], "risk": {"decision_hours": 24}, "symbols": ["BTCUSDT"]}
    champ, promoted = update_champion([{**setup, "strategy": "a", "robust_score": 0.01}], path)
    assert promoted and champ["strategy"] == "a"
    champ, promoted = update_champion([{**setup, "strategy": "b", "robust_score": -0.02}], path)
    assert not promoted and champ["strategy"] == "a"
    champ, promoted = update_champion([{**setup, "strategy": "c", "robust_score": 0.03}], path)
    assert promoted and champ["strategy"] == "c"
    other = {**setup, "symbols": ["BTCUSDT", "ETHUSDT"]}       # different coin set: separate champion
    champ, promoted = update_champion([{**other, "strategy": "d", "robust_score": -0.5}], path)
    assert promoted and champ["strategy"] == "d"


def test_robustness_suite_end_to_end(tmp_path):
    """Synthetic market: every randomized test runs end to end and returns sane numbers."""
    from cryptofutures.config import DataConfig
    from cryptofutures.robustness import RobustnessSuite
    from cryptofutures.data import MarketData
    rng = np.random.default_rng(3)
    for sym in ("AAAUSDT", "BBBUSDT"):
        prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 24 * 300)))
        c = candles(list(prices), start="2025-01-01", spread=0.002)
        MarketData(tmp_path)._write(c, MarketData(tmp_path)._path(sym, "1h"))
    cfg = Config(data=DataConfig(symbols=["AAAUSDT", "BBBUSDT"], data_dir=str(tmp_path)),
                 exchange=ExchangeConfig(use_funding=False))
    cfg = with_risk(cfg, decision_hours=24, min_confidence=0.0)
    suite = RobustnessSuite(cfg, "2025-08-01", "2025-10-20", seed=1)
    r = suite.evaluate("random", n_perm=10, n_windows=5, window_days=20, n_risk=3)
    assert 0 < r["timing_permutation"]["p_value"] <= 1
    assert r["random_windows"]["n"] == 5 and r["risk_perturbation"]["n"] == 3
    assert r["robust_score"] == r["robust_score"]       # finite / not NaN


def test_cache_only_never_calls_model(tmp_path):
    from cryptofutures.config import LLMConfig
    from cryptofutures.strategies.llm import LLMStrategy
    st = LLMStrategy(LLMConfig(base_url="http://127.0.0.1:9/v1", cache_only=True,
                               cache_path=str(tmp_path / "c.sqlite")))
    st.client.chat = lambda *_: (_ for _ in ()).throw(AssertionError("model was called"))
    c = candles([100.0] * (24 * 300), spread=0.002)
    from cryptofutures.features import FeatureStore
    store = FeatureStore(c, 24)
    d = st.decide("X", store, store.decision_times()[:3])
    assert (d.action == "FLAT").all() and st.stats["missing"] == 3
