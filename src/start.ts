import {
  escapeHtml,
  formatRelativeTime,
  getAvailableModelsForPicker,
  MOD_LABEL,
  rankCommandBarRoutes,
  state,
} from "./state";
import type { CommandBarRoute, DigestEntry, LocalModelId } from "./types";

export interface StartScreenActions {
  onSubmitStartInput: (raw: string) => void;
  onExecuteCommandRoute?: (route: CommandBarRoute, raw: string) => void;
  onSelectConversation: (id: string) => void;
  onOpenDigestUrl: (url: string, title: string, convId?: string) => void;
  onChangeModel: (model: LocalModelId) => void;
  onToggleWeb: () => void;
  onCloseCommandBar?: () => void;
  onGoHome?: () => void;
  onRefreshDigest?: () => void;
  onUnlockProfile?: (profileId: string, pin: string) => void;
  onCreateProfile?: (name: string, pin: string) => void;
}

function digestKindTag(kind?: string): string {
  switch (kind) {
    case "watch_triggered":
      return "[watch]";
    case "bookmark_changed":
      return "[changed]";
    case "mail_reply":
      return "[reply]";
    case "mail_recent":
      return "[mail]";
    case "mail_ping":
      return "[ping]";
    case "mail_order":
      return "[order]";
    case "mail_promo":
      return "[promo]";
    case "news_story":
      return "[news]";
    case "brain_entity":
      return "[brain]";
    case "digest_adjacent":
      return "[related]";
    case "source_capture":
      return "[captured]";
    default:
      return "[web]";
  }
}

function formatDigestTime(ts?: number): string {
  if (!ts || !Number.isFinite(ts) || ts <= 0) return "";
  return formatRelativeTime(String(Math.floor(ts)));
}

function renderDigestItemsHtml(
  items: DigestEntry[],
  mode: "start" | "overlay"
): string {
  if (items.length === 0) {
    return `<div class="muted">unlock profile, receive mail, browse pages, or refresh news to populate your feed</div>`;
  }
  const visible = mode === "overlay" ? items.slice(0, 6) : items;
  return visible
    .map((item) => {
      const tag = digestKindTag(item.kind);
      const relTime = formatDigestTime(item.ts);
      const leadImg = (item.image_url || "").trim();
      const extraImgs =
        mode === "start" && Array.isArray(item.images)
          ? item.images.filter((u) => u && u !== leadImg).slice(0, 2)
          : [];
      const snippetText = (item.summary || "").trim();
      const reasonText = (item.reason || "").trim();
      return `
        <div
          class="start-digest-card ${mode === "overlay" ? "compact" : ""}"
          data-digest-url="${escapeHtml(item.url)}"
          data-digest-title="${escapeHtml(item.title)}"
          ${item.conversation_id ? `data-digest-conv-id="${escapeHtml(item.conversation_id)}"` : ""}
        >
          <div class="start-digest-card-top">
            <span class="start-digest-title-wrap">
              <span class="start-digest-kind">${escapeHtml(tag)}</span>
              <strong>${escapeHtml(item.title)}</strong>
            </span>
            <span class="muted start-digest-right-meta">
              ${escapeHtml(item.domain)}${relTime ? ` · ${escapeHtml(relTime)}` : ""}
            </span>
          </div>
          ${
            leadImg || snippetText || reasonText
              ? `
                <div class="start-digest-media">
                  ${
                    leadImg
                      ? `<img class="start-digest-thumb ${mode === "overlay" ? "compact" : ""}" src="${escapeHtml(leadImg)}" alt="" loading="lazy" referrerpolicy="no-referrer" />`
                      : ""
                  }
                  <div class="start-digest-body">
                    ${
                      snippetText
                        ? `<div class="start-digest-snippet">${escapeHtml(snippetText)}</div>`
                        : ""
                    }
                    ${
                      reasonText
                        ? `<div class="start-digest-meta muted">${escapeHtml(reasonText)}</div>`
                        : ""
                    }
                    ${
                      extraImgs.length > 0
                        ? `<div class="start-digest-extra-thumbs">${extraImgs
                            .map(
                              (iu) =>
                                `<img class="start-digest-extra-thumb" src="${escapeHtml(iu)}" alt="" loading="lazy" referrerpolicy="no-referrer" />`
                            )
                            .join("")}</div>`
                        : ""
                    }
                  </div>
                </div>
              `
              : ""
          }
        </div>
      `;
    })
    .join("");
}

function bindDigestItemEvents(
  root: HTMLElement,
  actions: StartScreenActions,
  closeCommandBarOnClick = false
): void {
  root.querySelectorAll("[data-digest-url]").forEach((el) => {
    el.addEventListener("click", () => {
      const node = el as HTMLElement;
      const url = node.getAttribute("data-digest-url");
      const title = node.getAttribute("data-digest-title") ?? url ?? "";
      const convId = node.getAttribute("data-digest-conv-id") ?? undefined;
      if (closeCommandBarOnClick) {
        actions.onCloseCommandBar?.();
      }
      if (url) actions.onOpenDigestUrl(url, title, convId);
    });
  });

  root
    .querySelectorAll("img.start-digest-thumb, img.start-digest-extra-thumb")
    .forEach((imgEl) => {
      imgEl.addEventListener("error", () => {
        imgEl.remove();
      });
    });
}

export function updateStartDigestInPlace(actions: StartScreenActions): boolean {
  const slot = document.getElementById("start-foryou-slot");
  if (!slot) return false;
  slot.innerHTML = renderDigestItemsHtml(state.digestItems, "start");
  const meta = document.getElementById("start-foryou-meta");
  if (meta) {
    const updatedLbl = state.digestUpdatedAt
      ? `updated ${formatRelativeTime(String(Math.floor(state.digestUpdatedAt / 1000)))}`
      : "";
    meta.textContent = `${state.digestItems.length} item${state.digestItems.length === 1 ? "" : "s"}${state.digestRefreshing ? " · updating..." : updatedLbl ? ` · ${updatedLbl}` : ""}`;
  }
  bindDigestItemEvents(slot, actions, false);
  return true;
}

export function updateOverlayDigestInPlace(actions: StartScreenActions): boolean {
  const slot = document.getElementById("overlay-foryou-slot");
  if (!slot) return false;
  slot.innerHTML = renderDigestItemsHtml(state.digestItems, "overlay");
  const countEl = document.getElementById("overlay-foryou-count");
  if (countEl) {
    countEl.textContent = `(${state.digestItems.length}${state.digestRefreshing ? " · updating..." : ""})`;
  }
  bindDigestItemEvents(slot, actions, true);
  return true;
}

function renderRoutesListHtml(
  routes: CommandBarRoute[],
  selectedIdx: number,
  prefixId: string
): string {
  return `
    <div id="${escapeHtml(prefixId)}-routes" class="kb-section" style="margin-top:8px; border-top:1px solid #333333; padding-top:6px;">
      ${routes
        .map((r, idx) => {
          const isSelected = idx === selectedIdx;
          const badge = idx === 0 ? "[default · enter]" : `[${idx + 1}]`;
          return `
            <div
              class="rail-row ${isSelected ? "active" : ""}"
              data-cmd-route-idx="${idx}"
              style="padding:4px 6px; cursor:pointer; justify-content:space-between; border:1px solid ${isSelected ? "#e8e8e8" : "transparent"};"
            >
              <span class="truncate">
                <span class="muted">${escapeHtml(badge)}</span>
                ${escapeHtml(r.label)}
              </span>
              <span class="muted" style="margin-left:8px; flex-shrink:0;">
                [${escapeHtml(r.privacy)}]
              </span>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

export function renderStartScreen(
  container: HTMLElement,
  actions: StartScreenActions
): void {
  const resumeConvs = state.conversations
    .filter((c) => c.status === "active")
    .slice(0, 6);

  const initialRoutes = rankCommandBarRoutes(state.commandBarInput);
  const clampedIdx = Math.max(
    0,
    Math.min(state.commandBarSelectedIdx, Math.max(0, initialRoutes.length - 1))
  );

  const profileInfo = state.knowledge.profile;
  const profilesList = profileInfo?.profiles ?? [];
  const isUnlocked = Boolean(
    profileInfo?.unlocked && profileInfo?.active_profile
  );

  const unlockPromptHtml = !isUnlocked
    ? `
      <div class="kb-card" id="start-profile-unlock-card" style="margin-bottom:14px;">
        <div class="kb-card-header">
          <span><strong>profile locked</strong> · unlock your profile to load your Brain, Mail accounts &amp; password vault</span>
          <span class="muted">[6-digit PIN]</span>
        </div>
        ${
          state.profileStatusMessage
            ? `<div class="profile-status-banner">${escapeHtml(state.profileStatusMessage)}</div>`
            : ""
        }
        ${
          profilesList.length > 0
            ? `
              <div class="vault-form-row">
                <label class="muted">profile:</label>
                <select id="start-unlock-profile-select" class="vault-input">
                  ${profilesList
                    .map(
                      (p) =>
                        `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)} (${escapeHtml(p.id)})</option>`
                    )
                    .join("")}
                </select>
                <input
                  id="start-unlock-pin-input"
                  class="vault-input vault-pin-input"
                  type="password"
                  inputmode="numeric"
                  maxlength="6"
                  spellcheck="false"
                  autocorrect="off"
                  autocapitalize="off"
                  placeholder="6-digit PIN_"
                />
                <button id="start-unlock-profile-btn" type="button">[unlock profile &amp; mail]</button>
              </div>
            `
            : ""
        }
        <div class="vault-form-row" style="margin-top:6px;">
          <span class="muted">${profilesList.length > 0 ? "or create a new profile:" : "create a new profile with a 6-digit PIN:"}</span>
          <input
            id="start-create-profile-name"
            class="vault-input"
            type="text"
            spellcheck="false"
            autocorrect="off"
            autocapitalize="off"
            placeholder="new profile name (e.g. Nikita)_"
          />
          <input
            id="start-create-profile-pin"
            class="vault-input vault-pin-input"
            type="password"
            inputmode="numeric"
            maxlength="6"
            spellcheck="false"
            autocorrect="off"
            autocapitalize="off"
            placeholder="6-digit PIN_"
          />
          <button id="start-create-profile-btn" type="button">[+ create &amp; unlock]</button>
        </div>
      </div>
    `
    : "";

  container.innerHTML = `
    <div class="start-screen">
      <div class="start-container">
        ${unlockPromptHtml}
        <div class="start-prompt-title">where do you want to start? <span class="muted">[${MOD_LABEL}+k]</span></div>

        <div class="start-input-box" id="start-command-bar-box">
          <div class="start-input-row">
            <span class="muted">&gt;</span>
            <input
              id="start-main-input"
              class="start-input-field"
              type="text"
              spellcheck="false"
              autocorrect="off"
              autocapitalize="off"
              placeholder="url, question, mail: term, brain: term, or command (home, new, bookmark, compare, lock)_"
              value="${escapeHtml(state.commandBarInput)}"
            />
            <span class="caret-blink">▌</span>
          </div>

          <div class="start-controls-row">
            <span class="muted">enter runs default route · up/down selects route</span>
            <div class="composer-controls">
              <label class="muted">model:</label>
              <select id="start-model-select">
                ${getAvailableModelsForPicker().map(
                  (m) => `
                  <option value="${escapeHtml(m.id)}" ${state.selectedModel === m.id ? "selected" : ""}>
                    ${escapeHtml(m.label)}
                  </option>
                `
                ).join("")}
              </select>
              <button id="start-web-toggle" class="${state.webSearchEnabled ? "active" : ""}">
                web: ${state.webSearchEnabled ? "on" : "off"}
              </button>
            </div>
          </div>

          <div id="start-routes-slot">
            ${renderRoutesListHtml(initialRoutes, clampedIdx, "start")}
          </div>
        </div>

        <div class="start-columns">
          <div class="start-col start-col-foryou">
            <div class="start-col-header">
              <span>for you</span>
              <span class="composer-controls">
                <span class="muted" id="start-foryou-meta">${state.digestItems.length} item${state.digestItems.length === 1 ? "" : "s"}${state.digestRefreshing ? " · updating..." : state.digestUpdatedAt ? ` · updated ${escapeHtml(formatRelativeTime(String(Math.floor(state.digestUpdatedAt / 1000))))}` : ""}</span>
                <button id="start-refresh-digest-btn" type="button">[refresh]</button>
              </span>
            </div>
            <div id="start-foryou-slot" class="start-foryou-list">
              ${renderDigestItemsHtml(state.digestItems, "start")}
            </div>
          </div>

          <div class="start-col start-col-resume">
            <div class="start-col-header">
              <span>resume</span>
              <span class="muted">${resumeConvs.length} conversation${resumeConvs.length === 1 ? "" : "s"}</span>
            </div>
            ${
              resumeConvs.length === 0
                ? `<div class="muted">no recent conversations</div>`
                : resumeConvs
                    .map(
                      (c) => `
                  <div class="start-list-item start-resume-item" data-resume-id="${escapeHtml(c.id)}">
                    <div class="start-resume-main truncate">
                      <span class="muted">[${escapeHtml(c.origin)}]</span>
                      <span>${escapeHtml(c.title)}</span>
                    </div>
                    <span class="muted start-digest-right-meta">${c.source_count ?? 0} src · ${escapeHtml(formatRelativeTime(c.last_active_at))}</span>
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

  bindUnifiedCommandBox(
    container,
    "#start-main-input",
    "#start-routes-slot",
    "start",
    actions,
    !isUnlocked && profilesList.length > 0 ? false : false
  );

  const startPinInput = container.querySelector(
    "#start-unlock-pin-input"
  ) as HTMLInputElement | null;
  if (!isUnlocked && startPinInput) {
    startPinInput.focus();
  }

  const triggerStartUnlock = () => {
    const sel = container.querySelector(
      "#start-unlock-profile-select"
    ) as HTMLSelectElement | null;
    const pid = sel?.value || profilesList[0]?.id || "";
    const pin = startPinInput?.value.trim() ?? "";
    if (pid && pin && actions.onUnlockProfile) {
      actions.onUnlockProfile(pid, pin);
    }
  };

  container
    .querySelector("#start-unlock-profile-btn")
    ?.addEventListener("click", triggerStartUnlock);
  startPinInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      triggerStartUnlock();
    }
  });

  const triggerStartCreate = () => {
    const nameEl = container.querySelector(
      "#start-create-profile-name"
    ) as HTMLInputElement | null;
    const pinEl = container.querySelector(
      "#start-create-profile-pin"
    ) as HTMLInputElement | null;
    const name = nameEl?.value.trim() ?? "";
    const pin = pinEl?.value.trim() ?? "";
    if (name && pin && actions.onCreateProfile) {
      actions.onCreateProfile(name, pin);
    }
  };

  container
    .querySelector("#start-create-profile-btn")
    ?.addEventListener("click", triggerStartCreate);
  container
    .querySelector("#start-create-profile-pin")
    ?.addEventListener("keydown", (e) => {
      if ((e as KeyboardEvent).key === "Enter") {
        e.preventDefault();
        triggerStartCreate();
      }
    });

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

  container
    .querySelector("#start-refresh-digest-btn")
    ?.addEventListener("click", () => {
      actions.onRefreshDigest?.();
    });

  container.querySelectorAll("[data-resume-id]").forEach((el) => {
    el.addEventListener("click", () => {
      const id = (el as HTMLElement).getAttribute("data-resume-id");
      if (id) actions.onSelectConversation(id);
    });
  });

  bindDigestItemEvents(container, actions, false);
}

export function renderCommandBarOverlay(actions: StartScreenActions): void {
  let overlay = document.getElementById("command-bar-overlay");
  if (!state.commandBarOpen) {
    if (overlay) {
      overlay.remove();
    }
    return;
  }

  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "command-bar-overlay";
    overlay.style.cssText =
      "position:fixed; inset:0; background:rgba(0,0,0,0.82); z-index:9000; display:flex; align-items:flex-start; justify-content:center; padding-top:48px;";
    document.body.appendChild(overlay);
  }

  const routes = rankCommandBarRoutes(state.commandBarInput);
  const clampedIdx = Math.max(
    0,
    Math.min(state.commandBarSelectedIdx, Math.max(0, routes.length - 1))
  );

  overlay.innerHTML = `
    <div id="command-bar-modal" class="start-input-box" style="width:720px; max-width:94vw; max-height:84vh; overflow-y:auto; background:#000000; border:1px solid #e8e8e8; padding:12px;">
      <div class="rail-row" style="justify-content:space-between; margin-bottom:6px;">
        <span>command bar <span class="muted">[${MOD_LABEL}+k]</span></span>
        <span class="composer-controls">
          <button id="command-bar-home-btn" type="button">[~ home / start]</button>
          <button id="command-bar-refresh-btn" type="button">[refresh]</button>
          <button id="command-bar-close-btn" type="button">[close · esc]</button>
        </span>
      </div>
      <div class="start-input-row">
        <span class="muted">&gt;</span>
        <input
          id="command-bar-input"
          class="start-input-field"
          type="text"
          spellcheck="false"
          autocorrect="off"
          autocapitalize="off"
          placeholder="url, question, mail: term, brain: term, or command (home, new, bookmark, compare, lock)_"
          value="${escapeHtml(state.commandBarInput)}"
        />
      </div>
      <div class="start-controls-row" style="margin-top:6px;">
        <span class="muted">enter runs selected route · up/down selects route</span>
        <div class="composer-controls">
          <label class="muted">model:</label>
          <select id="overlay-model-select">
            ${getAvailableModelsForPicker().map(
              (m) => `
              <option value="${escapeHtml(m.id)}" ${state.selectedModel === m.id ? "selected" : ""}>
                ${escapeHtml(m.label)}
              </option>
            `
            ).join("")}
          </select>
          <button id="overlay-web-toggle" class="${state.webSearchEnabled ? "active" : ""}">
            web: ${state.webSearchEnabled ? "on" : "off"}
          </button>
        </div>
      </div>
      <div id="overlay-routes-slot">
        ${renderRoutesListHtml(routes, clampedIdx, "overlay")}
      </div>
      <div class="cmd-foryou-section">
        <div class="start-col-header">
          <span>for you <span class="muted" id="overlay-foryou-count">(${state.digestItems.length}${state.digestRefreshing ? " · updating..." : ""})</span></span>
          <button id="overlay-open-home-foryou-btn" type="button">[view all on start screen]</button>
        </div>
        <div id="overlay-foryou-slot" class="start-foryou-list">
          ${renderDigestItemsHtml(state.digestItems, "overlay")}
        </div>
      </div>
    </div>
  `;

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) {
      actions.onCloseCommandBar?.();
    }
  });

  overlay
    .querySelector("#command-bar-home-btn")
    ?.addEventListener("click", () => {
      actions.onCloseCommandBar?.();
      actions.onGoHome?.();
    });

  overlay
    .querySelector("#overlay-open-home-foryou-btn")
    ?.addEventListener("click", () => {
      actions.onCloseCommandBar?.();
      actions.onGoHome?.();
    });

  overlay
    .querySelector("#command-bar-refresh-btn")
    ?.addEventListener("click", () => {
      actions.onRefreshDigest?.();
    });

  overlay
    .querySelector("#command-bar-close-btn")
    ?.addEventListener("click", () => {
      actions.onCloseCommandBar?.();
    });

  const modelSelect = overlay.querySelector(
    "#overlay-model-select"
  ) as HTMLSelectElement | null;
  modelSelect?.addEventListener("change", () => {
    actions.onChangeModel(modelSelect.value as LocalModelId);
    renderCommandBarOverlay(actions);
  });

  overlay
    .querySelector("#overlay-web-toggle")
    ?.addEventListener("click", () => {
      actions.onToggleWeb();
      renderCommandBarOverlay(actions);
    });

  bindDigestItemEvents(overlay, actions, true);

  bindUnifiedCommandBox(
    overlay,
    "#command-bar-input",
    "#overlay-routes-slot",
    "overlay",
    actions,
    true
  );
}

function bindUnifiedCommandBox(
  root: HTMLElement,
  inputSelector: string,
  slotSelector: string,
  prefixId: string,
  actions: StartScreenActions,
  isOverlay: boolean
): void {
  const input = root.querySelector(inputSelector) as HTMLInputElement | null;
  const slot = root.querySelector(slotSelector) as HTMLElement | null;
  if (!input || !slot) return;

  input.focus();
  const len = input.value.length;
  input.setSelectionRange(len, len);

  const refreshSlot = () => {
    const routes = rankCommandBarRoutes(state.commandBarInput);
    if (state.commandBarSelectedIdx >= routes.length) {
      state.commandBarSelectedIdx = 0;
    }
    slot.innerHTML = renderRoutesListHtml(
      routes,
      state.commandBarSelectedIdx,
      prefixId
    );
    bindRouteClicks();
  };

  const executeRouteAt = (idx: number) => {
    const routes = rankCommandBarRoutes(state.commandBarInput);
    const chosen = routes[idx] ?? routes[0];
    if (!chosen) return;
    const raw = state.commandBarInput.trim();
    state.commandBarInput = "";
    state.commandBarSelectedIdx = 0;
    if (actions.onExecuteCommandRoute) {
      actions.onExecuteCommandRoute(chosen, raw);
    } else if (raw) {
      actions.onSubmitStartInput(raw);
    }
  };

  const bindRouteClicks = () => {
    slot.querySelectorAll("[data-cmd-route-idx]").forEach((el) => {
      el.addEventListener("click", () => {
        const idx = Number(
          (el as HTMLElement).getAttribute("data-cmd-route-idx") ?? "0"
        );
        executeRouteAt(idx);
      });
    });
  };

  bindRouteClicks();

  input.addEventListener("input", () => {
    state.commandBarInput = input.value;
    state.commandBarSelectedIdx = 0;
    refreshSlot();
  });

  input.addEventListener("keydown", (e) => {
    const routes = rankCommandBarRoutes(state.commandBarInput);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      state.commandBarSelectedIdx =
        routes.length > 0
          ? (state.commandBarSelectedIdx + 1) % routes.length
          : 0;
      refreshSlot();
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      state.commandBarSelectedIdx =
        routes.length > 0
          ? (state.commandBarSelectedIdx - 1 + routes.length) % routes.length
          : 0;
      refreshSlot();
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      executeRouteAt(state.commandBarSelectedIdx);
      return;
    }
    if (e.key === "Escape") {
      if (isOverlay) {
        e.preventDefault();
        actions.onCloseCommandBar?.();
      } else {
        input.value = "";
        state.commandBarInput = "";
        state.commandBarSelectedIdx = 0;
        refreshSlot();
      }
    }
  });
}

export function renderProfileUnlockOverlay(actions: {
  onUnlockProfile?: (profileId: string, pin: string) => void;
  onCreateProfile?: (name: string, pin: string) => void;
  onDismissProfilePrompt?: () => void;
}): void {
  let overlay = document.getElementById("profile-unlock-overlay");
  const profileInfo = state.knowledge.profile;
  const isUnlocked = Boolean(
    profileInfo?.unlocked && profileInfo?.active_profile
  );

  if (!state.profilePromptOpen || isUnlocked) {
    if (overlay) {
      overlay.remove();
    }
    return;
  }

  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "profile-unlock-overlay";
    overlay.style.cssText =
      "position:fixed; inset:0; background:rgba(0,0,0,0.84); z-index:9500; display:flex; align-items:center; justify-content:center;";
    document.body.appendChild(overlay);
  }

  const profilesList = profileInfo?.profiles ?? [];

  overlay.innerHTML = `
    <div id="profile-unlock-modal" class="start-input-box" style="width:560px; max-width:94vw; background:#000000; border:1px solid #e8e8e8; padding:16px;">
      <div class="rail-row" style="justify-content:space-between; margin-bottom:10px; border-bottom:1px solid #333333; padding-bottom:6px;">
        <span><strong>unlock satz profile</strong> <span class="muted">(loads brain, mail &amp; vault)</span></span>
        <button id="profile-modal-dismiss-btn" type="button">[skip · esc]</button>
      </div>
      ${
        state.profileStatusMessage
          ? `<div class="profile-status-banner" style="margin-bottom:8px;">${escapeHtml(state.profileStatusMessage)}</div>`
          : ""
      }
      ${
        profilesList.length > 0
          ? `
            <div class="muted" style="margin-bottom:6px;">select your profile and enter its 6-digit PIN:</div>
            <div class="vault-form-row" style="margin-bottom:12px;">
              <select id="profile-modal-select" class="vault-input">
                ${profilesList
                  .map(
                    (p) =>
                      `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)} (${escapeHtml(p.id)})</option>`
                  )
                  .join("")}
              </select>
              <input
                id="profile-modal-pin"
                class="vault-input vault-pin-input"
                type="password"
                inputmode="numeric"
                maxlength="6"
                spellcheck="false"
                autocorrect="off"
                autocapitalize="off"
                placeholder="6-digit PIN_"
              />
              <button id="profile-modal-unlock-btn" type="button">[unlock]</button>
            </div>
          `
          : ""
      }
      <div class="muted" style="margin-bottom:6px; border-top:1px solid #222222; padding-top:8px;">
        ${profilesList.length > 0 ? "or create a new profile:" : "no profile found yet — create a profile with a 6-digit PIN:"}
      </div>
      <div class="vault-form-row">
        <input
          id="profile-modal-create-name"
          class="vault-input"
          type="text"
          spellcheck="false"
          autocorrect="off"
          autocapitalize="off"
          placeholder="profile name (e.g. Nikita)_"
        />
        <input
          id="profile-modal-create-pin"
          class="vault-input vault-pin-input"
          type="password"
          inputmode="numeric"
          maxlength="6"
          spellcheck="false"
          autocorrect="off"
          autocapitalize="off"
          placeholder="6-digit PIN_"
        />
        <button id="profile-modal-create-btn" type="button">[+ create &amp; unlock]</button>
      </div>
    </div>
  `;

  const pinEl = overlay.querySelector(
    "#profile-modal-pin"
  ) as HTMLInputElement | null;
  const createNameEl = overlay.querySelector(
    "#profile-modal-create-name"
  ) as HTMLInputElement | null;
  if (pinEl) {
    pinEl.focus();
  } else {
    createNameEl?.focus();
  }

  overlay
    .querySelector("#profile-modal-dismiss-btn")
    ?.addEventListener("click", () => {
      actions.onDismissProfilePrompt?.();
    });

  const doUnlock = () => {
    const sel = overlay?.querySelector(
      "#profile-modal-select"
    ) as HTMLSelectElement | null;
    const pid = sel?.value || profilesList[0]?.id || "";
    const pin = pinEl?.value.trim() ?? "";
    if (pid && pin && actions.onUnlockProfile) {
      actions.onUnlockProfile(pid, pin);
    }
  };

  overlay
    .querySelector("#profile-modal-unlock-btn")
    ?.addEventListener("click", doUnlock);
  pinEl?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      doUnlock();
    } else if (e.key === "Escape") {
      e.preventDefault();
      actions.onDismissProfilePrompt?.();
    }
  });

  const doCreate = () => {
    const cPinEl = overlay?.querySelector(
      "#profile-modal-create-pin"
    ) as HTMLInputElement | null;
    const name = createNameEl?.value.trim() ?? "";
    const pin = cPinEl?.value.trim() ?? "";
    if (name && pin && actions.onCreateProfile) {
      actions.onCreateProfile(name, pin);
    }
  };

  overlay
    .querySelector("#profile-modal-create-btn")
    ?.addEventListener("click", doCreate);
  overlay
    .querySelector("#profile-modal-create-pin")
    ?.addEventListener("keydown", (e) => {
      if ((e as KeyboardEvent).key === "Enter") {
        e.preventDefault();
        doCreate();
      }
    });
}
