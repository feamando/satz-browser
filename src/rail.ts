import { drawWordmark, fontsReady } from "./design-system/brand";
import { icon } from "./design-system/icons";
import { bindFaviconFallbacks, renderSiteFaviconHtml } from "./favicon";
import { t } from "./i18n";
import {
  escapeHtml,
  extractDomain,
  formatRelativeTime,
  getResolvedTheme,
  isConvStreaming,
  MOD_LABEL,
  setRailAccordionPref,
  state,
  type RailAccordionKey,
} from "./state";
import { renderStatusLine } from "./status";
import type { Conversation } from "./types";

export interface RailActions {
  onOpenHome?: () => void;
  onSelectConversation: (id: string) => void;
  onSelectMailAccount?: (convId: string, accountId: string | null) => void;
  onNewConversation: () => void;
  onTogglePin: (id: string) => void;
  onRenameConversation: (id: string, newTitle: string) => void;
  onToggleArchive: (id: string, archived: boolean) => void;
  onDeleteConversation: (id: string) => void;
  onOpenBookmark: (url: string) => void;
  onOpenBookmarkInNewTab?: (url: string, title: string) => void;
  onBookmarkCurrent: () => void;
  onRemoveBookmark: (id: string) => void;
  onOpenKnowledgeView: () => void;
  onOpenBrainView?: () => void;
  onOpenCommandBar?: () => void;
  onOpenProfileUnlock?: () => void;
  onLockProfile?: () => void;
}

function paintWordmark(): void {
  const cv = document.getElementById("rail-wordmark-canvas") as HTMLCanvasElement | null;
  if (!cv) return;
  const theme = getResolvedTheme();
  const draw = () => {
    const live = document.getElementById("rail-wordmark-canvas") as HTMLCanvasElement | null;
    if (live) {
      drawWordmark(live, { height: 22, theme: getResolvedTheme(), variant: "backdrop" });
    }
  };
  if (typeof document !== "undefined" && document.fonts?.check("700 16px Besley")) {
    draw();
  } else {
    void fontsReady().then(draw);
  }
  void theme;
}

export function renderRail(actions: RailActions): void {
  const container = document.getElementById("region-rail");
  if (!container) return;

  const q = state.railFilter.trim().toLowerCase();
  const visibleConvs = state.conversations.filter((c) => {
    // Settings & sub-workspaces are opened from dedicated buttons rather than duplicating in the rail.
    if (
      c.origin === "settings" ||
      c.origin === "news_settings" ||
      c.origin === "news_perspectives"
    ) {
      return false;
    }
    if (!q) return true;
    return (
      c.title.toLowerCase().includes(q) ||
      (c.summary ?? "").toLowerCase().includes(q)
    );
  });

  const pinned = visibleConvs.filter((c) => c.pinned && c.status === "active");
  const systemPinned = pinned.filter(
    (c) => c.origin === "mail" || c.origin === "news" || c.origin === "drives"
  );
  const userPinned = pinned.filter(
    (c) => c.origin !== "mail" && c.origin !== "news" && c.origin !== "drives"
  );
  const recent = visibleConvs.filter((c) => !c.pinned && c.status === "active");
  const archived = visibleConvs.filter((c) => c.status === "archived");

  const activeId = state.activeDetail?.conversation.id ?? null;
  const isHomeActive =
    !activeId && !state.showKnowledgeView && !state.showBrainView;

  const acc = state.railAccordion;
  const profile = state.knowledge.profile;
  const isUnlocked = Boolean(profile?.unlocked && profile?.active_profile);
  const profileName = isUnlocked
    ? profile?.active_profile?.name || t("rail.profile_title", { name: "" }).trim()
    : t("rail.locked");
  const avatarInitial = isUnlocked
    ? (profileName.trim()[0] || "S").toUpperCase()
    : "L";

  container.innerHTML = `
    <div class="brand">
      <button id="rail-brand-home-btn" class="brand-btn" type="button" title="${escapeHtml(t("rail.home_title", { mod: MOD_LABEL }))}">
        <canvas id="rail-wordmark-canvas" aria-label="satz"></canvas>
      </button>
    </div>

    <div class="quick">
      <button
        id="rail-home-btn"
        class="icon-btn quick-btn ${isHomeActive ? "active" : ""}"
        type="button"
        title="${escapeHtml(t("rail.home_title", { mod: MOD_LABEL }))}"
      >
        ${icon("home", "ico-sm")}
        <span>${escapeHtml(t("rail.home"))}</span>
      </button>
      <button
        id="rail-open-command-bar-btn"
        class="icon-btn quick-btn"
        type="button"
        title="${escapeHtml(t("rail.cmd_title", { mod: MOD_LABEL }))}"
      >
        ${icon("cmd", "ico-sm")}
        <span>${escapeHtml(t("common.search"))}</span>
      </button>
      <button
        id="rail-new-conv-btn"
        class="icon-btn quick-btn"
        type="button"
        title="${escapeHtml(t("rail.new_title", { mod: MOD_LABEL }))}"
      >
        ${icon("compose", "ico-sm")}
        <span>${escapeHtml(t("rail.new"))}</span>
      </button>
    </div>

    <div class="rail-filter-wrap">
      <input
        id="rail-filter-input"
        class="input"
        type="text"
        spellcheck="false"
        autocorrect="off"
        autocapitalize="off"
        placeholder="${escapeHtml(t("rail.filter_placeholder"))}"
        value="${escapeHtml(state.railFilter)}"
      />
    </div>

    <div class="rail-scroll">
      <section class="acc ${acc.pinned ? "" : "closed"}" data-acc="pinned">
        <button class="acc-h" type="button" data-acc-toggle="pinned" aria-expanded="${acc.pinned ? "true" : "false"}">
          <span class="rail-acc-chevron">${icon("chev", "ico-sm")}</span>
          <span class="label">${escapeHtml(t("rail.pinned"))}</span>
          <span class="acc-count">${pinned.length}</span>
        </button>
        <div class="acc-body">
          ${
            pinned.length === 0
              ? `<div class="muted" id="rail-empty-pinned">${escapeHtml(t("common.none"))}</div>`
              : `
                ${systemPinned
                  .map((c) => {
                    const activeOrigin = state.conversations.find((x) => x.id === activeId)?.origin;
                    const rowActive =
                      c.id === activeId ||
                      (c.origin === "news" &&
                        (activeOrigin === "news_settings" || activeOrigin === "news_perspectives"));
                    return renderConversationRow(c, rowActive);
                  })
                  .join("")}
                ${systemPinned.length > 0 && userPinned.length > 0 ? `<div class="sep"></div>` : ""}
                ${userPinned.map((c) => renderConversationRow(c, c.id === activeId)).join("")}
              `
          }
        </div>
      </section>

      <section class="acc ${acc.sources ? "" : "closed"}" data-acc="sources">
        <button class="acc-h" type="button" data-acc-toggle="sources" aria-expanded="${acc.sources ? "true" : "false"}" title="${escapeHtml(t("rail.bookmarks_title"))}">
          <span class="rail-acc-chevron">${icon("chev", "ico-sm")}</span>
          <span class="label">${escapeHtml(t("rail.bookmarks"))}</span>
          <span class="acc-count">${state.bookmarks.length}</span>
        </button>
        <div class="acc-body">
          ${
            state.bookmarks.length === 0
              ? `<div class="muted">${escapeHtml(t("rail.no_bookmarks"))}</div>`
              : state.bookmarks
                  .map((b) => {
                    const idxEntry = state.knowledge.bookmarks_indexed?.find(
                      (bi) => bi.id === b.id || bi.url === b.url
                    );
                    const synced = idxEntry && idxEntry.status === "indexed";
                    return `
                      <div
                        class="row"
                        data-bookmark-url="${escapeHtml(b.url)}"
                        title="${escapeHtml(t("rail.bookmark_url_title", { url: b.url }))}"
                      >
                        ${renderSiteFaviconHtml(b.url, b.favicon_url, "globe")}
                        <span class="row-title">${escapeHtml(b.title || extractDomain(b.url))}</span>
                        <span class="row-meta">${escapeHtml(synced ? t("rail.synced") : t("rail.index"))}</span>
                        <button class="row-menu" type="button" data-remove-bookmark="${escapeHtml(b.id)}" title="${escapeHtml(t("rail.remove_bookmark"))}">
                          ${icon("x", "ico-sm")}
                        </button>
                      </div>
                    `;
                  })
                  .join("")
          }
          <button
            id="rail-bookmark-current-btn"
            class="btn rail-bm-action"
            type="button"
            title="${escapeHtml(t("rail.bookmark_current_title", { mod: MOD_LABEL }))}"
          >
            ${icon("plus", "ico-sm")}
            <span>${escapeHtml(t("rail.bookmark_current"))}</span>
          </button>
          ${
            state.bookmarkTooltipNotice
              ? `<div class="muted">${escapeHtml(state.bookmarkTooltipNotice)}</div>`
              : ""
          }
        </div>
      </section>

      <section class="acc ${acc.conversations ? "" : "closed"}" data-acc="conversations">
        <button class="acc-h" type="button" data-acc-toggle="conversations" aria-expanded="${acc.conversations ? "true" : "false"}">
          <span class="rail-acc-chevron">${icon("chev", "ico-sm")}</span>
          <span class="label">${escapeHtml(t("rail.conversations"))}</span>
          <span class="acc-count">${recent.length}</span>
        </button>
        <div class="acc-body">
          ${
            recent.length === 0
              ? `<div class="muted" id="rail-empty-recent">${escapeHtml(t("common.none"))}</div>`
              : recent.map((c) => renderConversationRow(c, c.id === activeId)).join("")
          }
        </div>
      </section>

      <section class="acc ${acc.archived ? "" : "closed"}" data-acc="archived">
        <button class="acc-h" id="rail-toggle-archived" type="button" data-acc-toggle="archived" aria-expanded="${acc.archived ? "true" : "false"}">
          <span class="rail-acc-chevron">${icon("chev", "ico-sm")}</span>
          <span class="label">${escapeHtml(t("rail.archived"))}</span>
          <span class="acc-count">${archived.length}</span>
        </button>
        <div class="acc-body">
          ${
            archived.length === 0
              ? `<div class="muted">${escapeHtml(t("common.none"))}</div>`
              : archived.map((c) => renderConversationRow(c, c.id === activeId)).join("")
          }
        </div>
      </section>
    </div>

    ${
      state.profileMenuOpen
        ? `
          <div class="menu prof-menu" id="rail-profile-menu" role="menu">
            <div class="row">
              <span class="row-title">${escapeHtml(profileName)}</span>
              ${
                state.profileUnlocking
                  ? `<span class="badge soft"><span class="satz-spinner" aria-hidden="true"></span><span>${escapeHtml(t("profile.unlocking_short"))}</span></span>`
                  : `<span class="badge ${isUnlocked ? "good" : "warn"}">${escapeHtml(isUnlocked ? t("rail.unlocked") : t("rail.locked"))}</span>`
              }
            </div>
            <div class="sep"></div>
            <button class="menu-item" type="button" data-prof-action="settings">
              ${icon("settings", "ico-sm")}
              <span>${escapeHtml(t("rail.settings_appearance"))}</span>
            </button>
            <button class="menu-item" type="button" data-prof-action="toggle-lock" ${state.profileUnlocking ? "disabled" : ""}>
              ${icon("lock", "ico-sm")}
              <span>${escapeHtml(state.profileUnlocking ? t("profile.unlocking_short") : isUnlocked ? t("rail.lock_profile") : t("rail.unlock_profile"))}</span>
            </button>
          </div>
        `
        : ""
    }

    <div class="foot">
      <div class="foot-actions">
        <button
          id="rail-open-brain-btn"
          class="icon-btn ${state.showBrainView ? "active on" : ""}"
          type="button"
          title="${escapeHtml(t("rail.brain_title", { mod: MOD_LABEL }))}"
        >
          ${icon("brain")}
        </button>
        <button
          id="rail-open-knowledge-btn"
          class="icon-btn ${state.showKnowledgeView || state.activeDetail?.conversation.origin === "settings" ? "active on" : ""}"
          type="button"
          title="${escapeHtml(t("rail.settings_title"))}"
        >
          ${icon("settings")}
        </button>
        <button
          id="rail-telemetry-btn"
          class="icon-btn ${state.telemetryOpen ? "active on" : ""}"
          type="button"
          title="${escapeHtml(t("rail.telemetry_title"))}"
          aria-expanded="${state.telemetryOpen ? "true" : "false"}"
        >
          ${icon("pulse")}
          <i id="rail-telemetry-dot" class="dot"></i>
        </button>
      </div>
      <button
        id="rail-profile-btn"
        class="prof ${state.profileUnlocking ? "unlocking" : ""}"
        type="button"
        title="${escapeHtml(state.profileUnlocking ? (state.profileUnlockLabel || t("profile.unlocking_progress")) : t("rail.profile_title", { name: profileName }))}"
        aria-expanded="${state.profileMenuOpen ? "true" : "false"}"
      >
        ${state.profileUnlocking ? `<span class="satz-spinner" aria-hidden="true"></span>` : `<span class="avatar">${escapeHtml(avatarInitial)}</span>`}
        <span class="truncate">${escapeHtml(state.profileUnlocking ? t("profile.unlocking_short") : profileName)}</span>
      </button>
    </div>

    <div id="region-telemetry"></div>
  `;

  paintWordmark();
  bindRailEvents(container, actions);
  renderStatusLine();
}

function renderConversationRow(c: Conversation, isActive: boolean): string {
  const isMail = c.origin === "mail";
  const isNews = c.origin === "news";
  const isDrives = c.origin === "drives";
  const isSettings = c.origin === "settings";
  const isPinnedSystem = isMail || isNews || isDrives || isSettings;
  const srcCount = c.source_count ?? 0;
  const relTime = formatRelativeTime(c.last_active_at || c.created_at);
  const menuOpen = !isPinnedSystem && state.openMenuConvId === c.id;
  const isRenaming = !isPinnedSystem && state.renamingConvId === c.id;

  const totalUnread =
    state.mailAccounts.length > 0
      ? state.mailAccounts.reduce((acc, a) => acc + (a.inbox_unread ?? 0), 0) ||
        state.mailCounts.inbox_unread ||
        state.sidecar.mail?.inbox_unread ||
        0
      : state.mailCounts.inbox_unread || state.sidecar.mail?.inbox_unread || 0;
  const newsCount =
    state.newsStories.length || state.sidecar.news?.clusters || 0;
  const drivesCount =
    state.drivesStatus?.total_files ?? state.sidecar.drives?.total_files ?? 0;
  const settingsUnlocked = Boolean(
    state.knowledge.profile?.unlocked && state.knowledge.profile?.active_profile
  );

  const displayTitle = isMail
    ? state.mailAccounts.length > 0
      ? t("rail.all_mail")
      : t("common.mail")
    : isNews
      ? t("common.news")
      : isDrives
        ? t("common.drives")
        : isSettings
          ? t("common.settings")
          : c.title;

  const countLabel = isMail
    ? String(totalUnread)
    : isNews
      ? String(newsCount)
      : isDrives
        ? String(drivesCount)
        : isSettings
          ? settingsUnlocked
            ? state.knowledge.profile?.active_profile?.name || t("rail.unlocked")
            : t("rail.locked")
          : srcCount > 0
            ? t("rail.src_count", { count: srcCount })
            : relTime;

  const hasWatchBadge =
    state.watchBadgeConvIds.includes(c.id) ||
    Boolean(state.sidecar.watch_badges?.includes(c.id));

  const isCommonMailActive =
    isMail &&
    isActive &&
    !state.showKnowledgeView &&
    !state.showBrainView &&
    state.mailActiveAccountId === null;
  const isNormalConvActive =
    !isMail && isActive && !state.showKnowledgeView && !state.showBrainView;

  const convRunning = isConvStreaming(c.id);
  const leadIcon = isMail
    ? icon("mail", "ico-sm")
    : isNews
      ? icon("news", "ico-sm")
      : isDrives
        ? icon("drive", "ico-sm")
        : isSettings
          ? icon("settings", "ico-sm")
          : "";

  const mailAccountSubrowsHtml =
    isMail && state.mailAccounts.length > 0
      ? state.mailAccounts
          .map((acct) => {
            const acctActive =
              isActive &&
              !state.showKnowledgeView &&
              !state.showBrainView &&
              state.mailActiveAccountId === acct.id;
            const acctUnread = acct.inbox_unread ?? 0;
            const acctName = acct.email || acct.label;
            return `
              <div
                class="row sub ${acctActive ? "active" : ""}"
                data-mail-rail-conv="${escapeHtml(c.id)}"
                data-mail-rail-acct="${escapeHtml(acct.id)}"
                title="${escapeHtml(t("rail.messages_count_title", { name: acctName, count: acct.message_count ?? 0 }))}"
              >
                <span class="row-title">${escapeHtml(acctName)}</span>
                <span class="row-meta">${acctUnread > 0 ? acctUnread : acct.message_count ?? 0}</span>
              </div>
            `;
          })
          .join("")
      : "";

  return `
    <div class="row-wrap">
      <div
        class="row ${isCommonMailActive || isNormalConvActive ? "active" : ""}"
        data-conv-id="${escapeHtml(c.id)}"
        ${isMail ? 'data-mail-rail-all="1"' : ""}
        title="${escapeHtml(displayTitle)}"
      >
        ${leadIcon}
        ${convRunning ? `<i class="dot live" title="${escapeHtml(t("rail.generating"))}"></i>` : ""}
        ${hasWatchBadge ? `<i class="dot warn" title="${escapeHtml(t("rail.watched_changed"))}"></i>` : ""}
        ${isSettings && !settingsUnlocked ? `<i class="dot warn" title="${escapeHtml(t("rail.locked"))}"></i>` : ""}
        ${
          isRenaming
            ? `<input id="rail-rename-input-${escapeHtml(c.id)}" class="input row-rename-input" type="text" value="${escapeHtml(c.title)}" />`
            : `<span class="row-title">${escapeHtml(displayTitle)}</span>`
        }
        <span class="row-meta">${escapeHtml(countLabel)}</span>
        ${
          isPinnedSystem
            ? ""
            : `<button class="row-menu" type="button" data-menu-conv-id="${escapeHtml(c.id)}" title="${escapeHtml(t("rail.actions"))}">${icon("more", "ico-sm")}</button>`
        }
      </div>
      ${
        menuOpen
          ? `
            <div class="menu row-menu-pop">
              <button class="menu-item" type="button" data-action-pin="${escapeHtml(c.id)}">${escapeHtml(c.pinned ? t("common.unpin") : t("common.pin"))}</button>
              <button class="menu-item" type="button" data-action-rename="${escapeHtml(c.id)}">${escapeHtml(t("common.rename"))}</button>
              <button class="menu-item" type="button" data-action-archive="${escapeHtml(c.id)}" data-archived="${c.status === "archived" ? "1" : "0"}" title="${escapeHtml(c.status === "archived" ? t("rail.restore_title") : t("rail.archive_title", { mod: MOD_LABEL.toUpperCase() }))}"><span>${escapeHtml(c.status === "archived" ? t("common.restore") : t("common.archive"))}</span>${c.status === "archived" ? "" : `<span class="end">${escapeHtml(MOD_LABEL.toUpperCase())}+W</span>`}</button>
              <button class="menu-item" type="button" data-action-delete="${escapeHtml(c.id)}">${escapeHtml(t("common.delete"))}</button>
            </div>
          `
          : ""
      }
      ${mailAccountSubrowsHtml}
    </div>
  `;
}

function bindRailEvents(container: HTMLElement, actions: RailActions): void {
  bindFaviconFallbacks(container);
  const filterInput = container.querySelector(
    "#rail-filter-input"
  ) as HTMLInputElement | null;
  filterInput?.addEventListener("input", () => {
    const pos = filterInput.selectionStart ?? filterInput.value.length;
    state.railFilter = filterInput.value;
    renderRail(actions);
    const next = document.getElementById(
      "rail-filter-input"
    ) as HTMLInputElement | null;
    if (next) {
      next.focus();
      next.setSelectionRange(pos, pos);
    }
  });

  container.querySelectorAll("[data-acc-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = (btn as HTMLElement).getAttribute("data-acc-toggle") as RailAccordionKey | null;
      if (!key) return;
      state.railAccordion[key] = !state.railAccordion[key];
      if (key === "archived") {
        state.showArchived = state.railAccordion.archived;
      }
      setRailAccordionPref(state.railAccordion);
      renderRail(actions);
    });
  });

  container
    .querySelector("#rail-brand-home-btn")
    ?.addEventListener("click", () => {
      (actions.onOpenHome ?? actions.onNewConversation)();
    });

  container
    .querySelector("#rail-home-btn")
    ?.addEventListener("click", () => {
      (actions.onOpenHome ?? actions.onNewConversation)();
    });

  container
    .querySelector("#rail-open-command-bar-btn")
    ?.addEventListener("click", () => {
      actions.onOpenCommandBar?.();
    });

  container
    .querySelector("#rail-new-conv-btn")
    ?.addEventListener("click", () => {
      actions.onNewConversation();
    });

  container
    .querySelector("#rail-bookmark-current-btn")
    ?.addEventListener("click", () => {
      actions.onBookmarkCurrent();
    });

  container
    .querySelector("#rail-open-brain-btn")
    ?.addEventListener("click", () => {
      if (actions.onOpenBrainView) {
        actions.onOpenBrainView();
      } else {
        actions.onOpenKnowledgeView();
      }
    });

  container
    .querySelector("#rail-open-knowledge-btn")
    ?.addEventListener("click", () => {
      actions.onOpenKnowledgeView();
    });

  container
    .querySelector("#rail-telemetry-btn")
    ?.addEventListener("click", (e) => {
      e.stopPropagation();
      state.profileMenuOpen = false;
      state.telemetryOpen = !state.telemetryOpen;
      renderRail(actions);
    });

  container
    .querySelector("#rail-profile-btn")
    ?.addEventListener("click", (e) => {
      e.stopPropagation();
      state.telemetryOpen = false;
      state.profileMenuOpen = !state.profileMenuOpen;
      renderRail(actions);
    });

  container.querySelectorAll("[data-prof-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = (btn as HTMLElement).getAttribute("data-prof-action");
      state.profileMenuOpen = false;
      if (action === "settings") {
        actions.onOpenKnowledgeView();
      } else if (action === "toggle-lock") {
        const isUnlocked = Boolean(
          state.knowledge.profile?.unlocked && state.knowledge.profile?.active_profile
        );
        if (isUnlocked) {
          actions.onLockProfile?.();
        } else {
          actions.onOpenProfileUnlock?.();
        }
      }
    });
  });

  container.querySelectorAll("[data-conv-id]").forEach((row) => {
    row.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      if (
        target.closest("[data-menu-conv-id]") ||
        target.tagName.toLowerCase() === "input"
      ) {
        return;
      }
      const el = row as HTMLElement;
      const id = el.getAttribute("data-conv-id");
      const isMailAll = el.getAttribute("data-mail-rail-all") === "1";
      if (id) {
        state.openMenuConvId = null;
        if (isMailAll && actions.onSelectMailAccount) {
          actions.onSelectMailAccount(id, null);
        } else {
          actions.onSelectConversation(id);
        }
      }
    });

    row.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      const id = (row as HTMLElement).getAttribute("data-conv-id");
      if (id) {
        state.openMenuConvId = state.openMenuConvId === id ? null : id;
        renderRail(actions);
      }
    });
  });

  container.querySelectorAll("[data-mail-rail-acct]").forEach((row) => {
    row.addEventListener("click", () => {
      const el = row as HTMLElement;
      const convId = el.getAttribute("data-mail-rail-conv") ?? "";
      const acctId = el.getAttribute("data-mail-rail-acct") ?? "";
      if (convId && acctId) {
        state.openMenuConvId = null;
        if (actions.onSelectMailAccount) {
          actions.onSelectMailAccount(convId, acctId);
        } else {
          state.mailActiveAccountId = acctId;
          actions.onSelectConversation(convId);
        }
      }
    });
  });

  container.querySelectorAll("[data-menu-conv-id]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const id = (btn as HTMLElement).getAttribute("data-menu-conv-id");
      if (!id) return;
      state.openMenuConvId = state.openMenuConvId === id ? null : id;
      renderRail(actions);
    });
  });

  container.querySelectorAll("[data-action-pin]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = (btn as HTMLElement).getAttribute("data-action-pin");
      state.openMenuConvId = null;
      if (id) actions.onTogglePin(id);
    });
  });

  container.querySelectorAll("[data-action-rename]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = (btn as HTMLElement).getAttribute("data-action-rename");
      state.openMenuConvId = null;
      state.renamingConvId = id;
      renderRail(actions);
      if (id) {
        const input = document.getElementById(
          `rail-rename-input-${id}`
        ) as HTMLInputElement | null;
        input?.focus();
        input?.select();
      }
    });
  });

  if (state.renamingConvId) {
    const rid = state.renamingConvId;
    const renameInput = document.getElementById(
      `rail-rename-input-${rid}`
    ) as HTMLInputElement | null;
    if (renameInput) {
      const commitRename = () => {
        const val = renameInput.value.trim();
        state.renamingConvId = null;
        if (val) {
          actions.onRenameConversation(rid, val);
        } else {
          renderRail(actions);
        }
      };
      renameInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") commitRename();
        if (e.key === "Escape") {
          state.renamingConvId = null;
          renderRail(actions);
        }
      });
      renameInput.addEventListener("blur", commitRename);
    }
  }

  container.querySelectorAll("[data-action-archive]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const id = el.getAttribute("data-action-archive");
      const isArchived = el.getAttribute("data-archived") === "1";
      state.openMenuConvId = null;
      if (id) actions.onToggleArchive(id, !isArchived);
    });
  });

  container.querySelectorAll("[data-action-delete]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = (btn as HTMLElement).getAttribute("data-action-delete");
      state.openMenuConvId = null;
      if (id) actions.onDeleteConversation(id);
    });
  });

  container.querySelectorAll("[data-bookmark-url]").forEach((row) => {
    row.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      if (target.closest("[data-remove-bookmark]")) return;
      const url = (row as HTMLElement).getAttribute("data-bookmark-url");
      if (url) actions.onOpenBookmark(url);
    });
    row.addEventListener("mousedown", (e) => {
      if ((e as MouseEvent).button === 1) e.preventDefault();
    });
    row.addEventListener("auxclick", (e) => {
      const me = e as MouseEvent;
      if (me.button !== 1) return;
      const target = e.target as HTMLElement;
      if (target.closest("[data-remove-bookmark]")) return;
      me.preventDefault();
      me.stopPropagation();
      const el = row as HTMLElement;
      const url = el.getAttribute("data-bookmark-url");
      const title =
        el.querySelector(".row-title")?.textContent?.trim() ?? "";
      if (url) {
        if (actions.onOpenBookmarkInNewTab) {
          actions.onOpenBookmarkInNewTab(url, title);
        } else {
          actions.onOpenBookmark(url);
        }
      }
    });
  });

  container.querySelectorAll("[data-remove-bookmark]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const id = (btn as HTMLElement).getAttribute("data-remove-bookmark");
      if (id) actions.onRemoveBookmark(id);
    });
  });
}
