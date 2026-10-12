# Sample results

These runs prove the pipeline end to end. They are **not** evidence of a profitable strategy.
Every model ran locally on a 4-core CPU with no GPU (llama.cpp / llama-cpp-python).

## `jev-style-2b-10coins/`: Jev-style decision model, all 10 coins, daily decisions, 11 Sep → 11 Oct 2026

Model: `chaoliangUNSW/Jev-Style-Qwen3.5-2B-Decision-GGUF` (Q8_0), loaded in-process. It made 300 decisions at
~13 s each with 0 errors. Settings: direction question only, leverage from confidence, SL/TP from ATR (`ask_risk = false`).

| strategy | return | Sharpe | max DD | trades | win rate | avg lev | direction accuracy |
|---|---|---|---|---|---|---|---|
| buy_and_hold (1x) | +8.4% | 2.30 | −9.9% | 10 | 90% | 1.0 | 55.3% |
| ema_trend | +0.7% | 0.14 | −22.5% | 35 | 43% | 3.0 | 54.0% |
| **jev (Jev-Style 2B)** | **−2.8%** | 0.22 | −26.1% | 29 | 34.5% | 3.7 | 52.7% |
| random | −10.2% | −2.45 | −18.7% | 150 | 49% | 3.0 | 51.6% |
| donchian_breakout | −23.5% | −4.17 | −29.5% | 34 | 27% | 3.0 | 45.3% |

What the diagnostics show:

- It said LONG on 260 of 300 calls, FLAT 36 times and SHORT 4 times. In practice it acted as a leveraged
  buy-and-hold: up to +26% during the rally, then nearly all of it lost in the 7 Oct sell-off (`equity.png`).
- Its probabilities have no predictive value here. The correlation between P(LONG) − P(SHORT) and the
  next-day move is −0.07, and higher-confidence calls were not more accurate. The model is calibrated on the
  text tasks it was trained on (sentiment, inference, topic), not on price forecasts.
- Its 52.7% direction accuracy is below the 55.3% that always-LONG scores in this rising month.
- Walk-forward tuning (`optimize.json`) found settings that looked great on the first 15 days but did no
  better on the next 15. The optimizer reported overfitting and kept the default settings.

## `head-to-head-5coins/`: Jev-style 2B vs Qwen3-1.7B, BTC/ETH/XRP/BNB/SOL, daily, 26 Sep → 11 Oct 2026

Same data and risk settings, both from cached answers. Qwen3-1.7B: −6.7% (24 trades, avg 7.5x leverage).
Jev-style 2B: −11.5% (6 trades, all losers). Buy-and-hold: −2.6%. Neither small model has an edge.

## `baselines-2y/`: rule-based baselines, top 10 perps, Sep 2024 → Oct 2026, 4h decisions

Over this period only `buy_and_hold` (1x) finished positive: +14.5%, with a −63% drawdown along the way.
Every active rule lost money after fees and funding. `random` went to ~0, which mostly shows the cost of churning.
An LLM has to clear this bar to be worth running.

## `qwen3-1.7b-demo/`: real local LLM vs baselines, 5 coins, daily decisions, 26 Sep → 11 Oct 2026

The decisions come from **Qwen3-1.7B** (Q8 GGUF) running on llama.cpp on a 4-core CPU sandbox with no GPU,
at about 30 s per call. A model this small, over a 15-day window, says nothing about edge. Use a bigger model and
a longer window (see the main README).

What the diagnostics show:

- `directional_accuracy` was 46.7%, so the model had no edge picking direction.
- The model said "LONG, confidence 0.75, 8x" almost every time (`llm_decisions.csv`), and its average leverage was 7.5x.
- `optimize.json`: on the unseen half, walk-forward tuning chose **max_leverage = 1** and
  **min_confidence = 0.65**. That cut the out-of-sample loss from −11.3% to −1.7% and the drawdown from −18.6% to −3.0%.
  This is the loop working as intended: the risk layer limits the damage from a model with no skill.
  Only a better model or prompt can add skill.
