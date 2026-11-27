import { icon } from "./design-system/icons";
import {
  bindDriveAccountsEvents,
  getConfiguredDriveProviders,
  renderDriveAccountsPanelHtml,
} from "./drives";
import {
  EN_CATALOG,
  getActiveLocaleEntries,
  getUiLocale,
  getUiLocaleDir,
  getUiLocaleLabel,
  t,
  tCount,
  type UiKey,
} from "./i18n";
import {
  bindMailAccountsEvents,
  renderMailAccountsSectionHtml,
} from "./mail";
import {
  bindProfileUploadSectionEvents,
  renderProfileUploadSectionHtml,
} from "./profile_prompt";
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
import type {
  ActionProviderCategory,
  ActionProviderEntry,
  ActionProviderPreset,
  ActionProviderSuggestion,
  BrainEntityItem,
  CloudProviderInfo,
  SettingsLane,
} from "./types";

export interface KnowledgeActions {
  onChangeAppearance?: () => void;
  onReplayTour?: () => void;
  onOpenOnboarding?: () => void;
  onCheckAppUpdate?: () => Promise<void>;
  onInstallAppUpdate?: () => Promise<void>;
  onOpenSettingsChat?: () => void;
  onTogglePauseLearning: (paused: boolean) => void;
  onDeletePassage: (passageId: string) => void;
  onDeleteBrainEntity?: (slug: string) => void;
  onSetDomainTrust?: (domain: string, personalScore: number | null) => void;
  onSearchBrain?: (query: string) => void;
  onOpenSourceUrl?: (url: string, title?: string) => void;
  onSwitchToBrain?: () => void;
  onSwitchToSettings?: () => void;
  onMineSkillProposals?: () => void;
  onAcceptSkillProposal?: (proposalId: string) => void;
  onRejectSkillProposal?: (proposalId: string) => void;
  onRunSkill?: (slug: string) => void;
  onRunEvalSuite?: (evalId?: string, mode?: "deterministic" | "live") => Promise<void>;
  onDeleteEvalCase?: (evalId: string) => Promise<void>;
  onRunRedteamAudit?: () => Promise<void>;
  onCreateProfile?: (name: string, pin: string) => void;
  onUnlockProfile?: (profileId: string, pin: string) => void;
  onUnlockProfileKeychain?: (profileId: string) => void;
  onLockProfile?: () => void;
  onDeleteProfile?: (profileId: string, pin: string) => void;
  onExportProfile?: (profileId: string, pin?: string) => void | Promise<void>;
  onImportProfileFile?: (bundleB64: string, pin: string, localPin?: string) => void | Promise<void>;
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
  onSaveGoogleOAuthConfig?: (payload: {
    client_id?: string;
    client_secret?: string;
    client_secret_json?: string;
    scopes?: string[] | string;
    redirect_port?: number;
  }) => Promise<void>;
  onStartGoogleOAuth?: (payload?: {
    client_id?: string;
    client_secret?: string;
    client_secret_json?: string;
    scopes?: string[] | string;
    connect_gmail?: boolean;
    redirect_port?: number;
  }) => Promise<void>;
  onRefreshGoogleOAuth?: () => Promise<void>;
  onDisconnectGoogleOAuth?: (clearClientConfig: boolean) => Promise<void>;
  onConnectGmailOAuth?: () => Promise<void>;
  onConnectGoogleDrive?: (payload: {
    client_secret_json?: string;
    login_hint?: string;
  }) => Promise<void> | void;
  onConnectOneDrive?: (payload: {
    client_id?: string;
    tenant_id?: string;
    login_hint?: string;
  }) => Promise<void> | void;
  onDisconnectDriveProvider?: (provider: "gdrive" | "onedrive") => Promise<void> | void;
  onMailChanged?: () => Promise<void>;
  onSaveModelConfig?: (payload: Record<string, unknown>) => Promise<void>;
  onSearchHfModels?: (query: string) => Promise<void>;
  onInspectHfRepo?: (repoId: string, token?: string) => Promise<void>;
  onStartHfDownload?: (payload: {
    repo_id: string;
    token?: string;
    target_dir?: string;
    use_as_chat?: boolean;
  }) => Promise<void>;
  onCancelHfDownload?: (downloadId: string) => Promise<void>;
  onPointLocalModel?: (payload: {
    role_slot: string;
    path: string;
    label?: string;
    set_active?: boolean;
  }) => Promise<void>;
  onRemoveLocalModel?: (payload: {
    model_id?: string;
    role_slot?: string;
    delete_files?: boolean;
  }) => Promise<void>;
  onSaveHfToken?: (token: string, clear?: boolean) => Promise<void>;
  onBrowseLocalModelPath?: (mode: "directory" | "file", title?: string) => Promise<string | null>;
  onResetRoutingTelemetry?: (queryType?: string) => Promise<void>;
  onInferProvider?: (input: string, categoryId: string) => Promise<void>;
  onUpsertProvider?: (payload: {
    provider_id?: string;
    category_id: string;
    display_name: string;
    provider_slug?: string;
    mode?: "search_api" | "web_account";
    api_driver?: string;
    domains?: string[];
    url_template?: string;
    vault_service?: string;
    constraints_note?: string;
    priority?: number;
    enabled?: boolean;
    credentials?: {
      api_key?: string;
      username?: string;
      password?: string;
      token?: string;
      cookie?: string;
    };
  }) => Promise<void>;
  onReorderProviders?: (categoryId: string, orderedIds: string[]) => Promise<void>;
  onDeleteProvider?: (providerId: string, deleteCredentials?: boolean) => Promise<void>;
  onTestProvider?: (providerId: string) => Promise<void>;
  onUpsertProviderCategory?: (payload: {
    label: string;
    parent_group?: string;
    description?: string;
  }) => Promise<void>;
  onDeleteProviderCategory?: (categoryId: string) => Promise<void>;
  onResolveProviderSuggestion?: (suggestionId: string, action: "accept" | "dismiss") => Promise<void>;
  onSelectUiLanguage?: (lang: string) => Promise<void>;
  onTranslateUiLanguage?: (lang: string, force?: boolean) => Promise<void>;
  onCancelUiTranslate?: (lang?: string) => Promise<void>;
  onOverrideUiTranslation?: (lang: string, key: string, text?: string, reset?: boolean) => Promise<void>;
  onExportUiPack?: (lang: string) => Promise<void>;
  onImportUiPack?: (rawJson: string) => Promise<void>;
  onUpdateContentTranslation?: (patch: {
    known_languages?: string[];
    primary_language?: string;
    model_preference?: string;
    auto_translate_mail?: boolean;
    auto_translate_news?: boolean;
    mail_include_promos_pings?: boolean;
  }) => Promise<void>;
  onBackfillContentTranslation?: () => Promise<void>;
  onCloseKnowledgeView: () => void;
}

let brainSearchDebounceTimer: ReturnType<typeof setTimeout> | null = null;

function formatProviderGroupLabel(grp: string): string {
  if (grp === "search") return t("prov.grp_search");
  if (grp === "maps") return t("prov.grp_maps");
  if (grp === "commerce") return t("prov.grp_commerce");
  return t("prov.grp_custom");
}

function renderProviderAuthBadgeHtml(p: ActionProviderEntry): string {
  if (p.auth_status === "locked") {
    return `<span class="badge soft">${escapeHtml(t("prov.auth_locked"))}</span>`;
  }
  if (p.auth_status === "api_key") {
    return `<span class="badge ok">${escapeHtml(t("prov.auth_api_key", { label: p.masked_auth_label || "vault.enc" }))}</span>`;
  }
  if (p.auth_status === "login") {
    return `<span class="badge ok">${escapeHtml(t("prov.auth_login", { label: p.masked_auth_label || "saved" }))}</span>`;
  }
  if (p.auth_status === "token_or_cookie") {
    return `<span class="badge ok">${escapeHtml(t("prov.auth_token_cookie"))}</span>`;
  }
  if (p.requires_key) {
    return `<span class="badge soft">${escapeHtml(t("prov.auth_needed"))}</span>`;
  }
  return `<span class="muted">${escapeHtml(t("prov.auth_none"))}</span>`;
}

function renderActionProvidersSectionHtml(forceOpen = false): string {
  const reg = state.providerRegistry;
  const categories: ActionProviderCategory[] = reg?.categories ?? [];
  const byCat = reg?.providers_by_category ?? {};
  const presetsByCat = reg?.presets ?? {};
  const suggestions: ActionProviderSuggestion[] = reg?.suggestions ?? [];
  const isUnlocked = Boolean(state.knowledge.profile?.unlocked);

  const totalConfigured = Object.values(byCat).reduce((acc, list) => acc + list.length, 0);
  const filterGrp = state.providerFilterGroup;
  const visibleCats = categories.filter((c) => {
    if (filterGrp === "all") return true;
    if (filterGrp === "custom") return !c.is_builtin;
    return c.parent_group === filterGrp;
  });

  const accOpen = forceOpen || Boolean(state.settingsAccordionOpen.providers);

  return `
    <div class="card kb-acc-card acc ${accOpen ? "open" : ""}">
      <div class="settings-acc-bar">
        <button type="button" class="acc-h" data-settings-accordion="providers">
          <span>${escapeHtml(t("prov.section"))}</span>
          <span class="ct">${escapeHtml(t("prov.active_ct", { count: totalConfigured }))}${suggestions.length > 0 ? ` · ${escapeHtml(t("prov.suggested_ct", { count: suggestions.length }))}` : ""}</span>
          ${icon("chev", "ico-sm")}
        </button>
        <span class="muted">${escapeHtml(t("prov.section_sub"))}</span>
      </div>
      ${
        !accOpen
          ? ""
          : `
      <div class="acc-b section">
        ${state.providerStatusMsg ? `<div class="banner"><span>${escapeHtml(state.providerStatusMsg)}</span></div>` : ""}
        <div class="muted">
          ${escapeHtml(t("prov.intro"))}
        </div>

        ${
          suggestions.length === 0
            ? ""
            : `
          <div class="card inset">
            <div class="card-h">
              <b>${escapeHtml(t("prov.suggested_title"))}</b>
              <span class="end badge soft">${suggestions.length}</span>
            </div>
            ${suggestions
              .map(
                (sg) => `
              <div class="kb-kv-row">
                <span>
                  <b>${escapeHtml(sg.display_name)}</b> <span class="muted">(${escapeHtml(sg.domain)})</span> -> <b>${escapeHtml(sg.category_id)}</b>
                  <span class="muted">· ${escapeHtml(sg.reason)}</span>
                </span>
                <span class="acts">
                  <button type="button" class="btn primary" data-prov-sug-accept="${escapeHtml(sg.suggestion_id)}">${escapeHtml(t("prov.set_first"))}</button>
                  <button type="button" class="btn-text" data-prov-sug-dismiss="${escapeHtml(sg.suggestion_id)}">${escapeHtml(t("prov.dismiss"))}</button>
                </span>
              </div>
            `
              )
              .join("")}
          </div>
        `
        }

        <div class="form-row">
          <div class="seg" role="group" aria-label="${escapeHtml(t("prov.filter_aria"))}">
            <button type="button" data-prov-group-filter="all" aria-pressed="${filterGrp === "all"}">${escapeHtml(t("prov.all_n", { count: categories.length }))}</button>
            <button type="button" data-prov-group-filter="search" aria-pressed="${filterGrp === "search"}">${escapeHtml(t("prov.grp_search"))}</button>
            <button type="button" data-prov-group-filter="maps" aria-pressed="${filterGrp === "maps"}">${escapeHtml(t("prov.grp_maps"))}</button>
            <button type="button" data-prov-group-filter="commerce" aria-pressed="${filterGrp === "commerce"}">${escapeHtml(t("prov.grp_commerce"))}</button>
            <button type="button" data-prov-group-filter="custom" aria-pressed="${filterGrp === "custom"}">${escapeHtml(t("prov.grp_custom"))}</button>
          </div>
        </div>

        ${
          visibleCats.length === 0
            ? `<div class="muted">${escapeHtml(t("prov.no_cats"))}</div>`
            : visibleCats
                .map((cat) => {
                  const list: ActionProviderEntry[] = byCat[cat.category_id] ?? [];
                  const expanded = state.providerExpandedCategoryId === cat.category_id;
                  const summaryPills =
                    list.length === 0
                      ? `<span class="muted">${escapeHtml(t("prov.no_default"))}</span>`
                      : list
                          .slice(0, 3)
                          .map(
                            (p, idx) =>
                              `<span class="pill">#${idx + 1} ${escapeHtml(p.display_name)}${p.auth_ready ? " · Vault" : ""}</span>`
                          )
                          .join(" ");
                  const existingSlugs = new Set(list.map((x) => x.provider_slug));
                  const presets: ActionProviderPreset[] = (presetsByCat[cat.category_id] ?? []).filter(
                    (pr) => !existingSlugs.has(pr.provider_slug)
                  );
                  const draft = state.providerInferredDraft[cat.category_id];

                  return `
                  <div class="card inset acc ${expanded ? "open" : ""}">
                    <div class="settings-acc-bar">
                      <button type="button" class="acc-h" data-prov-toggle-cat="${escapeHtml(cat.category_id)}">
                        <span class="badge soft">${escapeHtml(formatProviderGroupLabel(cat.parent_group))}</span>
                        <span>${escapeHtml(cat.label)}</span>
                        ${cat.description ? `<span class="muted">${escapeHtml(cat.description)}</span>` : ""}
                        <span class="ct">${list.length}</span>
                        ${icon("chev", "ico-sm")}
                      </button>
                      ${!expanded ? `<span class="acts">${summaryPills}</span>` : ""}
                      ${
                        !cat.is_builtin
                          ? `<button type="button" class="btn-text" data-prov-delete-cat="${escapeHtml(cat.category_id)}">${escapeHtml(t("common.delete"))}</button>`
                          : ""
                      }
                    </div>

                    ${
                      !expanded
                        ? ""
                        : `
                    <div class="acc-b section">
                      ${
                        list.length === 0
                          ? `<div class="muted">${escapeHtml(t("prov.none_in_cat", { label: cat.label }))}</div>`
                          : list
                              .map((p, idx) => {
                                const credOpen = state.providerCredOpenId === p.id;
                                return `
                              <div class="card compact">
                                <div class="kb-kv-row">
                                  <span>
                                    <span class="badge soft">#${idx + 1}</span>
                                    <b>${escapeHtml(p.display_name)}</b>
                                    <span class="muted">(${escapeHtml(p.domains[0] || p.provider_slug)})</span>
                                    <span class="badge">${escapeHtml(p.mode === "search_api" ? t("prov.mode_api") : t("prov.mode_web"))}</span>
                                    ${renderProviderAuthBadgeHtml(p)}
                                    ${p.constraints_note ? `<span class="muted">· ${escapeHtml(p.constraints_note)}</span>` : ""}
                                  </span>
                                  <span class="acts">
                                    <button type="button" class="btn-text" data-prov-move-up="${escapeHtml(p.id)}" data-prov-cat="${escapeHtml(cat.category_id)}" ${idx === 0 ? "disabled" : ""}>${escapeHtml(t("prov.up"))}</button>
                                    <button type="button" class="btn-text" data-prov-move-down="${escapeHtml(p.id)}" data-prov-cat="${escapeHtml(cat.category_id)}" ${idx === list.length - 1 ? "disabled" : ""}>${escapeHtml(t("prov.down"))}</button>
                                    <button type="button" class="btn-text" data-prov-test="${escapeHtml(p.id)}">${escapeHtml(t("prov.test"))}</button>
                                    <button type="button" class="btn-text" data-prov-cred-toggle="${escapeHtml(p.id)}">${escapeHtml(credOpen ? t("prov.close_creds") : p.auth_ready ? t("prov.edit_vault") : t("prov.add_creds"))}</button>
                                    <button type="button" class="btn-text" data-prov-delete="${escapeHtml(p.id)}">${escapeHtml(t("news.remove"))}</button>
                                  </span>
                                </div>
                                ${
                                  !credOpen
                                    ? ""
                                    : !isUnlocked
                                      ? `<div class="muted mt-2">${escapeHtml(t("prov.unlock_to_edit", { service: p.vault_service }))}</div>`
                                      : `
                                    <div class="form-row mt-2">
                                      ${
                                        p.mode === "search_api"
                                          ? `<input type="password" class="input" data-prov-cred-apikey="${escapeHtml(p.id)}" placeholder="${escapeHtml(t("prov.apikey_ph", { service: p.vault_service }))}" />`
                                          : `
                                            <input type="text" class="input" data-prov-cred-user="${escapeHtml(p.id)}" placeholder="${escapeHtml(t("prov.user_opt_ph"))}" value="${p.auth_status === "login" ? escapeHtml(p.masked_auth_label) : ""}" />
                                            <input type="password" class="input" data-prov-cred-pass="${escapeHtml(p.id)}" placeholder="${escapeHtml(t("prov.pass_opt_ph"))}" />
                                            <input type="password" class="input" data-prov-cred-token="${escapeHtml(p.id)}" placeholder="${escapeHtml(t("prov.token_opt_ph"))}" />
                                          `
                                      }
                                      <input type="text" class="input" data-prov-cred-note="${escapeHtml(p.id)}" placeholder="${escapeHtml(t("prov.note_ph"))}" value="${escapeHtml(p.constraints_note)}" />
                                      <button type="button" class="btn primary" data-prov-cred-save="${escapeHtml(p.id)}" data-prov-cat="${escapeHtml(cat.category_id)}">${escapeHtml(t("prov.save_vault"))}</button>
                                    </div>
                                  `
                                }
                              </div>
                            `;
                              })
                              .join("")
                      }

                      ${
                        presets.length === 0
                          ? ""
                          : `
                        <div class="form-row">
                          <span class="muted">${escapeHtml(t("prov.quick_add"))}</span>
                          ${presets
                            .map(
                              (pr) =>
                                `<button type="button" class="btn" data-prov-quick-add="${escapeHtml(pr.provider_slug)}" data-prov-cat="${escapeHtml(cat.category_id)}">+ ${escapeHtml(pr.display_name)}</button>`
                            )
                            .join("")}
                        </div>
                      `
                      }

                      <div class="form-row">
                        <input
                          type="text"
                          class="input"
                          data-prov-add-raw="${escapeHtml(cat.category_id)}"
                          placeholder="${escapeHtml(t("prov.add_raw_ph"))}"
                          value="${draft ? escapeHtml(draft.domains[0] || "") : ""}"
                        />
                        <button type="button" class="btn" data-prov-detect-btn="${escapeHtml(cat.category_id)}">${escapeHtml(t("prov.detect"))}</button>
                        <button type="button" class="btn primary" data-prov-add-btn="${escapeHtml(cat.category_id)}">${escapeHtml(t("prov.add_btn"))}</button>
                      </div>
                      <details ${draft ? "open" : ""}>
                        <summary class="muted pointer">${escapeHtml(t("prov.advanced_summary", { query: "{query}" }))}</summary>
                        <div class="form-row mt-2">
                          <input type="text" class="input" data-prov-add-name="${escapeHtml(cat.category_id)}" placeholder="${escapeHtml(t("prov.display_name_ph"))}" value="${draft ? escapeHtml(draft.display_name) : ""}" />
                          <input type="text" class="input" data-prov-add-tpl="${escapeHtml(cat.category_id)}" placeholder="${escapeHtml(t("prov.url_tpl_ph", { query: "{query}" }))}" value="${draft ? escapeHtml(draft.url_template) : ""}" />
                          <select class="select" data-prov-add-mode="${escapeHtml(cat.category_id)}">
                            <option value="web_account" ${draft?.mode === "search_api" ? "" : "selected"}>${escapeHtml(t("prov.mode_web_acct"))}</option>
                            <option value="search_api" ${draft?.mode === "search_api" ? "selected" : ""}>${escapeHtml(t("prov.mode_api"))}</option>
                          </select>
                          <input type="text" class="input" data-prov-add-note="${escapeHtml(cat.category_id)}" placeholder="${escapeHtml(t("prov.pref_note_opt_ph"))}" />
                        </div>
                        ${
                          draft?.auth_ready
                            ? `<div class="muted mt-1">${escapeHtml(t("prov.vault_match", { service: draft.vault_service, label: draft.masked_auth_label }))}</div>`
                            : ""
                        }
                      </details>
                    </div>
                  `
                    }
                  </div>
                `;
                })
                .join("")
        }

        <div class="form-row mt-2">
          <select id="kb-prov-new-cat-group" class="select">
            <option value="search">${escapeHtml(t("prov.grp_search"))}</option>
            <option value="maps">${escapeHtml(t("prov.grp_maps_nav"))}</option>
            <option value="commerce">${escapeHtml(t("prov.grp_commerce"))}</option>
            <option value="custom" selected>${escapeHtml(t("prov.grp_custom"))}</option>
          </select>
          <input id="kb-prov-new-cat-label" class="input" type="text" placeholder="${escapeHtml(t("prov.new_cat_ph"))}" />
          <input id="kb-prov-new-cat-desc" class="input" type="text" placeholder="${escapeHtml(t("prov.new_cat_desc_ph"))}" />
          <button id="kb-prov-add-cat-btn" type="button" class="btn">${escapeHtml(t("prov.add_cat_btn"))}</button>
        </div>
      </div>
      `
      }
    </div>
  `;
}

function bindActionProvidersListeners(
  container: HTMLElement,
  actions: KnowledgeActions
): void {
  container.querySelectorAll<HTMLButtonElement>("[data-prov-group-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const g = (btn.getAttribute("data-prov-group-filter") || "all") as typeof state.providerFilterGroup;
      state.providerFilterGroup = g;
      renderKnowledgeView(container, actions);
    });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-prov-toggle-cat]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const cid = btn.getAttribute("data-prov-toggle-cat") ?? "";
      state.providerExpandedCategoryId = state.providerExpandedCategoryId === cid ? "" : cid;
      renderKnowledgeView(container, actions);
    });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-prov-delete-cat]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const cid = btn.getAttribute("data-prov-delete-cat") ?? "";
      if (cid) void actions.onDeleteProviderCategory?.(cid);
    });
  });

  container.querySelector("#kb-prov-add-cat-btn")?.addEventListener("click", () => {
    const grp = (container.querySelector("#kb-prov-new-cat-group") as HTMLSelectElement | null)?.value ?? "custom";
    const lbl = (container.querySelector("#kb-prov-new-cat-label") as HTMLInputElement | null)?.value.trim() ?? "";
    const desc = (container.querySelector("#kb-prov-new-cat-desc") as HTMLInputElement | null)?.value.trim() ?? "";
    if (!lbl) return;
    void actions.onUpsertProviderCategory?.({ label: lbl, parent_group: grp, description: desc });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-prov-sug-accept]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const sid = btn.getAttribute("data-prov-sug-accept") ?? "";
      if (sid) void actions.onResolveProviderSuggestion?.(sid, "accept");
    });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-prov-sug-dismiss]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const sid = btn.getAttribute("data-prov-sug-dismiss") ?? "";
      if (sid) void actions.onResolveProviderSuggestion?.(sid, "dismiss");
    });
  });

  const moveProvider = (pid: string, cid: string, delta: number) => {
    const list = state.providerRegistry?.providers_by_category?.[cid] ?? [];
    const idx = list.findIndex((x) => x.id === pid);
    if (idx < 0 || idx + delta < 0 || idx + delta >= list.length) return;
    const ordered = list.map((x) => x.id);
    const [moved] = ordered.splice(idx, 1);
    ordered.splice(idx + delta, 0, moved);
    void actions.onReorderProviders?.(cid, ordered);
  };

  container.querySelectorAll<HTMLButtonElement>("[data-prov-move-up]").forEach((btn) => {
    btn.addEventListener("click", () => {
      moveProvider(btn.getAttribute("data-prov-move-up") ?? "", btn.getAttribute("data-prov-cat") ?? "", -1);
    });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-prov-move-down]").forEach((btn) => {
    btn.addEventListener("click", () => {
      moveProvider(btn.getAttribute("data-prov-move-down") ?? "", btn.getAttribute("data-prov-cat") ?? "", 1);
    });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-prov-test]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = btn.getAttribute("data-prov-test") ?? "";
      if (pid) void actions.onTestProvider?.(pid);
    });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-prov-delete]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = btn.getAttribute("data-prov-delete") ?? "";
      if (pid) void actions.onDeleteProvider?.(pid, false);
    });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-prov-cred-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = btn.getAttribute("data-prov-cred-toggle") ?? "";
      state.providerCredOpenId = state.providerCredOpenId === pid ? "" : pid;
      renderKnowledgeView(container, actions);
    });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-prov-cred-save]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = btn.getAttribute("data-prov-cred-save") ?? "";
      const cid = btn.getAttribute("data-prov-cat") ?? "";
      const prov = (state.providerRegistry?.providers_by_category?.[cid] ?? []).find((x) => x.id === pid);
      if (!prov || !actions.onUpsertProvider) return;
      const apiKey = (container.querySelector(`[data-prov-cred-apikey="${pid}"]`) as HTMLInputElement | null)?.value.trim() ?? "";
      const username = (container.querySelector(`[data-prov-cred-user="${pid}"]`) as HTMLInputElement | null)?.value.trim() ?? "";
      const password = (container.querySelector(`[data-prov-cred-pass="${pid}"]`) as HTMLInputElement | null)?.value.trim() ?? "";
      const token = (container.querySelector(`[data-prov-cred-token="${pid}"]`) as HTMLInputElement | null)?.value.trim() ?? "";
      const note = (container.querySelector(`[data-prov-cred-note="${pid}"]`) as HTMLInputElement | null)?.value.trim() ?? "";
      const creds: Record<string, string> = {};
      if (apiKey) creds.api_key = apiKey;
      if (username) creds.username = username;
      if (password) creds.password = password;
      if (token) creds.token = token;
      void actions.onUpsertProvider({
        provider_id: prov.id,
        category_id: prov.category_id,
        display_name: prov.display_name,
        provider_slug: prov.provider_slug,
        mode: prov.mode,
        api_driver: prov.api_driver,
        domains: prov.domains,
        url_template: prov.url_template,
        vault_service: prov.vault_service,
        constraints_note: note,
        priority: prov.priority,
        enabled: prov.enabled,
        ...(Object.keys(creds).length > 0 ? { credentials: creds } : {}),
      });
    });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-prov-quick-add]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const slug = btn.getAttribute("data-prov-quick-add") ?? "";
      const cid = btn.getAttribute("data-prov-cat") ?? "";
      const preset = (state.providerRegistry?.presets?.[cid] ?? []).find((x) => x.provider_slug === slug);
      if (!preset || !actions.onUpsertProvider) return;
      void actions.onUpsertProvider({
        category_id: cid,
        display_name: preset.display_name,
        provider_slug: preset.provider_slug,
        mode: preset.mode,
        api_driver: preset.api_driver,
        domains: preset.domains,
        url_template: preset.url_template,
        vault_service: preset.vault_service,
      });
    });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-prov-detect-btn]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const cid = btn.getAttribute("data-prov-detect-btn") ?? "";
      const rawVal = (container.querySelector(`[data-prov-add-raw="${cid}"]`) as HTMLInputElement | null)?.value.trim() ?? "";
      if (cid && rawVal) void actions.onInferProvider?.(rawVal, cid);
    });
  });

  container.querySelectorAll<HTMLButtonElement>("[data-prov-add-btn]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const cid = btn.getAttribute("data-prov-add-btn") ?? "";
      if (!cid || !actions.onUpsertProvider) return;
      const rawVal = (container.querySelector(`[data-prov-add-raw="${cid}"]`) as HTMLInputElement | null)?.value.trim() ?? "";
      const nameIn = (container.querySelector(`[data-prov-add-name="${cid}"]`) as HTMLInputElement | null)?.value.trim() ?? "";
      const tplIn = (container.querySelector(`[data-prov-add-tpl="${cid}"]`) as HTMLInputElement | null)?.value.trim() ?? "";
      const modeIn = ((container.querySelector(`[data-prov-add-mode="${cid}"]`) as HTMLSelectElement | null)?.value ?? "web_account") as "search_api" | "web_account";
      const noteIn = (container.querySelector(`[data-prov-add-note="${cid}"]`) as HTMLInputElement | null)?.value.trim() ?? "";
      const draft = state.providerInferredDraft[cid];
      if (!rawVal && !nameIn) return;
      if (rawVal && !nameIn && !draft && actions.onInferProvider) {
        await actions.onInferProvider(rawVal, cid);
      }
      const dAfter = state.providerInferredDraft[cid];
      const effName = nameIn || dAfter?.display_name || rawVal;
      const effTpl = tplIn || dAfter?.url_template || (rawVal.startsWith("http") ? rawVal : `https://${rawVal.replace(/^https?:\/\//i, "")}`);
      const effDoms = dAfter?.domains ?? (rawVal && !rawVal.includes(" ") ? [rawVal.replace(/^https?:\/\//i, "").split("/")[0]] : []);
      delete state.providerInferredDraft[cid];
      await actions.onUpsertProvider({
        category_id: cid,
        display_name: effName,
        provider_slug: dAfter?.display_name ? undefined : effName.toLowerCase().replace(/[^a-z0-9]+/g, "_"),
        mode: dAfter?.mode ?? modeIn,
        api_driver: dAfter?.api_driver ?? "",
        domains: effDoms,
        url_template: effTpl,
        vault_service: dAfter?.vault_service ?? "",
        constraints_note: noteIn,
      });
    });
  });
}

function renderOverrideRowsHtml(filterRaw: string): string {
  const activeEntries = getActiveLocaleEntries();
  const q = filterRaw.trim().toLowerCase();
  const allKeys = Object.keys(EN_CATALOG) as UiKey[];
  const matched = q
    ? allKeys.filter((k) => {
        const src = EN_CATALOG[k]?.text ?? "";
        const loc = activeEntries[k]?.text ?? "";
        return (
          k.toLowerCase().includes(q) ||
          src.toLowerCase().includes(q) ||
          loc.toLowerCase().includes(q)
        );
      })
    : allKeys;

  return matched
    .slice(0, 40)
    .map((k) => {
      const srcText = EN_CATALOG[k]?.text ?? "";
      const ent = activeEntries[k];
      const curText = ent?.text ?? "";
      const isCustom = Boolean(ent?.custom);
      return `
        <tr>
          <td class="mono muted">${escapeHtml(k)}${isCustom ? ` <span class="badge soft">${escapeHtml(t("i18n.custom_badge"))}</span>` : ""}</td>
          <td>${escapeHtml(srcText)}</td>
          <td>
            <input
              type="text"
              class="input"
              data-kb-lang-override-input="${escapeHtml(k)}"
              value="${escapeHtml(curText)}"
              placeholder="${escapeHtml(srcText)}"
            />
          </td>
          <td>
            <button type="button" class="btn-text" data-kb-lang-override-save="${escapeHtml(k)}">${escapeHtml(t("common.save"))}</button>
            ${
              ent
                ? `<button type="button" class="btn-text" data-kb-lang-override-reset="${escapeHtml(k)}">${escapeHtml(t("common.reset"))}</button>`
                : ""
            }
          </td>
        </tr>
      `;
    })
    .join("");
}

function renderKbBannerHtml(msg: string): string {
  const low = msg.toLowerCase();
  const cls =
    low.includes("error") ||
    low.includes("failed") ||
    msg.startsWith(t("common.error_prefix"))
      ? "banner danger"
      : "banner";
  return `<div class="${cls}">${escapeHtml(msg)}</div>`;
}

function renderAppLanguageSectionHtml(): string {
  const st = state.i18nStatus;
  const activeLocale = getUiLocale();
  const activeLabel = st?.active_label || getUiLocaleLabel();
  const activeDir = st?.active_dir || getUiLocaleDir();
  const locales = st?.locales ?? [];
  const hasActiveInList = locales.some((x) => x.lang === activeLocale);
  const nonEnLocales = locales.filter((x) => x.lang !== "en");
  const targetStats =
    locales.find((x) => x.lang === activeLocale) ?? st?.target;
  const missingCount = targetStats?.missing ?? 0;
  const staleCount = targetStats?.stale ?? 0;
  const customCount = targetStats?.custom_count ?? 0;
  const totalKeys = targetStats?.total || Object.keys(EN_CATALOG).length;
  const isJobRunning = Boolean(
    state.i18nTranslating || (st?.job?.running && st.job.lang === activeLocale)
  );
  const doneCount = state.i18nTranslating
    ? state.i18nTranslateCompleted
    : st?.job?.running
      ? st.job.completed
      : targetStats?.translated ?? 0;
  const goalCount = state.i18nTranslating
    ? Math.max(1, state.i18nTranslateTotal || missingCount + staleCount || totalKeys)
    : st?.job?.running
      ? Math.max(1, st.job.total || totalKeys)
      : Math.max(1, totalKeys);
  const pct = Math.min(100, Math.max(0, Math.round((doneCount / goalCount) * 100)));

  const modelId = st?.model_info?.model_id || state.modelConfig?.roles?.chat || "gemma-4-e4b";
  const privacyLine = st?.model_info
    ? st.model_info.local_only
      ? t("i18n.privacy_local", { model: modelId })
      : t("i18n.privacy_cloud", { model: modelId, host: st.model_info.host })
    : t("i18n.privacy_local", { model: modelId });

  const suggested = st?.suggested_languages ?? [];
  const datalistHtml = suggested
    .filter((item) => item.code !== "en")
    .map(
      (item) =>
        `<option value="${escapeHtml(item.native)}">${escapeHtml(item.name)} (${escapeHtml(item.code)})</option>`
    )
    .join("");

  return `
    <div id="kb-app-language-slot" class="kb-app-lang-block">
      <div class="form-row">
        <span class="muted">${escapeHtml(t("i18n.label"))}</span>
        <select id="kb-lang-select" class="select" aria-label="${escapeHtml(t("i18n.label"))}">
          <option value="en" ${activeLocale === "en" ? "selected" : ""}>${escapeHtml(t("i18n.english_canonical"))}</option>
          ${nonEnLocales
            .map((loc) => {
              const covPct = loc.total > 0 ? Math.round((loc.translated / loc.total) * 100) : 100;
              return `<option value="${escapeHtml(loc.lang)}" ${activeLocale === loc.lang ? "selected" : ""}>${escapeHtml(
                t("i18n.pack_option", { label: loc.label, lang: loc.lang, pct: covPct })
              )}</option>`;
            })
            .join("")}
          ${
            activeLocale !== "en" && !hasActiveInList
              ? `<option value="${escapeHtml(activeLocale)}" selected>${escapeHtml(activeLabel)} (${escapeHtml(activeLocale)})</option>`
              : ""
          }
        </select>
        ${activeDir === "rtl" ? `<span class="badge soft">${escapeHtml(t("i18n.rtl_badge"))}</span>` : ""}
        <input
          id="kb-lang-custom-input"
          class="input"
          type="text"
          list="kb-lang-datalist"
          spellcheck="false"
          autocomplete="off"
          placeholder="${escapeHtml(t("i18n.custom_lang_ph"))}"
        />
        <datalist id="kb-lang-datalist">${datalistHtml}</datalist>
        <button id="kb-lang-translate-btn" type="button" class="btn primary" ${isJobRunning ? "disabled" : ""}>
          ${escapeHtml(
            isJobRunning
              ? t("i18n.translating_pct", { done: doneCount, total: goalCount })
              : t("i18n.translate_apply")
          )}
        </button>
        ${
          activeLocale !== "en" && !isJobRunning && missingCount + staleCount > 0
            ? `<button id="kb-lang-sync-missing-btn" type="button" class="btn">${escapeHtml(t("i18n.sync_missing_n", { count: missingCount + staleCount }))}</button>`
            : ""
        }
        ${
          activeLocale !== "en" && !isJobRunning
            ? `<button id="kb-lang-retranslate-btn" type="button" class="btn">${escapeHtml(t("i18n.retranslate_all"))}</button>`
            : ""
        }
        ${
          isJobRunning
            ? `<button id="kb-lang-cancel-btn" type="button" class="btn">${escapeHtml(t("common.cancel"))}</button>`
            : ""
        }
      </div>
      <div class="kb-app-lang-meta">
        <span class="muted">${escapeHtml(privacyLine)}</span>
        <div class="kb-app-lang-actions">
          ${
            activeLocale !== "en"
              ? `
                <button id="kb-lang-customize-toggle" type="button" class="btn-text">
                  ${escapeHtml(state.i18nCustomEditorOpen ? t("i18n.customize_open") : t("i18n.customize_closed", { count: customCount }))}
                </button>
                <button id="kb-lang-export-btn" type="button" class="btn-text">${escapeHtml(t("i18n.export_btn"))}</button>
              `
              : ""
          }
          <label class="btn-text pointer">
            <span>${escapeHtml(t("i18n.import_btn"))}</span>
            <input id="kb-lang-import-input" type="file" accept=".json" class="hidden" />
          </label>
        </div>
      </div>
      ${
        isJobRunning
          ? `
            <div class="kb-app-lang-progress">
              <div class="meter" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}">
                <b style="--v:${pct}%"></b>
              </div>
              <span class="badge soft">${escapeHtml(t("i18n.bg_sync_badge", { done: doneCount, total: goalCount }))}</span>
            </div>
          `
          : activeLocale !== "en" && targetStats
            ? `<div class="muted">${escapeHtml(
                t("i18n.coverage_line", {
                  translated: targetStats.translated,
                  total: targetStats.total,
                  missing: missingCount,
                  stale: staleCount,
                })
              )}</div>`
            : ""
      }
      ${state.i18nStatusMsg ? renderKbBannerHtml(state.i18nStatusMsg) : ""}
      ${
        state.i18nCustomEditorOpen && activeLocale !== "en"
          ? `
            <div class="card inset kb-app-lang-editor">
              <div class="form-row">
                <input
                  id="kb-lang-override-filter"
                  class="input"
                  type="text"
                  spellcheck="false"
                  placeholder="${escapeHtml(t("i18n.override_filter_ph"))}"
                  value="${escapeHtml(state.i18nOverrideFilter)}"
                />
              </div>
              <div class="table-wrap">
                <table class="table">
                  <thead>
                    <tr>
                      <th>${escapeHtml(t("i18n.col_key"))}</th>
                      <th>${escapeHtml(t("i18n.col_english"))}</th>
                      <th>${escapeHtml(t("i18n.col_translation", { lang: activeLocale }))}</th>
                      <th>${escapeHtml(t("mail.col_actions"))}</th>
                    </tr>
                  </thead>
                  <tbody id="kb-lang-override-tbody">
                    ${renderOverrideRowsHtml(state.i18nOverrideFilter)}
                  </tbody>
                </table>
              </div>
            </div>
          `
          : ""
      }
    </div>
  `;
}

export function renderKnowledgeEmbedded(
  container: HTMLElement,
  actions: KnowledgeActions
): void {
  renderKnowledgeView(container, actions, null, true);
}

export function renderKnowledgeView(
  container: HTMLElement,
  actions: KnowledgeActions,
  laneFilter: SettingsLane | null = null,
  embedded?: boolean
): void {
  const isEmbedded = embedded ?? container.dataset.kbEmbedded === "1";
  if (embedded !== undefined) {
    container.dataset.kbEmbedded = embedded ? "1" : "";
  }
  const activeLane: SettingsLane | null = laneFilter;
  const isLaneView = activeLane !== null;
  const kb = state.knowledge;
  const brainEntities = kb.brain?.entities ?? [];
  const brainRankingLabel =
    kb.brain?.brain_ranking ??
    kb.brain?.encoder?.label ??
    t("settings.ranking_lexical");
  const bookmarksIndexed = kb.bookmarks_indexed ?? [];
  const profileInfo = kb.profile;
  const profilesList = profileInfo?.profiles ?? [];
  const isUnlocked = Boolean(profileInfo?.unlocked && profileInfo?.active_profile);
  const activeProfile = profileInfo?.active_profile ?? null;
  const vault = kb.vault;
  const vaultServices = vault?.services ?? [];
  const doctorRoles = state.doctorRoles ?? [];
  const acc = isLaneView
    ? {
        ...state.settingsAccordionOpen,
        models: activeLane === "models" ? true : state.settingsAccordionOpen.models,
        profiles: activeLane === "profiles" ? true : state.settingsAccordionOpen.profiles,
        vault: activeLane === "profiles" ? true : state.settingsAccordionOpen.vault,
        providers: activeLane === "providers" ? true : state.settingsAccordionOpen.providers,
        mail: activeLane === "google_mail" ? true : state.settingsAccordionOpen.mail,
        indexing: activeLane === "sources" ? true : state.settingsAccordionOpen.indexing,
        translation: activeLane === "translation" ? true : state.settingsAccordionOpen.translation,
      }
    : state.settingsAccordionOpen;
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
      privacy_disclosure: t("settings.cloud_disclosure", { host: "generativelanguage.googleapis.com" }),
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
      privacy_disclosure: t("settings.cloud_disclosure", { host: "api.anthropic.com" }),
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
      privacy_disclosure: t("settings.cloud_disclosure", { host: "api.openai.com" }),
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
      privacy_disclosure: t("settings.cloud_disclosure", { host: "api.mistral.ai" }),
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
      ? t("settings.cloud_summary", { items: configuredCloudProviders.map((p) => `${p.id} (${(p.models ?? []).length})`).join(" · ") })
      : t("settings.local_only_summary");

  const localSnap = modelCfg?.local_models ?? null;
  const gemmaReady = localSnap
    ? Boolean(localSnap.gemma_ready)
    : doctorRoles.find((d) => d.role === "chat")?.state !== "missing";
  const customLocalLlms = localSnap?.custom_llms ?? [];
  const hfCatalog = localSnap?.hf_catalog ?? [];
  const hfDownloads =
    state.hfDownloads.length > 0 ? state.hfDownloads : (localSnap?.downloads ?? []);
  const slotOverrideMap = localSnap?.overrides ?? {};
  const selectedSlotHasOverride = Boolean(
    (state.localModelSlotDraft === "chat_llm" || state.localModelSlotDraft === "gemma_override")
      ? slotOverrideMap.chat_llm_path
      : state.localModelSlotDraft === "reader_hertz"
        ? slotOverrideMap.hertz_reader_path
        : state.localModelSlotDraft === "reader_planck"
          ? slotOverrideMap.planck_reader_path
          : state.localModelSlotDraft === "brain_encoder"
            ? slotOverrideMap.planck13_encoder_path
            : ""
  );
  const fmtBytes = (bytes?: number) => {
    const b = Number(bytes ?? 0);
    if (!b || b <= 0) return "";
    if (b >= 1024 ** 3) return `${(b / 1024 ** 3).toFixed(2)} GB`;
    if (b >= 1024 ** 2) return `${(b / 1024 ** 2).toFixed(1)} MB`;
    return `${Math.round(b / 1024)} KB`;
  };
  const renderLocalLlmOptionsHtml = (selectedRoleVal: string) =>
    customLocalLlms
      .map(
        (lm) =>
          `<option value="${escapeHtml(lm.id)}" ${selectedRoleVal === lm.id ? "selected" : ""}>${escapeHtml(lm.label)} (local${lm.ready ? "" : " · invalid"})</option>`
      )
      .join("");
  const gemmaOptionLabel = gemmaReady
    ? "gemma-4-e4b (local · default)"
    : "gemma-4-e4b (local · not installed)";
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
            <span>${escapeHtml(t("settings.models_section"))}</span>
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
                <b>${escapeHtml(t("settings.role_matrix_title"))}</b>
                <span class="end muted">${escapeHtml(t("settings.role_matrix_note"))}</span>
              </div>
              <div class="form-row">
                <div class="kb-form-field">
                  <label for="kb-role-chat-select">${escapeHtml(t("settings.role_chat"))}</label>
                  <select id="kb-role-chat-select" class="select">
                    <option value="gemma-4-e4b" ${roleChat === "gemma-4-e4b" ? "selected" : ""}>${escapeHtml(gemmaOptionLabel)}</option>
                    ${renderLocalLlmOptionsHtml(roleChat)}
                    ${renderCloudOptionsHtml(roleChat)}
                  </select>
                </div>
                <div class="kb-form-field">
                  <label for="kb-role-web-select">${escapeHtml(t("settings.role_web"))}</label>
                  <select id="kb-role-web-select" class="select">
                    <option value="planck3 (web)" ${roleWeb === "planck3 (web)" ? "selected" : ""}>planck3 (local read-weigh-write)</option>
                    ${renderCloudOptionsHtml(roleWeb)}
                  </select>
                </div>
                <div class="kb-form-field">
                  <label for="kb-role-reader-select">${escapeHtml(t("settings.role_reader"))}</label>
                  <select id="kb-role-reader-select" class="select">
                    <option value="hertz (reader)" ${roleReader === "hertz (reader)" ? "selected" : ""}>hertz 1.2 (local extractive)</option>
                    <option value="planck (reader)" ${roleReader === "planck (reader)" ? "selected" : ""}>planck (local extractive · shipped)</option>
                    <option value="gemma-4-e4b" ${roleReader === "gemma-4-e4b" ? "selected" : ""}>${escapeHtml(gemmaOptionLabel)}</option>
                    ${renderLocalLlmOptionsHtml(roleReader)}
                    ${renderCloudOptionsHtml(roleReader)}
                  </select>
                </div>
              </div>
              <div class="form-row">
                <div class="kb-form-field">
                  <label for="kb-role-news-planner-select">${escapeHtml(t("settings.role_news_planner"))}</label>
                  <select id="kb-role-news-planner-select" class="select">
                    <option value="gemma-4-e4b" ${roleNewsPlanner === "gemma-4-e4b" ? "selected" : ""}>${escapeHtml(gemmaOptionLabel)}</option>
                    ${renderLocalLlmOptionsHtml(roleNewsPlanner)}
                    ${renderCloudOptionsHtml(roleNewsPlanner)}
                  </select>
                </div>
                <div class="kb-form-field">
                  <label for="kb-role-news-capture-select">${escapeHtml(t("settings.role_news_translate"))}</label>
                  <select id="kb-role-news-capture-select" class="select">
                    <option value="gemma-4-e4b" ${roleNewsCapture === "gemma-4-e4b" ? "selected" : ""}>${escapeHtml(gemmaOptionLabel)}</option>
                    ${renderLocalLlmOptionsHtml(roleNewsCapture)}
                    ${renderCloudOptionsHtml(roleNewsCapture)}
                  </select>
                </div>
                <div class="kb-form-field">
                  <label for="kb-role-news-reader-select">${escapeHtml(t("settings.role_news_reader"))}</label>
                  <select id="kb-role-news-reader-select" class="select">
                    <option value="hertz (reader)" ${roleNewsReader === "hertz (reader)" ? "selected" : ""}>hertz 1.2 (local int8)</option>
                    <option value="planck (reader)" ${roleNewsReader === "planck (reader)" ? "selected" : ""}>planck (local reader · shipped)</option>
                    <option value="heuristic" ${roleNewsReader === "heuristic" ? "selected" : ""}>heuristic lexical</option>
                    <option value="gemma-4-e4b" ${roleNewsReader === "gemma-4-e4b" ? "selected" : ""}>${escapeHtml(gemmaOptionLabel)}</option>
                    ${renderLocalLlmOptionsHtml(roleNewsReader)}
                    ${renderCloudOptionsHtml(roleNewsReader)}
                  </select>
                </div>
                <div class="kb-form-field">
                  <label for="kb-role-news-analyzer-select">${escapeHtml(t("settings.role_news_analyzer"))}</label>
                  <select id="kb-role-news-analyzer-select" class="select">
                    <option value="gemma-4-e4b" ${roleNewsAnalyzer === "gemma-4-e4b" ? "selected" : ""}>${escapeHtml(gemmaOptionLabel)}</option>
                    ${renderLocalLlmOptionsHtml(roleNewsAnalyzer)}
                    <option value="template" ${roleNewsAnalyzer === "template" ? "selected" : ""}>template extractive</option>
                    ${renderCloudOptionsHtml(roleNewsAnalyzer)}
                  </select>
                </div>
                <button id="kb-save-roles-btn" type="button" class="btn primary">${escapeHtml(t("settings.apply_roles"))}</button>
              </div>
            </div>

            ${state.modelConfigStatusMsg ? renderKbBannerHtml(state.modelConfigStatusMsg) : ""}

            <div class="label">${escapeHtml(t("settings.lm_packaging_label"))}</div>
            <div class="card inset lm-subcard">
              <div class="card-h">
                <b>${escapeHtml(t("settings.lm_hf_title"))}</b>
                <span class="end badge soft">${escapeHtml(
                  t("settings.lm_shipped_ok", {
                    reader: `planck:${localSnap?.planck_reader_source ?? "shipped"}`,
                    encoder: `planck13:${localSnap?.planck13_source ?? "shipped"}`,
                  })
                )}</span>
              </div>
              ${
                localSnap?.models_dir
                  ? `<div class="lm-inline-meta">${escapeHtml(t("settings.lm_hf_sub", { dir: localSnap.models_dir }))}</div>`
                  : ""
              }
              <div class="form-row">
                <input
                  id="kb-hf-search-input"
                  class="input"
                  type="text"
                  value="${escapeHtml(state.hfSearchQuery)}"
                  placeholder="${escapeHtml(t("settings.lm_hf_search_ph"))}"
                />
                <button id="kb-hf-search-btn" type="button" class="btn">${escapeHtml(t("settings.lm_hf_search_btn"))}</button>
              </div>
              ${
                state.hfSearchResults.length > 0
                  ? `<div class="lm-chip-row">${state.hfSearchResults
                      .map(
                        (r) =>
                          `<button type="button" class="btn" data-hf-pick-repo="${escapeHtml(r.repo_id)}" title="${escapeHtml(r.notes ?? "")}">${escapeHtml(r.repo_id)}${r.gated ? " (gated)" : ""}</button>`
                      )
                      .join("")}</div>`
                  : hfCatalog.length > 0
                    ? `<div>
                         <div class="muted">${escapeHtml(t("settings.lm_hf_presets"))}</div>
                         <div class="lm-chip-row">${hfCatalog
                           .map(
                             (c) =>
                               `<button type="button" class="btn" data-hf-pick-repo="${escapeHtml(c.repo_id)}" title="${escapeHtml(c.notes)}">${escapeHtml(c.label)} · ${escapeHtml(c.approx_size)}${c.gated ? " (gated)" : ""}</button>`
                           )
                           .join("")}</div>
                       </div>`
                    : ""
              }
              <div class="form-row">
                <input
                  id="kb-hf-repo-input"
                  class="input"
                  type="text"
                  spellcheck="false"
                  value="${escapeHtml(state.hfRepoDraft)}"
                  placeholder="${escapeHtml(t("settings.lm_hf_repo_ph"))}"
                />
                <button id="kb-hf-inspect-btn" type="button" class="btn">${escapeHtml(t("settings.lm_hf_inspect_btn"))}</button>
                <button id="kb-hf-download-btn" type="button" class="btn primary">${escapeHtml(t("settings.lm_hf_download_btn"))}</button>
              </div>
              ${
                state.hfInspectResult
                  ? state.hfInspectResult.error
                    ? `<div class="muted">${escapeHtml(state.hfInspectResult.error)}</div>`
                    : `<div class="muted">${escapeHtml(
                        t("settings.lm_hf_inspect_summary", {
                          repo: state.hfInspectResult.repo_id,
                          count: state.hfInspectResult.file_count ?? 0,
                          size: fmtBytes(state.hfInspectResult.total_bytes) || "unknown size",
                          gated: state.hfInspectResult.gated ? t("settings.lm_hf_gated_tag") : "",
                        })
                      )}</div>`
                  : ""
              }
              <div class="form-row">
                <input
                  id="kb-hf-token-input"
                  class="input"
                  type="password"
                  spellcheck="false"
                  placeholder="${escapeHtml(t("settings.lm_hf_token_ph"))}"
                />
                <button id="kb-hf-token-save-btn" type="button" class="btn">${escapeHtml(t("settings.lm_hf_token_save_btn"))}</button>
                ${
                  localSnap?.hf_token_configured
                    ? `<span class="badge soft">${escapeHtml(t("settings.lm_hf_token_saved", { masked: localSnap.hf_token_masked || "***" }))}</span>
                       <button id="kb-hf-token-clear-btn" type="button" class="btn danger">${escapeHtml(t("settings.lm_hf_token_clear_btn"))}</button>`
                    : ""
                }
              </div>
              ${
                hfDownloads.length > 0
                  ? `<div>
                       <div class="muted">${escapeHtml(t("settings.lm_hf_downloads_title"))}</div>
                       ${hfDownloads
                         .slice(0, 6)
                         .map((dl) => {
                           const isActive = dl.state === "queued" || dl.state === "downloading";
                           const pct = Math.max(0, Math.min(100, Number(dl.pct ?? 0)));
                           return `
                             <div class="source-row">
                               <div class="source-row-top">
                                 <span>${escapeHtml(
                                   t("settings.lm_hf_dl_progress", {
                                     repo: dl.repo_id,
                                     state: dl.state,
                                     pct: pct.toFixed(1),
                                     done: dl.files_done,
                                     total: dl.files_total,
                                     file: dl.current_file || (dl.error ? dl.error : fmtBytes(dl.downloaded_bytes) || dl.state),
                                   })
                                 )}</span>
                                 ${
                                   isActive
                                     ? `<button type="button" class="btn danger" data-hf-cancel-dl="${escapeHtml(dl.download_id)}">${escapeHtml(t("settings.lm_hf_cancel_btn"))}</button>`
                                     : ""
                                 }
                               </div>
                               <div class="lm-progress-track"><div class="lm-progress-fill" style="width:${pct}%"></div></div>
                             </div>
                           `;
                         })
                         .join("")}
                     </div>`
                  : ""
              }
            </div>

            <div class="card inset lm-subcard">
              <div class="card-h">
                <b>${escapeHtml(t("settings.lm_point_title"))}</b>
                <span class="end muted">${escapeHtml(t("settings.lm_point_sub"))}</span>
              </div>
              <div class="form-row">
                <select id="kb-local-slot-select" class="select">
                  <option value="chat_llm" ${state.localModelSlotDraft === "chat_llm" ? "selected" : ""}>${escapeHtml(t("settings.lm_slot_chat"))}</option>
                  <option value="gemma_override" ${state.localModelSlotDraft === "gemma_override" ? "selected" : ""}>${escapeHtml(t("settings.lm_slot_gemma"))}</option>
                  <option value="reader_hertz" ${state.localModelSlotDraft === "reader_hertz" ? "selected" : ""}>${escapeHtml(t("settings.lm_slot_hertz"))}</option>
                  <option value="reader_planck" ${state.localModelSlotDraft === "reader_planck" ? "selected" : ""}>${escapeHtml(t("settings.lm_slot_planck"))}</option>
                  <option value="brain_encoder" ${state.localModelSlotDraft === "brain_encoder" ? "selected" : ""}>${escapeHtml(t("settings.lm_slot_brain"))}</option>
                </select>
                <input
                  id="kb-local-path-input"
                  class="input"
                  type="text"
                  spellcheck="false"
                  value="${escapeHtml(state.localModelPathDraft)}"
                  placeholder="${escapeHtml(t("settings.lm_path_ph"))}"
                />
                <button id="kb-local-browse-btn" type="button" class="btn">${escapeHtml(t("settings.lm_browse_btn"))}</button>
                <button id="kb-local-link-btn" type="button" class="btn primary">${escapeHtml(t("settings.lm_link_btn"))}</button>
                ${
                  selectedSlotHasOverride
                    ? `<button id="kb-local-reset-slot-btn" type="button" class="btn danger">${escapeHtml(t("settings.lm_reset_slot_btn"))}</button>`
                    : ""
                }
              </div>

              <div class="muted">${escapeHtml(t("settings.lm_installed_title", { count: customLocalLlms.length }))}</div>
              ${
                customLocalLlms.length === 0
                  ? `<div class="muted">${escapeHtml(t("settings.lm_installed_empty"))}</div>`
                  : customLocalLlms
                      .map((lm) => {
                        const szStr = fmtBytes(lm.size_bytes);
                        return `
                          <div class="source-row">
                            <div class="source-row-top">
                              <b>${escapeHtml(lm.label)} · <span class="muted">${escapeHtml(lm.id)}</span></b>
                              <span class="end">
                                ${
                                  lm.ready
                                    ? `<button type="button" class="btn" data-local-use-chat="${escapeHtml(lm.id)}">${escapeHtml(t("settings.lm_use_for_chat"))}</button>`
                                    : ""
                                }
                                <button type="button" class="btn danger" data-local-remove="${escapeHtml(lm.id)}">${escapeHtml(t("settings.lm_remove_btn"))}</button>
                                ${
                                  lm.source === "huggingface"
                                    ? `<button type="button" class="btn danger" data-local-delete-files="${escapeHtml(lm.id)}">${escapeHtml(t("settings.lm_remove_files_btn"))}</button>`
                                    : ""
                                }
                              </span>
                            </div>
                            <div class="lm-inline-meta">${escapeHtml(lm.path)}${szStr ? ` · ${escapeHtml(szStr)}` : ""}${lm.error ? ` · ${escapeHtml(lm.error)}` : ""}</div>
                          </div>
                        `;
                      })
                      .join("")
              }
            </div>

            <div class="label">${escapeHtml(t("settings.cloud_providers_label"))}</div>
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
                      <span class="end badge ${p.configured ? "" : "soft"}">${escapeHtml(
                        p.configured
                          ? t("settings.cloud_status_badge", { source: p.key_source ?? "vault", masked: p.masked_key || "***", count: modelsCount })
                          : t("settings.not_configured")
                      )}</span>
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
                        placeholder="${escapeHtml(t("settings.paste_key_ph", { envKey, hint: p.placeholder ?? "api key" }))}"
                      />
                      <button data-cloud-toggle-vis="${escapeHtml(p.id)}" type="button" class="btn">${escapeHtml(t("settings.show_key"))}</button>
                      <button data-cloud-save-key="${escapeHtml(p.id)}" type="button" class="btn primary">${escapeHtml(p.configured ? t("settings.update_pull_models") : t("settings.save_pull_models"))}</button>
                      <button data-cloud-refresh-models="${escapeHtml(p.id)}" type="button" class="btn">${escapeHtml(t("settings.refresh_models"))}</button>
                      ${
                        p.configured || storedKey
                          ? `<button data-cloud-clear-key="${escapeHtml(p.id)}" type="button" class="btn danger">${escapeHtml(t("settings.delete_key"))}</button>`
                          : ""
                      }
                    </div>
                    ${
                      modelsCount > 0
                        ? `
                          <div class="form-row">
                            <span class="muted">${escapeHtml(t("settings.discovered_n", { count: modelsCount }))}</span>
                            <select data-cloud-model-picker="${escapeHtml(p.id)}" class="select">
                              ${modelsList
                                .map(
                                  (m) =>
                                    `<option value="${escapeHtml(m.id)}" ${roleChat === m.id ? "selected" : ""}>${escapeHtml(m.label || m.slug)} · ${escapeHtml(m.id)}</option>`
                                )
                                .join("")}
                            </select>
                            <button data-cloud-use-model="${escapeHtml(p.id)}" type="button" class="btn">${escapeHtml(t("settings.use_chat_model"))}</button>
                          </div>
                        `
                        : `<div class="muted">${escapeHtml(
                            p.configured
                              ? t("settings.zero_models_cached")
                              : t("settings.paste_key_hint")
                          )}</div>`
                    }
                  </div>
                `;
              })
              .join("")}

            <div class="label">${escapeHtml(t("settings.local_models_label", { count: doctorRoles.length || 5 }))}</div>
            ${
              doctorRoles.length === 0
                ? `<div class="muted">${escapeHtml(t("settings.models_offline"))}</div>`
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
                          ? t("settings.ready_device", { device: dr.device })
                          : dr.state === "cpu_only"
                            ? t("settings.cpu_device", { device: dr.device })
                            : t("settings.missing");
                      return `
                        <div class="source-row">
                          <div class="source-row-top">
                            <b class="t">${escapeHtml(dr.role)} · <span class="muted">${escapeHtml(dr.model)}</span></b>
                            <span class="status"><span class="${dotCls}"></span><span>${escapeHtml(stateText)}</span></span>
                          </div>
                          ${
                            dr.fix
                              ? `<div class="source-row-meta">${escapeHtml(t("settings.fix_prefix", { fix: dr.fix }))}</div>`
                              : dr.path
                                ? `<div class="source-row-meta">${escapeHtml(dr.path)}</div>`
                                : ""
                          }
                        </div>
                      `;
                    })
                    .join("")}</div>`
            }

            <div class="label">${escapeHtml(t("settings.routing_section", { count: state.routingPolicy?.total_signals ?? 0 }))}</div>
            <div class="card inset">
              ${
                !state.routingPolicy || state.routingPolicy.rules.length === 0
                  ? `<div class="muted">${escapeHtml(t("settings.routing_empty"))}</div>`
                  : `<div class="table-wrap"><table class="table"><thead><tr><th>${escapeHtml(t("settings.col_query_type"))}</th><th class="num">${escapeHtml(t("settings.col_retries"))}</th><th class="num">${escapeHtml(t("settings.col_planck"))}</th><th class="num">${escapeHtml(t("settings.col_flagged"))}</th><th>${escapeHtml(t("settings.col_learned_action"))}</th></tr></thead><tbody>${state.routingPolicy.rules
                      .map((rule) => {
                        const actionParts: string[] = [];
                        if (rule.escalated && rule.recommended_model) {
                          actionParts.push(t("settings.escalate_to", { model: rule.recommended_model }));
                        }
                        if (rule.auto_web) actionParts.push(t("settings.auto_web"));
                        if (rule.auto_mail) actionParts.push(t("settings.auto_mail"));
                        const actTxt = actionParts.length > 0 ? actionParts.join(" · ") : t("settings.monitoring");
                        return `<tr><td>${escapeHtml(rule.query_type)}</td><td class="num">${rule.retries}</td><td class="num">${rule.planck_switches}</td><td class="num">${rule.flagged_citations}</td><td>${escapeHtml(actTxt)}</td></tr>`;
                      })
                      .join("")}</tbody></table></div>`
              }
              <div class="form-row">
                <button id="kb-reset-routing-btn" type="button" class="btn danger" ${!state.routingPolicy || state.routingPolicy.total_signals === 0 ? "disabled" : ""}>${escapeHtml(t("settings.reset_routing_btn"))}</button>
              </div>
            </div>
          </div>
        `
        }
      </div>
  `;

  const showAppearance = !isLaneView || activeLane === "profiles";
  const showModels = !isLaneView || activeLane === "models";
  const showProfilesVault = !isLaneView || activeLane === "profiles";
  const showGoogleMail = !isLaneView || activeLane === "google_mail";
  const showProviders = !isLaneView || activeLane === "providers";
  const showSources = !isLaneView || activeLane === "sources";
  const showTranslation = !isLaneView || activeLane === "translation";

  const kbScope = isEmbedded ? "embedded" : isLaneView ? `lane:${activeLane}` : "manual";
  const prevPage = container.querySelector(".kb-page") as HTMLElement | null;
  const preserveScroll = prevPage?.dataset.kbScope === kbScope;
  const prevPageScrollTop = preserveScroll ? prevPage.scrollTop : 0;
  const prevVpScrollTop = preserveScroll ? container.scrollTop : 0;
  const prevOverrideScrollTop = preserveScroll
    ? ((container.querySelector(".kb-app-lang-editor .table-wrap") as HTMLElement | null)?.scrollTop ?? 0)
    : 0;

  container.innerHTML = `
    <div class="${isEmbedded ? "kb-embedded" : "kb-page"}" data-kb-scope="${escapeHtml(kbScope)}">
      <div class="${isEmbedded ? "section" : "kb-page-inner"}">
        ${
          isEmbedded
            ? `
              <div class="kb-embedded-toolbar">
                <span class="muted">${escapeHtml(
                  isUnlocked && activeProfile
                    ? t("settings.unlocked_sub", { name: activeProfile.name, entities: brainEntities.length, bookmarks: bookmarksIndexed.length, ranking: brainRankingLabel })
                    : t("settings.locked_sub", { ranking: brainRankingLabel, queue: kb.queue_len })
                )}</span>
                <div class="kb-head-actions">
                  <button id="kb-expand-all-btn" type="button" class="btn">${escapeHtml(t("settings.expand_all"))}</button>
                  <button id="kb-collapse-all-btn" type="button" class="btn">${escapeHtml(t("settings.collapse_all"))}</button>
                  <button id="kb-open-brain-btn" type="button" class="btn">${escapeHtml(t("settings.brain_btn", { mod: MOD_LABEL }))}</button>
                  <button id="kb-pause-btn" type="button" class="btn" aria-pressed="${kb.pause_learning ? "true" : "false"}">
                    ${escapeHtml(t("settings.pause_learning", { state: kb.pause_learning ? t("common.on") : t("common.off") }))}
                  </button>
                </div>
              </div>
              ${
                state.profileUnlocking
                  ? `<div class="unlock-loading-row" role="status" aria-live="polite"><span class="satz-spinner" aria-hidden="true"></span><span>${escapeHtml(state.profileUnlockLabel || t("profile.unlocking_progress"))}</span></div>`
                  : ""
              }
            `
            : `
        <div class="view-h">
          <div>
            <h1>${escapeHtml(t("common.settings"))}</h1>
            <p>${escapeHtml(
              isUnlocked && activeProfile
                ? t("settings.unlocked_sub", { name: activeProfile.name, entities: brainEntities.length, bookmarks: bookmarksIndexed.length, ranking: brainRankingLabel })
                : t("settings.locked_sub", { ranking: brainRankingLabel, queue: kb.queue_len })
            )}</p>
          </div>
          <div class="end kb-head-actions">
            ${
              isLaneView && actions.onOpenSettingsChat
                ? `<button id="kb-open-settings-chat-btn" type="button" class="btn primary">${escapeHtml(t("settings.ask_in_chat"))}</button>`
                : ""
            }
            ${
              !isLaneView
                ? `
                  <button id="kb-expand-all-btn" type="button" class="btn">${escapeHtml(t("settings.expand_all"))}</button>
                  <button id="kb-collapse-all-btn" type="button" class="btn">${escapeHtml(t("settings.collapse_all"))}</button>
                `
                : ""
            }
            <button id="kb-open-brain-btn" type="button" class="btn">${escapeHtml(t("settings.brain_btn", { mod: MOD_LABEL }))}</button>
            <button id="kb-pause-btn" type="button" class="btn" aria-pressed="${kb.pause_learning ? "true" : "false"}">
              ${escapeHtml(t("settings.pause_learning", { state: kb.pause_learning ? t("common.on") : t("common.off") }))}
            </button>
            ${
              isLaneView
                ? ""
                : `<button id="kb-close-btn" type="button" class="icon-btn" title="${escapeHtml(t("settings.close_settings"))}">${icon("x", "ico-sm")}</button>`
            }
          </div>
        </div>
        `
        }

        ${
          !showAppearance
            ? ""
            : `
        <div class="card">
          <div class="card-h">
            <b>${escapeHtml(t("settings.app_wide_title"))}</b>
            <span class="end badge soft">${escapeHtml(t("settings.app_wide_sub"))}</span>
          </div>
          <div class="form-row">
            <span class="muted">${escapeHtml(t("settings.theme"))}</span>
            <div class="seg" role="group" aria-label="${escapeHtml(t("settings.theme"))}">
              <button type="button" data-ui-theme="system" aria-pressed="${getUiThemePref() === "system"}">${escapeHtml(t("settings.theme_system"))}</button>
              <button type="button" data-ui-theme="light" aria-pressed="${getUiThemePref() === "light"}">${escapeHtml(t("settings.theme_light"))}</button>
              <button type="button" data-ui-theme="dark" aria-pressed="${getUiThemePref() === "dark"}">${escapeHtml(t("settings.theme_dark"))}</button>
            </div>
            <span class="muted">${escapeHtml(t("settings.layout"))}</span>
            <div class="seg" role="group" aria-label="${escapeHtml(t("settings.layout"))}">
              <button type="button" data-ui-layout="floating" aria-pressed="${getUiLayoutPref() === "floating"}">${escapeHtml(t("settings.layout_floating"))}</button>
              <button type="button" data-ui-layout="flush" aria-pressed="${getUiLayoutPref() === "flush"}">${escapeHtml(t("settings.layout_flush"))}</button>
            </div>
          </div>
          ${renderAppLanguageSectionHtml()}
          <div class="form-row">
            <span class="muted">${escapeHtml(t("settings.app_updates_title"))}</span>
            <span class="badge soft">${escapeHtml(t("settings.app_version_label", { version: state.appUpdateStatus.currentVersion || "0.5.0" }))}</span>
            <button id="kb-check-update-btn" type="button" class="btn" ${state.appUpdateStatus.checking || state.appUpdateStatus.installing ? "disabled" : ""}>${escapeHtml(state.appUpdateStatus.checking ? t("settings.app_checking_update") : t("settings.app_check_update_btn"))}</button>
            <button id="kb-replay-tour-btn" type="button" class="btn">${escapeHtml(t("settings.replay_tour_btn"))}</button>
            ${
              state.appUpdateStatus.availableVersion
                ? `<button id="kb-install-update-btn" type="button" class="btn primary" ${state.appUpdateStatus.installing ? "disabled" : ""}>${escapeHtml(
                    state.appUpdateStatus.installing
                      ? t("settings.app_updating_progress", { pct: state.appUpdateStatus.progressPct })
                      : t("settings.app_install_update_btn", { version: state.appUpdateStatus.availableVersion })
                  )}</button>`
                : ""
            }
            ${
              state.appUpdateStatus.error
                ? `<span class="muted">${escapeHtml(state.appUpdateStatus.error)}</span>`
                : state.appUpdateStatus.message
                  ? `<span class="muted">${escapeHtml(state.appUpdateStatus.message)}</span>`
                  : ""
            }
          </div>
          ${
            state.appUpdateStatus.installing
              ? `<div class="lm-progress-track"><div class="lm-progress-fill" style="width:${Math.max(0, Math.min(100, state.appUpdateStatus.progressPct))}%"></div></div>`
              : ""
          }
        </div>
        <div class="label">${escapeHtml(isUnlocked && activeProfile ? t("settings.profile_scope_unlocked", { name: activeProfile.name }) : t("settings.profile_scope_locked"))}</div>
        `
        }

        ${state.profileStatusMessage ? renderKbBannerHtml(state.profileStatusMessage) : ""}

        ${showModels ? doctorSectionHtml : ""}

        ${!showProfilesVault ? "" : `<div class="card kb-acc-card acc ${acc.profiles ? "open" : ""}">
          <div class="settings-acc-bar">
            <button type="button" class="acc-h" data-settings-accordion="profiles">
              <span>${escapeHtml(t("settings.profiles_section"))}</span>
              <span class="ct">${profilesList.length}</span>
              ${icon("chev", "ico-sm")}
            </button>
            ${
              isUnlocked
                ? `<button id="kb-lock-profile-btn" type="button" class="btn">${escapeHtml(t("settings.lock_active_profile"))}</button>`
                : `<span class="badge soft">${escapeHtml(t("rail.locked"))}</span>`
            }
          </div>
          ${
            !acc.profiles
              ? ""
              : `
          <div class="acc-b section">
            ${
              state.profileUnlocking
                ? `<div class="unlock-loading-row" role="status" aria-live="polite"><span class="satz-spinner" aria-hidden="true"></span><span>${escapeHtml(state.profileUnlockLabel || t("profile.unlocking_long"))}</span></div>`
                : ""
            }
            <div class="form-row">
              <input
                id="kb-new-profile-name"
                class="input"
                type="text"
                spellcheck="false"
                autocorrect="off"
                autocapitalize="off"
                placeholder="${escapeHtml(t("profile.name_placeholder"))}"
                ${state.profileUnlocking ? "disabled" : ""}
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
                placeholder="${escapeHtml(t("profile.pin6_placeholder"))}"
                ${state.profileUnlocking ? "disabled" : ""}
              />
              <button id="kb-create-profile-btn" type="button" class="btn primary" ${state.profileUnlocking ? "disabled" : ""}>${icon("plus", "ico-sm")}<span>${escapeHtml(state.profileUnlocking ? t("profile.creating") : t("settings.create_profile_btn"))}</span></button>
            </div>
            ${renderProfileUploadSectionHtml("kb")}
            ${
              profilesList.length === 0
                ? `<div class="form-row"><span class="muted">${escapeHtml(t("settings.no_profiles"))}</span>${actions.onOpenOnboarding ? `<button id="kb-open-onboard-btn" type="button" class="btn end">${escapeHtml(t("settings.setup_profile_btn"))}</button>` : ""}</div>`
                : profilesList
                    .map(
                      (p) => `
                  <div class="source-row">
                    <div class="source-row-top">
                      <span class="t">
                        ${p.is_active ? `<span class="dot"></span> ` : ""}
                        <b>${escapeHtml(p.name)}</b>
                        <span class="muted">${escapeHtml(t("settings.profile_meta", { id: p.id, count: p.credential_services_count }))}</span>
                      </span>
                      ${
                        p.is_active
                          ? `<span class="badge">${escapeHtml(t("rail.unlocked"))}</span>`
                          : `
                        <input
                          class="input pin"
                          type="password"
                          inputmode="numeric"
                          maxlength="6"
                          spellcheck="false"
                          autocorrect="off"
                          autocapitalize="off"
                          placeholder="${escapeHtml(t("profile.pin_placeholder"))}"
                          data-profile-pin-input="${escapeHtml(p.id)}"
                          ${state.profileUnlocking ? "disabled" : ""}
                        />
                        <button type="button" class="btn primary" data-unlock-profile="${escapeHtml(p.id)}" ${state.profileUnlocking ? "disabled" : ""}>${escapeHtml(state.profileUnlocking ? t("profile.unlocking_short") : t("profile.unlock_btn"))}</button>
                        <button type="button" class="btn" data-unlock-touchid="${escapeHtml(p.id)}" ${state.profileUnlocking ? "disabled" : ""}>${escapeHtml(IS_MAC ? t("settings.touch_id") : t("settings.quick_unlock"))}</button>
                      `
                      }
                      <button type="button" class="btn" data-export-profile="${escapeHtml(p.id)}" title="${escapeHtml(t("profile.export_title"))}" ${(state.profileUnlocking || state.profileExportBusyId === p.id) ? "disabled" : ""}>${escapeHtml(state.profileExportBusyId === p.id ? t("profile.exporting_short") : t("profile.export_btn"))}</button>
                      <button type="button" class="btn-text" data-delete-profile="${escapeHtml(p.id)}" title="${escapeHtml(t("settings.delete_profile_title"))}" ${state.profileUnlocking ? "disabled" : ""}>${escapeHtml(t("common.delete"))}</button>
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
        `}

        ${
          !showProfilesVault
            ? ""
            : `
        <div class="card kb-acc-card acc ${acc.vault ? "open" : ""}">
          <div class="settings-acc-bar">
            <button type="button" class="acc-h" data-settings-accordion="vault">
              <span>${escapeHtml(t("settings.vault_section"))}</span>
              <span class="ct">${escapeHtml(isUnlocked ? t("settings.services_n", { count: vaultServices.length }) : t("settings.locked_lower"))}</span>
              ${icon("chev", "ico-sm")}
            </button>
            ${
              isUnlocked && state.activeDetail?.tabs.some((tb) => tb.is_open)
                ? `<button id="kb-autofill-tab-btn" type="button" class="btn" title="${escapeHtml(t("settings.autofill_open_tab_title"))}">${escapeHtml(t("settings.autofill_open_tab"))}</button>`
                : `<span class="muted">AES-256-GCM + Argon2id</span>`
            }
          </div>
          ${
            !acc.vault
              ? ""
              : !isUnlocked
                ? `<div class="muted acc-b">${escapeHtml(t("settings.vault_locked_note"))}</div>`
                : `
            <div class="acc-b section">
              <div class="muted">
                ${escapeHtml(t("settings.vault_file_note", { path: vault?.env_path ?? "", name: activeProfile?.name ?? "" }))}
              </div>

              <div class="form-row">
                <input id="kb-cred-service" class="input" type="text" spellcheck="false" autocorrect="off" autocapitalize="off" placeholder="${escapeHtml(t("settings.cred_service_ph"))}" />
                <input id="kb-cred-username" class="input" type="text" spellcheck="false" autocorrect="off" autocapitalize="off" placeholder="${escapeHtml(t("settings.cred_user_ph"))}" />
                <input id="kb-cred-password" class="input" type="password" spellcheck="false" autocorrect="off" autocapitalize="off" placeholder="${escapeHtml(t("settings.cred_pass_ph"))}" />
                <input id="kb-cred-token" class="input" type="password" spellcheck="false" autocorrect="off" autocapitalize="off" placeholder="${escapeHtml(t("settings.cred_token_ph"))}" />
                <button id="kb-save-cred-btn" type="button" class="btn primary">${escapeHtml(t("settings.save_env_btn"))}</button>
              </div>

              <div class="form-row">
                <input id="kb-import-env-path" class="input" type="text" spellcheck="false" autocorrect="off" autocapitalize="off" placeholder="${escapeHtml(t("settings.import_env_ph", { sample: IS_MAC ? "~/Downloads/.env" : "C:\\Users\\...\\.env" }))}" />
                <button id="kb-import-env-btn" type="button" class="btn">${escapeHtml(t("settings.import_env_btn"))}</button>
                <input
                  id="kb-reveal-pin-input"
                  class="input pin"
                  type="password"
                  inputmode="numeric"
                  maxlength="6"
                  spellcheck="false"
                  autocorrect="off"
                  autocapitalize="off"
                  placeholder="${escapeHtml(t("settings.reveal_pin_ph"))}"
                />
              </div>

              ${
                vaultServices.length === 0
                  ? `<div class="muted">${escapeHtml(t("settings.no_vault_creds"))}</div>`
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
                        · ${escapeHtml(t("settings.cred_user_meta", { user: s.username || t("settings.token_or_cookie") }))}
                      </span>
                      <span class="news-src-checks">
                        ${
                          s.has_password
                            ? revPwd
                              ? `<span class="pill">${escapeHtml(t("settings.revealed_password", { val: revPwd }))}</span>`
                              : `<button type="button" class="btn-text" data-reveal-service="${escapeHtml(s.service)}" data-reveal-field="password">${escapeHtml(t("settings.reveal_password"))}</button>`
                            : ""
                        }
                        ${
                          s.has_token
                            ? revTok
                              ? `<span class="pill">${escapeHtml(t("settings.revealed_token", { val: revTok }))}</span>`
                              : `<button type="button" class="btn-text" data-reveal-service="${escapeHtml(s.service)}" data-reveal-field="token">${escapeHtml(t("settings.reveal_token"))}</button>`
                            : ""
                        }
                        ${
                          s.has_cookie
                            ? revCook
                              ? `<span class="pill">${escapeHtml(t("settings.revealed_cookie", { val: revCook }))}</span>`
                              : `<button type="button" class="btn-text" data-reveal-service="${escapeHtml(s.service)}" data-reveal-field="cookie">${escapeHtml(t("settings.reveal_cookie"))}</button>`
                            : ""
                        }
                        <button type="button" class="btn-text" data-delete-cred="${escapeHtml(s.service)}">${escapeHtml(t("common.delete"))}</button>
                      </span>
                    </div>
                  `;
                      })
                      .join("")}</div>`
              }

              <div class="section">
                <div class="muted">${escapeHtml(t("settings.raw_env_note", { name: activeProfile?.name ?? "" }))}</div>
                <textarea id="kb-raw-env-textarea" class="textarea mono" rows="5" spellcheck="false" placeholder="${escapeHtml(t("settings.raw_env_ph"))}"></textarea>
                <div>
                  <button id="kb-save-raw-env-btn" type="button" class="btn">${escapeHtml(t("settings.merge_vault_btn"))}</button>
                </div>
              </div>

              ${!isLaneView ? renderGoogleOAuthSectionHtml() : ""}
            </div>
          `
          }
        </div>
        `
        }

        ${showProviders ? renderActionProvidersSectionHtml(Boolean(isLaneView && activeLane === "providers")) : ""}

        ${showGoogleMail && isLaneView ? renderGoogleOAuthSectionHtml() : ""}

        ${
          !showGoogleMail
            ? ""
            : `
        <div class="card kb-acc-card acc ${acc.mail ? "open" : ""}">
          <div class="settings-acc-bar">
            <button type="button" class="acc-h" data-settings-accordion="mail">
              <span>${escapeHtml(t("settings.mail_section"))}</span>
              <span class="ct">${escapeHtml(t("settings.accounts_n", { count: state.mailAccounts.length }))}</span>
              ${icon("chev", "ico-sm")}
            </button>
            <span class="muted">IMAP / POP3 / SMTP</span>
          </div>
          ${!acc.mail ? "" : `<div class="acc-b">${renderMailAccountsSectionHtml()}</div>`}
        </div>
        <div class="card kb-acc-card acc ${acc.drives ? "open" : ""}">
          <div class="settings-acc-bar">
            <button type="button" class="acc-h" data-settings-accordion="drives">
              <span>${escapeHtml(t("settings.drives_section"))}</span>
              <span class="ct">${escapeHtml(t("settings.drives_connected_n", { count: getConfiguredDriveProviders().list.length }))}</span>
              ${icon("chev", "ico-sm")}
            </button>
            <span class="muted">${escapeHtml(t("settings.drives_sub"))}</span>
          </div>
          ${!acc.drives ? "" : `<div class="acc-b section">${state.drivesStatusMessage ? renderKbBannerHtml(state.drivesStatusMessage) : ""}${renderDriveAccountsPanelHtml()}</div>`}
        </div>
        `
        }

        ${
          !showSources
            ? ""
            : `
        <div class="card kb-acc-card acc ${acc.indexing ? "open" : ""}">
          <div class="settings-acc-bar">
            <button type="button" class="acc-h" data-settings-accordion="indexing">
              <span>${escapeHtml(t("settings.indexing_section"))}</span>
              <span class="ct">${bookmarksIndexed.length}</span>
              ${icon("chev", "ico-sm")}
            </button>
            <span class="muted">${escapeHtml(t("settings.indexing_sub"))}</span>
          </div>
          ${
            !acc.indexing
              ? ""
              : `
          <div class="acc-b section">
            <div class="muted">
              ${escapeHtml(t("settings.indexing_note"))}
            </div>
            ${
              bookmarksIndexed.length === 0
                ? `<div class="muted">${escapeHtml(t("settings.no_bookmarks_indexed"))}</div>`
                : bookmarksIndexed
                    .map(
                      (bm) => `
                  <div class="kb-kv-row">
                    <span class="truncate">${escapeHtml(bm.title || bm.domain)} <span class="muted">(${escapeHtml(bm.url)})</span></span>
                    <span class="muted">
                      <span class="badge soft">${escapeHtml(bm.status)}</span> · ${escapeHtml(t("settings.indexing_chars", { chars: bm.text_chars }))} · ${escapeHtml(
                        bm.last_indexed_at > 0
                          ? t("start.updated_rel", { rel: formatRelativeTime(String(Math.floor(bm.last_indexed_at))) })
                          : t("settings.indexing_busy")
                      )}
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
        `
        }

        ${
          !showTranslation
            ? ""
            : renderContentTranslationSectionHtml(
                Boolean(acc.translation),
                isUnlocked,
                discoveredCloudModels.map((m) => m.id)
              )
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

  container.querySelector("#kb-lang-select")?.addEventListener("change", (e) => {
    const lang = (e.currentTarget as HTMLSelectElement).value;
    if (lang && actions.onSelectUiLanguage) {
      void actions.onSelectUiLanguage(lang);
    }
  });

  const triggerTranslateFromInput = (force = false) => {
    const customInput = container.querySelector("#kb-lang-custom-input") as HTMLInputElement | null;
    const rawLang = (customInput?.value ?? "").trim() || getUiLocale();
    if (!rawLang || rawLang === "en") {
      state.i18nStatusMsg = `${t("common.error_prefix")} ${t("i18n.err_enter_lang")}`;
      renderKnowledgeView(container, actions);
      return;
    }
    void actions.onTranslateUiLanguage?.(rawLang, force);
  };

  container.querySelector("#kb-lang-translate-btn")?.addEventListener("click", () => {
    triggerTranslateFromInput(false);
  });

  container.querySelector("#kb-lang-custom-input")?.addEventListener("keydown", (e) => {
    if ((e as KeyboardEvent).key === "Enter") {
      e.preventDefault();
      triggerTranslateFromInput(false);
    }
  });

  container.querySelector("#kb-lang-sync-missing-btn")?.addEventListener("click", () => {
    void actions.onTranslateUiLanguage?.(getUiLocale(), false);
  });

  container.querySelector("#kb-lang-retranslate-btn")?.addEventListener("click", () => {
    void actions.onTranslateUiLanguage?.(getUiLocale(), true);
  });

  container.querySelector("#kb-lang-cancel-btn")?.addEventListener("click", () => {
    void actions.onCancelUiTranslate?.(getUiLocale());
  });

  container.querySelector("#kb-lang-customize-toggle")?.addEventListener("click", () => {
    state.i18nCustomEditorOpen = !state.i18nCustomEditorOpen;
    renderKnowledgeView(container, actions);
  });

  container.querySelector("#kb-lang-export-btn")?.addEventListener("click", () => {
    void actions.onExportUiPack?.(getUiLocale());
  });

  container.querySelector("#kb-lang-import-input")?.addEventListener("change", (e) => {
    const inp = e.currentTarget as HTMLInputElement;
    const file = inp.files?.[0];
    inp.value = "";
    if (!file || !actions.onImportUiPack) return;
    void file.text().then((rawTxt) => {
      void actions.onImportUiPack?.(rawTxt);
    });
  });

  const bindOverrideRowButtons = () => {
    const locale = getUiLocale();
    container.querySelectorAll("[data-kb-lang-override-save]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = (btn as HTMLElement).getAttribute("data-kb-lang-override-save") ?? "";
        if (!key || !actions.onOverrideUiTranslation) return;
        const valEl = container.querySelector(
          `[data-kb-lang-override-input="${CSS.escape(key)}"]`
        ) as HTMLInputElement | null;
        const val = valEl?.value ?? "";
        void actions.onOverrideUiTranslation(locale, key, val, false);
      });
    });

    container.querySelectorAll("[data-kb-lang-override-reset]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = (btn as HTMLElement).getAttribute("data-kb-lang-override-reset") ?? "";
        if (!key || !actions.onOverrideUiTranslation) return;
        void actions.onOverrideUiTranslation(locale, key, undefined, true);
      });
    });
  };

  bindOverrideRowButtons();

  container.querySelector("#kb-lang-override-filter")?.addEventListener("input", (e) => {
    state.i18nOverrideFilter = (e.currentTarget as HTMLInputElement).value;
    const tbody = container.querySelector("#kb-lang-override-tbody");
    if (tbody) {
      tbody.innerHTML = renderOverrideRowsHtml(state.i18nOverrideFilter);
      bindOverrideRowButtons();
    }
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
    for (const k of ["models", "profiles", "vault", "providers", "mail", "drives", "indexing", "translation"]) {
      state.settingsAccordionOpen[k] = true;
    }
    renderKnowledgeView(container, actions);
  });

  container.querySelector("#kb-collapse-all-btn")?.addEventListener("click", () => {
    for (const k of ["models", "profiles", "vault", "providers", "mail", "drives", "indexing", "translation"]) {
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

  const hfSearchInput = container.querySelector("#kb-hf-search-input") as HTMLInputElement | null;
  const hfRepoInput = container.querySelector("#kb-hf-repo-input") as HTMLInputElement | null;
  const hfTokenInput = container.querySelector("#kb-hf-token-input") as HTMLInputElement | null;
  const localSlotSelect = container.querySelector("#kb-local-slot-select") as HTMLSelectElement | null;
  const localPathInput = container.querySelector("#kb-local-path-input") as HTMLInputElement | null;

  hfSearchInput?.addEventListener("input", () => {
    state.hfSearchQuery = hfSearchInput.value;
  });
  hfSearchInput?.addEventListener("keydown", (e) => {
    if ((e as KeyboardEvent).key === "Enter" && actions.onSearchHfModels) {
      e.preventDefault();
      state.hfSearchQuery = hfSearchInput.value.trim();
      void actions.onSearchHfModels(state.hfSearchQuery);
    }
  });
  container.querySelector("#kb-hf-search-btn")?.addEventListener("click", () => {
    if (!actions.onSearchHfModels) return;
    state.hfSearchQuery = (hfSearchInput?.value ?? "").trim();
    void actions.onSearchHfModels(state.hfSearchQuery);
  });
  hfRepoInput?.addEventListener("input", () => {
    state.hfRepoDraft = hfRepoInput.value;
  });
  container.querySelectorAll<HTMLButtonElement>("[data-hf-pick-repo]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const repoId = btn.getAttribute("data-hf-pick-repo") ?? "";
      if (!repoId) return;
      state.hfRepoDraft = repoId;
      if (hfRepoInput) hfRepoInput.value = repoId;
      if (actions.onInspectHfRepo) {
        void actions.onInspectHfRepo(repoId, hfTokenInput?.value.trim() ?? "");
      }
    });
  });
  container.querySelector("#kb-hf-inspect-btn")?.addEventListener("click", () => {
    if (!actions.onInspectHfRepo) return;
    const repoId = (hfRepoInput?.value ?? state.hfRepoDraft).trim();
    state.hfRepoDraft = repoId;
    void actions.onInspectHfRepo(repoId, hfTokenInput?.value.trim() ?? "");
  });
  container.querySelector("#kb-hf-download-btn")?.addEventListener("click", () => {
    if (!actions.onStartHfDownload) return;
    const repoId = (hfRepoInput?.value ?? state.hfRepoDraft).trim();
    state.hfRepoDraft = repoId;
    void actions.onStartHfDownload({
      repo_id: repoId,
      token: hfTokenInput?.value.trim() ?? "",
      use_as_chat: true,
    });
  });
  container.querySelector("#kb-hf-token-save-btn")?.addEventListener("click", () => {
    if (!actions.onSaveHfToken) return;
    const tok = hfTokenInput?.value.trim() ?? "";
    void actions.onSaveHfToken(tok, false);
  });
  container.querySelector("#kb-hf-token-clear-btn")?.addEventListener("click", () => {
    if (!actions.onSaveHfToken) return;
    void actions.onSaveHfToken("", true);
  });
  container.querySelectorAll<HTMLButtonElement>("[data-hf-cancel-dl]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!actions.onCancelHfDownload) return;
      const dlId = btn.getAttribute("data-hf-cancel-dl") ?? "";
      if (dlId) void actions.onCancelHfDownload(dlId);
    });
  });

  localSlotSelect?.addEventListener("change", () => {
    state.localModelSlotDraft = localSlotSelect.value || "chat_llm";
    renderKnowledgeView(container, actions, laneFilter, isEmbedded);
  });
  localPathInput?.addEventListener("input", () => {
    state.localModelPathDraft = localPathInput.value;
  });
  container.querySelector("#kb-local-browse-btn")?.addEventListener("click", async () => {
    if (!actions.onBrowseLocalModelPath) return;
    const slot = localSlotSelect?.value || state.localModelSlotDraft || "chat_llm";
    const mode = slot === "chat_llm" || slot === "gemma_override" ? "directory" : "file";
    const picked = await actions.onBrowseLocalModelPath(mode, t("settings.lm_point_title"));
    if (picked) {
      state.localModelPathDraft = picked;
      if (localPathInput) localPathInput.value = picked;
    }
  });
  container.querySelector("#kb-local-link-btn")?.addEventListener("click", () => {
    if (!actions.onPointLocalModel) return;
    const slot = localSlotSelect?.value || state.localModelSlotDraft || "chat_llm";
    const pVal = (localPathInput?.value ?? state.localModelPathDraft).trim();
    state.localModelSlotDraft = slot;
    state.localModelPathDraft = pVal;
    void actions.onPointLocalModel({
      role_slot: slot,
      path: pVal,
      set_active: slot === "chat_llm" || slot === "gemma_override",
    });
  });
  container.querySelector("#kb-local-reset-slot-btn")?.addEventListener("click", () => {
    if (!actions.onRemoveLocalModel) return;
    const slot = localSlotSelect?.value || state.localModelSlotDraft || "chat_llm";
    void actions.onRemoveLocalModel({ role_slot: slot });
  });
  container.querySelectorAll<HTMLButtonElement>("[data-local-use-chat]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!actions.onSaveModelConfig) return;
      const mid = btn.getAttribute("data-local-use-chat") ?? "";
      if (mid) void actions.onSaveModelConfig({ role_chat: mid });
    });
  });
  container.querySelectorAll<HTMLButtonElement>("[data-local-remove]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!actions.onRemoveLocalModel) return;
      const mid = btn.getAttribute("data-local-remove") ?? "";
      if (mid) void actions.onRemoveLocalModel({ model_id: mid, delete_files: false });
    });
  });
  container.querySelectorAll<HTMLButtonElement>("[data-local-delete-files]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!actions.onRemoveLocalModel) return;
      const mid = btn.getAttribute("data-local-delete-files") ?? "";
      if (mid) void actions.onRemoveLocalModel({ model_id: mid, delete_files: true });
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
        btn.textContent = t("settings.hide_key");
      } else {
        inputEl.type = "password";
        btn.textContent = t("settings.show_key");
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

  container
    .querySelector("#kb-reset-routing-btn")
    ?.addEventListener("click", () => {
      if (actions.onResetRoutingTelemetry) {
        void actions.onResetRoutingTelemetry();
      }
    });

  container.querySelector("#kb-open-settings-chat-btn")?.addEventListener("click", () => {
    if (actions.onOpenSettingsChat) {
      actions.onOpenSettingsChat();
    }
  });

  container.querySelector("#kb-check-update-btn")?.addEventListener("click", () => {
    if (actions.onCheckAppUpdate) {
      void actions.onCheckAppUpdate();
    }
  });

  container.querySelector("#kb-replay-tour-btn")?.addEventListener("click", () => {
    actions.onReplayTour?.();
  });

  container.querySelector("#kb-open-onboard-btn")?.addEventListener("click", () => {
    actions.onOpenOnboarding?.();
  });

  container.querySelector("#kb-install-update-btn")?.addEventListener("click", () => {
    if (actions.onInstallAppUpdate) {
      void actions.onInstallAppUpdate();
    }
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

  container.querySelectorAll("[data-export-profile]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = (btn as HTMLElement).getAttribute("data-export-profile");
      if (!pid || !actions.onExportProfile) return;
      const pinInput = container.querySelector(
        `[data-profile-pin-input="${pid}"]`
      ) as HTMLInputElement | null;
      const pin = pinInput?.value.trim() || undefined;
      void actions.onExportProfile(pid, pin);
    });
  });

  bindProfileUploadSectionEvents(container, "kb", actions.onImportProfileFile);

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

  container.querySelector("#kb-google-json-file")?.addEventListener("change", (ev) => {
    const inp = ev.target as HTMLInputElement;
    const f = inp.files?.[0];
    if (!f) return;
    void f.text().then((txt) => {
      const ta = container.querySelector("#kb-google-client-json") as HTMLTextAreaElement | null;
      if (ta) ta.value = txt;
      state.googleOAuthMessage = t("settings.google_loaded", { name: f.name });
      const msgEl = container.querySelector("#kb-google-status-banner");
      if (msgEl) msgEl.textContent = state.googleOAuthMessage;
    });
  });

  const collectGoogleOAuthPayload = () => {
    const cid = (container.querySelector("#kb-google-client-id") as HTMLInputElement | null)?.value.trim() ?? "";
    const csec = (container.querySelector("#kb-google-client-secret") as HTMLInputElement | null)?.value.trim() ?? "";
    const cjson = (container.querySelector("#kb-google-client-json") as HTMLTextAreaElement | null)?.value.trim() ?? "";
    const portStr = (container.querySelector("#kb-google-redir-port") as HTMLInputElement | null)?.value.trim() ?? "";
    const useGmail = (container.querySelector("#kb-google-scope-gmail") as HTMLInputElement | null)?.checked ?? true;
    const extraRaw = (container.querySelector("#kb-google-extra-scopes") as HTMLInputElement | null)?.value.trim() ?? "";
    const scopes: string[] = ["openid", "email", "profile"];
    if (useGmail) scopes.push("https://mail.google.com/");
    for (const s of extraRaw.split(/[\s,]+/).filter(Boolean)) {
      if (!scopes.includes(s)) scopes.push(s);
    }
    return {
      client_id: cid || undefined,
      client_secret: csec || undefined,
      client_secret_json: cjson || undefined,
      scopes,
      connect_gmail: useGmail,
      redirect_port: portStr && Number(portStr) > 0 ? Number(portStr) : undefined,
    };
  };

  container.querySelector("#kb-google-save-btn")?.addEventListener("click", () => {
    if (!actions.onSaveGoogleOAuthConfig) return;
    void actions.onSaveGoogleOAuthConfig(collectGoogleOAuthPayload());
  });

  container.querySelector("#kb-google-signin-btn")?.addEventListener("click", () => {
    if (!actions.onStartGoogleOAuth) return;
    void actions.onStartGoogleOAuth(collectGoogleOAuthPayload());
  });

  container.querySelector("#kb-google-refresh-btn")?.addEventListener("click", () => {
    if (!actions.onRefreshGoogleOAuth) return;
    void actions.onRefreshGoogleOAuth();
  });

  container.querySelector("#kb-google-link-gmail-btn")?.addEventListener("click", () => {
    if (!actions.onConnectGmailOAuth) return;
    void actions.onConnectGmailOAuth();
  });

  container.querySelector("#kb-google-disconnect-btn")?.addEventListener("click", () => {
    if (!actions.onDisconnectGoogleOAuth) return;
    void actions.onDisconnectGoogleOAuth(false);
  });

  bindMailAccountsEvents(
    container,
    async () => {
      if (actions.onMailChanged) {
        await actions.onMailChanged();
      }
    },
    actions.onStartGoogleOAuth
  );

  bindDriveAccountsEvents(container, {
    onConnectGoogleDrive: actions.onConnectGoogleDrive,
    onConnectOneDrive: actions.onConnectOneDrive,
    onDisconnectProvider: actions.onDisconnectDriveProvider,
  });

  bindActionProvidersListeners(container, actions);
  bindContentTranslationListeners(container, actions);

  if (preserveScroll) {
    const nextPage = container.querySelector(".kb-page") as HTMLElement | null;
    if (nextPage) nextPage.scrollTop = prevPageScrollTop;
    container.scrollTop = prevVpScrollTop;
    const nextOverrideWrap = container.querySelector(
      ".kb-app-lang-editor .table-wrap"
    ) as HTMLElement | null;
    if (nextOverrideWrap && prevOverrideScrollTop > 0) {
      nextOverrideWrap.scrollTop = prevOverrideScrollTop;
    }
  }
}

function renderContentTranslationSectionHtml(
  accOpen: boolean,
  isUnlocked: boolean,
  discoveredCloudModelIds: string[]
): string {
  const cfg = state.contentTranslationConfig;
  const known = cfg?.known_languages ?? [];
  const primary = cfg?.primary_language ?? "en";
  const resolved = cfg?.resolved_model;
  const resolvedModelId = resolved?.model_id ?? "gemma-4-e4b";
  const resolvedCost = resolved?.tier_label || resolved?.cost_hint || "local";
  const ctLabel = isUnlocked
    ? `${primary.toUpperCase()} · ${known.length}`
    : t("settings.locked_lower");
  const detailsMap = new Map(
    (cfg?.known_language_details ?? []).map((d) => [d.code, d])
  );
  const catalog = cfg?.catalog ?? [];
  const availableToAdd = catalog.filter((c) => !known.includes(c.code));
  const datalistHtml = availableToAdd
    .map(
      (c) =>
        `<option value="${escapeHtml(c.code)}">${escapeHtml(c.name)}${c.native && c.native !== c.name ? ` · ${escapeHtml(c.native)}` : ""}</option>`
    )
    .join("");
  const prefModel = cfg?.model_preference ?? "auto_cheapest";
  const knownModelChoices = new Set(["auto_cheapest", "gemma-4-e4b", ...discoveredCloudModelIds]);
  const extraPrefOption =
    prefModel && !knownModelChoices.has(prefModel)
      ? `<option value="${escapeHtml(prefModel)}" selected>${escapeHtml(prefModel)}</option>`
      : "";
  const statusMsg = state.contentTranslationStatusMsg;
  const isErrorBanner = Boolean(
    statusMsg &&
      (statusMsg.toLowerCase().includes("error") ||
        statusMsg.toLowerCase().includes("failed") ||
        statusMsg.startsWith(t("common.error_prefix")))
  );
  const statusBanner = isErrorBanner
    ? `<div class="banner danger">${escapeHtml(statusMsg)}</div>`
    : "";

  return `
    <div class="card kb-acc-card acc ${accOpen ? "open" : ""}" id="kb-translation-card">
      <div class="settings-acc-bar">
        <button type="button" class="acc-h" data-settings-accordion="translation">
          <span>${escapeHtml(t("settings.tr_section"))}</span>
          <span class="ct">${escapeHtml(ctLabel)}</span>
          ${icon("chev", "ico-sm")}
        </button>
        <span class="muted">${escapeHtml(t("settings.tr_sub"))}</span>
      </div>
      ${
        !accOpen
          ? ""
          : !isUnlocked
            ? `<div class="muted acc-b">${escapeHtml(t("settings.tr_unlock_hint"))}</div>`
            : `
      <div class="acc-b section">
        ${statusBanner}
        <div class="card inset">
          <div class="card-h">
            <b>${escapeHtml(t("settings.tr_known_title"))}</b>
          </div>
          <div class="muted">${escapeHtml(t("settings.tr_known_note"))}</div>
          <div class="kb-chip-list" id="kb-tr-known-list">
            ${known
              .map((code) => {
                const info = detailsMap.get(code);
                const label = info
                  ? info.native && info.native !== info.name
                    ? `${info.name} · ${info.native} (${code})`
                    : `${info.name} (${code})`
                  : code;
                const isPrimary = code === primary;
                return `
                  <div class="kb-kv-row" data-tr-lang-row="${escapeHtml(code)}">
                    <span>
                      <b>${escapeHtml(label)}</b>
                      ${isPrimary ? `<span class="badge good">${escapeHtml(t("settings.tr_primary_badge"))}</span>` : ""}
                    </span>
                    <span>
                      ${
                        isPrimary
                          ? ""
                          : `<button type="button" class="btn-text pri" data-tr-make-primary="${escapeHtml(code)}">${escapeHtml(t("settings.tr_make_primary"))}</button>`
                      }
                      ${
                        known.length > 1
                          ? `<button type="button" class="btn-text" data-tr-remove-lang="${escapeHtml(code)}">${escapeHtml(t("settings.tr_remove_lang"))}</button>`
                          : ""
                      }
                    </span>
                  </div>
                `;
              })
              .join("")}
          </div>
          <div class="form-row">
            <select id="kb-tr-catalog-select" class="select">
              <option value="">+</option>
              ${availableToAdd
                .map(
                  (c) =>
                    `<option value="${escapeHtml(c.code)}">${escapeHtml(c.name)}${
                      c.native && c.native !== c.name ? ` · ${escapeHtml(c.native)}` : ""
                    } (${escapeHtml(c.code)})</option>`
                )
                .join("")}
            </select>
            <input
              id="kb-tr-custom-lang"
              class="input"
              type="text"
              list="kb-tr-lang-datalist"
              spellcheck="false"
              autocomplete="off"
              placeholder="${escapeHtml(t("settings.tr_add_ph"))}"
            />
            <datalist id="kb-tr-lang-datalist">${datalistHtml}</datalist>
            <button id="kb-tr-add-lang-btn" type="button" class="btn primary">${escapeHtml(t("settings.tr_add_btn"))}</button>
          </div>
        </div>

        <div class="card inset">
          <div class="card-h">
            <b>${escapeHtml(t("settings.tr_model_card"))}</b>
            <span class="end muted">${escapeHtml(t("settings.tr_resolved_meta", { model: resolvedModelId, cost: resolvedCost }))}</span>
          </div>
          <div class="form-row">
            <select id="kb-tr-model-select" class="select" aria-label="${escapeHtml(t("settings.tr_model_card"))}">
              <option value="auto_cheapest" ${prefModel === "auto_cheapest" ? "selected" : ""}>${escapeHtml(t("settings.tr_auto_cheapest", { resolved: resolvedModelId }))}</option>
              <option value="gemma-4-e4b" ${prefModel === "gemma-4-e4b" ? "selected" : ""}>gemma-4-e4b (local · $0)</option>
              ${discoveredCloudModelIds
                .map(
                  (mid) =>
                    `<option value="${escapeHtml(mid)}" ${prefModel === mid ? "selected" : ""}>${escapeHtml(mid)}</option>`
                )
                .join("")}
              ${extraPrefOption}
            </select>
          </div>
          <div class="form-row">
            <label class="news-src-checks">
              <input type="checkbox" id="kb-tr-auto-mail" ${cfg?.auto_translate_mail !== false ? "checked" : ""} />
              ${escapeHtml(t("settings.tr_mail_auto"))}
            </label>
          </div>
          <div class="form-row">
            <label class="news-src-checks">
              <input type="checkbox" id="kb-tr-mail-promos" ${cfg?.mail_include_promos_pings ? "checked" : ""} />
              ${escapeHtml(t("settings.tr_mail_promos"))}
            </label>
          </div>
          <div class="form-row">
            <label class="news-src-checks">
              <input type="checkbox" id="kb-tr-auto-news" ${cfg?.auto_translate_news !== false ? "checked" : ""} />
              ${escapeHtml(t("settings.tr_news_auto"))}
            </label>
          </div>
          <div class="form-row">
            <button id="kb-tr-backfill-btn" type="button" class="btn">${escapeHtml(t("settings.tr_backfill_btn"))}</button>
          </div>
        </div>
      </div>
      `
      }
    </div>
  `;
}

function bindContentTranslationListeners(
  container: HTMLElement,
  actions: KnowledgeActions
): void {
  const cfg = state.contentTranslationConfig;
  const known = cfg?.known_languages ?? [];
  const update = (patch: {
    known_languages?: string[];
    primary_language?: string;
    model_preference?: string;
    auto_translate_mail?: boolean;
    auto_translate_news?: boolean;
    mail_include_promos_pings?: boolean;
  }) => {
    if (actions.onUpdateContentTranslation) {
      void actions.onUpdateContentTranslation(patch);
    }
  };

  container.querySelectorAll("[data-tr-make-primary]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const code = (btn as HTMLElement).getAttribute("data-tr-make-primary") ?? "";
      if (!code) return;
      const nextKnown = known.includes(code) ? known : [...known, code];
      update({ known_languages: nextKnown, primary_language: code });
    });
  });

  container.querySelectorAll("[data-tr-remove-lang]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const code = (btn as HTMLElement).getAttribute("data-tr-remove-lang") ?? "";
      if (!code) return;
      const nextKnown = known.filter((k) => k !== code);
      if (nextKnown.length === 0) return;
      const patch: { known_languages: string[]; primary_language?: string } = {
        known_languages: nextKnown,
      };
      if (cfg?.primary_language === code) {
        patch.primary_language = nextKnown[0];
      }
      update(patch);
    });
  });

  const addLang = (rawVal: string) => {
    const clean = rawVal.trim();
    if (!clean) return;
    if (known.some((k) => k.toLowerCase() === clean.toLowerCase())) return;
    update({ known_languages: [...known, clean] });
  };

  container.querySelector("#kb-tr-catalog-select")?.addEventListener("change", (ev) => {
    const val = (ev.currentTarget as HTMLSelectElement).value;
    if (val) addLang(val);
  });

  const customInp = container.querySelector("#kb-tr-custom-lang") as HTMLInputElement | null;
  container.querySelector("#kb-tr-add-lang-btn")?.addEventListener("click", () => {
    const catSel = (container.querySelector("#kb-tr-catalog-select") as HTMLSelectElement | null)?.value ?? "";
    addLang((customInp?.value ?? "").trim() || catSel);
  });
  customInp?.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      addLang(customInp.value);
    }
  });

  container.querySelector("#kb-tr-model-select")?.addEventListener("change", (ev) => {
    const val = (ev.currentTarget as HTMLSelectElement).value;
    if (val) update({ model_preference: val });
  });

  container.querySelector("#kb-tr-auto-mail")?.addEventListener("change", (ev) => {
    update({ auto_translate_mail: (ev.currentTarget as HTMLInputElement).checked });
  });

  container.querySelector("#kb-tr-mail-promos")?.addEventListener("change", (ev) => {
    update({ mail_include_promos_pings: (ev.currentTarget as HTMLInputElement).checked });
  });

  container.querySelector("#kb-tr-auto-news")?.addEventListener("change", (ev) => {
    update({ auto_translate_news: (ev.currentTarget as HTMLInputElement).checked });
  });

  container.querySelector("#kb-tr-backfill-btn")?.addEventListener("click", () => {
    if (actions.onBackfillContentTranslation) {
      void actions.onBackfillContentTranslation();
    }
  });
}

function renderGoogleOAuthSectionHtml(): string {
  const g = state.googleOAuthStatus;
  const configured = Boolean(g?.configured);
  const signedIn = Boolean(g?.signed_in);
  const gmailScopeOn = !g?.scopes || g.scopes.includes("https://mail.google.com/");
  const badge = signedIn
    ? `<span class="badge good">${escapeHtml(t("settings.google_signed_in_badge", { email: g?.email || "" }))}</span>`
    : configured
      ? `<span class="badge soft">${escapeHtml(t("settings.google_saved_badge", { id: g?.masked_client_id || "ready" }))}</span>`
      : `<span class="badge warn">${escapeHtml(t("settings.not_configured"))}</span>`;

  return `
    <div class="section card" id="kb-google-oauth-card">
      <div class="card-h">
        <b>${escapeHtml(t("settings.google_title"))}</b>
        <span class="end">${badge}</span>
      </div>
      <div class="muted">
        ${escapeHtml(t("settings.google_desc", {
          uri: g?.redirect_port ? `http://127.0.0.1:${g.redirect_port}/oauth/google/callback` : "http://127.0.0.1:<auto>/oauth/google/callback",
        }))}
      </div>
      ${
        state.googleOAuthMessage
          ? `<div id="kb-google-status-banner" class="banner">${escapeHtml(state.googleOAuthMessage)}</div>`
          : `<div id="kb-google-status-banner" class="muted"></div>`
      }
      <div class="form-row">
        <input id="kb-google-client-id" class="input" type="text" spellcheck="false" autocomplete="off" placeholder="${escapeHtml(configured ? t("settings.google_cid_saved", { id: g?.masked_client_id || "client_id" }) : t("settings.google_cid_ph"))}" />
        <input id="kb-google-client-secret" class="input" type="password" spellcheck="false" autocomplete="off" placeholder="${escapeHtml(configured ? t("settings.google_csec_saved") : t("settings.google_csec_ph"))}" />
        <input id="kb-google-redir-port" class="input pin" type="number" min="0" max="65535" value="${g?.redirect_port || ""}" placeholder="${escapeHtml(t("settings.google_port_ph"))}" title="${escapeHtml(t("settings.google_port_title"))}" />
      </div>
      <div class="form-row">
        <textarea id="kb-google-client-json" class="textarea mono" rows="2" spellcheck="false" placeholder="${escapeHtml(t("settings.google_json_ph"))}"></textarea>
      </div>
      <div class="form-row">
        <label class="muted"><input type="file" id="kb-google-json-file" accept=".json" class="w-210" /> ${escapeHtml(t("settings.google_load_json"))}</label>
        <label class="news-src-checks"><input type="checkbox" id="kb-google-scope-gmail" ${gmailScopeOn ? "checked" : ""} /> ${escapeHtml(t("settings.google_gmail_scope"))}</label>
        <input id="kb-google-extra-scopes" class="input" type="text" spellcheck="false" placeholder="${escapeHtml(t("settings.google_extra_scopes_ph"))}" />
      </div>
      <div class="form-row">
        <button id="kb-google-save-btn" type="button" class="btn">${escapeHtml(t("settings.google_save_btn"))}</button>
        <button id="kb-google-signin-btn" type="button" class="btn primary">${escapeHtml(t("settings.google_signin_btn"))}</button>
        ${
          signedIn
            ? `
          <button id="kb-google-link-gmail-btn" type="button" class="btn">${escapeHtml(t("settings.google_connect_gmail_btn"))}</button>
          <button id="kb-google-refresh-btn" type="button" class="btn">${escapeHtml(t("settings.google_refresh_btn"))}</button>
          <button id="kb-google-disconnect-btn" type="button" class="btn">${escapeHtml(t("settings.google_disconnect_btn"))}</button>
        `
            : ""
        }
      </div>
    </div>
  `;
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
      ? `<button type="button" class="btn-text" data-brain-open-source="${escapeHtml(normalizedSrcUrl)}" data-brain-source-title="${escapeHtml(e.name)}">${escapeHtml(t("brain.source"))}</button>`
      : "";

  const runSkillBtnHtml =
    e.type === "skill"
      ? `<button type="button" class="btn-text pri" data-run-skill="${escapeHtml(e.slug)}">${escapeHtml(t("brain.run_skill"))}</button>`
      : "";
  const skillRedteamBadge =
    e.type === "skill"
      ? e.attributes?.redteam_passed
        ? `<span class="badge soft" title="${escapeHtml(String(e.attributes?.redteam_summary ?? t("brain.redteam_ok_title")))}">${escapeHtml(t("brain.redteam_ok"))}</span>`
        : `<span class="badge soft">${escapeHtml(t("brain.gate_pending"))}</span>`
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
          <span class="muted">${escapeHtml(t("brain.tier_path", { tier: e.tier, path: e.path }))}</span>
          ${skillRedteamBadge}
        </span>
        ${runSkillBtnHtml}
        ${sourceBtnHtml}
        <button type="button" class="btn-text" data-delete-brain-entity="${escapeHtml(e.slug)}">${escapeHtml(t("brain.forget"))}</button>
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
    t("brain.ranking_lexical");
  const profileInfo = kb.profile;
  const isUnlocked = Boolean(profileInfo?.unlocked && profileInfo?.active_profile);
  const activeProfile = profileInfo?.active_profile ?? null;
  const thisWeek = kb.this_week ?? [];
  const searchRes = state.brainSearchResults;
  const hasActiveSearch = Boolean(state.brainSearchQuery.trim() && searchRes);

  const typeOrder = [
    { key: "skill", label: t("brain.type_skill") },
    { key: "order", label: t("brain.type_order") },
    { key: "person", label: t("brain.type_person") },
    { key: "organization", label: t("brain.type_organization") },
    { key: "promotion", label: t("brain.type_promotion") },
    { key: "place", label: t("brain.type_place") },
    { key: "account", label: t("brain.type_account") },
    { key: "note", label: t("brain.type_note") },
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
    ? `<div class="muted">${escapeHtml(t("brain.unlock_to_store"))}</div>`
    : brainEntities.length === 0
      ? `<div class="muted">${escapeHtml(t("brain.empty_entities"))}</div>`
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
                <div class="label">${escapeHtml(t("brain.type_other"))} <span class="ct">${otherEntities.length}</span></div>
                ${otherEntities.map((item) => renderBrainEntityCardHtml(item)).join("")}
              </div>
            `
            : "",
        ].join("");

  const searchResultsSectionHtml = hasActiveSearch && searchRes
    ? `
      <div class="card" id="brain-search-results-section">
        <div class="card-h">
          <b>${escapeHtml(t("brain.search_results_for", { query: state.brainSearchQuery }))}</b>
          <span class="muted">${escapeHtml(t("brain.search_counts", { entities: searchRes.entities.length, passages: searchRes.passages.length, mail: searchRes.mail.length }))}</span>
          <button id="brain-search-clear-btn" type="button" class="btn-text end">${escapeHtml(t("common.clear"))}</button>
        </div>
        ${
          searchRes.entities.length === 0 &&
          searchRes.passages.length === 0 &&
          searchRes.mail.length === 0
            ? `<div class="muted">${escapeHtml(t("brain.no_matches"))}</div>`
            : `
              ${
                searchRes.entities.length > 0
                  ? `
                    <div class="section">
                      <div class="label">${escapeHtml(t("brain.matching_entities"))} <span class="ct">${searchRes.entities.length}</span></div>
                      ${searchRes.entities.map((e) => renderBrainEntityCardHtml(e)).join("")}
                    </div>
                  `
                  : ""
              }
              ${
                searchRes.passages.length > 0
                  ? `
                    <div class="section">
                      <div class="label">${escapeHtml(t("brain.matching_passages"))} <span class="ct">${searchRes.passages.length}</span></div>
                      ${searchRes.passages
                        .map(
                          (p) => `
                            <div class="source-row">
                              <div class="source-row-top">
                                <button type="button" class="btn-text pri t" data-brain-open-source="${escapeHtml(p.url)}" data-brain-source-title="${escapeHtml(p.title || p.entity || p.url)}">
                                  ${escapeHtml(p.title || p.entity || p.url)}
                                </button>
                                <button type="button" class="btn-text" data-delete-passage="${escapeHtml(p.id)}">${escapeHtml(t("brain.forget"))}</button>
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
                      <div class="label">${escapeHtml(t("brain.matching_mail"))} <span class="ct">${searchRes.mail.length}</span></div>
                      ${searchRes.mail
                        .map((m) => {
                          const mid = String(m.id ?? "");
                          const sender = String(m.from_name || m.from_addr || "");
                          const subj = String(m.subject ?? t("brain.no_subject"));
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

  const skillProposals = kb.skill_proposals ?? [];
  const recipeCount = Number(kb.domain_recipes_count ?? 0);
  const evalCases = kb.evals ?? [];
  const evalSuiteRun = state.evalSuiteRun;
  const skillBuilderSectionHtml = isUnlocked
    ? `
      <div class="card" id="brain-skill-builder-section">
        <div class="card-h">
          <b>${escapeHtml(t("brain.skill_builder_title"))}</b>
          <span class="badge soft">${escapeHtml(t("brain.proposed_n", { count: skillProposals.length }))}</span>
          <span class="muted">${escapeHtml(tCount("brain.recipes_cached", recipeCount))}</span>
          <button id="brain-redteam-audit-btn" type="button" class="btn end">${escapeHtml(t("brain.redteam_audit_btn"))}</button>
          <button id="brain-mine-skills-btn" type="button" class="btn">${escapeHtml(t("brain.mine_habits_btn"))}</button>
        </div>
        ${state.redteamAuditSummary ? `<div class="muted mb-2">${escapeHtml(state.redteamAuditSummary)}</div>` : ""}
        ${
          skillProposals.length === 0
            ? `<div class="muted">${escapeHtml(t("brain.empty_proposals"))}</div>`
            : skillProposals
                .map((sp) => {
                  const stepsList = (sp.skill.step_graph ?? [])
                    .map(
                      (st) =>
                        `${st.primitive}${st.send_gate || st.mutating ? " [send_gate]" : ""}`
                    )
                    .join(" -> ");
                  const trigList = (sp.skill.trigger_examples ?? []).slice(0, 3).join(", ");
                  const rt = sp.skill.redteam;
                  const rtBlocked = rt ? !rt.passed : false;
                  const rtBadge = rt
                    ? `<span class="badge soft" title="${escapeHtml(rt.summary)}">${escapeHtml(rt.passed ? t("brain.redteam_passed_n", { passed: rt.cases_passed, total: rt.cases_run }) : t("brain.redteam_blocked"))}</span>`
                    : "";
                  return `
                    <div class="source-row">
                      <div class="source-row-top">
                        <span class="t">
                          <span class="flag">${escapeHtml(t("brain.proposed_skill_flag"))}</span>
                          <b>${escapeHtml(sp.skill.name)}</b>
                          <span class="muted">${Math.round((sp.confidence || 0.75) * 100)}%</span>
                          ${rtBadge}
                        </span>
                        <button type="button" class="btn primary" data-accept-skill-proposal="${escapeHtml(sp.proposal_id)}"${rtBlocked ? " disabled" : ""}>${escapeHtml(t("brain.accept"))}</button>
                        <button type="button" class="btn" data-reject-skill-proposal="${escapeHtml(sp.proposal_id)}">${escapeHtml(t("brain.reject"))}</button>
                      </div>
                      <div class="muted">${escapeHtml(sp.reason)}</div>
                      ${stepsList ? `<div class="source-row-meta">${escapeHtml(t("brain.pipeline_line", { steps: stepsList }))}</div>` : ""}
                      ${trigList ? `<div class="source-row-meta">${escapeHtml(t("brain.triggers_line", { triggers: trigList }))}</div>` : ""}
                    </div>
                  `;
                })
                .join("")
        }
      </div>
    `
    : "";

  const evalsSectionHtml = `
    <div class="card" id="brain-evals-section">
      <div class="card-h">
        <b>${escapeHtml(t("brain.evals_title"))}</b>
        <span class="badge soft">${escapeHtml(tCount("brain.eval_fixtures_n", evalCases.length))}</span>
        ${
          evalSuiteRun
            ? `<span class="badge soft">${escapeHtml(t("brain.eval_passing_n", { passed: evalSuiteRun.passed, total: evalSuiteRun.total }))}</span>`
            : ""
        }
        <button id="brain-run-evals-btn" type="button" class="btn primary end"${state.evalRunning ? " disabled" : ""}>
          ${escapeHtml(state.evalRunning ? t("brain.eval_running") : t("brain.run_eval_suite"))}
        </button>
        <button id="brain-run-evals-live-btn" type="button" class="btn"${state.evalRunning ? " disabled" : ""}>
          ${escapeHtml(t("brain.run_live_models"))}
        </button>
      </div>
      ${state.evalStatusMsg ? `<div class="muted mb-2">${escapeHtml(state.evalStatusMsg)}</div>` : ""}
      ${
        evalCases.length === 0
          ? `<div class="muted">${escapeHtml(t("brain.empty_evals"))}</div>`
          : evalCases
              .map((ev) => {
                const liveRes = evalSuiteRun?.results.find((r) => r.eval_id === ev.eval_id);
                const gemmaRes = liveRes?.targets?.local_gemma ?? ev.last_run?.local_gemma;
                const cloudRes = liveRes?.targets?.cloud ?? ev.last_run?.cloud;
                const gemmaBadge = gemmaRes
                  ? `<span class="badge soft">${escapeHtml(t("brain.eval_gemma_status", { status: gemmaRes.passed ? "PASS" : "FAIL" }))}</span>`
                  : `<span class="badge soft">${escapeHtml(t("brain.eval_gemma_status", { status: "unrun" }))}</span>`;
                const cloudBadge = cloudRes
                  ? `<span class="badge soft">${escapeHtml(t("brain.eval_cloud_status", { status: cloudRes.passed ? "PASS" : "FAIL" }))}</span>`
                  : `<span class="badge soft">${escapeHtml(t("brain.eval_cloud_status", { status: "unrun" }))}</span>`;
                const expTools = (ev.expected?.expected_tools ?? []).join(", ");
                const expSummary = [
                  expTools ? `tools: [${expTools}]` : "",
                  ev.expected?.expected_task_agent ? `agent: ${ev.expected.expected_task_agent}` : "",
                  ev.expected?.require_send_gate ? "send_gate" : "",
                  ev.expected?.min_citations ? `min_cites: ${ev.expected.min_citations}` : "",
                ]
                  .filter(Boolean)
                  .join(" · ");
                return `
                  <div class="source-row" data-eval-row="${escapeHtml(ev.eval_id)}">
                    <div class="source-row-top">
                      <span class="t">
                        <span class="flag">eval</span>
                        <b>${escapeHtml(ev.title || ev.eval_id)}</b>
                        ${gemmaBadge}
                        ${cloudBadge}
                      </span>
                      <button type="button" class="btn-text pri" data-run-eval-id="${escapeHtml(ev.eval_id)}"${state.evalRunning ? " disabled" : ""}>${escapeHtml(t("brain.eval_run_btn"))}</button>
                      <button type="button" class="btn-text" data-delete-eval-id="${escapeHtml(ev.eval_id)}">${escapeHtml(t("common.delete"))}</button>
                    </div>
                    <div class="muted">${escapeHtml(t("brain.eval_prompt", { prompt: (ev.user_msg || "").slice(0, 140) }))}</div>
                    ${expSummary ? `<div class="source-row-meta">${escapeHtml(t("brain.eval_assertions", { summary: expSummary }))}</div>` : ""}
                  </div>
                `;
              })
              .join("")
      }
    </div>
  `;

  container.innerHTML = `
    <div class="kb-page" id="brain-view-root">
      <div class="kb-page-inner">
        <div class="view-h">
          <div>
            <h1>${escapeHtml(t("brain.title"))}</h1>
            <p>${escapeHtml(
              isUnlocked && activeProfile
                ? t("brain.profile_sub", { name: activeProfile.name, ranking: brainRankingLabel, mod: MOD_LABEL })
                : t("brain.locked_sub", { mod: MOD_LABEL })
            )}</p>
          </div>
          <div class="end kb-head-actions">
            <button id="brain-open-settings-btn" type="button" class="btn">${icon("settings", "ico-sm")}<span>${escapeHtml(t("common.settings"))}</span></button>
            <button id="brain-close-btn" type="button" class="icon-btn" title="${escapeHtml(t("brain.close_btn_title"))}">${icon("x", "ico-sm")}</button>
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
                placeholder="${escapeHtml(t("brain.search_ph"))}"
                value="${escapeHtml(state.brainSearchQuery)}"
              />
            </div>
            <button id="brain-search-btn" type="button" class="btn primary">${escapeHtml(t("common.search"))}</button>
            ${
              state.brainSearchQuery
                ? `<button id="brain-search-reset-btn" type="button" class="btn">${escapeHtml(t("common.clear"))}</button>`
                : ""
            }
          </div>
        </div>

        ${searchResultsSectionHtml}

        ${skillBuilderSectionHtml}

        ${evalsSectionHtml}

        <div class="card">
          <div class="card-h">
            <b>${escapeHtml(t("brain.entity_cards_title"))}</b>
            <span class="badge soft">${brainEntities.length}</span>
            <span class="end muted">${escapeHtml(brainRankingLabel)}</span>
          </div>
          ${entityGroupsHtml}
        </div>

        <div class="card">
          <div class="card-h">
            <b>${escapeHtml(t("brain.this_week_title"))}</b>
            <span class="badge soft">${thisWeek.length}</span>
            <span class="end muted">${escapeHtml(t("brain.this_week_sub"))}</span>
          </div>
          ${
            thisWeek.length === 0
              ? `<div class="muted">${escapeHtml(t("brain.this_week_empty"))}</div>`
              : thisWeek
                  .map((item) => {
                    const kindText = item.kind === "received" ? t("brain.kind_received") : t("brain.kind_read");
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
            <b>${escapeHtml(t("brain.top_domains_title"))}</b>
            <span class="badge soft">${kb.top_domains.length}</span>
            <span class="end muted">${escapeHtml(t("news.trust_cap_note"))}</span>
          </div>
          ${
            kb.top_domains.length === 0
              ? `<div class="muted">${escapeHtml(t("brain.no_domains"))}</div>`
              : `<div class="table-wrap">
                  <table class="table">
                    <thead>
                      <tr>
                        <th>${escapeHtml(t("brain.col_domain"))}</th>
                        <th class="num">${escapeHtml(t("news.col_system"))}</th>
                        <th>${escapeHtml(t("brain.col_personal_trust_short"))}</th>
                        <th class="num">${escapeHtml(t("news.col_effective"))}</th>
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
                            ? ` <span class="badge soft" title="${escapeHtml(t("news.conflict_title"))}">${escapeHtml(t("news.conflict_badge"))}</span>`
                            : "";
                          return `
                            <tr data-domain-trust-row="${escapeHtml(d.domain)}">
                              <td>
                                <div><b>${escapeHtml(d.domain)}</b></div>
                                <div class="muted">${escapeHtml(t("brain.domain_visits", { visits: d.visits, reason: sysReason }))}</div>
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
                                      ? `<button type="button" class="btn-text" data-trust-reset-domain="${escapeHtml(d.domain)}">${escapeHtml(t("common.reset"))}</button>`
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
            <b>${escapeHtml(t("brain.recent_passages"))}</b>
            <span class="badge soft">${kb.passages.length}</span>
          </div>
          ${
            kb.passages.length === 0
              ? `<div class="muted">${escapeHtml(t("brain.no_passages"))}</div>`
              : kb.passages
                  .map(
                    (p) => `
                <div class="source-row">
                  <div class="source-row-top">
                    <b class="t">${escapeHtml(p.entity || p.url)}</b>
                    <button type="button" class="btn-text" data-delete-passage="${escapeHtml(p.id)}">${escapeHtml(t("brain.forget"))}</button>
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

  container.querySelector("#brain-mine-skills-btn")?.addEventListener("click", () => {
    actions.onMineSkillProposals?.();
  });

  container.querySelector("#brain-redteam-audit-btn")?.addEventListener("click", () => {
    void actions.onRunRedteamAudit?.();
  });

  container.querySelector("#brain-run-evals-btn")?.addEventListener("click", () => {
    void actions.onRunEvalSuite?.(undefined, "deterministic");
  });

  container.querySelector("#brain-run-evals-live-btn")?.addEventListener("click", () => {
    void actions.onRunEvalSuite?.(undefined, "live");
  });

  container.querySelectorAll("[data-run-eval-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const eid = (btn as HTMLElement).getAttribute("data-run-eval-id") ?? "";
      if (eid) void actions.onRunEvalSuite?.(eid);
    });
  });

  container.querySelectorAll("[data-delete-eval-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const eid = (btn as HTMLElement).getAttribute("data-delete-eval-id") ?? "";
      if (eid) void actions.onDeleteEvalCase?.(eid);
    });
  });

  container.querySelectorAll("[data-accept-skill-proposal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = (btn as HTMLElement).getAttribute("data-accept-skill-proposal") ?? "";
      if (pid) actions.onAcceptSkillProposal?.(pid);
    });
  });

  container.querySelectorAll("[data-reject-skill-proposal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = (btn as HTMLElement).getAttribute("data-reject-skill-proposal") ?? "";
      if (pid) actions.onRejectSkillProposal?.(pid);
    });
  });

  container.querySelectorAll("[data-run-skill]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const slug = (btn as HTMLElement).getAttribute("data-run-skill") ?? "";
      if (slug) actions.onRunSkill?.(slug);
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
