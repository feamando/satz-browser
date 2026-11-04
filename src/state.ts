import type {
  BookmarkItem,
  BrainProposalItem,
  BrowserTab,
  Conversation,
  ConversationDetail,
  DigestEntry,
  DoctorRoleEntry,
  FindingItem,
  KnowledgeSummary,
  LocalModelId,
  MailAccountItem,
  MailLaneCounts,
  MailPreset,
  SidecarHealth,
  SourceStatEntry,
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
  mailContextEnabled: boolean;
  isStreaming: boolean;
  streamingText: string;
  streamingStatus: string;
  streamingPhase: string;
  streamingStartedAt: number;
  streamingSteps: string[];
  lastUserPrompt: string;
  sidecar: SidecarHealth;
  doctorRoles: DoctorRoleEntry[];
  digestItems: DigestEntry[];
  knowledge: KnowledgeSummary;
  bookmarkTooltipNotice: string;
  profileStatusMessage: string;
  tabHasPasswordField: Record<string, boolean>;
  tabCanFillLogin: Record<string, boolean>;
  messageProposals: Record<string, BrainProposalItem[]>;
  messageFindings: Record<string, FindingItem[]>;
  revealedPasswords: Record<string, string>;
  sourceStats: Record<string, SourceStatEntry>;
  showErrorLog: boolean;
  mailAccounts: MailAccountItem[];
  mailPresets: MailPreset[];
  mailCounts: MailLaneCounts;
  mailInboxRows: Array<Record<string, unknown>>;
  mailActiveLane: "inbox" | "pings" | "orders" | "promos";
  mailLaneRows: Array<Record<string, unknown>>;
  mailLaneGroups: Array<Record<string, unknown>>;
  mailSelectedRowIdx: number;
  mailStatusMessage: string;
  mailSearchQuery: string;
  mailSearchRows: Array<Record<string, unknown>> | null;
  mailMessageDetails: Record<string, Record<string, unknown>>;
  mailTriageOverview: string;
  mailTriageSources: Array<{
    id: string;
    url: string;
    title: string;
    domain: string;
    is_open_tab: boolean;
  }>;
  siteTabPromoCodes: Record<string, Array<Record<string, unknown>>>;
  openCodesPopoverTabId: string | null;
  mailEvalOpen: boolean;
  mailEvalItems: Array<Record<string, unknown>>;
  mailEvalIdx: number;
  mailEvalReport: Record<string, unknown> | null;
  mailComposeDrafts: Record<
    string,
    {
      account_id: string;
      to: string;
      cc: string;
      bcc: string;
      subject: string;
      body: string;
      in_reply_to: string;
      references: string;
      reply_to_message_id: string;
      confirm_outbox_id?: string;
      confirm_token?: string;
      confirm_line?: string;
      queued_outbox_id?: string;
      undo_until?: number;
      status_msg?: string;
    }
  >;
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
  mailContextEnabled: false,
  isStreaming: false,
  streamingText: "",
  streamingStatus: "",
  streamingPhase: "",
  streamingStartedAt: 0,
  streamingSteps: [],
  lastUserPrompt: "",
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
    errors: [],
  },
  doctorRoles: [],
  digestItems: [],
  knowledge: {
    pause_learning: false,
    queue_len: 0,
    top_domains: [],
    top_topics: [],
    passages: [],
  },
  bookmarkTooltipNotice: "",
  profileStatusMessage: "",
  tabHasPasswordField: {},
  tabCanFillLogin: {},
  messageProposals: {},
  messageFindings: {},
  revealedPasswords: {},
  sourceStats: {},
  showErrorLog: false,
  mailAccounts: [],
  mailPresets: [],
  mailCounts: { inbox_unread: 0, pings: 0, orders: 0, promos: 0 },
  mailInboxRows: [],
  mailActiveLane: "inbox",
  mailLaneRows: [],
  mailLaneGroups: [],
  mailSelectedRowIdx: 0,
  mailStatusMessage: "",
  mailSearchQuery: "",
  mailSearchRows: null,
  mailMessageDetails: {},
  mailTriageOverview: "",
  mailTriageSources: [],
  siteTabPromoCodes: {},
  openCodesPopoverTabId: null,
  mailEvalOpen: false,
  mailEvalItems: [],
  mailEvalIdx: 0,
  mailEvalReport: null,
  mailComposeDrafts: {},
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

export interface LiveNavigationTarget {
  targetUrl: string;
  existingTabId: string | null;
  label: string;
}

function getOriginFromUrl(rawUrl: string): string {
  try {
    const u = new URL(normalizeUrl(rawUrl));
    return u.origin;
  } catch {
    return "";
  }
}

function buildSiteSearchUrl(
  siteKey: string,
  query: string,
  matchedOrigin: string
): string {
  const q = encodeURIComponent(query.trim());
  const key = siteKey.toLowerCase().replace(/^www\./, "");
  if (key.includes("zalando")) {
    const base = matchedOrigin.includes("zalando")
      ? matchedOrigin
      : "https://en.zalando.de";
    return `${base}/catalogue/?q=${q}`;
  }
  if (key.includes("amazon")) {
    const base = matchedOrigin.includes("amazon")
      ? matchedOrigin
      : "https://www.amazon.com";
    return `${base}/s?k=${q}`;
  }
  if (key.includes("ebay")) {
    const base = matchedOrigin.includes("ebay")
      ? matchedOrigin
      : "https://www.ebay.com";
    return `${base}/sch/i.html?_nkw=${q}`;
  }
  if (key.includes("github")) {
    return `https://github.com/search?q=${q}`;
  }
  if (key.includes("youtube")) {
    return `https://www.youtube.com/results?search_query=${q}`;
  }
  if (key.includes("wikipedia")) {
    return `https://en.wikipedia.org/w/index.php?search=${q}`;
  }
  if (key.includes("reddit")) {
    return `https://www.reddit.com/search/?q=${q}`;
  }
  if (key.includes("asos")) {
    const base = matchedOrigin.includes("asos")
      ? matchedOrigin
      : "https://www.asos.com";
    return `${base}/search/?q=${q}`;
  }
  if (key.includes("otto")) {
    return `https://www.otto.de/suche/${q}/`;
  }
  if (key.includes("ikea")) {
    const base = matchedOrigin.includes("ikea")
      ? matchedOrigin
      : "https://www.ikea.com/de/de";
    return `${base}/search/?q=${q}`;
  }
  if (key.includes("mediamarkt")) {
    return `https://www.mediamarkt.de/de/search.html?query=${q}`;
  }
  if (key.includes("booking")) {
    return `https://www.booking.com/searchresults.html?ss=${q}`;
  }
  if (key.includes("hackernews") || key.includes("ycombinator")) {
    return `https://hn.algolia.com/?q=${q}`;
  }
  if (key.includes("google")) {
    return `https://www.google.com/search?q=${q}`;
  }
  if (key.includes("bing")) {
    return `https://www.bing.com/search?q=${q}`;
  }
  if (key.includes("duckduckgo")) {
    return `https://duckduckgo.com/?q=${q}`;
  }
  if (matchedOrigin) {
    return `${matchedOrigin}/search?q=${q}`;
  }
  if (key.includes(".")) {
    return `https://${key}/search?q=${q}`;
  }
  return `https://duckduckgo.com/?q=${encodeURIComponent(`${siteKey} ${query}`.trim())}`;
}

export function resolveLiveNavigationTarget(
  prompt: string,
  openTabs: BrowserTab[],
  activeTabId: string,
  webSearchEnabled = false
): LiveNavigationTarget | null {
  const trimmed = prompt.trim();
  if (!trimmed) return null;

  // Never navigate away when asking about mail, inbox, brain, or summarizing the current page as-is
  if (
    /\b(my\s+(?:latest\s+)?(?:email|emails|inbox|mail|account|calendar|messages|address|order|package)|(?:summarize|summary\s+of|explain|translate)\s+(?:this|the)\s+(?:page|tab|article|email|site)|what\s+do\s+i\s+need\s+to\s+deal\s+with|draft\s+a\s+reply|store\s+(?:this|the)|save\s+(?:this|the)|in\s+my\s+brain)\b/i.test(
      trimmed
    )
  ) {
    return null;
  }

  const siteTabs = openTabs.filter(
    (t) =>
      t.is_open &&
      t.kind !== "mail" &&
      t.kind !== "compose" &&
      !t.url.startsWith("satzmail://") &&
      !t.url.startsWith("about:")
  );
  const activeSiteTab =
    siteTabs.find((t) => t.id === activeTabId) ?? siteTabs[0] ?? null;

  // 1. Pattern: "find/search/look for/show me <query> on/at/in/from <site>"
  const onSiteMatch = trimmed.match(
    /^(?:can\s+you\s+|please\s+)?(?:find(?:\s+me)?(?:\s+some)?|search(?:\s+for)?|look\s+(?:up|for)|show(?:\s+me)?(?:\s+some)?|get(?:\s+me)?(?:\s+some)?|browse(?:\s+for)?)\s+(.+?)\s+(?:on|at|in|from)\s+([a-zA-Z0-9.-]+)\s*[?.!]*$/i
  );
  if (onSiteMatch) {
    const rawQuery = onSiteMatch[1]
      .replace(/^(?:some|any|a\s+few|good|best|new)\s+/i, "")
      .trim();
    const rawSite = onSiteMatch[2].trim().toLowerCase();
    const matchingTab =
      siteTabs.find((t) => extractDomain(t.url).toLowerCase().includes(rawSite)) ??
      activeSiteTab;
    const matchedOrigin = matchingTab ? getOriginFromUrl(matchingTab.url) : "";
    const targetUrl = buildSiteSearchUrl(rawSite, rawQuery || trimmed, matchedOrigin);
    return {
      targetUrl,
      existingTabId: matchingTab ? matchingTab.id : null,
      label: `${rawSite}: ${rawQuery}`,
    };
  }

  // 2. Pattern: "search <site> for <query>" or "go to <site> and find <query>"
  const siteFirstMatch = trimmed.match(
    /^(?:can\s+you\s+|please\s+)?(?:search|check|go\s+to|open|visit)\s+([a-zA-Z0-9.-]+)\s+(?:for|and\s+(?:find|search\s+for|look\s+for|show\s+me))\s+(.+?)\s*[?.!]*$/i
  );
  if (siteFirstMatch) {
    const rawSite = siteFirstMatch[1].trim().toLowerCase();
    const rawQuery = siteFirstMatch[2]
      .replace(/^(?:some|any|a\s+few)\s+/i, "")
      .trim();
    const matchingTab =
      siteTabs.find((t) => extractDomain(t.url).toLowerCase().includes(rawSite)) ??
      activeSiteTab;
    const matchedOrigin = matchingTab ? getOriginFromUrl(matchingTab.url) : "";
    const targetUrl = buildSiteSearchUrl(rawSite, rawQuery || trimmed, matchedOrigin);
    return {
      targetUrl,
      existingTabId: matchingTab ? matchingTab.id : null,
      label: `${rawSite}: ${rawQuery}`,
    };
  }

  // 3. Pattern: User has an open site tab (or mentions a known site) and asks "find me some hats", "search for winter jackets", "show me ..."
  const discoveryMatch = trimmed.match(
    /^(?:can\s+you\s+|please\s+)?(?:find(?:\s+me)?(?:\s+some)?|search(?:\s+for)?|look\s+(?:up|for)|show(?:\s+me)?(?:\s+some)?|browse(?:\s+for)?)\s+(.+?)\s*[?.!]*$/i
  );
  if (discoveryMatch) {
    let rawQuery = discoveryMatch[1]
      .replace(/^(?:some|any|a\s+few)\s+/i, "")
      .trim();

    // Check if a known brand/site is mentioned anywhere inside rawQuery
    const knownSites = [
      "zalando",
      "amazon",
      "ebay",
      "github",
      "youtube",
      "wikipedia",
      "reddit",
      "asos",
      "otto",
      "ikea",
      "mediamarkt",
      "booking",
    ];
    const mentionedSite = knownSites.find((ks) =>
      new RegExp(`\\b${ks}\\b`, "i").test(rawQuery)
    );
    if (mentionedSite) {
      rawQuery = rawQuery
        .replace(new RegExp(`\\b(?:on|at|in|from)?\\s*${mentionedSite}\\b`, "gi"), "")
        .trim();
      const matchingTab =
        siteTabs.find((t) =>
          extractDomain(t.url).toLowerCase().includes(mentionedSite)
        ) ?? activeSiteTab;
      const matchedOrigin = matchingTab ? getOriginFromUrl(matchingTab.url) : "";
      const targetUrl = buildSiteSearchUrl(
        mentionedSite,
        rawQuery || discoveryMatch[1],
        matchedOrigin
      );
      return {
        targetUrl,
        existingTabId: matchingTab ? matchingTab.id : null,
        label: `${mentionedSite}: ${rawQuery || discoveryMatch[1]}`,
      };
    }

    if (activeSiteTab) {
      const dom = extractDomain(activeSiteTab.url);
      const origin = getOriginFromUrl(activeSiteTab.url);
      const targetUrl = buildSiteSearchUrl(dom, rawQuery, origin);
      return {
        targetUrl,
        existingTabId: activeSiteTab.id,
        label: `${dom}: ${rawQuery}`,
      };
    }

    if (webSearchEnabled || siteTabs.length === 0) {
      const targetUrl = `https://duckduckgo.com/?q=${encodeURIComponent(rawQuery)}`;
      return {
        targetUrl,
        existingTabId: null,
        label: `search: ${rawQuery}`,
      };
    }
  }

  return null;
}
