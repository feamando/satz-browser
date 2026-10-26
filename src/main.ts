import { listen } from "@tauri-apps/api/event";
import {
  apiAddBookmark,
  apiAddMessage,
  apiArchiveConversation,
  apiCaptureOpenTabs,
  apiCloseTab,
  apiControlTab,
  apiCreateConversation,
  apiDeleteConversation,
  apiGetConversation,
  apiListBookmarks,
  apiListConversations,
  apiNavigateTab,
  apiOpenTab,
  apiPinConversation,
  apiRemoveBookmark,
  apiRenameConversation,
  sidecarDeleteBrainEntity,
  sidecarDeletePassage,
  sidecarFetchDigest,
  sidecarFetchHealth,
  sidecarFetchKnowledge,
  sidecarRunAnswer,
  sidecarRunRead,
  sidecarSetPauseLearning,
  sidecarStreamChat,
} from "./api";
import { appendStreamingDelta, renderChatPanel } from "./chat";
import { bindKeyboardShortcuts } from "./keys";
import { renderKnowledgeView } from "./knowledge";
import { renderRail } from "./rail";
import { renderStartScreen } from "./start";
import {
  classifyStartInput,
  escapeHtml,
  extractDomain,
  getActiveTabSources,
  MOD_LABEL,
  normalizeUrl,
  state,
} from "./state";
import { renderStatusLine } from "./status";
import { renderTabStrip, scheduleWebviewLayoutSync } from "./tabs";
import type { LocalModelId, TabPageEvent } from "./types";

let resizeObserver: ResizeObserver | null = null;

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
  }
}

async function pollSidecarState(): Promise<void> {
  state.sidecar = await sidecarFetchHealth();
  if (state.sidecar.online && !state.activeDetail && state.digestItems.length === 0) {
    state.digestItems = await sidecarFetchDigest();
    if (!state.activeDetail && !state.showKnowledgeView) {
      renderViewportRegion();
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
          <button id="toggle-agent-rail-btn" class="${state.agentRailOpen ? "active" : ""}">
            [chat rail ${MOD_LABEL}+j]
          </button>
        </div>
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
    if (detail.conversation.origin === "direct" && openTabs.length > 0) {
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
  await apiAddBookmark(title || extractDomain(url), url);
  await refreshLists();
  renderRailRegion();
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
  if (!historicalSource) return;

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
  if (!state.activeDetail) return;
  const convId = state.activeDetail.conversation.id;

  await apiAddMessage(convId, "user", text, null, null);
  state.activeDetail = await apiGetConversation(convId);
  renderViewportRegion();

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

  // Capture live rendered DOM + visible_text from all open WebView2 tabs right before querying models
  await apiCaptureOpenTabs(convId);
  state.activeDetail = await apiGetConversation(convId);
  const activeTabSources = getActiveTabSources(state.activeDetail);

  try {
    if (state.selectedModel === "planck3 (web)") {
      state.isStreaming = true;
      state.streamingText = "searching and weighing sources...";
      renderViewportRegion();
      const result = await sidecarRunAnswer(text, convId);
      state.isStreaming = false;
      state.streamingText = "";
      const savedMsg = await apiAddMessage(
        convId,
        "assistant",
        `${result.answer}\n\nconfidence: ${result.band}`,
        state.selectedModel,
        JSON.stringify(result.sources.map((s) => s.url))
      );
      state.activeDetail = await apiGetConversation(convId);
      if (state.activeDetail) {
        const msgObj = state.activeDetail.messages.find(
          (m) => m.id === savedMsg.id
        );
        if (msgObj) {
          msgObj.cited_sources = result.sources;
        }
      }
      renderViewportRegion();
      return;
    }

    if (
      state.selectedModel === "hertz (reader)" ||
      state.selectedModel === "planck (reader)"
    ) {
      const res = await sidecarRunRead(
        state.selectedModel,
        text,
        activeTabSources.map((s) => ({
          id: s.sourceId,
          url: s.url,
          title: s.title,
        }))
      );
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
    state.isStreaming = true;
    state.streamingText = "";
    renderViewportRegion();

    const historyPayload = (state.activeDetail?.messages ?? []).map((m) => ({
      role: m.role,
      content: m.content,
    }));

    const streamRes = await sidecarStreamChat(
      state.selectedModel,
      historyPayload,
      activeTabSources.map((s) => ({
        id: s.sourceId,
        url: s.url,
        title: s.title,
        domain: s.domain,
        is_open_tab: true,
      })),
      state.webSearchEnabled,
      (delta) => {
        appendStreamingDelta(delta);
      }
    );

    const finalContent = state.streamingText || "(no response)";
    state.isStreaming = false;
    state.streamingText = "";

    await apiAddMessage(
      convId,
      "assistant",
      finalContent,
      state.selectedModel,
      JSON.stringify(streamRes.source_ids)
    );
    state.activeDetail = await apiGetConversation(convId);
    renderViewportRegion();
  } catch (err) {
    state.isStreaming = false;
    state.streamingText = "";
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

if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", () => {
    void initApp();
  });
} else {
  void initApp();
}
