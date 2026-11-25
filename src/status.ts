import { sidecarClearErrors } from "./api";
import { t, tCount } from "./i18n";
import { escapeHtml, getActiveTabSources, state } from "./state";

const CONTEXT_CHAR_BUDGET = 24000;

export function renderStatusLine(): void {
  const activeModel = state.selectedModel;
  const activeTabSources = getActiveTabSources(state.activeDetail);
  const checkedCount = activeTabSources.length;
  const totalCharsSent = Math.min(
    CONTEXT_CHAR_BUDGET,
    activeTabSources.reduce((acc, s) => acc + Math.min(6000, s.textChars), 0)
  );
  const pct = Math.min(100, Math.round((totalCharsSent / CONTEXT_CHAR_BUDGET) * 100));

  const readyCount = state.sidecar.models.filter((m) => m.state === "ready").length;
  const totalCount = state.sidecar.models.length || 4;
  const allErrors = [...(state.sidecar.errors ?? []), ...state.uiErrors];
  const errCount = allErrors.length;
  const queueLen = state.sidecar.ingest_queue_len;

  const dotEl = document.getElementById("rail-telemetry-dot");
  if (dotEl) {
    const dotState = !state.sidecar.online
      ? "err"
      : errCount > 0 || queueLen > 0
        ? "warn"
        : "live";
    dotEl.className = `dot ${dotState}`;
  }

  const telBtn = document.getElementById("rail-telemetry-btn");
  if (telBtn) {
    telBtn.classList.toggle("active", state.telemetryOpen);
    telBtn.setAttribute("aria-expanded", state.telemetryOpen ? "true" : "false");
  }

  const telemetryRegion = document.getElementById("region-telemetry");
  if (telemetryRegion) {
    if (!state.telemetryOpen) {
      telemetryRegion.innerHTML = "";
    } else {
      const statusBadgeClass = !state.sidecar.online
        ? "err"
        : errCount > 0
          ? "warn"
          : "good";
      const statusLabel = !state.sidecar.online
        ? t("common.offline")
        : errCount > 0
          ? tCount("status.notice_count", errCount)
          : t("common.online");
      const learningLabel = state.knowledge.pause_learning
        ? t("status.paused")
        : t("status.learning");

      telemetryRegion.innerHTML = `
        <div class="telemetry-pop" id="telemetry-popover" role="dialog" aria-label="${escapeHtml(t("status.telemetry_aria"))}">
          <div class="telemetry-pop-head">
            <span class="label">${escapeHtml(t("status.telemetry"))}</span>
            <span class="badge ${statusBadgeClass}">${escapeHtml(statusLabel)}</span>
          </div>
          <div class="kv">
            <span>${escapeHtml(t("status.model"))}</span>
            <strong class="truncate" title="${escapeHtml(activeModel)}">${escapeHtml(activeModel)}</strong>
            <span>${escapeHtml(t("status.runtime"))}</span>
            <span>${escapeHtml(t("status.ready_frac", { ready: readyCount, total: totalCount }))}</span>
            <span>${escapeHtml(t("status.context"))}</span>
            <span>${escapeHtml(t("status.open_chars", { open: checkedCount, sent: totalCharsSent.toLocaleString(), budget: CONTEXT_CHAR_BUDGET.toLocaleString() }))}</span>
            <span>${escapeHtml(t("status.queue"))}</span>
            <span>${escapeHtml(t("status.pending_n", { count: queueLen }))}</span>
            <span>${escapeHtml(t("status.memory"))}</span>
            <span>${escapeHtml(learningLabel)}</span>
          </div>
          <div class="meter" title="${escapeHtml(t("status.budget_title", { pct, budget: CONTEXT_CHAR_BUDGET.toLocaleString() }))}">
            <i style="width:${pct}%"></i>
          </div>
          <div class="telemetry-pop-foot">
            <button id="status-error-log-btn" class="btn-text" type="button">
              ${escapeHtml(t("status.logs_n", { count: errCount }))}
            </button>
            <button id="telemetry-close-btn" class="btn-text" type="button">${escapeHtml(t("common.close"))}</button>
          </div>
        </div>
      `;

      document
        .getElementById("status-error-log-btn")
        ?.addEventListener("click", (e) => {
          e.stopPropagation();
          state.showErrorLog = !state.showErrorLog;
          renderErrorLogOverlay();
        });

      document
        .getElementById("telemetry-close-btn")
        ?.addEventListener("click", (e) => {
          e.stopPropagation();
          state.telemetryOpen = false;
          renderStatusLine();
        });
    }
  }

  renderErrorLogOverlay();
}

export function renderErrorLogOverlay(): void {
  const existing = document.getElementById("region-error-log-overlay");
  const allErrors = [...(state.sidecar.errors ?? []), ...state.uiErrors];
  if (!state.showErrorLog) {
    existing?.remove();
    return;
  }

  let overlay = existing;
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "region-error-log-overlay";
    overlay.className = "err-log-pop";
    document.body.appendChild(overlay);
  }

  const itemsHtml =
    allErrors.length === 0
      ? `<div class="muted">${escapeHtml(t("status.no_errors"))}</div>`
      : allErrors
          .slice(-40)
          .reverse()
          .map((e) => {
            const tm = new Date(e.ts * 1000).toTimeString().slice(0, 8);
            return `
              <div class="row">
                <span class="row-meta">${escapeHtml(tm)}</span>
                <span class="badge">${escapeHtml(e.scope)}</span>
                <span class="row-title" title="${escapeHtml(e.message)}">${escapeHtml(e.message)}</span>
              </div>
            `;
          })
          .join("");

  overlay.innerHTML = `
    <div class="err-log-pop-head">
      <span class="label">${escapeHtml(t("status.diag_logs_n", { count: allErrors.length }))}</span>
      <div class="err-log-pop-actions">
        <button id="error-log-clear-btn" class="btn" type="button">${escapeHtml(t("common.clear"))}</button>
        <button id="error-log-close-btn" class="btn" type="button">${escapeHtml(t("common.close"))}</button>
      </div>
    </div>
    <div class="log-list">
      ${itemsHtml}
    </div>
  `;

  document
    .getElementById("error-log-clear-btn")
    ?.addEventListener("click", () => {
      void (async () => {
        await sidecarClearErrors();
        state.sidecar.errors = [];
        state.uiErrors = [];
        renderStatusLine();
      })();
    });

  document
    .getElementById("error-log-close-btn")
    ?.addEventListener("click", () => {
      state.showErrorLog = false;
      renderErrorLogOverlay();
    });
}
