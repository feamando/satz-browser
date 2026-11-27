import { applyUiLocalePreferences, formatLocaleRelativeTime, normalizeLangTag, t } from "./i18n";

export type UnlockStepId = "vault_brain" | "mail" | "news" | "drives" | "digest";
export type UnlockStepStatus = "pending" | "running" | "done" | "error";

export interface UnlockProgressStep {
  id: UnlockStepId;
  label: string;
  status: UnlockStepStatus;
  detail?: string;
}

import type {
  AgentTaskCard,
  AnswerMeta,
  BookmarkItem,
  BrainCitationItem,
  BrainProposalItem,
  BrainSearchResponse,
  BrowserTab,
  ChatEmailCard,
  ChatImageAttachment,
  CitedSourcePreview,
  CommandBarActionId,
  CommandBarRoute,
  ContentTranslationConfig,
  ConvStreamState,
  Conversation,
  ConversationDetail,
  DigestEntry,
  DoctorRoleEntry,
  DriveBreadcrumb,
  DriveCreateTarget,
  DriveFileTypeFilter,
  DriveItem,
  DriveNavSnapshot,
  DriveOwnerFacet,
  DriveProviderFilter,
  DrivesStatusResponse,
  EvalSuiteRunSummary,
  FindingItem,
  GoogleOAuthStatus,
  HfDownloadJob,
  HfRepoSearchEntry,
  I18nStatusResponse,
  KnowledgeSummary,
  LocalModelId,
  MailAccountItem,
  MailComposeDraft,
  MailLaneCounts,
  MailPreset,
  ModelManagementConfig,
  NewsCategoryEntry,
  NewsFollowedStory,
  NewsLane,
  NewsPerspectiveMatrix,
  NewsSourceEntry,
  NewsStoryCluster,
  NewsTopicItem,
  ProviderRegistryState,
  RoutingDecisionInfo,
  SettingsLane,
  SettingsUiCard,
  StagedSettingsFile,
  RoutingPolicySummary,
  SidecarErrorEntry,
  SidecarHealth,
  SourceStatEntry,
  TabTranslationState,
  WatchItem,
} from "./types";

export type UiThemePref = "system" | "light" | "dark";
export type UiLayoutPref = "floating" | "flush";

const THEME_STORAGE_KEY = "satz.ui.theme";
const LAYOUT_STORAGE_KEY = "satz.ui.layout";

export function getUiThemePref(): UiThemePref {
  try {
    const v = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    // Ignore storage access errors
  }
  return "system";
}

export function setUiThemePref(pref: UiThemePref): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, pref);
  } catch {
    // Ignore storage access errors
  }
  applyUiPreferences();
}

export function getUiLayoutPref(): UiLayoutPref {
  try {
    const v = window.localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (v === "flush" || v === "floating") return v;
  } catch {
    // Ignore storage access errors
  }
  return "floating";
}

export function setUiLayoutPref(pref: UiLayoutPref): void {
  try {
    window.localStorage.setItem(LAYOUT_STORAGE_KEY, pref);
  } catch {
    // Ignore storage access errors
  }
  applyUiPreferences();
}

export type RailAccordionKey = "pinned" | "conversations" | "sources" | "archived";

const RAIL_ACCORDION_KEY = "satz.ui.railAccordion";
const AGENT_FOLDED_KEY = "satz.ui.agentFolded";
const ONBOARDING_TOUR_DONE_KEY = "satz.ui.onboardingTourDone";

export type OnboardingStep = "welcome" | "models" | null;
export type OnboardingMode = "create" | "upload" | "demo";
export type OnboardingModelTab = "cloud" | "local";

export function getOnboardingTourDonePref(): boolean {
  try {
    return window.localStorage.getItem(ONBOARDING_TOUR_DONE_KEY) === "1";
  } catch {
    return false;
  }
}

export function setOnboardingTourDonePref(done: boolean): void {
  try {
    if (done) {
      window.localStorage.setItem(ONBOARDING_TOUR_DONE_KEY, "1");
    } else {
      window.localStorage.removeItem(ONBOARDING_TOUR_DONE_KEY);
    }
  } catch {
    // Ignore storage access errors
  }
}

const DEFAULT_RAIL_ACCORDION: Record<RailAccordionKey, boolean> = {
  pinned: true,
  conversations: true,
  sources: true,
  archived: false,
};

export function getRailAccordionPref(): Record<RailAccordionKey, boolean> {
  try {
    const raw = window.localStorage.getItem(RAIL_ACCORDION_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<Record<RailAccordionKey, boolean>>;
      return {
        pinned: parsed.pinned ?? DEFAULT_RAIL_ACCORDION.pinned,
        conversations: parsed.conversations ?? DEFAULT_RAIL_ACCORDION.conversations,
        sources: parsed.sources ?? DEFAULT_RAIL_ACCORDION.sources,
        archived: parsed.archived ?? DEFAULT_RAIL_ACCORDION.archived,
      };
    }
  } catch {
    // Ignore storage access errors
  }
  return { ...DEFAULT_RAIL_ACCORDION };
}

export function setRailAccordionPref(acc: Record<RailAccordionKey, boolean>): void {
  try {
    window.localStorage.setItem(RAIL_ACCORDION_KEY, JSON.stringify(acc));
  } catch {
    // Ignore storage access errors
  }
}

export function getUiAgentFoldedPref(): boolean {
  try {
    return window.localStorage.getItem(AGENT_FOLDED_KEY) === "1";
  } catch {
    return false;
  }
}

export function setUiAgentFoldedPref(folded: boolean): void {
  try {
    window.localStorage.setItem(AGENT_FOLDED_KEY, folded ? "1" : "0");
  } catch {
    // Ignore storage access errors
  }
}

export function getResolvedTheme(): "light" | "dark" {
  const pref = getUiThemePref();
  if (pref === "light" || pref === "dark") return pref;
  if (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  ) {
    return "dark";
  }
  return "light";
}

export function applyUiPreferences(): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  const theme = getUiThemePref();
  const layout = getUiLayoutPref();
  if (theme === "light" || theme === "dark") {
    root.setAttribute("data-theme", theme);
  } else {
    root.removeAttribute("data-theme");
  }
  root.setAttribute("data-layout", layout);
  applyUiLocalePreferences();
}

const FAVICONS_STORAGE_KEY = "satz.siteFavicons";

function loadStoredSiteFavicons(): Record<string, string> {
  try {
    if (typeof window === "undefined") return {};
    const raw = window.localStorage.getItem(FAVICONS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (!parsed || typeof parsed !== "object") return {};
    const clean: Record<string, string> = {};
    for (const [k, v] of Object.entries(parsed)) {
      if (
        typeof v === "string" &&
        (v.startsWith("data:image/") ||
          v.startsWith("https://") ||
          v.startsWith("http://"))
      ) {
        clean[k] = v;
      }
    }
    return clean;
  } catch {
    return {};
  }
}

function persistStoredSiteFavicons(map: Record<string, string>): void {
  try {
    if (typeof window === "undefined") return;
    const entries = Object.entries(map);
    const trimmed =
      entries.length > 200 ? entries.slice(entries.length - 200) : entries;
    window.localStorage.setItem(
      FAVICONS_STORAGE_KEY,
      JSON.stringify(Object.fromEntries(trimmed))
    );
  } catch {
    // Ignore storage quota or access errors
  }
}

export const IS_MAC =
  typeof navigator !== "undefined" &&
  (/Mac|iPod|iPhone|iPad/i.test(navigator.platform) ||
    /Macintosh|Mac OS/i.test(navigator.userAgent));

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
  railAccordion: Record<RailAccordionKey, boolean>;
  telemetryOpen: boolean;
  profileMenuOpen: boolean;
  composerModelMenuOpen: boolean;
  commandModelMenuOpen: "start" | "overlay" | null;
  composerContextExpanded: boolean;
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
  drivesContextEnabled: boolean;
  streamsByConv: Record<string, ConvStreamState>;
  lastPromptByConv: Record<string, string>;
  lastImagesByConv: Record<string, ChatImageAttachment[]>;
  pendingChatImagesByConv: Record<string, ChatImageAttachment[]>;
  pendingStagedFilesByConv: Record<string, StagedSettingsFile[]>;
  messageUiCards: Record<string, SettingsUiCard[]>;
  settingsActiveLane: SettingsLane;
  chatImagePreview: ChatImageAttachment | null;
  chatImageNotice: string;
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
  siteFavicons: Record<string, string>;
  failedFaviconSrcs: Record<string, true>;
  messageProposals: Record<string, BrainProposalItem[]>;
  messageFindings: Record<string, FindingItem[]>;
  messageBrainSources: Record<string, BrainCitationItem[]>;
  messageCitedSources: Record<string, CitedSourcePreview[]>;
  urlPreviews: Record<string, CitedSourcePreview>;
  chatLastRenderedConvId: string | null;
  chatPinToBottom: boolean;
  expandedDebugMessages: Record<string, boolean>;
  revealedPasswords: Record<string, string>;
  sourceStats: Record<string, SourceStatEntry>;
  showErrorLog: boolean;
  uiErrors: SidecarErrorEntry[];
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
  mailMessageHtml: Record<
    string,
    {
      html: string;
      csp: string;
      translated_html?: string;
      translation_source_lang?: string;
      translation_target_lang?: string;
    }
  >;
  mailMessageShowOriginal: Record<string, boolean>;
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
  mailComposeDrafts: Record<string, MailComposeDraft>;
  mailComposeModalOpen: boolean;
  mailComposeModalDraft: MailComposeDraft | null;
  inlineChatDrafts: Record<string, MailComposeDraft>;
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
  googleOAuthStatus: GoogleOAuthStatus | null;
  googleOAuthSessionId: string | null;
  googleOAuthMessage: string;
  modelConfig: ModelManagementConfig | null;
  modelConfigStatusMsg: string;
  hfSearchQuery: string;
  hfSearchResults: HfRepoSearchEntry[];
  hfInspectResult: {
    repo_id: string;
    gated?: boolean;
    total_bytes?: number;
    file_count?: number;
    error?: string;
  } | null;
  hfDownloads: HfDownloadJob[];
  hfRepoDraft: string;
  localModelSlotDraft: string;
  localModelPathDraft: string;
  appUpdateStatus: {
    currentVersion: string;
    checking: boolean;
    installing: boolean;
    availableVersion: string | null;
    notes: string;
    progressPct: number;
    message: string;
    error: string;
  };
  providerRegistry: ProviderRegistryState | null;
  providerStatusMsg: string;
  providerFilterGroup: "all" | "search" | "maps" | "commerce" | "custom";
  providerExpandedCategoryId: string;
  providerCredOpenId: string;
  providerInferredDraft: Record<
    string,
    {
      display_name: string;
      domains: string[];
      url_template: string;
      mode: "search_api" | "web_account";
      api_driver: string;
      vault_service: string;
      auth_status: string;
      masked_auth_label: string;
      auth_ready: boolean;
    }
  >;
  profilePromptOpen: boolean;
  profilePromptDismissed: boolean;
  onboardingStep: OnboardingStep;
  onboardingMode: OnboardingMode;
  onboardingModelTab: OnboardingModelTab;
  onboardingCloudProviderId: string;
  onboardingLocalRepoId: string;
  onboardingValidationMsg: string;
  onboardingDemoMode: boolean;
  onboardingTourStep: number | null;
  profileUnlocking: boolean;
  profileUnlockLabel: string;
  profileImportDraft: {
    filename: string;
    bundleB64: string;
    sizeBytes: number;
    needLocalPin?: boolean;
  } | null;
  profileExportBusyId: string | null;
  postUnlockLoading: boolean;
  postUnlockLabel: string;
  postUnlockTitle: string;
  unlockSteps: UnlockProgressStep[];
  newsActiveLane: NewsLane;
  newsStories: NewsStoryCluster[];
  newsFollowedStories: NewsFollowedStory[];
  newsPerspectivesStories: NewsStoryCluster[];
  newsPerspectivesDetail: ConversationDetail | null;
  newsPerspectivesStream: ConvStreamState | null;
  newsSettingsManualAcc: { topics: boolean; sources: boolean };
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
  newsPendingTopicKeys: Record<string, boolean>;
  newsPendingFeedKeys: Record<string, boolean>;
  newsPendingTrustDomains: Record<string, boolean>;
  newsExploreMode: boolean;
  newsLoading: boolean;
  newsStatusMessage: string;
  newsReaderArticleId: string | null;
  newsReaderShowOriginal: boolean;
  newsStoryShowOriginal: Record<string, boolean>;
  newsStoryMenuId: string | null;
  contentTranslationConfig: ContentTranslationConfig | null;
  contentTranslationStatusMsg: string;
  tabTranslationState: Record<string, TabTranslationState>;
  messageAnswerMeta: Record<string, AnswerMeta>;
  expandedExplainMessages: Record<string, boolean>;
  expandedInDepthMessages: Record<string, boolean>;
  routingPolicy: RoutingPolicySummary | null;
  routingNotice: string;
  savedEvalByMsgId: Record<string, string>;
  evalSuiteRun: EvalSuiteRunSummary | null;
  evalRunning: boolean;
  evalStatusMsg: string;
  redteamAuditSummary: string;
  i18nStatus: I18nStatusResponse | null;
  i18nTranslating: boolean;
  i18nTranslateCompleted: number;
  i18nTranslateTotal: number;
  i18nStatusMsg: string;
  i18nCustomEditorOpen: boolean;
  i18nOverrideFilter: string;
  drivesStatus: DrivesStatusResponse | null;
  drivesFolderKey: string;
  drivesParentKey: string | null;
  drivesBreadcrumbs: DriveBreadcrumb[];
  drivesItems: DriveItem[];
  drivesProviderFilter: DriveProviderFilter;
  drivesFileTypeFilter: DriveFileTypeFilter;
  drivesOwnerFilter: string;
  drivesSearchQuery: string;
  drivesScope: "folder" | "search" | "filtered" | "locked";
  drivesFacets: {
    providers: Array<{ id: string; count: number }>;
    file_types: Record<string, number>;
    owners: DriveOwnerFacet[];
  };
  drivesCreateTargets: DriveCreateTarget[];
  drivesCreateMenuOpen: boolean;
  drivesAccountsOpen: boolean;
  drivesNavStack: DriveNavSnapshot[];
  drivesLoading: boolean;
  drivesSyncing: boolean;
  drivesStatusMessage: string;
}

export const state: AppState = {
  conversations: [],
  bookmarks: [],
  activeDetail: null,
  activeTabId: "chat",
  compareTabIds: [],
  compareMode: false,
  agentRailOpen: !getUiAgentFoldedPref(),
  showArchived: getRailAccordionPref().archived,
  railAccordion: getRailAccordionPref(),
  telemetryOpen: false,
  profileMenuOpen: false,
  composerModelMenuOpen: false,
  commandModelMenuOpen: null,
  composerContextExpanded: false,
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
  drivesContextEnabled: false,
  streamsByConv: {},
  lastPromptByConv: {},
  lastImagesByConv: {},
  pendingChatImagesByConv: {},
  pendingStagedFilesByConv: {},
  messageUiCards: {},
  settingsActiveLane: "profiles",
  chatImagePreview: null,
  chatImageNotice: "",
  siteFavicons: loadStoredSiteFavicons(),
  failedFaviconSrcs: {},
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
  profilePromptOpen: false,
  profilePromptDismissed: false,
  onboardingStep: null,
  onboardingMode: "create",
  onboardingModelTab: "cloud",
  onboardingCloudProviderId: "gemini",
  onboardingLocalRepoId: "google/gemma-4-E4B-it",
  onboardingValidationMsg: "",
  onboardingDemoMode: false,
  onboardingTourStep: null,
  profileUnlocking: false,
  profileUnlockLabel: "",
  profileImportDraft: null,
  profileExportBusyId: null,
  postUnlockLoading: false,
  postUnlockLabel: "",
  postUnlockTitle: "",
  unlockSteps: [],
  tabHasPasswordField: {},
  tabCanFillLogin: {},
  messageProposals: {},
  messageFindings: {},
  messageBrainSources: {},
  messageCitedSources: {},
  urlPreviews: {},
  chatLastRenderedConvId: null,
  chatPinToBottom: true,
  expandedDebugMessages: {},
  revealedPasswords: {},
  sourceStats: {},
  showErrorLog: false,
  uiErrors: [],
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
  mailMessageShowOriginal: {},
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
  mailComposeModalOpen: false,
  mailComposeModalDraft: null,
  inlineChatDrafts: {},
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
    providers: false,
    mail: false,
    drives: false,
    indexing: false,
    translation: false,
  },
  contentTranslationConfig: null,
  contentTranslationStatusMsg: "",
  tabTranslationState: {},
  modelConfig: null,
  modelConfigStatusMsg: "",
  hfSearchQuery: "",
  hfSearchResults: [],
  hfInspectResult: null,
  hfDownloads: [],
  hfRepoDraft: "",
  localModelSlotDraft: "chat_llm",
  localModelPathDraft: "",
  appUpdateStatus: {
    currentVersion: "0.5.0",
    checking: false,
    installing: false,
    availableVersion: null,
    notes: "",
    progressPct: 0,
    message: "",
    error: "",
  },
  providerRegistry: null,
  providerStatusMsg: "",
  providerFilterGroup: "all",
  providerExpandedCategoryId: "",
  providerCredOpenId: "",
  providerInferredDraft: {},
  routingPolicy: null,
  routingNotice: "",
  newsActiveLane: "stories",
  newsStories: [],
  newsFollowedStories: [],
  newsPerspectivesStories: [],
  newsPerspectivesDetail: null,
  newsPerspectivesStream: null,
  newsSettingsManualAcc: { topics: true, sources: true },
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
  newsPendingTopicKeys: {},
  newsPendingFeedKeys: {},
  newsPendingTrustDomains: {},
  newsExploreMode: false,
  newsLoading: false,
  newsStatusMessage: "",
  newsReaderArticleId: null,
  newsReaderShowOriginal: false,
  newsStoryShowOriginal: {},
  newsStoryMenuId: null,
  googleOAuthStatus: null,
  googleOAuthSessionId: null,
  googleOAuthMessage: "",
  messageAnswerMeta: {},
  expandedExplainMessages: {},
  expandedInDepthMessages: {},
  savedEvalByMsgId: {},
  evalSuiteRun: null,
  evalRunning: false,
  evalStatusMsg: "",
  redteamAuditSummary: "",
  i18nStatus: null,
  i18nTranslating: false,
  i18nTranslateCompleted: 0,
  i18nTranslateTotal: 0,
  i18nStatusMsg: "",
  i18nCustomEditorOpen: false,
  i18nOverrideFilter: "",
  drivesStatus: null,
  drivesFolderKey: "",
  drivesParentKey: null,
  drivesBreadcrumbs: [{ key: "", name: "Drives" }],
  drivesItems: [],
  drivesProviderFilter: "all",
  drivesFileTypeFilter: "all",
  drivesOwnerFilter: "all",
  drivesSearchQuery: "",
  drivesScope: "folder",
  drivesFacets: { providers: [], file_types: {}, owners: [] },
  drivesCreateTargets: [],
  drivesCreateMenuOpen: false,
  drivesAccountsOpen: false,
  drivesNavStack: [],
  drivesLoading: false,
  drivesSyncing: false,
  drivesStatusMessage: "",
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

export function classifyQueryTypeClient(
  prompt: string,
  sourceCount = 0,
  webEnabled = false,
  mailEnabled = false
): string {
  const low = (prompt || "").trim().toLowerCase();
  if (/^(?:https?:\/\/)?[a-z0-9.-]+\.[a-z]{2,}(?:\/|\s|$)/i.test(low)) {
    return "url_or_navigation";
  }
  if (
    /\b(email|emails|mail|mails|inbox|unread|outbox|reply\s+to|sender|newsletter|unsubscribe|order|tracking|paket|bestellung|voucher)\b/.test(
      low
    ) ||
    (mailEnabled && !webEnabled && sourceCount === 0)
  ) {
    return "mail_query";
  }
  if (
    /\b(compare|comparison|versus|vs\.?|pros\s+and\s+cons|trade-?off|research|deep\s+dive|synthesize|difference\s+between|across\s+all|multi-?source)\b/.test(
      low
    ) ||
    sourceCount >= 4
  ) {
    return "comparison_research";
  }
  if (
    /\b(code|bug|debug|traceback|stack\s*trace|typescript|python|rust|sql|regex|function|compile|refactor|api|json|error|exception|syntax)\b/.test(
      low
    )
  ) {
    return "coding_technical";
  }
  if (
    webEnabled ||
    /\b(today|latest|current|recent|news|price|cost|weather|stock|exchange\s+rate|score|schedule|release\s+date|202\d|online|web\s+search)\b/.test(
      low
    )
  ) {
    return "factual_web";
  }
  if (
    sourceCount > 0 ||
    /\b(this\s+page|this\s+tab|this\s+article|this\s+site|summarize|summary|tldr)\b/.test(
      low
    )
  ) {
    return "tab_qa";
  }
  return "general_chat";
}

export function resolveLearnedRouteForPrompt(
  prompt: string,
  selectedModel: LocalModelId,
  webEnabled: boolean,
  mailEnabled: boolean,
  sourceCount = 0,
  userOverrodeModel = false
): RoutingDecisionInfo {
  const queryType = classifyQueryTypeClient(
    prompt,
    sourceCount,
    webEnabled,
    mailEnabled
  );
  const rule = state.routingPolicy?.by_query_type?.[queryType];
  let effModel: LocalModelId = selectedModel || "gemma-4-e4b";
  let effWeb = Boolean(webEnabled);
  let effMail = Boolean(mailEnabled);
  let escalated = false;
  let reason = "";

  const isLocal =
    effModel === "gemma-4-e4b" ||
    effModel === "hertz (reader)" ||
    effModel === "planck (reader)";

  if (rule) {
    if (!userOverrodeModel && isLocal && rule.escalated && rule.recommended_model) {
      const available = getAvailableModelsForPicker();
      const cand = rule.recommended_model as LocalModelId;
      if (
        cand === "planck3 (web)" ||
        available.some((m) => m.id === cand)
      ) {
        effModel = cand;
        escalated = true;
      }
    }
    if (rule.auto_web && !effWeb) {
      effWeb = true;
      escalated = true;
    }
    if (rule.auto_mail && !effMail) {
      effMail = true;
      escalated = true;
    }
      if (escalated) {
        reason = rule.reason || t("cmd.learned_policy", { queryType });
      }
  }

  return {
    query_type: queryType,
    model: effModel,
    web_enabled: effWeb,
    mail_enabled: effMail,
    escalated,
    reason,
  };
}

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
  const baseWeb = Boolean(opts?.webSearchEnabled ?? state.webSearchEnabled);
  const baseModel = opts?.selectedModel ?? state.selectedModel;
  const activeTabCount = getActiveTabSources(state.activeDetail).length;
  const learned = trimmed
    ? resolveLearnedRouteForPrompt(
        trimmed,
        baseModel,
        baseWeb,
        state.mailContextEnabled,
        activeTabCount,
        state.userOverrodeModelInSession
      )
    : null;
  const model = learned?.model ?? baseModel;
  const webEnabled = learned?.web_enabled ?? baseWeb;
  const mailAutoEnabled = Boolean(learned?.mail_enabled ?? false);
  const isEscalated = Boolean(learned?.escalated);
  const escReason = learned?.reason ?? "";
  const isCloud =
    model.startsWith("gemini:") ||
    model.startsWith("anthropic:") ||
    model.startsWith("openai:") ||
    model.startsWith("mistral:");
  const usesWeb = webEnabled || model === "planck3 (web)";
  const leavesMachine = isCloud || usesWeb;
  const modelPrivacy = isCloud
    ? usesWeb
      ? t("privacy.cloud_web")
      : t("privacy.cloud_provider", { provider: model.split(":")[0] })
    : usesWeb
      ? t("privacy.web_ddg")
      : t("privacy.local_only");

  if (!trimmed) {
    return [
      {
        kind: "run_command",
        label: t("cmd.run_new_conv"),
        destination: t("cmd.dest_cmd", { id: "new_conversation" }),
        privacy: t("privacy.local_only"),
        leaves_machine: false,
        command_id: "new_conversation",
      },
      {
        kind: "search_brain",
        label: t("cmd.open_brain"),
        destination: t("cmd.dest_brain"),
        privacy: t("privacy.local_only"),
        leaves_machine: false,
        query: "",
      },
      {
        kind: "search_mail",
        label: t("cmd.open_mail"),
        destination: t("cmd.dest_mail"),
        privacy: t("privacy.local_only"),
        leaves_machine: false,
        query: "",
      },
      {
        kind: "run_command",
        label: t("cmd.run_lock"),
        destination: t("cmd.dest_cmd", { id: "lock" }),
        privacy: t("privacy.local_only"),
        leaves_machine: false,
        command_id: "lock",
      },
    ];
  }

  const makeAskRoute = (q: string): CommandBarRoute => {
    const label =
      isEscalated && escReason
        ? t("cmd.ask_model_auto", { model, query: q, reason: escReason })
        : t("cmd.ask_model", { model, query: q });
    const route: CommandBarRoute = {
      kind: "ask_model",
      label,
      destination: t("cmd.dest_chat", { model }),
      privacy: modelPrivacy,
      leaves_machine: leavesMachine,
      question: q,
    };
    if (
      isEscalated ||
      model !== baseModel ||
      webEnabled !== baseWeb ||
      mailAutoEnabled
    ) {
      route.model = model;
      route.auto_web = webEnabled;
      route.auto_mail = mailAutoEnabled;
      route.escalated = isEscalated;
      route.escalation_reason = escReason;
    }
    return route;
  };

  const makeBrainRoute = (q: string): CommandBarRoute => ({
    kind: "search_brain",
    label: t("cmd.search_brain", { query: q }),
    destination: t("cmd.dest_brain_full"),
    privacy: t("privacy.local_only"),
    leaves_machine: false,
    query: q,
  });

  const makeMailRoute = (q: string): CommandBarRoute => ({
    kind: "search_mail",
    label: t("cmd.search_mail", { query: q }),
    destination: t("cmd.dest_mail_fts"),
    privacy: t("privacy.local_only"),
    leaves_machine: false,
    query: q,
  });

  const makeNewsRoute = (q: string): CommandBarRoute => ({
    kind: "search_news",
    label: t("cmd.news_intel", { query: q }),
    destination: "satz news (read -> weigh -> write)",
    privacy: usesWeb ? t("privacy.news_web") : t("privacy.news_local"),
    leaves_machine: usesWeb,
    query: q,
  });

  const makeDrivesRoute = (q: string): CommandBarRoute => ({
    kind: "search_drives",
    label: q ? t("cmd.search_drives", { query: q }) : t("cmd.open_drives"),
    destination: t("cmd.dest_drives"),
    privacy: t("privacy.local_only"),
    leaves_machine: false,
    query: q,
  });

  // 1. Exact command match
  const cmdNorm = trimmed.toLowerCase().replace(/^\//, "").trim();
  const matchedCmd = COMMAND_ALIASES[cmdNorm];
  if (matchedCmd) {
    return [
      {
        kind: "run_command",
        label: t("cmd.run_cmd_name", { cmd: cmdNorm }),
        destination: t("cmd.dest_cmd", { id: matchedCmd }),
        privacy: t("privacy.local_only"),
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
        label: t("cmd.open_url", { url: parsed.url }),
        destination: dom,
        privacy: t("privacy.loads_domain", { domain: dom }),
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
      ? t("privacy.loads_domain_web", { domain: dom })
      : t("privacy.loads_domain_local", { domain: dom });
    return [
      {
        kind: "url_and_question",
        label: t("cmd.open_and_ask", {
          domain: dom,
          model,
          question: parsed.question,
        }),
        destination: `${dom} + ${model}`,
        privacy: priv,
        leaves_machine: true,
        url: parsed.url,
        question: parsed.question,
      },
      {
        kind: "open_url",
        label: t("cmd.open_url", { url: parsed.url }),
        destination: dom,
        privacy: t("privacy.loads_domain", { domain: dom }),
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

  // 3b. Explicit drives prefix (`drive: ...`, `drives: ...`, `files: ...`, `search drives ...`)
  const drivesPrefixMatch = trimmed.match(
    /^(?:(?:drive|drives|files)\s*:\s*|search\s+(?:drives?|files)\s+(?:for\s+)?|in\s+(?:drives?|files)\s+)(.+)$/i
  );
  if (drivesPrefixMatch) {
    const q = drivesPrefixMatch[1].trim();
    return [makeDrivesRoute(q), makeBrainRoute(q), makeAskRoute(trimmed)];
  }
  if (/^(?:open\s+)?(?:drives?|my\s+files|google\s+drive|onedrive)$/i.test(trimmed)) {
    return [makeDrivesRoute(""), makeBrainRoute(trimmed), makeAskRoute(trimmed)];
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

    if (state.activeDetail?.conversation.origin === "drives") {
      return [
        makeDrivesRoute(trimmed),
        makeAskRoute(trimmed),
        makeBrainRoute(trimmed),
        makeMailRoute(trimmed),
      ];
    }
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
  return formatLocaleRelativeTime(isoOrEpoch);
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
      summary: t("err.gemma_timeout"),
      rawDetail: cleanRaw,
    };
  }
  if (
    lower.includes("not found") &&
    (lower.includes("gemma") || lower.includes("checkpoint") || lower.includes("model"))
  ) {
    return {
      summary: t("err.gemma_missing"),
      rawDetail: cleanRaw,
    };
  }
  if (lower.includes("401") || lower.includes("403") || lower.includes("forbidden")) {
    return {
      summary: t("err.fetch_forbidden"),
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
      summary: t("err.sidecar_unreachable"),
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

export function getOriginFromUrl(rawUrl: string): string {
  try {
    const u = new URL(normalizeUrl(rawUrl));
    if (u.protocol !== "http:" && u.protocol !== "https:") return "";
    return u.origin;
  } catch {
    return "";
  }
}

export function isSafeFaviconSrc(src: string | null | undefined): src is string {
  if (!src) return false;
  const s = src.trim();
  return (
    s.startsWith("data:image/") ||
    s.startsWith("https://") ||
    s.startsWith("http://")
  );
}

export function cacheSiteFavicon(rawUrl: string, faviconUrl: string): boolean {
  if (!isSafeFaviconSrc(faviconUrl)) return false;
  const cleanUrl = (rawUrl || "").trim();
  const origin = getOriginFromUrl(cleanUrl);
  let changed = false;
  if (cleanUrl && state.siteFavicons[cleanUrl] !== faviconUrl) {
    state.siteFavicons[cleanUrl] = faviconUrl;
    changed = true;
  }
  if (origin) {
    const existingOrigin = state.siteFavicons[origin] ?? "";
    if (
      !existingOrigin ||
      faviconUrl.startsWith("data:image/") ||
      !existingOrigin.startsWith("data:image/")
    ) {
      if (existingOrigin !== faviconUrl) {
        state.siteFavicons[origin] = faviconUrl;
        changed = true;
      }
    }
  }
  if (changed) {
    persistStoredSiteFavicons(state.siteFavicons);
  }
  return changed;
}

export function getFaviconDisplaySrc(
  rawUrl: string,
  explicitFaviconUrl?: string | null
): string | null {
  const low = (rawUrl || "").trim().toLowerCase();
  if (
    !low ||
    low === "about:blank" ||
    low.startsWith("satzmail:") ||
    low.startsWith("javascript:") ||
    low.startsWith("file:")
  ) {
    return null;
  }
  const origin = getOriginFromUrl(rawUrl);
  const candidates = [
    explicitFaviconUrl,
    state.siteFavicons[rawUrl],
    origin ? state.siteFavicons[origin] : null,
    origin ? `${origin}/favicon.ico` : null,
  ];
  for (const cand of candidates) {
    if (isSafeFaviconSrc(cand) && !state.failedFaviconSrcs[cand.trim()]) {
      return cand.trim();
    }
  }
  return null;
}

export function normalizePreviewUrlKey(rawUrl: string): string {
  const clean = (rawUrl || "").trim();
  if (!/^https?:\/\//i.test(clean)) return clean;
  try {
    const u = new URL(clean);
    u.hash = "";
    const out = u.toString();
    return out.length > 8 && out.endsWith("/") && u.pathname !== "/" ? out.slice(0, -1) : out;
  } catch {
    return clean;
  }
}

export function getCachedUrlPreview(rawUrl: string): CitedSourcePreview | undefined {
  const clean = (rawUrl || "").trim();
  if (!clean) return undefined;
  return state.urlPreviews[clean] ?? state.urlPreviews[normalizePreviewUrlKey(clean)];
}

export function cacheUrlPreviews(items: Array<Partial<CitedSourcePreview> & { url?: string }>): void {
  for (const it of items) {
    const u = String(it?.url ?? "").trim();
    if (!u) continue;
    const norm = normalizePreviewUrlKey(u);
    const prev = state.urlPreviews[u] ?? state.urlPreviews[norm];
    const merged: CitedSourcePreview = {
      url: u,
      title: (it.title && it.title !== u ? it.title : prev?.title) || it.title || u,
      domain: it.domain || prev?.domain,
      snippet: it.snippet || prev?.snippet,
      image_url: it.image_url || prev?.image_url,
      favicon_url: it.favicon_url || prev?.favicon_url,
      trust: typeof it.trust === "number" ? it.trust : prev?.trust ?? null,
    };
    state.urlPreviews[u] = merged;
    if (norm) state.urlPreviews[norm] = merged;
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
  const cfg = state.modelConfig ?? state.sidecar.model_config ?? null;
  const lm = cfg?.local_models ?? null;
  const gemmaReady = lm
    ? Boolean(lm.gemma_ready)
    : state.sidecar.models.find((m) => m.id === "gemma-4-e4b")?.state !== "missing";
  const hertzReady = lm
    ? Boolean(lm.hertz_ready)
    : state.sidecar.models.find((m) => m.id === "hertz (reader)")?.state !== "missing";

  const base: Array<{ id: LocalModelId; label: string }> = [];
  const seen = new Set<string>();
  const pushItem = (id: LocalModelId, label: string) => {
    if (!id || seen.has(id)) return;
    seen.add(id);
    base.push({ id, label });
  };

  if (gemmaReady) {
    pushItem("gemma-4-e4b", "gemma-4-e4b (local)");
  }
  for (const item of lm?.custom_llms ?? []) {
    pushItem(
      item.id,
      item.ready ? `${item.label} (local)` : `${item.label} (local · invalid)`
    );
  }
  if (!gemmaReady) {
    pushItem("gemma-4-e4b", "gemma-4-e4b (local · not installed)");
  }

  pushItem(
    "planck3 (web)",
    lm?.planck_reader_source === "shipped"
      ? "planck3 (web · local shipped)"
      : "planck3 (web · local)"
  );
  pushItem(
    "hertz (reader)",
    hertzReady ? "hertz (reader · local)" : "hertz (reader · not installed)"
  );
  pushItem(
    "planck (reader)",
    lm?.planck_reader_source === "shipped"
      ? "planck (reader · local shipped)"
      : "planck (reader · local)"
  );

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

const NON_GENERATIVE_COMPOSE_MODELS = new Set<string>([
  "planck3 (web)",
  "hertz (reader)",
  "planck (reader)",
]);

export function getComposeModelsForPicker(): Array<{
  id: LocalModelId;
  label: string;
}> {
  const models = getAvailableModelsForPicker().filter(
    (m) => !NON_GENERATIVE_COMPOSE_MODELS.has(m.id)
  );
  if (models.length === 0) {
    return [{ id: "gemma-4-e4b", label: "gemma-4-e4b (local)" }];
  }
  return models;
}

export function getDefaultComposeModelId(): LocalModelId {
  const allowed = getComposeModelsForPicker();
  if (allowed.some((m) => m.id === state.selectedModel)) {
    return state.selectedModel;
  }
  return allowed[0]?.id ?? "gemma-4-e4b";
}

export function hasAnyGenerativeModelConfigured(
  cfg?: ModelManagementConfig | null
): boolean {
  const effectiveCfg = cfg ?? state.modelConfig ?? state.sidecar.model_config ?? null;
  const lm = effectiveCfg?.local_models ?? null;
  const gemmaReady = lm
    ? Boolean(lm.gemma_ready)
    : state.sidecar.models.some((m) => m.id === "gemma-4-e4b" && m.state !== "missing");
  if (gemmaReady) return true;
  if ((lm?.custom_llms ?? []).some((m) => Boolean(m.ready))) return true;
  if (
    (effectiveCfg?.cloud_providers ?? []).some(
      (p) => Boolean(p.configured) || (p.models?.length ?? 0) > 0
    )
  ) {
    return true;
  }
  return false;
}

/**
 * Syncs `state.selectedModel` to Settings' configured `roles.chat` (or backend
 * `effective_chat` when Gemma is not installed locally), falling back cleanly
 * to `planck3 (web)` when no local LLM or cloud API key is configured yet.
 */
export function syncConfiguredChatModel(
  cfg?: ModelManagementConfig | null,
  force = false
): boolean {
  const effectiveCfg = cfg ?? state.modelConfig ?? state.sidecar.model_config ?? null;
  if (effectiveCfg) {
    state.modelConfig = effectiveCfg;
    if (effectiveCfg.local_models?.downloads) {
      state.hfDownloads = effectiveCfg.local_models.downloads;
    }
    if (state.sidecar) {
      state.sidecar.model_config = effectiveCfg;
    }
  }
  if (force) {
    state.userOverrodeModelInSession = false;
  }
  const configuredChat =
    effectiveCfg?.roles?.effective_chat?.trim() ||
    effectiveCfg?.roles?.chat?.trim();
  const desiredChat: LocalModelId | "" =
    configuredChat === "gemma-4-e4b" && !hasAnyGenerativeModelConfigured(effectiveCfg)
      ? "planck3 (web)"
      : ((configuredChat || "") as LocalModelId | "");
  if (!desiredChat) return false;
  if (!state.userOverrodeModelInSession && state.selectedModel !== desiredChat) {
    state.selectedModel = desiredChat;
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
    return t("privacy.badge.cloud_gemini");
  }
  if (m.startsWith("anthropic:") || m.startsWith("claude-")) {
    return t("privacy.badge.cloud_anthropic");
  }
  if (m.startsWith("openai:") || m.startsWith("gpt-") || m.startsWith("o1") || m.startsWith("o3") || m.startsWith("o4")) {
    return t("privacy.badge.cloud_openai");
  }
  if (m.startsWith("mistral:")) {
    return t("privacy.badge.cloud_mistral");
  }
  if (m.includes("cloud")) {
    return t("privacy.badge.cloud_generic");
  }
  return t("privacy.badge.local_only");
}

export function isContentLanguageAllowed(langCode: string | null | undefined): boolean {
  const norm = normalizeLangTag((langCode || "").trim());
  if (!norm) return true;
  const known = state.contentTranslationConfig?.known_languages;
  if (!known || !known.length) {
    return norm === "en";
  }
  const base = norm.split("-")[0];
  return known.some((k) => {
    const kn = normalizeLangTag(k);
    return kn === norm || kn.split("-")[0] === base;
  });
}
