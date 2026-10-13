# Benchmark 20261013-120203 - qwen-v2-vs-v3-btc-eth

Period: 2026-07-13 -> 2026-10-11 | Symbols: BTCUSDT, ETHUSDT | Decision every 24h | Start equity 10,000 USDT

Risk: {"decision_hours": 24, "max_leverage": 10, "default_leverage": 3, "sizing": "margin", "margin_per_trade": 0.08, "risk_per_trade": 0.01, "sl_source": "model", "atr_sl_mult": 1.5, "reward_risk": 2.0, "min_sl_pct": 0.004, "max_sl_pct": 0.08, "min_confidence": 0.55, "flat_closes": true, "max_open_positions": 10}

| strategy | total_return | cagr | sharpe | sortino | max_drawdown | calmar | trades | win_rate | profit_factor | avg_leverage | liquidations | directional_accuracy | final_equity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| buy_and_hold | 5.2% | 23.1% | 2.70 | 5.54 | -2.3% | 10.15 | 2 | 100.0% | inf | 1.00 | 0 | 55.6% | 10524.50 |
| llm[qwen/qwen3.6-27b|v2] | 5.6% | 24.7% | 2.02 | 3.22 | -2.6% | 9.37 | 14 | 64.3% | 2.75 | 2.64 | 0 | 54.2% | 10559.57 |
| donchian_breakout | 3.3% | 14.0% | 0.83 | 1.47 | -6.7% | 2.08 | 14 | 42.9% | 1.36 | 3.00 | 0 | 53.4% | 10328.24 |
| llm[qwen/qwen3.6-27b|v3] | 1.0% | 4.3% | 0.38 | 0.60 | -5.7% | 0.75 | 39 | 51.3% | 1.10 | 2.92 | 0 | 52.7% | 10104.12 |
