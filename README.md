# crypto-futures

Paper trading for crypto **perpetual futures**, with a **local open-weight LLM** making the calls.
Every few hours the model looks at each of the top-10 coins and answers **LONG / SHORT / FLAT**,
plus **leverage**, **stop-loss** and **take-profit**. A risk layer clamps those numbers, and a simulated
exchange fills the orders. A benchmark harness then scores the model against rule-based baselines,
and a walk-forward optimizer tunes the risk settings so each run can improve on the last.

> Paper trading only. Nothing here places real orders, and nothing here is financial advice.
> Leveraged futures can lose your whole margin quickly.

```
 Binance Vision history ─┐                ┌─> backtest ─> benchmark leaderboard ─> history.jsonl
 live prices (ccxt) ─────┼─> features ─> LLM decision ─> risk layer ─> paper exchange
                         │   (no look-ahead)   (cached)   (lev/SL/TP)  (fees, funding,
                         └──────────────────────────────────────────    SL/TP, liquidation)
                                                         optimize (walk-forward) ─> better [risk] config
```

## What it does

| Piece | Details |
|---|---|
| **Coins** | BTC, ETH, XRP, BNB, SOL, DOGE, TRX, ADA, LINK, AVAX (USDT-M perps). Any Binance futures symbol works: `--symbols`. |
| **Decision model** | Any local model behind an OpenAI-compatible API: Ollama (default), llama.cpp, vLLM, LM Studio. The default is `gpt-oss:20b`. |
| **Model output** | JSON: `action`, `confidence`, `leverage`, `stop_loss_pct`, `take_profit_pct`, `reason`. Structured output is enforced when the server supports it, and parsing tolerates `<think>` blocks. |
| **Model input** | 4h trend, momentum, volatility, range, volume and taker flow; daily trend context; funding rate; the last 12 closes. Only closed candles go in, so the model never sees the future. |
| **Risk layer** | Caps leverage. Clamps SL to a min/max. Keeps the SL inside the liquidation price. Filters by confidence. Sizes by margin or by risk. |
| **Paper exchange** | Isolated margin. 0.05% taker fee and 2 bps slippage. 8h funding from real history. SL, TP and liquidation are checked on hourly candles. If SL and TP hit in the same candle, the SL is assumed to fill first. Gaps fill at the open. |
| **Baselines** | `buy_and_hold`, `ema_trend`, `donchian_breakout`, `rsi_reversion`, `random`, `flat` |
| **Metrics** | Return, CAGR, Sharpe, Sortino, max drawdown, Calmar, win rate, profit factor, liquidations, fees, funding. Also directional accuracy (forecasting skill without the risk layer) and accuracy on high-confidence calls. |

## Quick start

```bash
pip install -e ".[live,plot,dev]"

# 1. a local model (pick one that fits your hardware, see below)
ollama pull gpt-oss:20b

# 2. history: hourly futures candles + funding for the top 10 (Binance Vision, no API key)
cryptofutures download --start 2024-01-01

# 3. LLM vs baselines on the same data
cryptofutures benchmark --start 2026-07-01 --end 2026-10-01 --tag first-run

# 4. tune SL/TP/leverage/confidence walk-forward (reuses the cached LLM answers)
cryptofutures optimize --strategy llm --start 2026-01-01 --end 2026-10-01 --folds 4

# 5. live paper trading on real-time prices
cryptofutures paper --strategy llm                 # Binance USD-M
cryptofutures paper --strategy llm --exchange okx  # if Binance is geo-blocked
```

You can also run `python -m cryptofutures <command>` without installing the package.

## Choosing the local model

"Best" depends on your GPU or RAM, so the harness lets you **measure it** rather than guess.
Every model below works with `--model <tag>`:

| Hardware | Suggested Ollama tags |
|---|---|
| CPU only / 8 GB | `qwen3:4b`, `qwen3:8b` |
| 16 GB VRAM / unified memory | `gpt-oss:20b` (default; reasoning model, strong at structured output), `qwen3:14b` |
| 24 GB+ | `qwen3:32b`, `qwen3:30b-a3b` (fast MoE), `deepseek-r1:32b` |
| 80 GB+ | `gpt-oss:120b`, `qwen3:235b-a22b` |

Newer families (Qwen 3.x, GLM, DeepSeek) ship often. Check <https://ollama.com/library> and benchmark them yourself:

```bash
cryptofutures benchmark --strategies llm:gpt-oss:20b,llm:qwen3:14b,llm:qwen3:8b,ema_trend,buy_and_hold \
  --start 2026-07-01 --end 2026-10-01 --tag model-shootout
```

Strategy specs use the form `llm:<model>@<prompt_version>`, for example `llm:qwen3:14b@v1`.
To use llama.cpp instead of Ollama, pass `--base-url http://localhost:8080/v1`.

Speed matters: 10 coins × 6 decisions/day × 90 days is 5,400 calls. Every answer is cached in
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
   and reports tuned vs default. It writes `results/best_risk_<strategy>.toml`; paste that into `config.toml`.
4. **Iterate the model side.** Add a prompt version to `SYSTEM_PROMPTS` in
   `cryptofutures/strategies/llm.py` (for example `v3`), or try another model, then benchmark again.
5. **Track progress.** `cryptofutures history --rank-by sharpe` ranks every run you've done.

Judge on out-of-sample numbers. A tuned config that only wins in-sample is curve-fitting.

## Layout

```
cryptofutures/
  data.py        Binance Vision downloader (klines + funding), live candles via ccxt
  features.py    indicators + leak-free market snapshot at decision time
  strategies/    llm.py (prompting, parsing, cache), baselines.py, base.py
  risk.py        model decision -> order (leverage, SL/TP, size), with hard clamps
  engine.py      paper futures exchange + backtest loop
  metrics.py     performance + directional accuracy
  benchmark.py   multi-strategy leaderboard + history
  optimize.py    walk-forward risk-parameter tuning
  live.py        real-time paper trader (state persisted in results/live_state.json)
  cli.py         command line
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
