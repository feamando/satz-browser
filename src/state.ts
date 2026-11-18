import type {
  AgentTaskCard,
  AnswerMeta,
  BookmarkItem,
  BrainCitationItem,
  BrainProposalItem,
  BrainSearchResponse,
  BrowserTab,
  ChatEmailCard,
  CommandBarActionId,
  CommandBarRoute,
  ConvStreamState,
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
  ModelManagementConfig,
  NewsCategoryEntry,
  NewsLane,
  NewsPerspectiveMatrix,
  NewsSourceEntry,
  NewsStoryCluster,
  NewsTopicItem,
  SidecarHealth,
  SourceStatEntry,
  WatchItem,
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
  showBrainView: boolean;
  commandBarOpen: boolean;
  commandBarInput: string;
  commandBarSelectedIdx: number;
  brainSearchQuery: string;
  brainSearchResults: BrainSearchResponse | null;
  highlightedBrainSlug: string | null;
  railFilter: string;
  openMenuConvId: string | null;
  renamingConvId: string | null;
  selectedModel: LocalModelId;
  userOverrodeModelInSession: boolean;
  webSearchEnabled: boolean;
  mailContextEnabled: boolean;
  streamsByConv: Record<string, ConvStreamState>;
  lastPromptByConv: Record<string, string>;
  sidecar: SidecarHealth;
  doctorRoles: DoctorRoleEntry[];
  digestItems: DigestEntry[];
  digestRevision: string | null;
  digestUpdatedAt: number;
  digestRefreshing: boolean;
  knowledge: KnowledgeSummary;
  bookmarkTooltipNotice: string;
  profileStatusMessage: string;
  tabHasPasswordField: Record<string, boolean>;
  tabCanFillLogin: Record<string, boolean>;
  messageProposals: Record<string, BrainProposalItem[]>;
  messageFindings: Record<string, FindingItem[]>;
  messageBrainSources: Record<string, BrainCitationItem[]>;
  messageCitedSources: Record<
    string,
    Array<{ url: string; title: string; domain?: string }>
  >;
  chatLastRenderedConvId: string | null;
  chatPinToBottom: boolean;
  expandedDebugMessages: Record<string, boolean>;
  revealedPasswords: Record<string, string>;
  sourceStats: Record<string, SourceStatEntry>;
  showErrorLog: boolean;
  mailAccounts: MailAccountItem[];
  mailPresets: MailPreset[];
  mailActiveAccountId: string | null;
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
  mailMessageHtml: Record<string, { html: string; csp: string }>;
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
  mailClassifierInfo: {
    model_version: string;
    training_labels: number;
    target_labels: number;
    corrections_count: number;
    status_text: string;
  };
  mailOnboardingCandidates: Array<Record<string, unknown>>;
  mailOnboardingOpen: boolean;
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
      new_recipients?: string[];
      queued_outbox_id?: string;
      undo_until?: number;
      status_msg?: string;
    }
  >;
  conversationTasks: Record<string, AgentTaskCard[]>;
  watches: WatchItem[];
  watchBadgeConvIds: string[];
  watchStatusNotice: string;
  messageEmailCards: Record<string, ChatEmailCard[]>;
  expandedChatEmails: Record<string, boolean>;
  previewedAttachments: Record<
    string,
    { filename: string; mime: string; data_url: string; size: number }
  >;
  settingsAccordionOpen: Record<string, boolean>;
  modelConfig: ModelManagementConfig | null;
  modelConfigStatusMsg: string;
  profilePromptOpen: boolean;
  profilePromptDismissed: boolean;
  newsActiveLane: NewsLane;
  newsStories: NewsStoryCluster[];
  newsForYouStories: NewsStoryCluster[];
  newsPerspectivesStories: NewsStoryCluster[];
  newsSelectedClusterId: string | null;
  newsPerspectiveMatrix: NewsPerspectiveMatrix | null;
  newsSources: NewsSourceEntry[];
  newsCategories: NewsCategoryEntry[];
  newsSourcesAsOf: string;
  newsSourcesFilterQuery: string;
  newsSourcesFilterCategory: string;
  newsSourcesFilterBand: string;
  newsSourcesConflictedOnly: boolean;
  newsSourcesRssOnly: boolean;
  newsTopics: NewsTopicItem[];
  newsExploreMode: boolean;
  newsLoading: boolean;
  newsStatusMessage: string;
  newsReaderArticleId: string | null;
  newsReaderShowOriginal: boolean;
  messageAnswerMeta: Record<string, AnswerMeta>;
  expandedExplainMessages: Record<string, boolean>;
  expandedInDepthMessages: Record<string, boolean>;
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
  showBrainView: false,
  commandBarOpen: false,
  commandBarInput: "",
  commandBarSelectedIdx: 0,
  brainSearchQuery: "",
  brainSearchResults: null,
  highlightedBrainSlug: null,
  railFilter: "",
  openMenuConvId: null,
  renamingConvId: null,
  selectedModel: "gemma-4-e4b",
  userOverrodeModelInSession: false,
  webSearchEnabled: false,
  mailContextEnabled: false,
  streamsByConv: {},
  lastPromptByConv: {},
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
  digestRevision: null,
  digestUpdatedAt: 0,
  digestRefreshing: false,
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
  messageBrainSources: {},
  messageCitedSources: {},
  chatLastRenderedConvId: null,
  chatPinToBottom: true,
  expandedDebugMessages: {},
  revealedPasswords: {},
  sourceStats: {},
  showErrorLog: false,
  mailAccounts: [],
  mailPresets: [],
  mailActiveAccountId: null,
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
  mailMessageHtml: {},
  mailTriageOverview: "",
  mailTriageSources: [],
  siteTabPromoCodes: {},
  openCodesPopoverTabId: null,
  mailEvalOpen: false,
  mailEvalItems: [],
  mailEvalIdx: 0,
  mailEvalReport: null,
  mailClassifierInfo: {
    model_version: "cold",
    training_labels: 0,
    target_labels: 50,
    corrections_count: 0,
    status_text: "classifier: learning · 0 / 50 labels",
  },
  mailOnboardingCandidates: [],
  mailOnboardingOpen: false,
  mailComposeDrafts: {},
  conversationTasks: {},
  watches: [],
  watchBadgeConvIds: [],
  watchStatusNotice: "",
  messageEmailCards: {},
  expandedChatEmails: {},
  previewedAttachments: {},
  settingsAccordionOpen: {
    models: true,
    profiles: false,
    vault: false,
    mail: false,
    indexing: false,
  },
  modelConfig: null,
  modelConfigStatusMsg: "",
  profilePromptOpen: false,
  profilePromptDismissed: false,
  newsActiveLane: "stories",
  newsStories: [],
  newsForYouStories: [],
  newsPerspectivesStories: [],
  newsSelectedClusterId: null,
  newsPerspectiveMatrix: null,
  newsSources: [],
  newsCategories: [],
  newsSourcesAsOf: "",
  newsSourcesFilterQuery: "",
  newsSourcesFilterCategory: "",
  newsSourcesFilterBand: "",
  newsSourcesConflictedOnly: false,
  newsSourcesRssOnly: false,
  newsTopics: [],
  newsExploreMode: false,
  newsLoading: false,
  newsStatusMessage: "",
  newsReaderArticleId: null,
  newsReaderShowOriginal: false,
  messageAnswerMeta: {},
  expandedExplainMessages: {},
  expandedInDepthMessages: {},
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

const COMMAND_ALIASES: Record<string, CommandBarActionId> = {
  home: "home",
  start: "home",
  "start screen": "home",
  "for you": "home",
  "new conversation": "new_conversation",
  "new chat": "new_conversation",
  new: "new_conversation",
  bookmark: "bookmark",
  "bookmark page": "bookmark",
  "bookmark current": "bookmark",
  compare: "compare",
  "compare tabs": "compare",
  "compare view": "compare",
  lock: "lock",
  "lock profile": "lock",
  "lock vault": "lock",
  brain: "brain",
  "open brain": "brain",
  settings: "settings",
  "open settings": "settings",
};

const QUESTION_LEAD_RE =
  /^(?:what|who|where|when|why|how|which|can|could|should|would|does|do|did|is|are|was|were|will|explain|summarize|tell|describe|list|write|draft|compare|give|show)\b/i;

export function rankCommandBarRoutes(
  raw: string,
  opts?: {
    webSearchEnabled?: boolean;
    selectedModel?: LocalModelId;
    brainTerms?: string[];
    mailTerms?: string[];
  }
): CommandBarRoute[] {
  const trimmed = raw.trim();
  const webEnabled = Boolean(opts?.webSearchEnabled ?? state.webSearchEnabled);
  const model = opts?.selectedModel ?? state.selectedModel;
  const usesWeb = webEnabled || model === "planck3 (web)";
  const modelPrivacy = usesWeb ? "web search · duckduckgo" : "local only";

  if (!trimmed) {
    return [
      {
        kind: "run_command",
        label: "run command · new conversation",
        destination: "command: new_conversation",
        privacy: "local only",
        leaves_machine: false,
        command_id: "new_conversation",
      },
      {
        kind: "search_brain",
        label: "open brain · entities, passages & domain trust",
        destination: "satz brain",
        privacy: "local only",
        leaves_machine: false,
        query: "",
      },
      {
        kind: "search_mail",
        label: "open mail · inbox, pings, orders & promos",
        destination: "satz mail",
        privacy: "local only",
        leaves_machine: false,
        query: "",
      },
      {
        kind: "run_command",
        label: "run command · lock",
        destination: "command: lock",
        privacy: "local only",
        leaves_machine: false,
        command_id: "lock",
      },
    ];
  }

  const makeAskRoute = (q: string): CommandBarRoute => ({
    kind: "ask_model",
    label: `ask ${model} · "${q}"`,
    destination: `chat (${model})`,
    privacy: modelPrivacy,
    leaves_machine: usesWeb,
    question: q,
  });

  const makeBrainRoute = (q: string): CommandBarRoute => ({
    kind: "search_brain",
    label: `search brain · "${q}"`,
    destination: "brain (entities, passages, mail)",
    privacy: "local only",
    leaves_machine: false,
    query: q,
  });

  const makeMailRoute = (q: string): CommandBarRoute => ({
    kind: "search_mail",
    label: `search mail · "${q}"`,
    destination: "mail (FTS5)",
    privacy: "local only",
    leaves_machine: false,
    query: q,
  });

  const makeNewsRoute = (q: string): CommandBarRoute => ({
    kind: "search_news",
    label: `news intelligence · "${q}"`,
    destination: "satz news (read -> weigh -> write)",
    privacy: usesWeb ? "brave + trusted sources" : "local news cache + feeds",
    leaves_machine: usesWeb,
    query: q,
  });

  // 1. Exact command match
  const cmdNorm = trimmed.toLowerCase().replace(/^\//, "").trim();
  const matchedCmd = COMMAND_ALIASES[cmdNorm];
  if (matchedCmd) {
    return [
      {
        kind: "run_command",
        label: `run command · ${cmdNorm}`,
        destination: `command: ${matchedCmd}`,
        privacy: "local only",
        leaves_machine: false,
        command_id: matchedCmd,
      },
      makeAskRoute(trimmed),
      makeBrainRoute(trimmed),
      makeMailRoute(trimmed),
    ];
  }

  // 2. Reuse classifyStartInput for URL and URL + question
  const parsed = classifyStartInput(trimmed);
  if (parsed.kind === "url_only" && parsed.url) {
    const dom = extractDomain(parsed.url);
    return [
      {
        kind: "open_url",
        label: `open url · ${parsed.url}`,
        destination: dom,
        privacy: `loads ${dom}`,
        leaves_machine: true,
        url: parsed.url,
      },
      makeAskRoute(trimmed),
      makeBrainRoute(dom),
      makeMailRoute(dom),
    ];
  }

  if (parsed.kind === "url_and_text" && parsed.url && parsed.question) {
    const dom = extractDomain(parsed.url);
    const priv = usesWeb
      ? `loads ${dom} · web search · duckduckgo`
      : `loads ${dom} · local model`;
    return [
      {
        kind: "url_and_question",
        label: `open ${dom} + ask ${model} · "${parsed.question}"`,
        destination: `${dom} + ${model}`,
        privacy: priv,
        leaves_machine: true,
        url: parsed.url,
        question: parsed.question,
      },
      {
        kind: "open_url",
        label: `open url · ${parsed.url}`,
        destination: dom,
        privacy: `loads ${dom}`,
        leaves_machine: true,
        url: parsed.url,
      },
      makeAskRoute(trimmed),
      makeBrainRoute(parsed.question),
    ];
  }

  // 3. Explicit news prefix (`news: ...`, `breaking: ...`, `perspectives: ...`)
  const newsPrefixMatch = trimmed.match(
    /^(?:(?:news|breaking|perspectives|headlines)\s*:\s*|search\s+news\s+(?:for\s+)?)(.+)$/i
  );
  if (newsPrefixMatch) {
    const q = newsPrefixMatch[1].trim();
    return [makeNewsRoute(q), makeAskRoute(trimmed), makeBrainRoute(q)];
  }

  // 4. Explicit mail prefix (`mail: ...`, `from: ...`, `inbox: ...`, `search mail ...`)
  const mailPrefixMatch = trimmed.match(
    /^(?:(?:mail|inbox|from|to|subject)\s*:\s*|search\s+mail\s+(?:for\s+)?|in\s+mail\s+)(.+)$/i
  );
  if (mailPrefixMatch) {
    const q = mailPrefixMatch[1].trim();
    return [makeMailRoute(q), makeBrainRoute(q), makeAskRoute(trimmed)];
  }

  // 4. Explicit brain prefix (`brain: ...`, `memory: ...`, `entity: ...`, `search brain ...`)
  const brainPrefixMatch = trimmed.match(
    /^(?:(?:brain|memory|entity)\s*:\s*|search\s+brain\s+(?:for\s+)?|in\s+brain\s+)(.+)$/i
  );
  if (brainPrefixMatch) {
    const q = brainPrefixMatch[1].trim();
    return [makeBrainRoute(q), makeMailRoute(q), makeAskRoute(trimmed)];
  }

  const isQuestion =
    trimmed.endsWith("?") || QUESTION_LEAD_RE.test(trimmed);

  // 5. Non-question mail or brain terms
  if (!isQuestion) {
    const low = trimmed.toLowerCase();
    const hasEmailAddr = /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/.test(
      trimmed
    );
    const dynamicMailTerms = (opts?.mailTerms ?? []).map((t) => t.toLowerCase());
    for (const r of state.mailInboxRows) {
      if (r.from_name) dynamicMailTerms.push(String(r.from_name).toLowerCase());
      if (r.from_addr) dynamicMailTerms.push(String(r.from_addr).toLowerCase());
      if (r.subject) dynamicMailTerms.push(String(r.subject).toLowerCase());
    }
    const staticMailHints = [
      "jordan reyes",
      "anna weber",
      "lukas meier",
      "q4 launch",
      "lisbon workshop",
      "unread mail",
      "inbox",
    ];
    const isMailTerm =
      hasEmailAddr ||
      staticMailHints.some((h) => low.includes(h)) ||
      dynamicMailTerms.some((t) => t.length >= 3 && low.includes(t));

    const dynamicBrainTerms = (opts?.brainTerms ?? []).map((t) =>
      t.toLowerCase()
    );
    for (const ent of state.knowledge.brain?.entities ?? []) {
      dynamicBrainTerms.push(ent.name.toLowerCase());
      dynamicBrainTerms.push(ent.slug.toLowerCase());
    }
    const staticBrainHints = [
      "zalando",
      "zalando25autumn",
      "104099887712",
      "w1294810293",
      "hellofresh",
    ];
    const isBrainTerm =
      staticBrainHints.some((h) => low.includes(h)) ||
      dynamicBrainTerms.some((t) => t.length >= 3 && low.includes(t));

    if (isBrainTerm && !hasEmailAddr) {
      return [makeBrainRoute(trimmed), makeMailRoute(trimmed), makeAskRoute(trimmed)];
    }
    if (isMailTerm) {
      return [makeMailRoute(trimmed), makeBrainRoute(trimmed), makeAskRoute(trimmed)];
    }
  }

  // 6. Default: Question / prompt to model
  return [
    makeAskRoute(trimmed),
    makeBrainRoute(trimmed),
    makeMailRoute(trimmed),
  ];
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
  citeIndex: number | null;
  tab: BrowserTab;
  sourceId: string;
  domain: string;
  title: string;
  url: string;
  textChars: number;
  captureMode: "dom" | "fetch" | "timeout";
}

export function getActiveTabSources(
  detail: ConversationDetail | null = state.activeDetail
): ActiveTabSource[] {
  if (!detail) return [];
  const openTabs = detail.tabs.filter(
    (t) => t.is_open && t.kind !== "compose" && t.url !== "about:blank"
  );
  let nextCite = 1;
  return openTabs.map((tab, idx) => {
    const matchedSource =
      detail.sources.find((s) => s.tab_id === tab.id && s.in_context) ??
      detail.sources.find((s) => s.tab_id === tab.id && s.url === tab.url) ??
      detail.sources.find((s) => s.tab_id === tab.id);
    const sourceId = matchedSource?.id ?? tab.id;
    const domain = matchedSource?.domain || extractDomain(tab.url);
    const title = tab.title || matchedSource?.title || domain;
    const stat = state.sourceStats[sourceId];
    const isMailTab =
      tab.kind === "mail" || tab.url.startsWith("satzmail://message/");
    const textChars =
      stat?.chars_captured ??
      matchedSource?.text_chars ??
      (isMailTab ? 1 : 0);
    const captureMode: "dom" | "fetch" | "timeout" =
      stat?.capture_mode ?? (textChars === 0 && matchedSource?.captured_at ? "timeout" : "dom");
    const citeIndex = textChars > 0 ? nextCite++ : null;
    return {
      index: idx + 1,
      citeIndex,
      tab,
      sourceId,
      domain,
      title,
      url: tab.url,
      textChars,
      captureMode,
    };
  });
}

export function stripFilesystemPaths(raw: string): string {
  return raw
    .replace(/[A-Za-z]:\\[^\s"'`)\]]+/g, "<path>")
    .replace(/\/(?:Users|home|var|private|tmp|opt)\/[^\s"'`)\]]+/g, "<path>");
}

export function formatPlainErrorMessage(raw: string): {
  summary: string;
  rawDetail: string;
} {
  const cleanRaw = raw.replace(/^\[err\]\s*/i, "").replace(/^\[error:\s*/i, "").trim();
  const lower = cleanRaw.toLowerCase();
  if (lower.includes("stopped responding after 30 s")) {
    return {
      summary: "gemma stopped responding after 30 s.",
      rawDetail: cleanRaw,
    };
  }
  if (
    lower.includes("not found") &&
    (lower.includes("gemma") || lower.includes("checkpoint") || lower.includes("model"))
  ) {
    return {
      summary: "gemma is not downloaded [how to install]",
      rawDetail: cleanRaw,
    };
  }
  if (lower.includes("401") || lower.includes("403") || lower.includes("forbidden")) {
    return {
      summary: "the site refused the background fetch (401/403).",
      rawDetail: cleanRaw,
    };
  }
  if (
    lower.includes("load failed") ||
    lower.includes("failed to fetch") ||
    lower.includes("networkerror") ||
    lower.includes("offline")
  ) {
    return {
      summary: "could not reach the local model service.",
      rawDetail: cleanRaw,
    };
  }
  const stripped = stripFilesystemPaths(cleanRaw);
  return {
    summary: stripped.length > 140 ? `${stripped.slice(0, 140)}...` : stripped,
    rawDetail: cleanRaw,
  };
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

  // Never navigate away when asking about mail, inbox, brain, summarizing the current page,
  // or requesting an open web search handled by the sidecar Web Search Harness.
  if (
    /\b(my\s+(?:latest\s+)?(?:email|emails|inbox|mail|account|calendar|messages|address|order|package)|(?:summarize|summary\s+of|explain|translate)\s+(?:this|the)\s+(?:page|tab|article|email|site)|what\s+do\s+i\s+need\s+to\s+deal\s+with|draft\s+a\s+reply|store\s+(?:this|the)|save\s+(?:this|the)|in\s+my\s+brain)\b/i.test(
      trimmed
    ) ||
    /\b(?:do\s+(?:a\s+)?(?:quick\s+)?web\s+search|web\s+search|search\s+(?:on\s+)?the\s+web|search\s+online|look\s+(?:that|it|this)?\s*up\s+online|google\s+(?:that|it|this))\b/i.test(
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
      .replace(/\s+(?:then|please)[?.!]*$/i, "")
      .trim();

    if (
      !rawQuery ||
      /^(?:that|this|it|them|those|these|the\s+same)(?:\s+(?:then|now|please))?$/i.test(
        rawQuery
      )
    ) {
      return null;
    }

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
      if (!/^(?:duckduckgo\.com|google\.[a-z.]+|bing\.com)$/i.test(dom)) {
        const origin = getOriginFromUrl(activeSiteTab.url);
        const targetUrl = buildSiteSearchUrl(dom, rawQuery, origin);
        return {
          targetUrl,
          existingTabId: activeSiteTab.id,
          label: `${dom}: ${rawQuery}`,
        };
      }
    }

    // For general open-web queries with no named site, let the sidecar Web Search Harness
    // fetch sources and render clickable page previews without hijacking a DuckDuckGo SERP tab.
    void webSearchEnabled;
    return null;
  }

  return null;
}

export function getAvailableModelsForPicker(): Array<{
  id: LocalModelId;
  label: string;
}> {
  const base: Array<{ id: LocalModelId; label: string }> = [
    { id: "gemma-4-e4b", label: "gemma-4-e4b (local)" },
    { id: "planck3 (web)", label: "planck3 (web · local)" },
    { id: "hertz (reader)", label: "hertz (reader · local)" },
    { id: "planck (reader)", label: "planck (reader · local)" },
  ];
  const seen = new Set<string>(base.map((b) => b.id));
  const cfg = state.modelConfig ?? state.sidecar.model_config ?? null;
  for (const prov of cfg?.cloud_providers ?? []) {
    if (!prov.configured && (!prov.models || prov.models.length === 0)) continue;
    for (const m of prov.models ?? []) {
      if (m.id && !seen.has(m.id)) {
        seen.add(m.id);
        base.push({
          id: m.id,
          label: m.id,
        });
      }
    }
  }
  if (state.selectedModel && !seen.has(state.selectedModel)) {
    base.push({ id: state.selectedModel, label: state.selectedModel });
  }
  return base;
}

/**
 * Syncs `state.selectedModel` to Settings' configured `roles.chat` unless the user
 * manually picked a different model for the current chat session (`force = true`
 * overrides that on profile switches, `[+ new conversation]`, or Settings updates).
 */
export function syncConfiguredChatModel(
  cfg?: ModelManagementConfig | null,
  force = false
): boolean {
  const effectiveCfg = cfg ?? state.modelConfig ?? state.sidecar.model_config ?? null;
  if (effectiveCfg) {
    state.modelConfig = effectiveCfg;
    if (state.sidecar) {
      state.sidecar.model_config = effectiveCfg;
    }
  }
  if (force) {
    state.userOverrodeModelInSession = false;
  }
  const configuredChat = effectiveCfg?.roles?.chat?.trim();
  if (!configuredChat) return false;
  if (!state.userOverrodeModelInSession && state.selectedModel !== configuredChat) {
    state.selectedModel = configuredChat as LocalModelId;
    return true;
  }
  return false;
}

export function getActiveStream(convId?: string | null): ConvStreamState | null {
  const cid = convId ?? state.activeDetail?.conversation.id ?? "";
  if (!cid) return null;
  return state.streamsByConv[cid] ?? null;
}

export function isConvStreaming(convId?: string | null): boolean {
  return Boolean(getActiveStream(convId));
}

export function hasAnyActiveStream(): boolean {
  return Object.keys(state.streamsByConv).length > 0;
}

export function getModelPrivacySummary(modelId: string): string {
  const m = (modelId || "").toLowerCase();
  if (m.startsWith("gemini:") || m.startsWith("gemini-")) {
    return "[cloud · sends context to google gemini api]";
  }
  if (m.startsWith("anthropic:") || m.startsWith("claude-")) {
    return "[cloud · sends context to anthropic api]";
  }
  if (m.startsWith("openai:") || m.startsWith("gpt-") || m.startsWith("o1") || m.startsWith("o3") || m.startsWith("o4")) {
    return "[cloud · sends context to openai api]";
  }
  if (m.startsWith("mistral:")) {
    return "[cloud · sends context to mistral api]";
  }
  if (m.includes("cloud")) {
    return "[cloud · sends context to external api]";
  }
  return "[local only]";
}
