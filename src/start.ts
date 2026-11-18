import { icon, type IconName } from "./design-system/icons";
import {
  escapeHtml,
  formatRelativeTime,
  getAvailableModelsForPicker,
  getModelPrivacySummary,
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

function digestKindMeta(kind?: string): { ico: IconName; label: string } {
  switch (kind) {
    case "watch_triggered":
      return { ico: "watch", label: "Watch" };
    case "bookmark_changed":
      return { ico: "star", label: "Changed" };
    case "mail_reply":
      return { ico: "reply", label: "Reply" };
    case "mail_recent":
      return { ico: "mail", label: "Mail" };
    case "mail_ping":
      return { ico: "mail", label: "Ping" };
    case "mail_order":
      return { ico: "box", label: "Order" };
    case "mail_promo":
      return { ico: "spark", label: "Promo" };
    case "news_story":
      return { ico: "news", label: "News" };
    case "brain_entity":
      return { ico: "brain", label: "Brain" };
    case "digest_adjacent":
      return { ico: "globe", label: "Related" };
    case "source_capture":
      return { ico: "doc", label: "Captured" };
    default:
      return { ico: "globe", label: "Web" };
  }
}

function routeKindIcon(kind: CommandBarRoute["kind"]): string {
  switch (kind) {
    case "open_url":
      return icon("globe", "ico-sm");
    case "ask_model":
      return icon("spark", "ico-sm");
    case "search_mail":
      return icon("mail", "ico-sm");
    case "search_brain":
      return icon("brain", "ico-sm");
    case "search_news":
      return icon("news", "ico-sm");
    default:
      return icon("cmd", "ico-sm");
  }
}

function convOriginIcon(origin?: string): string {
  switch (origin) {
    case "mail":
      return icon("mail", "ico-sm");
    case "news":
      return icon("news", "ico-sm");
    default:
      return icon("chat", "ico-sm");
  }
}

function formatDigestTime(ts?: number): string {
  if (!ts || !Number.isFinite(ts) || ts <= 0) return "";
  return formatRelativeTime(String(Math.floor(ts)));
}

function formatHomeDateLine(): string {
  const now = new Date();
  const weekday = now
    .toLocaleDateString("en-US", { weekday: "long" })
    .toUpperCase();
  const day = String(now.getDate());
  const month = now
    .toLocaleDateString("en-US", { month: "short" })
    .toUpperCase();
  return `${weekday} · ${day} ${month}`;
}

function formatHomeGreeting(): string {
  const profileInfo = state.knowledge.profile;
  const activeName = profileInfo?.unlocked
    ? profileInfo.active_profile?.name?.trim()
    : "";
  const hour = new Date().getHours();
  const part =
    hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  if (activeName) {
    return `${part}, ${activeName}`;
  }
  return "Where do you want to start?";
}

function formatPlainPrivacyNote(rawPrivacy: string): string {
  return rawPrivacy.replace(/^\[|\]$/g, "").trim();
}

function renderBannerClass(msg: string): string {
  return msg.toLowerCase().startsWith("error") ? "banner danger" : "banner warn";
}

function renderDigestItemsHtml(
  items: DigestEntry[],
  mode: "start" | "overlay"
): string {
  if (items.length === 0) {
    return `<div class="home-empty">Unlock a profile, receive mail, browse pages, or refresh news to populate your feed.</div>`;
  }
  const visible = mode === "overlay" ? items.slice(0, 6) : items;
  return visible
    .map((item) => {
      const kind = digestKindMeta(item.kind);
      const relTime = formatDigestTime(item.ts);
      const leadImg = (item.image_url || "").trim();
      const extraImgs =
        mode === "start" && Array.isArray(item.images)
          ? item.images.filter((u) => u && u !== leadImg).slice(0, 2)
          : [];
      const snippetText = (item.summary || "").trim();
      const reasonText = (item.reason || "").trim();
      const metaParts = [
        kind.label,
        item.domain,
        relTime,
        mode === "start" ? reasonText : "",
      ].filter((p) => Boolean(p && p.trim()));

      return `
        <div
          class="digest ${mode === "overlay" ? "compact" : ""}"
          data-digest-url="${escapeHtml(item.url)}"
          data-digest-title="${escapeHtml(item.title)}"
          ${item.conversation_id ? `data-digest-conv-id="${escapeHtml(item.conversation_id)}"` : ""}
        >
          <div class="digest-src" title="${escapeHtml(kind.label)}">
            ${icon(kind.ico)}
          </div>
          <div class="digest-body">
            <b>${escapeHtml(item.title)}</b>
            <small>${escapeHtml(metaParts.join(" · "))}</small>
            ${
              mode === "start" && snippetText
                ? `<div class="digest-snippet">${escapeHtml(snippetText)}</div>`
                : ""
            }
            ${
              extraImgs.length > 0
                ? `<div class="digest-thumbs">${extraImgs
                    .map(
                      (iu) =>
                        `<img src="${escapeHtml(iu)}" alt="" loading="lazy" referrerpolicy="no-referrer" />`
                    )
                    .join("")}</div>`
                : ""
            }
          </div>
          ${
            leadImg
              ? `<img class="digest-thumb ${mode === "overlay" ? "compact" : ""}" src="${escapeHtml(leadImg)}" alt="" loading="lazy" referrerpolicy="no-referrer" />`
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
      state.commandModelMenuOpen = null;
      if (closeCommandBarOnClick) {
        actions.onCloseCommandBar?.();
      }
      if (url) actions.onOpenDigestUrl(url, title, convId);
    });
  });

  root
    .querySelectorAll("img.digest-thumb, .digest-thumbs img")
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
    <div id="${escapeHtml(prefixId)}-routes" class="cmd-results">
      ${routes
        .map((r, idx) => {
          const isSelected = idx === selectedIdx;
          const privacyText = formatPlainPrivacyNote(r.privacy);
          return `
            <button
              type="button"
              class="menu-item"
              data-cmd-route-idx="${idx}"
              aria-selected="${isSelected ? "true" : "false"}"
            >
              ${routeKindIcon(r.kind)}
              <span class="truncate">${escapeHtml(r.label)}</span>
              <span class="end">${escapeHtml(privacyText)}</span>
            </button>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderCommandModelSelectorHtml(mode: "start" | "overlay"): string {
  const models = getAvailableModelsForPicker();
  const cur = models.find((m) => m.id === state.selectedModel);
  const curLabel = cur?.label || state.selectedModel;
  const privacyNote = formatPlainPrivacyNote(
    getModelPrivacySummary(state.selectedModel)
  );
  const menuOpen = state.commandModelMenuOpen === mode;
  return `
    <div class="model-chip-anchor">
      <button
        id="${mode}-model-chip"
        class="chip"
        type="button"
        title="${escapeHtml(privacyNote)}"
        aria-expanded="${menuOpen ? "true" : "false"}"
      >
        ${icon("spark", "ico-sm")}
        <span class="truncate">${escapeHtml(curLabel)}</span>
        ${icon("chev", "ico-sm")}
      </button>
      ${
        menuOpen
          ? `
            <div class="menu model-menu-pop" id="${mode}-model-menu" role="menu">
              <div class="model-menu-note">${escapeHtml(privacyNote)}</div>
              ${models
                .map(
                  (m) => `
                <button
                  type="button"
                  class="menu-item ${state.selectedModel === m.id ? "active" : ""}"
                  data-select-cmd-model="${escapeHtml(m.id)}"
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
    </div>
  `;
}

function renderBigBarHtml(
  mode: "start" | "overlay",
  routes: CommandBarRoute[],
  selectedIdx: number
): string {
  const boxId = mode === "start" ? "start-command-bar-box" : "command-bar-modal";
  const inputId = mode === "start" ? "start-main-input" : "command-bar-input";
  const routesSlotId =
    mode === "start" ? "start-routes-slot" : "overlay-routes-slot";

  return `
    <div id="${boxId}" class="bigbar ${mode === "overlay" ? "cmd-bigbar" : ""}">
      <div class="bigbar-in">
        ${icon("cmd", "ico-sm")}
        <input
          id="${inputId}"
          class="bigbar-input"
          type="text"
          spellcheck="false"
          autocorrect="off"
          autocapitalize="off"
          placeholder="URL, question, mail: term, brain: term, or command"
          value="${escapeHtml(state.commandBarInput)}"
        />
        ${
          mode === "start"
            ? `<span class="kbd">${escapeHtml(MOD_LABEL)}+K</span>`
            : `<button id="command-bar-close-btn" class="icon-btn" type="button" title="Close command bar (Esc)">${icon("x", "ico-sm")}</button>`
        }
      </div>

      <div class="bigbar-ctl">
        ${renderCommandModelSelectorHtml(mode)}
        <button
          id="${mode}-web-toggle"
          type="button"
          class="chip ${state.webSearchEnabled ? "on" : ""}"
          aria-pressed="${state.webSearchEnabled ? "true" : "false"}"
          title="Toggle live web search"
        >
          ${icon("globe", "ico-sm")}
          <span>Web</span>
        </button>
        ${
          mode === "overlay"
            ? `
              <button id="command-bar-home-btn" class="chip" type="button" title="Go to Home">
                ${icon("home", "ico-sm")}
                <span>Home</span>
              </button>
              <button id="command-bar-refresh-btn" class="chip" type="button" title="Refresh For you digest">
                ${icon("reload", "ico-sm")}
                <span>Refresh</span>
              </button>
            `
            : ""
        }
        <button
          id="${mode}-submit-btn"
          class="send"
          type="button"
          title="Run selected route (Enter)"
        >
          ${icon("send", "ico-sm")}
        </button>
      </div>

      <div id="${routesSlotId}">
        ${renderRoutesListHtml(routes, selectedIdx, mode)}
      </div>

      ${
        mode === "overlay"
          ? `
            <div class="sep cmd-sep"></div>
            <div class="cmd-foryou-head">
              <div class="label">
                <span>For you</span>
                <span class="ct" id="overlay-foryou-count">(${state.digestItems.length}${state.digestRefreshing ? " · updating..." : ""})</span>
                <button id="overlay-open-home-foryou-btn" class="btn-text end" type="button">View all</button>
              </div>
            </div>
            <div id="overlay-foryou-slot" class="cmd-foryou-list">
              ${renderDigestItemsHtml(state.digestItems, "overlay")}
            </div>
          `
          : ""
      }
    </div>
  `;
}

export function renderStartScreen(
  container: HTMLElement,
  actions: StartScreenActions,
  autoFocusInput = true
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
      <div class="card start-unlock-card" id="start-profile-unlock-card">
        <div class="card-h">
          ${icon("lock", "ico-sm")}
          <b>Profile locked</b>
          <span class="end muted">Unlock Brain, Mail &amp; Password Vault</span>
        </div>
        ${
          state.profileStatusMessage
            ? `<div class="${renderBannerClass(state.profileStatusMessage)}">${escapeHtml(state.profileStatusMessage)}</div>`
            : ""
        }
        ${
          profilesList.length > 0
            ? `
              <div class="form-row">
                <select id="start-unlock-profile-select" class="select">
                  ${profilesList
                    .map(
                      (p) =>
                        `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)} (${escapeHtml(p.id)})</option>`
                    )
                    .join("")}
                </select>
                <input
                  id="start-unlock-pin-input"
                  class="input pin"
                  type="password"
                  inputmode="numeric"
                  maxlength="6"
                  spellcheck="false"
                  autocorrect="off"
                  autocapitalize="off"
                  placeholder="PIN"
                />
                <button id="start-unlock-profile-btn" class="btn primary" type="button">Unlock</button>
              </div>
              <div class="sep"></div>
            `
            : ""
        }
        <div class="section">
          <div class="muted">${profilesList.length > 0 ? "Or create a new profile" : "Create a new profile with a 6-digit PIN"}</div>
          <div class="form-row">
            <input
              id="start-create-profile-name"
              class="input"
              type="text"
              spellcheck="false"
              autocorrect="off"
              autocapitalize="off"
              placeholder="Profile name (e.g. Nikita)"
            />
            <input
              id="start-create-profile-pin"
              class="input pin"
              type="password"
              inputmode="numeric"
              maxlength="6"
              spellcheck="false"
              autocorrect="off"
              autocapitalize="off"
              placeholder="6-digit PIN"
            />
            <button id="start-create-profile-btn" class="btn" type="button">Create &amp; unlock</button>
          </div>
        </div>
      </div>
    `
    : "";

  const updatedLabel = state.digestUpdatedAt
    ? ` · updated ${formatRelativeTime(String(Math.floor(state.digestUpdatedAt / 1000)))}`
    : "";
  const foryouMeta = `${state.digestItems.length} item${state.digestItems.length === 1 ? "" : "s"}${state.digestRefreshing ? " · updating..." : updatedLabel}`;

  container.innerHTML = `
    <div class="home">
      <div class="home-hello">
        <div class="home-date">${escapeHtml(formatHomeDateLine())}</div>
        <h1 class="home-greet">${escapeHtml(formatHomeGreeting())}</h1>
      </div>

      ${renderBigBarHtml("start", initialRoutes, clampedIdx)}

      ${unlockPromptHtml}

      <div class="home-cols">
        <div>
          <div class="label home-section-head">
            <span>For you</span>
            <span class="ct" id="start-foryou-meta">${escapeHtml(foryouMeta)}</span>
            <button id="start-refresh-digest-btn" class="btn-text end" type="button">Refresh</button>
          </div>
          <div id="start-foryou-slot">
            ${renderDigestItemsHtml(state.digestItems, "start")}
          </div>
        </div>

        <div>
          <div class="label home-section-head">
            <span>Resume</span>
            <span class="end">${resumeConvs.length} conversation${resumeConvs.length === 1 ? "" : "s"}</span>
          </div>
          ${
            resumeConvs.length === 0
              ? `<div class="home-empty">No recent conversations yet.</div>`
              : resumeConvs
                  .map(
                    (c) => `
                <div class="row" data-resume-id="${escapeHtml(c.id)}">
                  ${convOriginIcon(c.origin)}
                  <span class="t">${escapeHtml(c.title)}</span>
                  <span class="meta">${c.source_count ?? 0} src · ${escapeHtml(formatRelativeTime(c.last_active_at))}</span>
                </div>
              `
                  )
                  .join("")
          }
        </div>
      </div>
    </div>
  `;

  bindBigBarEvents(
    container,
    "#start-main-input",
    "#start-routes-slot",
    "start",
    actions,
    false,
    autoFocusInput && isUnlocked && !state.commandModelMenuOpen,
    () => renderStartScreen(container, actions, false)
  );

  const startPinInput = container.querySelector(
    "#start-unlock-pin-input"
  ) as HTMLInputElement | null;
  if (autoFocusInput && !isUnlocked && startPinInput) {
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

  container
    .querySelector("#start-refresh-digest-btn")
    ?.addEventListener("click", () => {
      actions.onRefreshDigest?.();
    });

  container.querySelectorAll("[data-resume-id]").forEach((el) => {
    el.addEventListener("click", () => {
      const id = (el as HTMLElement).getAttribute("data-resume-id");
      state.commandModelMenuOpen = null;
      if (id) actions.onSelectConversation(id);
    });
  });

  bindDigestItemEvents(container, actions, false);
}

export function renderCommandBarOverlay(
  actions: StartScreenActions,
  autoFocusInput = true
): void {
  let overlay = document.getElementById("command-bar-overlay");
  if (!state.commandBarOpen) {
    state.commandModelMenuOpen = null;
    if (overlay) {
      overlay.remove();
    }
    return;
  }

  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "command-bar-overlay";
    overlay.className = "cmd-backdrop";
    document.body.appendChild(overlay);
  } else {
    overlay.className = "cmd-backdrop";
  }

  const routes = rankCommandBarRoutes(state.commandBarInput);
  const clampedIdx = Math.max(
    0,
    Math.min(state.commandBarSelectedIdx, Math.max(0, routes.length - 1))
  );

  overlay.innerHTML = renderBigBarHtml("overlay", routes, clampedIdx);

  overlay.onclick = (e) => {
    if (e.target === overlay) {
      state.commandModelMenuOpen = null;
      actions.onCloseCommandBar?.();
    }
  };

  overlay
    .querySelector("#command-bar-home-btn")
    ?.addEventListener("click", () => {
      state.commandModelMenuOpen = null;
      actions.onCloseCommandBar?.();
      actions.onGoHome?.();
    });

  overlay
    .querySelector("#overlay-open-home-foryou-btn")
    ?.addEventListener("click", () => {
      state.commandModelMenuOpen = null;
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
      state.commandModelMenuOpen = null;
      actions.onCloseCommandBar?.();
    });

  bindDigestItemEvents(overlay, actions, true);

  bindBigBarEvents(
    overlay,
    "#command-bar-input",
    "#overlay-routes-slot",
    "overlay",
    actions,
    true,
    autoFocusInput && !state.commandModelMenuOpen,
    () => renderCommandBarOverlay(actions, false)
  );
}

function bindBigBarEvents(
  root: HTMLElement,
  inputSelector: string,
  slotSelector: string,
  prefixId: "start" | "overlay",
  actions: StartScreenActions,
  isOverlay: boolean,
  autoFocusInput: boolean,
  onRefreshSelf: () => void
): void {
  const input = root.querySelector(inputSelector) as HTMLInputElement | null;
  const slot = root.querySelector(slotSelector) as HTMLElement | null;
  if (!input || !slot) return;

  if (autoFocusInput) {
    input.focus();
    const len = input.value.length;
    input.setSelectionRange(len, len);
  }

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
    state.commandModelMenuOpen = null;
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

  root.querySelector(`#${prefixId}-submit-btn`)?.addEventListener("click", () => {
    executeRouteAt(state.commandBarSelectedIdx);
  });

  root
    .querySelector(`#${prefixId}-model-chip`)
    ?.addEventListener("click", (e) => {
      e.stopPropagation();
      state.commandModelMenuOpen =
        state.commandModelMenuOpen === prefixId ? null : prefixId;
      onRefreshSelf();
    });

  root.querySelectorAll("[data-select-cmd-model]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mId = (btn as HTMLElement).getAttribute("data-select-cmd-model");
      state.commandModelMenuOpen = null;
      if (mId) {
        actions.onChangeModel(mId as LocalModelId);
        if (isOverlay) {
          renderCommandBarOverlay(actions, false);
        }
      } else {
        onRefreshSelf();
      }
    });
  });

  root
    .querySelector(`#${prefixId}-web-toggle`)
    ?.addEventListener("click", () => {
      actions.onToggleWeb();
      if (isOverlay) {
        renderCommandBarOverlay(actions, false);
      }
    });

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
      if (state.commandModelMenuOpen === prefixId) {
        e.preventDefault();
        state.commandModelMenuOpen = null;
        onRefreshSelf();
        return;
      }
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
    overlay.className = "modal-backdrop";
    document.body.appendChild(overlay);
  } else {
    overlay.className = "modal-backdrop";
  }

  const profilesList = profileInfo?.profiles ?? [];

  overlay.innerHTML = `
    <div id="profile-unlock-modal" class="card profile-modal">
      <div class="card-h">
        ${icon("lock", "ico-sm")}
        <b>Unlock profile</b>
        <button id="profile-modal-dismiss-btn" class="btn-text end" type="button">Skip</button>
      </div>
      ${
        state.profileStatusMessage
          ? `<div class="${renderBannerClass(state.profileStatusMessage)}">${escapeHtml(state.profileStatusMessage)}</div>`
          : ""
      }
      ${
        profilesList.length > 0
          ? `
            <div class="section">
              <div class="muted">Select your profile and enter its 6-digit PIN to load Brain, Mail &amp; Vault.</div>
              <div class="form-row">
                <select id="profile-modal-select" class="select">
                  ${profilesList
                    .map(
                      (p) =>
                        `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)} (${escapeHtml(p.id)})</option>`
                    )
                    .join("")}
                </select>
                <input
                  id="profile-modal-pin"
                  class="input pin"
                  type="password"
                  inputmode="numeric"
                  maxlength="6"
                  spellcheck="false"
                  autocorrect="off"
                  autocapitalize="off"
                  placeholder="PIN"
                />
                <button id="profile-modal-unlock-btn" class="btn primary" type="button">Unlock</button>
              </div>
            </div>
            <div class="sep"></div>
          `
          : ""
      }
      <div class="section">
        <div class="muted">${profilesList.length > 0 ? "Or create a new profile" : "Create a profile with a 6-digit PIN"}</div>
        <div class="form-row">
          <input
            id="profile-modal-create-name"
            class="input"
            type="text"
            spellcheck="false"
            autocorrect="off"
            autocapitalize="off"
            placeholder="Profile name (e.g. Nikita)"
          />
          <input
            id="profile-modal-create-pin"
            class="input pin"
            type="password"
            inputmode="numeric"
            maxlength="6"
            spellcheck="false"
            autocorrect="off"
            autocapitalize="off"
            placeholder="6-digit PIN"
          />
          <button id="profile-modal-create-btn" class="btn" type="button">Create &amp; unlock</button>
        </div>
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
