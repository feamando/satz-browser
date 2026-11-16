import {
  escapeHtml,
  extractDomain,
  formatPlainErrorMessage,
  getActiveTabSources,
  getAvailableModelsForPicker,
  getModelPrivacySummary,
  state,
} from "./state";
import type {
  AgentTaskCard,
  BrainCitationItem,
  BrainProposalItem,
  ChatEmailCard,
  CitationCheckEntry,
  FindingItem,
  LocalModelId,
} from "./types";

export interface ChatActions {
  onSendMessage: (text: string) => void;
  onChangeModel: (model: LocalModelId) => void;
  onUsePlanckInstead?: (text: string) => void;
  onToggleWeb: () => void;
  onToggleMail?: () => void;
  onClickCitation: (citationIndex: number, sourceId: string | null) => void;
  onClickBrainCitation?: (slug: string, citeLabel: string) => void;
  onOpenUrlAsTab: (url: string, title: string) => void;
  onSelectTab?: (tabId: string) => void;
  onCloseTab?: (tabId: string) => void;
  onNewTab?: () => void;
  onRecaptureTab?: (tabId: string) => void;
  onRecaptureAllTabs?: () => void;
  onAcceptProposal?: (proposalId: string, msgId: string) => void;
  onRejectProposal?: (proposalId: string, msgId: string) => void;
  onRunComparer?: () => void;
  onWatchAnswer?: (msgId: string, content: string) => void;
  onStopTask?: (taskId: string, stopToken: string) => void;
  onConfirmTaskStep?: (taskId: string, stepId: string, confirmToken: string) => void;
  onCancelTaskStep?: (taskId: string, stepId: string) => void;
  onOpenEmailTab?: (messageId: string, subject: string) => void;
  onPreviewMailAttachment?: (messageId: string, partId: string) => void;
  onDownloadMailAttachment?: (messageId: string, partId: string) => void;
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

  const prevListEl = container.querySelector(
    "#chat-messages-list"
  ) as HTMLElement | null;
  const isSameConv = state.chatLastRenderedConvId === detail.conversation.id;
  const prevScrollTop = prevListEl?.scrollTop ?? 0;
  const prevWasNearBottom =
    !prevListEl ||
    prevListEl.scrollHeight - prevListEl.scrollTop - prevListEl.clientHeight <=
      140;
  const shouldStickToBottom =
    !isSameConv || !prevListEl || state.isStreaming || state.chatPinToBottom || prevWasNearBottom;
  state.chatLastRenderedConvId = detail.conversation.id;

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

  const readableTabSources = activeTabSources.filter((s) => s.textChars > 0);
  const allOpenTabsEmpty =
    activeTabSources.length > 0 && readableTabSources.length === 0;

  const emptyContextBannerHtml =
    allOpenTabsEmpty && !state.webSearchEnabled && !state.isStreaming
      ? `
        <div class="composer-context-row">
          <span class="muted">no readable page in context ·</span>
          <button id="chat-recapture-all-btn" class="citation-link">[recapture]</button>
          <button id="chat-enable-web-banner-btn" class="citation-link">[turn on + web]</button>
          <span class="muted">[ask without pages]</span>
        </div>
      `
      : "";

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
          <span class="muted">context (${readableTabSources.length}/${activeTabSources.length}):</span>
          <div class="composer-context-pills">
            ${activeTabSources
              .map((item) => {
                const stat = state.sourceStats[item.sourceId];
                const charsCaptured = stat?.chars_captured ?? item.textChars;
                const captureMode = stat?.capture_mode ?? item.captureMode;
                if (charsCaptured === 0) {
                  return `
              <div
                class="context-pill muted ${state.activeTabId === item.tab.id ? "active" : ""}"
                data-pill-tab-id="${escapeHtml(item.tab.id)}"
                title="${escapeHtml(item.title)} (${escapeHtml(item.url)}) - empty capture (excluded from prompt)"
              >
                <span class="truncate">${escapeHtml(item.domain)} · ${escapeHtml(item.title.slice(0, 18))} · empty</span>
                <button
                  class="citation-link"
                  data-pill-recapture-tab-id="${escapeHtml(item.tab.id)}"
                  title="recapture live DOM from this tab"
                >[recapture]</button>
                <button
                  class="tab-close-btn"
                  data-pill-close-tab-id="${escapeHtml(item.tab.id)}"
                  title="close tab and remove from context"
                >x</button>
              </div>
            `;
                }
                const modeLabel =
                  captureMode === "fetch" ? " · public fetch" : "";
                const cutLabel = stat?.was_cut ? " [cut]" : "";
                const charsLabel = ` · ${charsCaptured.toLocaleString()}c${cutLabel}`;
                const tooltipText =
                  captureMode === "fetch"
                    ? `captured from public URL, not your logged-in tab (${charsCaptured.toLocaleString()} chars)`
                    : `${item.title} (${item.url}) - ${charsCaptured.toLocaleString()} chars${cutLabel}`;
                return `
              <div
                class="context-pill ${state.activeTabId === item.tab.id ? "active" : ""}"
                data-pill-tab-id="${escapeHtml(item.tab.id)}"
                title="${escapeHtml(tooltipText)}"
              >
                <span class="muted">[${item.citeIndex ?? item.index}]</span>
                <span class="truncate">${escapeHtml(item.domain)} · ${escapeHtml(item.title.slice(0, 20))}${escapeHtml(modeLabel)}${escapeHtml(charsLabel)}</span>
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
            ${
              activeTabSources.length >= 2
                ? `<button id="chat-compare-these-btn" class="context-add-btn" title="run Comparer agent across open tabs">[compare these]</button>`
                : ""
            }
          </div>
        </div>
        ${emptyContextBannerHtml}
      `;

  const stepsHtml = state.streamingSteps
    .map(
      (step, idx) =>
        `<div class="streaming-step-line">${idx === state.streamingSteps.length - 1 ? "&gt;" : "ok"} ${escapeHtml(step)}</div>`
    )
    .join("");

  const isMailConv = detail.conversation.origin === "mail";
  const mailEffectiveOn = isMailConv || state.mailContextEnabled;
  const triageSourceIds = state.mailTriageSources.map((s) => s.id);
  const mailSuggestionsHtml =
    isMailConv && !state.isStreaming
      ? `
        <div class="composer-controls">
          <span class="muted">suggestions:</span>
          <button class="citation-link" data-chat-suggest="what do I need to deal with today?">[what do I need to deal with today?]</button>
          <button class="citation-link" data-chat-suggest="summarize unread">[summarize unread]</button>
          <button class="citation-link" data-chat-suggest="draft a reply to [1]">[draft a reply to [1]]</button>
        </div>
      `
      : "";

  const convTasks = state.conversationTasks[detail.conversation.id] ?? [];
  const taskCardsHtml = convTasks
    .map((task) => renderTaskCardBlock(task))
    .join("");
  const watchNoticeHtml = state.watchStatusNotice
    ? `<div class="kb-card muted">${escapeHtml(state.watchStatusNotice)}</div>`
    : "";

  container.innerHTML = `
    <div class="chat-column">
      <div class="chat-messages" id="chat-messages-list">
        ${watchNoticeHtml}
        ${
          isMailConv && state.mailTriageOverview
            ? renderMessageBlock(
                "mail-triage-overview",
                "assistant",
                state.mailTriageOverview,
                "triage overview",
                JSON.stringify(triageSourceIds)
              )
            : ""
        }
        ${
          messages.length === 0 && convTasks.length === 0 && !state.isStreaming && !(isMailConv && state.mailTriageOverview)
            ? `<div class="muted">no messages in this conversation yet.</div>`
            : messages
                .map((m) =>
                  renderMessageBlock(
                    m.id,
                    m.role,
                    m.content,
                    m.model,
                    m.source_ids_json,
                    m.cited_sources ?? state.messageCitedSources[m.id],
                    m.proposals ?? state.messageProposals[m.id],
                    m.citation_check,
                    m.citations_ok,
                    m.citations_flagged,
                    m.findings ?? state.messageFindings[m.id],
                    m.brain_sources ?? state.messageBrainSources[m.id],
                    m.email_cards ?? state.messageEmailCards[m.id]
                  )
                )
                .join("")
        }
        ${taskCardsHtml}
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
        ${mailSuggestionsHtml}
        <div class="composer-input-row">
          <span class="muted">&gt;</span>
          <input
            id="chat-composer-input"
            class="composer-input"
            type="text"
            spellcheck="false"
            autocorrect="off"
            autocapitalize="off"
            placeholder="${escapeHtml(offlineNotice)}"
            ${state.isStreaming ? "disabled" : ""}
          />
          <span class="caret-blink">▌</span>
          <button id="chat-send-btn" ${state.isStreaming ? "disabled" : ""}>${state.isStreaming ? "[in progress...]" : "[send]"}</button>
        </div>

        <div class="composer-meta-row">
          <span class="composer-status-label" title="${escapeHtml(getModelPrivacySummary(state.selectedModel))}">${state.sidecar.online ? "models [ok]" : "models [offline]"} · ${escapeHtml(getModelPrivacySummary(state.selectedModel))}</span>
          <div class="composer-controls">
            <label class="muted">model:</label>
            <select id="chat-model-select">
              ${getAvailableModelsForPicker()
                .map(
                  (m) => `
                <option value="${escapeHtml(m.id)}" ${state.selectedModel === m.id ? "selected" : ""}>
                  ${escapeHtml(m.label)}
                </option>
              `
                )
                .join("")}
            </select>
            <button id="chat-web-toggle" class="${state.webSearchEnabled ? "active" : ""}">
              web: ${state.webSearchEnabled ? "on" : "off"}
            </button>
            <button id="chat-mail-toggle" class="${mailEffectiveOn ? "active" : ""}" title="include top 5 FTS matches from mail.sqlite as sources">
              mail: ${mailEffectiveOn ? "on" : "off"}
            </button>
          </div>
        </div>
      </div>
    </div>
  `;

  bindChatEvents(container, actions);

  const listEl = container.querySelector(
    "#chat-messages-list"
  ) as HTMLElement | null;
  if (listEl) {
    if (shouldStickToBottom) {
      listEl.scrollTop = listEl.scrollHeight;
      window.requestAnimationFrame(() => {
        listEl.scrollTop = listEl.scrollHeight;
      });
    } else if (isSameConv) {
      listEl.scrollTop = prevScrollTop;
    }
    listEl.addEventListener("scroll", () => {
      const distFromBottom =
        listEl.scrollHeight - listEl.scrollTop - listEl.clientHeight;
      state.chatPinToBottom = distFromBottom <= 140;
    });
  }

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
  citationsFlagged?: number | null,
  findings?: FindingItem[],
  brainSources?: BrainCitationItem[],
  emailCards?: ChatEmailCard[]
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
      trimmed.startsWith("gemma stopped responding after 30 s.") ||
      trimmed.startsWith("models [offline]"));

  const plainErr = isErrorMsg ? formatPlainErrorMessage(content) : null;
  const debugExpanded = Boolean(state.expandedDebugMessages[msgId]);
  const formattedBody = plainErr
    ? escapeHtml(plainErr.summary)
    : formatCitationsInText(content, sourceIds, citationCheck, brainSources);
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

  let readFooterHtml = "";
  if (role === "assistant" && !isErrorMsg && sourceIds.length > 0) {
    let totalSent = 0;
    let cutCount = 0;
    for (const sid of sourceIds) {
      const st = state.sourceStats[sid];
      if (st) {
        totalSent += st.chars_sent || st.chars_captured || 0;
        if (st.was_cut) cutCount += 1;
      } else {
        const dbSrc = state.activeDetail?.sources.find((s) => s.id === sid);
        const chars = dbSrc?.text_chars ?? 0;
        totalSent += Math.min(6000, chars);
        if (chars > 6000) cutCount += 1;
      }
    }
    readFooterHtml = `<div class="muted">read ${sourceIds.length} source${sourceIds.length === 1 ? "" : "s"} · ${totalSent.toLocaleString()} chars · ${cutCount} cut</div>`;
  }

  const retryButtonHtml =
    isErrorMsg
      ? `
      <div class="composer-controls">
        ${
          state.lastUserPrompt
            ? `<button class="citation-link" data-retry-prompt="${escapeHtml(state.lastUserPrompt)}">[retry]</button>
               <button class="citation-link" data-use-planck-prompt="${escapeHtml(state.lastUserPrompt)}">[use planck instead]</button>`
            : ""
        }
        ${
          plainErr && plainErr.rawDetail && plainErr.rawDetail !== plainErr.summary
            ? `<button class="citation-link" data-toggle-debug-msg="${escapeHtml(msgId)}">[debug]</button>`
            : ""
        }
      </div>
      ${
        debugExpanded && plainErr
          ? `<div class="muted">${escapeHtml(plainErr.rawDetail)}</div>`
          : ""
      }
    `
      : "";

  const ytVideos: Array<{ videoId: string; title: string; url: string }> = [];
  const seenVidIds = new Set<string>();
  const addYtIfMatch = (rawUrl: string, rawTitle: string) => {
    const m = rawUrl.match(
      /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([A-Za-z0-9_-]{11})/
    );
    if (m && !seenVidIds.has(m[1])) {
      seenVidIds.add(m[1]);
      ytVideos.push({
        videoId: m[1],
        title: rawTitle || `YouTube video (${m[1]})`,
        url: `https://www.youtube.com/watch?v=${m[1]}`,
      });
    }
  };
  for (const f of findings ?? []) {
    addYtIfMatch(f.page_url || f.image_url, f.title);
  }
  for (const cs of citedSources ?? []) {
    addYtIfMatch(cs.url, cs.title);
  }
  const inlineYtMatches = content.matchAll(
    /https?:\/\/(?:www\.)?(?:youtube\.com\/watch\?v=|youtu\.be\/)([A-Za-z0-9_-]{11})/g
  );
  for (const m of inlineYtMatches) {
    addYtIfMatch(m[0], `YouTube video (${m[1]})`);
  }

  const embeddedVideosHtml =
    ytVideos.length > 0
      ? `
      <div class="msg-findings-section">
        <div class="muted msg-findings-header">embedded video players (${ytVideos.length}):</div>
        <div class="chat-video-grid">
          ${ytVideos
            .slice(0, 4)
            .map(
              (v) => `
            <div class="kb-card chat-video-card">
              <iframe
                class="chat-video-embed"
                src="https://www.youtube-nocookie.com/embed/${escapeHtml(v.videoId)}"
                title="${escapeHtml(v.title)}"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowfullscreen
                loading="lazy"
              ></iframe>
              <div class="rail-row">
                <span class="truncate" title="${escapeHtml(v.title)}">${escapeHtml(v.title)}</span>
                <button class="citation-link" data-open-tab-url="${escapeHtml(v.url)}" data-open-tab-title="${escapeHtml(v.title)}">[open tab]</button>
              </div>
            </div>
          `
            )
            .join("")}
        </div>
      </div>
    `
      : "";

  const nonVideoFindings = (findings ?? []).filter(
    (f) =>
      !/(?:youtube\.com\/watch\?v=|youtu\.be\/)/.test(
        f.page_url || f.image_url || ""
      )
  );

  const effectiveCitedSources: Array<{ url: string; title: string }> = [
    ...(citedSources ?? []),
  ];
  const seenPreviewUrls = new Set(
    effectiveCitedSources.map((cs) => cs.url.trim()).filter(Boolean)
  );
  if (role === "assistant" && !isErrorMsg) {
    // 1. Hydrate from inline Markdown links `[Title](https://...)` (excluding YouTube already rendered as players)
    for (const mLink of content.matchAll(
      /\[([^\][]+)\]\((https?:\/\/[^\s)]+)\)/g
    )) {
      const lTitle = mLink[1].trim();
      const lUrl = mLink[2].trim();
      if (
        lUrl &&
        !seenPreviewUrls.has(lUrl) &&
        !/(?:youtube\.com\/watch\?v=|youtu\.be\/)/.test(lUrl)
      ) {
        seenPreviewUrls.add(lUrl);
        effectiveCitedSources.push({ url: lUrl, title: lTitle || lUrl });
      }
    }
    // 2. Hydrate from HTTP(S) `sourceIds` or matching `state.activeDetail.sources`
    for (const sid of sourceIds) {
      if (effectiveCitedSources.length >= 6) break;
      const dbSrc = state.activeDetail?.sources.find((s) => s.id === sid);
      const candUrl = (
        dbSrc?.url || (sid.startsWith("http") ? sid : "")
      ).trim();
      const candTitle = (dbSrc?.title || candUrl).trim();
      if (
        candUrl.startsWith("http") &&
        !seenPreviewUrls.has(candUrl) &&
        !/(?:youtube\.com\/watch\?v=|youtu\.be\/)/.test(candUrl)
      ) {
        seenPreviewUrls.add(candUrl);
        effectiveCitedSources.push({ url: candUrl, title: candTitle || candUrl });
      }
    }
  }

  const pagePreviewCardsHtml =
    effectiveCitedSources.length > 0
      ? `
      <div class="msg-findings-section">
        <div class="muted msg-findings-header">page previews (${effectiveCitedSources.length}):</div>
        <div class="chat-preview-cards-grid">
          ${effectiveCitedSources
            .slice(0, 6)
            .map((cs, idx) => {
              const dom = extractDomain(cs.url);
              return `
              <div class="kb-card chat-page-preview-card" data-open-tab-url="${escapeHtml(cs.url)}" data-open-tab-title="${escapeHtml(cs.title)}">
                <div class="kb-card-header">
                  <span><strong>[${idx + 1}] ${escapeHtml(dom)}</strong></span>
                  <button class="citation-link" data-open-tab-url="${escapeHtml(cs.url)}" data-open-tab-title="${escapeHtml(cs.title)}">[open tab ↗]</button>
                </div>
                <div class="truncate" title="${escapeHtml(cs.title || cs.url)}">${escapeHtml(cs.title || cs.url)}</div>
                <div class="muted truncate">${escapeHtml(cs.url)}</div>
              </div>
            `;
            })
            .join("")}
        </div>
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

  const findingsHtml =
    nonVideoFindings.length > 0
      ? `
      <div class="msg-findings-section">
        <div class="muted msg-findings-header">captured visual findings (${nonVideoFindings.length}):</div>
        <div class="msg-findings-grid">
          ${nonVideoFindings
            .map(
              (f) => `
            <div
              class="msg-finding-card"
              data-open-tab-url="${escapeHtml(f.page_url || f.image_url)}"
              data-open-tab-title="${escapeHtml(f.title)}"
              title="${escapeHtml(f.title)}${f.price ? ` · ${escapeHtml(f.price)}` : ""}"
            >
              <img
                class="msg-finding-img"
                src="${escapeHtml(f.image_url)}"
                alt="${escapeHtml(f.title)}"
                loading="lazy"
              />
              <div class="msg-finding-meta">
                <div class="msg-finding-title truncate">${escapeHtml(f.title)}</div>
                ${f.price ? `<div class="msg-finding-price">${escapeHtml(f.price)}</div>` : ""}
              </div>
            </div>
          `
            )
            .join("")}
        </div>
      </div>
    `
      : "";

  const emailCardsHtml = renderChatEmailCardsHtml(msgId, emailCards, sourceIds);

  const citedBrainItems =
    role === "assistant" && !isErrorMsg && brainSources && brainSources.length > 0
      ? brainSources.filter(
          (bs) =>
            content.includes(`[${bs.cite_label}]`) ||
            (sourceIds.length === 0 && bs.b_index === 1)
        )
      : [];
  const brainCitationsListHtml =
    citedBrainItems.length > 0
      ? `
      <div class="composer-controls">
        <span class="muted">brain memory:</span>
        ${citedBrainItems
          .map(
            (bs) => `
          <button
            class="citation-link"
            data-brain-cite="${escapeHtml(bs.cite_label)}"
            data-brain-slug="${escapeHtml(bs.slug)}"
            title="open Brain card: ${escapeHtml(bs.name)}"
          >[${escapeHtml(bs.cite_label)}] ${escapeHtml(bs.name)}</button>
        `
          )
          .join("")}
      </div>
    `
      : "";

  const watchBtnHtml =
    role === "assistant" && !isErrorMsg && msgId !== "mail-triage-overview"
      ? ` <button class="citation-link" data-watch-msg="${escapeHtml(msgId)}" title="watch this answer or source for changes">[watch]</button>`
      : "";

  return `
    <div class="msg-block ${isErrorMsg ? "msg-error-block" : ""}">
      <div class="msg-header">
        <span>${escapeHtml(role)}${statusBadge}</span>
        <span>${modelLabel}${srcCountLabel}${escapeHtml(citeStatsLabel)}${watchBtnHtml}</span>
      </div>
      <div class="msg-body">${formattedBody}</div>
      ${readFooterHtml}
      ${brainCitationsListHtml}
      ${embeddedVideosHtml}
      ${emailCardsHtml}
      ${findingsHtml}
      ${pagePreviewCardsHtml}
      ${proposalsHtml}
      ${retryButtonHtml}
    </div>
  `;
}

function renderChatEmailCardsHtml(
  msgId: string,
  emailCards: ChatEmailCard[] | undefined,
  sourceIds: string[]
): string {
  const cards: ChatEmailCard[] = [...(emailCards ?? [])];
  const seenIds = new Set(cards.map((c) => c.message_id));

  for (const sid of sourceIds) {
    if (sid.startsWith("mail:")) {
      const mid = sid.slice(5).trim();
      if (mid && !seenIds.has(mid)) {
        const cached = state.mailMessageDetails[mid];
        const mObj = (cached?.message ?? cached) as Record<string, unknown> | undefined;
        if (mObj && mObj.id) {
          seenIds.add(mid);
          const parts = (mObj.parts ?? {}) as Record<string, string>;
          cards.push({
            message_id: mid,
            source_id: sid,
            subject: String(mObj.subject ?? "(no subject)"),
            from_name: String(mObj.from_name ?? ""),
            from_addr: String(mObj.from_addr ?? ""),
            date: Number(mObj.date ?? 0),
            label: String(mObj.label ?? "email"),
            snippet: String(mObj.snippet ?? ""),
            body_text: String(parts.new || mObj.body_text || ""),
            quoted_text: String(parts.quote || ""),
            attachments: (mObj.attachments as ChatEmailCard["attachments"]) ?? [],
          });
        }
      }
    }
  }

  if (cards.length === 0) return "";

  return `
    <div class="msg-findings-section">
      <div class="muted msg-findings-header">referenced emails &amp; attachments (${cards.length}):</div>
      ${cards
        .map((ec) => {
          const expandKey = `${msgId}:${ec.message_id}`;
          const isExpanded = Boolean(state.expandedChatEmails[expandKey]);
          const fromDisp = ec.from_name
            ? `${ec.from_name} <${ec.from_addr}>`
            : ec.from_addr;
          const atts = ec.attachments ?? [];
          const attsHtml =
            atts.length > 0
              ? `
            <div class="composer-controls">
              <span class="muted">attachments (${atts.length}):</span>
              ${atts
                .map((att) => {
                  const attKey = `${ec.message_id}:${att.part_id}`;
                  const previewObj = state.previewedAttachments[attKey];
                  const sizeKb = Math.max(1, Math.round((att.size || 0) / 1024));
                  return `
                    <span class="context-pill">
                      <span>${escapeHtml(att.filename)} (${sizeKb} KB)</span>
                      <button
                        class="citation-link"
                        data-chat-preview-att="${escapeHtml(ec.message_id)}"
                        data-part-id="${escapeHtml(String(att.part_id))}"
                      >${previewObj ? "[hide preview]" : "[preview in chat]"}</button>
                      <button
                        class="citation-link"
                        data-chat-download-att="${escapeHtml(ec.message_id)}"
                        data-part-id="${escapeHtml(String(att.part_id))}"
                      >[download]</button>
                    </span>
                  `;
                })
                .join("")}
            </div>
            ${atts
              .map((att) => {
                const attKey = `${ec.message_id}:${att.part_id}`;
                const prev = state.previewedAttachments[attKey];
                if (!prev || !prev.data_url) return "";
                if (prev.mime.startsWith("image/")) {
                  return `<div class="kb-card"><img class="chat-attachment-img" src="${escapeHtml(prev.data_url)}" alt="${escapeHtml(prev.filename)}" /></div>`;
                }
                return `<div class="kb-card"><embed class="chat-attachment-embed" type="${escapeHtml(prev.mime)}" src="${escapeHtml(prev.data_url)}" /></div>`;
              })
              .join("")}
          `
              : "";

          return `
            <div class="kb-card">
              <div class="kb-card-header">
                <span><strong>${escapeHtml(ec.subject)}</strong> · <span class="source-cut-badge">${escapeHtml(ec.label)}</span></span>
                <div>
                  <button
                    class="citation-link"
                    data-chat-toggle-email="${escapeHtml(expandKey)}"
                    data-email-mid="${escapeHtml(ec.message_id)}"
                  >${isExpanded ? "[hide email in chat]" : "[open email in chat]"}</button>
                  <button
                    class="citation-link"
                    data-chat-open-email-tab="${escapeHtml(ec.message_id)}"
                    data-email-subj="${escapeHtml(ec.subject)}"
                  >[open in tab]</button>
                </div>
              </div>
              <div class="muted">from: ${escapeHtml(fromDisp)}</div>
              ${
                isExpanded
                  ? `<div class="msg-body chat-inline-email-body"><pre>${escapeHtml(ec.body_text || ec.snippet || "(empty body)")}${ec.quoted_text ? `\n\n--- Quoted Thread ---\n${escapeHtml(ec.quoted_text)}` : ""}</pre></div>`
                  : `<div class="muted truncate">${escapeHtml(ec.snippet || ec.body_text.slice(0, 160))}</div>`
              }
              ${attsHtml}
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderTaskCardBlock(task: AgentTaskCard): string {
  const isRunning =
    task.status === "running" || task.status === "waiting_confirm";
  const stopBtnHtml = isRunning
    ? `<button class="citation-link" data-task-stop="${escapeHtml(task.id)}" data-stop-token="${escapeHtml(task.stop_token)}">[stop]</button>`
    : "";

  const stepsHtml = (task.steps ?? [])
    .map((step) => {
      if (step.kind === "send_gate") {
        const summary = step.action_summary || step.text;
        if (step.status === "waiting_confirm") {
          return `
            <div class="rail-row">
              <span>[send-gate] ${escapeHtml(summary)}</span>
              <span>
                <button
                  class="citation-link"
                  data-task-confirm="${escapeHtml(task.id)}"
                  data-step-id="${escapeHtml(step.id)}"
                  data-confirm-token="${escapeHtml(step.confirm_token ?? "")}"
                >[confirm]</button>
                <button
                  class="citation-link"
                  data-task-cancel="${escapeHtml(task.id)}"
                  data-step-id="${escapeHtml(step.id)}"
                >[cancel]</button>
              </span>
            </div>
          `;
        }
        return `<div class="streaming-step-line">[send-gate · ${escapeHtml(step.status)}] ${escapeHtml(summary)}</div>`;
      }
      const prefix = step.status === "running" ? "&gt;" : "ok";
      return `<div class="streaming-step-line">${prefix} ${escapeHtml(step.text)}</div>`;
    })
    .join("");

  const activeSourceIds = (state.activeDetail?.sources ?? []).map((s) => s.id);
  const resultHtml = task.result_md
    ? `<div class="msg-body">${formatCitationsInText(task.result_md, activeSourceIds)}</div>`
    : "";

  return `
    <div class="msg-block" data-task-card="${escapeHtml(task.id)}">
      <div class="msg-header">
        <span>task · ${escapeHtml(task.agent)} [${escapeHtml(task.status)}]</span>
        <span>goal: ${escapeHtml(task.goal)} ${stopBtnHtml}</span>
      </div>
      <div class="streaming-status-box">
        <div class="streaming-steps-list">${stepsHtml}</div>
      </div>
      ${resultHtml}
    </div>
  `;
}

function renderMarkdownTablesInHtml(escapedWithCites: string): string {
  const lines = escapedWithCites.split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();
    const nextLine = (lines[i + 1] ?? "").trim();
    if (
      line.startsWith("|") &&
      line.endsWith("|") &&
      nextLine.startsWith("|") &&
      nextLine.includes("---")
    ) {
      const parseRow = (r: string) =>
        r
          .slice(1, -1)
          .split("|")
          .map((c) => c.trim().replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>"));
      const headers = parseRow(line);
      i += 2;
      const bodyRows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|") && lines[i].trim().endsWith("|")) {
        bodyRows.push(parseRow(lines[i].trim()));
        i += 1;
      }
      const thead = `<thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>`;
      const tbody = `<tbody>${bodyRows
        .map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`)
        .join("")}</tbody>`;
      out.push(`<table class="kb-table">${thead}${tbody}</table>`);
      continue;
    }
    out.push(lines[i]);
    i += 1;
  }
  return out.join("\n");
}

export function formatCitationsInText(
  text: string,
  sourceIds: string[],
  citationCheck?: CitationCheckEntry[],
  brainSources?: BrainCitationItem[]
): string {
  const escaped = escapeHtml(text).replace(
    /\[unsourced\]/g,
    `<span class="msg-error-badge" title="citation index outside source list">[unsourced]</span>`
  );
  const withSrcCites = escaped.replace(/\[(\d+)\]/g, (_match, digits) => {
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

  const withBrainCites = withSrcCites.replace(/\[B(\d+)\]/g, (_match, digits) => {
    const bIdx = Number(digits);
    const bKey = `B${bIdx}`;
    const outOfRangeCheck = citationCheck?.find(
      (c) => String(c.n) === bKey && c.out_of_range
    );
    const maxB = brainSources?.length ?? 0;
    if (bIdx < 1 || (maxB > 0 && bIdx > maxB) || outOfRangeCheck) {
      return `<span class="msg-error-badge" title="brain citation [${bKey}] outside ${maxB} brain item(s)">[unsourced]</span>`;
    }
    const bs = brainSources?.[bIdx - 1];
    const slug = bs?.slug ?? "";
    const labelName = bs?.name ?? bKey;
    const flaggedEntries = (citationCheck ?? []).filter(
      (c) => String(c.n) === bKey && !c.ok
    );
    if (flaggedEntries.length > 0) {
      const missingItems = Array.from(
        new Set(flaggedEntries.flatMap((e) => e.missing ?? []))
      );
      const tooltip = `not found in brain [${bKey}] (${labelName}): ${missingItems.join(", ")}`;
      return `<button class="citation-link msg-error-badge" data-brain-cite="${escapeHtml(bKey)}" data-brain-slug="${escapeHtml(slug)}" title="${escapeHtml(tooltip)}">[${escapeHtml(bKey)}?]</button>`;
    }
    return `<button class="citation-link" data-brain-cite="${escapeHtml(bKey)}" data-brain-slug="${escapeHtml(slug)}" title="open Brain card: ${escapeHtml(labelName)}">[${escapeHtml(bKey)}]</button>`;
  });
  const withMdLinksAndBold = withBrainCites
    .replace(
      /\[([^\][]+)\]\((https?:\/\/[^\s)]+)\)/g,
      (_m, labelTxt, urlTxt) =>
        `<button class="citation-link inline-page-link" data-open-tab-url="${urlTxt}" data-open-tab-title="${labelTxt}" title="open ${urlTxt} in tab">${labelTxt} ↗</button>`
    )
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  return renderMarkdownTablesInHtml(withMdLinksAndBold);
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

  container
    .querySelector("#chat-mail-toggle")
    ?.addEventListener("click", () => {
      if (actions.onToggleMail) {
        actions.onToggleMail();
      }
    });

  container.querySelectorAll("[data-chat-suggest]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (state.isStreaming) return;
      const prompt = (btn as HTMLElement).getAttribute("data-chat-suggest");
      if (prompt) {
        actions.onSendMessage(prompt);
      }
    });
  });

  container.querySelectorAll("[data-citation-idx]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const idx = Number(el.getAttribute("data-citation-idx"));
      const srcId = el.getAttribute("data-citation-src") || null;
      actions.onClickCitation(idx, srcId);
    });
  });

  container.querySelectorAll("[data-brain-slug]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const slug = el.getAttribute("data-brain-slug") || "";
      const citeLabel = el.getAttribute("data-brain-cite") || "B1";
      if (actions.onClickBrainCitation) {
        actions.onClickBrainCitation(slug, citeLabel);
      }
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

  container.querySelectorAll("[data-use-planck-prompt]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (state.isStreaming) return;
      const prompt = (btn as HTMLElement).getAttribute("data-use-planck-prompt");
      if (!prompt) return;
      if (actions.onUsePlanckInstead) {
        actions.onUsePlanckInstead(prompt);
      } else {
        actions.onChangeModel("planck3 (web)");
        actions.onSendMessage(prompt);
      }
    });
  });

  container.querySelectorAll("[data-pill-tab-id]").forEach((pill) => {
    pill.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      if (
        target.closest("[data-pill-close-tab-id]") ||
        target.closest("[data-pill-recapture-tab-id]")
      ) {
        return;
      }
      const tabId = (pill as HTMLElement).getAttribute("data-pill-tab-id");
      if (tabId && actions.onSelectTab) {
        actions.onSelectTab(tabId);
      }
    });
  });

  container.querySelectorAll("[data-pill-recapture-tab-id]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const tabId = (btn as HTMLElement).getAttribute(
        "data-pill-recapture-tab-id"
      );
      if (tabId && actions.onRecaptureTab) {
        actions.onRecaptureTab(tabId);
      }
    });
  });

  container
    .querySelector("#chat-recapture-all-btn")
    ?.addEventListener("click", () => {
      if (actions.onRecaptureAllTabs) {
        actions.onRecaptureAllTabs();
      }
    });

  container
    .querySelector("#chat-enable-web-banner-btn")
    ?.addEventListener("click", () => {
      actions.onToggleWeb();
    });

  container.querySelectorAll("[data-toggle-debug-msg]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mid = (btn as HTMLElement).getAttribute("data-toggle-debug-msg");
      if (!mid) return;
      state.expandedDebugMessages[mid] = !state.expandedDebugMessages[mid];
      renderChatPanel(container, actions);
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

  container
    .querySelector("#chat-compare-these-btn")
    ?.addEventListener("click", () => {
      if (actions.onRunComparer) {
        actions.onRunComparer();
      }
    });

  container.querySelectorAll("[data-watch-msg]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mid = (btn as HTMLElement).getAttribute("data-watch-msg") ?? "";
      const msgObj = state.activeDetail?.messages.find((m) => m.id === mid);
      if (mid && actions.onWatchAnswer) {
        actions.onWatchAnswer(mid, msgObj?.content ?? "");
      }
    });
  });

  container.querySelectorAll("[data-task-stop]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const taskId = el.getAttribute("data-task-stop") ?? "";
      const stopToken = el.getAttribute("data-stop-token") ?? "";
      if (taskId && actions.onStopTask) {
        actions.onStopTask(taskId, stopToken);
      }
    });
  });

  container.querySelectorAll("[data-task-confirm]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const taskId = el.getAttribute("data-task-confirm") ?? "";
      const stepId = el.getAttribute("data-step-id") ?? "";
      const token = el.getAttribute("data-confirm-token") ?? "";
      if (taskId && actions.onConfirmTaskStep) {
        actions.onConfirmTaskStep(taskId, stepId, token);
      }
    });
  });

  container.querySelectorAll("[data-task-cancel]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const taskId = el.getAttribute("data-task-cancel") ?? "";
      const stepId = el.getAttribute("data-step-id") ?? "";
      if (taskId && actions.onCancelTaskStep) {
        actions.onCancelTaskStep(taskId, stepId);
      }
    });
  });

  container.querySelectorAll("[data-chat-toggle-email]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const key = el.getAttribute("data-chat-toggle-email") ?? "";
      const mid = el.getAttribute("data-email-mid") ?? "";
      if (!key) return;
      state.expandedChatEmails[key] = !state.expandedChatEmails[key];
      if (state.expandedChatEmails[key] && mid && actions.onPreviewMailAttachment) {
        // Ensure full message detail is loaded if not cached yet
      }
      renderChatPanel(container, actions);
    });
  });

  container.querySelectorAll("[data-chat-open-email-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const mid = el.getAttribute("data-chat-open-email-tab") ?? "";
      const subj = el.getAttribute("data-email-subj") ?? "mail";
      if (mid && actions.onOpenEmailTab) {
        actions.onOpenEmailTab(mid, subj);
      }
    });
  });

  container.querySelectorAll("[data-chat-preview-att]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const mid = el.getAttribute("data-chat-preview-att") ?? "";
      const partId = el.getAttribute("data-part-id") ?? "";
      if (mid && actions.onPreviewMailAttachment) {
        actions.onPreviewMailAttachment(mid, partId);
      }
    });
  });

  container.querySelectorAll("[data-chat-download-att]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const mid = el.getAttribute("data-chat-download-att") ?? "";
      const partId = el.getAttribute("data-part-id") ?? "";
      if (mid && actions.onDownloadMailAttachment) {
        actions.onDownloadMailAttachment(mid, partId);
      }
    });
  });
}
