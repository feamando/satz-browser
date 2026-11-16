export type ConversationOrigin = "chat" | "direct" | "mail";
export type ConversationStatus = "active" | "archived";
export type TabKind = "site" | "mail" | "compose";

export interface Conversation {
  id: string;
  title: string;
  status: ConversationStatus;
  pinned: boolean;
  origin: ConversationOrigin;
  created_at: string;
  last_active_at: string;
  source_count?: number;
  summary?: string | null;
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
  kind?: TabKind;
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

export interface CitationCheckEntry {
  n: number | string;
  sentence_idx: number;
  ok: boolean;
  out_of_range?: boolean;
  missing: string[];
}

export interface BrainCitationItem {
  id: string;
  cite_label: string;
  b_index: number;
  slug: string;
  name: string;
  type: string;
  summary: string;
  path?: string;
  source_url?: string;
}

export interface SourceStatEntry {
  id: string;
  chars_captured: number;
  chars_sent: number;
  was_cut: boolean;
  capture_mode?: "dom" | "fetch" | "timeout";
}

export interface FindingItem {
  image_url: string;
  title: string;
  price?: string;
  page_url: string;
}

export interface SidecarErrorEntry {
  ts: number;
  scope: string;
  message: string;
}

export interface EmailAttachmentItem {
  filename: string;
  mime: string;
  size: number;
  part_id: string;
  saved_path?: string;
}

export interface ChatEmailCard {
  message_id: string;
  source_id: string;
  subject: string;
  from_name: string;
  from_addr: string;
  date: number;
  label: string;
  snippet: string;
  body_text: string;
  quoted_text?: string;
  attachments: EmailAttachmentItem[];
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  model: string | null;
  source_ids_json: string | null;
  created_at: string;
  citations_ok?: number | null;
  citations_flagged?: number | null;
  citation_check_json?: string | null;
  citation_check?: CitationCheckEntry[];
  cited_sources?: Array<{ url: string; title: string; domain?: string }>;
  brain_sources?: BrainCitationItem[];
  proposals?: BrainProposalItem[];
  findings?: FindingItem[];
  email_cards?: ChatEmailCard[];
}

export interface BrainProposalItem {
  proposal_id: string;
  type: string;
  name: string;
  summary: string;
  attributes: Record<string, unknown>;
  content: string;
  source_url?: string;
  status?: "pending" | "accepted" | "rejected";
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
  toolbar_bottom?: number;
  viewport_h?: number;
}

export interface TabPageEvent {
  tab_id: string;
  event_type: "load_started" | "load_finished" | "title_changed" | "dom_captured";
  url: string | null;
  title: string | null;
  has_password_field?: boolean | null;
}

export type LocalModelId =
  | "gemma-4-e4b"
  | "planck3 (web)"
  | "hertz (reader)"
  | "planck (reader)"
  | (string & {});

export type ModelHealthState = "not_loaded" | "loading" | "ready" | "missing";

export interface ModelHealthEntry {
  id: LocalModelId;
  state: ModelHealthState;
  device?: string;
  detail?: string;
  reason?: string;
}

export interface DoctorRoleEntry {
  role: string;
  model: string;
  state: "ready" | "missing" | "cpu_only";
  device: string;
  path?: string;
  fix: string;
}

export interface CloudProviderInfo {
  id: string;
  label: string;
  env_key?: string;
  host?: string;
  placeholder?: string;
  configured: boolean;
  key_source: string;
  masked_key: string;
  stored_key?: string;
  models: Array<{ id: string; slug: string; label: string; provider?: string }>;
  privacy_disclosure: string;
}

export interface ModelManagementConfig {
  ok: boolean;
  roles: {
    chat: string;
    web_answer: string;
    reader: string;
    mail_classifier: string;
    brain_encoder: string;
  };
  cloud_providers: CloudProviderInfo[];
  test_ok?: boolean;
  test_message?: string;
  error?: string;
}

export interface SidecarHealth {
  online: boolean;
  version?: string;
  models: ModelHealthEntry[];
  ingest_queue_len: number;
  pause_learning: boolean;
  errors?: SidecarErrorEntry[];
  mail?: MailStatusSummary | null;
  watch_badges?: string[];
  model_config?: ModelManagementConfig;
}

export interface MailPreset {
  id: string;
  label: string;
  protocol: "imap" | "pop3";
  in_host: string;
  in_port: number;
  in_security: "ssl" | "starttls";
  smtp_host: string;
  smtp_port: number;
  smtp_security: "ssl" | "starttls";
}

export interface MailAccountItem {
  id: string;
  label: string;
  email: string;
  protocol: "imap" | "pop3";
  in_host: string;
  in_port: number;
  in_security: string;
  smtp_host: string;
  smtp_port: number;
  smtp_security: string;
  vault_prefix: string;
  sync_days: number;
  last_sync_at: number;
  last_error: string;
  auth_failed?: boolean;
  message_count?: number;
}

export interface MailLaneCounts {
  inbox_unread: number;
  pings: number;
  orders: number;
  promos: number;
}

export interface MailStatusSummary {
  unlocked: boolean;
  accounts_count: number;
  inbox_unread: number;
  counts?: MailLaneCounts;
  processing_done: number;
  processing_total: number;
  is_processing?: boolean;
  model_version: string;
  labelled_count?: number;
  last_retrain_at?: number;
}

export interface MailMessageRow {
  id: string;
  account_id: string;
  thread_id: string;
  from_name: string;
  from_addr: string;
  subject: string;
  snippet: string;
  date: number;
  seen: number;
  answered?: number;
  flagged?: number;
  has_attachments?: number;
  label?: string;
  confidence?: number;
  needs_reply?: number;
  due_date?: string | null;
  ask?: string;
  platform?: string;
}

export interface MailClassifierInfo {
  model_version: string;
  training_labels: number;
  target_labels: number;
  corrections_count: number;
  status_text: string;
}

export interface MailLaneResponse {
  unlocked: boolean;
  lane: "inbox" | "pings" | "orders" | "promos";
  rows: Array<Record<string, unknown>>;
  groups?: Array<Record<string, unknown>>;
  next_cursor?: number | null;
  counts: MailLaneCounts;
  classifier?: MailClassifierInfo;
  onboarding_candidates?: Array<Record<string, unknown>>;
}

export interface DigestEntry {
  title: string;
  url: string;
  domain: string;
  summary: string;
  kind: string;
}

export interface BrainEntityItem {
  slug: string;
  type: string;
  name: string;
  tier: number;
  summary: string;
  path: string;
  source_url?: string;
  body?: string;
  attributes: Record<string, unknown>;
  updated: string;
}

export interface BrainSearchResponse {
  ok: boolean;
  query: string;
  entities: BrainEntityItem[];
  passages: Array<{
    id: string;
    url: string;
    domain: string;
    title: string;
    text: string;
    entity: string;
    ts: number;
    score: number;
  }>;
  mail: Array<Record<string, unknown>>;
  brain_ranking: string;
}

export interface BookmarkIndexStatus {
  id: string;
  url: string;
  domain: string;
  title: string;
  last_indexed_at: number;
  text_chars: number;
  status: string;
}

export interface UserProfileItem {
  id: string;
  name: string;
  created_at: string;
  last_active_at: string;
  credential_services_count: number;
  is_active: boolean;
  failed_attempts?: number;
  retry_after_seconds?: number;
}

export interface ProfileStatusSummary {
  profiles: UserProfileItem[];
  active_profile_id: string | null;
  unlocked: boolean;
  active_profile: UserProfileItem | null;
}

export interface ProfileVaultService {
  service: string;
  domain: string;
  username: string;
  has_password: boolean;
  has_token: boolean;
  has_cookie: boolean;
  keys: string[];
}

export interface ProfileVaultSummary {
  unlocked: boolean;
  profile_id: string | null;
  env_path: string | null;
  services: ProfileVaultService[];
  raw_env: string;
}

export interface KnowledgeSummary {
  pause_learning: boolean;
  queue_len: number;
  brain?: {
    brain_dir: string;
    brain_md: string;
    entity_count: number;
    entities: BrainEntityItem[];
    locked?: boolean;
    message?: string;
    brain_ranking?: string;
    encoder?: {
      mode: string;
      state: string;
      label: string;
    };
  };
  bookmarks_indexed?: BookmarkIndexStatus[];
  profile?: ProfileStatusSummary;
  vault?: ProfileVaultSummary;
  top_domains: Array<{
    domain: string;
    visits: number;
    trust: number;
    score?: number;
    dwell_seconds?: number;
    system?: number;
    personal?: number | null;
    effective?: number;
    band?: string;
    band_label?: string;
    category?: string;
    why?: string;
    scored?: boolean;
    conflict?: boolean;
  }>;
  top_topics: Array<{
    entity: string;
    score: number;
    topic?: string;
    weight?: number;
  }>;
  passages: Array<{
    id: string;
    conversation_id: string;
    entity: string;
    url: string;
    text: string;
    added_at: string;
  }>;
  this_week?: Array<{
    kind: "read" | "received";
    title: string;
    url: string;
    domain: string;
    ts: number;
    label?: string;
    message_id?: string;
  }>;
}

export type CommandRouteKind =
  | "open_url"
  | "url_and_question"
  | "ask_model"
  | "search_mail"
  | "search_brain"
  | "run_command";

export type CommandBarActionId =
  | "new_conversation"
  | "bookmark"
  | "compare"
  | "lock"
  | "brain"
  | "settings";

export interface CommandBarRoute {
  kind: CommandRouteKind;
  label: string;
  destination: string;
  privacy: string;
  leaves_machine: boolean;
  url?: string;
  question?: string;
  query?: string;
  command_id?: CommandBarActionId;
}

export interface TaskStep {
  id: string;
  text: string;
  kind: "log" | "send_gate";
  status: "running" | "done" | "waiting_confirm" | "confirmed" | "cancelled" | "stopped";
  ts: number;
  action_summary?: string;
  confirm_token?: string;
}

export interface AgentTaskCard {
  id: string;
  conversation_id: string;
  agent: string;
  goal: string;
  steps: TaskStep[];
  status: "running" | "waiting_confirm" | "completed" | "stopped" | "cancelled";
  started_at: number;
  stop_token: string;
  result_md?: string;
}

export interface WatchItem {
  watch_id: string;
  store_watch_id?: number;
  conversation_id: string;
  query_or_url: string;
  title: string;
  cadence_seconds: number;
  condition: string;
  last_value: string;
  previous_value: string;
  last_checked_at: number;
  changed_at: number;
  badge_unread: boolean;
}
