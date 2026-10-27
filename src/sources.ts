import { escapeHtml, state } from "./state";
import type { SourceItem } from "./types";

export interface SourcesPanelActions {
  onToggleSourceInContext: (sourceId: string, inContext: boolean) => void;
  onJumpToSource: (source: SourceItem) => void;
}

export function renderSourcesPanel(
  container: HTMLElement,
  actions: SourcesPanelActions
): void {
  const detail = state.activeDetail;
  if (!detail) {
    container.innerHTML = "";
    return;
  }

  const sources = detail.sources;
  const openTabs = detail.tabs.filter((t) => t.is_open);

  container.innerHTML = `
    <div class="panel-header">
      <span>sources (${sources.length})</span>
      <span>in context</span>
    </div>
    <div class="panel-scroll">
      ${
        sources.length === 0
          ? `<div class="muted">no sources yet. open a site tab [+] to add pages.</div>`
          : sources
              .map((src, idx) => {
                const matchingTabIdx = openTabs.findIndex(
                  (t) => t.id === src.tab_id
                );
                let locationLabel = "closed";
                if (matchingTabIdx >= 0) {
                  const openTab = openTabs[matchingTabIdx];
                  locationLabel =
                    openTab.url === src.url
                      ? `tab ${matchingTabIdx + 2}`
                      : `earlier`;
                }
                const timeStr = formatTimeHhMm(src.captured_at || src.added_at);
                const checkMark = src.in_context ? "[x]" : "[ ]";
                const stat = state.sourceStats[src.id];
                const charsCaptured =
                  stat?.chars_captured ?? src.text_chars ?? 0;
                const charsSent =
                  stat?.chars_sent ??
                  (src.in_context ? Math.min(6000, charsCaptured) : 0);
                const wasCut = stat?.was_cut ?? charsCaptured > 6000;
                const charsBadge = `${charsSent.toLocaleString()} / ${charsCaptured.toLocaleString()} chars${wasCut ? " · cut" : ""}`;
                return `
                  <div class="source-row" data-source-id="${escapeHtml(src.id)}">
                    <div class="source-row-top">
                      <button class="rail-menu-btn" data-toggle-src="${escapeHtml(src.id)}" data-current-ctx="${src.in_context ? "1" : "0"}">${checkMark}</button>
                      <span class="muted">[${idx + 1}]</span>
                      <span class="truncate">${escapeHtml(src.domain)}</span>
                      <span class="muted">${escapeHtml(locationLabel)} · captured ${escapeHtml(timeStr)}</span>
                    </div>
                    <div class="source-row-title truncate" data-jump-src="${escapeHtml(src.id)}">
                      ${escapeHtml(src.title || src.url)}
                    </div>
                    <div class="muted">${escapeHtml(charsBadge)}</div>
                  </div>
                `;
              })
              .join("")
      }
    </div>
  `;

  container.querySelectorAll("[data-toggle-src]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const el = btn as HTMLElement;
      const id = el.getAttribute("data-toggle-src");
      const cur = el.getAttribute("data-current-ctx") === "1";
      if (id) actions.onToggleSourceInContext(id, !cur);
    });
  });

  container.querySelectorAll("[data-jump-src]").forEach((el) => {
    el.addEventListener("click", () => {
      const id = (el as HTMLElement).getAttribute("data-jump-src");
      const found = sources.find((s) => s.id === id);
      if (found) actions.onJumpToSource(found);
    });
  });
}

function formatTimeHhMm(raw: string): string {
  if (!raw) return "--:--";
  const num = Number(raw);
  const d = !Number.isNaN(num)
    ? new Date(num < 1e12 ? num * 1000 : num)
    : new Date(raw);
  if (Number.isNaN(d.getTime())) return raw.slice(11, 16) || "--:--";
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}
