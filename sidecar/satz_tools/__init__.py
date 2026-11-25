"""Satz declarative tool registry & domain modules."""
from __future__ import annotations

from satz_tools.registry import REGISTRY, ToolRegistry, ToolSpec, satz_tool

# Register all built-in Settings domain tools on import.
from satz_tools import (  # noqa: F401
    news_settings,
    settings_i18n,
    settings_mail,
    settings_models,
    settings_oauth,
    settings_profiles,
    settings_providers,
    settings_status,
)

__all__ = ["REGISTRY", "ToolRegistry", "ToolSpec", "satz_tool"]
