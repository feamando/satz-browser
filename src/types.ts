export type ConversationOrigin =
  | "chat"
  | "direct"
  | "mail"
  | "news"
  | "drives"
  | "settings"
  | "news_settings"
  | "news_perspectives";
export type ConversationStatus = "active" | "archived";
export type TabKind = "site" | "mail" | "compose";
export type NewsLane = "stories" | "tracked" | "perspectives";
export type SettingsLane =
  | "profiles"
  | "models"
  | "google_mail"
  | "providers"
  | "translation"
  | "sources";

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
  last_summary?: string;
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
  entity_type?: string;
  summary: string;
  attributes?: Record<string, unknown>;
  aliases?: string[];
  path?: string;
  source_url?: string;
}

export interface SourceStatEntry {
  id: string;
  chars_captured: number;
  chars_sent: number;
  was_cut: boolean;
  capture_mode?: "dom" | "fetch" | "timeout";
  context_tier?: "full" | "excerpt" | "manifest" | "expanded";
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

export interface MailComposeDraft {
  account_id: string;
  to: string;
  cc: string;
  bcc: string;
  subject: string;
  body: string;
  in_reply_to: string;
  references: string;
  reply_to_message_id: string;
  ai_prompt?: string;
  ai_model?: LocalModelId;
  ai_loading?: boolean;
  ai_draft_id?: string;
  confirm_outbox_id?: string;
  confirm_token?: string;
  confirm_line?: string;
  new_recipients?: string[];
  queued_outbox_id?: string;
  undo_until?: number;
  status_msg?: string;
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
  can_unsubscribe?: boolean;
  unsubscribe_method?: string;
}

export interface ChatImageAttachment {
  id: string;
  name: string;
  mime: string;
  data_url: string;
  width?: number;
  height?: number;
  size?: number;
}

export interface StagedSettingsFile {
  staging_id: string;
  filename: string;
  detected_kind: "google_client_secret" | "env_secrets" | "unknown_text";
  summary: string;
  safe_fields: Record<string, unknown>;
}

export interface SettingsUiCard {
  id: string;
  kind:
    | "profile_create_card"
    | "profile_unlock_card"
    | "google_oauth_connect_card"
    | "vault_secret_input_card"
    | "mail_account_card"
    | "provider_preview_card"
    | "confirm_gate_card"
    | "locale_translate_card"
    | "settings_status_card"
    | "news_settings_status_card"
    | "news_topic_suggestions_card"
    | "news_source_suggestions_card"
    | "news_source_trust_card"
    | "news_add_feed_card";
  title: string;
  title_key?: string;
  title_vars?: Record<string, string | number>;
  subtitle?: string;
  subtitle_key?: string;
  subtitle_vars?: Record<string, string | number>;
  data: Record<string, unknown>;
  confirm_token?: string;
  resolved?: boolean;
  resolution_note?: string;
  resolution_note_key?: string;
  resolution_note_vars?: Record<string, string | number>;
}

export interface CitedSourcePreview {
  url: string;
  title: string;
  domain?: string;
  snippet?: string;
  image_url?: string;
  favicon_url?: string;
  trust?: number | null;
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
  extras_json?: string | null;
  citation_check?: CitationCheckEntry[];
  cited_sources?: CitedSourcePreview[];
  brain_sources?: BrainCitationItem[];
  proposals?: BrainProposalItem[];
  findings?: FindingItem[];
  email_cards?: ChatEmailCard[];
  email_draft?: MailComposeDraft;
  answer_meta?: AnswerMeta;
  tools_used?: string[];
  images?: ChatImageAttachment[];
  staged_files?: StagedSettingsFile[];
  ui_cards?: SettingsUiCard[];
}

export interface AnswerMetaSourceTrust {
  system: number;
  personal: number | null;
  effective: number;
  category: string;
  family: string;
  why: string;
  conflict: boolean;
}

export interface AnswerMetaSource {
  idx: number;
  role: string;
  domain: string;
  url: string;
  title: string;
  snippet?: string;
  image_url?: string;
  trust: AnswerMetaSourceTrust;
}

export interface AnswerMeta {
  pipeline: string;
  question: string;
  scrubbed_query?: string;
  value?: string | null;
  confidence10: number | null;
  band: string;
  band_label: string;
  qtype: string;
  items: Array<[string, number]>;
  candidates?: Array<{ value: string; r: number; top_trust?: number; sources?: string[] }>;
  conflicts?: Array<{ value: string; domain: string; url: string; r?: number }>;
  divergence?: { system_value: string; system_confidence: number; system_band: string } | null;
  steps: string[];
  sources: AnswerMetaSource[];
  passages?: Array<{ domain: string; url: string; title: string; trust: number; text: string }>;
  models_used?: { planner: string; reader: string; analyzer: string };
  writer_fallback?: boolean;
  writer_problems?: string[];
  privacy_disclosure?: string;
  ms?: number;
}

export interface NewsArticleItem {
  article_id: string;
  url: string;
  domain: string;
  family: string;
  title: string;
  title_tr?: string;
  snippet: string;
  snippet_tr?: string;
  body_text: string;
  translated_text?: string | null;
  language: string;
  translation_source_lang?: string;
  translation_target_lang?: string;
  image_url: string;
  author: string;
  published_at: number;
  trust_system: number;
  trust_effective: number;
  category: string;
  conflict: boolean;
  wire_origin?: string | null;
}

export interface NewsFamilyBadge {
  family: string;
  domain: string;
  url: string;
  trust_system: number;
  trust_effective: number;
  category: string;
  conflict: boolean;
  language: string;
}

export interface NewsStoryCluster {
  cluster_id: string;
  headline: string;
  language?: string;
  translated_headline?: string;
  summary_md: string;
  translated_summary_md?: string;
  translation_source_lang?: string;
  translation_target_lang?: string;
  confidence10: number;
  band: string;
  band_label: string;
  independent_families: number;
  collapsed_mirrors: number;
  topic_tags: string[];
  brain_match_reasons: string[];
  outside_usual: boolean;
  story_rank: number;
  updated_at: number;
  is_read: boolean;
  has_conflict: boolean;
  lead_image: string;
  families: NewsFamilyBadge[];
  articles: NewsArticleItem[];
}

export interface NewsFollowedStoryUpdate {
  article_id: string;
  url: string;
  domain: string;
  family: string;
  title: string;
  title_tr?: string | null;
  snippet: string;
  snippet_tr?: string | null;
  translated_text?: string | null;
  translation_source_lang?: string | null;
  translation_target_lang?: string | null;
  language: string;
  image_url: string;
  published_at: number;
  added_at: number;
  trust_system: number;
  trust_effective: number;
  conflict: boolean;
  is_seed: boolean;
  is_new: boolean;
}

export interface NewsFollowedStory {
  story_id: string;
  title: string;
  summary_overview: string;
  summary_model: string;
  keywords: string[];
  seed_cluster_id: string;
  anchor_domain: string;
  lead_image: string;
  confidence10: number;
  band: string;
  band_label: string;
  independent_families: number;
  update_count: number;
  unread_updates: number;
  status: string;
  created_at: number;
  updated_at: number;
  last_synthesized_at: number;
  updates: NewsFollowedStoryUpdate[];
}

export interface NewsPerspectiveFraming {
  label: string;
  sources: Array<{
    url: string;
    domain: string;
    family: string;
    title: string;
    snippet: string;
    category: string;
    why: string;
    trust_system: number;
    trust_effective: number;
    conflict: boolean;
  }>;
  claims: string[];
}

export interface NewsPerspectiveMatrix {
  ok: boolean;
  cluster_id: string;
  headline: string;
  agreed: string[];
  framings: NewsPerspectiveFraming[];
  blind_spots: string[];
  syndicated_collapsed: number;
  system_counterfactual: string;
  analyzer_model: string;
  privacy_disclosure: string;
  cached?: boolean;
  error?: string;
}

export interface NewsSourceFeedItem {
  feed_id: string;
  feed_url: string;
  title: string;
  language: string;
  enabled: boolean;
  last_fetched_at: number;
  last_synced_at?: number;
  sync_status?: string;
  synced?: boolean;
  error_count: number;
}

export interface NewsSourceEntry {
  domain: string;
  category: string;
  rubric: string;
  family: string;
  system: number;
  personal: number | null;
  effective: number;
  band: string;
  band_label: string;
  why: string;
  scored: boolean;
  conflict: boolean;
  visits: number;
  feeds: NewsSourceFeedItem[];
}

export interface NewsCategoryEntry {
  id: string;
  score: number;
  rubric: string;
  what: string;
}

export interface NewsTopicItem {
  topic_id: string;
  name: string;
  keywords: string[];
  suppressed: boolean;
  watch_id?: string | null;
  last_checked_at: number;
  changed_at: number;
  badge_unread: boolean;
  last_value: string;
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
  favicon_url?: string | null;
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
  favicon_url?: string | null;
}

export interface TabNewWindowEvent {
  source_tab_id: string;
  url: string;
  background?: boolean;
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
  source?: string;
  label?: string;
  fix: string;
}

export interface HfCuratedCatalogEntry {
  repo_id: string;
  label: string;
  approx_size: string;
  gated: boolean;
  notes: string;
}

export interface HfRepoSearchEntry {
  repo_id: string;
  label: string;
  approx_size?: string;
  downloads?: number;
  likes?: number;
  gated?: boolean;
  private?: boolean;
  pipeline_tag?: string;
  notes?: string;
}

export interface HfDownloadJob {
  download_id: string;
  repo_id: string;
  target_dir: string;
  state: "queued" | "downloading" | "completed" | "error" | "cancelled";
  files_total: number;
  files_done: number;
  current_file: string;
  downloaded_bytes: number;
  total_bytes: number;
  pct: number;
  speed_bps: number;
  error: string;
  started_at: number;
  finished_at: number;
  use_as_chat: boolean;
  model_id: string;
}

export interface LocalCustomLlmEntry {
  id: string;
  label: string;
  repo_id?: string;
  path: string;
  source: string;
  ready: boolean;
  error?: string;
  size_bytes: number;
  added_at: number;
}

export interface LocalModelsSnapshot {
  models_dir: string;
  gemma_path: string;
  gemma_ready: boolean;
  local_llm_ready: boolean;
  planck_reader_source: "custom" | "local_sgs" | "shipped" | "missing" | string;
  planck_reader_path: string;
  planck13_source: "custom" | "local_sgs" | "shipped" | "missing" | string;
  planck13_path: string;
  hertz_reader_path: string;
  hertz_ready: boolean;
  custom_llms: LocalCustomLlmEntry[];
  overrides: Record<string, string>;
  hf_catalog: HfCuratedCatalogEntry[];
  hf_token_configured: boolean;
  hf_token_masked: string;
  downloads: HfDownloadJob[];
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
    effective_chat?: string;
    web_answer: string;
    reader: string;
    news_planner?: string;
    news_capture?: string;
    news_reader?: string;
    news_analyzer?: string;
    mail_classifier: string;
    brain_encoder: string;
  };
  cloud_providers: CloudProviderInfo[];
  local_models?: LocalModelsSnapshot | null;
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
  news?: {
    articles: number;
    clusters: number;
    feeds_enabled: number;
    topics: number;
    brain_stories?: number;
    followed_stories?: number;
    unread_story_updates?: number;
    sync_interval_seconds?: number;
    last_sync_at?: number;
    next_sync_at?: number;
    last_brain_sync_at?: number;
    syncing?: boolean;
  } | null;
  drives?: DrivesStatusResponse | null;
  profile?: {
    unlocked?: boolean;
    active_profile_id?: string | null;
    unlocking?: boolean;
  } | null;
  watch_badges?: string[];
  model_config?: ModelManagementConfig;
  digest_revision?: string;
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
  auth_type?: "password" | "oauth2";
  sync_days: number;
  last_sync_at: number;
  last_error: string;
  auth_failed?: boolean;
  message_count?: number;
  inbox_unread?: number;
  counts?: MailLaneCounts;
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
  entity?: string;
  reason?: string;
  image_url?: string;
  images?: string[];
  ts?: number;
  watch_id?: string;
  conversation_id?: string;
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
  uuid?: string;
  name: string;
  created_at: string;
  updated_at?: string;
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

export interface RedTeamReport {
  ok: boolean;
  passed: boolean;
  cases_run: number;
  cases_passed: number;
  failures?: Array<{ case_id: string; reason: string }>;
  checked_at?: string;
  summary: string;
}

export interface EvalCaseExpected {
  expected_tools?: string[];
  expected_task_agent?: string;
  require_send_gate?: boolean;
  min_citations?: number;
  max_flagged_citations?: number;
  must_contain?: string[];
  forbidden_substrings?: string[];
  min_answer_chars?: number;
}

export interface EvalTargetResult {
  target?: string;
  passed: boolean;
  summary: string;
  failures?: string[];
  tools_used?: string[];
  citations_ok?: number;
  citations_flagged?: number;
  tasks_count?: number;
}

export interface EvalCaseItem {
  eval_id: string;
  created_at: string;
  title: string;
  notes?: string;
  model_id: string;
  mode: { web_enabled: boolean; mail_enabled: boolean };
  user_msg: string;
  bad_assistant_answer?: string;
  sources?: Array<Record<string, unknown>>;
  expected?: EvalCaseExpected;
  _filename?: string;
  last_run?: {
    ran_at?: string;
    passed?: boolean;
    local_gemma?: EvalTargetResult;
    cloud?: EvalTargetResult;
  };
}

export interface EvalSuiteRunSummary {
  ok: boolean;
  total: number;
  passed: number;
  failed: number;
  ran_at?: string;
  results: Array<{
    eval_id: string;
    title: string;
    passed: boolean;
    ran_at: string;
    targets: {
      local_gemma?: EvalTargetResult;
      cloud?: EvalTargetResult;
    };
  }>;
}

export interface SkillProposalItem {
  proposal_id: string;
  pattern_key: string;
  status: string;
  reason: string;
  confidence: number;
  skill: {
    name: string;
    summary?: string;
    trigger_examples?: string[];
    required_context?: string[];
    step_graph?: Array<{
      id: string;
      primitive: string;
      summary?: string;
      send_gate?: boolean;
      mutating?: boolean;
      args?: Record<string, unknown>;
    }>;
    send_gate_steps?: string[];
    redteam?: RedTeamReport;
  };
}

export interface DomainRecipeItem {
  domain: string;
  control_key: string;
  selector: string;
  label: string;
  action_kind: string;
  sample_url: string;
  success_count: number;
  last_success_at: number;
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
  drives?: DrivesStatusResponse | null;
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
  skill_proposals?: SkillProposalItem[];
  domain_recipes_count?: number;
  recipes?: DomainRecipeItem[];
  evals?: EvalCaseItem[];
  evals_count?: number;
}

export type CommandRouteKind =
  | "open_url"
  | "url_and_question"
  | "ask_model"
  | "search_mail"
  | "search_drives"
  | "search_news"
  | "search_brain"
  | "run_command";

export type CommandBarActionId =
  | "home"
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
  model?: LocalModelId;
  auto_web?: boolean;
  auto_mail?: boolean;
  escalated?: boolean;
  escalation_reason?: string;
}

export interface RoutingDecisionInfo {
  query_type: string;
  model: LocalModelId;
  web_enabled: boolean;
  mail_enabled: boolean;
  escalated: boolean;
  reason?: string;
}

export interface RoutingPolicyRule {
  query_type: string;
  signal_count: number;
  retries: number;
  planck_switches: number;
  flagged_citations: number;
  errors: number;
  successes: number;
  recommended_model: string;
  escalated: boolean;
  auto_web: boolean;
  auto_mail: boolean;
  reason: string;
}

export interface RoutingPolicySummary {
  ok: boolean;
  total_signals: number;
  ready_cloud_model: string;
  rules: RoutingPolicyRule[];
  by_query_type: Record<string, RoutingPolicyRule>;
}

export interface HarnessSignalPayload {
  query_type?: string;
  prompt?: string;
  model_id: string;
  source_count?: number;
  chars_cut?: number;
  outcome_signal:
    | "retry"
    | "use_planck_instead"
    | "citations_flagged"
    | "citation_flagged_click"
    | "manual_model_override"
    | "manual_context_override"
    | "error"
    | "success";
  web_enabled?: boolean;
  mail_enabled?: boolean;
  target_model?: string;
}

export interface TaskStep {
  id: string;
  text: string;
  kind: "log" | "send_gate";
  status: "running" | "done" | "waiting_confirm" | "confirmed" | "cancelled" | "stopped";
  ts: number;
  action_summary?: string;
  action_payload?: Record<string, unknown>;
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

export interface ConvStreamState {
  convId: string;
  model: LocalModelId;
  text: string;
  status: string;
  phase: string;
  startedAt: number;
  steps: string[];
  lastUserPrompt: string;
}

export interface GoogleOAuthStatus {
  ok: boolean;
  unlocked: boolean;
  configured: boolean;
  signed_in: boolean;
  has_client_id: boolean;
  has_client_secret: boolean;
  has_refresh_token: boolean;
  masked_client_id: string;
  email: string;
  name: string;
  scopes: string[];
  expires_at: number;
  token_valid?: boolean;
  redirect_port: number;
  session?: {
    session_id: string;
    status: "pending" | "authorized" | "error" | "expired";
    email: string;
    error: string;
    gmail_connected: boolean;
    redirect_uri: string;
  } | null;
  error?: string;
}

export interface ActionProviderCategory {
  category_id: string;
  parent_group: string;
  label: string;
  description: string;
  is_builtin: boolean;
  sort_order: number;
}

export interface ActionProviderPreset {
  provider_slug: string;
  display_name: string;
  mode: "search_api" | "web_account";
  api_driver: string;
  domains: string[];
  url_template: string;
  vault_service: string;
  requires_key?: boolean;
}

export interface ActionProviderEntry {
  id: string;
  category_id: string;
  provider_slug: string;
  display_name: string;
  mode: "search_api" | "web_account";
  api_driver: string;
  domains: string[];
  url_template: string;
  vault_service: string;
  constraints_note: string;
  priority: number;
  enabled: boolean;
  auto_learned: boolean;
  requires_key: boolean;
  auth_status: "api_key" | "login" | "token_or_cookie" | "none" | "locked";
  auth_service: string;
  masked_auth_label: string;
  auth_fields: string[];
  auth_ready: boolean;
}

export interface ActionProviderSuggestion {
  suggestion_id: string;
  category_id: string;
  provider_slug: string;
  display_name: string;
  domain: string;
  url_template: string;
  reason: string;
  evidence_count: number;
  status: string;
  updated_at: number;
}

export interface ProviderRegistryState {
  ok: boolean;
  unlocked: boolean;
  profile_id: string | null;
  categories: ActionProviderCategory[];
  providers_by_category: Record<string, ActionProviderEntry[]>;
  presets: Record<string, ActionProviderPreset[]>;
  suggestions: ActionProviderSuggestion[];
  error?: string;
}

export interface I18nBundleEntry {
  text: string;
  one?: string;
  source_hash?: string;
  model?: string;
  updated_at?: number;
  custom?: boolean;
}

export interface I18nLocaleSummary {
  lang: string;
  label: string;
  dir: "ltr" | "rtl";
  model: string;
  total: number;
  translated: number;
  missing: number;
  stale: number;
  custom_count: number;
  updated_at: number;
}

export interface I18nStatusResponse {
  ok: boolean;
  active_locale: string;
  active_label: string;
  active_dir: "ltr" | "rtl";
  default_model: string;
  model_info: {
    model_id: string;
    local_only: boolean;
    provider_id: string;
    host: string;
    disclosure: string;
  };
  target: I18nLocaleSummary;
  locales: I18nLocaleSummary[];
  job: {
    running: boolean;
    lang: string;
    label: string;
    model: string;
    completed: number;
    total: number;
    current_batch: number;
    total_batches: number;
    error: string;
    updated_at: number;
  };
  suggested_languages?: Array<{
    code: string;
    name: string;
    native: string;
    rtl: boolean;
  }>;
  background_job?: {
    ok: boolean;
    started: boolean;
    already_running?: boolean;
    lang: string;
    model?: string;
  };
  error?: string;
}

export interface ContentLanguageInfo {
  code: string;
  name: string;
  native: string;
  rtl: boolean;
}

export interface ContentTranslationModelInfo {
  model_id: string;
  provider: string;
  is_cloud: boolean;
  tier_label: string;
  cost_hint: string;
  rank: number;
  mode: string;
  alternates?: string[];
}

export interface ContentTranslationConfig {
  ok: boolean;
  unlocked: boolean;
  profile_id: string | null;
  known_languages: string[];
  known_language_details: ContentLanguageInfo[];
  primary_language: string;
  primary_language_info: ContentLanguageInfo;
  model_preference: string;
  resolved_model: ContentTranslationModelInfo;
  auto_translate_mail: boolean;
  auto_translate_news: boolean;
  mail_include_promos_pings: boolean;
  mail_max_age_days: number;
  mail_max_recent: number;
  catalog: ContentLanguageInfo[];
  error?: string;
}

export interface PageTranslationBlock {
  id: string;
  text: string;
  viewport: boolean;
}

export interface TabTranslationState {
  status: "idle" | "translating" | "translated" | "allowed_notice" | "error";
  url?: string;
  sourceLang?: string;
  targetLang?: string;
  showingTranslated?: boolean;
  model?: string;
  blocksDone?: number;
  blocksTotal?: number;
  errorMsg?: string;
}

export type DriveProviderFilter = "all" | "gdrive" | "onedrive";
export type DriveFileTypeFilter =
  | "all"
  | "folder"
  | "doc"
  | "sheet"
  | "slide"
  | "pdf"
  | "image"
  | "other";

export interface DriveBreadcrumb {
  key: string;
  name: string;
  provider?: string;
}

export interface DriveItem {
  item_key: string;
  navigate_key: string;
  provider: "gdrive" | "onedrive" | "shared";
  remote_id?: string;
  name: string;
  is_folder: boolean;
  is_shortcut: boolean;
  mime_type: string;
  file_category: string;
  resolved_path: string;
  path_crumbs: DriveBreadcrumb[];
  owner_name: string;
  owner_email: string;
  is_me: boolean;
  modified_at: number;
  size_bytes: number;
  web_url: string;
  core_summary: string;
  brain_slug: string;
  indexed: boolean;
}

export interface DriveOwnerFacet {
  value: string;
  label: string;
  email: string;
  name: string;
  is_me: boolean;
  count: number;
}

export interface DriveListResponse {
  ok: boolean;
  unlocked: boolean;
  folder_key: string;
  parent_key: string | null;
  breadcrumbs: DriveBreadcrumb[];
  items: DriveItem[];
  facets: {
    providers: Array<{ id: string; count: number }>;
    file_types: Record<string, number>;
    owners: DriveOwnerFacet[];
  };
  scope: "folder" | "search" | "filtered" | "locked";
}

export interface DriveProviderStatus {
  provider: "gdrive" | "onedrive";
  connected: boolean;
  configured: boolean;
  signed_in_gmail_only?: boolean;
  masked_client_id?: string;
  tenant_id?: string;
  email: string;
  name: string;
  total_files: number;
  indexed_docs: number;
  last_synced_at: number;
  status: string;
  last_error: string;
  session?: {
    session_id: string;
    status: string;
    email: string;
    error: string;
    redirect_uri: string;
  } | null;
}

export interface DrivesStatusResponse {
  ok: boolean;
  unlocked: boolean;
  syncing: boolean;
  indexing: boolean;
  total_files: number;
  indexed_docs: number;
  last_synced_at: number;
  google: DriveProviderStatus;
  onedrive: DriveProviderStatus;
}

export interface DriveCreateTarget {
  id: string;
  provider: "gdrive" | "onedrive";
  provider_label: string;
  label: string;
  url: string;
}

export interface DriveNavSnapshot {
  folderKey: string;
  provider: DriveProviderFilter;
  fileType: DriveFileTypeFilter;
  owner: string;
  query: string;
}

export interface TelemetryInstanceMeta {
  schema_version: number;
  instance_id: string;
  created_at?: string;
  updated_at?: string;
  app_version: string;
  os: string;
  arch?: string;
  hosted_sync_enabled: boolean;
  hosted_endpoint: string;
  last_sync_at?: string;
  last_sync_error?: string;
  last_sync_count?: number;
}

export interface TelemetrySummaryResponse {
  ok: boolean;
  dev_dir: string;
  instance: TelemetryInstanceMeta;
  totals: {
    total_events: number;
    error_events: number;
    unexported_events: number;
  };
  by_subsystem: Array<{
    subsystem: string;
    count: number;
    errors: number;
    avg_duration_ms: number | null;
  }>;
  recent_evals: Array<{
    ts: string;
    run_type: string;
    cases_total: number;
    passed_count: number;
    failed_count: number;
    passed: number;
  }>;
}

export interface TelemetrySyncResponse {
  ok: boolean;
  skipped?: boolean;
  status?: number;
  uploaded?: number;
  through_seq?: number;
  remaining?: number;
  error?: string;
  instance?: TelemetryInstanceMeta;
}
