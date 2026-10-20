export type ConversationOrigin = "chat" | "direct";
export type ConversationStatus = "active" | "archived";

export interface Conversation {
  id: string;
  title: string;
  status: ConversationStatus;
  pinned: boolean;
  origin: ConversationOrigin;
  created_at: string;
  last_active_at: string;
  source_count?: number;
}

export interface BrowserTab {
  id: string;
  conversation_id: string;
  position: number;
  url: string;
  title: string;
  is_open: boolean;
  suspended?: boolean;
  created_at: string;
}

export interface SourceItem {
  id: string;
  conversation_id: string;
  tab_id: string | null;
  url: string;
  title: string;
  domain: string;
  in_context: boolean;
  added_at: string;
  captured_at: string | null;
  text_chars: number | null;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  model: string | null;
  source_ids_json: string | null;
  created_at: string;
  cited_sources?: Array<{ url: string; title: string; domain?: string }>;
}

export interface BookmarkItem {
  id: string;
  title: string;
  url: string;
  position: number;
  created_at: string;
}

export interface HistoryItem {
  id: string;
  conversation_id: string;
  tab_id: string | null;
  url: string;
  title: string;
  visited_at: string;
}

export interface ConversationDetail {
  conversation: Conversation;
  tabs: BrowserTab[];
  sources: SourceItem[];
  messages: ChatMessage[];
  history: HistoryItem[];
}

export interface TabBoundsSpec {
  tab_id: string;
  url: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface TabPageEvent {
  tab_id: string;
  event_type: "load_started" | "load_finished" | "title_changed";
  url: string | null;
  title: string | null;
}

export type LocalModelId =
  | "gemma-4-e4b"
  | "planck3 (web)"
  | "hertz (reader)"
  | "planck (reader)";

export type ModelHealthState = "not_loaded" | "loading" | "ready" | "missing";

export interface ModelHealthEntry {
  id: LocalModelId;
  state: ModelHealthState;
  reason?: string;
}

export interface SidecarHealth {
  online: boolean;
  models: ModelHealthEntry[];
  ingest_queue_len: number;
  pause_learning: boolean;
}

export interface DigestEntry {
  title: string;
  url: string;
  domain: string;
  summary: string;
  kind: string;
}

export interface KnowledgeSummary {
  pause_learning: boolean;
  queue_len: number;
  top_domains: Array<{ domain: string; visits: number; score: number }>;
  top_topics: Array<{ topic: string; weight: number }>;
  passages: Array<{
    id: string;
    conversation_id: string;
    entity: string;
    url: string;
    text: string;
    added_at: string;
  }>;
}
