# Benchmark 20261013-115745 - top3-90d-4coins

Period: 2026-07-13 -> 2026-10-11 | Symbols: BTCUSDT, ETHUSDT, XRPUSDT, BNBUSDT | Decision every 24h | Start equity 10,000 USDT

Risk: {"decision_hours": 24, "max_leverage": 10, "default_leverage": 3, "sizing": "margin", "margin_per_trade": 0.08, "risk_per_trade": 0.01, "sl_source": "model", "atr_sl_mult": 1.5, "reward_risk": 2.0, "min_sl_pct": 0.004, "max_sl_pct": 0.08, "min_confidence": 0.55, "flat_closes": true, "max_open_positions": 10}

| strategy | total_return | cagr | sharpe | sortino | max_drawdown | calmar | trades | win_rate | profit_factor | avg_leverage | liquidations | directional_accuracy | final_equity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| buy_and_hold | 9.8% | 46.3% | 2.58 | 5.12 | -5.0% | 9.18 | 4 | 100.0% | inf | 1.00 | 0 | 54.7% | 10982.53 |
| llm[qwen/qwen3.6-27b|v2] | 7.4% | 33.4% | 1.65 | 2.51 | -4.3% | 7.72 | 40 | 50.0% | 1.84 | 2.45 | 0 | 53.5% | 10736.52 |
| donchian_breakout | 4.4% | 19.2% | 0.71 | 1.05 | -17.0% | 1.13 | 32 | 43.8% | 1.17 | 3.00 | 0 | 53.4% | 10442.77 |
| llm[openai/gpt-oss-120b|v2] | 0.4% | 1.5% | 0.17 | 0.21 | -5.5% | 0.28 | 37 | 37.8% | 1.04 | 2.00 | 0 | 49.3% | 10036.83 |
| random | -3.5% | -13.3% | -0.50 | -0.66 | -9.4% | -1.42 | 177 | 45.2% | 0.92 | 3.00 | 0 | 49.3% | 9654.56 |
| ema_trend | -6.4% | -23.6% | -1.00 | -1.34 | -11.4% | -2.07 | 33 | 36.4% | 0.73 | 3.00 | 0 | 50.6% | 9359.01 |
| llm[deepseek/deepseek-v4-flash|v2] | -10.2% | -35.2% | -2.80 | -2.51 | -10.5% | -3.36 | 40 | 20.0% | 0.33 | 3.08 | 0 | 41.3% | 8984.90 |
