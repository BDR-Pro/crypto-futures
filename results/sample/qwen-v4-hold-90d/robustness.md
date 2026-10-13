# Robustness 2026-07-13 -> 2026-10-11

| strategy | return | vs B&H | timing p-value | shuffled median | bootstrap 5–95% | beats B&H in random windows | median excess | risk-perturbed median | robust score |
|---|---|---|---|---|---|---|---|---|---|
| buy_and_hold | +28.5% | +0.0 pts | 1.000 | +28.5% | +21.1% … +35.8% | 0% | +0.0 pts | +27.3% | +0.00 |
| llm[qwen/qwen3.6-27b|v4] | +19.1% | -9.4 pts | 0.284 | +14.5% | -0.2% … +38.6% | 38% | -1.1 pts | +9.2% | -1.10 |
| llm[qwen/qwen3.6-27b|v2] | +5.0% | -23.5 pts | 0.642 | +7.6% | -8.3% … +18.3% | 25% | -5.6 pts | +0.0% | -5.57 |
