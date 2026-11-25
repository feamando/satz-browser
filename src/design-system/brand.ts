/*
  Satz brand marks: wordmark and icon, drawn to <canvas>.
  Spec: docs/design/DESIGN_SYSTEM.md section 3 (Logo).

  The dither is generated, never an image file, so it stays crisp at any DPR.
  Always await fontsReady() before the first draw, or the S renders in Georgia.
*/

export type WordmarkVariant = "backdrop" | "offset" | "grain";
export type MarkTheme = "light" | "dark";

/** Dither stops, deep purple to light grey (the "lock screen" ramp). */
export const DITHER_STOPS = [
  "#3f2775", "#5b3f99", "#8466c2", "#ad95de", "#cdbdec", "#ddd6e8", "#e7e5eb",
] as const;

const BAYER4 = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];
const INK = { light: "#1f1b22", dark: "#f4f1f8" } as const;
const font = (px: number) => `700 ${px}px Besley, Georgia, serif`;

/** Disc geometry in cap-height units, relative to the centre of the S. */
const WORDMARK: Record<WordmarkVariant, { r: number; ox: number; oy: number; grain: number }> = {
  backdrop: { r: 1.02, ox: 0, oy: 0, grain: 25 },
  offset: { r: 0.92, ox: -0.26, oy: -0.24, grain: 23 },
  grain: { r: 1.12, ox: 0.02, oy: 0, grain: 36 },
};

export function fontsReady(): Promise<unknown> {
  return document.fonts.load(font(40));
}

function prepare(cv: HTMLCanvasElement, w: number, h: number): CanvasRenderingContext2D {
  const k = Math.max(2, window.devicePixelRatio || 1);
  cv.width = Math.ceil(w * k);
  cv.height = Math.ceil(h * k);
  cv.style.width = `${w}px`;
  cv.style.height = `${h}px`;
  const g = cv.getContext("2d")!;
  g.setTransform(k, 0, 0, k, 0, 0);
  g.clearRect(0, 0, w, h);
  return g;
}

/** Ordered-dither dot disc. Gradient runs along `angleRad` (default top-left purple to bottom-right grey). */
function drawDisc(
  g: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  r: number,
  step: number,
  angleRad = Math.PI * 0.25,
  wavePhase = 0,
): void {
  const n = Math.ceil((2 * r) / step);
  const x0 = cx - r;
  const y0 = cy - r;
  const ux = Math.cos(angleRad);
  const uy = Math.sin(angleRad);
  const hasWave = wavePhase !== 0;
  for (let gy = 0; gy < n; gy++) {
    for (let gx = 0; gx < n; gx++) {
      const x = x0 + (gx + 0.5) * step;
      const y = y0 + (gy + 0.5) * step;
      const d = Math.hypot(x - cx, y - cy) / r;
      if (d > 0.98) continue;
      const proj = ((x - cx) * ux + (y - cy) * uy) / (2 * r) + 0.5;
      const ripple = hasWave ? 0.14 * Math.sin(d * 6.5 - wavePhase * 2.0) : 0;
      const t = Math.min(1, Math.max(0, (proj + ripple) * 1.3 - 0.28));
      const v = t * (DITHER_STOPS.length - 1);
      const i = Math.floor(v);
      const threshold = (BAYER4[(gy % 4) * 4 + (gx % 4)] + 0.5) / 16;
      const pulse = hasWave ? 0.88 + 0.22 * (0.5 + 0.5 * Math.sin(wavePhase * 1.6 - d * 5.0)) : 1;
      let rad = step * 0.42 * pulse;
      if (d > 0.9) rad *= 1 - (d - 0.9) * 5;
      g.fillStyle = DITHER_STOPS[Math.min(DITHER_STOPS.length - 1, v - i > threshold ? i + 1 : i)];
      g.beginPath();
      g.arc(x, y, Math.max(0.35, rad), 0, Math.PI * 2);
      g.fill();
    }
  }
}

/**
 * "Satz" set as one word with the dither disc behind the S.
 * height = font size in px (sidebar 22, header 42+). Canvas sizes itself.
 */
export function drawWordmark(
  cv: HTMLCanvasElement,
  opts: { height: number; theme: MarkTheme; variant?: WordmarkVariant },
): void {
  const v = WORDMARK[opts.variant ?? "backdrop"];
  const fs = opts.height;
  const m = document.createElement("canvas").getContext("2d")!;
  m.font = font(fs);
  const mS = m.measureText("S");
  const word = m.measureText("Satz");
  const capH = mS.actualBoundingBoxAscent;
  const r = v.r * capH;
  const dx = mS.width / 2 + v.ox * capH;
  const dy = -capH / 2 + v.oy * capH;
  const x0 = Math.max(2, r - dx + 2);
  const base = Math.max(capH + 2, r - dy + 2);
  const w = Math.ceil(x0 + word.width + 3);
  const h = Math.ceil(Math.max(base + word.actualBoundingBoxDescent, base + dy + r) + 2);
  const g = prepare(cv, w, h);

  drawDisc(g, x0 + dx, base + dy, r, Math.max(1.3, (2 * r) / v.grain));

  g.font = font(fs);
  g.textBaseline = "alphabetic";
  g.lineJoin = "round";
  // Knock a gap out of the dots around the letters. Dark theme: no outline on the S.
  g.globalCompositeOperation = "destination-out";
  g.lineWidth = Math.max(1.4, fs * 0.08);
  g.strokeText("atz", x0 + word.width - m.measureText("atz").width, base);
  if (opts.theme === "light") g.strokeText("S", x0, base);
  g.globalCompositeOperation = "source-over";
  g.fillStyle = INK[opts.theme];
  g.fillText("Satz", x0, base);
}

/** App icon / favicon: dither disc with a solid white S, no outline. */
export function drawIcon(cv: HTMLCanvasElement, opts: { size: number; tile?: boolean }): void {
  const px = opts.size;
  const g = prepare(cv, px, px);
  const c = px / 2;
  let r = c;
  if (opts.tile) {
    g.fillStyle = "#141218";
    g.beginPath();
    g.roundRect(0, 0, px, px, px * 0.23);
    g.fill();
    r = px * 0.39;
  }
  drawDisc(g, c, c, r, Math.max(1.2, (2 * r) / (px < 24 ? 11 : 21)));
  g.font = font(r * 1.42);
  g.textAlign = "center";
  g.textBaseline = "alphabetic";
  const s = g.measureText("S");
  g.fillStyle = "#ffffff";
  g.fillText("S", c, c + (s.actualBoundingBoxAscent - s.actualBoundingBoxDescent) / 2);
}

/**
 * Animated post-unlock emblem using the logo's Bayer ordered-dither dot matrix.
 * Returns a cleanup callback to stop the `requestAnimationFrame` loop.
 */
export function startDitherLoaderAnimation(
  cv: HTMLCanvasElement,
  opts: { size: number; theme: MarkTheme },
): () => void {
  const px = opts.size;
  const g = prepare(cv, px, px);
  const c = px / 2;
  const r = px * 0.47;
  const step = Math.max(1.5, (2 * r) / 19);
  const reducedMotion =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  let rafId = 0;
  let stopped = false;
  const t0 = performance.now();

  const renderFrame = (nowMs: number) => {
    const secs = Math.max(0, (nowMs - t0) / 1000);
    const angle = reducedMotion ? Math.PI * 0.25 : Math.PI * 0.25 + secs * 1.45;
    const wave = reducedMotion ? 0 : secs * 2.4;
    g.clearRect(0, 0, px, px);
    drawDisc(g, c, c, r, step, angle, wave);
    g.font = font(r * 1.38);
    g.textAlign = "center";
    g.textBaseline = "alphabetic";
    g.lineJoin = "round";
    g.globalCompositeOperation = "destination-out";
    g.lineWidth = Math.max(1.8, r * 0.14);
    const s = g.measureText("S");
    const yBase = c + (s.actualBoundingBoxAscent - s.actualBoundingBoxDescent) / 2;
    if (opts.theme === "light") g.strokeText("S", c, yBase);
    g.globalCompositeOperation = "source-over";
    g.fillStyle = INK[opts.theme];
    g.fillText("S", c, yBase);
  };

  renderFrame(t0);
  void fontsReady().then(() => {
    if (!stopped) renderFrame(performance.now());
  });

  if (!reducedMotion) {
    const tick = (nowMs: number) => {
      if (stopped) return;
      renderFrame(nowMs);
      rafId = window.requestAnimationFrame(tick);
    };
    rafId = window.requestAnimationFrame(tick);
  }

  return () => {
    stopped = true;
    if (rafId) window.cancelAnimationFrame(rafId);
  };
}
