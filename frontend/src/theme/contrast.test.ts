import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Design-rule checks read straight from src/index.css:
 * - every colour token has zero chroma (true monochrome, no tint anywhere);
 * - body and muted text meet WCAG AA (4.5:1; the main text far exceeds it) on every glass surface, over both the
 *   lightest and the darkest tone of the backdrop the glass can sit on, in light and dark, and on the solid
 *   fallbacks used without backdrop-filter or under prefers-reduced-transparency.
 */
const css = readFileSync(resolve(process.cwd(), "src/index.css"), "utf8");

interface Colour {
  l: number;
  c: number;
  alpha: number;
}

function blockOf(selector: string): string {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`No ${selector} block in index.css`);
  return css.slice(start, css.indexOf("\n}", start));
}

function tokens(selector: string): Map<string, Colour> {
  const found = new Map<string, Colour>();
  for (const match of blockOf(selector).matchAll(/--([\w-]+):\s*oklch\(([^)]*)\)/g)) {
    const [name, body] = [match[1]!, match[2]!];
    const [color, alpha = "1"] = body.split("/").map((part) => part.trim());
    const [l, c] = color!.split(/\s+/).map(Number);
    found.set(name, { l: l!, c: c!, alpha: Number(alpha) });
  }
  return found;
}

// For a zero-chroma colour OKLab's cube-root lightness gives linear luminance directly: Y = L^3.
const luminance = (l: number) => l ** 3;
const toGamma = (y: number) => (y <= 0.0031308 ? 12.92 * y : 1.055 * y ** (1 / 2.4) - 0.055);
const fromGamma = (s: number) => (s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4);

/** Source-over compositing in sRGB (what browsers do) of a translucent grey over an opaque grey luminance. */
function over(top: Colour, backY: number): number {
  const s = top.alpha * toGamma(luminance(top.l)) + (1 - top.alpha) * toGamma(backY);
  return fromGamma(s);
}

const contrast = (a: number, b: number) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);

describe.each([
  ["light", ":root"],
  ["dark", ':root[data-theme="dark"]'],
] as const)("%s theme", (_name, selector) => {
  const t = tokens(selector);
  const get = (name: string) => {
    const value = t.get(name);
    if (!value) throw new Error(`Missing token --${name}`);
    return value;
  };

  it("has zero chroma in every colour token", () => {
    for (const [name, colour] of t) expect(colour.c, `--${name}`).toBe(0);
  });

  const backdrops = ["ambient-lo", "ambient-hi"] as const;
  const levels = ["glass-1", "glass-2"] as const;

  for (const level of levels) {
    for (const backdrop of backdrops) {
      it(`keeps AA text contrast on ${level} over ${backdrop}`, () => {
        const grainShift = Number(/--grain-opacity:\s*([\d.]+)/.exec(blockOf(selector))![1]); // grain nudges the backdrop
        const backY = luminance(get(backdrop).l);
        // Worst case for the grain: pushed towards the text colour.
        const backs = [backY, Math.min(1, backY + grainShift), Math.max(0, backY - grainShift)];
        const surfaces = backs.map((y) => over(get(level), y));
        const text = luminance(get("foreground").l);
        const muted = luminance(get("muted-foreground").l);
        for (const surface of surfaces) {
          expect(contrast(text, surface)).toBeGreaterThanOrEqual(7);
          expect(contrast(muted, surface)).toBeGreaterThanOrEqual(4.5);
        }
      });
    }
  }

  for (const level of levels) {
    it(`keeps AA text contrast on the solid fallback for ${level}`, () => {
      const solid = luminance(get(`${level}-solid`).l);
      expect(contrast(luminance(get("foreground").l), solid)).toBeGreaterThanOrEqual(7);
      expect(contrast(luminance(get("muted-foreground").l), solid)).toBeGreaterThanOrEqual(4.5);
    });
  }

  it("keeps AA text contrast on the page background", () => {
    const page = luminance(get("background").l);
    expect(contrast(luminance(get("foreground").l), page)).toBeGreaterThanOrEqual(7);
    expect(contrast(luminance(get("muted-foreground").l), page)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("glass rules", () => {
  it("falls back to a solid surface without backdrop-filter and under reduced transparency", () => {
    expect(css).toMatch(/@supports \(\(-webkit-backdrop-filter: blur\(1px\)\) or \(backdrop-filter: blur\(1px\)\)\)/);
    expect(css.match(/prefers-reduced-transparency: reduce/g)?.length).toBeGreaterThanOrEqual(3);
  });

  it("keeps blur radii modest and uses no gradients", () => {
    const blurs = [...css.matchAll(/blur\((\d+)px\)/g)].map((m) => Number(m[1]));
    expect(Math.max(...blurs)).toBeLessThanOrEqual(72);
    expect(css).not.toMatch(/gradient\(/);
  });
});
