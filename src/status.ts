import { sidecarClearErrors } from "./api";
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
        ? "Offline"
        : errCount > 0
          ? `${errCount} notice${errCount === 1 ? "" : "s"}`
          : "Online";
      const learningLabel = state.knowledge.pause_learning ? "Paused" : "Learning";

      telemetryRegion.innerHTML = `
        <div class="telemetry-pop" id="telemetry-popover" role="dialog" aria-label="Model and context telemetry">
          <div class="telemetry-pop-head">
            <span class="label">Telemetry</span>
            <span class="badge ${statusBadgeClass}">${escapeHtml(statusLabel)}</span>
          </div>
          <div class="kv">
            <span>Model</span>
            <strong class="truncate" title="${escapeHtml(activeModel)}">${escapeHtml(activeModel)}</strong>
            <span>Runtime</span>
            <span>${readyCount} / ${totalCount} ready</span>
            <span>Context</span>
            <span>${checkedCount} open (${totalCharsSent.toLocaleString()} / ${CONTEXT_CHAR_BUDGET.toLocaleString()})</span>
            <span>Queue</span>
            <span>${queueLen} pending</span>
            <span>Memory</span>
            <span>${learningLabel}</span>
          </div>
          <div class="meter" title="${pct}% of 24,000 char context budget used">
            <i style="width:${pct}%"></i>
          </div>
          <div class="telemetry-pop-foot">
            <button id="status-error-log-btn" class="btn-text" type="button">
              Logs (${errCount})
            </button>
            <button id="telemetry-close-btn" class="btn-text" type="button">Close</button>
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
      ? `<div class="muted">No logged errors.</div>`
      : allErrors
          .slice(-40)
          .reverse()
          .map((e) => {
            const t = new Date(e.ts * 1000).toTimeString().slice(0, 8);
            return `
              <div class="row">
                <span class="row-meta">${escapeHtml(t)}</span>
                <span class="badge">${escapeHtml(e.scope)}</span>
                <span class="row-title" title="${escapeHtml(e.message)}">${escapeHtml(e.message)}</span>
              </div>
            `;
          })
          .join("");

  overlay.innerHTML = `
    <div class="err-log-pop-head">
      <span class="label">Diagnostic logs (${allErrors.length})</span>
      <div class="err-log-pop-actions">
        <button id="error-log-clear-btn" class="btn" type="button">Clear</button>
        <button id="error-log-close-btn" class="btn" type="button">Close</button>
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
