# crypto-futures

Paper trading for crypto **perpetual futures**, with **local open-weight models** making the calls.
Every few hours a model looks at each of the top-10 coins and decides **LONG / SHORT / FLAT**,
plus **leverage**, **stop-loss** and **take-profit**. A risk layer clamps those numbers, and a simulated
exchange fills the orders. A benchmark harness scores each model against rule-based baselines,
and a walk-forward optimizer tunes the risk settings so each run can improve on the last.

**Everything runs on your machine.** The models are GGUF files run by llama.cpp, either loaded in-process
(the decision models) or served on `127.0.0.1` (the generative LLM). Market history is downloaded once into `data/`. After that, backtests, benchmarks and the
optimizer need no internet and no API keys. Only live paper trading reads prices from an exchange's public
feed, because real-time prices can't come from anywhere else.

> Paper trading only. Nothing here places real orders, and nothing here is financial advice.
> Leveraged futures can lose your whole margin quickly.

```
 data/ (Binance Vision history, local) ─┐               ┌─> backtest ─> benchmark leaderboard ─> history.jsonl
 live prices (public feed, paper mode) ─┼─> features ─> model decision ─> risk layer ─> paper exchange
                                        │  (no look-ahead)  (local, cached) (lev/SL/TP)   (fees, funding,
                                        └─────────────────────────────────────────────    SL/TP, liquidation)
                                                              optimize (walk-forward) ─> better [risk] config
```

## Decision models

| Strategy | Model | How it decides |
|---|---|---|
| `nimble` (default) | **Bespoke-Nimble-9B v3** by Bespoke Labs: a Qwen3.5-9B LoRA, an open alternative to TypeSafe's Jev. GGUF: `ggml-org/Bespoke-Nimble-9B-v3-GGUF` (Q4_K_M, 6.3 GB). **Licence: CC BY-NC 4.0, non-commercial use only.** | It does not write text. The market state goes in as context with a typed schema of four fields: `position` (LONG/SHORT/FLAT), `leverage` (1/2/3/5/10x), `stop_loss` (1–3× ATR) and `take_profit` (1–3× the stop). For each field it scores the allowed answer letters and returns softmax probabilities, using Bespoke's exact prompt format. The most likely `position` is the action and its probability is the confidence. The model also picks leverage, SL and TP. All four fields share one evaluated prompt prefix: the model state is snapshotted after the shared part, so the extra fields cost seconds, not minutes. Runs in-process with llama-cpp-python: about 80 s per decision on 4 CPU cores, far less on a GPU (`n_gpu_layers = -1`). |
| `jev` | **Jev-Style 2B**: `chaoliangUNSW/Jev-Style-Qwen3.5-2B-Decision-GGUF` (Apache-2.0), a smaller Jev-style model. | Same idea with its own prompt format: one typed question per call, answered as calibrated probabilities from a single token. By default only direction is asked; leverage scales with confidence and SL/TP come from ATR. About 13 s per decision on CPU. |
| `llm` | Generative LLM (Qwen3, gpt-oss, DeepSeek, ...) | Writes a JSON decision: `action`, `confidence`, `leverage`, `stop_loss_pct`, `take_profit_pct`, `reason`. |

About Jev: TypeSafe AI released Jev on 15 Sep 2026 as a closed, hosted decision API. Open-weight alternatives followed
within days, mostly built on Qwen3.5 with a LoRA adapter. Bespoke Labs' Nimble is the default here: it ships an official
llama.cpp GGUF, and Bespoke published the model, training recipe and evaluation setup. Its v3 scores 56.88 on Decision Index 0.2.1.
Its licence is non-commercial; for commercial use, the Apache-2.0 Jev-Style 2B (`jev`) is the alternative here. Other options include
`autotrust/JEV-9B` / `JEV-27B` (vLLM, GPU) and `jaredpalmer/kev-*`.

## What it does

| Piece | Details |
|---|---|
| **Coins** | BTC, ETH, XRP, BNB, SOL, DOGE, TRX, ADA, LINK, AVAX (USDT-M perps). Any Binance futures symbol works: `--symbols`. |
| **Model input** | Trend, momentum, volatility, range, volume and taker flow on the decision timeframe; daily trend context; funding rate; the last 12 closes. Only closed candles go in, so the model never sees the future. |
| **Risk layer** | Caps leverage. Clamps SL to a min/max. Keeps the SL inside the liquidation price. Filters by confidence. Sizes by margin or by risk. |
| **Paper exchange** | Isolated margin. 0.05% taker fee and 2 bps slippage. 8h funding from real history. SL, TP and liquidation are checked on hourly candles. If SL and TP hit in the same candle, the SL is assumed to fill first. Gaps fill at the open. |
| **Baselines** | `buy_and_hold`, `ema_trend`, `donchian_breakout`, `rsi_reversion`, `random`, `flat` |
| **Metrics** | Return, CAGR, Sharpe, Sortino, max drawdown, Calmar, win rate, profit factor, liquidations, fees, funding. Also directional accuracy (forecasting skill without the risk layer) and accuracy on high-confidence calls. |

## Quick start (all local)

```bash
pip install -e ".[local,live,plot,dev]"

# 1. local models: download the GGUFs into ./models once (Nimble 6.3 GB, Jev-Style 2.1 GB, Qwen3-8B 5 GB).
#    The decision models (nimble, jev) load in-process, no server. The generative LLM is served on 127.0.0.1:8080.
scripts/serve_local.sh download
scripts/serve_local.sh llm &          # only needed for the `llm` strategy; GPU_LAYERS=-1 offloads to a GPU

# 2. history: hourly futures candles + funding for the top 10 into ./data (one time, no API key)
cryptofutures download --start 2024-01-01

# 3. backtest + benchmark: decision models vs baselines on the same data
cryptofutures backtest  --strategy nimble --start 2026-09-26 --end 2026-10-11 --decision-hours 24
cryptofutures benchmark --strategies nimble,jev,llm,buy_and_hold,ema_trend,random --start 2026-07-01 --end 2026-10-01

# 4. tune SL/TP/leverage/confidence walk-forward (reuses the cached model answers)
cryptofutures optimize --strategy nimble --start 2026-07-01 --end 2026-10-01 --folds 4

# 5. live paper trading on real-time prices
cryptofutures paper --strategy nimble              # Binance USD-M public feed
cryptofutures paper --strategy nimble --exchange okx  # if Binance is geo-blocked
```

You can also run `python -m cryptofutures <command>` without installing the package.

## Choosing the generative model

"Best" depends on your GPU or RAM, so the harness lets you **measure it** rather than guess.
Use `scripts/serve_local.sh` with `LLM_REPO`/`LLM_FILE` set to any GGUF. With Ollama, set
`[llm] base_url = "http://localhost:11434/v1"` and pass `--model <tag>`:

| Hardware | Suggested models |
|---|---|
| CPU only / 8 GB | Qwen3-4B, Qwen3-8B (Q4_K_M) |
| 16 GB VRAM / unified memory | `gpt-oss:20b` (reasoning model, strong at structured output), Qwen3-14B |
| 24 GB+ | Qwen3-32B, Qwen3-30B-A3B (fast MoE), DeepSeek-R1-32B |
| 80 GB+ | `gpt-oss:120b`, Qwen3-235B-A22B |

Newer families ship often, so benchmark them yourself:

```bash
cryptofutures benchmark --strategies nimble,jev,llm:gpt-oss:20b,llm:qwen3:14b,ema_trend,buy_and_hold \
  --start 2026-07-01 --end 2026-10-01 --tag model-shootout
```

### Optional: hosted models through OpenRouter

Everything above runs locally. To try models too big for your machine, point the `llm` strategy at
[OpenRouter](https://openrouter.ai). The decision models (`nimble`, `jev`) stay local, because they need raw
answer-token logits from their own weights.

```bash
export OPENROUTER_API_KEY=sk-or-...        # read from the environment, only ever sent to openrouter.ai
cryptofutures benchmark --base-url https://openrouter.ai/api/v1 \
  --strategies "llm:openai/gpt-oss-120b,llm:qwen/qwen3.6-27b,nimble,buy_and_hold" --start 2026-09-26 --end 2026-10-11
```

Answers are cached like local ones, so re-runs and optimizer sweeps cost nothing. TypeSafe's own
`typesafe/jev-router` is also listed there; it routes to generative models, so it fits the `llm` strategy.

Strategy specs: `llm:<model>@<prompt_version>` (for example `llm:qwen3:14b@v1`), `jev:<model>@<question_set>`
and `nimble:<path to gguf>@<schema>`.

Speed matters: 10 coins × 6 decisions/day × 90 days is 5,400 calls. On a 4-core CPU the Jev-style 2B
takes about 13 s per decision and Qwen3-1.7B about 30 s; a GPU is 10-50× faster. Every answer is cached in
`data/llm_cache.sqlite`, keyed by model + prompt. Re-runs, optimizer sweeps and repeated benchmarks
therefore cost nothing after the first pass. Raise `--concurrency` and set `OLLAMA_NUM_PARALLEL` to match.

## The improvement loop

1. **Benchmark.** `cryptofutures benchmark` writes `results/<run>/leaderboard.md`, `equity.png`,
   and per-strategy trades, decisions and per-symbol PnL. It also appends one row per strategy to
   `results/history.jsonl`.
2. **Read the diagnostics.** `directional_accuracy` near 50% means the model has no edge in picking
   direction. In that case fix the prompt or model, not the SL/TP. If `accuracy_high_conf` beats overall
   accuracy, the confidence scores carry signal, so raise `min_confidence`. Many `liquidations` or a
   high `avg_leverage` mean `max_leverage` should come down.
3. **Tune the risk layer out-of-sample.** `cryptofutures optimize` searches SL source (model vs ATR),
   ATR multiple, reward:risk, max leverage, confidence threshold, margin per trade and flat behaviour.
   It picks parameters on an expanding training window, scores them on the next unseen window,
   and reports tuned vs default. The tuned settings are recommended only if they beat the defaults
   on that unseen data; otherwise it tells you the tuning overfit and keeps your current settings.
   It writes `results/best_risk_<strategy>.toml`; paste that into `config.toml`.
4. **Iterate the model side.** Add a prompt version to `SYSTEM_PROMPTS` in
   `cryptofutures/strategies/llm.py` (for example `v3`), or try another model, then benchmark again.
5. **Track progress.** `cryptofutures history --rank-by sharpe` ranks every run you've done.

Judge on out-of-sample numbers. A tuned config that only wins in-sample is curve-fitting.

## Sample results

`results/sample/` holds the runs made while building this repo, all on a 4-core CPU with local models:

- **Jev-style 2B decision model, 10 coins, 30 days: −2.8%.** Buy-and-hold made +8.4%. The model said LONG
  87% of the time, and its probabilities did not predict the next day's move (correlation −0.07).
  It behaved like leveraged buy-and-hold: +26% at the peak, then lost in the 7 Oct sell-off.
- **Head-to-head on 5 coins, 15 days:** Qwen3-1.7B −6.7%, Jev-style 2B −11.5%, buy-and-hold −2.6%.
- **Baselines over 2 years:** only buy-and-hold finished positive (+14.5%), with a 63% drawdown.
- **The optimizer** cut Qwen3-1.7B's out-of-sample loss from −11.3% to −1.7% (1x leverage, stricter confidence).
  For the Jev model it correctly reported that tuning overfit and kept the defaults.

So far no small model shows an edge. The harness is there to find out whether bigger models
(JEV-9B/27B, gpt-oss-20b, Qwen3-32B on a GPU) do. See `results/sample/README.md` for details.

## Layout

```
cryptofutures/
  data.py        Binance Vision downloader (klines + funding), live candles via ccxt
  features.py    indicators + leak-free market snapshot at decision time
  strategies/    nimble.py (Bespoke-Nimble), jev.py (Jev-Style), llm.py (generative LLM, cache), baselines.py, base.py
  risk.py        model decision -> order (leverage, SL/TP, size), with hard clamps
  engine.py      paper futures exchange + backtest loop
  metrics.py     performance + directional accuracy
  benchmark.py   multi-strategy leaderboard + history
  optimize.py    walk-forward risk-parameter tuning
  live.py        real-time paper trader (state persisted in results/live_state.json)
  cli.py         command line
scripts/         serve_local.sh - download GGUFs once and serve them on 127.0.0.1
tests/           engine math, liquidation, fees/funding, no-look-ahead, parsing
config.toml      all settings
```

## Assumptions and limits

- Hourly candles can't show the order of prices inside the hour. The stop is assumed to hit before the target.
- Liquidation uses a simplified isolated-margin formula (`entry × (1 ∓ 1/lev ± mmr)`), and a liquidation
  loses the full position margin.
- Live paper mode checks SL and TP against the last price every `--poll` seconds. A wick shorter
  than that can be missed.
- An LLM call that fails after 3 retries becomes FLAT and is not cached, so the next run retries it.
- Past performance, especially from a short benchmark window, says little about the future.
