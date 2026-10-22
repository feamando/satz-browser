import { escapeHtml, getActiveTabSources, state } from "./state";
import type { LocalModelId } from "./types";

const LOCAL_MODELS: LocalModelId[] = [
  "gemma-4-e4b",
  "planck3 (web)",
  "hertz (reader)",
  "planck (reader)",
];

export interface ChatActions {
  onSendMessage: (text: string) => void;
  onChangeModel: (model: LocalModelId) => void;
  onToggleWeb: () => void;
  onClickCitation: (citationIndex: number, sourceId: string | null) => void;
  onOpenUrlAsTab: (url: string, title: string) => void;
  onSelectTab?: (tabId: string) => void;
  onCloseTab?: (tabId: string) => void;
  onNewTab?: () => void;
}

export function renderChatPanel(
  container: HTMLElement,
  actions: ChatActions
): void {
  const detail = state.activeDetail;
  if (!detail) {
    container.innerHTML = "";
    return;
  }

  const existingInput = container.querySelector(
    "#chat-composer-input"
  ) as HTMLInputElement | null;
  const wasFocused =
    Boolean(existingInput) && document.activeElement === existingInput;
  const preservedValue = existingInput?.value ?? "";
  const preservedSelection =
    existingInput?.selectionStart ?? preservedValue.length;

  const messages = detail.messages;
  const activeTabSources = getActiveTabSources(detail);
  const offlineNotice = !state.sidecar.online
    ? "models [offline] - browser tabs work normally; start sidecar for local chat"
    : activeTabSources.length > 0
      ? `ask over ${activeTabSources.length} open tab${activeTabSources.length === 1 ? "" : "s"} in context or type a question_`
      : "ask a question or open a tab [+] to add context_";

  const contextPillsHtml =
    activeTabSources.length === 0
      ? `
        <div class="composer-context-row">
          <span class="muted">context (0 tabs):</span>
          <div class="composer-context-pills">
            <span class="muted">open tabs are automatically added to chat context</span>
            <button id="chat-context-add-tab-btn" class="context-add-btn">[+ open tab]</button>
          </div>
        </div>
      `
      : `
        <div class="composer-context-row">
          <span class="muted">context (${activeTabSources.length}):</span>
          <div class="composer-context-pills">
            ${activeTabSources
              .map(
                (item) => `
              <div
                class="context-pill ${state.activeTabId === item.tab.id ? "active" : ""}"
                data-pill-tab-id="${escapeHtml(item.tab.id)}"
                title="${escapeHtml(item.title)} (${escapeHtml(item.url)})"
              >
                <span class="muted">[${item.index}]</span>
                <span class="truncate">${escapeHtml(item.domain)} · ${escapeHtml(item.title.slice(0, 22))}</span>
                <button
                  class="tab-close-btn"
                  data-pill-close-tab-id="${escapeHtml(item.tab.id)}"
                  title="close tab and remove from context"
                >x</button>
              </div>
            `
              )
              .join("")}
            <button id="chat-context-add-tab-btn" class="context-add-btn" title="open a new tab to add to context">[+ tab]</button>
          </div>
        </div>
      `;

  container.innerHTML = `
    <div class="chat-column">
      <div class="chat-messages" id="chat-messages-list">
        ${
          messages.length === 0
            ? `<div class="muted">no messages in this conversation yet.</div>`
            : messages.map((m) => renderMessageBlock(m.role, m.content, m.model, m.source_ids_json, m.cited_sources)).join("")
        }
        ${
          state.isStreaming
            ? `
          <div class="msg-block" id="streaming-msg-block">
            <div class="msg-header">
              <span>assistant</span>
              <span>${escapeHtml(state.selectedModel)} [streaming]</span>
            </div>
            <div class="msg-body"><span id="streaming-msg-text">${escapeHtml(state.streamingText)}</span><span class="caret-blink">▌</span></div>
          </div>
        `
            : ""
        }
      </div>

      <div class="chat-composer">
        ${contextPillsHtml}
        <div class="composer-input-row">
          <span class="muted">&gt;</span>
          <input
            id="chat-composer-input"
            class="composer-input"
            type="text"
            placeholder="${escapeHtml(offlineNotice)}"
          />
          <span class="caret-blink">▌</span>
          <button id="chat-send-btn">[send]</button>
        </div>

        <div class="composer-meta-row">
          <span>${state.sidecar.online ? "models [ok]" : "models [offline]"}</span>
          <div class="composer-controls">
            <label class="muted">model:</label>
            <select id="chat-model-select">
              ${LOCAL_MODELS.map(
                (m) => `
                <option value="${escapeHtml(m)}" ${state.selectedModel === m ? "selected" : ""}>
                  ${escapeHtml(m)}
                </option>
              `
              ).join("")}
            </select>
            <button id="chat-web-toggle" class="${state.webSearchEnabled ? "active" : ""}">
              web: ${state.webSearchEnabled ? "on" : "off"}
            </button>
          </div>
        </div>
      </div>
    </div>
  `;

  bindChatEvents(container, actions);

  if (preservedValue || wasFocused) {
    const nextInput = container.querySelector(
      "#chat-composer-input"
    ) as HTMLInputElement | null;
    if (nextInput) {
      nextInput.value = preservedValue;
      if (wasFocused) {
        nextInput.focus();
        nextInput.setSelectionRange(preservedSelection, preservedSelection);
      }
    }
  }
}

export function appendStreamingDelta(delta: string): void {
  state.streamingText += delta;
  const el = document.getElementById("streaming-msg-text");
  if (el) {
    el.textContent = state.streamingText;
    const list = document.getElementById("chat-messages-list");
    if (list) {
      list.scrollTop = list.scrollHeight;
    }
  }
}

function renderMessageBlock(
  role: string,
  content: string,
  model: string | null,
  sourceIdsJson: string | null,
  citedSources?: Array<{ url: string; title: string }>
): string {
  let sourceIds: string[] = [];
  if (sourceIdsJson) {
    try {
      sourceIds = JSON.parse(sourceIdsJson) as string[];
    } catch {
      sourceIds = [];
    }
  }

  const formattedBody = formatCitationsInText(content, sourceIds);
  const modelLabel = model ? `model: ${escapeHtml(model)}` : "";
  const srcCountLabel =
    sourceIds.length > 0 ? ` · ${sourceIds.length} src` : "";

  const openAsTabButtons =
    citedSources && citedSources.length > 0
      ? `
      <div class="composer-controls">
        ${citedSources
          .map(
            (cs) => `
          <button class="citation-link" data-open-tab-url="${escapeHtml(cs.url)}" data-open-tab-title="${escapeHtml(cs.title)}">
            [open as tab: ${escapeHtml(cs.title || cs.url)}]
          </button>
        `
          )
          .join("")}
      </div>
    `
      : "";

  return `
    <div class="msg-block">
      <div class="msg-header">
        <span>${escapeHtml(role)}</span>
        <span>${modelLabel}${srcCountLabel}</span>
      </div>
      <div class="msg-body">${formattedBody}</div>
      ${openAsTabButtons}
    </div>
  `;
}

function formatCitationsInText(text: string, sourceIds: string[]): string {
  const escaped = escapeHtml(text);
  return escaped.replace(/\[(\d+)\]/g, (_match, digits) => {
    const idx = Number(digits);
    const sourceId = sourceIds[idx - 1] ?? "";
    return `<button class="citation-link" data-citation-idx="${idx}" data-citation-src="${escapeHtml(sourceId)}">[${idx}]</button>`;
  });
}

function bindChatEvents(container: HTMLElement, actions: ChatActions): void {
  const input = container.querySelector(
    "#chat-composer-input"
  ) as HTMLInputElement | null;
  const submit = () => {
    const val = input?.value.trim() ?? "";
    if (!val || state.isStreaming) return;
    if (input) input.value = "";
    actions.onSendMessage(val);
  };

  input?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submit();
    }
  });

  container.querySelector("#chat-send-btn")?.addEventListener("click", submit);

  const modelSelect = container.querySelector(
    "#chat-model-select"
  ) as HTMLSelectElement | null;
  modelSelect?.addEventListener("change", () => {
    actions.onChangeModel(modelSelect.value as LocalModelId);
  });

  container
    .querySelector("#chat-web-toggle")
    ?.addEventListener("click", () => {
      actions.onToggleWeb();
    });

  container.querySelectorAll("[data-citation-idx]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const idx = Number(el.getAttribute("data-citation-idx"));
      const srcId = el.getAttribute("data-citation-src") || null;
      actions.onClickCitation(idx, srcId);
    });
  });

  container.querySelectorAll("[data-open-tab-url]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const url = el.getAttribute("data-open-tab-url");
      const title = el.getAttribute("data-open-tab-title") ?? "";
      if (url) actions.onOpenUrlAsTab(url, title);
    });
  });

  container.querySelectorAll("[data-pill-tab-id]").forEach((pill) => {
    pill.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      if (target.closest("[data-pill-close-tab-id]")) return;
      const tabId = (pill as HTMLElement).getAttribute("data-pill-tab-id");
      if (tabId && actions.onSelectTab) {
        actions.onSelectTab(tabId);
      }
    });
  });

  container.querySelectorAll("[data-pill-close-tab-id]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const tabId = (btn as HTMLElement).getAttribute("data-pill-close-tab-id");
      if (tabId && actions.onCloseTab) {
        actions.onCloseTab(tabId);
      }
    });
  });

  container
    .querySelector("#chat-context-add-tab-btn")
    ?.addEventListener("click", () => {
      if (actions.onNewTab) {
        actions.onNewTab();
      }
    });
}
