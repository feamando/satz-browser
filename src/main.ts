import { listen } from "@tauri-apps/api/event";
import {
  apiAddBookmark,
  apiAddMessage,
  apiArchiveConversation,
  apiAutofillTabCredentials,
  apiCaptureOpenTabs,
  apiCloseTab,
  apiControlTab,
  apiCreateConversation,
  apiDeleteConversation,
  apiGetConversation,
  apiListBookmarks,
  apiListConversations,
  apiNavigateAndCaptureTab,
  apiNavigateTab,
  apiOpenTab,
  apiPinConversation,
  apiRemoveBookmark,
  apiRenameConversation,
  apiSetConversationSummary,
  apiSetSourceInContext,
  sidecarAcceptBrainProposal,
  sidecarCreateProfile,
  sidecarDeleteBrainEntity,
  sidecarDeletePassage,
  sidecarDeletePassword,
  sidecarDeleteProfile,
  sidecarFetchDigest,
  sidecarFetchHealth,
  sidecarFetchKnowledge,
  sidecarGetMailCodes,
  sidecarImportEnvFile,
  sidecarLockProfile,
  sidecarMatchPasswordForUrl,
  sidecarRejectBrainProposal,
  sidecarRevealPassword,
  sidecarRunAnswer,
  sidecarRunRead,
  sidecarSaveRawEnv,
  sidecarSetPauseLearning,
  sidecarStreamChat,
  sidecarSummarizeConversation,
  sidecarSyncBookmarks,
  sidecarUnlockProfile,
  sidecarUpsertPassword,
} from "./api";
import {
  appendStreamingDelta,
  renderChatPanel,
  tickStreamingElapsed,
  updateStreamingStatus,
} from "./chat";
import { bindKeyboardShortcuts } from "./keys";
import { renderKnowledgeView } from "./knowledge";
import {
  refreshMailState,
  renderComposeTabView,
  renderEmailAgentRailCardsHtml,
  renderEmailTabHeaderHtml,
  renderMailLaneView,
  sidecarGetMailMessage,
  sidecarHideMailMessage,
  sidecarLabelMailMessage,
  sidecarOpenMailMessage,
  sidecarSaveMailAttachment,
  sidecarUpdateMailSettings,
} from "./mail";
import { renderRail } from "./rail";
import { renderSourcesPanel } from "./sources";
import { renderStartScreen } from "./start";
import {
  classifyStartInput,
  escapeHtml,
  extractDomain,
  getActiveTabSources,
  MOD_LABEL,
  normalizeUrl,
  resolveLiveNavigationTarget,
  state,
} from "./state";
import { renderStatusLine } from "./status";
import { renderTabStrip, scheduleWebviewLayoutSync } from "./tabs";
import type { LocalModelId, TabPageEvent } from "./types";

let resizeObserver: ResizeObserver | null = null;
let streamingTimerId: number | null = null;

function startStreamingProgress(initialStatus: string, phase: string): void {
  state.isStreaming = true;
  state.streamingText = "";
  state.streamingStatus = initialStatus;
  state.streamingPhase = phase;
  state.streamingStartedAt = Date.now();
  state.streamingSteps = [initialStatus];
  if (streamingTimerId !== null) {
    window.clearInterval(streamingTimerId);
  }
  streamingTimerId = window.setInterval(() => {
    tickStreamingElapsed();
  }, 200);
}

function stopStreamingProgress(): void {
  if (streamingTimerId !== null) {
    window.clearInterval(streamingTimerId);
    streamingTimerId = null;
  }
  state.isStreaming = false;
  state.streamingText = "";
  state.streamingStatus = "";
  state.streamingPhase = "";
  state.streamingStartedAt = 0;
  state.streamingSteps = [];
}

async function initApp(): Promise<void> {
  mountShellSkeleton();

  bindKeyboardShortcuts({
    onNewConversation: () => {
      state.activeDetail = null;
      state.showKnowledgeView = false;
      state.compareMode = false;
      renderAllRegions();
    },
    onFilterConversations: () => {
      const el = document.getElementById(
        "rail-filter-input"
      ) as HTMLInputElement | null;
      el?.focus();
      el?.select();
    },
    onNewTab: () => {
      void handleCreateNewTab();
    },
    onCloseTab: () => {
      if (state.activeTabId !== "chat") {
        void handleCloseTab(state.activeTabId);
      }
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
      state.agentRailOpen = !state.agentRailOpen;
      renderViewportRegion();
    },
    onToggleCompare: () => {
      handleToggleCompareMode();
    },
    onBookmarkCurrentPage: () => {
      void handleBookmarkCurrentPage();
    },
    onEscape: () => {
      if (state.compareMode) {
        state.compareMode = false;
        renderWorkspaceRegions();
      }
    },
  });

  window.addEventListener("keydown", (e: KeyboardEvent) => {
    void handleMailSingleKeyShortcuts(e);
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

  await listen<string>("menu-shortcut", (event) => {
    handleMenuShortcut(event.payload);
  });

  await refreshLists();
  renderAllRegions();

  void pollSidecarState();
  window.setInterval(() => {
    void pollSidecarState();
  }, 6000);
}

function handleMenuShortcut(cmd: string): void {
  if (cmd === "new_conversation") {
    state.activeDetail = null;
    state.showKnowledgeView = false;
    state.compareMode = false;
    renderAllRegions();
  } else if (cmd === "filter_conversations") {
    const el = document.getElementById(
      "rail-filter-input"
    ) as HTMLInputElement | null;
    el?.focus();
    el?.select();
  } else if (cmd === "new_tab") {
    void handleCreateNewTab();
  } else if (cmd === "close_tab") {
    if (state.activeTabId !== "chat") {
      void handleCloseTab(state.activeTabId);
    }
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
    state.agentRailOpen = !state.agentRailOpen;
    renderViewportRegion();
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

async function pollSidecarState(): Promise<void> {
  state.sidecar = await sidecarFetchHealth();
  if (state.sidecar.online) {
    if (state.sidecar.mail?.counts) {
      state.mailCounts = state.sidecar.mail.counts;
    }
    void sidecarSyncBookmarks(state.bookmarks);
    if (!state.knowledge.profile) {
      const kb = await sidecarFetchKnowledge();
      if (kb) {
        state.knowledge = kb;
        if (kb.profile?.unlocked) {
          await refreshMailState();
          await refreshLists();
        }
        renderRailRegion();
      }
    }
    if (!state.activeDetail && state.digestItems.length === 0) {
      state.digestItems = await sidecarFetchDigest();
      if (!state.activeDetail && !state.showKnowledgeView) {
        renderViewportRegion();
      }
    }
  }
  renderStatusLine();
}

function mountShellSkeleton(): void {
  const app = document.getElementById("app");
  if (!app) return;
  app.innerHTML = `
    <div class="shell-root">
      <div class="shell-main-row">
        <aside class="left-rail" id="region-rail"></aside>
        <main class="workspace-column">
          <header class="tab-strip" id="region-tab-strip"></header>
          <div class="workspace-body" id="region-viewport"></div>
        </main>
      </div>
      <footer class="status-line" id="region-status-bar"></footer>
    </div>
  `;
}

async function refreshLists(): Promise<void> {
  const [convs, bookmarks] = await Promise.all([
    apiListConversations(),
    apiListBookmarks(),
  ]);
  state.conversations = convs;
  state.bookmarks = bookmarks;
  if (state.sidecar.online) {
    void sidecarSyncBookmarks(bookmarks);
  }
}

async function handleTabPageEvent(payload: TabPageEvent): Promise<void> {
  if (!state.activeDetail) return;
  const tab = state.activeDetail.tabs.find((t) => t.id === payload.tab_id);
  if (!tab) return;

  if (payload.url && payload.url !== tab.url) {
    tab.url = payload.url;
    const addrEl = document.getElementById(
      `address-input-${tab.id}`
    ) as HTMLInputElement | null;
    if (addrEl && document.activeElement !== addrEl) {
      addrEl.value = payload.url;
    }
  }
  if (payload.title && payload.title !== tab.title) {
    tab.title = payload.title;
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
      renderViewportRegion();
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
      renderTabStripRegion();
      renderStatusLine();
      refreshChatContextIfVisible();
    }
  } else {
    renderTabStripRegion();
    refreshChatContextIfVisible();
  }
}

function refreshChatContextIfVisible(): void {
  if (state.isStreaming) return;
  const chatEl =
    document.getElementById("chat-main-container") ??
    document.getElementById("site-tab-agent-rail") ??
    document.getElementById("compare-agent-rail");
  if (chatEl) {
    renderChatPanel(chatEl, getChatActions());
  }
}

function renderAllRegions(): void {
  renderRailRegion();
  renderWorkspaceRegions();
  renderStatusLine();
}

function renderWorkspaceRegions(): void {
  renderTabStripRegion();
  renderViewportRegion();
  renderStatusLine();
}

function renderRailRegion(): void {
  renderRail({
    onSelectConversation: (id) => {
      void selectConversation(id);
    },
    onNewConversation: () => {
      state.activeDetail = null;
      state.showKnowledgeView = false;
      state.compareMode = false;
      renderAllRegions();
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
    onBookmarkCurrent: () => {
      void handleBookmarkCurrentPage();
    },
    onRemoveBookmark: async (id) => {
      await apiRemoveBookmark(id);
      await refreshLists();
      renderRailRegion();
    },
    onOpenKnowledgeView: async () => {
      state.showKnowledgeView = !state.showKnowledgeView;
      if (state.showKnowledgeView) {
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        await refreshMailState();
      }
      renderAllRegions();
    },
  });
}

function renderTabStripRegion(): void {
  renderTabStrip({
    onSelectTab: (tabId) => {
      state.compareMode = false;
      state.activeTabId = tabId;
      if (tabId.startsWith("lane:")) {
        const laneName = tabId.slice(5) as "inbox" | "pings" | "orders" | "promos";
        state.mailActiveLane = laneName;
        void (async () => {
          await refreshMailState();
          renderWorkspaceRegions();
        })();
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
  });
}

function renderViewportRegion(): void {
  const viewport = document.getElementById("region-viewport");
  if (!viewport) return;

  if (resizeObserver) {
    resizeObserver.disconnect();
  }

  if (state.showKnowledgeView) {
    renderKnowledgeView(viewport, {
      onTogglePauseLearning: async (paused) => {
        const updated = await sidecarSetPauseLearning(paused);
        state.knowledge.pause_learning = updated;
        state.sidecar.pause_learning = updated;
        renderViewportRegion();
        renderStatusLine();
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
        const res = await sidecarCreateProfile(name, pin);
        state.profileStatusMessage = res.ok
          ? `profile "${name}" created and unlocked.`
          : `error: ${res.error ?? "failed to create profile (ensure PIN is 6 digits)"}`;
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        await refreshMailState();
        await refreshLists();
        renderAllRegions();
      },
      onUnlockProfile: async (profileId, pin) => {
        state.revealedPasswords = {};
        const res = await sidecarUnlockProfile(profileId, pin);
        state.profileStatusMessage = res.ok
          ? `profile "${profileId}" unlocked.`
          : `error: ${res.error ?? "invalid 6-digit PIN"}`;
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        await refreshMailState();
        await refreshLists();
        renderAllRegions();
      },
      onLockProfile: async () => {
        state.revealedPasswords = {};
        await sidecarLockProfile();
        state.profileStatusMessage = "profile locked. encrypted vault unloaded.";
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        await refreshMailState();
        renderAllRegions();
      },
      onDeleteProfile: async (profileId, pin) => {
        state.revealedPasswords = {};
        const res = await sidecarDeleteProfile(profileId, pin);
        state.profileStatusMessage = res.ok
          ? `profile "${profileId}" deleted.`
          : `error: ${res.error ?? "enter the profile's 6-digit PIN to delete"}`;
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderAllRegions();
      },
      onUpsertPassword: async (payload) => {
        const res = await sidecarUpsertPassword(payload);
        state.profileStatusMessage = res.ok
          ? `saved ${payload.service} credentials to active profile vault.enc.`
          : `error: ${res.error ?? "failed to save credential"}`;
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderViewportRegion();
      },
      onSaveRawEnv: async (rawEnv) => {
        const res = await sidecarSaveRawEnv(rawEnv);
        state.profileStatusMessage = res.ok
          ? "merged .env lines into encrypted profile vault.enc."
          : `error: ${res.error ?? "failed to save vault"}`;
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderViewportRegion();
      },
      onImportEnvFile: async (path) => {
        const res = await sidecarImportEnvFile(path);
        state.profileStatusMessage = res.ok
          ? `imported credentials from ${path} into profile vault.enc.`
          : `error: ${res.error ?? "failed to import .env file"}`;
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderViewportRegion();
      },
      onDeletePassword: async (service) => {
        await sidecarDeletePassword(service);
        state.profileStatusMessage = `deleted ${service} from profile vault.enc.`;
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        renderViewportRegion();
      },
      onRevealPassword: async (service, field, pin) => {
        if (!pin) {
          state.profileStatusMessage = "enter your 6-digit PIN in the reveal box first.";
          renderViewportRegion();
          return;
        }
        const res = await sidecarRevealPassword(service, field, pin);
        if (res.ok && res.value !== undefined) {
          state.revealedPasswords[`${service}:${field}`] = res.value;
          state.profileStatusMessage = `revealed ${service} ${field}.`;
        } else {
          state.profileStatusMessage = `error: ${res.error ?? "failed to reveal secret"}`;
        }
        renderViewportRegion();
      },
      onAutofillActiveTab: async () => {
        const openTab = state.activeDetail?.tabs.find((t) => t.is_open);
        if (openTab) {
          const ok = await apiAutofillTabCredentials(openTab.id, false);
          state.profileStatusMessage = ok
            ? `filled login credentials on open tab (${extractDomain(openTab.url)}).`
            : `no matching credentials found for ${extractDomain(openTab.url)}.`;
          renderViewportRegion();
        }
      },
      onMailChanged: async () => {
        await refreshLists();
        renderAllRegions();
      },
      onCloseKnowledgeView: () => {
        state.showKnowledgeView = false;
        renderAllRegions();
      },
    });
    scheduleWebviewLayoutSync();
    return;
  }

  if (!state.activeDetail) {
    renderStartScreen(viewport, {
      onSubmitStartInput: (raw) => {
        void handleStartSubmission(raw);
      },
      onSelectConversation: (id) => {
        void selectConversation(id);
      },
      onOpenDigestUrl: (url) => {
        if (url.startsWith("satzmail://message/")) {
          const mid = url.replace("satzmail://message/", "").split("/")[0].trim();
          const mailConv = state.conversations.find((c) => c.origin === "mail");
          if (mailConv && mid) {
            void (async () => {
              await selectConversation(mailConv.id);
              await openEmailMessageTab(mid, "mail");
            })();
            return;
          }
        }
        void startDirectBrowsing(url);
      },
      onChangeModel: (model) => {
        state.selectedModel = model;
        renderViewportRegion();
        renderStatusLine();
      },
      onToggleWeb: () => {
        state.webSearchEnabled = !state.webSearchEnabled;
        renderViewportRegion();
      },
    });
    scheduleWebviewLayoutSync();
    return;
  }

  if (state.compareMode && state.compareTabIds.length >= 2) {
    renderCompareViewport(viewport);
    scheduleWebviewLayoutSync();
    return;
  }

  if (state.activeTabId.startsWith("lane:")) {
    renderMailLaneView(viewport, {
      onOpenEmailMessage: (messageId, subject) => {
        void openEmailMessageTab(messageId, subject);
      },
      onOpenComposeTab: (seed) => {
        void openComposeTab(seed);
      },
      onOpenSiteUrl: (url, title) => {
        void handleOpenUrlAsTab(url, title);
      },
      onRefreshState: async () => {
        await refreshLists();
        renderAllRegions();
      },
    });
    scheduleWebviewLayoutSync();
    return;
  }

  if (state.activeTabId === "chat") {
    viewport.innerHTML = `
      <div class="chat-view">
        <div class="viewport-primary" id="chat-main-container"></div>
        ${
          state.agentRailOpen
            ? `<aside class="right-panel" id="chat-sources-rail"></aside>`
            : ""
        }
      </div>
    `;
    const chatEl = document.getElementById("chat-main-container");
    if (chatEl) {
      renderChatPanel(chatEl, getChatActions());
    }
    const sourcesEl = document.getElementById("chat-sources-rail");
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
    renderComposeTabView(viewport, tab, () => {
      renderViewportRegion();
    });
    return;
  }

  if (tab.kind === "mail" || tab.url.startsWith("satzmail://")) {
    const mid = tab.url.replace("satzmail://message/", "").split("/")[0].trim();
    const cachedDetail = state.mailMessageDetails[mid];
    if (!cachedDetail && mid) {
      void (async () => {
        const res = await sidecarGetMailMessage(mid);
        if (res.ok) {
          state.mailMessageDetails[mid] = res;
          renderViewportRegion();
        }
      })();
    }

    viewport.innerHTML = `
      <div class="chat-view">
        <div class="viewport-primary">
          ${renderEmailTabHeaderHtml(tab, cachedDetail)}
          <div id="webview-slot-${escapeHtml(tab.id)}" class="webview-slot">
            loading ${escapeHtml(tab.url)}...
          </div>
        </div>
        ${
          state.agentRailOpen
            ? `<aside class="right-panel" id="site-tab-agent-rail">
                ${renderEmailAgentRailCardsHtml(cachedDetail)}
                <div id="email-tab-chat-container"></div>
              </aside>`
            : ""
        }
      </div>
    `;

    const chatEl =
      document.getElementById("email-tab-chat-container") ??
      document.getElementById("site-tab-agent-rail");
    if (chatEl) {
      renderChatPanel(chatEl, getChatActions());
    }

    bindEmailTabHeaderEvents(viewport, mid, cachedDetail);
    bindToolbarEvents(viewport);
    return;
  }

  const tabDomain = extractDomain(tab.url);
  if (
    tabDomain &&
    state.siteTabPromoCodes[tab.id] === undefined &&
    state.sidecar.online
  ) {
    state.siteTabPromoCodes[tab.id] = [];
    void (async () => {
      const codes = await sidecarGetMailCodes(tabDomain);
      state.siteTabPromoCodes[tab.id] = codes;
      if (codes.length > 0 && state.activeTabId === tab.id) {
        renderViewportRegion();
      }
    })();
  }
  const activePromoCodes = state.siteTabPromoCodes[tab.id] ?? [];
  const showCodesPopover =
    state.openCodesPopoverTabId === tab.id && activePromoCodes.length > 0;

  viewport.innerHTML = `
    <div class="chat-view">
      <div class="viewport-primary">
        <div class="site-tab-toolbar">
          <button data-nav-btn="back" data-tab="${escapeHtml(tab.id)}">&lt;-</button>
          <button data-nav-btn="forward" data-tab="${escapeHtml(tab.id)}">-&gt;</button>
          <button data-nav-btn="reload" data-tab="${escapeHtml(tab.id)}">[reload]</button>
          <input
            id="address-input-${escapeHtml(tab.id)}"
            class="address-input"
            data-address-tab="${escapeHtml(tab.id)}"
            type="text"
            value="${escapeHtml(tab.url)}"
          />
          ${
            activePromoCodes.length > 0
              ? `
          <button
            data-codes-pill-tab="${escapeHtml(tab.id)}"
            class="${showCodesPopover ? "active" : ""}"
            title="Active promo codes from mail for ${escapeHtml(tabDomain)}"
          >
            [codes (${activePromoCodes.length})]
          </button>
          `
              : ""
          }
          ${
            state.tabCanFillLogin[tab.id]
              ? `
          <button
            data-autofill-tab="${escapeHtml(tab.id)}"
            title="Fill login credentials (${MOD_LABEL}+shift+l)"
          >
            [fill login]
          </button>
          `
              : ""
          }
          <button id="toggle-agent-rail-btn" class="${state.agentRailOpen ? "active" : ""}">
            [chat rail ${MOD_LABEL}+j]
          </button>
        </div>
        ${
          showCodesPopover
            ? `
        <div class="kb-card">
          <div class="rail-row">
            <span class="muted">promo codes for ${escapeHtml(tabDomain)}:</span>
            <div>
              ${activePromoCodes
                .map(
                  (c) =>
                    `<button data-copy-promo-code="${escapeHtml(String(c.code ?? ""))}">[copy ${escapeHtml(String(c.code ?? ""))}${c.discount_value ? ` · ${escapeHtml(String(c.discount_value))}` : ""}${c.expiry ? ` · exp ${escapeHtml(String(c.expiry))}` : ""}]</button>`
                )
                .join(" ")}
            </div>
          </div>
        </div>
        `
            : ""
        }
        <div id="webview-slot-${escapeHtml(tab.id)}" class="webview-slot">
          loading ${escapeHtml(tab.url)}...
        </div>
      </div>
      ${
        state.agentRailOpen
          ? `<aside class="right-panel" id="site-tab-agent-rail"></aside>`
          : ""
      }
    </div>
  `;

  const railEl = document.getElementById("site-tab-agent-rail");
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
    <div class="chat-view">
      <div class="viewport-primary">
        <div class="compare-grid panes-${count}">
          ${tabs
            .map(
              (tab) => `
            <div class="compare-tile">
              <div class="site-tab-toolbar">
                <button data-nav-btn="back" data-tab="${escapeHtml(tab.id)}">&lt;-</button>
                <button data-nav-btn="forward" data-tab="${escapeHtml(tab.id)}">-&gt;</button>
                <button data-nav-btn="reload" data-tab="${escapeHtml(tab.id)}">[r]</button>
                <input
                  id="address-input-${escapeHtml(tab.id)}"
                  class="address-input"
                  data-address-tab="${escapeHtml(tab.id)}"
                  type="text"
                  value="${escapeHtml(tab.url)}"
                />
              </div>
              <div id="webview-slot-${escapeHtml(tab.id)}" class="webview-slot">
                loading ${escapeHtml(tab.url)}...
              </div>
            </div>
          `
            )
            .join("")}
        </div>
      </div>
      ${
        state.agentRailOpen
          ? `<aside class="right-panel" id="compare-agent-rail"></aside>`
          : ""
      }
    </div>
  `;

  const railEl = document.getElementById("compare-agent-rail");
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
          renderStatusLine();
        }
      }
    });
  });

  viewport
    .querySelector("#toggle-agent-rail-btn")
    ?.addEventListener("click", () => {
      state.agentRailOpen = !state.agentRailOpen;
      renderViewportRegion();
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
      state.openCodesPopoverTabId =
        state.openCodesPopoverTabId === tabId ? null : tabId;
      renderViewportRegion();
    });
  });

  viewport.querySelectorAll("[data-copy-promo-code]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const code = el.getAttribute("data-copy-promo-code") || "";
      if (code && navigator.clipboard) {
        void navigator.clipboard.writeText(code);
        el.textContent = `[copied ${code}]`;
      }
    });
  });

  if (resizeObserver) {
    viewport.querySelectorAll(".webview-slot").forEach((slot) => {
      resizeObserver?.observe(slot);
    });
  }
}

function getChatActions() {
  return {
    onSendMessage: (text: string) => {
      void handleSendChatMessage(text);
    },
    onChangeModel: (model: LocalModelId) => {
      state.selectedModel = model;
      renderViewportRegion();
      renderStatusLine();
    },
    onToggleWeb: () => {
      state.webSearchEnabled = !state.webSearchEnabled;
      renderViewportRegion();
    },
    onToggleMail: () => {
      if (state.activeDetail?.conversation.origin === "mail") {
        return;
      }
      state.mailContextEnabled = !state.mailContextEnabled;
      renderViewportRegion();
    },
    onClickCitation: (citationIndex: number, sourceId: string | null) => {
      void handleCitationClick(citationIndex, sourceId);
    },
    onOpenUrlAsTab: (url: string, title: string) => {
      void handleOpenUrlAsTab(url, title);
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
  };
}

async function selectConversation(conversationId: string): Promise<void> {
  state.showKnowledgeView = false;
  state.compareMode = false;
  state.compareTabIds = [];
  const detail = await apiGetConversation(conversationId);
  state.activeDetail = detail;
  if (detail) {
    const openTabs = detail.tabs.filter((t) => t.is_open);
    if (detail.conversation.origin === "mail") {
      state.mailActiveLane = "inbox";
      await refreshMailState();
      state.activeTabId = "lane:inbox";
      state.agentRailOpen = true;
    } else if (detail.conversation.origin === "direct" && openTabs.length > 0) {
      state.activeTabId = openTabs[0].id;
      state.agentRailOpen = false;
    } else {
      state.activeTabId = "chat";
      state.agentRailOpen = true;
    }
  }
  renderAllRegions();
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
  renderAllRegions();
  await handleSendChatMessage(question);
}

async function startDirectBrowsing(rawUrl: string): Promise<void> {
  const url = normalizeUrl(rawUrl);
  const domain = extractDomain(url);
  const conv = await apiCreateConversation(domain, "direct");
  const tab = await apiOpenTab(conv.id, url, domain);
  state.activeDetail = await apiGetConversation(conv.id);
  state.showKnowledgeView = false;
  state.compareMode = false;
  state.activeTabId = tab.id;
  state.agentRailOpen = false;
  await refreshLists();
  renderAllRegions();
}

async function handleCreateNewTab(): Promise<void> {
  if (!state.activeDetail) {
    const conv = await apiCreateConversation("new session", "direct");
    state.activeDetail = await apiGetConversation(conv.id);
  }
  if (!state.activeDetail) return;
  const tab = await apiOpenTab(
    state.activeDetail.conversation.id,
    "https://en.wikipedia.org",
    "new tab"
  );
  state.activeDetail = await apiGetConversation(
    state.activeDetail.conversation.id
  );
  state.compareMode = false;
  state.activeTabId = tab.id;
  await refreshLists();
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
  renderAllRegions();
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
  await apiAddBookmark(title || dom, url);
  state.bookmarkTooltipNotice = `hooked up: ${dom} will be indexed continuously in the background`;
  await refreshLists();
  renderRailRegion();
  setTimeout(() => {
    if (state.bookmarkTooltipNotice.includes(dom)) {
      state.bookmarkTooltipNotice = "";
      renderRailRegion();
    }
  }, 5000);
}

async function handleOpenUrlAsTab(url: string, title: string): Promise<void> {
  if (!state.activeDetail) return;
  const tab = await apiOpenTab(
    state.activeDetail.conversation.id,
    url,
    title || extractDomain(url)
  );
  state.activeDetail = await apiGetConversation(
    state.activeDetail.conversation.id
  );
  state.compareMode = false;
  state.activeTabId = tab.id;
  await refreshLists();
  renderAllRegions();
}

async function handleCitationClick(
  citationIndex: number,
  sourceId: string | null
): Promise<void> {
  if (!state.activeDetail) return;

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

async function handleSendChatMessage(text: string): Promise<void> {
  if (!state.activeDetail || state.isStreaming) return;
  const convId = state.activeDetail.conversation.id;
  state.lastUserPrompt = text;

  await apiAddMessage(convId, "user", text, null, null);
  state.activeDetail = await apiGetConversation(convId);

  if (!state.sidecar.online) {
    await apiAddMessage(
      convId,
      "assistant",
      "models [offline]: start the local sidecar service to run gemma, planck3, or hertz.",
      state.selectedModel,
      JSON.stringify([])
    );
    state.activeDetail = await apiGetConversation(convId);
    renderViewportRegion();
    return;
  }

  startStreamingProgress("capturing live open tab DOM...", "capturing");
  renderViewportRegion();

  try {
    // 1. Check if the user prompt requests finding/searching/browsing a site or web query.
    // If so, actively navigate the live WebView2 tab (or open a tab if on [1 chat]) and capture its rendered DOM + images.
    const navTarget = resolveLiveNavigationTarget(
      text,
      state.activeDetail?.tabs ?? [],
      state.activeTabId,
      state.webSearchEnabled
    );
    if (navTarget) {
      updateStreamingStatus(
        `navigating live browser tab to ${navTarget.targetUrl}...`,
        "navigating"
      );
      if (navTarget.existingTabId) {
        const addrInput = document.getElementById(
          `address-input-${navTarget.existingTabId}`
        ) as HTMLInputElement | null;
        if (addrInput) {
          addrInput.value = navTarget.targetUrl;
        }
        await apiNavigateAndCaptureTab(
          navTarget.existingTabId,
          navTarget.targetUrl,
          2500
        );
      } else {
        const prevActiveTabId = state.activeTabId;
        const openedTab = await apiOpenTab(
          convId,
          navTarget.targetUrl,
          navTarget.label
        );
        state.activeDetail = await apiGetConversation(convId);
        state.activeTabId = prevActiveTabId;
        renderTabStripRegion();
        await apiNavigateAndCaptureTab(
          openedTab.id,
          navTarget.targetUrl,
          2600
        );
      }
      state.activeDetail = await apiGetConversation(convId);
      renderTabStripRegion();
    }

    // 2. Capture live rendered DOM + visible_text from all open WebView2 tabs right before querying models
    updateStreamingStatus("capturing live open tab DOM...", "capturing");
    await apiCaptureOpenTabs(convId);
    state.activeDetail = await apiGetConversation(convId);
    const activeTabSources = getActiveTabSources(state.activeDetail);

    if (state.selectedModel === "planck3 (web)") {
      updateStreamingStatus(
        "searching and weighing web sources via planck3...",
        "web_search"
      );
      const result = await sidecarRunAnswer(text, convId);
      stopStreamingProgress();
      const savedMsg = await apiAddMessage(
        convId,
        "assistant",
        `${result.answer}\n\nconfidence: ${result.band}`,
        state.selectedModel,
        JSON.stringify(result.sources.map((s) => s.url))
      );
      if (result.findings && result.findings.length > 0) {
        state.messageFindings[savedMsg.id] = result.findings;
      }
      state.activeDetail = await apiGetConversation(convId);
      if (state.activeDetail) {
        const msgObj = state.activeDetail.messages.find(
          (m) => m.id === savedMsg.id
        );
        if (msgObj) {
          msgObj.cited_sources = result.sources;
          if (state.messageFindings[savedMsg.id]) {
            msgObj.findings = state.messageFindings[savedMsg.id];
          }
        }
      }
      renderViewportRegion();
      return;
    }

    if (
      state.selectedModel === "hertz (reader)" ||
      state.selectedModel === "planck (reader)"
    ) {
      updateStreamingStatus(
        `reading ${activeTabSources.length} open tab source(s) with ${state.selectedModel}...`,
        "reading"
      );
      const res = await sidecarRunRead(
        state.selectedModel,
        text,
        activeTabSources.map((s) => ({
          id: s.sourceId,
          url: s.url,
          title: s.title,
        }))
      );
      stopStreamingProgress();
      await apiAddMessage(
        convId,
        "assistant",
        res.answer,
        state.selectedModel,
        JSON.stringify(res.source_ids)
      );
      state.activeDetail = await apiGetConversation(convId);
      renderViewportRegion();
      return;
    }

    // Default: gemma-4-e4b streaming over open tabs in context
    updateStreamingStatus(
      `sending ${activeTabSources.length} open tab source(s) to ${state.selectedModel}...`,
      "connecting"
    );

    const historyPayload = (state.activeDetail?.messages ?? []).map((m) => ({
      role: m.role,
      content: m.content,
    }));

    const convSummary = state.activeDetail?.conversation.summary ?? "";
    const isMailConv = state.activeDetail?.conversation.origin === "mail";
    const mailEnabled = Boolean(isMailConv || state.mailContextEnabled);
    const initialSources = activeTabSources.map((s) => ({
      id: s.sourceId,
      url: s.url,
      title: s.title,
      domain: s.domain,
      is_open_tab: true,
    }));
    if (isMailConv && initialSources.length === 0 && state.mailTriageSources.length > 0) {
      initialSources.push(...state.mailTriageSources);
    }

    const streamRes = await sidecarStreamChat(
      state.selectedModel,
      historyPayload,
      initialSources,
      state.webSearchEnabled,
      (delta) => {
        appendStreamingDelta(delta);
      },
      (status, phase) => {
        updateStreamingStatus(status, phase);
      },
      (errText) => {
        updateStreamingStatus(`error: ${errText}`, "error");
      },
      convSummary,
      (stats) => {
        for (const st of stats) {
          state.sourceStats[st.id] = st;
        }
      },
      mailEnabled
    );

    if (streamRes.source_stats) {
      for (const st of streamRes.source_stats) {
        state.sourceStats[st.id] = st;
      }
    }

    const finalContent =
      streamRes.annotated_text ||
      state.streamingText ||
      (streamRes.error ? `[err] ${streamRes.error}` : "(no response)");
    stopStreamingProgress();

    const savedMsg = await apiAddMessage(
      convId,
      "assistant",
      finalContent,
      state.selectedModel,
      JSON.stringify(streamRes.source_ids),
      typeof streamRes.citations_ok === "number" ? streamRes.citations_ok : null,
      typeof streamRes.citations_flagged === "number"
        ? streamRes.citations_flagged
        : null,
      streamRes.citation_check ? JSON.stringify(streamRes.citation_check) : null
    );
    if (streamRes.proposals && streamRes.proposals.length > 0) {
      state.messageProposals[savedMsg.id] = streamRes.proposals;
    }
    if (streamRes.findings && streamRes.findings.length > 0) {
      state.messageFindings[savedMsg.id] = streamRes.findings;
    }
    state.activeDetail = await apiGetConversation(convId);
    if (state.activeDetail) {
      const msgObj = state.activeDetail.messages.find(
        (m) => m.id === savedMsg.id
      );
      if (msgObj) {
        if (state.messageProposals[savedMsg.id]) {
          msgObj.proposals = state.messageProposals[savedMsg.id];
        }
        if (state.messageFindings[savedMsg.id]) {
          msgObj.findings = state.messageFindings[savedMsg.id];
        }
        if (streamRes.cited_sources && streamRes.cited_sources.length > 0) {
          msgObj.cited_sources = streamRes.cited_sources;
        }
      }
    }

    // Section 3.2 (M9): After every 6th assistant turn, write a rolling summary (max 600 chars) in background
    const allMessages = state.activeDetail?.messages ?? [];
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

    renderViewportRegion();
  } catch (err) {
    stopStreamingProgress();
    await apiAddMessage(
      convId,
      "assistant",
      `[err] ${String(err)}`,
      state.selectedModel,
      JSON.stringify([])
    );
    state.activeDetail = await apiGetConversation(convId);
    renderViewportRegion();
  }
}

async function openEmailMessageTab(
  messageId: string,
  subject: string
): Promise<void> {
  if (!state.activeDetail) return;
  void sidecarOpenMailMessage(messageId);
  const msgDetail = await sidecarGetMailMessage(messageId);
  if (msgDetail.ok) {
    state.mailMessageDetails[messageId] = msgDetail;
  }
  const tab = await apiOpenTab(
    state.activeDetail.conversation.id,
    `satzmail://message/${messageId}`,
    subject,
    "mail"
  );
  state.activeDetail = await apiGetConversation(
    state.activeDetail.conversation.id
  );
  state.activeTabId = tab.id;
  await refreshMailState();
  await refreshLists();
  renderAllRegions();
}

async function openComposeTab(seed?: {
  to?: string;
  cc?: string;
  subject?: string;
  body?: string;
  in_reply_to?: string;
  references?: string;
  reply_to_message_id?: string;
}): Promise<void> {
  if (!state.activeDetail) return;
  const title = seed?.subject || "compose";
  const tab = await apiOpenTab(
    state.activeDetail.conversation.id,
    "about:compose",
    title,
    "compose"
  );
  state.mailComposeDrafts[tab.id] = {
    account_id: state.mailAccounts[0]?.id ?? "",
    to: seed?.to ?? "",
    cc: seed?.cc ?? "",
    bcc: "",
    subject: seed?.subject ?? "",
    body: seed?.body ?? "",
    in_reply_to: seed?.in_reply_to ?? "",
    references: seed?.references ?? "",
    reply_to_message_id: seed?.reply_to_message_id ?? "",
  };
  state.activeDetail = await apiGetConversation(
    state.activeDetail.conversation.id
  );
  state.activeTabId = tab.id;
  await refreshLists();
  renderAllRegions();
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

  viewport.querySelectorAll("[data-email-move]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const el = btn as HTMLElement;
      const targetLabel = el.getAttribute("data-target-label") as
        | "email"
        | "ping"
        | "information"
        | "promotion"
        | null;
      if (!targetLabel) return;
      await sidecarLabelMailMessage(messageId, targetLabel);
      const updated = await sidecarGetMailMessage(messageId);
      if (updated.ok) {
        state.mailMessageDetails[messageId] = updated;
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
      const updated = await sidecarGetMailMessage(messageId);
      if (updated.ok) {
        state.mailMessageDetails[messageId] = updated;
      }
      if (state.activeTabId) {
        void apiControlTab(state.activeTabId, "reload");
      }
      renderViewportRegion();
    });
  });

  viewport.querySelectorAll("[data-email-save-att]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const el = btn as HTMLElement;
      const partId = el.getAttribute("data-part-id") || "";
      const res = await sidecarSaveMailAttachment(messageId, partId);
      if (res.ok) {
        el.textContent = "[saved to Downloads]";
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

if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", () => {
    void initApp();
  });
} else {
  void initApp();
}
