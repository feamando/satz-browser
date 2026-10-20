import {
  escapeHtml,
  extractDomain,
  formatRelativeTime,
  MOD_LABEL,
  state,
} from "./state";
import type { Conversation } from "./types";

export interface RailActions {
  onSelectConversation: (id: string) => void;
  onNewConversation: () => void;
  onTogglePin: (id: string) => void;
  onRenameConversation: (id: string, newTitle: string) => void;
  onToggleArchive: (id: string, archived: boolean) => void;
  onDeleteConversation: (id: string) => void;
  onOpenBookmark: (url: string) => void;
  onBookmarkCurrent: () => void;
  onRemoveBookmark: (id: string) => void;
  onOpenKnowledgeView: () => void;
}

export function renderRail(actions: RailActions): void {
  const container = document.getElementById("region-rail");
  if (!container) return;

  const q = state.railFilter.trim().toLowerCase();
  const visibleConvs = state.conversations.filter((c) => {
    if (!state.showArchived && c.status === "archived") return false;
    if (q && !c.title.toLowerCase().includes(q)) return false;
    return true;
  });

  const pinned = visibleConvs.filter((c) => c.pinned && c.status === "active");
  const recent = visibleConvs.filter((c) => !c.pinned && c.status === "active");
  const archived = visibleConvs.filter((c) => c.status === "archived");

  const activeId = state.activeDetail?.conversation.id ?? null;

  container.innerHTML = `
    <div class="rail-header">
      <span>satz</span>
      <span class="muted">[${MOD_LABEL}+k]</span>
    </div>

    <div class="rail-controls">
      <div class="rail-filter-row">
        <span class="muted">&gt;</span>
        <input
          id="rail-filter-input"
          class="rail-filter-input"
          type="text"
          placeholder="filter conversations_"
          value="${escapeHtml(state.railFilter)}"
        />
      </div>
      <button id="rail-new-conv-btn" class="rail-btn-full">
        <span>[+ new conversation]</span>
        <span class="muted">[${MOD_LABEL}+n]</span>
      </button>
    </div>

    <div class="rail-scroll">
      <div class="rail-group">
        <div class="rail-group-label">
          <span>conversations</span>
        </div>

        <div class="rail-group-label">
          <span>pinned</span>
          <span>${pinned.length}</span>
        </div>
        ${
          pinned.length === 0
            ? `<div class="muted" id="rail-empty-pinned">  (none)</div>`
            : pinned
                .map((c) => renderConversationRow(c, c.id === activeId, true))
                .join("")
        }

        <div class="rail-group-label">
          <span>recent</span>
          <span>${recent.length}</span>
        </div>
        ${
          recent.length === 0
            ? `<div class="muted" id="rail-empty-recent">  (none)</div>`
            : recent
                .map((c) => renderConversationRow(c, c.id === activeId, false))
                .join("")
        }

        ${
          state.showArchived
            ? `
          <div class="rail-group-label">
            <span>archived</span>
            <span>${archived.length}</span>
          </div>
          ${archived.map((c) => renderConversationRow(c, c.id === activeId, false)).join("")}
        `
            : ""
        }

        <button id="rail-toggle-archived" class="rail-btn-full muted">
          <span>[${state.showArchived ? "hide archived" : "show archived"}]</span>
        </button>
      </div>

      <div class="rail-group">
        <div class="rail-group-label">
          <span>bookmarks</span>
          <span>${state.bookmarks.length}</span>
        </div>
        ${
          state.bookmarks.length === 0
            ? `<div class="muted">  (none)</div>`
            : state.bookmarks
                .map(
                  (b) => `
              <div class="rail-row" data-bookmark-url="${escapeHtml(b.url)}">
                <span class="rail-row-title">${escapeHtml(b.title || extractDomain(b.url))}</span>
                <button class="rail-menu-btn" data-remove-bookmark="${escapeHtml(b.id)}" title="remove bookmark">x</button>
              </div>
            `
                )
                .join("")
        }
        <button id="rail-bookmark-current-btn" class="rail-btn-full">
          <span>[+ bookmark current]</span>
          <span class="muted">[${MOD_LABEL}+d]</span>
        </button>
      </div>
    </div>

    <div class="rail-footer">
      <button id="rail-open-knowledge-btn" class="${state.showKnowledgeView ? "active" : ""}">
        [knowledge]
      </button>
      <span>v0.3</span>
    </div>
  `;

  bindRailEvents(container, actions);
}

function renderConversationRow(
  c: Conversation,
  isActive: boolean,
  isPinned: boolean
): string {
  const prefix = isPinned ? "* " : "  ";
  const srcCount = c.source_count ?? 0;
  const relTime = formatRelativeTime(c.last_active_at || c.created_at);
  const menuOpen = state.openMenuConvId === c.id;
  const isRenaming = state.renamingConvId === c.id;

  return `
    <div>
      <div class="rail-row ${isActive && !state.showKnowledgeView ? "active" : ""}" data-conv-id="${escapeHtml(c.id)}">
        ${
          isRenaming
            ? `<input id="rail-rename-input-${escapeHtml(c.id)}" class="rail-rename-input" type="text" value="${escapeHtml(c.title)}" />`
            : `<span class="rail-row-title">${prefix}${escapeHtml(c.title)}</span>`
        }
        <span class="rail-row-meta rail-row-src-count">${srcCount} src</span>
        <span class="rail-row-time">${escapeHtml(relTime)}</span>
        <button class="rail-menu-btn" data-menu-conv-id="${escapeHtml(c.id)}">...</button>
      </div>
      ${
        menuOpen
          ? `
        <div class="rail-popover-menu">
          <button data-action-pin="${escapeHtml(c.id)}">[${c.pinned ? "unpin" : "pin"}]</button>
          <button data-action-rename="${escapeHtml(c.id)}">[rename]</button>
          <button data-action-archive="${escapeHtml(c.id)}" data-archived="${c.status === "archived" ? "1" : "0"}">[${c.status === "archived" ? "unarchive" : "archive"}]</button>
          <button data-action-delete="${escapeHtml(c.id)}">[delete]</button>
        </div>
      `
          : ""
      }
    </div>
  `;
}

function bindRailEvents(container: HTMLElement, actions: RailActions): void {
  const filterInput = container.querySelector(
    "#rail-filter-input"
  ) as HTMLInputElement | null;
  if (filterInput) {
    filterInput.addEventListener("input", () => {
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
  }

  container
    .querySelector("#rail-new-conv-btn")
    ?.addEventListener("click", () => {
      actions.onNewConversation();
    });

  container
    .querySelector("#rail-toggle-archived")
    ?.addEventListener("click", () => {
      state.showArchived = !state.showArchived;
      renderRail(actions);
    });

  container
    .querySelector("#rail-bookmark-current-btn")
    ?.addEventListener("click", () => {
      actions.onBookmarkCurrent();
    });

  container
    .querySelector("#rail-open-knowledge-btn")
    ?.addEventListener("click", () => {
      actions.onOpenKnowledgeView();
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
      const id = (row as HTMLElement).getAttribute("data-conv-id");
      if (id) {
        state.openMenuConvId = null;
        actions.onSelectConversation(id);
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
