# Robustness 2026-07-13 -> 2026-10-11

| strategy | return | vs B&H | timing p-value | shuffled median | bootstrap 5–95% | beats B&H in random windows | median excess | risk-perturbed median | robust score |
|---|---|---|---|---|---|---|---|---|---|
| buy_and_hold | +28.5% | +0.0 pts | 1.000 | +28.5% | +21.1% … +35.8% | 0% | +0.0 pts | +28.5% | +0.00 |
| donchian_breakout | -1.6% | -30.1 pts | 0.965 | +26.8% | -38.5% … +35.5% | 32% | -1.7 pts | -0.5% | -1.68 |
| llm[qwen/qwen3.6-27b|v2] | +5.0% | -23.5 pts | 0.642 | +7.6% | -8.3% … +18.3% | 25% | -5.6 pts | +0.0% | -5.57 |
| llm[openai/gpt-oss-120b|v2] | -3.0% | -31.5 pts | 0.925 | +6.4% | -14.1% … +8.4% | 2% | -7.8 pts | +0.0% | -7.75 |
| llm[deepseek/deepseek-v4-flash|v2] | -11.2% | -39.7 pts | 1.000 | +6.1% | -21.6% … -0.3% | 4% | -10.4 pts | -2.0% | -10.36 |
