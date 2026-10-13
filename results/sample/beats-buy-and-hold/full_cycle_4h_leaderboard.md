# Benchmark 20261013-191434 - full-cycle-4h

Period: 2024-09-01 -> 2026-10-11 | Symbols: BTCUSDT, ETHUSDT, XRPUSDT, BNBUSDT, SOLUSDT, DOGEUSDT, TRXUSDT, ADAUSDT, LINKUSDT, AVAXUSDT | Decision every 4h | Start equity 10,000 USDT

Risk: {"decision_hours": 4, "max_leverage": 10, "default_leverage": 3, "sizing": "margin", "margin_per_trade": 0.08, "risk_per_trade": 0.01, "sl_source": "model", "atr_sl_mult": 1.5, "reward_risk": 2.0, "min_sl_pct": 0.004, "max_sl_pct": 0.08, "min_confidence": 0.55, "flat_closes": true, "max_open_positions": 10, "leverage_override": 0, "liq_guard": "reduce_leverage"}

| strategy | total_return | cagr | sharpe | sortino | max_drawdown | calmar | trades | win_rate | profit_factor | avg_leverage | liquidations | directional_accuracy | final_equity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| buy_and_hold | 9.7% | 4.5% | 0.39 | 0.54 | -63.1% | 0.07 | 10 | 40.0% | 1.66 | 1.00 | 0 | 50.2% | 10968.54 |
| ema_trend | -41.5% | -22.5% | 0.13 | 0.20 | -74.1% | -0.30 | 3328 | 36.7% | 0.97 | 3.00 | 0 | 49.7% | 5845.96 |
| donchian_breakout | -88.7% | -64.4% | -0.40 | -0.65 | -92.6% | -0.70 | 4264 | 33.3% | 0.93 | 3.00 | 0 | 48.9% | 1132.50 |
| random | -99.6% | -92.6% | -6.16 | -7.70 | -99.6% | -0.93 | 14654 | 44.0% | 0.81 | 3.00 | 0 | 49.2% | 41.61 |
