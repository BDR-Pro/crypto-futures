# Benchmark 20261013-191423 - full-cycle-24h

Period: 2024-09-01 -> 2026-10-11 | Symbols: BTCUSDT, ETHUSDT, XRPUSDT, BNBUSDT, SOLUSDT, DOGEUSDT, TRXUSDT, ADAUSDT, LINKUSDT, AVAXUSDT | Decision every 24h | Start equity 10,000 USDT

Risk: {"decision_hours": 24, "max_leverage": 10, "default_leverage": 3, "sizing": "margin", "margin_per_trade": 0.08, "risk_per_trade": 0.01, "sl_source": "model", "atr_sl_mult": 1.5, "reward_risk": 2.0, "min_sl_pct": 0.004, "max_sl_pct": 0.08, "min_confidence": 0.55, "flat_closes": true, "max_open_positions": 10, "leverage_override": 0, "liq_guard": "reduce_leverage"}

| strategy | total_return | cagr | sharpe | sortino | max_drawdown | calmar | trades | win_rate | profit_factor | avg_leverage | liquidations | directional_accuracy | final_equity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ema_trend | 36.5% | 15.9% | 0.59 | 0.78 | -74.3% | 0.21 | 694 | 38.9% | 1.06 | 3.00 | 0 | 52.6% | 13654.23 |
| buy_and_hold | 9.7% | 4.5% | 0.39 | 0.54 | -63.1% | 0.07 | 10 | 40.0% | 1.66 | 1.00 | 0 | 49.6% | 10968.54 |
| donchian_breakout | -53.2% | -30.2% | 0.15 | 0.21 | -75.7% | -0.40 | 928 | 35.1% | 0.93 | 3.00 | 0 | 50.0% | 4678.84 |
| random | -74.6% | -47.8% | -1.07 | -1.69 | -84.4% | -0.57 | 3937 | 45.7% | 0.93 | 3.00 | 0 | 49.8% | 2537.41 |
