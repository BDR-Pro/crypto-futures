# crypto-futures

Paper trading for crypto **perpetual futures**, with **local open-weight models** making the calls.
Every few hours a model looks at each of the top-10 coins and decides **LONG / SHORT / FLAT**,
plus **leverage**, **stop-loss** and **take-profit**. A risk layer clamps those numbers, and a simulated
exchange fills the orders. A benchmark harness scores each model against rule-based baselines,
and a walk-forward optimizer tunes the risk settings so each run can improve on the last.

**Everything runs on your machine.** The models are GGUF files served by llama.cpp (or Ollama / LM Studio)
on `127.0.0.1`. Market history is downloaded once into `data/`. After that, backtests, benchmarks and the
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

## Two kinds of decision model

| Strategy | Model type | How it decides |
|---|---|---|
| `jev` | **Jev-style decision model**: a "System 1" model like TypeSafe's Jev, open-weight reproduction. Default: `chaoliangUNSW/Jev-Style-Qwen3.5-2B-Decision-GGUF` (Apache-2.0). | It does not write text. It reads the market state plus a typed question with declared options, and returns a **calibrated probability for each option** from a single token. The direction question gives P(LONG), P(SHORT), P(FLAT); the most likely option is the action and its probability is the confidence. With `ask_risk = true` it also picks leverage, stop width (in ATR) and target (multiple of the stop). With `ask_risk = false` (fast on CPU), leverage scales with confidence and SL/TP come from ATR. The GGUF loads in-process with llama-cpp-python and only the last token's logits are computed: about 13 s per decision on 4 CPU cores. `backend = "server"` uses llama-server or LM Studio instead. |
| `llm` | Generative LLM (Qwen3, gpt-oss, DeepSeek, ...) | Writes a JSON decision: `action`, `confidence`, `leverage`, `stop_loss_pct`, `take_profit_pct`, `reason`. |

About Jev: TypeSafe AI released Jev on 15 Sep 2026 as a closed, hosted decision API. Open-weight clones followed
within days, mostly built on Qwen3.5 with a LoRA adapter and a decision head. Examples are `autotrust/JEV-9B` / `JEV-27B`
(vLLM, GPU), `jaredpalmer/kev-*`, `openjev/openjev` (non-commercial licence), `TokenRhythm/NeoHorse-Jev-4B` and the
`chaoliangUNSW/Jev-Style-*` GGUFs. The Jev-Style v1 GGUF is used here because stock llama.cpp runs it directly, through
token log-probs. The v3 GGUFs score higher but need a custom scorer built against a pinned llama.cpp commit.

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

# 1. local models: download the GGUFs into ./models once.
#    The Jev-style model then loads in-process (no server). The generative LLM is served on 127.0.0.1:8080.
scripts/serve_local.sh download
scripts/serve_local.sh llm &          # only needed for the `llm` strategy; GPU_LAYERS=-1 offloads to a GPU

# 2. history: hourly futures candles + funding for the top 10 into ./data (one time, no API key)
cryptofutures download --start 2024-01-01

# 3. backtest + benchmark: decision models vs baselines on the same data
cryptofutures backtest  --strategy jev --start 2026-09-11 --end 2026-10-11 --decision-hours 24
cryptofutures benchmark --strategies jev,llm,buy_and_hold,ema_trend,random --start 2026-07-01 --end 2026-10-01

# 4. tune SL/TP/leverage/confidence walk-forward (reuses the cached model answers)
cryptofutures optimize --strategy jev --start 2026-07-01 --end 2026-10-01 --folds 4

# 5. live paper trading on real-time prices
cryptofutures paper --strategy jev                 # Binance USD-M public feed
cryptofutures paper --strategy jev --exchange okx  # if Binance is geo-blocked
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
cryptofutures benchmark --strategies jev,llm:gpt-oss:20b,llm:qwen3:14b,ema_trend,buy_and_hold \
  --start 2026-07-01 --end 2026-10-01 --tag model-shootout
```

Strategy specs: `llm:<model>@<prompt_version>` (for example `llm:qwen3:14b@v1`) and `jev:<model>@<question_set>`.

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

`results/sample/` holds two runs made while building this repo:

- A 2-year baseline leaderboard. Only buy-and-hold finished positive, with a 63% drawdown.
- A smoke test of a real local model: Qwen3-1.7B on CPU, 5 coins, 15 days. The tiny model had no directional
  edge and over-used leverage. The walk-forward optimizer then cut its leverage to 1x and raised the confidence
  filter, which reduced the out-of-sample loss from −11.3% to −1.7%.

See `results/sample/README.md` for details. Run your own benchmarks with a bigger model and a longer window.

## Layout

```
cryptofutures/
  data.py        Binance Vision downloader (klines + funding), live candles via ccxt
  features.py    indicators + leak-free market snapshot at decision time
  strategies/    jev.py (Jev-style typed decisions), llm.py (generative LLM, cache), baselines.py, base.py
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
