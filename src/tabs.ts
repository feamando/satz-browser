import { apiSyncTabWebviews } from "./api";
import { isModKey } from "./keys";
import { escapeHtml, extractDomain, MOD_LABEL, state } from "./state";
import type { TabBoundsSpec } from "./types";

export interface TabStripActions {
  onSelectTab: (tabId: string) => void;
  onToggleCompareCandidate: (tabId: string) => void;
  onNewTab: () => void;
  onCloseTab: (tabId: string) => void;
  onToggleCompareMode: () => void;
}

export function renderTabStrip(actions: TabStripActions): void {
  const container = document.getElementById("region-tab-strip");
  if (!container) return;

  const detail = state.activeDetail;
  if (!detail || state.showKnowledgeView) {
    container.innerHTML = `
      <div class="tab-strip-left">
        <span class="muted">${state.showKnowledgeView ? "knowledge base" : "start screen"}</span>
      </div>
      <div class="tab-strip-right"></div>
    `;
    return;
  }

  const openTabs = detail.tabs.filter((t) => t.is_open);
  const isChatActive = state.activeTabId === "chat" && !state.compareMode;

  container.innerHTML = `
    <div class="tab-strip-left">
      <div class="tab-item ${isChatActive ? "active" : ""}" data-tab-id="chat">
        <span>[ chat ]</span>
      </div>
      ${openTabs
        .map((tab, idx) => {
          const isActive =
            !state.compareMode && state.activeTabId === tab.id;
          const isSelectedForCompare = state.compareTabIds.includes(tab.id);
          const domain = extractDomain(tab.url);
          const shortTitle = (tab.title || domain).slice(0, 22);
          return `
            <div
              class="tab-item ${isActive ? "active" : ""} ${isSelectedForCompare ? "selected-compare" : ""}"
              data-site-tab-id="${escapeHtml(tab.id)}"
              title="source [${idx + 1}] in chat context · ${escapeHtml(tab.title || tab.url)}"
            >
              <span class="truncate">[${idx + 1}] ${escapeHtml(domain)} · ${escapeHtml(shortTitle)}</span>
              <button class="tab-close-btn" data-close-tab-id="${escapeHtml(tab.id)}" title="close tab and remove from context">x</button>
            </div>
          `;
        })
        .join("")}
      <button id="tab-strip-add-btn" title="new tab [${MOD_LABEL}+t]">[ + ]</button>
    </div>

    <div class="tab-strip-right">
      <button
        id="tab-strip-compare-btn"
        class="${state.compareMode ? "active" : ""}"
        title="select 2-4 tabs with ${MOD_LABEL}+click then press ${MOD_LABEL}+m"
      >
        compare: ${state.compareTabIds.length >= 2 ? `${state.compareTabIds.length} tabs` : "select tabs"} [${MOD_LABEL}+m]
      </button>
    </div>
  `;

  container.querySelector('[data-tab-id="chat"]')?.addEventListener("click", () => {
    actions.onSelectTab("chat");
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

  container
    .querySelector("#tab-strip-compare-btn")
    ?.addEventListener("click", () => {
      actions.onToggleCompareMode();
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
    (!state.compareMode && state.activeTabId === "chat")
  ) {
    await apiSyncTabWebviews([]);
    return;
  }

  const visible: TabBoundsSpec[] = [];

  if (state.compareMode) {
    for (const tabId of state.compareTabIds.slice(0, 4)) {
      const tab = detail.tabs.find((t) => t.id === tabId && t.is_open);
      const slot = document.getElementById(`webview-slot-${tabId}`);
      if (tab && slot) {
        const rect = slot.getBoundingClientRect();
        visible.push({
          tab_id: tab.id,
          url: tab.url,
          x: Math.round(rect.left),
          y: Math.round(rect.top),
          w: Math.max(0, Math.round(rect.width)),
          h: Math.max(0, Math.round(rect.height)),
        });
      }
    }
  } else {
    const tab = detail.tabs.find(
      (t) => t.id === state.activeTabId && t.is_open
    );
    const slot = document.getElementById(`webview-slot-${state.activeTabId}`);
    if (tab && slot) {
      const rect = slot.getBoundingClientRect();
      visible.push({
        tab_id: tab.id,
        url: tab.url,
        x: Math.round(rect.left),
        y: Math.round(rect.top),
        w: Math.max(0, Math.round(rect.width)),
        h: Math.max(0, Math.round(rect.height)),
      });
    }
  }

  await apiSyncTabWebviews(visible);
}
