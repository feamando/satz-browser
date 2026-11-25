"""Declarative tool registry shared across Satz local/cloud LLM harnesses and future MCP bridges."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    domain: str
    description: str
    parameters: dict[str, Any]
    mode: str  # "read" | "staged_write" | "confirm_gate" | "ui_prompt"
    handler: Callable[..., dict[str, Any]]
    redacted_args: tuple[str, ...] = field(default_factory=tuple)
    mcp_safe: bool = False


class ToolRegistry:
    """Thread-safe declarative registry compiling LLM tool specs and dispatching tool invocations."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolSpec:
        self._tools[spec.name] = spec
        return spec

    def has(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list_tools(
        self,
        *,
        domains: tuple[str, ...] | list[str] | None = None,
        mcp_safe_only: bool = False,
    ) -> list[ToolSpec]:
        domain_set = set(domains) if domains is not None else None
        out: list[ToolSpec] = []
        for spec in self._tools.values():
            if domain_set is not None and spec.domain not in domain_set:
                continue
            if mcp_safe_only and not spec.mcp_safe:
                continue
            out.append(spec)
        return out

    def active_specs(
        self,
        *,
        domains: tuple[str, ...] | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Returns normalized OpenAI/Gemini/Anthropic/Mistral/Gemma function schema dicts."""
        return [
            {
                "name": s.name,
                "description": s.description,
                "parameters": s.parameters,
            }
            for s in self.list_tools(domains=domains)
        ]

    def format_local_addendum(
        self,
        *,
        domains: tuple[str, ...] | list[str] | None = None,
    ) -> str:
        """Builds a compact ReAct addendum suited for 4B local models (e.g. gemma-4-e4b)."""
        lines: list[str] = []
        for s in self.list_tools(domains=domains):
            props = s.parameters.get("properties") or {}
            req = set(s.parameters.get("required") or [])
            arg_sig = ", ".join(f"{k}{'' if k in req else '?'}" for k in props.keys())
            first_sent = str(s.description or "").split(".")[0].strip()
            lines.append(f"- {s.name}({arg_sig}): {first_sent}.")
        return "\n".join(lines)

    def dispatch(
        self,
        name: str,
        args: dict[str, Any] | None,
        *,
        runtime: Any,
        session: Any = None,
    ) -> dict[str, Any]:
        spec = self._tools.get(name)
        if spec is None:
            return {"ok": False, "error": f"Unknown registry tool: {name}"}

        clean_args = dict(args) if isinstance(args, dict) else {}
        for rk in spec.redacted_args:
            if rk in clean_args and clean_args[rk]:
                clean_args.pop(rk, None)

        res = spec.handler(runtime, session, **clean_args)
        if not isinstance(res, dict):
            return {"ok": False, "error": f"Invalid tool return payload from {name}"}

        cards = res.get("ui_cards")
        if session is not None and isinstance(cards, list) and cards:
            ui_buf = getattr(session, "ui_cards", None)
            if isinstance(ui_buf, list):
                existing_ids = {str(c.get("id") or "") for c in ui_buf if isinstance(c, dict)}
                for c in cards:
                    if not isinstance(c, dict):
                        continue
                    cid = str(c.get("id") or "")
                    if cid and cid in existing_ids:
                        continue
                    if cid:
                        existing_ids.add(cid)
                    ui_buf.append(c)

        if session is not None and res.get("tab_list_updated"):
            try:
                session.tab_list_updated = True
            except Exception:
                pass

        # Strip ui_cards/side_effects from the text payload sent back into model context to save tokens
        model_payload = dict(res.get("model_payload") or res)
        model_payload.pop("ui_cards", None)
        model_payload.pop("tab_list_updated", None)
        return model_payload


REGISTRY = ToolRegistry()


def satz_tool(
    *,
    name: str,
    domain: str,
    description: str,
    parameters: dict[str, Any],
    mode: str = "read",
    redacted_args: tuple[str, ...] = (),
    mcp_safe: bool = False,
) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    """Decorator registering a Satz tool on the global declarative `REGISTRY`."""

    def _decorator(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        REGISTRY.register(
            ToolSpec(
                name=name,
                domain=domain,
                description=description,
                parameters=parameters,
                mode=mode,
                handler=fn,
                redacted_args=redacted_args,
                mcp_safe=mcp_safe,
            )
        )
        return fn

    return _decorator
