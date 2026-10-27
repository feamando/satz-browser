import { sidecarClearErrors } from "./api";
import { escapeHtml, getActiveTabSources, state } from "./state";

export function renderStatusLine(): void {
  const container = document.getElementById("region-status-bar");
  if (!container) return;

  const gemmaEntry = state.sidecar.models.find((m) => m.id === "gemma-4-e4b");
  const gemmaWarmLabel =
    state.sidecar.online && gemmaEntry?.state === "ready"
      ? `<span>gemma [warm]</span>`
      : state.sidecar.online && gemmaEntry?.state === "loading"
        ? `<span>gemma [loading]</span>`
        : "";

  const modelEntry = state.sidecar.models.find(
    (m) => m.id === state.selectedModel
  );
  const modelStatus = !state.sidecar.online
    ? "[offline]"
    : modelEntry?.state === "ready"
      ? state.selectedModel === "gemma-4-e4b"
        ? "[warm]"
        : "[ok]"
      : modelEntry?.state === "loading"
        ? "[loading]"
        : modelEntry?.state === "missing"
          ? "[err]"
          : "[ok]";

  const sidecarStatus = state.sidecar.online ? "[ok]" : "[offline]";
  const sourcesInContext = getActiveTabSources(state.activeDetail).length;
  const queueLen = state.sidecar.ingest_queue_len;
  const learnState = state.sidecar.pause_learning ? " [paused]" : "";
  const errors = state.sidecar.errors ?? [];
  const errCount = errors.length;
  const errBtnHtml =
    errCount > 0
      ? `<button id="status-errors-btn" class="rail-menu-btn msg-error-badge">[${errCount} error${errCount === 1 ? "" : "s"}]</button>`
      : "";

  container.innerHTML = `
    <div class="status-segment">
      <span>model: <span class="status-item">${escapeHtml(state.selectedModel)}</span> ${modelStatus}</span>
      ${gemmaWarmLabel}
      <span>models ${sidecarStatus}</span>
      <span>sources in context: <span class="status-item">${sourcesInContext}</span></span>
    </div>
    <div class="status-segment">
      ${errBtnHtml}
      <span>kb queue: <span class="status-item">${queueLen}</span>${learnState}</span>
    </div>
  `;

  container.querySelector("#status-errors-btn")?.addEventListener("click", () => {
    state.showErrorLog = !state.showErrorLog;
    renderErrorLogOverlay();
  });

  renderErrorLogOverlay();
}

function renderErrorLogOverlay(): void {
  let overlay = document.getElementById("region-error-log-overlay");
  const errors = state.sidecar.errors ?? [];
  if (!state.showErrorLog || errors.length === 0) {
    if (overlay) {
      overlay.remove();
    }
    return;
  }

  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "region-error-log-overlay";
    overlay.className = "knowledge-section";
    const statusBar = document.getElementById("region-status-bar");
    statusBar?.parentElement?.insertBefore(overlay, statusBar);
  }

  const rowsHtml = errors
    .slice()
    .reverse()
    .map((err) => {
      const d = new Date((err.ts || 0) * 1000);
      const hh = String(d.getHours()).padStart(2, "0");
      const mm = String(d.getMinutes()).padStart(2, "0");
      const ss = String(d.getSeconds()).padStart(2, "0");
      return `
        <div class="rail-row">
          <span>[${escapeHtml(err.scope)}] ${escapeHtml(err.message)}</span>
          <span class="muted">${hh}:${mm}:${ss}</span>
        </div>
      `;
    })
    .join("");

  overlay.innerHTML = `
    <div class="panel-header">
      <span>sidecar error ring buffer (${errors.length} / 50)</span>
      <div>
        <button id="error-log-clear-btn">[clear]</button>
        <button id="error-log-close-btn">[close]</button>
      </div>
    </div>
    <div class="panel-scroll">
      ${rowsHtml}
    </div>
  `;

  overlay.querySelector("#error-log-close-btn")?.addEventListener("click", () => {
    state.showErrorLog = false;
    renderErrorLogOverlay();
  });

  overlay.querySelector("#error-log-clear-btn")?.addEventListener("click", async () => {
    await sidecarClearErrors();
    state.sidecar.errors = [];
    state.showErrorLog = false;
    renderStatusLine();
  });
}
