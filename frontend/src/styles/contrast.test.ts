// @vitest-environment node
/**
 * WCAG 2.2 AA contrast for the color pairs the stylesheet uses, in both themes:
 * 4.5:1 for text (SC 1.4.3) and 3:1 for borders, focus rings and status bars (SC 1.4.11).
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const css = readFileSync(fileURLToPath(new URL("./tokens.css", import.meta.url)), "utf8");
const darkStart = css.indexOf("@media (prefers-color-scheme: dark)");

function readTokens(block: string): Record<string, string> {
  const tokens: Record<string, string> = {};
  for (const match of block.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    tokens[match[1]!] = match[2]!.toLowerCase();
  }
  return tokens;
}

const light = readTokens(css.slice(0, darkStart));
const dark = { ...light, ...readTokens(css.slice(darkStart)) };

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((index) => channel(Number.parseInt(hex.slice(index, index + 2), 16)));
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

export function contrast(first: string, second: string): number {
  const [high, low] = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (high! + 0.05) / (low! + 0.05);
}

const TONES = ["pass", "fail", "warn", "neutral", "info", "progress"];
const SURFACES = ["color-canvas", "color-surface", "color-surface-2", "color-surface-3", "color-accent-soft"];
const SYNTAX = ["syn-keyword", "syn-entity", "syn-string", "syn-number", "syn-comment"];

const TEXT_PAIRS: Array<[string, string]> = [
  ...SURFACES.map((bg): [string, string] => ["color-text", bg]),
  ...SURFACES.map((bg): [string, string] => ["color-text-muted", bg]),
  ...SURFACES.map((bg): [string, string] => ["color-accent", bg]),
  ["color-on-accent", "color-accent"],
  ["color-on-accent", "color-accent-strong"],
  ["color-surface", "color-text"],
  ...TONES.flatMap((tone): Array<[string, string]> => [
    [`tone-${tone}-fg`, `tone-${tone}-bg`],
    [`tone-${tone}-fg`, "color-surface"],
    ["color-text", `tone-${tone}-bg`],
    ["color-text-muted", `tone-${tone}-bg`],
  ]),
  ["diff-add-fg", "diff-add-bg"],
  ["diff-del-fg", "diff-del-bg"],
  ["color-text", "diff-add-bg"],
  ["color-text", "diff-del-bg"],
  ["color-text-muted", "diff-add-num"],
  ["color-text-muted", "diff-del-num"],
  ["diff-hunk-fg", "diff-hunk-bg"],
  // Code surfaces: plain text, line numbers and every syntax color on each background
  // a code line can have (plain, added, removed).
  ["color-text", "code-bg"],
  ["color-text-muted", "code-bg"],
  ["code-gutter-fg", "code-gutter-bg"],
  ["code-gutter-fg", "code-bg"],
  ["diff-add-fg", "diff-add-num"],
  ["diff-del-fg", "diff-del-num"],
  ...SYNTAX.flatMap((token): Array<[string, string]> =>
    ["code-bg", "diff-add-bg", "diff-del-bg"].map((bg): [string, string] => [token, bg]),
  ),
];

const UI_PAIRS: Array<[string, string]> = [
  ["color-border-strong", "color-surface"],
  ["color-border-strong", "color-surface-2"],
  ["color-border-strong", "color-canvas"],
  ["color-focus", "color-surface"],
  ["color-focus", "color-canvas"],
  ["color-focus", "color-surface-2"],
  ["diff-flag", "color-surface"],
  ["diff-flag", "code-bg"],
  ["shape-original", "color-surface"],
  ["shape-proposed", "color-surface"],
  ...TONES.map((tone): [string, string] => [`tone-${tone}-line`, "color-surface"]),
  // Icons drawn on a solid status color.
  ...TONES.map((tone): [string, string] => ["on-tone", `tone-${tone}-line`]),
];

describe.each([
  ["light", light],
  ["dark", dark],
] as const)("%s theme", (_name, palette) => {
  it("defines every token used in the checks", () => {
    for (const [fg, bg] of [...TEXT_PAIRS, ...UI_PAIRS]) {
      expect(palette[fg], fg).toMatch(/^#[0-9a-f]{6}$/);
      expect(palette[bg], bg).toMatch(/^#[0-9a-f]{6}$/);
    }
  });

  it.each(TEXT_PAIRS)("text %s on %s reaches 4.5:1", (fg, bg) => {
    expect(contrast(palette[fg]!, palette[bg]!)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(UI_PAIRS)("%s against %s reaches 3:1", (fg, bg) => {
    expect(contrast(palette[fg]!, palette[bg]!)).toBeGreaterThanOrEqual(3);
  });
});

describe("contrast()", () => {
  it("matches the WCAG reference values", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrast("#ffffff", "#ffffff")).toBeCloseTo(1, 5);
    expect(contrast("#767676", "#ffffff")).toBeCloseTo(4.54, 2);
  });
});
