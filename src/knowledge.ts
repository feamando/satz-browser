import { escapeHtml, formatRelativeTime, state } from "./state";

export interface KnowledgeActions {
  onTogglePauseLearning: (paused: boolean) => void;
  onDeletePassage: (passageId: string) => void;
  onDeleteBrainEntity?: (slug: string) => void;
  onCreateProfile?: (name: string, pin: string) => void;
  onUnlockProfile?: (profileId: string, pin: string) => void;
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
  onAutofillActiveTab?: () => void;
  onCloseKnowledgeView: () => void;
}

export function renderKnowledgeView(
  container: HTMLElement,
  actions: KnowledgeActions
): void {
  const kb = state.knowledge;
  const brainEntities = kb.brain?.entities ?? [];
  const bookmarksIndexed = kb.bookmarks_indexed ?? [];
  const profileInfo = kb.profile;
  const profilesList = profileInfo?.profiles ?? [];
  const isUnlocked = Boolean(profileInfo?.unlocked && profileInfo?.active_profile);
  const activeProfile = profileInfo?.active_profile ?? null;
  const vault = kb.vault;
  const vaultServices = vault?.services ?? [];

  container.innerHTML = `
    <div class="knowledge-view">
      <div class="knowledge-section">
        <div class="panel-header">
          <span>knowledge base · user profiles (6-digit pin) · .env password vault</span>
          <div>
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
              : "none [locked - unlock with 6-digit PIN to access profile .env passwords]"
          } · brain entities: ${brainEntities.length} · indexed bookmarks: ${bookmarksIndexed.length} · ingest queue: ${kb.queue_len}
        </div>
        ${
          state.profileStatusMessage
            ? `<div class="profile-status-banner">${escapeHtml(state.profileStatusMessage)}</div>`
            : ""
        }
      </div>

      <div class="knowledge-section">
        <div class="panel-header">
          <span>user profiles (name + 6-digit pin) (${profilesList.length})</span>
          ${
            isUnlocked
              ? `<button id="kb-lock-profile-btn">[lock active profile]</button>`
              : ""
          }
        </div>
        <div class="vault-form-row">
          <input
            id="kb-new-profile-name"
            class="vault-input"
            type="text"
            placeholder="profile name (e.g. Nikita)_"
          />
          <input
            id="kb-new-profile-pin"
            class="vault-input vault-pin-input"
            type="password"
            inputmode="numeric"
            maxlength="6"
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
                        placeholder="6-digit PIN"
                        data-profile-pin-input="${escapeHtml(p.id)}"
                      />
                      <button data-unlock-profile="${escapeHtml(p.id)}">[unlock]</button>
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
      </div>

      <div class="knowledge-section">
        <div class="panel-header">
          <span>profile .env password management system (${isUnlocked ? `${vaultServices.length} services` : "locked"})</span>
          ${
            isUnlocked && state.activeDetail?.tabs.some((t) => t.is_open)
              ? `<button id="kb-autofill-tab-btn" title="Auto-fill & login on open tab using active profile .env credentials">[auto-fill open tab]</button>`
              : ""
          }
        </div>
        ${
          !isUnlocked
            ? `<div class="muted">locked: password files (.env) are strictly scoped to a profile. create or unlock a profile with your 6-digit PIN above so the agent and background bookmark indexer can use your stored credentials.</div>`
            : `
          <div class="muted">
            profile .env file: ${escapeHtml(vault?.env_path ?? "")} · only accessible while profile "${escapeHtml(activeProfile?.name ?? "")}" is unlocked. used by the agent when prompted and in the background for bookmarks.
          </div>

          <div class="vault-form-row">
            <input id="kb-cred-service" class="vault-input" type="text" placeholder="service/domain (e.g. gmail.com, zalando.de)_" />
            <input id="kb-cred-username" class="vault-input" type="text" placeholder="username / email_" />
            <input id="kb-cred-password" class="vault-input" type="password" placeholder="password / app-password_" />
            <input id="kb-cred-token" class="vault-input" type="password" placeholder="token or cookie (optional)_" />
            <button id="kb-save-cred-btn">[+ save to .env]</button>
          </div>

          <div class="vault-form-row">
            <input id="kb-import-env-path" class="vault-input" type="text" placeholder="import external .env file path (e.g. C:\\Users\\...\\.env)_" />
            <button id="kb-import-env-btn">[import .env file]</button>
          </div>

          ${
            vaultServices.length === 0
              ? `<div class="muted">no credentials in this profile's .env yet. add a service above or paste/import a .env file below.</div>`
              : vaultServices
                  .map(
                    (s) => `
                <div class="rail-row">
                  <span>
                    <strong>${escapeHtml(s.service)}</strong>
                    ${s.domain ? `<span class="muted">(${escapeHtml(s.domain)})</span>` : ""}
                    · user: ${escapeHtml(s.username || "(token/cookie)")}
                  </span>
                  <span>
                    <span class="muted">
                      ${s.has_password ? "[password] " : ""}${s.has_token ? "[token] " : ""}${s.has_cookie ? "[cookie]" : ""}
                    </span>
                    <button class="rail-menu-btn" data-delete-cred="${escapeHtml(s.service)}">[delete]</button>
                  </span>
                </div>
              `
                  )
                  .join("")
          }

          <div class="vault-raw-block">
            <div class="muted">direct .env password file editor (${escapeHtml(activeProfile?.name ?? "")}):</div>
            <textarea id="kb-raw-env-textarea" class="vault-textarea" rows="6" spellcheck="false">${escapeHtml(vault?.raw_env ?? "")}</textarea>
            <div>
              <button id="kb-save-raw-env-btn">[save .env file]</button>
            </div>
          </div>
        `
        }
      </div>

      <div class="knowledge-section">
        <div class="panel-header">
          <span>continuously indexed bookmarks (${bookmarksIndexed.length})</span>
        </div>
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
      </div>

      <div class="knowledge-section">
        <div class="panel-header">
          <span>satz brain entities (${brainEntities.length})</span>
        </div>
        ${
          brainEntities.length === 0
            ? `<div class="muted">no brain entities stored yet. browse authenticated tabs or ask chat to store addresses, contacts, accounts, or notes.</div>`
            : brainEntities
                .map((e) => {
                  const attrEntries = Object.entries(e.attributes ?? {})
                    .filter(([k]) => k !== "source_url")
                    .map(([k, v]) => `${k}: ${String(v)}`)
                    .join(" · ");
                  return `
              <div class="source-row">
                <div class="source-row-top">
                  <span>[${escapeHtml(e.type)}] ${escapeHtml(e.name)} <span class="muted">(tier ${e.tier} · ${escapeHtml(e.path)})</span></span>
                  <button class="rail-menu-btn" data-delete-brain-entity="${escapeHtml(e.slug)}">[delete]</button>
                </div>
                <div>${escapeHtml(e.summary)}</div>
                ${attrEntries ? `<div class="muted">${escapeHtml(attrEntries)}</div>` : ""}
              </div>
            `;
                })
                .join("")
        }
      </div>

      <div class="knowledge-section">
        <div class="panel-header">
          <span>top domains (${kb.top_domains.length})</span>
        </div>
        ${
          kb.top_domains.length === 0
            ? `<div class="muted">no domains recorded yet</div>`
            : kb.top_domains
                .map(
                  (d) => `
              <div class="rail-row">
                <span>${escapeHtml(d.domain)}</span>
                <span class="muted">${d.visits} visits · trust ${Number(d.score ?? 0).toFixed(1)}</span>
              </div>
            `
                )
                .join("")
        }
      </div>

      <div class="knowledge-section">
        <div class="panel-header">
          <span>top topics (${kb.top_topics.length})</span>
        </div>
        ${
          kb.top_topics.length === 0
            ? `<div class="muted">no topics extracted yet</div>`
            : kb.top_topics
                .map(
                  (t) => `
              <div class="rail-row">
                <span>${escapeHtml(t.topic)}</span>
                <span class="muted">score ${Number(t.weight ?? 0).toFixed(2)}</span>
              </div>
            `
                )
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
                  <button class="rail-menu-btn" data-delete-passage="${escapeHtml(p.id)}">[delete]</button>
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

  container.querySelectorAll("[data-delete-passage]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = (btn as HTMLElement).getAttribute("data-delete-passage");
      if (id) actions.onDeletePassage(id);
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
}
