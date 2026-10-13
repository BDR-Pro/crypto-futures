# Robustness 2026-07-13 -> 2026-10-11

| strategy | return | vs B&H | timing p-value | shuffled median | bootstrap 5–95% | beats B&H in random windows | median excess | risk-perturbed median | robust score |
|---|---|---|---|---|---|---|---|---|---|
| donchian_breakout | +4.4% | -5.4 pts | 0.877 | +12.6% | -14.1% … +23.0% | 76% | +1.9 pts | +1.3% | +0.94 |
| buy_and_hold | +9.8% | +0.0 pts | 1.000 | +9.8% | +9.0% … +11.2% | 0% | +0.0 pts | +9.8% | +0.00 |
| llm[qwen/qwen3.6-27b|v2] | +7.4% | -2.5 pts | 0.229 | +3.7% | -1.2% … +16.1% | 39% | -1.5 pts | +0.9% | -1.46 |
| ema_trend | -6.4% | -16.2 pts | 0.963 | +6.0% | -19.6% … +7.7% | 28% | -1.5 pts | -3.1% | -1.48 |
| llm[openai/gpt-oss-120b|v2] | +0.4% | -9.5 pts | 0.817 | +3.7% | -7.1% … +7.7% | 18% | -2.3 pts | +0.2% | -2.30 |
| llm[deepseek/deepseek-v4-flash|v2] | -10.2% | -20.0 pts | 0.993 | +2.7% | -16.2% … -3.7% | 8% | -5.3 pts | -1.9% | -5.25 |
