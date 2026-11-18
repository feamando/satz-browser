import {
  apiEnsureMailConversation,
  sidecarAddMailAccount,
  sidecarConfirmMailSend,
  sidecarCreateProfile,
  sidecarDraftMailReply,
  sidecarFetchKnowledge,
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
  sidecarUnlockProfile,
  sidecarUnlockProfileKeychain,
  sidecarUpdateMailSettings,
} from "./api";
import { icon } from "./design-system/icons";
import {
  escapeHtml,
  formatRelativeTime,
  getResolvedTheme,
  IS_MAC,
  MOD_LABEL,
  state,
} from "./state";
import type { BrowserTab, MailPreset } from "./types";

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
  onRefreshState: () => Promise<void>;
}

const pendingPreviewIds = new Set<string>();

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
    a, a * { color: ${accentColor} !important; text-decoration: underline !important; }
    pre { white-space: pre-wrap; word-break: break-word; font-family: inherit !important; margin: 0; }
    code, kbd { font-family: 'JetBrains Mono', monospace; }
    blockquote { border-left: 2px solid ${lineColor} !important; margin: 8px 0; padding-left: 12px; color: ${mutedColor} !important; }
  </style>`;

  if (rawHtml) {
    return `<meta http-equiv="Content-Security-Policy" content="${escapeHtml(csp)}">${themeMeta}${rawHtml}${themeOverrideCss}`;
  }
  if (!plainFallback) return "";
  const fallbackDoc = `<!DOCTYPE html><html><head><meta charset="utf-8">${themeMeta}${themeOverrideCss}</head><body><pre>${escapeHtml(plainFallback)}</pre></body></html>`;
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
  const variant =
    low.includes("error") || low.includes("failed") || low.includes("rejected")
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
        <div class="label"><span>Mail accounts</span><span class="end">Vault locked</span></div>
        <div class="muted">Unlock your profile with its 6-digit PIN above to view, add, or sync mail accounts.</div>
      </div>
    `;
  }

  return `
    <div class="section" id="mail-accounts-panel">
      <div class="label">
        <span>Mail accounts</span>
        <span class="ct">${accounts.length}</span>
        <span class="end">
          <button
            id="mail-toggle-eval-btn"
            type="button"
            class="btn-text ${state.mailEvalOpen ? "pri" : ""}"
          >Eval mode (200 emails)</button>
          <button id="mail-sync-all-btn" type="button" class="btn-text">Sync now</button>
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
          ? `<div class="muted">No mail accounts configured yet. Add an account below (Gmail/Outlook require an app password).</div>`
          : `
          <div class="table-wrap">
            <table class="table">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Incoming</th>
                  <th>Outgoing</th>
                  <th>Vault</th>
                  <th class="num">Messages</th>
                  <th>Status</th>
                  <th>Actions</th>
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
                      ? "Auth failed"
                      : a.last_error
                        ? escapeHtml(a.last_error.slice(0, 48))
                        : a.last_sync_at > 0
                          ? `Synced ${escapeHtml(formatRelativeTime(String(Math.floor(a.last_sync_at))))}`
                          : "Ready";
                    return `
                  <tr>
                    <td><b>${escapeHtml(a.label)}</b> · ${escapeHtml(a.email)}</td>
                    <td>${escapeHtml(a.protocol.toUpperCase())} ${escapeHtml(a.in_host)}:${a.in_port} (${escapeHtml(a.in_security)})</td>
                    <td>SMTP ${escapeHtml(a.smtp_host)}:${a.smtp_port} (${escapeHtml(a.smtp_security)})</td>
                    <td class="muted">${escapeHtml(a.vault_prefix)}</td>
                    <td class="num">${a.message_count ?? 0}</td>
                    <td><span class="status">${statusDot}<span>${statusText}</span></span></td>
                    <td>
                      <button type="button" class="btn-text" data-mail-test-acct="${escapeHtml(a.id)}">Test</button>
                      <button type="button" class="btn-text" data-mail-sync-acct="${escapeHtml(a.id)}">Sync</button>
                      <button type="button" class="btn-text" data-mail-remove-acct="${escapeHtml(a.id)}">Remove</button>
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
          <b>Add mail account</b>
          <span class="end muted">Credentials are stored in your encrypted vault</span>
        </div>
        <div class="form-row">
          <select id="mail-preset-select" class="select">
            ${presets
              .map(
                (p) =>
                  `<option value="${escapeHtml(p.id)}">${escapeHtml(p.label)} (${p.protocol.toUpperCase()})</option>`
              )
              .join("")}
          </select>
          <input id="mail-acct-email" class="input" type="text" placeholder="Email (you@gmail.com)" />
          <input id="mail-acct-label" class="input" type="text" placeholder="Account name (optional)" value="" />
          <input id="mail-acct-password" class="input" type="password" placeholder="App password" />
        </div>
        <div class="form-row">
          <select id="mail-acct-protocol" class="select">
            <option value="imap">IMAP</option>
            <option value="pop3">POP3 (leave on server)</option>
          </select>
          <input id="mail-acct-in-host" class="input" type="text" placeholder="Incoming host" value="imap.gmail.com" />
          <input id="mail-acct-in-port" class="input" type="number" placeholder="993" value="993" />
          <select id="mail-acct-in-sec" class="select">
            <option value="ssl">SSL</option>
            <option value="starttls">STARTTLS</option>
          </select>
        </div>
        <div class="form-row">
          <input id="mail-acct-smtp-host" class="input" type="text" placeholder="SMTP host" value="smtp.gmail.com" />
          <input id="mail-acct-smtp-port" class="input" type="number" placeholder="587" value="587" />
          <select id="mail-acct-smtp-sec" class="select">
            <option value="starttls">STARTTLS</option>
            <option value="ssl">SSL</option>
          </select>
          <button id="mail-form-test-btn" type="button" class="btn">Test</button>
          <button id="mail-form-add-btn" type="button" class="btn primary">Add account</button>
        </div>
      </div>
    </div>
  `;
}

export function bindMailAccountsEvents(
  container: HTMLElement,
  onChanged: () => Promise<void>
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
    .querySelector("#mail-form-test-btn")
    ?.addEventListener("click", async () => {
      state.mailStatusMessage =
        "Testing incoming and outgoing login (SMTP EHLO + AUTH)...";
      await onChanged();
      const res = await sidecarTestMailAccount(collectFormPayload());
      if (res.ok) {
        state.mailStatusMessage =
          "Test passed: incoming and outgoing login verified.";
      } else {
        state.mailStatusMessage = `Test failed: ${res.error ?? "unknown error"}`;
      }
      await onChanged();
    });

  container
    .querySelector("#mail-form-add-btn")
    ?.addEventListener("click", async () => {
      const payload = collectFormPayload();
      state.mailStatusMessage = "Adding account and starting background sync...";
      await onChanged();
      const res = await sidecarAddMailAccount(payload);
      if (res.ok) {
        await apiEnsureMailConversation();
        state.mailStatusMessage = `Added account (${res.vault_prefix ?? "vault"}). Syncing last 30 days...`;
        await refreshMailState();
      } else {
        state.mailStatusMessage = `Error adding account: ${res.error ?? "failed"}`;
      }
      await onChanged();
    });

  container
    .querySelector("#mail-sync-all-btn")
    ?.addEventListener("click", async () => {
      state.mailStatusMessage = "Syncing all mail accounts...";
      await onChanged();
      const res = await sidecarSyncMail();
      await refreshMailState();
      state.mailStatusMessage = res.ok
        ? "Sync complete."
        : `Sync error: ${res.error ?? "failed"}`;
      await onChanged();
    });

  container.querySelectorAll("[data-mail-test-acct]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = (btn as HTMLElement).getAttribute("data-mail-test-acct");
      if (!id) return;
      state.mailStatusMessage = `Testing account ${id}...`;
      await onChanged();
      const res = await sidecarTestMailAccount({ account_id: id });
      state.mailStatusMessage = res.ok
        ? `Account ${id}: incoming & SMTP test verified.`
        : `Account ${id} test failed: ${res.error ?? "error"}`;
      await onChanged();
    });
  });

  container.querySelectorAll("[data-mail-sync-acct]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = (btn as HTMLElement).getAttribute("data-mail-sync-acct");
      if (!id) return;
      state.mailStatusMessage = `Syncing account ${id}...`;
      await onChanged();
      const res = await sidecarSyncMail(id);
      await refreshMailState();
      state.mailStatusMessage = res.ok
        ? `Synced ${res.synced_count ?? 0} new messages.`
        : `Sync failed: ${res.error ?? "error"}`;
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
        ? `Removed account ${id}.`
        : `Remove failed: ${res.error ?? "error"}`;
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
          <b>Eval mode</b>
          <span class="end muted">200 stratified emails · excluded from training</span>
        </div>
        <div class="muted">No messages sampled yet. Sync a mail account first.</div>
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

  return `
    <div class="card" id="mail-eval-card">
      <div class="card-h">
        <b>Eval mode</b>
        <span class="badge soft">${idx + 1} / ${items.length}</span>
        <span class="muted">Labelled: ${Number(rep.total_evaluated ?? 0)}</span>
        <span class="end">
          <button type="button" class="btn" data-eval-nav="prev">Prev</button>
          <button type="button" class="btn" data-eval-nav="next">Next</button>
        </span>
      </div>
      <div class="mail-read-actions">
        <span><b>${escapeHtml(String(item.from_name || item.from_addr || ""))}</b> · ${escapeHtml(String(item.subject || ""))}</span>
        <span class="end muted">Pred: ${escapeHtml(predLabel)} (${Number(item.pred_confidence ?? 0).toFixed(2)})${humanLabel ? ` · Label: ${escapeHtml(humanLabel)}` : ""}</span>
      </div>
      <div class="eval-excerpt">${escapeHtml(String(item.new_text || item.snippet || "").slice(0, 360))}</div>
      <div class="mail-read-actions">
        <span class="muted">Label (keys 1-4):</span>
        <div class="seg" role="group" aria-label="Message label">
          <button type="button" data-eval-label="email" aria-pressed="${humanLabel === "email" ? "true" : "false"}">1 Email</button>
          <button type="button" data-eval-label="ping" aria-pressed="${humanLabel === "ping" ? "true" : "false"}">2 Ping</button>
          <button type="button" data-eval-label="information" aria-pressed="${humanLabel === "information" ? "true" : "false"}">3 Information</button>
          <button type="button" data-eval-label="promotion" aria-pressed="${humanLabel === "promotion" ? "true" : "false"}">4 Promotion</button>
        </div>
      </div>
      ${
        showExtractCheck
          ? `<div class="mail-read-actions">
              <span class="muted">Extracts: ${
                extEntries.length > 0
                  ? extEntries
                      .map(([k, v]) => `${escapeHtml(k)}=${escapeHtml(v)}`)
                      .join(" · ")
                  : "(none)"
              }</span>
              <span class="end">
                <span class="muted">Correct?</span>
                <div class="seg" role="group" aria-label="Extraction check">
                  <button type="button" data-eval-extract="y" aria-pressed="${item.human_extract_ok === 1 ? "true" : "false"}">Yes (y)</button>
                  <button type="button" data-eval-extract="n" aria-pressed="${item.human_extract_ok === 0 ? "true" : "false"}">No (n)</button>
                </div>
              </span>
            </div>`
          : ""
      }
      <div class="mail-read-actions">
        <span class="muted">
          Gates: email to promo ${Number(rep.real_email_misfiled_as_promotion_pct ?? 0).toFixed(2)}% (target &lt;=1%) ·
          promo recall ${Number(rep.promotion_recall_pct ?? 100).toFixed(2)}% (target &gt;=90%) ·
          extract acc ${Number(rep.extraction_accuracy_pct ?? 100).toFixed(2)}% (target &gt;=90%)
        </span>
        <span class="badge ${rep.gates_passed ? "" : "soft"}">${rep.gates_passed ? "Gates pass" : "Pending"}</span>
      </div>
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>True \\ Pred</th>
              <th class="num">Email</th>
              <th class="num">Ping</th>
              <th class="num">Information</th>
              <th class="num">Promotion</th>
            </tr>
          </thead>
          <tbody>
            ${labels
              .map(
                (t) => `
              <tr>
                <td>${escapeHtml(t)}</td>
                ${labels
                  .map((p) => `<td class="num">${Number(matrix[t]?.[p] ?? 0)}</td>`)
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
      ? `synced ${formatRelativeTime(String(Math.floor(latestSync)))}`
      : "ready";

  return `
    <div class="acct-bar">
      <button
        type="button"
        class="pill round ${state.mailActiveAccountId === null ? "on" : ""}"
        data-mail-acct-tab="all"
        aria-pressed="${state.mailActiveAccountId === null ? "true" : "false"}"
        title="Unified view across all configured email accounts"
      >
        <span>All mail</span>
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
              title="Filter mail lanes to ${escapeHtml(acct.email || acctName)}"
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
        title="Add email account in Settings"
      >
        ${icon("plus", "ico-sm")}
        <span>Add account</span>
      </button>
      <div class="end">
        <span>${escapeHtml(syncLabel)}</span>
        ${
          showOnboardingBtn
            ? `<button id="mail-onboarding-toggle-btn" type="button" class="btn ${state.mailOnboardingOpen ? "primary" : ""}">Sort 10 emails</button>`
            : ""
        }
        <button id="mail-compose-btn" type="button" class="btn" title="Compose email (c)">
          ${icon("compose", "ico-sm")}
          <span>Compose</span>
        </button>
        <button id="mail-lane-refresh-btn" type="button" class="btn" title="Sync all accounts">
          ${icon("reload", "ico-sm")}
          <span>Sync now</span>
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
        <div class="mail-empty">Select a message to read.</div>
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
  const fromPrimary = fromName || fromAddr || "Sender";
  const subj = String(
    msg.subject || selectedRow.subject || "(no subject)"
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
  const defaultCsp =
    "default-src 'none'; img-src data: cid:; style-src 'unsafe-inline'; font-src data:";
  const effectiveCsp = cachedHtml?.csp || defaultCsp;
  const iframeSrcdoc = cachedHtml?.html
    ? buildMailIframeSrcdoc(cachedHtml.html, plainText, effectiveCsp)
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
              <div><b>Action date</b> · ${escapeHtml(dueDate)}</div>
              <button
                type="button"
                class="btn primary"
                data-email-rail-ask="extract dates and action items from this email: ${escapeHtml(subj)}"
              >Add to calendar</button>
            </div>`
          : ""
      }
      ${
        trackingNo || trackingUrl
          ? `<div class="extract">
              ${icon("box", "ico-sm")}
              <div><b>Tracking</b> · ${escapeHtml(trackingNo || "Shipment link")}</div>
              ${
                trackingUrl
                  ? `<button type="button" class="btn primary" data-open-site-url="${escapeHtml(trackingUrl)}">Track</button>`
                  : ""
              }
            </div>`
          : ""
      }
      ${
        iframeSrcdoc
          ? `<iframe
              class="email-frame"
              sandbox="allow-popups allow-popups-to-escape-sandbox"
              referrerpolicy="no-referrer"
              srcdoc="${escapeHtml(iframeSrcdoc)}"
            ></iframe>`
          : `<div class="mail-body">
              ${
                plainText
                  ? plainText
                      .split(/\n{2,}/)
                      .filter((p) => p.trim())
                      .map((p) => `<p>${escapeHtml(p.trim())}</p>`)
                      .join("")
                  : `<p class="muted">Loading message from ${escapeHtml(fromPrimary)}...</p>`
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

  if (!unlocked) {
    const profilesList = state.knowledge.profile?.profiles ?? [];
    container.innerHTML = `
      <div class="mail-view">
        <div class="view-h">
          <div>
            <h1>Mail</h1>
            <p>Unlock your profile to access Inbox, Pings, Orders, and Promos.</p>
          </div>
        </div>
        <div class="banner warn">
          ${icon("lock", "ico-sm")}
          <b>Mail is locked</b>
          <span>Enter your 6-digit PIN to decrypt mail accounts and messages.</span>
        </div>
        ${
          state.profileStatusMessage
            ? renderStatusBannerHtml(state.profileStatusMessage)
            : ""
        }
        <div class="card">
          ${
            profilesList.length === 0
              ? `
            <div class="muted">Create a profile with a 6-digit PIN to unlock Mail in place.</div>
            <div class="form-row">
              <input
                id="mail-inline-new-profile-name"
                class="input"
                type="text"
                spellcheck="false"
                autocorrect="off"
                autocapitalize="off"
                placeholder="Profile name (e.g. Nikita)"
              />
              <input
                id="mail-inline-new-profile-pin"
                class="input pin"
                type="password"
                inputmode="numeric"
                maxlength="6"
                spellcheck="false"
                autocorrect="off"
                autocapitalize="off"
                placeholder="6-digit PIN"
              />
              <button id="mail-inline-create-profile-btn" type="button" class="btn primary">Create &amp; unlock</button>
            </div>
          `
              : `
            <div class="muted">Select profile and enter your 6-digit PIN:</div>
            <div class="form-row">
              <select id="mail-inline-profile-select" class="select">
                ${profilesList
                  .map(
                    (p) =>
                      `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)} (${escapeHtml(p.id)})</option>`
                  )
                  .join("")}
              </select>
              <input
                id="mail-inline-pin-input"
                class="input pin"
                type="password"
                inputmode="numeric"
                maxlength="6"
                spellcheck="false"
                autocorrect="off"
                autocapitalize="off"
                placeholder="PIN"
              />
              <button id="mail-inline-unlock-btn" type="button" class="btn primary">Unlock</button>
              ${
                IS_MAC
                  ? `<button id="mail-inline-touchid-btn" type="button" class="btn">Unlock with Touch ID</button>`
                  : ""
              }
            </div>
          `
          }
        </div>
      </div>
    `;

    const pinInput = container.querySelector(
      "#mail-inline-pin-input"
    ) as HTMLInputElement | null;
    pinInput?.focus();

    const doInlineUnlock = async () => {
      const sel = container.querySelector(
        "#mail-inline-profile-select"
      ) as HTMLSelectElement | null;
      const pid = sel?.value || profilesList[0]?.id || "";
      const pin = pinInput?.value.trim() ?? "";
      if (!pid || !pin) return;
      const res = await sidecarUnlockProfile(pid, pin);
      state.profileStatusMessage = res.ok
        ? ""
        : `error: ${res.error ?? "invalid 6-digit PIN"}`;
      const kb = await sidecarFetchKnowledge();
      if (kb) state.knowledge = kb;
      await refreshMailState();
      await actions.onRefreshState();
    };

    container
      .querySelector("#mail-inline-unlock-btn")
      ?.addEventListener("click", () => {
        void doInlineUnlock();
      });

    pinInput?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        void doInlineUnlock();
      }
    });

    container
      .querySelector("#mail-inline-touchid-btn")
      ?.addEventListener("click", async () => {
        const sel = container.querySelector(
          "#mail-inline-profile-select"
        ) as HTMLSelectElement | null;
        const pid = sel?.value || profilesList[0]?.id || "";
        if (!pid) return;
        const res = await sidecarUnlockProfileKeychain(pid);
        state.profileStatusMessage = res.ok
          ? ""
          : `error: ${res.error ?? "Touch ID unlock unavailable"}`;
        const kb = await sidecarFetchKnowledge();
        if (kb) state.knowledge = kb;
        await refreshMailState();
        await actions.onRefreshState();
      });

    const doInlineCreate = async () => {
      const nameEl = container.querySelector(
        "#mail-inline-new-profile-name"
      ) as HTMLInputElement | null;
      const newPinEl = container.querySelector(
        "#mail-inline-new-profile-pin"
      ) as HTMLInputElement | null;
      const name = nameEl?.value.trim() ?? "";
      const pin = newPinEl?.value.trim() ?? "";
      if (!name || !pin) return;
      const res = await sidecarCreateProfile(name, pin);
      state.profileStatusMessage = res.ok
        ? ""
        : `error: ${res.error ?? "failed to create profile"}`;
      const kb = await sidecarFetchKnowledge();
      if (kb) state.knowledge = kb;
      await refreshMailState();
      await actions.onRefreshState();
    };

    container
      .querySelector("#mail-inline-create-profile-btn")
      ?.addEventListener("click", () => {
        void doInlineCreate();
      });

    container
      .querySelector("#mail-inline-new-profile-pin")
      ?.addEventListener("keydown", (e) => {
        if ((e as KeyboardEvent).key === "Enter") {
          e.preventDefault();
          void doInlineCreate();
        }
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
        ? `<div class="mail-empty">${
            state.mailSearchRows !== null
              ? `No messages matched "${escapeHtml(state.mailSearchQuery)}".`
              : "No messages in Inbox lane yet."
          }</div>`
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
        ? `<div class="mail-empty">No platform notifications in Pings lane yet.</div>`
        : `<div class="mail-cards-stack">
            ${groups
              .map((g) => {
                const plat = String(g.platform ?? "Other");
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
                      <span class="badge soft">${cnt} ping${cnt === 1 ? "" : "s"}</span>
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
        ? `<div class="mail-empty">No order or shipping updates in Orders lane yet.</div>`
        : `<div class="mail-cards-stack">
            ${rows
              .map((card, idx) => {
                const merchant = String(card.merchant ?? "Merchant");
                const orderNo = String(card.order_number ?? "");
                const status = String(card.status ?? "ordered");
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
                            <div><b>Tracking</b> · ${escapeHtml(trackingNo || "Shipment link")}</div>
                            ${
                              trackingUrl
                                ? `<button type="button" class="btn primary" data-open-site-url="${escapeHtml(trackingUrl)}">Track</button>`
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
        ? `<div class="mail-empty">No promotions or discount codes in Promos lane yet.</div>`
        : `<div class="mail-cards-stack">
            ${rows
              .map((comp) => {
                const company = String(comp.company ?? "Company");
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
                      <span class="end muted">${activeCodes.length} active code${activeCodes.length === 1 ? "" : "s"}</span>
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
                                  <button type="button" class="pill" data-copy-promo-code="${escapeHtml(codeStr)}" title="Click to copy code">
                                    <strong>${escapeHtml(codeStr)}</strong>
                                    ${valStr ? `<span>${escapeHtml(valStr)}</span>` : ""}
                                    ${expStr ? `<span class="muted">exp ${escapeHtml(expStr)}</span>` : ""}
                                  </button>
                                `;
                              })
                              .join("")}
                          </div>`
                        : ""
                    }
                    ${
                      expiredCodes.length > 0
                        ? `<div class="muted">Expired: ${expiredCodes
                            .map((c) => escapeHtml(String(c.code ?? "")))
                            .join(", ")}</div>`
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
          <b>Help sort ${onboardingCands.length} email${onboardingCands.length === 1 ? "" : "s"}</b>
          <span class="muted">${escapeHtml(clf.status_text)}</span>
          <span class="end">
            <button id="mail-onboarding-close-btn" type="button" class="btn-text">Close</button>
          </span>
        </div>
        <div class="mail-cards-stack">
          ${onboardingCands
            .map((cand) => {
              const cid = String(cand.id ?? "");
              const cfrom = String(cand.from_name || cand.from_addr || "Unknown");
              const csubj = String(cand.subject || "(no subject)");
              const csnip = String(cand.snippet || "").slice(0, 140);
              const cpred = String(cand.pred_label || "email");
              return `
                <div class="card inset" data-onboarding-card="${escapeHtml(cid)}">
                  <div class="card-h">
                    <b>${escapeHtml(cfrom)}</b>
                    <span class="muted truncate">${escapeHtml(csubj)}</span>
                    <span class="end badge soft">${escapeHtml(cpred)}</span>
                  </div>
                  <div class="muted">${escapeHtml(csnip)}</div>
                  <div class="mail-read-actions">
                    <span class="muted">Is this a promotion?</span>
                    <span class="end">
                      <button type="button" class="btn" data-onboard-msg="${escapeHtml(cid)}" data-onboard-label="promotion">Yes, promo</button>
                      <button type="button" class="btn" data-onboard-msg="${escapeHtml(cid)}" data-onboard-label="email">No, inbox</button>
                      <button type="button" class="btn" data-onboard-msg="${escapeHtml(cid)}" data-onboard-label="ping">Ping</button>
                      <button type="button" class="btn" data-onboard-msg="${escapeHtml(cid)}" data-onboard-label="information">Order</button>
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
    : "All mail";

  container.innerHTML = `
    <div class="mail-view ${isSplitView ? "mail-view-split" : ""}">
      ${renderAcctBarHtml(showOnboardingBtn)}
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
            placeholder="Search mail (press /)"
            value="${escapeHtml(state.mailSearchQuery)}"
          />
        </div>
        ${
          state.mailSearchRows !== null
            ? `<button id="mail-search-clear-btn" type="button" class="btn">Clear</button>`
            : ""
        }
        <span class="mail-toolbar-meta">${escapeHtml(activeScopeLabel)} · ${escapeHtml(lane)} (${rows.length}) · ${escapeHtml(clf.status_text)}</span>
      </div>
      ${onboardingHtml}
      ${bodyHtml}
      ${state.mailAccounts.length === 0 ? renderMailAccountsSectionHtml() : ""}
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
          (el as HTMLElement).getAttribute("data-mail-msg-subject") || "Mail";
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
          ) || "Mail";
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
          (el as HTMLElement).getAttribute("data-mail-msg-subject") || "Mail";
        if (mid) {
          actions.onOpenEmailMessage(mid, subj);
        }
      });
    });
  }

  container.querySelectorAll("[data-open-site-url]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const url = (btn as HTMLElement).getAttribute("data-open-site-url");
      if (url) {
        actions.onOpenSiteUrl(url, "Track Package");
      }
    });
  });

  container.querySelectorAll("[data-copy-promo-code]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const code = (btn as HTMLElement).getAttribute("data-copy-promo-code");
      if (code && navigator.clipboard) {
        void navigator.clipboard.writeText(code);
        (btn as HTMLElement).innerHTML = "<strong>Copied</strong>";
      }
    });
  });

  if (state.mailAccounts.length === 0) {
    bindMailAccountsEvents(container, actions.onRefreshState);
  }
}

function renderInboxRowsHtml(rows: Array<Record<string, unknown>>): string {
  const showAccountBadge =
    state.mailActiveAccountId === null && state.mailAccounts.length > 0;
  return rows
    .map((r, idx) => {
      const id = String(r.id ?? r.latest_message_id ?? "");
      const fromStr = String(
        r.from_name || r.from_addr || r.merchant || r.company || "Unknown"
      );
      const acctEmail = String(r.account_email ?? "");
      const subj = String(
        r.subject || r.order_number || r.domain || "(no subject)"
      );
      const snip = String(r.snippet || r.status || "");
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
          data-mail-msg-subject="${escapeHtml(subj)}"
        >
          <div class="h">
            ${unseen ? `<span class="dot accent" title="Unread"></span>` : ""}
            <b>${escapeHtml(fromStr)}</b>
            ${showAccountBadge && acctEmail ? `<span class="badge soft" title="Email account: ${escapeHtml(acctEmail)}">${escapeHtml(acctEmail.split("@")[0] || acctEmail)}</span>` : ""}
            ${needsReply ? `<span class="badge">Reply</span>` : ""}
            ${dueDate ? `<span class="badge soft">Due ${escapeHtml(dueDate.slice(5))}</span>` : ""}
            <span class="time">${escapeHtml(timeLabel)}</span>
          </div>
          <div class="s">${escapeHtml(subj)}</div>
          <div class="p">${escapeHtml(snip)}</div>
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
  const fromDisp = fromName ? `${fromName} <${fromAddr}>` : fromAddr || "Loading...";
  const toList = ((msg.to ?? []) as Array<Record<string, string>>)
    .map((x) => x.email || x.name)
    .join(", ");
  const ccList = ((msg.cc ?? []) as Array<Record<string, string>>)
    .map((x) => x.email || x.name)
    .join(", ");
  const subj = String(msg.subject || tab.title || "(no subject)");
  const label = String(msg.label || "email");
  const ts = Number(msg.date ?? 0);
  const whenLabel = ts > 0 ? formatRelativeTime(String(Math.floor(ts))) : "";
  const allowRemote = Boolean(msg.allow_remote_images);
  const attachments = (msg.attachments ?? []) as Array<Record<string, unknown>>;

  return `
    <div class="section" id="email-tab-header-${escapeHtml(tab.id)}">
      <h2 class="mail-subject">${escapeHtml(subj)}</h2>
      <div class="mail-from">
        <span class="mail-avatar">${escapeHtml(getInitials(fromName || fromAddr))}</span>
        <div class="mail-from-meta">
          <b>${escapeHtml(fromDisp)}</b>
          ${toList || ccList ? `<small>${toList ? `To ${escapeHtml(toList)}` : ""}${toList && ccList ? " · " : ""}${ccList ? `Cc ${escapeHtml(ccList)}` : ""}</small>` : ""}
        </div>
        ${whenLabel ? `<span class="when">${escapeHtml(whenLabel)}</span>` : ""}
      </div>
      <div class="mail-read-actions">
        <button type="button" class="btn primary" data-email-reply="${escapeHtml(mid)}">${icon("reply", "ico-sm")}<span>Reply</span></button>
        <button type="button" class="btn" data-email-reply-all="${escapeHtml(mid)}">Reply all</button>
        <button type="button" class="btn" data-email-forward="${escapeHtml(mid)}">Forward</button>
        <button type="button" class="btn" data-email-hide="${escapeHtml(mid)}">${icon("archive", "ico-sm")}<span>Archive</span></button>
        ${
          includeOpenTabBtn
            ? `<button type="button" class="btn-text" data-mail-open-tab="${escapeHtml(mid)}" data-mail-open-subject="${escapeHtml(subj)}">${icon("external", "ico-sm")}<span>Open tab</span></button>`
            : ""
        }
        <div class="end">
          <div class="seg" role="group" aria-label="Move message to lane">
            <button type="button" data-email-move="${escapeHtml(mid)}" data-target-label="email" aria-pressed="${label === "email" ? "true" : "false"}">Inbox</button>
            <button type="button" data-email-move="${escapeHtml(mid)}" data-target-label="ping" aria-pressed="${label === "ping" ? "true" : "false"}">Pings</button>
            <button type="button" data-email-move="${escapeHtml(mid)}" data-target-label="information" aria-pressed="${label === "information" ? "true" : "false"}">Orders</button>
            <button type="button" data-email-move="${escapeHtml(mid)}" data-target-label="promotion" aria-pressed="${label === "promotion" ? "true" : "false"}">Promos</button>
          </div>
          ${
            !allowRemote && fromAddr
              ? `<button type="button" class="btn" data-email-allow-remote="${escapeHtml(fromAddr)}">Load images</button>`
              : ""
          }
        </div>
      </div>
      ${
        attachments.length > 0
          ? `<div class="mail-atts-row">
              <span class="muted">Attachments (${attachments.length}):</span>
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
                        <span>${isPrev ? "Hide" : escapeHtml(fname)} (${sizeKb} KB)</span>
                      </button>
                      <button type="button" class="btn-text" data-email-save-att="${escapeHtml(mid)}" data-part-id="${escapeHtml(partId)}">Save</button>
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
        <div class="muted">Loading email context...</div>
      </div>
    `;
  }

  const mid = String(msg.id ?? "");
  const senderCard = msg.sender_card as Record<string, unknown> | null;
  const extracts = (msg.extracts ?? {}) as Record<string, string>;
  const fromDisp = String(msg.from_name || msg.from_addr || "Sender");
  const subj = String(msg.subject || "(no subject)");
  const extractPairs = Object.entries(extracts).filter(
    ([, v]) => v !== undefined && v !== null && String(v).trim() !== ""
  );

  return `
    <div class="section" id="email-focused-rail-cards">
      <div class="card">
        <div class="card-h">
          <b>${escapeHtml(String(senderCard?.name ?? fromDisp))}</b>
          <span class="end badge soft">${escapeHtml(String(senderCard?.type ?? "contact"))}</span>
        </div>
        <div class="muted">${escapeHtml(String(senderCard?.summary ?? msg.from_addr ?? ""))}</div>
      </div>
      <div class="card">
        <div class="card-h">
          <b>Extracted items</b>
          <span class="end muted">${extractPairs.length}</span>
        </div>
        ${
          extractPairs.length === 0
            ? `<div class="muted">No structured codes, dates, or order numbers extracted.</div>`
            : extractPairs
                .map(
                  ([k, v]) =>
                    `<div class="rail-kv"><span>${escapeHtml(k)}</span><span>${escapeHtml(String(v))}</span></div>`
                )
                .join("")
        }
      </div>
      <div class="mail-chip-row">
        <button type="button" class="chip" data-email-rail-save-brain="${escapeHtml(mid)}" data-email-rail-subj="${escapeHtml(subj)}">
          ${icon("brain", "ico-sm")}
          <span>Save to Brain</span>
        </button>
        <button type="button" class="chip" data-email-rail-ask="ask about this email: ${escapeHtml(subj)}">
          ${icon("chat", "ico-sm")}
          <span>Ask about email</span>
        </button>
        <button type="button" class="chip" data-email-rail-ask="summarize this email">Summarize</button>
        <button type="button" class="chip" data-email-rail-ask="draft a reply to this email">Draft reply</button>
        <button type="button" class="chip" data-email-rail-ask="extract dates and action items from this email">Extract dates</button>
      </div>
    </div>
  `;
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
  });

  container.innerHTML = `
    <div class="compose-view" id="compose-view-${escapeHtml(tab.id)}">
      <div class="card-h">
        <b>Compose message</b>
        <span class="muted">Plain text · requires confirmation to send</span>
        <span class="end">
          <button id="compose-draft-btn" type="button" class="btn">${icon("spark", "ico-sm")}<span>Draft with Gemma</span></button>
          <button id="compose-prepare-send-btn" type="button" class="btn primary">${icon("send", "ico-sm")}<span>Send (${escapeHtml(MOD_LABEL)}+Enter)</span></button>
        </span>
      </div>

      ${
        draft.status_msg
          ? renderStatusBannerHtml(draft.status_msg)
          : ""
      }

      ${
        draft.confirm_token && draft.confirm_line
          ? `<div class="draft" id="compose-confirm-bar">
              <div class="gate">Send gate · sends only after you press Confirm</div>
              <div>${escapeHtml(draft.confirm_line).replace(/\[new\]/g, '<span class="badge soft">New</span>')}</div>
              <div class="acts">
                <button id="compose-confirm-send-btn" type="button" class="btn primary">Confirm send</button>
                <button id="compose-cancel-send-btn" type="button" class="btn">Cancel</button>
              </div>
            </div>`
          : ""
      }

      ${
        draft.queued_outbox_id
          ? `<div class="banner" id="compose-undo-bar">
              <span>Queued for delivery (10s undo window)...</span>
              <button id="compose-undo-send-btn" type="button" class="btn">Undo</button>
            </div>`
          : ""
      }

      <div class="card">
        <div class="form-row">
          <label class="muted">From</label>
          <select id="compose-from-select" class="select">
            ${accounts
              .map(
                (a) =>
                  `<option value="${escapeHtml(a.id)}" ${a.id === draft.account_id ? "selected" : ""}>${escapeHtml(a.label)} &lt;${escapeHtml(a.email)}&gt;</option>`
              )
              .join("")}
          </select>
        </div>
        <div class="form-row">
          <input id="compose-to-input" class="input" type="text" placeholder="To: alice@example.com" value="${escapeHtml(draft.to)}" />
          <input id="compose-cc-input" class="input" type="text" placeholder="Cc" value="${escapeHtml(draft.cc)}" />
          <input id="compose-bcc-input" class="input" type="text" placeholder="Bcc" value="${escapeHtml(draft.bcc)}" />
        </div>
        <div class="form-row">
          <input id="compose-subject-input" class="input" type="text" placeholder="Subject" value="${escapeHtml(draft.subject)}" />
        </div>
        <textarea
          id="compose-body-textarea"
          class="textarea compose-textarea"
          rows="16"
          placeholder="Write plain-text message..."
        >${escapeHtml(draft.body)}</textarea>
      </div>
    </div>
  `;

  const syncFields = () => {
    draft.account_id =
      (container.querySelector("#compose-from-select") as HTMLSelectElement | null)
        ?.value ?? draft.account_id;
    draft.to =
      (container.querySelector("#compose-to-input") as HTMLInputElement | null)
        ?.value ?? "";
    draft.cc =
      (container.querySelector("#compose-cc-input") as HTMLInputElement | null)
        ?.value ?? "";
    draft.bcc =
      (container.querySelector("#compose-bcc-input") as HTMLInputElement | null)
        ?.value ?? "";
    draft.subject =
      (container.querySelector("#compose-subject-input") as HTMLInputElement | null)
        ?.value ?? "";
    draft.body =
      (
        container.querySelector(
          "#compose-body-textarea"
        ) as HTMLTextAreaElement | null
      )?.value ?? "";
  };

  container
    .querySelectorAll("input, textarea, select")
    .forEach((el) => el.addEventListener("input", syncFields));

  const bodyTextarea = container.querySelector(
    "#compose-body-textarea"
  ) as HTMLTextAreaElement | null;
  if (bodyTextarea && draft.reply_to_message_id && !draft.confirm_token) {
    bodyTextarea.focus();
    bodyTextarea.setSelectionRange(0, 0);
    bodyTextarea.scrollTop = 0;
  }

  container
    .querySelector("#compose-draft-btn")
    ?.addEventListener("click", async () => {
      syncFields();
      draft.status_msg = "Drafting reply with Gemma...";
      onChanged();
      const res = await sidecarDraftMailReply({
        message_id: draft.reply_to_message_id,
        to: draft.to,
        subject: draft.subject,
        instructions: draft.body,
      });
      if (res.ok) {
        if (res.to && !draft.to) draft.to = res.to;
        if (res.subject && !draft.subject) draft.subject = res.subject;
        if (res.body) draft.body = res.body;
        draft.status_msg =
          "Draft ready. Review and press Send to prepare confirmation.";
      } else {
        draft.status_msg = `Draft error: ${res.error ?? "failed"}`;
      }
      onChanged();
    });

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
    });
    if (res.ok && res.confirm_token && res.outbox_id) {
      draft.confirm_outbox_id = res.outbox_id;
      draft.confirm_token = res.confirm_token;
      draft.confirm_line = res.confirm_line;
      draft.status_msg = "";
    } else {
      draft.status_msg = `Send prepare error: ${res.error ?? "failed"}`;
    }
    onChanged();
  };

  container
    .querySelector("#compose-prepare-send-btn")
    ?.addEventListener("click", () => {
      void handlePrepare();
    });

  container
    .querySelector("#compose-body-textarea")
    ?.addEventListener("keydown", (e) => {
      const ke = e as KeyboardEvent;
      if ((ke.ctrlKey || ke.metaKey) && ke.key === "Enter") {
        ke.preventDefault();
        void handlePrepare();
      }
    });

  container
    .querySelector("#compose-confirm-send-btn")
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
        draft.status_msg = "Sending in 10s (press Undo to cancel)...";
      } else {
        draft.status_msg = `Send rejected: ${res.error ?? "failed"}`;
      }
      onChanged();
    });

  container
    .querySelector("#compose-cancel-send-btn")
    ?.addEventListener("click", () => {
      draft.confirm_outbox_id = undefined;
      draft.confirm_token = undefined;
      draft.confirm_line = undefined;
      draft.status_msg = "Send cancelled.";
      onChanged();
    });

  container
    .querySelector("#compose-undo-send-btn")
    ?.addEventListener("click", async () => {
      if (!draft.queued_outbox_id) return;
      const res = await sidecarUndoMailSend(draft.queued_outbox_id);
      if (res.ok) {
        draft.queued_outbox_id = undefined;
        draft.status_msg = "Send undone. Message returned to draft.";
      } else {
        draft.status_msg = `Undo failed: ${res.error ?? "already sent"}`;
      }
      onChanged();
    });
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
