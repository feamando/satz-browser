import { EN_CATALOG, type I18nCatalogEntry, type UiKey } from "./catalog";

export { EN_CATALOG, type I18nCatalogEntry, type UiKey } from "./catalog";

export interface I18nTranslatedEntry {
  text: string;
  one?: string;
  source_hash?: string;
  model?: string;
  custom?: boolean;
  fallback?: boolean;
  updated_at?: number;
}

export interface I18nLanguageSummary {
  lang: string;
  label: string;
  dir: "ltr" | "rtl";
  translated: number;
  total: number;
  missing: number;
  stale: number;
  custom: number;
  model?: string;
  updated_at?: number;
}

export const UI_LOCALE_STORAGE_KEY = "satz.ui.locale";
export const UI_LOCALE_DIR_STORAGE_KEY = "satz.ui.dir";
export const UI_LOCALE_BUNDLE_PREFIX = "satz.ui.i18n.";

interface CachedBundle {
  lang: string;
  label: string;
  dir: "ltr" | "rtl";
  entries: Record<string, I18nTranslatedEntry>;
}

let activeLocale = "en";
let activeDir: "ltr" | "rtl" = "ltr";
let activeLabel = "English";
let activeEntries: Record<string, I18nTranslatedEntry> = {};

const _PLACEHOLDER_RE = /\{([a-zA-Z0-9_]+)\}/g;

export function normalizeLangTag(raw: string): string {
  const s = (raw || "").trim();
  if (!s) return "en";
  const low = s.toLowerCase();
  const quick: Record<string, string> = {
    english: "en",
    en: "en",
    german: "de",
    deutsch: "de",
    french: "fr",
    français: "fr",
    francais: "fr",
    spanish: "es",
    español: "es",
    espanol: "es",
    italian: "it",
    italiano: "it",
    portuguese: "pt",
    português: "pt",
    portugues: "pt",
    dutch: "nl",
    nederlands: "nl",
    polish: "pl",
    polski: "pl",
    russian: "ru",
    русский: "ru",
    ukrainian: "uk",
    japanese: "ja",
    日本語: "ja",
    korean: "ko",
    한국어: "ko",
    chinese: "zh",
    中文: "zh",
    arabic: "ar",
    العربية: "ar",
    hebrew: "he",
    turkish: "tr",
    türkçe: "tr",
    swedish: "sv",
    norwegian: "nb",
    danish: "da",
    finnish: "fi",
    czech: "cs",
    hindi: "hi",
  };
  if (quick[low]) return quick[low];
  if (/^[a-z]{2,3}(?:-[a-z0-9]{2,8}){0,2}$/i.test(s)) {
    return low.replace(/_/g, "-");
  }
  const slug = low
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "custom";
}

export function extractPlaceholders(template: string): string[] {
  const set = new Set<string>();
  const re = new RegExp(_PLACEHOLDER_RE.source, "g");
  let m: RegExpExecArray | null;
  while ((m = re.exec(template)) !== null) {
    set.add(m[1]);
  }
  return [...set].sort();
}

export function hasMatchingPlaceholders(source: string, translated: string): boolean {
  const srcVars = extractPlaceholders(source);
  const trVars = extractPlaceholders(translated);
  if (srcVars.length !== trVars.length) return false;
  for (let i = 0; i < srcVars.length; i++) {
    if (srcVars[i] !== trVars[i]) return false;
  }
  return true;
}

export function safeIntlLocale(lang?: string): string {
  const cand = (lang || activeLocale || "en").trim() || "en";
  try {
    new Intl.DateTimeFormat(cand);
    return cand;
  } catch {
    return "en";
  }
}

function readBundleFromStorage(lang: string): CachedBundle | null {
  try {
    if (typeof window === "undefined") return null;
    const raw = window.localStorage.getItem(`${UI_LOCALE_BUNDLE_PREFIX}${lang}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<CachedBundle>;
    if (!parsed || typeof parsed !== "object" || typeof parsed.entries !== "object" || !parsed.entries) {
      return null;
    }
    return {
      lang: String(parsed.lang || lang),
      label: String(parsed.label || lang),
      dir: parsed.dir === "rtl" ? "rtl" : "ltr",
      entries: parsed.entries,
    };
  } catch {
    return null;
  }
}

function writeBundleToStorage(bundle: CachedBundle): void {
  try {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(
      `${UI_LOCALE_BUNDLE_PREFIX}${bundle.lang}`,
      JSON.stringify(bundle)
    );
  } catch {
    // Ignore storage quota / privacy mode errors
  }
}

function bootstrapFromStorage(): void {
  try {
    if (typeof window === "undefined") return;
    const stored = normalizeLangTag(window.localStorage.getItem(UI_LOCALE_STORAGE_KEY) || "en");
    activeLocale = stored || "en";
    if (activeLocale === "en") {
      activeDir = "ltr";
      activeLabel = "English";
      activeEntries = {};
      return;
    }
    const bundle = readBundleFromStorage(activeLocale);
    if (bundle) {
      activeDir = bundle.dir;
      activeLabel = bundle.label || activeLocale;
      activeEntries = bundle.entries;
    } else {
      const dirRaw = window.localStorage.getItem(UI_LOCALE_DIR_STORAGE_KEY);
      activeDir = dirRaw === "rtl" ? "rtl" : "ltr";
    }
  } catch {
    activeLocale = "en";
    activeDir = "ltr";
    activeEntries = {};
  }
}

bootstrapFromStorage();

export function getUiLocale(): string {
  return activeLocale;
}

export function getUiLocaleDir(): "ltr" | "rtl" {
  return activeDir;
}

export function getUiLocaleLabel(): string {
  return activeLabel;
}

export function getActiveLocaleEntries(): Record<string, I18nTranslatedEntry> {
  return activeEntries;
}

export function applyUiLocalePreferences(): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.setAttribute("lang", safeIntlLocale(activeLocale));
  root.setAttribute("dir", activeDir);
}

export function switchActiveLocale(
  lang: string,
  label?: string,
  dir?: "ltr" | "rtl"
): void {
  const norm = normalizeLangTag(lang);
  activeLocale = norm;
  if (norm === "en") {
    activeDir = "ltr";
    activeLabel = "English";
    activeEntries = {};
  } else {
    const cached = readBundleFromStorage(norm);
    if (cached) {
      activeDir = dir ?? cached.dir;
      activeLabel = label || cached.label || norm;
      activeEntries = cached.entries;
    } else {
      activeDir = dir ?? (/^(ar|he|fa|ur)(?:-|$)/i.test(norm) ? "rtl" : "ltr");
      activeLabel = label || norm;
      activeEntries = {};
    }
  }
  try {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(UI_LOCALE_STORAGE_KEY, activeLocale);
      window.localStorage.setItem(UI_LOCALE_DIR_STORAGE_KEY, activeDir);
    }
  } catch {
    // Ignore storage access errors
  }
  applyUiLocalePreferences();
}

export function setActiveLocaleBundle(
  lang: string,
  label: string,
  dir: "ltr" | "rtl",
  entries: Record<string, I18nTranslatedEntry>,
  activate = true
): void {
  const norm = normalizeLangTag(lang);
  const cleanDir: "ltr" | "rtl" = dir === "rtl" ? "rtl" : "ltr";
  const cleanLabel = (label || norm).trim() || norm;
  writeBundleToStorage({
    lang: norm,
    label: cleanLabel,
    dir: cleanDir,
    entries,
  });
  if (activate) {
    activeLocale = norm;
    activeLabel = cleanLabel;
    activeDir = cleanDir;
    activeEntries = { ...entries };
    try {
      if (typeof window !== "undefined") {
        window.localStorage.setItem(UI_LOCALE_STORAGE_KEY, norm);
        window.localStorage.setItem(UI_LOCALE_DIR_STORAGE_KEY, cleanDir);
      }
    } catch {
      // Ignore storage access errors
    }
    applyUiLocalePreferences();
  }
}

export function mergeActiveLocaleEntries(
  lang: string,
  label: string,
  dir: "ltr" | "rtl",
  delta: Record<string, I18nTranslatedEntry>,
  activate = false
): void {
  const norm = normalizeLangTag(lang);
  const existing =
    norm === activeLocale
      ? { ...activeEntries }
      : { ...(readBundleFromStorage(norm)?.entries ?? {}) };
  for (const [k, v] of Object.entries(delta)) {
    if (v && typeof v.text === "string" && v.text.trim()) {
      existing[k] = v;
    }
  }
  setActiveLocaleBundle(
    norm,
    label,
    dir,
    existing,
    activate || norm === activeLocale
  );
}

export function removeCachedLocaleBundle(lang: string): void {
  const norm = normalizeLangTag(lang);
  try {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(`${UI_LOCALE_BUNDLE_PREFIX}${norm}`);
    }
  } catch {
    // Ignore storage access errors
  }
  if (activeLocale === norm) {
    switchActiveLocale("en", "English");
  }
}

function interpolate(
  template: string,
  vars?: Record<string, string | number | undefined | null>
): string {
  if (!vars) return template;
  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (_full, name: string) => {
    const val = vars[name];
    return val === undefined || val === null ? "" : String(val);
  });
}

function resolveTemplate(key: UiKey, pluralCategory?: Intl.LDMLPluralRule): string {
  const base = EN_CATALOG[key] as I18nCatalogEntry;
  const wantOne = pluralCategory === "one" && typeof base.one === "string";
  const srcTemplate = wantOne ? (base.one as string) : base.text;
  if (activeLocale === "en") return srcTemplate;
  const entry = activeEntries[key];
  if (!entry) return srcTemplate;
  const candidate = wantOne ? entry.one || entry.text : entry.text;
  if (!candidate || typeof candidate !== "string") return srcTemplate;
  if (!hasMatchingPlaceholders(srcTemplate, candidate)) {
    return srcTemplate;
  }
  return candidate;
}

export function t(
  key: UiKey,
  vars?: Record<string, string | number | undefined | null>
): string {
  return interpolate(resolveTemplate(key), vars);
}

export function tCount(
  key: UiKey,
  count: number,
  vars?: Record<string, string | number | undefined | null>
): string {
  let category: Intl.LDMLPluralRule = count === 1 ? "one" : "other";
  try {
    category = new Intl.PluralRules(safeIntlLocale(activeLocale)).select(count);
  } catch {
    category = count === 1 ? "one" : "other";
  }
  const tpl = resolveTemplate(key, category);
  return interpolate(tpl, { ...vars, count });
}

export function tDynamic(
  maybeKey: string | undefined | null,
  fallbackText: string,
  vars?: Record<string, string | number | undefined | null>
): string {
  if (maybeKey && Object.prototype.hasOwnProperty.call(EN_CATALOG, maybeKey)) {
    return t(maybeKey as UiKey, vars);
  }
  return interpolate(fallbackText, vars);
}

export function formatLocaleRelativeTime(isoOrEpoch: string): string {
  if (!isoOrEpoch) return t("time.now");
  const num = Number(isoOrEpoch);
  const ms = !Number.isNaN(num)
    ? num < 1e12
      ? num * 1000
      : num
    : Date.parse(isoOrEpoch);
  if (Number.isNaN(ms)) return isoOrEpoch.slice(0, 10);
  const diffSec = Math.max(0, Math.floor((Date.now() - ms) / 1000));
  const loc = safeIntlLocale(activeLocale);
  try {
    const rtf = new Intl.RelativeTimeFormat(loc, { numeric: "auto", style: "narrow" });
    if (diffSec < 60) return rtf.format(-diffSec, "second");
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return rtf.format(-diffMin, "minute");
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return rtf.format(-diffHr, "hour");
    const diffDays = Math.floor(diffHr / 24);
    return rtf.format(-diffDays, "day");
  } catch {
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDays = Math.floor(diffHr / 24);
    return `${diffDays}d ago`;
  }
}

export function formatLocaleDateLine(date: Date = new Date()): string {
  const loc = safeIntlLocale(activeLocale);
  try {
    const weekday = date
      .toLocaleDateString(loc, { weekday: "long" })
      .toUpperCase();
    const day = String(date.getDate());
    const month = date
      .toLocaleDateString(loc, { month: "short" })
      .toUpperCase();
    return `${weekday} · ${day} ${month}`;
  } catch {
    const weekday = date
      .toLocaleDateString("en-US", { weekday: "long" })
      .toUpperCase();
    const day = String(date.getDate());
    const month = date
      .toLocaleDateString("en-US", { month: "short" })
      .toUpperCase();
    return `${weekday} · ${day} ${month}`;
  }
}

export function exportCatalogManifest(): Array<{
  key: string;
  text: string;
  one?: string;
  hint?: string;
}> {
  return Object.entries(EN_CATALOG).map(([key, val]) => {
    const entry = val as { text: string; one?: string; hint?: string };
    return {
      key,
      text: entry.text,
      ...(typeof entry.one === "string" ? { one: entry.one } : {}),
      ...(typeof entry.hint === "string" ? { hint: entry.hint } : {}),
    };
  });
}
