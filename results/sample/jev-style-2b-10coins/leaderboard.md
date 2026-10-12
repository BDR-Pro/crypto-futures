# Benchmark 20261012-200142 - jev-style-2b-10coins

Period: 2026-09-11 -> 2026-10-11 | Symbols: BTCUSDT, ETHUSDT, XRPUSDT, BNBUSDT, SOLUSDT, DOGEUSDT, TRXUSDT, ADAUSDT, LINKUSDT, AVAXUSDT | Decision every 24h | Start equity 10,000 USDT

Risk: {"decision_hours": 24, "max_leverage": 10, "default_leverage": 3, "sizing": "margin", "margin_per_trade": 0.08, "risk_per_trade": 0.01, "sl_source": "model", "atr_sl_mult": 1.5, "reward_risk": 2.0, "min_sl_pct": 0.004, "max_sl_pct": 0.08, "min_confidence": 0.55, "flat_closes": true, "max_open_positions": 10}

| strategy | total_return | cagr | sharpe | sortino | max_drawdown | calmar | trades | win_rate | profit_factor | avg_leverage | liquidations | directional_accuracy | final_equity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| buy_and_hold | 8.4% | 168.3% | 2.30 | 3.06 | -9.9% | 16.99 | 10 | 90.0% | 52.48 | 1.00 | 0 | 55.3% | 10843.83 |
| jev[jev-style-2b|j1] | -2.8% | -29.0% | 0.22 | 0.27 | -26.1% | -1.11 | 29 | 34.5% | 0.93 | 3.66 | 0 | 52.7% | 9722.78 |
| ema_trend | 0.7% | 8.3% | 0.14 | 0.16 | -22.5% | 0.37 | 35 | 42.9% | 1.02 | 3.00 | 0 | 54.0% | 10065.68 |
| rsi_reversion | 0.0% | 0.0% | 0.00 | 0.00 | 0.0% | 0.00 | 0 | - | - | - | - | - | 10000.00 |
| random | -10.2% | -73.2% | -2.45 | -3.80 | -18.7% | -3.92 | 150 | 48.7% | 0.81 | 3.00 | 0 | 51.6% | 8975.53 |
| donchian_breakout | -23.5% | -96.1% | -4.17 | -4.03 | -29.5% | -3.26 | 34 | 26.5% | 0.35 | 3.00 | 0 | 45.3% | 7654.80 |
