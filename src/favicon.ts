import { icon } from "./design-system/icons";
import { escapeHtml, getFaviconDisplaySrc, state } from "./state";

export function renderSiteFaviconHtml(
  rawUrl: string,
  explicitFaviconUrl?: string | null,
  fallbackIcon: "globe" | "mail" | "compose" = "globe"
): string {
  const src = getFaviconDisplaySrc(rawUrl, explicitFaviconUrl);
  if (!src) {
    return icon(fallbackIcon, "ico-sm");
  }
  return `<img class="favicon" src="${escapeHtml(src)}" alt="" /><span class="favicon-fallback hidden">${icon(fallbackIcon, "ico-sm")}</span>`;
}

export function bindFaviconFallbacks(container: HTMLElement): void {
  container.querySelectorAll("img.favicon").forEach((el) => {
    const img = el as HTMLImageElement;
    const swapToFallback = () => {
      const currentSrc = img.getAttribute("src") || img.src;
      if (currentSrc) {
        state.failedFaviconSrcs[currentSrc] = true;
      }
      img.classList.add("hidden");
      const fallback = img.nextElementSibling;
      if (fallback?.classList.contains("favicon-fallback")) {
        fallback.classList.remove("hidden");
      }
    };
    img.addEventListener("error", swapToFallback, { once: true });
    const attrSrc = img.getAttribute("src") || "";
    if (
      img.complete &&
      img.naturalWidth === 0 &&
      !attrSrc.startsWith("data:image/svg+xml")
    ) {
      swapToFallback();
    }
  });
}
