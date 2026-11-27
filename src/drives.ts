import { icon, type IconName } from "./design-system/icons";
import { t } from "./i18n";
import { escapeHtml, formatRelativeTime, state } from "./state";
import type {
  DriveFileTypeFilter,
  DriveItem,
  DriveNavSnapshot,
  DriveProviderFilter,
  DrivesStatusResponse,
} from "./types";

export interface ConfiguredDriveProviders {
  gdrive: boolean;
  onedrive: boolean;
  list: Array<"gdrive" | "onedrive">;
}

/** Determine which cloud drive providers are actually configured or connected in Settings/vault. */
export function getConfiguredDriveProviders(
  dStatus: DrivesStatusResponse | null | undefined = state.drivesStatus ?? state.sidecar.drives
): ConfiguredDriveProviders {
  const gConnected = Boolean(dStatus?.google?.connected);
  const odConnected = Boolean(dStatus?.onedrive?.connected);
  const gConfigured = Boolean(
    gConnected ||
      (dStatus?.google?.total_files ?? 0) > 0 ||
      ((dStatus?.google?.configured || state.googleOAuthStatus?.configured) &&
        !dStatus?.google?.signed_in_gmail_only)
  );
  const odConfigured = Boolean(
    odConnected ||
      Boolean(dStatus?.onedrive?.configured) ||
      (dStatus?.onedrive?.total_files ?? 0) > 0
  );
  const list: Array<"gdrive" | "onedrive"> = [];
  if (gConfigured) list.push("gdrive");
  if (odConfigured) list.push("onedrive");
  return { gdrive: gConfigured, onedrive: odConfigured, list };
}

export interface DriveAccountsActions {
  onConnectGoogleDrive: (payload: {
    client_secret_json?: string;
    login_hint?: string;
  }) => void;
  onConnectOneDrive: (payload: {
    client_id?: string;
    tenant_id?: string;
    login_hint?: string;
  }) => void;
  onDisconnectProvider: (provider: "gdrive" | "onedrive") => void;
}
import {
  bindInlineProfileGateEvents,
  renderInlineProfileGateHtml,
} from "./profile_prompt";

export interface DrivesViewActions {
  onNavigateFolder: (folderKey: string, pushHistory?: boolean) => void;
  onNavigateBack: () => void;
  onNavigateUp: () => void;
  onChangeProviderFilter: (provider: DriveProviderFilter) => void;
  onChangeFileTypeFilter: (fileType: DriveFileTypeFilter) => void;
  onChangeOwnerFilter: (owner: string) => void;
  onResetFilters: () => void;
  onOpenDocumentInTab: (url: string, title: string, activate: boolean) => void;
  onTriggerSync: (fullResync?: boolean) => void;
  onConnectGoogleDrive: (payload: {
    client_secret_json?: string;
    login_hint?: string;
  }) => void;
  onConnectOneDrive: (payload: {
    client_id?: string;
    tenant_id?: string;
    login_hint?: string;
  }) => void;
  onDisconnectProvider: (provider: "gdrive" | "onedrive") => void;
  onOpenProfileUnlock: () => void;
  onUnlockProfile?: (profileId: string, pin: string) => void | Promise<void>;
  onUnlockProfileKeychain?: (profileId: string) => void | Promise<void>;
  onCreateProfile?: (name: string, pin: string) => void | Promise<void>;
  onImportProfileFile?: (bundleB64: string, pin: string, localPin?: string) => void | Promise<void>;
}

export function snapshotCurrentDrivesNav(): DriveNavSnapshot {
  return {
    folderKey: state.drivesFolderKey,
    provider: state.drivesProviderFilter,
    fileType: state.drivesFileTypeFilter,
    owner: state.drivesOwnerFilter,
    query: state.drivesSearchQuery,
  };
}

export function pushDrivesNavHistory(snap?: DriveNavSnapshot): void {
  const entry = snap ?? snapshotCurrentDrivesNav();
  const top = state.drivesNavStack[state.drivesNavStack.length - 1];
  if (
    top &&
    top.folderKey === entry.folderKey &&
    top.provider === entry.provider &&
    top.fileType === entry.fileType &&
    top.owner === entry.owner &&
    top.query === entry.query
  ) {
    return;
  }
  state.drivesNavStack.push(entry);
  if (state.drivesNavStack.length > 60) {
    state.drivesNavStack.shift();
  }
}

function itemCategoryIcon(item: DriveItem): IconName {
  if (item.is_folder || item.file_category === "folder") return "folder";
  switch (item.file_category) {
    case "sheet":
      return "sheet";
    case "slide":
      return "slide";
    case "image":
      return "image";
    case "doc":
    case "pdf":
      return "doc";
    default:
      return "box";
  }
}

function itemCategoryLabel(cat: string): string {
  switch (cat) {
    case "folder":
      return t("drives.filter_type_folder");
    case "doc":
      return t("drives.filter_type_doc");
    case "sheet":
      return t("drives.filter_type_sheet");
    case "slide":
      return t("drives.filter_type_slide");
    case "pdf":
      return t("drives.filter_type_pdf");
    case "image":
      return t("drives.filter_type_image");
    default:
      return t("drives.filter_type_other");
  }
}

function providerBadgeLabel(provider: string): string {
  if (provider === "gdrive") return t("drives.badge_gdrive");
  if (provider === "onedrive") return t("drives.badge_onedrive");
  return t("drives.badge_shared");
}

export function renderDrivesView(
  container: HTMLElement,
  actions: DrivesViewActions
): void {
  const isUnlocked = Boolean(
    state.knowledge.profile?.unlocked && state.knowledge.profile?.active_profile
  );

  const hasProfiles = (state.knowledge.profile?.profiles.length ?? 0) > 0;
  if (!isUnlocked || !hasProfiles) {
    container.innerHTML = `
      <div class="drives-view">
        ${renderInlineProfileGateHtml({
          iconName: "drive",
          subtitle: t("drives.locked_subtitle"),
        })}
      </div>
    `;
    bindInlineProfileGateEvents(container, {
      onUnlockProfile: actions.onUnlockProfile,
      onUnlockProfileKeychain: actions.onUnlockProfileKeychain,
      onCreateProfile: actions.onCreateProfile,
      onImportProfileFile: actions.onImportProfileFile,
      onOpenSettings: actions.onOpenProfileUnlock,
    });
    return;
  }

  const dStatus = state.drivesStatus ?? state.sidecar.drives ?? null;
  const gConnected = Boolean(dStatus?.google?.connected);
  const odConnected = Boolean(dStatus?.onedrive?.connected);
  const anyConnected = gConnected || odConnected;
  const configuredProviders = getConfiguredDriveProviders(dStatus);
  const showCloudFilter = configuredProviders.list.length >= 2;
  if (
    state.drivesProviderFilter !== "all" &&
    (!showCloudFilter || !configuredProviders[state.drivesProviderFilter])
  ) {
    state.drivesProviderFilter = "all";
  }
  const showAccountsPanel = state.drivesAccountsOpen || !anyConnected;

  const canGoBack = state.drivesNavStack.length > 0;
  const canGoUp =
    state.drivesParentKey !== null && state.drivesFolderKey !== "" && !state.drivesSearchQuery;

  const crumbs =
    state.drivesBreadcrumbs.length > 0
      ? state.drivesBreadcrumbs
      : [{ key: "", name: t("drives.root_label") }];

  const breadcrumbsHtml = crumbs
    .map((c, idx) => {
      const isLast = idx === crumbs.length - 1 && !state.drivesSearchQuery;
      const sep = idx > 0 ? `<span class="drives-crumb-sep">/</span>` : "";
      const label = c.key === "" ? t("drives.root_label") : c.name;
      return `
        ${sep}
        <button
          type="button"
          class="drives-crumb-btn ${isLast ? "current" : ""}"
          data-drives-crumb="${escapeHtml(c.key)}"
          title="${escapeHtml(label)}"
        >
          ${c.key === "" ? icon("drive", "ico-sm") : ""}
          <span>${escapeHtml(label)}</span>
        </button>
      `;
    })
    .join("");

  const createTargets = state.drivesCreateTargets;
  const gCreateTargets = createTargets.filter((x) => x.provider === "gdrive");
  const odCreateTargets = createTargets.filter((x) => x.provider === "onedrive");

  const createMenuHtml =
    state.drivesCreateMenuOpen && createTargets.length > 0
      ? `
        <div class="menu drives-create-menu" role="menu">
          ${
            gCreateTargets.length > 0
              ? `
                <div class="drives-create-group">${escapeHtml(t("drives.filter_provider_gdrive"))}</div>
                ${gCreateTargets
                  .map(
                    (ct) => `
                  <button
                    type="button"
                    class="menu-item"
                    data-drives-create-url="${escapeHtml(ct.url)}"
                    data-drives-create-label="${escapeHtml(ct.label)}"
                  >
                    ${icon(ct.id.endsWith("sheet") ? "sheet" : ct.id.endsWith("slide") ? "slide" : "doc", "ico-sm")}
                    <span>${escapeHtml(ct.label)}</span>
                  </button>
                `
                  )
                  .join("")}
              `
              : ""
          }
          ${
            odCreateTargets.length > 0
              ? `
                <div class="drives-create-group">${escapeHtml(t("drives.filter_provider_onedrive"))}</div>
                ${odCreateTargets
                  .map(
                    (ct) => `
                  <button
                    type="button"
                    class="menu-item"
                    data-drives-create-url="${escapeHtml(ct.url)}"
                    data-drives-create-label="${escapeHtml(ct.label)}"
                  >
                    ${icon(ct.id.endsWith("excel") ? "sheet" : ct.id.endsWith("powerpoint") ? "slide" : "doc", "ico-sm")}
                    <span>${escapeHtml(ct.label)}</span>
                  </button>
                `
                  )
                  .join("")}
              `
              : ""
          }
        </div>
      `
      : "";

  const isBusySync = Boolean(dStatus?.syncing || dStatus?.indexing || state.drivesSyncing);
  const isViewLoading = Boolean(state.drivesLoading);

  const accountsPanelHtml = showAccountsPanel
    ? renderDriveAccountsPanelHtml(gConnected, odConnected)
    : "";

  const providerOptions: Array<{ id: DriveProviderFilter; label: string }> = showCloudFilter
    ? [
        { id: "all", label: t("drives.filter_provider_all") },
        ...configuredProviders.list.map((p) => ({
          id: p,
          label: t(
            p === "gdrive" ? "drives.filter_provider_gdrive" : "drives.filter_provider_onedrive"
          ),
        })),
      ]
    : [];

  const typeOptions: Array<{ id: DriveFileTypeFilter; label: string }> = [
    { id: "all", label: t("drives.filter_type_all") },
    { id: "folder", label: t("drives.filter_type_folder") },
    { id: "doc", label: t("drives.filter_type_doc") },
    { id: "sheet", label: t("drives.filter_type_sheet") },
    { id: "slide", label: t("drives.filter_type_slide") },
    { id: "pdf", label: t("drives.filter_type_pdf") },
    { id: "image", label: t("drives.filter_type_image") },
    { id: "other", label: t("drives.filter_type_other") },
  ];

  const ownersList = state.drivesFacets.owners.filter((o) => !o.is_me);
  const hasActiveFilterOrSearch =
    state.drivesProviderFilter !== "all" ||
    state.drivesFileTypeFilter !== "all" ||
    state.drivesOwnerFilter !== "all" ||
    Boolean(state.drivesSearchQuery.trim());

  const statusBannerHtml = state.drivesStatusMessage
    ? `<div class="banner">${escapeHtml(state.drivesStatusMessage)}</div>`
    : "";

  const trimmedSearch = state.drivesSearchQuery.trim();
  const scopeNoteHtml =
    state.drivesScope === "search"
      ? `<div class="banner"><span>${escapeHtml(
          trimmedSearch
            ? t("drives.scope_search_query_banner", { query: trimmedSearch })
            : t("drives.scope_search_banner")
        )} · ${state.drivesItems.length}</span><button id="drives-reset-filters-banner-btn" class="btn" type="button">${escapeHtml(t("drives.clear_filters"))}</button></div>`
      : state.drivesScope === "filtered"
        ? `<div class="banner"><span>${escapeHtml(t("drives.scope_filter_banner"))} · ${state.drivesItems.length}</span><button id="drives-reset-filters-banner-btn" class="btn" type="button">${escapeHtml(t("drives.clear_filters"))}</button></div>`
        : "";

  const showParentPathInRow =
    state.drivesScope === "search" || state.drivesScope === "filtered";

  const loadingText =
    state.drivesFolderKey && !hasActiveFilterOrSearch
      ? t("drives.loading_folder")
      : t("drives.loading_files");

  const loadingBarHtml = isViewLoading
    ? `<div class="drives-loading-bar" aria-hidden="true"></div>`
    : `<div class="drives-loading-bar is-idle" aria-hidden="true"></div>`;

  const loadingBannerHtml =
    isViewLoading && state.drivesItems.length > 0
      ? `
        <div class="drives-loading-banner" role="status" aria-live="polite">
          <span class="satz-spinner" aria-hidden="true"></span>
          <span>${escapeHtml(loadingText)}</span>
        </div>
      `
      : "";

  const rowsHtml =
    isViewLoading && state.drivesItems.length === 0
      ? `
        <div class="drives-empty drives-empty-loading" role="status" aria-live="polite">
          <span class="satz-spinner" aria-hidden="true"></span>
          <span>${escapeHtml(loadingText)}</span>
        </div>
      `
      : state.drivesItems.length === 0
      ? `
        <div class="drives-empty">
          <span>${escapeHtml(
            !anyConnected
              ? t("drives.empty_connect")
              : hasActiveFilterOrSearch
                ? t("drives.empty_search")
                : t("drives.empty_folder")
          )}</span>
          ${
            hasActiveFilterOrSearch
              ? `<button id="drives-empty-reset-btn" class="btn" type="button">${escapeHtml(t("drives.clear_filters"))}</button>`
              : ""
          }
        </div>
      `
      : `
        <table class="table drives-table">
          <thead>
            <tr>
              <th>${escapeHtml(t("drives.col_name"))}</th>
              ${showCloudFilter ? `<th>${escapeHtml(t("drives.col_cloud"))}</th>` : ""}
              <th>${escapeHtml(t("drives.col_type"))}</th>
              <th>${escapeHtml(t("drives.col_owner"))}</th>
              <th>${escapeHtml(t("drives.col_modified"))}</th>
              <th>${escapeHtml(t("drives.col_brain"))}</th>
            </tr>
          </thead>
          <tbody>
            ${state.drivesItems
              .map((item) => renderDriveItemRowHtml(item, showParentPathInRow, showCloudFilter))
              .join("")}
          </tbody>
        </table>
      `;

  container.innerHTML = `
    <div class="drives-view">
      <div class="drives-bar">
        <div class="drives-nav-btns">
          <button
            id="drives-back-btn"
            class="icon-btn"
            type="button"
            ${canGoBack ? "" : "disabled"}
            title="${escapeHtml(t("drives.back_title"))}"
            aria-label="${escapeHtml(t("drives.back_btn"))}"
          >
            ${icon("back")}
          </button>
          <button
            id="drives-up-btn"
            class="icon-btn"
            type="button"
            ${canGoUp ? "" : "disabled"}
            title="${escapeHtml(t("drives.up_title"))}"
            aria-label="${escapeHtml(t("drives.up_btn"))}"
          >
            ${icon("up")}
          </button>
        </div>

        <nav class="drives-crumbs" aria-label="${escapeHtml(t("drives.root_label"))}">
          ${breadcrumbsHtml}
        </nav>

        <div class="drives-top-actions">
          <div class="drives-create-anchor">
            <button
              id="drives-create-btn"
              class="btn primary"
              type="button"
              ${createTargets.length === 0 ? "disabled" : ""}
              title="${escapeHtml(t("drives.create_title"))}"
              aria-expanded="${state.drivesCreateMenuOpen ? "true" : "false"}"
            >
              ${icon("plus", "ico-sm")}
              <span>${escapeHtml(t("drives.create_btn"))}</span>
              ${icon("chev", "ico-sm")}
            </button>
            ${createMenuHtml}
          </div>

          <button
            id="drives-sync-btn"
            class="btn"
            type="button"
            ${!anyConnected || isBusySync ? "disabled" : ""}
            title="${escapeHtml(t("drives.sync_title"))}"
          >
            ${icon("reload", "ico-sm")}
            <span>${escapeHtml(isBusySync ? t("common.syncing") : t("drives.sync_btn"))}</span>
          </button>

          <button
            id="drives-accounts-toggle-btn"
            class="btn ${showAccountsPanel ? "on" : ""}"
            type="button"
            title="${escapeHtml(t("drives.accounts_btn"))}"
          >
            ${icon("settings", "ico-sm")}
            <span>${escapeHtml(t("drives.accounts_btn"))}</span>
          </button>
        </div>
      </div>

      ${accountsPanelHtml}

      <div class="drives-filter-bar">
        ${
          providerOptions.length > 0
            ? `<div class="drives-filter-group" role="group" aria-label="${escapeHtml(t("drives.col_cloud"))}">
          ${providerOptions
            .map(
              (po) => `
            <button
              type="button"
              class="chip ${state.drivesProviderFilter === po.id ? "on" : ""}"
              data-drives-provider="${po.id}"
            >
              <span>${escapeHtml(po.label)}</span>
            </button>
          `
            )
            .join("")}
        </div>`
            : ""
        }

        <div class="drives-filter-group" role="group" aria-label="${escapeHtml(t("drives.col_type"))}">
          ${typeOptions
            .map(
              (to) => `
            <button
              type="button"
              class="chip ${state.drivesFileTypeFilter === to.id ? "on" : ""}"
              data-drives-filetype="${to.id}"
            >
              <span>${escapeHtml(to.label)}</span>
            </button>
          `
            )
            .join("")}
        </div>

        <select
          id="drives-owner-select"
          class="drives-owner-select"
          aria-label="${escapeHtml(t("drives.col_owner"))}"
        >
          <option value="all" ${state.drivesOwnerFilter === "all" ? "selected" : ""}>${escapeHtml(t("drives.filter_owner_all"))}</option>
          <option value="me" ${state.drivesOwnerFilter === "me" ? "selected" : ""}>${escapeHtml(t("drives.filter_owner_me"))}</option>
          ${ownersList
            .map(
              (ow) => `
            <option value="${escapeHtml(ow.value)}" ${state.drivesOwnerFilter === ow.value ? "selected" : ""}>
              ${escapeHtml(ow.label)} (${ow.count})
            </option>
          `
            )
            .join("")}
        </select>

        ${
          hasActiveFilterOrSearch
            ? `<button id="drives-clear-filters-btn" class="btn-text" type="button">${escapeHtml(t("drives.clear_filters"))}</button>`
            : ""
        }
      </div>

      ${loadingBarHtml}
      <div class="drives-scroll${isViewLoading ? " is-loading" : ""}" aria-busy="${isViewLoading ? "true" : "false"}">
        ${loadingBannerHtml}
        ${statusBannerHtml}
        ${scopeNoteHtml}
        ${rowsHtml}
      </div>
    </div>
  `;

  bindDrivesEvents(container, actions);
}

export function renderDriveAccountsPanelHtml(
  gConnectedParam?: boolean,
  odConnectedParam?: boolean
): string {
  const dStatus = state.drivesStatus ?? state.sidecar.drives ?? null;
  const gConnected = gConnectedParam ?? Boolean(dStatus?.google?.connected);
  const odConnected = odConnectedParam ?? Boolean(dStatus?.onedrive?.connected);
  const gInfo = dStatus?.google;
  const odInfo = dStatus?.onedrive;
  const gConfigured = Boolean(gInfo?.configured || state.googleOAuthStatus?.configured);

  return `
    <div class="drives-accounts-panel">
      <div class="drives-acct-card">
        <div class="drives-acct-head">
          <div class="drives-acct-title">
            ${icon("drive", "ico-sm")}
            <span>${escapeHtml(t("drives.gdrive_title"))}</span>
          </div>
          <span class="pill ${gConnected ? "accent" : ""}">
            ${escapeHtml(
              gConnected
                ? `${gInfo?.email || "Connected"} · ${gInfo?.total_files ?? 0}`
                : t("common.offline")
            )}
          </span>
        </div>
        ${
          gConnected
            ? `
              <div class="muted">
                ${escapeHtml(`${gInfo?.total_files ?? 0} items · ${gInfo?.indexed_docs ?? 0} Brain docs`)}
                ${gInfo?.last_error ? ` · ${escapeHtml(gInfo.last_error)}` : ""}
              </div>
              <div class="drives-acct-row">
                <button type="button" class="btn" data-drives-disconnect="gdrive">
                  ${escapeHtml(t("drives.disconnect_btn"))}
                </button>
              </div>
            `
            : `
              <div class="drives-acct-form">
                ${
                  gConfigured
                    ? `<div class="muted">OAuth client configured in local vault (${escapeHtml(gInfo?.masked_client_id || state.googleOAuthStatus?.masked_client_id || "ready")}).</div>`
                    : `
                      <textarea
                        id="drives-gdrive-secret-json"
                        class="input"
                        rows="2"
                        placeholder="${escapeHtml(t("drives.gdrive_json_placeholder"))}"
                      ></textarea>
                    `
                }
                <div class="drives-acct-row">
                  <input
                    id="drives-gdrive-hint"
                    class="input"
                    type="email"
                    placeholder="name@company.example"
                    value="${escapeHtml(gInfo?.email || state.googleOAuthStatus?.email || "")}"
                  />
                  <button id="drives-connect-gdrive-btn" class="btn primary" type="button">
                    ${escapeHtml(t("drives.connect_gdrive"))}
                  </button>
                </div>
                ${gInfo?.last_error ? `<div class="muted">${escapeHtml(gInfo.last_error)}</div>` : ""}
              </div>
            `
        }
      </div>

      <div class="drives-acct-card">
        <div class="drives-acct-head">
          <div class="drives-acct-title">
            ${icon("drive", "ico-sm")}
            <span>${escapeHtml(t("drives.onedrive_title"))}</span>
          </div>
          <span class="pill ${odConnected ? "accent" : ""}">
            ${escapeHtml(
              odConnected
                ? `${odInfo?.email || "Connected"} · ${odInfo?.total_files ?? 0}`
                : t("common.offline")
            )}
          </span>
        </div>
        ${
          odConnected
            ? `
              <div class="muted">
                ${escapeHtml(`${odInfo?.total_files ?? 0} items · ${odInfo?.indexed_docs ?? 0} Brain docs`)}
                ${odInfo?.last_error ? ` · ${escapeHtml(odInfo.last_error)}` : ""}
              </div>
              <div class="drives-acct-row">
                <button type="button" class="btn" data-drives-disconnect="onedrive">
                  ${escapeHtml(t("drives.disconnect_btn"))}
                </button>
              </div>
            `
            : `
              <div class="drives-acct-form">
                ${
                  odInfo?.configured
                    ? `<div class="muted">Entra client configured in local vault (${escapeHtml(odInfo.masked_client_id || "ready")}).</div>`
                    : `
                      <div class="drives-acct-row">
                        <input
                          id="drives-onedrive-client-id"
                          class="input"
                          type="text"
                          placeholder="${escapeHtml(t("drives.onedrive_cid_placeholder"))}"
                        />
                        <input
                          id="drives-onedrive-tenant-id"
                          class="input"
                          type="text"
                          placeholder="${escapeHtml(t("drives.onedrive_tid_placeholder"))}"
                          value="${escapeHtml(odInfo?.tenant_id || "common")}"
                        />
                      </div>
                    `
                }
                <div class="drives-acct-row">
                  <button id="drives-connect-onedrive-btn" class="btn primary" type="button">
                    ${escapeHtml(t("drives.connect_onedrive"))}
                  </button>
                </div>
                ${odInfo?.last_error ? `<div class="muted">${escapeHtml(odInfo.last_error)}</div>` : ""}
              </div>
            `
        }
      </div>

      <div class="drives-privacy-strip">
        <span>${escapeHtml(t("drives.local_privacy_note"))}</span>
      </div>
    </div>
  `;
}

function renderDriveItemRowHtml(
  item: DriveItem,
  showParentPath: boolean,
  showCloudCol = true
): string {
  const ico = icon(itemCategoryIcon(item), "ico-sm");
  const ownerText = item.is_me
    ? t("drives.owner_me")
    : item.owner_name || item.owner_email || t("drives.owner_me");
  const modText =
    item.modified_at > 0 ? formatRelativeTime(String(item.modified_at)) : "";
  const subParts: string[] = [];
  if (showParentPath && item.resolved_path) {
    subParts.push(item.resolved_path);
  }
  if (item.core_summary && !item.is_folder) {
    subParts.push(item.core_summary);
  }
  const subLine = subParts.join(" · ");

  return `
    <tr
      class="drives-row ${item.is_folder ? "is-folder" : "is-file"}"
      data-drive-item-key="${escapeHtml(item.item_key)}"
      data-drive-is-folder="${item.is_folder ? "1" : "0"}"
      data-drive-nav-key="${escapeHtml(item.navigate_key)}"
      data-drive-url="${escapeHtml(item.web_url)}"
      data-drive-name="${escapeHtml(item.name)}"
      title="${escapeHtml(item.core_summary || item.resolved_path || item.name)}"
    >
      <td>
        <div class="drives-name-cell">
          <span class="drives-item-icon">${ico}</span>
          <div class="drives-name-stack">
            <span class="drives-item-name truncate">${escapeHtml(item.name)}</span>
            ${subLine ? `<span class="drives-item-sub truncate">${escapeHtml(subLine)}</span>` : ""}
          </div>
        </div>
      </td>
      ${
        showCloudCol
          ? `<td>
        <span class="pill">${escapeHtml(providerBadgeLabel(item.provider))}</span>
      </td>`
          : ""
      }
      <td class="muted">${escapeHtml(itemCategoryLabel(item.file_category))}</td>
      <td class="muted truncate" title="${escapeHtml(item.owner_email || ownerText)}">${escapeHtml(ownerText)}</td>
      <td class="muted">${escapeHtml(modText)}</td>
      <td>
        ${
          item.indexed
            ? `<span class="pill accent" title="${escapeHtml(item.brain_slug)}">${escapeHtml(t("drives.badge_indexed"))}</span>`
            : item.is_folder
              ? ""
              : `<span class="muted">${escapeHtml(t("drives.badge_meta"))}</span>`
        }
      </td>
    </tr>
  `;
}

export function bindDriveAccountsEvents(
  container: HTMLElement,
  actions: Partial<DriveAccountsActions>
): void {
  container.querySelector("#drives-connect-gdrive-btn")?.addEventListener("click", () => {
    if (!actions.onConnectGoogleDrive) return;
    const jsonEl = container.querySelector("#drives-gdrive-secret-json") as HTMLTextAreaElement | null;
    const hintEl = container.querySelector("#drives-gdrive-hint") as HTMLInputElement | null;
    actions.onConnectGoogleDrive({
      client_secret_json: jsonEl?.value.trim() || undefined,
      login_hint: hintEl?.value.trim() || undefined,
    });
  });

  container.querySelector("#drives-connect-onedrive-btn")?.addEventListener("click", () => {
    if (!actions.onConnectOneDrive) return;
    const cidEl = container.querySelector("#drives-onedrive-client-id") as HTMLInputElement | null;
    const tidEl = container.querySelector("#drives-onedrive-tenant-id") as HTMLInputElement | null;
    actions.onConnectOneDrive({
      client_id: cidEl?.value.trim() || undefined,
      tenant_id: tidEl?.value.trim() || undefined,
    });
  });

  container.querySelectorAll("[data-drives-disconnect]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!actions.onDisconnectProvider) return;
      const prov = (btn as HTMLElement).getAttribute("data-drives-disconnect") as
        | "gdrive"
        | "onedrive"
        | null;
      if (prov) {
        actions.onDisconnectProvider(prov);
      }
    });
  });
}

function bindDrivesEvents(
  container: HTMLElement,
  actions: DrivesViewActions
): void {
  container.querySelector("#drives-back-btn")?.addEventListener("click", () => {
    actions.onNavigateBack();
  });

  container.querySelector("#drives-up-btn")?.addEventListener("click", () => {
    actions.onNavigateUp();
  });

  container.querySelectorAll("[data-drives-crumb]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetKey = (btn as HTMLElement).getAttribute("data-drives-crumb") ?? "";
      actions.onNavigateFolder(targetKey, true);
    });
  });

  container.querySelector("#drives-create-btn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    state.drivesCreateMenuOpen = !state.drivesCreateMenuOpen;
    renderDrivesView(container, actions);
  });

  container.querySelectorAll("[data-drives-create-url]").forEach((btn) => {
    const openCreateTarget = (activate: boolean) => {
      const el = btn as HTMLElement;
      const url = el.getAttribute("data-drives-create-url") ?? "";
      const label = el.getAttribute("data-drives-create-label") ?? t("drives.create_btn");
      state.drivesCreateMenuOpen = false;
      if (url) {
        actions.onOpenDocumentInTab(url, label, activate);
      }
    };
    btn.addEventListener("click", () => openCreateTarget(true));
    btn.addEventListener("mousedown", (e) => {
      if ((e as MouseEvent).button === 1) e.preventDefault();
    });
    btn.addEventListener("auxclick", (e) => {
      if ((e as MouseEvent).button === 1) {
        e.preventDefault();
        e.stopPropagation();
        openCreateTarget(false);
      }
    });
  });

  container.querySelector("#drives-sync-btn")?.addEventListener("click", (e) => {
    const full = (e as MouseEvent).shiftKey;
    actions.onTriggerSync(full);
  });

  container.querySelector("#drives-accounts-toggle-btn")?.addEventListener("click", () => {
    state.drivesAccountsOpen = !state.drivesAccountsOpen;
    renderDrivesView(container, actions);
  });

  bindDriveAccountsEvents(container, actions);

  container.querySelectorAll("[data-drives-provider]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const prov = (btn as HTMLElement).getAttribute("data-drives-provider") as DriveProviderFilter;
      if (prov) actions.onChangeProviderFilter(prov);
    });
  });

  container.querySelectorAll("[data-drives-filetype]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const ft = (btn as HTMLElement).getAttribute("data-drives-filetype") as DriveFileTypeFilter;
      if (ft) actions.onChangeFileTypeFilter(ft);
    });
  });

  const ownerSel = container.querySelector("#drives-owner-select") as HTMLSelectElement | null;
  ownerSel?.addEventListener("change", () => {
    actions.onChangeOwnerFilter(ownerSel.value);
  });

  for (const sel of [
    "#drives-clear-filters-btn",
    "#drives-reset-filters-banner-btn",
    "#drives-empty-reset-btn",
  ]) {
    container.querySelector(sel)?.addEventListener("click", () => {
      actions.onResetFilters();
    });
  }

  container.querySelectorAll("[data-drive-item-key]").forEach((row) => {
    const el = row as HTMLElement;
    const isFolder = el.getAttribute("data-drive-is-folder") === "1";
    const navKey = el.getAttribute("data-drive-nav-key") ?? "";
    const url = el.getAttribute("data-drive-url") ?? "";
    const name = el.getAttribute("data-drive-name") ?? "";

    el.addEventListener("click", () => {
      if (isFolder) {
        actions.onNavigateFolder(navKey, true);
      } else if (url) {
        actions.onOpenDocumentInTab(url, name, true);
      }
    });

    el.addEventListener("mousedown", (e) => {
      if ((e as MouseEvent).button === 1) {
        e.preventDefault();
      }
    });

    el.addEventListener("auxclick", (e) => {
      if ((e as MouseEvent).button !== 1) return;
      e.preventDefault();
      e.stopPropagation();
      if (!isFolder && url) {
        actions.onOpenDocumentInTab(url, name, false);
      } else if (isFolder) {
        actions.onNavigateFolder(navKey, true);
      }
    });
  });
}
