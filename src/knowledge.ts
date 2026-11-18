import { icon } from "./design-system/icons";
import {
  bindMailAccountsEvents,
  renderMailAccountsSectionHtml,
} from "./mail";
import {
  escapeHtml,
  formatRelativeTime,
  getUiLayoutPref,
  getUiThemePref,
  IS_MAC,
  MOD_LABEL,
  setUiLayoutPref,
  setUiThemePref,
  state,
  type UiLayoutPref,
  type UiThemePref,
} from "./state";
import type { BrainEntityItem, CloudProviderInfo } from "./types";

export interface KnowledgeActions {
  onChangeAppearance?: () => void;
  onTogglePauseLearning: (paused: boolean) => void;
  onDeletePassage: (passageId: string) => void;
  onDeleteBrainEntity?: (slug: string) => void;
  onSetDomainTrust?: (domain: string, personalScore: number | null) => void;
  onSearchBrain?: (query: string) => void;
  onOpenSourceUrl?: (url: string, title?: string) => void;
  onSwitchToBrain?: () => void;
  onSwitchToSettings?: () => void;
  onCreateProfile?: (name: string, pin: string) => void;
  onUnlockProfile?: (profileId: string, pin: string) => void;
  onUnlockProfileKeychain?: (profileId: string) => void;
  onLockProfile?: () => void;
  onDeleteProfile?: (profileId: string, pin: string) => void;
  onUpsertPassword?: (payload: {
    service: string;
    username: string;
    password?: string;
    token?: string;
    cookie?: string;
    url?: string;
  }) => void;
  onSaveRawEnv?: (rawEnv: string) => void;
  onImportEnvFile?: (path: string) => void;
  onDeletePassword?: (service: string) => void;
  onRevealPassword?: (service: string, field: string, pin: string) => void;
  onAutofillActiveTab?: () => void;
  onMailChanged?: () => Promise<void>;
  onSaveModelConfig?: (payload: Record<string, unknown>) => Promise<void>;
  onCloseKnowledgeView: () => void;
}

let brainSearchDebounceTimer: ReturnType<typeof setTimeout> | null = null;

export function renderKnowledgeView(
  container: HTMLElement,
  actions: KnowledgeActions
): void {
  const kb = state.knowledge;
  const brainEntities = kb.brain?.entities ?? [];
  const brainRankingLabel =
    kb.brain?.brain_ranking ??
    kb.brain?.encoder?.label ??
    "brain ranking: lexical (planck13 missing)";
  const bookmarksIndexed = kb.bookmarks_indexed ?? [];
  const profileInfo = kb.profile;
  const profilesList = profileInfo?.profiles ?? [];
  const isUnlocked = Boolean(profileInfo?.unlocked && profileInfo?.active_profile);
  const activeProfile = profileInfo?.active_profile ?? null;
  const vault = kb.vault;
  const vaultServices = vault?.services ?? [];
  const doctorRoles = state.doctorRoles ?? [];
  const acc = state.settingsAccordionOpen;
  const modelCfg = state.modelConfig ?? state.sidecar.model_config ?? null;
  const fallbackProviders: CloudProviderInfo[] = [
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
      privacy_disclosure:
        "Opt-in cloud provider: only active when a (cloud) model is selected. Sends prompt + checked source passages to generativelanguage.googleapis.com over HTTPS. Vault secrets and raw mail databases never leave your machine.",
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
      privacy_disclosure:
        "Opt-in cloud provider: only active when a (cloud) model is selected. Sends prompt + checked source passages to api.anthropic.com over HTTPS. Vault secrets and raw mail databases never leave your machine.",
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
      privacy_disclosure:
        "Opt-in cloud provider: only active when a (cloud) model is selected. Sends prompt + checked source passages to api.openai.com over HTTPS. Vault secrets and raw mail databases never leave your machine.",
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
      privacy_disclosure:
        "Opt-in cloud provider: only active when a (cloud) model is selected. Sends prompt + checked source passages to api.mistral.ai over HTTPS. Vault secrets and raw mail databases never leave your machine.",
    },
  ];
  const cloudProviders: CloudProviderInfo[] =
    modelCfg?.cloud_providers && modelCfg.cloud_providers.length > 0
      ? modelCfg.cloud_providers
      : fallbackProviders;
  const configuredCloudProviders = cloudProviders.filter(
    (p) => p.configured || (p.models && p.models.length > 0)
  );
  const discoveredCloudModels = cloudProviders.flatMap((p) => p.models ?? []);
  const roleChat = modelCfg?.roles?.chat ?? state.selectedModel ?? "gemma-4-e4b";
  const roleWeb = modelCfg?.roles?.web_answer ?? "planck3 (web)";
  const roleReader = modelCfg?.roles?.reader ?? "hertz (reader)";
  const roleNewsPlanner = modelCfg?.roles?.news_planner ?? "gemma-4-e4b";
  const roleNewsCapture = modelCfg?.roles?.news_capture ?? "gemma-4-e4b";
  const roleNewsReader = modelCfg?.roles?.news_reader ?? "hertz (reader)";
  const roleNewsAnalyzer = modelCfg?.roles?.news_analyzer ?? roleChat;
  const cloudSummaryBadge =
    configuredCloudProviders.length > 0
      ? `Cloud: ${configuredCloudProviders.map((p) => `${p.id} (${(p.models ?? []).length})`).join(" · ")}`
      : "Local only · 0 cloud providers";

  const renderBanner = (msg: string): string => {
    const low = msg.toLowerCase();
    const cls = low.includes("error") || low.includes("failed") ? "banner danger" : "banner";
    return `<div class="${cls}">${escapeHtml(msg)}</div>`;
  };

  const renderCloudOptionsHtml = (selectedRoleVal: string) =>
    discoveredCloudModels
      .map(
        (cm) =>
          `<option value="${escapeHtml(cm.id)}" ${selectedRoleVal === cm.id ? "selected" : ""}>${escapeHtml(cm.id)}</option>`
      )
      .join("");

  const doctorSectionHtml = `
      <div class="card kb-acc-card acc ${acc.models ? "open" : ""}">
        <div class="settings-acc-bar">
          <button type="button" class="acc-h" data-settings-accordion="models">
            <span>1. Model management &amp; cloud setup</span>
            <span class="ct">${escapeHtml(cloudSummaryBadge)}</span>
            ${icon("chev", "ico-sm")}
          </button>
        </div>
        ${
          !acc.models
            ? ""
            : `
          <div class="acc-b section">
            <div class="card inset">
              <div class="card-h">
                <b>Role routing matrix</b>
                <span class="end muted">Mail classifier &amp; Brain encoder stay 100% local</span>
              </div>
              <div class="form-row">
                <div class="kb-form-field">
                  <label for="kb-role-chat-select">Chat &amp; synthesis</label>
                  <select id="kb-role-chat-select" class="select">
                    <option value="gemma-4-e4b" ${roleChat === "gemma-4-e4b" ? "selected" : ""}>gemma-4-e4b (local · default)</option>
                    ${renderCloudOptionsHtml(roleChat)}
                  </select>
                </div>
                <div class="kb-form-field">
                  <label for="kb-role-web-select">Web answer</label>
                  <select id="kb-role-web-select" class="select">
                    <option value="planck3 (web)" ${roleWeb === "planck3 (web)" ? "selected" : ""}>planck3 (local read→weigh→write)</option>
                    ${renderCloudOptionsHtml(roleWeb)}
                  </select>
                </div>
                <div class="kb-form-field">
                  <label for="kb-role-reader-select">Page reader</label>
                  <select id="kb-role-reader-select" class="select">
                    <option value="hertz (reader)" ${roleReader === "hertz (reader)" ? "selected" : ""}>hertz 1.2 (local extractive)</option>
                    <option value="planck (reader)" ${roleReader === "planck (reader)" ? "selected" : ""}>planck (local extractive)</option>
                    <option value="gemma-4-e4b" ${roleReader === "gemma-4-e4b" ? "selected" : ""}>gemma-4-e4b (local generative)</option>
                    ${renderCloudOptionsHtml(roleReader)}
                  </select>
                </div>
              </div>
              <div class="form-row">
                <div class="kb-form-field">
                  <label for="kb-role-news-planner-select">News planner</label>
                  <select id="kb-role-news-planner-select" class="select">
                    <option value="gemma-4-e4b" ${roleNewsPlanner === "gemma-4-e4b" ? "selected" : ""}>gemma-4-e4b (local · default)</option>
                    ${renderCloudOptionsHtml(roleNewsPlanner)}
                  </select>
                </div>
                <div class="kb-form-field">
                  <label for="kb-role-news-capture-select">News translate</label>
                  <select id="kb-role-news-capture-select" class="select">
                    <option value="gemma-4-e4b" ${roleNewsCapture === "gemma-4-e4b" ? "selected" : ""}>gemma-4-e4b (local · default)</option>
                    ${renderCloudOptionsHtml(roleNewsCapture)}
                  </select>
                </div>
                <div class="kb-form-field">
                  <label for="kb-role-news-reader-select">News reader (trust-blind)</label>
                  <select id="kb-role-news-reader-select" class="select">
                    <option value="hertz (reader)" ${roleNewsReader === "hertz (reader)" ? "selected" : ""}>hertz 1.2 (local int8)</option>
                    <option value="planck (reader)" ${roleNewsReader === "planck (reader)" ? "selected" : ""}>planck (local reader)</option>
                    <option value="heuristic" ${roleNewsReader === "heuristic" ? "selected" : ""}>heuristic lexical</option>
                    <option value="gemma-4-e4b" ${roleNewsReader === "gemma-4-e4b" ? "selected" : ""}>gemma-4-e4b (local)</option>
                    ${renderCloudOptionsHtml(roleNewsReader)}
                  </select>
                </div>
                <div class="kb-form-field">
                  <label for="kb-role-news-analyzer-select">News analyzer</label>
                  <select id="kb-role-news-analyzer-select" class="select">
                    <option value="gemma-4-e4b" ${roleNewsAnalyzer === "gemma-4-e4b" ? "selected" : ""}>gemma-4-e4b (local)</option>
                    <option value="template" ${roleNewsAnalyzer === "template" ? "selected" : ""}>template extractive</option>
                    ${renderCloudOptionsHtml(roleNewsAnalyzer)}
                  </select>
                </div>
                <button id="kb-save-roles-btn" type="button" class="btn primary">Apply role routing</button>
              </div>
            </div>

            ${state.modelConfigStatusMsg ? renderBanner(state.modelConfigStatusMsg) : ""}

            <div class="label">Cloud model providers (models discovered from /models)</div>
            ${cloudProviders
              .map((p) => {
                const envKey = p.env_key ?? `${p.id.toUpperCase()}_API_KEY`;
                const modelsList = p.models ?? [];
                const modelsCount = modelsList.length;
                const storedKey = p.stored_key ?? "";
                return `
                  <div class="card inset">
                    <div class="card-h">
                      <b>${escapeHtml(p.label)}</b>
                      <span class="muted">${escapeHtml(envKey)} · ${escapeHtml(p.host ?? "")}</span>
                      <span class="end badge ${p.configured ? "" : "soft"}">${
                        p.configured
                          ? `${escapeHtml(p.key_source ?? "vault")} · ${escapeHtml(p.masked_key || "***")} · ${modelsCount} models`
                          : "Not configured"
                      }</span>
                    </div>
                    <div class="muted">${escapeHtml(p.privacy_disclosure)}</div>
                    <div class="form-row">
                      <input
                        data-cloud-key-input="${escapeHtml(p.id)}"
                        class="input"
                        type="password"
                        spellcheck="false"
                        autocorrect="off"
                        autocapitalize="off"
                        value="${escapeHtml(storedKey)}"
                        placeholder="Paste ${escapeHtml(envKey)} (${escapeHtml(p.placeholder ?? "api key")})"
                      />
                      <button data-cloud-toggle-vis="${escapeHtml(p.id)}" type="button" class="btn">Show key</button>
                      <button data-cloud-save-key="${escapeHtml(p.id)}" type="button" class="btn primary">${p.configured ? "Update & pull models" : "Save & pull models"}</button>
                      <button data-cloud-refresh-models="${escapeHtml(p.id)}" type="button" class="btn">Refresh models</button>
                      ${
                        p.configured || storedKey
                          ? `<button data-cloud-clear-key="${escapeHtml(p.id)}" type="button" class="btn danger">Delete key</button>`
                          : ""
                      }
                    </div>
                    ${
                      modelsCount > 0
                        ? `
                          <div class="form-row">
                            <span class="muted">Discovered (${modelsCount})</span>
                            <select data-cloud-model-picker="${escapeHtml(p.id)}" class="select">
                              ${modelsList
                                .map(
                                  (m) =>
                                    `<option value="${escapeHtml(m.id)}" ${roleChat === m.id ? "selected" : ""}>${escapeHtml(m.label || m.slug)} · ${escapeHtml(m.id)}</option>`
                                )
                                .join("")}
                            </select>
                            <button data-cloud-use-model="${escapeHtml(p.id)}" type="button" class="btn">Use as chat model</button>
                          </div>
                        `
                        : `<div class="muted">${
                            p.configured
                              ? "0 models cached. Click Refresh models to query /models."
                              : "Paste your API key above and click Save & pull models to discover available models."
                          }</div>`
                    }
                  </div>
                `;
              })
              .join("")}

            <div class="label">Local on-device models (${doctorRoles.length || 5} roles)</div>
            ${
              doctorRoles.length === 0
                ? `<div class="muted">Models offline. Start sidecar to inspect checkpoints and device placement.</div>`
                : `<div>${doctorRoles
                    .map((dr) => {
                      const dotCls =
                        dr.state === "ready"
                          ? "dot"
                          : dr.state === "cpu_only"
                            ? "dot warn"
                            : "dot danger";
                      const stateText =
                        dr.state === "ready"
                          ? `Ready · ${escapeHtml(dr.device)}`
                          : dr.state === "cpu_only"
                            ? `CPU only · ${escapeHtml(dr.device)}`
                            : "Missing";
                      return `
                        <div class="source-row">
                          <div class="source-row-top">
                            <b class="t">${escapeHtml(dr.role)} · <span class="muted">${escapeHtml(dr.model)}</span></b>
                            <span class="status"><span class="${dotCls}"></span><span>${stateText}</span></span>
                          </div>
                          ${
                            dr.fix
                              ? `<div class="source-row-meta">Fix: ${escapeHtml(dr.fix)}</div>`
                              : dr.path
                                ? `<div class="source-row-meta">${escapeHtml(dr.path)}</div>`
                                : ""
                          }
                        </div>
                      `;
                    })
                    .join("")}</div>`
            }
          </div>
        `
        }
      </div>
  `;

  container.innerHTML = `
    <div class="kb-page">
      <div class="kb-page-inner">
        <div class="view-h">
          <div>
            <h1>Settings</h1>
            <p>${
              isUnlocked && activeProfile
                ? `Profile ${escapeHtml(activeProfile.name)} unlocked · ${brainEntities.length} brain entities · ${bookmarksIndexed.length} indexed bookmarks · ${escapeHtml(brainRankingLabel)}`
                : `No active profile · ${escapeHtml(brainRankingLabel)} · queue ${kb.queue_len}`
            }</p>
          </div>
          <div class="end kb-head-actions">
            <button id="kb-expand-all-btn" type="button" class="btn">Expand all</button>
            <button id="kb-collapse-all-btn" type="button" class="btn">Collapse all</button>
            <button id="kb-open-brain-btn" type="button" class="btn">Brain (${escapeHtml(MOD_LABEL)}+B)</button>
            <button id="kb-pause-btn" type="button" class="btn" aria-pressed="${kb.pause_learning ? "true" : "false"}">
              Pause learning: ${kb.pause_learning ? "On" : "Off"}
            </button>
            <button id="kb-close-btn" type="button" class="icon-btn" title="Close settings">${icon("x", "ico-sm")}</button>
          </div>
        </div>

        <div class="card">
          <div class="card-h">
            <b>Appearance</b>
            <span class="end muted">Stored locally in browser preferences</span>
          </div>
          <div class="form-row">
            <span class="muted">Theme</span>
            <div class="seg" role="group" aria-label="Theme">
              <button type="button" data-ui-theme="system" aria-pressed="${getUiThemePref() === "system"}">System</button>
              <button type="button" data-ui-theme="light" aria-pressed="${getUiThemePref() === "light"}">Light</button>
              <button type="button" data-ui-theme="dark" aria-pressed="${getUiThemePref() === "dark"}">Dark</button>
            </div>
            <span class="muted">Layout</span>
            <div class="seg" role="group" aria-label="Layout">
              <button type="button" data-ui-layout="floating" aria-pressed="${getUiLayoutPref() === "floating"}">Floating</button>
              <button type="button" data-ui-layout="flush" aria-pressed="${getUiLayoutPref() === "flush"}">Flush</button>
            </div>
          </div>
        </div>

        ${state.profileStatusMessage ? renderBanner(state.profileStatusMessage) : ""}

        ${doctorSectionHtml}

        <div class="card kb-acc-card acc ${acc.profiles ? "open" : ""}">
          <div class="settings-acc-bar">
            <button type="button" class="acc-h" data-settings-accordion="profiles">
              <span>2. User profiles &amp; security</span>
              <span class="ct">${profilesList.length}</span>
              ${icon("chev", "ico-sm")}
            </button>
            ${
              isUnlocked
                ? `<button id="kb-lock-profile-btn" type="button" class="btn">Lock active profile</button>`
                : `<span class="badge soft">Locked</span>`
            }
          </div>
          ${
            !acc.profiles
              ? ""
              : `
          <div class="acc-b section">
            <div class="form-row">
              <input
                id="kb-new-profile-name"
                class="input"
                type="text"
                spellcheck="false"
                autocorrect="off"
                autocapitalize="off"
                placeholder="Profile name (e.g. Nikita)"
              />
              <input
                id="kb-new-profile-pin"
                class="input pin"
                type="password"
                inputmode="numeric"
                maxlength="6"
                spellcheck="false"
                autocorrect="off"
                autocapitalize="off"
                placeholder="6-digit PIN"
              />
              <button id="kb-create-profile-btn" type="button" class="btn primary">${icon("plus", "ico-sm")}<span>Create profile</span></button>
            </div>
            ${
              profilesList.length === 0
                ? `<div class="muted">No profiles created yet. Create one with a 6-digit PIN above.</div>`
                : profilesList
                    .map(
                      (p) => `
                  <div class="source-row">
                    <div class="source-row-top">
                      <span class="t">
                        ${p.is_active ? `<span class="dot"></span> ` : ""}
                        <b>${escapeHtml(p.name)}</b>
                        <span class="muted">(${escapeHtml(p.id)} · ${p.credential_services_count} vault services)</span>
                      </span>
                      ${
                        p.is_active
                          ? `<span class="badge">Unlocked</span>`
                          : `
                        <input
                          class="input pin"
                          type="password"
                          inputmode="numeric"
                          maxlength="6"
                          spellcheck="false"
                          autocorrect="off"
                          autocapitalize="off"
                          placeholder="PIN"
                          data-profile-pin-input="${escapeHtml(p.id)}"
                        />
                        <button type="button" class="btn primary" data-unlock-profile="${escapeHtml(p.id)}">Unlock</button>
                        ${
                          IS_MAC
                            ? `<button type="button" class="btn" data-unlock-touchid="${escapeHtml(p.id)}">Touch ID</button>`
                            : ""
                        }
                      `
                      }
                      <button type="button" class="btn-text" data-delete-profile="${escapeHtml(p.id)}" title="Enter 6-digit PIN to delete profile">Delete</button>
                    </div>
                  </div>
                `
                    )
                    .join("")
            }
          </div>
          `
          }
        </div>

        <div class="card kb-acc-card acc ${acc.vault ? "open" : ""}">
          <div class="settings-acc-bar">
            <button type="button" class="acc-h" data-settings-accordion="vault">
              <span>3. Profile .env password vault</span>
              <span class="ct">${isUnlocked ? `${vaultServices.length} services` : "locked"}</span>
              ${icon("chev", "ico-sm")}
            </button>
            ${
              isUnlocked && state.activeDetail?.tabs.some((t) => t.is_open)
                ? `<button id="kb-autofill-tab-btn" type="button" class="btn" title="Auto-fill & login on open tab using active profile .env credentials">Auto-fill open tab</button>`
                : `<span class="muted">AES-256-GCM + Argon2id</span>`
            }
          </div>
          ${
            !acc.vault
              ? ""
              : !isUnlocked
                ? `<div class="muted acc-b">Locked. Vault credentials (vault.enc), Mail (mail.sqlite), Satz Brain (BRAIN.md), and the passage store belong to an unlocked profile.</div>`
                : `
            <div class="acc-b section">
              <div class="muted">
                Vault file: ${escapeHtml(vault?.env_path ?? "")} · accessible only while profile "${escapeHtml(activeProfile?.name ?? "")}" is unlocked.
              </div>

              <div class="form-row">
                <input id="kb-cred-service" class="input" type="text" spellcheck="false" autocorrect="off" autocapitalize="off" placeholder="Service/domain (e.g. gmail.com)" />
                <input id="kb-cred-username" class="input" type="text" spellcheck="false" autocorrect="off" autocapitalize="off" placeholder="Username / email" />
                <input id="kb-cred-password" class="input" type="password" spellcheck="false" autocorrect="off" autocapitalize="off" placeholder="Password / app password" />
                <input id="kb-cred-token" class="input" type="password" spellcheck="false" autocorrect="off" autocapitalize="off" placeholder="Token or cookie (optional)" />
                <button id="kb-save-cred-btn" type="button" class="btn primary">Save to .env</button>
              </div>

              <div class="form-row">
                <input id="kb-import-env-path" class="input" type="text" spellcheck="false" autocorrect="off" autocapitalize="off" placeholder="Import .env file path (${IS_MAC ? "~/Downloads/.env" : "C:\\Users\\...\\.env"})" />
                <button id="kb-import-env-btn" type="button" class="btn">Import .env file</button>
                <input
                  id="kb-reveal-pin-input"
                  class="input pin"
                  type="password"
                  inputmode="numeric"
                  maxlength="6"
                  spellcheck="false"
                  autocorrect="off"
                  autocapitalize="off"
                  placeholder="PIN to reveal"
                />
              </div>

              ${
                vaultServices.length === 0
                  ? `<div class="muted">No credentials stored in this profile yet. Add a service above or paste/import a .env file below.</div>`
                  : `<div>${vaultServices
                      .map((s) => {
                        const revPwd = state.revealedPasswords[`${s.service}:password`];
                        const revTok = state.revealedPasswords[`${s.service}:token`];
                        const revCook = state.revealedPasswords[`${s.service}:cookie`];
                        return `
                    <div class="kb-kv-row">
                      <span>
                        <b>${escapeHtml(s.service)}</b>
                        ${s.domain ? `<span class="muted">(${escapeHtml(s.domain)})</span>` : ""}
                        · user: ${escapeHtml(s.username || "(token/cookie)")}
                      </span>
                      <span class="news-src-checks">
                        ${
                          s.has_password
                            ? revPwd
                              ? `<span class="pill">Password: ${escapeHtml(revPwd)}</span>`
                              : `<button type="button" class="btn-text" data-reveal-service="${escapeHtml(s.service)}" data-reveal-field="password">Reveal password</button>`
                            : ""
                        }
                        ${
                          s.has_token
                            ? revTok
                              ? `<span class="pill">Token: ${escapeHtml(revTok)}</span>`
                              : `<button type="button" class="btn-text" data-reveal-service="${escapeHtml(s.service)}" data-reveal-field="token">Reveal token</button>`
                            : ""
                        }
                        ${
                          s.has_cookie
                            ? revCook
                              ? `<span class="pill">Cookie: ${escapeHtml(revCook)}</span>`
                              : `<button type="button" class="btn-text" data-reveal-service="${escapeHtml(s.service)}" data-reveal-field="cookie">Reveal cookie</button>`
                            : ""
                        }
                        <button type="button" class="btn-text" data-delete-cred="${escapeHtml(s.service)}">Delete</button>
                      </span>
                    </div>
                  `;
                      })
                      .join("")}</div>`
              }

              <div class="section">
                <div class="muted">Write-only .env batch importer for encrypted vault.enc (${escapeHtml(activeProfile?.name ?? "")})</div>
                <textarea id="kb-raw-env-textarea" class="textarea mono" rows="5" spellcheck="false" placeholder="Paste KEY=VALUE lines here to merge into encrypted vault.enc (write-only; secrets are never returned over HTTP)"></textarea>
                <div>
                  <button id="kb-save-raw-env-btn" type="button" class="btn">Merge into vault.enc</button>
                </div>
              </div>
            </div>
          `
          }
        </div>

        <div class="card kb-acc-card acc ${acc.mail ? "open" : ""}">
          <div class="settings-acc-bar">
            <button type="button" class="acc-h" data-settings-accordion="mail">
              <span>4. Mail accounts &amp; classifier eval</span>
              <span class="ct">${state.mailAccounts.length} accounts</span>
              ${icon("chev", "ico-sm")}
            </button>
            <span class="muted">IMAP / POP3 / SMTP</span>
          </div>
          ${!acc.mail ? "" : `<div class="acc-b">${renderMailAccountsSectionHtml()}</div>`}
        </div>

        <div class="card kb-acc-card acc ${acc.indexing ? "open" : ""}">
          <div class="settings-acc-bar">
            <button type="button" class="acc-h" data-settings-accordion="indexing">
              <span>5. Background indexing &amp; bookmarks</span>
              <span class="ct">${bookmarksIndexed.length}</span>
              ${icon("chev", "ico-sm")}
            </button>
            <span class="muted">30-min conditional fetch</span>
          </div>
          ${
            !acc.indexing
              ? ""
              : `
          <div class="acc-b section">
            <div class="muted">
              Bookmarked sources are continuously fetched, authenticated via unlocked profile vault credentials, and indexed in the background.
            </div>
            ${
              bookmarksIndexed.length === 0
                ? `<div class="muted">No bookmarks hooked up yet. Click Bookmark current in the sidebar to index a source.</div>`
                : bookmarksIndexed
                    .map(
                      (bm) => `
                  <div class="kb-kv-row">
                    <span class="truncate">${escapeHtml(bm.title || bm.domain)} <span class="muted">(${escapeHtml(bm.url)})</span></span>
                    <span class="muted">
                      <span class="badge soft">${escapeHtml(bm.status)}</span> · ${bm.text_chars} chars · ${
                        bm.last_indexed_at > 0
                          ? `updated ${escapeHtml(formatRelativeTime(String(Math.floor(bm.last_indexed_at))))}`
                          : "indexing..."
                      }
                    </span>
                  </div>
                `
                    )
                    .join("")
            }
          </div>
          `
          }
        </div>
      </div>
    </div>
  `;

  container.querySelectorAll("[data-ui-theme]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const val = btn.getAttribute("data-ui-theme") as UiThemePref | null;
      if (!val) return;
      setUiThemePref(val);
      actions.onChangeAppearance?.();
      renderKnowledgeView(container, actions);
    });
  });

  container.querySelectorAll("[data-ui-layout]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const val = btn.getAttribute("data-ui-layout") as UiLayoutPref | null;
      if (!val) return;
      setUiLayoutPref(val);
      actions.onChangeAppearance?.();
      renderKnowledgeView(container, actions);
    });
  });

  container.querySelectorAll("[data-settings-accordion]").forEach((hdr) => {
    hdr.addEventListener("click", () => {
      const key = (hdr as HTMLElement).getAttribute("data-settings-accordion") ?? "";
      if (key) {
        state.settingsAccordionOpen[key] = !state.settingsAccordionOpen[key];
        renderKnowledgeView(container, actions);
      }
    });
  });

  container.querySelector("#kb-expand-all-btn")?.addEventListener("click", () => {
    for (const k of ["models", "profiles", "vault", "mail", "indexing"]) {
      state.settingsAccordionOpen[k] = true;
    }
    renderKnowledgeView(container, actions);
  });

  container.querySelector("#kb-collapse-all-btn")?.addEventListener("click", () => {
    for (const k of ["models", "profiles", "vault", "mail", "indexing"]) {
      state.settingsAccordionOpen[k] = false;
    }
    renderKnowledgeView(container, actions);
  });

  container.querySelector("#kb-save-roles-btn")?.addEventListener("click", () => {
    if (!actions.onSaveModelConfig) return;
    const chatSel = (container.querySelector("#kb-role-chat-select") as HTMLSelectElement | null)?.value ?? "gemma-4-e4b";
    const webSel = (container.querySelector("#kb-role-web-select") as HTMLSelectElement | null)?.value ?? "planck3 (web)";
    const readerSel = (container.querySelector("#kb-role-reader-select") as HTMLSelectElement | null)?.value ?? "hertz (reader)";
    const npSel = (container.querySelector("#kb-role-news-planner-select") as HTMLSelectElement | null)?.value ?? "gemma-4-e4b";
    const ncSel = (container.querySelector("#kb-role-news-capture-select") as HTMLSelectElement | null)?.value ?? "gemma-4-e4b";
    const nrSel = (container.querySelector("#kb-role-news-reader-select") as HTMLSelectElement | null)?.value ?? "hertz (reader)";
    const naSel = (container.querySelector("#kb-role-news-analyzer-select") as HTMLSelectElement | null)?.value ?? chatSel;
    void actions.onSaveModelConfig({
      role_chat: chatSel,
      role_web_answer: webSel,
      role_reader: readerSel,
      role_news_planner: npSel,
      role_news_capture: ncSel,
      role_news_reader: nrSel,
      role_news_analyzer: naSel,
    });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-cloud-toggle-vis]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = btn.getAttribute("data-cloud-toggle-vis") ?? "";
      if (!pid) return;
      const inputEl = container.querySelector(
        `[data-cloud-key-input="${pid}"]`
      ) as HTMLInputElement | null;
      if (!inputEl) return;
      if (inputEl.type === "password") {
        inputEl.type = "text";
        btn.textContent = "Hide key";
      } else {
        inputEl.type = "password";
        btn.textContent = "Show key";
      }
    });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-cloud-use-model]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!actions.onSaveModelConfig) return;
      const pid = btn.getAttribute("data-cloud-use-model") ?? "";
      if (!pid) return;
      const selEl = container.querySelector(
        `[data-cloud-model-picker="${pid}"]`
      ) as HTMLSelectElement | null;
      const modelId = selEl?.value ?? "";
      if (!modelId) return;
      void actions.onSaveModelConfig({
        role_chat: modelId,
      });
    });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-cloud-save-key]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!actions.onSaveModelConfig) return;
      const pid = btn.getAttribute("data-cloud-save-key") ?? "";
      if (!pid) return;
      const inputEl = container.querySelector(
        `[data-cloud-key-input="${pid}"]`
      ) as HTMLInputElement | null;
      const keyVal = inputEl?.value.trim() ?? "";
      void actions.onSaveModelConfig({
        provider_id: pid,
        api_key: keyVal,
        refresh_models: true,
      });
    });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-cloud-refresh-models]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!actions.onSaveModelConfig) return;
      const pid = btn.getAttribute("data-cloud-refresh-models") ?? "";
      if (!pid) return;
      const inputEl = container.querySelector(
        `[data-cloud-key-input="${pid}"]`
      ) as HTMLInputElement | null;
      const keyVal = inputEl?.value.trim() ?? "";
      const payload: Record<string, unknown> = {
        provider_id: pid,
        refresh_models: true,
      };
      if (keyVal) {
        payload.api_key = keyVal;
      }
      void actions.onSaveModelConfig(payload);
    });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-cloud-clear-key]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!actions.onSaveModelConfig) return;
      const pid = btn.getAttribute("data-cloud-clear-key") ?? "";
      if (!pid) return;
      void actions.onSaveModelConfig({
        provider_id: pid,
        clear_key: true,
      });
    });
  });

  container.querySelector("#kb-open-brain-btn")?.addEventListener("click", () => {
    if (actions.onSwitchToBrain) {
      actions.onSwitchToBrain();
    }
  });

  container.querySelector("#kb-pause-btn")?.addEventListener("click", () => {
    actions.onTogglePauseLearning(!kb.pause_learning);
  });

  container.querySelector("#kb-close-btn")?.addEventListener("click", () => {
    actions.onCloseKnowledgeView();
  });

  container.querySelector("#kb-create-profile-btn")?.addEventListener("click", () => {
    const nameEl = container.querySelector("#kb-new-profile-name") as HTMLInputElement | null;
    const pinEl = container.querySelector("#kb-new-profile-pin") as HTMLInputElement | null;
    const name = nameEl?.value.trim() ?? "";
    const pin = pinEl?.value.trim() ?? "";
    if (actions.onCreateProfile) {
      actions.onCreateProfile(name, pin);
    }
  });

  container.querySelector("#kb-lock-profile-btn")?.addEventListener("click", () => {
    if (actions.onLockProfile) {
      actions.onLockProfile();
    }
  });

  container.querySelectorAll("[data-unlock-profile]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = (btn as HTMLElement).getAttribute("data-unlock-profile");
      if (!pid || !actions.onUnlockProfile) return;
      const pinInput = container.querySelector(
        `[data-profile-pin-input="${pid}"]`
      ) as HTMLInputElement | null;
      const pin = pinInput?.value.trim() ?? "";
      actions.onUnlockProfile(pid, pin);
    });
  });

  container.querySelectorAll("[data-profile-pin-input]").forEach((inp) => {
    inp.addEventListener("keydown", (e) => {
      if ((e as KeyboardEvent).key === "Enter") {
        e.preventDefault();
        const el = inp as HTMLInputElement;
        const pid = el.getAttribute("data-profile-pin-input");
        if (pid && actions.onUnlockProfile) {
          actions.onUnlockProfile(pid, el.value.trim());
        }
      }
    });
  });

  container.querySelectorAll("[data-unlock-touchid]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = (btn as HTMLElement).getAttribute("data-unlock-touchid");
      if (pid && actions.onUnlockProfileKeychain) {
        actions.onUnlockProfileKeychain(pid);
      }
    });
  });

  container.querySelectorAll("[data-delete-profile]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = (btn as HTMLElement).getAttribute("data-delete-profile");
      if (!pid || !actions.onDeleteProfile) return;
      const pinInput = container.querySelector(
        `[data-profile-pin-input="${pid}"]`
      ) as HTMLInputElement | null;
      const newPinInput = container.querySelector(
        "#kb-new-profile-pin"
      ) as HTMLInputElement | null;
      const pin = pinInput?.value.trim() || newPinInput?.value.trim() || "";
      actions.onDeleteProfile(pid, pin);
    });
  });

  container.querySelector("#kb-save-cred-btn")?.addEventListener("click", () => {
    if (!actions.onUpsertPassword) return;
    const srv = (container.querySelector("#kb-cred-service") as HTMLInputElement | null)?.value.trim() ?? "";
    const usr = (container.querySelector("#kb-cred-username") as HTMLInputElement | null)?.value.trim() ?? "";
    const pwd = (container.querySelector("#kb-cred-password") as HTMLInputElement | null)?.value.trim() ?? "";
    const tok = (container.querySelector("#kb-cred-token") as HTMLInputElement | null)?.value.trim() ?? "";
    if (!srv) return;
    actions.onUpsertPassword({
      service: srv,
      username: usr,
      password: pwd,
      token: tok,
      url: srv,
    });
  });

  container.querySelector("#kb-import-env-btn")?.addEventListener("click", () => {
    if (!actions.onImportEnvFile) return;
    const p = (container.querySelector("#kb-import-env-path") as HTMLInputElement | null)?.value.trim() ?? "";
    if (p) actions.onImportEnvFile(p);
  });

  container.querySelector("#kb-save-raw-env-btn")?.addEventListener("click", () => {
    if (!actions.onSaveRawEnv) return;
    const raw = (container.querySelector("#kb-raw-env-textarea") as HTMLTextAreaElement | null)?.value ?? "";
    actions.onSaveRawEnv(raw);
  });

  container.querySelector("#kb-autofill-tab-btn")?.addEventListener("click", () => {
    if (actions.onAutofillActiveTab) {
      actions.onAutofillActiveTab();
    }
  });

  container.querySelectorAll("[data-delete-cred]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const srv = (btn as HTMLElement).getAttribute("data-delete-cred");
      if (srv && actions.onDeletePassword) {
        actions.onDeletePassword(srv);
      }
    });
  });

  container.querySelectorAll("[data-reveal-service]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const srv = el.getAttribute("data-reveal-service") ?? "";
      const fld = el.getAttribute("data-reveal-field") ?? "password";
      const pinEl = container.querySelector(
        "#kb-reveal-pin-input"
      ) as HTMLInputElement | null;
      const pin = pinEl?.value.trim() ?? "";
      if (srv && actions.onRevealPassword) {
        actions.onRevealPassword(srv, fld, pin);
      }
    });
  });

  bindMailAccountsEvents(container, async () => {
    if (actions.onMailChanged) {
      await actions.onMailChanged();
    }
  });
}

function renderBrainEntityCardHtml(e: BrainEntityItem): string {
  const isHighlighted = state.highlightedBrainSlug === e.slug;
  const attrEntries = Object.entries(e.attributes ?? {})
    .filter(([k, v]) => k !== "source_url" && !k.startsWith("$") && v !== "" && v !== null && v !== undefined)
    .map(([k, v]) => `${k}: ${String(v)}`)
    .join(" · ");

  const rawSrc = String(
    e.source_url || (e.attributes?.source_url as string | undefined) || ""
  ).trim();
  const normalizedSrcUrl = rawSrc.startsWith("mail:")
    ? `satzmail://message/${rawSrc.slice(5).trim()}`
    : rawSrc;
  const sourceBtnHtml =
    normalizedSrcUrl &&
    (normalizedSrcUrl.startsWith("http://") ||
      normalizedSrcUrl.startsWith("https://") ||
      normalizedSrcUrl.startsWith("satzmail://"))
      ? `<button type="button" class="btn-text" data-brain-open-source="${escapeHtml(normalizedSrcUrl)}" data-brain-source-title="${escapeHtml(e.name)}">Source</button>`
      : "";

  return `
    <div
      class="source-row ${isHighlighted ? "on" : ""}"
      id="brain-card-${escapeHtml(e.slug)}"
      data-brain-card-slug="${escapeHtml(e.slug)}"
    >
      <div class="source-row-top">
        <span class="t">
          <span class="flag">${escapeHtml(e.type)}</span>
          <button type="button" class="btn-text pri" data-select-brain-slug="${escapeHtml(e.slug)}">${escapeHtml(e.name)}</button>
          <span class="muted">Tier ${e.tier} · ${escapeHtml(e.path)}</span>
        </span>
        ${sourceBtnHtml}
        <button type="button" class="btn-text" data-delete-brain-entity="${escapeHtml(e.slug)}">Forget</button>
      </div>
      <div>${escapeHtml(e.summary)}</div>
      ${attrEntries ? `<div class="source-row-meta">${escapeHtml(attrEntries)}</div>` : ""}
      ${
        isHighlighted && e.body
          ? `<div class="muted">${escapeHtml(e.body)}</div>`
          : ""
      }
    </div>
  `;
}

export function renderBrainView(
  container: HTMLElement,
  actions: KnowledgeActions
): void {
  const prevSearchInput = container.querySelector(
    "#brain-search-input"
  ) as HTMLInputElement | null;
  const wasFocused =
    prevSearchInput && document.activeElement === prevSearchInput;
  const selStart = prevSearchInput?.selectionStart ?? null;

  const kb = state.knowledge;
  const brainEntities = kb.brain?.entities ?? [];
  const brainRankingLabel =
    kb.brain?.brain_ranking ??
    kb.brain?.encoder?.label ??
    "Ranking: lexical (planck13 missing)";
  const profileInfo = kb.profile;
  const isUnlocked = Boolean(profileInfo?.unlocked && profileInfo?.active_profile);
  const activeProfile = profileInfo?.active_profile ?? null;
  const thisWeek = kb.this_week ?? [];
  const searchRes = state.brainSearchResults;
  const hasActiveSearch = Boolean(state.brainSearchQuery.trim() && searchRes);

  const typeOrder = [
    { key: "order", label: "Orders" },
    { key: "person", label: "People" },
    { key: "organization", label: "Organizations" },
    { key: "promotion", label: "Promotions" },
    { key: "place", label: "Places" },
    { key: "account", label: "Accounts" },
    { key: "note", label: "Notes" },
  ];

  const groupedEntities = new Map<string, BrainEntityItem[]>();
  for (const tg of typeOrder) {
    groupedEntities.set(tg.key, []);
  }
  const otherEntities: BrainEntityItem[] = [];
  for (const ent of brainEntities) {
    const tKey = (ent.type || "note").toLowerCase();
    if (groupedEntities.has(tKey)) {
      groupedEntities.get(tKey)!.push(ent);
    } else {
      otherEntities.push(ent);
    }
  }

  const entityGroupsHtml = !isUnlocked
    ? `<div class="muted">Unlock a profile to load and store Brain entities.</div>`
    : brainEntities.length === 0
      ? `<div class="muted">No Brain entities stored yet. Sync mail, browse authenticated tabs, or ask Chat to remember facts.</div>`
      : [
          ...typeOrder
            .filter((tg) => (groupedEntities.get(tg.key)?.length ?? 0) > 0)
            .map((tg) => {
              const items = groupedEntities.get(tg.key) ?? [];
              return `
                <div class="section">
                  <div class="label">${escapeHtml(tg.label)} <span class="ct">${items.length}</span></div>
                  ${items.map((item) => renderBrainEntityCardHtml(item)).join("")}
                </div>
              `;
            }),
          otherEntities.length > 0
            ? `
              <div class="section">
                <div class="label">Other <span class="ct">${otherEntities.length}</span></div>
                ${otherEntities.map((item) => renderBrainEntityCardHtml(item)).join("")}
              </div>
            `
            : "",
        ].join("");

  const searchResultsSectionHtml = hasActiveSearch && searchRes
    ? `
      <div class="card" id="brain-search-results-section">
        <div class="card-h">
          <b>Search results for "${escapeHtml(state.brainSearchQuery)}"</b>
          <span class="muted">${searchRes.entities.length} entities · ${searchRes.passages.length} passages · ${searchRes.mail.length} mail</span>
          <button id="brain-search-clear-btn" type="button" class="btn-text end">Clear</button>
        </div>
        ${
          searchRes.entities.length === 0 &&
          searchRes.passages.length === 0 &&
          searchRes.mail.length === 0
            ? `<div class="muted">No matches in entities, passages, or mail.</div>`
            : `
              ${
                searchRes.entities.length > 0
                  ? `
                    <div class="section">
                      <div class="label">Matching entities <span class="ct">${searchRes.entities.length}</span></div>
                      ${searchRes.entities.map((e) => renderBrainEntityCardHtml(e)).join("")}
                    </div>
                  `
                  : ""
              }
              ${
                searchRes.passages.length > 0
                  ? `
                    <div class="section">
                      <div class="label">Matching passages <span class="ct">${searchRes.passages.length}</span></div>
                      ${searchRes.passages
                        .map(
                          (p) => `
                            <div class="source-row">
                              <div class="source-row-top">
                                <button type="button" class="btn-text pri t" data-brain-open-source="${escapeHtml(p.url)}" data-brain-source-title="${escapeHtml(p.title || p.entity || p.url)}">
                                  ${escapeHtml(p.title || p.entity || p.url)}
                                </button>
                                <button type="button" class="btn-text" data-delete-passage="${escapeHtml(p.id)}">Forget</button>
                              </div>
                              <div class="source-row-meta">${escapeHtml(p.url)}</div>
                              <div>${escapeHtml(p.text.slice(0, 260))}</div>
                            </div>
                          `
                        )
                        .join("")}
                    </div>
                  `
                  : ""
              }
              ${
                searchRes.mail.length > 0
                  ? `
                    <div class="section">
                      <div class="label">Matching mail <span class="ct">${searchRes.mail.length}</span></div>
                      ${searchRes.mail
                        .map((m) => {
                          const mid = String(m.id ?? "");
                          const sender = String(m.from_name || m.from_addr || "");
                          const subj = String(m.subject ?? "(no subject)");
                          const snip = String(m.snippet ?? "");
                          return `
                            <div class="source-row">
                              <div class="source-row-top">
                                <button type="button" class="btn-text pri t" data-brain-open-source="satzmail://message/${escapeHtml(mid)}" data-brain-source-title="${escapeHtml(subj)}">
                                  ${escapeHtml(sender)} · ${escapeHtml(subj)}
                                </button>
                                <span class="badge soft">${escapeHtml(String(m.label ?? "email"))}</span>
                              </div>
                              <div class="muted">${escapeHtml(snip.slice(0, 200))}</div>
                            </div>
                          `;
                        })
                        .join("")}
                    </div>
                  `
                  : ""
              }
            `
        }
      </div>
    `
    : "";

  container.innerHTML = `
    <div class="kb-page" id="brain-view-root">
      <div class="kb-page-inner">
        <div class="view-h">
          <div>
            <h1>Satz Brain</h1>
            <p>${
              isUnlocked && activeProfile
                ? `Profile ${escapeHtml(activeProfile.name)} · ${escapeHtml(brainRankingLabel)} · ${escapeHtml(MOD_LABEL)}+B`
                : `Locked · ${escapeHtml(MOD_LABEL)}+B`
            }</p>
          </div>
          <div class="end kb-head-actions">
            <button id="brain-open-settings-btn" type="button" class="btn">${icon("settings", "ico-sm")}<span>Settings</span></button>
            <button id="brain-close-btn" type="button" class="icon-btn" title="Close Brain">${icon("x", "ico-sm")}</button>
          </div>
        </div>

        <div class="card">
          <div class="form-row">
            <div class="input-wrap">
              ${icon("search", "ico-sm")}
              <input
                id="brain-search-input"
                class="input"
                type="text"
                spellcheck="false"
                autocorrect="off"
                autocapitalize="off"
                placeholder="Search entities, passages, and mail (FTS5 + encoder rank)"
                value="${escapeHtml(state.brainSearchQuery)}"
              />
            </div>
            <button id="brain-search-btn" type="button" class="btn primary">Search</button>
            ${
              state.brainSearchQuery
                ? `<button id="brain-search-reset-btn" type="button" class="btn">Clear</button>`
                : ""
            }
          </div>
        </div>

        ${searchResultsSectionHtml}

        <div class="card">
          <div class="card-h">
            <b>Entity cards</b>
            <span class="badge soft">${brainEntities.length}</span>
            <span class="end muted">${escapeHtml(brainRankingLabel)}</span>
          </div>
          ${entityGroupsHtml}
        </div>

        <div class="card">
          <div class="card-h">
            <b>This week</b>
            <span class="badge soft">${thisWeek.length}</span>
            <span class="end muted">Pages read and mail received</span>
          </div>
          ${
            thisWeek.length === 0
              ? `<div class="muted">No pages read or emails received in the last 7 days.</div>`
              : thisWeek
                  .map((item) => {
                    const kindText = item.kind === "received" ? "Received" : "Read";
                    const rel = item.ts > 0 ? formatRelativeTime(String(Math.floor(item.ts))) : "";
                    return `
                      <div class="kb-kv-row">
                        <span class="truncate">
                          <span class="flag">${escapeHtml(kindText)}</span>
                          <button type="button" class="btn-text pri" data-brain-open-source="${escapeHtml(item.url)}" data-brain-source-title="${escapeHtml(item.title)}">
                            ${escapeHtml(item.title)}
                          </button>
                        </span>
                        <span class="muted">${escapeHtml(item.domain)} · ${escapeHtml(rel)}</span>
                      </div>
                    `;
                  })
                  .join("")
          }
        </div>

        <div class="card">
          <div class="card-h">
            <b>Top domains &amp; source trust</b>
            <span class="badge soft">${kb.top_domains.length}</span>
            <span class="end muted">Personal trust counts for at most 30% (0.7 system + 0.3 yours)</span>
          </div>
          ${
            kb.top_domains.length === 0
              ? `<div class="muted">No domains recorded yet.</div>`
              : `<div class="table-wrap">
                  <table class="table">
                    <thead>
                      <tr>
                        <th>Domain</th>
                        <th class="num">System</th>
                        <th>Personal trust (0-10)</th>
                        <th class="num">Effective</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${kb.top_domains
                        .map((d) => {
                          const sysScore = Number(d.system ?? d.trust ?? 5.0);
                          const hasPersonal =
                            d.personal !== undefined && d.personal !== null;
                          const personalScore = hasPersonal
                            ? Number(d.personal)
                            : sysScore;
                          const effScore = Number(
                            d.effective ??
                              (0.7 * sysScore + 0.3 * personalScore).toFixed(2)
                          );
                          const bandLabel = d.band_label || "Unscored";
                          const sysReason = d.scored
                            ? d.why || d.category || "registry"
                            : "unscored (default 5.0)";
                          const conflictBadge = d.conflict
                            ? ` <span class="badge soft" title="Personal and system trust differ by at least 3.0">Conflict</span>`
                            : "";
                          return `
                            <tr data-domain-trust-row="${escapeHtml(d.domain)}">
                              <td>
                                <div><b>${escapeHtml(d.domain)}</b></div>
                                <div class="muted">${d.visits} visits · ${escapeHtml(sysReason)}</div>
                              </td>
                              <td class="num">${sysScore.toFixed(1)}</td>
                              <td>
                                <div class="slider-row">
                                  <input
                                    class="slider"
                                    type="range"
                                    min="0"
                                    max="10"
                                    step="0.5"
                                    value="${personalScore}"
                                    data-trust-slider-domain="${escapeHtml(d.domain)}"
                                  />
                                  <span class="slider-val" data-trust-slider-val="${escapeHtml(d.domain)}">${personalScore.toFixed(1)}</span>
                                  ${
                                    hasPersonal
                                      ? `<button type="button" class="btn-text" data-trust-reset-domain="${escapeHtml(d.domain)}">Reset</button>`
                                      : ""
                                  }
                                </div>
                              </td>
                              <td class="num">${effScore.toFixed(2)}/10 · ${escapeHtml(bandLabel)}${conflictBadge}</td>
                            </tr>
                          `;
                        })
                        .join("")}
                    </tbody>
                  </table>
                </div>`
          }
        </div>

        <div class="card">
          <div class="card-h">
            <b>Recent passages</b>
            <span class="badge soft">${kb.passages.length}</span>
          </div>
          ${
            kb.passages.length === 0
              ? `<div class="muted">No passages ingested yet.</div>`
              : kb.passages
                  .map(
                    (p) => `
                <div class="source-row">
                  <div class="source-row-top">
                    <b class="t">${escapeHtml(p.entity || p.url)}</b>
                    <button type="button" class="btn-text" data-delete-passage="${escapeHtml(p.id)}">Forget</button>
                  </div>
                  <div class="source-row-meta">${escapeHtml(p.url)}</div>
                  <div>${escapeHtml(p.text.slice(0, 260))}</div>
                </div>
              `
                  )
                  .join("")
          }
        </div>
      </div>
    </div>
  `;

  container
    .querySelector("#brain-open-settings-btn")
    ?.addEventListener("click", () => {
      if (actions.onSwitchToSettings) {
        actions.onSwitchToSettings();
      }
    });

  container.querySelector("#brain-close-btn")?.addEventListener("click", () => {
    actions.onCloseKnowledgeView();
  });

  const searchInput = container.querySelector(
    "#brain-search-input"
  ) as HTMLInputElement | null;
  if (wasFocused && searchInput) {
    searchInput.focus();
    if (selStart !== null) {
      searchInput.setSelectionRange(selStart, selStart);
    }
  }

  const triggerBrainSearch = (q: string) => {
    state.brainSearchQuery = q;
    if (actions.onSearchBrain) {
      actions.onSearchBrain(q);
    }
  };

  searchInput?.addEventListener("input", () => {
    const val = searchInput.value;
    state.brainSearchQuery = val;
    if (brainSearchDebounceTimer) {
      clearTimeout(brainSearchDebounceTimer);
    }
    brainSearchDebounceTimer = setTimeout(() => {
      triggerBrainSearch(val.trim());
    }, 150);
  });

  searchInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (brainSearchDebounceTimer) {
        clearTimeout(brainSearchDebounceTimer);
      }
      triggerBrainSearch(searchInput.value.trim());
    }
  });

  container.querySelector("#brain-search-btn")?.addEventListener("click", () => {
    triggerBrainSearch(searchInput?.value.trim() ?? "");
  });

  const clearSearch = () => {
    state.brainSearchQuery = "";
    state.brainSearchResults = null;
    renderBrainView(container, actions);
  };
  container
    .querySelector("#brain-search-clear-btn")
    ?.addEventListener("click", clearSearch);
  container
    .querySelector("#brain-search-reset-btn")
    ?.addEventListener("click", clearSearch);

  container.querySelectorAll("[data-select-brain-slug]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const slug = (btn as HTMLElement).getAttribute("data-select-brain-slug");
      if (!slug) return;
      state.highlightedBrainSlug =
        state.highlightedBrainSlug === slug ? null : slug;
      renderBrainView(container, actions);
    });
  });

  container.querySelectorAll("[data-brain-open-source]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const url = el.getAttribute("data-brain-open-source") ?? "";
      const title = el.getAttribute("data-brain-source-title") ?? "";
      if (url && actions.onOpenSourceUrl) {
        actions.onOpenSourceUrl(url, title);
      }
    });
  });

  container.querySelectorAll("[data-delete-brain-entity]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const slug = (btn as HTMLElement).getAttribute("data-delete-brain-entity");
      if (slug && actions.onDeleteBrainEntity) {
        actions.onDeleteBrainEntity(slug);
      }
    });
  });

  container.querySelectorAll("[data-delete-passage]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = (btn as HTMLElement).getAttribute("data-delete-passage");
      if (id) actions.onDeletePassage(id);
    });
  });

  container.querySelectorAll("[data-trust-slider-domain]").forEach((inp) => {
    const slider = inp as HTMLInputElement;
    const dom = slider.getAttribute("data-trust-slider-domain") ?? "";
    slider.addEventListener("input", () => {
      const valEl = container.querySelector(
        `[data-trust-slider-val="${dom}"]`
      );
      if (valEl) {
        valEl.textContent = Number(slider.value).toFixed(1);
      }
    });
    slider.addEventListener("change", () => {
      if (dom && actions.onSetDomainTrust) {
        actions.onSetDomainTrust(dom, Number(slider.value));
      }
    });
  });

  container.querySelectorAll("[data-trust-reset-domain]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const dom = (btn as HTMLElement).getAttribute("data-trust-reset-domain");
      if (dom && actions.onSetDomainTrust) {
        actions.onSetDomainTrust(dom, null);
      }
    });
  });

  if (state.highlightedBrainSlug) {
    const cardEl = container.querySelector(
      `#brain-card-${CSS.escape(state.highlightedBrainSlug)}`
    );
    if (cardEl && typeof cardEl.scrollIntoView === "function") {
      cardEl.scrollIntoView({ block: "nearest" });
    }
  }
}
