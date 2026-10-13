# Benchmark 20261013-162500 - qwen-v4-hold-10coins

Period: 2026-07-13 -> 2026-10-11 | Symbols: BTCUSDT, ETHUSDT, XRPUSDT, BNBUSDT, SOLUSDT, DOGEUSDT, TRXUSDT, ADAUSDT, LINKUSDT, AVAXUSDT | Decision every 24h | Start equity 10,000 USDT

Risk: {"decision_hours": 24, "max_leverage": 10, "default_leverage": 3, "sizing": "margin", "margin_per_trade": 0.08, "risk_per_trade": 0.01, "sl_source": "model", "atr_sl_mult": 1.5, "reward_risk": 2.0, "min_sl_pct": 0.004, "max_sl_pct": 0.08, "min_confidence": 0.55, "flat_closes": true, "max_open_positions": 10, "leverage_override": 0, "liq_guard": "reduce_leverage"}

| strategy | total_return | cagr | sharpe | sortino | max_drawdown | calmar | trades | win_rate | profit_factor | avg_leverage | liquidations | directional_accuracy | final_equity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| buy_and_hold | 28.5% | 176.5% | 2.90 | 4.96 | -10.4% | 17.01 | 10 | 100.0% | inf | 1.00 | 0 | 52.9% | 12848.55 |
| llm[qwen/qwen3.6-27b|v4] | 19.1% | 103.2% | 1.95 | 3.49 | -11.3% | 9.11 | 83 | 36.1% | 1.75 | 1.61 | 0 | 47.6% | 11908.89 |
| llm[qwen/qwen3.6-27b|v2] | 5.0% | 21.8% | 0.85 | 1.21 | -8.2% | 2.67 | 97 | 45.4% | 1.19 | 2.14 | 0 | 50.4% | 10497.35 |
| donchian_breakout | -1.6% | -6.4% | 0.32 | 0.43 | -37.9% | -0.17 | 95 | 40.0% | 0.98 | 3.00 | 0 | 50.7% | 9838.57 |
