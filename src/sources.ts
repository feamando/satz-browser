import { escapeHtml, state } from "./state";
import type { SourceItem } from "./types";

export interface SourcesPanelActions {
  onToggleSourceInContext: (sourceId: string, inContext: boolean) => void;
  onJumpToSource: (source: SourceItem) => void;
  onRecaptureTab?: (tabId: string) => void;
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
  let nextCiteIdx = 1;

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
              .map((src) => {
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
                const isMailSource =
                  src.id.startsWith("mail:") ||
                  src.url.startsWith("satzmail://message/");
                const charsCaptured =
                  stat?.chars_captured ?? src.text_chars ?? (isMailSource ? 1 : 0);
                const charsSent =
                  stat?.chars_sent ??
                  (src.in_context ? Math.min(6000, charsCaptured) : 0);
                const wasCut = stat?.was_cut ?? charsCaptured > 6000;
                const captureMode = stat?.capture_mode ?? "dom";
                const citeBadgeHtml =
                  charsCaptured > 0 && src.in_context
                    ? `<span class="muted">[${nextCiteIdx++}]</span>`
                    : `<span class="muted">[-]</span>`;
                const modeLabel =
                  captureMode === "fetch" ? " · public fetch" : "";
                const charsBadgeHtml =
                  charsCaptured > 0
                    ? `${charsSent.toLocaleString()} / ${charsCaptured.toLocaleString()} chars${escapeHtml(modeLabel)}${wasCut ? " · cut" : ""}`
                    : `empty ${src.tab_id ? `<button class="citation-link" data-recapture-src-tab="${escapeHtml(src.tab_id)}">[recapture]</button>` : ""}`;
                return `
                  <div class="source-row ${charsCaptured === 0 ? "muted" : ""}" data-source-id="${escapeHtml(src.id)}">
                    <div class="source-row-top">
                      <button class="rail-menu-btn" data-toggle-src="${escapeHtml(src.id)}" data-current-ctx="${src.in_context ? "1" : "0"}">${checkMark}</button>
                      ${citeBadgeHtml}
                      <span class="truncate">${escapeHtml(src.domain)}</span>
                      <span class="muted">${escapeHtml(locationLabel)} · ${escapeHtml(timeStr)}</span>
                    </div>
                    <div class="source-row-title truncate" data-jump-src="${escapeHtml(src.id)}">
                      ${escapeHtml(src.title || src.url)}
                    </div>
                    <div class="muted">${charsBadgeHtml}</div>
                  </div>
                `;
              })
              .join("")
      }
    </div>
  `;

  container.querySelectorAll("[data-recapture-src-tab]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const tabId = (btn as HTMLElement).getAttribute("data-recapture-src-tab");
      if (tabId && actions.onRecaptureTab) {
        actions.onRecaptureTab(tabId);
      }
    });
  });

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
