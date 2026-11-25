import { icon } from "./design-system/icons";
import { t } from "./i18n";
import { escapeHtml, state } from "./state";
import type { SourceItem } from "./types";

export interface SourcesPanelActions {
  onToggleSourceInContext: (sourceId: string, inContext: boolean) => void;
  onJumpToSource: (source: SourceItem) => void;
  onOpenSourceInNewTab?: (url: string, title: string) => void;
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
    <div class="label sources-subhead">
      <span>${escapeHtml(t("sources.heading"))}</span>
      <span class="ct">${sources.length}</span>
    </div>
    <div class="sources-list">
      ${
        sources.length === 0
          ? `<div class="empty">${escapeHtml(t("sources.empty_list"))}</div>`
          : sources
              .map((src) => {
                const matchingTabIdx = openTabs.findIndex(
                  (t) => t.id === src.tab_id
                );
                let locationLabel = t("sources.closed");
                if (matchingTabIdx >= 0) {
                  const openTab = openTabs[matchingTabIdx];
                  locationLabel =
                    openTab.url === src.url
                      ? t("sources.tab_n", { num: matchingTabIdx + 2 })
                      : t("sources.earlier");
                }
                const timeStr = formatTimeHhMm(src.captured_at || src.added_at);
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
                const contextTier = stat?.context_tier ?? (wasCut ? "excerpt" : "full");
                const captureMode = stat?.capture_mode ?? "dom";
                const citeBadgeHtml =
                  charsCaptured > 0 && src.in_context
                    ? `<span class="cite">${nextCiteIdx++}</span>`
                    : `<span class="badge soft">${escapeHtml(t("sources.off"))}</span>`;
                const modeLabel =
                  captureMode === "fetch" ? t("sources.public_fetch") : "";
                const tierBadgeHtml =
                  contextTier === "manifest"
                    ? `<span class="badge soft" title="${escapeHtml(t("sources.manifest_title"))}">${escapeHtml(t("sources.manifest"))}</span>`
                    : contextTier === "expanded"
                      ? `<span class="badge soft" title="${escapeHtml(t("sources.expanded_title"))}">${escapeHtml(t("sources.expanded"))}</span>`
                      : wasCut
                        ? `<span class="flag">${escapeHtml(t("sources.cut"))}</span>`
                        : "";
                const charsBadgeHtml =
                  charsCaptured > 0
                    ? `<span>${escapeHtml(t("sources.chars_frac", { sent: charsSent.toLocaleString(), captured: charsCaptured.toLocaleString(), mode: modeLabel }))}</span>${tierBadgeHtml}`
                    : `<span>${escapeHtml(t("sources.empty_capture"))}</span>${src.tab_id ? `<button type="button" class="btn-text" data-recapture-src-tab="${escapeHtml(src.tab_id)}">${escapeHtml(t("sources.recapture"))}</button>` : ""}`;
                return `
                  <div class="source-row ${charsCaptured === 0 ? "muted" : ""}" data-source-id="${escapeHtml(src.id)}">
                    <div class="source-row-top">
                      <button
                        type="button"
                        class="icon-btn src-ctx-btn ${src.in_context ? "on" : ""}"
                        data-toggle-src="${escapeHtml(src.id)}"
                        data-current-ctx="${src.in_context ? "1" : "0"}"
                        title="${escapeHtml(src.in_context ? t("sources.in_ctx_title") : t("sources.excluded_title"))}"
                      >${src.in_context ? icon("check", "ico-sm") : icon("plus", "ico-sm")}</button>
                      ${citeBadgeHtml}
                      <span class="t" data-jump-src="${escapeHtml(src.id)}" title="${escapeHtml(src.title || src.url)}">
                        ${escapeHtml(src.title || src.domain || src.url)}
                      </span>
                      <span class="trust">${escapeHtml(src.domain)}</span>
                    </div>
                    <div class="source-row-meta">
                      <span>${escapeHtml(locationLabel)} · ${escapeHtml(timeStr)}</span>
                      ${charsBadgeHtml}
                    </div>
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
    el.addEventListener("mousedown", (e) => {
      if ((e as MouseEvent).button === 1) e.preventDefault();
    });
    el.addEventListener("auxclick", (e) => {
      const me = e as MouseEvent;
      if (me.button !== 1) return;
      me.preventDefault();
      me.stopPropagation();
      const id = (el as HTMLElement).getAttribute("data-jump-src");
      const found = sources.find((s) => s.id === id);
      if (found && /^https?:\/\//i.test(found.url) && actions.onOpenSourceInNewTab) {
        actions.onOpenSourceInNewTab(found.url, found.title);
      }
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
