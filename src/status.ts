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

  container.innerHTML = `
    <div class="status-segment">
      <span>model: <span class="status-item">${escapeHtml(state.selectedModel)}</span> ${modelStatus}</span>
      ${gemmaWarmLabel}
      <span>models ${sidecarStatus}</span>
      <span>sources in context: <span class="status-item">${sourcesInContext}</span></span>
    </div>
    <div class="status-segment">
      <span>kb queue: <span class="status-item">${queueLen}</span>${learnState}</span>
    </div>
  `;
}
