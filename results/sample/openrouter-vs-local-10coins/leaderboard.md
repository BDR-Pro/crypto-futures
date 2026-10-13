# Benchmark 20261013-112048 - openrouter-vs-local-10coins

Period: 2026-09-26 -> 2026-10-11 | Symbols: BTCUSDT, ETHUSDT, XRPUSDT, BNBUSDT, SOLUSDT, DOGEUSDT, TRXUSDT, ADAUSDT, LINKUSDT, AVAXUSDT | Decision every 24h | Start equity 10,000 USDT

Risk: {"decision_hours": 24, "max_leverage": 10, "default_leverage": 3, "sizing": "margin", "margin_per_trade": 0.08, "risk_per_trade": 0.01, "sl_source": "model", "atr_sl_mult": 1.5, "reward_risk": 2.0, "min_sl_pct": 0.004, "max_sl_pct": 0.08, "min_confidence": 0.55, "flat_closes": true, "max_open_positions": 10}

| strategy | total_return | cagr | sharpe | sortino | max_drawdown | calmar | trades | win_rate | profit_factor | avg_leverage | liquidations | directional_accuracy | final_equity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| llm[qwen/qwen3.6-27b|v2] | -3.8% | -60.9% | -2.54 | -2.92 | -9.3% | -6.58 | 30 | 36.7% | 0.64 | 2.13 | 0 | 42.7% | 9622.18 |
| buy_and_hold | -5.0% | -71.3% | -4.25 | -4.20 | -9.3% | -7.70 | 10 | 0.0% | 0.00 | 1.00 | 0 | 45.3% | 9501.73 |
| donchian_breakout | -5.3% | -73.4% | -4.59 | -5.35 | -9.5% | -7.74 | 7 | 42.9% | 0.29 | 3.00 | 0 | 48.6% | 9472.11 |
| ema_trend | -18.9% | -99.4% | -5.69 | -5.51 | -23.8% | -4.17 | 20 | 35.0% | 0.11 | 3.00 | 0 | 45.7% | 8109.69 |
| jev[jev-style-2b|j1] | -27.6% | -100.0% | -7.44 | -7.03 | -31.4% | -3.18 | 12 | 0.0% | 0.00 | 4.08 | 0 | 43.8% | 7242.86 |
| llm[deepseek/deepseek-v4-flash|v2] | -7.9% | -86.7% | -8.09 | -8.84 | -8.9% | -9.74 | 28 | 25.0% | 0.25 | 2.64 | 0 | 38.8% | 9206.10 |
| nimble[Bespoke-Nimble-9B-v3-Q4_K_M|n1] | -10.2% | -92.7% | -8.29 | -8.42 | -11.5% | -8.07 | 18 | 5.6% | 0.06 | 2.39 | 0 | 33.8% | 8982.59 |
| llm[openai/gpt-oss-120b|v2] | -7.7% | -85.7% | -8.50 | -8.30 | -8.4% | -10.17 | 27 | 18.5% | 0.12 | 1.81 | 0 | 40.6% | 9232.57 |
| random | -15.0% | -98.1% | -8.90 | -11.54 | -15.7% | -6.24 | 77 | 36.4% | 0.41 | 3.00 | 0 | 43.5% | 8504.99 |
