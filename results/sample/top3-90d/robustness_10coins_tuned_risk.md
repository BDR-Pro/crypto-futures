# Robustness 2026-07-13 -> 2026-10-11

| strategy | return | vs B&H | timing p-value | shuffled median | bootstrap 5–95% | beats B&H in random windows | median excess | risk-perturbed median | robust score |
|---|---|---|---|---|---|---|---|---|---|
| donchian_breakout | -2.8% | -31.2 pts | 0.980 | +32.9% | -39.8% … +36.6% | 44% | -1.3 pts | -0.5% | -1.27 |
| llm[qwen/qwen3.6-27b|v2] | +6.9% | -21.6 pts | 0.194 | +3.1% | -1.4% … +15.7% | 12% | -5.9 pts | +0.0% | -5.91 |
