import { drawWordmark, fontsReady } from "./design-system/brand";
import { icon } from "./design-system/icons";
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
    if (!q) return true;
    return (
      c.title.toLowerCase().includes(q) ||
      (c.summary ?? "").toLowerCase().includes(q)
    );
  });

  const pinned = visibleConvs.filter((c) => c.pinned && c.status === "active");
  const systemPinned = pinned.filter(
    (c) => c.origin === "mail" || c.origin === "news"
  );
  const userPinned = pinned.filter(
    (c) => c.origin !== "mail" && c.origin !== "news"
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
    ? profile?.active_profile?.name || "Profile"
    : "Locked";
  const avatarInitial = isUnlocked
    ? (profileName.trim()[0] || "S").toUpperCase()
    : "L";

  container.innerHTML = `
    <div class="brand">
      <button id="rail-brand-home-btn" class="brand-btn" type="button" title="Home (${MOD_LABEL}+Shift+H)">
        <canvas id="rail-wordmark-canvas" aria-label="satz"></canvas>
      </button>
    </div>

    <div class="quick">
      <button
        id="rail-home-btn"
        class="icon-btn quick-btn ${isHomeActive ? "active" : ""}"
        type="button"
        title="Home / Start Screen (${MOD_LABEL}+Shift+H)"
      >
        ${icon("home", "ico-sm")}
        <span>Home</span>
      </button>
      <button
        id="rail-open-command-bar-btn"
        class="icon-btn quick-btn"
        type="button"
        title="Command Bar (${MOD_LABEL}+K)"
      >
        ${icon("cmd", "ico-sm")}
        <span>Search</span>
      </button>
      <button
        id="rail-new-conv-btn"
        class="icon-btn quick-btn"
        type="button"
        title="New Conversation (${MOD_LABEL}+N)"
      >
        ${icon("compose", "ico-sm")}
        <span>New</span>
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
        placeholder="Filter..."
        value="${escapeHtml(state.railFilter)}"
      />
    </div>

    <div class="rail-scroll">
      <section class="acc ${acc.pinned ? "" : "closed"}" data-acc="pinned">
        <button class="acc-h" type="button" data-acc-toggle="pinned" aria-expanded="${acc.pinned ? "true" : "false"}">
          <span class="rail-acc-chevron">${icon("chev", "ico-sm")}</span>
          <span class="label">Pinned</span>
          <span class="acc-count">${pinned.length}</span>
        </button>
        <div class="acc-body">
          ${
            pinned.length === 0
              ? `<div class="muted" id="rail-empty-pinned">None</div>`
              : `
                ${systemPinned.map((c) => renderConversationRow(c, c.id === activeId)).join("")}
                ${systemPinned.length > 0 && userPinned.length > 0 ? `<div class="sep"></div>` : ""}
                ${userPinned.map((c) => renderConversationRow(c, c.id === activeId)).join("")}
              `
          }
        </div>
      </section>

      <section class="acc ${acc.conversations ? "" : "closed"}" data-acc="conversations">
        <button class="acc-h" type="button" data-acc-toggle="conversations" aria-expanded="${acc.conversations ? "true" : "false"}">
          <span class="rail-acc-chevron">${icon("chev", "ico-sm")}</span>
          <span class="label">Conversations</span>
          <span class="acc-count">${recent.length}</span>
        </button>
        <div class="acc-body">
          ${
            recent.length === 0
              ? `<div class="muted" id="rail-empty-recent">None</div>`
              : recent.map((c) => renderConversationRow(c, c.id === activeId)).join("")
          }
        </div>
      </section>

      <section class="acc ${acc.sources ? "" : "closed"}" data-acc="sources">
        <button class="acc-h" type="button" data-acc-toggle="sources" aria-expanded="${acc.sources ? "true" : "false"}" title="Bookmarked sources stay indexed in your local Brain">
          <span class="rail-acc-chevron">${icon("chev", "ico-sm")}</span>
          <span class="label">Sources</span>
          <span class="acc-count">${state.bookmarks.length}</span>
        </button>
        <div class="acc-body">
          ${
            state.bookmarks.length === 0
              ? `<div class="muted">No saved bookmarks</div>`
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
                        title="${escapeHtml(b.url)} — Auto-indexed into local Brain"
                      >
                        ${icon("globe", "ico-sm")}
                        <span class="row-title">${escapeHtml(b.title || extractDomain(b.url))}</span>
                        <span class="row-meta">${synced ? "Synced" : "Index"}</span>
                        <button class="row-menu" type="button" data-remove-bookmark="${escapeHtml(b.id)}" title="Remove bookmark">
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
            title="Index the active tab continuously in your local Brain (${MOD_LABEL}+D)"
          >
            ${icon("plus", "ico-sm")}
            <span>Bookmark current</span>
          </button>
          ${
            state.bookmarkTooltipNotice
              ? `<div class="muted">${escapeHtml(state.bookmarkTooltipNotice)}</div>`
              : ""
          }
        </div>
      </section>

      <section class="acc ${acc.archived ? "" : "closed"}" data-acc="archived">
        <button class="acc-h" id="rail-toggle-archived" type="button" data-acc-toggle="archived" aria-expanded="${acc.archived ? "true" : "false"}">
          <span class="rail-acc-chevron">${icon("chev", "ico-sm")}</span>
          <span class="label">Archived</span>
          <span class="acc-count">${archived.length}</span>
        </button>
        <div class="acc-body">
          ${
            archived.length === 0
              ? `<div class="muted">None</div>`
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
              <span class="badge ${isUnlocked ? "good" : "warn"}">${isUnlocked ? "Unlocked" : "Locked"}</span>
            </div>
            <div class="sep"></div>
            <button class="menu-item" type="button" data-prof-action="settings">
              ${icon("settings", "ico-sm")}
              <span>Settings &amp; Appearance</span>
            </button>
            <button class="menu-item" type="button" data-prof-action="toggle-lock">
              ${icon("lock", "ico-sm")}
              <span>${isUnlocked ? "Lock profile" : "Unlock profile"}</span>
            </button>
          </div>
        `
        : ""
    }

    <div class="foot">
      <div class="foot-actions">
        <button
          id="rail-open-brain-btn"
          class="icon-btn ${state.showBrainView ? "active" : ""}"
          type="button"
          title="Satz Brain (${MOD_LABEL}+B)"
        >
          ${icon("brain")}
        </button>
        <button
          id="rail-open-knowledge-btn"
          class="icon-btn ${state.showKnowledgeView ? "active" : ""}"
          type="button"
          title="Settings &amp; Models"
        >
          ${icon("settings")}
        </button>
        <button
          id="rail-telemetry-btn"
          class="icon-btn ${state.telemetryOpen ? "active" : ""}"
          type="button"
          title="Model, context &amp; logs"
          aria-expanded="${state.telemetryOpen ? "true" : "false"}"
        >
          ${icon("pulse")}
          <i id="rail-telemetry-dot" class="dot"></i>
        </button>
      </div>
      <button
        id="rail-profile-btn"
        class="prof"
        type="button"
        title="Profile (${escapeHtml(profileName)})"
        aria-expanded="${state.profileMenuOpen ? "true" : "false"}"
      >
        <span class="avatar">${escapeHtml(avatarInitial)}</span>
        <span class="truncate">${escapeHtml(profileName)}</span>
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
  const isPinnedSystem = isMail || isNews;
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

  const displayTitle = isMail
    ? state.mailAccounts.length > 0
      ? "All mail"
      : "Mail"
    : isNews
      ? "News"
      : c.title;

  const countLabel = isMail
    ? String(totalUnread)
    : isNews
      ? String(newsCount)
      : srcCount > 0
        ? `${srcCount} src`
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
                title="${escapeHtml(acctName)} (${acct.message_count ?? 0} messages)"
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
        ${convRunning ? `<i class="dot live" title="Generation in progress"></i>` : ""}
        ${hasWatchBadge ? `<i class="dot warn" title="Watched page changed"></i>` : ""}
        ${
          isRenaming
            ? `<input id="rail-rename-input-${escapeHtml(c.id)}" class="input row-rename-input" type="text" value="${escapeHtml(c.title)}" />`
            : `<span class="row-title">${escapeHtml(displayTitle)}</span>`
        }
        <span class="row-meta">${escapeHtml(countLabel)}</span>
        ${
          isPinnedSystem
            ? ""
            : `<button class="row-menu" type="button" data-menu-conv-id="${escapeHtml(c.id)}" title="Actions">${icon("more", "ico-sm")}</button>`
        }
      </div>
      ${
        menuOpen
          ? `
            <div class="menu row-menu-pop">
              <button class="menu-item" type="button" data-action-pin="${escapeHtml(c.id)}">${c.pinned ? "Unpin" : "Pin"}</button>
              <button class="menu-item" type="button" data-action-rename="${escapeHtml(c.id)}">Rename</button>
              <button class="menu-item" type="button" data-action-archive="${escapeHtml(c.id)}" data-archived="${c.status === "archived" ? "1" : "0"}">${c.status === "archived" ? "Restore" : "Archive"}</button>
              <button class="menu-item" type="button" data-action-delete="${escapeHtml(c.id)}">Delete</button>
            </div>
          `
          : ""
      }
      ${mailAccountSubrowsHtml}
    </div>
  `;
}

function bindRailEvents(container: HTMLElement, actions: RailActions): void {
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
        if (!state.showKnowledgeView) {
          actions.onOpenKnowledgeView();
        } else {
          renderRail(actions);
        }
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
  });

  container.querySelectorAll("[data-remove-bookmark]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const id = (btn as HTMLElement).getAttribute("data-remove-bookmark");
      if (id) actions.onRemoveBookmark(id);
    });
  });
}
