import { apiSyncTabWebviews } from "./api";
import { icon } from "./design-system/icons";
import { bindFaviconFallbacks, renderSiteFaviconHtml } from "./favicon";
import { t, tCount } from "./i18n";
import { isModKey } from "./keys";
import { escapeHtml, extractDomain, MOD_LABEL, state } from "./state";
import type { TabBoundsSpec } from "./types";

export interface TopBarActions {
  onNavTab: (tabId: string, action: "back" | "forward" | "reload") => void;
  onNavigateAddress: (tabId: string, url: string) => void;
  onTranslateTab?: (tabId: string, force?: boolean) => void;
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
  onToggleCompareCandidate: (tabId: string) => void;
  onNewTab: () => void;
  onCloseTab: (tabId: string) => void;
  onToggleCompareMode: () => void;
  onOpenNewsSettings?: (targetTab?: string) => void;
  onOpenNewsHome?: () => void;
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
  const isDrivesConv = detail.conversation.origin === "drives";
  const isSettingsConv = detail.conversation.origin === "settings";
  const isNewsSettingsConv = detail.conversation.origin === "news_settings";
  const isAnySettingsConv = isSettingsConv || isNewsSettingsConv;
  const isCompare = state.compareMode && state.compareTabIds.length >= 2;
  const activeTab = !isCompare
    ? openTabs.find((t) => t.id === state.activeTabId)
    : undefined;
  const isMailMsgTab = Boolean(
    activeTab && (activeTab.kind === "mail" || activeTab.url.startsWith("satzmail://"))
  );
  const isComposeTab = activeTab?.kind === "compose";
  const isSiteTab = Boolean(activeTab && !isMailMsgTab && !isComposeTab);
  const siteTab = isSiteTab ? activeTab! : null;
  const isChatTab = !isCompare && state.activeTabId === "chat";
  const tabsVisible =
    isMailConv ||
    isNewsConv ||
    isDrivesConv ||
    isAnySettingsConv ||
    openTabs.length > 0;
  const supportsAgent =
    !isAnySettingsConv && (isCompare || isChatTab || isSiteTab || isMailMsgTab);
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
        <button class="icon-btn" type="button" data-nav-btn="back" data-tab="${escapeHtml(siteTab.id)}" title="${escapeHtml(t("top.back"))}">${icon("back")}</button>
        <button class="icon-btn" type="button" data-nav-btn="forward" data-tab="${escapeHtml(siteTab.id)}" title="${escapeHtml(t("top.forward"))}">${icon("fwd")}</button>
        <button class="icon-btn" type="button" data-nav-btn="reload" data-tab="${escapeHtml(siteTab.id)}" title="${escapeHtml(t("top.reload"))}">${icon("reload")}</button>
      </div>
    `
    : `
      <div class="top-nav">
        <button class="icon-btn" type="button" disabled title="${escapeHtml(t("top.back"))}">${icon("back")}</button>
        <button class="icon-btn" type="button" disabled title="${escapeHtml(t("top.forward"))}">${icon("fwd")}</button>
        <button class="icon-btn" type="button" disabled title="${escapeHtml(t("top.reload"))}">${icon("reload")}</button>
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
          placeholder="${escapeHtml(t("top.addr_placeholder"))}"
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
                  title="${escapeHtml(t("top.promo_title", { domain: tabDomain }))}"
                >
                  ${escapeHtml(tCount("top.promo_count", activePromoCodes.length))}
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
                                <span class="muted">${valStr ? escapeHtml(valStr) : ""}${expStr ? ` · ${escapeHtml(t("top.promo_exp", { expiry: expStr }))}` : ""}</span>
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
        <span class="addr-static truncate">${escapeHtml(t("top.compare_panes", { count: Math.min(4, state.compareTabIds.length) }))}</span>
      </div>
    `;
  } else if (isComposeTab) {
    centerHtml = `
      <div class="addr">
        ${icon("compose", "ico-sm")}
        <span class="addr-static truncate">${escapeHtml(t("top.compose_message"))}</span>
      </div>
    `;
  } else if (isMailMsgTab && activeTab) {
    centerHtml = `
      <div class="addr">
        ${icon("mail", "ico-sm")}
        <span class="addr-static truncate">${escapeHtml(activeTab.title || t("top.email_message"))}</span>
      </div>
    `;
  } else if (isMailConv) {
    const activeAcct = state.mailAccounts.find(
      (a) => a.id === state.mailActiveAccountId
    );
    const scopeLabel = activeAcct
      ? activeAcct.label || activeAcct.email
      : t("rail.all_mail");
    const laneKeyMap: Record<string, string> = {
      inbox: t("top.mail_inbox"),
      pings: t("top.mail_pings"),
      orders: t("top.mail_orders"),
      promos: t("top.mail_promos"),
    };
    const laneLabel = state.activeTabId.startsWith("lane:")
      ? ` · ${laneKeyMap[state.activeTabId.slice(5)] ?? state.activeTabId.slice(5)}`
      : state.activeTabId === "chat"
        ? ` · ${t("common.chat")}`
        : "";
    centerHtml = `
      <div class="addr addr-static-box">
        ${icon("mail", "ico-sm")}
        <span class="addr-static truncate">${escapeHtml(t("common.mail"))} · ${escapeHtml(scopeLabel)}${escapeHtml(laneLabel)}</span>
      </div>
    `;
  } else if (isSettingsConv || isNewsSettingsConv) {
    const prof = state.knowledge.profile;
    const isUnlocked = Boolean(prof?.unlocked && prof?.active_profile);
    const labelText = isNewsSettingsConv
      ? isUnlocked
        ? t("top.news_settings_chat", { name: prof?.active_profile?.name || "profile" })
        : t("top.news_settings_locked")
      : isUnlocked
        ? t("top.settings_unlocked", { name: prof?.active_profile?.name || "profile" })
        : t("top.settings_locked");
    centerHtml = `
      <div class="addr addr-static-box">
        ${icon("settings", "ico-sm")}
        <span class="addr-static truncate">${escapeHtml(labelText)}</span>
      </div>
    `;
  } else {
    const promptHint = isNewsConv
      ? t("top.search_explore_news")
      : isDrivesConv
        ? t("top.search_explore_drives")
        : detail.conversation.title || t("top.search_or_url");
    centerHtml = `
      <div class="addr">
        <button id="top-cmd-addr-btn" class="addr-trigger" type="button" title="${escapeHtml(t("rail.cmd_title", { mod: MOD_LABEL }))}">
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
          ? `<button id="tab-strip-add-btn" class="icon-btn" type="button" title="${escapeHtml(t("top.new_tab_title", { mod: MOD_LABEL }))}">${icon("plus")}</button>`
          : ""
      }
      ${
        siteTab && state.tabCanFillLogin[siteTab.id]
          ? `<button class="btn" type="button" data-autofill-tab="${escapeHtml(siteTab.id)}" title="${escapeHtml(t("top.fill_login_title", { mod: MOD_LABEL }))}">${icon("lock", "ico-sm")}<span>${escapeHtml(t("top.fill_login"))}</span></button>`
          : ""
      }
      ${
        siteTab
          ? (() => {
              const tr = state.tabTranslationState[siteTab.id];
              const primaryLang = state.contentTranslationConfig?.primary_language || "en";
              if (tr?.status === "translating") {
                const lbl =
                  tr.blocksTotal && tr.blocksTotal > 0
                    ? t("top.translating_progress", {
                        done: tr.blocksDone ?? 0,
                        total: tr.blocksTotal,
                      })
                    : t("top.translating_page");
                return `<button class="btn active" type="button" data-translate-tab="${escapeHtml(siteTab.id)}" disabled title="${escapeHtml(t("top.translate_title", { lang: primaryLang }))}">${icon("translate", "ico-sm")}<span>${escapeHtml(lbl)}</span></button>`;
              }
              if (tr?.status === "translated") {
                const showingTr = tr.showingTranslated !== false;
                const src = tr.sourceLang || "?";
                const tgt = tr.targetLang || primaryLang;
                const lbl = showingTr
                  ? t("top.translated_badge", { src, tgt })
                  : t("top.show_translated_badge", { src, tgt });
                return `<button class="btn ${showingTr ? "active on" : ""}" type="button" data-translate-tab="${escapeHtml(siteTab.id)}" title="${escapeHtml(t("top.restore_page_title"))}">${icon("translate", "ico-sm")}<span>${escapeHtml(lbl)}</span></button>`;
              }
              if (tr?.status === "allowed_notice") {
                const src = tr.sourceLang || primaryLang;
                return `<span class="badge soft">${escapeHtml(t("top.page_allowed_notice", { lang: src }))}</span><button class="btn" type="button" data-translate-tab="${escapeHtml(siteTab.id)}" data-translate-force="1" title="${escapeHtml(t("top.page_allowed_title", { lang: src }))}">${icon("translate", "ico-sm")}<span>${escapeHtml(t("top.translate_anyway"))}</span></button>`;
              }
              const errTitle =
                tr?.status === "error" && tr.errorMsg
                  ? t("top.translate_error", { error: tr.errorMsg })
                  : t("top.translate_title", { lang: primaryLang });
              return `<button class="btn" type="button" data-translate-tab="${escapeHtml(siteTab.id)}"${tr?.status === "error" ? ` data-translate-force="1"` : ""} title="${escapeHtml(errTitle)}">${icon("translate", "ico-sm")}<span>${escapeHtml(t("top.translate_page"))}</span></button>`;
            })()
          : ""
      }
      ${
        siteTab
          ? `<button class="icon-btn" type="button" data-watch-tab="${escapeHtml(siteTab.id)}" title="${escapeHtml(t("top.watch_title"))}">${icon("watch")}</button>`
          : ""
      }
      ${
        isCompare
          ? `
            <button id="compare-run-comparer-btn" class="btn primary" type="button" title="${escapeHtml(t("top.compare_these_title"))}">${icon("compare", "ico-sm")}<span>${escapeHtml(t("top.compare_these"))}</span></button>
            <button id="compare-exit-btn" class="btn" type="button">${escapeHtml(t("common.exit"))}</button>
          `
          : openTabs.length >= 2
            ? `
              <button
                id="tab-strip-compare-btn"
                class="btn ${state.compareTabIds.length >= 2 ? "active on" : ""}"
                type="button"
                title="${escapeHtml(t("top.compare_title", { mod: MOD_LABEL }))}"
              >
                ${icon("compare", "ico-sm")}
                <span>${escapeHtml(state.compareTabIds.length >= 2 ? t("top.compare_n", { count: state.compareTabIds.length }) : t("common.compare"))}</span>
              </button>
            `
            : ""
      }
      ${
        supportsAgent
          ? `
            <button
              id="toggle-agent-rail-btn"
              class="icon-btn ${state.agentRailOpen ? "active on" : ""}"
              type="button"
              title="${escapeHtml(t("top.toggle_agent_title", { mod: MOD_LABEL }))}"
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

  container.querySelectorAll("[data-translate-tab]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      const el = btn as HTMLElement;
      const tabId = el.getAttribute("data-translate-tab");
      if (!tabId) return;
      const force =
        el.getAttribute("data-translate-force") === "1" || (ev as MouseEvent).shiftKey;
      actions.onTranslateTab?.(tabId, force);
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
        el.innerHTML = `<strong>${escapeHtml(code)}</strong> <span class="muted">${escapeHtml(t("top.promo_copied"))}</span>`;
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
  const isDrivesConv = detail.conversation.origin === "drives";
  const isSettingsConv = detail.conversation.origin === "settings";
  const isNewsSettingsConv = detail.conversation.origin === "news_settings";
  const isAnySettingsConv = isSettingsConv || isNewsSettingsConv;

  if (!isMailConv && !isNewsConv && !isDrivesConv && !isAnySettingsConv && openTabs.length === 0) {
    container.classList.add("hidden");
    container.innerHTML = "";
    return;
  }

  container.classList.remove("hidden");

  const isChatActive = state.activeTabId === "chat" && !state.compareMode;
  const counts = state.mailCounts;

  const mailLaneTabsHtml = isMailConv
    ? `
      <button type="button" class="tab tab-pinned ${!state.compareMode && state.activeTabId === "lane:inbox" ? "active on" : ""}" aria-selected="${!state.compareMode && state.activeTabId === "lane:inbox" ? "true" : "false"}" data-lane-tab="inbox">
        <span>${escapeHtml(t("top.mail_inbox"))}</span>
        ${counts.inbox_unread > 0 ? `<span class="count">${counts.inbox_unread}</span>` : ""}
      </button>
      <button type="button" class="tab tab-pinned ${!state.compareMode && state.activeTabId === "lane:pings" ? "active on" : ""}" aria-selected="${!state.compareMode && state.activeTabId === "lane:pings" ? "true" : "false"}" data-lane-tab="pings">
        <span>${escapeHtml(t("top.mail_pings"))}</span>
        ${counts.pings > 0 ? `<span class="count">${counts.pings}</span>` : ""}
      </button>
      <button type="button" class="tab tab-pinned ${!state.compareMode && state.activeTabId === "lane:orders" ? "active on" : ""}" aria-selected="${!state.compareMode && state.activeTabId === "lane:orders" ? "true" : "false"}" data-lane-tab="orders">
        <span>${escapeHtml(t("top.mail_orders"))}</span>
        ${counts.orders > 0 ? `<span class="count">${counts.orders}</span>` : ""}
      </button>
      <button type="button" class="tab tab-pinned ${!state.compareMode && state.activeTabId === "lane:promos" ? "active on" : ""}" aria-selected="${!state.compareMode && state.activeTabId === "lane:promos" ? "true" : "false"}" data-lane-tab="promos">
        <span>${escapeHtml(t("top.mail_promos"))}</span>
        ${counts.promos > 0 ? `<span class="count">${counts.promos}</span>` : ""}
      </button>
    `
    : "";

  const newsClusterCount = state.newsStories.length || state.sidecar.news?.clusters || 0;
  const newsTopicCount = state.newsTopics.length || state.sidecar.news?.topics || 0;
  const newsLaneTabsHtml = isNewsConv
    ? `
      <button type="button" class="tab tab-pinned ${!state.compareMode && state.activeTabId === "news-lane:stories" ? "active on" : ""}" aria-selected="${!state.compareMode && state.activeTabId === "news-lane:stories" ? "true" : "false"}" data-news-lane-tab="stories" title="${escapeHtml(t("top.news_stories_title"))}">
        <span>${escapeHtml(t("top.news_stories"))}</span>
        ${newsClusterCount > 0 ? `<span class="count">${newsClusterCount}</span>` : ""}
      </button>
      <button type="button" class="tab tab-pinned ${!state.compareMode && state.activeTabId === "news-lane:perspectives" ? "active on" : ""}" aria-selected="${!state.compareMode && state.activeTabId === "news-lane:perspectives" ? "true" : "false"}" data-news-lane-tab="perspectives" title="${escapeHtml(t("top.news_perspectives_title"))}">
        <span>${escapeHtml(t("top.news_perspectives"))}</span>
      </button>
      <button type="button" class="tab tab-pinned" data-open-news-settings="1" title="${escapeHtml(t("top.news_settings_title"))}">
        ${icon("settings", "ico-sm")}
        <span>${escapeHtml(t("top.news_settings"))}</span>
        ${newsTopicCount > 0 ? `<span class="count">${newsTopicCount}</span>` : ""}
      </button>
    `
    : "";

  const isDrivesFilesActive =
    !state.compareMode && state.activeTabId === "drives-lane:files";
  const drivesTotalCount =
    state.drivesStatus?.total_files ?? state.sidecar.drives?.total_files ?? 0;
  const drivesLaneTabsHtml = isDrivesConv
    ? `
      <button type="button" class="tab tab-pinned ${isDrivesFilesActive ? "active on" : ""}" aria-selected="${isDrivesFilesActive ? "true" : "false"}" data-drives-lane-tab="files" title="${escapeHtml(t("top.drives_files_title"))}">
        ${icon("folder", "ico-sm")}
        <span>${escapeHtml(t("top.drives_files"))}</span>
        ${drivesTotalCount > 0 ? `<span class="count">${drivesTotalCount}</span>` : ""}
      </button>
    `
    : "";

  const isManualSettingsActive =
    !state.compareMode && state.activeTabId === "settings-manual";
  const isManualNewsSettingsActive =
    !state.compareMode && state.activeTabId === "news-settings-manual";
  const settingsLaneTabsHtml = isSettingsConv
    ? `
      <button type="button" class="tab tab-pinned ${isManualSettingsActive ? "active on" : ""}" aria-selected="${isManualSettingsActive ? "true" : "false"}" data-tab-id="settings-manual">
        ${icon("settings", "ico-sm")}
        <span>${escapeHtml(t("top.settings_manual"))}</span>
      </button>
    `
    : isNewsSettingsConv
      ? `
        <button type="button" class="tab tab-pinned ${isManualNewsSettingsActive ? "active on" : ""}" aria-selected="${isManualNewsSettingsActive ? "true" : "false"}" data-tab-id="news-settings-manual">
          ${icon("settings", "ico-sm")}
          <span>${escapeHtml(t("top.news_settings_manual"))}</span>
        </button>
        <button type="button" class="tab tab-pinned" data-jump-back-news="1" title="${escapeHtml(t("top.back_to_news"))}">
          ${icon("news", "ico-sm")}
          <span>${escapeHtml(t("top.back_to_news"))}</span>
        </button>
      `
      : "";

  container.innerHTML = `
    <button type="button" class="tab tab-pinned ${isChatActive ? "active on" : ""}" aria-selected="${isChatActive ? "true" : "false"}" data-tab-id="chat">
      ${icon("chat", "ico-sm")}
      <span>${escapeHtml(t("common.chat"))}</span>
    </button>
    ${mailLaneTabsHtml}
    ${newsLaneTabsHtml}
    ${drivesLaneTabsHtml}
    ${settingsLaneTabsHtml}
    ${openTabs.length > 0 ? `<span class="tabs-sep" aria-hidden="true"></span>` : ""}
    ${openTabs
      .map((tab, idx) => {
        const isActive = !state.compareMode && state.activeTabId === tab.id;
        const isSelectedForCompare = state.compareTabIds.includes(tab.id);
        const domain =
          tab.kind === "mail"
            ? t("common.mail")
            : tab.kind === "compose"
              ? t("top.tab_compose")
              : extractDomain(tab.url);
        const leadIcon =
          tab.kind === "mail"
            ? icon("mail", "ico-sm")
            : tab.kind === "compose"
              ? icon("compose", "ico-sm")
              : renderSiteFaviconHtml(tab.url, null, "globe");
        const label = tab.title || domain;
        return `
          <div
            class="tab ${isActive ? "active on" : ""} ${isSelectedForCompare ? "selected-compare" : ""}"
            aria-selected="${isActive ? "true" : "false"}"
            data-site-tab-id="${escapeHtml(tab.id)}"
            title="${escapeHtml(t("top.tab_source_title", { index: idx + 1, label: tab.title || tab.url }))}"
          >
            ${leadIcon}
            <span class="truncate">${escapeHtml(label)}</span>
            <button class="tab-close-btn" type="button" data-close-tab-id="${escapeHtml(tab.id)}" title="${escapeHtml(t("top.close_tab"))}">${icon("x", "ico-sm")}</button>
          </div>
        `;
      })
      .join("")}
    ${isAnySettingsConv ? "" : `<button id="tab-strip-add-btn" class="icon-btn" type="button" title="${escapeHtml(t("top.new_tab_title", { mod: MOD_LABEL }))}">${icon("plus", "ico-sm")}</button>`}
  `;

  bindFaviconFallbacks(container);

  container.querySelector('[data-tab-id="chat"]')?.addEventListener("click", () => {
    actions.onSelectTab("chat");
  });

  container.querySelector('[data-tab-id="settings-manual"]')?.addEventListener("click", () => {
    actions.onSelectTab("settings-manual");
  });

  container.querySelector('[data-tab-id="news-settings-manual"]')?.addEventListener("click", () => {
    actions.onSelectTab("news-settings-manual");
  });

  container.querySelector("[data-open-news-settings]")?.addEventListener("click", () => {
    actions.onOpenNewsSettings?.("chat");
  });

  container.querySelector("[data-jump-back-news]")?.addEventListener("click", () => {
    actions.onOpenNewsHome?.();
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

  container.querySelectorAll("[data-drives-lane-tab]").forEach((el) => {
    el.addEventListener("click", () => {
      const lane = (el as HTMLElement).getAttribute("data-drives-lane-tab");
      if (lane) {
        actions.onSelectTab(`drives-lane:${lane}`);
      }
    });
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
    el.addEventListener("mousedown", (e) => {
      if ((e as MouseEvent).button === 1) {
        e.preventDefault();
      }
    });
    el.addEventListener("auxclick", (e) => {
      const me = e as MouseEvent;
      if (me.button !== 1) return;
      me.preventDefault();
      me.stopPropagation();
      const tabId = (el as HTMLElement).getAttribute("data-site-tab-id");
      if (tabId) actions.onCloseTab(tabId);
    });
  });

  container.querySelectorAll("[data-close-tab-id]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const tabId = (btn as HTMLElement).getAttribute("data-close-tab-id");
      if (tabId) actions.onCloseTab(tabId);
    });
  });

  const addBtn = container.querySelector("#tab-strip-add-btn");
  addBtn?.addEventListener("click", () => {
    actions.onNewTab();
  });
  addBtn?.addEventListener("mousedown", (e) => {
    if ((e as MouseEvent).button === 1) e.preventDefault();
  });
  addBtn?.addEventListener("auxclick", (e) => {
    if ((e as MouseEvent).button === 1) {
      e.preventDefault();
      e.stopPropagation();
      actions.onNewTab();
    }
  });

  container.addEventListener("mousedown", (e) => {
    if ((e as MouseEvent).button === 1 && e.target === container) {
      e.preventDefault();
    }
  });
  const isAnySettingsConvForMouse =
    detail.conversation.origin === "settings" || detail.conversation.origin === "news_settings";
  container.addEventListener("auxclick", (e) => {
    if (!isAnySettingsConvForMouse && (e as MouseEvent).button === 1 && e.target === container) {
      e.preventDefault();
      e.stopPropagation();
      actions.onNewTab();
    }
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
    state.postUnlockLoading ||
    state.mailComposeModalOpen ||
    state.chatImagePreview !== null ||
    (!state.compareMode &&
      (state.activeTabId === "chat" ||
        state.activeTabId === "settings-manual" ||
        state.activeTabId === "news-settings-manual" ||
        state.activeTabId.startsWith("lane:") ||
        state.activeTabId.startsWith("news-lane:") ||
        state.activeTabId.startsWith("drives-lane:")))
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
      parentEl?.querySelector(".tile-h");
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
        tab.url !== "about:blank" &&
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
      tab.url !== "about:blank" &&
      !tab.url.startsWith("satzmail://") &&
      slot
    ) {
      visible.push(measureSlotBounds(tab.id, tab.url, slot));
    }
  }

  await apiSyncTabWebviews(visible);
}
