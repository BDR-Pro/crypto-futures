# Robustness 2026-07-13 -> 2026-10-11

| strategy | return | vs B&H | timing p-value | shuffled median | bootstrap 5–95% | beats B&H in random windows | median excess | risk-perturbed median | robust score |
|---|---|---|---|---|---|---|---|---|---|
| donchian_breakout | +6.4% | -3.4 pts | 0.957 | +18.6% | -13.0% … +28.5% | 72% | +2.8 pts | +1.3% | +1.39 |
| buy_and_hold | +9.8% | +0.0 pts | 1.000 | +9.8% | +9.0% … +11.2% | 0% | +0.0 pts | +9.8% | +0.00 |
| llm[qwen/qwen3.6-27b|v2] | +6.0% | -3.8 pts | 0.096 | +1.6% | -0.0% … +11.9% | 34% | -1.1 pts | +0.9% | -1.13 |
