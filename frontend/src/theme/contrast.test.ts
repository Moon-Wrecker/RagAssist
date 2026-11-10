import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { DARK_BACKDROP_MAX, DARK_PAGE_MAX, LIGHT_BACKDROP_MIN, LIGHT_PAGE_MIN, LIQUID } from "@/background/liquid-config";

/**
 * Design-rule checks read straight from src/index.css and the liquid background's brightness budget:
 * - every colour token has zero chroma (true monochrome, no accent anywhere);
 * - body text (primary) and secondary text meet WCAG AA on every glass thickness (thin, regular, thick) over the
 *   brightest frame the liquid can draw (the pixel that is hardest for the text colour), in light and dark, after the
 *   backdrop filter's brightness lift, and on the solid fallbacks used without backdrop-filter or under
 *   prefers-reduced-transparency;
 * - the same on the bare page, where text sits directly on the liquid under its reading-column scrim.
 */
const css = readFileSync(resolve(process.cwd(), "src/index.css"), "utf8");

interface Colour {
  l: number;
  c: number;
  alpha: number;
}

function blockOf(selector: string): string {
  const start = css.indexOf(`\n${selector} {`);
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

function numbers(selector: string): Map<string, number> {
  const found = new Map<string, number>();
  for (const match of blockOf(selector).matchAll(/--([\w-]+):\s*([\d.]+)(?:px)?\s*;/g)) found.set(match[1]!, Number(match[2]));
  return found;
}

// For a zero-chroma colour OKLab's cube-root lightness gives linear luminance directly: Y = L^3.
const luminance = (l: number) => l ** 3;
const toGamma = (y: number) => (y <= 0.0031308 ? 12.92 * y : 1.055 * y ** (1 / 2.4) - 0.055);
const fromGamma = (s: number) => (s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4);
const contrast = (a: number, b: number) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);

/** Source-over compositing in sRGB (what browsers do) of a translucent grey over an opaque sRGB grey. Returns Y. */
function over(top: Colour, backSrgb: number): number {
  const s = top.alpha * toGamma(luminance(top.l)) + (1 - top.alpha) * backSrgb;
  return fromGamma(s);
}

const TIERS = ["thin", "regular", "thick"] as const;

describe.each([
  ["light", ":root", LIGHT_BACKDROP_MIN, 1 - LIQUID.floor, LIGHT_PAGE_MIN],
  ["dark", ':root[data-theme="dark"]', DARK_BACKDROP_MAX, LIQUID.floor, DARK_PAGE_MAX],
] as const)("%s theme", (_name, selector, hardest, easiest, pageHardest) => {
  const t = tokens(selector);
  const n = numbers(selector);
  // Tokens that only the light block defines are inherited by the dark theme (same for the numbers).
  const base = tokens(":root");
  const baseN = numbers(":root");
  const get = (name: string) => {
    const value = t.get(name) ?? base.get(name);
    if (!value) throw new Error(`Missing token --${name}`);
    return value;
  };
  const num = (name: string) => {
    const value = n.get(name) ?? baseN.get(name);
    if (value === undefined) throw new Error(`Missing number --${name}`);
    return value;
  };
  const text = luminance(get("foreground").l);
  const muted = luminance(get("muted-foreground").l);

  it("has zero chroma in every colour token", () => {
    for (const [name, colour] of t) expect(colour.c, `--${name}`).toBe(0);
  });

  for (const tier of TIERS) {
    for (const [label, backdrop] of [
      ["the hardest backdrop pixel", hardest],
      ["the easiest backdrop pixel", easiest],
    ] as const) {
      it(`keeps AA text contrast on ${tier} glass over ${label}`, () => {
        // The backdrop filter lifts brightness on the sRGB value; grain may push the pixel either way.
        const lifted = Math.min(1, backdrop * num(`glass-${tier}-brightness`));
        const surface = over(get(`glass-${tier}`), lifted);
        expect(contrast(text, surface)).toBeGreaterThanOrEqual(7);
        expect(contrast(muted, surface)).toBeGreaterThanOrEqual(4.5);
      });
    }

    it(`keeps AA text contrast on the solid fallback for ${tier} glass`, () => {
      const solid = luminance(get(`glass-${tier}-solid`).l);
      expect(contrast(text, solid)).toBeGreaterThanOrEqual(7);
      expect(contrast(muted, solid)).toBeGreaterThanOrEqual(4.5);
    });
  }

  it("keeps AA text contrast directly on the liquid under the reading column, at its hardest pixel", () => {
    const page = fromGamma(pageHardest);
    expect(contrast(text, page)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(muted, page)).toBeGreaterThanOrEqual(4.5);
  });

  it("holds the reading column scrim below the centre of the screen and the centre below the edges", () => {
    expect(LIQUID.scrim).toBeLessThan(LIQUID.centre);
    expect(LIQUID.centre).toBeLessThan(LIQUID.edge);
  });
});

describe("liquid brightness budget", () => {
  it("stays between black and mid-grey in the dark theme, and mirrors that in the light theme", () => {
    expect(DARK_BACKDROP_MAX).toBeLessThanOrEqual(0.5);
    expect(LIGHT_BACKDROP_MIN).toBeCloseTo(1 - DARK_BACKDROP_MAX, 6);
  });
});

describe("glass rules", () => {
  it("falls back to a solid surface without backdrop-filter and under reduced transparency, for every thickness", () => {
    expect(css).toMatch(/@supports \(\(-webkit-backdrop-filter: blur\(1px\)\) or \(backdrop-filter: blur\(1px\)\)\)/);
    expect(css.match(/prefers-reduced-transparency: reduce/g)?.length).toBeGreaterThanOrEqual(3);
  });

  it("keeps blur radii modest", () => {
    const blurs = [...css.matchAll(/--glass-\w+-blur:\s*(\d+)px/g)].map((m) => Number(m[1]));
    expect(blurs.length).toBe(3);
    expect(Math.max(...blurs)).toBeLessThanOrEqual(48);
    expect(blurs[0]).toBeLessThan(blurs[1]!);
    expect(blurs[1]).toBeLessThan(blurs[2]!);
  });

  it("defines thin, regular and thick glass and no accent hues", () => {
    for (const tier of TIERS) expect(css).toContain(`@utility glass-${tier}`);
    expect(css).not.toMatch(/\bhsl\(|\brgb\(\s*\d+\s*[, ]\s*\d+\s*[, ]\s*\d+(?!.*(?:rim|0\)))/);
  });
});
