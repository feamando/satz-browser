import { t } from "./i18n";
import { icon } from "./design-system/icons";
import { escapeHtml, IS_MAC, state } from "./state";

export interface ProfileGateActions {
  onUnlockProfile?: (profileId: string, pin: string) => void | Promise<void>;
  onUnlockProfileKeychain?: (profileId: string) => void | Promise<void>;
  onCreateProfile?: (name: string, pin: string) => void | Promise<void>;
  onImportProfileFile?: (bundleB64: string, pin: string, localPin?: string) => void | Promise<void>;
  onOpenSettings?: () => void | Promise<void>;
}

function encodeBytesToBase64(bytes: Uint8Array): string {
  const chunkSize = 0x2000;
  let binary = "";
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const slice = bytes.subarray(i, Math.min(i + chunkSize, bytes.length));
    binary += String.fromCharCode(...slice);
  }
  return btoa(binary);
}

function formatBundleBytes(sizeBytes: number): string {
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  const kb = sizeBytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(2)} MB`;
}

function renderProfileUploadInnerHtml(prefix: string): string {
  const draft = state.profileImportDraft;
  const busy = Boolean(state.profileUnlocking);
  const dis = busy ? "disabled" : "";
  const fileInput = `<input id="${escapeHtml(prefix)}-upload-file-input" class="sr-only-file-input" type="file" accept=".satzprofile,.json,application/octet-stream" data-prof-upload-file="${escapeHtml(prefix)}" ${dis} />`;
  if (!draft) {
    return `
      <div class="section profile-upload-block">
        <div class="form-row">
          <span class="muted">${escapeHtml(t("profile.upload_section_title"))}</span>
          <button id="${escapeHtml(prefix)}-upload-pick-btn" type="button" class="btn end" data-prof-upload-pick="${escapeHtml(prefix)}" ${dis}>
            ${icon("upload", "ico-sm")}
            <span>${escapeHtml(t("profile.upload_btn"))}</span>
          </button>
          ${fileInput}
        </div>
      </div>
    `;
  }
  return `
    <div class="section profile-upload-block">
      <div class="profile-upload-meta">
        <span>${escapeHtml(t("profile.upload_selected", { filename: draft.filename, size: formatBundleBytes(draft.sizeBytes) }))}</span>
        <button id="${escapeHtml(prefix)}-upload-pick-btn" type="button" class="btn-text" data-prof-upload-pick="${escapeHtml(prefix)}" ${dis}>${escapeHtml(t("profile.upload_btn"))}</button>
        <button id="${escapeHtml(prefix)}-import-cancel-btn" type="button" class="btn-text end" data-prof-import-cancel="${escapeHtml(prefix)}" ${dis}>${escapeHtml(t("profile.upload_cancel_btn"))}</button>
        ${fileInput}
      </div>
      <div class="muted">${escapeHtml(t("profile.upload_pin_hint"))}</div>
      <div class="form-row">
        <input
          id="${escapeHtml(prefix)}-import-pin-input"
          class="input pin"
          type="password"
          inputmode="numeric"
          maxlength="6"
          spellcheck="false"
          autocorrect="off"
          autocapitalize="off"
          placeholder="${escapeHtml(t("profile.pin6_placeholder"))}"
          data-prof-import-pin="${escapeHtml(prefix)}"
          ${dis}
        />
        ${
          draft.needLocalPin
            ? `
          <input
            id="${escapeHtml(prefix)}-import-local-pin-input"
            class="input pin"
            type="password"
            inputmode="numeric"
            maxlength="6"
            spellcheck="false"
            autocorrect="off"
            autocapitalize="off"
            placeholder="${escapeHtml(t("profile.upload_local_pin_ph"))}"
            data-prof-import-local-pin="${escapeHtml(prefix)}"
            ${dis}
          />
        `
            : ""
        }
        <button
          id="${escapeHtml(prefix)}-import-submit-btn"
          type="button"
          class="btn primary"
          data-prof-import-submit="${escapeHtml(prefix)}"
          ${dis}
        >${escapeHtml(busy ? t("profile.importing_short") : t("profile.upload_open_btn"))}</button>
      </div>
    </div>
  `;
}

export function renderProfileUploadSectionHtml(prefix: string): string {
  return `
    <div class="sep"></div>
    <div class="profile-upload-host" data-prof-upload-host="${escapeHtml(prefix)}">
      ${renderProfileUploadInnerHtml(prefix)}
    </div>
  `;
}

export function bindProfileUploadSectionEvents(
  container: ParentNode,
  prefix: string,
  onImportProfileFile?: (bundleB64: string, pin: string, localPin?: string) => void | Promise<void>
): void {
  const host = container.querySelector(`[data-prof-upload-host="${prefix}"]`) as HTMLElement | null;
  if (!host) return;

  const wireHost = (focusPin: boolean) => {
    const pickBtn = host.querySelector(`[data-prof-upload-pick="${prefix}"]`) as HTMLButtonElement | null;
    const fileInput = host.querySelector(`[data-prof-upload-file="${prefix}"]`) as HTMLInputElement | null;
    const cancelBtn = host.querySelector(`[data-prof-import-cancel="${prefix}"]`) as HTMLButtonElement | null;
    const pinInput = host.querySelector(`[data-prof-import-pin="${prefix}"]`) as HTMLInputElement | null;
    const localPinInput = host.querySelector(`[data-prof-import-local-pin="${prefix}"]`) as HTMLInputElement | null;
    const submitBtn = host.querySelector(`[data-prof-import-submit="${prefix}"]`) as HTMLButtonElement | null;

    pickBtn?.addEventListener("click", () => {
      if (state.profileUnlocking) return;
      fileInput?.click();
    });

    fileInput?.addEventListener("change", async () => {
      const f = fileInput.files?.[0];
      if (!f) return;
      try {
        const buf = await f.arrayBuffer();
        const bytes = new Uint8Array(buf);
        const bundleB64 = encodeBytesToBase64(bytes);
        state.profileImportDraft = {
          filename: f.name || "profile.satzprofile",
          bundleB64,
          sizeBytes: bytes.byteLength,
          needLocalPin: false,
        };
        state.profileStatusMessage = "";
        host.innerHTML = renderProfileUploadInnerHtml(prefix);
        wireHost(true);
      } catch (err) {
        state.profileStatusMessage = `${t("common.error_prefix")} ${String(err)}`;
      }
    });

    cancelBtn?.addEventListener("click", () => {
      if (state.profileUnlocking) return;
      state.profileImportDraft = null;
      host.innerHTML = renderProfileUploadInnerHtml(prefix);
      wireHost(false);
    });

    const submitImport = () => {
      if (state.profileUnlocking || !state.profileImportDraft) return;
      const pin = pinInput?.value.trim() ?? "";
      const localPin = localPinInput?.value.trim() || undefined;
      if (!pin || !onImportProfileFile) return;
      void onImportProfileFile(state.profileImportDraft.bundleB64, pin, localPin);
    };

    submitBtn?.addEventListener("click", submitImport);
    pinInput?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        submitImport();
      }
    });
    localPinInput?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        submitImport();
      }
    });

    if (focusPin && pinInput && !state.profileUnlocking) {
      pinInput.focus();
    }
  };

  wireHost(false);
}

export function renderInlineProfileGateHtml(opts: {
  iconName: "mail" | "news" | "drive" | "settings";
  subtitle: string;
}): string {
  const prof = state.knowledge.profile;
  const profiles = prof?.profiles ?? [];
  const hasProfiles = profiles.length > 0;
  const unlocking = state.profileUnlocking;
  const progressText = state.profileUnlockLabel || t("profile.unlocking_progress");

  const defaultPid =
    prof?.active_profile_id ||
    profiles[0]?.id ||
    "";
  const selectedProfile =
    profiles.find((p) => p.id === defaultPid) ?? profiles[0] ?? null;
  const canKeychain = hasProfiles && Boolean(selectedProfile);
  const kcLabel = IS_MAC ? t("settings.touch_id") : t("profile.unlock_keychain_btn");

  const heading = hasProfiles
    ? t("profile.locked_title")
    : t("profile.create_new_title");

  return `
    <div class="drives-locked-wrap inline-profile-gate">
      <div class="card drives-locked-card inline-profile-card">
        <div class="card-h">
          ${icon(opts.iconName, "ico-sm")}
          <b>${escapeHtml(heading)}</b>
          ${
            unlocking
              ? `<span class="end badge soft inline-unlock-badge"><span class="satz-spinner" aria-hidden="true"></span><span>${escapeHtml(t("profile.unlocking_short"))}</span></span>`
              : ""
          }
        </div>
        <div class="muted">${escapeHtml(opts.subtitle)}</div>

        ${
          unlocking
            ? `
              <div class="unlock-loading-row" role="status" aria-live="polite">
                <span class="satz-spinner" aria-hidden="true"></span>
                <span>${escapeHtml(progressText)}</span>
              </div>
            `
            : ""
        }

        ${
          !unlocking && state.profileStatusMessage
            ? `<div class="banner"><span>${escapeHtml(state.profileStatusMessage)}</span></div>`
            : ""
        }

        ${
          hasProfiles
            ? `
              <div class="section">
                <div class="form-row">
                  <select id="inline-unlock-profile-select" class="input" ${unlocking ? "disabled" : ""}>
                    ${profiles
                      .map(
                        (p) =>
                          `<option value="${escapeHtml(p.id)}" ${p.id === selectedProfile?.id ? "selected" : ""}>${escapeHtml(p.name)} (${escapeHtml(p.id)})</option>`
                      )
                      .join("")}
                  </select>
                </div>
                <div class="form-row">
                  <input
                    id="inline-unlock-pin-input"
                    class="input mono"
                    type="password"
                    inputmode="numeric"
                    maxlength="6"
                    placeholder="${escapeHtml(t("profile.pin6_placeholder"))}"
                    ${unlocking ? "disabled" : ""}
                  />
                  <button
                    id="inline-unlock-submit-btn"
                    type="button"
                    class="btn primary"
                    ${unlocking ? "disabled" : ""}
                  >
                    ${unlocking ? `<span class="satz-spinner" aria-hidden="true"></span>` : ""}
                    <span>${escapeHtml(unlocking ? t("profile.unlocking_short") : t("profile.unlock_btn"))}</span>
                  </button>
                </div>
                ${
                  canKeychain
                    ? `
                      <div>
                        <button
                          id="inline-unlock-keychain-btn"
                          type="button"
                          class="btn"
                          ${unlocking ? "disabled" : ""}
                        >
                          ${escapeHtml(kcLabel)}
                        </button>
                      </div>
                    `
                    : ""
                }
              </div>
            `
            : ""
        }

        <div class="section inline-profile-create-block">
          <div class="muted">${escapeHtml(hasProfiles ? t("profile.or_create_new") : t("profile.create_required_subtitle"))}</div>
          <div class="form-row">
            <input
              id="inline-create-name-input"
              class="input"
              type="text"
              placeholder="${escapeHtml(t("profile.name_placeholder"))}"
              ${unlocking ? "disabled" : ""}
            />
            <input
              id="inline-create-pin-input"
              class="input mono"
              type="password"
              inputmode="numeric"
              maxlength="6"
              placeholder="${escapeHtml(t("profile.pin6_placeholder"))}"
              ${unlocking ? "disabled" : ""}
            />
            <button
              id="inline-create-submit-btn"
              type="button"
              class="btn ${hasProfiles ? "" : "primary"}"
              ${unlocking ? "disabled" : ""}
            >
              ${escapeHtml(unlocking ? t("profile.creating") : t("profile.create_unlock"))}
            </button>
          </div>
        </div>
        ${renderProfileUploadSectionHtml("inline")}
      </div>
    </div>
  `;
}

export function bindInlineProfileGateEvents(
  container: HTMLElement,
  actions: ProfileGateActions
): void {
  const sel = container.querySelector(
    "#inline-unlock-profile-select"
  ) as HTMLSelectElement | null;
  const pinInput = container.querySelector(
    "#inline-unlock-pin-input"
  ) as HTMLInputElement | null;
  const unlockBtn = container.querySelector(
    "#inline-unlock-submit-btn"
  ) as HTMLButtonElement | null;
  const kcBtn = container.querySelector(
    "#inline-unlock-keychain-btn"
  ) as HTMLButtonElement | null;
  const nameInput = container.querySelector(
    "#inline-create-name-input"
  ) as HTMLInputElement | null;
  const createPinInput = container.querySelector(
    "#inline-create-pin-input"
  ) as HTMLInputElement | null;
  const createBtn = container.querySelector(
    "#inline-create-submit-btn"
  ) as HTMLButtonElement | null;

  const submitUnlock = () => {
    if (state.profileUnlocking) return;
    const pid = sel?.value || "";
    const pin = pinInput?.value.trim() || "";
    if (!pid || !pin) return;
    if (actions.onUnlockProfile) {
      void actions.onUnlockProfile(pid, pin);
    } else {
      void actions.onOpenSettings?.();
    }
  };

  unlockBtn?.addEventListener("click", submitUnlock);
  pinInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submitUnlock();
    }
  });

  kcBtn?.addEventListener("click", () => {
    if (state.profileUnlocking) return;
    const pid = sel?.value || "";
    if (!pid) return;
    if (actions.onUnlockProfileKeychain) {
      void actions.onUnlockProfileKeychain(pid);
    } else {
      void actions.onOpenSettings?.();
    }
  });

  const submitCreate = () => {
    if (state.profileUnlocking) return;
    const name = nameInput?.value.trim() || "";
    const pin = createPinInput?.value.trim() || "";
    if (!name || !pin) return;
    if (actions.onCreateProfile) {
      void actions.onCreateProfile(name, pin);
    } else {
      void actions.onOpenSettings?.();
    }
  };

  createBtn?.addEventListener("click", submitCreate);
  createPinInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submitCreate();
    }
  });

  bindProfileUploadSectionEvents(container, "inline", actions.onImportProfileFile);
}
