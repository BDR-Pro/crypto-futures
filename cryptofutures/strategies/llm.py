"""Decision agent backed by a local open-weight LLM via any OpenAI-compatible server.

The prompt is a pure function of market data at decision time (no account state),
so every answer can be cached. That makes re-running backtests and tuning the risk
layer free after the first pass, and makes runs reproducible.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

from ..config import LLMConfig
from ..features import FeatureStore
from .base import FLAT, LONG, SHORT, Decision, Strategy, decisions_frame

log = logging.getLogger(__name__)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": [LONG, SHORT, FLAT]},
        "confidence": {"type": "number"},
        "leverage": {"type": "integer"},
        "stop_loss_pct": {"type": "number"},
        "take_profit_pct": {"type": "number"},
        "reason": {"type": "string", "maxLength": 160},
    },
    "required": ["action", "confidence", "leverage", "stop_loss_pct", "take_profit_pct", "reason"],
}

SYSTEM_PROMPTS = {
    "v1": (
        "You are a crypto futures trader. Given market data for a USDT perpetual, decide the position "
        "to hold for the next bar: LONG, SHORT or FLAT. Also choose leverage (1-{max_lev}), a stop-loss "
        "and a take-profit as percent distance from entry. Reply with JSON only: "
        '{{"action": "LONG|SHORT|FLAT", "confidence": 0-1, "leverage": int, '
        '"stop_loss_pct": number, "take_profit_pct": number, "reason": "short"}}'
    ),
    "v2": (
        "You are a disciplined quantitative crypto futures trader managing one USDT-margined perpetual. "
        "Every {tf}h you decide the position to hold until the next decision: LONG, SHORT or FLAT.\n"
        "Rules:\n"
        "1. Capital preservation first. Choose FLAT when signals conflict, the market is choppy "
        "(low ADX, price hugging EMAs) or reward does not clearly exceed risk.\n"
        "2. Prefer trading in the direction of the daily trend. Counter-trend trades need strong evidence "
        "(RSI extreme + reversal in recent closes) and lower leverage.\n"
        "3. Stop-loss: place it beyond normal noise, typically 1.0-2.5x ATR%. Take-profit at least 1.5x the stop distance.\n"
        "4. Leverage 1-{max_lev}: scale inversely with volatility. Keep leverage x stop_loss_pct <= 15 "
        "(at most ~15% of posted margin lost at the stop). High funding against you is a cost.\n"
        "5. confidence is your calibrated probability (0-1) that the trade reaches take-profit before stop-loss. "
        "Below 0.55 means FLAT.\n"
        "Reply with a single JSON object and nothing else: "
        '{{"action": "LONG|SHORT|FLAT", "confidence": number, "leverage": integer, '
        '"stop_loss_pct": number (percent, e.g. 2.5), "take_profit_pct": number (percent), '
        '"reason": "max 25 words"}}'
    ),
}


def _pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def render_prompt(symbol: str, f: dict) -> str:
    closes = ", ".join(f"{c:.6g}" for c in f["recent_closes"])
    ranges = ", ".join(f"{r:.2f}" for r in f["recent_ranges_pct"])
    return (
        f"Symbol: {symbol} perpetual | Decision time: {f['time']:%Y-%m-%d %H:%M} UTC | Bars: {f['tf_hours']}h\n"
        f"Price: {f['price']:.6g}\n"
        f"Trend ({f['tf_hours']}h): price vs EMA20 {_pct(f['ema20_dist'])}, EMA50 {_pct(f['ema50_dist'])}, "
        f"EMA200 {_pct(f['ema200_dist'])}; EMA20>EMA50: {'yes' if f['ema20_gt_ema50'] else 'no'}; ADX {f['adx']:.1f}\n"
        f"Momentum: RSI14 {f['rsi']:.1f}; MACD hist {_pct(f['macd_hist_pct'])} of price; returns last bar "
        f"{_pct(f['ret_1'])}, 6 bars {_pct(f['ret_6'])}, 30 bars {_pct(f['ret_30'])}\n"
        f"Volatility: ATR14 {f['atr_pct'] * 100:.2f}% per bar; Bollinger position {f['bb_pos']:.2f} (0=lower band, 1=upper)\n"
        f"Range: {_pct(f['dist_hh20'])} from 20-bar high, {_pct(f['dist_ll20'])} from 20-bar low\n"
        f"Flow: volume {f['vol_ratio']:.2f}x 20-bar average; taker buy ratio {f['taker_buy_ratio']:.2f}\n"
        f"Daily: RSI {f['d_rsi']:.1f}; price vs EMA50 {_pct(f['d_ema50_dist'])}, vs EMA200 {_pct(f['d_ema200_dist'])}; "
        f"7d {_pct(f['d_ret_7'])}, 30d {_pct(f['d_ret_30'])}; ADX {f['d_adx']:.1f}\n"
        f"Funding rate (8h): {f['funding_rate'] * 100:+.4f}%\n"
        f"Last 12 closes (oldest first): {closes}\n"
        f"Last 12 bar ranges %: {ranges}"
    )


def parse_response(text: str) -> Decision:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError(f"no JSON object in response: {text[:200]!r}")
    obj = json.loads(match.group(0))
    action = str(obj.get("action", FLAT)).upper().strip()
    if action not in (LONG, SHORT, FLAT):
        action = FLAT

    def num(key, default=None):
        try:
            v = float(obj.get(key))
            return v if v == v else default
        except (TypeError, ValueError):
            return default

    conf = num("confidence", 0.5)
    if conf is not None and conf > 1:      # some models answer 0-100
        conf /= 100
    sl, tp = num("stop_loss_pct"), num("take_profit_pct")
    lev = num("leverage")
    return Decision(
        action=action,
        confidence=max(0.0, min(1.0, conf)),
        leverage=int(round(lev)) if lev else None,
        sl_pct=sl / 100 if sl and sl > 0 else None,
        tp_pct=tp / 100 if tp and tp > 0 else None,
        reason=str(obj.get("reason", ""))[:300],
    )


class DecisionCache:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.lock = threading.Lock()
        self.conn.execute("CREATE TABLE IF NOT EXISTS decisions (key TEXT PRIMARY KEY, model TEXT, "
                          "prompt_version TEXT, symbol TEXT, time TEXT, raw TEXT, created REAL)")
        self.conn.commit()

    def get(self, key: str) -> str | None:
        with self.lock:
            row = self.conn.execute("SELECT raw FROM decisions WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key: str, model: str, version: str, symbol: str, t: str, raw: str) -> None:
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO decisions VALUES (?,?,?,?,?,?,?)",
                              (key, model, version, symbol, t, raw, _time.time()))
            self.conn.commit()


class LLMClient:
    """Minimal OpenAI-compatible chat client with structured-output fallbacks."""

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self.session = requests.Session()
        self._format_mode = "json_schema"

    def _payload(self, messages, mode):
        p = {"model": self.cfg.model, "messages": messages, "temperature": self.cfg.temperature,
             "max_tokens": self.cfg.max_tokens, "seed": 42}
        if self.cfg.reasoning_effort:
            p["reasoning_effort"] = self.cfg.reasoning_effort
        if mode == "json_schema":
            p["response_format"] = {"type": "json_schema",
                                    "json_schema": {"name": "decision", "schema": RESPONSE_SCHEMA}}
        elif mode == "json_object":
            p["response_format"] = {"type": "json_object", "schema": RESPONSE_SCHEMA}
        return p

    def chat(self, messages: list[dict]) -> str:
        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.cfg.api_key}"}
        modes = ["json_schema", "json_object", "none"]
        for mode in modes[modes.index(self._format_mode):]:
            resp = self.session.post(url, json=self._payload(messages, mode), headers=headers, timeout=self.cfg.timeout)
            # Servers disagree on structured-output support and on how they reject it
            # (Ollama/vLLM: json_schema, llama-cpp-python: json_object, some answer 500).
            if resp.status_code in (400, 422, 500) and mode != "none" and "response_format" in resp.text:
                log.info("server rejected response_format=%s, falling back", mode)
                self._format_mode = modes[modes.index(mode) + 1]
                continue
            resp.raise_for_status()
            msg = resp.json()["choices"][0]["message"]
            return msg.get("content") or msg.get("reasoning_content") or ""
        raise RuntimeError("unreachable")


class SnapshotModelStrategy(Strategy):
    """A model queried once per (symbol, decision time) on a market snapshot.

    Handles parallel requests, retries, progress logging and the error -> FLAT fallback.
    """
    concurrency: int = 1

    def __init__(self):
        self.stats = {"cached": 0, "queried": 0, "errors": 0}

    def decide_one(self, symbol: str, features: dict) -> Decision:
        raise NotImplementedError

    def decide(self, symbol: str, store: FeatureStore, times: pd.DatetimeIndex) -> pd.DataFrame:
        snaps = {t: store.snapshot(t) for t in times}
        results: dict = {}

        def work(t):
            f = snaps[t]
            if f is None:
                return t, Decision(FLAT, 0.0, reason="warm-up")
            err: Exception | None = None
            for attempt in range(3):
                try:
                    return t, self.decide_one(symbol, f)
                except Exception as exc:  # network hiccup or unparsable answer
                    err = exc
                    _time.sleep(1 + attempt)
            self.stats["errors"] += 1
            log.warning("%s %s: model failed (%s) -> FLAT", symbol, t, err)
            return t, Decision(FLAT, 0.0, reason=f"error: {err}"[:200])

        started, done = _time.time(), 0
        with ThreadPoolExecutor(max_workers=max(1, self.concurrency)) as pool:
            for fut in as_completed([pool.submit(work, t) for t in times]):
                t, d = fut.result()
                results[t] = d
                done += 1
                if done % 50 == 0 or done == len(times):
                    log.info("%s %s: %d/%d decisions (%.1fs)", self.name, symbol, done, len(times), _time.time() - started)
        return decisions_frame(times, [results[t] for t in times])


class LLMStrategy(SnapshotModelStrategy):
    """Generative LLM: writes a JSON decision (action, confidence, leverage, SL, TP)."""

    def __init__(self, cfg: LLMConfig, max_leverage: int = 10, decision_hours: int = 4):
        super().__init__()
        self.cfg = cfg
        self.concurrency = cfg.concurrency
        self.max_leverage = max_leverage
        self.decision_hours = decision_hours
        self.client = LLMClient(cfg)
        self.cache = DecisionCache(cfg.cache_path)
        self.name = f"llm[{cfg.model}|{cfg.prompt_version}]"

    def system_prompt(self) -> str:
        return SYSTEM_PROMPTS[self.cfg.prompt_version].format(max_lev=self.max_leverage, tf=self.decision_hours)

    def _key(self, system: str, user: str) -> str:
        blob = json.dumps([self.cfg.model, self.cfg.temperature, system, user])
        return hashlib.sha256(blob.encode()).hexdigest()

    def decide_one(self, symbol: str, features: dict) -> Decision:
        system, user = self.system_prompt(), render_prompt(symbol, features)
        key = self._key(system, user)
        raw = self.cache.get(key)
        if raw is not None:
            self.stats["cached"] += 1
        else:
            raw = self.client.chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
            parse_response(raw)  # validate before caching
            self.cache.put(key, self.cfg.model, self.cfg.prompt_version, symbol, str(features["time"]), raw)
            self.stats["queried"] += 1
        return parse_response(raw)
