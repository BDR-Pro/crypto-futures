# Top-3 hosted models, 90 days (13 Jul → 11 Oct 2026), daily decisions

Models via OpenRouter, prompt v2, all answers cached: 900 decisions per model (DeepSeek 895; 5 malformed
answers count as FLAT). About $6.50 of OpenRouter credit in total.

## All 10 coins: `leaderboard_10coins.md`, `robustness_10coins_*.md`

| strategy | return | Sharpe | max DD | trades | profit factor | timing p-value | beats B&H in random windows |
|---|---|---|---|---|---|---|---|
| buy_and_hold | **+28.5%** | 2.90 | −10.4% | 10 | – | – | – |
| **Qwen3.6-27B** | +5.0% | 0.85 | −8.2% | 97 | 1.19 | 0.64 | 25% |
| Qwen3.6-27B, tuned risk | +6.9% | – | – | – | – | 0.19 | 12% |
| donchian_breakout | −1.6% | 0.32 | −37.9% | 95 | 0.98 | 0.97 | 32% |
| gpt-oss-120b | −3.0% | −0.43 | −11.5% | 101 | 0.89 | 0.93 | 2% |
| DeepSeek V4 Flash | −11.2% | −1.75 | −12.7% | 93 | 0.63 | 1.00 | 4% |
| random | −29.9% | −3.51 | −32.7% | 463 | 0.78 | – | – |

- The models sat FLAT about 70% of the time (Qwen 646 FLAT / 220 LONG / 34 SHORT) and missed most of a strong rally.
- Qwen stays the best model and the only one in profit, but its timing signal from the 4-coin subset did not hold
  across 10 coins (p = 0.64 default, 0.19 tuned). No model shows statistically meaningful timing skill yet.
- Champion for this setup (`results/champion.json`): buy_and_hold.

## First pass: 4 coins (BTC, ETH, XRP, BNB)

The first run hit the OpenRouter credit limit; these 4 coins were fully covered at that point.

## Benchmark (4 coins, default risk settings): `leaderboard_4coins.md`

| strategy | return | Sharpe | max DD | trades | profit factor | direction acc. |
|---|---|---|---|---|---|---|
| buy_and_hold | +9.8% | 2.58 | −5.0% | 4 | – | 54.7% |
| **Qwen3.6-27B** | **+7.4%** | 1.65 | −4.3% | 40 | 1.84 | 53.5% |
| donchian_breakout | +4.4% | 0.71 | −17.0% | 32 | 1.17 | 53.4% |
| gpt-oss-120b | +0.4% | 0.17 | −5.5% | 37 | 1.04 | 49.3% |
| random | −3.5% | −0.50 | −9.4% | 177 | 0.92 | 49.3% |
| ema_trend | −6.4% | −1.00 | −11.4% | 33 | 0.73 | 50.6% |
| DeepSeek V4 Flash | −10.2% | −2.80 | −10.5% | 40 | 0.33 | 41.3% |

## Randomized tests: `robustness_default_risk.md`, `robustness_tuned_risk.md`

300 timing shuffles, trade bootstrap, 80 random 30-day windows on random 3-coin subsets, 40 random risk settings.

- Qwen3.6-27B beat 77% of its own timing shuffles with default risk (p = 0.23), and 90% (p = 0.096) with the
  walk-forward-tuned settings (`qwen_tuned_risk.toml`: ATR stops 3×, 3:1 target, min confidence 0.65).
  This is the strongest signal so far, but many variants were tried, so treat it as a lead, not proof.
- No model beat buy-and-hold in most random windows (Qwen: 34–39%). DeepSeek's timing was worse than 99% of shuffles.
- Champion (`results/champion.json`): donchian_breakout with the tuned risk settings, which beat buy-and-hold
  in 72% of random windows; its timing is not significant (p = 0.96), so its score is halved.

## Prompt test: `prompt_v2_vs_v3_btc_eth.md`

v3 asks for symmetric bull/bear reasoning. It fixed the long bias (15 shorts vs 2), but returned +1.0% against
v2's +5.6% on BTC+ETH in this rising quarter. v2 stays the default.
