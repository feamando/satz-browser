import { sidecarEnrichUrlPreviews } from "./api";
import { icon } from "./design-system/icons";
import { getConfiguredDriveProviders } from "./drives";
import { bindFaviconFallbacks, renderSiteFaviconHtml } from "./favicon";
import { t, tCount, tDynamic } from "./i18n";
import { bindComposeEditorEvents, renderComposeEditorHtml } from "./mail";
import { scheduleWebviewLayoutSync } from "./tabs";
import {
  cacheUrlPreviews,
  escapeHtml,
  extractDomain,
  formatPlainErrorMessage,
  getActiveStream,
  getActiveTabSources,
  getAvailableModelsForPicker,
  getCachedUrlPreview,
  getModelPrivacySummary,
  IS_MAC,
  isConvStreaming,
  MOD_LABEL,
  normalizePreviewUrlKey,
  state,
} from "./state";
import type {
  AgentTaskCard,
  AnswerMeta,
  BrainCitationItem,
  BrainProposalItem,
  ChatEmailCard,
  ChatImageAttachment,
  ChatMessage,
  CitationCheckEntry,
  CitedSourcePreview,
  FindingItem,
  LocalModelId,
  MailComposeDraft,
  SettingsUiCard,
  SourceItem,
  StagedSettingsFile,
} from "./types";

const MAX_CHAT_IMAGES = 6;
const MAX_CHAT_IMAGE_DIM = 1600;
const MAX_CHAT_IMAGE_BYTES = 1_200_000;
const SUPPORTED_DIRECT_IMAGE_MIMES = new Set([
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
]);
const CHAT_IMAGE_PREVIEW_OVERLAY_ID = "chat-image-preview-overlay";
const LINK_PREVIEW_POPOVER_ID = "chat-link-preview-popover";

interface ResolvedSourcePreview {
  url: string;
  domain: string;
  title: string;
  snippet: string;
  image_url: string;
  favicon_url?: string;
  trust: number | null;
}

function formatPreviewDisplayPath(rawUrl: string): string {
  try {
    const u = new URL(rawUrl);
    const host = u.hostname.replace(/^www\./, "");
    const path = u.pathname === "/" ? "" : u.pathname;
    const out = `${host}${path}${u.search}`;
    return out.length > 72 ? `${out.slice(0, 69)}...` : out;
  } catch {
    return rawUrl.length > 72 ? `${rawUrl.slice(0, 69)}...` : rawUrl;
  }
}

function resolveRichCitedPreview(
  raw: CitedSourcePreview,
  answerMeta?: AnswerMeta,
  findings?: FindingItem[]
): ResolvedSourcePreview {
  const cleanUrl = (raw.url || "").trim();
  const normKey = normalizePreviewUrlKey(cleanUrl);
  const cached = getCachedUrlPreview(cleanUrl);
  const metaSrc = answerMeta?.sources?.find(
    (s) => s.url === cleanUrl || normalizePreviewUrlKey(s.url) === normKey
  );
  const findingMatch = (findings ?? []).find(
    (f) =>
      f.image_url &&
      (f.page_url === cleanUrl || normalizePreviewUrlKey(f.page_url || "") === normKey)
  );
  const dom =
    (raw.domain || metaSrc?.domain || cached?.domain || extractDomain(cleanUrl) || "")
      .trim()
      .replace(/^www\./, "");
  const bestTitle =
    (raw.title && raw.title !== cleanUrl ? raw.title : "") ||
    (metaSrc?.title && metaSrc.title !== cleanUrl ? metaSrc.title : "") ||
    (cached?.title && cached.title !== cleanUrl ? cached.title : "") ||
    findingMatch?.title ||
    raw.title ||
    dom ||
    cleanUrl;
  const snippet = (
    raw.snippet ||
    metaSrc?.snippet ||
    cached?.snippet ||
    ""
  ).trim();
  const imageUrl = (
    raw.image_url ||
    metaSrc?.image_url ||
    cached?.image_url ||
    findingMatch?.image_url ||
    ""
  ).trim();
  const trust =
    typeof raw.trust === "number"
      ? raw.trust
      : typeof metaSrc?.trust?.effective === "number"
        ? metaSrc.trust.effective
        : typeof cached?.trust === "number"
          ? cached.trust
          : null;
  return {
    url: cleanUrl,
    domain: dom,
    title: bestTitle,
    snippet,
    image_url: /^https?:\/\//i.test(imageUrl) ? imageUrl : "",
    favicon_url: raw.favicon_url || cached?.favicon_url,
    trust,
  };
}

let linkPreviewOpenTimer: number | null = null;
let linkPreviewCloseTimer: number | null = null;
let activeHoverTrigger: HTMLElement | null = null;
let activeHoverKey: string | null = null;
let activeHoverActions: ChatActions | null = null;
let hoverGlobalListenersBound = false;
const hoverEnrichAttempted = new Set<string>();
const hoverContainerActions = new WeakMap<HTMLElement, ChatActions>();

export function applyCachedPreviewsToChatDom(previews: CitedSourcePreview[]): void {
  if (!previews || previews.length === 0) return;
  for (const pv of previews) {
    patchPreviewCardsInContainer(document.body, pv);
  }
}

interface HoverPopoverPayload {
  kind: "url" | "citation" | "brain";
  url?: string;
  domain: string;
  title: string;
  snippet: string;
  image_url: string;
  favicon_url?: string;
  badge?: string;
  displayUrl: string;
  hint: string;
  loading?: boolean;
  citationIndex?: number;
  sourceId?: string | null;
  brainSlug?: string;
  brainLabel?: string;
}

export function closeChatLinkPreviewPopover(): void {
  if (linkPreviewOpenTimer !== null) {
    window.clearTimeout(linkPreviewOpenTimer);
    linkPreviewOpenTimer = null;
  }
  if (linkPreviewCloseTimer !== null) {
    window.clearTimeout(linkPreviewCloseTimer);
    linkPreviewCloseTimer = null;
  }
  activeHoverTrigger = null;
  activeHoverKey = null;
  document.getElementById(LINK_PREVIEW_POPOVER_ID)?.remove();
}

function scheduleCloseLinkPreviewPopover(delayMs = 130): void {
  if (linkPreviewOpenTimer !== null) {
    window.clearTimeout(linkPreviewOpenTimer);
    linkPreviewOpenTimer = null;
  }
  if (linkPreviewCloseTimer !== null) {
    window.clearTimeout(linkPreviewCloseTimer);
  }
  linkPreviewCloseTimer = window.setTimeout(() => {
    linkPreviewCloseTimer = null;
    closeChatLinkPreviewPopover();
  }, delayMs);
}

function ensureGlobalHoverPreviewListeners(): void {
  if (hoverGlobalListenersBound) return;
  hoverGlobalListenersBound = true;
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeChatLinkPreviewPopover();
    }
  });
  window.addEventListener(
    "scroll",
    (e) => {
      const pop = document.getElementById(LINK_PREVIEW_POPOVER_ID);
      if (!pop) return;
      const target = e.target as Node | null;
      if (target && pop.contains(target)) return;
      closeChatLinkPreviewPopover();
    },
    true
  );
  window.addEventListener("resize", () => {
    if (document.getElementById(LINK_PREVIEW_POPOVER_ID)) {
      closeChatLinkPreviewPopover();
    }
  });
  window.addEventListener("blur", () => {
    closeChatLinkPreviewPopover();
  });
  document.addEventListener(
    "pointerdown",
    (e) => {
      const pop = document.getElementById(LINK_PREVIEW_POPOVER_ID);
      if (!pop) return;
      if (e.target instanceof Node && pop.contains(e.target)) return;
      closeChatLinkPreviewPopover();
    },
    true
  );
}

function positionPopoverAroundTrigger(
  pop: HTMLElement,
  anchor: HTMLElement
): void {
  const rect = anchor.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) {
    closeChatLinkPreviewPopover();
    return;
  }
  const margin = 12;
  const gap = 8;
  const popW = pop.offsetWidth || 320;
  const popH = pop.offsetHeight || 180;
  let left = rect.left;
  if (left + popW > window.innerWidth - margin) {
    left = window.innerWidth - margin - popW;
  }
  left = Math.max(margin, left);

  const spaceBelow = window.innerHeight - rect.bottom - margin;
  const spaceAbove = rect.top - margin;
  let top =
    spaceBelow >= popH + gap || spaceBelow >= spaceAbove
      ? rect.bottom + gap
      : rect.top - popH - gap;
  top = Math.max(margin, Math.min(window.innerHeight - margin - popH, top));
  pop.style.left = `${Math.round(left)}px`;
  pop.style.top = `${Math.round(top)}px`;
}

function findMessageAcrossDetails(msgId: string): ChatMessage | undefined {
  if (!msgId) return undefined;
  return (
    state.activeDetail?.messages.find((m) => m.id === msgId) ??
    state.newsPerspectivesDetail?.messages.find((m) => m.id === msgId)
  );
}

function findSourceAcrossDetails(sourceId: string): SourceItem | undefined {
  if (!sourceId) return undefined;
  return (
    state.activeDetail?.sources.find((s) => s.id === sourceId) ??
    state.newsPerspectivesDetail?.sources.find((s) => s.id === sourceId)
  );
}

function buildHoverPopoverPayload(trigger: HTMLElement): HoverPopoverPayload | null {
  const msgEl = trigger.closest("[data-msg-id]") as HTMLElement | null;
  const msgId = msgEl?.getAttribute("data-msg-id") ?? "";
  const msg = findMessageAcrossDetails(msgId);
  const answerMeta =
    msg?.answer_meta ?? (msgId ? state.messageAnswerMeta[msgId] : undefined);
  const citedSources =
    msg?.cited_sources ?? (msgId ? state.messageCitedSources[msgId] : undefined) ?? [];
  const findings =
    msg?.findings ?? (msgId ? state.messageFindings[msgId] : undefined) ?? [];
  const brainSources =
    msg?.brain_sources ?? (msgId ? state.messageBrainSources[msgId] : undefined) ?? [];

  const brainKey = trigger.getAttribute("data-brain-cite");
  if (brainKey) {
    const slug = trigger.getAttribute("data-brain-slug") || "";
    const bIdx = Number(brainKey.replace(/^B/i, "")) || 0;
    const bs =
      brainSources.find((b) => slug && b.slug === slug) ??
      (bIdx > 0 ? brainSources[bIdx - 1] : undefined);
    const title = bs?.name || brainKey;
    const attrPairs = Object.entries(bs?.attributes ?? {})
      .slice(0, 3)
      .map(([k, v]) => `${k}: ${String(v)}`)
      .join(" · ");
    return {
      kind: "brain",
      domain: t("chat.preview_brain_entity"),
      title,
      snippet: attrPairs || bs?.aliases?.slice(0, 3).join(", ") || "",
      image_url: "",
      badge: bs?.entity_type || brainKey,
      displayUrl: bs?.path || bs?.slug || brainKey,
      hint: t("chat.open_brain_card", { name: title }),
      brainSlug: bs?.slug || slug,
      brainLabel: brainKey,
    };
  }

  const citeAttr = trigger.getAttribute("data-citation-idx");
  if (citeAttr) {
    const idx = Number(citeAttr);
    const srcId = trigger.getAttribute("data-citation-src") || null;
    let sourceIds: string[] = [];
    if (msg?.source_ids_json) {
      try {
        sourceIds = JSON.parse(msg.source_ids_json) as string[];
      } catch {
        sourceIds = [];
      }
    }
    const metaSrc =
      answerMeta?.sources?.find((s) => s.idx === idx) ??
      (idx > 0 ? answerMeta?.sources?.[idx - 1] : undefined);
    const citedMatch =
      (srcId && /^https?:\/\//i.test(srcId)
        ? citedSources.find((cs) => cs.url === srcId)
        : undefined) ?? (idx > 0 ? citedSources[idx - 1] : undefined);
    const rawSid = srcId ?? (idx > 0 ? sourceIds[idx - 1] : "") ?? "";
    const targetUrl =
      metaSrc?.url || citedMatch?.url || (/^https?:\/\//i.test(rawSid) ? rawSid : "");

    if (targetUrl && /^https?:\/\//i.test(targetUrl)) {
      const pv = resolveRichCitedPreview(
        {
          url: targetUrl,
          title: metaSrc?.title || citedMatch?.title || targetUrl,
          domain: metaSrc?.domain || citedMatch?.domain,
          snippet: metaSrc?.snippet || citedMatch?.snippet,
          image_url: metaSrc?.image_url || citedMatch?.image_url,
          favicon_url: citedMatch?.favicon_url,
        },
        answerMeta,
        findings
      );
      const needsEnrich =
        (!pv.image_url || !pv.snippet) &&
        !hoverEnrichAttempted.has(normalizePreviewUrlKey(pv.url));
      return {
        kind: "citation",
        url: pv.url,
        domain: pv.domain || extractDomain(pv.url),
        title: pv.title,
        snippet: pv.snippet,
        image_url: pv.image_url,
        favicon_url: pv.favicon_url,
        badge:
          pv.trust !== null
            ? `[${idx}] · ${pv.trust.toFixed(1)}/10`
            : `[${idx}]`,
        displayUrl: formatPreviewDisplayPath(pv.url),
        hint: t("chat.preview_open_tab"),
        loading: needsEnrich && !pv.snippet,
        citationIndex: idx,
        sourceId: rawSid || null,
      };
    }

    const openTab = state.activeDetail?.tabs.find(
      (tb) => tb.id === rawSid || tb.url === rawSid
    );
    const title = openTab?.title || rawSid || `[${idx}]`;
    const tabUrl = openTab?.url || rawSid;
    return {
      kind: "citation",
      domain: extractDomain(tabUrl) || "source",
      title,
      snippet: openTab?.last_summary || "",
      image_url: "",
      badge: `[${idx}]`,
      displayUrl: formatPreviewDisplayPath(tabUrl),
      hint: t("chat.preview_open_tab"),
      citationIndex: idx,
      sourceId: rawSid || null,
    };
  }

  const openUrl =
    trigger.getAttribute("data-open-tab-url") ||
    (trigger instanceof HTMLAnchorElement && /^https?:\/\//i.test(trigger.href)
      ? trigger.href
      : "");
  if (!openUrl || !/^https?:\/\//i.test(openUrl)) return null;

  const fallbackTitle =
    trigger.getAttribute("data-open-tab-title") ||
    (trigger.textContent || "").replace(/↗\s*$/, "").trim() ||
    openUrl;
  const normKey = normalizePreviewUrlKey(openUrl);
  const citedMatch = citedSources.find(
    (cs) => cs.url === openUrl || normalizePreviewUrlKey(cs.url) === normKey
  );
  const pv = resolveRichCitedPreview(
    {
      url: openUrl,
      title: citedMatch?.title || fallbackTitle,
      domain: citedMatch?.domain,
      snippet: citedMatch?.snippet,
      image_url: citedMatch?.image_url,
      favicon_url: citedMatch?.favicon_url,
    },
    answerMeta,
    findings
  );
  const needsEnrich =
    (!pv.image_url || !pv.snippet) && !hoverEnrichAttempted.has(normKey);
  return {
    kind: "url",
    url: pv.url,
    domain: pv.domain || extractDomain(pv.url),
    title: pv.title,
    snippet: pv.snippet,
    image_url: pv.image_url,
    favicon_url: pv.favicon_url,
    badge: pv.trust !== null ? `${pv.trust.toFixed(1)}/10` : undefined,
    displayUrl: formatPreviewDisplayPath(pv.url),
    hint: t("chat.preview_open_tab"),
    loading: needsEnrich && !pv.snippet,
  };
}

function patchPreviewCardsInContainer(
  container: HTMLElement,
  pv: CitedSourcePreview
): void {
  const normTarget = normalizePreviewUrlKey(pv.url);
  container.querySelectorAll(".card.preview-card[data-open-tab-url]").forEach((cardEl) => {
    const el = cardEl as HTMLElement;
    const cardUrl = el.getAttribute("data-open-tab-url") || "";
    if (!cardUrl || (cardUrl !== pv.url && normalizePreviewUrlKey(cardUrl) !== normTarget)) {
      return;
    }
    const body = el.querySelector(".preview-card-body") as HTMLElement | null;
    if (!body) return;
    if (pv.image_url && !el.querySelector(".preview-card-media")) {
      const media = document.createElement("div");
      media.className = "preview-card-media";
      const img = document.createElement("img");
      img.className = "preview-card-thumb";
      img.src = pv.image_url;
      img.alt = "";
      img.loading = "lazy";
      img.setAttribute("referrerpolicy", "no-referrer");
      img.addEventListener("error", () => media.remove(), { once: true });
      media.appendChild(img);
      el.prepend(media);
    }
    if (pv.snippet && !body.querySelector(".preview-card-snippet")) {
      const snip = document.createElement("div");
      snip.className = "preview-card-snippet";
      snip.textContent = pv.snippet;
      const urlLine = body.querySelector(".preview-card-url");
      if (urlLine) {
        body.insertBefore(snip, urlLine);
      } else {
        body.appendChild(snip);
      }
    }
  });
}

function renderLinkPreviewPopoverDom(
  anchor: HTMLElement,
  payload: HoverPopoverPayload,
  container: HTMLElement,
  actions: ChatActions
): void {
  if (!anchor.isConnected) {
    closeChatLinkPreviewPopover();
    return;
  }
  activeHoverActions = actions;
  let pop = document.getElementById(LINK_PREVIEW_POPOVER_ID) as HTMLElement | null;
  if (!pop) {
    pop = document.createElement("div");
    pop.id = LINK_PREVIEW_POPOVER_ID;
    pop.className = "link-preview-popover";
    pop.setAttribute("role", "tooltip");
    pop.addEventListener("mouseenter", () => {
      if (linkPreviewCloseTimer !== null) {
        window.clearTimeout(linkPreviewCloseTimer);
        linkPreviewCloseTimer = null;
      }
    });
    pop.addEventListener("mouseleave", () => {
      scheduleCloseLinkPreviewPopover(130);
    });
    document.body.appendChild(pop);
  }

  const headIconHtml =
    payload.kind === "brain"
      ? icon("brain", "ico-sm")
      : payload.url
        ? renderSiteFaviconHtml(payload.url, payload.favicon_url, "globe")
        : icon("globe", "ico-sm");

  const mediaHtml = payload.image_url
    ? `<div class="link-preview-media"><img class="link-preview-thumb" src="${escapeHtml(payload.image_url)}" alt="" referrerpolicy="no-referrer" /></div>`
    : "";
  const snippetHtml = payload.snippet
    ? `<div class="link-preview-snippet">${escapeHtml(payload.snippet)}</div>`
    : payload.loading
      ? `<div class="link-preview-snippet">${escapeHtml(t("chat.preview_loading"))}</div>`
      : "";

  pop.innerHTML = `
    ${mediaHtml}
    <div class="link-preview-body">
      <div class="link-preview-head">
        ${headIconHtml}
        <span class="link-preview-dom">${escapeHtml(payload.domain)}</span>
        ${payload.badge ? `<span class="link-preview-badge">${escapeHtml(payload.badge)}</span>` : ""}
      </div>
      <div class="link-preview-title">${escapeHtml(payload.title)}</div>
      ${snippetHtml}
      <div class="link-preview-foot">
        <span class="link-preview-url">${escapeHtml(payload.displayUrl)}</span>
        <span>${escapeHtml(payload.hint)}</span>
      </div>
    </div>
  `;

  bindFaviconFallbacks(pop);
  const thumb = pop.querySelector("img.link-preview-thumb") as HTMLImageElement | null;
  if (thumb) {
    thumb.addEventListener(
      "error",
      () => {
        thumb.closest(".link-preview-media")?.remove();
        if (pop && anchor.isConnected) {
          positionPopoverAroundTrigger(pop, anchor);
        }
      },
      { once: true }
    );
  }

  pop.onclick = () => {
    if (payload.url) {
      activeHoverActions?.onOpenUrlAsTab(payload.url, payload.title, true);
    } else if (payload.kind === "brain" && payload.brainSlug) {
      activeHoverActions?.onClickBrainCitation?.(payload.brainSlug, payload.brainLabel || "");
    } else if (typeof payload.citationIndex === "number") {
      activeHoverActions?.onClickCitation(payload.citationIndex, payload.sourceId ?? null);
    }
    closeChatLinkPreviewPopover();
  };

  pop.style.visibility = "hidden";
  positionPopoverAroundTrigger(pop, anchor);
  pop.style.visibility = "visible";

  if (payload.url && (!payload.image_url || !payload.snippet)) {
    const urlKey = normalizePreviewUrlKey(payload.url);
    if (!hoverEnrichAttempted.has(urlKey)) {
      hoverEnrichAttempted.add(urlKey);
      const reqUrl = payload.url;
      void sidecarEnrichUrlPreviews(
        [{ url: reqUrl, title: payload.title, domain: payload.domain }],
        true
      ).then((previews) => {
        const values = Object.values(previews);
        if (values.length === 0) {
          const curPop = document.getElementById(LINK_PREVIEW_POPOVER_ID);
          if (curPop && activeHoverKey === urlKey) {
            const updated = buildHoverPopoverPayload(anchor);
            if (updated) {
              updated.loading = false;
              renderLinkPreviewPopoverDom(anchor, updated, container, actions);
            }
          }
          return;
        }
        cacheUrlPreviews(values);
        for (const pv of values) {
          patchPreviewCardsInContainer(container, pv);
        }
        if (
          document.getElementById(LINK_PREVIEW_POPOVER_ID) &&
          activeHoverKey === urlKey &&
          anchor.isConnected
        ) {
          const refreshed = buildHoverPopoverPayload(anchor);
          if (refreshed) {
            refreshed.loading = false;
            renderLinkPreviewPopoverDom(anchor, refreshed, container, actions);
          }
        }
      });
    }
  }
}

function makeChatImageId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `img-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function extractImageFilesFromDataTransfer(
  dt: DataTransfer | null
): File[] {
  if (!dt) return [];
  const files: File[] = [];
  const seen = new Set<string>();
  const pushIfImage = (file: File | null | undefined) => {
    if (!file) return;
    const isImageMime = file.type.startsWith("image/");
    const hasImageExt = /\.(png|jpe?g|webp|gif|bmp|ico|svg)$/i.test(
      file.name || ""
    );
    if (!isImageMime && !hasImageExt) return;
    const sig = `${file.name}:${file.size}:${file.type}:${file.lastModified}`;
    if (seen.has(sig)) return;
    seen.add(sig);
    files.push(file);
  };
  if (dt.items) {
    for (let i = 0; i < dt.items.length; i += 1) {
      const item = dt.items[i];
      if (item.kind === "file") {
        pushIfImage(item.getAsFile());
      }
    }
  }
  if (dt.files) {
    for (let i = 0; i < dt.files.length; i += 1) {
      pushIfImage(dt.files[i]);
    }
  }
  return files;
}

export function isSupportedSettingsConfigFile(file: File | null | undefined): boolean {
  if (!file) return false;
  const name = (file.name || "").toLowerCase();
  const base = name.split(/[\\/]/).pop() ?? name;
  return (
    base === ".env" ||
    base.startsWith(".env.") ||
    /\.(json|env|txt|toml|conf|cfg|ini)$/i.test(base)
  );
}

export function extractSettingsConfigFilesFromDataTransfer(
  dt: DataTransfer | null
): File[] {
  if (!dt) return [];
  const files: File[] = [];
  const seen = new Set<string>();
  const pushIfConfig = (file: File | null | undefined) => {
    if (!file || !isSupportedSettingsConfigFile(file)) return;
    const sig = `${file.name}:${file.size}:${file.type}:${file.lastModified}`;
    if (seen.has(sig)) return;
    seen.add(sig);
    files.push(file);
  };
  if (dt.items) {
    for (let i = 0; i < dt.items.length; i += 1) {
      const item = dt.items[i];
      if (item.kind === "file") {
        pushIfConfig(item.getAsFile());
      }
    }
  }
  if (dt.files) {
    for (let i = 0; i < dt.files.length; i += 1) {
      pushIfConfig(dt.files[i]);
    }
  }
  return files;
}

function readBlobAsDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
      } else {
        reject(new Error("Could not read image data."));
      }
    };
    reader.onerror = () => {
      reject(reader.error ?? new Error("Could not read image file."));
    };
    reader.readAsDataURL(blob);
  });
}

function loadImageElement(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Could not decode image."));
    img.src = src;
  });
}

export async function readAndNormalizeImageFile(
  file: File
): Promise<ChatImageAttachment> {
  const rawDataUrl = await readBlobAsDataUrl(file);
  const rawMime = file.type || "image/png";
  const name = file.name?.trim() || "pasted-image.png";

  const img = await loadImageElement(rawDataUrl);
  const width = img.naturalWidth || img.width || 0;
  const height = img.naturalHeight || img.height || 0;

  const needsResize =
    width > MAX_CHAT_IMAGE_DIM || height > MAX_CHAT_IMAGE_DIM;
  const needsFormatNorm = !SUPPORTED_DIRECT_IMAGE_MIMES.has(rawMime);
  const needsSizeCompress = file.size > MAX_CHAT_IMAGE_BYTES;

  if (
    (needsResize || needsFormatNorm || needsSizeCompress) &&
    width > 0 &&
    height > 0
  ) {
    const scale = Math.min(1, MAX_CHAT_IMAGE_DIM / Math.max(width, height));
    const targetW = Math.max(1, Math.round(width * scale));
    const targetH = Math.max(1, Math.round(height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = targetW;
    canvas.height = targetH;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.drawImage(img, 0, 0, targetW, targetH);
      const outMime =
        rawMime === "image/png" && !needsSizeCompress
          ? "image/png"
          : rawMime === "image/webp"
            ? "image/webp"
            : needsFormatNorm && !needsSizeCompress
              ? "image/png"
              : "image/jpeg";
      const quality = outMime === "image/png" ? undefined : 0.88;
      let outUrl = canvas.toDataURL(outMime, quality);
      if (
        outMime === "image/png" &&
        outUrl.length > MAX_CHAT_IMAGE_BYTES * 1.4
      ) {
        outUrl = canvas.toDataURL("image/jpeg", 0.86);
      }
      const approxBytes = Math.round(
        (outUrl.split(",")[1]?.length ?? 0) * 0.75
      );
      const semiIdx = outUrl.indexOf(";");
      const finalMime = semiIdx > 5 ? outUrl.slice(5, semiIdx) : outMime;
      return {
        id: makeChatImageId(),
        name,
        mime: finalMime,
        data_url: outUrl,
        width: targetW,
        height: targetH,
        size: approxBytes || file.size,
      };
    }
  }

  return {
    id: makeChatImageId(),
    name,
    mime: rawMime,
    data_url: rawDataUrl,
    width: width || undefined,
    height: height || undefined,
    size: file.size || undefined,
  };
}

function reRenderPreservingDraft(
  container?: HTMLElement | null,
  actions?: ChatActions,
  focusInput = true
): void {
  const target =
    container ??
    (document
      .getElementById("chat-composer-input")
      ?.closest(
        "#chat-main-container, #site-tab-agent-rail, #compare-agent-rail"
      ) as HTMLElement | null);
  if (!target || !actions) return;

  const prevInput = target.querySelector(
    "#chat-composer-input"
  ) as HTMLTextAreaElement | null;
  const draftText = prevInput ? prevInput.value : "";
  const selStart = prevInput?.selectionStart ?? draftText.length;
  const selEnd = prevInput?.selectionEnd ?? draftText.length;
  const wasFocused = Boolean(prevInput && document.activeElement === prevInput);

  renderChatPanel(target, actions);

  const nextInput = target.querySelector(
    "#chat-composer-input"
  ) as HTMLTextAreaElement | null;
  if (nextInput) {
    if (draftText && !nextInput.value) {
      nextInput.value = draftText;
    }
    if (nextInput.value) {
      nextInput.style.height = "auto";
      nextInput.style.height = `${Math.min(140, nextInput.scrollHeight)}px`;
    }
    if (focusInput || wasFocused) {
      nextInput.focus();
      try {
        nextInput.setSelectionRange(selStart, selEnd);
      } catch {
        // Ignore selection errors if not focusable.
      }
    }
  }
}

export async function addChatImageFiles(
  files: File[],
  convId: string,
  container?: HTMLElement | null,
  actions?: ChatActions
): Promise<void> {
  if (!convId || files.length === 0) return;

  const existing = state.pendingChatImagesByConv[convId] ?? [];
  const remaining = Math.max(0, MAX_CHAT_IMAGES - existing.length);
  if (remaining === 0) {
    state.chatImageNotice = t("chat.err_max_images", { max: MAX_CHAT_IMAGES });
    reRenderPreservingDraft(container, actions);
    return;
  }

  const toProcess = files.slice(0, remaining);
  const droppedCount = files.length - toProcess.length;
  const added: ChatImageAttachment[] = [];
  let failedCount = 0;

  for (const file of toProcess) {
    try {
      added.push(await readAndNormalizeImageFile(file));
    } catch {
      failedCount += 1;
    }
  }

  if (added.length > 0) {
    state.pendingChatImagesByConv[convId] = [...existing, ...added];
  }

  if (droppedCount > 0 && failedCount > 0) {
    state.chatImageNotice = t("chat.err_attached_skipped", {
      max: MAX_CHAT_IMAGES,
      count: failedCount,
    });
  } else if (droppedCount > 0) {
    state.chatImageNotice = t("chat.err_max_images_dropped", {
      max: MAX_CHAT_IMAGES,
      dropped: droppedCount,
    });
  } else if (failedCount > 0) {
    state.chatImageNotice = t("chat.err_unreadable_images", {
      count: failedCount,
    });
  } else {
    state.chatImageNotice = "";
  }

  reRenderPreservingDraft(container, actions);
}

export function renderChatImagePreviewOverlay(): void {
  const existing = document.getElementById(CHAT_IMAGE_PREVIEW_OVERLAY_ID);
  const img = state.chatImagePreview;
  if (!img) {
    existing?.remove();
    scheduleWebviewLayoutSync();
    return;
  }

  let overlay = existing as HTMLDivElement | null;
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = CHAT_IMAGE_PREVIEW_OVERLAY_ID;
    overlay.className = "modal-backdrop";
    document.body.appendChild(overlay);
  }

  const metaParts: string[] = [];
  if (img.width && img.height) metaParts.push(`${img.width}x${img.height}`);
  if (img.size) {
    metaParts.push(t("mail.att_kb", { size: Math.max(1, Math.round(img.size / 1024)) }));
  }
  const metaLabel = metaParts.length > 0 ? ` (${metaParts.join(", ")})` : "";
  const imgName = img.name || t("chat.img_attached_fallback");

  overlay.innerHTML = `
    <div class="card img-preview-modal" role="dialog" aria-modal="true" aria-label="${escapeHtml(t("chat.img_preview_aria"))}">
      <div class="card-h">
        ${icon("image", "ico-sm")}
        <b class="truncate">${escapeHtml(imgName + metaLabel)}</b>
        <button
          id="chat-image-preview-close"
          class="icon-btn end"
          type="button"
          title="${escapeHtml(t("chat.img_close_preview_esc"))}"
          aria-label="${escapeHtml(t("chat.img_close_preview"))}"
        >
          ${icon("x", "ico-sm")}
        </button>
      </div>
      <div class="img-preview-stage">
        <img class="img-preview-full" src="${escapeHtml(img.data_url)}" alt="${escapeHtml(imgName)}" />
      </div>
    </div>
  `;

  overlay.onclick = (e) => {
    if (e.target === overlay) {
      state.chatImagePreview = null;
      renderChatImagePreviewOverlay();
    }
  };
  overlay
    .querySelector("#chat-image-preview-close")
    ?.addEventListener("click", () => {
      state.chatImagePreview = null;
      renderChatImagePreviewOverlay();
    });

  scheduleWebviewLayoutSync();
}

export interface ChatActions {
  onSendMessage: (
    text: string,
    images?: ChatImageAttachment[],
    stagedFiles?: StagedSettingsFile[]
  ) => void;
  onRetryMessage?: (text: string, images?: ChatImageAttachment[], msgId?: string) => void;
  onStageConfigFiles?: (files: File[], convId: string) => Promise<void>;
  onSettingsCardCreateProfile?: (msgId: string, cardId: string, name: string, pin: string) => Promise<void>;
  onSettingsCardUnlockProfile?: (msgId: string, cardId: string, profileId: string, pin: string, useKeychain?: boolean) => Promise<void>;
  onSettingsCardGoogleSaveJson?: (msgId: string, cardId: string, rawJson: string) => Promise<void>;
  onSettingsCardGoogleStartLogin?: (msgId: string, cardId: string, existing?: { session_id?: string; auth_url?: string }) => Promise<void>;
  onSettingsCardGoogleConnectGmail?: (msgId: string, cardId: string) => Promise<void>;
  onSettingsCardGoogleRefresh?: (msgId: string, cardId: string) => Promise<void>;
  onSettingsCardSaveApiKey?: (msgId: string, cardId: string, providerId: string, apiKey: string) => Promise<void>;
  onSettingsCardAddMail?: (msgId: string, cardId: string, payload: Record<string, unknown>) => Promise<void>;
  onSettingsCardSaveProvider?: (msgId: string, cardId: string, payload: Record<string, unknown>) => Promise<void>;
  onSettingsCardConfirmGate?: (msgId: string, cardId: string, confirmToken: string, pin?: string) => Promise<void>;
  onSettingsCardCancelGate?: (msgId: string, cardId: string) => void;
  onSettingsCardTranslateLanguage?: (msgId: string, cardId: string, lang: string, force?: boolean) => Promise<void>;
  onSettingsCardSwitchLanguage?: (msgId: string, cardId: string, lang: string) => Promise<void>;
  onSettingsCardCancelLanguage?: (msgId: string, cardId: string, lang: string) => Promise<void>;
  onChangeModel: (model: LocalModelId) => void;
  onUsePlanckInstead?: (text: string, msgId?: string) => void;
  onOpenModelsSettings?: () => void;
  onFlaggedCitationClick?: (
    citeLabel: string,
    kind: "src" | "brain" | "unsourced",
    msgId?: string
  ) => void;
  onToggleWeb: () => void;
  onToggleMail?: () => void;
  onToggleDrives?: () => void;
  onOpenDrivesFiles?: () => void;
  onStartInlineCompose?: () => void;
  onPopoutInlineCompose?: (draft: MailComposeDraft) => void;
  onNewsTrustDelta?: (msgId: string, domain: string, delta: number) => void;
  onOpenNewsLane?: (lane: string) => void;
  onOpenNewsSettings?: (targetTab?: string) => void;
  onNewsSettingsToggleFeed?: (
    msgId: string,
    cardId: string,
    domain: string,
    enabled: boolean,
    feedUrl?: string,
    title?: string
  ) => Promise<void>;
  onNewsSettingsTrackTopic?: (
    msgId: string,
    cardId: string,
    name: string,
    keywords: string[]
  ) => Promise<void>;
  onNewsSettingsSetTrust?: (
    msgId: string,
    cardId: string,
    domain: string,
    personalScore: number | null
  ) => Promise<void>;
  onNewsSettingsAddFeedUrl?: (
    msgId: string,
    cardId: string,
    feedUrl: string,
    title?: string,
    domain?: string
  ) => Promise<void>;
  onClickCitation: (citationIndex: number, sourceId: string | null) => void;
  onClickBrainCitation?: (slug: string, citeLabel: string) => void;
  onOpenUrlAsTab: (url: string, title: string, activate?: boolean) => void;
  onSelectTab?: (tabId: string) => void;
  onCloseTab?: (tabId: string) => void;
  onNewTab?: () => void;
  onRecaptureTab?: (tabId: string) => void;
  onRecaptureAllTabs?: () => void;
  onAcceptProposal?: (proposalId: string, msgId: string) => void;
  onRejectProposal?: (proposalId: string, msgId: string) => void;
  onRunComparer?: () => void;
  onWatchAnswer?: (msgId: string, content: string) => void;
  onSaveAsSkill?: (payload: { taskId?: string; msgId?: string }) => void;
  onSaveFailureAsEval?: (msgId: string) => void;
  onStopTask?: (taskId: string, stopToken: string) => void;
  onConfirmTaskStep?: (taskId: string, stepId: string, confirmToken: string) => void;
  onCancelTaskStep?: (taskId: string, stepId: string) => void;
  onOpenEmailTab?: (messageId: string, subject: string) => void;
  onPrepareUnsubscribe?: (messageId: string, senderName: string) => void;
  onArchiveSenderFromTask?: (taskId: string, senderEmail: string) => void;
  onPreviewMailAttachment?: (messageId: string, partId: string) => void;
  onDownloadMailAttachment?: (messageId: string, partId: string) => void;
}

export function renderChatPanel(
  container: HTMLElement,
  actions: ChatActions
): void {
  const detail = state.activeDetail;
  if (!detail) {
    container.innerHTML = "";
    return;
  }

  const convId = detail.conversation.id;
  const convStream = getActiveStream(convId);
  const isStreamingHere = Boolean(convStream);

  const prevListEl = container.querySelector(
    "#chat-messages-list"
  ) as HTMLElement | null;
  const isSameConv = state.chatLastRenderedConvId === convId;
  const prevScrollTop = prevListEl?.scrollTop ?? 0;
  const prevWasNearBottom =
    !prevListEl ||
    prevListEl.scrollHeight - prevListEl.scrollTop - prevListEl.clientHeight <=
      140;
  const shouldStickToBottom =
    !isSameConv || !prevListEl || isStreamingHere || state.chatPinToBottom || prevWasNearBottom;
  state.chatLastRenderedConvId = convId;

  const existingInput = container.querySelector(
    "#chat-composer-input"
  ) as HTMLTextAreaElement | HTMLInputElement | null;
  const wasFocused =
    Boolean(existingInput) && document.activeElement === existingInput;
  const preservedValue = existingInput?.value ?? "";
  const preservedSelection =
    existingInput?.selectionStart ?? preservedValue.length;

  const messages = detail.messages;
  const activeTabSources = getActiveTabSources(detail);
  const elapsedSec =
    convStream && convStream.startedAt > 0
      ? ((Date.now() - convStream.startedAt) / 1000).toFixed(1)
      : "0.0";
  const phaseLabel = convStream?.phase || t("chat.phase_processing");
  const statusLineText =
    convStream?.status || t("chat.status_in_progress");

  const pendingImages = state.pendingChatImagesByConv[convId] ?? [];
  const pendingStagedFiles = state.pendingStagedFilesByConv[convId] ?? [];
  const isSettingsOrigin = detail.conversation.origin === "settings";
  const isNewsSettingsConv = detail.conversation.origin === "news_settings";
  const isSettingsConv = isSettingsOrigin || isNewsSettingsConv;
  const pendingImagesHtml =
    pendingImages.length > 0
      ? `<div class="composer-images" aria-label="${escapeHtml(t("chat.attached_images_aria"))}">${pendingImages
          .map(
            (img, idx) => `
              <div class="composer-img-item">
                <button
                  type="button"
                  class="composer-img-thumb"
                  data-preview-pending-img="${escapeHtml(img.id)}"
                  title="${escapeHtml(t("chat.preview_img_title", { name: img.name || t("chat.img_indexed", { idx: idx + 1 }) }))}"
                  aria-label="${escapeHtml(t("chat.preview_img_title", { name: img.name || t("chat.img_indexed", { idx: idx + 1 }) }))}"
                >
                  <img src="${escapeHtml(img.data_url)}" alt="${escapeHtml(img.name || t("chat.img_attached_indexed", { idx: idx + 1 }))}" />
                </button>
                <button
                  type="button"
                  class="composer-img-remove"
                  data-remove-pending-img="${escapeHtml(img.id)}"
                  title="${escapeHtml(t("chat.remove_img"))}"
                  aria-label="${escapeHtml(t("chat.remove_img"))}"
                >
                  ${icon("x", "ico-xs")}
                </button>
              </div>`
          )
          .join("")}</div>`
      : "";
  const imageNoticeHtml = state.chatImageNotice
    ? `<div class="composer-img-notice">${escapeHtml(state.chatImageNotice)}</div>`
    : "";

  const offlineNotice = !state.sidecar.online
    ? t("chat.offline_notice")
    : isStreamingHere
      ? statusLineText
      : pendingStagedFiles.length > 0
        ? tCount("chat.ph_staged_files", pendingStagedFiles.length)
        : pendingImages.length > 0
          ? tCount("chat.ph_attached_images", pendingImages.length)
          : isNewsSettingsConv
            ? t("chat.ph_news_settings")
            : isSettingsOrigin
              ? t("chat.ph_settings")
            : activeTabSources.length > 0
              ? tCount("chat.ph_tabs", activeTabSources.length)
              : t("chat.ph_default");

  const readableTabSources = activeTabSources.filter((s) => s.textChars > 0);
  const allOpenTabsEmpty =
    activeTabSources.length > 0 && readableTabSources.length === 0;

  const emptyContextBannerHtml =
    allOpenTabsEmpty && !state.webSearchEnabled && !isStreamingHere
      ? `
        <div class="composer-ctx-warn">
          <span>${escapeHtml(t("chat.ctx_empty_warn"))}</span>
          <button id="chat-recapture-all-btn" class="btn-text" type="button">${escapeHtml(t("sources.recapture"))}</button>
          <button id="chat-enable-web-banner-btn" class="btn-text" type="button">${escapeHtml(t("chat.enable_web_search"))}</button>
        </div>
      `
      : "";

  const visibleContextSources =
    state.composerContextExpanded || activeTabSources.length <= 2
      ? activeTabSources
      : activeTabSources.slice(0, 2);
  const collapsedExtraCount =
    !state.composerContextExpanded && activeTabSources.length > 2
      ? activeTabSources.length - 2
      : 0;

  const renderContextPillHtml = (item: (typeof activeTabSources)[number]) => {
    const stat = state.sourceStats[item.sourceId];
    const charsCaptured = stat?.chars_captured ?? item.textChars;
    const captureMode = stat?.capture_mode ?? item.captureMode;
    const isEmpty = charsCaptured === 0;
    const isActive = state.activeTabId === item.tab.id;
    const modeLabel = captureMode === "fetch" ? t("sources.public_fetch") : "";
    const cutLabel = stat?.was_cut ? t("chat.cut_suffix") : "";
    const tooltipText = isEmpty
      ? t("chat.pill_empty_title", { title: item.title, url: item.url })
      : captureMode === "fetch"
        ? t("chat.pill_fetch_title", {
            chars: charsCaptured.toLocaleString(),
            mode: modeLabel,
            cut: cutLabel,
          })
        : t("chat.pill_tab_title", {
            title: item.title,
            url: item.url,
            chars: charsCaptured.toLocaleString(),
            mode: modeLabel,
            cut: cutLabel,
          });

    return `
      <div
        class="pill ${isActive ? "accent" : ""} ${isEmpty ? "muted" : ""}"
        data-pill-tab-id="${escapeHtml(item.tab.id)}"
        title="${escapeHtml(tooltipText)}"
      >
        <span>${isEmpty ? "-" : `[${item.citeIndex ?? item.index}]`}</span>
        <span class="truncate">${escapeHtml(item.domain)}${isEmpty ? escapeHtml(t("chat.pill_empty_suffix")) : ""}</span>
        ${
          isEmpty
            ? `<button class="btn-text" type="button" data-pill-recapture-tab-id="${escapeHtml(item.tab.id)}" title="${escapeHtml(t("chat.recapture_page"))}">${escapeHtml(t("common.retry"))}</button>`
            : ""
        }
        <button
          class="composer-pill-close"
          type="button"
          data-pill-close-tab-id="${escapeHtml(item.tab.id)}"
          title="${escapeHtml(t("chat.close_tab_ctx"))}"
        >${icon("x", "ico-sm")}</button>
      </div>
    `;
  };

  const stagedFilePillsHtml = pendingStagedFiles
    .map(
      (sf) => `
      <div
        class="pill accent"
        data-staged-id="${escapeHtml(sf.staging_id)}"
        title="${escapeHtml(t("chat.staged_file_title", { filename: sf.filename, kind: sf.detected_kind }))}"
      >
        ${icon("doc", "ico-sm")}
        <span class="truncate">${escapeHtml(sf.filename)} · ${escapeHtml(sf.summary)}</span>
        <button
          class="composer-pill-close"
          type="button"
          data-remove-staged-file="${escapeHtml(sf.staging_id)}"
          title="${escapeHtml(t("chat.remove_staged_file"))}"
        >${icon("x", "ico-sm")}</button>
      </div>
    `
    )
    .join("");

  const visibleSourcesInComposer = isSettingsConv ? [] : visibleContextSources;
  const contextPillsHtml =
    (isSettingsConv ? 0 : activeTabSources.length) === 0 && pendingStagedFiles.length === 0
      ? ""
      : `
        <div class="composer-ctx">
          ${stagedFilePillsHtml}
          ${visibleSourcesInComposer.map(renderContextPillHtml).join("")}
          ${
            !isSettingsConv && collapsedExtraCount > 0
              ? `<button id="chat-context-expand-btn" class="pill" type="button">${escapeHtml(t("chat.ctx_more", { count: collapsedExtraCount }))}</button>`
              : !isSettingsConv && activeTabSources.length > 2
                ? `<button id="chat-context-expand-btn" class="pill" type="button">${escapeHtml(t("chat.ctx_fewer"))}</button>`
                : ""
          }
          ${
            !isSettingsConv
              ? `<button id="chat-context-add-tab-btn" class="pill" type="button" title="${escapeHtml(t("chat.ctx_add_tab_title"))}">${icon("plus", "ico-sm")}<span>${escapeHtml(t("chat.tab_label"))}</span></button>`
              : ""
          }
          ${
            !isSettingsConv && activeTabSources.length >= 2
              ? `<button id="chat-compare-these-btn" class="pill" type="button" title="${escapeHtml(t("top.compare_these_title"))}">${icon("compare", "ico-sm")}<span>${escapeHtml(t("common.compare"))}</span></button>`
              : ""
          }
        </div>
        ${emptyContextBannerHtml}
      `;

  const stepsHtml = (convStream?.steps ?? [])
    .map(
      (step, idx) =>
        `<div class="stream-step">${escapeHtml(idx === (convStream?.steps.length ?? 0) - 1 ? t("chat.step_now") : t("chat.step_done"))} · ${escapeHtml(step)}</div>`
    )
    .join("");

  const isMailConv = detail.conversation.origin === "mail";
  const isNewsConv = detail.conversation.origin === "news";
  const isDrivesConv = detail.conversation.origin === "drives";
  const mailEffectiveOn = isMailConv || state.mailContextEnabled;
  const drivesEffectiveOn = isDrivesConv || state.drivesContextEnabled;
  const triageSourceIds = state.mailTriageSources.map((s) => s.id);
  const mailSuggestionsHtml =
    isMailConv && !isStreamingHere
      ? `
        <div class="sugg">
          <button class="pill" type="button" data-chat-suggest="what do I need to deal with today?">${escapeHtml(t("chat.sugg_mail_today"))}</button>
          <button class="pill" type="button" data-chat-suggest="summarize unread">${escapeHtml(t("chat.sugg_mail_unread"))}</button>
          <button class="pill" type="button" data-chat-suggest="draft a reply to [1]">${escapeHtml(t("chat.sugg_mail_reply"))}</button>
          <button class="pill" type="button" data-chat-compose-inline="1">${icon("compose", "ico-sm")}<span>${escapeHtml(t("mail.compose_heading"))}</span></button>
        </div>
      `
      : isNewsConv && !isStreamingHere
        ? `
        <div class="sugg">
          <button class="pill" type="button" data-chat-suggest="What are today's top corroborated European news stories?">${escapeHtml(t("chat.sugg_news_eu"))}</button>
          <button class="pill" type="button" data-chat-suggest="Compare perspectives on current global energy &amp; grid policy news">${escapeHtml(t("chat.sugg_news_persp"))}</button>
          <button class="pill" type="button" data-news-jump-lane="stories">${escapeHtml(t("chat.sugg_news_stories"))}</button>
          <button class="pill" type="button" data-news-jump-lane="tracked">${escapeHtml(t("chat.sugg_news_tracked"))}</button>
          <button class="pill" type="button" data-news-jump-lane="perspectives">${escapeHtml(t("chat.sugg_news_persp_open"))}</button>
          <button class="pill" type="button" data-open-news-settings="chat">${escapeHtml(t("chat.sugg_news_settings"))}</button>
        </div>
      `
        : isDrivesConv && !isStreamingHere
          ? (() => {
              const dp = getConfiguredDriveProviders();
              const sheetPrompt =
                dp.gdrive && dp.onedrive
                  ? "List spreadsheets across Google Drive and OneDrive"
                  : dp.onedrive
                    ? "List spreadsheets in OneDrive"
                    : "List spreadsheets in Google Drive";
              const sheetLabel =
                dp.gdrive && dp.onedrive
                  ? t("chat.sugg_drives_sheets")
                  : t("chat.sugg_drives_sheets_single", {
                      provider: t(
                        dp.onedrive
                          ? "drives.filter_provider_onedrive"
                          : "drives.filter_provider_gdrive"
                      ),
                    });
              return `
        <div class="sugg">
          <button class="pill" type="button" data-chat-suggest="Summarize my most recent documents">${escapeHtml(t("chat.sugg_drives_recent"))}</button>
          <button class="pill" type="button" data-chat-suggest="What documents were shared with me recently?">${escapeHtml(t("chat.sugg_drives_shared"))}</button>
          <button class="pill" type="button" data-chat-suggest="${escapeHtml(sheetPrompt)}">${escapeHtml(sheetLabel)}</button>
          <button class="pill" type="button" data-drives-jump-files="1">${icon("folder", "ico-sm")}<span>${escapeHtml(t("chat.sugg_drives_browse"))}</span></button>
        </div>
      `;
            })()
          : isNewsSettingsConv && !isStreamingHere
            ? `
        <div class="sugg">
          <button class="pill" type="button" data-chat-suggest="Suggest news topics to follow">${escapeHtml(t("chat.sugg_ns_topics"))}</button>
          <button class="pill" type="button" data-chat-suggest="Suggest trusted news sources and feeds">${escapeHtml(t("chat.sugg_ns_sources"))}</button>
          <button class="pill" type="button" data-chat-suggest="Suggest German and European news sources">${escapeHtml(t("chat.sugg_ns_de_eu"))}</button>
          <button class="pill" type="button" data-chat-suggest="Show my current news topics and sources">${escapeHtml(t("chat.sugg_ns_status"))}</button>
          <button class="pill" type="button" data-open-news-settings="news-settings-manual">${escapeHtml(t("chat.ns_open_manual"))}</button>
        </div>
      `
            : isSettingsOrigin && !isStreamingHere
          ? `
        <div class="sugg">
          <button class="pill" type="button" data-chat-suggest="Connect a Google account">${escapeHtml(t("chat.sugg_settings_google"))}</button>
          <button class="pill" type="button" data-chat-suggest="Check Cloud Drives configuration status">${escapeHtml(t("chat.sugg_settings_drives"))}</button>
          <button class="pill" type="button" data-chat-suggest="Create a new profile">${escapeHtml(t("chat.sugg_settings_profile"))}</button>
          <button class="pill" type="button" data-chat-suggest="Add an API key for cloud models">${escapeHtml(t("chat.sugg_settings_apikey"))}</button>
          <button class="pill" type="button" data-chat-suggest="Configure a mail account">${escapeHtml(t("chat.sugg_settings_mail"))}</button>
        </div>
      `
          : "";

  const convTasks = state.conversationTasks[detail.conversation.id] ?? [];
  const taskCardsHtml = convTasks
    .map((task) => renderTaskCardBlock(task))
    .join("");
  const watchNoticeHtml = state.watchStatusNotice
    ? `<div class="banner">${escapeHtml(state.watchStatusNotice)}</div>`
    : "";

  container.innerHTML = `
    <div class="chat-stage">
      <div class="thread-scroll" id="chat-messages-list">
        <div class="thread ${isSettingsConv ? "settings-thread" : ""}">
          ${watchNoticeHtml}
          ${
            isMailConv && state.mailTriageOverview
              ? renderMessageBlock(
                  "mail-triage-overview",
                  "assistant",
                  state.mailTriageOverview,
                  t("chat.triage_model"),
                  JSON.stringify(triageSourceIds)
                )
              : ""
          }
          ${
            messages.length === 0 &&
            convTasks.length === 0 &&
            !isStreamingHere &&
            !(isMailConv && state.mailTriageOverview)
              ? `${
                  isNewsConv && state.newsTopics.length === 0
                    ? `<div class="card inset news-onboard-banner">
                        <div class="card-h">
                          <b>${escapeHtml(t("news.empty_onboard_banner_title"))}</b>
                          <button type="button" class="btn primary sm" data-open-news-settings="chat">${escapeHtml(t("news.open_settings_btn"))}</button>
                        </div>
                        <div class="settings-card-note">${escapeHtml(t("news.empty_onboard_banner_sub"))}</div>
                      </div>`
                    : ""
                }<div class="chat-empty">${escapeHtml(t("chat.empty_conv"))}</div>`
              : messages
                  .map((m) =>
                    renderMessageBlock(
                      m.id,
                      m.role,
                      m.content,
                      m.model,
                      m.source_ids_json,
                      m.cited_sources ?? state.messageCitedSources[m.id],
                      m.proposals ?? state.messageProposals[m.id],
                      m.citation_check,
                      m.citations_ok,
                      m.citations_flagged,
                      m.findings ?? state.messageFindings[m.id],
                      m.brain_sources ?? state.messageBrainSources[m.id],
                      m.email_cards ?? state.messageEmailCards[m.id],
                      m.answer_meta ?? state.messageAnswerMeta[m.id],
                      m.email_draft,
                      m.images,
                      m.staged_files,
                      m.ui_cards ?? state.messageUiCards[m.id]
                    )
                  )
                  .join("")
          }
          ${taskCardsHtml}
          ${
            isStreamingHere && convStream
              ? `
            <div class="msg-bot" id="streaming-msg-block" data-streaming-conv-id="${escapeHtml(convId)}">
              <div class="msg-meta">
                <span>${escapeHtml(t("chat.assistant"))}</span>
                <span>· ${escapeHtml(convStream.model)}</span>
                <span>· <span id="streaming-phase-badge">${escapeHtml(phaseLabel)}</span></span>
                <span>· <span id="streaming-elapsed-timer">${escapeHtml(t("chat.elapsed_s", { sec: elapsedSec }))}</span></span>
              </div>
              <div class="stream" id="streaming-status-box">
                <div class="stream-now">
                  <span class="dot live"></span>
                  <span id="streaming-status-current" class="truncate">${escapeHtml(statusLineText)}</span>
                </div>
                <div id="streaming-steps-list">${stepsHtml}</div>
              </div>
              <div class="msg-text" id="streaming-msg-text">${escapeHtml(convStream.text)}</div>
            </div>
          `
              : ""
          }
        </div>
      </div>

      <div class="composer">
        ${mailSuggestionsHtml}
        <div id="chat-composer-box" class="cbox">
          ${contextPillsHtml}
          ${pendingImagesHtml}
          ${imageNoticeHtml}
          <input
            id="chat-image-file-input"
            type="file"
            accept="${isSettingsConv ? "image/*,.json,.env,.txt,.toml,.conf" : "image/*"}"
            multiple
            class="hidden"
          />
          <textarea
            id="chat-composer-input"
            class="cbox-input"
            rows="1"
            spellcheck="false"
            autocorrect="off"
            autocapitalize="off"
            placeholder="${escapeHtml(offlineNotice)}"
            ${isStreamingHere ? "disabled" : ""}
          ></textarea>
          <div class="cbox-foot">
            <div class="chips">
              <div class="model-chip-anchor">
                ${(() => {
                  const models = getAvailableModelsForPicker();
                  const cur = models.find((m) => m.id === state.selectedModel);
                  const curLabel = cur?.label || state.selectedModel;
                  const privacyNote = getModelPrivacySummary(state.selectedModel);
                  return `
                    <button
                      id="chat-model-chip"
                      class="chip"
                      type="button"
                      title="${escapeHtml(privacyNote)}"
                      aria-expanded="${state.composerModelMenuOpen ? "true" : "false"}"
                    >
                      ${icon("spark", "ico-sm")}
                      <span class="truncate">${escapeHtml(curLabel)}</span>
                      ${icon("chev", "ico-sm")}
                    </button>
                    ${
                      state.composerModelMenuOpen
                        ? `
                          <div class="menu" id="chat-model-menu" role="menu">
                            <div class="model-menu-note">${escapeHtml(privacyNote)}</div>
                            ${models
                              .map(
                                (m) => `
                              <button
                                type="button"
                                class="menu-item ${state.selectedModel === m.id ? "active" : ""}"
                                data-select-model="${escapeHtml(m.id)}"
                              >
                                <span class="truncate">${escapeHtml(m.label)}</span>
                                ${state.selectedModel === m.id ? icon("check", "ico-sm") : ""}
                              </button>
                            `
                              )
                              .join("")}
                          </div>
                        `
                        : ""
                    }
                  `;
                })()}
              </div>
              ${
                !isSettingsConv
                  ? `
              <button
                id="chat-web-toggle"
                type="button"
                class="chip ${state.webSearchEnabled ? "on" : ""}"
                title="${escapeHtml(t("chat.web_toggle_title"))}"
              >
                ${icon("globe", "ico-sm")}
                <span>${escapeHtml(t("common.web"))}</span>
              </button>
              <button
                id="chat-mail-toggle"
                type="button"
                class="chip ${mailEffectiveOn ? "on" : ""}"
                title="${escapeHtml(t("chat.mail_toggle_title"))}"
              >
                ${icon("mail", "ico-sm")}
                <span>${escapeHtml(t("common.mail"))}</span>
              </button>
              <button
                id="chat-drives-toggle"
                type="button"
                class="chip ${drivesEffectiveOn ? "on" : ""}"
                title="${escapeHtml(t("chat.drives_toggle_title"))}"
              >
                ${icon("drive", "ico-sm")}
                <span>${escapeHtml(t("common.drives"))}</span>
              </button>
              ${
                mailEffectiveOn
                  ? `<button id="chat-compose-inline-btn" type="button" class="chip" title="${escapeHtml(t("chat.compose_inline_title"))}">${icon("compose", "ico-sm")}<span>${escapeHtml(t("mail.compose_btn"))}</span></button>`
                  : ""
              }
              ${
                activeTabSources.length === 0
                  ? `<button id="chat-context-add-tab-btn" type="button" class="chip" title="${escapeHtml(t("chat.add_tab_ctx_title"))}">${icon("plus", "ico-sm")}<span>${escapeHtml(t("chat.tab_label"))}</span></button>`
                  : ""
              }
                  `
                  : ""
              }
              <button
                id="chat-add-image-btn"
                type="button"
                class="chip ${pendingImages.length > 0 || pendingStagedFiles.length > 0 ? "on" : ""}"
                ${isStreamingHere ? "disabled" : ""}
                title="${escapeHtml(isSettingsConv ? t("chat.attach_cfg_title") : t("chat.add_img_title", { mod: MOD_LABEL }))}"
                aria-label="${escapeHtml(isSettingsConv ? t("chat.attach_cfg_aria") : t("chat.add_img_aria"))}"
              >
                ${icon(isSettingsConv ? "attach" : "image", "ico-sm")}
                <span>${escapeHtml(
                  isSettingsConv
                    ? pendingStagedFiles.length + pendingImages.length > 0
                      ? t("chat.attach_n", { count: pendingStagedFiles.length + pendingImages.length })
                      : t("chat.attach")
                    : pendingImages.length > 0
                      ? t("chat.image_n", { count: pendingImages.length })
                      : t("chat.image")
                )}</span>
              </button>
            </div>
            <button
              id="chat-send-btn"
              type="button"
              class="send ${isStreamingHere ? "stop" : ""}"
              ${isStreamingHere ? "disabled" : ""}
              title="${escapeHtml(isStreamingHere ? t("rail.generating") : t("chat.send_msg_title"))}"
              aria-label="${escapeHtml(isStreamingHere ? t("rail.generating") : t("chat.send_msg_aria"))}"
            >
              ${isStreamingHere ? `<span class="stop-sq"></span>` : icon("send", "ico-sm")}
            </button>
          </div>
        </div>
      </div>
    </div>
  `;

  bindChatEvents(container, actions);

  const listEl = container.querySelector(
    "#chat-messages-list"
  ) as HTMLElement | null;
  if (listEl) {
    if (shouldStickToBottom) {
      listEl.scrollTop = listEl.scrollHeight;
      window.requestAnimationFrame(() => {
        listEl.scrollTop = listEl.scrollHeight;
      });
    } else if (isSameConv) {
      listEl.scrollTop = prevScrollTop;
    }
    listEl.addEventListener("scroll", () => {
      const distFromBottom =
        listEl.scrollHeight - listEl.scrollTop - listEl.clientHeight;
      state.chatPinToBottom = distFromBottom <= 140;
    });
  }

  if (preservedValue || wasFocused) {
    const nextInput = container.querySelector(
      "#chat-composer-input"
    ) as HTMLTextAreaElement | HTMLInputElement | null;
    if (nextInput) {
      nextInput.value = preservedValue;
      if (wasFocused) {
        nextInput.focus();
        nextInput.setSelectionRange(preservedSelection, preservedSelection);
      }
    }
  }
}

export function appendStreamingDelta(convId: string, delta: string): void {
  const s = state.streamsByConv[convId];
  if (!s) return;
  s.text += delta;
  const blockEl = document.getElementById("streaming-msg-block");
  if (blockEl?.getAttribute("data-streaming-conv-id") !== convId) return;
  const el = document.getElementById("streaming-msg-text");
  if (el) {
    el.textContent = s.text;
    const list = document.getElementById("chat-messages-list");
    if (list) {
      list.scrollTop = list.scrollHeight;
    }
  }
}

export function replaceStreamingText(convId: string, text: string): void {
  const s = state.streamsByConv[convId];
  if (!s) return;
  s.text = text;
  const blockEl = document.getElementById("streaming-msg-block");
  if (blockEl?.getAttribute("data-streaming-conv-id") !== convId) return;
  const el = document.getElementById("streaming-msg-text");
  if (el) {
    el.textContent = s.text;
    const list = document.getElementById("chat-messages-list");
    if (list) {
      list.scrollTop = list.scrollHeight;
    }
  }
}

export function updateStreamingStatus(
  convId: string,
  status: string,
  phase?: string
): void {
  const s = state.streamsByConv[convId];
  if (!s) return;
  s.status = status;
  if (phase) {
    s.phase = phase;
  }
  if (status && s.steps[s.steps.length - 1] !== status) {
    s.steps = [...s.steps.slice(-4), status];
  }

  const blockEl = document.getElementById("streaming-msg-block");
  if (blockEl?.getAttribute("data-streaming-conv-id") !== convId) return;

  const phaseEl = document.getElementById("streaming-phase-badge");
  if (phaseEl && s.phase) {
    phaseEl.textContent = s.phase;
  }
  const curEl = document.getElementById("streaming-status-current");
  if (curEl) {
    curEl.textContent = status;
  }
  const stepsEl = document.getElementById("streaming-steps-list");
  if (stepsEl) {
    stepsEl.innerHTML = s.steps
      .map(
        (step, idx) =>
          `<div class="stream-step">${escapeHtml(idx === s.steps.length - 1 ? t("chat.step_now") : t("chat.step_done"))} · ${escapeHtml(step)}</div>`
      )
      .join("");
  }
  const inputEl = document.getElementById(
    "chat-composer-input"
  ) as HTMLInputElement | null;
  if (inputEl && state.activeDetail?.conversation.id === convId) {
    inputEl.placeholder = t("chat.in_progress_ph", { status });
  }
  const list = document.getElementById("chat-messages-list");
  if (list) {
    list.scrollTop = list.scrollHeight;
  }
}

export function tickStreamingElapsed(): void {
  const blockEl = document.getElementById("streaming-msg-block");
  const domConvId = blockEl?.getAttribute("data-streaming-conv-id") ?? "";
  const s = domConvId ? state.streamsByConv[domConvId] : null;
  if (!s || s.startedAt <= 0) return;
  const elapsedSec = ((Date.now() - s.startedAt) / 1000).toFixed(1);
  const timerEl = document.getElementById("streaming-elapsed-timer");
  if (timerEl) {
    timerEl.textContent = t("chat.elapsed_s", { sec: elapsedSec });
  }
}

function renderSettingsUiCardsHtml(
  msgId: string,
  cards?: SettingsUiCard[]
): string {
  if (!cards || cards.length === 0) return "";
  const liveGoogle = state.googleOAuthStatus;
  const activeProfileId = state.knowledge.profile?.active_profile?.id ?? "";

  const renderCard = (c: SettingsUiCard): string => {
    const d = c.data ?? {};
    const cardTitle = tDynamic(c.title_key, c.title, c.title_vars);
    const cardSub = c.subtitle || c.subtitle_key
      ? tDynamic(c.subtitle_key, c.subtitle ?? "", c.subtitle_vars)
      : "";
    const cardNote = c.resolution_note || c.resolution_note_key
      ? tDynamic(c.resolution_note_key, c.resolution_note ?? "", c.resolution_note_vars)
      : "";

    if (c.resolved) {
      return `
        <div class="card inset" data-settings-card-id="${escapeHtml(c.id)}" data-settings-card-kind="${escapeHtml(c.kind)}">
          <div class="card-h">
            <b>${escapeHtml(cardTitle)}</b>
            <span class="badge soft">${escapeHtml(t("chat.step_done"))}</span>
          </div>
          ${cardNote ? `<div class="banner">${escapeHtml(cardNote)}</div>` : ""}
        </div>
      `;
    }

    if (c.kind === "profile_create_card") {
      const defName = String(d.profile_name ?? "");
      return `
        <div class="card inset" data-settings-card-id="${escapeHtml(c.id)}" data-settings-card-msg="${escapeHtml(msgId)}" data-settings-card-kind="profile_create_card">
          <div class="card-h">
            <b>${escapeHtml(cardTitle)}</b>
            <span class="pill end">vault.enc</span>
          </div>
          ${cardSub ? `<div class="settings-card-note">${escapeHtml(cardSub)}</div>` : ""}
          <div class="form-row">
            <input type="text" class="input" data-sc-prof-name="${escapeHtml(c.id)}" value="${escapeHtml(defName)}" placeholder="${escapeHtml(t("profile.name_placeholder"))}" spellcheck="false" ${state.profileUnlocking ? "disabled" : ""} />
            <input type="password" class="input pin" data-sc-prof-pin1="${escapeHtml(c.id)}" inputmode="numeric" maxlength="6" placeholder="${escapeHtml(t("profile.pin6_placeholder"))}" ${state.profileUnlocking ? "disabled" : ""} />
            <input type="password" class="input pin" data-sc-prof-pin2="${escapeHtml(c.id)}" inputmode="numeric" maxlength="6" placeholder="${escapeHtml(t("chat.sc_pin_confirm_ph"))}" ${state.profileUnlocking ? "disabled" : ""} />
            <button type="button" class="btn primary" data-sc-create-profile="${escapeHtml(c.id)}" data-sc-msg="${escapeHtml(msgId)}" ${state.profileUnlocking ? "disabled" : ""}>${escapeHtml(state.profileUnlocking ? t("profile.creating") : t("profile.create_unlock"))}</button>
          </div>
          <div class="settings-card-note">${escapeHtml(t("chat.sc_argon_note"))}</div>
        </div>
      `;
    }

    if (c.kind === "profile_unlock_card") {
      const pid = String(d.profile_id ?? "");
      const pname = String(d.profile_name ?? pid);
      const isAlreadyUnlockedHere = Boolean(pid && activeProfileId === pid && state.knowledge.profile?.unlocked);
      if (isAlreadyUnlockedHere) {
        return `
          <div class="card inset" data-settings-card-id="${escapeHtml(c.id)}" data-settings-card-kind="profile_unlock_card">
            <div class="card-h">
              <b>${escapeHtml(t("chat.sc_profile_label", { name: pname }))}</b>
              <span class="badge soft">${escapeHtml(t("chat.sc_unlocked"))}</span>
            </div>
          </div>
        `;
      }
      return `
        <div class="card inset" data-settings-card-id="${escapeHtml(c.id)}" data-settings-card-msg="${escapeHtml(msgId)}" data-settings-card-kind="profile_unlock_card">
          <div class="card-h">
            <b>${escapeHtml(cardTitle)}</b>
            <span class="pill end">${escapeHtml(pid || t("settings.locked_lower"))}</span>
          </div>
          ${cardSub ? `<div class="settings-card-note">${escapeHtml(cardSub)}</div>` : ""}
          <div class="form-row">
            <input type="password" class="input pin" data-sc-unlock-pin="${escapeHtml(c.id)}" inputmode="numeric" maxlength="6" placeholder="${escapeHtml(t("profile.pin6_placeholder"))}" ${state.profileUnlocking ? "disabled" : ""} />
            <button type="button" class="btn primary" data-sc-unlock-btn="${escapeHtml(c.id)}" data-sc-prof-id="${escapeHtml(pid)}" data-sc-msg="${escapeHtml(msgId)}" ${state.profileUnlocking ? "disabled" : ""}>${escapeHtml(t("profile.unlock_btn"))}</button>
            ${
              d.keychain_available
                ? `<button type="button" class="btn" data-sc-keychain-btn="${escapeHtml(c.id)}" data-sc-prof-id="${escapeHtml(pid)}" data-sc-msg="${escapeHtml(msgId)}" ${state.profileUnlocking ? "disabled" : ""}>${escapeHtml(IS_MAC ? t("settings.touch_id") : t("settings.quick_unlock"))}</button>`
                : ""
            }
          </div>
        </div>
      `;
    }

    if (c.kind === "google_oauth_connect_card") {
      const configured = Boolean(liveGoogle?.configured ?? d.configured);
      const signedIn = Boolean(liveGoogle?.signed_in ?? d.signed_in);
      const email = String(liveGoogle?.email ?? d.email ?? "");
      const maskedCid = String(liveGoogle?.masked_client_id ?? d.masked_client_id ?? "");
      const authUrl = String(d.auth_url ?? "");
      const sessionId = String(d.session_id ?? "");
      return `
        <div class="card inset" data-settings-card-id="${escapeHtml(c.id)}" data-settings-card-msg="${escapeHtml(msgId)}" data-settings-card-kind="google_oauth_connect_card">
          <div class="card-h">
            <b>${escapeHtml(cardTitle)}</b>
            <span class="end">
              ${
                signedIn
                  ? `<span class="pill"><i class="dot"></i><span>${escapeHtml(email || t("chat.sc_signed_in"))}</span></span>`
                  : configured
                    ? `<span class="pill"><i class="dot"></i><span>${escapeHtml(t("chat.sc_client_ready"))}</span></span>`
                    : `<span class="pill"><i class="dot warn"></i><span>${escapeHtml(t("chat.sc_needs_secret"))}</span></span>`
              }
            </span>
          </div>
          ${cardSub ? `<div class="settings-card-note">${escapeHtml(cardSub)}</div>` : ""}
          ${
            maskedCid
              ? `<div class="kb-kv-row"><span>${escapeHtml(t("chat.sc_client_id"))}</span><span class="mono muted">${escapeHtml(maskedCid)}</span></div>`
              : ""
          }
          ${
            !configured
              ? `
                <div class="form-row">
                  <label class="btn settings-card-file-btn">
                    ${icon("attach", "ico-sm")}
                    <span>${escapeHtml(t("chat.sc_select_json"))}</span>
                    <input type="file" accept=".json" class="hidden" data-sc-google-file="${escapeHtml(c.id)}" data-sc-msg="${escapeHtml(msgId)}" />
                  </label>
                </div>
                <div class="settings-card-note">${escapeHtml(t("chat.sc_json_vault_note"))}</div>
              `
              : signedIn
                ? `
                  <div class="settings-card-actions">
                    <button type="button" class="btn primary" data-sc-google-gmail="${escapeHtml(c.id)}" data-sc-msg="${escapeHtml(msgId)}">${escapeHtml(t("settings.google_connect_gmail_btn"))}</button>
                    <button type="button" class="btn" data-sc-google-refresh="${escapeHtml(c.id)}" data-sc-msg="${escapeHtml(msgId)}">${escapeHtml(t("settings.google_refresh_btn"))}</button>
                  </div>
                `
                : `
                  <div class="settings-card-actions">
                    <button
                      type="button"
                      class="btn primary"
                      data-sc-google-signin="${escapeHtml(c.id)}"
                      data-sc-msg="${escapeHtml(msgId)}"
                      data-sc-auth-url="${escapeHtml(authUrl)}"
                      data-sc-session-id="${escapeHtml(sessionId)}"
                    >${escapeHtml(t("chat.sc_open_signin"))}</button>
                    <label class="btn settings-card-file-btn">
                      <span>${escapeHtml(t("chat.sc_replace_json"))}</span>
                      <input type="file" accept=".json" class="hidden" data-sc-google-file="${escapeHtml(c.id)}" data-sc-msg="${escapeHtml(msgId)}" />
                    </label>
                  </div>
                `
          }
        </div>
      `;
    }

    if (c.kind === "vault_secret_input_card") {
      const prov = String(d.provider_id ?? "gemini");
      return `
        <div class="card inset" data-settings-card-id="${escapeHtml(c.id)}" data-settings-card-msg="${escapeHtml(msgId)}" data-settings-card-kind="vault_secret_input_card">
          <div class="card-h">
            <b>${escapeHtml(cardTitle)}</b>
            <span class="pill end">vault.enc</span>
          </div>
          ${cardSub ? `<div class="settings-card-note">${escapeHtml(cardSub)}</div>` : ""}
          <div class="form-row">
            <select class="select" data-sc-apikey-prov="${escapeHtml(c.id)}">
              <option value="gemini" ${prov === "gemini" ? "selected" : ""}>${escapeHtml(t("chat.sc_prov_gemini"))}</option>
              <option value="anthropic" ${prov === "anthropic" ? "selected" : ""}>${escapeHtml(t("chat.sc_prov_anthropic"))}</option>
              <option value="openai" ${prov === "openai" ? "selected" : ""}>${escapeHtml(t("chat.sc_prov_openai"))}</option>
              <option value="mistral" ${prov === "mistral" ? "selected" : ""}>${escapeHtml(t("chat.sc_prov_mistral"))}</option>
            </select>
            <input type="password" class="input" data-sc-apikey-val="${escapeHtml(c.id)}" placeholder="${escapeHtml(t("chat.sc_paste_apikey_ph"))}" autocomplete="off" spellcheck="false" />
            <button type="button" class="btn primary" data-sc-save-apikey="${escapeHtml(c.id)}" data-sc-msg="${escapeHtml(msgId)}">${escapeHtml(t("chat.sc_save_vault"))}</button>
          </div>
        </div>
      `;
    }

    if (c.kind === "mail_account_card") {
      const em = String(d.email ?? "");
      const lbl = String(d.label ?? "");
      const rawHint = String(d.provider_hint ?? "custom_imap");
      const hint = rawHint === "imap" ? "custom_imap" : rawHint;
      const presets = Array.isArray(d.presets) && d.presets.length > 0
        ? (d.presets as Array<{ id?: string; label?: string }>)
        : [
            { id: "gmail", label: "Gmail" },
            { id: "outlook", label: "Outlook / Hotmail" },
            { id: "icloud", label: "iCloud" },
            { id: "gmx", label: "GMX" },
            { id: "webde", label: "WEB.DE" },
            { id: "custom_imap", label: t("chat.sc_mail_custom_imap") },
          ];
      const googleSignedIn = Boolean(d.google_signed_in || liveGoogle?.signed_in);
      const googleEmail = String(d.google_email || liveGoogle?.email || "");
      return `
        <div class="card inset" data-settings-card-id="${escapeHtml(c.id)}" data-settings-card-msg="${escapeHtml(msgId)}" data-settings-card-kind="mail_account_card">
          <div class="card-h">
            <b>${escapeHtml(cardTitle)}</b>
            <span class="pill end">${escapeHtml(hint.replace(/_/g, " ").toUpperCase())}</span>
          </div>
          ${cardSub ? `<div class="settings-card-note">${escapeHtml(cardSub)}</div>` : ""}
          ${
            googleSignedIn && hint === "gmail"
              ? `
                <div class="banner">
                  <span>${escapeHtml(t("chat.sc_google_ready", { target: googleEmail || t("chat.sc_google_auth_fallback") }))}</span>
                  <button type="button" class="btn primary" data-sc-google-gmail="${escapeHtml(c.id)}" data-sc-msg="${escapeHtml(msgId)}">${escapeHtml(t("chat.sc_connect_xoauth2"))}</button>
                </div>
              `
              : ""
          }
          <div class="form-row">
            <select class="select" data-sc-mail-preset="${escapeHtml(c.id)}">
              ${presets
                .map(
                  (pr) =>
                    `<option value="${escapeHtml(pr.id || "")}" ${hint === pr.id ? "selected" : ""}>${escapeHtml(pr.label || pr.id || "")}</option>`
                )
                .join("")}
            </select>
            <input type="text" class="input" data-sc-mail-email="${escapeHtml(c.id)}" value="${escapeHtml(em)}" placeholder="${escapeHtml(t("chat.sc_email_ph"))}" spellcheck="false" />
            <input type="text" class="input" data-sc-mail-label="${escapeHtml(c.id)}" value="${escapeHtml(lbl)}" placeholder="${escapeHtml(t("chat.sc_label_opt_ph"))}" spellcheck="false" />
            <input type="password" class="input" data-sc-mail-pass="${escapeHtml(c.id)}" placeholder="${escapeHtml(t("chat.sc_app_pass_ph"))}" autocomplete="off" />
          </div>
          <div class="form-row">
            <input type="text" class="input" data-sc-mail-inhost="${escapeHtml(c.id)}" placeholder="${escapeHtml(t("chat.sc_imap_opt_ph"))}" spellcheck="false" />
            <input type="text" class="input" data-sc-mail-smtphost="${escapeHtml(c.id)}" placeholder="${escapeHtml(t("chat.sc_smtp_opt_ph"))}" spellcheck="false" />
            <button type="button" class="btn primary" data-sc-add-mail="${escapeHtml(c.id)}" data-sc-msg="${escapeHtml(msgId)}">${escapeHtml(t("chat.sc_test_add_mail"))}</button>
          </div>
        </div>
      `;
    }

    if (c.kind === "provider_preview_card") {
      const cats = Array.isArray(d.categories)
        ? (d.categories as Array<{ id?: string; label?: string }>)
        : [];
      const chosenCat = String(d.category_id ?? "");
      const dispName = String(d.display_name ?? "");
      const tpl = String(d.url_template ?? "");
      const modeVal = String(d.mode ?? "web_account");
      const doms = Array.isArray(d.domains) ? (d.domains as string[]) : [];
      return `
        <div class="card inset" data-settings-card-id="${escapeHtml(c.id)}" data-settings-card-msg="${escapeHtml(msgId)}" data-settings-card-kind="provider_preview_card">
          <div class="card-h">
            <b>${escapeHtml(cardTitle)}</b>
            <span class="pill end">${escapeHtml(modeVal)}</span>
          </div>
          ${cardSub ? `<div class="settings-card-note">${escapeHtml(cardSub)}</div>` : ""}
          <div class="kb-kv-row"><span>${escapeHtml(t("chat.sc_domains"))}</span><span class="mono muted">${escapeHtml(doms.join(", "))}</span></div>
          <div class="kb-kv-row"><span>${escapeHtml(t("chat.sc_url_template"))}</span><span class="mono muted truncate">${escapeHtml(tpl)}</span></div>
          <div class="form-row">
            <select class="select" data-sc-prov-cat="${escapeHtml(c.id)}">
              ${cats
                .map(
                  (ct) =>
                    `<option value="${escapeHtml(ct.id || "")}" ${chosenCat === ct.id ? "selected" : ""}>${escapeHtml(ct.label || ct.id || "")}</option>`
                )
                .join("")}
            </select>
            <input type="text" class="input" data-sc-prov-name="${escapeHtml(c.id)}" value="${escapeHtml(dispName)}" placeholder="${escapeHtml(t("chat.sc_provider_name_ph"))}" />
            <button type="button" class="btn primary" data-sc-save-prov="${escapeHtml(c.id)}" data-sc-tpl="${escapeHtml(tpl)}" data-sc-mode="${escapeHtml(modeVal)}" data-sc-dom="${escapeHtml(doms.join(","))}" data-sc-msg="${escapeHtml(msgId)}">${escapeHtml(t("chat.sc_save_provider"))}</button>
          </div>
        </div>
      `;
    }

    if (c.kind === "confirm_gate_card") {
      const isDanger = Boolean(d.danger);
      const requiresPin = Boolean(d.requires_pin);
      const maskedPreviews =
        d.masked_previews && typeof d.masked_previews === "object"
          ? Object.entries(d.masked_previews as Record<string, string>)
          : [];
      return `
        <div class="draft" data-settings-card-id="${escapeHtml(c.id)}" data-settings-card-msg="${escapeHtml(msgId)}" data-settings-card-kind="confirm_gate_card">
          <div class="draft-note">${escapeHtml(t("chat.sc_review_gate"))}</div>
          <div class="card-h">
            <b>${escapeHtml(cardTitle)}</b>
          </div>
          ${
            isDanger
              ? `<div class="banner danger">${icon("settings", "ico-sm")}<span>${escapeHtml(cardSub || t("chat.sc_perm_change"))}</span></div>`
              : cardSub
                ? `<div class="settings-card-note">${escapeHtml(cardSub)}</div>`
                : ""
          }
          ${
            maskedPreviews.length > 0
              ? `<div class="settings-card-keys">${maskedPreviews
                  .slice(0, 12)
                  .map(
                    ([k, v]) =>
                      `<span class="pill"><b>${escapeHtml(k)}</b><span>${escapeHtml(v)}</span></span>`
                  )
                  .join("")}</div>`
              : ""
          }
          <div class="form-row">
            ${
              requiresPin
                ? `<input type="password" class="input pin" data-sc-gate-pin="${escapeHtml(c.id)}" inputmode="numeric" maxlength="6" placeholder="${escapeHtml(t("profile.pin6_placeholder"))}" />`
                : ""
            }
            <button type="button" class="btn ${isDanger ? "danger" : "primary"}" data-sc-gate-confirm="${escapeHtml(c.id)}" data-sc-gate-token="${escapeHtml(c.confirm_token || "")}" data-sc-msg="${escapeHtml(msgId)}">${escapeHtml(t("common.confirm"))}</button>
            <button type="button" class="btn" data-sc-gate-cancel="${escapeHtml(c.id)}" data-sc-msg="${escapeHtml(msgId)}">${escapeHtml(t("common.cancel"))}</button>
          </div>
        </div>
      `;
    }

    if (c.kind === "locale_translate_card") {
      const targetLang = String(d.lang ?? "en");
      const targetLabel = String(d.label ?? targetLang);
      const targetDir = String(d.dir ?? "ltr");
      const modelId = String(d.model ?? "gemma-4-e4b");
      const privacyDesc = String(d.privacy ?? "");
      const missingCt = Number(d.missing ?? 0);
      const totalCt = Math.max(1, Number(d.total ?? 1));
      const translatedCt = Number(d.translated ?? 0);
      const isTranslatingHere = Boolean(
        state.i18nTranslating && state.i18nStatus?.job?.lang === targetLang
      );
      const doneCt = isTranslatingHere ? state.i18nTranslateCompleted : translatedCt;
      const goalCt = isTranslatingHere ? Math.max(1, state.i18nTranslateTotal || totalCt) : totalCt;
      const pct = Math.min(100, Math.max(0, Math.round((doneCt / goalCt) * 100)));

      return `
        <div class="card inset" data-settings-card-id="${escapeHtml(c.id)}" data-settings-card-msg="${escapeHtml(msgId)}" data-settings-card-kind="locale_translate_card">
          <div class="card-h">
            <b>${escapeHtml(cardTitle)}</b>
            <span class="pill end">${escapeHtml(targetLang)}${targetDir === "rtl" ? ` · ${escapeHtml(t("i18n.rtl_badge"))}` : ""}</span>
          </div>
          ${cardSub ? `<div class="settings-card-note">${escapeHtml(cardSub)}</div>` : ""}
          ${privacyDesc ? `<div class="settings-card-note">${escapeHtml(privacyDesc)}</div>` : ""}
          ${
            isTranslatingHere
              ? `
                <div class="kb-app-lang-progress">
                  <div class="meter" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}">
                    <b style="--v:${pct}%"></b>
                  </div>
                  <span class="badge soft">${escapeHtml(t("i18n.translating_pct", { done: doneCt, total: goalCt }))}</span>
                </div>
              `
              : ""
          }
          <div class="settings-card-actions mt-2">
            ${
              targetLang !== "en" && !isTranslatingHere
                ? `<button type="button" class="btn primary" data-sc-translate-lang="${escapeHtml(c.id)}" data-sc-lang="${escapeHtml(targetLang)}" data-sc-msg="${escapeHtml(msgId)}">${escapeHtml(missingCt > 0 && translatedCt > 0 ? t("i18n.sync_missing_n", { count: missingCt }) : t("i18n.translate_apply"))}</button>`
                : ""
            }
            ${
              (targetLang === "en" || translatedCt > 0) && !isTranslatingHere
                ? `<button type="button" class="btn" data-sc-switch-lang="${escapeHtml(c.id)}" data-sc-lang="${escapeHtml(targetLang)}" data-sc-msg="${escapeHtml(msgId)}">${escapeHtml(targetLabel)}</button>`
                : ""
            }
            ${
              isTranslatingHere
                ? `<button type="button" class="btn" data-sc-cancel-lang="${escapeHtml(c.id)}" data-sc-lang="${escapeHtml(targetLang)}" data-sc-msg="${escapeHtml(msgId)}">${escapeHtml(t("common.cancel"))}</button>`
                : ""
            }
          </div>
        </div>
      `;
    }

    if (c.kind === "news_settings_status_card") {
      const d = (c.data ?? {}) as Record<string, unknown>;
      const rawTopics = Array.isArray(d.topics) ? (d.topics as Array<Record<string, unknown>>) : [];
      const rawFeeds = Array.isArray(d.enabled_feeds)
        ? (d.enabled_feeds as Array<Record<string, unknown>>)
        : [];
      const rawOverrides = Array.isArray(d.personal_overrides)
        ? (d.personal_overrides as Array<Record<string, unknown>>)
        : [];
      const liveTopics = state.newsTopics.length > 0 ? state.newsTopics : rawTopics;
      const liveFeedsCount =
        state.newsSources.length > 0
          ? state.newsSources.filter((s) => s.feeds?.some((f) => f.enabled)).length
          : rawFeeds.length;
      const overridesCount =
        state.newsSources.length > 0
          ? state.newsSources.filter((s) => s.personal !== null && s.personal !== undefined).length
          : rawOverrides.length;
      return `
        <div class="card inset" data-settings-card-id="${escapeHtml(c.id)}" data-settings-card-kind="${escapeHtml(c.kind)}">
          <div class="card-h">
            <b>${escapeHtml(cardTitle)}</b>
            <button type="button" class="btn sm" data-open-news-settings="news-settings-manual">${escapeHtml(t("chat.ns_open_manual"))}</button>
          </div>
          ${cardSub ? `<div class="settings-card-note">${escapeHtml(cardSub)}</div>` : ""}
          <div class="ns-card-stats">
            <span class="badge">${escapeHtml(tCount("news.manual_topics_count", liveTopics.length))}</span>
            <span class="badge soft">${liveFeedsCount} feeds</span>
            <span class="badge">${overridesCount} trust overrides</span>
          </div>
          ${
            rawTopics.length > 0
              ? `<div class="ns-chip-list">${rawTopics
                  .slice(0, 8)
                  .map((tp) => `<span class="badge">${escapeHtml(String(tp.name ?? ""))}</span>`)
                  .join("")}</div>`
              : ""
          }
          ${
            rawFeeds.length > 0
              ? `<div class="ns-chip-list">${rawFeeds
                  .slice(0, 8)
                  .map(
                    (fd) =>
                      `<span class="badge soft">${escapeHtml(String(fd.title || fd.domain || ""))}</span>`
                  )
                  .join("")}</div>`
              : ""
          }
        </div>
      `;
    }

    if (c.kind === "news_topic_suggestions_card") {
      const d = (c.data ?? {}) as Record<string, unknown>;
      const suggestions = Array.isArray(d.suggestions)
        ? (d.suggestions as Array<Record<string, unknown>>)
        : [];
      const trackedNames = new Set(state.newsTopics.map((tp) => tp.name.trim().toLowerCase()));
      return `
        <div class="card inset" data-settings-card-id="${escapeHtml(c.id)}" data-settings-card-kind="${escapeHtml(c.kind)}">
          <div class="card-h">
            <b>${escapeHtml(cardTitle)}</b>
          </div>
          ${cardSub ? `<div class="settings-card-note">${escapeHtml(cardSub)}</div>` : ""}
          <div class="ns-list">
            ${suggestions
              .map((sg) => {
                const name = String(sg.name ?? "").trim();
                const normName = name.toLowerCase();
                const keywords = Array.isArray(sg.keywords)
                  ? sg.keywords.map((k) => String(k ?? "").trim()).filter(Boolean)
                  : [];
                const reason = String(sg.reason ?? "");
                const isTracked = trackedNames.has(normName);
                const isPending = Boolean(state.newsPendingTopicKeys[normName]);
                return `
                  <div class="ns-row">
                    <div class="ns-row-main">
                      <div class="ns-row-title">${escapeHtml(name)}</div>
                      <div class="ns-row-meta">${escapeHtml(
                        [reason, keywords.slice(0, 3).join(", ")].filter(Boolean).join(" · ")
                      )}</div>
                    </div>
                    <div class="ns-row-acts">
                      ${
                        isTracked
                          ? `<span class="badge ok">${escapeHtml(t("chat.ns_tracked_badge"))}</span>`
                          : `<button type="button" class="btn sm primary" data-ns-track-topic="${escapeHtml(name)}" data-ns-topic-kw="${escapeHtml(keywords.join(","))}" data-ns-card="${escapeHtml(c.id)}" data-ns-msg="${escapeHtml(msgId)}" ${isPending ? "disabled" : ""}>${escapeHtml(isPending ? t("chat.ns_tracking_pending") : t("chat.ns_track_topic"))}</button>`
                      }
                    </div>
                  </div>
                `;
              })
              .join("")}
          </div>
        </div>
      `;
    }

    if (c.kind === "news_source_suggestions_card") {
      const d = (c.data ?? {}) as Record<string, unknown>;
      const sourcesList = Array.isArray(d.sources)
        ? (d.sources as Array<Record<string, unknown>>)
        : [];
      const normDom = (val: string) => val.trim().toLowerCase().replace(/^www\./, "");
      const liveByDom = new Map(state.newsSources.map((s) => [normDom(s.domain), s]));
      return `
        <div class="card inset" data-settings-card-id="${escapeHtml(c.id)}" data-settings-card-kind="${escapeHtml(c.kind)}">
          <div class="card-h">
            <b>${escapeHtml(cardTitle)}</b>
          </div>
          ${cardSub ? `<div class="settings-card-note">${escapeHtml(cardSub)}</div>` : ""}
          <div class="ns-list">
            ${sourcesList
              .map((src) => {
                const dom = String(src.domain ?? "").trim();
                const domKey = normDom(dom);
                const live = liveByDom.get(domKey);
                const title = String(src.title || dom);
                const feedUrl = String(src.feed_url ?? live?.feeds?.[0]?.feed_url ?? "");
                const category = String(src.category ?? live?.category ?? "");
                const lang = String(src.language ?? live?.feeds?.[0]?.language ?? "");
                const eff = Number(live?.effective ?? src.effective ?? 0);
                const band = String(live?.band ?? src.band ?? "");
                const hasRss = Boolean(src.has_starter_rss || feedUrl || (live?.feeds?.length ?? 0) > 0);
                const isEnabled = live
                  ? Boolean(live.feeds?.some((f) => f.enabled))
                  : Boolean(src.enabled);
                const isPending = Boolean(state.newsPendingFeedKeys[domKey]);
                return `
                  <div class="ns-row">
                    <div class="ns-row-main">
                      <div class="ns-row-title">
                        <span>${escapeHtml(title)}</span>
                        ${title !== dom ? `<span class="ns-row-dom">${escapeHtml(dom)}</span>` : ""}
                      </div>
                      <div class="ns-row-meta">${escapeHtml(
                        [`${eff.toFixed(1)}/10 (${band})`, category, lang ? lang.toUpperCase() : ""]
                          .filter(Boolean)
                          .join(" · ")
                      )}</div>
                    </div>
                    <div class="ns-row-acts">
                      ${
                        hasRss
                          ? `<button type="button" class="btn sm ${isEnabled ? "" : "primary"}" data-ns-toggle-feed="${escapeHtml(dom)}" data-ns-feed-enable="${isEnabled ? "0" : "1"}" data-ns-feed-url="${escapeHtml(feedUrl)}" data-ns-feed-title="${escapeHtml(title)}" data-ns-card="${escapeHtml(c.id)}" data-ns-msg="${escapeHtml(msgId)}" ${isPending ? "disabled" : ""}>${escapeHtml(
                              isPending ? t("chat.ns_saving") : isEnabled ? t("chat.ns_disable_feed") : t("chat.ns_add_enable_feed")
                            )}</button>`
                          : `<span class="badge soft">${escapeHtml(`${eff.toFixed(1)}/10`)}</span>`
                      }
                    </div>
                  </div>
                `;
              })
              .join("")}
          </div>
        </div>
      `;
    }

    if (c.kind === "news_source_trust_card") {
      const d = (c.data ?? {}) as Record<string, unknown>;
      const dom = String(d.domain ?? "").trim();
      const domKey = dom.toLowerCase().replace(/^www\./, "");
      const live = state.newsSources.find((s) => s.domain.toLowerCase().replace(/^www\./, "") === domKey);
      const sysVal = Number(live?.system ?? d.system ?? 5.0);
      const rawPers = live?.personal ?? d.personal;
      const hasPers = rawPers !== null && rawPers !== undefined;
      const persVal = hasPers ? Number(rawPers) : sysVal;
      const effVal = hasPers ? 0.7 * sysVal + 0.3 * persVal : sysVal;
      const isPending = Boolean(state.newsPendingTrustDomains[domKey]);
      return `
        <div class="card inset" data-settings-card-id="${escapeHtml(c.id)}" data-settings-card-kind="${escapeHtml(c.kind)}">
          <div class="card-h">
            <b>${escapeHtml(cardTitle)}</b>
            <span class="badge">${escapeHtml(dom)}</span>
          </div>
          ${cardSub ? `<div class="settings-card-note">${escapeHtml(cardSub)}</div>` : ""}
          <div class="ns-trust-grid">
            <div class="ns-trust-readout">
              <span>${escapeHtml(t("chat.ns_system_score"))}: <b>${sysVal.toFixed(1)}</b></span>
              <span data-ns-trust-pers-label="${escapeHtml(c.id)}">${escapeHtml(t("chat.ns_personal_score"))}: <b>${hasPers ? persVal.toFixed(1) : "system"}</b></span>
              <span data-ns-trust-eff-label="${escapeHtml(c.id)}">${escapeHtml(t("chat.ns_effective_score"))}: <b>${effVal.toFixed(2)}/10</b></span>
            </div>
            <input
              type="range"
              min="0"
              max="10"
              step="0.5"
              value="${persVal.toFixed(1)}"
              class="ns-trust-slider"
              data-ns-trust-range="${escapeHtml(c.id)}"
              data-ns-trust-sys="${sysVal.toFixed(2)}"
              ${isPending ? "disabled" : ""}
            />
            <div class="chat-audit-row">
              <button type="button" class="btn primary sm" data-ns-save-trust="${escapeHtml(c.id)}" data-ns-domain="${escapeHtml(dom)}" data-ns-msg="${escapeHtml(msgId)}" ${isPending ? "disabled" : ""}>${escapeHtml(isPending ? t("chat.ns_saving") : t("chat.ns_apply_trust"))}</button>
              <button type="button" class="btn sm" data-ns-reset-trust="${escapeHtml(c.id)}" data-ns-domain="${escapeHtml(dom)}" data-ns-msg="${escapeHtml(msgId)}" ${isPending ? "disabled" : ""}>${escapeHtml(t("chat.ns_reset_trust"))}</button>
            </div>
          </div>
        </div>
      `;
    }

    if (c.kind === "news_add_feed_card") {
      const d = (c.data ?? {}) as Record<string, unknown>;
      const dom = String(d.domain ?? "").trim();
      const domKey = dom.toLowerCase().replace(/^www\./, "");
      const titleVal = String(d.title ?? dom);
      const isPending = Boolean(state.newsPendingFeedKeys[`add:${c.id}`] || (domKey && state.newsPendingFeedKeys[domKey]));
      const suggs = Array.isArray(d.suggestions)
        ? (d.suggestions as Array<Record<string, unknown>>).filter(
            (sg) => Boolean(sg.has_starter_rss || sg.feed_url)
          )
        : [];
      return `
        <div class="card inset" data-settings-card-id="${escapeHtml(c.id)}" data-settings-card-kind="${escapeHtml(c.kind)}">
          <div class="card-h">
            <b>${escapeHtml(cardTitle)}</b>
          </div>
          ${cardSub ? `<div class="settings-card-note">${escapeHtml(cardSub)}</div>` : ""}
          <div class="ns-add-feed-form">
            <input type="url" class="settings-card-input" placeholder="https://example.com/rss.xml" data-ns-feed-url-input="${escapeHtml(c.id)}" ${isPending ? "disabled" : ""} />
            <input type="text" class="settings-card-input" placeholder="Source title (optional)" value="${escapeHtml(titleVal)}" data-ns-feed-title-input="${escapeHtml(c.id)}" ${isPending ? "disabled" : ""} />
            <button type="button" class="btn primary sm" data-ns-submit-feed="${escapeHtml(c.id)}" data-ns-domain="${escapeHtml(dom)}" data-ns-msg="${escapeHtml(msgId)}" ${isPending ? "disabled" : ""}>${escapeHtml(isPending ? t("chat.ns_saving") : t("chat.ns_add_enable_feed"))}</button>
          </div>
          ${
            suggs.length > 0
              ? `<div class="ns-chip-list">${suggs
                  .slice(0, 6)
                  .map(
                    (sg) => {
                      const sgDom = String(sg.domain ?? "");
                      const sgKey = sgDom.trim().toLowerCase().replace(/^www\./, "");
                      const sgPending = Boolean(state.newsPendingFeedKeys[sgKey]);
                      return `<button type="button" class="pill" data-ns-toggle-feed="${escapeHtml(sgDom)}" data-ns-feed-enable="1" data-ns-feed-url="${escapeHtml(String(sg.feed_url ?? ""))}" data-ns-feed-title="${escapeHtml(String(sg.title || sgDom || ""))}" data-ns-card="${escapeHtml(c.id)}" data-ns-msg="${escapeHtml(msgId)}" ${sgPending ? "disabled" : ""}>${escapeHtml(String(sg.title || sgDom || ""))}</button>`;
                    }
                  )
                  .join("")}</div>`
              : ""
          }
        </div>
      `;
    }

    return `
      <div class="card inset" data-settings-card-id="${escapeHtml(c.id)}" data-settings-card-kind="${escapeHtml(c.kind)}">
        <div class="card-h">
          <b>${escapeHtml(cardTitle)}</b>
        </div>
        ${cardSub ? `<div class="settings-card-note">${escapeHtml(cardSub)}</div>` : ""}
      </div>
    `;
  };

  return `
    <div class="chat-section-block" data-settings-cards-msg="${escapeHtml(msgId)}">
      ${cards.map(renderCard).join("")}
    </div>
  `;
}

export function renderMessageBlock(
  msgId: string,
  role: string,
  content: string,
  model: string | null,
  sourceIdsJson: string | null,
  citedSources?: CitedSourcePreview[],
  proposals?: BrainProposalItem[],
  citationCheck?: CitationCheckEntry[],
  citationsOk?: number | null,
  citationsFlagged?: number | null,
  findings?: FindingItem[],
  brainSources?: BrainCitationItem[],
  emailCards?: ChatEmailCard[],
  answerMeta?: AnswerMeta,
  emailDraft?: MailComposeDraft,
  images?: ChatImageAttachment[],
  stagedFiles?: StagedSettingsFile[],
  uiCards?: SettingsUiCard[]
): string {
  let sourceIds: string[] = [];
  if (sourceIdsJson) {
    try {
      sourceIds = JSON.parse(sourceIdsJson) as string[];
    } catch {
      sourceIds = [];
    }
  }

  const trimmed = content.trim();
  const isErrorMsg =
    role === "assistant" &&
    (trimmed.startsWith("[err]") ||
      trimmed.startsWith("[error:") ||
      trimmed.startsWith("gemma stopped responding after 30 s.") ||
      trimmed.startsWith("models [offline]"));

  const plainErr = isErrorMsg ? formatPlainErrorMessage(content) : null;
  const debugExpanded = Boolean(state.expandedDebugMessages[msgId]);
  const formattedBody = plainErr
    ? escapeHtml(plainErr.summary)
    : formatCitationsInText(content, sourceIds, citationCheck, brainSources);

  if (role === "user") {
    const attached = Array.isArray(images) ? images : [];
    const attachedStaged = Array.isArray(stagedFiles) ? stagedFiles : [];
    if (attached.length === 0 && attachedStaged.length === 0) {
      return `<div class="msg-you">${formattedBody}</div>`;
    }
    const stagedBadgesHtml =
      attachedStaged.length > 0
        ? `<div class="composer-ctx">${attachedStaged
            .map(
              (sf) =>
                `<span class="pill accent">${icon("doc", "ico-sm")}<span class="truncate">${escapeHtml(sf.filename)} · ${escapeHtml(sf.summary)}</span></span>`
            )
            .join("")}</div>`
        : "";
    const imgsHtml =
      attached.length > 0
        ? `<div class="msg-you-images">${attached
            .map(
              (img, idx) => `
          <button
            type="button"
            class="msg-you-img-btn"
            data-preview-msg-id="${escapeHtml(msgId)}"
            data-preview-msg-img="${idx}"
            title="${escapeHtml(t("chat.preview_img_title", { name: img.name || t("chat.img_indexed", { idx: idx + 1 }) }))}"
            aria-label="${escapeHtml(t("chat.preview_img_title", { name: img.name || t("chat.img_indexed", { idx: idx + 1 }) }))}"
          >
            <img class="msg-you-img" src="${escapeHtml(img.data_url)}" alt="${escapeHtml(img.name || t("chat.img_attached_indexed", { idx: idx + 1 }))}" />
          </button>`
            )
            .join("")}</div>`
        : "";
    const trimmedContent = content.trim();
    const textHtml = trimmedContent
      ? `<div class="msg-you-text">${formattedBody}</div>`
      : "";
    return `<div class="msg-you ${attached.length > 0 ? "has-images" : ""}">${stagedBadgesHtml}${imgsHtml}${textHtml}</div>`;
  }

  const modelLabel = model ? escapeHtml(model) : "";
  const srcCountLabel =
    sourceIds.length > 0 ? ` · ${t("rail.src_count", { count: sourceIds.length })}` : "";
  const citeStatsLabel =
    typeof citationsOk === "number" || typeof citationsFlagged === "number"
      ? (citationsFlagged ?? 0) > 0
        ? t("chat.cite_stats_flagged", { ok: citationsOk ?? 0, flagged: citationsFlagged ?? 0 })
        : (citationsOk ?? 0) > 0
          ? t("chat.cite_stats", { ok: citationsOk })
          : ""
      : "";

  let readFooterHtml = "";
  if (role === "assistant" && !isErrorMsg && sourceIds.length > 0) {
    let totalSent = 0;
    let cutCount = 0;
    let manifestCount = 0;
    let expandedCount = 0;
    for (const sid of sourceIds) {
      const st = state.sourceStats[sid];
      if (st) {
        totalSent += st.chars_sent || st.chars_captured || 0;
        if (st.context_tier === "manifest") {
          manifestCount += 1;
        } else if (st.context_tier === "expanded") {
          expandedCount += 1;
          if (st.was_cut) cutCount += 1;
        } else if (st.was_cut) {
          cutCount += 1;
        }
      } else {
        const dbSrc = findSourceAcrossDetails(sid);
        const chars = dbSrc?.text_chars ?? 0;
        totalSent += Math.min(6000, chars);
        if (chars > 6000) cutCount += 1;
      }
    }
    const tierNotes: string[] = [];
    if (manifestCount > 0) tierNotes.push(t("chat.tier_manifest", { count: manifestCount }));
    if (expandedCount > 0) tierNotes.push(t("chat.tier_expanded", { count: expandedCount }));
    if (cutCount > 0 || (manifestCount === 0 && expandedCount === 0)) {
      tierNotes.push(t("chat.tier_cut", { count: cutCount }));
    }
    readFooterHtml = `<div class="msg-sources">${escapeHtml(
      tCount("chat.read_sources_footer", sourceIds.length, {
        chars: totalSent.toLocaleString(),
        tiers: tierNotes.join(" · "),
      })
    )}</div>`;
  }

  const originNow = state.activeDetail?.conversation.origin ?? "chat";
  const isSettingsConv = originNow === "settings" || originNow === "news_settings";
  const lastPromptHere =
    state.lastPromptByConv[state.activeDetail?.conversation.id ?? ""] ?? "";
  const showFlaggedRecovery = !isErrorMsg && (citationsFlagged ?? 0) > 0 && Boolean(lastPromptHere);
  const retryButtonHtml =
    isErrorMsg || showFlaggedRecovery
      ? `
      <div class="chat-audit-row">
        ${
          lastPromptHere
            ? `<button type="button" class="btn ${isErrorMsg ? "primary" : ""}" data-retry-prompt="${escapeHtml(lastPromptHere)}" data-msg-id="${escapeHtml(msgId)}">${escapeHtml(t("common.retry"))}</button>
               ${!isSettingsConv ? `<button type="button" class="btn" data-use-planck-prompt="${escapeHtml(lastPromptHere)}" data-msg-id="${escapeHtml(msgId)}">${escapeHtml(t("chat.use_planck"))}</button>` : ""}`
            : ""
        }
        ${
          isErrorMsg
            ? `<button type="button" class="btn" data-open-models-settings>${escapeHtml(t("chat.open_models_settings"))}</button>`
            : ""
        }
        ${
          plainErr && plainErr.rawDetail && plainErr.rawDetail !== plainErr.summary
            ? `<button type="button" class="btn" data-toggle-debug-msg="${escapeHtml(msgId)}">${escapeHtml(t("chat.debug"))}</button>`
            : ""
        }
      </div>
      ${
        debugExpanded && plainErr
          ? `<div class="card inset muted">${escapeHtml(plainErr.rawDetail)}</div>`
          : ""
      }
    `
      : "";

  const ytVideos: Array<{ videoId: string; title: string; url: string }> = [];
  const seenVidIds = new Set<string>();
  const addYtIfMatch = (rawUrl: string, rawTitle: string) => {
    const m = rawUrl.match(
      /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([A-Za-z0-9_-]{11})/
    );
    if (m && !seenVidIds.has(m[1])) {
      seenVidIds.add(m[1]);
      ytVideos.push({
        videoId: m[1],
        title: rawTitle || t("chat.yt_video", { id: m[1] }),
        url: `https://www.youtube.com/watch?v=${m[1]}`,
      });
    }
  };
  for (const f of findings ?? []) {
    addYtIfMatch(f.page_url || f.image_url, f.title);
  }
  for (const cs of citedSources ?? []) {
    addYtIfMatch(cs.url, cs.title);
  }
  const inlineYtMatches = content.matchAll(
    /https?:\/\/(?:www\.)?(?:youtube\.com\/watch\?v=|youtu\.be\/)([A-Za-z0-9_-]{11})/g
  );
  for (const m of inlineYtMatches) {
    addYtIfMatch(m[0], t("chat.yt_video", { id: m[1] }));
  }

  const embeddedVideosHtml =
    ytVideos.length > 0
      ? `
      <div class="chat-section-block">
        <div class="label">${escapeHtml(t("chat.videos"))} <span class="ct">${ytVideos.length}</span></div>
        <div class="video-grid">
          ${ytVideos
            .slice(0, 4)
            .map(
              (v) => `
            <div class="card chat-video-card">
              <iframe
                src="https://www.youtube-nocookie.com/embed/${escapeHtml(v.videoId)}"
                title="${escapeHtml(v.title)}"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowfullscreen
                loading="lazy"
              ></iframe>
              <div class="card-h">
                <span class="truncate" title="${escapeHtml(v.title)}">${escapeHtml(v.title)}</span>
                <button type="button" class="btn-text end" data-open-tab-url="${escapeHtml(v.url)}" data-open-tab-title="${escapeHtml(v.title)}">${escapeHtml(t("mail.open_tab"))}</button>
              </div>
            </div>
          `
            )
            .join("")}
        </div>
      </div>
    `
      : "";

  const nonVideoFindings = (findings ?? []).filter(
    (f) =>
      !/(?:youtube\.com\/watch\?v=|youtu\.be\/)/.test(
        f.page_url || f.image_url || ""
      )
  );

  const effectiveCitedSources: CitedSourcePreview[] = [
    ...(citedSources ?? []),
  ];
  const seenPreviewUrls = new Set(
    effectiveCitedSources.map((cs) => cs.url.trim()).filter(Boolean)
  );
  if (role === "assistant" && !isErrorMsg) {
    // 1. Hydrate from inline Markdown links `[Title](https://...)` (excluding YouTube already rendered as players)
    for (const mLink of content.matchAll(
      /\[([^\][]+)\]\((https?:\/\/[^\s)]+)\)/g
    )) {
      const lTitle = mLink[1].trim();
      const lUrl = mLink[2].trim();
      if (
        lUrl &&
        !seenPreviewUrls.has(lUrl) &&
        !/(?:youtube\.com\/watch\?v=|youtu\.be\/)/.test(lUrl)
      ) {
        seenPreviewUrls.add(lUrl);
        effectiveCitedSources.push({ url: lUrl, title: lTitle || lUrl });
      }
    }
    // 2. Hydrate from HTTP(S) `sourceIds` or matching `state.activeDetail.sources`
    for (const sid of sourceIds) {
      if (effectiveCitedSources.length >= 6) break;
      const dbSrc = findSourceAcrossDetails(sid);
      const candUrl = (
        dbSrc?.url || (sid.startsWith("http") ? sid : "")
      ).trim();
      const candTitle = (dbSrc?.title || candUrl).trim();
      if (
        candUrl.startsWith("http") &&
        !seenPreviewUrls.has(candUrl) &&
        !/(?:youtube\.com\/watch\?v=|youtu\.be\/)/.test(candUrl)
      ) {
        seenPreviewUrls.add(candUrl);
        effectiveCitedSources.push({ url: candUrl, title: candTitle || candUrl });
      }
    }
  }

  const pagePreviewCardsHtml =
    effectiveCitedSources.length > 0
      ? `
      <div class="chat-section-block">
        <div class="label">${escapeHtml(t("chat.page_previews"))} <span class="ct">${effectiveCitedSources.length}</span></div>
        <div class="preview-grid">
          ${effectiveCitedSources
            .slice(0, 6)
            .map((cs, idx) => {
              const pv = resolveRichCitedPreview(cs, answerMeta, findings);
              const dom = pv.domain || extractDomain(cs.url);
              const mediaHtml = pv.image_url
                ? `<div class="preview-card-media"><img class="preview-card-thumb" src="${escapeHtml(pv.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer" /></div>`
                : "";
              const snippetHtml = pv.snippet
                ? `<div class="preview-card-snippet">${escapeHtml(pv.snippet)}</div>`
                : "";
              const trustHtml =
                pv.trust !== null
                  ? `<span class="preview-card-trust">${pv.trust.toFixed(1)}/10</span>`
                  : "";
              return `
              <div class="card link preview-card" data-open-tab-url="${escapeHtml(cs.url)}" data-open-tab-title="${escapeHtml(pv.title)}">
                ${mediaHtml}
                <div class="preview-card-body">
                  <div class="preview-card-head">
                    <span class="preview-card-idx">${idx + 1}</span>
                    ${renderSiteFaviconHtml(cs.url, pv.favicon_url, "globe")}
                    <span class="preview-card-dom">${escapeHtml(dom)}</span>
                    ${trustHtml}
                    <button type="button" class="btn-text end" data-open-tab-url="${escapeHtml(cs.url)}" data-open-tab-title="${escapeHtml(pv.title)}">${escapeHtml(t("mail.open_tab"))}</button>
                  </div>
                  <div class="preview-card-title" title="${escapeHtml(pv.title)}">${escapeHtml(pv.title)}</div>
                  ${snippetHtml}
                  <div class="preview-card-url" title="${escapeHtml(cs.url)}">${escapeHtml(formatPreviewDisplayPath(cs.url))}</div>
                </div>
              </div>
            `;
            })
            .join("")}
        </div>
      </div>
    `
      : "";

  const proposalsHtml =
    proposals && proposals.length > 0
      ? `
      <div class="chat-section-block">
        ${proposals
          .map((p) => {
            const summaryPart = p.summary ? `, ${escapeHtml(p.summary.slice(0, 80))}` : "";
            const status = p.status ?? "pending";
            if (status === "accepted") {
              return `<div class="banner"><span>${escapeHtml(t("chat.stored_proposal", { type: p.type }))}<b>${escapeHtml(p.name)}</b>${summaryPart}</span><span class="badge">${escapeHtml(t("chat.accepted"))}</span></div>`;
            }
            if (status === "rejected") {
              return `<div class="banner"><span class="muted">${escapeHtml(t("chat.skipped_proposal", { type: p.type, name: p.name, summary: p.summary ? `, ${p.summary.slice(0, 80)}` : "" }))}</span><span class="badge soft">${escapeHtml(t("chat.rejected"))}</span></div>`;
            }
            return `
              <div class="card inset">
                <div class="card-h">
                  <span class="badge soft">${escapeHtml(t("chat.store_badge"))}</span>
                  <b>${escapeHtml(p.type)}: ${escapeHtml(p.name)}</b>
                  <span class="end">
                    <button type="button" class="btn primary" data-accept-proposal="${escapeHtml(p.proposal_id)}" data-proposal-msg="${escapeHtml(msgId)}">${escapeHtml(t("brain.accept"))}</button>
                    <button type="button" class="btn" data-reject-proposal="${escapeHtml(p.proposal_id)}" data-proposal-msg="${escapeHtml(msgId)}">${escapeHtml(t("brain.reject"))}</button>
                  </span>
                </div>
                ${summaryPart ? `<div class="muted">${escapeHtml(p.summary)}</div>` : ""}
              </div>
            `;
          })
          .join("")}
      </div>
    `
      : "";

  const findingsHtml =
    nonVideoFindings.length > 0
      ? `
      <div class="chat-section-block">
        <div class="label">${escapeHtml(t("chat.findings"))} <span class="ct">${nonVideoFindings.length}</span></div>
        <div class="findings">
          ${nonVideoFindings
            .map(
              (f) => `
            <div
              class="finding"
              data-open-tab-url="${escapeHtml(f.page_url || f.image_url)}"
              data-open-tab-title="${escapeHtml(f.title)}"
              title="${escapeHtml(f.title)}${f.price ? ` · ${escapeHtml(f.price)}` : ""}"
            >
              <img
                src="${escapeHtml(f.image_url)}"
                alt="${escapeHtml(f.title)}"
                loading="lazy"
              />
              <div>
                <div class="truncate">${escapeHtml(f.title)}</div>
                ${f.price ? `<div class="price">${escapeHtml(f.price)}</div>` : ""}
              </div>
            </div>
          `
            )
            .join("")}
        </div>
      </div>
    `
      : "";

  const emailCardsHtml = renderChatEmailCardsHtml(msgId, emailCards, sourceIds);
  const inlineComposeHtml =
    emailDraft && !isErrorMsg
      ? (() => {
          const liveDraft = (state.inlineChatDrafts[msgId] ??= {
            ...emailDraft,
          });
          return `
            <div class="chat-section-block">
              <div class="card inset chat-inline-compose">
                ${renderComposeEditorHtml(liveDraft, `chat-${msgId}`, {
                  mode: "inline",
                  title: t("mail.compose_heading"),
                })}
              </div>
            </div>
          `;
        })()
      : "";

  const citedBrainItems =
    role === "assistant" && !isErrorMsg && brainSources && brainSources.length > 0
      ? brainSources.filter(
          (bs) =>
            content.includes(`[${bs.cite_label}]`) ||
            (sourceIds.length === 0 && bs.b_index === 1)
        )
      : [];
  const brainCitationsListHtml =
    citedBrainItems.length > 0
      ? `
      <div class="msg-cite-row">
        <span>${escapeHtml(t("chat.brain_memory"))}</span>
        ${citedBrainItems
          .map(
            (bs) => `
          <button
            type="button"
            class="cite"
            data-brain-cite="${escapeHtml(bs.cite_label)}"
            data-brain-slug="${escapeHtml(bs.slug)}"
            title="${escapeHtml(t("chat.open_brain_card", { name: bs.name }))}"
          >${escapeHtml(bs.cite_label)} · ${escapeHtml(bs.name)}</button>
        `
          )
          .join("")}
      </div>
    `
      : "";

  const watchBtnHtml =
    role === "assistant" &&
    !isErrorMsg &&
    !isSettingsConv &&
    originNow !== "news_perspectives" &&
    !state.activeTabId.startsWith("news-lane:perspectives") &&
    msgId !== "mail-triage-overview"
      ? `<button type="button" class="btn-text" data-watch-msg="${escapeHtml(msgId)}" title="${escapeHtml(t("chat.watch_title"))}">${icon("watch", "ico-sm")}<span>${escapeHtml(t("chat.watch"))}</span></button>`
      : "";
  const isMultiStepTurn =
    role === "assistant" &&
    !isErrorMsg &&
    msgId !== "mail-triage-overview" &&
    (sourceIds.length >= 2 || (emailCards && emailCards.length > 0) || Boolean(answerMeta));
  const saveSkillMsgBtnHtml = isMultiStepTurn
    ? `<button type="button" class="btn-text" data-save-msg-skill="${escapeHtml(msgId)}" title="${escapeHtml(t("chat.save_as_skill_title"))}">${escapeHtml(t("chat.save_as_skill"))}</button>`
    : "";
  const savedEvalId = state.savedEvalByMsgId[msgId] ?? "";
  const saveEvalBtnHtml =
    role === "assistant" && msgId !== "mail-triage-overview"
      ? savedEvalId
        ? `<span class="badge soft" title="${escapeHtml(t("chat.saved_eval_title", { id: savedEvalId }))}">${escapeHtml(t("chat.saved_eval"))}</span>`
        : `<button type="button" class="btn-text" data-save-failure-eval="${escapeHtml(msgId)}" title="${escapeHtml(t("chat.save_failure_eval_title"))}">${escapeHtml(t("chat.save_failure_eval"))}</button>`
      : "";
  const msgActBtns = [saveSkillMsgBtnHtml, saveEvalBtnHtml, watchBtnHtml].filter(Boolean).join("");

  const answerAuditHtml = renderAnswerMetaSectionHtml(msgId, answerMeta);

  if (isErrorMsg) {
    return `
      <div class="msg-bot msg-error">
        <div class="msg-meta">
          <span>${escapeHtml(t("chat.assistant"))}</span>
          ${modelLabel ? `<span>· ${modelLabel}</span>` : ""}
          ${saveEvalBtnHtml ? `<span class="msg-meta-acts">${saveEvalBtnHtml}</span>` : ""}
        </div>
        <div class="banner danger">
          <span>${formattedBody}</span>
        </div>
        ${retryButtonHtml}
      </div>
    `;
  }

  return `
    <div class="msg-bot" data-msg-id="${escapeHtml(msgId)}">
      <div class="msg-meta">
        <span>${escapeHtml(t("chat.assistant"))}</span>
        ${modelLabel ? `<span>· ${modelLabel}</span>` : ""}
        ${srcCountLabel ? `<span>${escapeHtml(srcCountLabel)}</span>` : ""}
        ${citeStatsLabel ? `<span>${escapeHtml(citeStatsLabel)}</span>` : ""}
        ${msgActBtns ? `<span class="msg-meta-acts">${msgActBtns}</span>` : ""}
      </div>
      <div class="msg-text">${formattedBody}</div>
      ${answerAuditHtml}
      ${readFooterHtml}
      ${brainCitationsListHtml}
      ${embeddedVideosHtml}
      ${emailCardsHtml}
      ${inlineComposeHtml}
      ${renderSettingsUiCardsHtml(msgId, uiCards)}
      ${findingsHtml}
      ${pagePreviewCardsHtml}
      ${proposalsHtml}
    </div>
  `;
}

function renderAnswerMetaSectionHtml(
  msgId: string,
  meta?: AnswerMeta
): string {
  if (!meta) return "";
  const conf10 = meta.confidence10 ?? 0;
  const pct = Math.max(0, Math.min(100, Math.round(conf10 * 10)));
  const isLowBand =
    meta.band === "low" || meta.band === "sceptical" || (meta.conflicts?.length ?? 0) > 0;
  const rolesLine = meta.models_used
    ? t("chat.meta_roles", {
        planner: meta.models_used.planner,
        reader: meta.models_used.reader,
        analyzer: meta.models_used.analyzer,
      })
    : "";

  const divHtml = meta.divergence
    ? `<div class="banner warn">${escapeHtml(
        t("chat.meta_divergence", {
          value: String(meta.divergence.system_value ?? "n/a"),
          conf: meta.divergence.system_confidence.toFixed(1),
          band: meta.divergence.system_band,
        })
      )}</div>`
    : "";

  const defaultOpenExplain =
    meta.band === "low" || meta.band === "sceptical" || (meta.conflicts?.length ?? 0) > 0;
  const explainOpen = state.expandedExplainMessages[msgId] ?? defaultOpenExplain;
  const inDepthOpen = Boolean(state.expandedInDepthMessages[msgId]);

  const explainBodyHtml = explainOpen
    ? `
      <div class="card inset">
        <div class="muted">${escapeHtml(t("chat.meta_steps", { steps: meta.steps.join(" -> ") }))}</div>
        ${
          meta.items && meta.items.length > 0
            ? `<div class="table-wrap"><table class="table"><thead><tr><th class="num">${escapeHtml(t("chat.col_delta"))}</th><th>${escapeHtml(t("chat.col_reason"))}</th></tr></thead><tbody>${meta.items
                .map(
                  ([lbl, val]) =>
                    `<tr><td class="num">${val >= 0 ? `+${val.toFixed(1)}` : val.toFixed(1)}</td><td>${escapeHtml(lbl)}</td></tr>`
                )
                .join("")}</tbody></table></div>`
            : ""
        }
        ${
          meta.sources && meta.sources.length > 0
            ? `<div class="table-wrap"><table class="table"><thead><tr><th>${escapeHtml(t("chat.col_role"))}</th><th>${escapeHtml(t("brain.col_domain"))}</th><th>${escapeHtml(t("chat.col_family"))}</th><th class="num">${escapeHtml(t("chat.col_sys"))}</th><th class="num">${escapeHtml(t("chat.col_you"))}</th><th class="num">${escapeHtml(t("chat.col_eff"))}</th><th>${escapeHtml(t("news.col_category"))}</th><th>${escapeHtml(t("chat.col_trust"))}</th></tr></thead><tbody>${meta.sources
                .map((s) => {
                  const st = s.trust;
                  const youStr = st.personal !== null && st.personal !== undefined ? st.personal.toFixed(1) : "-";
                  const confFlag = st.conflict ? ` <span class="badge soft">${escapeHtml(t("news.conflict_badge"))}</span>` : "";
                  return `<tr><td>${escapeHtml(s.role)}</td><td><button type="button" class="btn-text" data-open-tab-url="${escapeHtml(s.url)}" data-open-tab-title="${escapeHtml(s.title)}">${escapeHtml(s.domain)}</button>${confFlag}</td><td>${escapeHtml(st.family)}</td><td class="num">${st.system.toFixed(0)}</td><td class="num">${escapeHtml(youStr)}</td><td class="num"><b>${st.effective.toFixed(1)}</b></td><td>${escapeHtml(st.category)}</td><td><button type="button" class="btn-text" data-news-trust-msg="${escapeHtml(msgId)}" data-news-trust-dom="${escapeHtml(s.domain)}" data-news-trust-delta="2">+</button> <button type="button" class="btn-text" data-news-trust-msg="${escapeHtml(msgId)}" data-news-trust-dom="${escapeHtml(s.domain)}" data-news-trust-delta="-2">-</button></td></tr>`;
                })
                .join("")}</tbody></table></div>`
            : ""
        }
      </div>
    `
    : "";

  const inDepthBodyHtml =
    inDepthOpen && meta.passages && meta.passages.length > 0
      ? `
      <div class="card inset">
        ${meta.passages
          .map(
            (p) => `
          <div class="source-row">
            <div class="source-row-top">
              <b class="t">${escapeHtml(p.domain)}</b>
              <button type="button" class="btn-text" data-open-tab-url="${escapeHtml(p.url)}" data-open-tab-title="${escapeHtml(p.title || p.domain)}">${escapeHtml(t("mail.open_tab"))}</button>
            </div>
            <div class="muted">${escapeHtml(p.text)}</div>
          </div>`
          )
          .join("")}
      </div>
    `
      : "";

  return `
    <div class="chat-audit">
      <div class="chat-audit-row">
        <span class="conf ${isLowBand ? "low" : ""}" style="--c:${pct}%"><i></i>${conf10.toFixed(1)}/10 · ${escapeHtml(meta.band_label)}</span>
        ${rolesLine ? `<span>${escapeHtml(rolesLine)}</span>` : ""}
      </div>
      ${divHtml}
      ${meta.privacy_disclosure ? `<div class="muted">${escapeHtml(meta.privacy_disclosure)}</div>` : ""}
      <div class="chat-audit-row">
        <button type="button" class="btn-text" data-toggle-explain-msg="${escapeHtml(msgId)}">${escapeHtml(explainOpen ? t("chat.hide_how") : t("chat.show_how"))}</button>
        ${
          meta.passages && meta.passages.length > 0
            ? `<button type="button" class="btn-text" data-toggle-indepth-msg="${escapeHtml(msgId)}">${escapeHtml(inDepthOpen ? tCount("chat.hide_in_depth", meta.passages.length) : tCount("chat.show_in_depth", meta.passages.length))}</button>`
            : ""
        }
      </div>
      ${explainBodyHtml}
      ${inDepthBodyHtml}
    </div>
  `;
}

function renderChatEmailCardsHtml(
  msgId: string,
  emailCards: ChatEmailCard[] | undefined,
  sourceIds: string[]
): string {
  const cards: ChatEmailCard[] = [...(emailCards ?? [])];
  const seenIds = new Set(cards.map((c) => c.message_id));

  for (const sid of sourceIds) {
    if (sid.startsWith("mail:")) {
      const mid = sid.slice(5).trim();
      if (mid && !seenIds.has(mid)) {
        const cached = state.mailMessageDetails[mid];
        const mObj = (cached?.message ?? cached) as Record<string, unknown> | undefined;
        if (mObj && mObj.id) {
          seenIds.add(mid);
          const parts = (mObj.parts ?? {}) as Record<string, string>;
          cards.push({
            message_id: mid,
            source_id: sid,
            subject: String(mObj.subject ?? t("brain.no_subject")),
            from_name: String(mObj.from_name ?? ""),
            from_addr: String(mObj.from_addr ?? ""),
            date: Number(mObj.date ?? 0),
            label: String(mObj.label ?? "email"),
            snippet: String(mObj.snippet ?? ""),
            body_text: String(parts.new || mObj.body_text || ""),
            quoted_text: String(parts.quote || ""),
            attachments: (mObj.attachments as ChatEmailCard["attachments"]) ?? [],
          });
        }
      }
    }
  }

  if (cards.length === 0) return "";

  return `
    <div class="chat-section-block">
      <div class="label">${escapeHtml(t("chat.referenced_emails"))} <span class="ct">${cards.length}</span></div>
      ${cards
        .map((ec) => {
          const expandKey = `${msgId}:${ec.message_id}`;
          const isExpanded = Boolean(state.expandedChatEmails[expandKey]);
          const fromDisp = ec.from_name
            ? `${ec.from_name} <${ec.from_addr}>`
            : ec.from_addr;
          const atts = ec.attachments ?? [];
          const attsHtml =
            atts.length > 0
              ? `
            <div class="chat-audit-row">
              <span class="muted">${escapeHtml(t("mail.attachments_n", { count: atts.length }))}</span>
              ${atts
                .map((att) => {
                  const attKey = `${ec.message_id}:${att.part_id}`;
                  const previewObj = state.previewedAttachments[attKey];
                  const sizeKb = Math.max(1, Math.round((att.size || 0) / 1024));
                  return `
                    <span class="pill">
                      <span>${escapeHtml(att.filename)} (${escapeHtml(t("mail.att_kb", { size: sizeKb }))})</span>
                      <button
                        type="button"
                        class="btn-text"
                        data-chat-preview-att="${escapeHtml(ec.message_id)}"
                        data-part-id="${escapeHtml(String(att.part_id))}"
                      >${escapeHtml(previewObj ? t("mail.att_hide") : t("chat.att_preview"))}</button>
                      <button
                        type="button"
                        class="btn-text"
                        data-chat-download-att="${escapeHtml(ec.message_id)}"
                        data-part-id="${escapeHtml(String(att.part_id))}"
                      >${escapeHtml(t("chat.download"))}</button>
                    </span>
                  `;
                })
                .join("")}
            </div>
            ${atts
              .map((att) => {
                const attKey = `${ec.message_id}:${att.part_id}`;
                const prev = state.previewedAttachments[attKey];
                if (!prev || !prev.data_url) return "";
                if (prev.mime.startsWith("image/")) {
                  return `<img class="attach-img" src="${escapeHtml(prev.data_url)}" alt="${escapeHtml(prev.filename)}" />`;
                }
                return `<embed class="attach-embed" type="${escapeHtml(prev.mime)}" src="${escapeHtml(prev.data_url)}" />`;
              })
              .join("")}
          `
              : "";

          return `
            <div class="card inset">
              <div class="card-h">
                <b>${escapeHtml(ec.subject)}</b>
                <span class="badge soft">${escapeHtml(ec.label)}</span>
                <span class="end">
                  <button
                    type="button"
                    class="btn-text"
                    data-chat-toggle-email="${escapeHtml(expandKey)}"
                    data-email-mid="${escapeHtml(ec.message_id)}"
                  >${escapeHtml(isExpanded ? t("chat.hide_body") : t("chat.show_body"))}</button>
                  <button
                    type="button"
                    class="btn-text"
                    data-chat-open-email-tab="${escapeHtml(ec.message_id)}"
                    data-email-subj="${escapeHtml(ec.subject)}"
                  >${escapeHtml(t("mail.open_tab"))}</button>
                  ${
                    ec.can_unsubscribe || ec.label === "promotion"
                      ? `<button
                    type="button"
                    class="btn-text"
                    data-chat-unsub-email="${escapeHtml(ec.message_id)}"
                    data-unsub-sender="${escapeHtml(ec.from_name || ec.from_addr)}"
                  >${escapeHtml(t("mail.unsubscribe"))}</button>`
                      : ""
                  }
                </span>
              </div>
              <div class="muted">${escapeHtml(t("chat.from_addr_line", { sender: fromDisp }))}</div>
              ${
                isExpanded
                  ? `<div class="chat-inline-email"><pre>${escapeHtml(ec.body_text || ec.snippet || t("chat.empty_body"))}${ec.quoted_text ? `\n\n--- ${escapeHtml(t("chat.quoted_thread"))} ---\n${escapeHtml(ec.quoted_text)}` : ""}</pre></div>`
                  : `<div class="muted truncate">${escapeHtml(ec.snippet || ec.body_text.slice(0, 160))}</div>`
              }
              ${attsHtml}
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderTaskCardBlock(task: AgentTaskCard): string {
  const isRunning =
    task.status === "running" || task.status === "waiting_confirm";
  const stopBtnHtml = isRunning
    ? `<button type="button" class="btn" data-task-stop="${escapeHtml(task.id)}" data-stop-token="${escapeHtml(task.stop_token)}">${escapeHtml(t("chat.stop"))}</button>`
    : "";

  const stepsHtml = (task.steps ?? [])
    .map((step) => {
      if (step.kind === "send_gate") {
        const summary = step.action_summary || step.text;
        const ap = (step.action_payload ?? {}) as Record<string, unknown>;
        const apUrl = typeof ap.url === "string" && ap.url.startsWith("http") ? ap.url : "";
        const apMid = typeof ap.message_id === "string" ? ap.message_id : "";
        const apSubj = typeof ap.subject === "string" ? ap.subject : t("common.mail");
        if (step.status === "waiting_confirm") {
          return `
            <div class="draft">
              <div class="gate">${escapeHtml(t("chat.send_gate_req"))}</div>
              <div>${escapeHtml(summary)}</div>
              <div class="acts">
                <button
                  type="button"
                  class="btn primary"
                  data-task-confirm="${escapeHtml(task.id)}"
                  data-step-id="${escapeHtml(step.id)}"
                  data-confirm-token="${escapeHtml(step.confirm_token ?? "")}"
                >${escapeHtml(t("common.confirm"))}</button>
                ${
                  apUrl
                    ? `<button type="button" class="btn" data-open-tab-url="${escapeHtml(apUrl)}" data-open-tab-title="${escapeHtml(String(ap.label || ap.element_label || t("chat.open_url_fallback")))}">${escapeHtml(t("chat.open_link"))}</button>`
                    : ""
                }
                ${
                  apMid
                    ? `<button type="button" class="btn-text" data-chat-open-email-tab="${escapeHtml(apMid)}" data-email-subj="${escapeHtml(apSubj)}">${escapeHtml(t("chat.open_email"))}</button>`
                    : ""
                }
                <button
                  type="button"
                  class="btn"
                  data-task-cancel="${escapeHtml(task.id)}"
                  data-step-id="${escapeHtml(step.id)}"
                >${escapeHtml(t("common.cancel"))}</button>
              </div>
            </div>
          `;
        }
        return `<div class="stream-step">${escapeHtml(t("chat.send_gate_status", { status: step.status, summary }))}</div>`;
      }
      const prefix = step.status === "running" ? t("chat.step_now") : t("chat.step_done");
      return `<div class="stream-step">${escapeHtml(prefix)} · ${escapeHtml(step.text)}</div>`;
    })
    .join("");

  const activeSourceIds = (state.activeDetail?.sources ?? []).map((s) => s.id);
  const resultHtml = task.result_md
    ? `<div class="msg-text">${formatCitationsInText(task.result_md, activeSourceIds)}</div>`
    : "";

  const unsubStep = (task.steps ?? []).find(
    (s) =>
      s.kind === "send_gate" &&
      (s.action_payload as Record<string, unknown> | undefined)?.action_type === "mail_unsubscribe" &&
      typeof (s.action_payload as Record<string, unknown> | undefined)?.sender === "string"
  );
  const completedSenderEmail =
    task.status === "completed" && unsubStep
      ? String((unsubStep.action_payload as Record<string, unknown>).sender ?? "")
      : "";
  const archiveFollowupHtml = completedSenderEmail
    ? `<button type="button" class="btn" data-task-archive-sender="${escapeHtml(task.id)}" data-archive-sender-email="${escapeHtml(completedSenderEmail)}">${escapeHtml(t("chat.archive_from_sender", { sender: completedSenderEmail }))}</button>`
    : "";
  const saveTaskSkillBtnHtml =
    task.status === "completed"
      ? `<button type="button" class="btn" data-save-task-skill="${escapeHtml(task.id)}">${escapeHtml(t("chat.save_as_skill"))}</button>`
      : "";
  const taskFooterActsHtml =
    archiveFollowupHtml || saveTaskSkillBtnHtml
      ? `<div class="acts mt-2">${archiveFollowupHtml}${saveTaskSkillBtnHtml}</div>`
      : "";

  return `
    <div class="card" data-task-card="${escapeHtml(task.id)}">
      <div class="card-h">
        <b>${escapeHtml(t("chat.task_header", { agent: task.agent }))}</b>
        <span class="badge soft">${escapeHtml(task.status)}</span>
        <span class="end muted truncate">${escapeHtml(task.goal)}</span>
        ${stopBtnHtml}
      </div>
      <div class="stream">${stepsHtml}</div>
      ${resultHtml}
      ${taskFooterActsHtml}
    </div>
  `;
}

function renderMarkdownTablesInHtml(escapedWithCites: string): string {
  const lines = escapedWithCites.split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();
    const nextLine = (lines[i + 1] ?? "").trim();
    if (
      line.startsWith("|") &&
      line.endsWith("|") &&
      nextLine.startsWith("|") &&
      nextLine.includes("---")
    ) {
      const parseRow = (r: string) =>
        r
          .slice(1, -1)
          .split("|")
          .map((c) => c.trim().replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>"));
      const headers = parseRow(line);
      i += 2;
      const bodyRows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|") && lines[i].trim().endsWith("|")) {
        bodyRows.push(parseRow(lines[i].trim()));
        i += 1;
      }
      const thead = `<thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>`;
      const tbody = `<tbody>${bodyRows
        .map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`)
        .join("")}</tbody>`;
      out.push(`<div class="table-wrap"><table class="table">${thead}${tbody}</table></div>`);
      continue;
    }
    out.push(lines[i]);
    i += 1;
  }
  return out.join("\n");
}

export function formatCitationsInText(
  text: string,
  sourceIds: string[],
  citationCheck?: CitationCheckEntry[],
  brainSources?: BrainCitationItem[]
): string {
  const unsourcedLbl = escapeHtml(t("chat.cite_unsourced"));
  const escaped = escapeHtml(text).replace(
    /\[unsourced\]/g,
    `<button type="button" class="cite flagged" data-flagged-unsourced="1" title="${escapeHtml(t("chat.cite_outside"))}">${unsourcedLbl}</button>`
  );
  const withSrcCites = escaped.replace(/\[(\d+)\]/g, (_match, digits) => {
    const idx = Number(digits);
    const outOfRangeCheck = citationCheck?.find(
      (c) => c.n === idx && c.out_of_range
    );
    if (
      idx < 1 ||
      (sourceIds.length > 0 && idx > sourceIds.length) ||
      outOfRangeCheck
    ) {
      return `<button type="button" class="cite flagged" data-flagged-unsourced="1" title="${escapeHtml(t("chat.cite_idx_outside", { idx, total: sourceIds.length }))}">${unsourcedLbl}</button>`;
    }
    const sourceId = sourceIds[idx - 1] ?? "";
    const flaggedEntries = (citationCheck ?? []).filter(
      (c) => c.n === idx && !c.ok
    );
    if (flaggedEntries.length > 0) {
      const missingItems = Array.from(
        new Set(flaggedEntries.flatMap((e) => e.missing ?? []))
      );
      const tooltip = t("chat.cite_missing", { idx, missing: missingItems.join(", ") });
      return `<button type="button" class="cite flagged" data-citation-idx="${idx}" data-citation-src="${escapeHtml(sourceId)}" title="${escapeHtml(tooltip)}">${idx}?</button>`;
    }
    return `<button type="button" class="cite" data-citation-idx="${idx}" data-citation-src="${escapeHtml(sourceId)}">${idx}</button>`;
  });

  const withBrainCites = withSrcCites.replace(/\[B(\d+)\]/g, (_match, digits) => {
    const bIdx = Number(digits);
    const bKey = `B${bIdx}`;
    const outOfRangeCheck = citationCheck?.find(
      (c) => String(c.n) === bKey && c.out_of_range
    );
    const maxB = brainSources?.length ?? 0;
    if (bIdx < 1 || (maxB > 0 && bIdx > maxB) || outOfRangeCheck) {
      return `<button type="button" class="cite flagged" data-flagged-unsourced="1" title="${escapeHtml(t("chat.cite_brain_outside", { key: bKey, total: maxB }))}">${unsourcedLbl}</button>`;
    }
    const bs = brainSources?.[bIdx - 1];
    const slug = bs?.slug ?? "";
    const labelName = bs?.name ?? bKey;
    const flaggedEntries = (citationCheck ?? []).filter(
      (c) => String(c.n) === bKey && !c.ok
    );
    if (flaggedEntries.length > 0) {
      const missingItems = Array.from(
        new Set(flaggedEntries.flatMap((e) => e.missing ?? []))
      );
      const tooltip = t("chat.cite_brain_missing", {
        key: bKey,
        name: labelName,
        missing: missingItems.join(", "),
      });
      return `<button type="button" class="cite flagged" data-brain-cite="${escapeHtml(bKey)}" data-brain-slug="${escapeHtml(slug)}" aria-label="${escapeHtml(tooltip)}" title="${escapeHtml(tooltip)}">${escapeHtml(bKey)}?</button>`;
    }
    return `<button type="button" class="cite" data-brain-cite="${escapeHtml(bKey)}" data-brain-slug="${escapeHtml(slug)}" aria-label="${escapeHtml(t("chat.open_brain_card", { name: labelName }))}">${escapeHtml(bKey)}</button>`;
  });
  const withMdLinksAndBold = withBrainCites
    .replace(
      /\[([^\][]+)\]\((satzmail:\/\/message\/([A-Za-z0-9_.-]+)[^\s)]*)\)/g,
      (_m, labelTxt, _fullUrl, mid) =>
        `<button type="button" class="btn-text inline-page-link" data-chat-open-email-tab="${mid}" data-email-subj="${labelTxt}" title="${escapeHtml(t("chat.open_email_tab_title"))}">${labelTxt} ↗</button>`
    )
    .replace(
      /\[([^\][]+)\]\((https?:\/\/[^\s)]+)\)/g,
      (_m, labelTxt, urlTxt) =>
        `<button type="button" class="btn-text inline-page-link" data-open-tab-url="${urlTxt}" data-open-tab-title="${labelTxt}" aria-label="${escapeHtml(t("chat.open_url_tab_title", { url: urlTxt }))}">${labelTxt} ↗</button>`
    )
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  return renderMarkdownTablesInHtml(withMdLinksAndBold);
}

function bindChatEvents(container: HTMLElement, actions: ChatActions): void {
  const activeConvId = state.activeDetail?.conversation.id ?? "";
  const originNow = state.activeDetail?.conversation.origin ?? "chat";
  const isSettingsConv = originNow === "settings" || originNow === "news_settings";
  const input = container.querySelector(
    "#chat-composer-input"
  ) as HTMLTextAreaElement | HTMLInputElement | null;
  const submit = () => {
    const val = input?.value.trim() ?? "";
    const pendingImages = activeConvId
      ? (state.pendingChatImagesByConv[activeConvId] ?? [])
      : [];
    const pendingStaged = activeConvId
      ? (state.pendingStagedFilesByConv[activeConvId] ?? [])
      : [];
    if (
      (!val && pendingImages.length === 0 && pendingStaged.length === 0) ||
      isConvStreaming(activeConvId)
    ) {
      return;
    }
    if (input) {
      input.value = "";
      input.style.height = "";
    }
    if (activeConvId && pendingImages.length > 0) {
      delete state.pendingChatImagesByConv[activeConvId];
    }
    if (activeConvId && pendingStaged.length > 0) {
      delete state.pendingStagedFilesByConv[activeConvId];
    }
    state.chatImageNotice = "";
    state.composerModelMenuOpen = false;
    actions.onSendMessage(val, pendingImages, pendingStaged);
  };

  input?.addEventListener("keydown", (e) => {
    const ke = e as KeyboardEvent;
    if (ke.key === "Enter" && !ke.shiftKey) {
      ke.preventDefault();
      submit();
    }
  });

  const composerBox = container.querySelector(
    "#chat-composer-box"
  ) as HTMLElement | null;
  const fileInput = container.querySelector(
    "#chat-image-file-input"
  ) as HTMLInputElement | null;

  container
    .querySelector("#chat-add-image-btn")
    ?.addEventListener("click", () => {
      if (isConvStreaming(activeConvId)) return;
      state.chatImageNotice = "";
      fileInput?.click();
    });

  fileInput?.addEventListener("change", () => {
    const files = Array.from(fileInput.files ?? []);
    fileInput.value = "";
    if (!activeConvId || files.length === 0) return;
    const cfgFiles = isSettingsConv
      ? files.filter((f) => isSupportedSettingsConfigFile(f))
      : [];
    const imgFiles = files.filter((f) => !cfgFiles.includes(f));
    if (imgFiles.length > 0) {
      void addChatImageFiles(imgFiles, activeConvId, container, actions);
    }
    if (cfgFiles.length > 0 && actions.onStageConfigFiles) {
      void actions.onStageConfigFiles(cfgFiles, activeConvId);
    }
  });

  (composerBox ?? input)?.addEventListener("paste", (e) => {
    const ce = e as ClipboardEvent;
    const files = extractImageFilesFromDataTransfer(ce.clipboardData);
    const cfgFiles = isSettingsConv
      ? extractSettingsConfigFilesFromDataTransfer(ce.clipboardData)
      : [];
    if (
      (files.length === 0 && cfgFiles.length === 0) ||
      !activeConvId ||
      isConvStreaming(activeConvId)
    ) {
      return;
    }
    const plainText = ce.clipboardData?.getData("text/plain") ?? "";
    if (!plainText.trim()) {
      ce.preventDefault();
    }
    ce.stopPropagation();
    if (files.length > 0) {
      void addChatImageFiles(files, activeConvId, container, actions);
    }
    if (cfgFiles.length > 0 && actions.onStageConfigFiles) {
      void actions.onStageConfigFiles(cfgFiles, activeConvId);
    }
  });

  const dropTarget =
    (container.querySelector(".chat-stage") as HTMLElement | null) ??
    composerBox;
  let dragDepth = 0;
  const hasDraggedFiles = (de: DragEvent): boolean => {
    const types = de.dataTransfer?.types;
    if (!types) return false;
    return Array.from(types).includes("Files");
  };

  dropTarget?.addEventListener("dragenter", (e) => {
    const de = e as DragEvent;
    if (!hasDraggedFiles(de) || isConvStreaming(activeConvId)) return;
    de.preventDefault();
    dragDepth += 1;
    composerBox?.classList.add("drag-over");
  });

  dropTarget?.addEventListener("dragover", (e) => {
    const de = e as DragEvent;
    if (!hasDraggedFiles(de) || isConvStreaming(activeConvId)) return;
    de.preventDefault();
    if (de.dataTransfer) de.dataTransfer.dropEffect = "copy";
    composerBox?.classList.add("drag-over");
  });

  dropTarget?.addEventListener("dragleave", (e) => {
    const de = e as DragEvent;
    if (!hasDraggedFiles(de)) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) {
      composerBox?.classList.remove("drag-over");
    }
  });

  dropTarget?.addEventListener("drop", (e) => {
    const de = e as DragEvent;
    dragDepth = 0;
    composerBox?.classList.remove("drag-over");
    if (!activeConvId || isConvStreaming(activeConvId)) return;
    const files = extractImageFilesFromDataTransfer(de.dataTransfer ?? null);
    const cfgFiles = isSettingsConv
      ? extractSettingsConfigFilesFromDataTransfer(de.dataTransfer ?? null)
      : [];
    if (files.length === 0 && cfgFiles.length === 0) return;
    de.preventDefault();
    if (files.length > 0) {
      void addChatImageFiles(files, activeConvId, container, actions);
    }
    if (cfgFiles.length > 0 && actions.onStageConfigFiles) {
      void actions.onStageConfigFiles(cfgFiles, activeConvId);
    }
  });

  container.querySelectorAll("[data-remove-staged-file]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!activeConvId || isConvStreaming(activeConvId)) return;
      const stId = (btn as HTMLElement).getAttribute("data-remove-staged-file");
      if (!stId) return;
      const next = (state.pendingStagedFilesByConv[activeConvId] ?? []).filter(
        (sf) => sf.staging_id !== stId
      );
      if (next.length > 0) {
        state.pendingStagedFilesByConv[activeConvId] = next;
      } else {
        delete state.pendingStagedFilesByConv[activeConvId];
      }
      reRenderPreservingDraft(container, actions, false);
    });
  });

  container.querySelectorAll("[data-remove-pending-img]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!activeConvId || isConvStreaming(activeConvId)) return;
      const imgId = (btn as HTMLElement).getAttribute(
        "data-remove-pending-img"
      );
      if (!imgId) return;
      const next = (state.pendingChatImagesByConv[activeConvId] ?? []).filter(
        (img) => img.id !== imgId
      );
      if (next.length > 0) {
        state.pendingChatImagesByConv[activeConvId] = next;
      } else {
        delete state.pendingChatImagesByConv[activeConvId];
      }
      state.chatImageNotice = "";
      reRenderPreservingDraft(container, actions, false);
    });
  });

  container.querySelectorAll("[data-preview-pending-img]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!activeConvId) return;
      const imgId = (btn as HTMLElement).getAttribute(
        "data-preview-pending-img"
      );
      const found = (state.pendingChatImagesByConv[activeConvId] ?? []).find(
        (img) => img.id === imgId
      );
      if (!found) return;
      state.chatImagePreview = found;
      renderChatImagePreviewOverlay();
    });
  });

  container.querySelectorAll("[data-preview-msg-img]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const msgId =
        (btn as HTMLElement).getAttribute("data-preview-msg-id") ?? "";
      const idxStr =
        (btn as HTMLElement).getAttribute("data-preview-msg-img") ?? "";
      const idx = Number.parseInt(idxStr, 10);
      const msg = state.activeDetail?.messages.find((m) => m.id === msgId);
      const found = Number.isFinite(idx) ? msg?.images?.[idx] : undefined;
      if (!found) return;
      state.chatImagePreview = found;
      renderChatImagePreviewOverlay();
    });
  });

  if (input && input.tagName.toLowerCase() === "textarea") {
    const resizeTa = () => {
      input.style.height = "auto";
      input.style.height = `${Math.min(140, input.scrollHeight)}px`;
    };
    resizeTa();
    input.addEventListener("input", resizeTa);
  }

  container.querySelector("#chat-send-btn")?.addEventListener("click", submit);

  container
    .querySelector("#chat-context-expand-btn")
    ?.addEventListener("click", () => {
      state.composerContextExpanded = !state.composerContextExpanded;
      renderChatPanel(container, actions);
    });

  container
    .querySelector("#chat-model-chip")
    ?.addEventListener("click", (e) => {
      e.stopPropagation();
      state.composerModelMenuOpen = !state.composerModelMenuOpen;
      renderChatPanel(container, actions);
    });

  container.querySelectorAll("[data-select-model]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mId = (btn as HTMLElement).getAttribute("data-select-model");
      state.composerModelMenuOpen = false;
      if (mId) {
        actions.onChangeModel(mId as LocalModelId);
      }
    });
  });

  container
    .querySelector("#chat-web-toggle")
    ?.addEventListener("click", () => {
      actions.onToggleWeb();
    });

  container
    .querySelector("#chat-mail-toggle")
    ?.addEventListener("click", () => {
      if (actions.onToggleMail) {
        actions.onToggleMail();
      }
    });

  container
    .querySelector("#chat-drives-toggle")
    ?.addEventListener("click", () => {
      if (actions.onToggleDrives) {
        actions.onToggleDrives();
      }
    });

  container
    .querySelectorAll("[data-drives-jump-files]")
    .forEach((btn) => {
      btn.addEventListener("click", () => {
        actions.onOpenDrivesFiles?.();
      });
    });

  container.querySelectorAll("[data-chat-suggest]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (isConvStreaming(state.activeDetail?.conversation.id)) return;
      const prompt = (btn as HTMLElement).getAttribute("data-chat-suggest");
      if (prompt) {
        actions.onSendMessage(prompt);
      }
    });
  });

  container.querySelectorAll("[data-pill-tab-id]").forEach((pill) => {
    pill.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      if (
        target.closest("[data-pill-close-tab-id]") ||
        target.closest("[data-pill-recapture-tab-id]")
      ) {
        return;
      }
      const tabId = (pill as HTMLElement).getAttribute("data-pill-tab-id");
      if (tabId && actions.onSelectTab) {
        actions.onSelectTab(tabId);
      }
    });
    pill.addEventListener("mousedown", (e) => {
      if ((e as MouseEvent).button === 1) e.preventDefault();
    });
    pill.addEventListener("auxclick", (e) => {
      const me = e as MouseEvent;
      if (me.button !== 1) return;
      me.preventDefault();
      me.stopPropagation();
      const tabId = (pill as HTMLElement).getAttribute("data-pill-tab-id");
      if (tabId && actions.onCloseTab) {
        actions.onCloseTab(tabId);
      }
    });
  });

  container.querySelectorAll("[data-pill-recapture-tab-id]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const tabId = (btn as HTMLElement).getAttribute(
        "data-pill-recapture-tab-id"
      );
      if (tabId && actions.onRecaptureTab) {
        actions.onRecaptureTab(tabId);
      }
    });
  });

  container
    .querySelector("#chat-recapture-all-btn")
    ?.addEventListener("click", () => {
      if (actions.onRecaptureAllTabs) {
        actions.onRecaptureAllTabs();
      }
    });

  container
    .querySelector("#chat-enable-web-banner-btn")
    ?.addEventListener("click", () => {
      actions.onToggleWeb();
    });

  container.querySelectorAll("[data-pill-close-tab-id]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const tabId = (btn as HTMLElement).getAttribute("data-pill-close-tab-id");
      if (tabId && actions.onCloseTab) {
        actions.onCloseTab(tabId);
      }
    });
  });

  container
    .querySelector("#chat-context-add-tab-btn")
    ?.addEventListener("click", () => {
      if (actions.onNewTab) {
        actions.onNewTab();
      }
    });

  container.querySelectorAll("[data-task-stop]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const taskId = el.getAttribute("data-task-stop") ?? "";
      const stopToken = el.getAttribute("data-stop-token") ?? "";
      if (taskId && actions.onStopTask) {
        actions.onStopTask(taskId, stopToken);
      }
    });
  });

  container.querySelectorAll("[data-task-confirm]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const taskId = el.getAttribute("data-task-confirm") ?? "";
      const stepId = el.getAttribute("data-step-id") ?? "";
      const token = el.getAttribute("data-confirm-token") ?? "";
      if (taskId && actions.onConfirmTaskStep) {
        actions.onConfirmTaskStep(taskId, stepId, token);
      }
    });
  });

  container.querySelectorAll("[data-task-cancel]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const taskId = el.getAttribute("data-task-cancel") ?? "";
      const stepId = el.getAttribute("data-step-id") ?? "";
      if (taskId && actions.onCancelTaskStep) {
        actions.onCancelTaskStep(taskId, stepId);
      }
    });
  });

  container.querySelectorAll("[data-chat-toggle-email]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const key = el.getAttribute("data-chat-toggle-email") ?? "";
      const mid = el.getAttribute("data-email-mid") ?? "";
      if (!key) return;
      state.expandedChatEmails[key] = !state.expandedChatEmails[key];
      if (state.expandedChatEmails[key] && mid && actions.onPreviewMailAttachment) {
        // Ensure full message detail is loaded if not cached yet
      }
      renderChatPanel(container, actions);
    });
  });

  container.querySelectorAll("[data-chat-open-email-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const mid = el.getAttribute("data-chat-open-email-tab") ?? "";
      const subj = el.getAttribute("data-email-subj") ?? "mail";
      if (mid && actions.onOpenEmailTab) {
        actions.onOpenEmailTab(mid, subj);
      }
    });
  });

  container.querySelectorAll("[data-chat-unsub-email]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const mid = el.getAttribute("data-chat-unsub-email") ?? "";
      const sender = el.getAttribute("data-unsub-sender") ?? "";
      if (mid && actions.onPrepareUnsubscribe) {
        actions.onPrepareUnsubscribe(mid, sender);
      }
    });
  });

  container.querySelectorAll("[data-task-archive-sender]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const tid = el.getAttribute("data-task-archive-sender") ?? "";
      const sender = el.getAttribute("data-archive-sender-email") ?? "";
      if (tid && sender && actions.onArchiveSenderFromTask) {
        actions.onArchiveSenderFromTask(tid, sender);
      }
    });
  });

  container.querySelectorAll("[data-save-task-skill]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const tid = el.getAttribute("data-save-task-skill") ?? "";
      if (tid && actions.onSaveAsSkill) {
        el.textContent = t("chat.saved_skill_btn");
        actions.onSaveAsSkill({ taskId: tid });
      }
    });
  });

  container.querySelectorAll("[data-chat-preview-att]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const mid = el.getAttribute("data-chat-preview-att") ?? "";
      const partId = el.getAttribute("data-part-id") ?? "";
      if (mid && actions.onPreviewMailAttachment) {
        actions.onPreviewMailAttachment(mid, partId);
      }
    });
  });

  container.querySelectorAll("[data-chat-download-att]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const mid = el.getAttribute("data-chat-download-att") ?? "";
      const partId = el.getAttribute("data-part-id") ?? "";
      if (mid && actions.onDownloadMailAttachment) {
        actions.onDownloadMailAttachment(mid, partId);
      }
    });
  });

  container.querySelectorAll("[data-chat-compose-inline], #chat-compose-inline-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (isConvStreaming(state.activeDetail?.conversation.id)) return;
      actions.onStartInlineCompose?.();
    });
  });

  container.querySelectorAll('[data-compose-scope^="chat-"]').forEach((el) => {
    const scopeId = (el as HTMLElement).getAttribute("data-compose-scope") ?? "";
    const msgId = scopeId.slice(5);
    const draft = msgId ? state.inlineChatDrafts[msgId] : undefined;
    if (scopeId && draft) {
      bindComposeEditorEvents(container, draft, scopeId, {
        onChanged: () => renderChatPanel(container, actions),
        onPopout: actions.onPopoutInlineCompose,
      });
    }
  });

  // Settings inline UI card actions (execute out-of-band directly via sidecar IPC)
  container.querySelectorAll("[data-sc-create-profile]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-sc-create-profile") ?? "";
      const mid = el.getAttribute("data-sc-msg") ?? "";
      const nameEl = container.querySelector(`[data-sc-prof-name="${cid}"]`) as HTMLInputElement | null;
      const p1El = container.querySelector(`[data-sc-prof-pin1="${cid}"]`) as HTMLInputElement | null;
      const p2El = container.querySelector(`[data-sc-prof-pin2="${cid}"]`) as HTMLInputElement | null;
      const name = (nameEl?.value ?? "").trim();
      const pin1 = (p1El?.value ?? "").trim();
      const pin2 = (p2El?.value ?? "").trim();
      if (!name || !/^\d{6}$/.test(pin1)) {
        state.profileStatusMessage = t("chat.sc_err_pin6");
        renderChatPanel(container, actions);
        return;
      }
      if (pin2 && pin1 !== pin2) {
        state.profileStatusMessage = t("chat.sc_err_pin_mismatch");
        renderChatPanel(container, actions);
        return;
      }
      void actions.onSettingsCardCreateProfile?.(mid, cid, name, pin1);
    });
  });

  container.querySelectorAll("[data-sc-unlock-btn]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-sc-unlock-btn") ?? "";
      const pid = el.getAttribute("data-sc-prof-id") ?? "";
      const mid = el.getAttribute("data-sc-msg") ?? "";
      const pinEl = container.querySelector(`[data-sc-unlock-pin="${cid}"]`) as HTMLInputElement | null;
      const pin = (pinEl?.value ?? "").trim();
      void actions.onSettingsCardUnlockProfile?.(mid, cid, pid, pin, false);
    });
  });

  container.querySelectorAll("[data-sc-keychain-btn]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-sc-keychain-btn") ?? "";
      const pid = el.getAttribute("data-sc-prof-id") ?? "";
      const mid = el.getAttribute("data-sc-msg") ?? "";
      void actions.onSettingsCardUnlockProfile?.(mid, cid, pid, "", true);
    });
  });

  container.querySelectorAll("[data-sc-google-file]").forEach((inp) => {
    inp.addEventListener("change", () => {
      const el = inp as HTMLInputElement;
      const cid = el.getAttribute("data-sc-google-file") ?? "";
      const mid = el.getAttribute("data-sc-msg") ?? "";
      const f = el.files?.[0];
      el.value = "";
      if (!f) return;
      void f.text().then((txt) => {
        void actions.onSettingsCardGoogleSaveJson?.(mid, cid, txt);
      });
    });
  });

  container.querySelectorAll("[data-sc-google-signin]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-sc-google-signin") ?? "";
      const mid = el.getAttribute("data-sc-msg") ?? "";
      const authUrl = el.getAttribute("data-sc-auth-url") ?? "";
      const sessId = el.getAttribute("data-sc-session-id") ?? "";
      void actions.onSettingsCardGoogleStartLogin?.(
        mid,
        cid,
        authUrl || sessId ? { auth_url: authUrl, session_id: sessId } : undefined
      );
    });
  });

  container.querySelectorAll("[data-sc-google-gmail]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-sc-google-gmail") ?? "";
      const mid = el.getAttribute("data-sc-msg") ?? "";
      void actions.onSettingsCardGoogleConnectGmail?.(mid, cid);
    });
  });

  container.querySelectorAll("[data-sc-google-refresh]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-sc-google-refresh") ?? "";
      const mid = el.getAttribute("data-sc-msg") ?? "";
      void actions.onSettingsCardGoogleRefresh?.(mid, cid);
    });
  });

  container.querySelectorAll("[data-sc-save-apikey]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-sc-save-apikey") ?? "";
      const mid = el.getAttribute("data-sc-msg") ?? "";
      const provEl = container.querySelector(`[data-sc-apikey-prov="${cid}"]`) as HTMLSelectElement | null;
      const keyEl = container.querySelector(`[data-sc-apikey-val="${cid}"]`) as HTMLInputElement | null;
      const provId = (provEl?.value ?? "gemini").trim();
      const apiKey = (keyEl?.value ?? "").trim();
      if (!apiKey) return;
      void actions.onSettingsCardSaveApiKey?.(mid, cid, provId, apiKey);
    });
  });

  container.querySelectorAll("[data-sc-add-mail]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-sc-add-mail") ?? "";
      const mid = el.getAttribute("data-sc-msg") ?? "";
      const presetEl = container.querySelector(`[data-sc-mail-preset="${cid}"]`) as HTMLSelectElement | null;
      const emailEl = container.querySelector(`[data-sc-mail-email="${cid}"]`) as HTMLInputElement | null;
      const labelEl = container.querySelector(`[data-sc-mail-label="${cid}"]`) as HTMLInputElement | null;
      const passEl = container.querySelector(`[data-sc-mail-pass="${cid}"]`) as HTMLInputElement | null;
      const inHostEl = container.querySelector(`[data-sc-mail-inhost="${cid}"]`) as HTMLInputElement | null;
      const smtpHostEl = container.querySelector(`[data-sc-mail-smtphost="${cid}"]`) as HTMLInputElement | null;
      const emailVal = (emailEl?.value ?? "").trim();
      const passVal = passEl?.value ?? "";
      if (!emailVal || !passVal) return;
      void actions.onSettingsCardAddMail?.(mid, cid, {
        preset: presetEl?.value || "custom_imap",
        email: emailVal,
        label: (labelEl?.value ?? "").trim(),
        password: passVal,
        in_host: (inHostEl?.value ?? "").trim() || undefined,
        smtp_host: (smtpHostEl?.value ?? "").trim() || undefined,
      });
    });
  });

  container.querySelectorAll("[data-sc-save-prov]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-sc-save-prov") ?? "";
      const mid = el.getAttribute("data-sc-msg") ?? "";
      const catEl = container.querySelector(`[data-sc-prov-cat="${cid}"]`) as HTMLSelectElement | null;
      const nameEl = container.querySelector(`[data-sc-prov-name="${cid}"]`) as HTMLInputElement | null;
      const tpl = el.getAttribute("data-sc-tpl") ?? "";
      const mode = el.getAttribute("data-sc-mode") ?? "web_account";
      const doms = (el.getAttribute("data-sc-dom") ?? "").split(",").filter(Boolean);
      void actions.onSettingsCardSaveProvider?.(mid, cid, {
        category_id: catEl?.value || "custom",
        display_name: (nameEl?.value ?? "").trim(),
        url_template: tpl,
        mode,
        domains: doms,
      });
    });
  });

  container.querySelectorAll("[data-sc-gate-confirm]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-sc-gate-confirm") ?? "";
      const tok = el.getAttribute("data-sc-gate-token") ?? "";
      const mid = el.getAttribute("data-sc-msg") ?? "";
      const pinEl = container.querySelector(`[data-sc-gate-pin="${cid}"]`) as HTMLInputElement | null;
      const pin = (pinEl?.value ?? "").trim() || undefined;
      void actions.onSettingsCardConfirmGate?.(mid, cid, tok, pin);
    });
  });

  container.querySelectorAll("[data-sc-gate-cancel]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-sc-gate-cancel") ?? "";
      const mid = el.getAttribute("data-sc-msg") ?? "";
      actions.onSettingsCardCancelGate?.(mid, cid);
    });
  });

  container.querySelectorAll("[data-sc-translate-lang]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-sc-translate-lang") ?? "";
      const lang = el.getAttribute("data-sc-lang") ?? "";
      const mid = el.getAttribute("data-sc-msg") ?? "";
      if (lang) {
        void actions.onSettingsCardTranslateLanguage?.(mid, cid, lang, false);
      }
    });
  });

  container.querySelectorAll("[data-sc-switch-lang]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-sc-switch-lang") ?? "";
      const lang = el.getAttribute("data-sc-lang") ?? "";
      const mid = el.getAttribute("data-sc-msg") ?? "";
      if (lang) {
        void actions.onSettingsCardSwitchLanguage?.(mid, cid, lang);
      }
    });
  });

  container.querySelectorAll("[data-sc-cancel-lang]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-sc-cancel-lang") ?? "";
      const lang = el.getAttribute("data-sc-lang") ?? "";
      const mid = el.getAttribute("data-sc-msg") ?? "";
      void actions.onSettingsCardCancelLanguage?.(mid, cid, lang);
    });
  });

  container.querySelectorAll("[data-ns-track-topic]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const name = el.getAttribute("data-ns-track-topic") ?? "";
      const kws = (el.getAttribute("data-ns-topic-kw") ?? "")
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean);
      const cid = el.getAttribute("data-ns-card") ?? "";
      const mid = el.getAttribute("data-ns-msg") ?? "";
      if (name) {
        void actions.onNewsSettingsTrackTopic?.(mid, cid, name, kws);
      }
    });
  });

  container.querySelectorAll("[data-ns-toggle-feed]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const dom = el.getAttribute("data-ns-toggle-feed") ?? "";
      const enable = el.getAttribute("data-ns-feed-enable") === "1";
      const feedUrl = el.getAttribute("data-ns-feed-url") ?? "";
      const title = el.getAttribute("data-ns-feed-title") ?? "";
      const cid = el.getAttribute("data-ns-card") ?? "";
      const mid = el.getAttribute("data-ns-msg") ?? "";
      if (dom) {
        void actions.onNewsSettingsToggleFeed?.(mid, cid, dom, enable, feedUrl || undefined, title || undefined);
      }
    });
  });

  container.querySelectorAll("[data-ns-trust-range]").forEach((slider) => {
    slider.addEventListener("input", () => {
      const inputEl = slider as HTMLInputElement;
      const cid = inputEl.getAttribute("data-ns-trust-range") ?? "";
      const sysVal = Number(inputEl.getAttribute("data-ns-trust-sys") ?? "5");
      const persVal = Number(inputEl.value);
      const effVal = 0.7 * sysVal + 0.3 * persVal;
      const persLbl = container.querySelector(`[data-ns-trust-pers-label="${cid}"]`);
      const effLbl = container.querySelector(`[data-ns-trust-eff-label="${cid}"]`);
      if (persLbl) {
        persLbl.innerHTML = `${escapeHtml(t("chat.ns_personal_score"))}: <b>${persVal.toFixed(1)}</b>`;
      }
      if (effLbl) {
        effLbl.innerHTML = `${escapeHtml(t("chat.ns_effective_score"))}: <b>${effVal.toFixed(2)}/10</b>`;
      }
    });
  });

  container.querySelectorAll("[data-ns-save-trust]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-ns-save-trust") ?? "";
      const dom = el.getAttribute("data-ns-domain") ?? "";
      const mid = el.getAttribute("data-ns-msg") ?? "";
      const slider = container.querySelector(`[data-ns-trust-range="${cid}"]`) as HTMLInputElement | null;
      const val = slider ? Number(slider.value) : 5.0;
      if (dom) {
        void actions.onNewsSettingsSetTrust?.(mid, cid, dom, val);
      }
    });
  });

  container.querySelectorAll("[data-ns-reset-trust]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-ns-reset-trust") ?? "";
      const dom = el.getAttribute("data-ns-domain") ?? "";
      const mid = el.getAttribute("data-ns-msg") ?? "";
      if (dom) {
        void actions.onNewsSettingsSetTrust?.(mid, cid, dom, null);
      }
    });
  });

  container.querySelectorAll("[data-ns-submit-feed]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-ns-submit-feed") ?? "";
      const dom = el.getAttribute("data-ns-domain") ?? "";
      const mid = el.getAttribute("data-ns-msg") ?? "";
      const urlEl = container.querySelector(`[data-ns-feed-url-input="${cid}"]`) as HTMLInputElement | null;
      const titleEl = container.querySelector(`[data-ns-feed-title-input="${cid}"]`) as HTMLInputElement | null;
      const urlVal = (urlEl?.value ?? "").trim();
      const titleVal = (titleEl?.value ?? "").trim();
      if (urlVal) {
        void actions.onNewsSettingsAddFeedUrl?.(mid, cid, urlVal, titleVal || undefined, dom || undefined);
      } else {
        urlEl?.focus();
      }
    });
  });

  bindChatThreadEvents(container, actions);
}

export function bindChatThreadEvents(
  container: HTMLElement,
  actions: ChatActions,
  opts?: {
    onStateChange?: () => void;
    activeConvId?: string;
    getSources?: () => SourceItem[];
    getMessages?: () => ChatMessage[];
  }
): void {
  const activeConvId = opts?.activeConvId ?? state.activeDetail?.conversation.id ?? "";
  const reRender = () => {
    if (opts?.onStateChange) {
      opts.onStateChange();
    } else {
      renderChatPanel(container, actions);
    }
  };
  const getSources = () => opts?.getSources?.() ?? state.activeDetail?.sources ?? [];
  const getMessages = () => opts?.getMessages?.() ?? state.activeDetail?.messages ?? [];

  container.querySelectorAll("[data-citation-idx]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const idx = Number(el.getAttribute("data-citation-idx"));
      const srcId = el.getAttribute("data-citation-src") || null;
      if (el.classList.contains("flagged") && actions.onFlaggedCitationClick) {
        const msgId = el.closest("[data-msg-id]")?.getAttribute("data-msg-id") ?? undefined;
        actions.onFlaggedCitationClick(`[${idx}?]`, "src", msgId);
      }
      actions.onClickCitation(idx, srcId);
    });
    btn.addEventListener("mousedown", (e) => {
      if ((e as MouseEvent).button === 1) e.preventDefault();
    });
    btn.addEventListener("auxclick", (e) => {
      const me = e as MouseEvent;
      if (me.button !== 1) return;
      me.preventDefault();
      me.stopPropagation();
      const el = btn as HTMLElement;
      const srcId = el.getAttribute("data-citation-src") || "";
      const matched =
        getSources().find((s) => s.id === srcId) ??
        findSourceAcrossDetails(srcId) ??
        (srcId && /^https?:\/\//i.test(srcId)
          ? { url: srcId, title: extractDomain(srcId) }
          : null);
      if (matched && /^https?:\/\//i.test(matched.url)) {
        actions.onOpenUrlAsTab(matched.url, matched.title || "", false);
      }
    });
  });

  container.querySelectorAll("[data-brain-slug]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const slug = el.getAttribute("data-brain-slug") || "";
      const citeLabel = el.getAttribute("data-brain-cite") || "B1";
      if (el.classList.contains("flagged") && actions.onFlaggedCitationClick) {
        const msgId = el.closest("[data-msg-id]")?.getAttribute("data-msg-id") ?? undefined;
        actions.onFlaggedCitationClick(`[${citeLabel}?]`, "brain", msgId);
      }
      if (actions.onClickBrainCitation) {
        actions.onClickBrainCitation(slug, citeLabel);
      }
    });
  });

  container.querySelectorAll("[data-flagged-unsourced]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const msgId = el.closest("[data-msg-id]")?.getAttribute("data-msg-id") ?? undefined;
      actions.onFlaggedCitationClick?.("[unsourced]", "unsourced", msgId);
    });
  });

  container.querySelectorAll("[data-open-tab-url]").forEach((btn) => {
    const getUrlTitle = () => {
      const el = btn as HTMLElement;
      return {
        url: el.getAttribute("data-open-tab-url"),
        title: el.getAttribute("data-open-tab-title") ?? "",
      };
    };
    btn.addEventListener("click", () => {
      closeChatLinkPreviewPopover();
      const { url, title } = getUrlTitle();
      if (url) actions.onOpenUrlAsTab(url, title, true);
    });
    btn.addEventListener("mousedown", (e) => {
      if ((e as MouseEvent).button === 1) e.preventDefault();
    });
    btn.addEventListener("auxclick", (e) => {
      const me = e as MouseEvent;
      if (me.button !== 1) return;
      me.preventDefault();
      me.stopPropagation();
      const { url, title } = getUrlTitle();
      if (url) actions.onOpenUrlAsTab(url, title, false);
    });
  });

  container.querySelectorAll("[data-retry-prompt]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (isConvStreaming(activeConvId)) return;
      const el = btn as HTMLElement;
      const prompt = el.getAttribute("data-retry-prompt") ?? "";
      const msgId = el.getAttribute("data-msg-id") ?? undefined;
      const retryImages = activeConvId ? state.lastImagesByConv[activeConvId] : undefined;
      if (prompt || (retryImages && retryImages.length > 0)) {
        if (actions.onRetryMessage) {
          actions.onRetryMessage(prompt, retryImages, msgId);
        } else {
          actions.onSendMessage(prompt, retryImages);
        }
      }
    });
  });

  container.querySelectorAll("[data-use-planck-prompt]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (isConvStreaming(activeConvId)) return;
      const el = btn as HTMLElement;
      const prompt = el.getAttribute("data-use-planck-prompt");
      const msgId = el.getAttribute("data-msg-id") ?? undefined;
      if (!prompt) return;
      if (actions.onUsePlanckInstead) {
        actions.onUsePlanckInstead(prompt, msgId);
      } else {
        actions.onChangeModel("planck3 (web)");
        actions.onSendMessage(prompt);
      }
    });
  });

  container.querySelectorAll("[data-open-models-settings]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (actions.onOpenModelsSettings) {
        actions.onOpenModelsSettings();
      }
    });
  });

  container.querySelectorAll("[data-toggle-debug-msg]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mid = (btn as HTMLElement).getAttribute("data-toggle-debug-msg");
      if (!mid) return;
      state.expandedDebugMessages[mid] = !state.expandedDebugMessages[mid];
      reRender();
    });
  });

  container.querySelectorAll("[data-accept-proposal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const pid = el.getAttribute("data-accept-proposal") ?? "";
      const mid = el.getAttribute("data-proposal-msg") ?? "";
      if (pid && actions.onAcceptProposal) {
        actions.onAcceptProposal(pid, mid);
      }
    });
  });

  container.querySelectorAll("[data-reject-proposal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const pid = el.getAttribute("data-reject-proposal") ?? "";
      const mid = el.getAttribute("data-proposal-msg") ?? "";
      if (pid && actions.onRejectProposal) {
        actions.onRejectProposal(pid, mid);
      }
    });
  });

  container
    .querySelector("#chat-compare-these-btn")
    ?.addEventListener("click", () => {
      actions.onRunComparer?.();
    });

  container.querySelectorAll("[data-watch-msg]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mid = (btn as HTMLElement).getAttribute("data-watch-msg") ?? "";
      const msgObj = getMessages().find((m) => m.id === mid);
      if (mid && actions.onWatchAnswer) {
        actions.onWatchAnswer(mid, msgObj?.content ?? "");
      }
    });
  });

  container.querySelectorAll("[data-save-msg-skill]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const mid = el.getAttribute("data-save-msg-skill") ?? "";
      if (mid && actions.onSaveAsSkill) {
        el.textContent = t("chat.saved_skill_btn");
        actions.onSaveAsSkill({ msgId: mid });
      }
    });
  });

  container.querySelectorAll("[data-save-failure-eval]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const mid = el.getAttribute("data-save-failure-eval") ?? "";
      if (mid && actions.onSaveFailureAsEval) {
        el.textContent = t("chat.saving_eval_btn");
        (el as HTMLButtonElement).disabled = true;
        actions.onSaveFailureAsEval(mid);
      }
    });
  });

  container.querySelectorAll("[data-toggle-explain-msg]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mid = (btn as HTMLElement).getAttribute("data-toggle-explain-msg") ?? "";
      if (!mid) return;
      state.expandedExplainMessages[mid] = !state.expandedExplainMessages[mid];
      reRender();
    });
  });

  container.querySelectorAll("[data-toggle-indepth-msg]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mid = (btn as HTMLElement).getAttribute("data-toggle-indepth-msg") ?? "";
      if (!mid) return;
      state.expandedInDepthMessages[mid] = !state.expandedInDepthMessages[mid];
      reRender();
    });
  });

  container.querySelectorAll("[data-news-trust-dom]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const mid = el.getAttribute("data-news-trust-msg") ?? "";
      const dom = el.getAttribute("data-news-trust-dom") ?? "";
      const delta = Number(el.getAttribute("data-news-trust-delta") ?? "0");
      if (mid && dom && actions.onNewsTrustDelta) {
        actions.onNewsTrustDelta(mid, dom, delta);
      }
    });
  });

  container.querySelectorAll("[data-news-jump-lane]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const lane = (btn as HTMLElement).getAttribute("data-news-jump-lane") ?? "";
      if (lane && actions.onOpenNewsLane) {
        actions.onOpenNewsLane(lane);
      }
    });
  });

  container.querySelectorAll("[data-open-news-settings]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = (btn as HTMLElement).getAttribute("data-open-news-settings") ?? "chat";
      actions.onOpenNewsSettings?.(tab);
    });
  });

  bindFaviconFallbacks(container);
  container.querySelectorAll("img.preview-card-thumb").forEach((imgEl) => {
    imgEl.addEventListener(
      "error",
      () => {
        imgEl.closest(".preview-card-media")?.remove();
      },
      { once: true }
    );
  });

  ensureGlobalHoverPreviewListeners();
  hoverContainerActions.set(container, actions);
  const alreadyBound = container.getAttribute("data-hover-preview-bound") === "1";
  if (alreadyBound) {
    return;
  }
  container.setAttribute("data-hover-preview-bound", "1");
  container.addEventListener("mousedown", (e) => {
    if (e.button !== 1) return;
    const anchor = (e.target as HTMLElement | null)?.closest("a[href]") as HTMLAnchorElement | null;
    if (anchor && /^https?:\/\//i.test(anchor.href)) {
      e.preventDefault();
    }
  });
  container.addEventListener("auxclick", (e) => {
    if (e.button !== 1) return;
    const target = e.target as HTMLElement | null;
    if (target?.closest("[data-open-tab-url]")) return;
    const anchor = target?.closest("a[href]") as HTMLAnchorElement | null;
    if (!anchor || !/^https?:\/\//i.test(anchor.href)) return;
    e.preventDefault();
    e.stopPropagation();
    const label = (anchor.textContent || anchor.title || "").replace(/\s+/g, " ").trim().slice(0, 80);
    const curActions = hoverContainerActions.get(container) ?? actions;
    curActions.onOpenUrlAsTab(anchor.href, label, false);
  });
  const findHoverTarget = (rawTarget: EventTarget | null): HTMLElement | null => {
    if (!(rawTarget instanceof HTMLElement)) return null;
    const match = rawTarget.closest(
      ".msg-bot .inline-page-link[data-open-tab-url], .msg-bot button.cite[data-citation-idx], .msg-bot button.cite[data-brain-cite], .msg-bot .msg-text a[href]"
    ) as HTMLElement | null;
    if (!match) return null;
    if (match instanceof HTMLAnchorElement && !/^https?:\/\//i.test(match.href)) {
      return null;
    }
    return match;
  };
  const openHoverForTarget = (trigger: HTMLElement) => {
    const curActions = hoverContainerActions.get(container) ?? actions;
    if (linkPreviewCloseTimer !== null) {
      window.clearTimeout(linkPreviewCloseTimer);
      linkPreviewCloseTimer = null;
    }
    const payload = buildHoverPopoverPayload(trigger);
    if (!payload) return;
    const hoverKey = payload.url
      ? normalizePreviewUrlKey(payload.url)
      : payload.kind === "brain"
        ? `brain:${payload.brainSlug || payload.title}`
        : `cite:${payload.citationIndex}:${payload.sourceId || ""}`;
    if (
      activeHoverTrigger === trigger &&
      activeHoverKey === hoverKey &&
      document.getElementById(LINK_PREVIEW_POPOVER_ID)
    ) {
      return;
    }
    if (linkPreviewOpenTimer !== null) {
      window.clearTimeout(linkPreviewOpenTimer);
    }
    activeHoverTrigger = trigger;
    activeHoverKey = hoverKey;
    linkPreviewOpenTimer = window.setTimeout(() => {
      linkPreviewOpenTimer = null;
      if (activeHoverTrigger !== trigger || !trigger.isConnected) return;
      const latest = buildHoverPopoverPayload(trigger);
      if (!latest) return;
      renderLinkPreviewPopoverDom(trigger, latest, container, curActions);
    }, 120);
  };
  container.addEventListener("mouseover", (e) => {
    const trigger = findHoverTarget(e.target);
    if (!trigger) return;
    const related = e.relatedTarget as Node | null;
    if (related && trigger.contains(related)) return;
    openHoverForTarget(trigger);
  });
  container.addEventListener("mouseout", (e) => {
    const trigger = findHoverTarget(e.target);
    if (!trigger) return;
    const related = e.relatedTarget as Node | null;
    if (related && trigger.contains(related)) return;
    if (activeHoverTrigger === trigger) {
      scheduleCloseLinkPreviewPopover(130);
    }
  });
  container.addEventListener("focusin", (e) => {
    const trigger = findHoverTarget(e.target);
    if (trigger) openHoverForTarget(trigger);
  });
  container.addEventListener("focusout", (e) => {
    const trigger = findHoverTarget(e.target);
    if (!trigger) return;
    if (activeHoverTrigger === trigger) {
      scheduleCloseLinkPreviewPopover(130);
    }
  });
}
