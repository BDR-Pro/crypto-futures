# Benchmark 20261012-210104 - head-to-head-5coins

Period: 2026-09-26 -> 2026-10-11 | Symbols: BTCUSDT, ETHUSDT, XRPUSDT, BNBUSDT, SOLUSDT | Decision every 24h | Start equity 10,000 USDT

Risk: {"decision_hours": 24, "max_leverage": 10, "default_leverage": 3, "sizing": "margin", "margin_per_trade": 0.08, "risk_per_trade": 0.01, "sl_source": "model", "atr_sl_mult": 1.5, "reward_risk": 2.0, "min_sl_pct": 0.004, "max_sl_pct": 0.08, "min_confidence": 0.55, "flat_closes": true, "max_open_positions": 10}

| strategy | total_return | cagr | sharpe | sortino | max_drawdown | calmar | trades | win_rate | profit_factor | avg_leverage | liquidations | directional_accuracy | final_equity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| llm[qwen3-1.7b|v2] | -6.7% | -81.3% | -1.10 | -1.52 | -18.8% | -4.32 | 24 | 45.8% | 0.69 | 7.54 | 0 | 46.7% | 9334.99 |
| buy_and_hold | -2.6% | -48.0% | -5.28 | -5.63 | -4.3% | -11.08 | 5 | 0.0% | 0.00 | 1.00 | 0 | 46.7% | 9735.32 |
| ema_trend | -8.7% | -89.1% | -5.74 | -6.33 | -11.2% | -7.93 | 11 | 36.4% | 0.10 | 3.00 | 0 | 46.7% | 9130.23 |
| random | -5.7% | -76.1% | -6.39 | -9.35 | -6.0% | -12.78 | 42 | 31.0% | 0.43 | 3.00 | 0 | 41.5% | 9429.94 |
| jev[jev-style-2b|j1] | -11.5% | -94.9% | -6.84 | -7.55 | -13.1% | -7.25 | 6 | 0.0% | 0.00 | 4.00 | 0 | 44.3% | 8854.40 |
