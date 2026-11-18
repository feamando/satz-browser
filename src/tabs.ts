import { apiSyncTabWebviews } from "./api";
import { icon } from "./design-system/icons";
import { isModKey } from "./keys";
import { escapeHtml, extractDomain, MOD_LABEL, state } from "./state";
import type { TabBoundsSpec } from "./types";

export interface TopBarActions {
  onNavTab: (tabId: string, action: "back" | "forward" | "reload") => void;
  onNavigateAddress: (tabId: string, url: string) => void;
  onWatchTab: (tabId: string) => void;
  onAutofillTab: (tabId: string) => void;
  onToggleCodesPopover: (tabId: string) => void;
  onRunComparer: () => void;
  onExitCompare: () => void;
  onToggleCompareMode: () => void;
  onToggleAgentRail: () => void;
  onNewTab: () => void;
  onOpenCommandBar: () => void;
}

export interface TabStripActions {
  onSelectTab: (tabId: string) => void;
  onSelectMailAccount?: (accountId: string | null) => void;
  onAddMailAccount?: () => void;
  onToggleCompareCandidate: (tabId: string) => void;
  onNewTab: () => void;
  onCloseTab: (tabId: string) => void;
  onToggleCompareMode: () => void;
}

export function renderTopBar(actions: TopBarActions): void {
  const container = document.getElementById("region-top");
  if (!container) return;

  const detail = state.activeDetail;
  if (!detail || state.showKnowledgeView || state.showBrainView) {
    container.classList.add("hidden");
    container.innerHTML = "";
    return;
  }

  container.classList.remove("hidden");

  const openTabs = detail.tabs.filter((t) => t.is_open);
  const isMailConv = detail.conversation.origin === "mail";
  const isNewsConv = detail.conversation.origin === "news";
  const isCompare = state.compareMode && state.compareTabIds.length >= 2;
  const activeTab = !isCompare
    ? openTabs.find((t) => t.id === state.activeTabId)
    : undefined;
  const isMailMsgTab = Boolean(
    activeTab && (activeTab.kind === "mail" || activeTab.url.startsWith("satzmail://"))
  );
  const isComposeTab = activeTab?.kind === "compose";
  const isSiteTab = Boolean(activeTab && !isMailMsgTab && !isComposeTab);
  const isChatTab = !isCompare && state.activeTabId === "chat";
  const tabsVisible = isMailConv || isNewsConv || openTabs.length > 0;
  const supportsAgent = isCompare || isChatTab || isSiteTab || isMailMsgTab;

  const siteTab = isSiteTab ? activeTab! : null;
  const tabDomain = siteTab ? extractDomain(siteTab.url) : "";
  const promoCacheKey = siteTab ? `${siteTab.id}:${tabDomain}` : "";
  const activePromoCodes = siteTab
    ? (state.siteTabPromoCodes[promoCacheKey] ??
        state.siteTabPromoCodes[siteTab.id] ??
        [])
    : [];
  const showCodesPopover = Boolean(
    siteTab &&
      state.openCodesPopoverTabId === siteTab.id &&
      activePromoCodes.length > 0
  );

  const navHtml = siteTab
    ? `
      <div class="top-nav">
        <button class="icon-btn" type="button" data-nav-btn="back" data-tab="${escapeHtml(siteTab.id)}" title="Back">${icon("back")}</button>
        <button class="icon-btn" type="button" data-nav-btn="forward" data-tab="${escapeHtml(siteTab.id)}" title="Forward">${icon("fwd")}</button>
        <button class="icon-btn" type="button" data-nav-btn="reload" data-tab="${escapeHtml(siteTab.id)}" title="Reload">${icon("reload")}</button>
      </div>
    `
    : `
      <div class="top-nav">
        <button class="icon-btn" type="button" disabled title="Back">${icon("back")}</button>
        <button class="icon-btn" type="button" disabled title="Forward">${icon("fwd")}</button>
        <button class="icon-btn" type="button" disabled title="Reload">${icon("reload")}</button>
      </div>
    `;

  let centerHtml = "";
  if (siteTab) {
    const isSecure = siteTab.url.startsWith("https://");
    const addrIcon = isSecure ? icon("lock", "ico-sm") : icon("globe", "ico-sm");
    const displayVal = siteTab.url === "about:blank" ? "" : siteTab.url;
    centerHtml = `
      <div class="addr">
        ${addrIcon}
        <input
          id="address-input-${escapeHtml(siteTab.id)}"
          class="address-input"
          data-address-tab="${escapeHtml(siteTab.id)}"
          type="text"
          spellcheck="false"
          autocorrect="off"
          autocapitalize="off"
          placeholder="Enter URL or search query..."
          value="${escapeHtml(displayVal)}"
        />
        ${
          activePromoCodes.length > 0
            ? `
              <div class="codes-pop-anchor">
                <button
                  type="button"
                  data-codes-pill-tab="${escapeHtml(siteTab.id)}"
                  class="pill accent ${showCodesPopover ? "active" : ""}"
                  title="Active promo codes from mail for ${escapeHtml(tabDomain)}"
                >
                  ${activePromoCodes.length} promo${activePromoCodes.length === 1 ? "" : "s"}
                </button>
                ${
                  showCodesPopover
                    ? `
                      <div class="menu codes-pop-menu">
                        ${activePromoCodes
                          .map((c) => {
                            const codeStr = String(c.code ?? "");
                            const valStr = String(c.discount_value ?? "");
                            const expStr = String(c.expiry ?? "");
                            return `
                              <button class="menu-item" type="button" data-copy-promo-code="${escapeHtml(codeStr)}">
                                <strong>${escapeHtml(codeStr)}</strong>
                                <span class="muted">${valStr ? escapeHtml(valStr) : ""}${expStr ? ` · exp ${escapeHtml(expStr)}` : ""}</span>
                              </button>
                            `;
                          })
                          .join("")}
                      </div>
                    `
                    : ""
                }
              </div>
            `
            : ""
        }
      </div>
    `;
  } else if (isCompare) {
    centerHtml = `
      <div class="addr">
        ${icon("compare", "ico-sm")}
        <span class="addr-static truncate">Compare · ${Math.min(4, state.compareTabIds.length)} panes</span>
      </div>
    `;
  } else if (isComposeTab) {
    centerHtml = `
      <div class="addr">
        ${icon("compose", "ico-sm")}
        <span class="addr-static truncate">Compose message</span>
      </div>
    `;
  } else if (isMailMsgTab && activeTab) {
    centerHtml = `
      <div class="addr">
        ${icon("mail", "ico-sm")}
        <span class="addr-static truncate">${escapeHtml(activeTab.title || "Email message")}</span>
      </div>
    `;
  } else {
    const promptHint = isMailConv
      ? "Search or ask over Mail"
      : isNewsConv
        ? "Search or explore News"
        : detail.conversation.title || "Search or enter URL";
    centerHtml = `
      <div class="addr">
        <button id="top-cmd-addr-btn" class="addr-trigger" type="button" title="Command Bar (${MOD_LABEL}+K)">
          ${icon("search", "ico-sm")}
          <span class="truncate">${escapeHtml(promptHint)}</span>
          <span class="kbd">${escapeHtml(MOD_LABEL.toUpperCase())}+K</span>
        </button>
      </div>
    `;
  }

  const actionsHtml = `
    <div class="top-actions">
      ${
        !tabsVisible
          ? `<button id="tab-strip-add-btn" class="icon-btn" type="button" title="New tab (${MOD_LABEL}+T)">${icon("plus")}</button>`
          : ""
      }
      ${
        siteTab && state.tabCanFillLogin[siteTab.id]
          ? `<button class="btn" type="button" data-autofill-tab="${escapeHtml(siteTab.id)}" title="Fill login credentials (${MOD_LABEL}+Shift+L)">${icon("lock", "ico-sm")}<span>Fill login</span></button>`
          : ""
      }
      ${
        siteTab
          ? `<button class="icon-btn" type="button" data-watch-tab="${escapeHtml(siteTab.id)}" title="Watch this page for changes">${icon("watch")}</button>`
          : ""
      }
      ${
        isCompare
          ? `
            <button id="compare-run-comparer-btn" class="btn primary" type="button" title="Run Comparer agent across compared tiles">${icon("compare", "ico-sm")}<span>Compare these</span></button>
            <button id="compare-exit-btn" class="btn" type="button">Exit</button>
          `
          : openTabs.length >= 2
            ? `
              <button
                id="tab-strip-compare-btn"
                class="btn ${state.compareTabIds.length >= 2 ? "active" : ""}"
                type="button"
                title="Select 2-4 tabs with ${MOD_LABEL}+click then press ${MOD_LABEL}+M"
              >
                ${icon("compare", "ico-sm")}
                <span>${state.compareTabIds.length >= 2 ? `Compare (${state.compareTabIds.length})` : "Compare"}</span>
              </button>
            `
            : ""
      }
      ${
        supportsAgent
          ? `
            <button
              id="toggle-agent-rail-btn"
              class="icon-btn ${state.agentRailOpen ? "active" : ""}"
              type="button"
              title="Toggle assistant panel (${MOD_LABEL}+J)"
            >
              ${icon("panel")}
            </button>
          `
          : ""
      }
    </div>
  `;

  container.innerHTML = `${navHtml}${centerHtml}${actionsHtml}`;

  container.querySelectorAll("[data-nav-btn]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const action = el.getAttribute("data-nav-btn") as "back" | "forward" | "reload" | null;
      const tabId = el.getAttribute("data-tab");
      if (action && tabId) actions.onNavTab(tabId, action);
    });
  });

  const addrInput = container.querySelector("[data-address-tab]") as HTMLInputElement | null;
  addrInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const tabId = addrInput.getAttribute("data-address-tab");
      if (tabId) actions.onNavigateAddress(tabId, addrInput.value);
    }
  });

  container.querySelector("#top-cmd-addr-btn")?.addEventListener("click", () => {
    actions.onOpenCommandBar();
  });

  if (!tabsVisible) {
    container.querySelector("#tab-strip-add-btn")?.addEventListener("click", () => {
      actions.onNewTab();
    });
  }

  container.querySelectorAll("[data-autofill-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tabId = (btn as HTMLElement).getAttribute("data-autofill-tab");
      if (tabId) actions.onAutofillTab(tabId);
    });
  });

  container.querySelectorAll("[data-watch-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tabId = (btn as HTMLElement).getAttribute("data-watch-tab");
      if (tabId) {
        actions.onWatchTab(tabId);
        (btn as HTMLElement).classList.add("active");
      }
    });
  });

  container.querySelectorAll("[data-codes-pill-tab]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const tabId = (btn as HTMLElement).getAttribute("data-codes-pill-tab");
      if (tabId) actions.onToggleCodesPopover(tabId);
    });
  });

  container.querySelectorAll("[data-copy-promo-code]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const code = el.getAttribute("data-copy-promo-code") || "";
      if (code && navigator.clipboard) {
        void navigator.clipboard.writeText(code);
        el.innerHTML = `<strong>${escapeHtml(code)}</strong> <span class="muted">Copied</span>`;
      }
    });
  });

  container.querySelector("#tab-strip-compare-btn")?.addEventListener("click", () => {
    actions.onToggleCompareMode();
  });

  container.querySelector("#compare-run-comparer-btn")?.addEventListener("click", () => {
    actions.onRunComparer();
  });

  container.querySelector("#compare-exit-btn")?.addEventListener("click", () => {
    actions.onExitCompare();
  });

  container.querySelector("#toggle-agent-rail-btn")?.addEventListener("click", () => {
    actions.onToggleAgentRail();
  });
}

export function renderTabStrip(actions: TabStripActions): void {
  const container = document.getElementById("region-tab-strip");
  if (!container) return;

  const detail = state.activeDetail;
  if (!detail || state.showKnowledgeView || state.showBrainView) {
    container.classList.add("hidden");
    container.innerHTML = "";
    return;
  }

  const openTabs = detail.tabs.filter((t) => t.is_open);
  const isMailConv = detail.conversation.origin === "mail";
  const isNewsConv = detail.conversation.origin === "news";

  if (!isMailConv && !isNewsConv && openTabs.length === 0) {
    container.classList.add("hidden");
    container.innerHTML = "";
    return;
  }

  container.classList.remove("hidden");

  const isChatActive = state.activeTabId === "chat" && !state.compareMode;
  const counts = state.mailCounts;
  const totalUnreadAll =
    state.mailAccounts.length > 0
      ? state.mailAccounts.reduce((acc, a) => acc + (a.inbox_unread ?? 0), 0) ||
        counts.inbox_unread
      : counts.inbox_unread;

  const mailAccountTabsHtml =
    isMailConv && state.mailAccounts.length > 0
      ? `
        <span class="tabs-sep"></span>
        <button
          type="button"
          class="tab ${state.mailActiveAccountId === null ? "active" : ""}"
          data-mail-acct-tab="all"
          title="Common unified view across all configured email accounts"
        >
          <span>All mail</span>
          ${totalUnreadAll > 0 ? `<span class="count">${totalUnreadAll}</span>` : ""}
        </button>
        ${state.mailAccounts
          .map((acct) => {
            const isAcctSelected = state.mailActiveAccountId === acct.id;
            const acctName = acct.email || acct.label;
            const acctUnread = acct.inbox_unread ?? 0;
            return `
              <button
                type="button"
                class="tab ${isAcctSelected ? "active" : ""}"
                data-mail-acct-tab="${escapeHtml(acct.id)}"
                title="Filter mail lanes to ${escapeHtml(acctName)}"
              >
                <span class="truncate">${escapeHtml(acctName)}</span>
                ${acctUnread > 0 ? `<span class="count">${acctUnread}</span>` : ""}
              </button>
            `;
          })
          .join("")}
        <button id="tab-strip-add-mail-acct-btn" class="icon-btn" type="button" title="Add email account in Settings">${icon("plus", "ico-sm")}</button>
        <span class="tabs-sep"></span>
      `
      : "";

  const mailLaneTabsHtml = isMailConv
    ? `
      ${mailAccountTabsHtml}
      <button type="button" class="tab ${!state.compareMode && state.activeTabId === "lane:inbox" ? "active" : ""}" data-lane-tab="inbox">
        <span>Inbox</span>
        ${counts.inbox_unread > 0 ? `<span class="count">${counts.inbox_unread}</span>` : ""}
      </button>
      <button type="button" class="tab ${!state.compareMode && state.activeTabId === "lane:pings" ? "active" : ""}" data-lane-tab="pings">
        <span>Pings</span>
        ${counts.pings > 0 ? `<span class="count">${counts.pings}</span>` : ""}
      </button>
      <button type="button" class="tab ${!state.compareMode && state.activeTabId === "lane:orders" ? "active" : ""}" data-lane-tab="orders">
        <span>Orders</span>
        ${counts.orders > 0 ? `<span class="count">${counts.orders}</span>` : ""}
      </button>
      <button type="button" class="tab ${!state.compareMode && state.activeTabId === "lane:promos" ? "active" : ""}" data-lane-tab="promos">
        <span>Promos</span>
        ${counts.promos > 0 ? `<span class="count">${counts.promos}</span>` : ""}
      </button>
    `
    : "";

  const newsClusterCount = state.newsStories.length || state.sidecar.news?.clusters || 0;
  const newsTopicCount = state.newsTopics.length || state.sidecar.news?.topics || 0;
  const newsLaneTabsHtml = isNewsConv
    ? `
      <button type="button" class="tab ${!state.compareMode && state.activeTabId === "news-lane:stories" ? "active" : ""}" data-news-lane-tab="stories" title="Clustered stories ranked by source family independence &amp; recency">
        <span>Top stories</span>
        ${newsClusterCount > 0 ? `<span class="count">${newsClusterCount}</span>` : ""}
      </button>
      <button type="button" class="tab ${!state.compareMode && state.activeTabId === "news-lane:foryou" ? "active" : ""}" data-news-lane-tab="foryou" title="Personalized from your Brain &amp; Mail topics (local PII-scrubbed) + 25% trusted explore">
        <span>For you</span>
      </button>
      <button type="button" class="tab ${!state.compareMode && state.activeTabId === "news-lane:perspectives" ? "active" : ""}" data-news-lane-tab="perspectives" title="Side-by-side conflicting source families &amp; blind spots">
        <span>Perspectives</span>
      </button>
      <button type="button" class="tab ${!state.compareMode && state.activeTabId === "news-lane:topics" ? "active" : ""}" data-news-lane-tab="topics" title="Tracked news beats and story watches">
        <span>Topics</span>
        ${newsTopicCount > 0 ? `<span class="count">${newsTopicCount}</span>` : ""}
      </button>
      <button type="button" class="tab ${!state.compareMode && state.activeTabId === "news-lane:sources" ? "active" : ""}" data-news-lane-tab="sources" title="Hand-scored sources, RSS feeds &amp; trust sliders">
        <span>Sources</span>
      </button>
    `
    : "";

  container.innerHTML = `
    <button type="button" class="tab ${isChatActive ? "active" : ""}" data-tab-id="chat">
      ${icon("chat", "ico-sm")}
      <span>Chat</span>
    </button>
    ${mailLaneTabsHtml}
    ${newsLaneTabsHtml}
    ${openTabs
      .map((tab, idx) => {
        const isActive = !state.compareMode && state.activeTabId === tab.id;
        const isSelectedForCompare = state.compareTabIds.includes(tab.id);
        const domain =
          tab.kind === "mail"
            ? "Mail"
            : tab.kind === "compose"
              ? "Compose"
              : extractDomain(tab.url);
        const leadIcon =
          tab.kind === "mail"
            ? icon("mail", "ico-sm")
            : tab.kind === "compose"
              ? icon("compose", "ico-sm")
              : icon("globe", "ico-sm");
        const label = tab.title || domain;
        return `
          <div
            class="tab ${isActive ? "active" : ""} ${isSelectedForCompare ? "selected-compare" : ""}"
            data-site-tab-id="${escapeHtml(tab.id)}"
            title="Source [${idx + 1}] · ${escapeHtml(tab.title || tab.url)}"
          >
            ${leadIcon}
            <span class="truncate">${escapeHtml(label)}</span>
            <button class="tab-close-btn" type="button" data-close-tab-id="${escapeHtml(tab.id)}" title="Close tab">${icon("x", "ico-sm")}</button>
          </div>
        `;
      })
      .join("")}
    <button id="tab-strip-add-btn" class="icon-btn" type="button" title="New tab (${MOD_LABEL}+T)">${icon("plus", "ico-sm")}</button>
  `;

  container.querySelector('[data-tab-id="chat"]')?.addEventListener("click", () => {
    actions.onSelectTab("chat");
  });

  container.querySelectorAll("[data-lane-tab]").forEach((el) => {
    el.addEventListener("click", () => {
      const lane = (el as HTMLElement).getAttribute("data-lane-tab");
      if (lane) {
        actions.onSelectTab(`lane:${lane}`);
      }
    });
  });

  container.querySelectorAll("[data-news-lane-tab]").forEach((el) => {
    el.addEventListener("click", () => {
      const lane = (el as HTMLElement).getAttribute("data-news-lane-tab");
      if (lane) {
        actions.onSelectTab(`news-lane:${lane}`);
      }
    });
  });

  container.querySelectorAll("[data-mail-acct-tab]").forEach((el) => {
    el.addEventListener("click", () => {
      const acctVal = (el as HTMLElement).getAttribute("data-mail-acct-tab") ?? "all";
      if (actions.onSelectMailAccount) {
        actions.onSelectMailAccount(acctVal === "all" ? null : acctVal);
      }
    });
  });

  container
    .querySelector("#tab-strip-add-mail-acct-btn")
    ?.addEventListener("click", () => {
      actions.onAddMailAccount?.();
    });

  container.querySelectorAll("[data-site-tab-id]").forEach((el) => {
    el.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      if (target.closest("[data-close-tab-id]")) return;
      const tabId = (el as HTMLElement).getAttribute("data-site-tab-id");
      if (!tabId) return;
      if (isModKey(e as MouseEvent)) {
        actions.onToggleCompareCandidate(tabId);
      } else {
        actions.onSelectTab(tabId);
      }
    });
  });

  container.querySelectorAll("[data-close-tab-id]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const tabId = (btn as HTMLElement).getAttribute("data-close-tab-id");
      if (tabId) actions.onCloseTab(tabId);
    });
  });

  container
    .querySelector("#tab-strip-add-btn")
    ?.addEventListener("click", () => {
      actions.onNewTab();
    });
}

let syncTimeout: number | null = null;

export function scheduleWebviewLayoutSync(): void {
  if (syncTimeout !== null) {
    window.clearTimeout(syncTimeout);
  }
  syncTimeout = window.setTimeout(() => {
    void syncWebviewsNow();
  }, 25);
}

export async function syncWebviewsNow(): Promise<void> {
  const detail = state.activeDetail;
  if (
    !detail ||
    state.showKnowledgeView ||
    state.showBrainView ||
    state.commandBarOpen ||
    state.profilePromptOpen ||
    (!state.compareMode &&
      (state.activeTabId === "chat" || state.activeTabId.startsWith("lane:")))
  ) {
    await apiSyncTabWebviews([]);
    return;
  }

  const visible: TabBoundsSpec[] = [];
  const viewportH = Math.max(0, Math.round(window.innerHeight));
  const tabStripRect = document
    .getElementById("region-tab-strip")
    ?.getBoundingClientRect();
  const minStripBottom = tabStripRect ? Math.ceil(tabStripRect.bottom) : 34;

  const measureSlotBounds = (tabId: string, url: string, slot: HTMLElement): TabBoundsSpec => {
    const rect = slot.getBoundingClientRect();
    const parentEl = slot.parentElement;
    const toolbarEl =
      parentEl?.querySelector(".site-tab-toolbar") ??
      parentEl?.querySelector(".email-tab-header");
    const toolbarRect = toolbarEl?.getBoundingClientRect();
    const toolbarBottom = Math.max(
      minStripBottom,
      toolbarRect ? Math.ceil(toolbarRect.bottom) : minStripBottom
    );
    const clampedTop = Math.max(Math.round(rect.top), toolbarBottom);
    const clampedHeight = Math.max(0, Math.round(rect.bottom) - clampedTop);
    return {
      tab_id: tabId,
      url,
      x: Math.round(rect.left),
      y: clampedTop,
      w: Math.max(0, Math.round(rect.width)),
      h: clampedHeight,
      toolbar_bottom: toolbarBottom,
      viewport_h: viewportH,
    };
  };

  if (state.compareMode) {
    for (const tabId of state.compareTabIds.slice(0, 4)) {
      const tab = detail.tabs.find((t) => t.id === tabId && t.is_open);
      const slot = document.getElementById(`webview-slot-${tabId}`);
      if (
        tab &&
        tab.kind !== "compose" &&
        tab.kind !== "mail" &&
        !tab.url.startsWith("satzmail://") &&
        slot
      ) {
        visible.push(measureSlotBounds(tab.id, tab.url, slot));
      }
    }
  } else {
    const tab = detail.tabs.find(
      (t) => t.id === state.activeTabId && t.is_open
    );
    const slot = document.getElementById(`webview-slot-${state.activeTabId}`);
    if (
      tab &&
      tab.kind !== "compose" &&
      tab.kind !== "mail" &&
      !tab.url.startsWith("satzmail://") &&
      slot
    ) {
      visible.push(measureSlotBounds(tab.id, tab.url, slot));
    }
  }

  await apiSyncTabWebviews(visible);
}
