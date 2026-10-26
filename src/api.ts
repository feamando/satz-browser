import { invoke } from "@tauri-apps/api/core";
import { extractDomain } from "./state";
import type {
  BookmarkItem,
  BrowserTab,
  ChatMessage,
  Conversation,
  ConversationDetail,
  ConversationOrigin,
  ConversationStatus,
  DigestEntry,
  KnowledgeSummary,
  LocalModelId,
  SidecarHealth,
  SourceItem,
  TabBoundsSpec,
} from "./types";

const SIDECAR_BASE = "http://127.0.0.1:8020";

function mapConversationRow(raw: Record<string, unknown>): Conversation {
  // v1 -> v2 migration mapping: map legacy intent_title to title
  const mappedTitle = String(raw.title ?? raw.intent_title ?? "untitled");
  return {
    id: String(raw.id ?? ""),
    title: mappedTitle,
    status: (raw.status === "archived" ? "archived" : "active") as ConversationStatus,
    pinned: Boolean(raw.pinned),
    origin: (raw.origin === "direct" ? "direct" : "chat") as ConversationOrigin,
    created_at: String(raw.created_at ?? ""),
    last_active_at: String(raw.last_active_at ?? raw.created_at ?? ""),
    source_count:
      typeof raw.source_count === "number" ? raw.source_count : undefined,
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
  const messages: ChatMessage[] = rawMsgs.map((m) => ({
    id: String(m.id ?? ""),
    conversation_id: conv.id,
    role: (m.role ?? m.author ?? "user") as "user" | "assistant" | "system",
    content: String(m.content ?? ""),
    model: m.model ? String(m.model) : null,
    source_ids_json: m.source_ids_json ? String(m.source_ids_json) : null,
    created_at: String(m.created_at ?? ""),
  }));

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
    await fetch(`${SIDECAR_BASE}/forget`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId }),
    });
  } catch {
    // Sidecar offline is fine
  }
}

export async function apiOpenTab(
  conversationId: string,
  url: string,
  title?: string
): Promise<BrowserTab> {
  return await invoke<BrowserTab>("open_tab", {
    conversationId,
    url,
    title: title ?? null,
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
  sourceIdsJson: string | null = null
): Promise<ChatMessage> {
  return await invoke<ChatMessage>("add_message", {
    conversationId,
    role,
    content,
    model,
    sourceIdsJson,
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
  url: string
): Promise<BookmarkItem> {
  return await invoke<BookmarkItem>("add_bookmark", { title, url });
}

export async function apiRemoveBookmark(bookmarkId: string): Promise<void> {
  await invoke("remove_bookmark", { bookmarkId });
}

export async function sidecarFetchHealth(): Promise<SidecarHealth> {
  try {
    const res = await fetch(`${SIDECAR_BASE}/health`);
    if (!res.ok) throw new Error("sidecar error");
    const data = (await res.json()) as SidecarHealth;
    return { ...data, online: true };
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
    };
  }
}

export async function sidecarFetchDigest(): Promise<DigestEntry[]> {
  try {
    const res = await fetch(`${SIDECAR_BASE}/digest`);
    if (!res.ok) return [];
    const data = (await res.json()) as { items?: DigestEntry[] };
    return data.items ?? [];
  } catch {
    return [];
  }
}

export async function sidecarFetchKnowledge(): Promise<KnowledgeSummary | null> {
  try {
    const res = await fetch(`${SIDECAR_BASE}/knowledge`);
    if (!res.ok) return null;
    const raw = (await res.json()) as Record<string, unknown>;
    const rawDomains = (raw.top_domains ?? []) as Array<Record<string, unknown>>;
    const rawTopics = (raw.top_topics ?? []) as Array<Record<string, unknown>>;
    const rawPassages = (raw.passages ?? []) as Array<Record<string, unknown>>;
    const rawBrain = (raw.brain ?? null) as Record<string, unknown> | null;
    const rawEntities = (rawBrain?.entities ?? []) as Array<Record<string, unknown>>;

    return {
      pause_learning: Boolean(raw.pause_learning),
      queue_len: Number(raw.queue_len ?? 0),
      brain: rawBrain
        ? {
            brain_dir: String(rawBrain.brain_dir ?? ""),
            brain_md: String(rawBrain.brain_md ?? ""),
            entity_count: Number(rawBrain.entity_count ?? rawEntities.length),
            entities: rawEntities.map((e) => ({
              slug: String(e.slug ?? ""),
              type: String(e.type ?? "note"),
              name: String(e.name ?? ""),
              tier: Number(e.tier ?? 2),
              summary: String(e.summary ?? ""),
              path: String(e.path ?? ""),
              attributes: (e.attributes ?? {}) as Record<string, unknown>,
              updated: String(e.updated ?? ""),
            })),
          }
        : undefined,
      top_domains: rawDomains.map((d) => ({
        domain: String(d.domain ?? ""),
        visits: Number(d.visits ?? 0),
        score: Number(d.score ?? d.trust ?? 0),
      })),
      top_topics: rawTopics.map((t) => ({
        topic: String(t.topic ?? t.entity ?? ""),
        weight: Number(t.weight ?? t.score ?? 0),
      })),
      passages: rawPassages.map((p) => ({
        id: String(p.id ?? ""),
        conversation_id: String(p.conversation_id ?? ""),
        entity: String(p.entity ?? p.title ?? p.domain ?? ""),
        url: String(p.url ?? ""),
        text: String(p.text ?? ""),
        added_at: String(p.added_at ?? p.ts ?? ""),
      })),
    };
  } catch {
    return null;
  }
}

export async function sidecarSetPauseLearning(paused: boolean): Promise<boolean> {
  try {
    const res = await fetch(`${SIDECAR_BASE}/knowledge/pause`, {
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
    await fetch(`${SIDECAR_BASE}/knowledge/delete_passage`, {
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
    await fetch(`${SIDECAR_BASE}/knowledge/delete_entity`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug }),
    });
  } catch {
    // Ignore when offline
  }
}

export async function sidecarRunAnswer(
  question: string,
  conversationId: string
): Promise<{
  answer: string;
  band: string;
  sources: Array<{ id?: string; url: string; title: string; domain?: string }>;
}> {
  const res = await fetch(`${SIDECAR_BASE}/answer`, {
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
  const res = await fetch(`${SIDECAR_BASE}/read`, {
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

export async function sidecarStreamChat(
  model: LocalModelId,
  messages: Array<{ role: string; content: string }>,
  sources: Array<{ id: string; url: string; title: string; domain: string; is_open_tab: boolean }>,
  web: boolean,
  onDelta: (delta: string) => void
): Promise<{ source_ids: string[]; cited_sources?: Array<{ url: string; title: string }> }> {
  const res = await fetch(`${SIDECAR_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model, messages, sources, web }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`/chat returned ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalSourceIds: string[] = [];
  let citedSources: Array<{ url: string; title: string }> | undefined;

  while (true) {
    const { value, done } = await reader.read();
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
        const payload = JSON.parse(jsonStr) as {
          delta?: string;
          done?: boolean;
          source_ids?: string[];
          cited_sources?: Array<{ url: string; title: string }>;
        };
        if (payload.delta) {
          onDelta(payload.delta);
        }
        if (payload.done) {
          finalSourceIds = payload.source_ids ?? [];
          citedSources = payload.cited_sources;
        }
      } catch {
        // Ignore malformed SSE line
      }
    }
  }
  return { source_ids: finalSourceIds, cited_sources: citedSources };
}
