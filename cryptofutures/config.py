"""Configuration loading (TOML) with dataclass defaults."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from typing import Any

# Top-10 non-stablecoin USDT-margined perpetuals by market cap.
TOP10 = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT", "SOLUSDT",
    "DOGEUSDT", "TRXUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT",
]


@dataclass
class DataConfig:
    symbols: list[str] = field(default_factory=lambda: list(TOP10))
    base_interval: str = "1h"          # simulation resolution (SL/TP/liquidation checks)
    data_dir: str = "data"
    start: str = "2024-01-01"
    end: str = "2026-09-30"


@dataclass
class ExchangeConfig:
    initial_equity: float = 10_000.0
    taker_fee: float = 0.0005          # 0.05% per side (Binance USD-M taker)
    slippage: float = 0.0002           # 2 bps adverse fill
    maint_margin_rate: float = 0.005   # maintenance margin rate used for liquidation price
    use_funding: bool = True           # apply 8h funding payments if data is available


@dataclass
class RiskConfig:
    decision_hours: int = 4            # how often the model is asked for a decision
    max_leverage: int = 10
    default_leverage: int = 3
    sizing: str = "margin"             # "margin": margin_per_trade * leverage = notional
                                       # "risk":   size so hitting SL loses risk_per_trade
    margin_per_trade: float = 0.08     # fraction of equity posted as margin per position
    risk_per_trade: float = 0.01       # fraction of equity lost at SL (sizing="risk")
    sl_source: str = "model"           # "model": use model SL/TP (clamped); "atr": ATR multiples
    atr_sl_mult: float = 1.5
    reward_risk: float = 2.0           # TP distance = reward_risk * SL distance (atr mode / fallback)
    min_sl_pct: float = 0.004
    max_sl_pct: float = 0.08
    min_confidence: float = 0.55       # ignore signals below this confidence
    flat_closes: bool = True           # a FLAT decision closes an open position
    max_open_positions: int = 10
    leverage_override: int = 0         # >0: force this leverage on every trade (leverage experiments)
    liq_guard: str = "reduce_leverage" # keep the stop inside liquidation by: "reduce_leverage" |
                                       # "tighten_stop" (keep leverage, pull the stop in) | "off" (liquidations happen)


@dataclass
class LLMConfig:
    # Any OpenAI-compatible server works: Ollama, llama.cpp server, vLLM, LM Studio.
    base_url: str = "http://localhost:11434/v1"
    model: str = "gpt-oss:20b"
    api_key: str = "local"
    # Optional hosted fallback: with base_url = "https://openrouter.ai/api/v1" the key is read from this
    # env var (it is only ever sent to openrouter.ai) and model is an OpenRouter id, e.g. "openai/gpt-oss-120b".
    api_key_env: str = "OPENROUTER_API_KEY"
    temperature: float = 0.0
    max_tokens: int = 600
    timeout: float = 180.0
    concurrency: int = 2
    prompt_version: str = "v2"
    reasoning_effort: str = "low"      # for reasoning models that honour it (gpt-oss)
    cache_path: str = "data/llm_cache.sqlite"
    cache_only: bool = False           # never call the model: cached answers only, misses become FLAT


@dataclass
class JevConfig:
    # Jev-style decision model (typed choice -> calibrated probabilities, no text generation),
    # served locally by llama.cpp / llama-cpp-python / LM Studio.
    backend: str = "local"            # "local": load the GGUF in this process (llama-cpp-python, no server)
                                       # "server": any OpenAI-compatible server returning top_logprobs
    model_path: str = "models/Jev-Style-Qwen3.5-2B-Decision-Q8_0.gguf"
    n_ctx: int = 4096
    n_threads: int = 0                 # 0 = auto
    n_gpu_layers: int = 0              # -1 = offload everything to the GPU
    base_url: str = "http://127.0.0.1:8081/v1"
    model: str = "jev-style-2b"
    api_key: str = "local"
    timeout: float = 120.0
    concurrency: int = 1
    question_set: str = "j1"
    ask_risk: bool = False             # True: also ask leverage / stop width / target (4 questions per trade;
                                       # use with a GPU). False: leverage from confidence, SL/TP from ATR.
    cache_path: str = "data/llm_cache.sqlite"


@dataclass
class NimbleConfig:
    # Bespoke-Nimble-9B (Bespoke Labs): Qwen3.5-9B decision model, open alternative to Jev.
    # Loaded in-process from a GGUF with llama-cpp-python; nothing leaves the machine.
    model_path: str = "models/Bespoke-Nimble-9B-v3-Q4_K_M.gguf"
    n_ctx: int = 4096
    n_threads: int = 0                 # 0 = auto
    n_gpu_layers: int = 0              # -1 = offload everything to the GPU
    temperature: float = 1.0           # softmax temperature on candidate logits (Bespoke's default)
    schema_version: str = "n1"
    ask_risk: bool = True              # also score leverage / stop / target fields (cheap: shared prefix)
    concurrency: int = 1
    cache_path: str = "data/llm_cache.sqlite"


@dataclass
class LiveConfig:
    exchange: str = "binanceusdm"      # any ccxt id; "okx" works where Binance is geo-blocked
    state_path: str = "results/live_state.json"
    log_path: str = "results/live_trades.csv"


@dataclass
class Config:
    data: DataConfig = field(default_factory=DataConfig)
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    jev: JevConfig = field(default_factory=JevConfig)
    nimble: NimbleConfig = field(default_factory=NimbleConfig)
    live: LiveConfig = field(default_factory=LiveConfig)


def _merge(obj: Any, values: dict[str, Any]) -> Any:
    known = {f.name: f for f in fields(obj)}
    updates = {}
    for key, val in values.items():
        if key not in known:
            raise KeyError(f"unknown config key {type(obj).__name__}.{key}")
        cur = getattr(obj, key)
        updates[key] = _merge(cur, val) if is_dataclass(cur) and isinstance(val, dict) else val
    return replace(obj, **updates)


def load_config(path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> Config:
    cfg = Config()
    if path:
        with open(path, "rb") as fh:
            cfg = _merge(cfg, tomllib.load(fh))
    if overrides:
        cfg = _merge(cfg, overrides)
    return cfg


def with_risk(cfg: Config, **kw: Any) -> Config:
    return replace(cfg, risk=replace(cfg.risk, **kw))


def utc(ts):
    """Timestamp in UTC from a string, naive or aware datetime."""
    import pandas as pd
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
