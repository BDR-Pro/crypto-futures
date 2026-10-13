# Robustness 2026-07-13 -> 2026-10-11

| strategy | return | vs B&H | timing p-value | shuffled median | bootstrap 5–95% | beats B&H in random windows | median excess | risk-perturbed median | robust score |
|---|---|---|---|---|---|---|---|---|---|
| buy_and_hold | +28.5% | +0.0 pts | 1.000 | +28.5% | +20.9% … +35.6% | 0% | +0.0 pts | +28.5% | +0.00 |
| ema_trend | -5.9% | -34.4 pts | 0.891 | +13.3% | -29.5% … +17.6% | 35% | -3.7 pts | -3.8% | -3.67 |
| donchian_breakout | -1.6% | -30.1 pts | 0.941 | +26.3% | -38.7% … +33.8% | 12% | -5.5 pts | +0.1% | -5.50 |
| random | -29.9% | -58.4 pts | 0.881 | -8.8% | -55.1% … -4.2% | 8% | -9.5 pts | -12.9% | -9.49 |
