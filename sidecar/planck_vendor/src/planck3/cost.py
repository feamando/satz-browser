"""
Cost per answer, the commercial half of the bet.

    llm    teacher tokens priced at an API chat model's rates (config llm_equivalent),
           i.e. what an LLM-chat-with-search product pays for the same decisions
    search per logical search call (a live system pays every one, cache or not)
    cpu    local policy decision time x an assumed vCPU-hour price

Shared tool work (fetch, extraction) is identical for every policy and excluded.
Our LLM comparator only sees compact candidate lists, so real LLM chat products
(which read whole pages) cost MORE than this: the ratio we report is conservative.
"""

import json
from pathlib import Path

from .util import REPO_ROOT

PRICES = REPO_ROOT / "config" / "planck3_prices.json"


def load_prices(path: str | Path = PRICES) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def task_cost(prices: dict, policy_kind: str, usage: dict, search_calls: int, backend: str,
              decision_ms: list[float]) -> dict:
    llm = cpu = 0.0
    if policy_kind == "llm":
        rate = prices["llm_per_mtok"][prices["llm_equivalent"]]
        llm = usage.get("input_tokens", 0) * rate["input"] / 1e6 + usage.get("output_tokens", 0) * rate["output"] / 1e6
    else:
        cpu = sum(decision_ms) / 3.6e6 * prices["cpu_per_hour"]
    search = search_calls * prices["search_per_call"].get(backend, 0.0)
    return {"llm_usd": llm, "search_usd": search, "cpu_usd": cpu, "total_usd": llm + search + cpu,
            "input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0)}


def summarize_cost(records: list[dict], prices: dict) -> dict:
    n = len(records)
    if not n:
        return {}
    tot = sum(r["cost"]["total_usd"] for r in records)
    n_ok = sum(1 for r in records if r["correct"])
    return {"usd_per_task": tot / n, "usd_per_correct": tot / n_ok if n_ok else None,
            "usd_per_1k_tasks": 1000 * tot / n,
            "llm_tokens_per_task": sum(r["cost"]["input_tokens"] + r["cost"]["output_tokens"] for r in records) / n,
            "priced_as": prices["llm_equivalent"], "prices_as_of": prices["as_of"]}
