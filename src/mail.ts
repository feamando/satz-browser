import {
  apiEnsureMailConversation,
  sidecarAddMailAccount,
  sidecarConfirmMailSend,
  sidecarConnectGmailOAuth,
  sidecarDraftMailReply,
  sidecarGetMailAccounts,
  sidecarGetMailEval,
  sidecarGetMailEvalReport,
  sidecarGetMailLane,
  sidecarGetMailMessage,
  sidecarGetMailMessageHtml,
  sidecarGetMailTriage,
  sidecarHideMailMessage,
  sidecarLabelMailEval,
  sidecarLabelMailMessage,
  sidecarOpenMailMessage,
  sidecarPrepareMailSend,
  sidecarRemoveMailAccount,
  sidecarSaveMailAttachment,
  sidecarSearchMail,
  sidecarSyncMail,
  sidecarTestMailAccount,
  sidecarUndoMailSend,
  sidecarUpdateMailSettings,
} from "./api";
import { icon } from "./design-system/icons";
import { t, tCount } from "./i18n";
import {
  bindInlineProfileGateEvents,
  renderInlineProfileGateHtml,
} from "./profile_prompt";
import {
  escapeHtml,
  formatRelativeTime,
  getComposeModelsForPicker,
  getDefaultComposeModelId,
  getModelPrivacySummary,
  getResolvedTheme,
  isContentLanguageAllowed,
  MOD_LABEL,
  state,
} from "./state";
import type { BrowserTab, LocalModelId, MailComposeDraft, MailPreset } from "./types";

const DEFAULT_PRESETS: MailPreset[] = [
  {
    id: "gmail",
    label: "Gmail",
    protocol: "imap",
    in_host: "imap.gmail.com",
    in_port: 993,
    in_security: "ssl",
    smtp_host: "smtp.gmail.com",
    smtp_port: 587,
    smtp_security: "starttls",
  },
  {
    id: "outlook",
    label: "Outlook / Hotmail",
    protocol: "imap",
    in_host: "outlook.office365.com",
    in_port: 993,
    in_security: "ssl",
    smtp_host: "smtp.office365.com",
    smtp_port: 587,
    smtp_security: "starttls",
  },
  {
    id: "icloud",
    label: "iCloud",
    protocol: "imap",
    in_host: "imap.mail.me.com",
    in_port: 993,
    in_security: "ssl",
    smtp_host: "smtp.mail.me.com",
    smtp_port: 587,
    smtp_security: "starttls",
  },
  {
    id: "gmx",
    label: "GMX",
    protocol: "imap",
    in_host: "imap.gmx.net",
    in_port: 993,
    in_security: "ssl",
    smtp_host: "mail.gmx.net",
    smtp_port: 587,
    smtp_security: "starttls",
  },
  {
    id: "webde",
    label: "WEB.DE",
    protocol: "imap",
    in_host: "imap.web.de",
    in_port: 993,
    in_security: "ssl",
    smtp_host: "smtp.web.de",
    smtp_port: 587,
    smtp_security: "starttls",
  },
  {
    id: "custom_imap",
    label: "Custom IMAP",
    protocol: "imap",
    in_host: "",
    in_port: 993,
    in_security: "ssl",
    smtp_host: "",
    smtp_port: 587,
    smtp_security: "starttls",
  },
  {
    id: "custom_pop3",
    label: "Custom POP3",
    protocol: "pop3",
    in_host: "",
    in_port: 995,
    in_security: "ssl",
    smtp_host: "",
    smtp_port: 587,
    smtp_security: "starttls",
  },
];

export interface MailViewActions {
  onOpenEmailMessage: (messageId: string, subject: string) => void;
  onOpenComposeTab: (seed?: {
    to?: string;
    cc?: string;
    subject?: string;
    body?: string;
    in_reply_to?: string;
    references?: string;
    reply_to_message_id?: string;
  }) => void;
  onOpenSiteUrl: (url: string, title: string) => void;
  onSelectMailAccount?: (accountId: string | null) => void;
  onAddMailAccount?: () => void;
  onBindEmailReader?: (
    messageId: string,
    detailObj: Record<string, unknown> | undefined
  ) => void;
  onStartGoogleOAuth?: (payload?: {
    client_id?: string;
    client_secret?: string;
    client_secret_json?: string;
    scopes?: string[] | string;
    connect_gmail?: boolean;
    redirect_port?: number;
  }) => Promise<void>;
  onUnlockProfile?: (profileId: string, pin: string) => void | Promise<void>;
  onUnlockProfileKeychain?: (profileId: string) => void | Promise<void>;
  onCreateProfile?: (name: string, pin: string) => void | Promise<void>;
  onRefreshState: () => Promise<void>;
}

const pendingPreviewIds = new Set<string>();

/** Normalize a web link extracted from email HTML/text; rejects unsafe schemes. */
export function normalizeEmailLinkUrl(rawHref: string): string | null {
  const s = (rawHref || "").trim();
  if (!s || s.startsWith("#")) return null;
  if (/^\/\/[a-z0-9.-]+/i.test(s)) {
    return `https:${s}`;
  }
  if (/^https?:\/\//i.test(s)) {
    return s;
  }
  return null;
}

/** Parse mailto: link into Compose draft seed. */
export function parseMailtoHref(rawHref: string): {
  to: string;
  cc?: string;
  subject?: string;
  body?: string;
} {
  const withoutScheme = rawHref.replace(/^mailto:/i, "");
  const qIdx = withoutScheme.indexOf("?");
  const rawTo = qIdx >= 0 ? withoutScheme.slice(0, qIdx) : withoutScheme;
  const query = qIdx >= 0 ? withoutScheme.slice(qIdx + 1) : "";
  const params = new URLSearchParams(query);
  const decode = (v: string | null) => (v ? v.trim() : "");
  return {
    to: decodeURIComponent(rawTo.trim()),
    cc: decode(params.get("cc")) || undefined,
    subject: decode(params.get("subject")) || undefined,
    body: decode(params.get("body")) || undefined,
  };
}

/** Escape plain text and convert http(s) URLs into safe clickable links. */
function linkifyPlainTextToHtml(text: string): string {
  const urlRe = /(https?:\/\/[^\s<>"')\]}]+)/gi;
  let out = "";
  let lastIdx = 0;
  for (const m of text.matchAll(urlRe)) {
    const start = m.index ?? 0;
    let rawUrl = m[0];
    let trailing = "";
    while (rawUrl.length > 8 && /[.,;:!?)]$/.test(rawUrl)) {
      trailing = rawUrl.slice(-1) + trailing;
      rawUrl = rawUrl.slice(0, -1);
    }
    out += escapeHtml(text.slice(lastIdx, start));
    out += `<a href="${escapeHtml(rawUrl)}" rel="noopener noreferrer">${escapeHtml(rawUrl)}</a>${escapeHtml(trailing)}`;
    lastIdx = start + m[0].length;
  }
  out += escapeHtml(text.slice(lastIdx));
  return out;
}

/** Intercept link clicks inside sandboxed (no-script, same-origin srcdoc) email frames so links open as new conversations inside Satz Browser. */
export function bindMailIframeInteractions(
  container: HTMLElement,
  opts: {
    onOpenUrl: (url: string, title: string) => void;
    onOpenMailto?: (seed: {
      to: string;
      cc?: string;
      subject?: string;
      body?: string;
    }) => void;
  }
): void {
  container.querySelectorAll("iframe.email-frame").forEach((el) => {
    const iframe = el as HTMLIFrameElement;
    const attach = () => {
      let doc: Document | null = null;
      try {
        doc = iframe.contentDocument;
      } catch {
        return;
      }
      if (!doc || !doc.documentElement) return;
      if (doc.documentElement.dataset.satzLinksBound === "1") return;
      doc.documentElement.dataset.satzLinksBound = "1";

      doc.querySelectorAll("a[href]").forEach((a) => {
        const href = (a.getAttribute("href") ?? "").trim();
        const webUrl = normalizeEmailLinkUrl(href);
        if (webUrl) {
          a.setAttribute("rel", "noopener noreferrer");
          if (!a.getAttribute("title")) {
            a.setAttribute("title", t("mail.open_conv_link", { url: webUrl }));
          }
          (a as HTMLElement).style.cursor = "pointer";
        }
      });

      const handleAnchorActivate = (ev: MouseEvent) => {
        if (ev.type === "auxclick" && ev.button !== 1) return;
        const target = ev.target as HTMLElement | null;
        const anchor = target?.closest("a[href]") as HTMLAnchorElement | null;
        if (!anchor) return;
        const rawHref = (anchor.getAttribute("href") ?? "").trim();
        if (!rawHref || rawHref.startsWith("#")) return;

        if (/^mailto:/i.test(rawHref)) {
          ev.preventDefault();
          ev.stopPropagation();
          opts.onOpenMailto?.(parseMailtoHref(rawHref));
          return;
        }

        const webUrl = normalizeEmailLinkUrl(rawHref);
        ev.preventDefault();
        ev.stopPropagation();
        if (webUrl) {
          const label = (
            anchor.textContent ||
            anchor.getAttribute("aria-label") ||
            anchor.getAttribute("title") ||
            anchor.querySelector("img")?.getAttribute("alt") ||
            ""
          )
            .replace(/\s+/g, " ")
            .trim()
            .slice(0, 80);
          opts.onOpenUrl(webUrl, label);
        }
      };

      doc.addEventListener(
        "mousedown",
        (ev) => {
          if (ev.button === 1) {
            const target = ev.target as HTMLElement | null;
            if (target?.closest("a[href]")) ev.preventDefault();
          }
        },
        true
      );
      doc.addEventListener("click", handleAnchorActivate, true);
      doc.addEventListener("auxclick", handleAnchorActivate, true);
      doc.addEventListener(
        "keydown",
        (ev) => {
          const mod = ev.ctrlKey || ev.metaKey;
          if (ev.key === "Escape" || (mod && !ev.altKey)) {
            const kLow = ev.key.toLowerCase();
            if (
              ev.key === "Escape" ||
              kLow === "w" ||
              ev.code === "KeyW" ||
              kLow === "t" ||
              kLow === "n" ||
              kLow === "k" ||
              kLow === "l" ||
              kLow === "b" ||
              kLow === "j" ||
              kLow === "m" ||
              kLow === "d" ||
              /^[1-9]$/.test(kLow)
            ) {
              ev.preventDefault();
              ev.stopPropagation();
              window.dispatchEvent(
                new KeyboardEvent("keydown", {
                  key: ev.key,
                  code: ev.code,
                  ctrlKey: ev.ctrlKey,
                  metaKey: ev.metaKey,
                  shiftKey: ev.shiftKey,
                  altKey: ev.altKey,
                  bubbles: true,
                  cancelable: true,
                })
              );
            }
          }
        },
        true
      );
      doc.addEventListener(
        "submit",
        (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
        },
        true
      );
    };

    iframe.addEventListener("load", attach);
    if (
      iframe.contentDocument?.readyState === "complete" &&
      iframe.contentDocument.body?.childNodes.length
    ) {
      attach();
    }
  });
}

/** Build sandboxed HTML srcdoc synced with the resolved UI theme without inline hex tokens. */
export function buildMailIframeSrcdoc(
  rawHtml: string | undefined,
  plainFallback: string,
  csp: string
): string {
  const resolvedTheme = getResolvedTheme();
  const cs = getComputedStyle(document.documentElement);
  const panelBg = cs.getPropertyValue("--panel").trim();
  const inkColor = cs.getPropertyValue("--ink").trim();
  const mutedColor = cs.getPropertyValue("--muted").trim();
  const accentColor = cs.getPropertyValue("--accent").trim();
  const lineColor = cs.getPropertyValue("--line").trim();
  const themeMeta = `<meta name="color-scheme" content="${resolvedTheme}">`;
  const themeOverrideCss = `<style>
    html, body { background: ${panelBg} !important; color: ${inkColor} !important; font-family: 'Inter', system-ui, sans-serif !important; font-size: 14px; line-height: 1.55; margin: 0; padding: 16px; }
    body *, font, span, div, p, td, th, li, h1, h2, h3, h4, h5, h6, pre { color: ${inkColor} !important; -webkit-text-stroke-color: ${inkColor} !important; background-color: transparent !important; }
    a, a * { color: ${accentColor} !important; text-decoration: underline !important; cursor: pointer !important; }
    pre { white-space: pre-wrap; word-break: break-word; font-family: inherit !important; margin: 0; }
    code, kbd { font-family: 'JetBrains Mono', monospace; }
    blockquote { border-left: 2px solid ${lineColor} !important; margin: 8px 0; padding-left: 12px; color: ${mutedColor} !important; }
  </style>`;

  if (rawHtml) {
    return `<meta http-equiv="Content-Security-Policy" content="${escapeHtml(csp)}">${themeMeta}${rawHtml}${themeOverrideCss}`;
  }
  if (!plainFallback) return "";
  const fallbackDoc = `<!DOCTYPE html><html><head><meta charset="utf-8">${themeMeta}${themeOverrideCss}</head><body><pre>${linkifyPlainTextToHtml(plainFallback)}</pre></body></html>`;
  return `<meta http-equiv="Content-Security-Policy" content="${escapeHtml(csp)}">${fallbackDoc}`;
}

function getInitials(nameOrEmail: string): string {
  const cleaned = nameOrEmail.trim();
  if (!cleaned) return "M";
  const parts = cleaned.split(/[\s.@_-]+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }
  return cleaned.slice(0, 2).toUpperCase();
}

function renderStatusBannerHtml(msg: string): string {
  const low = msg.toLowerCase();
  const localizedErrPrefixes = [
    t("common.error_prefix"),
    t("mail.err_linking_gmail", { error: "" }).trim(),
    t("mail.err_test_failed", { error: "" }).trim(),
    t("mail.err_adding_acct", { error: "" }).trim(),
    t("mail.err_sync", { error: "" }).trim(),
    t("mail.err_sync_failed", { error: "" }).trim(),
    t("mail.err_remove_failed", { error: "" }).trim(),
    t("mail.err_draft", { error: "" }).trim(),
    t("mail.err_send_prepare", { error: "" }).trim(),
    t("mail.err_send_rejected", { error: "" }).trim(),
    t("mail.err_undo_failed", { error: "" }).trim(),
  ].filter((p) => p.length > 0);
  const variant =
    low.includes("error") ||
    low.includes("failed") ||
    low.includes("rejected") ||
    localizedErrPrefixes.some((p) => low.startsWith(p.toLowerCase()))
      ? "banner danger"
      : "banner";
  return `<div class="${variant}">${escapeHtml(msg)}</div>`;
}

export async function refreshMailState(): Promise<void> {
  const acctRes = await sidecarGetMailAccounts();
  state.mailAccounts = acctRes.accounts ?? [];
  if (
    state.mailActiveAccountId &&
    !state.mailAccounts.some((a) => a.id === state.mailActiveAccountId)
  ) {
    state.mailActiveAccountId = null;
  }
  state.mailPresets =
    acctRes.presets && acctRes.presets.length > 0
      ? acctRes.presets
      : DEFAULT_PRESETS;
  // Reset cached site-tab promo codes so active merchant tabs re-query updated codes
  state.siteTabPromoCodes = {};

  if (acctRes.unlocked && state.mailAccounts.length > 0) {
    await apiEnsureMailConversation();
    const laneRes = await sidecarGetMailLane(
      state.mailActiveLane,
      0,
      state.mailActiveAccountId
    );
    state.mailCounts = laneRes.counts ?? {
      inbox_unread: 0,
      pings: 0,
      orders: 0,
      promos: 0,
    };
    state.mailLaneRows = laneRes.rows ?? [];
    state.mailLaneGroups = laneRes.groups ?? [];
    if (laneRes.classifier) {
      state.mailClassifierInfo = laneRes.classifier;
    }
    state.mailOnboardingCandidates = laneRes.onboarding_candidates ?? [];
    if (state.mailActiveLane === "inbox") {
      state.mailInboxRows = laneRes.rows ?? [];
    }
    const triageRes = await sidecarGetMailTriage(state.mailActiveAccountId);
    if (triageRes.ok) {
      state.mailTriageOverview = triageRes.overview ?? "";
      state.mailTriageSources = triageRes.sources ?? [];
    }
  } else {
    state.mailLaneRows = [];
    state.mailLaneGroups = [];
    state.mailCounts = { inbox_unread: 0, pings: 0, orders: 0, promos: 0 };
    state.mailOnboardingCandidates = [];
    state.mailTriageOverview = "";
    state.mailTriageSources = [];
  }
}

export function renderMailAccountsSectionHtml(): string {
  const unlocked = Boolean(state.knowledge.profile?.unlocked);
  const presets =
    state.mailPresets.length > 0 ? state.mailPresets : DEFAULT_PRESETS;
  const accounts = state.mailAccounts ?? [];

  if (!unlocked) {
    return `
      <div class="section">
        <div class="label"><span>${escapeHtml(t("mail.accounts_title"))}</span><span class="end">${escapeHtml(t("mail.vault_locked"))}</span></div>
        <div class="muted">${escapeHtml(t("mail.vault_locked_desc"))}</div>
      </div>
    `;
  }

  return `
    <div class="section" id="mail-accounts-panel">
      <div class="label">
        <span>${escapeHtml(t("mail.accounts_title"))}</span>
        <span class="ct">${accounts.length}</span>
        <span class="end">
          <button
            id="mail-toggle-eval-btn"
            type="button"
            class="btn-text ${state.mailEvalOpen ? "pri" : ""}"
          >${escapeHtml(t("mail.eval_mode_200"))}</button>
          <button id="mail-sync-all-btn" type="button" class="btn-text">${escapeHtml(t("mail.sync_now"))}</button>
        </span>
      </div>
      ${state.mailEvalOpen ? renderMailEvalPanelHtml() : ""}
      ${
        state.mailStatusMessage
          ? renderStatusBannerHtml(state.mailStatusMessage)
          : ""
      }
      ${
        accounts.length === 0
          ? `<div class="muted">${escapeHtml(t("mail.no_accounts"))}</div>`
          : `
          <div class="table-wrap">
            <table class="table">
              <thead>
                <tr>
                  <th>${escapeHtml(t("mail.col_account"))}</th>
                  <th>${escapeHtml(t("mail.col_incoming"))}</th>
                  <th>${escapeHtml(t("mail.col_outgoing"))}</th>
                  <th>${escapeHtml(t("mail.col_vault"))}</th>
                  <th class="num">${escapeHtml(t("mail.col_messages"))}</th>
                  <th>${escapeHtml(t("mail.col_status"))}</th>
                  <th>${escapeHtml(t("mail.col_actions"))}</th>
                </tr>
              </thead>
              <tbody>
                ${accounts
                  .map((a) => {
                    const statusDot = a.auth_failed
                      ? `<span class="dot danger"></span>`
                      : a.last_error
                        ? `<span class="dot warn"></span>`
                        : `<span class="dot"></span>`;
                    const statusText = a.auth_failed
                      ? escapeHtml(t("mail.auth_failed"))
                      : a.last_error
                        ? escapeHtml(a.last_error.slice(0, 48))
                        : a.last_sync_at > 0
                          ? escapeHtml(t("mail.synced_age", { age: formatRelativeTime(String(Math.floor(a.last_sync_at))) }))
                          : escapeHtml(t("mail.ready"));
                    return `
                  <tr>
                    <td><b>${escapeHtml(a.label)}</b> · ${escapeHtml(a.email)} ${a.auth_type === "oauth2" ? `<span class="badge good">${escapeHtml(t("mail.google_oauth_badge"))}</span>` : ""}</td>
                    <td>${escapeHtml(a.protocol.toUpperCase())} ${escapeHtml(a.in_host)}:${a.in_port} (${escapeHtml(a.in_security)})</td>
                    <td>SMTP ${escapeHtml(a.smtp_host)}:${a.smtp_port} (${escapeHtml(a.smtp_security)})</td>
                    <td class="muted">${escapeHtml(a.vault_prefix)}</td>
                    <td class="num">${a.message_count ?? 0}</td>
                    <td><span class="status">${statusDot}<span>${statusText}</span></span></td>
                    <td>
                      <button type="button" class="btn-text" data-mail-test-acct="${escapeHtml(a.id)}">${escapeHtml(t("mail.test_btn"))}</button>
                      <button type="button" class="btn-text" data-mail-sync-acct="${escapeHtml(a.id)}">${escapeHtml(t("mail.sync_btn"))}</button>
                      <button type="button" class="btn-text" data-mail-remove-acct="${escapeHtml(a.id)}">${escapeHtml(t("mail.remove_btn"))}</button>
                    </td>
                  </tr>
                `;
                  })
                  .join("")}
              </tbody>
            </table>
          </div>
        `
      }

      <div class="card">
        <div class="card-h">
          <b>${escapeHtml(t("mail.add_account_title"))}</b>
          <span class="end muted">${escapeHtml(t("mail.vault_note"))}</span>
        </div>
        ${
          state.googleOAuthStatus?.signed_in
            ? `<div class="form-row">
                <span class="badge good">${escapeHtml(t("mail.google_signed_in", { email: state.googleOAuthStatus.email }))}</span>
                <button id="mail-google-connect-btn" type="button" class="btn primary">${escapeHtml(t("mail.connect_gmail", { email: state.googleOAuthStatus.email }))}</button>
              </div>`
            : `<div class="form-row">
                <input id="mail-google-client-id" class="input" type="text" spellcheck="false" autocomplete="off" placeholder="${escapeHtml(state.googleOAuthStatus?.configured ? t("mail.google_cid_saved_ph", { masked: state.googleOAuthStatus.masked_client_id }) : t("mail.google_cid_ph"))}" />
                <input id="mail-google-client-secret" class="input" type="password" spellcheck="false" autocomplete="off" placeholder="${escapeHtml(state.googleOAuthStatus?.configured ? t("mail.google_csec_saved_ph") : t("mail.google_csec_ph"))}" />
                <button id="mail-google-oauth-btn" type="button" class="btn primary">${escapeHtml(t("mail.google_signin_tab_btn"))}</button>
              </div>`
        }
        <div class="form-row">
          <select id="mail-preset-select" class="select">
            ${presets
              .map(
                (p) =>
                  `<option value="${escapeHtml(p.id)}">${escapeHtml(p.label)} (${p.protocol.toUpperCase()})</option>`
              )
              .join("")}
          </select>
          <input id="mail-acct-email" class="input" type="text" placeholder="${escapeHtml(t("mail.email_ph"))}" />
          <input id="mail-acct-label" class="input" type="text" placeholder="${escapeHtml(t("mail.label_ph"))}" value="" />
          <input id="mail-acct-password" class="input" type="password" placeholder="${escapeHtml(t("mail.password_ph"))}" />
        </div>
        <div class="form-row">
          <select id="mail-acct-protocol" class="select">
            <option value="imap">IMAP</option>
            <option value="pop3">${escapeHtml(t("mail.pop3_leave"))}</option>
          </select>
          <input id="mail-acct-in-host" class="input" type="text" placeholder="${escapeHtml(t("mail.in_host_ph"))}" value="imap.gmail.com" />
          <input id="mail-acct-in-port" class="input" type="number" placeholder="993" value="993" />
          <select id="mail-acct-in-sec" class="select">
            <option value="ssl">SSL</option>
            <option value="starttls">STARTTLS</option>
          </select>
        </div>
        <div class="form-row">
          <input id="mail-acct-smtp-host" class="input" type="text" placeholder="${escapeHtml(t("mail.smtp_host_ph"))}" value="smtp.gmail.com" />
          <input id="mail-acct-smtp-port" class="input" type="number" placeholder="587" value="587" />
          <select id="mail-acct-smtp-sec" class="select">
            <option value="starttls">STARTTLS</option>
            <option value="ssl">SSL</option>
          </select>
          <button id="mail-form-test-btn" type="button" class="btn">${escapeHtml(t("mail.test_btn"))}</button>
          <button id="mail-form-add-btn" type="button" class="btn primary">${escapeHtml(t("mail.add_account_btn"))}</button>
        </div>
      </div>
    </div>
  `;
}

export function bindMailAccountsEvents(
  container: HTMLElement,
  onChanged: () => Promise<void>,
  onStartGoogleOAuth?: (payload?: {
    client_id?: string;
    client_secret?: string;
    client_secret_json?: string;
    scopes?: string[] | string;
    connect_gmail?: boolean;
    redirect_port?: number;
  }) => Promise<void>
): void {
  const presets =
    state.mailPresets.length > 0 ? state.mailPresets : DEFAULT_PRESETS;

  const presetSelect = container.querySelector(
    "#mail-preset-select"
  ) as HTMLSelectElement | null;
  const labelInput = container.querySelector(
    "#mail-acct-label"
  ) as HTMLInputElement | null;
  const emailInput = container.querySelector(
    "#mail-acct-email"
  ) as HTMLInputElement | null;
  const passwordInput = container.querySelector(
    "#mail-acct-password"
  ) as HTMLInputElement | null;
  const protocolSelect = container.querySelector(
    "#mail-acct-protocol"
  ) as HTMLSelectElement | null;
  const inHostInput = container.querySelector(
    "#mail-acct-in-host"
  ) as HTMLInputElement | null;
  const inPortInput = container.querySelector(
    "#mail-acct-in-port"
  ) as HTMLInputElement | null;
  const inSecSelect = container.querySelector(
    "#mail-acct-in-sec"
  ) as HTMLSelectElement | null;
  const smtpHostInput = container.querySelector(
    "#mail-acct-smtp-host"
  ) as HTMLInputElement | null;
  const smtpPortInput = container.querySelector(
    "#mail-acct-smtp-port"
  ) as HTMLInputElement | null;
  const smtpSecSelect = container.querySelector(
    "#mail-acct-smtp-sec"
  ) as HTMLSelectElement | null;

  presetSelect?.addEventListener("change", () => {
    const p = presets.find((x) => x.id === presetSelect.value);
    if (!p) return;
    if (protocolSelect) protocolSelect.value = p.protocol;
    if (inHostInput) inHostInput.value = p.in_host;
    if (inPortInput) inPortInput.value = String(p.in_port);
    if (inSecSelect) inSecSelect.value = p.in_security;
    if (smtpHostInput) smtpHostInput.value = p.smtp_host;
    if (smtpPortInput) smtpPortInput.value = String(p.smtp_port);
    if (smtpSecSelect) smtpSecSelect.value = p.smtp_security;
  });

  const collectFormPayload = (): Record<string, unknown> => {
    const emailVal = emailInput?.value.trim() ?? "";
    const customLabel = labelInput?.value.trim() ?? "";
    return {
      preset: presetSelect?.value ?? "gmail",
      label: customLabel || emailVal || "Mail",
      email: emailVal,
      password: passwordInput?.value ?? "",
      protocol: protocolSelect?.value ?? "imap",
      in_host: inHostInput?.value.trim() ?? "",
      in_port: Number(inPortInput?.value ?? 993),
      in_security: inSecSelect?.value ?? "ssl",
      smtp_host: smtpHostInput?.value.trim() ?? "",
      smtp_port: Number(smtpPortInput?.value ?? 587),
      smtp_security: smtpSecSelect?.value ?? "starttls",
    };
  };

  container
    .querySelector("#mail-google-oauth-btn")
    ?.addEventListener("click", () => {
      if (!onStartGoogleOAuth) return;
      const cid = (container.querySelector("#mail-google-client-id") as HTMLInputElement | null)?.value.trim() ?? "";
      const csec = (container.querySelector("#mail-google-client-secret") as HTMLInputElement | null)?.value.trim() ?? "";
      void onStartGoogleOAuth({
        client_id: cid || undefined,
        client_secret: csec || undefined,
        scopes: ["openid", "email", "profile", "https://mail.google.com/"],
        connect_gmail: true,
      });
    });

  container
    .querySelector("#mail-google-connect-btn")
    ?.addEventListener("click", async () => {
      state.mailStatusMessage = t("mail.status_linking_gmail");
      await onChanged();
      const res = await sidecarConnectGmailOAuth();
      if (res.ok) {
        await apiEnsureMailConversation();
        state.mailStatusMessage = t("mail.status_gmail_connected");
        await refreshMailState();
      } else {
        state.mailStatusMessage = t("mail.err_linking_gmail", {
          error: res.error ?? t("mail.err_failed"),
        });
      }
      await onChanged();
    });

  container
    .querySelector("#mail-form-test-btn")
    ?.addEventListener("click", async () => {
      state.mailStatusMessage = t("mail.status_testing_form");
      await onChanged();
      const res = await sidecarTestMailAccount(collectFormPayload());
      if (res.ok) {
        state.mailStatusMessage = t("mail.status_test_passed");
      } else {
        state.mailStatusMessage = t("mail.err_test_failed", {
          error: res.error ?? t("mail.err_unknown"),
        });
      }
      await onChanged();
    });

  container
    .querySelector("#mail-form-add-btn")
    ?.addEventListener("click", async () => {
      const payload = collectFormPayload();
      state.mailStatusMessage = t("mail.status_adding_acct");
      await onChanged();
      const res = await sidecarAddMailAccount(payload);
      if (res.ok) {
        await apiEnsureMailConversation();
        state.mailStatusMessage = t("mail.status_added_acct", {
          vault: res.vault_prefix ?? "vault",
        });
        await refreshMailState();
      } else {
        state.mailStatusMessage = t("mail.err_adding_acct", {
          error: res.error ?? t("mail.err_failed"),
        });
      }
      await onChanged();
    });

  container
    .querySelector("#mail-sync-all-btn")
    ?.addEventListener("click", async () => {
      state.mailStatusMessage = t("mail.status_syncing_all");
      await onChanged();
      const res = await sidecarSyncMail();
      await refreshMailState();
      state.mailStatusMessage = res.ok
        ? t("mail.status_sync_complete")
        : t("mail.err_sync", { error: res.error ?? t("mail.err_failed") });
      await onChanged();
    });

  container.querySelectorAll("[data-mail-test-acct]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = (btn as HTMLElement).getAttribute("data-mail-test-acct");
      if (!id) return;
      state.mailStatusMessage = t("mail.status_testing_acct", { id });
      await onChanged();
      const res = await sidecarTestMailAccount({ account_id: id });
      state.mailStatusMessage = res.ok
        ? t("mail.status_acct_verified", { id })
        : t("mail.err_acct_test", { id, error: res.error ?? t("mail.err_failed") });
      await onChanged();
    });
  });

  container.querySelectorAll("[data-mail-sync-acct]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = (btn as HTMLElement).getAttribute("data-mail-sync-acct");
      if (!id) return;
      state.mailStatusMessage = t("mail.status_syncing_acct", { id });
      await onChanged();
      const res = await sidecarSyncMail(id);
      await refreshMailState();
      state.mailStatusMessage = res.ok
        ? tCount("mail.status_synced_n", res.synced_count ?? 0)
        : t("mail.err_sync_failed", { error: res.error ?? t("mail.err_failed") });
      await onChanged();
    });
  });

  container.querySelectorAll("[data-mail-remove-acct]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = (btn as HTMLElement).getAttribute("data-mail-remove-acct");
      if (!id) return;
      const res = await sidecarRemoveMailAccount(id);
      await refreshMailState();
      state.mailStatusMessage = res.ok
        ? t("mail.status_removed_acct", { id })
        : t("mail.err_remove_failed", { error: res.error ?? t("mail.err_failed") });
      await onChanged();
    });
  });

  container
    .querySelector("#mail-toggle-eval-btn")
    ?.addEventListener("click", async () => {
      state.mailEvalOpen = !state.mailEvalOpen;
      if (state.mailEvalOpen) {
        const sample = await sidecarGetMailEval(200);
        state.mailEvalItems = sample.items ?? [];
        state.mailEvalIdx = 0;
        state.mailEvalReport = await sidecarGetMailEvalReport();
      }
      await onChanged();
    });

  container.querySelectorAll("[data-eval-nav]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const dir = (btn as HTMLElement).getAttribute("data-eval-nav");
      if (dir === "prev") {
        state.mailEvalIdx = Math.max(0, state.mailEvalIdx - 1);
      } else {
        state.mailEvalIdx = Math.min(
          Math.max(0, state.mailEvalItems.length - 1),
          state.mailEvalIdx + 1
        );
      }
      await onChanged();
    });
  });

  container.querySelectorAll("[data-eval-label]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const item = state.mailEvalItems[state.mailEvalIdx];
      if (!item) return;
      const lbl = (btn as HTMLElement).getAttribute("data-eval-label") as
        | "email"
        | "ping"
        | "information"
        | "promotion"
        | null;
      if (!lbl) return;
      const mid = String(item.id ?? "");
      const curExtOk =
        typeof item.human_extract_ok === "number"
          ? item.human_extract_ok === 1
          : undefined;
      await sidecarLabelMailEval(mid, lbl, curExtOk);
      item.human_label = lbl;
      state.mailEvalReport = await sidecarGetMailEvalReport();
      if (
        lbl !== "information" &&
        lbl !== "promotion" &&
        state.mailEvalIdx < state.mailEvalItems.length - 1
      ) {
        state.mailEvalIdx += 1;
      }
      await onChanged();
    });
  });

  container.querySelectorAll("[data-eval-extract]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const item = state.mailEvalItems[state.mailEvalIdx];
      if (!item) return;
      const okStr = (btn as HTMLElement).getAttribute("data-eval-extract");
      const extOk = okStr === "y";
      const mid = String(item.id ?? "");
      const lbl = (String(item.human_label || item.pred_label || "email") as
        | "email"
        | "ping"
        | "information"
        | "promotion");
      await sidecarLabelMailEval(mid, lbl, extOk);
      item.human_label = lbl;
      item.human_extract_ok = extOk ? 1 : 0;
      state.mailEvalReport = await sidecarGetMailEvalReport();
      if (state.mailEvalIdx < state.mailEvalItems.length - 1) {
        state.mailEvalIdx += 1;
      }
      await onChanged();
    });
  });
}

function evalLabelText(lbl: string): string {
  switch (lbl) {
    case "email":
      return t("mail.eval_col_email");
    case "ping":
      return t("mail.eval_col_ping");
    case "information":
      return t("mail.eval_col_info");
    case "promotion":
      return t("mail.eval_col_promo");
    default:
      return lbl;
  }
}

function renderMailEvalPanelHtml(): string {
  const items = state.mailEvalItems;
  const idx = Math.min(state.mailEvalIdx, Math.max(0, items.length - 1));
  const item = items[idx];
  const rep = (state.mailEvalReport ?? {}) as Record<string, unknown>;
  const matrix = (rep.confusion_matrix ?? {}) as Record<
    string,
    Record<string, number>
  >;
  const labels = ["email", "ping", "information", "promotion"];

  if (!item) {
    return `
      <div class="card">
        <div class="card-h">
          <b>${escapeHtml(t("mail.eval_title"))}</b>
          <span class="end muted">${escapeHtml(t("mail.eval_sub"))}</span>
        </div>
        <div class="muted">${escapeHtml(t("mail.eval_empty"))}</div>
      </div>
    `;
  }

  const extracts = (item.extracts ?? {}) as Record<string, string>;
  const extEntries = Object.entries(extracts);
  const humanLabel = String(item.human_label || "");
  const predLabel = String(item.pred_label || "email");
  const showExtractCheck =
    humanLabel === "information" ||
    humanLabel === "promotion" ||
    predLabel === "information" ||
    predLabel === "promotion";
  const extSummary =
    extEntries.length > 0
      ? extEntries.map(([k, v]) => `${k}=${v}`).join(" · ")
      : t("mail.eval_extracts_none");

  return `
    <div class="card" id="mail-eval-card">
      <div class="card-h">
        <b>${escapeHtml(t("mail.eval_title"))}</b>
        <span class="badge soft">${idx + 1} / ${items.length}</span>
        <span class="muted">${escapeHtml(t("mail.eval_labelled", { count: Number(rep.total_evaluated ?? 0) }))}</span>
        <span class="end">
          <button type="button" class="btn" data-eval-nav="prev">${escapeHtml(t("mail.eval_prev"))}</button>
          <button type="button" class="btn" data-eval-nav="next">${escapeHtml(t("mail.eval_next"))}</button>
        </span>
      </div>
      <div class="mail-read-actions">
        <span><b>${escapeHtml(String(item.from_name || item.from_addr || ""))}</b> · ${escapeHtml(String(item.subject || ""))}</span>
        <span class="end muted">${escapeHtml(t("mail.eval_pred", { pred: evalLabelText(predLabel), conf: Number(item.pred_confidence ?? 0).toFixed(2) }))}${humanLabel ? escapeHtml(t("mail.eval_label_suffix", { label: evalLabelText(humanLabel) })) : ""}</span>
      </div>
      <div class="eval-excerpt">${escapeHtml(String(item.new_text || item.snippet || "").slice(0, 360))}</div>
      <div class="mail-read-actions">
        <span class="muted">${escapeHtml(t("mail.eval_label_keys"))}</span>
        <div class="seg" role="group" aria-label="${escapeHtml(t("mail.eval_label_group_aria"))}">
          <button type="button" data-eval-label="email" aria-pressed="${humanLabel === "email" ? "true" : "false"}">${escapeHtml(t("mail.eval_key_email"))}</button>
          <button type="button" data-eval-label="ping" aria-pressed="${humanLabel === "ping" ? "true" : "false"}">${escapeHtml(t("mail.eval_key_ping"))}</button>
          <button type="button" data-eval-label="information" aria-pressed="${humanLabel === "information" ? "true" : "false"}">${escapeHtml(t("mail.eval_key_info"))}</button>
          <button type="button" data-eval-label="promotion" aria-pressed="${humanLabel === "promotion" ? "true" : "false"}">${escapeHtml(t("mail.eval_key_promo"))}</button>
        </div>
      </div>
      ${
        showExtractCheck
          ? `<div class="mail-read-actions">
              <span class="muted">${escapeHtml(t("mail.eval_extracts", { summary: extSummary }))}</span>
              <span class="end">
                <span class="muted">${escapeHtml(t("mail.eval_correct_q"))}</span>
                <div class="seg" role="group" aria-label="${escapeHtml(t("mail.eval_extract_group_aria"))}">
                  <button type="button" data-eval-extract="y" aria-pressed="${item.human_extract_ok === 1 ? "true" : "false"}">${escapeHtml(t("mail.eval_yes_y"))}</button>
                  <button type="button" data-eval-extract="n" aria-pressed="${item.human_extract_ok === 0 ? "true" : "false"}">${escapeHtml(t("mail.eval_no_n"))}</button>
                </div>
              </span>
            </div>`
          : ""
      }
      <div class="mail-read-actions">
        <span class="muted">
          ${escapeHtml(
            t("mail.eval_gates_line", {
              misfiled: Number(rep.real_email_misfiled_as_promotion_pct ?? 0).toFixed(2),
              recall: Number(rep.promotion_recall_pct ?? 100).toFixed(2),
              extract: Number(rep.extraction_accuracy_pct ?? 100).toFixed(2),
            })
          )}
        </span>
        <span class="badge ${rep.gates_passed ? "" : "soft"}">${escapeHtml(rep.gates_passed ? t("mail.eval_gates_pass") : t("common.pending"))}</span>
      </div>
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>${escapeHtml(t("mail.eval_col_true_pred"))}</th>
              <th class="num">${escapeHtml(t("mail.eval_col_email"))}</th>
              <th class="num">${escapeHtml(t("mail.eval_col_ping"))}</th>
              <th class="num">${escapeHtml(t("mail.eval_col_info"))}</th>
              <th class="num">${escapeHtml(t("mail.eval_col_promo"))}</th>
            </tr>
          </thead>
          <tbody>
            ${labels
              .map(
                (lbl) => `
              <tr>
                <td>${escapeHtml(evalLabelText(lbl))}</td>
                ${labels
                  .map((p) => `<td class="num">${Number(matrix[lbl]?.[p] ?? 0)}</td>`)
                  .join("")}
              </tr>
            `
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderAcctBarHtml(
  showOnboardingBtn: boolean
): string {
  const accounts = state.mailAccounts ?? [];
  const totalUnreadAll =
    accounts.length > 0
      ? accounts.reduce((acc, a) => acc + (a.inbox_unread ?? 0), 0) ||
        state.mailCounts.inbox_unread
      : state.mailCounts.inbox_unread;

  const latestSync = accounts.reduce(
    (maxTs, a) => Math.max(maxTs, Number(a.last_sync_at || 0)),
    0
  );
  const syncLabel =
    latestSync > 0
      ? t("mail.synced_lower", { age: formatRelativeTime(String(Math.floor(latestSync))) })
      : t("mail.ready_lower");

  return `
    <div class="acct-bar">
      <button
        type="button"
        class="pill round ${state.mailActiveAccountId === null ? "on" : ""}"
        data-mail-acct-tab="all"
        aria-pressed="${state.mailActiveAccountId === null ? "true" : "false"}"
        title="${escapeHtml(t("mail.all_mail_title"))}"
      >
        <span>${escapeHtml(t("rail.all_mail"))}</span>
        ${totalUnreadAll > 0 ? `<span class="count">${totalUnreadAll}</span>` : ""}
      </button>
      ${accounts
        .map((acct) => {
          const isAcctSelected = state.mailActiveAccountId === acct.id;
          const acctName = acct.label || acct.email;
          const acctUnread = acct.inbox_unread ?? 0;
          return `
            <button
              type="button"
              class="pill round ${isAcctSelected ? "on" : ""}"
              data-mail-acct-tab="${escapeHtml(acct.id)}"
              aria-pressed="${isAcctSelected ? "true" : "false"}"
              title="${escapeHtml(t("mail.filter_acct_title", { target: acct.email || acctName }))}"
            >
              <span>${escapeHtml(acctName)}</span>
              ${acctUnread > 0 ? `<span class="count">${acctUnread}</span>` : ""}
            </button>
          `;
        })
        .join("")}
      <button
        id="mail-add-account-btn"
        class="pill round"
        type="button"
        title="${escapeHtml(t("mail.add_acct_bar_title"))}"
      >
        ${icon("plus", "ico-sm")}
        <span>${escapeHtml(t("mail.add_account_btn"))}</span>
      </button>
      <div class="end">
        <span>${escapeHtml(syncLabel)}</span>
        ${
          showOnboardingBtn
            ? `<button id="mail-onboarding-toggle-btn" type="button" class="btn ${state.mailOnboardingOpen ? "primary" : ""}">${escapeHtml(t("mail.sort_10"))}</button>`
            : ""
        }
        <button id="mail-compose-btn" type="button" class="btn" title="${escapeHtml(t("mail.compose_title"))}">
          ${icon("compose", "ico-sm")}
          <span>${escapeHtml(t("mail.compose_btn"))}</span>
        </button>
        <button id="mail-lane-refresh-btn" type="button" class="btn" title="${escapeHtml(t("mail.sync_all_title"))}">
          ${icon("reload", "ico-sm")}
          <span>${escapeHtml(t("mail.sync_now"))}</span>
        </button>
      </div>
    </div>
  `;
}

function renderSplitReadingPaneHtml(
  selectedRow: Record<string, unknown> | undefined
): string {
  if (!selectedRow) {
    return `
      <div class="mail-read">
        <div class="mail-empty">${escapeHtml(t("mail.select_message"))}</div>
      </div>
    `;
  }

  const mid = String(
    selectedRow.id ?? selectedRow.latest_message_id ?? ""
  );
  const detailObj = mid ? state.mailMessageDetails[mid] : undefined;
  const cachedHtml = mid ? state.mailMessageHtml[mid] : undefined;
  const msg = (detailObj?.message ?? detailObj ?? selectedRow) as Record<
    string,
    unknown
  >;

  const fromName = String(msg.from_name || selectedRow.from_name || "");
  const fromAddr = String(msg.from_addr || selectedRow.from_addr || "");
  const fromPrimary = fromName || fromAddr || t("mail.sender_fallback");
  const subj = String(
    msg.subject || selectedRow.subject || t("brain.no_subject")
  );
  const dueDate = String(
    msg.due_date || selectedRow.due_date || ""
  );
  const extracts = ((msg.extracts ?? {}) as Record<string, unknown>);
  const trackingNo = String(
    extracts.tracking_number ?? selectedRow.tracking_number ?? ""
  );
  const trackingUrl = String(
    extracts.tracking_url ?? selectedRow.tracking_url ?? ""
  );

  const partsObj = ((msg.parts ?? {}) as Record<string, string>);
  const plainText = String(
    partsObj.new ||
      msg.body_text ||
      selectedRow.snippet ||
      ""
  );
  const trObj = (msg.translation as Record<string, unknown> | undefined) ?? undefined;
  const showOrig = Boolean(mid && state.mailMessageShowOriginal[mid]);
  const trPlain = String(trObj?.new_text || trObj?.snippet || "").trim();
  const displayPlain = !showOrig && trPlain ? trPlain : plainText;
  const rawHtml =
    !showOrig && cachedHtml?.translated_html
      ? cachedHtml.translated_html
      : cachedHtml?.html;
  const defaultCsp =
    "default-src 'none'; img-src data: cid:; style-src 'unsafe-inline'; font-src data:";
  const effectiveCsp = cachedHtml?.csp || defaultCsp;
  const iframeSrcdoc = rawHtml
    ? buildMailIframeSrcdoc(rawHtml, displayPlain, effectiveCsp)
    : "";

  const fakeTab: BrowserTab = {
    id: `preview-${mid}`,
    conversation_id: state.activeDetail?.conversation.id ?? "conv-mail",
    url: `satzmail://message/${mid}`,
    title: subj,
    kind: "mail",
    position: 0,
    is_open: true,
    created_at: "",
  };

  return `
    <div class="mail-read">
      ${renderEmailTabHeaderHtml(fakeTab, detailObj ?? selectedRow, true)}
      ${
        dueDate
          ? `<div class="extract">
              ${icon("cal", "ico-sm")}
              <div><b>${escapeHtml(t("mail.action_date"))}</b> · ${escapeHtml(dueDate)}</div>
              <button
                type="button"
                class="btn primary"
                data-email-rail-ask="extract dates and action items from this email: ${escapeHtml(subj)}"
              >${escapeHtml(t("mail.add_to_calendar"))}</button>
            </div>`
          : ""
      }
      ${
        trackingNo || trackingUrl
          ? `<div class="extract">
              ${icon("box", "ico-sm")}
              <div><b>${escapeHtml(t("mail.tracking"))}</b> · ${escapeHtml(trackingNo || t("mail.shipment_link"))}</div>
              ${
                trackingUrl
                  ? `<button type="button" class="btn primary" data-open-site-url="${escapeHtml(trackingUrl)}" data-open-site-title="${escapeHtml(t("mail.track_package"))}">${escapeHtml(t("mail.track_btn"))}</button>`
                  : ""
              }
            </div>`
          : ""
      }
      ${
        iframeSrcdoc
          ? `<iframe
              class="email-frame"
              sandbox="allow-same-origin"
              referrerpolicy="no-referrer"
              srcdoc="${escapeHtml(iframeSrcdoc)}"
            ></iframe>`
          : `<div class="mail-body">
              ${
                displayPlain
                  ? displayPlain
                      .split(/\n{2,}/)
                      .filter((p) => p.trim())
                      .map((p) => `<p>${linkifyPlainTextToHtml(p.trim())}</p>`)
                      .join("")
                  : `<p class="muted">${escapeHtml(t("mail.loading_from", { sender: fromPrimary }))}</p>`
              }
            </div>`
      }
    </div>
  `;
}

export function renderMailLaneView(
  container: HTMLElement,
  actions: MailViewActions
): void {
  const lane = state.mailActiveLane;
  const rows = state.mailSearchRows ?? state.mailLaneRows;
  const groups = state.mailLaneGroups ?? [];
  const unlocked = Boolean(state.knowledge.profile?.unlocked);

  const prof = state.knowledge.profile;
  const hasProfiles = (prof?.profiles.length ?? 0) > 0;
  if (!unlocked || !hasProfiles) {
    container.innerHTML = `
      <div class="mail-view">
        ${renderInlineProfileGateHtml({
          iconName: "mail",
          subtitle: t("mail.locked_sub"),
        })}
      </div>
    `;
    bindInlineProfileGateEvents(container, {
      onUnlockProfile: actions.onUnlockProfile,
      onUnlockProfileKeychain: actions.onUnlockProfileKeychain,
      onCreateProfile: actions.onCreateProfile,
    });
    return;
  }

  const isSplitView = state.mailSearchRows !== null || lane === "inbox";
  if (rows.length > 0 && state.mailSelectedRowIdx >= rows.length) {
    state.mailSelectedRowIdx = rows.length - 1;
  } else if (state.mailSelectedRowIdx < 0) {
    state.mailSelectedRowIdx = 0;
  }

  let bodyHtml = "";
  const selectedRow = rows[state.mailSelectedRowIdx] ?? rows[0];
  const selectedMsgId = selectedRow
    ? String(selectedRow.id ?? selectedRow.latest_message_id ?? "")
    : "";

  if (isSplitView) {
    const listContent =
      rows.length === 0
        ? `<div class="mail-empty">${escapeHtml(
            state.mailSearchRows !== null
              ? t("mail.search_empty", { query: state.mailSearchQuery })
              : t("mail.inbox_empty")
          )}</div>`
        : renderInboxRowsHtml(rows);
    bodyHtml = `
      <div class="mail-split">
        <div class="mail-list">${listContent}</div>
        ${renderSplitReadingPaneHtml(selectedRow)}
      </div>
    `;
  } else if (lane === "pings") {
    bodyHtml =
      groups.length === 0
        ? `<div class="mail-empty">${escapeHtml(t("mail.pings_empty"))}</div>`
        : `<div class="mail-cards-stack">
            ${groups
              .map((g) => {
                const plat = String(g.platform ?? t("mail.other_platform"));
                const cnt = Number(g.count ?? 0);
                const authorsObj = (g.authors ?? {}) as Record<string, number>;
                const authorSummary = Object.entries(authorsObj)
                  .slice(0, 4)
                  .map(([a, n]) => `${escapeHtml(a)} (${n})`)
                  .join(", ");
                const items = (g.items ?? []) as Array<Record<string, unknown>>;
                return `
                  <div class="card">
                    <div class="card-h">
                      <b>${escapeHtml(plat)}</b>
                      <span class="badge soft">${escapeHtml(tCount("mail.pings_count", cnt))}</span>
                      <span class="end muted">${authorSummary}</span>
                    </div>
                    <div class="mail-card-rows">
                      ${renderInboxRowsHtml(items)}
                    </div>
                  </div>
                `;
              })
              .join("")}
          </div>`;
  } else if (lane === "orders") {
    bodyHtml =
      rows.length === 0
        ? `<div class="mail-empty">${escapeHtml(t("mail.orders_empty"))}</div>`
        : `<div class="mail-cards-stack">
            ${rows
              .map((card, idx) => {
                const merchant = String(card.merchant ?? t("mail.merchant_fallback"));
                const orderNo = String(card.order_number ?? "");
                const status = String(card.status ?? t("mail.ordered_fallback"));
                const trackingNo = String(card.tracking_number ?? "");
                const trackingUrl = String(card.tracking_url ?? "");
                const total = String(card.total ?? "");
                const latestId = String(card.latest_message_id ?? "");
                const emails = (card.emails ?? []) as Array<
                  Record<string, unknown>
                >;
                const isSelected = idx === state.mailSelectedRowIdx;
                return `
                  <div
                    class="card ${isSelected ? "selected" : ""}"
                    data-mail-msg-id="${escapeHtml(latestId)}"
                    data-mail-msg-subject="${escapeHtml(`${merchant} ${orderNo}`)}"
                  >
                    <div class="card-h">
                      <b>${escapeHtml(merchant)}${orderNo ? ` · #${escapeHtml(orderNo)}` : ""}</b>
                      <span class="status"><span class="dot"></span><span>${escapeHtml(status)}</span></span>
                      ${total ? `<span class="end">${escapeHtml(total)}</span>` : ""}
                    </div>
                    ${
                      trackingNo || trackingUrl
                        ? `<div class="extract">
                            ${icon("box", "ico-sm")}
                            <div><b>${escapeHtml(t("mail.tracking"))}</b> · ${escapeHtml(trackingNo || t("mail.shipment_link"))}</div>
                            ${
                              trackingUrl
                                ? `<button type="button" class="btn primary" data-open-site-url="${escapeHtml(trackingUrl)}">${escapeHtml(t("mail.track_btn"))}</button>`
                                : ""
                            }
                          </div>`
                        : ""
                    }
                    <div class="mail-card-rows">
                      ${emails
                        .map((em) => {
                          const eid = String(em.id ?? "");
                          const esubj = String(em.subject ?? "");
                          const ets = Number(em.date ?? 0);
                          return `
                            <div
                              class="mail-row"
                              data-mail-msg-id="${escapeHtml(eid)}"
                              data-mail-msg-subject="${escapeHtml(esubj)}"
                            >
                              <div class="h">
                                <b>${escapeHtml(String(em.status || status))}</b>
                                <span class="time">${ets > 0 ? escapeHtml(formatRelativeTime(String(Math.floor(ets)))) : ""}</span>
                              </div>
                              <div class="s">${escapeHtml(esubj)}</div>
                            </div>
                          `;
                        })
                        .join("")}
                    </div>
                  </div>
                `;
              })
              .join("")}
          </div>`;
  } else if (lane === "promos") {
    bodyHtml =
      rows.length === 0
        ? `<div class="mail-empty">${escapeHtml(t("mail.promos_empty"))}</div>`
        : `<div class="mail-cards-stack">
            ${rows
              .map((comp) => {
                const company = String(comp.company ?? t("mail.company_fallback"));
                const domain = String(comp.domain ?? "");
                const activeCodes = (comp.active_codes ?? []) as Array<
                  Record<string, unknown>
                >;
                const expiredCodes = (comp.expired_codes ?? []) as Array<
                  Record<string, unknown>
                >;
                const emails = (comp.emails ?? []) as Array<
                  Record<string, unknown>
                >;
                return `
                  <div class="card">
                    <div class="card-h">
                      <b>${escapeHtml(company)}</b>
                      <span class="muted">${escapeHtml(domain)}</span>
                      <span class="end muted">${escapeHtml(tCount("mail.active_codes_count", activeCodes.length))}</span>
                    </div>
                    ${
                      activeCodes.length > 0
                        ? `<div class="mail-chip-row">
                            ${activeCodes
                              .map((c) => {
                                const codeStr = String(c.code ?? "");
                                const valStr = String(c.discount_value ?? "");
                                const expStr = String(c.expiry ?? "");
                                return `
                                  <button type="button" class="pill" data-copy-promo-code="${escapeHtml(codeStr)}" title="${escapeHtml(t("mail.copy_code_title"))}">
                                    <strong>${escapeHtml(codeStr)}</strong>
                                    ${valStr ? `<span>${escapeHtml(valStr)}</span>` : ""}
                                    ${expStr ? `<span class="muted">${escapeHtml(t("top.promo_exp", { expiry: expStr }))}</span>` : ""}
                                  </button>
                                `;
                              })
                              .join("")}
                          </div>`
                        : ""
                    }
                    ${
                      expiredCodes.length > 0
                        ? `<div class="muted">${escapeHtml(
                            t("mail.expired_list", {
                              codes: expiredCodes.map((c) => String(c.code ?? "")).join(", "),
                            })
                          )}</div>`
                        : ""
                    }
                    <div class="mail-card-rows">
                      ${emails
                        .map((em) => {
                          const eid = String(em.id ?? "");
                          const esubj = String(em.subject ?? "");
                          const ets = Number(em.date ?? 0);
                          return `
                            <div
                              class="mail-row"
                              data-mail-msg-id="${escapeHtml(eid)}"
                              data-mail-msg-subject="${escapeHtml(esubj)}"
                            >
                              <div class="h">
                                <b>${escapeHtml(company)}</b>
                                <span class="time">${ets > 0 ? escapeHtml(formatRelativeTime(String(Math.floor(ets)))) : ""}</span>
                              </div>
                              <div class="s">${escapeHtml(esubj)}</div>
                            </div>
                          `;
                        })
                        .join("")}
                    </div>
                  </div>
                `;
              })
              .join("")}
          </div>`;
  }

  const clf = state.mailClassifierInfo;
  const isCold = clf.model_version === "cold";
  const onboardingCands = state.mailOnboardingCandidates ?? [];
  const showOnboardingBtn = isCold && onboardingCands.length > 0;
  const onboardingHtml =
    state.mailOnboardingOpen && onboardingCands.length > 0
      ? `
      <div class="card" id="mail-onboarding-panel">
        <div class="card-h">
          <b>${escapeHtml(tCount("mail.help_sort_count", onboardingCands.length))}</b>
          <span class="muted">${escapeHtml(clf.status_text)}</span>
          <span class="end">
            <button id="mail-onboarding-close-btn" type="button" class="btn-text">${escapeHtml(t("common.close"))}</button>
          </span>
        </div>
        <div class="mail-cards-stack">
          ${onboardingCands
            .map((cand) => {
              const cid = String(cand.id ?? "");
              const cfrom = String(cand.from_name || cand.from_addr || t("mail.unknown_sender"));
              const csubj = String(cand.subject || t("brain.no_subject"));
              const csnip = String(cand.snippet || "").slice(0, 140);
              const cpred = String(cand.pred_label || "email");
              return `
                <div class="card inset" data-onboarding-card="${escapeHtml(cid)}">
                  <div class="card-h">
                    <b>${escapeHtml(cfrom)}</b>
                    <span class="muted truncate">${escapeHtml(csubj)}</span>
                    <span class="end badge soft">${escapeHtml(evalLabelText(cpred))}</span>
                  </div>
                  <div class="muted">${escapeHtml(csnip)}</div>
                  <div class="mail-read-actions">
                    <span class="muted">${escapeHtml(t("mail.is_promo_q"))}</span>
                    <span class="end">
                      <button type="button" class="btn" data-onboard-msg="${escapeHtml(cid)}" data-onboard-label="promotion">${escapeHtml(t("mail.onboard_promo"))}</button>
                      <button type="button" class="btn" data-onboard-msg="${escapeHtml(cid)}" data-onboard-label="email">${escapeHtml(t("mail.onboard_inbox"))}</button>
                      <button type="button" class="btn" data-onboard-msg="${escapeHtml(cid)}" data-onboard-label="ping">${escapeHtml(t("mail.onboard_ping"))}</button>
                      <button type="button" class="btn" data-onboard-msg="${escapeHtml(cid)}" data-onboard-label="information">${escapeHtml(t("mail.onboard_order"))}</button>
                    </span>
                  </div>
                </div>
              `;
            })
            .join("")}
        </div>
      </div>
    `
      : "";

  const activeAccountObj = state.mailAccounts.find(
    (a) => a.id === state.mailActiveAccountId
  );
  const activeScopeLabel = activeAccountObj
    ? activeAccountObj.label || activeAccountObj.email
    : t("rail.all_mail");
  const laneLabel =
    lane === "inbox"
      ? t("top.mail_inbox")
      : lane === "pings"
        ? t("top.mail_pings")
        : lane === "orders"
          ? t("top.mail_orders")
          : t("top.mail_promos");

  const showEmptyAccountsSetupOnly =
    state.mailAccounts.length === 0 &&
    rows.length === 0 &&
    groups.length === 0 &&
    state.mailSearchRows === null;

  container.innerHTML = `
    <div class="mail-view ${isSplitView && !showEmptyAccountsSetupOnly ? "mail-view-split" : ""}">
      ${renderAcctBarHtml(showOnboardingBtn)}
      ${
        showEmptyAccountsSetupOnly
          ? `
            <div class="banner">
              ${icon("mail", "ico-sm")}
              <span><b>${escapeHtml(t("mail.empty_setup_title"))}</b> - ${escapeHtml(t("mail.empty_setup_subtitle"))}</span>
            </div>
            ${onboardingHtml}
            ${renderMailAccountsSectionHtml()}
          `
          : `
            <div class="mail-toolbar">
              <div class="input-wrap mail-search-wrap">
                ${icon("search", "ico-sm")}
                <input
                  id="mail-search-input"
                  class="input"
                  type="text"
                  spellcheck="false"
                  autocorrect="off"
                  autocapitalize="off"
                  placeholder="${escapeHtml(t("mail.search_ph"))}"
                  value="${escapeHtml(state.mailSearchQuery)}"
                />
              </div>
              ${
                state.mailSearchRows !== null
                  ? `<button id="mail-search-clear-btn" type="button" class="btn">${escapeHtml(t("common.clear"))}</button>`
                  : ""
              }
              <span class="mail-toolbar-meta">${escapeHtml(t("mail.toolbar_meta", { scope: activeScopeLabel, lane: laneLabel, count: rows.length, classifier: clf.status_text }))}</span>
            </div>
            ${onboardingHtml}
            ${bodyHtml}
            ${state.mailAccounts.length === 0 ? renderMailAccountsSectionHtml() : ""}
          `
      }
    </div>
  `;

  if (
    isSplitView &&
    selectedMsgId &&
    !state.mailMessageDetails[selectedMsgId] &&
    !pendingPreviewIds.has(selectedMsgId)
  ) {
    pendingPreviewIds.add(selectedMsgId);
    void (async () => {
      try {
        const [detailRes, htmlRes] = await Promise.all([
          sidecarGetMailMessage(selectedMsgId),
          sidecarGetMailMessageHtml(selectedMsgId),
        ]);
        if (detailRes.ok) {
          state.mailMessageDetails[selectedMsgId] = detailRes;
        }
        if (htmlRes.ok && htmlRes.html) {
          state.mailMessageHtml[selectedMsgId] = {
            html: htmlRes.html,
            csp:
              htmlRes.csp ||
              "default-src 'none'; img-src data: cid:; style-src 'unsafe-inline'; font-src data:",
            translated_html: htmlRes.translated_html || undefined,
            translation_source_lang: htmlRes.translation_source_lang || undefined,
            translation_target_lang: htmlRes.translation_target_lang || undefined,
          };
        }
      } finally {
        pendingPreviewIds.delete(selectedMsgId);
      }
      if (!container.isConnected || !state.activeTabId.startsWith("lane:")) {
        return;
      }
      const curRows = state.mailSearchRows ?? state.mailLaneRows;
      const curSelected = curRows[state.mailSelectedRowIdx] ?? curRows[0];
      const curId = curSelected
        ? String(curSelected.id ?? curSelected.latest_message_id ?? "")
        : "";
      if (curId === selectedMsgId) {
        renderMailLaneView(container, actions);
      }
    })();
  }

  container.querySelectorAll("[data-mail-acct-tab]").forEach((el) => {
    el.addEventListener("click", () => {
      const acctVal = (el as HTMLElement).getAttribute("data-mail-acct-tab") ?? "all";
      actions.onSelectMailAccount?.(acctVal === "all" ? null : acctVal);
    });
  });

  container
    .querySelector("#mail-add-account-btn")
    ?.addEventListener("click", () => {
      actions.onAddMailAccount?.();
    });

  container
    .querySelector("#mail-onboarding-toggle-btn")
    ?.addEventListener("click", async () => {
      state.mailOnboardingOpen = !state.mailOnboardingOpen;
      await actions.onRefreshState();
    });

  container
    .querySelector("#mail-onboarding-close-btn")
    ?.addEventListener("click", async () => {
      state.mailOnboardingOpen = false;
      await actions.onRefreshState();
    });

  container.querySelectorAll("[data-onboard-msg]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const el = btn as HTMLElement;
      const mid = el.getAttribute("data-onboard-msg");
      const targetLbl = el.getAttribute("data-onboard-label") as
        | "email"
        | "ping"
        | "information"
        | "promotion"
        | null;
      if (!mid || !targetLbl) return;
      await sidecarLabelMailMessage(mid, targetLbl);
      await refreshMailState();
      await actions.onRefreshState();
    });
  });

  const searchInput = container.querySelector(
    "#mail-search-input"
  ) as HTMLInputElement | null;
  let searchDebounceTimer: number | null = null;
  searchInput?.addEventListener("input", () => {
    if (searchDebounceTimer !== null) {
      window.clearTimeout(searchDebounceTimer);
    }
    searchDebounceTimer = window.setTimeout(async () => {
      const q = searchInput.value.trim();
      state.mailSearchQuery = q;
      state.mailSelectedRowIdx = 0;
      if (!q) {
        state.mailSearchRows = null;
      } else {
        const res = await sidecarSearchMail(q, state.mailActiveAccountId);
        state.mailSearchRows = res.rows ?? [];
      }
      await actions.onRefreshState();
      const refocused = document.getElementById(
        "mail-search-input"
      ) as HTMLInputElement | null;
      if (refocused) {
        refocused.focus();
        const len = refocused.value.length;
        refocused.setSelectionRange(len, len);
      }
    }, 220);
  });
  searchInput?.addEventListener("keydown", async (e) => {
    if (e.key === "Enter") {
      if (searchDebounceTimer !== null) {
        window.clearTimeout(searchDebounceTimer);
      }
      const q = searchInput.value.trim();
      state.mailSearchQuery = q;
      state.mailSelectedRowIdx = 0;
      if (!q) {
        state.mailSearchRows = null;
      } else {
        const res = await sidecarSearchMail(q, state.mailActiveAccountId);
        state.mailSearchRows = res.rows ?? [];
      }
      await actions.onRefreshState();
    } else if (e.key === "Escape") {
      if (searchDebounceTimer !== null) {
        window.clearTimeout(searchDebounceTimer);
      }
      state.mailSearchQuery = "";
      state.mailSearchRows = null;
      await actions.onRefreshState();
    }
  });

  container
    .querySelector("#mail-search-clear-btn")
    ?.addEventListener("click", async () => {
      state.mailSearchQuery = "";
      state.mailSearchRows = null;
      state.mailSelectedRowIdx = 0;
      await actions.onRefreshState();
    });

  container
    .querySelector("#mail-compose-btn")
    ?.addEventListener("click", () => {
      actions.onOpenComposeTab();
    });

  container
    .querySelector("#mail-lane-refresh-btn")
    ?.addEventListener("click", async () => {
      await sidecarSyncMail();
      await refreshMailState();
      await actions.onRefreshState();
    });

  if (isSplitView) {
    container.querySelectorAll(".mail-list [data-mail-msg-id]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        const idxAttr = (el as HTMLElement).getAttribute("data-mail-row-idx");
        const nextIdx = idxAttr !== null ? Number(idxAttr) : -1;
        if (nextIdx >= 0 && nextIdx !== state.mailSelectedRowIdx) {
          state.mailSelectedRowIdx = nextIdx;
          renderMailLaneView(container, actions);
        }
      });
      el.addEventListener("dblclick", (e) => {
        e.stopPropagation();
        const mid = (el as HTMLElement).getAttribute("data-mail-msg-id");
        const subj =
          (el as HTMLElement).getAttribute("data-mail-msg-subject") || t("common.mail");
        if (mid) {
          actions.onOpenEmailMessage(mid, subj);
        }
      });
    });

    container
      .querySelector(".mail-list .mail-row.on")
      ?.scrollIntoView({ block: "nearest" });

    container
      .querySelector("[data-mail-open-tab]")
      ?.addEventListener("click", (e) => {
        e.stopPropagation();
        const mid = (e.currentTarget as HTMLElement).getAttribute(
          "data-mail-open-tab"
        );
        const subj =
          (e.currentTarget as HTMLElement).getAttribute(
            "data-mail-open-subject"
          ) || t("common.mail");
        if (mid) {
          actions.onOpenEmailMessage(mid, subj);
        }
      });

    if (selectedMsgId) {
      actions.onBindEmailReader?.(
        selectedMsgId,
        state.mailMessageDetails[selectedMsgId] ?? selectedRow
      );
    }
  } else {
    container.querySelectorAll("[data-mail-msg-id]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        const mid = (el as HTMLElement).getAttribute("data-mail-msg-id");
        const subj =
          (el as HTMLElement).getAttribute("data-mail-msg-subject") || t("common.mail");
        if (mid) {
          actions.onOpenEmailMessage(mid, subj);
        }
      });
    });
  }

  container.querySelectorAll("[data-open-site-url]").forEach((btn) => {
    const openSite = (e: Event) => {
      e.stopPropagation();
      const el = btn as HTMLElement;
      const url = el.getAttribute("data-open-site-url");
      const title = el.getAttribute("data-open-site-title") || t("mail.track_package");
      if (url) {
        actions.onOpenSiteUrl(url, title);
      }
    };
    btn.addEventListener("click", openSite);
    btn.addEventListener("mousedown", (e) => {
      if ((e as MouseEvent).button === 1) e.preventDefault();
    });
    btn.addEventListener("auxclick", (e) => {
      if ((e as MouseEvent).button === 1) {
        e.preventDefault();
        openSite(e);
      }
    });
  });

  bindMailIframeInteractions(container, {
    onOpenUrl: actions.onOpenSiteUrl,
    onOpenMailto: (seed) => actions.onOpenComposeTab(seed),
  });

  container.querySelectorAll(".mail-body a[href]").forEach((a) => {
    const openMailBodyAnchor = (e: Event) => {
      e.preventDefault();
      e.stopPropagation();
      const rawHref = (a as HTMLAnchorElement).getAttribute("href") ?? "";
      if (/^mailto:/i.test(rawHref)) {
        actions.onOpenComposeTab(parseMailtoHref(rawHref));
        return;
      }
      const webUrl = normalizeEmailLinkUrl(rawHref);
      if (webUrl) {
        const label = ((a as HTMLElement).textContent || "")
          .replace(/\s+/g, " ")
          .trim()
          .slice(0, 80);
        actions.onOpenSiteUrl(webUrl, label);
      }
    };
    a.addEventListener("click", openMailBodyAnchor);
    a.addEventListener("mousedown", (e) => {
      if ((e as MouseEvent).button === 1) e.preventDefault();
    });
    a.addEventListener("auxclick", (e) => {
      if ((e as MouseEvent).button === 1) openMailBodyAnchor(e);
    });
  });

  container.querySelectorAll("[data-copy-promo-code]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const code = (btn as HTMLElement).getAttribute("data-copy-promo-code");
      if (code && navigator.clipboard) {
        void navigator.clipboard.writeText(code);
        (btn as HTMLElement).innerHTML = `<strong>${escapeHtml(t("top.promo_copied"))}</strong>`;
      }
    });
  });

  if (state.mailAccounts.length === 0) {
    bindMailAccountsEvents(container, actions.onRefreshState, actions.onStartGoogleOAuth);
  }
}

function renderInboxRowsHtml(rows: Array<Record<string, unknown>>): string {
  const showAccountBadge =
    state.mailActiveAccountId === null && state.mailAccounts.length > 0;
  return rows
    .map((r, idx) => {
      const id = String(r.id ?? r.latest_message_id ?? "");
      const fromStr = String(
        r.from_name || r.from_addr || r.merchant || r.company || t("mail.unknown_sender")
      );
      const acctEmail = String(r.account_email ?? "");
      const subj = String(
        r.subject || r.order_number || r.domain || t("brain.no_subject")
      );
      const snip = String(r.snippet || r.status || "");
      const showOrig = Boolean(id && state.mailMessageShowOriginal[id]);
      const trSubj = String(r.translated_subject || "").trim();
      const trSnip = String(r.translated_snippet || "").trim();
      const trSrc = String(r.translation_source_lang || "").trim();
      const trTgt = String(
        r.translation_target_lang ||
          state.contentTranslationConfig?.primary_language ||
          "en"
      ).trim();
      const dispSubj = !showOrig && trSubj ? trSubj : subj;
      const dispSnip = !showOrig && trSnip ? trSnip : snip;
      const hasTrBadge = Boolean(!showOrig && (trSubj || trSnip) && trSrc);
      const ts = Number(r.date ?? r.last_update ?? 0);
      const timeLabel =
        ts > 0 ? formatRelativeTime(String(Math.floor(ts))) : "";
      const unseen = Number(r.seen ?? 1) === 0;
      const needsReply = Number(r.needs_reply ?? 0) === 1;
      const dueDate = r.due_date ? String(r.due_date) : "";
      const isSelected = idx === state.mailSelectedRowIdx;

      return `
        <div
          class="mail-row ${unseen ? "unread" : "read"} ${isSelected ? "on selected" : ""}"
          data-mail-msg-id="${escapeHtml(id)}"
          data-mail-row-idx="${idx}"
          data-mail-msg-subject="${escapeHtml(dispSubj)}"
        >
          <div class="h">
            ${unseen ? `<span class="dot accent" title="${escapeHtml(t("mail.unread"))}"></span>` : ""}
            <b>${escapeHtml(fromStr)}</b>
            ${showAccountBadge && acctEmail ? `<span class="badge soft" title="${escapeHtml(t("mail.account_email_title", { email: acctEmail }))}">${escapeHtml(acctEmail.split("@")[0] || acctEmail)}</span>` : ""}
            ${hasTrBadge ? `<span class="badge soft">${escapeHtml(t("mail.tr_pill", { src: trSrc, tgt: trTgt }))}</span>` : ""}
            ${needsReply ? `<span class="badge">${escapeHtml(t("mail.reply_badge"))}</span>` : ""}
            ${dueDate ? `<span class="badge soft">${escapeHtml(t("mail.due_date", { date: dueDate.slice(5) }))}</span>` : ""}
            <span class="time">${escapeHtml(timeLabel)}</span>
          </div>
          <div class="s">${escapeHtml(dispSubj)}</div>
          <div class="p">${escapeHtml(dispSnip)}</div>
        </div>
      `;
    })
    .join("");
}

export function renderEmailTabHeaderHtml(
  tab: BrowserTab,
  detailObj: Record<string, unknown> | undefined,
  includeOpenTabBtn = false
): string {
  const msg = (detailObj?.message ?? detailObj ?? {}) as Record<string, unknown>;
  const mid = String(
    msg.id || tab.url.replace("satzmail://message/", "").split("/")[0]
  );
  const fromName = String(msg.from_name || "");
  const fromAddr = String(msg.from_addr || "");
  const fromDisp = fromName ? `${fromName} <${fromAddr}>` : fromAddr || t("mail.loading");
  const toList = ((msg.to ?? []) as Array<Record<string, string>>)
    .map((x) => x.email || x.name)
    .join(", ");
  const ccList = ((msg.cc ?? []) as Array<Record<string, string>>)
    .map((x) => x.email || x.name)
    .join(", ");
  const subj = String(msg.subject || tab.title || t("brain.no_subject"));
  const trObj = (msg.translation as Record<string, unknown> | undefined) ?? undefined;
  const cachedHtml = mid ? state.mailMessageHtml[mid] : undefined;
  const srcLang = String(
    trObj?.source_lang ||
      msg.translation_source_lang ||
      msg.detected_language ||
      cachedHtml?.translation_source_lang ||
      ""
  );
  const primaryLang = state.contentTranslationConfig?.primary_language || "en";
  const tgtLang = String(
    trObj?.target_lang ||
      msg.translation_target_lang ||
      cachedHtml?.translation_target_lang ||
      primaryLang
  );
  const hasTranslation = Boolean(trObj || cachedHtml?.translated_html);
  const showOrig = Boolean(mid && state.mailMessageShowOriginal[mid]);
  const trSubj = String(trObj?.subject || msg.translated_subject || "").trim();
  const dispSubj = !showOrig && trSubj ? trSubj : subj;
  const needsTranslateOffer = Boolean(
    mid && !hasTranslation && srcLang && !isContentLanguageAllowed(srcLang)
  );
  const label = String(msg.label || "email");
  const ts = Number(msg.date ?? 0);
  const whenLabel = ts > 0 ? formatRelativeTime(String(Math.floor(ts))) : "";
  const allowRemote = Boolean(msg.allow_remote_images);
  const attachments = (msg.attachments ?? []) as Array<Record<string, unknown>>;
  const unsubInfo = (msg.unsubscribe ?? {}) as Record<string, unknown>;
  const canUnsub = Boolean(unsubInfo.available);

  return `
    <div class="section" id="email-tab-header-${escapeHtml(tab.id)}">
      <h2 class="mail-subject">${escapeHtml(dispSubj)}</h2>
      <div class="mail-from">
        <span class="mail-avatar">${escapeHtml(getInitials(fromName || fromAddr))}</span>
        <div class="mail-from-meta">
          <b>${escapeHtml(fromDisp)}</b>
          ${toList || ccList ? `<small>${toList ? escapeHtml(t("mail.to_list", { to: toList })) : ""}${toList && ccList ? " · " : ""}${ccList ? escapeHtml(t("mail.cc_list", { cc: ccList })) : ""}</small>` : ""}
        </div>
        ${whenLabel ? `<span class="when">${escapeHtml(whenLabel)}</span>` : ""}
      </div>
      <div class="mail-read-actions">
        <button type="button" class="btn primary" data-email-reply="${escapeHtml(mid)}">${icon("reply", "ico-sm")}<span>${escapeHtml(t("mail.reply_badge"))}</span></button>
        <button type="button" class="btn" data-email-reply-all="${escapeHtml(mid)}">${escapeHtml(t("mail.reply_all"))}</button>
        <button type="button" class="btn" data-email-forward="${escapeHtml(mid)}">${escapeHtml(t("mail.forward"))}</button>
        <button type="button" class="btn" data-email-hide="${escapeHtml(mid)}">${icon("archive", "ico-sm")}<span>${escapeHtml(t("common.archive"))}</span></button>
        ${
          canUnsub
            ? `<button type="button" class="btn" data-email-unsubscribe="${escapeHtml(mid)}" data-email-sender="${escapeHtml(fromName || fromAddr)}">${escapeHtml(t("mail.unsubscribe"))}</button>`
            : ""
        }
        ${
          mid
            ? hasTranslation
              ? `<button type="button" class="btn" data-email-toggle-orig="${escapeHtml(mid)}">${escapeHtml(
                  showOrig
                    ? t("mail.tr_show_translated", { src: srcLang || "?", tgt: tgtLang })
                    : t("mail.tr_show_orig", { src: srcLang || "?" })
                )}</button>`
              : `<button type="button" class="${needsTranslateOffer ? "btn primary" : "btn"}" data-email-translate="${escapeHtml(mid)}">${escapeHtml(
                  t("mail.tr_translate_btn", { tgt: primaryLang })
                )}</button>`
            : ""
        }
        ${
          hasTranslation && !showOrig
            ? `<span class="badge soft">${escapeHtml(t("mail.tr_pill", { src: srcLang || "?", tgt: tgtLang }))}</span>`
            : ""
        }
        ${
          includeOpenTabBtn
            ? `<button type="button" class="btn-text" data-mail-open-tab="${escapeHtml(mid)}" data-mail-open-subject="${escapeHtml(dispSubj)}">${icon("external", "ico-sm")}<span>${escapeHtml(t("mail.open_tab"))}</span></button>`
            : ""
        }
        <div class="end">
          <label class="mail-move-wrap">
            <span class="muted">${escapeHtml(t("mail.move_to_label"))}</span>
            <select
              class="select mail-move-select"
              data-email-move="${escapeHtml(mid)}"
              aria-label="${escapeHtml(t("mail.move_lane_aria"))}"
            >
              <option value="email" ${label === "email" ? "selected" : ""}>${escapeHtml(t("top.mail_inbox"))}</option>
              <option value="ping" ${label === "ping" ? "selected" : ""}>${escapeHtml(t("top.mail_pings"))}</option>
              <option value="information" ${label === "information" ? "selected" : ""}>${escapeHtml(t("top.mail_orders"))}</option>
              <option value="promotion" ${label === "promotion" ? "selected" : ""}>${escapeHtml(t("top.mail_promos"))}</option>
            </select>
          </label>
          ${
            !allowRemote && fromAddr
              ? `<button type="button" class="btn" data-email-allow-remote="${escapeHtml(fromAddr)}">${escapeHtml(t("mail.load_images"))}</button>`
              : ""
          }
        </div>
      </div>
      ${
        attachments.length > 0
          ? `<div class="mail-atts-row">
              <span class="muted">${escapeHtml(t("mail.attachments_n", { count: attachments.length }))}</span>
              ${attachments
                .map((a) => {
                  const partId = String(a.part_id ?? "");
                  const fname = String(a.filename ?? "file");
                  const sizeKb = Math.max(1, Math.round(Number(a.size ?? 0) / 1024));
                  const attKey = `${mid}:${partId}`;
                  const isPrev = Boolean(state.previewedAttachments[attKey]);
                  return `
                    <span class="mail-att-group">
                      <button type="button" class="pill" data-email-preview-att="${escapeHtml(mid)}" data-part-id="${escapeHtml(partId)}">
                        ${icon("doc", "ico-sm")}
                        <span>${isPrev ? escapeHtml(t("mail.att_hide")) : escapeHtml(fname)} (${escapeHtml(t("mail.att_kb", { size: sizeKb }))})</span>
                      </button>
                      <button type="button" class="btn-text" data-email-save-att="${escapeHtml(mid)}" data-part-id="${escapeHtml(partId)}">${escapeHtml(t("common.save"))}</button>
                    </span>
                  `;
                })
                .join("")}
            </div>
            ${attachments
              .map((a) => {
                const partId = String(a.part_id ?? "");
                const attKey = `${mid}:${partId}`;
                const prev = state.previewedAttachments[attKey];
                if (!prev || !prev.data_url) return "";
                if (prev.mime.startsWith("image/")) {
                  return `<img class="attach-img" src="${escapeHtml(prev.data_url)}" alt="${escapeHtml(prev.filename)}" />`;
                }
                return `<embed class="attach-embed" type="${escapeHtml(prev.mime)}" src="${escapeHtml(prev.data_url)}" />`;
              })
              .join("")}`
          : ""
      }
    </div>
  `;
}

export function renderEmailAgentRailCardsHtml(
  detailObj: Record<string, unknown> | undefined
): string {
  const msg = (detailObj?.message ?? detailObj ?? {}) as Record<string, unknown>;
  if (!msg || !msg.id) {
    return `
      <div class="section">
        <div class="muted">${escapeHtml(t("mail.loading_ctx"))}</div>
      </div>
    `;
  }

  const mid = String(msg.id ?? "");
  const senderCard = msg.sender_card as Record<string, unknown> | null;
  const extracts = (msg.extracts ?? {}) as Record<string, string>;
  const fromDisp = String(msg.from_name || msg.from_addr || t("mail.sender_fallback"));
  const subj = String(msg.subject || t("brain.no_subject"));
  const extractPairs = Object.entries(extracts).filter(
    ([, v]) => v !== undefined && v !== null && String(v).trim() !== ""
  );

  return `
    <div class="section" id="email-focused-rail-cards">
      <div class="card">
        <div class="card-h">
          <b>${escapeHtml(String(senderCard?.name ?? fromDisp))}</b>
          <span class="end badge soft">${escapeHtml(String(senderCard?.type ?? t("mail.contact_type")))}</span>
        </div>
        <div class="muted">${escapeHtml(String(senderCard?.summary ?? msg.from_addr ?? ""))}</div>
      </div>
      <div class="card">
        <div class="card-h">
          <b>${escapeHtml(t("mail.extracted_items"))}</b>
          <span class="end muted">${extractPairs.length}</span>
        </div>
        ${
          extractPairs.length === 0
            ? `<div class="muted">${escapeHtml(t("mail.no_extracts"))}</div>`
            : extractPairs
                .map(([k, v]) => {
                  const valStr = String(v);
                  const webUrl = normalizeEmailLinkUrl(valStr);
                  return webUrl
                    ? `<div class="rail-kv"><span>${escapeHtml(k)}</span><button type="button" class="btn-text inline-page-link" data-open-site-url="${escapeHtml(webUrl)}" data-open-site-title="${escapeHtml(k)}" title="${escapeHtml(t("mail.open_conv_link", { url: webUrl }))}">${escapeHtml(webUrl)} ↗</button></div>`
                    : `<div class="rail-kv"><span>${escapeHtml(k)}</span><span>${escapeHtml(valStr)}</span></div>`;
                })
                .join("")
        }
      </div>
      <div class="mail-chip-row">
        <button type="button" class="chip" data-email-rail-save-brain="${escapeHtml(mid)}" data-email-rail-subj="${escapeHtml(subj)}">
          ${icon("brain", "ico-sm")}
          <span>${escapeHtml(t("mail.save_to_brain"))}</span>
        </button>
        <button type="button" class="chip" data-email-rail-ask="ask about this email: ${escapeHtml(subj)}">
          ${icon("chat", "ico-sm")}
          <span>${escapeHtml(t("mail.ask_about_email"))}</span>
        </button>
        <button type="button" class="chip" data-email-rail-ask="summarize this email">${escapeHtml(t("mail.summarize"))}</button>
        <button type="button" class="chip" data-email-rail-ask="draft a reply to this email">${escapeHtml(t("mail.draft_reply"))}</button>
        <button type="button" class="chip" data-email-rail-ask="extract dates and action items from this email">${escapeHtml(t("mail.extract_dates"))}</button>
      </div>
    </div>
  `;
}

export function renderComposeEditorHtml(
  draft: MailComposeDraft,
  scopeId: string,
  opts?: { mode?: "modal" | "tab" | "inline"; title?: string }
): string {
  const mode = opts?.mode ?? "modal";
  const accounts = state.mailAccounts ?? [];
  const defaultAcct = accounts[0]?.id ?? "";
  if (!draft.account_id && defaultAcct) {
    draft.account_id = defaultAcct;
  }
  const models = getComposeModelsForPicker();
  const activeAiModel =
    draft.ai_model && models.some((m) => m.id === draft.ai_model)
      ? draft.ai_model
      : getDefaultComposeModelId();
  draft.ai_model = activeAiModel;
  const sc = escapeHtml(scopeId);
  const heading =
    opts?.title || (draft.reply_to_message_id ? t("mail.reply_badge") : t("mail.compose_heading"));
  const showCcBcc = mode !== "inline" || Boolean(draft.cc || draft.bcc);

  return `
    <div class="compose-editor compose-mode-${mode}" data-compose-scope="${sc}">
      <div class="card-h">
        ${icon("compose", "ico-sm")}
        <b>${escapeHtml(heading)}</b>
        <span class="muted">${escapeHtml(t("mail.compose_sub"))}</span>
        <span class="end">
          <button
            type="button"
            class="btn primary"
            data-compose-send="${sc}"
            ${draft.ai_loading ? "disabled" : ""}
            title="${escapeHtml(t("mail.prepare_send_title", { mod: MOD_LABEL }))}"
          >${icon("send", "ico-sm")}<span>${escapeHtml(t("mail.send_btn"))}</span></button>
          ${
            mode === "inline"
              ? `<button type="button" class="btn" data-compose-popout="${sc}" title="${escapeHtml(t("mail.popout_title"))}">${icon("external", "ico-sm")}<span>${escapeHtml(t("mail.popout_btn"))}</span></button>`
              : mode === "modal"
                ? `<button type="button" class="icon-btn" data-compose-close="${sc}" title="${escapeHtml(t("mail.close_esc_title"))}">${icon("x", "ico-sm")}</button>`
                : ""
          }
        </span>
      </div>

      ${draft.status_msg ? renderStatusBannerHtml(draft.status_msg) : ""}

      ${
        draft.confirm_token && draft.confirm_line
          ? `<div class="draft" data-compose-confirm-bar="${sc}">
              <div class="gate">${escapeHtml(t("mail.send_gate_note"))}</div>
              <div>${escapeHtml(draft.confirm_line).replace(/\[new\]/g, `<span class="badge soft">${escapeHtml(t("mail.new_recipient_badge"))}</span>`)}</div>
              <div class="acts">
                <button type="button" class="btn primary" data-compose-confirm-send="${sc}">${escapeHtml(t("mail.confirm_send_btn"))}</button>
                <button type="button" class="btn" data-compose-cancel-send="${sc}">${escapeHtml(t("common.cancel"))}</button>
              </div>
            </div>`
          : ""
      }

      ${
        draft.queued_outbox_id
          ? `<div class="banner" data-compose-undo-bar="${sc}">
              <span>${escapeHtml(t("mail.queued_undo"))}</span>
              <button type="button" class="btn" data-compose-undo-send="${sc}">${escapeHtml(t("mail.undo_btn"))}</button>
            </div>`
          : ""
      }

      <div class="compose-ai-row">
        <select
          class="select compose-ai-model"
          data-compose-field="ai_model"
          data-compose-scope="${sc}"
          title="${escapeHtml(getModelPrivacySummary(activeAiModel))}"
        >
          ${models
            .map(
              (m) =>
                `<option value="${escapeHtml(m.id)}" ${m.id === activeAiModel ? "selected" : ""}>${escapeHtml(m.label)}</option>`
            )
            .join("")}
        </select>
        <input
          class="input compose-ai-prompt"
          type="text"
          data-compose-field="ai_prompt"
          data-compose-scope="${sc}"
          placeholder="${escapeHtml(draft.body.trim() ? t("mail.ai_revise_ph") : t("mail.ai_generate_ph"))}"
          value="${escapeHtml(draft.ai_prompt ?? "")}"
        />
        <button
          type="button"
          class="btn"
          data-compose-generate="${sc}"
          ${draft.ai_loading ? "disabled" : ""}
        >
          ${icon("spark", "ico-sm")}
          <span>${escapeHtml(draft.ai_loading ? t("mail.generating") : draft.body.trim() ? t("mail.generate_revise") : t("mail.generate"))}</span>
        </button>
      </div>

      <div class="card inset compose-fields-card">
        <div class="form-row">
          <label class="muted">${escapeHtml(t("mail.from_label"))}</label>
          <select class="select" data-compose-field="account_id" data-compose-scope="${sc}">
            ${
              accounts.length === 0
                ? `<option value="">${escapeHtml(t("mail.no_acct_unlocked"))}</option>`
                : accounts
                    .map(
                      (a) =>
                        `<option value="${escapeHtml(a.id)}" ${a.id === draft.account_id ? "selected" : ""}>${escapeHtml(a.label)} &lt;${escapeHtml(a.email)}&gt;</option>`
                    )
                    .join("")
            }
          </select>
        </div>
        <div class="form-row">
          <input
            class="input"
            type="text"
            data-compose-field="to"
            data-compose-scope="${sc}"
            placeholder="${escapeHtml(t("mail.to_ph"))}"
            value="${escapeHtml(draft.to)}"
          />
          ${
            showCcBcc
              ? `
            <input
              class="input"
              type="text"
              data-compose-field="cc"
              data-compose-scope="${sc}"
              placeholder="${escapeHtml(t("mail.cc_ph"))}"
              value="${escapeHtml(draft.cc)}"
            />
            <input
              class="input"
              type="text"
              data-compose-field="bcc"
              data-compose-scope="${sc}"
              placeholder="${escapeHtml(t("mail.bcc_ph"))}"
              value="${escapeHtml(draft.bcc)}"
            />
          `
              : ""
          }
        </div>
        <div class="form-row">
          <input
            class="input"
            type="text"
            data-compose-field="subject"
            data-compose-scope="${sc}"
            placeholder="${escapeHtml(t("mail.subject_ph"))}"
            value="${escapeHtml(draft.subject)}"
          />
        </div>
        <textarea
          class="textarea ${mode === "inline" ? "compose-textarea-inline" : "compose-textarea"}"
          data-compose-field="body"
          data-compose-scope="${sc}"
          rows="${mode === "inline" ? 7 : 12}"
          placeholder="${escapeHtml(t("mail.body_ph"))}"
        >${escapeHtml(draft.body)}</textarea>
      </div>
    </div>
  `;
}

export function bindComposeEditorEvents(
  container: HTMLElement,
  draft: MailComposeDraft,
  scopeId: string,
  callbacks: {
    onChanged: () => void;
    onClose?: () => void;
    onPopout?: (draft: MailComposeDraft) => void;
  }
): void {
  const root = container.querySelector(
    `[data-compose-scope="${CSS.escape(scopeId)}"]`
  ) as HTMLElement | null;
  if (!root) return;

  const getField = <T extends HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(
    field: string
  ): T | null =>
    root.querySelector(`[data-compose-field="${field}"]`) as T | null;

  const syncFields = () => {
    const acctEl = getField<HTMLSelectElement>("account_id");
    if (acctEl) draft.account_id = acctEl.value;
    const modelEl = getField<HTMLSelectElement>("ai_model");
    if (modelEl) draft.ai_model = modelEl.value as LocalModelId;
    const aiPromptEl = getField<HTMLInputElement>("ai_prompt");
    if (aiPromptEl) draft.ai_prompt = aiPromptEl.value;
    const toEl = getField<HTMLInputElement>("to");
    if (toEl) draft.to = toEl.value;
    const ccEl = getField<HTMLInputElement>("cc");
    if (ccEl) draft.cc = ccEl.value;
    const bccEl = getField<HTMLInputElement>("bcc");
    if (bccEl) draft.bcc = bccEl.value;
    const subjEl = getField<HTMLInputElement>("subject");
    if (subjEl) draft.subject = subjEl.value;
    const bodyEl = getField<HTMLTextAreaElement>("body");
    if (bodyEl) draft.body = bodyEl.value;
  };

  root.querySelectorAll("[data-compose-field]").forEach((el) => {
    el.addEventListener("input", syncFields);
    el.addEventListener("change", syncFields);
  });

  const handleGenerate = async () => {
    syncFields();
    if (draft.ai_loading) return;
    const model = draft.ai_model || getDefaultComposeModelId();
    draft.ai_loading = true;
    draft.status_msg = t("mail.status_generating_draft", { model });
    callbacks.onChanged();
    try {
      const res = await sidecarDraftMailReply({
        message_id: draft.reply_to_message_id,
        to: draft.to,
        cc: draft.cc,
        subject: draft.subject,
        instructions: draft.ai_prompt || "",
        current_body: draft.body,
        model,
        structured: !draft.to.trim() || !draft.subject.trim(),
      });
      if (res.ok) {
        if (res.draft_id) draft.ai_draft_id = res.draft_id;
        if (res.to && !draft.to.trim()) draft.to = res.to;
        if (res.subject && !draft.subject.trim()) draft.subject = res.subject;
        if (res.body !== undefined) draft.body = res.body;
        const styleNote = res.style_applied ? t("mail.style_applied_suffix") : "";
        draft.status_msg = t("mail.status_draft_ready", {
          model: res.model || model,
          style: styleNote,
        });
      } else {
        draft.status_msg = t("mail.err_draft", {
          error: res.error ?? t("mail.err_failed"),
        });
      }
    } finally {
      draft.ai_loading = false;
      callbacks.onChanged();
    }
  };

  const handlePrepare = async () => {
    syncFields();
    const res = await sidecarPrepareMailSend({
      account_id: draft.account_id,
      to: draft.to,
      cc: draft.cc,
      bcc: draft.bcc,
      subject: draft.subject,
      body: draft.body,
      in_reply_to: draft.in_reply_to,
      references: draft.references,
      reply_to_message_id: draft.reply_to_message_id,
      ai_draft_id: draft.ai_draft_id ?? "",
    });
    if (res.ok && res.confirm_token && res.outbox_id) {
      draft.confirm_outbox_id = res.outbox_id;
      draft.confirm_token = res.confirm_token;
      draft.confirm_line = res.confirm_line;
      draft.status_msg = "";
    } else {
      draft.status_msg = t("mail.err_send_prepare", {
        error: res.error ?? t("mail.err_failed"),
      });
    }
    callbacks.onChanged();
  };

  getField<HTMLInputElement>("ai_prompt")?.addEventListener("keydown", (e) => {
    if ((e as KeyboardEvent).key === "Enter") {
      e.preventDefault();
      void handleGenerate();
    }
  });

  root
    .querySelector(`[data-compose-generate="${CSS.escape(scopeId)}"]`)
    ?.addEventListener("click", () => {
      void handleGenerate();
    });

  root
    .querySelector(`[data-compose-send="${CSS.escape(scopeId)}"]`)
    ?.addEventListener("click", () => {
      void handlePrepare();
    });

  getField<HTMLTextAreaElement>("body")?.addEventListener("keydown", (e) => {
    const ke = e as KeyboardEvent;
    if ((ke.ctrlKey || ke.metaKey) && ke.key === "Enter") {
      ke.preventDefault();
      void handlePrepare();
    }
  });

  root
    .querySelector(`[data-compose-confirm-send="${CSS.escape(scopeId)}"]`)
    ?.addEventListener("click", async () => {
      if (!draft.confirm_outbox_id || !draft.confirm_token) return;
      const outboxId = draft.confirm_outbox_id;
      const tok = draft.confirm_token;
      draft.confirm_outbox_id = undefined;
      draft.confirm_token = undefined;
      draft.confirm_line = undefined;
      const res = await sidecarConfirmMailSend(outboxId, tok);
      if (res.ok) {
        draft.queued_outbox_id = outboxId;
        draft.status_msg = t("mail.status_sending_10s");
      } else {
        draft.status_msg = t("mail.err_send_rejected", {
          error: res.error ?? t("mail.err_failed"),
        });
      }
      callbacks.onChanged();
    });

  root
    .querySelector(`[data-compose-cancel-send="${CSS.escape(scopeId)}"]`)
    ?.addEventListener("click", () => {
      draft.confirm_outbox_id = undefined;
      draft.confirm_token = undefined;
      draft.confirm_line = undefined;
      draft.status_msg = t("mail.status_send_cancelled");
      callbacks.onChanged();
    });

  root
    .querySelector(`[data-compose-undo-send="${CSS.escape(scopeId)}"]`)
    ?.addEventListener("click", async () => {
      if (!draft.queued_outbox_id) return;
      const res = await sidecarUndoMailSend(draft.queued_outbox_id);
      if (res.ok) {
        draft.queued_outbox_id = undefined;
        draft.status_msg = t("mail.status_send_undone");
      } else {
        draft.status_msg = t("mail.err_undo_failed", {
          error: res.error ?? t("mail.err_already_sent"),
        });
      }
      callbacks.onChanged();
    });

  root
    .querySelector(`[data-compose-close="${CSS.escape(scopeId)}"]`)
    ?.addEventListener("click", () => {
      syncFields();
      callbacks.onClose?.();
    });

  root
    .querySelector(`[data-compose-popout="${CSS.escape(scopeId)}"]`)
    ?.addEventListener("click", () => {
      syncFields();
      callbacks.onPopout?.(draft);
    });
}

export function renderMailComposeModalOverlay(actions: {
  onChanged: () => void;
  onClose: () => void;
}): void {
  let overlay = document.getElementById("mail-compose-overlay");
  const draft = state.mailComposeModalDraft;
  if (!state.mailComposeModalOpen || !draft) {
    if (overlay) {
      overlay.remove();
    }
    return;
  }

  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "mail-compose-overlay";
    overlay.className = "modal-backdrop compose-backdrop";
    document.body.appendChild(overlay);
  } else {
    overlay.className = "modal-backdrop compose-backdrop";
  }

  const scopeId = "modal-compose";
  overlay.innerHTML = `
    <div class="card glass compose-modal" role="dialog" aria-label="${escapeHtml(t("mail.compose_heading"))}">
      ${renderComposeEditorHtml(draft, scopeId, {
        mode: "modal",
        title: draft.reply_to_message_id ? t("mail.reply_badge") : t("mail.compose_heading"),
      })}
    </div>
  `;

  overlay.onclick = (e) => {
    if (
      e.target === overlay &&
      !draft.body.trim() &&
      !draft.to.trim() &&
      !draft.subject.trim()
    ) {
      actions.onClose();
    }
  };

  bindComposeEditorEvents(overlay, draft, scopeId, {
    onChanged: actions.onChanged,
    onClose: actions.onClose,
  });

  if (!draft.ai_loading && !draft.confirm_token) {
    const focusEl = (
      !draft.to.trim()
        ? overlay.querySelector('[data-compose-field="to"]')
        : overlay.querySelector('[data-compose-field="body"]')
    ) as HTMLElement | null;
    if (focusEl && !overlay.contains(document.activeElement)) {
      focusEl.focus();
    }
  }
}

export function renderComposeTabView(
  container: HTMLElement,
  tab: BrowserTab,
  onChanged: () => void
): void {
  const accounts = state.mailAccounts;
  const defaultAcct = accounts[0]?.id ?? "";
  const draft = (state.mailComposeDrafts[tab.id] ??= {
    account_id: defaultAcct,
    to: "",
    cc: "",
    bcc: "",
    subject: tab.title && tab.title !== "compose" ? tab.title : "",
    body: "",
    in_reply_to: "",
    references: "",
    reply_to_message_id: "",
    ai_prompt: "",
    ai_model: getDefaultComposeModelId(),
  });

  container.innerHTML = `
    <div class="compose-view" id="compose-view-${escapeHtml(tab.id)}">
      ${renderComposeEditorHtml(draft, tab.id, { mode: "tab" })}
    </div>
  `;

  bindComposeEditorEvents(container, draft, tab.id, { onChanged });
}

export {
  sidecarGetMailMessage,
  sidecarGetMailMessageHtml,
  sidecarHideMailMessage,
  sidecarLabelMailMessage,
  sidecarOpenMailMessage,
  sidecarSaveMailAttachment,
  sidecarUpdateMailSettings,
};
