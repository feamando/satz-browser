import {
  apiEnsureMailConversation,
  sidecarAddMailAccount,
  sidecarConfirmMailSend,
  sidecarDraftMailReply,
  sidecarGetMailAccounts,
  sidecarGetMailLane,
  sidecarGetMailMessage,
  sidecarHideMailMessage,
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
import { escapeHtml, formatRelativeTime, MOD_LABEL, state } from "./state";
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
  const rows = state.mailSearchRows ?? state.mailLaneRows;
  const groups = state.mailLaneGroups ?? [];
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

  let bodyHtml = "";

  if (state.mailSearchRows !== null) {
    bodyHtml =
      rows.length === 0
        ? `<div class="muted">no messages matched "${escapeHtml(state.mailSearchQuery)}".</div>`
        : renderInboxRowsHtml(rows);
  } else if (lane === "inbox") {
    bodyHtml =
      rows.length === 0
        ? `<div class="muted">no messages in inbox lane yet.</div>`
        : renderInboxRowsHtml(rows);
  } else if (lane === "pings") {
    bodyHtml =
      groups.length === 0
        ? `<div class="muted">no platform notifications in pings lane yet.</div>`
        : groups
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
                <div class="kb-card">
                  <div class="kb-card-header">
                    <span>${escapeHtml(plat)} · ${cnt} ping${cnt === 1 ? "" : "s"}</span>
                    <span class="muted">${authorSummary}</span>
                  </div>
                  <div class="mail-lane-list">
                    ${renderInboxRowsHtml(items)}
                  </div>
                </div>
              `;
            })
            .join("");
  } else if (lane === "orders") {
    bodyHtml =
      rows.length === 0
        ? `<div class="muted">no order or shipping updates in orders lane yet.</div>`
        : rows
            .map((card, idx) => {
              const merchant = String(card.merchant ?? "Merchant");
              const orderNo = String(card.order_number ?? "");
              const status = String(card.status ?? "ordered");
              const trackingNo = String(card.tracking_number ?? "");
              const trackingUrl = String(card.tracking_url ?? "");
              const total = String(card.total ?? "");
              const latestId = String(card.latest_message_id ?? "");
              const emails = (card.emails ?? []) as Array<Record<string, unknown>>;
              const isSelected = idx === state.mailSelectedRowIdx;
              return `
                <div
                  class="kb-card ${isSelected ? "selected" : ""}"
                  data-mail-msg-id="${escapeHtml(latestId)}"
                  data-mail-msg-subject="${escapeHtml(`${merchant} ${orderNo}`)}"
                >
                  <div class="kb-card-header">
                    <span>${escapeHtml(merchant)}${orderNo ? ` · #${escapeHtml(orderNo)}` : ""}</span>
                    <span>
                      <span class="source-cut-badge">${escapeHtml(status)}</span>
                      ${total ? ` <span class="muted">${escapeHtml(total)}</span>` : ""}
                    </span>
                  </div>
                  ${
                    trackingNo || trackingUrl
                      ? `<div class="rail-row">
                          <span class="muted">tracking: ${escapeHtml(trackingNo || "link")}</span>
                          ${
                            trackingUrl
                              ? `<button data-open-site-url="${escapeHtml(trackingUrl)}">[track package]</button>`
                              : ""
                          }
                        </div>`
                      : ""
                  }
                  <div class="mail-lane-list">
                    ${emails
                      .map((em) => {
                        const eid = String(em.id ?? "");
                        const esubj = String(em.subject ?? "");
                        const ets = Number(em.date ?? 0);
                        return `
                          <div
                            class="mail-lane-row"
                            data-mail-msg-id="${escapeHtml(eid)}"
                            data-mail-msg-subject="${escapeHtml(esubj)}"
                          >
                            <span class="mail-col-from muted">${escapeHtml(String(em.status || status))}</span>
                            <span class="mail-col-subject truncate">${escapeHtml(esubj)}</span>
                            <span class="mail-col-time muted">${ets > 0 ? escapeHtml(formatRelativeTime(String(Math.floor(ets)))) : ""}</span>
                          </div>
                        `;
                      })
                      .join("")}
                  </div>
                </div>
              `;
            })
            .join("");
  } else if (lane === "promos") {
    bodyHtml =
      rows.length === 0
        ? `<div class="muted">no promotions or discount codes in promos lane yet.</div>`
        : rows
            .map((comp) => {
              const company = String(comp.company ?? "Company");
              const domain = String(comp.domain ?? "");
              const activeCodes = (comp.active_codes ?? []) as Array<Record<string, unknown>>;
              const expiredCodes = (comp.expired_codes ?? []) as Array<Record<string, unknown>>;
              const emails = (comp.emails ?? []) as Array<Record<string, unknown>>;
              return `
                <div class="kb-card">
                  <div class="kb-card-header">
                    <span>${escapeHtml(company)} <span class="muted">(${escapeHtml(domain)})</span></span>
                    <span class="muted">${activeCodes.length} active code${activeCodes.length === 1 ? "" : "s"}</span>
                  </div>
                  ${
                    activeCodes.length > 0
                      ? `<div class="kb-form-row">
                          ${activeCodes
                            .map((c) => {
                              const codeStr = String(c.code ?? "");
                              const valStr = String(c.discount_value ?? "");
                              const expStr = String(c.expiry ?? "");
                              return `
                                <span class="rail-row">
                                  <span><strong>${escapeHtml(codeStr)}</strong>${valStr ? ` (${escapeHtml(valStr)})` : ""}${expStr ? ` · exp ${escapeHtml(expStr)}` : ""}</span>
                                  <button data-copy-promo-code="${escapeHtml(codeStr)}">[copy]</button>
                                </span>
                              `;
                            })
                            .join("")}
                        </div>`
                      : ""
                  }
                  ${
                    expiredCodes.length > 0
                      ? `<div class="muted">expired: ${expiredCodes
                          .map((c) => escapeHtml(String(c.code ?? "")))
                          .join(", ")}</div>`
                      : ""
                  }
                  <div class="mail-lane-list">
                    ${emails
                      .map((em) => {
                        const eid = String(em.id ?? "");
                        const esubj = String(em.subject ?? "");
                        const ets = Number(em.date ?? 0);
                        return `
                          <div
                            class="mail-lane-row"
                            data-mail-msg-id="${escapeHtml(eid)}"
                            data-mail-msg-subject="${escapeHtml(esubj)}"
                          >
                            <span class="mail-col-from muted">${escapeHtml(company)}</span>
                            <span class="mail-col-subject truncate">${escapeHtml(esubj)}</span>
                            <span class="mail-col-time muted">${ets > 0 ? escapeHtml(formatRelativeTime(String(Math.floor(ets)))) : ""}</span>
                          </div>
                        `;
                      })
                      .join("")}
                  </div>
                </div>
              `;
            })
            .join("");
  }

  container.innerHTML = `
    <div class="knowledge-view">
      <div class="kb-header">
        <span>mail · ${escapeHtml(lane)} (${rows.length}) · keys: j/k move, Enter open, r reply, c compose, e hide, 1-4 move, / search</span>
        <div>
          <input
            id="mail-search-input"
            class="kb-input"
            type="text"
            placeholder="search mail [/]..."
            value="${escapeHtml(state.mailSearchQuery)}"
          />
          ${
            state.mailSearchRows !== null
              ? `<button id="mail-search-clear-btn">[clear]</button>`
              : ""
          }
          <button id="mail-compose-btn">[compose (c)]</button>
          <button id="mail-lane-refresh-btn">[sync &amp; refresh]</button>
        </div>
      </div>
      <div class="mail-lane-list">
        ${bodyHtml}
      </div>
      ${state.mailAccounts.length === 0 ? renderMailAccountsSectionHtml() : ""}
    </div>
  `;

  const searchInput = container.querySelector(
    "#mail-search-input"
  ) as HTMLInputElement | null;
  searchInput?.addEventListener("keydown", async (e) => {
    if (e.key === "Enter") {
      const q = searchInput.value.trim();
      state.mailSearchQuery = q;
      if (!q) {
        state.mailSearchRows = null;
      } else {
        const res = await sidecarSearchMail(q);
        state.mailSearchRows = res.rows ?? [];
      }
      await actions.onRefreshState();
    } else if (e.key === "Escape") {
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

  container.querySelectorAll("[data-mail-msg-id]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      const mid = (el as HTMLElement).getAttribute("data-mail-msg-id");
      const subj =
        (el as HTMLElement).getAttribute("data-mail-msg-subject") || "mail";
      if (mid) {
        actions.onOpenEmailMessage(mid, subj);
      }
    });
  });

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
        (btn as HTMLElement).textContent = "[copied]";
      }
    });
  });

  if (state.mailAccounts.length === 0) {
    bindMailAccountsEvents(container, actions.onRefreshState);
  }
}

function renderInboxRowsHtml(rows: Array<Record<string, unknown>>): string {
  return rows
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
}

export function renderEmailTabHeaderHtml(
  tab: BrowserTab,
  detailObj: Record<string, unknown> | undefined
): string {
  const msg = (detailObj?.message ?? detailObj ?? {}) as Record<string, unknown>;
  const mid = String(
    msg.id || tab.url.replace("satzmail://message/", "").split("/")[0]
  );
  const fromName = String(msg.from_name || "");
  const fromAddr = String(msg.from_addr || "");
  const fromDisp = fromName ? `${fromName} <${fromAddr}>` : fromAddr || "loading...";
  const toList = ((msg.to ?? []) as Array<Record<string, string>>)
    .map((x) => x.email || x.name)
    .join(", ");
  const ccList = ((msg.cc ?? []) as Array<Record<string, string>>)
    .map((x) => x.email || x.name)
    .join(", ");
  const subj = String(msg.subject || tab.title || "(no subject)");
  const label = String(msg.label || "email");
  const allowRemote = Boolean(msg.allow_remote_images);
  const attachments = ((msg.attachments ?? []) as Array<Record<string, unknown>>);

  return `
    <div class="kb-card" id="email-tab-header-${escapeHtml(tab.id)}">
      <div class="kb-card-header">
        <span><strong>${escapeHtml(subj)}</strong> · <span class="source-cut-badge">${escapeHtml(label)}</span></span>
        <div>
          <button data-email-reply="${escapeHtml(mid)}">[reply (r)]</button>
          <button data-email-reply-all="${escapeHtml(mid)}">[reply all]</button>
          <button data-email-forward="${escapeHtml(mid)}">[forward]</button>
          <button data-email-hide="${escapeHtml(mid)}">[hide (e)]</button>
          <button id="toggle-agent-rail-btn" class="${state.agentRailOpen ? "active" : ""}">
            [agent rail ${MOD_LABEL}+j]
          </button>
        </div>
      </div>
      <div class="rail-row">
        <span>from: ${escapeHtml(fromDisp)}${toList ? ` · to: ${escapeHtml(toList)}` : ""}${ccList ? ` · cc: ${escapeHtml(ccList)}` : ""}</span>
        <div>
          <span class="muted">move to:</span>
          <button data-email-move="${escapeHtml(mid)}" data-target-label="email" class="${label === "email" ? "active" : ""}">[1 inbox]</button>
          <button data-email-move="${escapeHtml(mid)}" data-target-label="ping" class="${label === "ping" ? "active" : ""}">[2 pings]</button>
          <button data-email-move="${escapeHtml(mid)}" data-target-label="information" class="${label === "information" ? "active" : ""}">[3 orders]</button>
          <button data-email-move="${escapeHtml(mid)}" data-target-label="promotion" class="${label === "promotion" ? "active" : ""}">[4 promos]</button>
          ${
            !allowRemote && fromAddr
              ? `<button data-email-allow-remote="${escapeHtml(fromAddr)}">[load remote images]</button>`
              : ""
          }
        </div>
      </div>
      ${
        attachments.length > 0
          ? `<div class="rail-row">
              <span class="muted">attachments:</span>
              <div>
                ${attachments
                  .map(
                    (a) =>
                      `<button data-email-save-att="${escapeHtml(mid)}" data-part-id="${escapeHtml(String(a.part_id ?? ""))}">[save ${escapeHtml(String(a.filename ?? "file"))}]</button>`
                  )
                  .join(" ")}
              </div>
            </div>`
          : ""
      }
    </div>
  `;
}

export function renderEmailAgentRailCardsHtml(
  detailObj: Record<string, unknown> | undefined
): string {
  const msg = (detailObj?.message ?? detailObj ?? {}) as Record<string, unknown>;
  if (!msg || !msg.id) return "";

  const senderCard = msg.sender_card as Record<string, unknown> | null;
  const recent = (msg.recent_with_sender ?? []) as Array<Record<string, unknown>>;
  const extracts = (msg.extracts ?? {}) as Record<string, string>;

  return `
    <div class="kb-section">
      ${
        senderCard
          ? `<div class="kb-card">
              <div class="kb-card-header">
                <span>sender · ${escapeHtml(String(senderCard.name ?? ""))}</span>
                <span class="muted">${escapeHtml(String(senderCard.type ?? ""))}</span>
              </div>
              <div class="muted">${escapeHtml(String(senderCard.summary ?? ""))}</div>
            </div>`
          : ""
      }
      ${
        extracts.order_number || extracts.tracking_number
          ? `<div class="kb-card">
              <div class="kb-card-header">
                <span>order · ${escapeHtml(extracts.merchant || "Order")}</span>
                <span class="source-cut-badge">${escapeHtml(extracts.status || "ordered")}</span>
              </div>
              <div class="muted">
                ${extracts.order_number ? `#${escapeHtml(extracts.order_number)} ` : ""}
                ${extracts.tracking_number ? `· tracking: ${escapeHtml(extracts.tracking_number)}` : ""}
              </div>
            </div>`
          : ""
      }
      ${
        recent.length > 0
          ? `<div class="kb-card">
              <div class="kb-card-header">recent with sender (${recent.length})</div>
              ${recent
                .map(
                  (r) =>
                    `<div class="rail-row"><span class="truncate">${escapeHtml(String(r.subject ?? ""))}</span></div>`
                )
                .join("")}
            </div>`
          : ""
      }
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
    <div class="knowledge-view" id="compose-view-${escapeHtml(tab.id)}">
      <div class="kb-header">
        <span>compose mail (plain text · Gemma never sends without [confirm])</span>
        <div>
          <button id="compose-draft-btn">[draft with gemma]</button>
          <button id="compose-prepare-send-btn">[send (${MOD_LABEL}+Enter)]</button>
        </div>
      </div>

      ${
        draft.status_msg
          ? `<div class="kb-status-banner">${escapeHtml(draft.status_msg)}</div>`
          : ""
      }

      ${
        draft.confirm_token && draft.confirm_line
          ? `<div class="kb-card" id="compose-confirm-bar">
              <div class="rail-row">
                <span>${escapeHtml(draft.confirm_line)}</span>
                <div>
                  <button id="compose-confirm-send-btn">[confirm]</button>
                  <button id="compose-cancel-send-btn">[cancel]</button>
                </div>
              </div>
            </div>`
          : ""
      }

      ${
        draft.queued_outbox_id
          ? `<div class="kb-card" id="compose-undo-bar">
              <div class="rail-row">
                <span>queued for delivery (10s window)...</span>
                <button id="compose-undo-send-btn">[undo]</button>
              </div>
            </div>`
          : ""
      }

      <div class="kb-card">
        <div class="kb-form-row">
          <label class="muted">from:</label>
          <select id="compose-from-select" class="kb-input">
            ${accounts
              .map(
                (a) =>
                  `<option value="${escapeHtml(a.id)}" ${a.id === draft.account_id ? "selected" : ""}>${escapeHtml(a.label)} &lt;${escapeHtml(a.email)}&gt;</option>`
              )
              .join("")}
          </select>
        </div>
        <div class="kb-form-row">
          <input id="compose-to-input" class="kb-input" type="text" placeholder="to: alice@example.com" value="${escapeHtml(draft.to)}" />
          <input id="compose-cc-input" class="kb-input" type="text" placeholder="cc:" value="${escapeHtml(draft.cc)}" />
          <input id="compose-bcc-input" class="kb-input" type="text" placeholder="bcc:" value="${escapeHtml(draft.bcc)}" />
        </div>
        <div class="kb-form-row">
          <input id="compose-subject-input" class="kb-input" type="text" placeholder="subject" value="${escapeHtml(draft.subject)}" />
        </div>
        <textarea
          id="compose-body-textarea"
          class="kb-textarea"
          rows="16"
          placeholder="write plain-text message..."
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

  container
    .querySelector("#compose-draft-btn")
    ?.addEventListener("click", async () => {
      syncFields();
      draft.status_msg = "drafting reply with Gemma...";
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
        draft.status_msg = "draft ready (review and click [send] to prepare confirmation).";
      } else {
        draft.status_msg = `draft error: ${res.error ?? "failed"}`;
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
      draft.status_msg = `send prepare error: ${res.error ?? "failed"}`;
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
        draft.status_msg = "sending in 10s (click [undo] to cancel)...";
      } else {
        draft.status_msg = `send rejected: ${res.error ?? "failed"}`;
      }
      onChanged();
    });

  container
    .querySelector("#compose-cancel-send-btn")
    ?.addEventListener("click", () => {
      draft.confirm_outbox_id = undefined;
      draft.confirm_token = undefined;
      draft.confirm_line = undefined;
      draft.status_msg = "send cancelled.";
      onChanged();
    });

  container
    .querySelector("#compose-undo-send-btn")
    ?.addEventListener("click", async () => {
      if (!draft.queued_outbox_id) return;
      const res = await sidecarUndoMailSend(draft.queued_outbox_id);
      if (res.ok) {
        draft.queued_outbox_id = undefined;
        draft.status_msg = "send undone. message returned to draft.";
      } else {
        draft.status_msg = `undo failed: ${res.error ?? "already sent"}`;
      }
      onChanged();
    });
}

export {
  sidecarGetMailMessage,
  sidecarHideMailMessage,
  sidecarLabelMailMessage,
  sidecarOpenMailMessage,
  sidecarSaveMailAttachment,
  sidecarUpdateMailSettings,
};
