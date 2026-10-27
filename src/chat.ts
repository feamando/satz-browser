import { escapeHtml, getActiveTabSources, state } from "./state";
import type { BrainProposalItem, CitationCheckEntry, LocalModelId } from "./types";

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
  onAcceptProposal?: (proposalId: string, msgId: string) => void;
  onRejectProposal?: (proposalId: string, msgId: string) => void;
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
  const elapsedSec =
    state.isStreaming && state.streamingStartedAt > 0
      ? ((Date.now() - state.streamingStartedAt) / 1000).toFixed(1)
      : "0.0";
  const phaseLabel = state.streamingPhase || "processing";
  const statusLineText =
    state.streamingStatus || "request in progress...";

  const offlineNotice = !state.sidecar.online
    ? "models [offline] - browser tabs work normally; start sidecar for local chat"
    : state.isStreaming
      ? `[in progress: ${statusLineText}]`
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
              .map((item) => {
                const stat = state.sourceStats[item.sourceId];
                const statLabel = stat
                  ? ` · ${stat.chars_sent}/${stat.chars_captured}c${stat.was_cut ? " [cut]" : ""}`
                  : "";
                return `
              <div
                class="context-pill ${state.activeTabId === item.tab.id ? "active" : ""}"
                data-pill-tab-id="${escapeHtml(item.tab.id)}"
                title="${escapeHtml(item.title)} (${escapeHtml(item.url)})${stat ? ` - ${stat.chars_sent.toLocaleString()} / ${stat.chars_captured.toLocaleString()} chars${stat.was_cut ? " [cut]" : ""}` : ""}"
              >
                <span class="muted">[${item.index}]</span>
                <span class="truncate">${escapeHtml(item.domain)} · ${escapeHtml(item.title.slice(0, 22))}${escapeHtml(statLabel)}</span>
                <button
                  class="tab-close-btn"
                  data-pill-close-tab-id="${escapeHtml(item.tab.id)}"
                  title="close tab and remove from context"
                >x</button>
              </div>
            `;
              })
              .join("")}
            <button id="chat-context-add-tab-btn" class="context-add-btn" title="open a new tab to add to context">[+ tab]</button>
          </div>
        </div>
      `;

  const stepsHtml = state.streamingSteps
    .map(
      (step, idx) =>
        `<div class="streaming-step-line">${idx === state.streamingSteps.length - 1 ? "&gt;" : "ok"} ${escapeHtml(step)}</div>`
    )
    .join("");

  container.innerHTML = `
    <div class="chat-column">
      <div class="chat-messages" id="chat-messages-list">
        ${
          messages.length === 0 && !state.isStreaming
            ? `<div class="muted">no messages in this conversation yet.</div>`
            : messages
                .map((m) =>
                  renderMessageBlock(
                    m.id,
                    m.role,
                    m.content,
                    m.model,
                    m.source_ids_json,
                    m.cited_sources,
                    m.proposals ?? state.messageProposals[m.id],
                    m.citation_check,
                    m.citations_ok,
                    m.citations_flagged
                  )
                )
                .join("")
        }
        ${
          state.isStreaming
            ? `
          <div class="msg-block msg-streaming-block" id="streaming-msg-block">
            <div class="msg-header">
              <span>assistant</span>
              <span>${escapeHtml(state.selectedModel)} [<span id="streaming-phase-badge">${escapeHtml(phaseLabel)}</span> · <span id="streaming-elapsed-timer">${elapsedSec}s</span>]</span>
            </div>
            <div class="streaming-status-box" id="streaming-status-box">
              <div class="streaming-status-current" id="streaming-status-current">&gt; status: ${escapeHtml(statusLineText)}</div>
              <div class="streaming-steps-list" id="streaming-steps-list">${stepsHtml}</div>
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
            ${state.isStreaming ? "disabled" : ""}
          />
          <span class="caret-blink">▌</span>
          <button id="chat-send-btn" ${state.isStreaming ? "disabled" : ""}>${state.isStreaming ? "[in progress...]" : "[send]"}</button>
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

export function updateStreamingStatus(status: string, phase?: string): void {
  state.streamingStatus = status;
  if (phase) {
    state.streamingPhase = phase;
  }
  if (
    status &&
    state.streamingSteps[state.streamingSteps.length - 1] !== status
  ) {
    state.streamingSteps = [...state.streamingSteps.slice(-4), status];
  }

  const phaseEl = document.getElementById("streaming-phase-badge");
  if (phaseEl && state.streamingPhase) {
    phaseEl.textContent = state.streamingPhase;
  }
  const curEl = document.getElementById("streaming-status-current");
  if (curEl) {
    curEl.textContent = `> status: ${status}`;
  }
  const stepsEl = document.getElementById("streaming-steps-list");
  if (stepsEl) {
    stepsEl.innerHTML = state.streamingSteps
      .map(
        (step, idx) =>
          `<div class="streaming-step-line">${idx === state.streamingSteps.length - 1 ? "&gt;" : "ok"} ${escapeHtml(step)}</div>`
      )
      .join("");
  }
  const inputEl = document.getElementById(
    "chat-composer-input"
  ) as HTMLInputElement | null;
  if (inputEl && state.isStreaming) {
    inputEl.placeholder = `[in progress: ${status}]`;
  }
  const list = document.getElementById("chat-messages-list");
  if (list) {
    list.scrollTop = list.scrollHeight;
  }
}

export function tickStreamingElapsed(): void {
  if (!state.isStreaming || state.streamingStartedAt <= 0) return;
  const elapsedSec = ((Date.now() - state.streamingStartedAt) / 1000).toFixed(
    1
  );
  const timerEl = document.getElementById("streaming-elapsed-timer");
  if (timerEl) {
    timerEl.textContent = `${elapsedSec}s`;
  }
}

function renderMessageBlock(
  msgId: string,
  role: string,
  content: string,
  model: string | null,
  sourceIdsJson: string | null,
  citedSources?: Array<{ url: string; title: string }>,
  proposals?: BrainProposalItem[],
  citationCheck?: CitationCheckEntry[],
  citationsOk?: number | null,
  citationsFlagged?: number | null
): string {
  let sourceIds: string[] = [];
  if (sourceIdsJson) {
    try {
      sourceIds = JSON.parse(sourceIdsJson) as string[];
    } catch {
      sourceIds = [];
    }
  }

  const trimmed = content.trim();
  const isErrorMsg =
    role === "assistant" &&
    (trimmed.startsWith("[err]") ||
      trimmed.startsWith("[error:") ||
      trimmed.startsWith("models [offline]"));

  const formattedBody = formatCitationsInText(content, sourceIds, citationCheck);
  const modelLabel = model ? `model: ${escapeHtml(model)}` : "";
  const srcCountLabel =
    sourceIds.length > 0 ? ` · ${sourceIds.length} src` : "";
  const citeStatsLabel =
    typeof citationsOk === "number" || typeof citationsFlagged === "number"
      ? (citationsFlagged ?? 0) > 0
        ? ` · cites: ${citationsOk ?? 0} ok, ${citationsFlagged ?? 0} flagged`
        : (citationsOk ?? 0) > 0
          ? ` · cites: ${citationsOk} ok`
          : ""
      : "";
  const statusBadge = isErrorMsg
    ? ` <span class="msg-error-badge">[error]</span>`
    : "";

  const retryButtonHtml =
    isErrorMsg && state.lastUserPrompt
      ? `
      <div class="composer-controls">
        <button class="citation-link" data-retry-prompt="${escapeHtml(state.lastUserPrompt)}">[retry request]</button>
      </div>
    `
      : "";

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

  const proposalsHtml =
    proposals && proposals.length > 0
      ? `
      <div class="composer-controls">
        ${proposals
          .map((p) => {
            const summaryPart = p.summary ? `, ${escapeHtml(p.summary.slice(0, 80))}` : "";
            const status = p.status ?? "pending";
            if (status === "accepted") {
              return `<div class="muted">[store] ${escapeHtml(p.type)}: ${escapeHtml(p.name)}${summaryPart} [accepted]</div>`;
            }
            if (status === "rejected") {
              return `<div class="muted">[store] ${escapeHtml(p.type)}: ${escapeHtml(p.name)}${summaryPart} [rejected]</div>`;
            }
            return `
              <div class="rail-row">
                <span>[store] ${escapeHtml(p.type)}: ${escapeHtml(p.name)}${summaryPart}</span>
                <span>
                  <button class="citation-link" data-accept-proposal="${escapeHtml(p.proposal_id)}" data-proposal-msg="${escapeHtml(msgId)}">[accept]</button>
                  <button class="citation-link" data-reject-proposal="${escapeHtml(p.proposal_id)}" data-proposal-msg="${escapeHtml(msgId)}">[reject]</button>
                </span>
              </div>
            `;
          })
          .join("")}
      </div>
    `
      : "";

  return `
    <div class="msg-block ${isErrorMsg ? "msg-error-block" : ""}">
      <div class="msg-header">
        <span>${escapeHtml(role)}${statusBadge}</span>
        <span>${modelLabel}${srcCountLabel}${escapeHtml(citeStatsLabel)}</span>
      </div>
      <div class="msg-body">${formattedBody}</div>
      ${proposalsHtml}
      ${retryButtonHtml}
      ${openAsTabButtons}
    </div>
  `;
}

export function formatCitationsInText(
  text: string,
  sourceIds: string[],
  citationCheck?: CitationCheckEntry[]
): string {
  const escaped = escapeHtml(text).replace(
    /\[unsourced\]/g,
    `<span class="msg-error-badge" title="citation index outside source list">[unsourced]</span>`
  );
  return escaped.replace(/\[(\d+)\]/g, (_match, digits) => {
    const idx = Number(digits);
    const outOfRangeCheck = citationCheck?.find(
      (c) => c.n === idx && c.out_of_range
    );
    if (
      idx < 1 ||
      (sourceIds.length > 0 && idx > sourceIds.length) ||
      outOfRangeCheck
    ) {
      return `<span class="msg-error-badge" title="citation [${idx}] outside ${sourceIds.length} source(s)">[unsourced]</span>`;
    }
    const sourceId = sourceIds[idx - 1] ?? "";
    const flaggedEntries = (citationCheck ?? []).filter(
      (c) => c.n === idx && !c.ok
    );
    if (flaggedEntries.length > 0) {
      const missingItems = Array.from(
        new Set(flaggedEntries.flatMap((e) => e.missing ?? []))
      );
      const tooltip = `not found in source [${idx}]: ${missingItems.join(", ")}`;
      return `<button class="citation-link msg-error-badge" data-citation-idx="${idx}" data-citation-src="${escapeHtml(sourceId)}" title="${escapeHtml(tooltip)}">[${idx}?]</button>`;
    }
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

  container.querySelectorAll("[data-retry-prompt]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (state.isStreaming) return;
      const prompt = (btn as HTMLElement).getAttribute("data-retry-prompt");
      if (prompt) actions.onSendMessage(prompt);
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

  container.querySelectorAll("[data-accept-proposal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const pid = el.getAttribute("data-accept-proposal") ?? "";
      const mid = el.getAttribute("data-proposal-msg") ?? "";
      if (pid && actions.onAcceptProposal) {
        actions.onAcceptProposal(pid, mid);
      }
    });
  });

  container.querySelectorAll("[data-reject-proposal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const pid = el.getAttribute("data-reject-proposal") ?? "";
      const mid = el.getAttribute("data-proposal-msg") ?? "";
      if (pid && actions.onRejectProposal) {
        actions.onRejectProposal(pid, mid);
      }
    });
  });
}
