import { icon } from "./design-system/icons";
import {
  escapeHtml,
  extractDomain,
  formatPlainErrorMessage,
  getActiveStream,
  getActiveTabSources,
  getAvailableModelsForPicker,
  getModelPrivacySummary,
  isConvStreaming,
  state,
} from "./state";
import type {
  AgentTaskCard,
  AnswerMeta,
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
  onNewsTrustDelta?: (msgId: string, domain: string, delta: number) => void;
  onOpenNewsLane?: (lane: string) => void;
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

  const convId = detail.conversation.id;
  const convStream = getActiveStream(convId);
  const isStreamingHere = Boolean(convStream);

  const prevListEl = container.querySelector(
    "#chat-messages-list"
  ) as HTMLElement | null;
  const isSameConv = state.chatLastRenderedConvId === convId;
  const prevScrollTop = prevListEl?.scrollTop ?? 0;
  const prevWasNearBottom =
    !prevListEl ||
    prevListEl.scrollHeight - prevListEl.scrollTop - prevListEl.clientHeight <=
      140;
  const shouldStickToBottom =
    !isSameConv || !prevListEl || isStreamingHere || state.chatPinToBottom || prevWasNearBottom;
  state.chatLastRenderedConvId = convId;

  const existingInput = container.querySelector(
    "#chat-composer-input"
  ) as HTMLTextAreaElement | HTMLInputElement | null;
  const wasFocused =
    Boolean(existingInput) && document.activeElement === existingInput;
  const preservedValue = existingInput?.value ?? "";
  const preservedSelection =
    existingInput?.selectionStart ?? preservedValue.length;

  const messages = detail.messages;
  const activeTabSources = getActiveTabSources(detail);
  const elapsedSec =
    convStream && convStream.startedAt > 0
      ? ((Date.now() - convStream.startedAt) / 1000).toFixed(1)
      : "0.0";
  const phaseLabel = convStream?.phase || "processing";
  const statusLineText =
    convStream?.status || "request in progress...";

  const offlineNotice = !state.sidecar.online
    ? "Sidecar offline — start runtime to ask"
    : isStreamingHere
      ? statusLineText
      : activeTabSources.length > 0
        ? `Ask about ${activeTabSources.length} open tab${activeTabSources.length === 1 ? "" : "s"} or type a question...`
        : "Ask anything, or open a tab to include it in context...";

  const readableTabSources = activeTabSources.filter((s) => s.textChars > 0);
  const allOpenTabsEmpty =
    activeTabSources.length > 0 && readableTabSources.length === 0;

  const emptyContextBannerHtml =
    allOpenTabsEmpty && !state.webSearchEnabled && !isStreamingHere
      ? `
        <div class="composer-ctx-warn">
          <span>No readable page text captured yet.</span>
          <button id="chat-recapture-all-btn" class="btn-text" type="button">Recapture</button>
          <button id="chat-enable-web-banner-btn" class="btn-text" type="button">Enable web search</button>
        </div>
      `
      : "";

  const visibleContextSources =
    state.composerContextExpanded || activeTabSources.length <= 2
      ? activeTabSources
      : activeTabSources.slice(0, 2);
  const collapsedExtraCount =
    !state.composerContextExpanded && activeTabSources.length > 2
      ? activeTabSources.length - 2
      : 0;

  const renderContextPillHtml = (item: (typeof activeTabSources)[number]) => {
    const stat = state.sourceStats[item.sourceId];
    const charsCaptured = stat?.chars_captured ?? item.textChars;
    const captureMode = stat?.capture_mode ?? item.captureMode;
    const isEmpty = charsCaptured === 0;
    const isActive = state.activeTabId === item.tab.id;
    const modeLabel = captureMode === "fetch" ? " · public fetch" : "";
    const cutLabel = stat?.was_cut ? " · cut" : "";
    const tooltipText = isEmpty
      ? `${item.title} (${item.url}) — empty capture`
      : captureMode === "fetch"
        ? `Captured from public URL (${charsCaptured.toLocaleString()} chars)${modeLabel}${cutLabel}`
        : `${item.title} (${item.url}) — ${charsCaptured.toLocaleString()} chars${modeLabel}${cutLabel}`;

    return `
      <div
        class="pill ${isActive ? "accent" : ""} ${isEmpty ? "muted" : ""}"
        data-pill-tab-id="${escapeHtml(item.tab.id)}"
        title="${escapeHtml(tooltipText)}"
      >
        <span>${isEmpty ? "—" : `[${item.citeIndex ?? item.index}]`}</span>
        <span class="truncate">${escapeHtml(item.domain)}${isEmpty ? " · empty" : ""}</span>
        ${
          isEmpty
            ? `<button class="btn-text" type="button" data-pill-recapture-tab-id="${escapeHtml(item.tab.id)}" title="Recapture page">Retry</button>`
            : ""
        }
        <button
          class="composer-pill-close"
          type="button"
          data-pill-close-tab-id="${escapeHtml(item.tab.id)}"
          title="Close tab and remove from context"
        >${icon("x", "ico-sm")}</button>
      </div>
    `;
  };

  const contextPillsHtml =
    activeTabSources.length === 0
      ? ""
      : `
        <div class="composer-ctx">
          ${visibleContextSources.map(renderContextPillHtml).join("")}
          ${
            collapsedExtraCount > 0
              ? `<button id="chat-context-expand-btn" class="pill" type="button">+${collapsedExtraCount} more</button>`
              : activeTabSources.length > 2
                ? `<button id="chat-context-expand-btn" class="pill" type="button">Show fewer</button>`
                : ""
          }
          <button id="chat-context-add-tab-btn" class="pill" type="button" title="Open a new tab to add context">${icon("plus", "ico-sm")}<span>Tab</span></button>
          ${
            activeTabSources.length >= 2
              ? `<button id="chat-compare-these-btn" class="pill" type="button" title="Run Comparer agent across open tabs">${icon("compare", "ico-sm")}<span>Compare</span></button>`
              : ""
          }
        </div>
        ${emptyContextBannerHtml}
      `;

  const stepsHtml = (convStream?.steps ?? [])
    .map(
      (step, idx) =>
        `<div class="stream-step">${idx === (convStream?.steps.length ?? 0) - 1 ? "Now" : "Done"} · ${escapeHtml(step)}</div>`
    )
    .join("");

  const isMailConv = detail.conversation.origin === "mail";
  const isNewsConv = detail.conversation.origin === "news";
  const mailEffectiveOn = isMailConv || state.mailContextEnabled;
  const triageSourceIds = state.mailTriageSources.map((s) => s.id);
  const mailSuggestionsHtml =
    isMailConv && !isStreamingHere
      ? `
        <div class="sugg">
          <button class="pill" type="button" data-chat-suggest="what do I need to deal with today?">What needs attention today?</button>
          <button class="pill" type="button" data-chat-suggest="summarize unread">Summarize unread</button>
          <button class="pill" type="button" data-chat-suggest="draft a reply to [1]">Draft reply to [1]</button>
        </div>
      `
      : isNewsConv && !isStreamingHere
        ? `
        <div class="sugg">
          <button class="pill" type="button" data-chat-suggest="What are today's top corroborated European news stories?">Top European stories</button>
          <button class="pill" type="button" data-chat-suggest="Compare perspectives on current global energy &amp; grid policy news">Compare perspectives</button>
          <button class="pill" type="button" data-news-jump-lane="stories">Top stories lane</button>
          <button class="pill" type="button" data-news-jump-lane="foryou">For you</button>
        </div>
      `
        : "";

  const convTasks = state.conversationTasks[detail.conversation.id] ?? [];
  const taskCardsHtml = convTasks
    .map((task) => renderTaskCardBlock(task))
    .join("");
  const watchNoticeHtml = state.watchStatusNotice
    ? `<div class="banner">${escapeHtml(state.watchStatusNotice)}</div>`
    : "";

  container.innerHTML = `
    <div class="chat-stage">
      <div class="thread-scroll" id="chat-messages-list">
        <div class="thread">
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
            messages.length === 0 && convTasks.length === 0 && !isStreamingHere && !(isMailConv && state.mailTriageOverview)
              ? `<div class="chat-empty">No messages in this conversation yet.</div>`
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
                      m.email_cards ?? state.messageEmailCards[m.id],
                      m.answer_meta ?? state.messageAnswerMeta[m.id]
                    )
                  )
                  .join("")
          }
          ${taskCardsHtml}
          ${
            isStreamingHere && convStream
              ? `
            <div class="msg-bot" id="streaming-msg-block" data-streaming-conv-id="${escapeHtml(convId)}">
              <div class="msg-meta">
                <span>Assistant</span>
                <span>· ${escapeHtml(convStream.model)}</span>
                <span>· <span id="streaming-phase-badge">${escapeHtml(phaseLabel)}</span></span>
                <span>· <span id="streaming-elapsed-timer">${elapsedSec}s</span></span>
              </div>
              <div class="stream" id="streaming-status-box">
                <div class="stream-now">
                  <span class="dot live"></span>
                  <span id="streaming-status-current" class="truncate">${escapeHtml(statusLineText)}</span>
                </div>
                <div id="streaming-steps-list">${stepsHtml}</div>
              </div>
              <div class="msg-text" id="streaming-msg-text">${escapeHtml(convStream.text)}</div>
            </div>
          `
              : ""
          }
        </div>
      </div>

      <div class="composer">
        ${mailSuggestionsHtml}
        <div class="cbox">
          ${contextPillsHtml}
          <textarea
            id="chat-composer-input"
            class="cbox-input"
            rows="1"
            spellcheck="false"
            autocorrect="off"
            autocapitalize="off"
            placeholder="${escapeHtml(offlineNotice)}"
            ${isStreamingHere ? "disabled" : ""}
          ></textarea>
          <div class="cbox-foot">
            <div class="chips">
              <div class="model-chip-anchor">
                ${(() => {
                  const models = getAvailableModelsForPicker();
                  const cur = models.find((m) => m.id === state.selectedModel);
                  const curLabel = cur?.label || state.selectedModel;
                  const privacyNote = getModelPrivacySummary(state.selectedModel);
                  return `
                    <button
                      id="chat-model-chip"
                      class="chip"
                      type="button"
                      title="${escapeHtml(privacyNote)}"
                      aria-expanded="${state.composerModelMenuOpen ? "true" : "false"}"
                    >
                      ${icon("spark", "ico-sm")}
                      <span class="truncate">${escapeHtml(curLabel)}</span>
                      ${icon("chev", "ico-sm")}
                    </button>
                    ${
                      state.composerModelMenuOpen
                        ? `
                          <div class="menu" id="chat-model-menu" role="menu">
                            <div class="model-menu-note">${escapeHtml(privacyNote)}</div>
                            ${models
                              .map(
                                (m) => `
                              <button
                                type="button"
                                class="menu-item ${state.selectedModel === m.id ? "active" : ""}"
                                data-select-model="${escapeHtml(m.id)}"
                              >
                                <span class="truncate">${escapeHtml(m.label)}</span>
                                ${state.selectedModel === m.id ? icon("check", "ico-sm") : ""}
                              </button>
                            `
                              )
                              .join("")}
                          </div>
                        `
                        : ""
                    }
                  `;
                })()}
              </div>
              <button
                id="chat-web-toggle"
                type="button"
                class="chip ${state.webSearchEnabled ? "on" : ""}"
                title="Enable live web_search and fetch_webpage tools"
              >
                ${icon("globe", "ico-sm")}
                <span>Web</span>
              </button>
              <button
                id="chat-mail-toggle"
                type="button"
                class="chip ${mailEffectiveOn ? "on" : ""}"
                title="Include Mail matches in context"
              >
                ${icon("mail", "ico-sm")}
                <span>Mail</span>
              </button>
              ${
                activeTabSources.length === 0
                  ? `<button id="chat-context-add-tab-btn" type="button" class="chip" title="Open a new tab to add to context">${icon("plus", "ico-sm")}<span>Tab</span></button>`
                  : ""
              }
            </div>
            <button
              id="chat-send-btn"
              type="button"
              class="send ${isStreamingHere ? "stop" : ""}"
              ${isStreamingHere ? "disabled" : ""}
              title="${isStreamingHere ? "Generation in progress" : "Send message (Enter)"}"
            >
              ${isStreamingHere ? `<span class="stop-sq"></span>` : icon("send", "ico-sm")}
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
    ) as HTMLTextAreaElement | HTMLInputElement | null;
    if (nextInput) {
      nextInput.value = preservedValue;
      if (wasFocused) {
        nextInput.focus();
        nextInput.setSelectionRange(preservedSelection, preservedSelection);
      }
    }
  }
}

export function appendStreamingDelta(convId: string, delta: string): void {
  const s = state.streamsByConv[convId];
  if (!s) return;
  s.text += delta;
  const blockEl = document.getElementById("streaming-msg-block");
  if (blockEl?.getAttribute("data-streaming-conv-id") !== convId) return;
  const el = document.getElementById("streaming-msg-text");
  if (el) {
    el.textContent = s.text;
    const list = document.getElementById("chat-messages-list");
    if (list) {
      list.scrollTop = list.scrollHeight;
    }
  }
}

export function updateStreamingStatus(
  convId: string,
  status: string,
  phase?: string
): void {
  const s = state.streamsByConv[convId];
  if (!s) return;
  s.status = status;
  if (phase) {
    s.phase = phase;
  }
  if (status && s.steps[s.steps.length - 1] !== status) {
    s.steps = [...s.steps.slice(-4), status];
  }

  const blockEl = document.getElementById("streaming-msg-block");
  if (blockEl?.getAttribute("data-streaming-conv-id") !== convId) return;

  const phaseEl = document.getElementById("streaming-phase-badge");
  if (phaseEl && s.phase) {
    phaseEl.textContent = s.phase;
  }
  const curEl = document.getElementById("streaming-status-current");
  if (curEl) {
    curEl.textContent = status;
  }
  const stepsEl = document.getElementById("streaming-steps-list");
  if (stepsEl) {
    stepsEl.innerHTML = s.steps
      .map(
        (step, idx) =>
          `<div class="stream-step">${idx === s.steps.length - 1 ? "Now" : "Done"} · ${escapeHtml(step)}</div>`
      )
      .join("");
  }
  const inputEl = document.getElementById(
    "chat-composer-input"
  ) as HTMLInputElement | null;
  if (inputEl && state.activeDetail?.conversation.id === convId) {
    inputEl.placeholder = `In progress: ${status}`;
  }
  const list = document.getElementById("chat-messages-list");
  if (list) {
    list.scrollTop = list.scrollHeight;
  }
}

export function tickStreamingElapsed(): void {
  const blockEl = document.getElementById("streaming-msg-block");
  const domConvId = blockEl?.getAttribute("data-streaming-conv-id") ?? "";
  const s = domConvId ? state.streamsByConv[domConvId] : null;
  if (!s || s.startedAt <= 0) return;
  const elapsedSec = ((Date.now() - s.startedAt) / 1000).toFixed(1);
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
  emailCards?: ChatEmailCard[],
  answerMeta?: AnswerMeta
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

  if (role === "user") {
    return `<div class="msg-you">${formattedBody}</div>`;
  }

  const modelLabel = model ? escapeHtml(model) : "";
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
    readFooterHtml = `<div class="msg-sources">Read ${sourceIds.length} source${sourceIds.length === 1 ? "" : "s"} · ${totalSent.toLocaleString()} chars · ${cutCount} cut</div>`;
  }

  const lastPromptHere =
    state.lastPromptByConv[state.activeDetail?.conversation.id ?? ""] ?? "";
  const retryButtonHtml =
    isErrorMsg
      ? `
      <div class="chat-audit-row">
        ${
          lastPromptHere
            ? `<button type="button" class="btn primary" data-retry-prompt="${escapeHtml(lastPromptHere)}">Retry</button>
               <button type="button" class="btn" data-use-planck-prompt="${escapeHtml(lastPromptHere)}">Use Planck instead</button>`
            : ""
        }
        ${
          plainErr && plainErr.rawDetail && plainErr.rawDetail !== plainErr.summary
            ? `<button type="button" class="btn" data-toggle-debug-msg="${escapeHtml(msgId)}">Debug</button>`
            : ""
        }
      </div>
      ${
        debugExpanded && plainErr
          ? `<div class="card inset muted">${escapeHtml(plainErr.rawDetail)}</div>`
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
      <div class="chat-section-block">
        <div class="label">Videos <span class="ct">${ytVideos.length}</span></div>
        <div class="video-grid">
          ${ytVideos
            .slice(0, 4)
            .map(
              (v) => `
            <div class="card chat-video-card">
              <iframe
                src="https://www.youtube-nocookie.com/embed/${escapeHtml(v.videoId)}"
                title="${escapeHtml(v.title)}"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowfullscreen
                loading="lazy"
              ></iframe>
              <div class="card-h">
                <span class="truncate" title="${escapeHtml(v.title)}">${escapeHtml(v.title)}</span>
                <button type="button" class="btn-text end" data-open-tab-url="${escapeHtml(v.url)}" data-open-tab-title="${escapeHtml(v.title)}">Open tab</button>
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
      <div class="chat-section-block">
        <div class="label">Page previews <span class="ct">${effectiveCitedSources.length}</span></div>
        <div class="preview-grid">
          ${effectiveCitedSources
            .slice(0, 6)
            .map((cs, idx) => {
              const dom = extractDomain(cs.url);
              return `
              <div class="card link" data-open-tab-url="${escapeHtml(cs.url)}" data-open-tab-title="${escapeHtml(cs.title)}">
                <div class="card-h">
                  <b>${idx + 1} · ${escapeHtml(dom)}</b>
                  <button type="button" class="btn-text end" data-open-tab-url="${escapeHtml(cs.url)}" data-open-tab-title="${escapeHtml(cs.title)}">Open tab</button>
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
      <div class="chat-section-block">
        ${proposals
          .map((p) => {
            const summaryPart = p.summary ? `, ${escapeHtml(p.summary.slice(0, 80))}` : "";
            const status = p.status ?? "pending";
            if (status === "accepted") {
              return `<div class="banner"><span>Stored ${escapeHtml(p.type)}: <b>${escapeHtml(p.name)}</b>${summaryPart}</span><span class="badge">Accepted</span></div>`;
            }
            if (status === "rejected") {
              return `<div class="banner"><span class="muted">Skipped ${escapeHtml(p.type)}: ${escapeHtml(p.name)}${summaryPart}</span><span class="badge soft">Rejected</span></div>`;
            }
            return `
              <div class="card inset">
                <div class="card-h">
                  <span class="badge soft">Store</span>
                  <b>${escapeHtml(p.type)}: ${escapeHtml(p.name)}</b>
                  <span class="end">
                    <button type="button" class="btn primary" data-accept-proposal="${escapeHtml(p.proposal_id)}" data-proposal-msg="${escapeHtml(msgId)}">Accept</button>
                    <button type="button" class="btn" data-reject-proposal="${escapeHtml(p.proposal_id)}" data-proposal-msg="${escapeHtml(msgId)}">Reject</button>
                  </span>
                </div>
                ${summaryPart ? `<div class="muted">${escapeHtml(p.summary)}</div>` : ""}
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
      <div class="chat-section-block">
        <div class="label">Findings <span class="ct">${nonVideoFindings.length}</span></div>
        <div class="findings">
          ${nonVideoFindings
            .map(
              (f) => `
            <div
              class="finding"
              data-open-tab-url="${escapeHtml(f.page_url || f.image_url)}"
              data-open-tab-title="${escapeHtml(f.title)}"
              title="${escapeHtml(f.title)}${f.price ? ` · ${escapeHtml(f.price)}` : ""}"
            >
              <img
                src="${escapeHtml(f.image_url)}"
                alt="${escapeHtml(f.title)}"
                loading="lazy"
              />
              <div>
                <div class="truncate">${escapeHtml(f.title)}</div>
                ${f.price ? `<div class="price">${escapeHtml(f.price)}</div>` : ""}
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
      <div class="msg-cite-row">
        <span>Brain memory:</span>
        ${citedBrainItems
          .map(
            (bs) => `
          <button
            type="button"
            class="cite"
            data-brain-cite="${escapeHtml(bs.cite_label)}"
            data-brain-slug="${escapeHtml(bs.slug)}"
            title="Open Brain card: ${escapeHtml(bs.name)}"
          >${escapeHtml(bs.cite_label)} · ${escapeHtml(bs.name)}</button>
        `
          )
          .join("")}
      </div>
    `
      : "";

  const watchBtnHtml =
    role === "assistant" && !isErrorMsg && msgId !== "mail-triage-overview"
      ? `<button type="button" class="btn-text" data-watch-msg="${escapeHtml(msgId)}" title="Watch this answer or source for changes">${icon("watch", "ico-sm")}<span>Watch</span></button>`
      : "";

  const answerAuditHtml = renderAnswerMetaSectionHtml(msgId, answerMeta);

  if (isErrorMsg) {
    return `
      <div class="msg-bot msg-error">
        <div class="msg-meta">
          <span>Assistant</span>
          ${modelLabel ? `<span>· ${modelLabel}</span>` : ""}
        </div>
        <div class="banner danger">
          <span>${formattedBody}</span>
        </div>
        ${retryButtonHtml}
      </div>
    `;
  }

  return `
    <div class="msg-bot">
      <div class="msg-meta">
        <span>Assistant</span>
        ${modelLabel ? `<span>· ${modelLabel}</span>` : ""}
        ${srcCountLabel ? `<span>${escapeHtml(srcCountLabel)}</span>` : ""}
        ${citeStatsLabel ? `<span>${escapeHtml(citeStatsLabel)}</span>` : ""}
        ${watchBtnHtml ? `<span class="msg-meta-acts">${watchBtnHtml}</span>` : ""}
      </div>
      <div class="msg-text">${formattedBody}</div>
      ${answerAuditHtml}
      ${readFooterHtml}
      ${brainCitationsListHtml}
      ${embeddedVideosHtml}
      ${emailCardsHtml}
      ${findingsHtml}
      ${pagePreviewCardsHtml}
      ${proposalsHtml}
    </div>
  `;
}

function renderAnswerMetaSectionHtml(
  msgId: string,
  meta?: AnswerMeta
): string {
  if (!meta) return "";
  const conf10 = meta.confidence10 ?? 0;
  const pct = Math.max(0, Math.min(100, Math.round(conf10 * 10)));
  const isLowBand =
    meta.band === "low" || meta.band === "sceptical" || (meta.conflicts?.length ?? 0) > 0;
  const rolesLine = meta.models_used
    ? `Plan: ${meta.models_used.planner} · Read: ${meta.models_used.reader} · Analyze: ${meta.models_used.analyzer}`
    : "";

  const divHtml = meta.divergence
    ? `<div class="banner warn">Personal trust shifted result · system-only: ${escapeHtml(String(meta.divergence.system_value ?? "n/a"))} (${meta.divergence.system_confidence.toFixed(1)}/10 ${escapeHtml(meta.divergence.system_band)})</div>`
    : "";

  const defaultOpenExplain =
    meta.band === "low" || meta.band === "sceptical" || (meta.conflicts?.length ?? 0) > 0;
  const explainOpen = state.expandedExplainMessages[msgId] ?? defaultOpenExplain;
  const inDepthOpen = Boolean(state.expandedInDepthMessages[msgId]);

  const explainBodyHtml = explainOpen
    ? `
      <div class="card inset">
        <div class="muted">Steps: ${meta.steps.map((s) => escapeHtml(s)).join(" → ")}</div>
        ${
          meta.items && meta.items.length > 0
            ? `<div class="table-wrap"><table class="table"><thead><tr><th class="num">Delta</th><th>Reason</th></tr></thead><tbody>${meta.items
                .map(
                  ([lbl, val]) =>
                    `<tr><td class="num">${val >= 0 ? `+${val.toFixed(1)}` : val.toFixed(1)}</td><td>${escapeHtml(lbl)}</td></tr>`
                )
                .join("")}</tbody></table></div>`
            : ""
        }
        ${
          meta.sources && meta.sources.length > 0
            ? `<div class="table-wrap"><table class="table"><thead><tr><th>Role</th><th>Domain</th><th>Family</th><th class="num">Sys</th><th class="num">You</th><th class="num">Eff</th><th>Category</th><th>Trust</th></tr></thead><tbody>${meta.sources
                .map((s) => {
                  const t = s.trust;
                  const youStr = t.personal !== null && t.personal !== undefined ? t.personal.toFixed(1) : "—";
                  const confFlag = t.conflict ? ` <span class="badge soft">Conflict</span>` : "";
                  return `<tr><td>${escapeHtml(s.role)}</td><td><button type="button" class="btn-text" data-open-tab-url="${escapeHtml(s.url)}" data-open-tab-title="${escapeHtml(s.title)}">${escapeHtml(s.domain)}</button>${confFlag}</td><td>${escapeHtml(t.family)}</td><td class="num">${t.system.toFixed(0)}</td><td class="num">${escapeHtml(youStr)}</td><td class="num"><b>${t.effective.toFixed(1)}</b></td><td>${escapeHtml(t.category)}</td><td><button type="button" class="btn-text" data-news-trust-msg="${escapeHtml(msgId)}" data-news-trust-dom="${escapeHtml(s.domain)}" data-news-trust-delta="2">+</button> <button type="button" class="btn-text" data-news-trust-msg="${escapeHtml(msgId)}" data-news-trust-dom="${escapeHtml(s.domain)}" data-news-trust-delta="-2">-</button></td></tr>`;
                })
                .join("")}</tbody></table></div>`
            : ""
        }
      </div>
    `
    : "";

  const inDepthBodyHtml =
    inDepthOpen && meta.passages && meta.passages.length > 0
      ? `
      <div class="card inset">
        ${meta.passages
          .map(
            (p) => `
          <div class="source-row">
            <div class="source-row-top">
              <b class="t">${escapeHtml(p.domain)}</b>
              <button type="button" class="btn-text" data-open-tab-url="${escapeHtml(p.url)}" data-open-tab-title="${escapeHtml(p.title || p.domain)}">Open tab</button>
            </div>
            <div class="muted">${escapeHtml(p.text)}</div>
          </div>`
          )
          .join("")}
      </div>
    `
      : "";

  return `
    <div class="chat-audit">
      <div class="chat-audit-row">
        <span class="conf ${isLowBand ? "low" : ""}" style="--c:${pct}%"><i></i>${conf10.toFixed(1)}/10 · ${escapeHtml(meta.band_label)}</span>
        ${rolesLine ? `<span>${escapeHtml(rolesLine)}</span>` : ""}
      </div>
      ${divHtml}
      ${meta.privacy_disclosure ? `<div class="muted">${escapeHtml(meta.privacy_disclosure)}</div>` : ""}
      <div class="chat-audit-row">
        <button type="button" class="btn-text" data-toggle-explain-msg="${escapeHtml(msgId)}">${explainOpen ? "Hide how I got this" : "Show how I got this"}</button>
        ${
          meta.passages && meta.passages.length > 0
            ? `<button type="button" class="btn-text" data-toggle-indepth-msg="${escapeHtml(msgId)}">${inDepthOpen ? "Hide" : "Show"} in depth · ${meta.passages.length} passages</button>`
            : ""
        }
      </div>
      ${explainBodyHtml}
      ${inDepthBodyHtml}
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
    <div class="chat-section-block">
      <div class="label">Referenced emails <span class="ct">${cards.length}</span></div>
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
            <div class="chat-audit-row">
              <span class="muted">Attachments (${atts.length}):</span>
              ${atts
                .map((att) => {
                  const attKey = `${ec.message_id}:${att.part_id}`;
                  const previewObj = state.previewedAttachments[attKey];
                  const sizeKb = Math.max(1, Math.round((att.size || 0) / 1024));
                  return `
                    <span class="pill">
                      <span>${escapeHtml(att.filename)} (${sizeKb} KB)</span>
                      <button
                        type="button"
                        class="btn-text"
                        data-chat-preview-att="${escapeHtml(ec.message_id)}"
                        data-part-id="${escapeHtml(String(att.part_id))}"
                      >${previewObj ? "Hide" : "Preview"}</button>
                      <button
                        type="button"
                        class="btn-text"
                        data-chat-download-att="${escapeHtml(ec.message_id)}"
                        data-part-id="${escapeHtml(String(att.part_id))}"
                      >Download</button>
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
                  return `<img class="attach-img" src="${escapeHtml(prev.data_url)}" alt="${escapeHtml(prev.filename)}" />`;
                }
                return `<embed class="attach-embed" type="${escapeHtml(prev.mime)}" src="${escapeHtml(prev.data_url)}" />`;
              })
              .join("")}
          `
              : "";

          return `
            <div class="card inset">
              <div class="card-h">
                <b>${escapeHtml(ec.subject)}</b>
                <span class="badge soft">${escapeHtml(ec.label)}</span>
                <span class="end">
                  <button
                    type="button"
                    class="btn-text"
                    data-chat-toggle-email="${escapeHtml(expandKey)}"
                    data-email-mid="${escapeHtml(ec.message_id)}"
                  >${isExpanded ? "Hide body" : "Show body"}</button>
                  <button
                    type="button"
                    class="btn-text"
                    data-chat-open-email-tab="${escapeHtml(ec.message_id)}"
                    data-email-subj="${escapeHtml(ec.subject)}"
                  >Open tab</button>
                </span>
              </div>
              <div class="muted">From: ${escapeHtml(fromDisp)}</div>
              ${
                isExpanded
                  ? `<div class="chat-inline-email"><pre>${escapeHtml(ec.body_text || ec.snippet || "(empty body)")}${ec.quoted_text ? `\n\n--- Quoted Thread ---\n${escapeHtml(ec.quoted_text)}` : ""}</pre></div>`
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
    ? `<button type="button" class="btn" data-task-stop="${escapeHtml(task.id)}" data-stop-token="${escapeHtml(task.stop_token)}">Stop</button>`
    : "";

  const stepsHtml = (task.steps ?? [])
    .map((step) => {
      if (step.kind === "send_gate") {
        const summary = step.action_summary || step.text;
        if (step.status === "waiting_confirm") {
          return `
            <div class="draft">
              <div class="gate">Send gate · confirmation required</div>
              <div>${escapeHtml(summary)}</div>
              <div class="acts">
                <button
                  type="button"
                  class="btn primary"
                  data-task-confirm="${escapeHtml(task.id)}"
                  data-step-id="${escapeHtml(step.id)}"
                  data-confirm-token="${escapeHtml(step.confirm_token ?? "")}"
                >Confirm</button>
                <button
                  type="button"
                  class="btn"
                  data-task-cancel="${escapeHtml(task.id)}"
                  data-step-id="${escapeHtml(step.id)}"
                >Cancel</button>
              </div>
            </div>
          `;
        }
        return `<div class="stream-step">Send gate (${escapeHtml(step.status)}): ${escapeHtml(summary)}</div>`;
      }
      const prefix = step.status === "running" ? "Now" : "Done";
      return `<div class="stream-step">${prefix} · ${escapeHtml(step.text)}</div>`;
    })
    .join("");

  const activeSourceIds = (state.activeDetail?.sources ?? []).map((s) => s.id);
  const resultHtml = task.result_md
    ? `<div class="msg-text">${formatCitationsInText(task.result_md, activeSourceIds)}</div>`
    : "";

  return `
    <div class="card" data-task-card="${escapeHtml(task.id)}">
      <div class="card-h">
        <b>Task · ${escapeHtml(task.agent)}</b>
        <span class="badge soft">${escapeHtml(task.status)}</span>
        <span class="end muted truncate">${escapeHtml(task.goal)}</span>
        ${stopBtnHtml}
      </div>
      <div class="stream">${stepsHtml}</div>
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
      out.push(`<div class="table-wrap"><table class="table">${thead}${tbody}</table></div>`);
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
    `<span class="cite flagged" title="Citation index outside source list">unsourced</span>`
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
      return `<span class="cite flagged" title="Citation ${idx} outside ${sourceIds.length} source(s)">unsourced</span>`;
    }
    const sourceId = sourceIds[idx - 1] ?? "";
    const flaggedEntries = (citationCheck ?? []).filter(
      (c) => c.n === idx && !c.ok
    );
    if (flaggedEntries.length > 0) {
      const missingItems = Array.from(
        new Set(flaggedEntries.flatMap((e) => e.missing ?? []))
      );
      const tooltip = `Not found in source ${idx}: ${missingItems.join(", ")}`;
      return `<button type="button" class="cite flagged" data-citation-idx="${idx}" data-citation-src="${escapeHtml(sourceId)}" title="${escapeHtml(tooltip)}">${idx}?</button>`;
    }
    return `<button type="button" class="cite" data-citation-idx="${idx}" data-citation-src="${escapeHtml(sourceId)}">${idx}</button>`;
  });

  const withBrainCites = withSrcCites.replace(/\[B(\d+)\]/g, (_match, digits) => {
    const bIdx = Number(digits);
    const bKey = `B${bIdx}`;
    const outOfRangeCheck = citationCheck?.find(
      (c) => String(c.n) === bKey && c.out_of_range
    );
    const maxB = brainSources?.length ?? 0;
    if (bIdx < 1 || (maxB > 0 && bIdx > maxB) || outOfRangeCheck) {
      return `<span class="cite flagged" title="Brain citation ${bKey} outside ${maxB} brain item(s)">unsourced</span>`;
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
      const tooltip = `Not found in brain ${bKey} (${labelName}): ${missingItems.join(", ")}`;
      return `<button type="button" class="cite flagged" data-brain-cite="${escapeHtml(bKey)}" data-brain-slug="${escapeHtml(slug)}" title="${escapeHtml(tooltip)}">${escapeHtml(bKey)}?</button>`;
    }
    return `<button type="button" class="cite" data-brain-cite="${escapeHtml(bKey)}" data-brain-slug="${escapeHtml(slug)}" title="Open Brain card: ${escapeHtml(labelName)}">${escapeHtml(bKey)}</button>`;
  });
  const withMdLinksAndBold = withBrainCites
    .replace(
      /\[([^\][]+)\]\((https?:\/\/[^\s)]+)\)/g,
      (_m, labelTxt, urlTxt) =>
        `<button type="button" class="btn-text inline-page-link" data-open-tab-url="${urlTxt}" data-open-tab-title="${labelTxt}" title="Open ${urlTxt} in tab">${labelTxt} ↗</button>`
    )
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  return renderMarkdownTablesInHtml(withMdLinksAndBold);
}

function bindChatEvents(container: HTMLElement, actions: ChatActions): void {
  const input = container.querySelector(
    "#chat-composer-input"
  ) as HTMLTextAreaElement | HTMLInputElement | null;
  const submit = () => {
    const val = input?.value.trim() ?? "";
    if (!val || isConvStreaming(state.activeDetail?.conversation.id)) return;
    if (input) input.value = "";
    state.composerModelMenuOpen = false;
    actions.onSendMessage(val);
  };

  input?.addEventListener("keydown", (e) => {
    const ke = e as KeyboardEvent;
    if (ke.key === "Enter" && !ke.shiftKey) {
      ke.preventDefault();
      submit();
    }
  });

  if (input && input.tagName.toLowerCase() === "textarea") {
    const resizeTa = () => {
      input.style.height = "auto";
      input.style.height = `${Math.min(140, input.scrollHeight)}px`;
    };
    resizeTa();
    input.addEventListener("input", resizeTa);
  }

  container.querySelector("#chat-send-btn")?.addEventListener("click", submit);

  container
    .querySelector("#chat-context-expand-btn")
    ?.addEventListener("click", () => {
      state.composerContextExpanded = !state.composerContextExpanded;
      renderChatPanel(container, actions);
    });

  container
    .querySelector("#chat-model-chip")
    ?.addEventListener("click", (e) => {
      e.stopPropagation();
      state.composerModelMenuOpen = !state.composerModelMenuOpen;
      renderChatPanel(container, actions);
    });

  container.querySelectorAll("[data-select-model]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mId = (btn as HTMLElement).getAttribute("data-select-model");
      state.composerModelMenuOpen = false;
      if (mId) {
        actions.onChangeModel(mId as LocalModelId);
      }
    });
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
      if (isConvStreaming(state.activeDetail?.conversation.id)) return;
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
      if (isConvStreaming(state.activeDetail?.conversation.id)) return;
      const prompt = (btn as HTMLElement).getAttribute("data-retry-prompt");
      if (prompt) actions.onSendMessage(prompt);
    });
  });

  container.querySelectorAll("[data-use-planck-prompt]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (isConvStreaming(state.activeDetail?.conversation.id)) return;
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

  container.querySelectorAll("[data-toggle-explain-msg]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mid = (btn as HTMLElement).getAttribute("data-toggle-explain-msg") ?? "";
      if (!mid) return;
      state.expandedExplainMessages[mid] = !state.expandedExplainMessages[mid];
      renderChatPanel(container, actions);
    });
  });

  container.querySelectorAll("[data-toggle-indepth-msg]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mid = (btn as HTMLElement).getAttribute("data-toggle-indepth-msg") ?? "";
      if (!mid) return;
      state.expandedInDepthMessages[mid] = !state.expandedInDepthMessages[mid];
      renderChatPanel(container, actions);
    });
  });

  container.querySelectorAll("[data-news-trust-dom]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const mid = el.getAttribute("data-news-trust-msg") ?? "";
      const dom = el.getAttribute("data-news-trust-dom") ?? "";
      const delta = Number(el.getAttribute("data-news-trust-delta") ?? "0");
      if (mid && dom && actions.onNewsTrustDelta) {
        actions.onNewsTrustDelta(mid, dom, delta);
      }
    });
  });

  container.querySelectorAll("[data-news-jump-lane]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const lane = (btn as HTMLElement).getAttribute("data-news-jump-lane") ?? "";
      if (lane && actions.onOpenNewsLane) {
        actions.onOpenNewsLane(lane);
      }
    });
  });
}
