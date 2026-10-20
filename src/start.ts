import { escapeHtml, state } from "./state";
import type { LocalModelId } from "./types";

const LOCAL_MODELS: LocalModelId[] = [
  "gemma-4-e4b",
  "planck3 (web)",
  "hertz (reader)",
  "planck (reader)",
];

export interface StartScreenActions {
  onSubmitStartInput: (raw: string) => void;
  onSelectConversation: (id: string) => void;
  onOpenDigestUrl: (url: string, title: string) => void;
  onChangeModel: (model: LocalModelId) => void;
  onToggleWeb: () => void;
}

export function renderStartScreen(
  container: HTMLElement,
  actions: StartScreenActions
): void {
  const resumeConvs = state.conversations
    .filter((c) => c.status === "active")
    .slice(0, 6);

  container.innerHTML = `
    <div class="start-screen">
      <div class="start-container">
        <div class="start-prompt-title">where do you want to start?</div>

        <div class="start-input-box">
          <div class="start-input-row">
            <span class="muted">&gt;</span>
            <input
              id="start-main-input"
              class="start-input-field"
              type="text"
              placeholder="paste a url, ask something, or both_"
            />
            <span class="caret-blink">▌</span>
          </div>

          <div class="start-controls-row">
            <span class="muted">enter to start</span>
            <div class="composer-controls">
              <label class="muted">model:</label>
              <select id="start-model-select">
                ${LOCAL_MODELS.map(
                  (m) => `
                  <option value="${escapeHtml(m)}" ${state.selectedModel === m ? "selected" : ""}>
                    ${escapeHtml(m)}
                  </option>
                `
                ).join("")}
              </select>
              <button id="start-web-toggle" class="${state.webSearchEnabled ? "active" : ""}">
                web: ${state.webSearchEnabled ? "on" : "off"}
              </button>
            </div>
          </div>
        </div>

        <div class="start-columns">
          <div class="start-col">
            <div class="start-col-header">for you</div>
            ${
              state.digestItems.length === 0
                ? `<div class="muted">no digest items yet (browse pages to build local store)</div>`
                : state.digestItems
                    .map(
                      (item) => `
                  <div class="start-list-item" data-digest-url="${escapeHtml(item.url)}" data-digest-title="${escapeHtml(item.title)}">
                    <span class="truncate">${escapeHtml(item.title)}</span>
                    <span class="muted">${escapeHtml(item.domain)}</span>
                  </div>
                `
                    )
                    .join("")
            }
          </div>

          <div class="start-col">
            <div class="start-col-header">resume</div>
            ${
              resumeConvs.length === 0
                ? `<div class="muted">no recent conversations</div>`
                : resumeConvs
                    .map(
                      (c) => `
                  <div class="start-list-item" data-resume-id="${escapeHtml(c.id)}">
                    <span class="truncate">${escapeHtml(c.title)}</span>
                    <span class="muted">${c.source_count ?? 0} src</span>
                  </div>
                `
                    )
                    .join("")
            }
          </div>
        </div>
      </div>
    </div>
  `;

  const input = container.querySelector(
    "#start-main-input"
  ) as HTMLInputElement | null;
  if (input) {
    input.focus();
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const val = input.value.trim();
        if (val) {
          actions.onSubmitStartInput(val);
        }
      }
      if (e.key === "Escape") {
        input.value = "";
      }
    });
  }

  const modelSelect = container.querySelector(
    "#start-model-select"
  ) as HTMLSelectElement | null;
  modelSelect?.addEventListener("change", () => {
    actions.onChangeModel(modelSelect.value as LocalModelId);
  });

  container
    .querySelector("#start-web-toggle")
    ?.addEventListener("click", () => {
      actions.onToggleWeb();
    });

  container.querySelectorAll("[data-resume-id]").forEach((el) => {
    el.addEventListener("click", () => {
      const id = (el as HTMLElement).getAttribute("data-resume-id");
      if (id) actions.onSelectConversation(id);
    });
  });

  container.querySelectorAll("[data-digest-url]").forEach((el) => {
    el.addEventListener("click", () => {
      const url = (el as HTMLElement).getAttribute("data-digest-url");
      const title =
        (el as HTMLElement).getAttribute("data-digest-title") ?? url ?? "";
      if (url) actions.onOpenDigestUrl(url, title);
    });
  });
}
