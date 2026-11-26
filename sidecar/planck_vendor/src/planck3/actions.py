"""
Closed action vocabulary + typed decisions.

Page text can only ever become a *candidate* the policy scores; it can never
become an action or an action argument. That is the injection defence: every
Decision is (action from ACTIONS, index into a harness-built candidate list, p).
"""

from dataclasses import dataclass, field

ACTIONS = ("LOOKUP", "SEARCH", "OPEN", "FOLLOW", "EXTRACT", "VERIFY", "ANSWER", "ABSTAIN")

# Actions that select one of the current candidates (need k).
POINTER_ACTIONS = frozenset({"OPEN", "FOLLOW", "EXTRACT", "ANSWER"})

# Which actions are legal in each harness phase, plus which candidate list a
# pointer action indexes into. The harness masks everything else.
PHASES = {
    "start":     {"allowed": ("LOOKUP", "SEARCH"),                          "pointer": {}},
    "store_hit": {"allowed": ("ANSWER", "SEARCH"),                          "pointer": {"ANSWER": "store"}},
    "results":   {"allowed": ("OPEN", "ABSTAIN"),                           "pointer": {"OPEN": "results"}},
    # snippet-first: candidate values read straight off the result snippets (0 fetches)
    "results_snip": {"allowed": ("EXTRACT", "OPEN", "ABSTAIN"), "pointer": {"EXTRACT": "spans", "OPEN": "results"}},
    "page":      {"allowed": ("EXTRACT", "OPEN", "ABSTAIN"),                "pointer": {"EXTRACT": "spans", "OPEN": "results"}},
    "extracted": {"allowed": ("ANSWER", "VERIFY", "OPEN", "ABSTAIN"),       "pointer": {"OPEN": "results"}},
    "verified":  {"allowed": ("ANSWER", "OPEN", "ABSTAIN"),                 "pointer": {"OPEN": "results"}},
}


@dataclass
class Decision:
    action: str
    k: int | None = None
    p: float = 0.5
    raw: str = ""                 # teacher's raw output, for debugging only
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"action": self.action, "k": self.k, "p": round(float(self.p), 4)}


class InvalidDecision(ValueError):
    pass


def validate(decision: Decision, phase: str, n_candidates: dict[str, int]) -> Decision:
    """Raise InvalidDecision unless the decision is legal in this phase."""
    spec = PHASES[phase]
    if decision.action not in spec["allowed"]:
        raise InvalidDecision(f"{decision.action} not allowed in phase {phase} {spec['allowed']}")
    list_name = spec["pointer"].get(decision.action)
    if list_name is not None:
        n = n_candidates.get(list_name, 0)
        if decision.k is None or not (0 <= decision.k < n):
            raise InvalidDecision(f"{decision.action} k={decision.k} out of range for {list_name} (n={n})")
    decision.p = min(1.0, max(0.0, float(decision.p)))
    return decision


def fallback(phase: str) -> Decision:
    """What the harness does when a policy emits garbage: the safe exit."""
    if phase == "start":
        return Decision("SEARCH", p=0.0, meta={"fallback": True})
    return Decision("ABSTAIN", p=0.0, meta={"fallback": True})
