import { invoke } from "@tauri-apps/api/core";
import { extractDomain, state } from "./state";
import type {
  AgentTaskCard,
  BookmarkItem,
  BrainCitationItem,
  BrainProposalItem,
  BrainSearchResponse,
  BrowserTab,
  ChatEmailCard,
  ChatImageAttachment,
  ChatMessage,
  CitationCheckEntry,
  CitedSourcePreview,
  ContentTranslationConfig,
  Conversation,
  ConversationDetail,
  ConversationOrigin,
  ConversationStatus,
  DigestEntry,
  DoctorRoleEntry,
  DriveCreateTarget,
  DriveFileTypeFilter,
  DriveListResponse,
  DriveProviderFilter,
  DrivesStatusResponse,
  EvalCaseItem,
  EvalSuiteRunSummary,
  FindingItem,
  GoogleOAuthStatus,
  HarnessSignalPayload,
  I18nBundleEntry,
  I18nStatusResponse,
  KnowledgeSummary,
  LocalModelId,
  MailAccountItem,
  MailLaneResponse,
  MailPreset,
  MailStatusSummary,
  ModelManagementConfig,
  AnswerMeta,
  NewsCategoryEntry,
  NewsPerspectiveMatrix,
  NewsSourceEntry,
  NewsStoryCluster,
  NewsTopicItem,
  PageTranslationBlock,
  ProfileStatusSummary,
  ProviderRegistryState,
  RoutingDecisionInfo,
  RoutingPolicySummary,
  SidecarHealth,
  SettingsUiCard,
  SkillProposalItem,
  DomainRecipeItem,
  SourceItem,
  StagedSettingsFile,
  SourceStatEntry,
  TabBoundsSpec,
  TabKind,
  WatchItem,
} from "./types";

let sidecarBaseUrl = "";
let sidecarAuthToken = "";
let sidecarConfigPromise: Promise<{ baseUrl: string; token: string }> | null = null;

async function ensureSidecarConfig(): Promise<{ baseUrl: string; token: string }> {
  if (sidecarBaseUrl && sidecarAuthToken) {
    return { baseUrl: sidecarBaseUrl, token: sidecarAuthToken };
  }
  if (!sidecarConfigPromise) {
    sidecarConfigPromise = (async () => {
      try {
        const cfg = await invoke<{ base_url: string; token: string }>("get_sidecar_config");
        sidecarBaseUrl = cfg.base_url;
        sidecarAuthToken = cfg.token;
      } catch {
        if (!sidecarBaseUrl) {
          sidecarBaseUrl = "http://127.0.0.1:8020";
        }
      }
      return { baseUrl: sidecarBaseUrl, token: sidecarAuthToken };
    })();
  }
  return await sidecarConfigPromise;
}

async function sidecarFetch(
  path: string,
  init: RequestInit = {},
  timeoutMs?: number
): Promise<Response> {
  const { baseUrl, token } = await ensureSidecarConfig();
  const headers = new Headers(init.headers ?? {});
  if (token) {
    headers.set("X-Satz-Token", token);
  }
  let ctrl: AbortController | null = null;
  let timerId: number | null = null;
  if (timeoutMs && timeoutMs > 0 && !init.signal) {
    ctrl = new AbortController();
    timerId = window.setTimeout(() => ctrl?.abort(), timeoutMs);
  }
  try {
    return await fetch(`${baseUrl}${path}`, {
      ...init,
      headers,
      signal: init.signal ?? ctrl?.signal,
    });
  } finally {
    if (timerId !== null) {
      window.clearTimeout(timerId);
    }
  }
}

function mapConversationRow(raw: Record<string, unknown>): Conversation {
  // v1 -> v2 migration mapping: map legacy intent_title to title
  const mappedTitle = String(raw.title ?? raw.intent_title ?? "untitled");
  const rawOrigin = String(raw.origin ?? "chat");
  const origin: ConversationOrigin =
    rawOrigin === "mail" ||
    rawOrigin === "news" ||
    rawOrigin === "drives" ||
    rawOrigin === "direct" ||
    rawOrigin === "settings" ||
    rawOrigin === "news_settings" ||
    rawOrigin === "news_perspectives"
      ? rawOrigin
      : "chat";
  return {
    id: String(raw.id ?? ""),
    title: mappedTitle,
    status: (raw.status === "archived" ? "archived" : "active") as ConversationStatus,
    pinned: Boolean(raw.pinned),
    origin,
    created_at: String(raw.created_at ?? ""),
    last_active_at: String(raw.last_active_at ?? raw.created_at ?? ""),
    source_count:
      typeof raw.source_count === "number" ? raw.source_count : undefined,
    summary: raw.summary ? String(raw.summary) : null,
  };
}

export async function apiListConversations(): Promise<Conversation[]> {
  try {
    const rows = await invoke<Array<Record<string, unknown>>>("list_conversations");
    return rows.map(mapConversationRow);
  } catch {
    return [];
  }
}

export async function apiGetConversation(
  conversationId: string
): Promise<ConversationDetail | null> {
  try {
    const raw = await invoke<Record<string, unknown>>("get_conversation", {
      conversationId,
    });
    return normalizeConversationDetail(raw);
  } catch {
    try {
      const legacy = await invoke<Record<string, unknown>>(
        "get_conversation_bundle",
        { conversationId }
      );
      return normalizeConversationDetail(legacy);
    } catch {
      return null;
    }
  }
}

function normalizeConversationDetail(
  raw: Record<string, unknown>
): ConversationDetail {
  const conv = mapConversationRow(
    (raw.conversation as Record<string, unknown>) ?? {}
  );
  const rawTabs = (raw.tabs ?? raw.attached_pages ?? []) as Array<
    Record<string, unknown>
  >;
  const tabs: BrowserTab[] = rawTabs.map((t, idx) => ({
    id: String(t.id ?? `tab-${idx}`),
    conversation_id: conv.id,
    position: typeof t.position === "number" ? t.position : Number(t.pane_index ?? idx),
    url: String(t.url ?? ""),
    title: String(t.title ?? t.url ?? ""),
    is_open: t.is_open !== undefined ? Boolean(t.is_open) : true,
    created_at: String(t.created_at ?? conv.created_at),
    kind: (t.kind === "mail" || t.kind === "compose" ? t.kind : "site") as TabKind,
  }));

  const rawSources = (raw.sources ?? []) as Array<Record<string, unknown>>;
  const sources: SourceItem[] =
    rawSources.length > 0
      ? rawSources.map((s) => ({
          id: String(s.id ?? ""),
          conversation_id: conv.id,
          tab_id: s.tab_id ? String(s.tab_id) : null,
          url: String(s.url ?? ""),
          title: String(s.title ?? s.url ?? ""),
          domain: String(s.domain ?? extractDomain(String(s.url ?? ""))),
          in_context: s.in_context !== undefined ? Boolean(s.in_context) : true,
          added_at: String(s.added_at ?? conv.created_at),
          captured_at: s.captured_at ? String(s.captured_at) : null,
          text_chars:
            typeof s.text_chars === "number" ? s.text_chars : null,
        }))
      : tabs.map((t) => ({
          id: `src-${t.id}`,
          conversation_id: conv.id,
          tab_id: t.id,
          url: t.url,
          title: t.title,
          domain: extractDomain(t.url),
          in_context: true,
          added_at: t.created_at,
          captured_at: null,
          text_chars: null,
        }));

  const rawMsgs = (raw.messages ?? raw.notes ?? []) as Array<
    Record<string, unknown>
  >;
  const messages: ChatMessage[] = rawMsgs.map((m) => {
    let parsedCheck: CitationCheckEntry[] | undefined;
    if (typeof m.citation_check_json === "string" && m.citation_check_json) {
      try {
        parsedCheck = JSON.parse(m.citation_check_json) as CitationCheckEntry[];
      } catch {
        parsedCheck = undefined;
      }
    }
    let parsedExtras: Record<string, unknown> | null = null;
    if (typeof m.extras_json === "string" && m.extras_json) {
      try {
        parsedExtras = JSON.parse(m.extras_json) as Record<string, unknown>;
      } catch {
        parsedExtras = null;
      }
    }
    return {
      id: String(m.id ?? ""),
      conversation_id: conv.id,
      role: (m.role ?? m.author ?? "user") as "user" | "assistant" | "system",
      content: String(m.content ?? ""),
      model: m.model ? String(m.model) : null,
      source_ids_json: m.source_ids_json ? String(m.source_ids_json) : null,
      created_at: String(m.created_at ?? ""),
      citations_ok:
        typeof m.citations_ok === "number" ? m.citations_ok : null,
      citations_flagged:
        typeof m.citations_flagged === "number" ? m.citations_flagged : null,
      citation_check_json:
        typeof m.citation_check_json === "string"
          ? m.citation_check_json
          : null,
      extras_json:
        typeof m.extras_json === "string" ? m.extras_json : null,
      citation_check: parsedCheck,
      cited_sources: parsedExtras?.cited_sources as ChatMessage["cited_sources"],
      findings: parsedExtras?.findings as ChatMessage["findings"],
      brain_sources: parsedExtras?.brain_sources as ChatMessage["brain_sources"],
      proposals: parsedExtras?.proposals as ChatMessage["proposals"],
      email_cards: parsedExtras?.email_cards as ChatMessage["email_cards"],
      email_draft: parsedExtras?.email_draft as ChatMessage["email_draft"],
      answer_meta: parsedExtras?.answer_meta as ChatMessage["answer_meta"],
      tools_used: Array.isArray(parsedExtras?.tools_used)
        ? (parsedExtras.tools_used as string[])
        : undefined,
      images: Array.isArray(parsedExtras?.images)
        ? (parsedExtras.images as ChatMessage["images"])
        : undefined,
      staged_files: Array.isArray(parsedExtras?.staged_files)
        ? (parsedExtras.staged_files as ChatMessage["staged_files"])
        : undefined,
      ui_cards: Array.isArray(parsedExtras?.ui_cards)
        ? (parsedExtras.ui_cards as ChatMessage["ui_cards"])
        : undefined,
    };
  });

  const rawHist = (raw.history ?? []) as Array<Record<string, unknown>>;
  const history = rawHist.map((h) => ({
    id: String(h.id ?? ""),
    conversation_id: conv.id,
    tab_id: h.tab_id ? String(h.tab_id) : null,
    url: String(h.url ?? ""),
    title: String(h.title ?? ""),
    visited_at: String(h.visited_at ?? ""),
  }));

  return {
    conversation: conv,
    tabs,
    sources,
    messages,
    history,
  };
}

export async function apiCreateConversation(
  title: string,
  origin: ConversationOrigin = "chat"
): Promise<Conversation> {
  const row = await invoke<Record<string, unknown>>("create_conversation", {
    title,
    origin,
  });
  return mapConversationRow(row);
}

export async function apiRenameConversation(
  conversationId: string,
  title: string
): Promise<Conversation> {
  const row = await invoke<Record<string, unknown>>("rename_conversation", {
    conversationId,
    title,
  });
  return mapConversationRow(row);
}

export async function apiPinConversation(
  conversationId: string
): Promise<Conversation> {
  try {
    const row = await invoke<Record<string, unknown>>("pin_conversation", {
      conversationId,
    });
    return mapConversationRow(row);
  } catch {
    const row = await invoke<Record<string, unknown>>(
      "toggle_pin_conversation",
      { conversationId }
    );
    return mapConversationRow(row);
  }
}

export async function apiArchiveConversation(
  conversationId: string,
  archived: boolean
): Promise<Conversation> {
  try {
    const row = await invoke<Record<string, unknown>>("archive_conversation", {
      conversationId,
      archived,
    });
    return mapConversationRow(row);
  } catch {
    const row = await invoke<Record<string, unknown>>(
      "update_conversation_status",
      {
        conversationId,
        status: archived ? "archived" : "active",
      }
    );
    return mapConversationRow(row);
  }
}

export async function apiDeleteConversation(
  conversationId: string
): Promise<void> {
  await invoke("delete_conversation", { conversationId });
  try {
    await sidecarFetch("/forget", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId }),
    });
  } catch {
    // Sidecar offline is fine
  }
}

export async function apiSetConversationSummary(
  conversationId: string,
  summary: string
): Promise<void> {
  try {
    await invoke("set_conversation_summary", { conversationId, summary });
  } catch {
    // Ignore if command unavailable
  }
}

export async function apiEnsureMailConversation(): Promise<Conversation> {
  const row = await invoke<Record<string, unknown>>("ensure_mail_conversation");
  const conv = mapConversationRow(row);
  try {
    state.conversations = await apiListConversations();
  } catch {
    if (!state.conversations.some((c) => c.id === conv.id)) {
      state.conversations = [conv, ...state.conversations];
    }
  }
  return conv;
}

export async function apiEnsureNewsConversation(): Promise<Conversation> {
  const row = await invoke<Record<string, unknown>>("ensure_news_conversation");
  const conv = mapConversationRow(row);
  try {
    state.conversations = await apiListConversations();
  } catch {
    if (!state.conversations.some((c) => c.id === conv.id)) {
      state.conversations = [conv, ...state.conversations];
    }
  }
  return conv;
}

export async function apiEnsureDrivesConversation(): Promise<Conversation> {
  const row = await invoke<Record<string, unknown>>("ensure_drives_conversation");
  const conv = mapConversationRow(row);
  try {
    state.conversations = await apiListConversations();
  } catch {
    if (!state.conversations.some((c) => c.id === conv.id)) {
      state.conversations = [conv, ...state.conversations];
    }
  }
  return conv;
}

async function ensureSystemConversation(command: string): Promise<Conversation> {
  const row = await invoke<Record<string, unknown>>(command);
  const conv = mapConversationRow(row);
  try {
    state.conversations = await apiListConversations();
  } catch {
    if (!state.conversations.some((c) => c.id === conv.id)) {
      state.conversations = [conv, ...state.conversations];
    }
  }
  return conv;
}

export async function apiEnsureSettingsConversation(): Promise<Conversation> {
  return ensureSystemConversation("ensure_settings_conversation");
}

export async function apiEnsureNewsSettingsConversation(): Promise<Conversation> {
  return ensureSystemConversation("ensure_news_settings_conversation");
}

export async function apiEnsureNewsPerspectivesConversation(): Promise<Conversation> {
  return ensureSystemConversation("ensure_news_perspectives_conversation");
}

export async function apiOpenTab(
  conversationId: string,
  url: string,
  title?: string,
  kind?: TabKind
): Promise<BrowserTab> {
  return await invoke<BrowserTab>("open_tab", {
    conversationId,
    url,
    title: title ?? null,
    kind: kind ?? null,
  });
}

export async function apiCloseTab(tabId: string): Promise<void> {
  await invoke("close_tab", { tabId });
}

export async function apiNavigateTab(
  tabId: string,
  url: string
): Promise<BrowserTab> {
  return await invoke<BrowserTab>("navigate_tab", { tabId, url });
}

export async function apiNavigateAndCaptureTab(
  tabId: string,
  url: string,
  waitMs = 2400
): Promise<BrowserTab | null> {
  try {
    return await invoke<BrowserTab>("navigate_and_capture_tab", {
      tabId,
      url,
      waitMs,
    });
  } catch {
    try {
      return await invoke<BrowserTab>("navigate_tab", { tabId, url });
    } catch {
      return null;
    }
  }
}

export interface TabUnsubscribeActorResult {
  ok: boolean;
  status:
    | "clicked"
    | "already_unsubscribed"
    | "needs_user"
    | "manual_review"
    | "needs_confirmation"
    | "error"
    | "unavailable";
  reason?: string;
  clicked_label?: string;
  candidate_label?: string;
  matched_selector?: string;
  final_status?: string;
  url?: string;
  url_before?: string;
  title?: string;
  excerpt?: string;
}

export async function apiExecuteTabUnsubscribeActor(
  tabId: string,
  url: string,
  waitMs = 2600,
  hintSelector?: string
): Promise<TabUnsubscribeActorResult> {
  try {
    return await invoke<TabUnsubscribeActorResult>(
      "execute_tab_unsubscribe_actor",
      {
        tabId,
        url,
        waitMs,
        hintSelector: hintSelector ?? null,
      }
    );
  } catch (e) {
    return {
      ok: false,
      status: "unavailable",
      reason: String(e),
      url,
    };
  }
}

export interface TabActionResult {
  ok: boolean;
  error?: string;
  status?: string;
  action_kind?: string;
  eid?: string;
  label?: string;
  clicked_label?: string;
  matched_selector?: string;
  url?: string;
  title?: string;
  new_value?: string;
}

export async function apiExecuteTabAction(
  tabId: string,
  action: {
    expected_origin?: string;
    eid?: string;
    action_kind?: string;
    value?: string;
    element_label?: string;
    selector_hint?: unknown;
  }
): Promise<TabActionResult> {
  try {
    return await invoke<TabActionResult>("execute_tab_action", {
      tabId,
      action,
    });
  } catch (e) {
    return {
      ok: false,
      error: String(e),
      action_kind: action.action_kind,
      eid: action.eid,
    };
  }
}

export async function apiControlTab(
  tabId: string,
  action: "back" | "forward" | "reload"
): Promise<void> {
  await invoke("control_tab", { tabId, action });
}

export async function apiSyncTabWebviews(
  visible: TabBoundsSpec[]
): Promise<void> {
  try {
    await invoke("sync_tab_webviews", { visible });
  } catch {
    if (visible.length === 0) {
      try {
        await invoke("hide_all_child_panes");
      } catch {
        // Ignore if not registered
      }
    }
  }
}

export async function apiCaptureOpenTabs(
  conversationId: string
): Promise<number> {
  try {
    return await invoke<number>("capture_open_tabs", { conversationId });
  } catch {
    return 0;
  }
}

export async function apiAutofillTabCredentials(
  tabId: string,
  autoSubmit = true
): Promise<boolean> {
  try {
    return await invoke<boolean>("autofill_tab_credentials", {
      tabId,
      autoSubmit,
    });
  } catch {
    return false;
  }
}

export async function apiSetSourceInContext(
  sourceId: string,
  inContext: boolean
): Promise<void> {
  await invoke("set_source_in_context", { sourceId, inContext });
}

export async function apiAddMessage(
  conversationId: string,
  role: "user" | "assistant" | "system",
  content: string,
  model: string | null = null,
  sourceIdsJson: string | null = null,
  citationsOk: number | null = null,
  citationsFlagged: number | null = null,
  citationCheckJson: string | null = null,
  extrasJson: string | null = null
): Promise<ChatMessage> {
  return await invoke<ChatMessage>("add_message", {
    conversationId,
    role,
    content,
    model,
    sourceIdsJson,
    citationsOk,
    citationsFlagged,
    citationCheckJson,
    extrasJson,
  });
}

export async function apiListBookmarks(): Promise<BookmarkItem[]> {
  try {
    return await invoke<BookmarkItem[]>("list_bookmarks");
  } catch {
    return [];
  }
}

export async function apiAddBookmark(
  title: string,
  url: string,
  faviconUrl: string | null = null
): Promise<BookmarkItem> {
  return await invoke<BookmarkItem>("add_bookmark", {
    title,
    url,
    faviconUrl,
  });
}

export async function apiSetBookmarkFavicon(
  bookmarkId: string,
  faviconUrl: string
): Promise<void> {
  try {
    await invoke("set_bookmark_favicon", { bookmarkId, faviconUrl });
  } catch {
    // Non-fatal in browser-only Vite preview
  }
}

export async function apiRemoveBookmark(bookmarkId: string): Promise<void> {
  await invoke("remove_bookmark", { bookmarkId });
}

export async function sidecarResolveFavicons(
  items: Array<{ url: string; icon_url?: string | null }>,
  force = false
): Promise<{
  icons: Record<string, string>;
  by_origin: Record<string, string>;
}> {
  if (!items || items.length === 0) {
    return { icons: {}, by_origin: {} };
  }
  try {
    const res = await sidecarFetch("/favicons/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items, force }),
    });
    if (!res.ok) return { icons: {}, by_origin: {} };
    const data = (await res.json()) as {
      icons?: Record<string, string>;
      by_origin?: Record<string, string>;
    };
    return {
      icons: data.icons ?? {},
      by_origin: data.by_origin ?? {},
    };
  } catch {
    return { icons: {}, by_origin: {} };
  }
}

export async function sidecarFetchHealth(timeoutMs?: number): Promise<SidecarHealth> {
  try {
    const res = await sidecarFetch("/health", {}, timeoutMs);
    if (!res.ok) throw new Error("sidecar error");
    const data = (await res.json()) as SidecarHealth;
    return {
      online: true,
      version: data.version,
      models: data.models ?? [
        { id: "gemma-4-e4b", state: "not_loaded" },
        { id: "planck3 (web)", state: "not_loaded" },
        { id: "hertz (reader)", state: "not_loaded" },
        { id: "planck (reader)", state: "not_loaded" },
      ],
      ingest_queue_len: data.ingest_queue_len ?? 0,
      pause_learning: Boolean(data.pause_learning),
      errors: Array.isArray(data.errors) ? data.errors : [],
      mail: data.mail ?? null,
      watch_badges: Array.isArray(data.watch_badges) ? data.watch_badges : [],
      model_config: data.model_config,
    };
  } catch {
    return {
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
    };
  }
}

export async function sidecarFetchDoctor(): Promise<DoctorRoleEntry[]> {
  try {
    const res = await sidecarFetch("/doctor");
    if (!res.ok) return [];
    const data = (await res.json()) as { roles?: DoctorRoleEntry[] };
    return Array.isArray(data.roles) ? data.roles : [];
  } catch {
    return [];
  }
}

export async function sidecarClearErrors(): Promise<void> {
  try {
    await sidecarFetch("/errors/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
  } catch {
    // Ignore when offline
  }
}

export async function sidecarFetchDigest(): Promise<DigestEntry[]> {
  try {
    const res = await sidecarFetch("/digest");
    if (!res.ok) return [];
    const data = (await res.json()) as { items?: DigestEntry[] };
    return data.items ?? [];
  } catch {
    return [];
  }
}

export async function sidecarFetchKnowledge(timeoutMs?: number): Promise<KnowledgeSummary | null> {
  try {
    const res = await sidecarFetch("/knowledge", {}, timeoutMs);
    if (!res.ok) return null;
    const raw = (await res.json()) as Record<string, unknown>;
    const rawDomains = (raw.top_domains ?? []) as Array<Record<string, unknown>>;
    const rawTopics = (raw.top_topics ?? []) as Array<Record<string, unknown>>;
    const rawPassages = (raw.passages ?? []) as Array<Record<string, unknown>>;
    const rawThisWeek = (raw.this_week ?? []) as Array<Record<string, unknown>>;
    const rawBrain = (raw.brain ?? null) as Record<string, unknown> | null;
    const rawEntities = (rawBrain?.entities ?? []) as Array<Record<string, unknown>>;
    const rawBookmarks = (raw.bookmarks_indexed ?? []) as Array<Record<string, unknown>>;
    const rawProfile = (raw.profile ?? null) as Record<string, unknown> | null;
    const rawVault = (raw.vault ?? null) as Record<string, unknown> | null;

    return {
      pause_learning: Boolean(raw.pause_learning),
      queue_len: Number(raw.queue_len ?? 0),
      brain: rawBrain
        ? {
            brain_dir: String(rawBrain.brain_dir ?? ""),
            brain_md: String(rawBrain.brain_md ?? ""),
            entity_count: Number(rawBrain.entity_count ?? rawEntities.length),
            locked: Boolean(rawBrain.locked),
            message: rawBrain.message ? String(rawBrain.message) : undefined,
            brain_ranking: rawBrain.brain_ranking
              ? String(rawBrain.brain_ranking)
              : undefined,
            encoder: rawBrain.encoder
              ? {
                  mode: String(
                    (rawBrain.encoder as Record<string, unknown>).mode ?? ""
                  ),
                  state: String(
                    (rawBrain.encoder as Record<string, unknown>).state ?? ""
                  ),
                  label: String(
                    (rawBrain.encoder as Record<string, unknown>).label ?? ""
                  ),
                }
              : undefined,
            entities: rawEntities.map((e) => ({
              slug: String(e.slug ?? ""),
              type: String(e.type ?? "note"),
              name: String(e.name ?? ""),
              tier: Number(e.tier ?? 2),
              summary: String(e.summary ?? ""),
              path: String(e.path ?? ""),
              source_url: e.source_url ? String(e.source_url) : undefined,
              body: e.body ? String(e.body) : undefined,
              attributes: (e.attributes ?? {}) as Record<string, unknown>,
              updated: String(e.updated ?? ""),
            })),
          }
        : undefined,
      bookmarks_indexed: rawBookmarks.map((b) => ({
        id: String(b.id ?? ""),
        url: String(b.url ?? ""),
        domain: String(b.domain ?? ""),
        title: String(b.title ?? ""),
        last_indexed_at: Number(b.last_indexed_at ?? 0),
        text_chars: Number(b.text_chars ?? 0),
        status: String(b.status ?? "pending"),
      })),
      profile: rawProfile
        ? {
            profiles: ((rawProfile.profiles ?? []) as Array<Record<string, unknown>>).map(
              (p) => ({
                id: String(p.id ?? ""),
                name: String(p.name ?? ""),
                created_at: String(p.created_at ?? ""),
                last_active_at: String(p.last_active_at ?? ""),
                credential_services_count: Number(p.credential_services_count ?? 0),
                is_active: Boolean(p.is_active),
                failed_attempts: Number(p.failed_attempts ?? 0),
                retry_after_seconds: Number(p.retry_after_seconds ?? 0),
              })
            ),
            active_profile_id: rawProfile.active_profile_id
              ? String(rawProfile.active_profile_id)
              : null,
            unlocked: Boolean(rawProfile.unlocked),
            active_profile: rawProfile.active_profile
              ? {
                  id: String((rawProfile.active_profile as Record<string, unknown>).id ?? ""),
                  name: String((rawProfile.active_profile as Record<string, unknown>).name ?? ""),
                  created_at: String(
                    (rawProfile.active_profile as Record<string, unknown>).created_at ?? ""
                  ),
                  last_active_at: String(
                    (rawProfile.active_profile as Record<string, unknown>).last_active_at ?? ""
                  ),
                  credential_services_count: Number(
                    (rawProfile.active_profile as Record<string, unknown>)
                      .credential_services_count ?? 0
                  ),
                  is_active: true,
                }
              : null,
          }
        : undefined,
      vault: rawVault
        ? {
            unlocked: Boolean(rawVault.unlocked),
            profile_id: rawVault.profile_id ? String(rawVault.profile_id) : null,
            env_path: rawVault.env_path ? String(rawVault.env_path) : null,
            services: ((rawVault.services ?? []) as Array<Record<string, unknown>>).map((s) => ({
              service: String(s.service ?? ""),
              domain: String(s.domain ?? ""),
              username: String(s.username ?? ""),
              has_password: Boolean(s.has_password),
              has_token: Boolean(s.has_token),
              has_cookie: Boolean(s.has_cookie),
            keys: ((s.keys ?? []) as unknown[]).map((k) => String(k)),
          })),
          raw_env: "",
        }
      : undefined,
    top_domains: rawDomains.map((d) => {
      const trustVal = Number(d.effective ?? d.trust ?? d.score ?? 0);
      return {
        domain: String(d.domain ?? ""),
        visits: Number(d.visits ?? 0),
        dwell_seconds: Number(d.dwell_seconds ?? 0),
        trust: trustVal,
        score: trustVal,
        system: d.system !== undefined ? Number(d.system) : trustVal,
        personal:
          d.personal !== undefined && d.personal !== null
            ? Number(d.personal)
            : null,
        effective: trustVal,
        band: d.band ? String(d.band) : undefined,
        band_label: d.band_label ? String(d.band_label) : undefined,
        category: d.category ? String(d.category) : undefined,
        why: d.why ? String(d.why) : undefined,
        scored: d.scored !== undefined ? Boolean(d.scored) : false,
        conflict: d.conflict !== undefined ? Boolean(d.conflict) : false,
      };
    }),
    top_topics: rawTopics.map((t) => {
      const entName = String(t.entity ?? t.topic ?? "");
      const scoreVal = Number(t.score ?? t.weight ?? 0);
      return {
        entity: entName,
        score: scoreVal,
        topic: entName,
        weight: scoreVal,
      };
    }),
    passages: rawPassages.map((p) => ({
      id: String(p.id ?? ""),
      conversation_id: String(p.conversation_id ?? ""),
      entity: String(p.entity ?? p.title ?? p.domain ?? ""),
      url: String(p.url ?? ""),
      text: String(p.text ?? ""),
      added_at: String(p.added_at ?? p.ts ?? ""),
    })),
    this_week: rawThisWeek.map((w) => ({
      kind: (w.kind === "received" ? "received" : "read") as "read" | "received",
      title: String(w.title ?? ""),
      url: String(w.url ?? ""),
      domain: String(w.domain ?? ""),
      ts: Number(w.ts ?? 0),
      label: w.label ? String(w.label) : undefined,
      message_id: w.message_id ? String(w.message_id) : undefined,
    })),
    skill_proposals: (raw.skill_proposals ?? []) as SkillProposalItem[],
    domain_recipes_count: Number(raw.domain_recipes_count ?? 0),
    recipes: (raw.recipes ?? []) as DomainRecipeItem[],
    evals: (raw.evals ?? []) as EvalCaseItem[],
    evals_count: Number(raw.evals_count ?? 0),
  };
  } catch {
    return null;
  }
}

export async function sidecarSetPauseLearning(paused: boolean): Promise<boolean> {
  try {
    const res = await sidecarFetch("/knowledge/pause", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pause_learning: paused }),
    });
    if (!res.ok) return paused;
    const data = (await res.json()) as { pause_learning: boolean };
    return Boolean(data.pause_learning);
  } catch {
    return paused;
  }
}

export async function sidecarDeletePassage(passageId: string): Promise<void> {
  try {
    await sidecarFetch("/knowledge/delete_passage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passage_id: passageId }),
    });
  } catch {
    // Ignore when offline
  }
}

export async function sidecarDeleteBrainEntity(slug: string): Promise<void> {
  try {
    await sidecarFetch("/knowledge/delete_entity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug }),
    });
  } catch {
    // Ignore when offline
  }
}

export async function sidecarSetDomainTrust(
  domain: string,
  personalScore: number | null
): Promise<Record<string, unknown> | null> {
  try {
    const res = await sidecarFetch("/knowledge/domain_trust", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain, personal_score: personalScore }),
    });
    if (!res.ok) return null;
    return (await res.json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export async function sidecarSearchBrain(
  query: string,
  limit = 20
): Promise<BrainSearchResponse | null> {
  try {
    const res = await sidecarFetch(
      `/brain/search?q=${encodeURIComponent(query)}&limit=${limit}`
    );
    if (!res.ok) return null;
    return (await res.json()) as BrainSearchResponse;
  } catch {
    return null;
  }
}

export async function sidecarAcceptBrainProposal(
  proposalId: string
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await sidecarFetch("/brain/accept", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proposal_id: proposalId }),
    });
    const data = (await res.json()) as { ok?: boolean; error?: string };
    return { ok: Boolean(res.ok && data.ok), error: data.error };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarUpsertBrainEntity(payload: {
  type: string;
  name: string;
  summary: string;
  attributes?: Record<string, unknown>;
  content?: string;
  source_url?: string;
}): Promise<{ ok: boolean }> {
  try {
    const res = await sidecarFetch("/knowledge/upsert_entity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return { ok: res.ok };
  } catch {
    return { ok: false };
  }
}

export async function sidecarRejectBrainProposal(
  proposalId: string
): Promise<boolean> {
  try {
    const res = await sidecarFetch("/brain/reject", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proposal_id: proposalId }),
    });
    const data = (await res.json()) as { ok?: boolean };
    return Boolean(res.ok && data.ok);
  } catch {
    return false;
  }
}

export async function sidecarSyncBookmarks(
  bookmarks: BookmarkItem[]
): Promise<void> {
  try {
    await sidecarFetch("/bookmarks/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bookmarks: bookmarks.map((b) => ({
          id: b.id,
          title: b.title,
          url: b.url,
        })),
      }),
    });
  } catch {
    // Ignore when offline
  }
}

function _normalizeProfileSummary(data: {
  unlocked?: boolean;
  active_profile_id?: string | null;
  active_profile?: ProfileStatusSummary["active_profile"];
  profiles?: ProfileStatusSummary["profiles"];
}): ProfileStatusSummary {
  const profiles = data.profiles ?? [];
  const active = data.active_profile ?? profiles.find((p) => p.is_active) ?? null;
  return {
    unlocked: Boolean(data.unlocked ?? true),
    active_profile_id: data.active_profile_id ?? active?.id ?? null,
    active_profile: active,
    profiles,
  };
}

export async function sidecarCreateProfile(
  name: string,
  pin: string
): Promise<{
  ok: boolean;
  error?: string;
  profile?: ProfileStatusSummary;
}> {
  try {
    const res = await sidecarFetch(
      "/profile/create",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, pin }),
      },
      25000
    );
    const data = (await res.json()) as {
      ok?: boolean;
      error?: string;
      unlocked?: boolean;
      active_profile_id?: string | null;
      active_profile?: ProfileStatusSummary["active_profile"];
      profiles?: ProfileStatusSummary["profiles"];
    };
    const ok = Boolean(res.ok && data.ok);
    return {
      ok,
      error: data.error,
      profile: ok ? _normalizeProfileSummary(data) : undefined,
    };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarUnlockProfile(
  profileId: string,
  pin: string
): Promise<{
  ok: boolean;
  error?: string;
  profile?: ProfileStatusSummary;
}> {
  try {
    const res = await sidecarFetch(
      "/profile/unlock",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_id: profileId, pin }),
      },
      25000
    );
    const data = (await res.json()) as {
      ok?: boolean;
      error?: string;
      unlocked?: boolean;
      active_profile_id?: string | null;
      active_profile?: ProfileStatusSummary["active_profile"];
      profiles?: ProfileStatusSummary["profiles"];
    };
    const ok = Boolean(res.ok && data.ok);
    return {
      ok,
      error: data.error,
      profile: ok ? _normalizeProfileSummary(data) : undefined,
    };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarUnlockProfileKeychain(
  profileId: string
): Promise<{
  ok: boolean;
  error?: string;
  profile?: ProfileStatusSummary;
}> {
  try {
    const res = await sidecarFetch(
      "/profile/unlock_keychain",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_id: profileId }),
      },
      25000
    );
    const data = (await res.json()) as {
      ok?: boolean;
      error?: string;
      unlocked?: boolean;
      active_profile_id?: string | null;
      active_profile?: ProfileStatusSummary["active_profile"];
      profiles?: ProfileStatusSummary["profiles"];
    };
    const ok = Boolean(res.ok && data.ok);
    return {
      ok,
      error: data.error,
      profile: ok ? _normalizeProfileSummary(data) : undefined,
    };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarLockProfile(): Promise<void> {
  try {
    await sidecarFetch("/profile/lock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
  } catch {
    // Ignore
  }
}

export async function sidecarDeleteProfile(
  profileId: string,
  pin: string
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await sidecarFetch("/profile/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile_id: profileId, pin }),
    });
    const data = (await res.json()) as { ok?: boolean; error?: string };
    return { ok: Boolean(res.ok && data.ok), error: data.error };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarUpsertPassword(payload: {
  service: string;
  username: string;
  password?: string;
  token?: string;
  cookie?: string;
  url?: string;
}): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await sidecarFetch("/passwords/upsert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = (await res.json()) as { ok?: boolean; error?: string };
    return { ok: Boolean(res.ok && data.ok), error: data.error };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarRevealPassword(
  service: string,
  field: string,
  pin: string
): Promise<{ ok: boolean; value?: string; error?: string }> {
  try {
    const res = await sidecarFetch("/passwords/reveal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ service, field, pin }),
    });
    const data = (await res.json()) as {
      ok?: boolean;
      value?: string;
      error?: string;
    };
    return {
      ok: Boolean(res.ok && data.ok),
      value: data.value,
      error: data.error,
    };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarMatchPasswordForUrl(
  targetUrl: string
): Promise<boolean> {
  try {
    const res = await sidecarFetch("/passwords/match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: targetUrl }),
    });
    if (!res.ok) return false;
    const data = (await res.json()) as { credentials?: Record<string, unknown> | null };
    return Boolean(data.credentials);
  } catch {
    return false;
  }
}

export async function sidecarSaveRawEnv(
  rawEnv: string
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await sidecarFetch("/passwords/save_env", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_env: rawEnv }),
    });
    const data = (await res.json()) as { ok?: boolean; error?: string };
    return { ok: Boolean(res.ok && data.ok), error: data.error };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarImportEnvFile(
  path: string
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await sidecarFetch("/passwords/import_env", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const data = (await res.json()) as { ok?: boolean; error?: string };
    return { ok: Boolean(res.ok && data.ok), error: data.error };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarDeletePassword(
  service: string
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await sidecarFetch("/passwords/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ service }),
    });
    const data = (await res.json()) as { ok?: boolean; error?: string };
    return { ok: Boolean(res.ok && data.ok), error: data.error };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarRunAnswer(
  question: string,
  conversationId: string
): Promise<{
  answer: string;
  band: string;
  sources: Array<CitedSourcePreview & { id?: string }>;
  findings?: FindingItem[];
}> {
  const res = await sidecarFetch("/answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session: conversationId }),
  });
  if (!res.ok) {
    throw new Error(`planck3 /answer returned ${res.status}`);
  }
  return await res.json();
}

export async function sidecarRunRead(
  model: LocalModelId,
  question: string,
  sources: Array<{ id: string; url: string; title: string }>
): Promise<{ answer: string; source_ids: string[] }> {
  const res = await sidecarFetch("/read", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      question,
      source_ids: sources.map((s) => s.id),
      sources,
    }),
  });
  if (!res.ok) {
    throw new Error(`/read returned ${res.status}`);
  }
  return await res.json();
}

export async function sidecarSummarizeConversation(
  messages: Array<{ role: string; content: string }>,
  summary?: string
): Promise<string> {
  try {
    const res = await sidecarFetch("/chat/summarize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, summary: summary ?? "" }),
    });
    if (!res.ok) return "";
    const data = (await res.json()) as { summary?: string };
    return String(data.summary ?? "").slice(0, 600);
  } catch {
    return "";
  }
}

export interface OpenTabMeta {
  tab_id: string;
  source_id?: string;
  url: string;
  title: string;
  domain?: string;
  is_active: boolean;
  is_sleeping?: boolean;
}

async function consumeSseStream<T extends Record<string, unknown>>(
  res: Response,
  stallTimeoutMs: number,
  onEvent: (payload: T) => void
): Promise<{ stalled: boolean; streamError?: string }> {
  if (!res.body) {
    throw new Error("Response has no readable stream body");
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let stalled = false;
  let streamError: string | undefined;

  const readChunkWithWatchdog = async (): Promise<ReadableStreamReadResult<Uint8Array>> => {
    let timerId: ReturnType<typeof setTimeout> | null = null;
    try {
      return await Promise.race([
        reader.read(),
        new Promise<never>((_, reject) => {
          timerId = setTimeout(() => {
            reject(new Error("__SATZ_STALL_TIMEOUT__"));
          }, stallTimeoutMs);
        }),
      ]);
    } finally {
      if (timerId !== null) {
        clearTimeout(timerId);
      }
    }
  };

  try {
    while (true) {
      const { value, done } = await readChunkWithWatchdog();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line.startsWith("data:")) continue;
        const jsonStr = line.slice(5).trim();
        if (!jsonStr) continue;
        try {
          const payload = JSON.parse(jsonStr) as T;
          onEvent(payload);
        } catch {
          // Ignore malformed SSE line
        }
      }
    }
  } catch (err) {
    if (err instanceof Error && err.message === "__SATZ_STALL_TIMEOUT__") {
      stalled = true;
      streamError = "model stopped responding after 30 s.";
      try {
        await reader.cancel();
      } catch {
        // Ignore cancel errors
      }
    } else {
      throw err;
    }
  }
  return { stalled, streamError };
}

export async function sidecarStreamChat(
  model: LocalModelId,
  messages: Array<{ role: string; content: string; images?: ChatImageAttachment[] }>,
  sources: Array<{ id: string; url: string; title: string; domain: string; is_open_tab: boolean }>,
  web: boolean,
  onDelta: (delta: string) => void,
  onStatus?: (status: string, phase?: string) => void,
  onError?: (err: string) => void,
  summary?: string,
  onSourceStats?: (stats: SourceStatEntry[]) => void,
  mail?: boolean,
  stallTimeoutMs = 30000,
  conversationId?: string,
  userOverrodeModel = false,
  openTabs?: OpenTabMeta[],
  onTabListUpdated?: () => void,
  origin?: ConversationOrigin,
  stagedFiles?: StagedSettingsFile[],
  drives?: boolean
): Promise<{
  source_ids: string[];
  cited_sources?: CitedSourcePreview[];
  brain_sources?: BrainCitationItem[];
  proposals?: BrainProposalItem[];
  citation_check?: CitationCheckEntry[];
  citations_ok?: number;
  citations_flagged?: number;
  annotated_text?: string;
  source_stats?: SourceStatEntry[];
  findings?: FindingItem[];
  email_cards?: ChatEmailCard[];
  tasks?: AgentTaskCard[];
  ui_cards?: SettingsUiCard[];
  effective_model?: LocalModelId;
  effective_web?: boolean;
  effective_mail?: boolean;
  routing_info?: RoutingDecisionInfo;
  tools_used?: string[];
  tab_list_updated?: boolean;
  error?: string;
  stalled?: boolean;
}> {
  const res = await sidecarFetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      messages,
      sources,
      web,
      mail: Boolean(mail),
      drives: Boolean(drives),
      summary: summary ?? "",
      conversation_id: conversationId ?? "",
      user_overrode_model: Boolean(userOverrodeModel),
      open_tabs: openTabs ?? [],
      origin: origin ?? "chat",
      staged_files: stagedFiles ?? [],
    }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`/chat returned HTTP ${res.status}`);
  }

  let finalSourceIds: string[] = [];
  let citedSources: CitedSourcePreview[] | undefined;
  let brainSources: BrainCitationItem[] | undefined;
  let proposals: BrainProposalItem[] | undefined;
  let citationCheck: CitationCheckEntry[] | undefined;
  let citationsOk: number | undefined;
  let citationsFlagged: number | undefined;
  let annotatedText: string | undefined;
  let sourceStats: SourceStatEntry[] | undefined;
  let findings: FindingItem[] | undefined;
  let emailCards: ChatEmailCard[] | undefined;
  let tasks: AgentTaskCard[] | undefined;
  let uiCards: SettingsUiCard[] | undefined;
  let effectiveModel: LocalModelId | undefined;
  let effectiveWeb: boolean | undefined;
  let effectiveMail: boolean | undefined;
  let routingInfo: RoutingDecisionInfo | undefined;
  let toolsUsed: string[] | undefined;
  let tabListUpdated = false;
  let streamError: string | undefined;

  type ChatSseEvent = {
    delta?: string;
    status?: string;
    phase?: string;
    error?: string;
    done?: boolean;
    source_ids?: string[];
    cited_sources?: CitedSourcePreview[];
    brain_sources?: BrainCitationItem[];
    proposals?: BrainProposalItem[];
    citation_check?: CitationCheckEntry[];
    citations_ok?: number;
    citations_flagged?: number;
    annotated_text?: string;
    source_stats?: SourceStatEntry[];
    findings?: FindingItem[];
    email_cards?: ChatEmailCard[];
    tasks?: AgentTaskCard[];
    ui_cards?: SettingsUiCard[];
    effective_model?: LocalModelId;
    effective_web?: boolean;
    effective_mail?: boolean;
    routing_info?: RoutingDecisionInfo;
    tools_used?: string[];
    tab_list_updated?: boolean;
  };

  const { stalled, streamError: stallErr } = await consumeSseStream<ChatSseEvent>(
    res,
    stallTimeoutMs,
    (payload) => {
      if (payload.phase === "heartbeat") {
        return;
      }
      if (payload.tab_list_updated) {
        tabListUpdated = true;
        if (onTabListUpdated) onTabListUpdated();
      }
      if (payload.brain_sources && Array.isArray(payload.brain_sources)) {
        brainSources = payload.brain_sources;
      }
      if (payload.source_stats && Array.isArray(payload.source_stats)) {
        sourceStats = payload.source_stats;
        if (onSourceStats) onSourceStats(payload.source_stats);
      }
      if (payload.status && onStatus) {
        onStatus(payload.status, payload.phase);
      }
      if (payload.error) {
        streamError = payload.error;
        if (onError) onError(payload.error);
      }
      if (payload.delta) {
        onDelta(payload.delta);
      }
      if (payload.done) {
        finalSourceIds = payload.source_ids ?? [];
        citedSources = payload.cited_sources;
        if (payload.brain_sources) {
          brainSources = payload.brain_sources;
        }
        proposals = payload.proposals;
        citationCheck = payload.citation_check;
        citationsOk = payload.citations_ok;
        citationsFlagged = payload.citations_flagged;
        annotatedText = payload.annotated_text;
        if (payload.source_stats) {
          sourceStats = payload.source_stats;
        }
        if (payload.findings && Array.isArray(payload.findings)) {
          findings = payload.findings;
        }
        if (payload.email_cards && Array.isArray(payload.email_cards)) {
          emailCards = payload.email_cards;
        }
        if (payload.tasks && Array.isArray(payload.tasks)) {
          tasks = payload.tasks;
        }
        if (payload.ui_cards && Array.isArray(payload.ui_cards)) {
          uiCards = payload.ui_cards;
        }
        if (payload.effective_model) {
          effectiveModel = payload.effective_model;
        }
        if (typeof payload.effective_web === "boolean") {
          effectiveWeb = payload.effective_web;
        }
        if (typeof payload.effective_mail === "boolean") {
          effectiveMail = payload.effective_mail;
        }
        if (payload.routing_info) {
          routingInfo = payload.routing_info;
        }
        if (Array.isArray(payload.tools_used)) {
          toolsUsed = payload.tools_used.map((x) => String(x));
        }
      }
    }
  );
  if (stalled) {
    streamError = "gemma stopped responding after 30 s.";
    if (onError) onError(streamError);
  } else if (stallErr && !streamError) {
    streamError = stallErr;
  }

  return {
    source_ids: finalSourceIds,
    cited_sources: citedSources,
    brain_sources: brainSources,
    proposals,
    citation_check: citationCheck,
    citations_ok: citationsOk,
    citations_flagged: citationsFlagged,
    annotated_text: annotatedText,
    source_stats: sourceStats,
    findings,
    email_cards: emailCards,
    tasks,
    ui_cards: uiCards,
    effective_model: effectiveModel,
    effective_web: effectiveWeb,
    effective_mail: effectiveMail,
    routing_info: routingInfo,
    tools_used: toolsUsed,
    tab_list_updated: tabListUpdated,
    error: streamError,
    stalled,
  };
}

export async function sidecarGetMailAccounts(): Promise<{
  unlocked: boolean;
  accounts: MailAccountItem[];
  presets: MailPreset[];
  settings?: Record<string, unknown>;
}> {
  try {
    const res = await sidecarFetch("/mail/accounts");
    if (!res.ok) {
      return { unlocked: false, accounts: [], presets: [] };
    }
    return await res.json();
  } catch {
    return { unlocked: false, accounts: [], presets: [] };
  }
}

export async function sidecarTestMailAccount(
  payload: Record<string, unknown>
): Promise<{ ok: boolean; error?: string; stage?: string }> {
  try {
    const res = await sidecarFetch("/mail/accounts/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarAddMailAccount(
  payload: Record<string, unknown>
): Promise<{
  ok: boolean;
  account_id?: string;
  vault_prefix?: string;
  accounts?: MailAccountItem[];
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/mail/accounts/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarRemoveMailAccount(
  accountId: string
): Promise<{
  ok: boolean;
  accounts?: MailAccountItem[];
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/mail/accounts/remove", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_id: accountId }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarSyncMail(
  accountId?: string
): Promise<{ ok: boolean; synced_count?: number; error?: string }> {
  try {
    const res = await sidecarFetch("/mail/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(accountId ? { account_id: accountId } : {}),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarGetMailLane(
  name: "inbox" | "pings" | "orders" | "promos" = "inbox",
  cursor = 0,
  accountId?: string | null
): Promise<MailLaneResponse> {
  try {
    const acctParam =
      accountId && accountId !== "all"
        ? `&account_id=${encodeURIComponent(accountId)}`
        : "";
    const res = await sidecarFetch(
      `/mail/lane?name=${encodeURIComponent(name)}&cursor=${cursor}${acctParam}`
    );
    if (!res.ok) {
      return {
        unlocked: false,
        lane: name,
        rows: [],
        counts: { inbox_unread: 0, pings: 0, orders: 0, promos: 0 },
      };
    }
    return await res.json();
  } catch {
    return {
      unlocked: false,
      lane: name,
      rows: [],
      counts: { inbox_unread: 0, pings: 0, orders: 0, promos: 0 },
    };
  }
}

export async function sidecarGetMailStatus(): Promise<MailStatusSummary> {
  try {
    const res = await sidecarFetch("/mail/status");
    if (!res.ok) {
      return {
        unlocked: false,
        accounts_count: 0,
        inbox_unread: 0,
        processing_done: 0,
        processing_total: 0,
        model_version: "cold",
      };
    }
    return await res.json();
  } catch {
    return {
      unlocked: false,
      accounts_count: 0,
      inbox_unread: 0,
      processing_done: 0,
      processing_total: 0,
      model_version: "cold",
    };
  }
}

export async function sidecarGetMailMessage(
  messageId: string
): Promise<Record<string, unknown>> {
  try {
    const res = await sidecarFetch(
      `/mail/message/${encodeURIComponent(messageId)}`
    );
    if (!res.ok) return { ok: false };
    return await res.json();
  } catch {
    return { ok: false };
  }
}

export async function sidecarGetMailMessageHtml(
  messageId: string
): Promise<{
  ok: boolean;
  html?: string;
  csp?: string;
  translated_html?: string;
  translation_source_lang?: string;
  translation_target_lang?: string;
}> {
  try {
    const res = await sidecarFetch(
      `/mail/message/${encodeURIComponent(messageId)}/html`
    );
    if (!res.ok) return { ok: false };
    return await res.json();
  } catch {
    return { ok: false };
  }
}

export async function sidecarOpenMailMessage(
  messageId: string
): Promise<Record<string, unknown>> {
  try {
    const res = await sidecarFetch(
      `/mail/message/${encodeURIComponent(messageId)}/open`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      }
    );
    return await res.json();
  } catch {
    return { ok: false };
  }
}

export async function sidecarLabelMailMessage(
  messageId: string,
  label: "email" | "ping" | "information" | "promotion"
): Promise<Record<string, unknown>> {
  try {
    const res = await sidecarFetch(
      `/mail/message/${encodeURIComponent(messageId)}/label`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label }),
      }
    );
    return await res.json();
  } catch {
    return { ok: false };
  }
}

export async function sidecarHideMailMessage(
  messageId: string
): Promise<Record<string, unknown>> {
  try {
    const res = await sidecarFetch(
      `/mail/message/${encodeURIComponent(messageId)}/hide`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      }
    );
    return await res.json();
  } catch {
    return { ok: false };
  }
}

export async function sidecarSaveMailAttachment(
  messageId: string,
  partId: string
): Promise<{ ok: boolean; saved_to?: string; filename?: string; error?: string }> {
  try {
    const res = await sidecarFetch(
      `/mail/message/${encodeURIComponent(messageId)}/attachment`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ part_id: partId }),
      }
    );
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarSearchMail(
  query: string,
  accountId?: string | null
): Promise<{ ok: boolean; rows: Array<Record<string, unknown>> }> {
  try {
    const acctParam =
      accountId && accountId !== "all"
        ? `&account_id=${encodeURIComponent(accountId)}`
        : "";
    const res = await sidecarFetch(
      `/mail/search?q=${encodeURIComponent(query)}${acctParam}`
    );
    if (!res.ok) return { ok: false, rows: [] };
    return await res.json();
  } catch {
    return { ok: false, rows: [] };
  }
}

export async function sidecarUpdateMailSettings(
  payload: Record<string, unknown>
): Promise<Record<string, unknown>> {
  try {
    const res = await sidecarFetch("/mail/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch {
    return { ok: false };
  }
}

export async function sidecarDraftMailReply(
  payload: Record<string, unknown>
): Promise<{
  ok: boolean;
  draft_id?: string;
  to?: string;
  cc?: string;
  subject?: string;
  body?: string;
  model?: string;
  style_applied?: boolean;
  style_rules_summary?: string;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/mail/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarPrepareMailSend(
  payload: Record<string, unknown>
): Promise<{
  ok: boolean;
  outbox_id?: string;
  confirm_token?: string;
  confirm_line?: string;
  new_recipients?: string[];
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/mail/send/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarConfirmMailSend(
  outboxId: string,
  confirmToken: string
): Promise<{
  ok: boolean;
  outbox_id?: string;
  status?: string;
  undo_window_seconds?: number;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/mail/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ outbox_id: outboxId, confirm_token: confirmToken }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarUndoMailSend(
  outboxId: string
): Promise<{ ok: boolean; undone?: boolean; error?: string }> {
  try {
    const res = await sidecarFetch("/mail/send/undo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ outbox_id: outboxId }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarGetMailTriage(
  accountId?: string | null
): Promise<{
  ok: boolean;
  unlocked?: boolean;
  overview?: string;
  sources?: Array<{
    id: string;
    url: string;
    title: string;
    domain: string;
    is_open_tab: boolean;
  }>;
  emails_needing_attention?: Array<Record<string, unknown>>;
  order_updates?: Array<Record<string, unknown>>;
  expiring_promos?: Array<Record<string, unknown>>;
}> {
  try {
    const acctParam =
      accountId && accountId !== "all"
        ? `?account_id=${encodeURIComponent(accountId)}`
        : "";
    const res = await sidecarFetch(`/mail/triage${acctParam}`);
    if (!res.ok) return { ok: false };
    return await res.json();
  } catch {
    return { ok: false };
  }
}

export async function sidecarGetMailCodes(
  domain: string
): Promise<Array<Record<string, unknown>>> {
  try {
    const res = await sidecarFetch(
      `/mail/codes?domain=${encodeURIComponent(domain)}`
    );
    if (!res.ok) return [];
    const data = (await res.json()) as {
      ok?: boolean;
      codes?: Array<Record<string, unknown>>;
    };
    return data.codes ?? [];
  } catch {
    return [];
  }
}

export async function sidecarGetMailEval(limit = 200): Promise<{
  ok: boolean;
  total_sampled?: number;
  labelled_count?: number;
  items?: Array<Record<string, unknown>>;
}> {
  try {
    const res = await sidecarFetch(`/mail/eval?limit=${limit}`);
    if (!res.ok) return { ok: false, items: [] };
    return await res.json();
  } catch {
    return { ok: false, items: [] };
  }
}

export async function sidecarLabelMailEval(
  messageId: string,
  label: "email" | "ping" | "information" | "promotion",
  extractOk?: boolean | null
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await sidecarFetch("/mail/eval/label", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message_id: messageId,
        label,
        extract_ok: extractOk,
      }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarGetMailEvalReport(): Promise<Record<string, unknown>> {
  try {
    const res = await sidecarFetch("/mail/eval/report");
    if (!res.ok) return { ok: false };
    return await res.json();
  } catch {
    return { ok: false };
  }
}

export async function sidecarListTasks(
  conversationId?: string
): Promise<AgentTaskCard[]> {
  try {
    const q = conversationId
      ? `?conversation_id=${encodeURIComponent(conversationId)}`
      : "";
    const res = await sidecarFetch(`/tasks${q}`);
    if (!res.ok) return [];
    const data = (await res.json()) as { tasks?: AgentTaskCard[] };
    return Array.isArray(data.tasks) ? data.tasks : [];
  } catch {
    return [];
  }
}

export async function sidecarStopTask(
  taskId: string,
  stopToken: string
): Promise<{ ok: boolean; task?: AgentTaskCard; error?: string }> {
  try {
    const res = await sidecarFetch("/task/stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: taskId, stop_token: stopToken }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarConfirmTaskStep(
  taskId: string,
  stepId: string,
  confirmToken: string
): Promise<{ ok: boolean; task?: AgentTaskCard; error?: string }> {
  try {
    const res = await sidecarFetch("/task/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task_id: taskId,
        step_id: stepId,
        confirm_token: confirmToken,
      }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarCancelTaskStep(
  taskId: string,
  stepId: string
): Promise<{ ok: boolean; task?: AgentTaskCard; error?: string }> {
  try {
    const res = await sidecarFetch("/task/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: taskId, step_id: stepId }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarAppendTaskStep(
  taskId: string,
  text: string,
  kind = "log"
): Promise<{ ok: boolean; task?: AgentTaskCard; error?: string }> {
  try {
    const res = await sidecarFetch("/task/step", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: taskId, text, kind }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarCompleteTask(
  taskId: string,
  resultMd: string,
  stepText?: string
): Promise<{ ok: boolean; task?: AgentTaskCard; error?: string }> {
  try {
    const res = await sidecarFetch("/task/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task_id: taskId,
        result_md: resultMd,
        step_text: stepText ?? "",
      }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarPrepareUnsubscribeTask(params: {
  conversation_id: string;
  message_id?: string;
  query?: string;
  sender?: string;
}): Promise<{
  ok: boolean;
  task?: AgentTaskCard;
  preferred_method?: string;
  summary?: string;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/actor/unsubscribe/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarExecuteMailUnsubscribe(params: {
  message_id?: string;
  url?: string;
  method_type?: string;
  task_id?: string;
  step_id?: string;
  archive_sender?: boolean;
  confirm_explicit?: boolean;
}): Promise<{
  ok: boolean;
  executed?: boolean;
  needs_browser_actor?: boolean;
  method?: string;
  url?: string;
  label?: string;
  http_status?: number;
  sent_to?: string;
  from_addr?: string;
  subject?: string;
  excerpt?: string;
  post_error?: string;
  fallback_mailto?: Record<string, unknown> | null;
  task?: AgentTaskCard;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/mail/unsubscribe/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarHideMailSender(
  sender: string,
  taskId?: string
): Promise<{
  ok: boolean;
  sender?: string;
  hidden_count?: number;
  task?: AgentTaskCard;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/mail/sender/hide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sender, task_id: taskId ?? "" }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarRunComparer(
  conversationId: string,
  sources: Array<{
    id?: string;
    url: string;
    title?: string;
    domain?: string;
    text?: string;
  }>,
  goal = "compare these",
  taskId?: string,
  stepId?: string
): Promise<{
  ok: boolean;
  task?: AgentTaskCard;
  table_md?: string;
  uncited_cells?: number;
  source_ids?: string[];
  cited_sources?: Array<{ url: string; title: string; domain?: string }>;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/agent/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: conversationId,
        sources,
        goal,
        task_id: taskId ?? "",
        step_id: stepId ?? "",
      }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarAddWatch(payload: {
  conversation_id: string;
  query_or_url: string;
  cadence_seconds?: number;
  condition?: string;
  title?: string;
  initial_value?: string;
  task_id?: string;
  step_id?: string;
}): Promise<{ ok: boolean; watch?: WatchItem; task?: AgentTaskCard; error?: string }> {
  try {
    const res = await sidecarFetch("/watch/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarListWatches(
  conversationId?: string
): Promise<{ watches: WatchItem[]; watch_badges: string[] }> {
  try {
    const q = conversationId
      ? `?conversation_id=${encodeURIComponent(conversationId)}`
      : "";
    const res = await sidecarFetch(`/watches${q}`);
    if (!res.ok) return { watches: [], watch_badges: [] };
    const data = (await res.json()) as {
      watches?: WatchItem[];
      watch_badges?: string[];
    };
    return {
      watches: Array.isArray(data.watches) ? data.watches : [],
      watch_badges: Array.isArray(data.watch_badges) ? data.watch_badges : [],
    };
  } catch {
    return { watches: [], watch_badges: [] };
  }
}

export async function sidecarDeleteWatch(
  watchId: string
): Promise<{ ok: boolean }> {
  try {
    const res = await sidecarFetch("/watch/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ watch_id: watchId }),
    });
    return await res.json();
  } catch {
    return { ok: false };
  }
}

export async function sidecarAckWatchBadge(
  conversationId: string
): Promise<{ ok: boolean; watch_badges?: string[] }> {
  try {
    const res = await sidecarFetch("/watch/ack", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId }),
    });
    return await res.json();
  } catch {
    return { ok: false };
  }
}

export async function sidecarCheckWatches(
  force = true
): Promise<{
  ok: boolean;
  checked?: number;
  triggered?: number;
  watch_badges?: string[];
}> {
  try {
    const res = await sidecarFetch("/watch/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force }),
    });
    return await res.json();
  } catch {
    return { ok: false };
  }
}

export async function sidecarGetMailAttachmentData(
  messageId: string,
  partId: string
): Promise<{
  ok: boolean;
  filename?: string;
  mime?: string;
  size?: number;
  data_url?: string;
  saved_path?: string;
  error?: string;
}> {
  try {
    const res = await sidecarFetch(
      `/mail/message/${encodeURIComponent(messageId)}/attachment?part_id=${encodeURIComponent(partId)}`
    );
    if (!res.ok) return { ok: false };
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarFetchConversationPreviews(
  conversationId: string
): Promise<
  Record<
    string,
    {
      url: string;
      domain: string;
      title: string;
      findings: FindingItem[];
    }
  >
> {
  try {
    const res = await sidecarFetch(
      `/sources/previews?conversation_id=${encodeURIComponent(conversationId)}`
    );
    if (!res.ok) return {};
    const data = (await res.json()) as {
      ok?: boolean;
      by_source?: Record<
        string,
        {
          url: string;
          domain: string;
          title: string;
          findings: FindingItem[];
        }
      >;
    };
    return data.by_source ?? {};
  } catch {
    return {};
  }
}

export async function sidecarGetModelConfig(): Promise<ModelManagementConfig | null> {
  try {
    const res = await sidecarFetch("/models/config");
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function sidecarUpdateModelConfig(
  payload: Record<string, unknown>
): Promise<ModelManagementConfig> {
  try {
    const res = await sidecarFetch("/models/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return {
      ok: false,
      roles: {
        chat: "gemma-4-e4b",
        web_answer: "planck3 (web)",
        reader: "hertz (reader)",
        news_planner: "gemma-4-e4b",
        news_capture: "gemma-4-e4b",
        news_reader: "hertz (reader)",
        news_analyzer: "gemma-4-e4b",
        mail_classifier: "local",
        brain_encoder: "planck13 (local)",
      },
      cloud_providers: [],
      error: String(e),
    };
  }
}

export async function sidecarFetchNewsStories(
  lane: string = "top",
  topic: string = "",
  explore: boolean = false,
  limit: number = 30
): Promise<{
  ok: boolean;
  lane: string;
  explore: boolean;
  total: number;
  stories: NewsStoryCluster[];
}> {
  try {
    const qs = new URLSearchParams({
      lane,
      topic,
      explore: explore ? "1" : "0",
      limit: String(limit),
    });
    const res = await sidecarFetch(`/news/stories?${qs.toString()}`);
    if (!res.ok) return { ok: false, lane, explore, total: 0, stories: [] };
    return await res.json();
  } catch {
    return { ok: false, lane, explore, total: 0, stories: [] };
  }
}

export async function sidecarRefreshNews(
  force: boolean = true,
  includeSearch: boolean = false,
  processBrain: boolean = true
): Promise<{
  ok: boolean;
  fetched_feeds?: number;
  not_modified?: number;
  articles_ingested?: number;
  clusters?: number;
  brain_synced?: number;
  last_sync_at?: number;
  errors?: string[];
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/news/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force, include_search: includeSearch, process_brain: processBrain }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarSyncNewsBrain(
  limit: number = 12,
  force: boolean = false
): Promise<{
  ok: boolean;
  processed?: number;
  updated?: number;
  total_synced?: number;
  skipped_locked?: boolean;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/news/sync_brain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit, force }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarFetchNewsPerspectives(
  clusterId: string,
  refresh: boolean = false
): Promise<NewsPerspectiveMatrix | null> {
  try {
    const qs = new URLSearchParams({
      cluster_id: clusterId,
      refresh: refresh ? "1" : "0",
    });
    const res = await sidecarFetch(`/news/perspectives?${qs.toString()}`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function sidecarNewsChatAnswer(
  question: string,
  sources?: Array<{ id: string; url: string; title: string; domain: string }>,
  roles?: Record<string, string>
): Promise<{
  ok: boolean;
  answer: string;
  model: string;
  sources: CitedSourcePreview[];
  source_stats?: SourceStatEntry[];
  findings: FindingItem[];
  answer_meta?: AnswerMeta;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/news/chat_answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, sources, roles }),
    });
    return await res.json();
  } catch (e) {
    return {
      ok: false,
      answer: `[error: ${e}]`,
      model: "error",
      sources: [],
      findings: [],
      error: String(e),
    };
  }
}

export async function sidecarEnrichUrlPreviews(
  items: Array<{ url: string; title?: string; domain?: string; snippet?: string; image_url?: string }>,
  fetchMissing = true
): Promise<Record<string, CitedSourcePreview>> {
  try {
    const res = await sidecarFetch("/sources/enrich_previews", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items, fetch_missing: fetchMissing }),
    });
    if (!res.ok) return {};
    const data = (await res.json()) as {
      ok?: boolean;
      previews?: Record<string, CitedSourcePreview>;
    };
    return data.previews ?? {};
  } catch {
    return {};
  }
}

export interface NewsSseCallbacks {
  onDelta: (delta: string) => void;
  onReplaceText?: (text: string) => void;
  onStatus?: (status: string, phase?: string) => void;
  onSourceStats?: (stats: SourceStatEntry[]) => void;
}

export interface NewsSseResult {
  ok: boolean;
  topic?: string;
  cluster_id?: string;
  answer: string;
  annotated_text?: string;
  model: string;
  sources: CitedSourcePreview[];
  source_stats?: SourceStatEntry[];
  findings: FindingItem[];
  answer_meta?: AnswerMeta;
  blind_spots?: string[];
  system_counterfactual?: string;
  error?: string;
  stalled?: boolean;
}

async function consumeNewsStreamResponse(
  res: Response,
  callbacks: NewsSseCallbacks,
  stallTimeoutMs: number,
  timeoutMessage: string
): Promise<NewsSseResult> {
  let ok = false;
  let topic: string | undefined;
  let clusterId: string | undefined;
  let answer = "";
  let annotatedText: string | undefined;
  let model = "template";
  let finalSources: CitedSourcePreview[] = [];
  let sourceStats: SourceStatEntry[] | undefined;
  let findings: FindingItem[] = [];
  let answerMeta: AnswerMeta | undefined;
  let blindSpots: string[] | undefined;
  let systemCounterfactual: string | undefined;
  let streamError: string | undefined;

  type NewsSseEvent = {
    delta?: string;
    replace_text?: string;
    status?: string;
    phase?: string;
    error?: string;
    done?: boolean;
    ok?: boolean;
    topic?: string;
    cluster_id?: string;
    answer?: string;
    annotated_text?: string;
    model?: string;
    sources?: CitedSourcePreview[];
    source_stats?: SourceStatEntry[];
    findings?: FindingItem[];
    answer_meta?: AnswerMeta;
    blind_spots?: string[];
    system_counterfactual?: string;
  };

  const { stalled, streamError: stallErr } = await consumeSseStream<NewsSseEvent>(
    res,
    stallTimeoutMs,
    (payload) => {
      if (payload.phase === "heartbeat") return;
      if (payload.status && callbacks.onStatus) {
        callbacks.onStatus(payload.status, payload.phase);
      }
      if (Array.isArray(payload.source_stats)) {
        sourceStats = payload.source_stats;
        callbacks.onSourceStats?.(payload.source_stats);
      }
      if (Array.isArray(payload.sources) && !payload.done) {
        finalSources = payload.sources;
      }
      if (payload.error) {
        streamError = payload.error;
      }
      if (typeof payload.replace_text === "string") {
        callbacks.onReplaceText?.(payload.replace_text);
      }
      if (payload.delta) {
        callbacks.onDelta(payload.delta);
      }
      if (payload.done) {
        ok = Boolean(payload.ok);
        if (typeof payload.topic === "string") topic = payload.topic;
        if (typeof payload.cluster_id === "string") clusterId = payload.cluster_id;
        answer = String(payload.answer ?? "");
        annotatedText = payload.annotated_text;
        model = String(payload.model ?? model);
        if (Array.isArray(payload.sources)) finalSources = payload.sources;
        if (Array.isArray(payload.findings)) findings = payload.findings;
        if (Array.isArray(payload.source_stats)) sourceStats = payload.source_stats;
        if (payload.answer_meta) answerMeta = payload.answer_meta;
        if (Array.isArray(payload.blind_spots)) blindSpots = payload.blind_spots;
        if (typeof payload.system_counterfactual === "string") {
          systemCounterfactual = payload.system_counterfactual;
        }
      }
    }
  );

  if (stalled) {
    return {
      ok: false,
      topic,
      cluster_id: clusterId,
      answer: streamError || stallErr || timeoutMessage,
      model: "error",
      sources: finalSources,
      source_stats: sourceStats,
      findings,
      answer_meta: answerMeta,
      blind_spots: blindSpots,
      system_counterfactual: systemCounterfactual,
      error: stallErr,
      stalled: true,
    };
  }

  return {
    ok: streamError ? false : ok,
    topic,
    cluster_id: clusterId,
    answer,
    annotated_text: annotatedText,
    model,
    sources: finalSources,
    source_stats: sourceStats,
    findings,
    answer_meta: answerMeta,
    blind_spots: blindSpots,
    system_counterfactual: systemCounterfactual,
    error: streamError,
  };
}

export async function sidecarStreamNewsChat(
  question: string,
  sources: Array<{ id: string; url: string; title: string; domain: string }>,
  roles: Record<string, string> | undefined,
  callbacks: NewsSseCallbacks,
  stallTimeoutMs = 30000
): Promise<NewsSseResult> {
  try {
    const res = await sidecarFetch("/news/chat_answer_stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, sources, roles }),
    });
    if (res.status === 404) {
      return await sidecarNewsChatAnswer(question, sources, roles);
    }
    if (!res.ok || !res.body) {
      throw new Error(`/news/chat_answer_stream returned HTTP ${res.status}`);
    }
    return await consumeNewsStreamResponse(
      res,
      callbacks,
      stallTimeoutMs,
      "News request timed out after 30 s."
    );
  } catch (e) {
    return {
      ok: false,
      answer: `[error: ${e}]`,
      model: "error",
      sources: [],
      findings: [],
      error: String(e),
    };
  }
}

export async function sidecarStreamNewsPerspectives(
  topic: string,
  callbacks: NewsSseCallbacks,
  opts?: {
    clusterId?: string;
    roles?: Record<string, string>;
    messages?: Array<{ role: string; content: string }>;
    stallTimeoutMs?: number;
  }
): Promise<NewsSseResult> {
  const stallTimeoutMs = opts?.stallTimeoutMs ?? 45000;
  try {
    const res = await sidecarFetch("/news/perspectives_stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic,
        cluster_id: opts?.clusterId ?? "",
        roles: opts?.roles,
        messages: opts?.messages ?? [],
      }),
    });
    if (!res.ok || !res.body) {
      throw new Error(`/news/perspectives_stream returned HTTP ${res.status}`);
    }
    return await consumeNewsStreamResponse(
      res,
      callbacks,
      stallTimeoutMs,
      "Perspectives request timed out after 45 s."
    );
  } catch (e) {
    return {
      ok: false,
      answer: `[error: ${e}]`,
      model: "error",
      sources: [],
      findings: [],
      error: String(e),
    };
  }
}

export async function sidecarReweighNewsMeta(
  answerMeta: AnswerMeta
): Promise<AnswerMeta | null> {
  try {
    const res = await sidecarFetch("/news/reweigh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer_meta: answerMeta }),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { ok?: boolean; answer_meta?: AnswerMeta };
    return data.answer_meta ?? null;
  } catch {
    return null;
  }
}

export async function sidecarTranslateNewsArticle(
  articleId: string,
  targetLang: string = "en"
): Promise<{
  ok: boolean;
  article_id?: string;
  language?: string;
  target_lang?: string;
  title_tr?: string;
  snippet_tr?: string;
  translated_text?: string;
  original_text?: string;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/news/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ article_id: articleId, target_lang: targetLang }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarFetchNewsSources(opts?: {
  q?: string;
  category?: string;
  band?: string;
  conflicted?: boolean;
  withRss?: boolean;
}): Promise<{
  ok: boolean;
  as_of: string;
  categories: NewsCategoryEntry[];
  total: number;
  sources: NewsSourceEntry[];
}> {
  try {
    const qs = new URLSearchParams({
      q: opts?.q ?? "",
      category: opts?.category ?? "",
      band: opts?.band ?? "",
      conflicted: opts?.conflicted ? "1" : "0",
      with_rss: opts?.withRss ? "1" : "0",
    });
    const res = await sidecarFetch(`/news/sources?${qs.toString()}`);
    if (!res.ok) return { ok: false, as_of: "", categories: [], total: 0, sources: [] };
    return await res.json();
  } catch {
    return { ok: false, as_of: "", categories: [], total: 0, sources: [] };
  }
}

export async function sidecarManageNewsFeed(
  payload: Record<string, unknown>
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await sidecarFetch("/news/sources/feed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarFetchNewsTopics(): Promise<{
  ok: boolean;
  topics: NewsTopicItem[];
}> {
  try {
    const res = await sidecarFetch("/news/topics");
    if (!res.ok) return { ok: false, topics: [] };
    return await res.json();
  } catch {
    return { ok: false, topics: [] };
  }
}

export async function sidecarManageNewsTopic(
  payload: Record<string, unknown>
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await sidecarFetch("/news/topics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarSaveNewsClusterToBrain(
  clusterId: string
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await sidecarFetch("/news/save_to_brain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cluster_id: clusterId }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export interface NewsSettingsOnboardResponse {
  ok: boolean;
  needs_onboarding: boolean;
  topics_count: number;
  enabled_feeds_count: number;
  personal_overrides_count: number;
  prompt_text: string;
  ui_cards: SettingsUiCard[];
  error?: string;
}

export async function sidecarFetchNewsSettingsOnboard(): Promise<NewsSettingsOnboardResponse> {
  try {
    const res = await sidecarFetch("/news/settings/onboard");
    if (!res.ok) {
      return {
        ok: false,
        needs_onboarding: false,
        topics_count: 0,
        enabled_feeds_count: 0,
        personal_overrides_count: 0,
        prompt_text: "",
        ui_cards: [],
        error: `HTTP ${res.status}`,
      };
    }
    return await res.json();
  } catch (e) {
    return {
      ok: false,
      needs_onboarding: false,
      topics_count: 0,
      enabled_feeds_count: 0,
      personal_overrides_count: 0,
      prompt_text: "",
      ui_cards: [],
      error: String(e),
    };
  }
}

export async function sidecarHideNewsCluster(clusterId: string): Promise<boolean> {
  try {
    const res = await sidecarFetch("/news/cluster/hide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cluster_id: clusterId }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function sidecarMineSkillProposals(): Promise<{
  ok: boolean;
  proposals: SkillProposalItem[];
  newly_mined?: SkillProposalItem[];
}> {
  try {
    const res = await sidecarFetch("/skills/mine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    return {
      ok: Boolean(res.ok && data.ok),
      proposals: data.proposals ?? [],
      newly_mined: data.newly_mined ?? [],
    };
  } catch {
    return { ok: false, proposals: [] };
  }
}

export async function sidecarAcceptSkillProposal(
  proposalId: string
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await sidecarFetch("/skills/proposals/accept", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proposal_id: proposalId }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarRejectSkillProposal(
  proposalId: string
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await sidecarFetch("/skills/proposals/reject", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proposal_id: proposalId }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarSaveAsSkill(payload: {
  conversation_id?: string;
  task_id?: string;
  name?: string;
  user_prompt?: string;
  assistant_text?: string;
  sources?: Array<Record<string, unknown>>;
}): Promise<{ ok: boolean; skill?: Record<string, unknown>; error?: string }> {
  try {
    const res = await sidecarFetch("/skills/save_from_turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarRunSkill(
  slug: string,
  conversationId: string
): Promise<{
  ok: boolean;
  status?: string;
  task?: AgentTaskCard;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/skills/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug, conversation_id: conversationId }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarContinueSkill(
  taskId: string,
  stepId: string,
  confirmToken?: string
): Promise<{
  ok: boolean;
  status?: string;
  task?: AgentTaskCard;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/skills/continue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task_id: taskId,
        step_id: stepId,
        confirm_token: confirmToken ?? "",
      }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarLookupDomainRecipe(
  domainOrUrl: string,
  controlKey = ""
): Promise<DomainRecipeItem | null> {
  try {
    const qs = new URLSearchParams({ domain: domainOrUrl, control_key: controlKey, limit: "1" });
    const res = await sidecarFetch(`/recipes?${qs.toString()}`);
    if (!res.ok) return null;
    const data = (await res.json()) as { ok?: boolean; recipes?: DomainRecipeItem[] };
    return data.recipes && data.recipes.length > 0 ? data.recipes[0] : null;
  } catch {
    return null;
  }
}

export async function sidecarRecordDomainRecipe(payload: {
  domain: string;
  control_key: string;
  selector: string;
  label?: string;
  action_kind?: string;
  sample_url?: string;
}): Promise<void> {
  try {
    await sidecarFetch("/recipes/record", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    // Non-critical recipe telemetry
  }
}

export async function sidecarLogBehaviorEvent(payload: {
  event_type: string;
  domain?: string;
  url?: string;
  query?: string;
  metadata?: Record<string, unknown>;
}): Promise<void> {
  try {
    await sidecarFetch("/behavior/log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    // Best-effort behavior trace
  }
}

export async function sidecarCaptureFailureEval(payload: {
  user_msg: string;
  bad_assistant_answer: string;
  sources?: Array<Record<string, unknown>>;
  prior_messages?: Array<{ role: string; content: string }>;
  model_id?: string;
  web_enabled?: boolean;
  mail_enabled?: boolean;
  tools_used?: string[];
  citation_check?: Array<Record<string, unknown>>;
  tasks?: AgentTaskCard[];
  expected?: Record<string, unknown>;
  title?: string;
  notes?: string;
}): Promise<{ ok: boolean; eval_case?: EvalCaseItem; error?: string }> {
  try {
    const res = await sidecarFetch("/evals/capture", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarRunEvals(payload?: {
  eval_id?: string;
  targets?: string[];
  mode?: string;
}): Promise<EvalSuiteRunSummary & { error?: string }> {
  try {
    const res = await sidecarFetch(
      "/evals/run",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload ?? {}),
      },
      payload?.mode === "live" ? 180000 : 60000
    );
    return await res.json();
  } catch (e) {
    return { ok: false, total: 0, passed: 0, failed: 0, results: [], error: String(e) };
  }
}

export async function sidecarDeleteEval(evalId: string): Promise<boolean> {
  try {
    const res = await sidecarFetch("/evals/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ eval_id: evalId }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function sidecarRunSkillRedteam(payload?: {
  slug?: string;
  proposal_id?: string;
}): Promise<{
  ok: boolean;
  passed?: boolean;
  audited_count?: number;
  passed_count?: number;
  failed_count?: number;
  summary?: string;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/skills/redteam", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ?? {}),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarFetchGoogleOAuthStatus(
  sessionId?: string
): Promise<GoogleOAuthStatus | null> {
  try {
    const qs = sessionId
      ? `?session_id=${encodeURIComponent(sessionId)}`
      : "";
    const res = await sidecarFetch(`/oauth/google/status${qs}`);
    if (!res.ok) return null;
    return (await res.json()) as GoogleOAuthStatus;
  } catch {
    return null;
  }
}

export async function sidecarSaveGoogleOAuthConfig(payload: {
  client_id?: string;
  client_secret?: string;
  client_secret_json?: string;
  scopes?: string[] | string;
  redirect_port?: number;
}): Promise<GoogleOAuthStatus> {
  try {
    const res = await sidecarFetch("/oauth/google/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return (await res.json()) as GoogleOAuthStatus;
  } catch (e) {
    return {
      ok: false,
      unlocked: false,
      configured: false,
      signed_in: false,
      has_client_id: false,
      has_client_secret: false,
      has_refresh_token: false,
      masked_client_id: "",
      email: "",
      name: "",
      scopes: [],
      expires_at: 0,
      redirect_port: 0,
      error: String(e),
    };
  }
}

export async function sidecarStartGoogleOAuthLogin(payload: {
  client_id?: string;
  client_secret?: string;
  client_secret_json?: string;
  scopes?: string[] | string;
  connect_gmail?: boolean;
  redirect_port?: number;
}): Promise<{
  ok: boolean;
  session_id?: string;
  auth_url?: string;
  redirect_uri?: string;
  scopes?: string[];
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/oauth/google/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarRefreshGoogleOAuth(): Promise<GoogleOAuthStatus | null> {
  try {
    const res = await sidecarFetch("/oauth/google/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    return (await res.json()) as GoogleOAuthStatus;
  } catch {
    return null;
  }
}

export async function sidecarDisconnectGoogleOAuth(
  clearClientConfig: boolean = false
): Promise<GoogleOAuthStatus | null> {
  try {
    const res = await sidecarFetch("/oauth/google/disconnect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clear_client_config: clearClientConfig }),
    });
    return (await res.json()) as GoogleOAuthStatus;
  } catch {
    return null;
  }
}

export async function sidecarConnectGmailOAuth(payload?: {
  email?: string;
  label?: string;
  sync_days?: number;
}): Promise<{ ok: boolean; account_id?: string; error?: string }> {
  try {
    const res = await sidecarFetch("/oauth/google/connect_gmail", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ?? {}),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarFetchRoutingPolicy(): Promise<RoutingPolicySummary | null> {
  try {
    const res = await sidecarFetch("/routing/policy");
    if (!res.ok) return null;
    return (await res.json()) as RoutingPolicySummary;
  } catch {
    return null;
  }
}

export async function sidecarRecordHarnessSignal(
  payload: HarnessSignalPayload
): Promise<{ ok: boolean; policy?: RoutingPolicySummary }> {
  try {
    const res = await sidecarFetch("/telemetry/signal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch {
    return { ok: false };
  }
}

export async function sidecarResetRoutingTelemetry(
  queryType?: string
): Promise<{ ok: boolean; deleted?: number; policy?: RoutingPolicySummary }> {
  try {
    const res = await sidecarFetch("/telemetry/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query_type: queryType ?? "" }),
    });
    return await res.json();
  } catch {
    return { ok: false };
  }
}

export async function sidecarGetMailStyle(): Promise<{
  ok: boolean;
  diff_count: number;
  min_samples: number;
  samples_until_distill: number;
  has_note: boolean;
  note_path?: string;
  note_summary?: string;
  rules?: string[];
}> {
  try {
    const res = await sidecarFetch("/mail/style");
    return await res.json();
  } catch {
    return { ok: false, diff_count: 0, min_samples: 10, samples_until_distill: 10, has_note: false };
  }
}

export async function sidecarDistillMailStyle(
  force = true
): Promise<{ ok: boolean; distilled?: boolean; reason?: string; diff_count?: number }> {
  try {
    const res = await sidecarFetch("/mail/style/distill", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, reason: String(e) };
  }
}

export async function sidecarGetProviders(): Promise<ProviderRegistryState | null> {
  try {
    const res = await sidecarFetch("/providers");
    if (!res.ok) return null;
    return (await res.json()) as ProviderRegistryState;
  } catch {
    return null;
  }
}

export async function sidecarInferProvider(
  input: string,
  categoryId = ""
): Promise<{
  ok: boolean;
  provider_slug?: string;
  display_name?: string;
  domains?: string[];
  url_template?: string;
  mode?: "search_api" | "web_account";
  api_driver?: string;
  vault_service?: string;
  suggested_category_id?: string;
  auth_status?: string;
  masked_auth_label?: string;
  auth_ready?: boolean;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/providers/infer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input, category_id: categoryId }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarUpsertProviderCategory(payload: {
  category_id?: string;
  label: string;
  parent_group?: string;
  description?: string;
}): Promise<ProviderRegistryState & { category_id?: string }> {
  try {
    const res = await sidecarFetch("/providers/category/upsert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return {
      ok: false,
      unlocked: false,
      profile_id: null,
      categories: [],
      providers_by_category: {},
      presets: {},
      suggestions: [],
      error: String(e),
    };
  }
}

export async function sidecarDeleteProviderCategory(
  categoryId: string
): Promise<ProviderRegistryState> {
  try {
    const res = await sidecarFetch("/providers/category/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category_id: categoryId }),
    });
    return await res.json();
  } catch (e) {
    return {
      ok: false,
      unlocked: false,
      profile_id: null,
      categories: [],
      providers_by_category: {},
      presets: {},
      suggestions: [],
      error: String(e),
    };
  }
}

export async function sidecarUpsertProvider(payload: {
  provider_id?: string;
  category_id: string;
  display_name: string;
  provider_slug?: string;
  mode?: "search_api" | "web_account";
  api_driver?: string;
  domains?: string[];
  url_template?: string;
  vault_service?: string;
  constraints_note?: string;
  priority?: number;
  enabled?: boolean;
  credentials?: {
    api_key?: string;
    username?: string;
    password?: string;
    token?: string;
    cookie?: string;
  };
}): Promise<ProviderRegistryState & { provider_id?: string }> {
  try {
    const res = await sidecarFetch("/providers/upsert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return {
      ok: false,
      unlocked: false,
      profile_id: null,
      categories: [],
      providers_by_category: {},
      presets: {},
      suggestions: [],
      error: String(e),
    };
  }
}

export async function sidecarReorderProviders(
  categoryId: string,
  orderedIds: string[]
): Promise<ProviderRegistryState> {
  try {
    const res = await sidecarFetch("/providers/reorder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category_id: categoryId, ordered_ids: orderedIds }),
    });
    return await res.json();
  } catch (e) {
    return {
      ok: false,
      unlocked: false,
      profile_id: null,
      categories: [],
      providers_by_category: {},
      presets: {},
      suggestions: [],
      error: String(e),
    };
  }
}

export async function sidecarDeleteProvider(
  providerId: string,
  deleteCredentials = false
): Promise<ProviderRegistryState> {
  try {
    const res = await sidecarFetch("/providers/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider_id: providerId,
        delete_credentials: deleteCredentials,
      }),
    });
    return await res.json();
  } catch (e) {
    return {
      ok: false,
      unlocked: false,
      profile_id: null,
      categories: [],
      providers_by_category: {},
      presets: {},
      suggestions: [],
      error: String(e),
    };
  }
}

export async function sidecarTestProvider(
  providerId: string,
  sampleQuery = "winter jacket"
): Promise<{
  ok: boolean;
  provider_id?: string;
  preview_url?: string;
  auth_status?: string;
  message?: string;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/providers/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider_id: providerId, sample_query: sampleQuery }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarResolveProviderSuggestion(
  suggestionId: string,
  action: "accept" | "dismiss"
): Promise<ProviderRegistryState> {
  try {
    const res = await sidecarFetch("/providers/suggestion/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ suggestion_id: suggestionId, action }),
    });
    return await res.json();
  } catch (e) {
    return {
      ok: false,
      unlocked: false,
      profile_id: null,
      categories: [],
      providers_by_category: {},
      presets: {},
      suggestions: [],
      error: String(e),
    };
  }
}

export async function sidecarExecuteSetDefaultProvider(
  taskId: string,
  stepId?: string
): Promise<{
  ok: boolean;
  task?: AgentTaskCard;
  message?: string;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/providers/set_default", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: taskId, step_id: stepId ?? "" }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarStageSettingsFile(payload: {
  filename: string;
  mime?: string;
  content_text: string;
}): Promise<{
  ok: boolean;
  staged?: StagedSettingsFile;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/settings/stage_file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarConfirmSettingsGate(payload: {
  confirm_token: string;
  action_payload?: Record<string, unknown>;
}): Promise<{
  ok: boolean;
  message?: string;
  error?: string;
  refresh_hints?: string[];
  google_oauth?: GoogleOAuthStatus;
}> {
  try {
    const res = await sidecarFetch("/settings/confirm_gate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function apiExtractTabTranslationDom(tabId: string): Promise<{
  ok: boolean;
  already_extracted?: boolean;
  showing_translated?: boolean;
  has_cached_translation?: boolean;
  url?: string;
  title?: string;
  html_lang?: string;
  block_count?: number;
  blocks?: PageTranslationBlock[];
  error?: string;
}> {
  try {
    return await invoke("extract_tab_translation_dom", { tabId });
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function apiApplyTabTranslationSegments(
  tabId: string,
  mode: "apply" | "restore" | "reapply",
  translations?: Record<string, string>
): Promise<{
  ok: boolean;
  status?: string;
  applied?: number;
  showing_translated?: boolean;
  error?: string;
}> {
  try {
    return await invoke("apply_tab_translation_segments", {
      tabId,
      mode,
      translations: translations ?? null,
    });
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarGetTranslationConfig(): Promise<ContentTranslationConfig | null> {
  try {
    const res = await sidecarFetch("/translation/config");
    if (!res.ok) return null;
    return (await res.json()) as ContentTranslationConfig;
  } catch {
    return null;
  }
}

export async function sidecarUpdateTranslationConfig(payload: {
  known_languages?: string[];
  add_language?: string;
  remove_language?: string;
  primary_language?: string;
  model_preference?: string;
  auto_translate_mail?: boolean;
  auto_translate_news?: boolean;
  mail_include_promos_pings?: boolean;
  backfill_recent?: boolean;
}): Promise<ContentTranslationConfig & { queued_mail?: number }> {
  try {
    const res = await sidecarFetch("/translation/config/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return {
      ok: false,
      unlocked: false,
      profile_id: null,
      known_languages: ["en"],
      known_language_details: [{ code: "en", name: "English", native: "English", rtl: false }],
      primary_language: "en",
      primary_language_info: { code: "en", name: "English", native: "English", rtl: false },
      model_preference: "auto_cheapest",
      resolved_model: {
        model_id: "gemma-4-e4b",
        provider: "local",
        is_cloud: false,
        tier_label: "local_free",
        cost_hint: "$0",
        rank: 300,
        mode: "auto_cheapest",
      },
      auto_translate_mail: true,
      auto_translate_news: true,
      mail_include_promos_pings: false,
      mail_max_age_days: 90,
      mail_max_recent: 200,
      catalog: [],
      error: String(e),
    };
  }
}

export async function sidecarTranslateMailMessage(
  messageId: string,
  targetLang = "",
  force = false
): Promise<{
  ok: boolean;
  message_id?: string;
  skipped_allowed?: boolean;
  source_lang?: string;
  target_lang?: string;
  translation?: {
    target_lang: string;
    source_lang: string;
    subject: string;
    snippet: string;
    new_text: string;
    html: string;
    model_id: string;
  } | null;
  error?: string;
}> {
  try {
    const res = await sidecarFetch(
      "/translation/mail",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message_id: messageId,
          target_lang: targetLang,
          force,
        }),
      },
      45000
    );
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarBackfillTranslations(): Promise<{
  ok: boolean;
  queued_mail?: number;
  translated_articles?: number;
  error?: string;
}> {
  try {
    const res = await sidecarFetch(
      "/translation/mail/backfill",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      },
      60000
    );
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export interface PageTranslateSseEvent {
  phase: "batch" | "done" | "error";
  batch?: number;
  total_batches?: number;
  translations?: Record<string, string>;
  ok?: boolean;
  skipped_allowed?: boolean;
  source_lang?: string;
  target_lang?: string;
  model?: string;
  error?: string;
}

export async function sidecarTranslatePageStream(
  payload: {
    url: string;
    title: string;
    html_lang: string;
    blocks: PageTranslationBlock[];
    force?: boolean;
  },
  onEvent: (ev: PageTranslateSseEvent) => Promise<void> | void
): Promise<PageTranslateSseEvent> {
  let finalEv: PageTranslateSseEvent = { phase: "error", ok: false, error: "empty response" };
  try {
    const res = await sidecarFetch(
      "/translation/page",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...payload, stream: true }),
      },
      60000
    );
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      return { phase: "error", ok: false, error: String(errJson.error ?? `HTTP ${res.status}`) };
    }
    const reader = res.body?.getReader();
    if (!reader) {
      const fallback = await res.json().catch(() => ({ ok: false }));
      return { phase: "done", ...fallback };
    }
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() ?? "";
      for (const ln of lines) {
        const trimmed = ln.trim();
        if (!trimmed.startsWith("data: ")) continue;
        try {
          const ev = JSON.parse(trimmed.slice(6)) as PageTranslateSseEvent;
          await onEvent(ev);
          if (ev.phase === "done" || ev.phase === "error") {
            finalEv = ev;
          }
        } catch {
          // Ignore partial or malformed keepalive chunks
        }
      }
    }
    if (buf.trim().startsWith("data: ")) {
      try {
        const ev = JSON.parse(buf.trim().slice(6)) as PageTranslateSseEvent;
        await onEvent(ev);
        if (ev.phase === "done" || ev.phase === "error") finalEv = ev;
      } catch {
        // ignore
      }
    }
    return finalEv;
  } catch (e) {
    return { phase: "error", ok: false, error: String(e) };
  }
}

export async function sidecarGetI18nStatus(
  lang?: string
): Promise<I18nStatusResponse | null> {
  try {
    const qs = lang ? `?lang=${encodeURIComponent(lang)}` : "";
    const res = await sidecarFetch(`/i18n/status${qs}`);
    if (!res.ok) return null;
    return (await res.json()) as I18nStatusResponse;
  } catch {
    return null;
  }
}

export async function sidecarGetI18nBundle(lang: string): Promise<{
  ok: boolean;
  lang: string;
  label: string;
  dir: "ltr" | "rtl";
  model?: string;
  entries: Record<string, I18nBundleEntry>;
  error?: string;
} | null> {
  try {
    const res = await sidecarFetch(`/i18n/bundle?lang=${encodeURIComponent(lang)}`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function sidecarSwitchI18nLanguage(payload: {
  lang: string;
  catalog?: Record<string, { text: string; one?: string; hint?: string }>;
  sync_missing?: boolean;
  model?: string;
}): Promise<I18nStatusResponse> {
  try {
    const res = await sidecarFetch("/i18n/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...payload,
        switch_only: true,
        activate: true,
      }),
    });
    return (await res.json()) as I18nStatusResponse;
  } catch (e) {
    return {
      ok: false,
      active_locale: "en",
      active_label: "English",
      active_dir: "ltr",
      default_model: "gemma-4-e4b",
      model_info: {
        model_id: "gemma-4-e4b",
        local_only: true,
        provider_id: "local",
        host: "localhost",
        disclosure: "",
      },
      target: {
        lang: payload.lang,
        label: payload.lang,
        dir: "ltr",
        model: "",
        total: 0,
        translated: 0,
        missing: 0,
        stale: 0,
        custom_count: 0,
        updated_at: 0,
      },
      locales: [],
      job: {
        running: false,
        lang: "",
        label: "",
        model: "",
        completed: 0,
        total: 0,
        current_batch: 0,
        total_batches: 0,
        error: String(e),
        updated_at: 0,
      },
      error: String(e),
    };
  }
}

export async function sidecarTranslateI18nStream(
  payload: {
    lang: string;
    catalog?: Record<string, { text: string; one?: string; hint?: string }>;
    model?: string;
    only_missing?: boolean;
    force?: boolean;
    activate?: boolean;
  },
  callbacks: {
    onStart?: (ev: {
      lang: string;
      label: string;
      dir: "ltr" | "rtl";
      model: string;
      missing: number;
      stale: number;
    }) => void;
    onBatch?: (ev: {
      batch: number;
      total_batches: number;
      completed: number;
      total: number;
      entries: Record<string, I18nBundleEntry>;
    }) => void;
    onDone?: (ev: {
      ok: boolean;
      lang: string;
      label: string;
      dir: "ltr" | "rtl";
      model: string;
      translated_now: number;
      skipped_or_failed: number;
      cancelled?: boolean;
      entries: Record<string, I18nBundleEntry>;
      error?: string;
    }) => void;
    onError?: (err: string) => void;
  }
): Promise<void> {
  const res = await sidecarFetch("/i18n/translate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload,
      stream: true,
    }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`/i18n/translate returned HTTP ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: !done });
    } else if (done) {
      buffer += decoder.decode();
    }
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        try {
          const ev = JSON.parse(line.slice(6)) as Record<string, unknown>;
          const phase = String(ev.phase || "");
          if (phase === "start") {
            callbacks.onStart?.(
              ev as unknown as {
                lang: string;
                label: string;
                dir: "ltr" | "rtl";
                model: string;
                missing: number;
                stale: number;
              }
            );
          } else if (phase === "batch") {
            callbacks.onBatch?.(
              ev as unknown as {
                batch: number;
                total_batches: number;
                completed: number;
                total: number;
                entries: Record<string, I18nBundleEntry>;
              }
            );
          } else if (phase === "done") {
            callbacks.onDone?.(
              ev as unknown as {
                ok: boolean;
                lang: string;
                label: string;
                dir: "ltr" | "rtl";
                model: string;
                translated_now: number;
                skipped_or_failed: number;
                cancelled?: boolean;
                entries: Record<string, I18nBundleEntry>;
                error?: string;
              }
            );
          } else if (phase === "error") {
            callbacks.onError?.(String(ev.error || "translation failed"));
          }
        } catch {
          // Ignore malformed SSE chunks
        }
      }
    }
    if (done) break;
  }
}

export async function sidecarCancelI18nTranslate(
  lang?: string
): Promise<{ ok: boolean; cancelled?: string[] }> {
  try {
    const res = await sidecarFetch("/i18n/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(lang ? { lang } : {}),
    });
    return await res.json();
  } catch {
    return { ok: false };
  }
}

export async function sidecarOverrideI18n(payload: {
  lang: string;
  key: string;
  text?: string;
  one?: string;
  reset?: boolean;
  catalog?: Record<string, { text: string; one?: string; hint?: string }>;
}): Promise<{ ok: boolean; error?: string; entry?: I18nBundleEntry }> {
  try {
    const res = await sidecarFetch("/i18n/override", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarExportI18n(lang: string): Promise<{
  ok: boolean;
  pack?: Record<string, unknown>;
  error?: string;
}> {
  try {
    const res = await sidecarFetch(`/i18n/export?lang=${encodeURIComponent(lang)}`);
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarImportI18n(
  pack: Record<string, unknown>,
  activate = true
): Promise<{
  ok: boolean;
  lang?: string;
  label?: string;
  dir?: "ltr" | "rtl";
  imported?: number;
  entries?: Record<string, I18nBundleEntry>;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/i18n/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pack, activate }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarFetchDrivesStatus(
  googleSessionId = "",
  onedriveSessionId = ""
): Promise<DrivesStatusResponse | null> {
  try {
    const params = new URLSearchParams();
    if (googleSessionId) params.set("google_session_id", googleSessionId);
    if (onedriveSessionId) params.set("onedrive_session_id", onedriveSessionId);
    const qs = params.toString();
    const res = await sidecarFetch(`/drives/status${qs ? `?${qs}` : ""}`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function sidecarFetchDrivesList(payload: {
  folder_key?: string;
  provider?: DriveProviderFilter;
  file_type?: DriveFileTypeFilter;
  owner?: string;
  query?: string;
  limit?: number;
}): Promise<DriveListResponse | null> {
  try {
    const res = await sidecarFetch("/drives/list", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function sidecarFetchDriveCreateTargets(): Promise<DriveCreateTarget[]> {
  try {
    const res = await sidecarFetch("/drives/create_targets");
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data.targets) ? data.targets : [];
  } catch {
    return [];
  }
}

export async function sidecarSyncDrives(payload?: {
  providers?: string[];
  full_resync?: boolean;
  blocking?: boolean;
}): Promise<{ ok: boolean; error?: string; status?: DrivesStatusResponse }> {
  try {
    const res = await sidecarFetch(
      "/drives/sync",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload ?? {}),
      },
      60000
    );
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarConnectGoogleDrive(payload?: {
  client_id?: string;
  client_secret?: string;
  client_secret_json?: string;
  login_hint?: string;
  hd?: string;
}): Promise<{
  ok: boolean;
  session_id?: string;
  auth_url?: string;
  redirect_uri?: string;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/drives/google/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ?? {}),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarSaveOneDriveConfig(payload: {
  client_id: string;
  tenant_id?: string;
  client_secret?: string;
}): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await sidecarFetch("/drives/onedrive/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarStartOneDriveConnect(payload?: {
  client_id?: string;
  tenant_id?: string;
  client_secret?: string;
  login_hint?: string;
}): Promise<{
  ok: boolean;
  session_id?: string;
  auth_url?: string;
  redirect_uri?: string;
  error?: string;
}> {
  try {
    const res = await sidecarFetch("/drives/onedrive/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ?? {}),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function sidecarDisconnectDrive(
  provider: "gdrive" | "onedrive",
  purgeIndex = true,
  clearClientConfig = false
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await sidecarFetch("/drives/disconnect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider,
        purge_index: purgeIndex,
        clear_client_config: clearClientConfig,
      }),
    });
    return await res.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}
