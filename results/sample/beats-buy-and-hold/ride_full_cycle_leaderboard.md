# Benchmark 20261013-193306 - ride-full-cycle

Period: 2024-09-01 -> 2026-10-11 | Symbols: BTCUSDT, ETHUSDT, XRPUSDT, BNBUSDT, SOLUSDT, DOGEUSDT, TRXUSDT, ADAUSDT, LINKUSDT, AVAXUSDT | Decision every 24h | Start equity 10,000 USDT

Risk: {"decision_hours": 24, "max_leverage": 10, "default_leverage": 3, "sizing": "margin", "margin_per_trade": 0.08, "risk_per_trade": 0.01, "sl_source": "atr", "atr_sl_mult": 3.0, "reward_risk": 100.0, "min_sl_pct": 0.004, "max_sl_pct": 0.25, "min_confidence": 0.55, "flat_closes": true, "max_open_positions": 10, "leverage_override": 1, "liq_guard": "reduce_leverage"}

| strategy | total_return | cagr | sharpe | sortino | max_drawdown | calmar | trades | win_rate | profit_factor | avg_leverage | liquidations | directional_accuracy | final_equity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ema_trend | 90.5% | 35.7% | 1.11 | 1.42 | -28.0% | 1.28 | 209 | 36.8% | 1.93 | 1.00 | 0 | 52.6% | 19054.02 |
| donchian_breakout | 38.7% | 16.8% | 0.61 | 0.85 | -40.9% | 0.41 | 192 | 38.5% | 1.28 | 1.00 | 0 | 50.0% | 13865.39 |
| trend_long_short | 28.4% | 12.6% | 0.48 | 0.57 | -43.5% | 0.29 | 216 | 25.9% | 1.31 | 1.00 | 0 | 50.9% | 12841.47 |
| trend_filter_long | 16.2% | 7.4% | 0.39 | 0.40 | -44.9% | 0.16 | 121 | 23.1% | 1.32 | 1.00 | 0 | 50.9% | 11618.81 |
| buy_and_hold | 9.7% | 4.5% | 0.39 | 0.54 | -63.1% | 0.07 | 10 | 40.0% | 1.66 | 1.00 | 0 | 49.6% | 10968.54 |
