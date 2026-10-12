"""Decision agent backed by a local Jev-style decision model.

Jev (TypeSafe AI, 2026) popularised "System 1" decision models: instead of writing
text, the model reads a state plus a typed question with declared options and
returns a calibrated probability for every option from a single token position.
Open-weight reproductions (e.g. chaoliangUNSW/Jev-Style-Qwen3.5-2B-Decision-GGUF)
run on stock llama.cpp: we request one token with top log-probs and renormalise
the probabilities of the option letters.

Each decision asks the direction question; when the answer is not FLAT it also
asks leverage, stop width and target questions about the same state. The state
comes first in the prompt, so llama.cpp reuses its KV cache for the follow-ups.
"""
from __future__ import annotations

import hashlib
import json
import math

import requests

from ..config import JevConfig
from .base import FLAT, LONG, SHORT, Decision
from .llm import DecisionCache, SnapshotModelStrategy, render_prompt

LETTERS = "ABCDEFGHIJKLMNOPQRST"
HEADER = ("You are a decision function. Read the state, then answer the question "
          "by choosing exactly one option.\n\n")

# question_set -> question key -> (question template, [(option text, value)])
QUESTION_SETS = {
    "j1": {
        "direction": (
            "Market data for a USDT perpetual future is shown above. A disciplined trader must hold one "
            "position for the next {tf} hours, paying fees on every trade. Which position has the best "
            "risk-adjusted expected return?",
            [("LONG: the price is more likely to rise", LONG),
             ("SHORT: the price is more likely to fall", SHORT),
             ("FLAT: no clear edge, stay out", FLAT)]),
        "leverage": (
            "Given this volatility and trend strength, how much leverage is prudent for this trade?",
            [("1x (very risky conditions)", 1), ("2x", 2), ("3x", 3), ("5x", 5), ("10x (calm, strong trend)", 10)]),
        "stop": (
            "Where should the stop-loss go, measured in multiples of the ATR (average bar range)?",
            [("1x ATR (tight)", 1.0), ("1.5x ATR", 1.5), ("2x ATR", 2.0), ("3x ATR (wide)", 3.0)]),
        "target": (
            "How far should the take-profit be, relative to the stop-loss distance?",
            [("1x the stop distance", 1.0), ("1.5x", 1.5), ("2x", 2.0), ("3x the stop distance", 3.0)]),
    },
}


def build_prompt(state: str, question: str, options: list[str]) -> str:
    lines = "\n".join(f"{LETTERS[i]}. {o}" for i, o in enumerate(options))
    return f"{HEADER}[State]\n{state}\n\n[Question]\n{question}\n\n[Options]\n{lines}\n\nAnswer:"


def option_probabilities(top_logprobs: dict[str, float], n_options: int) -> list[float]:
    """Renormalise the log-probs of the option letters (' A', ' B', ...) into a distribution."""
    floor = min(top_logprobs.values()) - 5.0   # letter not among the candidates: negligible mass
    logits = []
    for i in range(n_options):
        cands = [lp for tok, lp in top_logprobs.items() if tok.strip() == LETTERS[i]]
        logits.append(max(cands) if cands else floor)
    z = max(logits)
    exp = [math.exp(x - z) for x in logits]
    total = sum(exp)
    return [e / total for e in exp]


class JevClient:
    def __init__(self, cfg: JevConfig):
        self.cfg = cfg
        self.session = requests.Session()

    def top_logprobs(self, prompt: str) -> dict[str, float]:
        # Chat endpoint: the model ships a pass-through chat template and both llama-server and
        # LM Studio return candidate log-probs here.
        resp = self.session.post(
            self.cfg.base_url.rstrip("/") + "/chat/completions",
            json={"model": self.cfg.model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1,
                  "temperature": 0, "logprobs": True, "top_logprobs": 20},
            headers={"Authorization": f"Bearer {self.cfg.api_key}"}, timeout=self.cfg.timeout)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
        return {t["token"]: t["logprob"] for t in content}


class InProcessJev:
    """Loads the GGUF with llama-cpp-python inside this process: no server, nothing over the network.

    A decision only needs the logits of the last prompt token, so the prompt is evaluated
    once with logits for that position alone. This is about 2x faster than asking an HTTP
    server for logprobs (llama-cpp-python's server keeps logits for every prompt token).
    """

    def __init__(self, cfg: JevConfig):
        import os
        import threading

        from llama_cpp import Llama
        if not os.path.exists(cfg.model_path):
            raise FileNotFoundError(f"{cfg.model_path} not found - run `scripts/serve_local.sh jev` once to "
                                    "download it, or set [jev] backend = \"server\"")
        self.llm = Llama(cfg.model_path, n_ctx=cfg.n_ctx, n_threads=cfg.n_threads or None,
                         n_gpu_layers=cfg.n_gpu_layers, logits_all=False, verbose=False)
        self.lock = threading.Lock()

    def top_logprobs(self, prompt: str, k: int = 20) -> dict[str, float]:
        import numpy as np
        # The model ships a pass-through chat template and no BOS: the prompt is the model input.
        tokens = self.llm.tokenize(prompt.encode(), add_bos=False, special=True)
        with self.lock:
            self.llm.reset()
            self.llm.eval(tokens)
            logits = np.ctypeslib.as_array(self.llm._ctx.get_logits(), shape=(self.llm.n_vocab(),)).copy()
        m = logits.max()
        logprobs = logits - (m + np.log(np.exp(logits - m).sum()))
        top = np.argpartition(-logprobs, k)[:k]
        return {self.llm.detokenize([int(i)]).decode("utf-8", errors="ignore"): float(logprobs[i]) for i in top}


class JevStrategy(SnapshotModelStrategy):
    def __init__(self, cfg: JevConfig, max_leverage: int = 10, decision_hours: int = 4):
        super().__init__()
        self.cfg = cfg
        self.concurrency = cfg.concurrency
        self.max_leverage = max_leverage
        self.decision_hours = decision_hours
        self.questions = QUESTION_SETS[cfg.question_set]
        self.client = InProcessJev(cfg) if cfg.backend == "local" else JevClient(cfg)
        self.cache = DecisionCache(cfg.cache_path)
        self.name = f"jev[{cfg.model}|{cfg.question_set}]"

    def ask(self, key: str, state: str, symbol: str, t: str) -> list[tuple[object, float]]:
        template, options = self.questions[key]
        prompt = build_prompt(state, template.format(tf=self.decision_hours), [o for o, _ in options])
        cache_key = hashlib.sha256(json.dumps(["jev", self.cfg.model, prompt]).encode()).hexdigest()
        raw = self.cache.get(cache_key)
        if raw is None:
            raw = json.dumps(self.client.top_logprobs(prompt))
            self.cache.put(cache_key, self.cfg.model, f"{self.cfg.question_set}:{key}", symbol, t, raw)
            self.stats["queried"] += 1
        else:
            self.stats["cached"] += 1
        probs = option_probabilities(json.loads(raw), len(options))
        return [(value, p) for (_, value), p in zip(options, probs)]

    def decide_one(self, symbol: str, features: dict) -> Decision:
        state, t = render_prompt(symbol, features), str(features["time"])
        direction = self.ask("direction", state, symbol, t)
        action, conf = max(direction, key=lambda x: x[1])
        dist = " ".join(f"P({a})={p:.2f}" for a, p in direction)
        if action == FLAT:
            return Decision(action, conf, reason=dist)
        if not self.cfg.ask_risk:
            # One question per decision (fast on CPU): leverage scales with the calibrated
            # probability - 50% -> 1x, 100% -> max_leverage. SL/TP come from the risk layer (ATR).
            lev = round(1 + max(0.0, conf - 0.5) * 2 * (self.max_leverage - 1))
            return Decision(action, conf, leverage=max(1, min(lev, self.max_leverage)), reason=dist)

        def argmax(key):
            return max(self.ask(key, state, symbol, t), key=lambda x: x[1])[0]

        lev = min(int(argmax("leverage")), self.max_leverage)
        sl_pct = float(argmax("stop")) * features["atr_pct"]
        tp_pct = float(argmax("target")) * sl_pct
        return Decision(action, conf, leverage=lev, sl_pct=sl_pct, tp_pct=tp_pct, reason=dist)
