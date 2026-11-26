"""
Policies: map an observation to one typed Decision.

    heuristic  lexical rules, no model. The no-learning baseline every trained
               policy must beat, and what the offline smoke test runs.
    gemma      Gemma 4 E4B teacher (local GPU, $0). Same typed action space.
    bedrock    Claude Haiku teacher via AWS Bedrock (optional, stronger).

An observation (built by harness.py) is:
    {question, answer_type, phase, allowed, pointer, lists: {results, spans, store},
     held, verified, history, opened, store_size}
"""

import json
import math
import re

from .actions import ACTIONS, Decision
from .util import content_words, norm_text


def _overlap(a: str, b: str) -> float:
    qa = content_words(a)
    if not qa:
        return 0.0
    sb = set(norm_text(b).split())
    return sum(1 for w in qa if w in sb) / len(qa)


def _sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class Policy:
    name = "base"
    kind = "local"          # local (CPU rules / small model) | llm (priced per token)
    model_id = None
    calibrated = False      # is p a calibrated probability? (the answer card says which)
    confidence_kind = "rule-based score, not calibrated"

    def __init__(self):
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

    def decide(self, obs: dict) -> Decision:
        raise NotImplementedError


class HeuristicPolicy(Policy):
    name = "heuristic"

    def __init__(self, answer_threshold: float = 0.6):
        super().__init__()
        self.tau = answer_threshold

    @staticmethod
    def _conf(span) -> float:
        """Confidence from the lead over the runner-up, damped when the match itself is weak."""
        return _sig(10 * span.get("margin", 0.0)) * min(1.0, span["score"])

    def _best_unopened(self, obs):
        best, best_s = None, -1.0
        for i, r in enumerate(obs["lists"].get("results", [])):
            if i in obs["opened"]:
                continue
            s = _overlap(obs["question"], f"{r['title']} {r['snippet']}") + 0.5 * r.get("trust", 0.5)
            if s > best_s:
                best, best_s = i, s
        return best

    def decide(self, obs):
        phase = obs["phase"]
        if phase == "start":
            return Decision("LOOKUP" if obs["store_size"] else "SEARCH", p=0.5)
        if phase == "store_hit":
            top = obs["lists"]["store"][0]
            if top["match"] >= 0.9:
                return Decision("ANSWER", k=0, p=top["p"])
            return Decision("SEARCH", p=0.5)
        if phase == "results_snip":  # take a snippet value only when it clearly answers
            spans = obs["lists"].get("spans", [])
            # only from a page about the subject, or when 2+ domains agree; otherwise read a page
            if spans and spans[0]["score"] >= 0.4 and (spans[0].get("about", 0) >= 0.5 or len(spans[0].get("domains", [])) >= 2):
                return Decision("EXTRACT", k=0, p=self._conf(spans[0]))
            phase = "results"
        if phase == "results":
            k = self._best_unopened(obs)
            return Decision("OPEN", k=k, p=0.5) if k is not None else Decision("ABSTAIN", p=0.0)
        if phase == "page":
            spans = obs["lists"].get("spans", [])
            if spans and spans[0]["score"] >= 0.35:
                return Decision("EXTRACT", k=0, p=self._conf(spans[0]))
            k = self._best_unopened(obs)
            return Decision("OPEN", k=k, p=0.3) if k is not None else Decision("ABSTAIN", p=0.0)
        held_p = self._conf(obs["held"])
        if phase == "extracted":
            if held_p >= self.tau:
                return Decision("ANSWER", p=held_p)
            if self._best_unopened(obs) is not None:
                return Decision("VERIFY", p=held_p)
            return Decision("ANSWER", p=held_p) if held_p >= 0.4 else Decision("ABSTAIN", p=held_p)
        if phase == "verified":
            if obs["verified"]:
                return Decision("ANSWER", p=min(0.95, held_p + 0.25))
            return Decision("ANSWER", p=held_p * 0.8) if held_p >= 0.5 else Decision("ABSTAIN", p=held_p)
        return Decision("ABSTAIN", p=0.0)


# ── LLM teachers ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are the decision module of a small web research agent.
You NEVER write answers yourself. At each step you pick exactly one action from
the ALLOWED list and, for pointer actions, the index k of one listed candidate.

Actions:
  LOOKUP   check the local knowledge store for a fresh stored answer
  SEARCH   run a web search for the question
  OPEN k   open search result k (read the full page)
  EXTRACT k  take span candidate k as the answer: values from the search snippets
           (before any page is opened) or from the open page
  VERIFY   check the held value against another source before answering
  ANSWER   answer with the held value (or ANSWER k = stored fact k)
  ABSTAIN  give up: nothing trustworthy was found (better than a wrong answer)

Snippets first: if a snippet value clearly answers the question (ideally the same
value from several domains), EXTRACT it; OPEN a page only when the snippets do not.
Pick the candidate that actually answers the question, not one that repeats its
words (the subject itself, an alias, a later product version, an unrelated year).
p is your probability that the FINAL answer is correct; be calibrated. An ANSWER
with low p is turned into "couldn't verify", which is better than a wrong answer.

Reply with ONLY one JSON object, no prose:
{"action": "<ACTION>", "k": <integer or null>, "p": <number 0..1>}"""


def render_observation(obs: dict) -> str:
    lines = [f"QUESTION: {obs['question']}",
             f"EXPECTED ANSWER TYPE: {obs['answer_type']}",
             f"ALLOWED: {', '.join(obs['allowed'])}"]
    for act, lst in obs["pointer"].items():
        lines.append(f"  ({act} takes k from the {lst.upper()} list)")
    if obs["history"]:
        lines.append("HISTORY: " + " -> ".join(obs["history"][-8:]))
    lists = obs["lists"]
    if lists.get("store") and "store" in obs["pointer"].values():
        lines.append("STORE (fresh stored facts):")
        for i, s in enumerate(lists["store"]):
            lines.append(f"  [{i}] {s['value']} | from {s['domain']} | match {s['match']} | p {s['p']:.2f}")
    if lists.get("results") and "results" in obs["pointer"].values():
        lines.append("RESULTS:")
        for i, r in enumerate(lists["results"]):
            tag = " (already opened)" if i in obs["opened"] else ""
            lines.append(f"  [{i}] {r['title'][:90]} | {r['domain']} (trust {r.get('trust', 0.5):.2f}){tag}"
                         f" | {r['snippet'][:160]}")
    if lists.get("spans") and "spans" in obs["pointer"].values():
        lines.append(f"SPANS (candidate values from {obs.get('spans_source', 'the open page')}):")
        for i, s in enumerate(lists["spans"]):
            doms = s.get("domains") or []
            src = f" | {len(doms)} domains: {', '.join(doms[:3])}" if len(doms) > 1 else (f" | {doms[0]}" if doms else "")
            if "about" in s:
                src += " | from a page about the subject" if s["about"] >= 0.5 else " | from a page about something else"
            lines.append(f"  [{i}] {s['value'][:80]} | \"{s['context'][:200]}\"{src}")
    if obs.get("held"):
        h = obs["held"]
        lines.append(f"HELD VALUE: {h['value']} (from {h['domain']}): \"{h['context'][:200]}\"")
    if obs.get("verified") is not None:
        lines.append(f"VERIFICATION: {'another source AGREES' if obs['verified'] else 'no second source agreed'}")
    return "\n".join(lines)


def parse_decision(text: str) -> Decision:
    m = re.search(r"\{.*?\}", text, re.S)
    if not m:
        return Decision("INVALID", raw=text)
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return Decision("INVALID", raw=text)
    action = str(d.get("action", "")).strip().upper().split()[0] if d.get("action") else ""
    k = d.get("k")
    try:
        k = int(k) if k is not None and str(k).strip().lower() not in ("null", "none", "") else None
    except (TypeError, ValueError):
        k = None
    try:
        p = float(d.get("p", 0.5))
    except (TypeError, ValueError):
        p = 0.5
    if action not in ACTIONS:
        action = "INVALID"
    return Decision(action, k=k, p=p, raw=text)


CLOSED_BOOK_SYSTEM = ("You are a helpful assistant. Answer the user's question from your own knowledge. "
                      "Reply with only the answer (a value, date or name), no explanation.")


class LLMPolicy(Policy):
    kind = "llm"
    confidence_kind = "the model's own estimate, not calibrated"

    def _complete(self, system: str, user: str) -> str:
        raise NotImplementedError

    def answer_closed_book(self, question: str, history: list[tuple[str, str]] | None = None) -> str:
        """The base-chat comparator: no tools, no retrieval, just the model's weights."""
        convo = "".join(f"User: {q}\nAssistant: {a}\n" for q, a in (history or []))
        return self._complete(CLOSED_BOOK_SYSTEM, f"{convo}User: {question}" if convo else question).strip()

    def decide(self, obs):
        return parse_decision(self._complete(SYSTEM_PROMPT, render_observation(obs)))


class GemmaPolicy(LLMPolicy):
    name = "gemma"

    def __init__(self, model_path: str = "models/gemma-4-e4b-it", max_new: int = 48):
        super().__init__()
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        self.max_new = max_new
        print(f"[planck3] loading Gemma teacher {model_path} ...")
        self.tok = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path, dtype=torch.bfloat16,
            device_map="auto" if torch.cuda.is_available() else None)
        self.model.eval()

    def _complete(self, system, user):
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        inputs = self.tok.apply_chat_template(msgs, add_generation_prompt=True,
                                              return_tensors="pt", return_dict=True).to(self.model.device)
        n = inputs["input_ids"].shape[1]
        with self.torch.no_grad():
            out = self.model.generate(**inputs, max_new_tokens=self.max_new, do_sample=False)
        self.usage["calls"] += 1
        self.usage["input_tokens"] += int(n)
        self.usage["output_tokens"] += int(out.shape[1] - n)
        return self.tok.decode(out[0][n:], skip_special_tokens=True)


class BedrockPolicy(LLMPolicy):
    name = "bedrock"

    def __init__(self, model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0",
                 region: str = "us-east-1", profile: str | None = None):
        super().__init__()
        import os
        import boto3
        session = boto3.Session(profile_name=profile or os.environ.get("AWS_PROFILE") or None)
        self.client = session.client("bedrock-runtime", region_name=region)
        self.model_id = model_id

    def _complete(self, system, user):
        body = json.dumps({"anthropic_version": "bedrock-2023-05-31", "max_tokens": 80,
                           "temperature": 0, "system": system,
                           "messages": [{"role": "user", "content": user}]})
        r = self.client.invoke_model(modelId=self.model_id, body=body,
                                     contentType="application/json", accept="application/json")
        out = json.loads(r["body"].read())
        u = out.get("usage", {})
        self.usage["calls"] += 1
        self.usage["input_tokens"] += int(u.get("input_tokens", 0))
        self.usage["output_tokens"] += int(u.get("output_tokens", 0))
        return out["content"][0]["text"]


def make_policy(name: str, **kw) -> Policy:
    if name == "heuristic":
        return HeuristicPolicy()
    if name == "gemma":
        return GemmaPolicy(kw.get("gemma_path") or "models/gemma-4-e4b-it")
    if name == "bedrock":
        return BedrockPolicy(**{k: v for k, v in kw.items() if k in ("model_id", "region", "profile") and v})
    raise ValueError(f"unknown policy {name}")
