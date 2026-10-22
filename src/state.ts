import type {
  BookmarkItem,
  BrowserTab,
  Conversation,
  ConversationDetail,
  DigestEntry,
  KnowledgeSummary,
  LocalModelId,
  SidecarHealth,
} from "./types";

export const IS_MAC =
  typeof navigator !== "undefined" &&
  /Mac|iPod|iPhone|iPad/.test(navigator.platform);

export const MOD_LABEL = IS_MAC ? "cmd" : "ctrl";

export interface AppState {
  conversations: Conversation[];
  bookmarks: BookmarkItem[];
  activeDetail: ConversationDetail | null;
  activeTabId: string; // "chat" or tab.id
  compareTabIds: string[];
  compareMode: boolean;
  agentRailOpen: boolean;
  showArchived: boolean;
  showKnowledgeView: boolean;
  railFilter: string;
  openMenuConvId: string | null;
  renamingConvId: string | null;
  selectedModel: LocalModelId;
  webSearchEnabled: boolean;
  isStreaming: boolean;
  streamingText: string;
  sidecar: SidecarHealth;
  digestItems: DigestEntry[];
  knowledge: KnowledgeSummary;
}

export const state: AppState = {
  conversations: [],
  bookmarks: [],
  activeDetail: null,
  activeTabId: "chat",
  compareTabIds: [],
  compareMode: false,
  agentRailOpen: true,
  showArchived: false,
  showKnowledgeView: false,
  railFilter: "",
  openMenuConvId: null,
  renamingConvId: null,
  selectedModel: "gemma-4-e4b",
  webSearchEnabled: false,
  isStreaming: false,
  streamingText: "",
  sidecar: {
    online: false,
    models: [
      { id: "gemma-4-e4b", state: "not_loaded" },
      { id: "planck3 (web)", state: "not_loaded" },
      { id: "hertz (reader)", state: "not_loaded" },
      { id: "planck (reader)", state: "not_loaded" },
    ],
    ingest_queue_len: 0,
    pause_learning: false,
  },
  digestItems: [],
  knowledge: {
    pause_learning: false,
    queue_len: 0,
    top_domains: [],
    top_topics: [],
    passages: [],
  },
};

export function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function extractDomain(rawUrl: string): string {
  try {
    const u = new URL(normalizeUrl(rawUrl));
    return u.hostname.replace(/^www\./, "");
  } catch {
    return rawUrl;
  }
}

export function isLikelyUrlToken(token: string): boolean {
  const t = token.trim();
  if (!t || t.includes(" ") || t.startsWith("?")) return false;
  if (
    t.startsWith("http://") ||
    t.startsWith("https://") ||
    t.startsWith("about:")
  ) {
    return true;
  }
  if (/^(localhost|127\.0\.0\.1)(:\d+)?(\/.*)?$/i.test(t)) {
    return true;
  }
  if (/^[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+(:\d+)?(\/.*)?$/.test(t)) {
    return true;
  }
  return false;
}

export function normalizeUrl(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return "about:blank";
  if (
    trimmed.startsWith("http://") ||
    trimmed.startsWith("https://") ||
    trimmed.startsWith("about:")
  ) {
    return trimmed;
  }
  if (/^(localhost|127\.0\.0\.1)(:\d+)?(\/.*)?$/i.test(trimmed)) {
    return `http://${trimmed}`;
  }
  if (isLikelyUrlToken(trimmed)) {
    return `https://${trimmed}`;
  }
  return `https://duckduckgo.com/?q=${encodeURIComponent(trimmed)}`;
}

export interface ParsedStartInput {
  kind: "url_only" | "text_only" | "url_and_text";
  url: string | null;
  question: string | null;
}

export function classifyStartInput(raw: string): ParsedStartInput {
  const trimmed = raw.trim();
  if (!trimmed) {
    return { kind: "text_only", url: null, question: "" };
  }
  const parts = trimmed.split(/\s+/);
  if (parts.length === 1 && isLikelyUrlToken(parts[0])) {
    return {
      kind: "url_only",
      url: normalizeUrl(parts[0]),
      question: null,
    };
  }
  if (parts.length > 1 && isLikelyUrlToken(parts[0])) {
    return {
      kind: "url_and_text",
      url: normalizeUrl(parts[0]),
      question: parts.slice(1).join(" ").trim(),
    };
  }
  return {
    kind: "text_only",
    url: null,
    question: trimmed,
  };
}

export function formatRelativeTime(isoOrEpoch: string): string {
  if (!isoOrEpoch) return "now";
  const num = Number(isoOrEpoch);
  const ms = !Number.isNaN(num)
    ? num < 1e12
      ? num * 1000
      : num
    : Date.parse(isoOrEpoch);
  if (Number.isNaN(ms)) return isoOrEpoch.slice(0, 10);
  const diffSec = Math.max(0, Math.floor((Date.now() - ms) / 1000));
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDays = Math.floor(diffHr / 24);
  return `${diffDays}d ago`;
}

export interface ActiveTabSource {
  index: number;
  tab: BrowserTab;
  sourceId: string;
  domain: string;
  title: string;
  url: string;
}

export function getActiveTabSources(
  detail: ConversationDetail | null = state.activeDetail
): ActiveTabSource[] {
  if (!detail) return [];
  const openTabs = detail.tabs.filter((t) => t.is_open);
  return openTabs.map((tab, idx) => {
    const matchedSource =
      detail.sources.find((s) => s.tab_id === tab.id && s.in_context) ??
      detail.sources.find((s) => s.tab_id === tab.id && s.url === tab.url) ??
      detail.sources.find((s) => s.tab_id === tab.id);
    const domain = matchedSource?.domain || extractDomain(tab.url);
    const title = tab.title || matchedSource?.title || domain;
    return {
      index: idx + 1,
      tab,
      sourceId: matchedSource?.id ?? tab.id,
      domain,
      title,
      url: tab.url,
    };
  });
}
