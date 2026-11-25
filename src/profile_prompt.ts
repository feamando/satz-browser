import { t } from "./i18n";
import { icon } from "./design-system/icons";
import { escapeHtml, IS_MAC, state } from "./state";

export interface ProfileGateActions {
  onUnlockProfile?: (profileId: string, pin: string) => void | Promise<void>;
  onUnlockProfileKeychain?: (profileId: string) => void | Promise<void>;
  onCreateProfile?: (name: string, pin: string) => void | Promise<void>;
  onOpenSettings?: () => void | Promise<void>;
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
}
