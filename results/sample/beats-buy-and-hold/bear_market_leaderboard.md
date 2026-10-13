# Benchmark 20261013-191401 - bear-qwen-v4

Period: 2025-09-20 -> 2025-12-19 | Symbols: BTCUSDT, ETHUSDT, XRPUSDT, BNBUSDT, SOLUSDT, DOGEUSDT, TRXUSDT, ADAUSDT, LINKUSDT, AVAXUSDT | Decision every 24h | Start equity 10,000 USDT

Risk: {"decision_hours": 24, "max_leverage": 10, "default_leverage": 3, "sizing": "margin", "margin_per_trade": 0.08, "risk_per_trade": 0.01, "sl_source": "model", "atr_sl_mult": 1.5, "reward_risk": 2.0, "min_sl_pct": 0.004, "max_sl_pct": 0.08, "min_confidence": 0.55, "flat_closes": true, "max_open_positions": 10, "leverage_override": 0, "liq_guard": "reduce_leverage"}

| strategy | total_return | cagr | sharpe | sortino | max_drawdown | calmar | trades | win_rate | profit_factor | avg_leverage | liquidations | directional_accuracy | final_equity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ema_trend | 71.2% | 785.6% | 2.66 | 4.35 | -28.7% | 27.38 | 96 | 50.0% | 1.91 | 3.00 | 0 | 56.1% | 17118.28 |
| donchian_breakout | 57.1% | 524.6% | 2.33 | 3.38 | -27.4% | 19.13 | 90 | 46.7% | 1.65 | 3.00 | 0 | 56.5% | 15706.87 |
| random | 10.0% | 47.1% | 0.94 | 1.22 | -22.0% | 2.14 | 466 | 48.7% | 1.05 | 3.00 | 0 | 48.8% | 10998.00 |
| llm[qwen/qwen3.6-27b|v4] | 1.8% | 7.4% | 0.37 | 0.57 | -22.4% | 0.33 | 105 | 39.0% | 1.05 | 1.38 | 0 | 53.6% | 10176.90 |
| buy_and_hold | -33.5% | -80.9% | -3.16 | -4.12 | -35.5% | -2.28 | 10 | 0.0% | 0.00 | 1.00 | 0 | 43.6% | 6651.09 |
