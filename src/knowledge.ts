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
      ? `[cloud: ${configuredCloudProviders.map((p) => `${p.id} (${(p.models ?? []).length})`).join(" · ")}]`
      : "[local only · 0 cloud providers configured]";

  const renderCloudOptionsHtml = (selectedRoleVal: string) =>
    discoveredCloudModels
      .map(
        (cm) =>
          `<option value="${escapeHtml(cm.id)}" ${selectedRoleVal === cm.id ? "selected" : ""}>${escapeHtml(cm.id)}</option>`
      )
      .join("");

  const doctorSectionHtml = `
      <div class="knowledge-section">
        <div class="panel-header accordion-header" data-settings-accordion="models">
          <span>[${acc.models ? "-" : "+"}] 1. model management &amp; cloud setup (local /doctor + gemini · anthropic · openai · mistral)</span>
          <span class="muted">${escapeHtml(cloudSummaryBadge)}</span>
        </div>
        ${
          !acc.models
            ? ""
            : `
          <div class="kb-card">
            <div class="kb-card-header">
              <span><strong>role routing matrix</strong> (which model handles each browser task · cloud models pulled live from configured provider APIs)</span>
              <span class="muted">mail classifier &amp; brain encoder stay 100% local</span>
            </div>
            <div class="vault-form-row">
              <label class="muted">chat &amp; synthesis:</label>
              <select id="kb-role-chat-select" class="vault-input">
                <option value="gemma-4-e4b" ${roleChat === "gemma-4-e4b" ? "selected" : ""}>gemma-4-e4b (local · default)</option>
                ${renderCloudOptionsHtml(roleChat)}
              </select>
              <label class="muted">web answer (+web):</label>
              <select id="kb-role-web-select" class="vault-input">
                <option value="planck3 (web)" ${roleWeb === "planck3 (web)" ? "selected" : ""}>planck3 (local read->weigh->write)</option>
                ${renderCloudOptionsHtml(roleWeb)}
              </select>
              <label class="muted">page reader:</label>
              <select id="kb-role-reader-select" class="vault-input">
                <option value="hertz (reader)" ${roleReader === "hertz (reader)" ? "selected" : ""}>hertz 1.2 (local extractive reader)</option>
                <option value="planck (reader)" ${roleReader === "planck (reader)" ? "selected" : ""}>planck (local extractive reader)</option>
                <option value="gemma-4-e4b" ${roleReader === "gemma-4-e4b" ? "selected" : ""}>gemma-4-e4b (local generative)</option>
                ${renderCloudOptionsHtml(roleReader)}
              </select>
              <button id="kb-save-roles-btn">[apply role routing]</button>
            </div>
            <div class="vault-form-row" style="margin-top:6px;">
              <label class="muted">news planner:</label>
              <select id="kb-role-news-planner-select" class="vault-input">
                <option value="gemma-4-e4b" ${roleNewsPlanner === "gemma-4-e4b" ? "selected" : ""}>gemma-4-e4b (local · default)</option>
                ${renderCloudOptionsHtml(roleNewsPlanner)}
              </select>
              <label class="muted">news capture/translate:</label>
              <select id="kb-role-news-capture-select" class="vault-input">
                <option value="gemma-4-e4b" ${roleNewsCapture === "gemma-4-e4b" ? "selected" : ""}>gemma-4-e4b (local · default)</option>
                ${renderCloudOptionsHtml(roleNewsCapture)}
              </select>
              <label class="muted">news reader (trust-blind):</label>
              <select id="kb-role-news-reader-select" class="vault-input">
                <option value="hertz (reader)" ${roleNewsReader === "hertz (reader)" ? "selected" : ""}>hertz 1.2 (local int8 · default)</option>
                <option value="planck (reader)" ${roleNewsReader === "planck (reader)" ? "selected" : ""}>planck (local reader)</option>
                <option value="heuristic" ${roleNewsReader === "heuristic" ? "selected" : ""}>heuristic lexical (0 model)</option>
                <option value="gemma-4-e4b" ${roleNewsReader === "gemma-4-e4b" ? "selected" : ""}>gemma-4-e4b (local)</option>
                ${renderCloudOptionsHtml(roleNewsReader)}
              </select>
              <label class="muted">news analyzer:</label>
              <select id="kb-role-news-analyzer-select" class="vault-input">
                <option value="gemma-4-e4b" ${roleNewsAnalyzer === "gemma-4-e4b" ? "selected" : ""}>gemma-4-e4b (local)</option>
                <option value="template" ${roleNewsAnalyzer === "template" ? "selected" : ""}>template extractive (0 LLM)</option>
                ${renderCloudOptionsHtml(roleNewsAnalyzer)}
              </select>
            </div>
          </div>

          ${
            state.modelConfigStatusMsg
              ? `<div class="profile-status-banner">${escapeHtml(state.modelConfigStatusMsg)}</div>`
              : ""
          }

          <div class="rail-group-label">
            <span>cloud model providers (models discovered dynamically from each provider's /models endpoint)</span>
          </div>
          ${cloudProviders
            .map((p) => {
              const envKey = p.env_key ?? `${p.id.toUpperCase()}_API_KEY`;
              const modelsList = p.models ?? [];
              const modelsCount = modelsList.length;
              const storedKey = p.stored_key ?? "";
              return `
                <div class="kb-card">
                  <div class="kb-card-header">
                    <span><strong>${escapeHtml(p.label)}</strong> <span class="muted">(${escapeHtml(envKey)} · ${escapeHtml(p.host ?? "")})</span></span>
                    <span class="status-item">${
                      p.configured
                        ? `[configured in ${escapeHtml(p.key_source ?? "vault.enc")} · ${escapeHtml(p.masked_key || "***")} · ${modelsCount} models]`
                        : "[not configured]"
                    }</span>
                  </div>
                  <div class="muted">${escapeHtml(p.privacy_disclosure)}</div>
                  <div class="vault-form-row">
                    <input
                      data-cloud-key-input="${escapeHtml(p.id)}"
                      class="vault-input"
                      type="password"
                      spellcheck="false"
                      autocorrect="off"
                      autocapitalize="off"
                      value="${escapeHtml(storedKey)}"
                      placeholder="paste ${escapeHtml(envKey)} (${escapeHtml(p.placeholder ?? "api key")})_"
                    />
                    <button data-cloud-toggle-vis="${escapeHtml(p.id)}" type="button">[show key]</button>
                    <button data-cloud-save-key="${escapeHtml(p.id)}" type="button">[${p.configured ? "update key &amp; pull models" : "save key &amp; pull models"}]</button>
                    <button data-cloud-refresh-models="${escapeHtml(p.id)}" type="button">[refresh models from api]</button>
                    ${
                      p.configured || storedKey
                        ? `<button data-cloud-clear-key="${escapeHtml(p.id)}" type="button">[delete key]</button>`
                        : ""
                    }
                  </div>
                  ${
                    modelsCount > 0
                      ? `
                        <div class="vault-form-row">
                          <label class="muted">discovered models (${modelsCount}):</label>
                          <select data-cloud-model-picker="${escapeHtml(p.id)}" class="vault-input">
                            ${modelsList
                              .map(
                                (m) =>
                                  `<option value="${escapeHtml(m.id)}" ${roleChat === m.id ? "selected" : ""}>${escapeHtml(m.label || m.slug)} — ${escapeHtml(m.id)}</option>`
                              )
                              .join("")}
                          </select>
                          <button data-cloud-use-model="${escapeHtml(p.id)}" type="button">[use as chat model]</button>
                        </div>
                      `
                      : `<div class="muted">${
                          p.configured
                            ? "0 models cached — click [refresh models from api] to query /models."
                            : "paste your API key above and click [save key & pull models] to load all available models from the provider API."
                        }</div>`
                  }
                </div>
              `;
            })
            .join("")}

          <div class="rail-group-label">
            <span>local on-device models (/doctor · ${doctorRoles.length || 5} roles)</span>
          </div>
          ${
            doctorRoles.length === 0
              ? `<div class="muted">models [offline]: start sidecar to inspect model checkpoints and device placement.</div>`
              : doctorRoles
                  .map((dr) => {
                    const badge =
                      dr.state === "ready"
                        ? `[ready · ${escapeHtml(dr.device)}]`
                        : dr.state === "cpu_only"
                          ? `[cpu_only · ${escapeHtml(dr.device)}]`
                          : `[missing]`;
                    return `
                      <div class="source-row">
                        <div class="source-row-top">
                          <span>
                            <strong>${escapeHtml(dr.role)}</strong>
                            <span class="muted">· ${escapeHtml(dr.model)}</span>
                          </span>
                          <span class="${dr.state === "missing" ? "msg-error-badge" : "status-item"}">${badge}</span>
                        </div>
                        ${
                          dr.fix
                            ? `<div class="muted">fix: ${escapeHtml(dr.fix)}</div>`
                            : dr.path
                              ? `<div class="muted">${escapeHtml(dr.path)}</div>`
                              : ""
                        }
                      </div>
                    `;
                  })
                  .join("")
          }
        `
        }
      </div>
  `;

  container.innerHTML = `
    <div class="knowledge-view">
      <div class="knowledge-section">
        <div class="panel-header">
          <span>settings · accordion navigation (click any section header to expand / collapse)</span>
          <div>
            <button id="kb-expand-all-btn">[expand all]</button>
            <button id="kb-collapse-all-btn">[collapse all]</button>
            <button id="kb-open-brain-btn">[brain · ${MOD_LABEL}+b]</button>
            <button id="kb-pause-btn" class="${kb.pause_learning ? "active" : ""}">
              [pause learning: ${kb.pause_learning ? "on" : "off"}]
            </button>
            <button id="kb-close-btn">[close]</button>
          </div>
        </div>
        <div class="muted">
          active profile: ${
            isUnlocked && activeProfile
              ? `${escapeHtml(activeProfile.name)} [unlocked]`
              : "none [locked - unlock a profile to save to your Brain, Mail, and password vault; browsing uses an ephemeral in-memory store]"
          } · brain entities: ${brainEntities.length} · ${escapeHtml(brainRankingLabel)} · indexed bookmarks: ${bookmarksIndexed.length} · ingest queue: ${kb.queue_len}
        </div>
        <div class="vault-form-row">
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
        ${
          state.profileStatusMessage
            ? `<div class="profile-status-banner">${escapeHtml(state.profileStatusMessage)}</div>`
            : ""
        }
      </div>

      ${doctorSectionHtml}

      <div class="knowledge-section">
        <div class="panel-header accordion-header" data-settings-accordion="profiles">
          <span>[${acc.profiles ? "-" : "+"}] 2. user profiles &amp; security (name + 6-digit pin) (${profilesList.length})</span>
          ${
            isUnlocked
              ? `<button id="kb-lock-profile-btn">[lock active profile]</button>`
              : `<span class="muted">[locked]</span>`
          }
        </div>
        ${
          !acc.profiles
            ? ""
            : `
        <div class="vault-form-row">
          <input
            id="kb-new-profile-name"
            class="vault-input"
            type="text"
            spellcheck="false"
            autocorrect="off"
            autocapitalize="off"
            placeholder="profile name (e.g. Nikita)_"
          />
          <input
            id="kb-new-profile-pin"
            class="vault-input vault-pin-input"
            type="password"
            inputmode="numeric"
            maxlength="6"
            spellcheck="false"
            autocorrect="off"
            autocapitalize="off"
            placeholder="6-digit PIN (e.g. 123456)_"
          />
          <button id="kb-create-profile-btn">[+ create profile]</button>
        </div>
        ${
          profilesList.length === 0
            ? `<div class="muted">no profiles created yet. create a profile with a name and a 6-digit PIN above.</div>`
            : profilesList
                .map(
                  (p) => `
              <div class="source-row">
                <div class="source-row-top">
                  <span>
                    ${p.is_active ? "* " : ""}${escapeHtml(p.name)}
                    <span class="muted">(id: ${escapeHtml(p.id)} · ${p.credential_services_count} .env services)</span>
                  </span>
                  <div class="vault-inline-controls">
                    ${
                      p.is_active
                        ? `<span class="status-item">[unlocked]</span>`
                        : `
                      <input
                        class="vault-input vault-pin-input"
                        type="password"
                        inputmode="numeric"
                        maxlength="6"
                        spellcheck="false"
                        autocorrect="off"
                        autocapitalize="off"
                        placeholder="6-digit PIN"
                        data-profile-pin-input="${escapeHtml(p.id)}"
                      />
                      <button data-unlock-profile="${escapeHtml(p.id)}">[unlock]</button>
                      ${
                        IS_MAC
                          ? `<button data-unlock-touchid="${escapeHtml(p.id)}">[unlock with Touch ID]</button>`
                          : ""
                      }
                    `
                    }
                    <button class="rail-menu-btn" data-delete-profile="${escapeHtml(p.id)}" title="enter 6-digit PIN to delete profile">[delete]</button>
                  </div>
                </div>
              </div>
            `
                )
                .join("")
        }
        `
        }
      </div>

      <div class="knowledge-section">
        <div class="panel-header accordion-header" data-settings-accordion="vault">
          <span>[${acc.vault ? "-" : "+"}] 3. profile .env password vault (${isUnlocked ? `${vaultServices.length} services` : "locked"})</span>
          ${
            isUnlocked && state.activeDetail?.tabs.some((t) => t.is_open)
              ? `<button id="kb-autofill-tab-btn" title="Auto-fill & login on open tab using active profile .env credentials">[auto-fill open tab]</button>`
              : `<span class="muted">AES-256-GCM + Argon2id</span>`
          }
        </div>
        ${
          !acc.vault
            ? ""
            : !isUnlocked
              ? `<div class="muted">locked: vault credentials (vault.enc), Mail (mail.sqlite), the Satz Brain (BRAIN.md), and the passage store (planck_store.sqlite) are scoped to an unlocked profile.</div>`
              : `
          <div class="muted">
            profile .env file: ${escapeHtml(vault?.env_path ?? "")} · only accessible while profile "${escapeHtml(activeProfile?.name ?? "")}" is unlocked. used by the agent when prompted and in the background for bookmarks.
          </div>

          <div class="vault-form-row">
            <input id="kb-cred-service" class="vault-input" type="text" spellcheck="false" autocorrect="off" autocapitalize="off" placeholder="service/domain (e.g. gmail.com, zalando.de)_" />
            <input id="kb-cred-username" class="vault-input" type="text" spellcheck="false" autocorrect="off" autocapitalize="off" placeholder="username / email_" />
            <input id="kb-cred-password" class="vault-input" type="password" spellcheck="false" autocorrect="off" autocapitalize="off" placeholder="password / app-password_" />
            <input id="kb-cred-token" class="vault-input" type="password" spellcheck="false" autocorrect="off" autocapitalize="off" placeholder="token or cookie (optional)_" />
            <button id="kb-save-cred-btn">[+ save to .env]</button>
          </div>

          <div class="vault-form-row">
            <input id="kb-import-env-path" class="vault-input" type="text" spellcheck="false" autocorrect="off" autocapitalize="off" placeholder="import external .env file path (e.g. ${IS_MAC ? "~/Downloads/.env" : "C:\\Users\\...\\.env"})_" />
            <button id="kb-import-env-btn">[import .env file]</button>
            <input
              id="kb-reveal-pin-input"
              class="vault-input vault-pin-input"
              type="password"
              inputmode="numeric"
              maxlength="6"
              spellcheck="false"
              autocorrect="off"
              autocapitalize="off"
              placeholder="6-digit PIN to [reveal]_"
            />
          </div>

          ${
            vaultServices.length === 0
              ? `<div class="muted">no credentials in this profile's vault.enc yet. add a service above or paste/import a .env file below.</div>`
              : vaultServices
                  .map((s) => {
                    const revPwd = state.revealedPasswords[`${s.service}:password`];
                    const revTok = state.revealedPasswords[`${s.service}:token`];
                    const revCook = state.revealedPasswords[`${s.service}:cookie`];
                    return `
                <div class="rail-row">
                  <span>
                    <strong>${escapeHtml(s.service)}</strong>
                    ${s.domain ? `<span class="muted">(${escapeHtml(s.domain)})</span>` : ""}
                    · user: ${escapeHtml(s.username || "(token/cookie)")}
                  </span>
                  <span>
                    <span class="muted">
                      ${
                        s.has_password
                          ? revPwd
                            ? `[password: ${escapeHtml(revPwd)}] `
                            : `[password <button class="rail-menu-btn" data-reveal-service="${escapeHtml(s.service)}" data-reveal-field="password">[reveal]</button>] `
                          : ""
                      }${
                        s.has_token
                          ? revTok
                            ? `[token: ${escapeHtml(revTok)}] `
                            : `[token <button class="rail-menu-btn" data-reveal-service="${escapeHtml(s.service)}" data-reveal-field="token">[reveal]</button>] `
                          : ""
                      }${
                        s.has_cookie
                          ? revCook
                            ? `[cookie: ${escapeHtml(revCook)}]`
                            : `[cookie <button class="rail-menu-btn" data-reveal-service="${escapeHtml(s.service)}" data-reveal-field="cookie">[reveal]</button>]`
                          : ""
                      }
                    </span>
                    <button class="rail-menu-btn" data-delete-cred="${escapeHtml(s.service)}">[delete]</button>
                  </span>
                </div>
              `;
                  })
                  .join("")
          }

          <div class="vault-raw-block">
            <div class="muted">write-only .env batch importer for encrypted vault.enc (${escapeHtml(activeProfile?.name ?? "")}):</div>
            <textarea id="kb-raw-env-textarea" class="vault-textarea" rows="5" spellcheck="false" placeholder="paste KEY=VALUE lines here to merge into encrypted vault.enc (write-only; stored secrets are never returned over HTTP)_"></textarea>
            <div>
              <button id="kb-save-raw-env-btn">[merge into vault.enc]</button>
            </div>
          </div>
        `
        }
      </div>

      <div class="knowledge-section">
        <div class="panel-header accordion-header" data-settings-accordion="mail">
          <span>[${acc.mail ? "-" : "+"}] 4. mail accounts &amp; classifier eval (${state.mailAccounts.length} accounts)</span>
          <span class="muted">IMAP / POP3 / SMTP</span>
        </div>
        ${!acc.mail ? "" : renderMailAccountsSectionHtml()}
      </div>

      <div class="knowledge-section">
        <div class="panel-header accordion-header" data-settings-accordion="indexing">
          <span>[${acc.indexing ? "-" : "+"}] 5. background indexing &amp; bookmarks (${bookmarksIndexed.length})</span>
          <span class="muted">30-min conditional fetch</span>
        </div>
        ${
          !acc.indexing
            ? ""
            : `
        <div class="muted">
          bookmarked sources are continuously fetched, authenticated (via unlocked profile .env when applicable), and indexed in the background.
        </div>
        ${
          bookmarksIndexed.length === 0
            ? `<div class="muted">no bookmarks hooked up yet. click [+ bookmark current] in the left rail to continuously index a source.</div>`
            : bookmarksIndexed
                .map(
                  (bm) => `
              <div class="rail-row">
                <span>${escapeHtml(bm.title || bm.domain)} <span class="muted">(${escapeHtml(bm.url)})</span></span>
                <span class="muted">
                  [${escapeHtml(bm.status)}] · ${bm.text_chars} chars · ${
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
        `
        }
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
    hdr.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      if (target.closest("button")) return;
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
        btn.textContent = "[hide key]";
      } else {
        inputEl.type = "password";
        btn.textContent = "[show key]";
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
      ? `<button class="rail-menu-btn" data-brain-open-source="${escapeHtml(normalizedSrcUrl)}" data-brain-source-title="${escapeHtml(e.name)}">[source]</button>`
      : "";

  return `
    <div
      class="source-row ${isHighlighted ? "active" : ""}"
      id="brain-card-${escapeHtml(e.slug)}"
      data-brain-card-slug="${escapeHtml(e.slug)}"
    >
      <div class="source-row-top">
        <span>
          <button class="citation-link" data-select-brain-slug="${escapeHtml(e.slug)}">
            [${escapeHtml(e.type)}] <strong>${escapeHtml(e.name)}</strong>
          </button>
          <span class="muted">(tier ${e.tier} · ${escapeHtml(e.path)})</span>
        </span>
        <div>
          ${sourceBtnHtml}
          <button class="rail-menu-btn" data-delete-brain-entity="${escapeHtml(e.slug)}">[forget]</button>
        </div>
      </div>
      <div>${escapeHtml(e.summary)}</div>
      ${attrEntries ? `<div class="muted">${escapeHtml(attrEntries)}</div>` : ""}
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
    "brain ranking: lexical (planck13 missing)";
  const profileInfo = kb.profile;
  const isUnlocked = Boolean(profileInfo?.unlocked && profileInfo?.active_profile);
  const activeProfile = profileInfo?.active_profile ?? null;
  const thisWeek = kb.this_week ?? [];
  const searchRes = state.brainSearchResults;
  const hasActiveSearch = Boolean(state.brainSearchQuery.trim() && searchRes);

  const typeOrder = [
    { key: "order", label: "orders" },
    { key: "person", label: "people" },
    { key: "organization", label: "organizations" },
    { key: "promotion", label: "promotions" },
    { key: "place", label: "places" },
    { key: "account", label: "accounts" },
    { key: "note", label: "notes" },
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
    ? `<div class="muted">unlock a profile to save to your Brain.</div>`
    : brainEntities.length === 0
      ? `<div class="muted">no brain entities stored yet. sync mail, browse authenticated tabs, or ask chat to store addresses, contacts, orders, or notes.</div>`
      : [
          ...typeOrder
            .filter((tg) => (groupedEntities.get(tg.key)?.length ?? 0) > 0)
            .map((tg) => {
              const items = groupedEntities.get(tg.key) ?? [];
              return `
                <div class="rail-group-label">
                  <span>${escapeHtml(tg.label)} (${items.length})</span>
                </div>
                ${items.map((item) => renderBrainEntityCardHtml(item)).join("")}
              `;
            }),
          otherEntities.length > 0
            ? `
              <div class="rail-group-label">
                <span>other (${otherEntities.length})</span>
              </div>
              ${otherEntities.map((item) => renderBrainEntityCardHtml(item)).join("")}
            `
            : "",
        ].join("");

  const searchResultsSectionHtml = hasActiveSearch && searchRes
    ? `
      <div class="knowledge-section" id="brain-search-results-section">
        <div class="panel-header">
          <span>search results for "${escapeHtml(state.brainSearchQuery)}" · ${searchRes.entities.length} entities · ${searchRes.passages.length} passages · ${searchRes.mail.length} mail</span>
          <button id="brain-search-clear-btn">[clear]</button>
        </div>
        ${
          searchRes.entities.length === 0 &&
          searchRes.passages.length === 0 &&
          searchRes.mail.length === 0
            ? `<div class="muted">no matches in entities, passages, or mail.</div>`
            : `
              ${
                searchRes.entities.length > 0
                  ? `
                    <div class="rail-group-label"><span>matching entities (${searchRes.entities.length})</span></div>
                    ${searchRes.entities.map((e) => renderBrainEntityCardHtml(e)).join("")}
                  `
                  : ""
              }
              ${
                searchRes.passages.length > 0
                  ? `
                    <div class="rail-group-label"><span>matching passages (${searchRes.passages.length})</span></div>
                    ${searchRes.passages
                      .map(
                        (p) => `
                          <div class="source-row">
                            <div class="source-row-top">
                              <button class="citation-link" data-brain-open-source="${escapeHtml(p.url)}" data-brain-source-title="${escapeHtml(p.title || p.entity || p.url)}">
                                ${escapeHtml(p.title || p.entity || p.url)}
                              </button>
                              <button class="rail-menu-btn" data-delete-passage="${escapeHtml(p.id)}">[forget]</button>
                            </div>
                            <div class="muted">${escapeHtml(p.url)}</div>
                            <div>${escapeHtml(p.text.slice(0, 260))}</div>
                          </div>
                        `
                      )
                      .join("")}
                  `
                  : ""
              }
              ${
                searchRes.mail.length > 0
                  ? `
                    <div class="rail-group-label"><span>matching mail (${searchRes.mail.length})</span></div>
                    ${searchRes.mail
                      .map((m) => {
                        const mid = String(m.id ?? "");
                        const sender = String(m.from_name || m.from_addr || "");
                        const subj = String(m.subject ?? "(no subject)");
                        const snip = String(m.snippet ?? "");
                        return `
                          <div class="source-row">
                            <div class="source-row-top">
                              <button class="citation-link" data-brain-open-source="satzmail://message/${escapeHtml(mid)}" data-brain-source-title="${escapeHtml(subj)}">
                                [mail] ${escapeHtml(sender)} · ${escapeHtml(subj)}
                              </button>
                              <span class="muted">[${escapeHtml(String(m.label ?? "email"))}]</span>
                            </div>
                            <div class="muted">${escapeHtml(snip.slice(0, 200))}</div>
                          </div>
                        `;
                      })
                      .join("")}
                  `
                  : ""
              }
            `
        }
      </div>
    `
    : "";

  container.innerHTML = `
    <div class="knowledge-view" id="brain-view-root">
      <div class="knowledge-section">
        <div class="panel-header">
          <span>satz brain · ${MOD_LABEL}+b · ${
            isUnlocked && activeProfile
              ? `profile: ${escapeHtml(activeProfile.name)}`
              : "locked"
          }</span>
          <div>
            <span class="muted">${escapeHtml(brainRankingLabel)}</span>
            <button id="brain-open-settings-btn">[settings]</button>
            <button id="brain-close-btn">[close]</button>
          </div>
        </div>
        <div class="vault-form-row">
          <input
            id="brain-search-input"
            class="vault-input"
            type="text"
            spellcheck="false"
            autocorrect="off"
            autocapitalize="off"
            placeholder="search entities, passages, and mail (FTS5 + encoder rank)_"
            value="${escapeHtml(state.brainSearchQuery)}"
          />
          <button id="brain-search-btn">[search]</button>
          ${
            state.brainSearchQuery
              ? `<button id="brain-search-reset-btn">[clear]</button>`
              : ""
          }
        </div>
      </div>

      ${searchResultsSectionHtml}

      <div class="knowledge-section">
        <div class="panel-header">
          <span>entity cards by type (${brainEntities.length})</span>
          <span class="muted">${escapeHtml(brainRankingLabel)}</span>
        </div>
        ${entityGroupsHtml}
      </div>

      <div class="knowledge-section">
        <div class="panel-header">
          <span>this week · read &amp; received (${thisWeek.length})</span>
        </div>
        ${
          thisWeek.length === 0
            ? `<div class="muted">no pages read or emails received in the last 7 days.</div>`
            : thisWeek
                .map((item) => {
                  const badge = item.kind === "received" ? "[received]" : "[read]";
                  const rel = item.ts > 0 ? formatRelativeTime(String(Math.floor(item.ts))) : "";
                  return `
                    <div class="rail-row">
                      <span>
                        <span class="muted">${badge}</span>
                        <button class="citation-link" data-brain-open-source="${escapeHtml(item.url)}" data-brain-source-title="${escapeHtml(item.title)}">
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

      <div class="knowledge-section">
        <div class="panel-header">
          <span>top domains &amp; source trust (${kb.top_domains.length})</span>
          <span class="muted">effective = 0.7 * system + 0.3 * yours (30% hard cap)</span>
        </div>
        ${
          kb.top_domains.length === 0
            ? `<div class="muted">no domains recorded yet</div>`
            : kb.top_domains
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
                    ? ` <span class="msg-error-badge" title="|yours - system| >= 3.0">[conflict]</span>`
                    : "";
                  return `
                    <div class="source-row" data-domain-trust-row="${escapeHtml(d.domain)}">
                      <div class="source-row-top">
                        <span>
                          <strong>${escapeHtml(d.domain)}</strong>
                          <span class="muted">· ${d.visits} visits</span>
                        </span>
                        <span>
                          effective <strong>${effScore.toFixed(2)}</strong> / 10
                          <span class="muted">[${escapeHtml(bandLabel)}]</span>${conflictBadge}
                        </span>
                      </div>
                      <div class="muted">
                        system: ${sysScore.toFixed(1)} (${escapeHtml(sysReason)}) · yours: ${
                          hasPersonal
                            ? `${personalScore.toFixed(1)} (0.7 * ${sysScore.toFixed(1)} + 0.3 * ${personalScore.toFixed(1)} = ${effScore.toFixed(2)})`
                            : `default (${sysScore.toFixed(1)})`
                        }
                      </div>
                      <div class="vault-form-row">
                        <span class="muted">your score (0-10, 30% max blend):</span>
                        <input
                          type="range"
                          min="0"
                          max="10"
                          step="0.5"
                          value="${personalScore}"
                          data-trust-slider-domain="${escapeHtml(d.domain)}"
                        />
                        <span class="muted" data-trust-slider-val="${escapeHtml(d.domain)}">${personalScore.toFixed(1)}</span>
                        ${
                          hasPersonal
                            ? `<button class="rail-menu-btn" data-trust-reset-domain="${escapeHtml(d.domain)}">[reset]</button>`
                            : ""
                        }
                      </div>
                    </div>
                  `;
                })
                .join("")
        }
      </div>

      <div class="knowledge-section">
        <div class="panel-header">
          <span>recent passages (${kb.passages.length})</span>
        </div>
        ${
          kb.passages.length === 0
            ? `<div class="muted">no passages ingested yet</div>`
            : kb.passages
                .map(
                  (p) => `
              <div class="source-row">
                <div class="source-row-top">
                  <span>${escapeHtml(p.entity || p.url)}</span>
                  <button class="rail-menu-btn" data-delete-passage="${escapeHtml(p.id)}">[forget]</button>
                </div>
                <div class="muted">${escapeHtml(p.url)}</div>
                <div>${escapeHtml(p.text.slice(0, 260))}</div>
              </div>
            `
                )
                .join("")
        }
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
