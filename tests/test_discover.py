import numpy as np
import pandas as pd
import pytest

from cryptofutures.discover import (CodeRejected, Panel, Scorer, check_code, evaluate, leak_check,
                                    portfolio_returns)


def _panel(days=900, coins=6, seed=0, late_listing=True):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2017-09-01", periods=days, freq="D", tz="UTC")
    cols = ["BTC"] + [f"c{i:02d}" for i in range(1, coins)]
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.03, (days, coins)), axis=0)), index=idx, columns=cols)
    if late_listing:
        close.iloc[:200, -1] = np.nan                  # a coin that lists late
    fields = {"open": close.shift(1).fillna(close), "high": close * 1.01, "low": close * 0.99, "close": close,
              "volume": close * 0 + 1e6, "taker_buy": close * 0 + 5e5}
    return Panel(fields, None, {c: c for c in cols})


def test_check_code_rejects_imports_dunders_and_dates():
    for bad in ("import os\ndef strategy(data): return data['close']",
                "def strategy(data): return data['close'].__class__",
                "def strategy(data): return open('x')",
                "def strategy(data): return data['close'].loc['2021-01-01':]",
                "def strategy(data): return data['close'].to_csv('x')",
                "def nope(data): return data"):
        with pytest.raises(CodeRejected):
            check_code(bad)
    check_code("def strategy(data):\n    return data['close'].notna().astype(float)\n")


def test_portfolio_returns_equal_slots_and_costs():
    p = _panel(days=5, coins=2, late_listing=False)
    close = p.fields["close"].to_numpy()
    pos = np.ones_like(close)
    r = portfolio_returns(pos, p, cost=0.001)
    fwd = close[1:] / close[:-1] - 1
    expected = fwd.mean(axis=1)
    expected[0] -= 0.001                               # entering 100% gross costs 0.1% once
    assert np.allclose(r.to_numpy(), expected)


def test_leak_check_flags_future_data():
    sc = Scorer(_panel(), start="2018-01-01", end="2019-12-31")
    leaky = "def strategy(data):\n    c = data['close']\n    return (c.shift(-1) > c).astype(float)\n"
    assert evaluate(leaky, sc)["status"] == "lookahead"
    full_sample = "def strategy(data):\n    c = data['close']\n    return (c > c.mean()).astype(float)\n"
    assert evaluate(full_sample, sc)["status"] == "lookahead"
    causal = "def strategy(data):\n    c = data['close']\n    return (c > c.rolling(20).mean()).astype(float)\n"
    res = evaluate(causal, sc)
    assert res["status"] == "ok" and len(res["metrics"]["cells"]) == 6


def test_leak_check_passes_identical_prefixes():
    full = np.arange(20.0).reshape(10, 2)
    assert leak_check(full, [full[:5], full[:8]]) is None
    bad = full[:5].copy()
    bad[2, 1] += 1
    assert "day 2" in leak_check(full, [bad])
