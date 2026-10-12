# Benchmark 20261012-185326 - baselines-2y

Period: 2024-09-01 -> 2026-10-01 | Symbols: BTCUSDT, ETHUSDT, XRPUSDT, BNBUSDT, SOLUSDT, DOGEUSDT, TRXUSDT, ADAUSDT, LINKUSDT, AVAXUSDT | Decision every 4h | Start equity 10,000 USDT

Risk: {"decision_hours": 4, "max_leverage": 10, "default_leverage": 3, "sizing": "margin", "margin_per_trade": 0.08, "risk_per_trade": 0.01, "sl_source": "model", "atr_sl_mult": 1.5, "reward_risk": 2.0, "min_sl_pct": 0.004, "max_sl_pct": 0.08, "min_confidence": 0.55, "flat_closes": true, "max_open_positions": 10}

| strategy | total_return | cagr | sharpe | sortino | max_drawdown | calmar | trades | win_rate | profit_factor | avg_leverage | liquidations | directional_accuracy | final_equity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| buy_and_hold | 14.5% | 6.7% | 0.43 | 0.60 | -63.1% | 0.11 | 10 | 50.0% | 2.13 | 1.00 | 0 | 50.2% | 11449.91 |
| ema_trend | -35.2% | -18.8% | 0.19 | 0.28 | -74.1% | -0.25 | 3289 | 36.9% | 0.97 | 3.00 | 0 | 49.8% | 6482.96 |
| flat | 0.0% | 0.0% | 0.00 | 0.00 | 0.0% | 0.00 | 0 | - | - | - | - | - | 10000.00 |
| donchian_breakout | -87.3% | -62.8% | -0.36 | -0.57 | -92.6% | -0.68 | 4220 | 33.4% | 0.93 | 3.00 | 0 | 48.9% | 1273.70 |
| rsi_reversion | -30.5% | -16.0% | -0.60 | -0.60 | -47.2% | -0.34 | 434 | 30.9% | 0.82 | 3.00 | 0 | 53.1% | 6951.57 |
| random | -99.6% | -92.8% | -6.20 | -7.80 | -99.6% | -0.93 | 14654 | 44.0% | 0.81 | 3.00 | 0 | 49.3% | 41.61 |
