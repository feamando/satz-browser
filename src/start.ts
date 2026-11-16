import {
  escapeHtml,
  MOD_LABEL,
  rankCommandBarRoutes,
  state,
} from "./state";
import type { CommandBarRoute, LocalModelId } from "./types";

const LOCAL_MODELS: LocalModelId[] = [
  "gemma-4-e4b",
  "planck3 (web)",
  "hertz (reader)",
  "planck (reader)",
  "gemini-2.5-flash (cloud)",
  "gemini-2.5-pro (cloud)",
];

export interface StartScreenActions {
  onSubmitStartInput: (raw: string) => void;
  onExecuteCommandRoute?: (route: CommandBarRoute, raw: string) => void;
  onSelectConversation: (id: string) => void;
  onOpenDigestUrl: (url: string, title: string) => void;
  onChangeModel: (model: LocalModelId) => void;
  onToggleWeb: () => void;
  onCloseCommandBar?: () => void;
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

  container.innerHTML = `
    <div class="start-screen">
      <div class="start-container">
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
              placeholder="url, question, mail: term, brain: term, or command (new, bookmark, compare, lock)_"
              value="${escapeHtml(state.commandBarInput)}"
            />
            <span class="caret-blink">▌</span>
          </div>

          <div class="start-controls-row">
            <span class="muted">enter runs default route · up/down selects route</span>
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

          <div id="start-routes-slot">
            ${renderRoutesListHtml(initialRoutes, clampedIdx, "start")}
          </div>
        </div>

        <div class="start-columns">
          <div class="start-col">
            <div class="start-col-header">for you</div>
            ${
              state.digestItems.length === 0
                ? `<div class="muted">browse or bookmark pages to build your digest</div>`
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

  bindUnifiedCommandBox(
    container,
    "#start-main-input",
    "#start-routes-slot",
    "start",
    actions,
    false
  );

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
      "position:fixed; inset:0; background:rgba(0,0,0,0.82); z-index:9000; display:flex; align-items:flex-start; justify-content:center; padding-top:72px;";
    document.body.appendChild(overlay);
  }

  const routes = rankCommandBarRoutes(state.commandBarInput);
  const clampedIdx = Math.max(
    0,
    Math.min(state.commandBarSelectedIdx, Math.max(0, routes.length - 1))
  );

  overlay.innerHTML = `
    <div id="command-bar-modal" class="start-input-box" style="width:680px; max-width:94vw; background:#000000; border:1px solid #e8e8e8; padding:12px;">
      <div class="rail-row" style="justify-content:space-between; margin-bottom:6px;">
        <span>command bar <span class="muted">[${MOD_LABEL}+k]</span></span>
        <button id="command-bar-close-btn">[close · esc]</button>
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
          placeholder="url, question, mail: term, brain: term, or command (new, bookmark, compare, lock)_"
          value="${escapeHtml(state.commandBarInput)}"
        />
      </div>
      <div class="start-controls-row" style="margin-top:6px;">
        <span class="muted">enter runs selected route · up/down selects route</span>
        <div class="composer-controls">
          <label class="muted">model:</label>
          <select id="overlay-model-select">
            ${LOCAL_MODELS.map(
              (m) => `
              <option value="${escapeHtml(m)}" ${state.selectedModel === m ? "selected" : ""}>
                ${escapeHtml(m)}
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
    </div>
  `;

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) {
      actions.onCloseCommandBar?.();
    }
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
