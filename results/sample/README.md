# Sample results

These runs prove the pipeline end to end. They are **not** evidence of a profitable strategy.

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
