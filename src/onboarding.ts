import { icon } from "./design-system/icons";
import { t } from "./i18n";
import {
  bindProfileUploadSectionEvents,
  renderProfileUploadSectionHtml,
} from "./profile_prompt";
import {
  escapeHtml,
  hasAnyGenerativeModelConfigured,
  MOD_LABEL,
  setRailAccordionPref,
  state,
} from "./state";
import type { CloudProviderInfo, HfDownloadJob } from "./types";

export interface OnboardingActions {
  onCreateProfile: (name: string, pin: string) => void | Promise<void>;
  onImportProfileFile: (
    bundleB64: string,
    pin: string,
    localPin?: string
  ) => void | Promise<void>;
  onStartDemoMode: () => void;
  onSaveCloudModelKey: (
    providerId: string,
    apiKey: string
  ) => Promise<{ ok: boolean; error?: string }>;
  onSelectChatModel: (modelId: string) => Promise<void>;
  onStartHfDownload: (payload: {
    repo_id: string;
    token?: string;
    use_as_chat?: boolean;
  }) => Promise<void>;
  onCancelHfDownload: (downloadId: string) => Promise<void>;
  onLinkExistingLocalFolder: () => Promise<void>;
  onFinishModelSetup: () => void;
  onSetTourStep: (step: number | null) => void;
  onRenderRail?: () => void;
}

const ONBOARD_LOCAL_PRESETS = [
  {
    repo_id: "google/gemma-4-E4B-it",
    label: "Gemma 4 E4B IT",
    approx_size: "~15.3 GB",
    gated: true,
    notes: "Reference local multimodal Gemma model (16 GB+ RAM/VRAM + HF license & token).",
  },
  {
    repo_id: "google/gemma-3-4b-it",
    label: "Gemma 3 4B IT",
    approx_size: "~8.0 GB",
    gated: true,
    notes: "Compact Gemma 3 model (requires HF license approval + HF token).",
  },
  {
    repo_id: "Qwen/Qwen2.5-1.5B-Instruct",
    label: "Qwen 2.5 1.5B Instruct",
    approx_size: "~3.1 GB",
    gated: false,
    notes: "Fast ungated local chat starter model for CPU or smaller laptops.",
  },
  {
    repo_id: "HuggingFaceTB/SmolLM2-1.7B-Instruct",
    label: "SmolLM2 1.7B Instruct",
    approx_size: "~3.4 GB",
    gated: false,
    notes: "Compact ungated Apache-2.0 local chat model.",
  },
] as const;

const TOUR_STEPS = [
  {
    id: "mail",
    anchorSelector: '[data-onboard-anchor="mail"]',
    accKey: "pinned" as const,
    titleKey: "onboard.tour_mail_title" as const,
    bodyKey: "onboard.tour_mail_body" as const,
  },
  {
    id: "news",
    anchorSelector: '[data-onboard-anchor="news"]',
    accKey: "pinned" as const,
    titleKey: "onboard.tour_news_title" as const,
    bodyKey: "onboard.tour_news_body" as const,
  },
  {
    id: "conversations",
    anchorSelector: '[data-onboard-anchor="conversations"]',
    accKey: "conversations" as const,
    titleKey: "onboard.tour_convs_title" as const,
    bodyKey: "onboard.tour_convs_body" as const,
  },
  {
    id: "bookmarks",
    anchorSelector: '[data-onboard-anchor="bookmarks"]',
    accKey: "sources" as const,
    titleKey: "onboard.tour_bookmarks_title" as const,
    bodyKey: "onboard.tour_bookmarks_body" as const,
  },
  {
    id: "settings",
    anchorSelector: '[data-onboard-anchor="settings"]',
    accKey: null,
    titleKey: "onboard.tour_settings_title" as const,
    bodyKey: "onboard.tour_settings_body" as const,
  },
] as const;

let onboardingCloudConnecting = false;
let onboardingCloudError = "";
let onboardingCloudKeyDraft = "";
let onboardingHfTokenDraft = "";
let onboardingCreateNameDraft = "";

function getCloudProvidersForOnboarding(): CloudProviderInfo[] {
  const cfg = state.modelConfig ?? state.sidecar.model_config ?? null;
  if (cfg?.cloud_providers && cfg.cloud_providers.length > 0) {
    return cfg.cloud_providers;
  }
  return [
    {
      id: "gemini",
      label: "Google Gemini API",
      env_key: "GEMINI_API_KEY",
      host: "generativelanguage.googleapis.com",
      placeholder: "AIzaSy...",
      configured: false,
      key_source: "none",
      masked_key: "",
      models: [],
      privacy_disclosure: t("settings.cloud_disclosure", {
        host: "generativelanguage.googleapis.com",
      }),
    },
    {
      id: "anthropic",
      label: "Anthropic API (Claude)",
      env_key: "ANTHROPIC_API_KEY",
      host: "api.anthropic.com",
      placeholder: "sk-ant-...",
      configured: false,
      key_source: "none",
      masked_key: "",
      models: [],
      privacy_disclosure: t("settings.cloud_disclosure", {
        host: "api.anthropic.com",
      }),
    },
    {
      id: "openai",
      label: "OpenAI API (GPT / o-series)",
      env_key: "OPENAI_API_KEY",
      host: "api.openai.com",
      placeholder: "sk-proj-...",
      configured: false,
      key_source: "none",
      masked_key: "",
      models: [],
      privacy_disclosure: t("settings.cloud_disclosure", {
        host: "api.openai.com",
      }),
    },
    {
      id: "mistral",
      label: "Mistral AI API",
      env_key: "MISTRAL_API_KEY",
      host: "api.mistral.ai",
      placeholder: "mistral-...",
      configured: false,
      key_source: "none",
      masked_key: "",
      models: [],
      privacy_disclosure: t("settings.cloud_disclosure", {
        host: "api.mistral.ai",
      }),
    },
  ];
}

function getLocalPresetsForOnboarding() {
  const cfg = state.modelConfig ?? state.sidecar.model_config ?? null;
  const catalog = cfg?.local_models?.hf_catalog ?? [];
  const byRepo = new Map<
    string,
    {
      repo_id: string;
      label: string;
      approx_size: string;
      gated: boolean;
      notes: string;
    }
  >();
  for (const item of ONBOARD_LOCAL_PRESETS) {
    byRepo.set(item.repo_id, { ...item });
  }
  for (const item of catalog) {
    if (!byRepo.has(item.repo_id)) {
      byRepo.set(item.repo_id, {
        repo_id: item.repo_id,
        label: item.label,
        approx_size: item.approx_size,
        gated: Boolean(item.gated),
        notes: item.notes,
      });
    }
  }
  return Array.from(byRepo.values());
}

function renderOnboardingDownloadsHtml(downloads: HfDownloadJob[]): string {
  if (!downloads || downloads.length === 0) return "";
  return `
    <div class="onboard-dl-list">
      ${downloads
        .slice(0, 3)
        .map((dl) => {
          const isActive = dl.state === "queued" || dl.state === "downloading";
          const pct = Math.max(0, Math.min(100, Number(dl.pct ?? 0)));
          const detail = dl.current_file || dl.error || dl.state;
          return `
            <div class="source-row">
              <div class="source-row-top">
                <span class="truncate">${escapeHtml(
                  t("settings.lm_hf_dl_progress", {
                    repo: dl.repo_id,
                    state: dl.state,
                    pct: pct.toFixed(1),
                    done: dl.files_done,
                    total: dl.files_total,
                    file: detail,
                  })
                )}</span>
                ${
                  isActive
                    ? `<button type="button" class="btn danger sm" data-onboard-hf-cancel="${escapeHtml(dl.download_id)}">${escapeHtml(t("settings.lm_hf_cancel_btn"))}</button>`
                    : ""
                }
              </div>
              <div class="lm-progress-track"><div class="lm-progress-fill" style="width:${pct}%"></div></div>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

export function updateOnboardingDownloadsInPlace(
  actions: Pick<OnboardingActions, "onCancelHfDownload">
): boolean {
  const slot = document.getElementById("onboard-dl-slot");
  if (!slot) return false;
  const cfg = state.modelConfig ?? state.sidecar.model_config ?? null;
  const downloads =
    state.hfDownloads.length > 0
      ? state.hfDownloads
      : (cfg?.local_models?.downloads ?? []);
  slot.innerHTML = renderOnboardingDownloadsHtml(downloads);
  slot
    .querySelectorAll<HTMLButtonElement>("[data-onboard-hf-cancel]")
    .forEach((btn) => {
      btn.addEventListener("click", () => {
        const dlId = btn.getAttribute("data-onboard-hf-cancel") ?? "";
        if (dlId) void actions.onCancelHfDownload(dlId);
      });
    });
  return true;
}

function renderWelcomeStepHtml(): string {
  const mode = state.onboardingMode;
  const busy = Boolean(state.profileUnlocking);
  const dis = busy ? "disabled" : "";
  const errBanner = state.onboardingValidationMsg
    ? `<div class="banner danger">${escapeHtml(state.onboardingValidationMsg)}</div>`
    : !busy && state.profileStatusMessage
      ? `<div class="banner ${state.profileStatusMessage.toLowerCase().startsWith("error") ? "danger" : "warn"}">${escapeHtml(state.profileStatusMessage)}</div>`
      : "";

  let bodyHtml = "";
  if (mode === "create") {
    bodyHtml = `
      <div class="section onboard-pane">
        <div class="muted">${escapeHtml(t("onboard.create_desc"))}</div>
        <div class="form-row">
          <input
            id="onboard-create-name"
            class="input"
            type="text"
            spellcheck="false"
            autocorrect="off"
            autocapitalize="off"
            value="${escapeHtml(onboardingCreateNameDraft)}"
            placeholder="${escapeHtml(t("profile.name_placeholder"))}"
            ${dis}
          />
          <input
            id="onboard-create-pin"
            class="input pin"
            type="password"
            inputmode="numeric"
            maxlength="6"
            spellcheck="false"
            autocorrect="off"
            autocapitalize="off"
            placeholder="${escapeHtml(t("profile.pin6_placeholder"))}"
            ${dis}
          />
        </div>
        <div class="onboard-actions-row">
          <button id="onboard-create-submit-btn" type="button" class="btn primary" ${dis}>
            ${busy ? `<span class="satz-spinner" aria-hidden="true"></span>` : ""}
            <span>${escapeHtml(busy ? t("profile.creating") : t("onboard.create_btn"))}</span>
          </button>
        </div>
      </div>
    `;
  } else if (mode === "upload") {
    bodyHtml = `
      <div class="section onboard-pane">
        <div class="muted">${escapeHtml(t("onboard.upload_desc"))}</div>
        ${renderProfileUploadSectionHtml("onboard")}
      </div>
    `;
  } else {
    bodyHtml = `
      <div class="section onboard-pane">
        <div class="muted">${escapeHtml(t("onboard.demo_desc"))}</div>
        <div class="onboard-actions-row">
          <button id="onboard-demo-start-btn" type="button" class="btn primary" ${dis}>
            ${icon("spark", "ico-sm")}
            <span>${escapeHtml(t("onboard.demo_btn"))}</span>
          </button>
        </div>
      </div>
    `;
  }

  return `
    <div class="card-h">
      ${icon("spark", "ico-sm")}
      <b>${escapeHtml(t("onboard.welcome_title"))}</b>
      <span class="end badge soft">${escapeHtml(t("onboard.badge_step", { step: 1, total: 2 }))}</span>
    </div>
    <div class="muted">${escapeHtml(t("onboard.welcome_sub"))}</div>
    <div class="seg onboard-mode-tabs" role="tablist" aria-label="${escapeHtml(t("onboard.welcome_title"))}">
      <button type="button" role="tab" data-onboard-mode="create" aria-selected="${mode === "create" ? "true" : "false"}" aria-pressed="${mode === "create" ? "true" : "false"}" ${dis}>${escapeHtml(t("onboard.tab_create"))}</button>
      <button type="button" role="tab" data-onboard-mode="upload" aria-selected="${mode === "upload" ? "true" : "false"}" aria-pressed="${mode === "upload" ? "true" : "false"}" ${dis}>${escapeHtml(t("onboard.tab_upload"))}</button>
      <button type="button" role="tab" data-onboard-mode="demo" aria-selected="${mode === "demo" ? "true" : "false"}" aria-pressed="${mode === "demo" ? "true" : "false"}" ${dis}>${escapeHtml(t("onboard.tab_demo"))}</button>
    </div>
    ${errBanner}
    ${bodyHtml}
  `;
}

function renderModelSetupStepHtml(): string {
  const cfg = state.modelConfig ?? state.sidecar.model_config ?? null;
  const activeName =
    state.knowledge.profile?.active_profile?.name ||
    state.knowledge.profile?.active_profile_id ||
    "profile";
  const tab = state.onboardingModelTab;
  const providers = getCloudProvidersForOnboarding();
  const selectedProv =
    providers.find((p) => p.id === state.onboardingCloudProviderId) ??
    providers[0];
  const presets = getLocalPresetsForOnboarding();
  const selectedPreset =
    presets.find((p) => p.repo_id === state.onboardingLocalRepoId) ?? presets[0];

  const lm = cfg?.local_models ?? null;
  const gemmaReady = Boolean(lm?.gemma_ready);
  const readyCustom = (lm?.custom_llms ?? []).filter((m) => Boolean(m.ready));
  const localReadyLabel = gemmaReady
    ? "gemma-4-e4b"
    : readyCustom[0]?.label || readyCustom[0]?.id || "";
  const downloads =
    state.hfDownloads.length > 0
      ? state.hfDownloads
      : (lm?.downloads ?? []);
  const hasActiveDownload = downloads.some(
    (d) => d.state === "queued" || d.state === "downloading"
  );
  const hasModelConfigured = hasAnyGenerativeModelConfigured(cfg);
  const activeRoleChat = cfg?.roles?.chat ?? state.selectedModel;

  let tabBodyHtml = "";
  if (tab === "cloud") {
    const models = selectedProv?.models ?? [];
    const envKey =
      selectedProv?.env_key ?? `${(selectedProv?.id ?? "cloud").toUpperCase()}_API_KEY`;
    const keyVal = onboardingCloudKeyDraft || selectedProv?.stored_key || "";
    const dis = onboardingCloudConnecting ? "disabled" : "";
    tabBodyHtml = `
      <div class="section onboard-pane">
        <div class="muted">${escapeHtml(t("onboard.cloud_desc"))}</div>
        <div class="form-row">
          <div class="kb-form-field">
            <label for="onboard-cloud-provider-select">${escapeHtml(t("onboard.cloud_provider_label"))}</label>
            <select id="onboard-cloud-provider-select" class="select" ${dis}>
              ${providers
                .map(
                  (p) =>
                    `<option value="${escapeHtml(p.id)}" ${p.id === selectedProv?.id ? "selected" : ""}>${escapeHtml(p.label)}</option>`
                )
                .join("")}
            </select>
          </div>
        </div>
        ${
          selectedProv?.privacy_disclosure
            ? `<div class="muted onboard-disclosure">${escapeHtml(selectedProv.privacy_disclosure)}</div>`
            : ""
        }
        <div class="form-row">
          <input
            id="onboard-cloud-key-input"
            class="input"
            type="password"
            spellcheck="false"
            autocorrect="off"
            autocapitalize="off"
            value="${escapeHtml(keyVal)}"
            placeholder="${escapeHtml(t("settings.paste_key_ph", { envKey, hint: selectedProv?.placeholder ?? "api key" }))}"
            ${dis}
          />
          <button id="onboard-cloud-vis-btn" type="button" class="btn" ${dis}>${escapeHtml(t("settings.show_key"))}</button>
          <button id="onboard-cloud-connect-btn" type="button" class="btn primary" ${dis}>
            ${onboardingCloudConnecting ? `<span class="satz-spinner" aria-hidden="true"></span>` : ""}
            <span>${escapeHtml(onboardingCloudConnecting ? t("onboard.cloud_connecting") : t("onboard.cloud_connect_btn"))}</span>
          </button>
        </div>
        ${
          selectedProv?.configured && models.length > 0
            ? `
              <div class="form-row">
                <span class="badge good">${escapeHtml(t("onboard.cloud_connected_badge", { count: models.length }))}</span>
                <label class="muted" for="onboard-cloud-model-select">${escapeHtml(t("onboard.cloud_active_model_label"))}</label>
                <select id="onboard-cloud-model-select" class="select">
                  ${models
                    .map(
                      (m) =>
                        `<option value="${escapeHtml(m.id)}" ${activeRoleChat === m.id ? "selected" : ""}>${escapeHtml(m.label || m.slug)}</option>`
                    )
                    .join("")}
                </select>
              </div>
            `
            : ""
        }
      </div>
    `;
  } else {
    tabBodyHtml = `
      <div class="section onboard-pane">
        <div class="muted">${escapeHtml(t("onboard.local_desc"))}</div>
        ${
          localReadyLabel
            ? `<div><span class="badge good">${escapeHtml(t("onboard.local_ready_badge", { model: localReadyLabel }))}</span></div>`
            : ""
        }
        <div class="kb-form-field">
          <label for="onboard-local-repo-select">${escapeHtml(t("onboard.local_pick_label"))}</label>
          <select id="onboard-local-repo-select" class="select">
            ${presets
              .map(
                (p) =>
                  `<option value="${escapeHtml(p.repo_id)}" ${p.repo_id === selectedPreset?.repo_id ? "selected" : ""}>${escapeHtml(p.label)} (${escapeHtml(p.approx_size)}${p.gated ? " · gated" : ""})</option>`
              )
              .join("")}
          </select>
        </div>
        ${
          selectedPreset?.notes
            ? `<div class="muted">${escapeHtml(selectedPreset.notes)}</div>`
            : ""
        }
        ${
          selectedPreset?.gated
            ? `
              <div class="banner warn">${escapeHtml(t("onboard.local_hf_gated_note"))}</div>
              <div class="form-row">
                <input
                  id="onboard-hf-token-input"
                  class="input"
                  type="password"
                  spellcheck="false"
                  autocorrect="off"
                  autocapitalize="off"
                  value="${escapeHtml(onboardingHfTokenDraft)}"
                  placeholder="${escapeHtml(t("settings.lm_hf_token_ph"))}"
                />
              </div>
            `
            : ""
        }
        <div class="onboard-actions-row">
          <button id="onboard-local-download-btn" type="button" class="btn primary">
            ${icon("upload", "ico-sm")}
            <span>${escapeHtml(t("onboard.local_download_btn"))}</span>
          </button>
          <button id="onboard-local-link-btn" type="button" class="btn">
            ${icon("folder", "ico-sm")}
            <span>${escapeHtml(t("onboard.local_link_existing_btn"))}</span>
          </button>
        </div>
        <div id="onboard-dl-slot">${renderOnboardingDownloadsHtml(downloads)}</div>
      </div>
    `;
  }

  const statusBanner = onboardingCloudError
    ? `<div class="banner danger">${escapeHtml(onboardingCloudError)}</div>`
    : state.modelConfigStatusMsg
      ? `<div class="banner ${state.modelConfigStatusMsg.toLowerCase().startsWith("error") ? "danger" : "warn"}">${escapeHtml(state.modelConfigStatusMsg)}</div>`
      : "";

  const finishLabel = hasModelConfigured
    ? t("onboard.models_continue_btn")
    : hasActiveDownload
      ? t("onboard.models_continue_dl_btn")
      : t("onboard.models_skip_btn");

  return `
    <div class="card-h">
      ${icon("spark", "ico-sm")}
      <b>${escapeHtml(t("onboard.models_title"))}</b>
      <span class="end badge soft">${escapeHtml(t("onboard.badge_step", { step: 2, total: 2 }))}</span>
    </div>
    <div class="muted">${escapeHtml(t("onboard.models_sub", { name: activeName }))}</div>
    <div class="seg onboard-mode-tabs" role="tablist" aria-label="${escapeHtml(t("onboard.models_title"))}">
      <button type="button" role="tab" data-onboard-model-tab="cloud" aria-selected="${tab === "cloud" ? "true" : "false"}" aria-pressed="${tab === "cloud" ? "true" : "false"}">${escapeHtml(t("onboard.models_tab_cloud"))}</button>
      <button type="button" role="tab" data-onboard-model-tab="local" aria-selected="${tab === "local" ? "true" : "false"}" aria-pressed="${tab === "local" ? "true" : "false"}">${escapeHtml(t("onboard.models_tab_local"))}</button>
    </div>
    ${statusBanner}
    ${tabBodyHtml}
    <div class="sep"></div>
    <div class="onboard-footer">
      ${
        hasModelConfigured || hasActiveDownload
          ? `<button id="onboard-models-skip-btn" type="button" class="btn-text">${escapeHtml(t("onboard.models_skip_btn"))}</button>`
          : `<span></span>`
      }
      <button id="onboard-models-finish-btn" type="button" class="btn ${hasModelConfigured || hasActiveDownload ? "primary" : ""}">
        <span>${escapeHtml(finishLabel)}</span>
      </button>
    </div>
  `;
}

export function renderOnboardingOverlay(actions: OnboardingActions): void {
  let overlay = document.getElementById("onboarding-overlay");
  const isUnlocked = Boolean(
    state.knowledge.profile?.unlocked && state.knowledge.profile?.active_profile
  );

  const shouldShow =
    state.profilePromptOpen &&
    state.onboardingStep !== null &&
    !(state.onboardingStep === "welcome" && isUnlocked);

  if (!shouldShow) {
    if (overlay) {
      overlay.remove();
    }
    return;
  }

  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "onboarding-overlay";
    overlay.className = "modal-backdrop";
    document.body.appendChild(overlay);
  } else {
    overlay.className = "modal-backdrop";
  }

  const innerHtml =
    state.onboardingStep === "models"
      ? renderModelSetupStepHtml()
      : renderWelcomeStepHtml();

  overlay.innerHTML = `
    <div id="onboarding-modal" class="card profile-modal onboard-modal" role="dialog" aria-modal="true">
      ${innerHtml}
    </div>
  `;

  if (state.onboardingStep === "welcome") {
    overlay
      .querySelectorAll<HTMLButtonElement>("[data-onboard-mode]")
      .forEach((btn) => {
        btn.addEventListener("click", () => {
          if (state.profileUnlocking) return;
          const m = btn.getAttribute("data-onboard-mode");
          if (m === "create" || m === "upload" || m === "demo") {
            state.onboardingMode = m;
            state.onboardingValidationMsg = "";
            state.profileStatusMessage = "";
            renderOnboardingOverlay(actions);
          }
        });
      });

    const nameEl = overlay.querySelector(
      "#onboard-create-name"
    ) as HTMLInputElement | null;
    const pinEl = overlay.querySelector(
      "#onboard-create-pin"
    ) as HTMLInputElement | null;
    nameEl?.addEventListener("input", () => {
      onboardingCreateNameDraft = nameEl.value;
    });

    const submitCreate = () => {
      if (state.profileUnlocking) return;
      const name = (nameEl?.value ?? onboardingCreateNameDraft).trim();
      const pin = (pinEl?.value ?? "").trim();
      if (!name) {
        state.onboardingValidationMsg = t("onboard.err_name_required");
        renderOnboardingOverlay(actions);
        (overlay?.querySelector("#onboard-create-name") as HTMLInputElement | null)?.focus();
        return;
      }
      if (!/^\d{6}$/.test(pin)) {
        state.onboardingValidationMsg = t("onboard.err_pin_6digits");
        renderOnboardingOverlay(actions);
        (overlay?.querySelector("#onboard-create-pin") as HTMLInputElement | null)?.focus();
        return;
      }
      state.onboardingValidationMsg = "";
      onboardingCreateNameDraft = "";
      void actions.onCreateProfile(name, pin);
    };

    overlay
      .querySelector("#onboard-create-submit-btn")
      ?.addEventListener("click", submitCreate);
    nameEl?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        pinEl?.focus();
      }
    });
    pinEl?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        submitCreate();
      }
    });

    if (state.onboardingMode === "create" && !state.profileUnlocking) {
      if (onboardingCreateNameDraft) {
        pinEl?.focus();
      } else {
        nameEl?.focus();
      }
    }

    if (state.onboardingMode === "upload") {
      bindProfileUploadSectionEvents(
        overlay,
        "onboard",
        actions.onImportProfileFile
      );
    }

    overlay
      .querySelector("#onboard-demo-start-btn")
      ?.addEventListener("click", () => {
        if (state.profileUnlocking) return;
        actions.onStartDemoMode();
      });
    return;
  }

  // Step 2: Model Setup bindings
  overlay
    .querySelectorAll<HTMLButtonElement>("[data-onboard-model-tab]")
    .forEach((btn) => {
      btn.addEventListener("click", () => {
        const nextTab = btn.getAttribute("data-onboard-model-tab");
        if (nextTab === "cloud" || nextTab === "local") {
          state.onboardingModelTab = nextTab;
          onboardingCloudError = "";
          renderOnboardingOverlay(actions);
        }
      });
    });

  const provSelect = overlay.querySelector(
    "#onboard-cloud-provider-select"
  ) as HTMLSelectElement | null;
  provSelect?.addEventListener("change", () => {
    state.onboardingCloudProviderId = provSelect.value;
    onboardingCloudKeyDraft = "";
    onboardingCloudError = "";
    renderOnboardingOverlay(actions);
  });

  const keyInput = overlay.querySelector(
    "#onboard-cloud-key-input"
  ) as HTMLInputElement | null;
  keyInput?.addEventListener("input", () => {
    onboardingCloudKeyDraft = keyInput.value;
  });

  overlay
    .querySelector("#onboard-cloud-vis-btn")
    ?.addEventListener("click", (e) => {
      if (!keyInput) return;
      const btn = e.currentTarget as HTMLButtonElement;
      if (keyInput.type === "password") {
        keyInput.type = "text";
        btn.textContent = t("settings.hide_key");
      } else {
        keyInput.type = "password";
        btn.textContent = t("settings.show_key");
      }
    });

  const submitCloudKey = async () => {
    if (onboardingCloudConnecting) return;
    const pid = provSelect?.value || state.onboardingCloudProviderId || "gemini";
    const keyVal = (keyInput?.value ?? onboardingCloudKeyDraft).trim();
    if (!keyVal) return;
    onboardingCloudConnecting = true;
    onboardingCloudError = "";
    renderOnboardingOverlay(actions);
    try {
      const res = await actions.onSaveCloudModelKey(pid, keyVal);
      if (!res.ok) {
        onboardingCloudError = `${t("common.error_prefix")} ${res.error || t("main.model_cfg_err")}`;
      } else {
        onboardingCloudKeyDraft = "";
      }
    } finally {
      onboardingCloudConnecting = false;
      renderOnboardingOverlay(actions);
    }
  };

  overlay
    .querySelector("#onboard-cloud-connect-btn")
    ?.addEventListener("click", () => {
      void submitCloudKey();
    });
  keyInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      void submitCloudKey();
    }
  });

  const cloudModelSelect = overlay.querySelector(
    "#onboard-cloud-model-select"
  ) as HTMLSelectElement | null;
  cloudModelSelect?.addEventListener("change", () => {
    if (cloudModelSelect.value) {
      void actions.onSelectChatModel(cloudModelSelect.value);
    }
  });

  const repoSelect = overlay.querySelector(
    "#onboard-local-repo-select"
  ) as HTMLSelectElement | null;
  repoSelect?.addEventListener("change", () => {
    state.onboardingLocalRepoId = repoSelect.value;
    renderOnboardingOverlay(actions);
  });

  const hfTokInput = overlay.querySelector(
    "#onboard-hf-token-input"
  ) as HTMLInputElement | null;
  hfTokInput?.addEventListener("input", () => {
    onboardingHfTokenDraft = hfTokInput.value;
  });

  overlay
    .querySelector("#onboard-local-download-btn")
    ?.addEventListener("click", () => {
      const repoId = repoSelect?.value || state.onboardingLocalRepoId;
      const tok = (hfTokInput?.value ?? onboardingHfTokenDraft).trim();
      void actions.onStartHfDownload({
        repo_id: repoId,
        token: tok,
        use_as_chat: true,
      });
    });

  overlay
    .querySelector("#onboard-local-link-btn")
    ?.addEventListener("click", () => {
      void actions.onLinkExistingLocalFolder();
    });

  updateOnboardingDownloadsInPlace(actions);

  const finishSetup = () => {
    onboardingCloudKeyDraft = "";
    onboardingHfTokenDraft = "";
    onboardingCloudError = "";
    actions.onFinishModelSetup();
  };

  overlay
    .querySelector("#onboard-models-finish-btn")
    ?.addEventListener("click", finishSetup);
  overlay
    .querySelector("#onboard-models-skip-btn")
    ?.addEventListener("click", finishSetup);
}

function clearTourHighlights(): void {
  document
    .querySelectorAll(".onboard-anchor-active")
    .forEach((el) => el.classList.remove("onboard-anchor-active"));
}

export function renderOnboardingTourPopover(
  actions: Pick<OnboardingActions, "onSetTourStep" | "onRenderRail">
): void {
  const existing = document.getElementById("onboard-tour-popover");
  clearTourHighlights();

  const stepIdx = state.onboardingTourStep;
  const blockedByOverlay =
    state.profilePromptOpen ||
    state.postUnlockLoading ||
    state.commandBarOpen ||
    state.mailComposeModalOpen ||
    state.showKnowledgeView ||
    state.showBrainView;

  if (stepIdx === null || stepIdx < 0 || stepIdx >= TOUR_STEPS.length || blockedByOverlay) {
    existing?.remove();
    return;
  }

  const step = TOUR_STEPS[stepIdx];
  if (step.accKey && !state.railAccordion[step.accKey]) {
    state.railAccordion[step.accKey] = true;
    setRailAccordionPref(state.railAccordion);
    actions.onRenderRail?.();
  }

  const anchorEl = document.querySelector(
    step.anchorSelector
  ) as HTMLElement | null;
  if (!anchorEl) {
    existing?.remove();
    return;
  }

  anchorEl.scrollIntoView({ block: "nearest" });
  anchorEl.classList.add("onboard-anchor-active");

  const pop = existing ?? document.createElement("div");
  pop.id = "onboard-tour-popover";
  pop.className = "onboard-tour-popover glass";
  pop.setAttribute("role", "dialog");
  pop.setAttribute("aria-label", t(step.titleKey));
  if (!existing) {
    document.body.appendChild(pop);
  }

  const isLast = stepIdx === TOUR_STEPS.length - 1;
  pop.innerHTML = `
    <div class="onboard-tour-arrow" aria-hidden="true"></div>
    <div class="onboard-tour-head">
      <b>${escapeHtml(t(step.titleKey))}</b>
      <span class="badge soft end">${escapeHtml(t("onboard.tour_counter", { step: stepIdx + 1, total: TOUR_STEPS.length }))}</span>
    </div>
    <p class="onboard-tour-body">${escapeHtml(t(step.bodyKey, { mod: MOD_LABEL.toUpperCase() }))}</p>
    <div class="onboard-tour-foot">
      <button id="onboard-tour-skip-btn" type="button" class="btn-text">${escapeHtml(t("onboard.tour_skip"))}</button>
      <div class="end onboard-tour-nav">
        ${
          stepIdx > 0
            ? `<button id="onboard-tour-prev-btn" type="button" class="btn sm">${escapeHtml(t("onboard.tour_back"))}</button>`
            : ""
        }
        <button id="onboard-tour-next-btn" type="button" class="btn primary sm">${escapeHtml(isLast ? t("onboard.tour_done") : t("onboard.tour_next"))}</button>
      </div>
    </div>
  `;

  // Position beside the left rail anchor (mirrored cleanly in RTL)
  const rect = anchorEl.getBoundingClientRect();
  const railRect = document
    .getElementById("region-rail")
    ?.getBoundingClientRect();
  const popRect = pop.getBoundingClientRect();
  const popW = popRect.width || 310;
  const popH = popRect.height || 170;
  const isRtl = document.documentElement.dir === "rtl";

  let left = isRtl
    ? Math.max(12, (railRect ? railRect.left : rect.left) - popW - 12)
    : Math.min(
        window.innerWidth - popW - 12,
        (railRect ? railRect.right : rect.right) + 12
      );
  left = Math.max(12, Math.min(left, window.innerWidth - popW - 12));

  const anchorCenterY = rect.top + rect.height / 2;
  const idealTop = anchorCenterY - 34;
  const top = Math.max(12, Math.min(idealTop, window.innerHeight - popH - 12));

  pop.style.left = `${Math.round(left)}px`;
  pop.style.top = `${Math.round(top)}px`;
  pop.classList.toggle("rtl", isRtl);

  const arrow = pop.querySelector(".onboard-tour-arrow") as HTMLElement | null;
  if (arrow) {
    const arrowOffset = Math.max(18, Math.min(popH - 22, anchorCenterY - top - 6));
    arrow.style.top = `${Math.round(arrowOffset)}px`;
  }

  pop
    .querySelector("#onboard-tour-skip-btn")
    ?.addEventListener("click", () => {
      actions.onSetTourStep(null);
    });
  pop
    .querySelector("#onboard-tour-prev-btn")
    ?.addEventListener("click", () => {
      actions.onSetTourStep(Math.max(0, stepIdx - 1));
    });
  pop
    .querySelector("#onboard-tour-next-btn")
    ?.addEventListener("click", () => {
      actions.onSetTourStep(isLast ? null : stepIdx + 1);
    });
}
