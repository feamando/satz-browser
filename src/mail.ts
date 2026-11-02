import {
  apiEnsureMailConversation,
  sidecarAddMailAccount,
  sidecarGetMailAccounts,
  sidecarGetMailLane,
  sidecarRemoveMailAccount,
  sidecarSyncMail,
  sidecarTestMailAccount,
} from "./api";
import { escapeHtml, formatRelativeTime, state } from "./state";
import type { MailPreset } from "./types";

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
  onRefreshState: () => Promise<void>;
}

export async function refreshMailState(): Promise<void> {
  const acctRes = await sidecarGetMailAccounts();
  state.mailAccounts = acctRes.accounts ?? [];
  state.mailPresets =
    acctRes.presets && acctRes.presets.length > 0
      ? acctRes.presets
      : DEFAULT_PRESETS;

  if (acctRes.unlocked && state.mailAccounts.length > 0) {
    await apiEnsureMailConversation();
    const laneRes = await sidecarGetMailLane(state.mailActiveLane, 0);
    state.mailCounts = laneRes.counts ?? {
      inbox_unread: 0,
      pings: 0,
      orders: 0,
      promos: 0,
    };
    state.mailLaneRows = laneRes.rows ?? [];
    state.mailLaneGroups = laneRes.groups ?? [];
    if (state.mailActiveLane === "inbox") {
      state.mailInboxRows = laneRes.rows ?? [];
    }
  } else {
    state.mailLaneRows = [];
    state.mailLaneGroups = [];
    state.mailCounts = { inbox_unread: 0, pings: 0, orders: 0, promos: 0 };
  }
}

export function renderMailAccountsSectionHtml(): string {
  const unlocked = Boolean(state.knowledge.profile?.unlocked);
  const presets =
    state.mailPresets.length > 0 ? state.mailPresets : DEFAULT_PRESETS;
  const accounts = state.mailAccounts ?? [];

  if (!unlocked) {
    return `
      <div class="kb-section">
        <div class="kb-section-title">mail accounts (vault locked)</div>
        <div class="muted">unlock your profile with its 6-digit PIN above to view, add, or sync mail accounts.</div>
      </div>
    `;
  }

  return `
    <div class="kb-section" id="mail-accounts-panel">
      <div class="kb-section-title">
        <span>mail accounts (${accounts.length})</span>
        <button id="mail-sync-all-btn">[sync now]</button>
      </div>
      ${
        state.mailStatusMessage
          ? `<div class="kb-status-banner">${escapeHtml(state.mailStatusMessage)}</div>`
          : ""
      }
      ${
        accounts.length === 0
          ? `<div class="muted">no mail accounts configured yet. add an account below (Gmail/Outlook require an app password).</div>`
          : `
          <table class="kb-table">
            <thead>
              <tr>
                <th>label / email</th>
                <th>incoming</th>
                <th>outgoing</th>
                <th>vault prefix</th>
                <th>messages</th>
                <th>status</th>
                <th>actions</th>
              </tr>
            </thead>
            <tbody>
              ${accounts
                .map(
                  (a) => `
                <tr>
                  <td>${escapeHtml(a.label)} · ${escapeHtml(a.email)}</td>
                  <td>${escapeHtml(a.protocol.toUpperCase())} ${escapeHtml(a.in_host)}:${a.in_port} (${escapeHtml(a.in_security)})</td>
                  <td>SMTP ${escapeHtml(a.smtp_host)}:${a.smtp_port} (${escapeHtml(a.smtp_security)})</td>
                  <td class="muted">${escapeHtml(a.vault_prefix)}</td>
                  <td>${a.message_count ?? 0}</td>
                  <td>${
                    a.auth_failed
                      ? `<span class="citation-flagged">[auth failed]</span>`
                      : a.last_error
                        ? `<span class="muted">${escapeHtml(a.last_error.slice(0, 48))}</span>`
                        : a.last_sync_at > 0
                          ? `synced ${escapeHtml(formatRelativeTime(String(Math.floor(a.last_sync_at))))}`
                          : "ready"
                  }</td>
                  <td>
                    <button data-mail-test-acct="${escapeHtml(a.id)}">[test]</button>
                    <button data-mail-sync-acct="${escapeHtml(a.id)}">[sync]</button>
                    <button data-mail-remove-acct="${escapeHtml(a.id)}">[remove]</button>
                  </td>
                </tr>
              `
                )
                .join("")}
            </tbody>
          </table>
        `
      }

      <div class="kb-card">
        <div class="kb-card-header">add mail account (credentials stored in encrypted vault.enc)</div>
        <div class="kb-form-row">
          <select id="mail-preset-select" class="kb-input">
            ${presets
              .map(
                (p) =>
                  `<option value="${escapeHtml(p.id)}">${escapeHtml(p.label)} (${p.protocol.toUpperCase()})</option>`
              )
              .join("")}
          </select>
          <input id="mail-acct-label" class="kb-input" type="text" placeholder="label (e.g. Gmail)" value="Gmail" />
          <input id="mail-acct-email" class="kb-input" type="text" placeholder="email (you@gmail.com)" />
          <input id="mail-acct-password" class="kb-input" type="password" placeholder="app password" />
        </div>
        <div class="kb-form-row">
          <select id="mail-acct-protocol" class="kb-input">
            <option value="imap">IMAP</option>
            <option value="pop3">POP3 (leave on server)</option>
          </select>
          <input id="mail-acct-in-host" class="kb-input" type="text" placeholder="incoming host" value="imap.gmail.com" />
          <input id="mail-acct-in-port" class="kb-input" type="number" placeholder="993" value="993" />
          <select id="mail-acct-in-sec" class="kb-input">
            <option value="ssl">SSL</option>
            <option value="starttls">STARTTLS</option>
          </select>
        </div>
        <div class="kb-form-row">
          <input id="mail-acct-smtp-host" class="kb-input" type="text" placeholder="smtp host" value="smtp.gmail.com" />
          <input id="mail-acct-smtp-port" class="kb-input" type="number" placeholder="587" value="587" />
          <select id="mail-acct-smtp-sec" class="kb-input">
            <option value="starttls">STARTTLS</option>
            <option value="ssl">SSL</option>
          </select>
          <button id="mail-form-test-btn">[test]</button>
          <button id="mail-form-add-btn">[+ add account]</button>
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
    if (labelInput) labelInput.value = p.label;
    if (protocolSelect) protocolSelect.value = p.protocol;
    if (inHostInput) inHostInput.value = p.in_host;
    if (inPortInput) inPortInput.value = String(p.in_port);
    if (inSecSelect) inSecSelect.value = p.in_security;
    if (smtpHostInput) smtpHostInput.value = p.smtp_host;
    if (smtpPortInput) smtpPortInput.value = String(p.smtp_port);
    if (smtpSecSelect) smtpSecSelect.value = p.smtp_security;
  });

  const collectFormPayload = (): Record<string, unknown> => ({
    preset: presetSelect?.value ?? "gmail",
    label: labelInput?.value.trim() ?? "Mail",
    email: emailInput?.value.trim() ?? "",
    password: passwordInput?.value ?? "",
    protocol: protocolSelect?.value ?? "imap",
    in_host: inHostInput?.value.trim() ?? "",
    in_port: Number(inPortInput?.value ?? 993),
    in_security: inSecSelect?.value ?? "ssl",
    smtp_host: smtpHostInput?.value.trim() ?? "",
    smtp_port: Number(smtpPortInput?.value ?? 587),
    smtp_security: smtpSecSelect?.value ?? "starttls",
  });

  container
    .querySelector("#mail-form-test-btn")
    ?.addEventListener("click", async () => {
      state.mailStatusMessage = "testing incoming & outgoing (SMTP EHLO + AUTH)...";
      await onChanged();
      const res = await sidecarTestMailAccount(collectFormPayload());
      if (res.ok) {
        state.mailStatusMessage = "test passed: incoming & outgoing login ok.";
      } else {
        state.mailStatusMessage = `test failed: ${res.error ?? "unknown error"}`;
      }
      await onChanged();
    });

  container
    .querySelector("#mail-form-add-btn")
    ?.addEventListener("click", async () => {
      const payload = collectFormPayload();
      state.mailStatusMessage = "adding account & starting background sync...";
      await onChanged();
      const res = await sidecarAddMailAccount(payload);
      if (res.ok) {
        await apiEnsureMailConversation();
        state.mailStatusMessage = `added account (${res.vault_prefix ?? "vault"}). syncing last 30 days...`;
        await refreshMailState();
      } else {
        state.mailStatusMessage = `error adding account: ${res.error ?? "failed"}`;
      }
      await onChanged();
    });

  container
    .querySelector("#mail-sync-all-btn")
    ?.addEventListener("click", async () => {
      state.mailStatusMessage = "syncing all mail accounts...";
      await onChanged();
      const res = await sidecarSyncMail();
      await refreshMailState();
      state.mailStatusMessage = res.ok
        ? "sync complete."
        : `sync error: ${res.error ?? "failed"}`;
      await onChanged();
    });

  container.querySelectorAll("[data-mail-test-acct]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = (btn as HTMLElement).getAttribute("data-mail-test-acct");
      if (!id) return;
      state.mailStatusMessage = `testing account ${id}...`;
      await onChanged();
      const res = await sidecarTestMailAccount({ account_id: id });
      state.mailStatusMessage = res.ok
        ? `account ${id}: incoming & SMTP test ok.`
        : `account ${id} test failed: ${res.error ?? "error"}`;
      await onChanged();
    });
  });

  container.querySelectorAll("[data-mail-sync-acct]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = (btn as HTMLElement).getAttribute("data-mail-sync-acct");
      if (!id) return;
      state.mailStatusMessage = `syncing account ${id}...`;
      await onChanged();
      const res = await sidecarSyncMail(id);
      await refreshMailState();
      state.mailStatusMessage = res.ok
        ? `synced ${res.synced_count ?? 0} new messages.`
        : `sync failed: ${res.error ?? "error"}`;
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
        ? `removed account ${id}.`
        : `remove failed: ${res.error ?? "error"}`;
      await onChanged();
    });
  });
}

export function renderMailLaneView(
  container: HTMLElement,
  actions: MailViewActions
): void {
  const lane = state.mailActiveLane;
  const rows = state.mailLaneRows;
  const unlocked = Boolean(state.knowledge.profile?.unlocked);

  if (!unlocked) {
    container.innerHTML = `
      <div class="knowledge-view">
        <div class="kb-header">
          <span>mail · locked</span>
        </div>
        <div class="muted">unlock your profile in [knowledge · profile] to access mail lanes.</div>
      </div>
    `;
    return;
  }

  const rowsHtml =
    rows.length === 0
      ? `<div class="muted">no messages in ${escapeHtml(lane)} lane yet.</div>`
      : rows
          .map((r, idx) => {
            const id = String(r.id ?? r.latest_message_id ?? "");
            const fromStr = String(
              r.from_name || r.from_addr || r.merchant || r.company || "unknown"
            );
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
                class="mail-lane-row ${unseen ? "mail-unseen" : ""} ${isSelected ? "selected" : ""}"
                data-mail-msg-id="${escapeHtml(id)}"
                data-mail-msg-subject="${escapeHtml(subj)}"
              >
                <span class="mail-col-from truncate">${unseen ? "* " : "  "}${escapeHtml(fromStr)}</span>
                <span class="mail-col-subject truncate">
                  ${needsReply ? `<span class="source-cut-badge">reply</span> ` : ""}
                  ${dueDate ? `<span class="source-cut-badge">due ${escapeHtml(dueDate.slice(5))}</span> ` : ""}
                  ${escapeHtml(subj)}
                  <span class="muted"> · ${escapeHtml(snip)}</span>
                </span>
                <span class="mail-col-time muted">${escapeHtml(timeLabel)}</span>
              </div>
            `;
          })
          .join("");

  container.innerHTML = `
    <div class="knowledge-view">
      <div class="kb-header">
        <span>mail · ${escapeHtml(lane)} (${rows.length})</span>
        <div>
          <button id="mail-lane-refresh-btn">[sync &amp; refresh]</button>
        </div>
      </div>
      <div class="mail-lane-list">
        ${rowsHtml}
      </div>
      ${state.mailAccounts.length === 0 ? renderMailAccountsSectionHtml() : ""}
    </div>
  `;

  container
    .querySelector("#mail-lane-refresh-btn")
    ?.addEventListener("click", async () => {
      await sidecarSyncMail();
      await refreshMailState();
      await actions.onRefreshState();
    });

  container.querySelectorAll("[data-mail-msg-id]").forEach((el) => {
    el.addEventListener("click", () => {
      const mid = (el as HTMLElement).getAttribute("data-mail-msg-id");
      const subj =
        (el as HTMLElement).getAttribute("data-mail-msg-subject") || "mail";
      if (mid) {
        actions.onOpenEmailMessage(mid, subj);
      }
    });
  });

  if (state.mailAccounts.length === 0) {
    bindMailAccountsEvents(container, actions.onRefreshState);
  }
}
