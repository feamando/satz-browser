import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type {
  AttachedPage,
  ChildPaneEventPayload,
  Conversation,
  ConversationBundle,
  PaneBoundsSpec,
  ViewMode,
} from "./types";

class SatzShellApp {
  private conversations: Conversation[] = [];
  private activeBundle: ConversationBundle | null = null;
  private filterQuery = "";
  private showNewIntentCreator = false;
  private viewMode: ViewMode = "thread";
  private focusPaneIndex = 0;
  private focusSideRailOpen = true;
  private comparePaneCount: 2 | 3 | 4 = 2;
  private dbPath = "";
  private resizeObserver: ResizeObserver | null = null;
  private syncTimer: number | null = null;

  async init() {
    this.setupGlobalKeyboardShortcuts();
    this.setupResizeHandling();

    await listen<ChildPaneEventPayload>("child-pane-event", (event) => {
      this.handleChildPaneEvent(event.payload);
    });

    try {
      this.dbPath = await invoke<string>("get_db_path");
    } catch {
      this.dbPath = "Local AppData/satz.db";
    }

    await this.reloadConversations();
    if (this.conversations.length > 0) {
      await this.selectConversation(this.conversations[0].id);
    } else {
      this.render();
    }
  }

  private setupGlobalKeyboardShortcuts() {
    window.addEventListener("keydown", (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();

      // Ctrl+K: Filter left conversation rail
      if (e.ctrlKey && !e.shiftKey && key === "k") {
        e.preventDefault();
        const searchInput = document.getElementById(
          "rail-search-input"
        ) as HTMLInputElement | null;
        if (searchInput) {
          searchInput.focus();
          searchInput.select();
        }
        return;
      }

      // Ctrl+N: New Intent / Conversation
      if (e.ctrlKey && !e.shiftKey && key === "n") {
        e.preventDefault();
        this.showNewIntentCreator = true;
        this.render();
        setTimeout(() => {
          const input = document.getElementById(
            "new-intent-title-input"
          ) as HTMLInputElement | null;
          input?.focus();
        }, 20);
        return;
      }

      // Ctrl+F: Toggle Focus Mode
      if (e.ctrlKey && !e.shiftKey && key === "f") {
        e.preventDefault();
        this.setViewMode(this.viewMode === "focus" ? "thread" : "focus");
        return;
      }

      // Ctrl+M: Toggle Compare View (2 to 4 tiled WebView2 panes)
      if (e.ctrlKey && !e.shiftKey && key === "m") {
        e.preventDefault();
        this.setViewMode(this.viewMode === "compare" ? "thread" : "compare");
        return;
      }

      // Ctrl+L: Focus URL bar in Focus Mode or Compare Mode
      if (e.ctrlKey && !e.shiftKey && key === "l") {
        e.preventDefault();
        const urlInput = document.querySelector(
          ".url-input"
        ) as HTMLInputElement | null;
        if (urlInput) {
          urlInput.focus();
          urlInput.select();
        }
        return;
      }

      // Alt+2 / Alt+3 / Alt+4: Switch Compare View tile count
      if (e.altKey && (key === "2" || key === "3" || key === "4")) {
        e.preventDefault();
        this.comparePaneCount = Number(key) as 2 | 3 | 4;
        if (this.viewMode !== "compare") {
          this.setViewMode("compare");
        } else {
          this.render();
        }
        return;
      }

      // Escape in New Intent creator or return to Thread mode
      if (e.key === "Escape" && this.showNewIntentCreator) {
        this.showNewIntentCreator = false;
        this.render();
      }
    });
  }

  private setupResizeHandling() {
    window.addEventListener("resize", () => {
      this.scheduleWebviewSync();
    });
    this.resizeObserver = new ResizeObserver(() => {
      this.scheduleWebviewSync();
    });
  }

  private scheduleWebviewSync() {
    if (this.syncTimer !== null) {
      window.clearTimeout(this.syncTimer);
    }
    this.syncTimer = window.setTimeout(() => {
      this.syncChildWebviews();
    }, 30);
  }

  private async handleChildPaneEvent(payload: ChildPaneEventPayload) {
    if (!this.activeBundle) return;
    const page = this.getOrCreatePageForPane(payload.pane_index);
    let changed = false;

    if (payload.url && payload.url !== page.url) {
      page.url = payload.url;
      changed = true;
      const inputEl = document.getElementById(
        `pane-url-input-${payload.pane_index}`
      ) as HTMLInputElement | null;
      if (inputEl && document.activeElement !== inputEl) {
        inputEl.value = payload.url;
      }
    }

    if (payload.title && payload.title !== page.title) {
      page.title = payload.title;
      changed = true;
    }

    if (changed) {
      try {
        await invoke("upsert_attached_page", {
          conversationId: this.activeBundle.conversation.id,
          paneIndex: payload.pane_index,
          url: page.url,
          title: page.title,
        });
      } catch (err) {
        console.warn("Failed to persist attached page update:", err);
      }
    }
  }

  private async reloadConversations() {
    this.conversations = await invoke<Conversation[]>("list_conversations");
  }

  private async selectConversation(conversationId: string) {
    this.activeBundle = await invoke<ConversationBundle>(
      "get_conversation_bundle",
      {
        conversationId,
      }
    );
    this.render();
  }

  private setViewMode(mode: ViewMode) {
    this.viewMode = mode;
    this.render();
  }

  private getOrCreatePageForPane(paneIndex: number): AttachedPage {
    const defaults = [
      "https://v2.tauri.app/learn/",
      "https://en.wikipedia.org/wiki/Microsoft_Edge_WebView2",
      "https://news.ycombinator.com/",
      "https://www.dw.com/en/",
    ];
    if (!this.activeBundle) {
      return {
        id: `temp-${paneIndex}`,
        conversation_id: "",
        url: defaults[paneIndex] || "https://en.wikipedia.org",
        title: `Pane ${paneIndex + 1}`,
        pane_index: paneIndex,
      };
    }
    const existing = this.activeBundle.attached_pages.find(
      (p) => p.pane_index === paneIndex
    );
    if (existing) return existing;

    const fallback: AttachedPage = {
      id: `page-${this.activeBundle.conversation.id}-${paneIndex}`,
      conversation_id: this.activeBundle.conversation.id,
      url: defaults[paneIndex] || "https://en.wikipedia.org",
      title: `Source Pane ${paneIndex + 1}`,
      pane_index: paneIndex,
    };
    this.activeBundle.attached_pages.push(fallback);
    return fallback;
  }

  private async syncChildWebviews() {
    if (this.viewMode === "thread" || !this.activeBundle) {
      await invoke("hide_all_child_panes");
      return;
    }

    const specs: PaneBoundsSpec[] = [];

    if (this.viewMode === "focus") {
      const slot = document.getElementById("focus-webview-slot");
      if (slot) {
        const rect = slot.getBoundingClientRect();
        const page = this.getOrCreatePageForPane(this.focusPaneIndex);
        specs.push({
          pane_index: this.focusPaneIndex,
          url: page.url,
          x: Math.round(rect.left),
          y: Math.round(rect.top),
          width: Math.max(0, Math.round(rect.width)),
          height: Math.max(0, Math.round(rect.height)),
        });
      }
    } else if (this.viewMode === "compare") {
      for (let i = 0; i < this.comparePaneCount; i++) {
        const slot = document.getElementById(`compare-webview-slot-${i}`);
        if (slot) {
          const rect = slot.getBoundingClientRect();
          const page = this.getOrCreatePageForPane(i);
          specs.push({
            pane_index: i,
            url: page.url,
            x: Math.round(rect.left),
            y: Math.round(rect.top),
            width: Math.max(0, Math.round(rect.width)),
            height: Math.max(0, Math.round(rect.height)),
          });
        }
      }
    }

    try {
      await invoke("sync_child_panes", { panes: specs });
    } catch (err) {
      console.error("Failed to sync WebView2 child panes:", err);
    }
  }

  private async navigatePane(paneIndex: number, rawUrl: string) {
    if (!this.activeBundle) return;
    try {
      const updated = await invoke<AttachedPage>("navigate_child_pane", {
        conversationId: this.activeBundle.conversation.id,
        paneIndex,
        url: rawUrl,
        title: null,
      });
      const idx = this.activeBundle.attached_pages.findIndex(
        (p) => p.pane_index === paneIndex
      );
      if (idx >= 0) {
        this.activeBundle.attached_pages[idx] = updated;
      } else {
        this.activeBundle.attached_pages.push(updated);
      }
      const inputEl = document.getElementById(
        `pane-url-input-${paneIndex}`
      ) as HTMLInputElement | null;
      if (inputEl) {
        inputEl.value = updated.url;
      }
    } catch (err) {
      console.error("Navigation error:", err);
    }
  }

  private async controlPane(
    paneIndex: number,
    action: "back" | "forward" | "reload"
  ) {
    try {
      await invoke("control_child_pane", { paneIndex, action });
    } catch (err) {
      console.error("Pane control error:", err);
    }
  }

  private escapeHtml(str: string): string {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  private render() {
    const appEl = document.getElementById("app");
    if (!appEl) return;

    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }

    const filtered = this.conversations.filter((c) =>
      c.intent_title.toLowerCase().includes(this.filterQuery.toLowerCase())
    );
    const pinnedConvs = filtered.filter((c) => c.pinned);
    const unpinnedConvs = filtered.filter((c) => !c.pinned);

    const activeConv = this.activeBundle?.conversation ?? null;

    appEl.innerHTML = `
      <div class="shell-root">
        <!-- Left Conversation Rail -->
        <aside class="left-rail">
          <div class="rail-brand">
            <div class="brand-title">
              <span class="brand-dot"></span>
              <span>SATZ</span>
            </div>
            <span class="phase-badge">PHASE 0 · SHELL</span>
          </div>

          <div class="rail-controls">
            <div class="search-box-wrap">
              <input
                id="rail-search-input"
                class="rail-search-input"
                type="text"
                placeholder="Filter conversations..."
                value="${this.escapeHtml(this.filterQuery)}"
              />
              <span class="kbd-hint">Ctrl+K</span>
            </div>
            <button id="btn-open-new-intent" class="btn-new-intent">
              <span>+ New Intent</span>
              <span style="font-family: var(--font-mono); font-size: 10px;">Ctrl+N</span>
            </button>
          </div>

          ${
            this.showNewIntentCreator
              ? `
            <div class="new-intent-panel">
              <input
                id="new-intent-title-input"
                type="text"
                placeholder="Intent (e.g. Flights Berlin → Lisbon)"
              />
              <input
                id="new-intent-url-input"
                type="text"
                placeholder="Starting URL (optional)"
                value="https://en.wikipedia.org/wiki/Main_Page"
              />
              <div class="new-intent-actions">
                <button id="btn-cancel-intent" class="btn-small">Cancel</button>
                <button id="btn-create-intent" class="btn-primary">Create</button>
              </div>
            </div>
          `
              : ""
          }

          <div class="rail-list-container">
            ${
              pinnedConvs.length > 0
                ? `
              <div>
                <div class="rail-section-label">Pinned Intents (${pinnedConvs.length})</div>
                <div class="conv-list">
                  ${pinnedConvs.map((c) => this.renderConvRailItem(c, activeConv?.id === c.id)).join("")}
                </div>
              </div>
            `
                : ""
            }

            <div>
              <div class="rail-section-label">Active Conversations (${unpinnedConvs.length})</div>
              <div class="conv-list">
                ${
                  unpinnedConvs.length > 0
                    ? unpinnedConvs
                        .map((c) =>
                          this.renderConvRailItem(c, activeConv?.id === c.id)
                        )
                        .join("")
                    : `<div style="color: var(--text-muted); padding: 6px 4px; font-size: 11.5px;">No matching conversations.</div>`
                }
              </div>
            </div>
          </div>

          <div class="rail-footer">
            <div class="shortcut-grid">
              <span>Ctrl+K Filter</span>
              <span>Ctrl+N Intent</span>
              <span>Ctrl+F Focus</span>
              <span>Ctrl+M Compare</span>
            </div>
            <div style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${this.escapeHtml(this.dbPath)}">
              SQLite: ${this.escapeHtml(this.dbPath.split(/[\\/]/).slice(-2).join("/"))}
            </div>
          </div>
        </aside>

        <!-- Main Workspace -->
        <main class="workspace-main">
          <header class="top-header-bar">
            <div class="active-intent-info">
              <span class="phase-badge">${activeConv?.pinned ? "PINNED" : "INTENT"}</span>
              <span class="active-intent-title">${
                activeConv
                  ? this.escapeHtml(activeConv.intent_title)
                  : "Select or create a conversation"
              }</span>
            </div>

            <div class="mode-switcher">
              <button
                id="mode-btn-thread"
                class="mode-btn ${this.viewMode === "thread" ? "active" : ""}"
              >
                <span>Thread</span>
              </button>
              <button
                id="mode-btn-focus"
                class="mode-btn ${this.viewMode === "focus" ? "active" : ""}"
              >
                <span>Focus Mode</span>
                <span class="mode-kbd">Ctrl+F</span>
              </button>
              <button
                id="mode-btn-compare"
                class="mode-btn ${this.viewMode === "compare" ? "active" : ""}"
              >
                <span>Compare (${this.comparePaneCount})</span>
                <span class="mode-kbd">Ctrl+M</span>
              </button>
            </div>
          </header>

          <div class="viewport-body" id="viewport-body">
            ${this.renderViewportContent()}
          </div>
        </main>
      </div>
    `;

    this.bindEvents();
    this.scheduleWebviewSync();
  }

  private renderConvRailItem(c: Conversation, isActive: boolean): string {
    return `
      <div class="conv-item ${isActive ? "active" : ""}" data-conv-id="${this.escapeHtml(c.id)}">
        <div class="conv-item-main">
          <div class="conv-title">${this.escapeHtml(c.intent_title)}</div>
          <div class="conv-meta">
            <span>${this.escapeHtml(c.status)}</span>
          </div>
        </div>
        <div class="conv-item-actions">
          <button
            class="icon-btn ${c.pinned ? "pinned" : ""}"
            data-pin-id="${this.escapeHtml(c.id)}"
            title="${c.pinned ? "Unpin" : "Pin conversation"}"
          >★</button>
          <button
            class="icon-btn"
            data-del-id="${this.escapeHtml(c.id)}"
            title="Delete conversation"
          >✕</button>
        </div>
      </div>
    `;
  }

  private renderViewportContent(): string {
    if (!this.activeBundle) {
      return `
        <div class="thread-view">
          <div class="section-card">
            <div class="section-title">No Active Conversation</div>
            <p style="color: var(--text-secondary);">Press <b>Ctrl+N</b> to open a new intent conversation.</p>
          </div>
        </div>
      `;
    }

    if (this.viewMode === "thread") {
      return this.renderThreadView();
    }
    if (this.viewMode === "focus") {
      return this.renderFocusView();
    }
    return this.renderCompareView();
  }

  private renderThreadView(): string {
    if (!this.activeBundle) return "";
    const pages = [0, 1, 2, 3].map((idx) => this.getOrCreatePageForPane(idx));
    const notes = this.activeBundle.notes;
    const history = this.activeBundle.history;

    return `
      <div class="thread-view">
        <!-- Attached Sources Card -->
        <section class="section-card">
          <div class="section-header">
            <span class="section-title">Attached Sources (Live WebView2 Panes 1–4)</span>
            <div style="display: flex; gap: 8px;">
              <button class="btn-small" id="btn-thread-launch-focus">Open Focus Mode (Ctrl+F)</button>
              <button class="btn-small" id="btn-thread-launch-compare">Tile in Compare View (Ctrl+M)</button>
            </div>
          </div>
          <div class="sources-grid">
            ${pages
              .map(
                (p) => `
              <div class="source-card">
                <div class="source-pane-tag">
                  <span>PANE ${p.pane_index + 1}</span>
                  <span>WebView2</span>
                </div>
                <div class="source-title">${this.escapeHtml(p.title)}</div>
                <div class="source-url">${this.escapeHtml(p.url)}</div>
                <div class="source-actions">
                  <button class="btn-small" data-focus-pane="${p.pane_index}">Focus Pane ${p.pane_index + 1}</button>
                </div>
              </div>
            `
              )
              .join("")}
          </div>
        </section>

        <!-- Conversation Thread Notes -->
        <section class="section-card">
          <div class="section-header">
            <span class="section-title">Conversation Thread & Research Notes</span>
            <span style="font-size: 11px; color: var(--text-muted);">${notes.length} entries stored in SQLite</span>
          </div>
          <div class="notes-list">
            ${notes
              .map(
                (n) => `
              <div class="note-item ${n.author === "system" ? "system" : ""}">
                <div class="note-author">${this.escapeHtml(n.author)}</div>
                <div class="note-content">${this.escapeHtml(n.content)}</div>
              </div>
            `
              )
              .join("")}
          </div>
          <div class="note-composer">
            <input
              id="thread-note-input"
              type="text"
              placeholder="Add note or finding to this conversation thread (Enter to save)..."
            />
            <button id="btn-add-note" class="btn-primary">Add Note</button>
          </div>
        </section>

        <!-- Local SQLite History Log -->
        <section class="section-card">
          <div class="section-header">
            <span class="section-title">Conversation Browsing History</span>
            <span style="font-size: 11px; color: var(--text-muted);">Local SQLite Index</span>
          </div>
          ${
            history.length === 0
              ? `<div style="color: var(--text-muted); font-size: 12px;">Navigate in Focus Mode (Ctrl+F) or Compare View (Ctrl+M) to log visited URLs.</div>`
              : `<div class="notes-list">
                  ${history
                    .slice(0, 8)
                    .map(
                      (h) => `
                    <div style="display: flex; justify-content: space-between; font-size: 12px; padding: 4px 0; border-bottom: 1px solid var(--border-subtle);">
                      <span style="color: var(--text-primary);">${this.escapeHtml(h.title)}</span>
                      <span style="font-family: var(--font-mono); color: var(--text-secondary);">${this.escapeHtml(h.url)}</span>
                    </div>
                  `
                    )
                    .join("")}
                </div>`
          }
        </section>
      </div>
    `;
  }

  private renderFocusView(): string {
    const page = this.getOrCreatePageForPane(this.focusPaneIndex);
    const notes = this.activeBundle?.notes ?? [];

    return `
      <div class="focus-view">
        <div class="focus-browser-column">
          <div class="pane-toolbar">
            <span class="pane-badge">FOCUS · PANE ${this.focusPaneIndex + 1}</span>
            <button class="nav-btn" data-nav-action="back" data-pane="${this.focusPaneIndex}" title="Back">←</button>
            <button class="nav-btn" data-nav-action="forward" data-pane="${this.focusPaneIndex}" title="Forward">→</button>
            <button class="nav-btn" data-nav-action="reload" data-pane="${this.focusPaneIndex}" title="Reload">↻</button>
            <input
              id="pane-url-input-${this.focusPaneIndex}"
              class="url-input"
              data-url-pane="${this.focusPaneIndex}"
              type="text"
              value="${this.escapeHtml(page.url)}"
              placeholder="Enter URL or search query (Ctrl+L)..."
            />
            <div style="display: flex; gap: 4px;">
              ${[0, 1, 2, 3]
                .map(
                  (idx) => `
                <button
                  class="btn-small ${this.focusPaneIndex === idx ? "active" : ""}"
                  style="${this.focusPaneIndex === idx ? "border-color: var(--accent); color: var(--accent);" : ""}"
                  data-switch-focus-pane="${idx}"
                >P${idx + 1}</button>
              `
                )
                .join("")}
            </div>
            <button id="btn-toggle-focus-rail" class="btn-small">
              ${this.focusSideRailOpen ? "Hide Rail" : "Show Rail"}
            </button>
          </div>
          <div id="focus-webview-slot" class="webview-host-slot">
            Mounting native WebView2 child pane ${this.focusPaneIndex + 1} (${this.escapeHtml(page.url)})...
          </div>
        </div>

        ${
          this.focusSideRailOpen
            ? `
          <aside class="focus-side-rail">
            <div class="rail-section-label">Thread Context (Beside Live Page)</div>
            <div class="notes-list" style="flex: 1; overflow-y: auto;">
              ${notes
                .map(
                  (n) => `
                <div class="note-item ${n.author === "system" ? "system" : ""}">
                  <div class="note-author">${this.escapeHtml(n.author)}</div>
                  <div class="note-content">${this.escapeHtml(n.content)}</div>
                </div>
              `
                )
                .join("")}
            </div>
            <div class="note-composer">
              <input
                id="focus-note-input"
                type="text"
                placeholder="Clip note from page..."
              />
              <button id="btn-focus-add-note" class="btn-primary">+</button>
            </div>
          </aside>
        `
            : ""
        }
      </div>
    `;
  }

  private renderCompareView(): string {
    const indices = Array.from({ length: this.comparePaneCount }, (_, i) => i);

    return `
      <div class="compare-view">
        <div class="compare-header-bar">
          <div style="display: flex; align-items: center; gap: 10px;">
            <span class="pane-badge">COMPARE VIEW · ${this.comparePaneCount} LIVE WEBVIEW2 PANES</span>
            <span style="color: var(--text-secondary); font-size: 12px;">Side-by-side multi-webview tiling inside active conversation</span>
          </div>
          <div style="display: flex; align-items: center; gap: 6px;">
            <span style="font-size: 11px; color: var(--text-muted);">Tiles:</span>
            ${([2, 3, 4] as const)
              .map(
                (cnt) => `
              <button
                class="btn-small"
                style="${this.comparePaneCount === cnt ? "border-color: var(--accent); color: var(--accent);" : ""}"
                data-compare-count="${cnt}"
              >${cnt} Panes (Alt+${cnt})</button>
            `
              )
              .join("")}
          </div>
        </div>

        <div class="compare-grid panes-${this.comparePaneCount}">
          ${indices
            .map((idx) => {
              const p = this.getOrCreatePageForPane(idx);
              return `
                <div class="compare-tile">
                  <div class="pane-toolbar">
                    <span class="pane-badge">P${idx + 1}</span>
                    <button class="nav-btn" data-nav-action="back" data-pane="${idx}" title="Back">←</button>
                    <button class="nav-btn" data-nav-action="forward" data-pane="${idx}" title="Forward">→</button>
                    <button class="nav-btn" data-nav-action="reload" data-pane="${idx}" title="Reload">↻</button>
                    <input
                      id="pane-url-input-${idx}"
                      class="url-input"
                      data-url-pane="${idx}"
                      type="text"
                      value="${this.escapeHtml(p.url)}"
                    />
                    <button class="btn-small" data-focus-pane="${idx}" title="Maximize this pane in Focus Mode">Focus</button>
                  </div>
                  <div id="compare-webview-slot-${idx}" class="webview-host-slot">
                    Mounting WebView2 Tile ${idx + 1} (${this.escapeHtml(p.url)})...
                  </div>
                </div>
              `;
            })
            .join("")}
        </div>
      </div>
    `;
  }

  private bindEvents() {
    // Filter input
    const searchInput = document.getElementById(
      "rail-search-input"
    ) as HTMLInputElement | null;
    if (searchInput) {
      searchInput.addEventListener("input", () => {
        const pos = searchInput.selectionStart ?? searchInput.value.length;
        this.filterQuery = searchInput.value;
        this.render();
        const nextInput = document.getElementById(
          "rail-search-input"
        ) as HTMLInputElement | null;
        if (nextInput) {
          nextInput.focus();
          nextInput.setSelectionRange(pos, pos);
        }
      });
    }

    // New Intent buttons
    document
      .getElementById("btn-open-new-intent")
      ?.addEventListener("click", () => {
        this.showNewIntentCreator = !this.showNewIntentCreator;
        this.render();
        if (this.showNewIntentCreator) {
          setTimeout(() => {
            document.getElementById("new-intent-title-input")?.focus();
          }, 20);
        }
      });

    document
      .getElementById("btn-cancel-intent")
      ?.addEventListener("click", () => {
        this.showNewIntentCreator = false;
        this.render();
      });

    const submitNewIntent = async () => {
      const titleEl = document.getElementById(
        "new-intent-title-input"
      ) as HTMLInputElement | null;
      const urlEl = document.getElementById(
        "new-intent-url-input"
      ) as HTMLInputElement | null;
      const title = titleEl?.value.trim() || "Untitled Intent";
      const initialUrl = urlEl?.value.trim() || null;

      const created = await invoke<Conversation>("create_conversation", {
        intentTitle: title,
        initialUrl,
      });
      this.showNewIntentCreator = false;
      await this.reloadConversations();
      await this.selectConversation(created.id);
    };

    document
      .getElementById("btn-create-intent")
      ?.addEventListener("click", submitNewIntent);
    document
      .getElementById("new-intent-title-input")
      ?.addEventListener("keydown", (e) => {
        if ((e as KeyboardEvent).key === "Enter") {
          submitNewIntent();
        }
      });

    // Conversation rail selection, pin, delete
    document.querySelectorAll("[data-conv-id]").forEach((el) => {
      el.addEventListener("click", (e) => {
        const target = e.target as HTMLElement;
        if (target.closest("[data-pin-id]") || target.closest("[data-del-id]")) {
          return;
        }
        const id = (el as HTMLElement).getAttribute("data-conv-id");
        if (id) this.selectConversation(id);
      });
    });

    document.querySelectorAll("[data-pin-id]").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const id = (btn as HTMLElement).getAttribute("data-pin-id");
        if (!id) return;
        await invoke("toggle_pin_conversation", { conversationId: id });
        await this.reloadConversations();
        if (this.activeBundle?.conversation.id === id) {
          await this.selectConversation(id);
        } else {
          this.render();
        }
      });
    });

    document.querySelectorAll("[data-del-id]").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const id = (btn as HTMLElement).getAttribute("data-del-id");
        if (!id) return;
        await invoke("delete_conversation", { conversationId: id });
        await this.reloadConversations();
        if (this.activeBundle?.conversation.id === id) {
          if (this.conversations.length > 0) {
            await this.selectConversation(this.conversations[0].id);
          } else {
            this.activeBundle = null;
            this.render();
          }
        } else {
          this.render();
        }
      });
    });

    // Mode switcher buttons
    document
      .getElementById("mode-btn-thread")
      ?.addEventListener("click", () => this.setViewMode("thread"));
    document
      .getElementById("mode-btn-focus")
      ?.addEventListener("click", () => this.setViewMode("focus"));
    document
      .getElementById("mode-btn-compare")
      ?.addEventListener("click", () => this.setViewMode("compare"));

    document
      .getElementById("btn-thread-launch-focus")
      ?.addEventListener("click", () => this.setViewMode("focus"));
    document
      .getElementById("btn-thread-launch-compare")
      ?.addEventListener("click", () => this.setViewMode("compare"));

    // Focus specific pane from Thread or Compare
    document.querySelectorAll("[data-focus-pane]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number((btn as HTMLElement).getAttribute("data-focus-pane"));
        this.focusPaneIndex = idx;
        this.setViewMode("focus");
      });
    });

    // Switch active pane inside Focus Mode
    document.querySelectorAll("[data-switch-focus-pane]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(
          (btn as HTMLElement).getAttribute("data-switch-focus-pane")
        );
        this.focusPaneIndex = idx;
        this.render();
      });
    });

    // Toggle side rail in Focus Mode
    document
      .getElementById("btn-toggle-focus-rail")
      ?.addEventListener("click", () => {
        this.focusSideRailOpen = !this.focusSideRailOpen;
        this.render();
      });

    // Compare pane count selector (2, 3, 4)
    document.querySelectorAll("[data-compare-count]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const cnt = Number(
          (btn as HTMLElement).getAttribute("data-compare-count")
        ) as 2 | 3 | 4;
        this.comparePaneCount = cnt;
        this.render();
      });
    });

    // Pane navigation controls (Back / Forward / Reload)
    document.querySelectorAll("[data-nav-action]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const action = (btn as HTMLElement).getAttribute("data-nav-action") as
          | "back"
          | "forward"
          | "reload";
        const paneIdx = Number((btn as HTMLElement).getAttribute("data-pane"));
        this.controlPane(paneIdx, action);
      });
    });

    // URL inputs (Enter to navigate)
    document.querySelectorAll("[data-url-pane]").forEach((input) => {
      input.addEventListener("keydown", (e) => {
        if ((e as KeyboardEvent).key === "Enter") {
          const el = input as HTMLInputElement;
          const paneIdx = Number(el.getAttribute("data-url-pane"));
          this.navigatePane(paneIdx, el.value);
        }
      });
    });

    // Thread note composer (in Thread Mode and Focus Side Rail)
    const addNoteFromInput = async (inputId: string) => {
      if (!this.activeBundle) return;
      const inputEl = document.getElementById(
        inputId
      ) as HTMLInputElement | null;
      const content = inputEl?.value.trim();
      if (!content) return;
      await invoke("add_thread_note", {
        conversationId: this.activeBundle.conversation.id,
        author: "user",
        content,
      });
      await this.selectConversation(this.activeBundle.conversation.id);
    };

    document
      .getElementById("btn-add-note")
      ?.addEventListener("click", () => addNoteFromInput("thread-note-input"));
    document
      .getElementById("thread-note-input")
      ?.addEventListener("keydown", (e) => {
        if ((e as KeyboardEvent).key === "Enter") {
          addNoteFromInput("thread-note-input");
        }
      });

    document
      .getElementById("btn-focus-add-note")
      ?.addEventListener("click", () => addNoteFromInput("focus-note-input"));
    document
      .getElementById("focus-note-input")
      ?.addEventListener("keydown", (e) => {
        if ((e as KeyboardEvent).key === "Enter") {
          addNoteFromInput("focus-note-input");
        }
      });

    // Observe WebView2 host slots for resize changes
    if (this.resizeObserver) {
      document.querySelectorAll(".webview-host-slot").forEach((slot) => {
        this.resizeObserver?.observe(slot);
      });
    }
  }
}

window.addEventListener("DOMContentLoaded", () => {
  const app = new SatzShellApp();
  app.init();
});
