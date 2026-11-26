import { listen } from "@tauri-apps/api/event";
import {
  apiAddBookmark,
  apiAddMessage,
  apiArchiveConversation,
  apiApplyTabTranslationSegments,
  apiAutofillTabCredentials,
  apiCaptureOpenTabs,
  apiCloseTab,
  apiControlTab,
  apiCreateConversation,
  apiDeleteConversation,
  apiEnsureMailConversation,
  apiEnsureNewsConversation,
  apiEnsureNewsPerspectivesConversation,
  apiEnsureNewsSettingsConversation,
  apiEnsureDrivesConversation,
  apiEnsureSettingsConversation,
  apiExecuteTabAction,
  apiExecuteTabUnsubscribeActor,
  apiExtractTabTranslationDom,
  apiGetConversation,
  apiListBookmarks,
  apiListConversations,
  apiNavigateAndCaptureTab,
  apiNavigateTab,
  apiOpenTab,
  apiPinConversation,
  apiRemoveBookmark,
  apiRenameConversation,
  apiSetBookmarkFavicon,
  apiSetConversationSummary,
  apiSetSourceInContext,
  sidecarAcceptBrainProposal,
  sidecarAcceptSkillProposal,
  sidecarAckWatchBadge,
  sidecarAddMailAccount,
  sidecarAddWatch,
  sidecarAppendTaskStep,
  sidecarBackfillTranslations,
  sidecarBrowseLocalModel,
  sidecarCancelHfDownload,
  sidecarCancelTaskStep,
  sidecarCaptureFailureEval,
  sidecarCancelI18nTranslate,
  sidecarCompleteTask,
  sidecarConfirmSettingsGate,
  sidecarConfirmTaskStep,
  sidecarConnectGmailOAuth,
  sidecarConnectGoogleDrive,
  sidecarContinueSkill,
  sidecarCreateProfile,
  sidecarDeleteBrainEntity,
  sidecarDeleteEval,
  sidecarDeletePassage,
  sidecarDeletePassword,
  sidecarDeleteProfile,
  sidecarDeleteProvider,
  sidecarDeleteProviderCategory,
  sidecarDisconnectGoogleOAuth,
  sidecarDraftMailReply,
  sidecarExecuteMailUnsubscribe,
  sidecarExecuteSetDefaultProvider,
  sidecarExportI18n,
  sidecarExportProfile,
  sidecarFetchConversationPreviews,
  sidecarFetchDigest,
  sidecarFetchDoctor,
  sidecarFetchGoogleOAuthStatus,
  sidecarFetchHealth,
  sidecarFetchKnowledge,
  sidecarFetchRoutingPolicy,
  sidecarGetI18nBundle,
  sidecarGetI18nStatus,
  sidecarGetMailAccounts,
  sidecarGetMailAttachmentData,
  sidecarGetMailCodes,
  sidecarGetMailStatus,
  sidecarGetModelConfig,
  sidecarGetProviders,
  sidecarGetTranslationConfig,
  sidecarHideMailSender,
  sidecarImportEnvFile,
  sidecarImportI18n,
  sidecarImportProfile,
  sidecarInferProvider,
  sidecarInspectHfRepo,
  sidecarListHfDownloads,
  sidecarListTasks,
  sidecarListWatches,
  sidecarLockProfile,
  sidecarLogBehaviorEvent,
  sidecarLookupDomainRecipe,
  sidecarMatchPasswordForUrl,
  sidecarFetchNewsSettingsOnboard,
  sidecarManageNewsFeed,
  sidecarManageNewsTopic,
  sidecarMineSkillProposals,
  sidecarPointLocalModel,
  sidecarRemoveLocalModel,
  sidecarSaveHfToken,
  sidecarSearchHfModels,
  sidecarStartHfDownload,
  sidecarStreamNewsChat,
  sidecarStreamNewsPerspectives,
  sidecarOverrideI18n,
  sidecarPrepareUnsubscribeTask,
  sidecarRecordDomainRecipe,
  sidecarRecordHarnessSignal,
  sidecarRefreshGoogleOAuth,
  sidecarRefreshNews,
  sidecarRejectBrainProposal,
  sidecarRejectSkillProposal,
  sidecarReorderProviders,
  sidecarResetRoutingTelemetry,
  sidecarResolveFavicons,
  sidecarResolveProviderSuggestion,
  sidecarRevealPassword,
  sidecarReweighNewsMeta,
  sidecarRunAnswer,
  sidecarRunComparer,
  sidecarRunEvals,
  sidecarRunRead,
  sidecarRunSkill,
  sidecarRunSkillRedteam,
  sidecarSaveAsSkill,
  sidecarSaveGoogleOAuthConfig,
  sidecarSaveRawEnv,
  sidecarSearchBrain,
  sidecarSearchMail,
  sidecarSetDomainTrust,
  sidecarSetPauseLearning,
  sidecarStageSettingsFile,
  sidecarStartGoogleOAuthLogin,
  sidecarStopTask,
  sidecarStreamChat,
  sidecarSummarizeConversation,
  sidecarSwitchI18nLanguage,
  sidecarSyncBookmarks,
  sidecarSyncDrives,
  sidecarSyncMail,
  sidecarFetchDriveCreateTargets,
  sidecarFetchDrivesList,
  sidecarFetchDrivesStatus,
  sidecarDisconnectDrive,
  sidecarStartOneDriveConnect,
  sidecarEnrichUrlPreviews,
  sidecarTestProvider,
  sidecarTranslateI18nStream,
  sidecarTranslateMailMessage,
  sidecarTranslatePageStream,
  sidecarUnlockProfile,
  sidecarUnlockProfileKeychain,
  sidecarUpdateModelConfig,
  sidecarUpdateTranslationConfig,
  sidecarUpsertBrainEntity,
  sidecarUpsertPassword,
  sidecarUpsertProvider,
  sidecarUpsertProviderCategory,
} from "./api";
import {
  addChatImageFiles,
  appendStreamingDelta,
  applyCachedPreviewsToChatDom,
  closeChatLinkPreviewPopover,
  extractImageFilesFromDataTransfer,
  renderChatImagePreviewOverlay,
  renderChatPanel,
  replaceStreamingText,
  tickStreamingElapsed,
  updateStreamingStatus,
} from "./chat";
import { pushDrivesNavHistory, renderDrivesView } from "./drives";
import { bindKeyboardShortcuts } from "./keys";
import {
  exportCatalogManifest,
  getUiLocale,
  mergeActiveLocaleEntries,
  setActiveLocaleBundle,
  switchActiveLocale,
  t,
} from "./i18n";
import { fontsReady } from "./design-system/brand";
import { icon } from "./design-system/icons";
import {
  renderBrainView,
  renderKnowledgeView,
  type KnowledgeActions,
} from "./knowledge";
import {
  bindMailIframeInteractions,
  buildMailIframeSrcdoc,
  normalizeEmailLinkUrl,
  refreshMailState,
  renderComposeTabView,
  renderEmailAgentRailCardsHtml,
  renderEmailTabHeaderHtml,
  renderMailComposeModalOverlay,
  renderMailLaneView,
  sidecarGetMailMessage,
  sidecarGetMailMessageHtml,
  sidecarHideMailMessage,
  sidecarLabelMailMessage,
  sidecarOpenMailMessage,
  sidecarSaveMailAttachment,
  sidecarUpdateMailSettings,
} from "./mail";
import {
  paintNewsWordmark,
  refreshNewsState,
  renderNewsLaneView,
  renderNewsSettingsManualView,
} from "./news";
import { renderRail } from "./rail";
import { renderSourcesPanel } from "./sources";
import {
  renderCommandBarOverlay,
  renderPostUnlockGlassOverlay,
  renderProfileUnlockOverlay,
  renderStartScreen,
  updateOverlayDigestInPlace,
  updateStartDigestInPlace,
} from "./start";
import {
  applyUiPreferences,
  cacheSiteFavicon,
  cacheUrlPreviews,
  classifyStartInput,
  escapeHtml,
  extractDomain,
  getActiveTabSources,
  getCachedUrlPreview,
  getDefaultComposeModelId,
  getOriginFromUrl,
  getUiThemePref,
  hasAnyActiveStream,
  isConvStreaming,
  MOD_LABEL,
  normalizePreviewUrlKey,
  normalizeUrl,
  resolveLearnedRouteForPrompt,
  setUiAgentFoldedPref,
  state,
  syncConfiguredChatModel,
} from "./state";
import { renderStatusLine } from "./status";
import { renderTabStrip, renderTopBar, scheduleWebviewLayoutSync } from "./tabs";
import type {
  ChatImageAttachment,
  CommandBarRoute,
  LocalModelId,
  MailComposeDraft,
  NewsLane,
  StagedSettingsFile,
  TabNewWindowEvent,
  TabPageEvent,
} from "./types";
import {
  type ProfileAuthResult,
  type UnlockStreamEvent,
} from "./api";
import type {
  UnlockProgressStep,
  UnlockStepId,
  UnlockStepStatus,
} from "./state";
import {
  checkForAppUpdate,
  downloadAndInstallAppUpdate,
  getInstalledAppVersion,
} from "./updater";

let resizeObserver: ResizeObserver | null = null;
let streamingTimerId: number | null = null;
let sidecarPollTimerId: number | null = null;
let sidecarPollInFlight = false;
let digestFetchPromise: Promise<void> | null = null;
let startupSyncKey = "";
const sidecarBootStartedAt = Date.now();

function scheduleSidecarPoll(delayMs: number): void {
  if (sidecarPollTimerId !== null) {
    window.clearTimeout(sidecarPollTimerId);
  }
  sidecarPollTimerId = window.setTimeout(() => {
    void pollSidecarState();
  }, delayMs);
}

function startStreamingProgress(
  convId: string,
  model: LocalModelId,
  initialStatus: string,
  phase: string,
  userPrompt: string
): void {
  state.lastPromptByConv[convId] = userPrompt;
  state.streamsByConv[convId] = {
    convId,
    model,
    text: "",
    status: initialStatus,
    phase,
    startedAt: Date.now(),
    steps: [initialStatus],
    lastUserPrompt: userPrompt,
  };
  if (streamingTimerId === null) {
    streamingTimerId = window.setInterval(() => {
      tickStreamingElapsed();
    }, 200);
  }
  renderRailRegion();
}

function stopStreamingProgress(convId: string): string {
  const streamedText = state.streamsByConv[convId]?.text ?? "";
  delete state.streamsByConv[convId];
  if (!hasAnyActiveStream() && streamingTimerId !== null) {
    window.clearInterval(streamingTimerId);
    streamingTimerId = null;
  }
  renderRailRegion();
  return streamedText;
}

async function refreshCompletedConversation(
  convId: string,
  savedMsgId?: string
): Promise<void> {
  const latest = await apiGetConversation(convId);
  if (state.activeDetail?.conversation.id === convId) {
    state.chatPinToBottom = true;
    state.activeDetail = latest;
    if (state.activeDetail) {
      await hydrateConversationPreviews(state.activeDetail);
      if (savedMsgId) {
        const msgObj = state.activeDetail.messages.find(
          (m) => m.id === savedMsgId
        );
        if (msgObj) {
          if (state.messageProposals[savedMsgId]) {
            msgObj.proposals = state.messageProposals[savedMsgId];
          }
          if (state.messageFindings[savedMsgId]) {
            msgObj.findings = state.messageFindings[savedMsgId];
          }
          if (state.messageBrainSources[savedMsgId]) {
            msgObj.brain_sources = state.messageBrainSources[savedMsgId];
          }
          if (state.messageEmailCards[savedMsgId]) {
            msgObj.email_cards = state.messageEmailCards[savedMsgId];
          }
          if (state.messageCitedSources[savedMsgId]) {
            msgObj.cited_sources = state.messageCitedSources[savedMsgId];
          }
          if (state.messageAnswerMeta[savedMsgId]) {
            msgObj.answer_meta = state.messageAnswerMeta[savedMsgId];
          }
          seedUrlPreviewCacheFromDetail(state.activeDetail);
        }
      }
    }
    renderAllRegions();
  } else {
    await refreshLists();
    renderRailRegion();
  }
}

function applyDigestUiUpdate(): void {
  const actions = getStartScreenActions();
  if (!state.activeDetail && !state.showKnowledgeView && !state.showBrainView) {
    if (!updateStartDigestInPlace(actions)) {
      renderViewportRegion();
    }
  }
  if (state.commandBarOpen) {
    if (!updateOverlayDigestInPlace(actions)) {
      renderCommandBarOverlay(actions);
    }
  }
}

async function refreshDigest(revisionSnapshot?: string | null): Promise<void> {
  if (!state.sidecar.online) return;
  if (digestFetchPromise) {
    await digestFetchPromise;
    return;
  }
  state.digestRefreshing = true;
  applyDigestUiUpdate();
  digestFetchPromise = (async () => {
    try {
      const items = await sidecarFetchDigest();
      state.digestItems = items;
      state.digestUpdatedAt = Date.now();
      if (revisionSnapshot !== undefined) {
        state.digestRevision = revisionSnapshot;
      } else if (state.sidecar.digest_revision) {
        state.digestRevision = state.sidecar.digest_revision;
      }
    } finally {
      state.digestRefreshing = false;
      digestFetchPromise = null;
      applyDigestUiUpdate();
    }
  })();
  await digestFetchPromise;
}

async function refreshLiveDigestSources(): Promise<void> {
  if (!state.sidecar.online) return;
  await refreshDigest(null);
  state.digestRefreshing = true;
  applyDigestUiUpdate();
  try {
    const tasks: Array<Promise<unknown>> = [];
    if (state.knowledge.profile?.unlocked) {
      tasks.push(
        sidecarSyncMail().then(async () => {
          await refreshMailState();
        })
      );
    }
    tasks.push(
      sidecarRefreshNews(false, false).then(async () => {
        await refreshNewsState("stories");
      })
    );
    await Promise.allSettled(tasks);
    const nextHealth = await sidecarFetchHealth();
    if (nextHealth.online) {
      state.sidecar = nextHealth;
      if (nextHealth.mail?.counts) {
        state.mailCounts = nextHealth.mail.counts;
      }
    }
    await refreshDigest(nextHealth.digest_revision ?? state.sidecar.digest_revision ?? null);
    renderRailRegion();
    renderStatusLine();
  } finally {
    state.digestRefreshing = false;
    applyDigestUiUpdate();
  }
}

function triggerStartupSyncIfNeeded(syncKey: string): void {
  if (!state.sidecar.online || startupSyncKey === syncKey) return;
  startupSyncKey = syncKey;
  void refreshDigest(null);
  if (
    syncKey.startsWith("unlocked:") &&
    state.newsStories.length === 0 &&
    !state.sidecar.news?.last_sync_at
  ) {
    void sidecarRefreshNews(false, false).then(async () => {
      await refreshNewsState(state.newsActiveLane || "stories");
      renderRailRegion();
    });
  }
}

async function refreshRoutingPolicy(): Promise<void> {
  if (!state.sidecar.online) return;
  const pol = await sidecarFetchRoutingPolicy();
  if (pol && pol.ok) {
    state.routingPolicy = pol;
  }
}

function getLastTurnTelemetryContext(
  convId: string,
  msgId?: string
): {
  prompt: string;
  model: string;
  sourceCount: number;
  charsCut: number;
} {
  const detail = state.activeDetail;
  const msgs = detail?.conversation.id === convId ? detail.messages : [];
  const targetMsg = msgId ? msgs.find((m) => m.id === msgId) : undefined;
  const fallbackAsst = [...msgs].reverse().find((m) => m.role === "assistant");
  const model =
    targetMsg?.model || fallbackAsst?.model || state.selectedModel || "gemma-4-e4b";
  let sourceCount = 0;
  let charsCut = 0;
  const rawSids = targetMsg?.source_ids_json ?? fallbackAsst?.source_ids_json;
  if (rawSids) {
    try {
      const sids = JSON.parse(rawSids) as unknown;
      if (Array.isArray(sids)) {
        sourceCount = sids.length;
        for (const sid of sids) {
          const st = state.sourceStats[String(sid)];
          if (st?.was_cut) {
            charsCut += Math.max(0, (st.chars_captured || 0) - (st.chars_sent || 0));
          }
        }
      }
    } catch {
      // Ignore parse errors
    }
  }
  const prompt = state.lastPromptByConv[convId] ?? "";
  return { prompt, model, sourceCount, charsCut };
}

function recordHarnessOutcomeSignal(
  outcomeSignal:
    | "retry"
    | "use_planck_instead"
    | "citation_flagged_click"
    | "manual_model_override"
    | "manual_context_override",
  opts: {
    prompt?: string;
    modelId?: string;
    sourceCount?: number;
    charsCut?: number;
    webEnabled?: boolean;
    mailEnabled?: boolean;
    targetModel?: string;
  }
): void {
  if (!state.sidecar.online) return;
  void sidecarRecordHarnessSignal({
    prompt: opts.prompt ?? "",
    model_id: opts.modelId ?? state.selectedModel,
    source_count: opts.sourceCount ?? 0,
    chars_cut: opts.charsCut ?? 0,
    outcome_signal: outcomeSignal,
    web_enabled: Boolean(opts.webEnabled ?? state.webSearchEnabled),
    mail_enabled: Boolean(opts.mailEnabled ?? state.mailContextEnabled),
    target_model: opts.targetModel ?? "",
  }).then((res) => {
    if (res.ok && res.policy) {
      state.routingPolicy = res.policy;
    }
  });
}

async function refreshContentTranslationConfig(unlocked: boolean): Promise<void> {
  if (!unlocked) {
    state.contentTranslationConfig = null;
    state.contentTranslationStatusMsg = "";
    return;
  }
  const cfg = await sidecarGetTranslationConfig();
  if (cfg && cfg.ok) {
    state.contentTranslationConfig = cfg;
  } else if (cfg && cfg.unlocked === false) {
    state.contentTranslationConfig = null;
  }
}

const UNLOCK_HEADLINE_PRIORITY: UnlockStepId[] = [
  "mail",
  "news",
  "drives",
  "vault_brain",
  "digest",
];
let unlockHeadlineByStep: Partial<Record<UnlockStepId, string>> = {};

function createUnlockSteps(preDoneVault = false): UnlockProgressStep[] {
  return [
    {
      id: "vault_brain",
      label: t("profile.step_vault_brain"),
      status: preDoneVault ? "running" : "pending",
      detail: preDoneVault ? t("profile.detail_hydrating_brain") : "",
    },
    { id: "mail", label: t("profile.step_mail"), status: "pending", detail: "" },
    { id: "news", label: t("profile.step_news"), status: "pending", detail: "" },
    { id: "drives", label: t("profile.step_drives"), status: "pending", detail: "" },
    { id: "digest", label: t("profile.step_digest"), status: "pending", detail: "" },
  ];
}

function initPostUnlockHydrationSteps(profileTitle = ""): void {
  unlockHeadlineByStep = {};
  state.postUnlockTitle = profileTitle;
  state.unlockSteps = createUnlockSteps(true);
  unlockHeadlineByStep.vault_brain = t("profile.status_hydrating_brain");
  state.postUnlockLabel = t("profile.status_hydrating_brain");
}

function clearUnlockOverlayState(): void {
  unlockHeadlineByStep = {};
  state.postUnlockLoading = false;
  state.postUnlockLabel = "";
  state.postUnlockTitle = "";
  state.unlockSteps = [];
}

function updateUnlockStep(
  id: UnlockStepId,
  status: UnlockStepStatus,
  detail?: string,
  headline?: string
): void {
  if (!state.postUnlockLoading) return;
  if (state.unlockSteps.length === 0) {
    state.unlockSteps = createUnlockSteps(false);
  }
  const idx = state.unlockSteps.findIndex((s) => s.id === id);
  if (idx >= 0) {
    const nextDetail = detail !== undefined ? detail : (state.unlockSteps[idx].detail ?? "");
    state.unlockSteps[idx] = {
      ...state.unlockSteps[idx],
      status,
      detail: nextDetail,
    };
  }
  if (status === "running" && headline) {
    unlockHeadlineByStep[id] = headline;
  } else if (status !== "running") {
    delete unlockHeadlineByStep[id];
  }

  let nextLabel = "";
  for (const candId of UNLOCK_HEADLINE_PRIORITY) {
    const cand = state.unlockSteps.find((s) => s.id === candId && s.status === "running");
    if (cand) {
      nextLabel =
        unlockHeadlineByStep[candId] ||
        (cand.detail ? `${cand.label}: ${cand.detail}` : t("profile.syncing_vault"));
      break;
    }
  }
  if (nextLabel) {
    state.postUnlockLabel = nextLabel;
    state.profileUnlockLabel = nextLabel;
  } else if (!state.postUnlockLabel) {
    state.postUnlockLabel = t("profile.syncing_vault");
  }
  renderPostUnlockGlassOverlay();
}

function applySidecarUnlockStreamEvent(ev: UnlockStreamEvent): void {
  const step = String(ev.step || "").toLowerCase();
  const status = String(ev.status || "running").toLowerCase();
  const detail = String(ev.detail || "").toLowerCase();
  if (step === "vault") {
    if (status === "running") {
      if (detail === "checking_keychain") {
        updateUnlockStep(
          "vault_brain",
          "running",
          t("profile.detail_checking_keychain"),
          t("profile.status_checking_keychain")
        );
      } else if (detail === "decrypting_bundle") {
        updateUnlockStep(
          "vault_brain",
          "running",
          t("profile.detail_decrypting_bundle"),
          t("profile.status_decrypting_bundle")
        );
      } else if (detail === "merging_profile") {
        updateUnlockStep(
          "vault_brain",
          "running",
          t("profile.detail_merging_profile"),
          t("profile.status_merging_profile")
        );
      } else if (detail === "creating_vault") {
        updateUnlockStep(
          "vault_brain",
          "running",
          t("profile.detail_creating_vault"),
          t("profile.status_creating_vault")
        );
      } else {
        updateUnlockStep(
          "vault_brain",
          "running",
          t("profile.detail_verifying_pin"),
          t("profile.status_verifying_pin")
        );
      }
    } else if (status === "done") {
      updateUnlockStep(
        "vault_brain",
        "running",
        t("profile.detail_opening_store"),
        t("profile.status_opening_store")
      );
    }
  } else if (step === "store") {
    if (status === "running") {
      updateUnlockStep(
        "vault_brain",
        "running",
        t("profile.detail_opening_store"),
        t("profile.status_opening_store")
      );
    } else if (status === "done") {
      updateUnlockStep(
        "vault_brain",
        "running",
        t("profile.detail_hydrating_brain"),
        t("profile.status_hydrating_brain")
      );
    }
  } else if (step === "mail") {
    if (detail === "repairing_calendar") {
      updateUnlockStep(
        "mail",
        "running",
        t("profile.detail_repairing_calendar"),
        t("profile.status_repairing_calendar")
      );
    } else {
      updateUnlockStep(
        "mail",
        "running",
        t("profile.detail_opening_mail_db"),
        t("profile.status_opening_mail")
      );
    }
  } else if (step === "drives") {
    updateUnlockStep(
      "drives",
      "running",
      t("profile.detail_drives_sync"),
      t("profile.status_loading_drives")
    );
  }
}

async function performProfileUnlockOrCreate(opts: {
  mode: "unlock" | "keychain" | "create" | "import";
  profileId?: string;
  name?: string;
  pin?: string;
  bundleB64?: string;
  localPin?: string;
  closeModalOnSuccess?: boolean;
}): Promise<{ ok: boolean; error: string }> {
  if (state.profileUnlocking) {
    return { ok: false, error: t("profile.unlocking_progress") };
  }
  const prevPromptOpen = state.profilePromptOpen;
  const matchedProfName =
    opts.mode === "create"
      ? (opts.name ?? "").trim()
      : opts.mode === "import"
        ? state.profileImportDraft?.filename ?? t("profile.upload_btn")
        : (state.knowledge.profile?.profiles.find((p) => p.id === opts.profileId)?.name ??
            opts.profileId ??
            "");

  state.revealedPasswords = {};
  state.profileUnlocking = true;
  state.profileUnlockLabel =
    opts.mode === "create"
      ? t("profile.status_creating_vault")
      : opts.mode === "import"
        ? t("profile.status_decrypting_bundle")
        : opts.mode === "keychain"
          ? t("profile.status_checking_keychain")
          : t("profile.status_verifying_pin");
  state.profileStatusMessage = "";
  state.profilePromptOpen = false;
  state.postUnlockLoading = true;
  state.postUnlockTitle = matchedProfName;
  unlockHeadlineByStep = {};
  state.unlockSteps = createUnlockSteps(false);
  updateUnlockStep(
    "vault_brain",
    "running",
    opts.mode === "create"
      ? t("profile.detail_creating_vault")
      : opts.mode === "import"
        ? t("profile.detail_decrypting_bundle")
        : opts.mode === "keychain"
          ? t("profile.detail_checking_keychain")
          : t("profile.detail_verifying_pin"),
    state.profileUnlockLabel
  );
  renderProfileUnlockOverlay(getProfilePromptActions());
  renderPostUnlockGlassOverlay();
  renderAllRegions();
  scheduleWebviewLayoutSync();
  let ok = false;
  let errMsg = "";
  try {
    const res: ProfileAuthResult =
      opts.mode === "create"
        ? await sidecarCreateProfile(opts.name ?? "", opts.pin ?? "", applySidecarUnlockStreamEvent)
        : opts.mode === "import"
          ? await sidecarImportProfile(
              opts.bundleB64 ?? "",
              opts.pin ?? "",
              { localPin: opts.localPin, activate: true },
              applySidecarUnlockStreamEvent
            )
          : opts.mode === "keychain"
            ? await sidecarUnlockProfileKeychain(opts.profileId ?? "", applySidecarUnlockStreamEvent)
            : await sidecarUnlockProfile(opts.profileId ?? "", opts.pin ?? "", applySidecarUnlockStreamEvent);
    ok = Boolean(res.ok);
    if (ok && res.profile) {
      state.knowledge = { ...state.knowledge, profile: res.profile };
      state.profileImportDraft = null;
      state.profilePromptOpen = false;
      if (opts.closeModalOnSuccess) {
        state.profilePromptDismissed = false;
      }
      const importedDisplayName =
        res.importedProfileName || res.profile.active_profile?.name || res.importedProfileId || matchedProfName;
      state.profileStatusMessage =
        opts.mode === "create"
          ? t("main.profile_created", { name: opts.name ?? "" })
          : opts.mode === "import"
            ? res.importAction === "merge"
              ? t("main.profile_merged", { name: importedDisplayName })
              : t("main.profile_imported", { name: importedDisplayName })
            : opts.mode === "keychain"
              ? t("main.profile_unlocked_keychain", { id: opts.profileId ?? "" })
              : t("main.profile_unlocked", { id: opts.profileId ?? "" });
      state.profileUnlocking = false;
      state.profileUnlockLabel = "";
      try {
        await syncAfterProfileAuthChange(true);
      } finally {
        clearUnlockOverlayState();
      }
    } else {
      clearUnlockOverlayState();
      renderPostUnlockGlassOverlay();
      if (prevPromptOpen || opts.closeModalOnSuccess) {
        state.profilePromptOpen = prevPromptOpen;
      }
      errMsg =
        res.error ??
        (opts.mode === "create"
          ? t("main.profile_err_create")
          : opts.mode === "import"
            ? t("main.profile_err_import")
            : opts.mode === "keychain"
              ? t("main.profile_err_keychain")
              : t("mail.err_invalid_pin"));
      if (opts.mode === "import" && state.profileImportDraft && errMsg.toLowerCase().includes("local pin")) {
        state.profileImportDraft = { ...state.profileImportDraft, needLocalPin: true };
      }
      state.profileStatusMessage = `${t("common.error_prefix")} ${errMsg}`;
      await syncAfterProfileAuthChange(false);
    }
  } finally {
    state.profileUnlocking = false;
    state.profileUnlockLabel = "";
    clearUnlockOverlayState();
  }
  renderProfileUnlockOverlay(getProfilePromptActions());
  renderAllRegions();
  scheduleWebviewLayoutSync();
  return { ok, error: errMsg };
}

function decodeBase64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const len = bin.length;
  const out = new Uint8Array(len);
  for (let i = 0; i < len; i += 1) {
    out[i] = bin.charCodeAt(i);
  }
  return out;
}

async function handleExportProfile(profileId: string, pin?: string): Promise<void> {
  if (state.profileExportBusyId || state.profileUnlocking) return;
  state.profileExportBusyId = profileId;
  renderViewportRegion();
  try {
    const res = await sidecarExportProfile(profileId, pin);
    if (!res.ok || !res.bundle_b64) {
      const msg = `${t("common.error_prefix")} ${res.error ?? t("main.profile_err_export")}`;
      state.profileStatusMessage = msg;
      showAppToast(msg, "danger");
      return;
    }
    const filename = res.filename || `${profileId}.satzprofile`;
    const bytes = decodeBase64ToBytes(res.bundle_b64);
    const blob = new Blob([bytes.buffer as ArrayBuffer], { type: "application/octet-stream" });

    let saved = false;
    const pickerFn = (
      window as unknown as {
        showSaveFilePicker?: (opts: {
          suggestedName?: string;
          types?: Array<{ description?: string; accept: Record<string, string[]> }>;
        }) => Promise<{
          createWritable: () => Promise<{ write: (data: Blob) => Promise<void>; close: () => Promise<void> }>;
        }>;
      }
    ).showSaveFilePicker;
    if (typeof pickerFn === "function") {
      try {
        const handle = await pickerFn({
          suggestedName: filename,
          types: [{ description: "Satz Profile Backup", accept: { "application/octet-stream": [".satzprofile"] } }],
        });
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        saved = true;
      } catch (err) {
        if ((err as { name?: string })?.name === "AbortError") {
          return;
        }
      }
    }
    if (!saved) {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    }

    const okMsg = t("main.profile_exported", {
      name: res.profile_name || profileId,
      filename,
    });
    state.profileStatusMessage = okMsg;
    showAppToast(okMsg, "info");
  } finally {
    state.profileExportBusyId = null;
    renderViewportRegion();
  }
}

async function syncAfterProfileAuthChange(unlocked: boolean): Promise<void> {
  state.digestRevision = null;
  startupSyncKey = "";
  state.mailMessageShowOriginal = {};
  state.newsStoryShowOriginal = {};
  state.tabTranslationState = {};
  state.contentTranslationStatusMsg = "";
  state.mailMessageDetails = {};
  state.mailMessageHtml = {};
  if (!unlocked) {
    state.drivesStatus = null;
    state.drivesItems = [];
    state.drivesCreateTargets = [];
    state.drivesNavStack = [];
    state.drivesFolderKey = "";
    state.drivesParentKey = null;
    state.drivesBreadcrumbs = [{ key: "", name: "Drives" }];
    state.newsFollowedStories = [];
    state.newsPendingTopicKeys = {};
    state.newsPendingFeedKeys = {};
    state.newsPendingTrustDomains = {};
    state.newsPerspectivesDetail = null;
    state.newsPerspectivesStream = null;
    state.googleOAuthSessionId = null;
    state.googleOAuthMessage = "";
    const [kb, mCfg, pol] = await Promise.all([
      sidecarFetchKnowledge(),
      sidecarGetModelConfig(),
      sidecarFetchRoutingPolicy(),
      refreshContentTranslationConfig(false),
      refreshMailState(),
      refreshLists(),
      refreshDigest(null),
    ]);
    if (kb) state.knowledge = kb;
    if (mCfg) {
    syncConfiguredChatModel(mCfg, false);
    ensureHfDownloadPolling();
  }
    if (pol && pol.ok) state.routingPolicy = pol;
    state.providerRegistry = null;
    state.googleOAuthStatus = null;
    state.providerCredOpenId = "";
    state.providerInferredDraft = {};
    renderRailRegion();
    return;
  }

  if (state.postUnlockLoading && state.unlockSteps.length === 0) {
    initPostUnlockHydrationSteps(
      state.knowledge.profile?.active_profile?.name ??
        state.knowledge.profile?.active_profile_id ??
        ""
    );
  }

  let liveMailPollId: number | null = null;
  if (state.postUnlockLoading) {
    liveMailPollId = window.setInterval(async () => {
      if (!state.postUnlockLoading) return;
      try {
        const st = await sidecarGetMailStatus();
        if (!state.postUnlockLoading || !st.unlocked) return;
        if ((st.processing_total ?? 0) > (st.processing_done ?? 0)) {
          const done = String(st.processing_done ?? 0);
          const total = String(st.processing_total ?? 0);
          updateUnlockStep(
            "mail",
            "running",
            t("profile.detail_mail_indexing", { done, total }),
            t("profile.status_indexing_mail", { done, total })
          );
        }
      } catch {
        // Ignore transient status poll errors
      }
    }, 550);
  }

  try {
    const mailTask = (async () => {
      updateUnlockStep(
        "mail",
        "running",
        t("profile.detail_mail_accounts"),
        t("profile.status_loading_mail")
      );
      try {
        await refreshMailState((detail, headline) =>
          updateUnlockStep("mail", "running", detail, headline)
        );
        updateUnlockStep("mail", "done", t("profile.detail_ready"));
      } catch (err) {
        updateUnlockStep("mail", "error");
        throw err;
      }
    })();

    const newsTask = (async () => {
      updateUnlockStep(
        "news",
        "running",
        t("profile.detail_news_fetch"),
        t("profile.status_loading_news")
      );
      try {
        await refreshNewsState(state.newsActiveLane || "stories", (detail, headline) =>
          updateUnlockStep("news", "running", detail, headline)
        );
        updateUnlockStep("news", "done", t("profile.detail_ready"));
      } catch (err) {
        updateUnlockStep("news", "error");
        throw err;
      }
    })();

    const drivesTask = (async () => {
      updateUnlockStep(
        "drives",
        "running",
        t("profile.detail_drives_sync"),
        t("profile.status_loading_drives")
      );
      try {
        await refreshDrivesState(false);
        updateUnlockStep("drives", "done", t("profile.detail_ready"));
      } catch (err) {
        updateUnlockStep("drives", "error");
        throw err;
      }
    })();

    const brainCoreTask = (async () => {
      updateUnlockStep(
        "vault_brain",
        "running",
        t("profile.detail_hydrating_brain"),
        t("profile.status_hydrating_brain")
      );
      try {
        const res = await Promise.all([
          sidecarFetchKnowledge(),
          sidecarGetModelConfig(),
          sidecarFetchHealth(),
          refreshContentTranslationConfig(true),
          refreshLists(),
          sidecarFetchRoutingPolicy().catch(() => null),
          sidecarGetProviders().catch(() => null),
        ]);
        updateUnlockStep("vault_brain", "done", t("profile.detail_ready"));
        return res;
      } catch (err) {
        updateUnlockStep("vault_brain", "error");
        throw err;
      }
    })();

    const digestTask = (async () => {
      updateUnlockStep(
        "digest",
        "running",
        t("profile.detail_digest_build"),
        t("profile.status_building_digest")
      );
      try {
        await refreshDigest(null);
        updateUnlockStep("digest", "done", t("profile.detail_ready"));
      } catch (err) {
        updateUnlockStep("digest", "error");
        throw err;
      }
    })();

    const heavyHydratePromise = Promise.allSettled([mailTask, newsTask, drivesTask]);
    const [coreRes, acctsRes, gStatus] = await Promise.all([
      brainCoreTask,
      sidecarGetMailAccounts(),
      sidecarFetchGoogleOAuthStatus().catch(() => null),
      digestTask,
      Promise.race([
        heavyHydratePromise,
        new Promise<void>((resolve) => window.setTimeout(resolve, 4500)),
      ]),
    ]);

    const [kb, mCfg, healthRes, , , pol, provReg] = coreRes;
    if (kb) state.knowledge = kb;
    if (mCfg) syncConfiguredChatModel(mCfg, true);
    if (gStatus !== undefined) state.googleOAuthStatus = gStatus;
    if (pol && pol.ok) state.routingPolicy = pol;
    if (provReg !== undefined) {
      state.providerRegistry = provReg;
      state.providerCredOpenId = "";
      state.providerInferredDraft = {};
    }
    if (healthRes.online) {
      state.sidecar = healthRes;
      if (healthRes.mail?.counts) state.mailCounts = healthRes.mail.counts;
      if (healthRes.drives && !state.drivesStatus) state.drivesStatus = healthRes.drives;
    }
    if (acctsRes.unlocked && state.mailAccounts.length === 0) {
      state.mailAccounts = acctsRes.accounts ?? [];
      if (acctsRes.presets?.length) state.mailPresets = acctsRes.presets;
      const totalAcctUnread = state.mailAccounts.reduce(
        (acc, a) => acc + (a.inbox_unread ?? 0),
        0
      );
      if (totalAcctUnread > 0 && state.mailCounts.inbox_unread === 0) {
        state.mailCounts = { ...state.mailCounts, inbox_unread: totalAcctUnread };
      }
    }
    const syncKey = `unlocked:${state.knowledge.profile?.active_profile?.id ?? "default"}`;
    triggerStartupSyncIfNeeded(syncKey);

    void heavyHydratePromise.then(() => {
      renderRailRegion();
      renderStatusLine();
      if (!state.activeDetail && !state.showKnowledgeView && !state.showBrainView) {
        renderViewportRegion();
      }
    });
  } finally {
    if (liveMailPollId !== null) {
      window.clearInterval(liveMailPollId);
    }
  }
}

let i18nBootSynced = false;
let i18nAutoSyncKey = "";

function renderRegionsPreservingOverrideInput(): void {
  const activeEl = document.activeElement as HTMLElement | null;
  if (activeEl?.closest("#kb-app-language-slot .kb-app-lang-editor")) {
    renderRailRegion();
    renderTabStripRegion();
    renderStatusLine();
    return;
  }
  renderAllRegions();
}

function getCatalogManifestRecord(): Record<
  string,
  { text: string; one?: string; hint?: string }
> {
  const rec: Record<string, { text: string; one?: string; hint?: string }> = {};
  for (const item of exportCatalogManifest()) {
    rec[item.key] = {
      text: item.text,
      ...(item.one !== undefined ? { one: item.one } : {}),
      ...(item.hint !== undefined ? { hint: item.hint } : {}),
    };
  }
  return rec;
}

async function handleTranslateUiLanguage(
  rawLang: string,
  force = false,
  silent = false,
  cardCtx?: { msgId: string; cardId: string }
): Promise<void> {
  if (state.i18nTranslating) return;
  const manifest = getCatalogManifestRecord();
  const totalManifestKeys = Object.keys(manifest).length;
  state.i18nTranslating = true;
  state.i18nTranslateCompleted = 0;
  state.i18nTranslateTotal = force ? totalManifestKeys : 0;
  if (!silent) {
    state.i18nStatusMsg = "";
  }
  renderRegionsPreservingOverrideInput();

  let streamLang = rawLang.trim();
  let streamLabel = streamLang;
  let streamDir: "ltr" | "rtl" = "ltr";
  let lastRenderAt = 0;

  try {
    await sidecarTranslateI18nStream(
      {
        lang: streamLang,
        catalog: manifest,
        only_missing: !force,
        force,
        activate: true,
      },
      {
        onStart: (ev) => {
          streamLang = ev.lang || streamLang;
          streamLabel = ev.label || streamLang;
          streamDir = ev.dir === "rtl" ? "rtl" : "ltr";
          state.i18nTranslateTotal = force
            ? totalManifestKeys
            : Math.max(1, (ev.missing || 0) + (ev.stale || 0));
          switchActiveLocale(streamLang, streamLabel, streamDir);
          void sidecarGetI18nBundle(streamLang).then((b) => {
            if (b?.ok) {
              setActiveLocaleBundle(
                streamLang,
                b.label || streamLabel,
                b.dir === "rtl" ? "rtl" : "ltr",
                b.entries ?? {}
              );
              renderRegionsPreservingOverrideInput();
            }
          });
        },
        onBatch: (ev) => {
          mergeActiveLocaleEntries(
            streamLang,
            streamLabel,
            streamDir,
            ev.entries ?? {},
            true
          );
          state.i18nTranslateCompleted = ev.completed;
          state.i18nTranslateTotal = Math.max(ev.total || state.i18nTranslateTotal, 1);
          const now = Date.now();
          if (now - lastRenderAt > 250 || ev.batch === ev.total_batches) {
            lastRenderAt = now;
            renderRegionsPreservingOverrideInput();
          }
        },
        onDone: async (ev) => {
          state.i18nTranslating = false;
          if (ev.lang && ev.lang !== "en") {
            setActiveLocaleBundle(
              ev.lang,
              ev.label || streamLabel,
              ev.dir === "rtl" ? "rtl" : "ltr",
              ev.entries ?? {}
            );
          } else {
            switchActiveLocale("en");
          }
          const refreshedStatus = await sidecarGetI18nStatus(ev.lang);
          if (refreshedStatus) state.i18nStatus = refreshedStatus;
          if (ev.error) {
            state.i18nStatusMsg = `${t("common.error_prefix")} ${ev.error}`;
          } else if (ev.cancelled) {
            if (!silent) {
              state.i18nStatusMsg = t("i18n.status_cancelled", {
                done: ev.translated_now,
              });
            }
          } else if (!silent) {
            state.i18nStatusMsg = t("i18n.status_translated_done", {
              count: ev.translated_now,
              label: ev.label,
              model: ev.model,
            });
          }
          if (cardCtx && ev.ok) {
            updateSettingsCardState(cardCtx.msgId, cardCtx.cardId, (c) => ({
              ...c,
              resolved: true,
              resolution_note: t("i18n.card_done", {
                label: ev.label,
                count: Object.keys(ev.entries ?? {}).length,
              }),
              resolution_note_key: "i18n.card_done",
              resolution_note_vars: {
                label: ev.label,
                count: Object.keys(ev.entries ?? {}).length,
              },
            }));
          }
          renderAllRegions();
          if (!silent || ev.error) {
            showAppToast(state.i18nStatusMsg, ev.error ? "danger" : "info");
          }
        },
        onError: (err) => {
          state.i18nTranslating = false;
          state.i18nStatusMsg = `${t("common.error_prefix")} ${err}`;
          renderAllRegions();
          showAppToast(state.i18nStatusMsg, "danger");
        },
      }
    );
  } catch (err) {
    state.i18nTranslating = false;
    if (!silent) {
      state.i18nStatusMsg = `${t("common.error_prefix")} ${String(err)}`;
    }
    renderAllRegions();
    if (!silent) {
      showAppToast(state.i18nStatusMsg, "danger");
    }
  } finally {
    state.i18nTranslating = false;
  }
}

async function handleSelectUiLanguage(
  rawLang: string,
  cardCtx?: { msgId: string; cardId: string }
): Promise<void> {
  const manifest = getCatalogManifestRecord();
  const res = await sidecarSwitchI18nLanguage({
    lang: rawLang,
    catalog: manifest,
    sync_missing: false,
  });
  if (!res.ok) {
    state.i18nStatusMsg = `${t("common.error_prefix")} ${res.error ?? "failed"}`;
    renderAllRegions();
    showAppToast(state.i18nStatusMsg, "danger");
    return;
  }
  state.i18nStatus = res;
  if (res.active_locale === "en") {
    switchActiveLocale("en");
  } else {
    const bundle = await sidecarGetI18nBundle(res.active_locale);
    setActiveLocaleBundle(
      res.active_locale,
      res.active_label || res.active_locale,
      res.active_dir === "rtl" ? "rtl" : "ltr",
      bundle?.entries ?? {}
    );
  }
  state.i18nStatusMsg = t("i18n.status_switched", { label: res.active_label });
  if (cardCtx) {
    updateSettingsCardState(cardCtx.msgId, cardCtx.cardId, (c) => ({
      ...c,
      resolved: true,
      resolution_note: t("i18n.status_switched", { label: res.active_label }),
    }));
  }
  renderAllRegions();
  showAppToast(state.i18nStatusMsg);

  const missingOrStale =
    (res.target?.missing ?? 0) + (res.target?.stale ?? 0);
  if (res.active_locale !== "en" && missingOrStale > 0 && !state.i18nTranslating) {
    const syncKey = `${res.active_locale}:${res.default_model}:${res.target.missing}:${res.target.stale}`;
    i18nAutoSyncKey = syncKey;
    void handleTranslateUiLanguage(res.active_locale, false, true);
  }
}

async function syncAppI18nState(
  triggerBackgroundIfNeeded = true,
  syncLocaleFromServer = false
): Promise<void> {
  const st = await sidecarGetI18nStatus();
  if (!st || !st.ok) return;
  state.i18nStatus = st;
  const serverLocale = st.active_locale || "en";
  if (serverLocale !== "en") {
    const bundle = await sidecarGetI18nBundle(serverLocale);
    setActiveLocaleBundle(
      serverLocale,
      st.active_label || serverLocale,
      st.active_dir === "rtl" ? "rtl" : "ltr",
      bundle?.entries ?? {}
    );
    renderRegionsPreservingOverrideInput();
    if (
      triggerBackgroundIfNeeded &&
      !state.i18nTranslating &&
      !st.job?.running &&
      (st.target.missing > 0 || st.target.stale > 0)
    ) {
      const syncKey = `${serverLocale}:${st.default_model}:${st.target.missing}:${st.target.stale}`;
      if (i18nAutoSyncKey !== syncKey) {
        i18nAutoSyncKey = syncKey;
        void handleTranslateUiLanguage(serverLocale, false, true);
      }
    }
  } else if (syncLocaleFromServer && getUiLocale() !== "en") {
    switchActiveLocale("en");
    renderRegionsPreservingOverrideInput();
  }
}

let googleOAuthPollTimer: number | null = null;
let drivesOAuthPollTimer: number | null = null;
let drivesRefreshSeq = 0;

async function refreshDrivesState(
  renderAfter = false,
  opts?: { showLoading?: boolean; renderImmediately?: boolean }
): Promise<void> {
  const showLoading = opts?.showLoading ?? renderAfter;
  const renderImmediately = opts?.renderImmediately ?? showLoading;
  const seq = ++drivesRefreshSeq;
  if (showLoading) {
    state.drivesLoading = true;
    if (
      renderImmediately &&
      state.activeDetail?.conversation.origin === "drives" &&
      state.activeTabId.startsWith("drives-lane:")
    ) {
      renderViewportRegion();
    }
  }
  try {
    const [statusRes, listRes, createTargets] = await Promise.all([
      sidecarFetchDrivesStatus(),
      sidecarFetchDrivesList({
        folder_key: state.drivesFolderKey,
        provider: state.drivesProviderFilter,
        file_type: state.drivesFileTypeFilter,
        owner: state.drivesOwnerFilter,
        query: state.drivesSearchQuery,
      }),
      sidecarFetchDriveCreateTargets(),
    ]);
    if (seq !== drivesRefreshSeq) {
      return;
    }
    if (statusRes) {
      state.drivesStatus = statusRes;
    }
    if (listRes && listRes.ok) {
      state.drivesFolderKey = listRes.folder_key;
      state.drivesParentKey = listRes.parent_key;
      state.drivesBreadcrumbs = listRes.breadcrumbs;
      state.drivesItems = listRes.items;
      state.drivesFacets = listRes.facets;
      state.drivesScope = listRes.scope;
    }
    state.drivesCreateTargets = createTargets;
  } finally {
    if (seq === drivesRefreshSeq) {
      state.drivesLoading = false;
      if (renderAfter) {
        renderAllRegions();
      }
    }
  }
}

function stepDrivesBack(): void {
  const prev = state.drivesNavStack.pop();
  if (!prev) return;
  state.drivesFolderKey = prev.folderKey;
  state.drivesProviderFilter = prev.provider;
  state.drivesFileTypeFilter = prev.fileType;
  state.drivesOwnerFilter = prev.owner;
  state.drivesSearchQuery = prev.query;
  void refreshDrivesState(true);
}

function stepDrivesUp(): void {
  if (state.drivesParentKey === null || state.drivesFolderKey === "") return;
  pushDrivesNavHistory();
  state.drivesFolderKey = state.drivesParentKey;
  state.drivesSearchQuery = "";
  void refreshDrivesState(true);
}

async function handleStartDrivesOAuthFlow(
  provider: "gdrive" | "onedrive",
  payload: {
    client_secret_json?: string;
    client_id?: string;
    tenant_id?: string;
    login_hint?: string;
  }
): Promise<void> {
  if (drivesOAuthPollTimer !== null) {
    window.clearInterval(drivesOAuthPollTimer);
    drivesOAuthPollTimer = null;
  }
  state.drivesStatusMessage = t("main.oauth_preparing_session");
  renderViewportRegion();

  const res =
    provider === "gdrive"
      ? await sidecarConnectGoogleDrive({
          client_secret_json: payload.client_secret_json,
          login_hint: payload.login_hint,
          hd: "hellofresh.com",
        })
      : await sidecarStartOneDriveConnect({
          client_id: payload.client_id,
          tenant_id: payload.tenant_id,
          login_hint: payload.login_hint,
        });

  if (!res.ok || !res.auth_url || !res.session_id) {
    state.drivesStatusMessage = `${t("common.error_prefix")} ${res.error ?? t("main.oauth_err_start")}`;
    renderViewportRegion();
    return;
  }

  const sessionId = res.session_id;
  const authUrl = res.auth_url;
  const tabTitle =
    provider === "gdrive" ? "Google Drive Sign-In" : "OneDrive Sign-In";

  const drivesConv =
    state.conversations.find((c) => c.origin === "drives") ??
    (await apiEnsureDrivesConversation());
  const authTab = await apiOpenTab(drivesConv.id, authUrl, tabTitle);
  state.activeDetail = await apiGetConversation(drivesConv.id);
  state.activeTabId = authTab.id;
  state.compareMode = false;
  state.drivesStatusMessage = t("main.oauth_complete_tab", {
    uri: res.redirect_uri ?? "loopback",
  });
  renderAllRegions();

  const startedAt = Date.now();
  drivesOAuthPollTimer = window.setInterval(() => {
    void (async () => {
      if (Date.now() - startedAt > 300_000) {
        if (drivesOAuthPollTimer !== null) {
          window.clearInterval(drivesOAuthPollTimer);
          drivesOAuthPollTimer = null;
        }
        state.drivesStatusMessage = t("main.oauth_timeout");
        renderAllRegions();
        return;
      }
      const st =
        provider === "gdrive"
          ? await sidecarFetchDrivesStatus(sessionId, "")
          : await sidecarFetchDrivesStatus("", sessionId);
      if (!st) return;
      state.drivesStatus = st;
      const sess = provider === "gdrive" ? st.google.session : st.onedrive.session;
      if (!sess || sess.status === "pending") return;

      if (drivesOAuthPollTimer !== null) {
        window.clearInterval(drivesOAuthPollTimer);
        drivesOAuthPollTimer = null;
      }

      if (sess.status === "authorized") {
        state.drivesStatusMessage = "";
        state.drivesAccountsOpen = false;
        try {
          await apiCloseTab(authTab.id);
        } catch {
          // Ignore if user already closed callback tab
        }
        if (state.activeDetail?.conversation.id === drivesConv.id) {
          state.activeDetail = await apiGetConversation(drivesConv.id);
          state.activeTabId = "drives-lane:files";
        }
        await sidecarSyncDrives({
          providers: [provider],
          blocking: true,
        });
        await refreshDrivesState(false);
        await refreshLists();
        renderAllRegions();
      } else {
        state.drivesStatusMessage = `${t("common.error_prefix")} ${sess.error || "Authorization failed."}`;
        renderAllRegions();
      }
    })();
  }, 1100);
}

async function handleStartGoogleOAuthInBrowserTab(payload?: {
  client_id?: string;
  client_secret?: string;
  client_secret_json?: string;
  scopes?: string[] | string;
  connect_gmail?: boolean;
  redirect_port?: number;
  existing_session_id?: string;
  existing_auth_url?: string;
}): Promise<void> {
  if (googleOAuthPollTimer !== null) {
    window.clearInterval(googleOAuthPollTimer);
    googleOAuthPollTimer = null;
  }

  let sessionId = payload?.existing_session_id ?? "";
  let authUrl = payload?.existing_auth_url ?? "";
  let redirectUri = "";

  if (!sessionId || !authUrl) {
    state.googleOAuthMessage = t("main.oauth_preparing_session");
    state.mailStatusMessage = t("main.oauth_preparing_tab");
    renderViewportRegion();

    const res = await sidecarStartGoogleOAuthLogin(payload ?? {});
    if (!res.ok || !res.auth_url || !res.session_id) {
      const errTxt = `${t("common.error_prefix")} ${res.error ?? t("main.oauth_err_start")}`;
      state.googleOAuthMessage = errTxt;
      state.mailStatusMessage = errTxt;
      renderViewportRegion();
      return;
    }
    sessionId = res.session_id;
    authUrl = res.auth_url;
    redirectUri = res.redirect_uri ?? "loopback";
  }

  state.googleOAuthSessionId = sessionId;
  state.googleOAuthMessage = t("main.oauth_complete_tab", { uri: redirectUri || "loopback" });
  state.mailStatusMessage = t("main.oauth_opened_mail");

  // Open Google consent URL in a real live Satz Browser tab (stay inside Settings if opened from Settings Chat)
  const oauthOrigin = state.activeDetail?.conversation.origin;
  if (state.activeDetail && (oauthOrigin === "settings" || oauthOrigin === "news_settings")) {
    const cid = state.activeDetail.conversation.id;
    const tab = await apiOpenTab(cid, authUrl, t("main.oauth_google_signin_tab"));
    state.activeDetail = await apiGetConversation(cid);
    state.activeTabId = tab.id;
    state.compareMode = false;
    renderAllRegions();
  } else {
    await startDirectBrowsing(authUrl, t("main.oauth_google_signin_tab"));
  }

  const startedAt = Date.now();
  googleOAuthPollTimer = window.setInterval(() => {
    void (async () => {
      if (Date.now() - startedAt > 300_000) {
        if (googleOAuthPollTimer !== null) {
          window.clearInterval(googleOAuthPollTimer);
          googleOAuthPollTimer = null;
        }
        state.googleOAuthMessage = t("main.oauth_timeout");
        renderAllRegions();
        return;
      }
      const st = await sidecarFetchGoogleOAuthStatus(sessionId);
      if (!st) return;
      state.googleOAuthStatus = st;
      const sess = st.session;
      if (!sess || sess.status === "pending") return;

      if (googleOAuthPollTimer !== null) {
        window.clearInterval(googleOAuthPollTimer);
        googleOAuthPollTimer = null;
      }
      if (sess.status === "authorized") {
        state.googleOAuthMessage = t("main.oauth_signed_in", {
          email: sess.email,
          gmail: sess.gmail_connected ? t("main.oauth_gmail_suffix") : "",
        });
        state.mailStatusMessage = sess.gmail_connected
          ? t("main.oauth_gmail_connected_syncing", { email: sess.email })
          : t("main.oauth_google_signed_in_short", { email: sess.email });
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        await refreshMailState();
        await refreshLists();
      } else {
        state.googleOAuthMessage = `${t("common.error_prefix")} ${sess.error || t("main.oauth_auth_failed")}`;
        state.mailStatusMessage = state.googleOAuthMessage;
      }
      renderAllRegions();
    })();
  }, 1200);
}

async function handleOpenDigestUrl(
  url: string,
  title?: string,
  convId?: string
): Promise<void> {
  if (url.startsWith("satzmail://message/")) {
    const mid = url.replace("satzmail://message/", "").split("/")[0].trim();
    if (mid) {
      await openEmailMessageTab(mid, (title || "").trim() || "mail");
    }
    return;
  }
  if (url.startsWith("satzbrain://entity/")) {
    const slug = url.replace("satzbrain://entity/", "").split("/")[0].trim();
    state.highlightedBrainSlug = slug || null;
    state.showBrainView = true;
    state.showKnowledgeView = false;
    const kb = await sidecarFetchKnowledge();
    if (kb) state.knowledge = kb;
    renderAllRegions();
    return;
  }
  if (url.startsWith("satzwatch://")) {
    if (convId) {
      await selectConversation(convId);
    }
    return;
  }
  await startDirectBrowsing(url);
}

function resetToNewConversation(): void {
  state.activeDetail = null;
  state.showKnowledgeView = false;
  state.showBrainView = false;
  state.compareMode = false;
  state.commandBarOpen = false;
  syncConfiguredChatModel(null, true);
  renderAllRegions();
  void refreshDigest();
}

async function runAppUpdateCheck(silent = false): Promise<void> {
  if (state.appUpdateStatus.checking || state.appUpdateStatus.installing) return;
  state.appUpdateStatus.checking = true;
  state.appUpdateStatus.error = "";
  if (!silent) {
    state.appUpdateStatus.message = t("settings.app_checking_update");
    renderViewportRegion();
  }
  const res = await checkForAppUpdate();
  state.appUpdateStatus.checking = false;
  state.appUpdateStatus.currentVersion = res.currentVersion;
  state.appUpdateStatus.availableVersion = res.availableVersion;
  state.appUpdateStatus.notes = res.notes;
  if (res.error) {
    state.appUpdateStatus.error = silent ? "" : t("settings.app_update_err", { error: res.error });
    state.appUpdateStatus.message = "";
  } else if (res.availableVersion) {
    state.appUpdateStatus.message = t("settings.app_update_available", {
      version: res.availableVersion,
    });
    showAppToast(state.appUpdateStatus.message);
  } else {
    state.appUpdateStatus.message = silent
      ? ""
      : t("settings.app_up_to_date", { version: res.currentVersion });
  }
  if (!silent || res.availableVersion) {
    renderViewportRegion();
  }
}

async function runAppUpdateInstall(): Promise<void> {
  if (state.appUpdateStatus.installing) return;
  state.appUpdateStatus.installing = true;
  state.appUpdateStatus.error = "";
  state.appUpdateStatus.progressPct = 0;
  renderViewportRegion();

  const res = await downloadAndInstallAppUpdate((pct) => {
    state.appUpdateStatus.progressPct = pct;
    state.appUpdateStatus.message = t("settings.app_updating_progress", { pct });
    renderViewportRegion();
  });
  if (!res.ok) {
    state.appUpdateStatus.installing = false;
    state.appUpdateStatus.error = t("settings.app_update_err", {
      error: res.error ?? "failed",
    });
    showAppToast(state.appUpdateStatus.error, "danger");
    renderViewportRegion();
  }
}

async function initApp(): Promise<void> {
  applyUiPreferences();
  mountShellSkeleton();

  void getInstalledAppVersion().then((ver) => {
    state.appUpdateStatus.currentVersion = ver;
  });
  window.setTimeout(() => {
    void runAppUpdateCheck(true);
  }, 5000);

  void fontsReady().then(async () => {
    await document.fonts.ready;
    if (!document.fonts.check("700 16px Besley")) {
      state.uiErrors.push({
        ts: Math.floor(Date.now() / 1000),
        scope: "fonts",
        message: "Bundled Besley 700 font unavailable; using fallback display font.",
      });
      renderStatusLine();
    }
  });

  bindKeyboardShortcuts({
    onOpenHome: () => {
      resetToNewConversation();
    },
    onNewConversation: () => {
      resetToNewConversation();
    },
    onFilterConversations: () => {
      handleToggleCommandBar();
    },
    onNewTab: () => {
      void handleCreateNewTab();
    },
    onCloseTab: () => {
      void handleCloseOrArchiveShortcut(false);
    },
    onArchiveConversation: () => {
      void handleCloseOrArchiveShortcut(true);
    },
    onSelectTabByNumber: (num: number) => {
      if (!state.activeDetail) return;
      if (num === 1) {
        state.compareMode = false;
        state.activeTabId = "chat";
        renderWorkspaceRegions();
        return;
      }
      const openTabs = state.activeDetail.tabs.filter((t) => t.is_open);
      const target = openTabs[num - 2];
      if (target) {
        state.compareMode = false;
        state.activeTabId = target.id;
        renderWorkspaceRegions();
      }
    },
    onFocusAddressBar: () => {
      const input = document.querySelector(
        ".address-input"
      ) as HTMLInputElement | null;
      input?.focus();
      input?.select();
    },
    onFillLogin: () => {
      if (state.activeTabId !== "chat") {
        void apiAutofillTabCredentials(state.activeTabId, false);
      }
    },
    onToggleAgentRail: () => {
      toggleAgentRail();
    },
    onToggleCompare: () => {
      handleToggleCompareMode();
    },
    onBookmarkCurrentPage: () => {
      void handleBookmarkCurrentPage();
    },
    onToggleBrain: () => {
      void handleToggleBrainView();
    },
    onEscape: () => {
      if (state.chatImagePreview) {
        state.chatImagePreview = null;
        renderChatImagePreviewOverlay();
        return;
      }
      if (state.profilePromptOpen) {
        state.profilePromptOpen = false;
        state.profilePromptDismissed = true;
        renderProfileUnlockOverlay(getProfilePromptActions());
        scheduleWebviewLayoutSync();
        return;
      }
      if (state.mailComposeModalOpen) {
        state.mailComposeModalOpen = false;
        renderComposeModalRegion();
        scheduleWebviewLayoutSync();
        return;
      }
      if (state.commandModelMenuOpen !== null) {
        const prevMenu = state.commandModelMenuOpen;
        state.commandModelMenuOpen = null;
        if (prevMenu === "overlay" && state.commandBarOpen) {
          renderCommandBarOverlay(getStartScreenActions());
        } else if (prevMenu === "start" && document.getElementById("start-command-bar-box")) {
          renderViewportRegion();
        }
        return;
      }
      if (state.commandBarOpen) {
        state.commandBarOpen = false;
        state.commandModelMenuOpen = null;
        renderCommandBarOverlay(getStartScreenActions());
        return;
      }
      if (
        state.openMenuConvId !== null ||
        state.openCodesPopoverTabId !== null ||
        state.renamingConvId !== null
      ) {
        state.openMenuConvId = null;
        state.openCodesPopoverTabId = null;
        state.renamingConvId = null;
        renderAllRegions();
        return;
      }
      if (state.telemetryOpen || state.profileMenuOpen) {
        state.telemetryOpen = false;
        state.profileMenuOpen = false;
        renderRailRegion();
        return;
      }
      if (state.composerModelMenuOpen) {
        state.composerModelMenuOpen = false;
        refreshChatContextIfVisible();
        return;
      }
      if (state.drivesCreateMenuOpen) {
        state.drivesCreateMenuOpen = false;
        if (state.activeTabId.startsWith("drives-lane:")) {
          renderViewportRegion();
        }
        return;
      }
      if (state.newsStoryMenuId !== null) {
        state.newsStoryMenuId = null;
        if (state.activeTabId.startsWith("news-lane:")) {
          renderViewportRegion();
        }
        return;
      }
      if (state.showErrorLog) {
        state.showErrorLog = false;
        renderStatusLine();
        return;
      }
      if (state.showBrainView) {
        state.showBrainView = false;
        state.highlightedBrainSlug = null;
        renderAllRegions();
        return;
      }
      if (state.showKnowledgeView) {
        state.showKnowledgeView = false;
        renderAllRegions();
        return;
      }
      if (state.compareMode) {
        state.compareMode = false;
        renderWorkspaceRegions();
      }
    },
  });

  window.addEventListener("click", (e: MouseEvent) => {
    const target = e.target as HTMLElement | null;
    if (!target) return;
    let changed = false;
    let railChanged = false;
    if (
      state.openMenuConvId !== null &&
      !target.closest(".row-menu-pop") &&
      !target.closest("[data-menu-conv-id]")
    ) {
      state.openMenuConvId = null;
      railChanged = true;
    }
    if (
      state.telemetryOpen &&
      !target.closest("#telemetry-popover") &&
      !target.closest("#rail-telemetry-btn") &&
      !target.closest("#region-error-log-overlay")
    ) {
      state.telemetryOpen = false;
      railChanged = true;
    }
    if (
      state.profileMenuOpen &&
      !target.closest("#rail-profile-menu") &&
      !target.closest("#rail-profile-btn")
    ) {
      state.profileMenuOpen = false;
      railChanged = true;
    }
    if (
      state.showErrorLog &&
      !target.closest("#region-error-log-overlay") &&
      !target.closest("#status-error-log-btn")
    ) {
      state.showErrorLog = false;
      renderStatusLine();
    }
    if (
      state.openCodesPopoverTabId !== null &&
      !target.closest("[data-codes-pill-tab]") &&
      !target.closest("[data-copy-promo-code]")
    ) {
      state.openCodesPopoverTabId = null;
      changed = true;
    }
    if (
      state.composerModelMenuOpen &&
      !target.closest(".model-chip-anchor")
    ) {
      state.composerModelMenuOpen = false;
      refreshChatContextIfVisible();
    }
    if (
      state.drivesCreateMenuOpen &&
      !target.closest(".drives-create-anchor")
    ) {
      state.drivesCreateMenuOpen = false;
      if (state.activeTabId.startsWith("drives-lane:")) {
        renderViewportRegion();
      }
    }
    if (
      state.newsStoryMenuId !== null &&
      !target.closest(".story-more-anchor")
    ) {
      state.newsStoryMenuId = null;
      if (state.activeTabId.startsWith("news-lane:")) {
        renderViewportRegion();
      }
    }
    if (
      state.commandModelMenuOpen !== null &&
      !target.closest(".model-chip-anchor")
    ) {
      const prevMenu = state.commandModelMenuOpen;
      state.commandModelMenuOpen = null;
      if (prevMenu === "overlay" && state.commandBarOpen) {
        renderCommandBarOverlay(getStartScreenActions());
      } else if (prevMenu === "start" && document.getElementById("start-command-bar-box")) {
        renderViewportRegion();
      }
    }
    if (changed) {
      renderAllRegions();
    } else if (railChanged) {
      renderRailRegion();
    }
  });

  window.addEventListener("keydown", (e: KeyboardEvent) => {
    if (
      state.activeDetail?.conversation.origin === "drives" &&
      state.activeTabId === "drives-lane:files" &&
      e.altKey &&
      !e.ctrlKey &&
      !e.metaKey
    ) {
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        stepDrivesBack();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        stepDrivesUp();
      }
    }
  });

  window.matchMedia?.("(prefers-color-scheme: dark)")?.addEventListener("change", () => {
    if (getUiThemePref() === "system") {
      renderRailRegion();
      paintNewsWordmark();
      if (document.querySelector(".email-frame")) {
        renderViewportRegion();
      }
    }
  });

  if (typeof MutationObserver !== "undefined") {
    const themeObserver = new MutationObserver(() => {
      paintNewsWordmark();
      if (document.querySelector(".email-frame")) {
        renderViewportRegion();
      }
    });
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
  }

  window.addEventListener("keydown", (e: KeyboardEvent) => {
    void handleMailSingleKeyShortcuts(e);
  });

  document.addEventListener("paste", (e: ClipboardEvent) => {
    if (e.defaultPrevented) return;
    if (
      state.showKnowledgeView ||
      state.showBrainView ||
      state.commandBarOpen ||
      state.profilePromptOpen ||
      state.mailComposeModalOpen ||
      state.chatImagePreview ||
      document.querySelector(".modal-backdrop")
    ) {
      return;
    }
    const convId = state.activeDetail?.conversation.id ?? "";
    if (!convId || isConvStreaming(convId)) return;
    const composerInput = document.getElementById("chat-composer-input");
    if (!composerInput) return;

    const target = e.target as HTMLElement | null;
    if (target?.closest?.("#chat-composer-box")) return;

    const active = document.activeElement as HTMLElement | null;
    if (
      active &&
      (active.tagName === "INPUT" ||
        active.tagName === "TEXTAREA" ||
        active.tagName === "SELECT" ||
        active.isContentEditable)
    ) {
      return;
    }

    const files = extractImageFilesFromDataTransfer(e.clipboardData);
    if (files.length === 0) return;

    const plainText = e.clipboardData?.getData("text/plain") ?? "";
    if (!plainText.trim()) {
      e.preventDefault();
    }

    const panelContainer = composerInput.closest(
      "#chat-main-container, #site-tab-agent-rail, #compare-agent-rail"
    ) as HTMLElement | null;
    void addChatImageFiles(files, convId, panelContainer, getChatActions());
  });

  window.addEventListener("resize", () => {
    scheduleWebviewLayoutSync();
  });

  resizeObserver = new ResizeObserver(() => {
    scheduleWebviewLayoutSync();
  });

  await listen<TabPageEvent>("tab-page-event", (event) => {
    void handleTabPageEvent(event.payload);
  });

  await listen<TabNewWindowEvent>("tab-new-window-requested", (event) => {
    const payload = event.payload;
    if (!payload?.url || !state.activeDetail) return;
    if (
      payload.source_tab_id &&
      !state.activeDetail.tabs.some((t) => t.id === payload.source_tab_id)
    ) {
      return;
    }
    const activate = payload.background !== true;
    void handleOpenUrlAsTab(payload.url, extractDomain(payload.url), activate);
  });

  await listen<string>("menu-shortcut", (event) => {
    handleMenuShortcut(event.payload);
  });

  await listen<string>("tab-list-updated", async (event) => {
    const targetCid = String(event.payload || "").trim();
    const curCid = state.activeDetail?.conversation.id ?? "";
    if (!curCid || (targetCid && targetCid !== curCid)) return;
    state.activeDetail = await apiGetConversation(curCid);
    renderTabStripRegion();
    renderViewportRegion();
  });

  await refreshLists();
  try {
    await apiEnsureNewsConversation();
    await apiEnsureDrivesConversation();
    await apiEnsureSettingsConversation();
    await apiEnsureNewsSettingsConversation();
    await apiEnsureNewsPerspectivesConversation();
  } catch {
    // Non-fatal if DB call fails in browser-only Vite dev preview
  }
  renderAllRegions();

  void pollSidecarState();
}

function handleMenuShortcut(cmd: string): void {
  if (cmd === "open_home") {
    resetToNewConversation();
  } else if (cmd === "new_conversation") {
    resetToNewConversation();
  } else if (cmd === "toggle_brain") {
    void handleToggleBrainView();
  } else if (cmd === "filter_conversations") {
    handleToggleCommandBar();
  } else if (cmd === "new_tab") {
    void handleCreateNewTab();
  } else if (cmd === "close_tab") {
    void handleCloseOrArchiveShortcut(false);
  } else if (cmd === "archive_conversation") {
    void handleCloseOrArchiveShortcut(true);
  } else if (cmd === "tab_chat") {
    if (state.activeDetail) {
      state.compareMode = false;
      state.activeTabId = "chat";
      renderWorkspaceRegions();
    }
  } else if (cmd.startsWith("tab_")) {
    const num = Number(cmd.replace("tab_", ""));
    if (state.activeDetail && num >= 2) {
      const openTabs = state.activeDetail.tabs.filter((t) => t.is_open);
      const target = openTabs[num - 2];
      if (target) {
        state.compareMode = false;
        state.activeTabId = target.id;
        renderWorkspaceRegions();
      }
    }
  } else if (cmd === "focus_address") {
    const input = document.querySelector(
      ".address-input"
    ) as HTMLInputElement | null;
    input?.focus();
    input?.select();
  } else if (cmd === "toggle_agent_rail") {
    toggleAgentRail();
  } else if (cmd === "toggle_compare") {
    handleToggleCompareMode();
  } else if (cmd === "bookmark_current") {
    void handleBookmarkCurrentPage();
  } else if (cmd === "fill_login") {
    if (state.activeTabId !== "chat") {
      void apiAutofillTabCredentials(state.activeTabId, false);
    }
  }
}

function getRailSignature(): string {
  const acctSig = state.mailAccounts
    .map((a) => `${a.id}:${a.inbox_unread ?? 0}:${a.message_count ?? 0}`)
    .join(",");
  return [
    Boolean(state.knowledge.profile?.unlocked),
    state.mailCounts.inbox_unread,
    state.sidecar.mail?.inbox_unread ?? 0,
    acctSig,
    state.newsStories.length,
    state.sidecar.news?.clusters ?? 0,
    state.drivesStatus?.total_files ?? 0,
    state.sidecar.drives?.total_files ?? 0,
    state.conversations.length,
  ].join("|");
}

async function pollSidecarState(): Promise<void> {
  if (sidecarPollInFlight) return;
  sidecarPollInFlight = true;
  let modelChanged = false;
  const prevRailSig = getRailSignature();
  try {
    // Fast-path startup: /knowledge reads SQLite in <5 ms without triggering PyTorch/CUDA init,
    // so probing /knowledge with a short connect timeout surfaces the Unlock Profile modal immediately.
    let earlyKb = null;
    if (!state.knowledge.profile) {
      earlyKb = await sidecarFetchKnowledge(!state.sidecar.online ? 450 : undefined);
      if (earlyKb) {
        state.knowledge = earlyKb;
        if (!earlyKb.profile?.unlocked && !state.profilePromptDismissed) {
          state.profilePromptOpen = true;
          renderProfileUnlockOverlay(getProfilePromptActions());
          scheduleWebviewLayoutSync();
        }
        renderRailRegion();
        if (!state.activeDetail && !state.showKnowledgeView && !state.showBrainView) {
          renderViewportRegion();
        }
      } else if (!state.sidecar.online) {
        renderStatusLine();
        return;
      }
    }

    // Once /knowledge responds (or after initial boot), allow full /health completion for cold torch probe.
    const healthTimeout = !state.sidecar.online && !earlyKb ? 2000 : undefined;
    state.sidecar = await sidecarFetchHealth(healthTimeout);
    if (state.sidecar.online) {
      if (syncConfiguredChatModel(state.sidecar.model_config ?? null)) {
        modelChanged = true;
      }
      if (state.doctorRoles.length === 0) {
        state.doctorRoles = await sidecarFetchDoctor();
      }
      if (!state.routingPolicy) {
        void refreshRoutingPolicy();
      }
      if (!i18nBootSynced) {
        i18nBootSynced = true;
        void syncAppI18nState(true, false);
      }
      if (state.sidecar.mail?.counts) {
        state.mailCounts = state.sidecar.mail.counts;
      }
      void sidecarSyncBookmarks(state.bookmarks);
      void ensureBookmarkFaviconsResolved();

      const kb = earlyKb ?? state.knowledge;
      if (state.sidecar.drives && !state.drivesStatus) {
        state.drivesStatus = state.sidecar.drives;
      }
      if (!state.profileUnlocking) {
        if (!kb.profile) {
          const [freshKb, mCfg] = await Promise.all([
            sidecarFetchKnowledge(),
            sidecarGetModelConfig(),
          ]);
          if (mCfg && syncConfiguredChatModel(mCfg, Boolean(freshKb?.profile?.unlocked))) {
            modelChanged = true;
          }
          if (freshKb) {
            state.knowledge = freshKb;
            if (freshKb.profile?.unlocked) {
              state.profilePromptOpen = false;
              state.postUnlockLoading = true;
              initPostUnlockHydrationSteps(
                freshKb.profile?.active_profile?.name ?? freshKb.profile?.active_profile_id ?? ""
              );
              renderProfileUnlockOverlay(getProfilePromptActions());
              renderPostUnlockGlassOverlay();
              scheduleWebviewLayoutSync();
              try {
                await syncAfterProfileAuthChange(true);
              } finally {
                clearUnlockOverlayState();
              }
              renderAllRegions();
              scheduleWebviewLayoutSync();
            } else if (!state.profilePromptDismissed) {
              state.profilePromptOpen = true;
              renderProfileUnlockOverlay(getProfilePromptActions());
              scheduleWebviewLayoutSync();
            }
            renderRailRegion();
            if (!state.activeDetail && !state.showKnowledgeView && !state.showBrainView) {
              renderViewportRegion();
            }
          }
        } else if (earlyKb) {
          if (earlyKb.profile?.unlocked) {
            state.profilePromptOpen = false;
            state.postUnlockLoading = true;
            initPostUnlockHydrationSteps(
              earlyKb.profile?.active_profile?.name ?? earlyKb.profile?.active_profile_id ?? ""
            );
            renderProfileUnlockOverlay(getProfilePromptActions());
            renderPostUnlockGlassOverlay();
            scheduleWebviewLayoutSync();
            try {
              await syncAfterProfileAuthChange(true);
            } finally {
              clearUnlockOverlayState();
            }
            renderAllRegions();
            scheduleWebviewLayoutSync();
          }
        } else if (
          state.sidecar.profile &&
          (Boolean(state.sidecar.profile.unlocked) !== Boolean(kb.profile.unlocked) ||
            (state.sidecar.profile.active_profile_id ?? null) !==
              (kb.profile.active_profile_id ?? null))
        ) {
          const backendUnlocked = Boolean(state.sidecar.profile.unlocked);
          if (backendUnlocked) {
            state.profilePromptOpen = false;
            state.postUnlockLoading = true;
            initPostUnlockHydrationSteps(
              state.knowledge.profile?.profiles.find(
                (p) => p.id === state.sidecar.profile?.active_profile_id
              )?.name ??
                state.sidecar.profile?.active_profile_id ??
                ""
            );
            renderProfileUnlockOverlay(getProfilePromptActions());
            renderPostUnlockGlassOverlay();
            scheduleWebviewLayoutSync();
          }
          try {
            await syncAfterProfileAuthChange(backendUnlocked);
          } finally {
            clearUnlockOverlayState();
          }
          renderAllRegions();
          scheduleWebviewLayoutSync();
        } else if (state.knowledge.profile?.unlocked && state.profilePromptOpen) {
          state.profilePromptOpen = false;
          const mCfg = await sidecarGetModelConfig();
          if (mCfg && syncConfiguredChatModel(mCfg, true)) {
            modelChanged = true;
          }
          renderProfileUnlockOverlay(getProfilePromptActions());
          scheduleWebviewLayoutSync();
        } else if (state.knowledge.profile?.unlocked) {
          if ((state.sidecar.mail?.accounts_count ?? 0) > 0 && state.mailAccounts.length === 0) {
            const acctsRes = await sidecarGetMailAccounts();
            if (acctsRes.unlocked && acctsRes.accounts?.length) {
              state.mailAccounts = acctsRes.accounts;
            }
          }
          if ((state.sidecar.news?.clusters ?? 0) > 0 && state.newsStories.length === 0) {
            await refreshNewsState("stories");
          }
        }
      }

      const curRev = state.sidecar.digest_revision ?? null;
      const activeUnlocked = Boolean(state.knowledge.profile?.unlocked);
      const syncKey = activeUnlocked
        ? `unlocked:${state.knowledge.profile?.active_profile?.id ?? "default"}`
        : "locked";
      if (startupSyncKey !== syncKey) {
        triggerStartupSyncIfNeeded(syncKey);
      } else if (
        !state.digestRefreshing &&
        (state.digestUpdatedAt === 0 ||
          (curRev !== null && curRev !== state.digestRevision))
      ) {
        await refreshDigest(curRev);
      }
    }
    if (getRailSignature() !== prevRailSig) {
      renderRailRegion();
    }
    if (modelChanged && !isConvStreaming(state.activeDetail?.conversation.id)) {
      renderViewportRegion();
    }
    renderStatusLine();
  } finally {
    sidecarPollInFlight = false;
    const elapsedMs = Date.now() - sidecarBootStartedAt;
    const nextDelayMs = state.sidecar.online
      ? 6000
      : elapsedMs < 15000
        ? 120
        : 1500;
    scheduleSidecarPoll(nextDelayMs);
  }
}

function setShellAgentFolded(folded: boolean): void {
  const shell = document.getElementById("region-shell");
  if (shell) {
    shell.classList.toggle("agent-folded", folded);
  }
}

function toggleAgentRail(): void {
  const orig = state.activeDetail?.conversation.origin;
  if (orig === "settings" || orig === "news_settings") {
    return;
  }
  state.agentRailOpen = !state.agentRailOpen;
  setUiAgentFoldedPref(!state.agentRailOpen);
  setShellAgentFolded(!state.agentRailOpen);
  renderTopBarRegion();
  renderViewportRegion();
}

function mountAgentPanel(
  title: string,
  bodyId: string,
  isChatBody: boolean
): HTMLElement | null {
  const agent = document.getElementById("region-agent");
  if (!agent) return null;
  agent.innerHTML = `
    <div class="ag-h">
      <span class="label">${escapeHtml(title)}</span>
      <button
        id="agent-fold-btn"
        class="icon-btn"
        type="button"
        title="${escapeHtml(t("main.fold_agent_title", { mod: MOD_LABEL }))}"
      >
        ${icon("panel")}
      </button>
    </div>
    <div class="ag-body ${isChatBody ? "ag-chat" : ""}" id="${escapeHtml(bodyId)}"></div>
  `;
  agent.querySelector("#agent-fold-btn")?.addEventListener("click", () => {
    toggleAgentRail();
  });
  setShellAgentFolded(!state.agentRailOpen);
  return document.getElementById(bodyId);
}

function clearAgentPanel(): void {
  const agent = document.getElementById("region-agent");
  if (agent) {
    agent.innerHTML = "";
  }
  setShellAgentFolded(true);
}

function mountShellSkeleton(): void {
  const app = document.getElementById("app");
  if (!app) return;
  app.innerHTML = `
    <div class="shell agent-folded" id="region-shell">
      <aside class="side" id="region-rail"></aside>
      <main class="main">
        <header class="top hidden" id="region-top"></header>
        <div class="tabs hidden" id="region-tab-strip"></div>
        <div class="workspace-body" id="region-viewport"></div>
        <div id="region-toast" class="toast-host" aria-live="polite" aria-atomic="true"></div>
      </main>
      <aside class="agent" id="region-agent"></aside>
    </div>
  `;
  const shell = document.getElementById("region-shell");
  shell?.addEventListener("transitionend", (e) => {
    if ((e as TransitionEvent).propertyName === "grid-template-columns") {
      scheduleWebviewLayoutSync();
    }
  });
}

const faviconResolveInFlight = new Set<string>();
const faviconResolveAttempted = new Set<string>();

async function ensureBookmarkFaviconsResolved(): Promise<void> {
  const reqItems: Array<{
    url: string;
    icon_url?: string | null;
  }> = [];
  const seenUrls = new Set<string>();
  let uiUpdated = false;

  for (const b of state.bookmarks) {
    const origin = getOriginFromUrl(b.url);
    const savedIcon = b.favicon_url?.trim() || "";
    if (savedIcon && !state.failedFaviconSrcs[savedIcon]) {
      cacheSiteFavicon(b.url, savedIcon);
      if (savedIcon.startsWith("data:image/")) {
        continue;
      }
    }

    const cachedLocal =
      state.siteFavicons[b.url] ||
      (origin ? state.siteFavicons[origin] : "") ||
      "";
    if (
      cachedLocal &&
      !state.failedFaviconSrcs[cachedLocal] &&
      cachedLocal.startsWith("data:image/")
    ) {
      b.favicon_url = cachedLocal;
      uiUpdated = true;
      void apiSetBookmarkFavicon(b.id, cachedLocal);
      continue;
    }

    if (
      state.sidecar.online &&
      !faviconResolveInFlight.has(b.url) &&
      !faviconResolveAttempted.has(b.url) &&
      !seenUrls.has(b.url)
    ) {
      seenUrls.add(b.url);
      const hint =
        savedIcon && !state.failedFaviconSrcs[savedIcon]
          ? savedIcon
          : cachedLocal && !state.failedFaviconSrcs[cachedLocal]
            ? cachedLocal
            : null;
      reqItems.push({ url: b.url, icon_url: hint });
    }
  }

  for (const t of state.activeDetail?.tabs ?? []) {
    if (
      !t.is_open ||
      t.kind === "mail" ||
      t.kind === "compose" ||
      !t.url ||
      t.url === "about:blank" ||
      t.url.startsWith("satzmail://")
    ) {
      continue;
    }
    const origin = getOriginFromUrl(t.url);
    const cached =
      state.siteFavicons[t.url] ||
      (origin ? state.siteFavicons[origin] : "") ||
      "";
    if (
      (!cached || !cached.startsWith("data:image/")) &&
      state.sidecar.online &&
      !faviconResolveInFlight.has(t.url) &&
      !faviconResolveAttempted.has(t.url) &&
      !seenUrls.has(t.url)
    ) {
      seenUrls.add(t.url);
      reqItems.push({
        url: t.url,
        icon_url: cached && !state.failedFaviconSrcs[cached] ? cached : null,
      });
    }
  }

  if (uiUpdated) {
    renderRailRegion();
    renderTabStripRegion();
  }

  if (reqItems.length === 0 || !state.sidecar.online) return;

  for (const it of reqItems) {
    faviconResolveInFlight.add(it.url);
    faviconResolveAttempted.add(it.url);
  }

  try {
    const res = await sidecarResolveFavicons(reqItems);
    let anyNew = false;
    for (const b of state.bookmarks) {
      const origin = getOriginFromUrl(b.url);
      const resolved =
        res.icons[b.url] ?? (origin ? res.by_origin[origin] : undefined);
      if (resolved && resolved !== b.favicon_url) {
        b.favicon_url = resolved;
        cacheSiteFavicon(b.url, resolved);
        anyNew = true;
        void apiSetBookmarkFavicon(b.id, resolved);
      }
    }
    for (const it of reqItems) {
      const origin = getOriginFromUrl(it.url);
      const resolved =
        res.icons[it.url] ?? (origin ? res.by_origin[origin] : undefined);
      if (resolved) {
        cacheSiteFavicon(it.url, resolved);
        anyNew = true;
      }
    }
    if (anyNew) {
      renderRailRegion();
      renderTabStripRegion();
    }
  } finally {
    for (const it of reqItems) {
      faviconResolveInFlight.delete(it.url);
    }
  }
}

async function refreshLists(): Promise<void> {
  const [convs, bookmarks] = await Promise.all([
    apiListConversations(),
    apiListBookmarks(),
  ]);
  state.conversations = convs;
  for (const b of bookmarks) {
    const origin = getOriginFromUrl(b.url);
    const saved = b.favicon_url?.trim() || "";
    if (saved) {
      cacheSiteFavicon(b.url, saved);
    } else {
      const cached =
        state.siteFavicons[b.url] ||
        (origin ? state.siteFavicons[origin] : "") ||
        "";
      if (cached && !state.failedFaviconSrcs[cached]) {
        b.favicon_url = cached;
      }
    }
  }
  state.bookmarks = bookmarks;
  if (state.sidecar.online) {
    void sidecarSyncBookmarks(bookmarks);
  }
  void ensureBookmarkFaviconsResolved();
}

async function handleTabPageEvent(payload: TabPageEvent): Promise<void> {
  if (!state.activeDetail) return;
  const tab = state.activeDetail.tabs.find((t) => t.id === payload.tab_id);
  if (!tab) return;

  if (payload.url && payload.url !== tab.url) {
    tab.url = payload.url;
    delete state.tabTranslationState[tab.id];
    const addrEl = document.getElementById(
      `address-input-${tab.id}`
    ) as HTMLInputElement | null;
    if (addrEl && document.activeElement !== addrEl) {
      addrEl.value = payload.url;
    }
  } else if (
    payload.event_type === "load_finished" &&
    state.tabTranslationState[tab.id]?.status !== "translating"
  ) {
    delete state.tabTranslationState[tab.id];
  }
  if (payload.title && payload.title !== tab.title) {
    tab.title = payload.title;
  }

  if (payload.favicon_url && tab.url) {
    const cachedChanged = cacheSiteFavicon(tab.url, payload.favicon_url);
    const tabOrigin = getOriginFromUrl(tab.url);
    let bookmarkUpdated = false;
    for (const b of state.bookmarks) {
      const bmOrigin = getOriginFromUrl(b.url);
      if (b.url === tab.url || (tabOrigin && bmOrigin === tabOrigin)) {
        if (!b.favicon_url || !b.favicon_url.startsWith("data:image/")) {
          b.favicon_url = payload.favicon_url;
          bookmarkUpdated = true;
          void apiSetBookmarkFavicon(b.id, payload.favicon_url);
        }
      }
    }
    if (cachedChanged || bookmarkUpdated) {
      renderRailRegion();
      renderTabStripRegion();
    }
    if (!payload.favicon_url.startsWith("data:image/") && state.sidecar.online) {
      faviconResolveAttempted.delete(tab.url);
      void ensureBookmarkFaviconsResolved();
    }
  }

  if (typeof payload.has_password_field === "boolean") {
    state.tabHasPasswordField[tab.id] = payload.has_password_field;
    const prevCanFill = Boolean(state.tabCanFillLogin[tab.id]);
    if (payload.has_password_field && tab.url) {
      const matched = await sidecarMatchPasswordForUrl(tab.url);
      state.tabCanFillLogin[tab.id] = matched;
    } else {
      state.tabCanFillLogin[tab.id] = false;
    }
    if (prevCanFill !== Boolean(state.tabCanFillLogin[tab.id])) {
      renderTopBarRegion();
    }
  }

  if (payload.event_type === "load_finished") {
    const refreshed = await apiGetConversation(
      state.activeDetail.conversation.id
    );
    if (refreshed) {
      state.activeDetail = refreshed;
      await refreshLists();
      renderRailRegion();
      renderTopBarRegion();
      renderTabStripRegion();
      renderStatusLine();
      refreshChatContextIfVisible();
    }
  } else {
    renderTopBarRegion();
    renderTabStripRegion();
    refreshChatContextIfVisible();
  }
}

function refreshChatContextIfVisible(): void {
  if (isConvStreaming(state.activeDetail?.conversation.id)) return;
  const chatEl =
    document.getElementById("chat-main-container") ??
    document.getElementById("site-tab-agent-rail") ??
    document.getElementById("compare-agent-rail");
  if (chatEl) {
    renderChatPanel(chatEl, getChatActions());
  }
}

function renderComposeModalRegion(): void {
  renderMailComposeModalOverlay({
    onChanged: () => {
      renderComposeModalRegion();
    },
    onClose: () => {
      state.mailComposeModalOpen = false;
      renderComposeModalRegion();
      scheduleWebviewLayoutSync();
    },
  });
}

function showAppToast(
  message: string,
  variant: "info" | "danger" = "info",
  durationMs = 2600
): void {
  const host = document.getElementById("region-toast");
  const clean = message.trim();
  if (!host || !clean) return;
  while (host.children.length >= 3) {
    host.firstElementChild?.remove();
  }
  const toast = document.createElement("div");
  toast.className = variant === "danger" ? "toast danger" : "toast";
  toast.textContent = clean;
  let gone = false;
  const dismiss = () => {
    if (gone) return;
    gone = true;
    toast.classList.add("leaving");
    setTimeout(() => toast.remove(), 180);
  };
  toast.addEventListener("click", dismiss);
  host.appendChild(toast);
  setTimeout(dismiss, durationMs);
}

function renderAllRegions(): void {
  renderRailRegion();
  renderWorkspaceRegions();
  renderStatusLine();
  renderCommandBarOverlay(getStartScreenActions());
  renderComposeModalRegion();
  renderPostUnlockGlassOverlay();
}

function renderWorkspaceRegions(): void {
  renderTopBarRegion();
  renderTabStripRegion();
  renderViewportRegion();
  renderStatusLine();
}

async function handleToggleBrainView(): Promise<void> {
  state.showBrainView = !state.showBrainView;
  if (state.showBrainView) {
    state.showKnowledgeView = false;
    const kb = await sidecarFetchKnowledge();
    if (kb) state.knowledge = kb;
  } else {
    state.highlightedBrainSlug = null;
  }
  renderAllRegions();
}

function renderRailRegion(): void {
  renderRail({
    onOpenHome: () => {
      resetToNewConversation();
    },
    onSelectConversation: (id) => {
      void selectConversation(id);
    },
    onSelectMailAccount: (convId, accountId) => {
      state.mailActiveAccountId = accountId;
      state.mailSearchRows = null;
      void selectConversation(convId);
    },
    onNewConversation: () => {
      resetToNewConversation();
    },
    onTogglePin: async (id) => {
      await apiPinConversation(id);
      await refreshLists();
      if (state.activeDetail?.conversation.id === id) {
        state.activeDetail = await apiGetConversation(id);
      }
      renderRailRegion();
    },
    onRenameConversation: async (id, newTitle) => {
      await apiRenameConversation(id, newTitle);
      await refreshLists();
      if (state.activeDetail?.conversation.id === id) {
        state.activeDetail = await apiGetConversation(id);
      }
      renderRailRegion();
    },
    onToggleArchive: async (id, archived) => {
      await apiArchiveConversation(id, archived);
      await refreshLists();
      if (state.activeDetail?.conversation.id === id && archived) {
        state.activeDetail = null;
      }
      renderAllRegions();
    },
    onDeleteConversation: async (id) => {
      await apiDeleteConversation(id);
      await refreshLists();
      if (state.activeDetail?.conversation.id === id) {
        state.activeDetail = null;
      }
      renderAllRegions();
    },
    onOpenBookmark: (url) => {
      void startDirectBrowsing(url);
    },
    onOpenBookmarkInNewTab: (url, title) => {
      if (state.activeDetail && state.activeDetail.conversation.origin !== "mail") {
        void handleOpenUrlAsTab(url, title || extractDomain(url), false);
      } else {
        void startDirectBrowsing(url, title);
      }
    },
    onBookmarkCurrent: () => {
      void handleBookmarkCurrentPage();
    },
    onRemoveBookmark: async (id) => {
      await apiRemoveBookmark(id);
      await refreshLists();
      renderRailRegion();
    },
    onOpenBrainView: () => {
      void handleToggleBrainView();
    },
    onOpenCommandBar: () => {
      handleToggleCommandBar();
    },
    onOpenKnowledgeView: async () => {
      if (state.activeDetail?.conversation.origin === "settings" && !state.showBrainView) {
        resetToNewConversation();
        return;
      }
      await openSettingsConversation("chat");
    },
    onOpenProfileUnlock: () => {
      state.profilePromptDismissed = false;
      state.profilePromptOpen = true;
      renderProfileUnlockOverlay(getProfilePromptActions());
      scheduleWebviewLayoutSync();
      renderRailRegion();
    },
    onLockProfile: async () => {
      state.revealedPasswords = {};
      await sidecarLockProfile();
      state.profileStatusMessage = t("main.profile_locked");
      await syncAfterProfileAuthChange(false);
      renderAllRegions();
    },
  });
}

async function handleTranslateTab(tabId: string, force = false): Promise<void> {
  const tab = state.activeDetail?.tabs.find((t) => t.id === tabId);
  if (!tab || !tab.url || tab.kind !== "site") return;
  const cur = state.tabTranslationState[tabId];
  if (cur?.status === "translating") return;

  if (!force && cur?.status === "translated" && cur.url === tab.url) {
    const nextShowing = cur.showingTranslated === false;
    const res = await apiApplyTabTranslationSegments(
      tabId,
      nextShowing ? "reapply" : "restore"
    );
    if (res.ok) {
      cur.showingTranslated = nextShowing;
      renderTopBarRegion();
      return;
    }
  }

  const targetLang = state.contentTranslationConfig?.primary_language || "en";
  state.tabTranslationState[tabId] = {
    status: "translating",
    url: tab.url,
    targetLang,
    blocksDone: 0,
    blocksTotal: 0,
  };
  renderTopBarRegion();

  const dom = await apiExtractTabTranslationDom(tabId);
  if (!dom.ok) {
    state.tabTranslationState[tabId] = {
      status: "error",
      url: tab.url,
      errorMsg: dom.error || "DOM extraction failed",
    };
    renderTopBarRegion();
    return;
  }

  if (dom.already_extracted && dom.has_cached_translation && !force) {
    const nextShowing = dom.showing_translated === false;
    const res = await apiApplyTabTranslationSegments(
      tabId,
      nextShowing ? "reapply" : "restore"
    );
    if (res.ok) {
      state.tabTranslationState[tabId] = {
        status: "translated",
        url: tab.url,
        sourceLang: cur?.sourceLang || dom.html_lang || "?",
        targetLang: cur?.targetLang || targetLang,
        showingTranslated: nextShowing,
        blocksDone: dom.block_count ?? dom.blocks?.length ?? 0,
        blocksTotal: dom.block_count ?? dom.blocks?.length ?? 0,
      };
      renderTopBarRegion();
      return;
    }
  }

  const blocks = dom.blocks ?? [];
  if (blocks.length === 0) {
    state.tabTranslationState[tabId] = { status: "idle", url: tab.url };
    renderTopBarRegion();
    return;
  }

  state.tabTranslationState[tabId] = {
    status: "translating",
    url: tab.url,
    sourceLang: dom.html_lang || undefined,
    targetLang,
    blocksDone: 0,
    blocksTotal: blocks.length,
  };
  renderTopBarRegion();

  let doneCount = 0;
  let applyChain: Promise<void> = Promise.resolve();
  let detectedSource = dom.html_lang || "?";
  let resolvedTarget = targetLang;
  let modelUsed = "";

  const finalEv = await sidecarTranslatePageStream(
    {
      url: dom.url || tab.url,
      title: dom.title || tab.title || "",
      html_lang: dom.html_lang || "",
      blocks,
      force,
    },
    (ev) => {
      if (ev.source_lang) detectedSource = ev.source_lang;
      if (ev.target_lang) resolvedTarget = ev.target_lang;
      if (ev.model) modelUsed = ev.model;

      if (ev.phase === "batch" && ev.translations) {
        const segMap = ev.translations;
        const nApplied = Object.keys(segMap).length;
        if (nApplied > 0) {
          applyChain = applyChain.then(async () => {
            await apiApplyTabTranslationSegments(tabId, "apply", segMap);
            doneCount += nApplied;
            const liveSt = state.tabTranslationState[tabId];
            if (liveSt && liveSt.status === "translating") {
              liveSt.blocksDone = Math.min(blocks.length, doneCount);
              liveSt.sourceLang = detectedSource;
              liveSt.targetLang = resolvedTarget;
              renderTopBarRegion();
            }
          });
        }
      }
    }
  );

  await applyChain;

  if (finalEv.skipped_allowed) {
    state.tabTranslationState[tabId] = {
      status: "allowed_notice",
      url: tab.url,
      sourceLang: finalEv.source_lang || detectedSource,
      targetLang: finalEv.target_lang || resolvedTarget,
    };
  } else if (finalEv.ok === false || finalEv.phase === "error") {
    state.tabTranslationState[tabId] = {
      status: "error",
      url: tab.url,
      errorMsg: finalEv.error || "translation failed",
    };
  } else {
    state.tabTranslationState[tabId] = {
      status: "translated",
      url: tab.url,
      sourceLang: finalEv.source_lang || detectedSource,
      targetLang: finalEv.target_lang || resolvedTarget,
      showingTranslated: true,
      model: finalEv.model || modelUsed,
      blocksDone: blocks.length,
      blocksTotal: blocks.length,
    };
  }
  renderTopBarRegion();
  renderStatusLine();
}

function renderTopBarRegion(): void {
  renderTopBar({
    onNavTab: (tabId, action) => {
      void apiControlTab(tabId, action);
    },
    onNavigateAddress: (tabId, rawVal) => {
      void (async () => {
        if (!state.activeDetail) return;
        const targetUrl = normalizeUrl(rawVal);
        await apiNavigateTab(tabId, targetUrl);
        state.activeDetail = await apiGetConversation(
          state.activeDetail.conversation.id
        );
        await refreshLists();
        renderRailRegion();
        renderTopBarRegion();
        renderTabStripRegion();
        renderViewportRegion();
        renderStatusLine();
      })();
    },
    onTranslateTab: (tabId, force = false) => {
      void handleTranslateTab(tabId, force);
    },
    onWatchTab: (tabId) => {
      const tab = state.activeDetail?.tabs.find((t) => t.id === tabId);
      if (tab && state.activeDetail) {
        void handleWatchTarget(
          state.activeDetail.conversation.id,
          tab.url,
          tab.title || extractDomain(tab.url)
        );
      }
    },
    onAutofillTab: (tabId) => {
      void apiAutofillTabCredentials(tabId, false);
    },
    onToggleCodesPopover: (tabId) => {
      const opening = state.openCodesPopoverTabId !== tabId;
      state.openCodesPopoverTabId = opening ? tabId : null;
      if (opening) {
        const tab = state.activeDetail?.tabs.find((t) => t.id === tabId);
        if (tab?.url) {
          void sidecarLogBehaviorEvent({
            event_type: "codes_check",
            domain: extractDomain(tab.url),
            url: tab.url,
          });
        }
      }
      renderTopBarRegion();
    },
    onRunComparer: () => {
      void handleRunComparer("compare these");
    },
    onExitCompare: () => {
      state.compareMode = false;
      renderWorkspaceRegions();
    },
    onToggleCompareMode: () => {
      handleToggleCompareMode();
    },
    onToggleAgentRail: () => {
      toggleAgentRail();
    },
    onNewTab: () => {
      void handleCreateNewTab();
    },
    onOpenCommandBar: () => {
      handleToggleCommandBar();
    },
    onClearDrivesSearch: () => {
      if (!state.drivesSearchQuery) return;
      state.drivesSearchQuery = "";
      void refreshDrivesState(true);
    },
  });
}

function selectMailAccountFilter(accountId: string | null): void {
  state.mailActiveAccountId = accountId;
  state.mailSearchRows = null;
  state.mailSelectedRowIdx = 0;
  if (!state.activeTabId.startsWith("lane:") && state.activeTabId !== "chat") {
    state.activeTabId = `lane:${state.mailActiveLane || "inbox"}`;
  }
  void (async () => {
    await refreshMailState();
    renderAllRegions();
  })();
}

async function loadSettingsPanelData(): Promise<void> {
  const [kb, docRoles, mCfg, gStatus, dStatus, pol, provReg, trCfg] = await Promise.all([
    sidecarFetchKnowledge(),
    sidecarFetchDoctor(),
    sidecarGetModelConfig(),
    sidecarFetchGoogleOAuthStatus(),
    sidecarFetchDrivesStatus(),
    sidecarFetchRoutingPolicy(),
    sidecarGetProviders(),
    sidecarGetTranslationConfig(),
  ]);
  if (kb) state.knowledge = kb;
  state.doctorRoles = docRoles;
  if (mCfg) {
    syncConfiguredChatModel(mCfg, false);
    ensureHfDownloadPolling();
  }
  state.googleOAuthStatus = gStatus;
  if (dStatus) state.drivesStatus = dStatus;
  if (pol && pol.ok) state.routingPolicy = pol;
  if (kb?.profile && !kb.profile.unlocked) {
    state.providerRegistry = null;
    state.contentTranslationConfig = null;
  } else {
    if (provReg) state.providerRegistry = provReg;
    if (trCfg && trCfg.ok) state.contentTranslationConfig = trCfg;
  }
  await Promise.all([refreshMailState(), syncAppI18nState(true, true)]);
  if (state.knowledge.profile?.unlocked) {
    try {
      await refreshNewsState("settings");
      if (state.activeDetail?.conversation.origin === "news_settings") {
        await seedNewsSettingsOnboardingIfEmpty(state.activeDetail.conversation.id);
      }
    } catch {
      // Non-fatal if sidecar warming
    }
  }
}

async function openSettingsConversation(targetTab = "chat"): Promise<void> {
  const settingsConv =
    state.conversations.find((c) => c.origin === "settings") ??
    (await apiEnsureSettingsConversation());
  await selectConversation(settingsConv.id);
  if (targetTab !== "chat") {
    state.activeTabId = targetTab;
    state.compareMode = false;
    renderAllRegions();
    await loadSettingsPanelData();
    if (
      state.activeDetail?.conversation.origin === "settings" &&
      state.activeTabId === targetTab
    ) {
      renderAllRegions();
    }
  }
}

async function seedNewsSettingsOnboardingIfEmpty(convId: string): Promise<void> {
  const detail = state.activeDetail;
  if (
    !detail ||
    detail.conversation.id !== convId ||
    detail.messages.length > 0 ||
    !state.knowledge.profile?.unlocked
  ) {
    return;
  }
  const ob = await sidecarFetchNewsSettingsOnboard();
  if (!ob.ok || !ob.needs_onboarding || !ob.prompt_text) {
    return;
  }
  if ((state.activeDetail?.messages.length ?? 0) > 0) return;
  const savedMsg = await apiAddMessage(
    convId,
    "assistant",
    ob.prompt_text,
    "news-settings-onboard",
    JSON.stringify([]),
    null,
    null,
    null,
    JSON.stringify({ ui_cards: ob.ui_cards ?? [] })
  );
  if (ob.ui_cards && ob.ui_cards.length > 0) {
    state.messageUiCards[savedMsg.id] = ob.ui_cards;
  }
  state.activeDetail = await apiGetConversation(convId);
  renderAllRegions();
}

async function openNewsSettingsConversation(targetTab = "chat"): Promise<void> {
  const nsConv =
    state.conversations.find((c) => c.origin === "news_settings") ??
    (await apiEnsureNewsSettingsConversation());
  await selectConversation(nsConv.id);
  try {
    await refreshNewsState("settings");
  } catch {
    // Profile may be locked
  }
  if (targetTab !== "chat") {
    state.activeTabId = targetTab;
    state.compareMode = false;
    renderAllRegions();
    return;
  }
  await seedNewsSettingsOnboardingIfEmpty(nsConv.id);
  renderAllRegions();
}

async function openNewsHome(lane: NewsLane = "stories"): Promise<void> {
  const newsConv =
    state.conversations.find((c) => c.origin === "news") ??
    (await apiEnsureNewsConversation());
  state.newsActiveLane = lane;
  await selectConversation(newsConv.id, { targetTabId: `news-lane:${lane}` });
  await refreshNewsState(lane);
  renderAllRegions();
}

async function handleSendPerspectivesTopic(
  topic: string,
  clusterId?: string,
  followedStoryId?: string
): Promise<void> {
  const cleanTopic = topic.trim();
  if (!cleanTopic || state.newsPerspectivesStream) return;

  state.newsActiveLane = "perspectives";
  state.activeTabId = "news-lane:perspectives";

  const pConv =
    state.conversations.find((c) => c.origin === "news_perspectives") ??
    (await apiEnsureNewsPerspectivesConversation());
  const pConvId = pConv.id;
  state.lastPromptByConv[pConvId] = cleanTopic;

  await apiAddMessage(pConvId, "user", cleanTopic, null, JSON.stringify([]));
  state.newsPerspectivesDetail = await apiGetConversation(pConvId);
  state.newsPerspectivesStream = {
    convId: pConvId,
    model: state.selectedModel,
    text: "",
    status: t("main.stream_web_search"),
    phase: "collecting",
    startedAt: Date.now(),
    steps: [],
    lastUserPrompt: cleanTopic,
  };
  renderViewportRegion();

  let lastPaint = 0;
  const paintThrottled = (force = false) => {
    const now = Date.now();
    if (force || now - lastPaint >= 75) {
      lastPaint = now;
      renderViewportRegion();
    }
  };

  try {
    const history = (state.newsPerspectivesDetail?.messages ?? [])
      .slice(-6)
      .map((m) => ({ role: m.role, content: m.content }));
    const res = await sidecarStreamNewsPerspectives(
      cleanTopic,
      {
        onStatus: (status, phase) => {
          if (state.newsPerspectivesStream) {
            state.newsPerspectivesStream.status = status;
            state.newsPerspectivesStream.phase = phase || "streaming";
            paintThrottled(false);
          }
        },
        onReplaceText: (txt) => {
          if (state.newsPerspectivesStream) {
            state.newsPerspectivesStream.text = txt;
            paintThrottled(true);
          }
        },
        onDelta: (delta) => {
          if (state.newsPerspectivesStream) {
            state.newsPerspectivesStream.text += delta;
            paintThrottled(false);
          }
        },
        onSourceStats: (stats) => {
          for (const st of stats) {
            state.sourceStats[st.id] = st;
          }
        },
      },
      {
        clusterId,
        followedStoryId,
        roles: state.modelConfig?.roles,
        messages: history,
      }
    );

    const streamedText = state.newsPerspectivesStream?.text ?? "";
    state.newsPerspectivesStream = null;

    let finalText = res.ok
      ? res.annotated_text || res.answer || streamedText
      : `${t("common.error_prefix")} ${res.error || t("main.err_news_query")}`;

    if (
      res.ok &&
      res.blind_spots &&
      res.blind_spots.length > 0 &&
      !finalText.toLowerCase().includes("blind spot")
    ) {
      finalText += `\n\n**${t("news.persp_blind_spots")}**\n${res.blind_spots.map((b) => `- ${b}`).join("\n")}`;
    }
    if (
      res.ok &&
      res.system_counterfactual &&
      !finalText.toLowerCase().includes("counterfactual")
    ) {
      finalText += `\n\n**${t("news.persp_counterfactual")}**: ${res.system_counterfactual}`;
    }

    const extrasObj = {
      cited_sources: res.sources ?? [],
      findings: res.findings ?? [],
      answer_meta: res.answer_meta ?? undefined,
    };
    const savedMsg = await apiAddMessage(
      pConvId,
      "assistant",
      finalText,
      res.model || state.selectedModel,
      JSON.stringify((res.sources ?? []).map((s) => s.url)),
      null,
      null,
      null,
      JSON.stringify(extrasObj)
    );
    if (res.sources && res.sources.length > 0) {
      state.messageCitedSources[savedMsg.id] = res.sources;
    }
    if (res.findings && res.findings.length > 0) {
      state.messageFindings[savedMsg.id] = res.findings;
    }
    if (res.answer_meta) {
      state.messageAnswerMeta[savedMsg.id] = res.answer_meta;
    }
    state.newsPerspectivesDetail = await apiGetConversation(pConvId);
    renderViewportRegion();
  } catch (err) {
    state.newsPerspectivesStream = null;
    await apiAddMessage(
      pConvId,
      "assistant",
      `${t("common.error_prefix")} ${String(err)}`,
      state.selectedModel,
      JSON.stringify([])
    );
    state.newsPerspectivesDetail = await apiGetConversation(pConvId);
    renderViewportRegion();
  }
}

let hfDownloadPollTimer: number | null = null;
const hfNotifiedDownloads = new Set<string>();

function ensureHfDownloadPolling(): void {
  const hasRunning = state.hfDownloads.some(
    (d) => d.state === "queued" || d.state === "downloading"
  );
  if (!hasRunning) {
    if (hfDownloadPollTimer !== null) {
      window.clearInterval(hfDownloadPollTimer);
      hfDownloadPollTimer = null;
    }
    return;
  }
  if (hfDownloadPollTimer !== null) return;
  hfDownloadPollTimer = window.setInterval(() => {
    void (async () => {
      const res = await sidecarListHfDownloads();
      if (!res.ok) return;
      state.hfDownloads = res.downloads;
      let finishedNow = false;
      for (const dl of res.downloads) {
        if (dl.state === "completed" && !hfNotifiedDownloads.has(dl.download_id)) {
          hfNotifiedDownloads.add(dl.download_id);
          finishedNow = true;
          state.modelConfigStatusMsg = t("main.lm_dl_done", { repo: dl.repo_id });
          showAppToast(state.modelConfigStatusMsg);
        } else if (dl.state === "error" && !hfNotifiedDownloads.has(dl.download_id)) {
          hfNotifiedDownloads.add(dl.download_id);
          finishedNow = true;
          state.modelConfigStatusMsg = t("main.lm_dl_failed", {
            repo: dl.repo_id,
            error: dl.error || "error",
          });
          showAppToast(state.modelConfigStatusMsg, "danger");
        }
      }
      const stillRunning = res.downloads.some(
        (d) => d.state === "queued" || d.state === "downloading"
      );
      if (!stillRunning && hfDownloadPollTimer !== null) {
        window.clearInterval(hfDownloadPollTimer);
        hfDownloadPollTimer = null;
      }
      if (finishedNow) {
        const [docRoles, mCfg, health] = await Promise.all([
          sidecarFetchDoctor(),
          sidecarGetModelConfig(),
          sidecarFetchHealth(),
        ]);
        state.doctorRoles = docRoles;
        state.sidecar = health;
        if (mCfg) syncConfiguredChatModel(mCfg, true);
      }
      renderViewportRegion();
    })();
  }, 1000);
}

async function openAddMailAccountSettings(): Promise<void> {
  state.settingsAccordionOpen.mail = true;
  await openSettingsConversation("settings-manual");
}

async function openModelsSettings(): Promise<void> {
  state.settingsAccordionOpen.models = true;
  await openSettingsConversation("settings-manual");
}

function renderTabStripRegion(): void {
  renderTabStrip({
    onSelectTab: (tabId) => {
      state.openMenuConvId = null;
      state.compareMode = false;
      state.activeTabId = tabId;
      if (tabId === "chat") {
        state.chatPinToBottom = true;
      }
      if (tabId === "settings-manual") {
        renderWorkspaceRegions();
        void loadSettingsPanelData().then(() => {
          if (
            state.activeDetail?.conversation.origin === "settings" &&
            state.activeTabId === "settings-manual"
          ) {
            renderWorkspaceRegions();
          }
        });
        return;
      }
      if (tabId === "news-settings-manual") {
        renderWorkspaceRegions();
        void refreshNewsState("settings").then(() => {
          if (
            state.activeDetail?.conversation.origin === "news_settings" &&
            state.activeTabId === "news-settings-manual"
          ) {
            renderWorkspaceRegions();
          }
        });
        return;
      }
      if (tabId.startsWith("lane:")) {
        const laneName = tabId.slice(5) as "inbox" | "pings" | "orders" | "promos";
        state.mailActiveLane = laneName;
        void (async () => {
          await refreshMailState();
          renderWorkspaceRegions();
        })();
        return;
      }
      if (tabId.startsWith("news-lane:")) {
        const rawLane = tabId.slice(10);
        const nLane: NewsLane =
          rawLane === "perspectives"
            ? "perspectives"
            : rawLane === "tracked"
              ? "tracked"
              : "stories";
        state.newsActiveLane = nLane;
        void (async () => {
          await refreshNewsState(nLane);
          renderWorkspaceRegions();
        })();
        return;
      }
      if (tabId.startsWith("drives-lane:")) {
        state.drivesLoading = true;
        renderWorkspaceRegions();
        void refreshDrivesState(true, { showLoading: true, renderImmediately: false });
        return;
      }
      renderWorkspaceRegions();
    },
    onToggleCompareCandidate: (tabId) => {
      const idx = state.compareTabIds.indexOf(tabId);
      if (idx >= 0) {
        state.compareTabIds.splice(idx, 1);
      } else if (state.compareTabIds.length < 4) {
        state.compareTabIds.push(tabId);
      }
      renderTabStripRegion();
    },
    onNewTab: () => {
      void handleCreateNewTab();
    },
    onCloseTab: (tabId) => {
      void handleCloseTab(tabId);
    },
    onToggleCompareMode: () => {
      handleToggleCompareMode();
    },
    onOpenNewsSettings: (targetTab = "chat") => {
      void openNewsSettingsConversation(targetTab);
    },
    onOpenNewsHome: () => {
      void openNewsHome("stories");
    },
  });
}

function renderBrainViewBlock(viewport: HTMLElement): void {
  renderBrainView(viewport, {
      onTogglePauseLearning: async (paused) => {
        const updated = await sidecarSetPauseLearning(paused);
        state.knowledge.pause_learning = updated;
        state.sidecar.pause_learning = updated;
        renderViewportRegion();
        renderStatusLine();
        showAppToast(
          t("settings.pause_learning", {
            state: updated ? t("common.on") : t("common.off"),
          })
        );
      },
      onDeletePassage: async (passageId) => {
        await sidecarDeletePassage(passageId);
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        if (state.brainSearchQuery) {
          state.brainSearchResults = await sidecarSearchBrain(state.brainSearchQuery);
        }
        renderViewportRegion();
      },
      onDeleteBrainEntity: async (slug) => {
        await sidecarDeleteBrainEntity(slug);
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        if (state.brainSearchQuery) {
          state.brainSearchResults = await sidecarSearchBrain(state.brainSearchQuery);
        }
        renderViewportRegion();
      },
      onSearchBrain: async (query) => {
        state.brainSearchQuery = query;
        if (!query) {
          state.brainSearchResults = null;
        } else {
          state.brainSearchResults = await sidecarSearchBrain(query);
        }
        renderViewportRegion();
      },
      onSetDomainTrust: async (domain, personalScore) => {
        await sidecarSetDomainTrust(domain, personalScore);
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderViewportRegion();
      },
      onOpenSourceUrl: (url, title) => {
        state.showBrainView = false;
        state.highlightedBrainSlug = null;
        if (url.startsWith("satzmail://message/")) {
          const mid = url.replace("satzmail://message/", "").split("/")[0].trim();
          if (mid) {
            void openEmailMessageTab(mid, (title || "").trim() || "mail");
            return;
          }
        }
        void startDirectBrowsing(url, title);
      },
      onSwitchToSettings: async () => {
        await openSettingsConversation("chat");
      },
      onMineSkillProposals: async () => {
        await sidecarMineSkillProposals();
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderViewportRegion();
      },
      onAcceptSkillProposal: async (proposalId) => {
        const res = await sidecarAcceptSkillProposal(proposalId);
        if (!res.ok && res.error) {
          state.redteamAuditSummary = res.error;
        }
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderViewportRegion();
      },
      onRejectSkillProposal: async (proposalId) => {
        await sidecarRejectSkillProposal(proposalId);
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderViewportRegion();
      },
      onRunRedteamAudit: async () => {
        state.redteamAuditSummary = "Running prompt-injection red-team suite across skills, proposals, and recipes...";
        renderViewportRegion();
        const res = await sidecarRunSkillRedteam();
        state.redteamAuditSummary = res.ok
          ? t("main.eval_redteam_pass", {
              passed: res.passed_count ?? 0,
              total: res.audited_count ?? 0,
            })
          : t("main.eval_redteam_alert", {
              failed: res.failed_count ?? 1,
              error: res.error ?? t("main.eval_check_rules"),
            });
        renderViewportRegion();
      },
      onRunEvalSuite: async (evalId, mode = "deterministic") => {
        if (state.evalRunning) return;
        state.evalRunning = true;
        state.evalStatusMsg = evalId
          ? t("main.eval_running_one", { id: evalId, mode })
          : t("main.eval_running_suite", { mode });
        renderViewportRegion();
        try {
          const res = await sidecarRunEvals(evalId ? { eval_id: evalId, mode } : { mode });
          if (evalId && res.results?.length === 1 && state.evalSuiteRun) {
            const updated = res.results[0];
            const prev = state.evalSuiteRun.results.filter((r) => r.eval_id !== updated.eval_id);
            const merged = [updated, ...prev];
            state.evalSuiteRun = {
              ok: merged.every((r) => r.passed),
              total: merged.length,
              passed: merged.filter((r) => r.passed).length,
              failed: merged.filter((r) => !r.passed).length,
              ran_at: res.ran_at,
              results: merged,
            };
          } else {
            state.evalSuiteRun = res;
          }
          state.evalStatusMsg = res.error
            ? t("main.eval_run_failed", { error: res.error })
            : t("main.eval_suite_done", { passed: res.passed, total: res.total });
          const kb = await sidecarFetchKnowledge();
          if (kb) state.knowledge = kb;
        } finally {
          state.evalRunning = false;
          renderViewportRegion();
        }
      },
      onDeleteEvalCase: async (evalId) => {
        const ok = await sidecarDeleteEval(evalId);
        if (ok) {
          state.evalStatusMsg = t("main.eval_deleted", { id: evalId });
          const kb = await sidecarFetchKnowledge();
          if (kb) state.knowledge = kb;
          renderViewportRegion();
        }
      },
      onRunSkill: async (slug) => {
        let cid = state.activeDetail?.conversation.id ?? "";
        if (!cid) {
          const conv = state.conversations.find((c) => c.status !== "archived") ?? (await apiCreateConversation(`Skill: ${slug}`, "chat"));
          await selectConversation(conv.id);
          cid = conv.id;
        }
        state.showBrainView = false;
        state.showKnowledgeView = false;
        const runRes = await sidecarRunSkill(slug, cid);
        state.conversationTasks[cid] = await sidecarListTasks(cid);
        if (runRes.ok && runRes.task?.result_md && runRes.status === "completed") {
          await apiAddMessage(cid, "assistant", runRes.task.result_md, `skill:${slug}`, JSON.stringify([]));
          await refreshCompletedConversation(cid);
        } else {
          renderAllRegions();
        }
      },
      onCreateProfile: async () => {},
      onUnlockProfile: async () => {},
      onUnlockProfileKeychain: async () => {},
      onLockProfile: async () => {},
      onDeleteProfile: async () => {},
      onUpsertPassword: async () => {},
      onSaveRawEnv: async () => {},
      onImportEnvFile: async () => {},
      onDeletePassword: async () => {},
      onRevealPassword: async () => {},
      onAutofillActiveTab: async () => {},
      onMailChanged: async () => {},
      onCloseKnowledgeView: () => {
        state.showBrainView = false;
        state.highlightedBrainSlug = null;
        renderAllRegions();
      },
    });
}

function getInlineProfileGateHandlers() {
  return {
    onUnlockProfile: async (profileId: string, pin: string) => {
      const res = await performProfileUnlockOrCreate({
        mode: "unlock",
        profileId,
        pin,
        closeModalOnSuccess: true,
      });
      showAppToast(state.profileStatusMessage, res.ok ? "info" : "danger");
    },
    onUnlockProfileKeychain: async (profileId: string) => {
      const res = await performProfileUnlockOrCreate({
        mode: "keychain",
        profileId,
        closeModalOnSuccess: true,
      });
      showAppToast(state.profileStatusMessage, res.ok ? "info" : "danger");
    },
    onCreateProfile: async (name: string, pin: string) => {
      const res = await performProfileUnlockOrCreate({
        mode: "create",
        name,
        pin,
        closeModalOnSuccess: true,
      });
      showAppToast(state.profileStatusMessage, res.ok ? "info" : "danger");
    },
    onImportProfileFile: async (bundleB64: string, pin: string, localPin?: string) => {
      const res = await performProfileUnlockOrCreate({
        mode: "import",
        bundleB64,
        pin,
        localPin,
        closeModalOnSuccess: true,
      });
      showAppToast(state.profileStatusMessage, res.ok ? "info" : "danger");
    },
  };
}

function getKnowledgeActions(): KnowledgeActions {
  return {
      onTogglePauseLearning: async (paused) => {
        const updated = await sidecarSetPauseLearning(paused);
        state.knowledge.pause_learning = updated;
        state.sidecar.pause_learning = updated;
        renderViewportRegion();
        renderStatusLine();
        showAppToast(
          t("settings.pause_learning", {
            state: updated ? t("common.on") : t("common.off"),
          })
        );
      },
      onDeletePassage: async (passageId) => {
        await sidecarDeletePassage(passageId);
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderViewportRegion();
      },
      onDeleteBrainEntity: async (slug) => {
        await sidecarDeleteBrainEntity(slug);
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderViewportRegion();
      },
      onCreateProfile: async (name, pin) => {
        const res = await performProfileUnlockOrCreate({
          mode: "create",
          name,
          pin,
          closeModalOnSuccess: true,
        });
        showAppToast(state.profileStatusMessage, res.ok ? "info" : "danger");
      },
      onUnlockProfile: async (profileId, pin) => {
        const res = await performProfileUnlockOrCreate({
          mode: "unlock",
          profileId,
          pin,
          closeModalOnSuccess: true,
        });
        showAppToast(state.profileStatusMessage, res.ok ? "info" : "danger");
      },
      onUnlockProfileKeychain: async (profileId) => {
        const res = await performProfileUnlockOrCreate({
          mode: "keychain",
          profileId,
          closeModalOnSuccess: true,
        });
        showAppToast(state.profileStatusMessage, res.ok ? "info" : "danger");
      },
      onLockProfile: async () => {
        state.revealedPasswords = {};
        state.profileImportDraft = null;
        await sidecarLockProfile();
        state.profileStatusMessage = t("main.profile_locked");
        await syncAfterProfileAuthChange(false);
        renderAllRegions();
        showAppToast(state.profileStatusMessage);
      },
      onDeleteProfile: async (profileId, pin) => {
        state.revealedPasswords = {};
        const res = await sidecarDeleteProfile(profileId, pin);
        state.profileStatusMessage = res.ok
          ? t("main.profile_deleted", { id: profileId })
          : `${t("common.error_prefix")} ${res.error ?? t("main.profile_err_delete")}`;
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderAllRegions();
        showAppToast(state.profileStatusMessage, res.ok ? "info" : "danger");
      },
      onExportProfile: async (profileId, pin) => {
        await handleExportProfile(profileId, pin);
      },
      onImportProfileFile: async (bundleB64, pin, localPin) => {
        const res = await performProfileUnlockOrCreate({
          mode: "import",
          bundleB64,
          pin,
          localPin,
          closeModalOnSuccess: true,
        });
        showAppToast(state.profileStatusMessage, res.ok ? "info" : "danger");
      },
      onUpsertPassword: async (payload) => {
        const res = await sidecarUpsertPassword(payload);
        state.profileStatusMessage = res.ok
          ? t("main.vault_saved_cred", { service: payload.service })
          : `${t("common.error_prefix")} ${res.error ?? t("main.vault_err_save_cred")}`;
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderViewportRegion();
        showAppToast(state.profileStatusMessage, res.ok ? "info" : "danger");
      },
      onSaveRawEnv: async (rawEnv) => {
        const res = await sidecarSaveRawEnv(rawEnv);
        state.profileStatusMessage = res.ok
          ? t("main.vault_merged_env")
          : `${t("common.error_prefix")} ${res.error ?? t("main.vault_err_save")}`;
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderViewportRegion();
        showAppToast(state.profileStatusMessage, res.ok ? "info" : "danger");
      },
      onImportEnvFile: async (path) => {
        const res = await sidecarImportEnvFile(path);
        state.profileStatusMessage = res.ok
          ? t("main.vault_imported_env", { path })
          : `${t("common.error_prefix")} ${res.error ?? t("main.vault_err_import")}`;
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderViewportRegion();
        showAppToast(state.profileStatusMessage, res.ok ? "info" : "danger");
      },
      onDeletePassword: async (service) => {
        await sidecarDeletePassword(service);
        state.profileStatusMessage = t("main.vault_deleted_cred", { service });
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderViewportRegion();
        showAppToast(state.profileStatusMessage);
      },
      onRevealPassword: async (service, field, pin) => {
        if (!pin) {
          state.profileStatusMessage = t("main.vault_enter_pin_first");
          renderViewportRegion();
          return;
        }
        const res = await sidecarRevealPassword(service, field, pin);
        if (res.ok && res.value !== undefined) {
          state.revealedPasswords[`${service}:${field}`] = res.value;
          state.profileStatusMessage = t("main.vault_revealed", { service, field });
        } else {
          state.profileStatusMessage = `${t("common.error_prefix")} ${res.error ?? t("main.vault_err_reveal")}`;
        }
        renderViewportRegion();
      },
      onAutofillActiveTab: async () => {
        const openTab = state.activeDetail?.tabs.find((t) => t.is_open);
        if (openTab) {
          const ok = await apiAutofillTabCredentials(openTab.id, false);
          state.profileStatusMessage = ok
            ? t("main.vault_filled_login", { domain: extractDomain(openTab.url) })
            : t("main.vault_no_match", { domain: extractDomain(openTab.url) });
          renderViewportRegion();
        }
      },
      onSaveGoogleOAuthConfig: async (payload) => {
        const st = await sidecarSaveGoogleOAuthConfig(payload);
        state.googleOAuthStatus = st;
        state.googleOAuthMessage = st.ok
          ? t("main.oauth_saved_client", { id: st.masked_client_id })
          : `${t("common.error_prefix")} ${st.error ?? t("main.oauth_err_save_cfg")}`;
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderViewportRegion();
        showAppToast(state.googleOAuthMessage, st.ok ? "info" : "danger");
      },
      onStartGoogleOAuth: async (payload) => {
        await handleStartGoogleOAuthInBrowserTab(payload);
      },
      onRefreshGoogleOAuth: async () => {
        const st = await sidecarRefreshGoogleOAuth();
        if (st) state.googleOAuthStatus = st;
        state.googleOAuthMessage = st?.ok
          ? t("main.oauth_refreshed", { email: st.email })
          : `${t("common.error_prefix")} ${st?.error ?? t("main.oauth_err_refresh")}`;
        renderViewportRegion();
        showAppToast(state.googleOAuthMessage, st?.ok ? "info" : "danger");
      },
      onDisconnectGoogleOAuth: async (clearCfg) => {
        const st = await sidecarDisconnectGoogleOAuth(clearCfg);
        state.googleOAuthStatus = st;
        state.googleOAuthMessage = t("main.oauth_disconnected");
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderViewportRegion();
        showAppToast(state.googleOAuthMessage);
      },
      onConnectGmailOAuth: async () => {
        const res = await sidecarConnectGmailOAuth();
        if (res.ok) {
          await apiEnsureMailConversation();
          state.googleOAuthMessage = t("main.oauth_connected_gmail");
          await refreshMailState();
          await refreshLists();
        } else {
          state.googleOAuthMessage = `${t("common.error_prefix")} ${res.error ?? t("main.oauth_err_link_gmail")}`;
        }
        renderAllRegions();
        showAppToast(state.googleOAuthMessage, res.ok ? "info" : "danger");
      },
      onMailChanged: async () => {
        await refreshLists();
        renderAllRegions();
        showAppToast(t("settings.saved_toast"));
      },
      onConnectGoogleDrive: (payload) => {
        void handleStartDrivesOAuthFlow("gdrive", payload);
      },
      onConnectOneDrive: (payload) => {
        void handleStartDrivesOAuthFlow("onedrive", payload);
      },
      onDisconnectDriveProvider: async (provider) => {
        await sidecarDisconnectDrive(provider, true, false);
        state.drivesFolderKey = "";
        state.drivesNavStack = [];
        await refreshDrivesState(false);
        renderAllRegions();
      },
      onSaveModelConfig: async (payload) => {
        const res = await sidecarUpdateModelConfig(payload);
        if (res.ok) {
          syncConfiguredChatModel(
            res,
            "role_chat" in payload || Boolean(payload.clear_key)
          );
          state.modelConfigStatusMsg =
            res.test_message || t("main.model_cfg_saved");
        } else {
          state.modelConfigStatusMsg = `${t("common.error_prefix")} ${res.error ?? t("main.model_cfg_err")}`;
        }
        state.sidecar = await sidecarFetchHealth();
        if (state.sidecar.model_config) {
          syncConfiguredChatModel(state.sidecar.model_config, false);
        }
        if ("role_chat" in payload && getUiLocale() !== "en") {
          void syncAppI18nState(true, false);
        }
        renderAllRegions();
        showAppToast(state.modelConfigStatusMsg, res.ok ? "info" : "danger");
      },
      onSearchHfModels: async (query) => {
        const res = await sidecarSearchHfModels(query, 10);
        if (res.ok) {
          state.hfSearchResults = res.results ?? [];
        } else {
          state.modelConfigStatusMsg = `${t("common.error_prefix")} ${res.error ?? "search failed"}`;
          showAppToast(state.modelConfigStatusMsg, "danger");
        }
        renderViewportRegion();
      },
      onInspectHfRepo: async (repoId, token) => {
        const res = await sidecarInspectHfRepo(repoId, token ?? "");
        if (res.ok) {
          state.hfInspectResult = {
            repo_id: res.repo_id || repoId,
            gated: res.gated,
            total_bytes: res.total_bytes,
            file_count: res.file_count,
          };
        } else {
          state.hfInspectResult = { repo_id: repoId, error: res.error ?? "inspect failed" };
        }
        renderViewportRegion();
      },
      onStartHfDownload: async (payload) => {
        const res = await sidecarStartHfDownload(payload);
        if (res.ok && res.download) {
          const existing = state.hfDownloads.filter(
            (d) => d.download_id !== res.download!.download_id
          );
          state.hfDownloads = [res.download, ...existing];
          state.modelConfigStatusMsg = t("main.lm_dl_started", {
            repo: res.download.repo_id,
          });
          ensureHfDownloadPolling();
          showAppToast(state.modelConfigStatusMsg);
        } else {
          state.modelConfigStatusMsg = `${t("common.error_prefix")} ${res.error ?? "download failed"}`;
          showAppToast(state.modelConfigStatusMsg, "danger");
        }
        renderViewportRegion();
      },
      onCancelHfDownload: async (downloadId) => {
        const res = await sidecarCancelHfDownload(downloadId);
        if (res.ok) {
          const dlRes = await sidecarListHfDownloads();
          if (dlRes.ok) state.hfDownloads = dlRes.downloads;
          ensureHfDownloadPolling();
        }
        renderViewportRegion();
      },
      onPointLocalModel: async (payload) => {
        const res = await sidecarPointLocalModel(payload);
        if (res.ok) {
          syncConfiguredChatModel(res, Boolean(payload.set_active));
          state.localModelPathDraft = "";
          state.modelConfigStatusMsg =
            res.message || t("main.lm_linked_ok", { path: payload.path });
          showAppToast(state.modelConfigStatusMsg);
        } else {
          state.modelConfigStatusMsg = `${t("common.error_prefix")} ${res.error ?? "failed to link model"}`;
          showAppToast(state.modelConfigStatusMsg, "danger");
        }
        const [docRoles, health] = await Promise.all([
          sidecarFetchDoctor(),
          sidecarFetchHealth(),
        ]);
        state.doctorRoles = docRoles;
        state.sidecar = health;
        renderAllRegions();
      },
      onRemoveLocalModel: async (payload) => {
        const res = await sidecarRemoveLocalModel(payload);
        if (res.ok) {
          syncConfiguredChatModel(res, true);
          state.modelConfigStatusMsg = res.message || t("main.lm_removed_ok");
          showAppToast(state.modelConfigStatusMsg);
        } else {
          state.modelConfigStatusMsg = `${t("common.error_prefix")} ${res.error ?? "failed"}`;
          showAppToast(state.modelConfigStatusMsg, "danger");
        }
        const [docRoles, health] = await Promise.all([
          sidecarFetchDoctor(),
          sidecarFetchHealth(),
        ]);
        state.doctorRoles = docRoles;
        state.sidecar = health;
        renderAllRegions();
      },
      onSaveHfToken: async (token, clear = false) => {
        const res = await sidecarSaveHfToken(token, clear);
        if (res.ok) {
          syncConfiguredChatModel(res, false);
          state.modelConfigStatusMsg = clear
            ? t("main.lm_hf_token_cleared")
            : t("main.lm_hf_token_saved");
          showAppToast(state.modelConfigStatusMsg);
        } else {
          state.modelConfigStatusMsg = `${t("common.error_prefix")} ${res.error ?? "failed"}`;
          showAppToast(state.modelConfigStatusMsg, "danger");
        }
        renderViewportRegion();
      },
      onBrowseLocalModelPath: async (mode, title) => {
        const res = await sidecarBrowseLocalModel(mode, title);
        if (!res.ok && !res.cancelled && res.error) {
          showAppToast(`${t("common.error_prefix")} ${res.error}`, "danger");
          return null;
        }
        return res.path?.trim() || null;
      },
      onResetRoutingTelemetry: async (queryType?: string) => {
        const res = await sidecarResetRoutingTelemetry(queryType);
        if (res.ok) {
          if (res.policy) state.routingPolicy = res.policy;
          state.modelConfigStatusMsg = t("main.routing_reset_ok", { count: res.deleted ?? 0 });
        } else {
          state.modelConfigStatusMsg = t("main.routing_reset_err");
        }
        renderAllRegions();
        showAppToast(state.modelConfigStatusMsg, res.ok ? "info" : "danger");
      },
      onInferProvider: async (input, categoryId) => {
        const res = await sidecarInferProvider(input, categoryId);
        if (res.ok) {
          state.providerInferredDraft[categoryId] = {
            display_name: String(res.display_name || ""),
            domains: res.domains ?? [],
            url_template: String(res.url_template || ""),
            mode: (res.mode as "search_api" | "web_account") || "web_account",
            api_driver: String(res.api_driver || ""),
            vault_service: String(res.vault_service || ""),
            auth_status: String(res.auth_status || "none"),
            masked_auth_label: String(res.masked_auth_label || ""),
            auth_ready: Boolean(res.auth_ready),
          };
          state.providerStatusMsg = t("main.prov_detected", {
            name: res.display_name || input,
            linked: res.auth_ready
              ? t("main.prov_linked_suffix", { label: res.masked_auth_label })
              : "",
          });
        } else {
          state.providerStatusMsg = `${t("common.error_prefix")} ${res.error ?? t("main.prov_err_detect")}`;
        }
        renderAllRegions();
        if (!res.ok) showAppToast(state.providerStatusMsg, "danger");
      },
      onUpsertProvider: async (payload) => {
        const res = await sidecarUpsertProvider(payload);
        if (res.ok) {
          state.providerRegistry = res;
          state.providerCredOpenId = "";
          state.providerStatusMsg = t("main.prov_saved", { name: payload.display_name });
          const kb = await sidecarFetchKnowledge();
          if (kb) state.knowledge = kb;
        } else {
          state.providerStatusMsg = `${t("common.error_prefix")} ${res.error ?? t("main.prov_err_save")}`;
        }
        renderAllRegions();
        showAppToast(state.providerStatusMsg, res.ok ? "info" : "danger");
      },
      onReorderProviders: async (categoryId, orderedIds) => {
        const res = await sidecarReorderProviders(categoryId, orderedIds);
        if (res.ok) {
          state.providerRegistry = res;
          state.providerStatusMsg = t("main.prov_reordered");
        } else {
          state.providerStatusMsg = `${t("common.error_prefix")} ${res.error ?? t("main.prov_err_reorder")}`;
        }
        renderAllRegions();
        showAppToast(state.providerStatusMsg, res.ok ? "info" : "danger");
      },
      onDeleteProvider: async (providerId, deleteCredentials) => {
        const res = await sidecarDeleteProvider(providerId, Boolean(deleteCredentials));
        if (res.ok) {
          state.providerRegistry = res;
          state.providerStatusMsg = t("main.prov_removed");
        } else {
          state.providerStatusMsg = `${t("common.error_prefix")} ${res.error ?? t("main.prov_err_remove")}`;
        }
        renderAllRegions();
        showAppToast(state.providerStatusMsg, res.ok ? "info" : "danger");
      },
      onTestProvider: async (providerId) => {
        const res = await sidecarTestProvider(providerId);
        state.providerStatusMsg = res.ok
          ? res.message || t("main.prov_verified", { url: res.preview_url || t("main.prov_ready") })
          : `${t("common.error_prefix")} ${res.error ?? t("main.prov_err_test")}`;
        renderAllRegions();
        showAppToast(state.providerStatusMsg, res.ok ? "info" : "danger");
      },
      onUpsertProviderCategory: async (payload) => {
        const res = await sidecarUpsertProviderCategory(payload);
        if (res.ok) {
          state.providerRegistry = res;
          if (res.category_id) state.providerExpandedCategoryId = res.category_id;
          state.providerStatusMsg = t("main.prov_cat_added", { label: payload.label });
        } else {
          state.providerStatusMsg = `${t("common.error_prefix")} ${res.error ?? t("main.prov_err_cat_add")}`;
        }
        renderAllRegions();
        showAppToast(state.providerStatusMsg, res.ok ? "info" : "danger");
      },
      onDeleteProviderCategory: async (categoryId) => {
        const res = await sidecarDeleteProviderCategory(categoryId);
        if (res.ok) {
          state.providerRegistry = res;
          if (state.providerExpandedCategoryId === categoryId) {
            state.providerExpandedCategoryId = "";
          }
          state.providerStatusMsg = t("main.prov_cat_deleted");
        } else {
          state.providerStatusMsg = `${t("common.error_prefix")} ${res.error ?? t("main.prov_err_cat_del")}`;
        }
        renderAllRegions();
        showAppToast(state.providerStatusMsg, res.ok ? "info" : "danger");
      },
      onResolveProviderSuggestion: async (suggestionId, action) => {
        const res = await sidecarResolveProviderSuggestion(suggestionId, action);
        if (res.ok) {
          state.providerRegistry = res;
          state.providerStatusMsg =
            action === "accept" ? t("main.prov_sugg_promoted") : t("main.prov_sugg_dismissed");
        } else {
          state.providerStatusMsg = `${t("common.error_prefix")} ${res.error ?? t("main.prov_err_sugg")}`;
        }
        renderAllRegions();
        showAppToast(state.providerStatusMsg, res.ok ? "info" : "danger");
      },
      onCloseKnowledgeView: () => {
        state.showKnowledgeView = false;
        if (state.activeDetail?.conversation.origin === "settings") {
          resetToNewConversation();
        } else {
          renderAllRegions();
        }
      },
      onChangeAppearance: () => {
        renderRailRegion();
        scheduleWebviewLayoutSync();
        renderStatusLine();
        showAppToast(t("settings.saved_toast"));
      },
      onCheckAppUpdate: async () => {
        await runAppUpdateCheck(false);
      },
      onInstallAppUpdate: async () => {
        await runAppUpdateInstall();
      },
      onOpenSettingsChat: () => {
        state.activeTabId = "chat";
        state.compareMode = false;
        renderAllRegions();
      },
      onSelectUiLanguage: async (lang: string) => {
        await handleSelectUiLanguage(lang);
      },
      onTranslateUiLanguage: async (lang: string, force = false) => {
        await handleTranslateUiLanguage(lang, force, false);
      },
      onCancelUiTranslate: async (lang?: string) => {
        await sidecarCancelI18nTranslate(lang);
        renderAllRegions();
      },
      onOverrideUiTranslation: async (
        lang: string,
        key: string,
        text?: string,
        reset = false
      ) => {
        const res = await sidecarOverrideI18n({
          lang,
          key,
          text,
          reset,
          catalog: getCatalogManifestRecord(),
        });
        if (!res.ok) {
          state.i18nStatusMsg = `${t("common.error_prefix")} ${res.error ?? "failed"}`;
          renderAllRegions();
          showAppToast(state.i18nStatusMsg, "danger");
          return;
        }
        const [bundle, st] = await Promise.all([
          sidecarGetI18nBundle(lang),
          sidecarGetI18nStatus(lang),
        ]);
        if (bundle?.ok) {
          setActiveLocaleBundle(
            lang,
            bundle.label || lang,
            bundle.dir === "rtl" ? "rtl" : "ltr",
            bundle.entries ?? {}
          );
        }
        if (st) state.i18nStatus = st;
        state.i18nStatusMsg = reset
          ? t("i18n.status_override_reset", { key })
          : t("i18n.status_override_saved", { key });
        renderAllRegions();
        showAppToast(state.i18nStatusMsg);
      },
      onExportUiPack: async (lang: string) => {
        const res = await sidecarExportI18n(lang);
        if (!res.ok || !res.pack) {
          state.i18nStatusMsg = `${t("common.error_prefix")} ${res.error ?? "failed"}`;
          renderAllRegions();
          showAppToast(state.i18nStatusMsg, "danger");
          return;
        }
        const blob = new Blob([JSON.stringify(res.pack, null, 2)], {
          type: "application/json",
        });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `satz-i18n-${lang}.json`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
        state.i18nStatusMsg = t("i18n.status_exported", { lang });
        renderViewportRegion();
        showAppToast(state.i18nStatusMsg);
      },
      onImportUiPack: async (rawJson: string) => {
        let parsed: Record<string, unknown> | null = null;
        try {
          parsed = JSON.parse(rawJson) as Record<string, unknown>;
        } catch {
          parsed = null;
        }
        if (!parsed || typeof parsed !== "object") {
          state.i18nStatusMsg = `${t("common.error_prefix")} ${t("i18n.err_invalid_pack")}`;
          renderViewportRegion();
          showAppToast(state.i18nStatusMsg, "danger");
          return;
        }
        const res = await sidecarImportI18n(parsed, true);
        if (!res.ok || !res.lang) {
          state.i18nStatusMsg = `${t("common.error_prefix")} ${res.error ?? t("i18n.err_invalid_pack")}`;
          renderViewportRegion();
          showAppToast(state.i18nStatusMsg, "danger");
          return;
        }
        setActiveLocaleBundle(
          res.lang,
          res.label || res.lang,
          res.dir === "rtl" ? "rtl" : "ltr",
          res.entries ?? {}
        );
        const st = await sidecarGetI18nStatus(res.lang);
        if (st) state.i18nStatus = st;
        state.i18nStatusMsg = t("i18n.status_imported", {
          count: res.imported ?? 0,
          label: res.label ?? res.lang,
        });
        renderAllRegions();
        showAppToast(state.i18nStatusMsg);
      },
      onUpdateContentTranslation: async (patch) => {
        const res = await sidecarUpdateTranslationConfig(patch);
        if (res.ok) {
          state.contentTranslationConfig = res;
          state.contentTranslationStatusMsg = t("settings.tr_saved_msg");
          renderAllRegions();
          showAppToast(state.contentTranslationStatusMsg);
          await Promise.all([
            refreshMailState(),
            refreshNewsState(state.newsActiveLane),
          ]);
          renderAllRegions();
        } else {
          state.contentTranslationStatusMsg = `${t("common.error_prefix")} ${res.error ?? "failed"}`;
          renderAllRegions();
          showAppToast(state.contentTranslationStatusMsg, "danger");
        }
      },
      onBackfillContentTranslation: async () => {
        const res = await sidecarBackfillTranslations();
        if (res.ok) {
          state.contentTranslationStatusMsg = t("settings.tr_backfill_msg", {
            mail: res.queued_mail ?? 0,
            news: res.translated_articles ?? 0,
          });
          showAppToast(state.contentTranslationStatusMsg);
          await Promise.all([
            refreshMailState(),
            refreshNewsState(state.newsActiveLane),
          ]);
        } else {
          state.contentTranslationStatusMsg = `${t("common.error_prefix")} ${res.error ?? "failed"}`;
          showAppToast(state.contentTranslationStatusMsg, "danger");
        }
        renderAllRegions();
      },
  };
}

function renderViewportRegion(): void {
  const viewport = document.getElementById("region-viewport");
  if (!viewport) return;

  if (resizeObserver) {
    resizeObserver.disconnect();
  }

  if (state.showBrainView) {
    clearAgentPanel();
    renderBrainViewBlock(viewport);
    scheduleWebviewLayoutSync();
    return;
  }

  if (state.showKnowledgeView) {
    clearAgentPanel();
    renderKnowledgeView(viewport, getKnowledgeActions(), null, false);
    scheduleWebviewLayoutSync();
    return;
  }

  if (!state.activeDetail) {
    clearAgentPanel();
    renderStartScreen(viewport, getStartScreenActions());
    scheduleWebviewLayoutSync();
    return;
  }

  if (state.compareMode && state.compareTabIds.length >= 2) {
    renderCompareViewport(viewport);
    scheduleWebviewLayoutSync();
    return;
  }

  if (state.activeTabId === "settings-manual") {
    clearAgentPanel();
    renderKnowledgeView(viewport, getKnowledgeActions(), null, false);
    scheduleWebviewLayoutSync();
    return;
  }

  const getNewsViewActions = () => ({
    onOpenSiteUrl: (url: string, title: string, activate = true) => {
      void handleOpenUrlAsTab(url, title, activate);
    },
    onCompareUrls: async (pairs: Array<{ url: string; title: string }>) => {
      if (!state.activeDetail) return;
      const cid = state.activeDetail.conversation.id;
      const compareIds: string[] = [];
      for (const p of pairs.slice(0, 4)) {
        const existing = state.activeDetail.tabs.find(
          (t) => t.is_open && t.url === p.url
        );
        if (existing) {
          compareIds.push(existing.id);
        } else {
          const tab = await apiOpenTab(cid, p.url, p.title);
          compareIds.push(tab.id);
        }
      }
      state.activeDetail = await apiGetConversation(cid);
      if (compareIds.length >= 2) {
        state.compareTabIds = compareIds;
        state.compareMode = true;
      }
      renderAllRegions();
    },
    onAskInNewsChat: async (prompt: string) => {
      state.activeTabId = "chat";
      state.compareMode = false;
      renderWorkspaceRegions();
      await handleSendChatMessage(prompt);
    },
    onOpenNewsSettings: (targetTab = "chat") => {
      void openNewsSettingsConversation(targetTab);
    },
    onOpenNewsHome: () => {
      void openNewsHome("stories");
    },
    onSendPerspectivesTopic: async (
      topic: string,
      clusterId?: string,
      followedStoryId?: string
    ) => {
      await handleSendPerspectivesTopic(topic, clusterId, followedStoryId);
    },
    perspChatActions: {
      ...getChatActions(),
      onSendMessage: (txt: string) => {
        void handleSendPerspectivesTopic(txt);
      },
      onRetryMessage: (txt: string) => {
        void handleSendPerspectivesTopic(txt);
      },
    },
    ...getInlineProfileGateHandlers(),
    onRefreshShell: () => {
      renderAllRegions();
    },
  });

  if (state.activeTabId === "news-settings-manual") {
    clearAgentPanel();
    renderNewsSettingsManualView(viewport, getNewsViewActions());
    scheduleWebviewLayoutSync();
    return;
  }

  if (state.activeTabId.startsWith("lane:")) {
    clearAgentPanel();
    renderMailLaneView(viewport, {
      onOpenEmailMessage: (messageId, subject) => {
        void openEmailMessageTab(messageId, subject);
      },
      onOpenComposeTab: (seed) => {
        void openComposeTab(seed);
      },
      onOpenSiteUrl: (url, title) => {
        void startDirectBrowsing(url, title);
      },
      onSelectMailAccount: (accountId) => {
        selectMailAccountFilter(accountId);
      },
      onAddMailAccount: () => {
        void openAddMailAccountSettings();
      },
      onBindEmailReader: (msgId, detailObj) => {
        bindEmailTabHeaderEvents(viewport, msgId, detailObj);
      },
      onStartGoogleOAuth: async (payload) => {
        await handleStartGoogleOAuthInBrowserTab(payload);
      },
      ...getInlineProfileGateHandlers(),
      onRefreshState: async () => {
        await refreshLists();
        renderAllRegions();
      },
    });
    scheduleWebviewLayoutSync();
    return;
  }

  if (state.activeTabId.startsWith("news-lane:")) {
    clearAgentPanel();
    renderNewsLaneView(viewport, getNewsViewActions());
    scheduleWebviewLayoutSync();
    return;
  }

  if (state.activeTabId.startsWith("drives-lane:")) {
    clearAgentPanel();
    renderDrivesView(viewport, {
      onNavigateFolder: (folderKey, pushHistory = true) => {
        if (pushHistory && folderKey !== state.drivesFolderKey) {
          pushDrivesNavHistory();
        }
        state.drivesFolderKey = folderKey;
        state.drivesSearchQuery = "";
        void refreshDrivesState(true);
      },
      onNavigateBack: () => {
        stepDrivesBack();
      },
      onNavigateUp: () => {
        stepDrivesUp();
      },
      onChangeProviderFilter: (prov) => {
        if (prov === state.drivesProviderFilter) return;
        pushDrivesNavHistory();
        state.drivesProviderFilter = prov;
        void refreshDrivesState(true);
      },
      onChangeFileTypeFilter: (ft) => {
        if (ft === state.drivesFileTypeFilter) return;
        pushDrivesNavHistory();
        state.drivesFileTypeFilter = ft;
        void refreshDrivesState(true);
      },
      onChangeOwnerFilter: (owner) => {
        if (owner === state.drivesOwnerFilter) return;
        pushDrivesNavHistory();
        state.drivesOwnerFilter = owner;
        void refreshDrivesState(true);
      },
      onResetFilters: () => {
        pushDrivesNavHistory();
        state.drivesProviderFilter = "all";
        state.drivesFileTypeFilter = "all";
        state.drivesOwnerFilter = "all";
        state.drivesSearchQuery = "";
        void refreshDrivesState(true);
      },
      onOpenDocumentInTab: (url, title, activate) => {
        void handleOpenUrlAsTab(url, title, activate);
      },
      onTriggerSync: (fullResync = false) => {
        void (async () => {
          state.drivesSyncing = true;
          renderViewportRegion();
          try {
            await sidecarSyncDrives({ full_resync: fullResync, blocking: true });
            await refreshDrivesState(false, { showLoading: true });
          } finally {
            state.drivesSyncing = false;
            renderAllRegions();
          }
        })();
      },
      onConnectGoogleDrive: (payload) => {
        void handleStartDrivesOAuthFlow("gdrive", payload);
      },
      onConnectOneDrive: (payload) => {
        void handleStartDrivesOAuthFlow("onedrive", payload);
      },
      onDisconnectProvider: (provider) => {
        void (async () => {
          state.drivesLoading = true;
          renderViewportRegion();
          try {
            await sidecarDisconnectDrive(provider, true, false);
            state.drivesFolderKey = "";
            state.drivesNavStack = [];
            await refreshDrivesState(true);
          } catch {
            state.drivesLoading = false;
            renderAllRegions();
          }
        })();
      },
      onOpenProfileUnlock: () => {
        state.profilePromptOpen = true;
        state.profilePromptDismissed = false;
        renderAllRegions();
      },
      ...getInlineProfileGateHandlers(),
    });
    scheduleWebviewLayoutSync();
    return;
  }

  if (state.activeTabId === "chat") {
    viewport.innerHTML = `
      <div class="chat-view">
        <div class="viewport-primary" id="chat-main-container"></div>
      </div>
    `;
    const chatEl = document.getElementById("chat-main-container");
    if (chatEl) {
      renderChatPanel(chatEl, getChatActions());
    }
    const sourcesEl = mountAgentPanel(
      `Sources (${state.activeDetail.sources.length})`,
      "chat-sources-rail",
      false
    );
    if (sourcesEl) {
      renderSourcesPanel(sourcesEl, {
        onToggleSourceInContext: async (sourceId, inContext) => {
          await apiSetSourceInContext(sourceId, inContext);
          if (state.activeDetail) {
            state.activeDetail = await apiGetConversation(
              state.activeDetail.conversation.id
            );
          }
          renderViewportRegion();
        },
        onJumpToSource: (src) => {
          void handleCitationClick(1, src.id);
        },
        onOpenSourceInNewTab: (url, title) => {
          void handleOpenUrlAsTab(url, title, false);
        },
        onRecaptureTab: () => {
          void handleRecaptureAllTabs();
        },
      });
    }
    scheduleWebviewLayoutSync();
    return;
  }

  renderSiteTabViewport(viewport);
  scheduleWebviewLayoutSync();
}

function renderSiteTabViewport(viewport: HTMLElement): void {
  const detail = state.activeDetail;
  if (!detail) return;
  const tab = detail.tabs.find((t) => t.id === state.activeTabId && t.is_open);
  if (!tab) {
    state.activeTabId = "chat";
    renderViewportRegion();
    return;
  }

  if (tab.kind === "compose") {
    clearAgentPanel();
    renderComposeTabView(viewport, tab, () => {
      renderViewportRegion();
    });
    return;
  }

  if (tab.kind === "mail" || tab.url.startsWith("satzmail://")) {
    const mid = tab.url.replace("satzmail://message/", "").split("/")[0].trim();
    const cachedDetail = state.mailMessageDetails[mid];
    const cachedHtml = state.mailMessageHtml[mid];
    if ((!cachedDetail || !cachedHtml) && mid) {
      void (async () => {
        const [res, htmlRes] = await Promise.all([
          cachedDetail
            ? Promise.resolve(cachedDetail)
            : sidecarGetMailMessage(mid),
          cachedHtml
            ? Promise.resolve({ ok: true, ...cachedHtml })
            : sidecarGetMailMessageHtml(mid),
        ]);
        let changed = false;
        if (res.ok && !state.mailMessageDetails[mid]) {
          state.mailMessageDetails[mid] = res;
          changed = true;
        }
        if (htmlRes.ok && htmlRes.html && !state.mailMessageHtml[mid]) {
          state.mailMessageHtml[mid] = {
            html: htmlRes.html,
            csp:
              htmlRes.csp ||
              "default-src 'none'; img-src data: cid:; style-src 'unsafe-inline'; font-src data:",
            translated_html: htmlRes.translated_html || undefined,
            translation_source_lang: htmlRes.translation_source_lang || undefined,
            translation_target_lang: htmlRes.translation_target_lang || undefined,
          };
          changed = true;
        }
        if (changed) {
          renderViewportRegion();
        }
      })();
    }

    const msgObj = (cachedDetail?.message ?? cachedDetail ?? {}) as Record<
      string,
      unknown
    >;
    const partsObj = (msgObj.parts ?? {}) as Record<string, string>;
    const plainFallback = String(
      partsObj.new || msgObj.body_text || msgObj.snippet || ""
    );
    const trObj = (msgObj.translation as Record<string, unknown> | undefined) ?? undefined;
    const showOrig = Boolean(mid && state.mailMessageShowOriginal[mid]);
    const trPlain = String(trObj?.new_text || trObj?.snippet || "").trim();
    const effectivePlain = !showOrig && trPlain ? trPlain : plainFallback;
    const effectiveHtml =
      !showOrig && cachedHtml?.translated_html
        ? cachedHtml.translated_html
        : cachedHtml?.html;
    const defaultCsp =
      "default-src 'none'; img-src data: cid:; style-src 'unsafe-inline'; font-src data:";
    const effectiveCsp = cachedHtml?.csp || defaultCsp;
    const srcdocWithCsp = buildMailIframeSrcdoc(
      effectiveHtml,
      effectivePlain,
      effectiveCsp
    );

    viewport.innerHTML = `
      <div class="mail-email-tab">
        ${renderEmailTabHeaderHtml(tab, cachedDetail)}
        <div id="webview-slot-${escapeHtml(tab.id)}" class="webview-slot mail-email-slot">
          ${
            srcdocWithCsp
              ? `<iframe
                  id="email-iframe-${escapeHtml(tab.id)}"
                  class="email-frame"
                  sandbox="allow-same-origin"
                  referrerpolicy="no-referrer"
                  srcdoc="${escapeHtml(srcdocWithCsp)}"
                ></iframe>`
              : `loading ${escapeHtml(tab.url)}...`
          }
        </div>
      </div>
    `;

    const mailRailEl = mountAgentPanel("Email context", "site-tab-agent-rail", false);
    if (mailRailEl) {
      mailRailEl.innerHTML = renderEmailAgentRailCardsHtml(cachedDetail);
    }

    bindMailIframeInteractions(viewport, {
      onOpenUrl: (url, title) => {
        void startDirectBrowsing(url, title);
      },
      onOpenMailto: (seed) => {
        void openComposeTab(seed);
      },
    });
    bindEmailTabHeaderEvents(
      document.getElementById("region-shell") ?? viewport,
      mid,
      cachedDetail
    );
    bindToolbarEvents(viewport);
    return;
  }

  const tabDomain = extractDomain(tab.url);
  const promoCacheKey = `${tab.id}:${tabDomain}`;
  if (
    tabDomain &&
    tab.url !== "about:blank" &&
    state.siteTabPromoCodes[promoCacheKey] === undefined &&
    state.sidecar.online
  ) {
    state.siteTabPromoCodes[promoCacheKey] = [];
    void (async () => {
      const codes = await sidecarGetMailCodes(tabDomain);
      state.siteTabPromoCodes[promoCacheKey] = codes;
      state.siteTabPromoCodes[tab.id] = codes;
      if (codes.length > 0 && state.activeTabId === tab.id) {
        renderTopBarRegion();
      }
    })();
  }

  viewport.innerHTML = `
    <div class="chat-view">
      <div class="viewport-primary">
        <div id="webview-slot-${escapeHtml(tab.id)}" class="webview-slot">
          ${
            tab.url === "about:blank"
              ? escapeHtml(t("main.new_tab_hint"))
              : escapeHtml(t("main.loading_url", { url: tab.url }))
          }
        </div>
      </div>
    </div>
  `;

  const railEl = mountAgentPanel("Assistant", "site-tab-agent-rail", true);
  if (railEl) {
    renderChatPanel(railEl, getChatActions());
  }

  bindToolbarEvents(viewport);
}

function renderCompareViewport(viewport: HTMLElement): void {
  const detail = state.activeDetail;
  if (!detail) return;
  const tabs = state.compareTabIds
    .slice(0, 4)
    .map((id) => detail.tabs.find((t) => t.id === id && t.is_open))
    .filter((t): t is NonNullable<typeof t> => Boolean(t));

  const count = Math.max(2, Math.min(4, tabs.length));

  viewport.innerHTML = `
    <div class="compare-view">
      <div class="compare-grid panes-${count}">
        ${tabs
          .map(
            (tab) => `
          <div class="compare-tile">
            <div class="tile-h">
              <button class="icon-btn tile-nav-btn" type="button" data-nav-btn="back" data-tab="${escapeHtml(tab.id)}" title="${escapeHtml(t("top.back"))}">${icon("back", "ico-sm")}</button>
              <button class="icon-btn tile-nav-btn" type="button" data-nav-btn="forward" data-tab="${escapeHtml(tab.id)}" title="${escapeHtml(t("top.forward"))}">${icon("fwd", "ico-sm")}</button>
              <button class="icon-btn tile-nav-btn" type="button" data-nav-btn="reload" data-tab="${escapeHtml(tab.id)}" title="${escapeHtml(t("top.reload"))}">${icon("reload", "ico-sm")}</button>
              <input
                id="address-input-${escapeHtml(tab.id)}"
                class="address-input tile-addr"
                data-address-tab="${escapeHtml(tab.id)}"
                type="text"
                spellcheck="false"
                autocorrect="off"
                autocapitalize="off"
                placeholder="${escapeHtml(t("main.tile_addr_ph"))}"
                value="${escapeHtml(tab.url === "about:blank" ? "" : tab.url)}"
              />
            </div>
            <div id="webview-slot-${escapeHtml(tab.id)}" class="webview-slot">
              ${escapeHtml(t("main.tile_loading", { target: extractDomain(tab.url) || tab.url }))}
            </div>
          </div>
        `
          )
          .join("")}
      </div>
    </div>
  `;

  const railEl = mountAgentPanel("Assistant", "compare-agent-rail", true);
  if (railEl) {
    renderChatPanel(railEl, getChatActions());
  }

  bindToolbarEvents(viewport);
}

function bindToolbarEvents(viewport: HTMLElement): void {
  viewport.querySelectorAll("[data-nav-btn]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const action = el.getAttribute("data-nav-btn") as
        | "back"
        | "forward"
        | "reload";
      const tabId = el.getAttribute("data-tab");
      if (tabId) {
        void apiControlTab(tabId, action);
      }
    });
  });

  viewport.querySelectorAll("[data-address-tab]").forEach((input) => {
    input.addEventListener("keydown", async (e) => {
      if ((e as KeyboardEvent).key === "Enter") {
        const el = input as HTMLInputElement;
        const tabId = el.getAttribute("data-address-tab");
        if (tabId && state.activeDetail) {
          const targetUrl = normalizeUrl(el.value);
          await apiNavigateTab(tabId, targetUrl);
          state.activeDetail = await apiGetConversation(
            state.activeDetail.conversation.id
          );
          await refreshLists();
          renderRailRegion();
          renderTabStripRegion();
          renderViewportRegion();
          renderStatusLine();
        }
      }
    });
  });

  viewport
    .querySelector("#toggle-agent-rail-btn")
    ?.addEventListener("click", () => {
      toggleAgentRail();
    });

  viewport.querySelectorAll("[data-autofill-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tabId = (btn as HTMLElement).getAttribute("data-autofill-tab");
      if (tabId) {
        void apiAutofillTabCredentials(tabId, false);
      }
    });
  });

  viewport.querySelectorAll("[data-codes-pill-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tabId = (btn as HTMLElement).getAttribute("data-codes-pill-tab");
      if (!tabId) return;
      const opening = state.openCodesPopoverTabId !== tabId;
      state.openCodesPopoverTabId = opening ? tabId : null;
      if (opening) {
        const tab = state.activeDetail?.tabs.find((t) => t.id === tabId);
        if (tab?.url) {
          void sidecarLogBehaviorEvent({
            event_type: "codes_check",
            domain: extractDomain(tab.url),
            url: tab.url,
          });
        }
      }
      renderViewportRegion();
    });
  });

  viewport.querySelectorAll("[data-copy-promo-code]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const code = el.getAttribute("data-copy-promo-code") || "";
      if (code && navigator.clipboard) {
        void navigator.clipboard.writeText(code);
        el.textContent = t("main.tile_copied_code", { code });
      }
    });
  });

  viewport.querySelectorAll("[data-watch-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const tabId = el.getAttribute("data-watch-tab");
      const tab = state.activeDetail?.tabs.find((t) => t.id === tabId);
      if (tab && state.activeDetail) {
        void handleWatchTarget(
          state.activeDetail.conversation.id,
          tab.url,
          tab.title || extractDomain(tab.url)
        );
        el.textContent = t("main.tile_watching");
      }
    });
  });

  viewport
    .querySelector("#compare-run-comparer-btn")
    ?.addEventListener("click", () => {
      void handleRunComparer("compare these");
    });

  viewport
    .querySelector("#compare-exit-btn")
    ?.addEventListener("click", () => {
      state.compareMode = false;
      renderWorkspaceRegions();
    });

  if (resizeObserver) {
    viewport.querySelectorAll(".webview-slot").forEach((slot) => {
      resizeObserver?.observe(slot);
    });
  }
}

function getChatActions() {
  return {
    onSendMessage: (
      text: string,
      images?: ChatImageAttachment[],
      stagedFiles?: StagedSettingsFile[]
    ) => {
      void handleSendChatMessage(text, images, { stagedFiles });
    },
    onStageConfigFiles: async (files: File[], convId: string) => {
      const MAX_BYTES = 512 * 1024;
      const existing = [...(state.pendingStagedFilesByConv[convId] ?? [])];
      const notices: string[] = [];
      for (const file of files) {
        if (file.size > MAX_BYTES) {
          notices.push(t("main.stage_size_limit", { filename: file.name }));
          continue;
        }
        try {
          const contentText = await file.text();
          const res = await sidecarStageSettingsFile({
            filename: file.name,
            mime: file.type || "text/plain",
            content_text: contentText,
          });
          if (res.ok && res.staged) {
            if (!existing.some((x) => x.staging_id === res.staged!.staging_id)) {
              existing.push(res.staged);
            }
          } else {
            notices.push(res.error || t("main.stage_err", { filename: file.name }));
          }
        } catch {
          notices.push(t("main.stage_unreadable", { filename: file.name }));
        }
      }
      if (existing.length > 0) {
        state.pendingStagedFilesByConv[convId] = existing;
      }
      state.chatImageNotice = notices.join(" ");
      renderViewportRegion();
    },
    onRetryMessage: (text: string, images?: ChatImageAttachment[], msgId?: string) => {
      const convId = state.activeDetail?.conversation.id ?? "";
      const ctx = getLastTurnTelemetryContext(convId, msgId);
      recordHarnessOutcomeSignal("retry", {
        prompt: text || ctx.prompt,
        modelId: ctx.model,
        sourceCount: ctx.sourceCount,
        charsCut: ctx.charsCut,
      });
      void handleSendChatMessage(text, images);
    },
    onChangeModel: (model: LocalModelId) => {
      const prevModel = state.selectedModel;
      const convId = state.activeDetail?.conversation.id ?? "";
      const lastPrompt = state.lastPromptByConv[convId] ?? "";
      if (model !== prevModel && (lastPrompt || (state.activeDetail?.messages.length ?? 0) > 0)) {
        const ctx = getLastTurnTelemetryContext(convId);
        recordHarnessOutcomeSignal("manual_model_override", {
          prompt: ctx.prompt || lastPrompt,
          modelId: prevModel,
          sourceCount: ctx.sourceCount,
          charsCut: ctx.charsCut,
          targetModel: model,
        });
      }
      state.userOverrodeModelInSession = true;
      state.selectedModel = model;
      renderViewportRegion();
      renderStatusLine();
    },
    onUsePlanckInstead: (text: string, msgId?: string) => {
      const convId = state.activeDetail?.conversation.id ?? "";
      const ctx = getLastTurnTelemetryContext(convId, msgId);
      const openTabs = getActiveTabSources(state.activeDetail);
      const hertzReady =
        state.sidecar.model_config?.local_models?.hertz_ready ??
        (state.sidecar.models.find((m) => m.id === "hertz (reader)")?.state !== "missing");
      const nextPlanckModel: LocalModelId =
        openTabs.length > 0 && !state.webSearchEnabled
          ? hertzReady
            ? "hertz (reader)"
            : "planck (reader)"
          : "planck3 (web)";
      recordHarnessOutcomeSignal("use_planck_instead", {
        prompt: text || ctx.prompt,
        modelId: ctx.model,
        sourceCount: ctx.sourceCount,
        charsCut: ctx.charsCut,
        targetModel: nextPlanckModel,
      });
      state.userOverrodeModelInSession = true;
      state.selectedModel = nextPlanckModel;
      renderViewportRegion();
      renderStatusLine();
      void handleSendChatMessage(text, [], { forceCurrentModel: true });
    },
    onOpenModelsSettings: () => {
      void openModelsSettings();
    },
    onFlaggedCitationClick: (_citeLabel: string, _kind: "src" | "brain" | "unsourced", msgId?: string) => {
      const convId = state.activeDetail?.conversation.id ?? "";
      const ctx = getLastTurnTelemetryContext(convId, msgId);
      recordHarnessOutcomeSignal("citation_flagged_click", {
        prompt: ctx.prompt,
        modelId: ctx.model,
        sourceCount: ctx.sourceCount,
        charsCut: ctx.charsCut,
      });
    },
    onToggleWeb: () => {
      state.webSearchEnabled = !state.webSearchEnabled;
      const convId = state.activeDetail?.conversation.id ?? "";
      const ctx = getLastTurnTelemetryContext(convId);
      if (state.webSearchEnabled && ctx.prompt) {
        recordHarnessOutcomeSignal("manual_context_override", {
          prompt: ctx.prompt,
          modelId: ctx.model,
          sourceCount: ctx.sourceCount,
          charsCut: ctx.charsCut,
          webEnabled: state.webSearchEnabled,
          mailEnabled: state.mailContextEnabled,
        });
      }
      renderViewportRegion();
    },
    onToggleMail: () => {
      if (state.activeDetail?.conversation.origin === "mail") {
        return;
      }
      state.mailContextEnabled = !state.mailContextEnabled;
      const convId = state.activeDetail?.conversation.id ?? "";
      const ctx = getLastTurnTelemetryContext(convId);
      if (state.mailContextEnabled && ctx.prompt) {
        recordHarnessOutcomeSignal("manual_context_override", {
          prompt: ctx.prompt,
          modelId: ctx.model,
          sourceCount: ctx.sourceCount,
          charsCut: ctx.charsCut,
          webEnabled: state.webSearchEnabled,
          mailEnabled: state.mailContextEnabled,
        });
      }
      renderViewportRegion();
    },
    onToggleDrives: () => {
      if (state.activeDetail?.conversation.origin === "drives") {
        return;
      }
      state.drivesContextEnabled = !state.drivesContextEnabled;
      renderViewportRegion();
    },
    onOpenDrivesFiles: () => {
      state.activeTabId = "drives-lane:files";
      state.compareMode = false;
      state.drivesLoading = true;
      renderWorkspaceRegions();
      void refreshDrivesState(true, { showLoading: true, renderImmediately: false });
    },
    onStartInlineCompose: () => {
      void createInlineComposeInChat();
    },
    onPopoutInlineCompose: (draft: MailComposeDraft) => {
      void openComposeTab({ ...draft });
    },
    onClickCitation: (citationIndex: number, sourceId: string | null) => {
      void handleCitationClick(citationIndex, sourceId);
    },
    onClickBrainCitation: (slug: string) => {
      void (async () => {
        state.highlightedBrainSlug = slug;
        state.showBrainView = true;
        state.showKnowledgeView = false;
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderAllRegions();
      })();
    },
    onOpenUrlAsTab: (url: string, title: string, activate = true) => {
      if (state.activeDetail?.conversation.origin === "mail") {
        void startDirectBrowsing(url, title);
      } else {
        void handleOpenUrlAsTab(url, title, activate);
      }
    },
    onSelectTab: (tabId: string) => {
      state.compareMode = false;
      state.activeTabId = tabId;
      renderWorkspaceRegions();
    },
    onCloseTab: (tabId: string) => {
      void handleCloseTab(tabId);
    },
    onNewTab: () => {
      void handleCreateNewTab();
    },
    onRecaptureTab: () => {
      void handleRecaptureAllTabs();
    },
    onRecaptureAllTabs: () => {
      void handleRecaptureAllTabs();
    },
    onAcceptProposal: (proposalId: string, msgId: string) => {
      void (async () => {
        const res = await sidecarAcceptBrainProposal(proposalId);
        if (res.ok) {
          const list = state.messageProposals[msgId] ?? [];
          for (const p of list) {
            if (p.proposal_id === proposalId) {
              p.status = "accepted";
            }
          }
          const kb = await sidecarFetchKnowledge();
          if (kb) state.knowledge = kb;
          renderViewportRegion();
        }
      })();
    },
    onRejectProposal: (proposalId: string, msgId: string) => {
      void (async () => {
        const ok = await sidecarRejectBrainProposal(proposalId);
        if (ok) {
          const list = state.messageProposals[msgId] ?? [];
          for (const p of list) {
            if (p.proposal_id === proposalId) {
              p.status = "rejected";
            }
          }
          renderViewportRegion();
        }
      })();
    },
    onRunComparer: () => {
      void handleRunComparer("compare these");
    },
    onWatchAnswer: (_msgId: string, content: string) => {
      if (!state.activeDetail) return;
      const convId = state.activeDetail.conversation.id;
      const openTab = state.activeDetail.tabs.find((t) => t.is_open);
      const primarySrc = state.activeDetail.sources[0];
      const target =
        openTab?.url && openTab.url !== "about:blank"
          ? openTab.url
          : primarySrc?.url || content.slice(0, 80);
      const title =
        openTab?.title ||
        primarySrc?.title ||
        state.activeDetail.conversation.title;
      void handleWatchTarget(convId, target, title, content.slice(0, 120));
    },
    onSaveAsSkill: (payload: { taskId?: string; msgId?: string }) => {
      void (async () => {
        const cid = state.activeDetail?.conversation.id ?? "default";
        if (payload.taskId) {
          await sidecarSaveAsSkill({ conversation_id: cid, task_id: payload.taskId });
        } else if (payload.msgId && state.activeDetail) {
          const msgs = state.activeDetail.messages;
          const idx = msgs.findIndex((m) => m.id === payload.msgId);
          const msg = idx >= 0 ? msgs[idx] : undefined;
          let userPrompt = "";
          for (let i = idx - 1; i >= 0; i -= 1) {
            if (msgs[i].role === "user") {
              userPrompt = msgs[i].content;
              break;
            }
          }
          const srcIds = (() => {
            try {
              return JSON.parse(msg?.source_ids_json || "[]") as string[];
            } catch {
              return [];
            }
          })();
          const usedSources = state.activeDetail.sources
            .filter((s) => srcIds.includes(s.id) || srcIds.includes(s.url))
            .map((s) => ({ id: s.id, url: s.url, domain: s.domain, title: s.title }));
          await sidecarSaveAsSkill({
            conversation_id: cid,
            name: (userPrompt || msg?.content || "Saved Skill").slice(0, 60),
            user_prompt: userPrompt,
            assistant_text: msg?.content ?? "",
            sources: usedSources,
          });
        }
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
      })();
    },
    onSaveFailureAsEval: (msgId: string) => {
      void (async () => {
        if (!state.activeDetail) return;
        const cid = state.activeDetail.conversation.id;
        const msgs = state.activeDetail.messages;
        const idx = msgs.findIndex((m) => m.id === msgId);
        const msg = idx >= 0 ? msgs[idx] : undefined;
        if (!msg) return;
        let userPrompt = "";
        let priorMsgs: Array<{ role: string; content: string }> = [];
        for (let i = idx - 1; i >= 0; i -= 1) {
          if (msgs[i].role === "user") {
            userPrompt = msgs[i].content;
            priorMsgs = msgs
              .slice(Math.max(0, i - 4), i)
              .map((m) => ({ role: m.role, content: m.content }));
            break;
          }
        }
        const srcIds = (() => {
          try {
            return JSON.parse(msg.source_ids_json || "[]") as string[];
          } catch {
            return [];
          }
        })();
        const emailCards = msg.email_cards ?? state.messageEmailCards[msg.id] ?? [];
        const attachedSources: Array<Record<string, unknown>> = state.activeDetail.sources
          .filter((s) => srcIds.length === 0 || srcIds.includes(s.id) || srcIds.includes(s.url))
          .slice(0, 10)
          .map((s) => ({
            id: s.id,
            url: s.url,
            domain: s.domain,
            title: s.title,
            is_open_tab: s.in_context,
          }));
        for (const ec of emailCards) {
          if (!attachedSources.some((x) => x.id === ec.source_id || x.id === `mail:${ec.message_id}`)) {
            attachedSources.push({
              id: `mail:${ec.message_id}`,
              url: `satzmail://message/${ec.message_id}`,
              domain: "mail",
              title: ec.subject,
              is_open_tab: true,
              text: ec.body_text || ec.snippet,
              mail_fixture: {
                from_addr: `${ec.from_name} <${ec.from_addr}>`.trim(),
                subject: ec.subject,
                plain_body: ec.body_text || ec.snippet,
              },
            });
          }
        }
        const res = await sidecarCaptureFailureEval({
          user_msg: userPrompt,
          bad_assistant_answer: msg.content,
          sources: attachedSources,
          prior_messages: priorMsgs,
          model_id: msg.model ?? state.selectedModel,
          web_enabled: state.webSearchEnabled,
          mail_enabled: state.mailContextEnabled,
          tools_used: msg.tools_used,
          citation_check: msg.citation_check as unknown as Array<Record<string, unknown>>,
          tasks: state.conversationTasks[cid] ?? [],
        });
        if (res.ok && res.eval_case) {
          state.savedEvalByMsgId[msgId] = res.eval_case.eval_id;
          state.evalStatusMsg = t("main.eval_captured", { id: res.eval_case.eval_id });
          const kb = await sidecarFetchKnowledge();
          if (kb) state.knowledge = kb;
        }
        renderViewportRegion();
      })();
    },
    onStopTask: (taskId: string, stopToken: string) => {
      void (async () => {
        const res = await sidecarStopTask(taskId, stopToken);
        if (res.ok && res.task && state.activeDetail) {
          const cid = state.activeDetail.conversation.id;
          state.conversationTasks[cid] = await sidecarListTasks(cid);
          renderViewportRegion();
        }
      })();
    },
    onConfirmTaskStep: (taskId: string, stepId: string, confirmToken: string) => {
      void handleConfirmActorTaskStep(taskId, stepId, confirmToken);
    },
    onCancelTaskStep: (taskId: string, stepId: string) => {
      void (async () => {
        const res = await sidecarCancelTaskStep(taskId, stepId);
        if (res.ok && state.activeDetail) {
          const cid = state.activeDetail.conversation.id;
          state.conversationTasks[cid] = await sidecarListTasks(cid);
          renderViewportRegion();
        }
      })();
    },
    onOpenEmailTab: (messageId: string, subject: string) => {
      void openEmailMessageTab(messageId, subject);
    },
    onPrepareUnsubscribe: (messageId: string, senderName: string) => {
      void handlePrepareUnsubscribeTask(messageId, senderName);
    },
    onArchiveSenderFromTask: (taskId: string, senderEmail: string) => {
      void (async () => {
        if (!state.activeDetail) return;
        const cid = state.activeDetail.conversation.id;
        const res = await sidecarHideMailSender(senderEmail, taskId);
        state.conversationTasks[cid] = await sidecarListTasks(cid);
        if (res.ok) {
          await refreshMailState();
        }
        renderAllRegions();
      })();
    },
    onPreviewMailAttachment: (messageId: string, partId: string) => {
      void handleToggleAttachmentPreview(messageId, partId);
    },
    onDownloadMailAttachment: (messageId: string, partId: string) => {
      void sidecarSaveMailAttachment(messageId, partId);
    },
    onNewsTrustDelta: (msgId: string, domain: string, delta: number) => {
      void (async () => {
        const curMeta =
          state.messageAnswerMeta[msgId] ??
          state.activeDetail?.messages.find((m) => m.id === msgId)
            ?.answer_meta ??
          state.newsPerspectivesDetail?.messages.find((m) => m.id === msgId)
            ?.answer_meta;
        const srcRow = curMeta?.sources?.find((s) => s.domain === domain);
        const curPersonal =
          srcRow?.trust.personal ?? srcRow?.trust.system ?? 5;
        const nextScore = Math.max(0, Math.min(10, curPersonal + delta));
        await sidecarSetDomainTrust(domain, nextScore);
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        if (curMeta) {
          const updatedMeta = await sidecarReweighNewsMeta(curMeta);
          if (updatedMeta) {
            state.messageAnswerMeta[msgId] = updatedMeta;
            const targetMsg =
              state.activeDetail?.messages.find((m) => m.id === msgId) ??
              state.newsPerspectivesDetail?.messages.find((m) => m.id === msgId);
            if (targetMsg) {
              targetMsg.answer_meta = updatedMeta;
            }
          }
        }
        renderViewportRegion();
      })();
    },
    onOpenNewsLane: (lane: string) => {
      const nl: NewsLane =
        lane === "perspectives"
          ? "perspectives"
          : lane === "tracked"
            ? "tracked"
            : "stories";
      state.newsActiveLane = nl;
      state.activeTabId = `news-lane:${nl}`;
      void refreshNewsState(nl).then(() => renderAllRegions());
      renderAllRegions();
    },
    onOpenNewsSettings: (targetTab = "chat") => {
      void openNewsSettingsConversation(targetTab);
    },
    onSettingsCardCreateProfile: async (msgId: string, cardId: string, name: string, pin: string) => {
      const res = await performProfileUnlockOrCreate({
        mode: "create",
        name,
        pin,
        closeModalOnSuccess: true,
      });
      updateSettingsCardState(msgId, cardId, (c) => ({
        ...c,
        resolved: res.ok,
        resolution_note: res.ok ? t("main.sc_created_note", { name }) : undefined,
        subtitle: res.ok ? c.subtitle : t("main.sc_err_prefix", { error: res.error }),
      }));
      renderAllRegions();
    },
    onSettingsCardUnlockProfile: async (msgId: string, cardId: string, profileId: string, pin: string, useKeychain = false) => {
      const res = await performProfileUnlockOrCreate({
        mode: useKeychain ? "keychain" : "unlock",
        profileId,
        pin,
        closeModalOnSuccess: true,
      });
      updateSettingsCardState(msgId, cardId, (c) => ({
        ...c,
        resolved: res.ok,
        resolution_note: res.ok ? t("main.sc_unlocked_note", { id: profileId }) : undefined,
        subtitle: res.ok ? c.subtitle : t("main.sc_err_prefix", { error: res.error }),
      }));
      renderAllRegions();
      showAppToast(state.profileStatusMessage, res.ok ? "info" : "danger");
    },
    onSettingsCardGoogleSaveJson: async (msgId: string, cardId: string, rawJson: string) => {
      const st = await sidecarSaveGoogleOAuthConfig({ client_secret_json: rawJson });
      state.googleOAuthStatus = st;
      state.googleOAuthMessage = st.ok
        ? t("main.oauth_saved_client", { id: st.masked_client_id })
        : `${t("common.error_prefix")} ${st.error ?? t("main.oauth_err_save_cfg")}`;
      updateSettingsCardState(msgId, cardId, (c) => ({
        ...c,
        data: {
          ...c.data,
          configured: Boolean(st.configured),
          signed_in: Boolean(st.signed_in),
          email: st.email ?? "",
          masked_client_id: st.masked_client_id ?? "",
        },
        subtitle: st.ok
          ? t("main.sc_google_saved_note", { id: st.masked_client_id })
          : t("main.sc_err_prefix", { error: st.error ?? t("main.sc_err_google_json") }),
      }));
      const kb = await sidecarFetchKnowledge();
      if (kb) state.knowledge = kb;
      renderViewportRegion();
      showAppToast(state.googleOAuthMessage, st.ok ? "info" : "danger");
    },
    onSettingsCardGoogleStartLogin: async (_msgId: string, _cardId: string, existing?: { session_id?: string; auth_url?: string }) => {
      await handleStartGoogleOAuthInBrowserTab(
        existing?.session_id && existing?.auth_url
          ? { existing_session_id: existing.session_id, existing_auth_url: existing.auth_url }
          : undefined
      );
    },
    onSettingsCardGoogleConnectGmail: async (msgId: string, cardId: string) => {
      const res = await sidecarConnectGmailOAuth();
      if (res.ok) {
        await apiEnsureMailConversation();
        await refreshMailState();
        await refreshLists();
      }
      updateSettingsCardState(msgId, cardId, (c) => ({
        ...c,
        resolved: Boolean(res.ok),
        resolution_note: res.ok ? t("main.oauth_connected_gmail") : undefined,
        subtitle: res.ok ? c.subtitle : t("main.sc_err_prefix", { error: res.error ?? t("main.sc_err_connect_gmail") }),
      }));
      renderAllRegions();
      showAppToast(
        res.ok
          ? t("main.oauth_connected_gmail")
          : `${t("common.error_prefix")} ${res.error ?? t("main.sc_err_connect_gmail")}`,
        res.ok ? "info" : "danger"
      );
    },
    onSettingsCardGoogleRefresh: async (msgId: string, cardId: string) => {
      const st = await sidecarRefreshGoogleOAuth();
      if (st) state.googleOAuthStatus = st;
      updateSettingsCardState(msgId, cardId, (c) => ({
        ...c,
        resolved: Boolean(st?.ok),
        resolution_note: st?.ok ? t("main.sc_refreshed_note", { target: st.email || "ok" }) : undefined,
        subtitle: st?.ok ? c.subtitle : t("main.sc_err_prefix", { error: st?.error ?? t("main.oauth_err_refresh") }),
      }));
      renderViewportRegion();
      showAppToast(
        st?.ok
          ? t("main.sc_refreshed_note", { target: st.email || "ok" })
          : `${t("common.error_prefix")} ${st?.error ?? t("main.oauth_err_refresh")}`,
        st?.ok ? "info" : "danger"
      );
    },
    onSettingsCardSaveApiKey: async (msgId: string, cardId: string, providerId: string, apiKey: string) => {
      const res = await sidecarUpdateModelConfig({
        provider_id: providerId,
        api_key: apiKey,
        refresh_models: true,
      });
      if (res.ok) {
        syncConfiguredChatModel(res, false);
        state.sidecar = await sidecarFetchHealth();
      }
      await loadSettingsPanelData();
      updateSettingsCardState(msgId, cardId, (c) => ({
        ...c,
        resolved: Boolean(res.ok),
        resolution_note: res.ok
          ? res.test_message || t("main.sc_apikey_saved_note", { provider: providerId })
          : undefined,
        subtitle: res.ok ? c.subtitle : t("main.sc_err_prefix", { error: res.error ?? t("main.sc_err_apikey") }),
      }));
      renderAllRegions();
      showAppToast(
        res.ok
          ? res.test_message || t("main.sc_apikey_saved_note", { provider: providerId })
          : `${t("common.error_prefix")} ${res.error ?? t("main.sc_err_apikey")}`,
        res.ok ? "info" : "danger"
      );
    },
    onSettingsCardAddMail: async (msgId: string, cardId: string, payload: Record<string, unknown>) => {
      const res = await sidecarAddMailAccount(payload);
      if (res.ok) {
        await apiEnsureMailConversation();
        await refreshMailState();
        await refreshLists();
      }
      await loadSettingsPanelData();
      updateSettingsCardState(msgId, cardId, (c) => ({
        ...c,
        resolved: Boolean(res.ok),
        resolution_note: res.ok
          ? t("main.sc_mail_connected_note", {
              target: String(payload.email || t("main.sc_mail_acct_fallback")),
            })
          : undefined,
        subtitle: res.ok ? c.subtitle : t("main.sc_err_prefix", { error: res.error ?? t("main.sc_err_mail_verify") }),
      }));
      renderAllRegions();
      showAppToast(
        res.ok
          ? t("main.sc_mail_connected_note", {
              target: String(payload.email || t("main.sc_mail_acct_fallback")),
            })
          : `${t("common.error_prefix")} ${res.error ?? t("main.sc_err_mail_verify")}`,
        res.ok ? "info" : "danger"
      );
    },
    onSettingsCardSaveProvider: async (msgId: string, cardId: string, payload: Record<string, unknown>) => {
      const res = await sidecarUpsertProvider(payload as Parameters<typeof sidecarUpsertProvider>[0]);
      if (res.ok) {
        state.providerRegistry = res;
        await loadSettingsPanelData();
      }
      updateSettingsCardState(msgId, cardId, (c) => ({
        ...c,
        resolved: Boolean(res.ok),
        resolution_note: res.ok ? t("main.sc_prov_saved_note", { name: String(payload.display_name || "") }) : undefined,
        subtitle: res.ok ? c.subtitle : t("main.sc_err_prefix", { error: res.error ?? t("main.prov_err_save") }),
      }));
      renderAllRegions();
      showAppToast(
        res.ok
          ? t("main.sc_prov_saved_note", { name: String(payload.display_name || "") })
          : `${t("common.error_prefix")} ${res.error ?? t("main.prov_err_save")}`,
        res.ok ? "info" : "danger"
      );
    },
    onSettingsCardConfirmGate: async (msgId: string, cardId: string, confirmToken: string, pin?: string) => {
      const res = await sidecarConfirmSettingsGate({
        confirm_token: confirmToken,
        action_payload: pin ? { pin } : undefined,
      });
      if (res.ok) {
        if (res.google_oauth) state.googleOAuthStatus = res.google_oauth;
        if (res.refresh_hints?.includes("profile")) {
          await syncAfterProfileAuthChange(Boolean(state.knowledge.profile?.unlocked));
        } else {
          await loadSettingsPanelData();
          await refreshMailState();
          await refreshLists();
        }
        if (res.refresh_hints?.some((h) => h.startsWith("news_"))) {
          await refreshNewsState("settings");
        }
      }
      updateSettingsCardState(msgId, cardId, (c) => ({
        ...c,
        resolved: Boolean(res.ok),
        resolution_note: res.ok ? res.message || t("main.sc_confirmed_note") : undefined,
        subtitle: res.ok ? c.subtitle : t("main.sc_err_prefix", { error: res.error ?? t("main.sc_err_confirm") }),
      }));
      renderAllRegions();
      showAppToast(
        res.ok
          ? res.message || t("main.sc_confirmed_note")
          : `${t("common.error_prefix")} ${res.error ?? t("main.sc_err_confirm")}`,
        res.ok ? "info" : "danger"
      );
    },
    onSettingsCardCancelGate: (msgId: string, cardId: string) => {
      updateSettingsCardState(msgId, cardId, (c) => ({
        ...c,
        resolved: true,
        resolution_note: t("common.cancel"),
      }));
      renderViewportRegion();
    },
    onSettingsCardTranslateLanguage: async (msgId: string, cardId: string, lang: string, force = false) => {
      await handleTranslateUiLanguage(lang, force, false, { msgId, cardId });
    },
    onSettingsCardSwitchLanguage: async (msgId: string, cardId: string, lang: string) => {
      await handleSelectUiLanguage(lang, { msgId, cardId });
    },
    onSettingsCardCancelLanguage: async (_msgId: string, _cardId: string, lang: string) => {
      await sidecarCancelI18nTranslate(lang);
      renderAllRegions();
    },
    onNewsSettingsTrackTopic: async (
      _msgId: string,
      _cardId: string,
      name: string,
      keywords: string[]
    ) => {
      const key = name.trim().toLowerCase();
      if (!key || state.newsPendingTopicKeys[key]) return;
      state.newsPendingTopicKeys[key] = true;
      renderViewportRegion();
      let r: { ok: boolean; error?: string } = { ok: false, error: "failed" };
      try {
        r = await sidecarManageNewsTopic({
          action: "add",
          name,
          keywords: keywords.join(", "),
          watch: true,
        });
        await refreshNewsState("settings");
      } catch (err) {
        r = { ok: false, error: String(err) };
      } finally {
        delete state.newsPendingTopicKeys[key];
        renderAllRegions();
      }
      showAppToast(
        r.ok ? t("news.tracked_topic_added", { name }) : `${t("common.error_prefix")} ${r.error ?? ""}`,
        r.ok ? "info" : "danger"
      );
    },
    onNewsSettingsToggleFeed: async (
      _msgId: string,
      _cardId: string,
      domain: string,
      enabled: boolean,
      feedUrl?: string,
      title?: string
    ) => {
      const normDom = domain.trim().toLowerCase().replace(/^www\./, "");
      if (!normDom || state.newsPendingFeedKeys[normDom]) return;
      state.newsPendingFeedKeys[normDom] = true;
      renderViewportRegion();
      let r: { ok: boolean; error?: string } = { ok: false, error: "failed" };
      try {
        const src = state.newsSources.find(
          (s) => s.domain.trim().toLowerCase().replace(/^www\./, "") === normDom
        );
        const fid = src?.feeds?.[0]?.feed_id;
        r = fid
          ? await sidecarManageNewsFeed({ action: "toggle", feed_id: fid, enabled })
          : await sidecarManageNewsFeed({
              domain: normDom,
              feed_url: feedUrl,
              title: title || normDom,
              enabled,
            });
        await refreshNewsState("settings");
      } catch (err) {
        r = { ok: false, error: String(err) };
      } finally {
        delete state.newsPendingFeedKeys[normDom];
        renderAllRegions();
      }
      showAppToast(
        r.ok
          ? `${title || normDom}: ${enabled ? t("chat.ns_enabled_badge") : t("chat.ns_disable_feed")}`
          : `${t("common.error_prefix")} ${r.error ?? ""}`,
        r.ok ? "info" : "danger"
      );
    },
    onNewsSettingsSetTrust: async (
      _msgId: string,
      _cardId: string,
      domain: string,
      personalScore: number | null
    ) => {
      const normDom = domain.trim().toLowerCase().replace(/^www\./, "");
      if (!normDom || state.newsPendingTrustDomains[normDom]) return;
      state.newsPendingTrustDomains[normDom] = true;
      renderViewportRegion();
      let ok = false;
      let errMsg = "";
      let effNum: number | null = null;
      try {
        const r = await sidecarSetDomainTrust(normDom, personalScore);
        ok = Boolean(r && r.ok !== false);
        effNum = typeof r?.effective === "number" ? r.effective : null;
        if (!ok && typeof r?.error === "string") errMsg = r.error;
        await refreshNewsState("settings");
      } catch (err) {
        ok = false;
        errMsg = String(err);
      } finally {
        delete state.newsPendingTrustDomains[normDom];
        renderAllRegions();
      }
      showAppToast(
        ok
          ? `${normDom}: ${personalScore === null ? t("chat.ns_reset_trust") : effNum !== null ? `${effNum.toFixed(2)}/10` : t("common.save")}`
          : `${t("common.error_prefix")} ${errMsg}`,
        ok ? "info" : "danger"
      );
    },
    onNewsSettingsAddFeedUrl: async (
      msgId: string,
      cardId: string,
      feedUrl: string,
      title?: string,
      domain?: string
    ) => {
      const pendingKey = `add:${cardId}`;
      if (state.newsPendingFeedKeys[pendingKey]) return;
      state.newsPendingFeedKeys[pendingKey] = true;
      renderViewportRegion();
      let r: { ok: boolean; error?: string } = { ok: false, error: "failed" };
      try {
        r = await sidecarManageNewsFeed({
          feed_url: feedUrl,
          title: title || undefined,
          domain: domain || undefined,
        });
        await refreshNewsState("settings");
        if (r.ok) {
          updateSettingsCardState(msgId, cardId, (c) => ({
            ...c,
            resolved: true,
            resolution_note: t("news.added_item", { item: title || feedUrl }),
          }));
        }
      } catch (err) {
        r = { ok: false, error: String(err) };
      } finally {
        delete state.newsPendingFeedKeys[pendingKey];
        renderAllRegions();
      }
      showAppToast(
        r.ok ? t("news.added_item", { item: title || feedUrl }) : `${t("common.error_prefix")} ${r.error ?? ""}`,
        r.ok ? "info" : "danger"
      );
    },
  };
}

function updateSettingsCardState(
  msgId: string,
  cardId: string,
  updater: (card: import("./types").SettingsUiCard) => import("./types").SettingsUiCard
): void {
  const list =
    state.messageUiCards[msgId] ??
    state.activeDetail?.messages.find((m) => m.id === msgId)?.ui_cards ??
    [];
  if (!list.length) return;
  const next = list.map((c) => (c.id === cardId ? updater(c) : c));
  state.messageUiCards[msgId] = next;
  const targetMsg = state.activeDetail?.messages.find((m) => m.id === msgId);
  if (targetMsg) {
    targetMsg.ui_cards = next;
  }
}

async function handleToggleAttachmentPreview(
  messageId: string,
  partId: string
): Promise<void> {
  const key = `${messageId}:${partId}`;
  if (state.previewedAttachments[key]) {
    delete state.previewedAttachments[key];
    renderViewportRegion();
    return;
  }
  const res = await sidecarGetMailAttachmentData(messageId, partId);
  if (res.ok && res.data_url) {
    state.previewedAttachments[key] = {
      filename: res.filename || "attachment",
      mime: res.mime || "application/pdf",
      data_url: res.data_url,
      size: res.size || 0,
    };
    renderViewportRegion();
  }
}

async function handleWatchTarget(
  conversationId: string,
  queryOrUrl: string,
  title: string,
  initialValue?: string
): Promise<void> {
  const res = await sidecarAddWatch({
    conversation_id: conversationId,
    query_or_url: queryOrUrl,
    cadence_seconds: 1800,
    condition: "any_change",
    title,
    initial_value: initialValue,
  });
  if (res.ok && res.watch) {
    state.watchStatusNotice = t("main.watch_active_val", {
      title: res.watch.title || queryOrUrl,
      value: res.watch.last_value || t("main.watch_monitoring"),
    });
    const wList = await sidecarListWatches();
    state.watches = wList.watches;
    state.watchBadgeConvIds = wList.watch_badges;
    renderAllRegions();
    setTimeout(() => {
      state.watchStatusNotice = "";
      renderViewportRegion();
    }, 5000);
  }
}

async function handleRunComparer(goal = "compare these"): Promise<void> {
  if (!state.activeDetail) return;
  const convId = state.activeDetail.conversation.id;
  if (isConvStreaming(convId)) return;
  const modelSnap = state.selectedModel;
  const compareModeSnap = state.compareMode;
  const compareTabsSnap = [...state.compareTabIds];
  state.agentRailOpen = true;
  startStreamingProgress(
    convId,
    modelSnap,
    "running Comparer agent across open sources...",
    "comparing",
    goal
  );
  renderViewportRegion();

  try {
    await apiCaptureOpenTabs(convId);
    const curDetail = await apiGetConversation(convId);
    if (state.activeDetail?.conversation.id === convId) {
      state.activeDetail = curDetail;
    }
    const activeTabSources = getActiveTabSources(curDetail);
    const compareSources =
      compareModeSnap && compareTabsSnap.length >= 2
        ? activeTabSources.filter((s) => compareTabsSnap.includes(s.tab.id))
        : activeTabSources;
    const chosen = (compareSources.length >= 2 ? compareSources : activeTabSources).map(
      (s) => ({
        id: s.sourceId,
        url: s.url,
        title: s.title,
        domain: s.domain,
      })
    );

    const res = await sidecarRunComparer(convId, chosen, goal);
    stopStreamingProgress(convId);

    if (res.ok && res.table_md) {
      if (res.task) {
        const existing = state.conversationTasks[convId] ?? [];
        state.conversationTasks[convId] = [
          ...existing.filter((t) => t.id !== res.task!.id),
          res.task,
        ];
      }
      const savedMsg = await apiAddMessage(
        convId,
        "assistant",
        res.table_md,
        "comparer (agent)",
        JSON.stringify(res.source_ids ?? [])
      );
      if (res.cited_sources) {
        state.messageCitedSources[savedMsg.id] = res.cited_sources;
      }
      await refreshCompletedConversation(convId, savedMsg.id);
    }
  } finally {
    stopStreamingProgress(convId);
    if (state.activeDetail?.conversation.id === convId) {
      renderAllRegions();
    } else {
      renderRailRegion();
    }
  }
}

const previewBatchEnrichAttempted = new Set<string>();

function seedUrlPreviewCacheFromDetail(
  detail: NonNullable<typeof state.activeDetail>
): void {
  for (const m of detail.messages) {
    if (m.role !== "assistant") continue;
    const am = m.answer_meta ?? state.messageAnswerMeta[m.id];
    if (am?.sources?.length) {
      cacheUrlPreviews(
        am.sources.map((s) => ({
          url: s.url,
          title: s.title,
          domain: s.domain,
          snippet: s.snippet,
          image_url: s.image_url,
          trust: s.trust?.effective,
        }))
      );
    }
    const cited = m.cited_sources ?? state.messageCitedSources[m.id] ?? [];
    if (cited.length > 0) {
      cacheUrlPreviews(cited);
    }
    const fds = m.findings ?? state.messageFindings[m.id] ?? [];
    if (fds.length > 0) {
      cacheUrlPreviews(
        fds
          .filter((f) => f.page_url && f.image_url)
          .map((f) => ({
            url: f.page_url,
            title: f.title || f.page_url,
            image_url: f.image_url,
          }))
      );
    }
  }
}

async function hydrateConversationPreviews(
  detail: NonNullable<typeof state.activeDetail>
): Promise<boolean> {
  for (const m of detail.messages) {
    if (m.answer_meta && !state.messageAnswerMeta[m.id]) {
      state.messageAnswerMeta[m.id] = m.answer_meta;
    }
  }
  seedUrlPreviewCacheFromDetail(detail);
  if (!state.sidecar.online || !detail.messages.length) return false;

  let hydratedAny = false;
  const needsHydration = detail.messages.some((m) => {
    if (m.role !== "assistant" || !m.source_ids_json) return false;
    const hasFindings = Boolean(
      (m.findings && m.findings.length > 0) ||
        (state.messageFindings[m.id] && state.messageFindings[m.id].length > 0)
    );
    return !hasFindings;
  });

  const bySource = needsHydration
    ? await sidecarFetchConversationPreviews(detail.conversation.id)
    : {};

  if (bySource && Object.keys(bySource).length > 0) {
    for (const m of detail.messages) {
      if (m.role !== "assistant" || !m.source_ids_json) continue;
      let sids: string[] = [];
      try {
        sids = JSON.parse(m.source_ids_json) as string[];
      } catch {
        sids = [];
      }
      if (!Array.isArray(sids) || sids.length === 0) continue;

      if (!m.findings && !state.messageFindings[m.id]) {
        const fList = [];
        const seenImgs = new Set<string>();
        for (const sid of sids) {
          const meta = bySource[sid];
          if (!meta?.findings) continue;
          for (const fd of meta.findings) {
            if (fd.image_url && !seenImgs.has(fd.image_url)) {
              seenImgs.add(fd.image_url);
              fList.push(fd);
              if (fList.length >= 8) break;
            }
          }
          if (fList.length >= 8) break;
        }
        if (fList.length > 0) {
          state.messageFindings[m.id] = fList;
          m.findings = fList;
          hydratedAny = true;
        }
      }

      if (!m.cited_sources && !state.messageCitedSources[m.id]) {
        const cList: Array<{ url: string; title: string }> = [];
        const seenUrls = new Set<string>();
        for (const sid of sids) {
          const meta = bySource[sid];
          const url = meta?.url || (sid.startsWith("http") ? sid : "");
          const title = meta?.title || url;
          if (url.startsWith("http") && !seenUrls.has(url)) {
            seenUrls.add(url);
            cList.push({ url, title });
          }
        }
        if (cList.length > 0) {
          state.messageCitedSources[m.id] = cList;
          m.cited_sources = cList;
          hydratedAny = true;
        }
      }
    }
    seedUrlPreviewCacheFromDetail(detail);
  }

  const enrichItems: Array<{ url: string; title?: string; domain?: string }> = [];
  const seenEnrichKeys = new Set<string>();
  const recentAssistantMsgs = detail.messages
    .filter((m) => m.role === "assistant")
    .slice(-4)
    .reverse();
  for (const m of recentAssistantMsgs) {
    const cited = m.cited_sources ?? state.messageCitedSources[m.id] ?? [];
    for (const cs of cited) {
      if (!cs.url || !/^https?:\/\//i.test(cs.url)) continue;
      const nKey = normalizePreviewUrlKey(cs.url);
      if (seenEnrichKeys.has(nKey) || previewBatchEnrichAttempted.has(nKey)) continue;
      const cached = getCachedUrlPreview(cs.url);
      if (cached?.image_url && cached?.snippet) continue;
      seenEnrichKeys.add(nKey);
      enrichItems.push({ url: cs.url, title: cs.title, domain: cs.domain });
      if (enrichItems.length >= 8) break;
    }
    if (enrichItems.length >= 8) break;
  }

  if (enrichItems.length > 0) {
    for (const it of enrichItems) {
      previewBatchEnrichAttempted.add(normalizePreviewUrlKey(it.url));
    }
    const enriched = await sidecarEnrichUrlPreviews(enrichItems, true);
    const enrichedValues = Object.values(enriched);
    if (enrichedValues.length > 0) {
      cacheUrlPreviews(enrichedValues);
      applyCachedPreviewsToChatDom(enrichedValues);
      hydratedAny = true;
    }
  }

  return hydratedAny;
}

async function selectConversation(
  conversationId: string,
  opts?: { targetTabId?: string; skipRender?: boolean }
): Promise<void> {
  closeChatLinkPreviewPopover();
  state.showKnowledgeView = false;
  state.showBrainView = false;
  state.highlightedBrainSlug = null;
  state.compareMode = false;
  state.compareTabIds = [];
  state.chatPinToBottom = true;
  if (
    state.watchBadgeConvIds.includes(conversationId) ||
    state.sidecar.watch_badges?.includes(conversationId)
  ) {
    state.watchBadgeConvIds = state.watchBadgeConvIds.filter(
      (id) => id !== conversationId
    );
    if (state.sidecar.watch_badges) {
      state.sidecar.watch_badges = state.sidecar.watch_badges.filter(
        (id) => id !== conversationId
      );
    }
    void sidecarAckWatchBadge(conversationId);
  }

  const detail = await apiGetConversation(conversationId);
  if (state.activeDetail && state.activeDetail.conversation.id === conversationId && isConvStreaming(conversationId)) {
    // Preserve active live stream state if user re-clicked current conv
  }
  state.activeDetail = detail;
  if (detail) {
    for (const m of detail.messages) {
      if (m.answer_meta && !state.messageAnswerMeta[m.id]) {
        state.messageAnswerMeta[m.id] = m.answer_meta;
      }
      if (m.ui_cards && !state.messageUiCards[m.id]) {
        state.messageUiCards[m.id] = m.ui_cards;
      }
    }
    const openTabs = detail.tabs.filter((t) => t.is_open);
    if (opts?.targetTabId) {
      state.activeTabId = opts.targetTabId;
      state.agentRailOpen = true;
    } else if (detail.conversation.origin === "mail") {
      state.mailActiveLane = "inbox";
      state.activeTabId = "chat";
      state.agentRailOpen = true;
    } else if (detail.conversation.origin === "news") {
      state.activeTabId = "chat";
      state.agentRailOpen = true;
    } else if (detail.conversation.origin === "drives") {
      state.activeTabId = "chat";
      state.agentRailOpen = true;
    } else if (
      detail.conversation.origin === "settings" ||
      detail.conversation.origin === "news_settings"
    ) {
      state.activeTabId = "chat";
      state.agentRailOpen = false;
    } else if (
      openTabs.length > 0 &&
      (detail.messages.length === 0 || detail.conversation.origin === "direct")
    ) {
      state.activeTabId = openTabs[0].id;
      state.agentRailOpen = true;
    } else {
      state.activeTabId = "chat";
      state.agentRailOpen = true;
    }
  }
  if (!opts?.skipRender) {
    renderAllRegions();
  }

  if (!detail) return;
  void (async () => {
    const bgTasks: Array<Promise<boolean>> = [];
    bgTasks.push(
      sidecarListTasks(conversationId).then((tasks) => {
        state.conversationTasks[conversationId] = tasks;
        return tasks.length > 0;
      })
    );
    bgTasks.push(hydrateConversationPreviews(detail));
    if (detail.conversation.origin === "mail") {
      bgTasks.push(
        refreshMailState().then(() => true)
      );
    } else if (detail.conversation.origin === "news") {
      bgTasks.push(
        Promise.all([
          refreshNewsState("stories"),
          refreshNewsState("topics"),
          refreshNewsState("tracked"),
        ]).then(() => true)
      );
    } else if (detail.conversation.origin === "drives") {
      bgTasks.push(
        refreshDrivesState(false, { showLoading: true }).then(() => true)
      );
    } else if (detail.conversation.origin === "settings") {
      bgTasks.push(
        loadSettingsPanelData().then(() => true)
      );
    } else if (detail.conversation.origin === "news_settings") {
      bgTasks.push(
        refreshNewsState("settings").then(() => true)
      );
    }
    const results = await Promise.all(bgTasks);
    if (
      state.activeDetail?.conversation.id === conversationId &&
      results.some(Boolean)
    ) {
      renderAllRegions();
    }
  })();
}

function handleToggleCommandBar(): void {
  if (
    !state.activeDetail &&
    !state.showBrainView &&
    !state.showKnowledgeView &&
    !state.commandBarOpen
  ) {
    const startInput = document.getElementById(
      "start-main-input"
    ) as HTMLInputElement | null;
    if (startInput) {
      startInput.focus();
      startInput.select();
      return;
    }
  }
  state.commandBarOpen = !state.commandBarOpen;
  state.commandBarSelectedIdx = 0;
  state.commandModelMenuOpen = null;
  renderCommandBarOverlay(getStartScreenActions());
  if (state.commandBarOpen) {
    void refreshDigest();
  }
}

function getProfilePromptActions() {
  return {
    onUnlockProfile: (profileId: string, pin: string) => {
      void performProfileUnlockOrCreate({
        mode: "unlock",
        profileId,
        pin,
        closeModalOnSuccess: true,
      });
    },
    onCreateProfile: (name: string, pin: string) => {
      void performProfileUnlockOrCreate({
        mode: "create",
        name,
        pin,
        closeModalOnSuccess: true,
      });
    },
    onImportProfileFile: (bundleB64: string, pin: string, localPin?: string) => {
      void performProfileUnlockOrCreate({
        mode: "import",
        bundleB64,
        pin,
        localPin,
        closeModalOnSuccess: true,
      });
    },
    onDismissProfilePrompt: () => {
      if (state.profileUnlocking) return;
      state.profileImportDraft = null;
      state.profilePromptOpen = false;
      state.profilePromptDismissed = true;
      renderProfileUnlockOverlay(getProfilePromptActions());
      scheduleWebviewLayoutSync();
    },
  };
}

function getStartScreenActions() {
  return {
    onSubmitStartInput: (raw: string) => {
      void handleStartSubmission(raw);
    },
    onExecuteCommandRoute: (route: CommandBarRoute, raw: string) => {
      void handleExecuteCommandRoute(route, raw);
    },
    onSelectConversation: (id: string) => {
      void selectConversation(id);
    },
    onOpenDigestUrl: (url: string, title: string, convId?: string) => {
      void handleOpenDigestUrl(url, title, convId);
    },
    onChangeModel: (model: LocalModelId) => {
      state.userOverrodeModelInSession = true;
      state.selectedModel = model;
      renderViewportRegion();
      renderStatusLine();
    },
    onToggleWeb: () => {
      state.webSearchEnabled = !state.webSearchEnabled;
      renderViewportRegion();
    },
    onCloseCommandBar: () => {
      state.commandBarOpen = false;
      state.commandModelMenuOpen = null;
      renderCommandBarOverlay(getStartScreenActions());
    },
    onGoHome: () => {
      resetToNewConversation();
    },
    onRefreshDigest: () => {
      void refreshLiveDigestSources();
    },
    onUnlockProfile: async (profileId: string, pin: string) => {
      await performProfileUnlockOrCreate({
        mode: "unlock",
        profileId,
        pin,
        closeModalOnSuccess: true,
      });
    },
    onCreateProfile: async (name: string, pin: string) => {
      await performProfileUnlockOrCreate({
        mode: "create",
        name,
        pin,
        closeModalOnSuccess: true,
      });
    },
    onImportProfileFile: async (bundleB64: string, pin: string, localPin?: string) => {
      await performProfileUnlockOrCreate({
        mode: "import",
        bundleB64,
        pin,
        localPin,
        closeModalOnSuccess: true,
      });
    },
  };
}

async function handleExecuteCommandRoute(
  route: CommandBarRoute,
  raw: string
): Promise<void> {
  state.commandBarOpen = false;
  state.commandModelMenuOpen = null;
  renderCommandBarOverlay(getStartScreenActions());

  if (route.kind === "run_command") {
    const cid = route.command_id;
    if (cid === "home" || cid === "new_conversation") {
      resetToNewConversation();
      return;
    }
    if (cid === "bookmark") {
      await handleBookmarkCurrentPage();
      return;
    }
    if (cid === "compare") {
      handleToggleCompareMode();
      return;
    }
    if (cid === "lock") {
      state.revealedPasswords = {};
      await sidecarLockProfile();
      state.profileStatusMessage = t("main.profile_locked");
      await syncAfterProfileAuthChange(false);
      renderAllRegions();
      return;
    }
    if (cid === "brain") {
      state.showBrainView = true;
      state.showKnowledgeView = false;
      const kb = await sidecarFetchKnowledge();
      if (kb) state.knowledge = kb;
      renderAllRegions();
      return;
    }
    if (cid === "settings") {
      await openSettingsConversation("chat");
      return;
    }
  }

  if (route.kind === "open_url" && route.url) {
    await startDirectBrowsing(route.url);
    return;
  }

  if (route.kind === "url_and_question" && route.url && route.question) {
    const title = route.question.slice(0, 60);
    const conv = await apiCreateConversation(title, "chat");
    await apiOpenTab(conv.id, route.url, extractDomain(route.url));
    state.activeDetail = await apiGetConversation(conv.id);
    state.showBrainView = false;
    state.showKnowledgeView = false;
    state.activeTabId = "chat";
    state.agentRailOpen = true;
    await refreshLists();
    renderAllRegions();
    await handleSendChatMessage(route.question);
    return;
  }

  if (route.kind === "search_brain") {
    const q = (route.query ?? raw).trim();
    state.showBrainView = true;
    state.showKnowledgeView = false;
    state.brainSearchQuery = q;
    const kb = await sidecarFetchKnowledge();
    if (kb) state.knowledge = kb;
    state.brainSearchResults = q ? await sidecarSearchBrain(q) : null;
    renderAllRegions();
    return;
  }

  if (route.kind === "search_news") {
    const q = (route.query ?? "").trim();
    const newsConv =
      state.conversations.find((c) => c.origin === "news") ??
      (await apiEnsureNewsConversation());
    await selectConversation(newsConv.id);
    if (q) {
      state.activeTabId = "chat";
      renderAllRegions();
      await handleSendChatMessage(q);
    } else {
      state.newsActiveLane = "stories";
      state.activeTabId = "news-lane:stories";
      await refreshNewsState("stories");
      renderAllRegions();
    }
    return;
  }

  if (route.kind === "search_mail") {
    const q = (route.query ?? raw).trim();
    const mailConv =
      state.conversations.find((c) => c.origin === "mail") ??
      (await apiEnsureMailConversation());
    await selectConversation(mailConv.id, {
      targetTabId: q ? "lane:inbox" : "chat",
      skipRender: true,
    });
    state.mailSearchQuery = q;
    if (q) {
      const sRes = await sidecarSearchMail(q);
      state.mailSearchRows = sRes.rows ?? [];
    } else {
      state.mailSearchRows = null;
    }
    renderAllRegions();
    return;
  }

  if (route.kind === "search_drives") {
    const q = (route.query ?? raw).trim();
    const drivesConv =
      state.conversations.find((c) => c.origin === "drives") ??
      (await apiEnsureDrivesConversation());
    await selectConversation(drivesConv.id, {
      targetTabId: "drives-lane:files",
      skipRender: true,
    });
    if (!state.drivesSearchQuery && q) {
      pushDrivesNavHistory();
    }
    state.drivesSearchQuery = q;
    state.drivesLoading = true;
    renderAllRegions();
    await refreshDrivesState(true, { showLoading: true, renderImmediately: false });
    return;
  }

  // Default: ask_model
  const question = (route.question ?? raw).trim();
  if (!question) return;
  const title = question.slice(0, 60);
  const conv = await apiCreateConversation(title, "chat");
  state.activeDetail = await apiGetConversation(conv.id);
  state.showBrainView = false;
  state.showKnowledgeView = false;
  state.activeTabId = "chat";
  state.agentRailOpen = true;
  await refreshLists();
  try {
    await apiEnsureNewsConversation();
    await apiEnsureDrivesConversation();
    await apiEnsureSettingsConversation();
    await apiEnsureNewsSettingsConversation();
    await apiEnsureNewsPerspectivesConversation();
  } catch {
    // Non-fatal if DB call fails in browser-only Vite dev preview
  }
  renderAllRegions();
  await handleSendChatMessage(question, [], { routeOverride: route });
}

async function handleStartSubmission(raw: string): Promise<void> {
  const parsed = classifyStartInput(raw);
  if (parsed.kind === "url_only" && parsed.url) {
    await startDirectBrowsing(parsed.url);
    return;
  }

  if (parsed.kind === "url_and_text" && parsed.url && parsed.question) {
    const title = parsed.question.slice(0, 60);
    const conv = await apiCreateConversation(title, "chat");
    await apiOpenTab(conv.id, parsed.url, extractDomain(parsed.url));
    state.activeDetail = await apiGetConversation(conv.id);
    state.activeTabId = "chat";
    state.agentRailOpen = true;
    await refreshLists();
    renderAllRegions();
    await handleSendChatMessage(parsed.question);
    return;
  }

  const question = parsed.question || raw;
  const title = question.slice(0, 60);
  const conv = await apiCreateConversation(title, "chat");
  state.activeDetail = await apiGetConversation(conv.id);
  state.activeTabId = "chat";
  state.agentRailOpen = true;
  await refreshLists();
  try {
    await apiEnsureNewsConversation();
    await apiEnsureDrivesConversation();
    await apiEnsureSettingsConversation();
    await apiEnsureNewsSettingsConversation();
    await apiEnsureNewsPerspectivesConversation();
  } catch {
    // Non-fatal if DB call fails in browser-only Vite dev preview
  }
  renderAllRegions();
  await handleSendChatMessage(question);
}

async function startDirectBrowsing(rawUrl: string, tabTitle?: string): Promise<void> {
  const url = normalizeUrl(rawUrl);
  const domain = extractDomain(url);
  const cleanTitle = (tabTitle || "").trim();
  const conv = await apiCreateConversation(domain, "direct");
  const tab = await apiOpenTab(conv.id, url, cleanTitle || domain);
  state.activeDetail = await apiGetConversation(conv.id);
  state.showBrainView = false;
  state.showKnowledgeView = false;
  state.compareMode = false;
  state.activeTabId = tab.id;
  state.agentRailOpen = true;
  await refreshLists();
  try {
    await apiEnsureNewsConversation();
    await apiEnsureDrivesConversation();
    await apiEnsureSettingsConversation();
    await apiEnsureNewsSettingsConversation();
    await apiEnsureNewsPerspectivesConversation();
  } catch {
    // Non-fatal if DB call fails in browser-only Vite dev preview
  }
  renderAllRegions();
}

async function handleRecaptureAllTabs(): Promise<void> {
  if (!state.activeDetail) return;
  const convId = state.activeDetail.conversation.id;
  await apiCaptureOpenTabs(convId);
  state.activeDetail = await apiGetConversation(convId);
  renderAllRegions();
}

async function handleCreateNewTab(): Promise<void> {
  if (
    !state.activeDetail ||
    state.activeDetail.conversation.origin === "settings" ||
    state.activeDetail.conversation.origin === "news_settings"
  ) {
    const conv = await apiCreateConversation("new session", "direct");
    state.activeDetail = await apiGetConversation(conv.id);
    state.showBrainView = false;
    state.showKnowledgeView = false;
  }
  if (!state.activeDetail) return;
  const tab = await apiOpenTab(
    state.activeDetail.conversation.id,
    "about:blank",
    "new tab"
  );
  state.activeDetail = await apiGetConversation(
    state.activeDetail.conversation.id
  );
  state.compareMode = false;
  state.activeTabId = tab.id;
  await refreshLists();
  try {
    await apiEnsureNewsConversation();
    await apiEnsureDrivesConversation();
    await apiEnsureSettingsConversation();
    await apiEnsureNewsSettingsConversation();
    await apiEnsureNewsPerspectivesConversation();
  } catch {
    // Non-fatal if DB call fails in browser-only Vite dev preview
  }
  renderAllRegions();
  window.setTimeout(() => {
    const input = document.getElementById(
      `address-input-${tab.id}`
    ) as HTMLInputElement | null;
    input?.focus();
    input?.select();
  }, 30);
}

async function handleCloseTab(tabId: string): Promise<void> {
  if (!state.activeDetail) return;
  await apiCloseTab(tabId);
  state.activeDetail = await apiGetConversation(
    state.activeDetail.conversation.id
  );
  state.compareTabIds = state.compareTabIds.filter((id) => id !== tabId);
  if (state.activeTabId === tabId) {
    const remaining = state.activeDetail?.tabs.filter((t) => t.is_open) ?? [];
    state.activeTabId = remaining.length > 0 ? remaining[0].id : "chat";
  }
  await refreshLists();
  try {
    await apiEnsureNewsConversation();
    await apiEnsureDrivesConversation();
    await apiEnsureSettingsConversation();
    await apiEnsureNewsSettingsConversation();
    await apiEnsureNewsPerspectivesConversation();
  } catch {
    // Non-fatal if DB call fails in browser-only Vite dev preview
  }
  renderAllRegions();
}

async function archiveActiveConversation(): Promise<void> {
  const conv = state.activeDetail?.conversation;
  if (
    !conv ||
    conv.origin === "mail" ||
    conv.origin === "news" ||
    conv.origin === "settings" ||
    conv.origin === "news_settings" ||
    conv.origin === "news_perspectives"
  ) {
    return;
  }
  await apiArchiveConversation(conv.id, true);
  await refreshLists();
  resetToNewConversation();
}

let lastCloseShortcutAt = 0;

async function handleCloseOrArchiveShortcut(forceArchive: boolean): Promise<void> {
  const nowMs = Date.now();
  if (!forceArchive && nowMs - lastCloseShortcutAt < 80) {
    return;
  }
  if (!forceArchive) {
    lastCloseShortcutAt = nowMs;
  }
  if (state.mailComposeModalOpen) {
    state.mailComposeModalOpen = false;
    renderComposeModalRegion();
    scheduleWebviewLayoutSync();
    return;
  }
  const detail = state.activeDetail;
  if (!detail) return;
  const conv = detail.conversation;
  const isArchivable =
    conv.origin !== "mail" &&
    conv.origin !== "news" &&
    conv.origin !== "drives" &&
    conv.origin !== "settings";

  if (forceArchive) {
    if (isArchivable) {
      await archiveActiveConversation();
    }
    return;
  }

  const openTabs = detail.tabs.filter((t) => t.is_open);
  const activeOpenTab =
    openTabs.find((t) => t.id === state.activeTabId) ??
    (state.compareMode
      ? openTabs.find((t) => state.compareTabIds.includes(t.id))
      : undefined);

  if (activeOpenTab) {
    if (isArchivable && openTabs.length === 1 && detail.messages.length === 0) {
      await archiveActiveConversation();
      return;
    }
    await handleCloseTab(activeOpenTab.id);
    return;
  }

  if (state.activeTabId === "chat" && isArchivable) {
    await archiveActiveConversation();
  }
}

function handleToggleCompareMode(): void {
  if (!state.activeDetail) return;
  if (state.compareMode) {
    state.compareMode = false;
    renderWorkspaceRegions();
    return;
  }
  const openTabs = state.activeDetail.tabs.filter((t) => t.is_open);
  if (state.compareTabIds.length < 2) {
    state.compareTabIds = openTabs.slice(0, 4).map((t) => t.id);
  }
  if (state.compareTabIds.length >= 2) {
    state.compareMode = true;
    void sidecarLogBehaviorEvent({
      event_type: "compare_run",
      domain: openTabs[0] ? extractDomain(openTabs[0].url) : "",
      metadata: { urls: openTabs.slice(0, 4).map((t) => t.url) },
    });
    renderWorkspaceRegions();
  }
}

async function handleBookmarkCurrentPage(): Promise<void> {
  if (!state.activeDetail) return;
  const activeTab = state.activeDetail.tabs.find(
    (t) => t.id === state.activeTabId && t.is_open
  );
  const fallbackSource = state.activeDetail.sources[0];
  const url = activeTab?.url ?? fallbackSource?.url;
  const title = activeTab?.title ?? fallbackSource?.title ?? "";
  if (!url) return;
  const dom = extractDomain(url);
  const origin = getOriginFromUrl(url);
  const knownFavicon =
    state.siteFavicons[url] ||
    (origin ? state.siteFavicons[origin] : null) ||
    null;
  const validKnownFavicon =
    knownFavicon && !state.failedFaviconSrcs[knownFavicon] ? knownFavicon : null;
  await apiAddBookmark(title || dom, url, validKnownFavicon);
  state.bookmarkTooltipNotice = t("main.bookmark_hooked", { domain: dom });
  await refreshLists();
  renderRailRegion();
  setTimeout(() => {
    if (state.bookmarkTooltipNotice.includes(dom)) {
      state.bookmarkTooltipNotice = "";
      renderRailRegion();
    }
  }, 5000);
}

async function handleOpenUrlAsTab(
  url: string,
  title: string,
  activate = true
): Promise<void> {
  if (!state.activeDetail) return;
  const convId = state.activeDetail.conversation.id;
  const tab = await apiOpenTab(
    convId,
    url,
    title || extractDomain(url)
  );
  state.activeDetail = await apiGetConversation(convId);
  if (activate) {
    state.compareMode = false;
    state.activeTabId = tab.id;
  }
  await refreshLists();
  try {
    await apiEnsureNewsConversation();
    await apiEnsureDrivesConversation();
    await apiEnsureSettingsConversation();
    await apiEnsureNewsSettingsConversation();
    await apiEnsureNewsPerspectivesConversation();
  } catch {
    // Non-fatal if DB call fails in browser-only Vite dev preview
  }
  if (activate) {
    renderAllRegions();
  } else {
    renderRailRegion();
    renderTopBarRegion();
    renderTabStripRegion();
    renderStatusLine();
  }
}

async function handleCitationClick(
  citationIndex: number,
  sourceId: string | null
): Promise<void> {
  if (!state.activeDetail) return;

  if (sourceId && sourceId.startsWith("drive:")) {
    const ikey = sourceId.slice(6).trim();
    const matchedDrive = state.drivesItems.find((d) => d.item_key === ikey);
    if (matchedDrive?.web_url) {
      await handleOpenUrlAsTab(matchedDrive.web_url, matchedDrive.name, true);
      return;
    }
  }

  if (sourceId && sourceId.startsWith("mail:")) {
    const mid = sourceId.slice(5).trim();
    if (mid) {
      await openEmailMessageTab(mid, "mail");
      return;
    }
  }

  const activeTabSources = getActiveTabSources(state.activeDetail);
  const byActiveTab =
    activeTabSources.find(
      (item) => item.sourceId === sourceId || item.tab.id === sourceId
    ) ?? activeTabSources[citationIndex - 1];

  if (byActiveTab) {
    state.compareMode = false;
    state.activeTabId = byActiveTab.tab.id;
    renderWorkspaceRegions();
    return;
  }

  const historicalSource =
    state.activeDetail.sources.find((s) => s.id === sourceId) ??
    state.activeDetail.sources[citationIndex - 1];
  if (!historicalSource) {
    const triageMatch =
      state.mailTriageSources.find((s) => s.id === sourceId) ??
      state.mailTriageSources[citationIndex - 1];
    if (triageMatch && triageMatch.id.startsWith("mail:")) {
      await openEmailMessageTab(
        triageMatch.id.slice(5).trim(),
        triageMatch.title || "mail"
      );
    }
    return;
  }

  if (
    historicalSource.id.startsWith("mail:") ||
    historicalSource.url.startsWith("satzmail://message/")
  ) {
    const mid = historicalSource.id.startsWith("mail:")
      ? historicalSource.id.slice(5).trim()
      : historicalSource.url
          .replace("satzmail://message/", "")
          .split("/")[0]
          .trim();
    if (mid) {
      await openEmailMessageTab(mid, historicalSource.title || "mail");
      return;
    }
  }

  const openTab = state.activeDetail.tabs.find(
    (t) =>
      t.is_open &&
      (t.id === historicalSource.tab_id || t.url === historicalSource.url)
  );
  if (openTab) {
    state.compareMode = false;
    state.activeTabId = openTab.id;
    renderWorkspaceRegions();
  } else {
    const newTab = await apiOpenTab(
      state.activeDetail.conversation.id,
      historicalSource.url,
      historicalSource.title
    );
    state.activeDetail = await apiGetConversation(
      state.activeDetail.conversation.id
    );
    state.compareMode = false;
    state.activeTabId = newTab.id;
    await refreshLists();
    renderAllRegions();
  }
}

function detectMailComposeIntent(
  prompt: string,
  _useMailContext: boolean
): boolean {
  const t = prompt.trim();
  if (!t) return false;
  return /^\/compose\b/i.test(t);
}

function resolveReplyMessageIdFromPrompt(
  prompt: string,
  detail: NonNullable<typeof state.activeDetail>
): string {
  const citeMatch = prompt.match(/\[(\d+)\]/);
  const sources = getActiveTabSources(detail);
  const pool =
    sources.length > 0
      ? sources.map((s) => ({ id: s.sourceId, url: s.url }))
      : state.mailTriageSources.map((s) => ({ id: s.id, url: s.url }));
  if (citeMatch) {
    const idx = Number(citeMatch[1]) - 1;
    const hit = pool[idx];
    if (hit) {
      if (hit.id.startsWith("mail:")) return hit.id.slice(5).trim();
      if (hit.url.startsWith("satzmail://message/")) {
        return hit.url.replace("satzmail://message/", "").split("/")[0].trim();
      }
    }
  }
  const mailTab = detail.tabs.find(
    (t) => t.is_open && (t.kind === "mail" || t.url.startsWith("satzmail://message/"))
  );
  if (mailTab) {
    return mailTab.url.replace("satzmail://message/", "").split("/")[0].trim();
  }
  const mailSrc = pool.find(
    (s) => s.id.startsWith("mail:") || s.url.startsWith("satzmail://message/")
  );
  if (mailSrc) {
    return mailSrc.id.startsWith("mail:")
      ? mailSrc.id.slice(5).trim()
      : mailSrc.url.replace("satzmail://message/", "").split("/")[0].trim();
  }
  const laneRow = (state.mailSearchRows ?? state.mailLaneRows)[
    state.mailSelectedRowIdx
  ];
  if (laneRow && /\bthis\s+email\b/i.test(prompt)) {
    return String(laneRow.id ?? laneRow.latest_message_id ?? "").trim();
  }
  return "";
}

async function createInlineComposeInChat(
  seed?: Partial<MailComposeDraft>,
  promptText?: string
): Promise<void> {
  if (!state.activeDetail) return;
  const convId = state.activeDetail.conversation.id;
  if (isConvStreaming(convId)) return;
  const chosenModel = getDefaultComposeModelId();
  const baseDraft: MailComposeDraft = {
    account_id: state.mailActiveAccountId ?? state.mailAccounts[0]?.id ?? "",
    to: seed?.to ?? "",
    cc: seed?.cc ?? "",
    bcc: seed?.bcc ?? "",
    subject: seed?.subject ?? "",
    body: seed?.body ?? "",
    in_reply_to: seed?.in_reply_to ?? "",
    references: seed?.references ?? "",
    reply_to_message_id: seed?.reply_to_message_id ?? "",
    ai_prompt: promptText ?? seed?.ai_prompt ?? "",
    ai_model: chosenModel,
  };

  if (promptText && state.sidecar.online && state.knowledge.profile?.unlocked) {
    startStreamingProgress(
      convId,
      chosenModel,
      `drafting inline email with ${chosenModel}...`,
      "drafting",
      promptText
    );
    if (state.activeDetail?.conversation.id === convId) {
      renderViewportRegion();
    }
    try {
      const res = await sidecarDraftMailReply({
        message_id: baseDraft.reply_to_message_id,
        to: baseDraft.to,
        cc: baseDraft.cc,
        subject: baseDraft.subject,
        instructions: promptText.replace(/^\/compose\s*/i, "").trim(),
        current_body: baseDraft.body,
        model: chosenModel,
        structured: !baseDraft.to || !baseDraft.subject,
      });
      if (res.ok) {
        if (res.to) baseDraft.to = res.to;
        if (res.cc) baseDraft.cc = res.cc;
        if (res.subject) baseDraft.subject = res.subject;
        if (res.body !== undefined) baseDraft.body = res.body;
        baseDraft.status_msg = `Draft ready (${res.model || chosenModel}). Review, edit, or press Send.`;
      } else if (res.error) {
        baseDraft.status_msg = `Draft notice: ${res.error}`;
      }
    } finally {
      stopStreamingProgress(convId);
    }
  } else if (!state.knowledge.profile?.unlocked) {
    baseDraft.status_msg = t("main.draft_unlock_first");
  }

  const savedMsg = await apiAddMessage(
    convId,
    "assistant",
    promptText
      ? t("main.draft_prepared_inline")
      : t("main.draft_created_inline"),
    chosenModel,
    JSON.stringify([]),
    null,
    null,
    null,
    JSON.stringify({ email_draft: baseDraft })
  );
  state.inlineChatDrafts[savedMsg.id] = baseDraft;
  state.activeTabId = "chat";
  await refreshCompletedConversation(convId, savedMsg.id);
}

function extractBalancedJsonSpans(
  raw: string
): Array<{ start: number; end: number; blob: string; parsed: Record<string, unknown> }> {
  const spans: Array<{ start: number; end: number; blob: string; parsed: Record<string, unknown> }> = [];
  let i = 0;
  while (i < raw.length) {
    if (raw[i] !== "{") {
      i += 1;
      continue;
    }
    let depth = 0;
    let inStr = false;
    let escaped = false;
    let j = i;
    let foundEnd = -1;
    while (j < raw.length) {
      const ch = raw[j];
      if (inStr) {
        if (escaped) {
          escaped = false;
        } else if (ch === "\\") {
          escaped = true;
        } else if (ch === '"') {
          inStr = false;
        }
      } else {
        if (ch === '"') {
          inStr = true;
        } else if (ch === "{") {
          depth += 1;
        } else if (ch === "}") {
          depth -= 1;
          if (depth === 0) {
            foundEnd = j + 1;
            break;
          }
        }
      }
      j += 1;
    }
    if (foundEnd > i) {
      const blob = raw.slice(i, foundEnd);
      try {
        const obj = JSON.parse(blob) as unknown;
        if (obj && typeof obj === "object" && !Array.isArray(obj)) {
          spans.push({ start: i, end: foundEnd, blob, parsed: obj as Record<string, unknown> });
          i = foundEnd;
          continue;
        }
      } catch {
        // Not valid JSON
      }
    }
    i += 1;
  }
  return spans;
}

function isGoogleClientSecretObj(obj: Record<string, unknown>): boolean {
  const inner =
    (obj.installed && typeof obj.installed === "object"
      ? (obj.installed as Record<string, unknown>)
      : null) ??
    (obj.web && typeof obj.web === "object"
      ? (obj.web as Record<string, unknown>)
      : obj);
  return Boolean(
    typeof inner.client_id === "string" &&
      inner.client_id.trim() &&
      typeof inner.client_secret === "string" &&
      inner.client_secret.trim()
  );
}

async function extractAndStageInlineSettingsSecrets(
  rawText: string,
  stagedFiles: StagedSettingsFile[]
): Promise<{ cleanText: string; stagedFiles: StagedSettingsFile[] }> {
  let out = rawText;
  const nextStaged = [...stagedFiles];
  const jsonSpans = extractBalancedJsonSpans(out).filter((s) =>
    isGoogleClientSecretObj(s.parsed)
  );
  if (jsonSpans.length > 0) {
    for (let idx = jsonSpans.length - 1; idx >= 0; idx -= 1) {
      const sp = jsonSpans[idx];
      let replacement = "[client_secret JSON redacted locally]";
      if (state.sidecar.online) {
        try {
          const res = await sidecarStageSettingsFile({
            filename: "client_secret_pasted.json",
            mime: "application/json",
            content_text: sp.blob,
          });
          if (res.ok && res.staged) {
            if (!nextStaged.some((x) => x.staging_id === res.staged!.staging_id)) {
              nextStaged.push(res.staged);
            }
            replacement = `[staged client_secret_pasted.json (${res.staged.summary})]`;
          }
        } catch {
          // Keep local redaction fallback even if staging request fails
        }
      }
      out = `${out.slice(0, sp.start)}${replacement}${out.slice(sp.end)}`;
    }
  }

  const envRe =
    /^(?:\s*export\s+)?(GEMINI_API_KEY|GOOGLE_API_KEY|ANTHROPIC_API_KEY|OPENAI_API_KEY|MISTRAL_API_KEY|BRAVE_API_KEY|EXA_API_KEY|TAVILY_API_KEY)\s*=\s*([^\s'"]+|'[^']*'|"[^"]*")\s*$/gm;
  const matchedEnvLines: string[] = [];
  const lineHits = [...out.matchAll(envRe)];
  if (lineHits.length > 0) {
    for (const m of lineHits) {
      matchedEnvLines.push(`${m[1]}=${String(m[2]).replace(/^['"]|['"]$/g, "")}`);
    }
    let envTag = "[env secrets redacted locally]";
    if (state.sidecar.online) {
      try {
        const res = await sidecarStageSettingsFile({
          filename: "pasted.env",
          mime: "text/plain",
          content_text: matchedEnvLines.join("\n"),
        });
        if (res.ok && res.staged) {
          if (!nextStaged.some((x) => x.staging_id === res.staged!.staging_id)) {
            nextStaged.push(res.staged);
          }
          envTag = `[staged pasted.env (${res.staged.summary})]`;
        }
      } catch {
        // Keep redaction placeholder
      }
    }
    out = out.replace(envRe, (_full, keyName) => `${keyName}=${envTag}`);
  }

  return { cleanText: out, stagedFiles: nextStaged };
}

async function handleSendChatMessage(
  text: string,
  images: ChatImageAttachment[] = [],
  sendOpts?: {
    routeOverride?: CommandBarRoute;
    forceCurrentModel?: boolean;
    stagedFiles?: StagedSettingsFile[];
  }
): Promise<void> {
  const detailSnap = state.activeDetail;
  if (!detailSnap) return;
  const convId = detailSnap.conversation.id;
  if (isConvStreaming(convId)) return;

  const hasImages = images.length > 0;
  let stagedFiles = [...(sendOpts?.stagedFiles ?? [])];
  const convOrigin = detailSnap.conversation.origin;
  const isCoreSettingsConv = convOrigin === "settings";
  const isNewsSettingsConv = convOrigin === "news_settings";
  const isSettingsConv = isCoreSettingsConv || isNewsSettingsConv;
  let rawUserText = text;
  if (isSettingsConv && rawUserText.trim()) {
    const extracted = await extractAndStageInlineSettingsSecrets(rawUserText, stagedFiles);
    rawUserText = extracted.cleanText;
    stagedFiles = extracted.stagedFiles;
  }
  const initialTabCount = getActiveTabSources(detailSnap).length;
  const routeOverride = sendOpts?.routeOverride;
  const baseModel: LocalModelId =
    routeOverride?.model ?? state.selectedModel;
  const baseWeb = Boolean(routeOverride?.auto_web ?? state.webSearchEnabled);
  const baseMail = Boolean(
    convOrigin === "mail" || routeOverride?.auto_mail || state.mailContextEnabled
  );
  const manualLocked = Boolean(
    sendOpts?.forceCurrentModel || state.userOverrodeModelInSession || isSettingsConv
  );
  const learnedDecision =
    !hasImages && !routeOverride && !isSettingsConv
      ? resolveLearnedRouteForPrompt(
          text,
          baseModel,
          baseWeb,
          baseMail,
          initialTabCount,
          manualLocked
        )
      : null;

  const routedModel: LocalModelId = learnedDecision?.model ?? baseModel;
  const chosenModel: LocalModelId =
    (hasImages || isSettingsConv) &&
    (routedModel === "planck3 (web)" ||
      routedModel === "hertz (reader)" ||
      routedModel === "planck (reader)")
      ? "gemma-4-e4b"
      : routedModel;
  const useWebSearch = isSettingsConv
    ? false
    : (learnedDecision?.web_enabled ?? baseWeb);
  const useMailContext = isSettingsConv
    ? false
    : (learnedDecision?.mail_enabled ?? baseMail);
  const useDrivesContext = isSettingsConv
    ? false
    : convOrigin === "drives" || state.drivesContextEnabled;
  const routeEscNote =
    routeOverride?.escalated && routeOverride.escalation_reason
      ? routeOverride.escalation_reason
      : learnedDecision?.escalated
        ? learnedDecision.reason
        : "";
  const activeTabSnap = state.activeTabId;

  const effectiveUserText =
    rawUserText.trim() ||
    (stagedFiles.length > 0
      ? `Analyze staged file(s): ${stagedFiles.map((s) => s.filename).join(", ")}`
      : rawUserText);

  state.lastPromptByConv[convId] = effectiveUserText;
  if (hasImages) {
    state.lastImagesByConv[convId] = images;
  } else {
    delete state.lastImagesByConv[convId];
  }
  state.chatPinToBottom = true;

  const userExtras: Record<string, unknown> = {};
  if (hasImages) userExtras.images = images;
  if (stagedFiles.length > 0) userExtras.staged_files = stagedFiles;
  const extrasJson =
    Object.keys(userExtras).length > 0 ? JSON.stringify(userExtras) : null;
  await apiAddMessage(convId, "user", effectiveUserText, null, null, null, null, null, extrasJson);
  let workDetail = await apiGetConversation(convId);
  if (state.activeDetail?.conversation.id === convId) {
    state.activeDetail = workDetail;
  }

  if (!hasImages && !isSettingsConv && workDetail && detectMailComposeIntent(effectiveUserText, useMailContext)) {
    const replyMid = resolveReplyMessageIdFromPrompt(effectiveUserText, workDetail);
    await createInlineComposeInChat(
      { reply_to_message_id: replyMid },
      effectiveUserText
    );
    return;
  }

  if (!state.sidecar.online) {
    await apiAddMessage(
      convId,
      "assistant",
      "models [offline]: start the local sidecar service to run gemma, planck3, or hertz.",
      chosenModel,
      JSON.stringify([])
    );
    await refreshCompletedConversation(convId);
    return;
  }

  const normalizedPrompt = text.trim().toLowerCase();
  if (
    !hasImages &&
    (normalizedPrompt === "compare these" || normalizedPrompt === "/compare")
  ) {
    await handleRunComparer(text.trim());
    return;
  }

  startStreamingProgress(
    convId,
    chosenModel,
    hasImages
      ? t("main.stream_prep_images", { count: images.length })
      : routeEscNote
        ? t("main.stream_auto_routed", { model: chosenModel, reason: routeEscNote })
        : t("main.stream_capturing"),
    "capturing",
    text
  );
  if (state.activeDetail?.conversation.id === convId) {
    renderViewportRegion();
  }

  try {
    // 1. Capture live rendered DOM + visible_text from open HTTP(S) WebView2 tabs when relevant
    const hasOpenWebTabs = Boolean(
      workDetail?.tabs.some((tab) => tab.is_open && /^https?:/i.test(tab.url))
    );
    const shouldCaptureTabs =
      hasOpenWebTabs &&
      (convOrigin !== "news" ||
        state.activeTabId !== "chat" ||
        /\b(tab|tabs|page|pages|this\s+article|open\s+tab|attached|above)\b/i.test(text));
    if (shouldCaptureTabs) {
      updateStreamingStatus(convId, t("main.stream_capturing"), "capturing");
      await apiCaptureOpenTabs(convId);
      workDetail = await apiGetConversation(convId);
      if (state.activeDetail?.conversation.id === convId) {
        state.activeDetail = workDetail;
      }
    }
    const activeTabSources = getActiveTabSources(workDetail);

    if (convOrigin === "news" && !hasImages) {
      updateStreamingStatus(
        convId,
        t("main.stream_news_weigh"),
        "news_weigh"
      );
      const rolesOverride =
        chosenModel &&
        chosenModel !== "hertz (reader)" &&
        chosenModel !== "planck (reader)" &&
        chosenModel !== "planck3 (web)"
          ? { news_analyzer: chosenModel }
          : undefined;
      const res = await sidecarStreamNewsChat(
        text,
        activeTabSources.map((s) => ({
          id: s.sourceId,
          url: s.url,
          title: s.title,
          domain: extractDomain(s.url),
        })),
        rolesOverride,
        {
          onDelta: (delta) => {
            appendStreamingDelta(convId, delta);
          },
          onReplaceText: (replacement) => {
            replaceStreamingText(convId, replacement);
          },
          onStatus: (status, phase) => {
            updateStreamingStatus(convId, status, phase);
          },
          onSourceStats: (stats) => {
            for (const st of stats) {
              state.sourceStats[st.id] = st;
            }
          },
        }
      );
      const streamedNewsSoFar = stopStreamingProgress(convId);
      if (res.source_stats) {
        for (const st of res.source_stats) {
          state.sourceStats[st.id] = st;
        }
      }
      const usedModel = res.model || chosenModel;
      const answerText = res.ok
        ? res.annotated_text || res.answer || streamedNewsSoFar
        : `${t("common.error_prefix")} ${res.error || t("main.err_news_query")}`;
      const extrasObj = {
        cited_sources: res.sources ?? [],
        findings: res.findings ?? [],
        answer_meta: res.answer_meta ?? undefined,
      };
      const savedMsg = await apiAddMessage(
        convId,
        "assistant",
        answerText,
        usedModel,
        JSON.stringify((res.sources ?? []).map((s) => s.url)),
        null,
        null,
        null,
        JSON.stringify(extrasObj)
      );
      if (res.sources && res.sources.length > 0) {
        state.messageCitedSources[savedMsg.id] = res.sources;
      }
      if (res.findings && res.findings.length > 0) {
        state.messageFindings[savedMsg.id] = res.findings;
      }
      if (res.answer_meta) {
        state.messageAnswerMeta[savedMsg.id] = res.answer_meta;
      }
      void refreshNewsState("topics").then(() => {
        renderRailRegion();
      });
      await refreshCompletedConversation(convId, savedMsg.id);
      return;
    }

    if (chosenModel === "planck3 (web)" && !hasImages && !isSettingsConv) {
      updateStreamingStatus(
        convId,
        t("main.stream_web_search"),
        "web_search"
      );
      const result = await sidecarRunAnswer(text, convId);
      stopStreamingProgress(convId);
      const extrasObj = {
        cited_sources: result.sources ?? [],
        findings: result.findings ?? [],
      };
      const savedMsg = await apiAddMessage(
        convId,
        "assistant",
        `${result.answer}\n\nconfidence: ${result.band}`,
        chosenModel,
        JSON.stringify(result.sources.map((s) => s.url)),
        null,
        null,
        null,
        JSON.stringify(extrasObj)
      );
      if (result.sources && result.sources.length > 0) {
        state.messageCitedSources[savedMsg.id] = result.sources;
      }
      if (result.findings && result.findings.length > 0) {
        state.messageFindings[savedMsg.id] = result.findings;
      }
      await refreshCompletedConversation(convId, savedMsg.id);
      return;
    }

    const readableSources = activeTabSources.filter((s) => s.textChars > 0);

    if (
      !hasImages &&
      !isSettingsConv &&
      (chosenModel === "hertz (reader)" || chosenModel === "planck (reader)")
    ) {
      updateStreamingStatus(
        convId,
        t("main.stream_reading_tabs", { count: readableSources.length, model: chosenModel }),
        "reading"
      );
      const res = await sidecarRunRead(
        chosenModel,
        text,
        readableSources.map((s) => ({
          id: s.sourceId,
          url: s.url,
          title: s.title,
        }))
      );
      stopStreamingProgress(convId);
      const savedMsg = await apiAddMessage(
        convId,
        "assistant",
        res.answer,
        chosenModel,
        JSON.stringify(res.source_ids)
      );
      await refreshCompletedConversation(convId, savedMsg.id);
      return;
    }

    // Default: selected local Gemma or cloud provider streaming over sources & web harness
    updateStreamingStatus(
      convId,
      hasImages
        ? t("main.stream_sending_imgs", {
            images: images.length,
            tabs: activeTabSources.length,
            model: chosenModel,
          })
        : t("main.stream_sending_tabs", {
            tabs: activeTabSources.length,
            model: chosenModel,
          }),
      "connecting"
    );

    const allMsgs = workDetail?.messages ?? [];
    const imageMsgIndices = allMsgs
      .map((m, idx) => (m.images && m.images.length > 0 ? idx : -1))
      .filter((idx) => idx >= 0);
    const keepImageDataIndices = new Set(imageMsgIndices.slice(-2));

    const historyPayload = allMsgs.map((m, idx) => {
      const stagedNote =
        m.staged_files && m.staged_files.length > 0
          ? m.staged_files
              .map(
                (sf) =>
                  `[Staged config file: filename="${sf.filename}", kind="${sf.detected_kind}", staging_id="${sf.staging_id}", summary="${sf.summary}"]`
              )
              .join("\n")
          : "";
      const textWithStaged = stagedNote
        ? `${stagedNote}\n${m.content}`.trim()
        : m.content;
      if (m.images && m.images.length > 0) {
        if (keepImageDataIndices.has(idx)) {
          return {
            role: m.role,
            content: textWithStaged,
            images: m.images,
          };
        }
        return {
          role: m.role,
          content: `[Attached ${m.images.length} image(s) earlier]\n${textWithStaged}`.trim(),
        };
      }
      return {
        role: m.role,
        content: textWithStaged,
      };
    });

    const convSummary = workDetail?.conversation.summary ?? "";
    const isMailConv = convOrigin === "mail";
    const initialSources = activeTabSources.map((s) => ({
      id: s.sourceId,
      url: s.url,
      title: s.title,
      domain: s.domain,
      is_open_tab: true,
    }));
    if (
      isMailConv &&
      initialSources.length === 0 &&
      state.mailTriageSources.length > 0 &&
      (/\[\d+\]/.test(text) ||
        !/\b(work|personal|home|private|office|corporate|business|order|orders|package|tracking|invoice|from\s+\S+)\b/i.test(
          text
        ))
    ) {
      initialSources.push(...state.mailTriageSources);
    }

    const openTabsMeta = (workDetail?.tabs ?? [])
      .filter((t) => t.is_open)
      .map((t) => ({
        tab_id: t.id,
        source_id:
          workDetail?.sources.find((s) => s.tab_id === t.id || s.url === t.url)
            ?.id ?? t.id,
        url: t.url,
        title: t.title,
        domain: extractDomain(t.url),
        is_active: t.id === activeTabSnap,
        is_sleeping: Boolean(t.suspended),
      }));

    const streamRes = await sidecarStreamChat(
      chosenModel,
      historyPayload,
      initialSources,
      useWebSearch,
      (delta) => {
        appendStreamingDelta(convId, delta);
      },
      (status, phase) => {
        updateStreamingStatus(convId, status, phase);
      },
      (errText) => {
        updateStreamingStatus(convId, `error: ${errText}`, "error");
      },
      convSummary,
      (stats) => {
        for (const st of stats) {
          state.sourceStats[st.id] = st;
        }
      },
      useMailContext,
      hasImages ? 60000 : 30000,
      convId,
      manualLocked,
      openTabsMeta,
      () => {
        if (state.activeDetail?.conversation.id === convId) {
          void apiGetConversation(convId).then((fresh) => {
            if (state.activeDetail?.conversation.id === convId) {
              state.activeDetail = fresh;
              renderTabStripRegion();
            }
          });
        }
      },
      convOrigin,
      stagedFiles,
      useDrivesContext
    );

    if (streamRes.tab_list_updated && state.activeDetail?.conversation.id === convId) {
      workDetail = await apiGetConversation(convId);
      state.activeDetail = workDetail;
      renderTabStripRegion();
    }

    void refreshRoutingPolicy();

    if (streamRes.tasks && streamRes.tasks.length > 0) {
      const existingTasks = state.conversationTasks[convId] ?? [];
      const merged = [...existingTasks];
      for (const nt of streamRes.tasks) {
        const idx = merged.findIndex((x) => x.id === nt.id);
        if (idx >= 0) merged[idx] = nt;
        else merged.push(nt);
      }
      state.conversationTasks[convId] = merged;
    }

    if (streamRes.source_stats) {
      for (const st of streamRes.source_stats) {
        state.sourceStats[st.id] = st;
      }
    }

    const streamedSoFar = stopStreamingProgress(convId);
    const finalContent = streamRes.stalled
      ? "gemma stopped responding after 30 s."
      : streamRes.annotated_text ||
        streamedSoFar ||
        (streamRes.error ? `[err] ${streamRes.error}` : "(no response)");

    const extrasPayload: Record<string, unknown> = {};
    if (streamRes.cited_sources && streamRes.cited_sources.length > 0) {
      extrasPayload.cited_sources = streamRes.cited_sources;
    }
    if (streamRes.findings && streamRes.findings.length > 0) {
      extrasPayload.findings = streamRes.findings;
    }
    if (streamRes.brain_sources && streamRes.brain_sources.length > 0) {
      extrasPayload.brain_sources = streamRes.brain_sources;
    }
    if (streamRes.email_cards && streamRes.email_cards.length > 0) {
      extrasPayload.email_cards = streamRes.email_cards;
    }
    if (streamRes.proposals && streamRes.proposals.length > 0) {
      extrasPayload.proposals = streamRes.proposals;
    }
    if (streamRes.tools_used && streamRes.tools_used.length > 0) {
      extrasPayload.tools_used = streamRes.tools_used;
    }
    if (streamRes.ui_cards && streamRes.ui_cards.length > 0) {
      extrasPayload.ui_cards = streamRes.ui_cards;
    }
    const extrasJson =
      Object.keys(extrasPayload).length > 0
        ? JSON.stringify(extrasPayload)
        : null;

    const savedMsg = await apiAddMessage(
      convId,
      "assistant",
      finalContent,
      streamRes.effective_model || chosenModel,
      JSON.stringify(streamRes.source_ids),
      typeof streamRes.citations_ok === "number" ? streamRes.citations_ok : null,
      typeof streamRes.citations_flagged === "number"
        ? streamRes.citations_flagged
        : null,
      streamRes.citation_check ? JSON.stringify(streamRes.citation_check) : null,
      extrasJson
    );
    if (streamRes.proposals && streamRes.proposals.length > 0) {
      state.messageProposals[savedMsg.id] = streamRes.proposals;
    }
    if (streamRes.findings && streamRes.findings.length > 0) {
      state.messageFindings[savedMsg.id] = streamRes.findings;
    }
    if (streamRes.brain_sources && streamRes.brain_sources.length > 0) {
      state.messageBrainSources[savedMsg.id] = streamRes.brain_sources;
    }
    if (streamRes.email_cards && streamRes.email_cards.length > 0) {
      state.messageEmailCards[savedMsg.id] = streamRes.email_cards;
    }
    if (streamRes.cited_sources && streamRes.cited_sources.length > 0) {
      state.messageCitedSources[savedMsg.id] = streamRes.cited_sources;
    }
    if (streamRes.ui_cards && streamRes.ui_cards.length > 0) {
      state.messageUiCards[savedMsg.id] = streamRes.ui_cards;
    }
    if (
      isCoreSettingsConv ||
      streamRes.tools_used?.some((t) => t.startsWith("settings_"))
    ) {
      void loadSettingsPanelData().then(() => renderRailRegion());
    }
    if (
      isNewsSettingsConv ||
      streamRes.tools_used?.some((t) => t.startsWith("news_settings_"))
    ) {
      void refreshNewsState("settings").then(() => {
        renderTabStripRegion();
        renderRailRegion();
        renderViewportRegion();
      });
    }
    await refreshCompletedConversation(convId, savedMsg.id);

    // Section 3.2 (M9): After every 6th assistant turn, write a rolling summary (max 600 chars) in background
    const refreshedNow = await apiGetConversation(convId);
    const allMessages = refreshedNow?.messages ?? [];
    const assistantTurns = allMessages.filter((m) => m.role === "assistant").length;
    if (assistantTurns > 0 && assistantTurns % 6 === 0) {
      const msgsForSummary = allMessages.map((m) => ({
        role: m.role,
        content: m.content,
      }));
      void (async () => {
        const newSum = await sidecarSummarizeConversation(
          msgsForSummary,
          convSummary
        );
        if (newSum) {
          await apiSetConversationSummary(convId, newSum);
          if (state.activeDetail?.conversation.id === convId) {
            state.activeDetail.conversation.summary = newSum;
          }
        }
      })();
    }
  } catch (err) {
    stopStreamingProgress(convId);
    await apiAddMessage(
      convId,
      "assistant",
      `[err] ${String(err)}`,
      chosenModel,
      JSON.stringify([])
    );
    await refreshCompletedConversation(convId);
  }
}

async function openEmailMessageTab(
  messageId: string,
  subject: string
): Promise<void> {
  const mailConv =
    state.activeDetail?.conversation.origin === "mail"
      ? state.activeDetail.conversation
      : state.conversations.find((c) => c.origin === "mail") ??
        (await apiEnsureMailConversation());
  if (!mailConv) return;

  const mailConvId = mailConv.id;
  if (
    state.watchBadgeConvIds.includes(mailConvId) ||
    state.sidecar.watch_badges?.includes(mailConvId)
  ) {
    state.watchBadgeConvIds = state.watchBadgeConvIds.filter(
      (id) => id !== mailConvId
    );
    if (state.sidecar.watch_badges) {
      state.sidecar.watch_badges = state.sidecar.watch_badges.filter(
        (id) => id !== mailConvId
      );
    }
    void sidecarAckWatchBadge(mailConvId);
  }

  void sidecarOpenMailMessage(messageId);
  const [baseDetail, msgDetail, msgHtml] = await Promise.all([
    state.activeDetail?.conversation.id === mailConvId
      ? Promise.resolve(state.activeDetail)
      : apiGetConversation(mailConvId),
    sidecarGetMailMessage(messageId),
    sidecarGetMailMessageHtml(messageId),
  ]);
  if (!baseDetail) return;

  for (const m of baseDetail.messages) {
    if (m.answer_meta && !state.messageAnswerMeta[m.id]) {
      state.messageAnswerMeta[m.id] = m.answer_meta;
    }
    if (m.ui_cards && !state.messageUiCards[m.id]) {
      state.messageUiCards[m.id] = m.ui_cards;
    }
  }

  if (msgDetail.ok) {
    state.mailMessageDetails[messageId] = msgDetail;
  }
  if (msgHtml.ok && msgHtml.html) {
    state.mailMessageHtml[messageId] = {
      html: msgHtml.html,
      csp:
        msgHtml.csp ||
        "default-src 'none'; img-src data: cid:; style-src 'unsafe-inline'; font-src data:",
      translated_html: msgHtml.translated_html || undefined,
      translation_source_lang: msgHtml.translation_source_lang || undefined,
      translation_target_lang: msgHtml.translation_target_lang || undefined,
    };
  }

  const fetchedMsg = msgDetail.ok
    ? ((msgDetail.message ?? msgDetail) as Record<string, unknown>)
    : null;
  const fetchedSubject = fetchedMsg?.subject
    ? String(fetchedMsg.subject).trim()
    : "";
  const resolvedSubject =
    fetchedSubject || (subject && subject !== "mail" ? subject : "mail");
  const targetUrl = `satzmail://message/${messageId}`;
  const existingTab = baseDetail.tabs.find(
    (t) => t.is_open && t.url === targetUrl
  );
  let nextDetail = baseDetail;
  const tab =
    existingTab ??
    (await apiOpenTab(mailConvId, targetUrl, resolvedSubject, "mail"));
  if (!existingTab) {
    nextDetail = (await apiGetConversation(mailConvId)) ?? baseDetail;
  }

  state.showKnowledgeView = false;
  state.showBrainView = false;
  state.highlightedBrainSlug = null;
  state.compareMode = false;
  state.compareTabIds = [];
  state.chatPinToBottom = true;
  state.mailActiveLane = "inbox";
  state.activeDetail = nextDetail;
  state.activeTabId = tab.id;
  state.agentRailOpen = true;
  renderAllRegions();

  void Promise.all([
    refreshMailState(),
    refreshLists(),
    sidecarListTasks(mailConvId).then((tasks) => {
      state.conversationTasks[mailConvId] = tasks;
    }),
    hydrateConversationPreviews(nextDetail),
  ]).then(() => {
    if (state.activeDetail?.conversation.id === mailConvId) {
      renderTabStripRegion();
      renderRailRegion();
    }
  });
}

async function openComposeTab(seed?: {
  to?: string;
  cc?: string;
  bcc?: string;
  subject?: string;
  body?: string;
  in_reply_to?: string;
  references?: string;
  reply_to_message_id?: string;
  account_id?: string;
  ai_prompt?: string;
  ai_model?: LocalModelId;
}): Promise<void> {
  state.mailComposeModalDraft = {
    account_id:
      seed?.account_id ??
      state.mailActiveAccountId ??
      state.mailAccounts[0]?.id ??
      "",
    to: seed?.to ?? "",
    cc: seed?.cc ?? "",
    bcc: seed?.bcc ?? "",
    subject: seed?.subject ?? "",
    body: seed?.body ?? "",
    in_reply_to: seed?.in_reply_to ?? "",
    references: seed?.references ?? "",
    reply_to_message_id: seed?.reply_to_message_id ?? "",
    ai_prompt: seed?.ai_prompt ?? "",
    ai_model: seed?.ai_model ?? getDefaultComposeModelId(),
  };
  state.mailComposeModalOpen = true;
  renderAllRegions();
  scheduleWebviewLayoutSync();
}

function bindEmailTabHeaderEvents(
  viewport: HTMLElement,
  messageId: string,
  detailObj: Record<string, unknown> | undefined
): void {
  const msg = (detailObj?.message ?? detailObj ?? {}) as Record<string, unknown>;
  const buildReplySeed = (replyAll: boolean) => {
    const origSubj = String(msg.subject || "");
    const reSubj = origSubj.toLowerCase().startsWith("re:")
      ? origSubj
      : `Re: ${origSubj}`;
    const fromAddr = String(msg.from_addr || "");
    const fromName = String(msg.from_name || fromAddr);
    const parts = (msg.parts ?? {}) as Record<string, string>;
    const origBody = parts.new || String(msg.body_text || "");
    const quoted = origBody
      .split("\n")
      .map((ln) => `> ${ln}`)
      .join("\n");
    const dt = new Date(Number(msg.date || 0) * 1000).toISOString().slice(0, 16);
    const ccArr = replyAll
      ? ((msg.cc ?? []) as Array<Record<string, string>>)
          .map((c) => c.email)
          .filter(Boolean)
      : [];
    return {
      to: fromAddr,
      cc: ccArr.join(", "),
      subject: reSubj,
      body: `\n\nOn ${dt}, ${fromName} wrote:\n${quoted}`,
      in_reply_to: String(msg.message_id || ""),
      references: `${String(msg.references || "")} ${String(msg.message_id || "")}`.trim(),
      reply_to_message_id: messageId,
    };
  };

  viewport
    .querySelector(`[data-email-reply="${messageId}"]`)
    ?.addEventListener("click", () => {
      void openComposeTab(buildReplySeed(false));
    });

  viewport
    .querySelector(`[data-email-reply-all="${messageId}"]`)
    ?.addEventListener("click", () => {
      void openComposeTab(buildReplySeed(true));
    });

  viewport
    .querySelector(`[data-email-forward="${messageId}"]`)
    ?.addEventListener("click", () => {
      const origSubj = String(msg.subject || "");
      const fwdSubj = origSubj.toLowerCase().startsWith("fwd:")
        ? origSubj
        : `Fwd: ${origSubj}`;
      const parts = (msg.parts ?? {}) as Record<string, string>;
      const origBody = parts.new || String(msg.body_text || "");
      void openComposeTab({
        to: "",
        subject: fwdSubj,
        body: `\n\n-----Forwarded message-----\n${origBody}`,
      });
    });

  viewport
    .querySelector(`[data-email-hide="${messageId}"]`)
    ?.addEventListener("click", async () => {
      await sidecarHideMailMessage(messageId);
      await refreshMailState();
      renderAllRegions();
    });

  viewport
    .querySelector(`[data-email-unsubscribe="${messageId}"]`)
    ?.addEventListener("click", () => {
      const sender =
        viewport
          .querySelector(`[data-email-unsubscribe="${messageId}"]`)
          ?.getAttribute("data-email-sender") || "";
      void handlePrepareUnsubscribeTask(messageId, sender);
    });

  viewport.querySelectorAll("[data-email-move]").forEach((el) => {
    el.addEventListener("change", async () => {
      const sel = el as HTMLSelectElement;
      const targetId = sel.getAttribute("data-email-move") || messageId;
      const targetLabel = sel.value as
        | "email"
        | "ping"
        | "information"
        | "promotion"
        | "";
      if (!targetLabel) return;
      await sidecarLabelMailMessage(targetId, targetLabel);
      const updated = await sidecarGetMailMessage(targetId);
      if (updated.ok) {
        state.mailMessageDetails[targetId] = updated;
      }
      await refreshMailState();
      renderAllRegions();
    });
  });

  viewport.querySelectorAll("[data-email-allow-remote]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const sender = (btn as HTMLElement).getAttribute(
        "data-email-allow-remote"
      );
      if (!sender) return;
      await sidecarUpdateMailSettings({ allow_remote_images_sender: sender });
      const [updated, updatedHtml] = await Promise.all([
        sidecarGetMailMessage(messageId),
        sidecarGetMailMessageHtml(messageId),
      ]);
      if (updated.ok) {
        state.mailMessageDetails[messageId] = updated;
      }
      if (updatedHtml.ok && updatedHtml.html) {
        state.mailMessageHtml[messageId] = {
          html: updatedHtml.html,
          csp:
            updatedHtml.csp ||
            "default-src 'none'; img-src https: data: cid:; style-src 'unsafe-inline'; font-src data:",
          translated_html: updatedHtml.translated_html || undefined,
          translation_source_lang: updatedHtml.translation_source_lang || undefined,
          translation_target_lang: updatedHtml.translation_target_lang || undefined,
        };
      }
      renderViewportRegion();
    });
  });

  viewport.querySelectorAll("[data-email-toggle-orig]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mid = (btn as HTMLElement).getAttribute("data-email-toggle-orig") || messageId;
      if (!mid) return;
      state.mailMessageShowOriginal[mid] = !state.mailMessageShowOriginal[mid];
      renderViewportRegion();
    });
  });

  viewport.querySelectorAll("[data-email-translate]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const el = btn as HTMLButtonElement;
      const mid = el.getAttribute("data-email-translate") || messageId;
      if (!mid) return;
      el.disabled = true;
      el.textContent = t("mail.tr_translating");
      const targetLang = state.contentTranslationConfig?.primary_language || "";
      const trRes = await sidecarTranslateMailMessage(mid, targetLang, true);
      if (trRes.ok) {
        const [freshDetail, freshHtml] = await Promise.all([
          sidecarGetMailMessage(mid),
          sidecarGetMailMessageHtml(mid),
        ]);
        if (freshDetail.ok) {
          state.mailMessageDetails[mid] = freshDetail;
        }
        if (freshHtml.ok && freshHtml.html) {
          state.mailMessageHtml[mid] = {
            html: freshHtml.html,
            csp:
              freshHtml.csp ||
              "default-src 'none'; img-src data: cid:; style-src 'unsafe-inline'; font-src data:",
            translated_html: freshHtml.translated_html || undefined,
            translation_source_lang: freshHtml.translation_source_lang || undefined,
            translation_target_lang: freshHtml.translation_target_lang || undefined,
          };
        }
        state.mailMessageShowOriginal[mid] = false;
        await refreshMailState();
      }
      renderViewportRegion();
    });
  });

  viewport.querySelectorAll("[data-email-preview-att]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const el = btn as HTMLElement;
      const partId = el.getAttribute("data-part-id") || "";
      await handleToggleAttachmentPreview(messageId, partId);
    });
  });

  viewport.querySelectorAll("[data-email-save-att]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const el = btn as HTMLElement;
      const partId = el.getAttribute("data-part-id") || "";
      const res = await sidecarSaveMailAttachment(messageId, partId);
      if (res.ok) {
        el.textContent = t("main.mail_saved_downloads");
      }
    });
  });

  viewport.querySelectorAll("[data-email-rail-save-brain]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const el = btn as HTMLElement;
      const subj =
        el.getAttribute("data-email-rail-subj") ||
        String(msg.subject || t("common.mail"));
      const parts = (msg.parts ?? {}) as Record<string, string>;
      const bodyTxt = parts.new || String(msg.body_text || "");
      const res = await sidecarUpsertBrainEntity({
        type: "note",
        name: subj,
        summary: `Saved from email (${String(msg.from_addr || "")})`,
        content: bodyTxt.slice(0, 1200),
        source_url: `satzmail://message/${messageId}`,
      });
      el.textContent = res.ok ? t("main.mail_saved_brain") : t("main.mail_unlock_first");
    });
  });

  viewport.querySelectorAll("[data-email-rail-ask]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const prompt = (btn as HTMLElement).getAttribute("data-email-rail-ask");
      if (!prompt) return;
      state.activeTabId = "chat";
      renderWorkspaceRegions();
      void handleSendChatMessage(prompt);
    });
  });

  viewport.querySelectorAll("[data-open-site-url]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const el = btn as HTMLElement;
      const url = el.getAttribute("data-open-site-url");
      const title = el.getAttribute("data-open-site-title") || "";
      if (url) {
        void startDirectBrowsing(url, title);
      }
    });
  });
}

async function handleMailSingleKeyShortcuts(e: KeyboardEvent): Promise<void> {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const activeEl = document.activeElement;
  if (
    activeEl &&
    (activeEl.tagName === "INPUT" ||
      activeEl.tagName === "TEXTAREA" ||
      activeEl.tagName === "SELECT" ||
      (activeEl as HTMLElement).isContentEditable)
  ) {
    return;
  }
  if (!state.activeDetail || state.activeDetail.conversation.origin !== "mail") {
    return;
  }

  const key = e.key;
  const rows = state.mailSearchRows ?? state.mailLaneRows;
  const isLaneView = state.activeTabId.startsWith("lane:");
  const activeTab = state.activeDetail.tabs.find(
    (t) => t.id === state.activeTabId && t.is_open
  );
  const currentMsgId =
    activeTab && activeTab.url.startsWith("satzmail://message/")
      ? activeTab.url.replace("satzmail://message/", "").split("/")[0].trim()
      : rows[state.mailSelectedRowIdx]
        ? String(
            rows[state.mailSelectedRowIdx].id ??
              rows[state.mailSelectedRowIdx].latest_message_id ??
              ""
          )
        : "";

  if (isLaneView && key === "j") {
    e.preventDefault();
    if (rows.length > 0) {
      state.mailSelectedRowIdx = Math.min(
        rows.length - 1,
        state.mailSelectedRowIdx + 1
      );
      renderViewportRegion();
    }
    return;
  }
  if (isLaneView && key === "k") {
    e.preventDefault();
    if (rows.length > 0) {
      state.mailSelectedRowIdx = Math.max(0, state.mailSelectedRowIdx - 1);
      renderViewportRegion();
    }
    return;
  }
  if (isLaneView && key === "Enter") {
    const row = rows[state.mailSelectedRowIdx];
    if (row) {
      e.preventDefault();
      const mid = String(row.id ?? row.latest_message_id ?? "");
      const subj = String(row.subject ?? row.merchant ?? "mail");
      if (mid) {
        await openEmailMessageTab(mid, subj);
      }
    }
    return;
  }
  if (key === "/") {
    e.preventDefault();
    const sInput = document.getElementById(
      "mail-search-input"
    ) as HTMLInputElement | null;
    sInput?.focus();
    sInput?.select();
    return;
  }
  if (key === "c") {
    e.preventDefault();
    await openComposeTab();
    return;
  }
  if (key === "r" && currentMsgId) {
    e.preventDefault();
    const detail =
      state.mailMessageDetails[currentMsgId] ??
      (await sidecarGetMailMessage(currentMsgId));
    const msg = (detail?.message ?? detail ?? {}) as Record<string, unknown>;
    const origSubj = String(msg.subject || "");
    await openComposeTab({
      to: String(msg.from_addr || ""),
      subject: origSubj.toLowerCase().startsWith("re:")
        ? origSubj
        : `Re: ${origSubj}`,
      in_reply_to: String(msg.message_id || ""),
      references: String(msg.references || ""),
      reply_to_message_id: currentMsgId,
    });
    return;
  }
  if (key === "e" && currentMsgId) {
    e.preventDefault();
    await sidecarHideMailMessage(currentMsgId);
    await refreshMailState();
    renderAllRegions();
    return;
  }
  if (
    (key === "1" || key === "2" || key === "3" || key === "4") &&
    currentMsgId
  ) {
    e.preventDefault();
    const map: Record<string, "email" | "ping" | "information" | "promotion"> = {
      "1": "email",
      "2": "ping",
      "3": "information",
      "4": "promotion",
    };
    await sidecarLabelMailMessage(currentMsgId, map[key]);
    await refreshMailState();
    renderAllRegions();
  }
}

async function handlePrepareUnsubscribeTask(
  messageId: string,
  senderName: string
): Promise<void> {
  if (!state.activeDetail) return;
  const cid = state.activeDetail.conversation.id;
  const res = await sidecarPrepareUnsubscribeTask({
    conversation_id: cid,
    message_id: messageId,
    sender: senderName,
  });
  if (res.ok && res.task) {
    const existing = state.conversationTasks[cid] ?? [];
    state.conversationTasks[cid] = [
      ...existing.filter((t) => t.id !== res.task!.id),
      res.task,
    ];
    state.activeTabId = "chat";
    renderAllRegions();
    scheduleWebviewLayoutSync();
  }
}

async function runBrowserUnsubscribeActorFlow(
  convId: string,
  taskId: string,
  targetUrl: string,
  senderLabel: string
): Promise<void> {
  await sidecarAppendTaskStep(
    taskId,
    `Opening unsubscribe page in live tab: ${targetUrl}`
  );
  state.conversationTasks[convId] = await sidecarListTasks(convId);
  if (state.activeDetail?.conversation.id === convId) {
    renderViewportRegion();
  }

  let detail = await apiGetConversation(convId);
  if (!detail) return;
  const existingTab = detail.tabs.find(
    (t) => t.is_open && t.url === targetUrl
  );
  const tab =
    existingTab ??
    (await apiOpenTab(
      convId,
      targetUrl,
      `Unsubscribe · ${senderLabel || extractDomain(targetUrl)}`
    ));
  detail = await apiGetConversation(convId);
  if (state.activeDetail?.conversation.id === convId && detail) {
    state.activeDetail = detail;
    renderTabStripRegion();
  }

  const cachedRecipe = await sidecarLookupDomainRecipe(targetUrl, "unsubscribe");
  const actorRes = await apiExecuteTabUnsubscribeActor(
    tab.id,
    targetUrl,
    2600,
    cachedRecipe?.selector
  );
  const pageDom = extractDomain(actorRes.url || targetUrl) || targetUrl;

  if (actorRes.status === "already_unsubscribed") {
    const msgTxt = `Unsubscribed from **${senderLabel || pageDom}** (verified on [${pageDom}](${actorRes.url || targetUrl})).`;
    await sidecarCompleteTask(
      taskId,
      msgTxt,
      `Verified unsubscribe confirmation on ${pageDom}`
    );
    await apiAddMessage(convId, "assistant", msgTxt, "actor (agent)", JSON.stringify([]));
  } else if (actorRes.status === "clicked") {
    const clickedLbl = actorRes.clicked_label || "Confirm";
    if (actorRes.matched_selector) {
      void sidecarRecordDomainRecipe({
        domain: pageDom,
        control_key: "unsubscribe",
        selector: actorRes.matched_selector,
        label: clickedLbl,
        action_kind: "click",
        sample_url: actorRes.url || targetUrl,
      });
    }
    const verifiedNote =
      actorRes.final_status === "already_unsubscribed"
        ? "Unsubscribe confirmed on page."
        : actorRes.excerpt
          ? `Page response: "${actorRes.excerpt.slice(0, 140)}"`
          : "Action submitted.";
    const msgTxt = `Clicked **"${clickedLbl}"** to unsubscribe from **${senderLabel || pageDom}** ([${pageDom}](${actorRes.url || targetUrl})). ${verifiedNote}`;
    await sidecarCompleteTask(
      taskId,
      msgTxt,
      `Clicked '${clickedLbl}' on ${pageDom} -> ${verifiedNote}`
    );
    await apiAddMessage(convId, "assistant", msgTxt, "actor (agent)", JSON.stringify([]));
  } else if (actorRes.status === "needs_user") {
    const reasonLbl =
      actorRes.reason === "login_required"
        ? t("main.actor_login_required")
        : t("main.actor_captcha_required");
    const msgTxt = t("main.actor_opened_needs_user", {
      domain: pageDom,
      url: actorRes.url || targetUrl,
      reason: reasonLbl,
    });
    await sidecarCompleteTask(taskId, msgTxt, `${reasonLbl} on ${pageDom}`);
    if (state.activeDetail?.conversation.id === convId) {
      state.activeTabId = tab.id;
    }
    await apiAddMessage(convId, "assistant", msgTxt, "actor (agent)", JSON.stringify([]));
  } else if (actorRes.status === "unavailable") {
    const msgTxt = `Opened unsubscribe link [${pageDom}](${targetUrl}) in a tab (live WebView actor unavailable in preview mode).`;
    await sidecarCompleteTask(taskId, msgTxt, `Opened ${pageDom}`);
  } else {
    const msgTxt = t("main.actor_opened_confirm", {
      domain: pageDom,
      url: actorRes.url || targetUrl,
    });
    await sidecarCompleteTask(
      taskId,
      msgTxt,
      `Manual confirmation needed on ${pageDom}`
    );
    if (state.activeDetail?.conversation.id === convId) {
      state.activeTabId = tab.id;
    }
    await apiAddMessage(convId, "assistant", msgTxt, "actor (agent)", JSON.stringify([]));
  }

  state.conversationTasks[convId] = await sidecarListTasks(convId);
  await refreshCompletedConversation(convId);
  scheduleWebviewLayoutSync();
}

async function handleConfirmActorTaskStep(
  taskId: string,
  stepId: string,
  confirmToken: string
): Promise<void> {
  if (!state.activeDetail) return;
  const cid = state.activeDetail.conversation.id;
  const preTask = (state.conversationTasks[cid] ?? []).find(
    (t) => t.id === taskId
  );
  const preStep = preTask?.steps.find((s) => s.id === stepId);

  const res = await sidecarConfirmTaskStep(taskId, stepId, confirmToken);
  if (!res.ok) return;

  const updatedTask = res.task;
  const confirmedStep =
    updatedTask?.steps.find((s) => s.id === stepId) ?? preStep;
  const ap = (confirmedStep?.action_payload ?? {}) as Record<string, unknown>;

  state.conversationTasks[cid] = await sidecarListTasks(cid);
  renderViewportRegion();

  const actionType = String(ap.action_type || "");
  if (actionType === "archive_sender_fallback") {
    const sender = String(ap.sender || "");
    const hideRes = await sidecarHideMailSender(sender, taskId);
    state.conversationTasks[cid] = await sidecarListTasks(cid);
    if (hideRes.ok) {
      await refreshMailState();
      const note = `Archived ${hideRes.hidden_count ?? 0} email(s) from **${sender}** locally.`;
      await apiAddMessage(cid, "assistant", note, "actor (agent)", JSON.stringify([]));
    }
    await refreshCompletedConversation(cid);
    return;
  }

  if (actionType === "browser_unsubscribe") {
    const url = String(ap.url || "");
    const senderName = String(ap.sender_name || "");
    if (url) {
      await runBrowserUnsubscribeActorFlow(cid, taskId, url, senderName);
    }
    return;
  }

  if (actionType === "mail_unsubscribe") {
    const mid = String(ap.message_id || "");
    const senderName = String(ap.sender_name || ap.sender || "sender");
    const methodType = String(ap.preferred_method || "");
    const targetUrl = String(ap.url || "");

    const execRes = await sidecarExecuteMailUnsubscribe({
      message_id: mid,
      url: targetUrl,
      method_type: methodType,
      task_id: taskId,
      step_id: stepId,
    });

    if (execRes.ok && execRes.executed) {
      state.conversationTasks[cid] = await sidecarListTasks(cid);
      const via =
        execRes.method === "one_click_post"
          ? `RFC 8058 One-Click POST (HTTP ${execRes.http_status ?? 200})`
          : execRes.method === "mailto"
            ? `email sent to ${execRes.sent_to}`
            : execRes.method || "unsubscribe";
      const doneNote = `Unsubscribed from **${senderName}** (${execRes.from_addr || ""}) via ${via}.`;
      await apiAddMessage(
        cid,
        "assistant",
        doneNote,
        "actor (agent)",
        JSON.stringify(mid ? [`mail:${mid}`] : [])
      );
      await refreshCompletedConversation(cid);
      return;
    }

    if (execRes.ok && execRes.needs_browser_actor && execRes.url) {
      await runBrowserUnsubscribeActorFlow(
        cid,
        taskId,
        execRes.url,
        senderName
      );
      return;
    }

    state.conversationTasks[cid] = await sidecarListTasks(cid);
    renderViewportRegion();
  }

  if (actionType === "run_comparer") {
    const goal = String(ap.goal || "compare these");
    const sourcesArg = Array.isArray(ap.sources)
      ? (ap.sources as Array<{
          id?: string;
          url: string;
          title?: string;
          domain?: string;
          text?: string;
        }>)
      : [];
    const compRes = await sidecarRunComparer(
      cid,
      sourcesArg,
      goal,
      taskId,
      stepId
    );
    state.conversationTasks[cid] = await sidecarListTasks(cid);
    if (compRes.ok && compRes.table_md) {
      const extrasObj = {
        cited_sources: compRes.cited_sources ?? [],
      };
      const savedMsg = await apiAddMessage(
        cid,
        "assistant",
        compRes.table_md,
        "comparer (agent)",
        JSON.stringify(compRes.source_ids ?? []),
        null,
        null,
        null,
        JSON.stringify(extrasObj)
      );
      if (compRes.cited_sources && compRes.cited_sources.length > 0) {
        state.messageCitedSources[savedMsg.id] = compRes.cited_sources;
      }
      await refreshCompletedConversation(cid, savedMsg.id);
      return;
    }
    renderViewportRegion();
    return;
  }

  if (actionType === "add_watch") {
    const watchRes = await sidecarAddWatch({
      conversation_id: cid,
      query_or_url: String(ap.url || ap.query_or_url || ""),
      cadence_seconds: Number(ap.cadence_seconds || 1800),
      condition: String(ap.condition || "any_change"),
      title: String(ap.title || ""),
      task_id: taskId,
      step_id: stepId,
    });
    state.conversationTasks[cid] = await sidecarListTasks(cid);
    if (watchRes.ok && watchRes.watch) {
      const wList = await sidecarListWatches();
      state.watches = wList.watches;
      state.watchBadgeConvIds = wList.watch_badges;
      state.watchStatusNotice = t("main.watch_active", {
        title: watchRes.watch.title || watchRes.watch.query_or_url,
      });
      const doneNote = `Started recurring watch on **${watchRes.watch.title || watchRes.watch.query_or_url}** (${watchRes.watch.condition}, current: ${watchRes.watch.last_value || "monitoring"}).`;
      await apiAddMessage(cid, "assistant", doneNote, "watcher (agent)", JSON.stringify([]));
      await refreshCompletedConversation(cid);
      renderAllRegions();
      return;
    }
    renderViewportRegion();
    return;
  }

  if (actionType === "mail_draft") {
    const apBody = String(ap.body || "");
    const apInstructions = String(ap.instructions || "");
    const draftSeed: Partial<MailComposeDraft> = {
      to: String(ap.to || ""),
      cc: String(ap.cc || ""),
      subject: String(ap.subject || ""),
      body: apBody,
      reply_to_message_id: String(ap.reply_to_message_id || ""),
    };
    await createInlineComposeInChat(
      draftSeed,
      apBody && apBody !== apInstructions ? undefined : apInstructions || undefined
    );
    await sidecarCompleteTask(
      taskId,
      `Opened editable email draft to ${draftSeed.to || "(recipient)"} (${draftSeed.subject || "no subject"}) - not sent yet.`,
      "Opened inline email draft card"
    );
    state.conversationTasks[cid] = await sidecarListTasks(cid);
    renderViewportRegion();
    return;
  }

  if (actionType === "tab_action") {
    const tabId = String(ap.tab_id || state.activeTabId || "");
    const execRes = await apiExecuteTabAction(tabId, {
      expected_origin: String(ap.expected_origin || ""),
      eid: String(ap.eid || ""),
      action_kind: String(ap.action_kind || "click"),
      value: String(ap.value || ""),
      element_label: String(ap.element_label || ""),
      selector_hint: ap.selector_hint,
    });
    if (execRes.ok) {
      await apiCaptureOpenTabs(cid);
      const summary = `Executed ${execRes.action_kind || ap.action_kind || "action"} on ${execRes.label || ap.element_label || execRes.eid || "control"}${execRes.new_value ? ` (value: ${execRes.new_value})` : ""}.`;
      await sidecarCompleteTask(taskId, summary, summary);
      await apiAddMessage(cid, "assistant", summary, "actor (agent)", JSON.stringify([]));
      state.conversationTasks[cid] = await sidecarListTasks(cid);
      await refreshCompletedConversation(cid);
      scheduleWebviewLayoutSync();
      return;
    }
    const failMsg = `Tab action failed: ${execRes.error || "control not found or origin mismatch"}`;
    await sidecarCompleteTask(taskId, failMsg, failMsg);
    state.conversationTasks[cid] = await sidecarListTasks(cid);
    renderViewportRegion();
    return;
  }

  if (actionType === "set_default_provider") {
    const execRes = await sidecarExecuteSetDefaultProvider(taskId, stepId);
    state.conversationTasks[cid] = await sidecarListTasks(cid);
    const provReg = await sidecarGetProviders();
    if (provReg) state.providerRegistry = provReg;
    if (execRes.ok) {
      const doneNote =
        execRes.message ||
        `Updated default provider for **${String(ap.category_id || "")}** to **${String(ap.display_name || "")}**.`;
      await apiAddMessage(cid, "assistant", doneNote, "providers (agent)", JSON.stringify([]));
      await refreshCompletedConversation(cid);
      return;
    }
    renderViewportRegion();
    return;
  }

  if (actionType === "skill_continue") {
    const contRes = await sidecarContinueSkill(taskId, stepId);
    state.conversationTasks[cid] = await sidecarListTasks(cid);
    if (contRes.ok && contRes.task?.result_md && contRes.status === "completed") {
      await apiAddMessage(
        cid,
        "assistant",
        contRes.task.result_md,
        String(contRes.task.agent || "skill"),
        JSON.stringify([])
      );
      await refreshMailState();
      await refreshCompletedConversation(cid);
      return;
    }
    renderViewportRegion();
  }
}

if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", () => {
    void initApp();
  });
} else {
  void initApp();
}
