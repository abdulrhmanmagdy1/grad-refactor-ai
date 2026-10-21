import { describe, expect, it } from "vitest";
import { highlightPython } from "./highlight";
import { codeShape } from "./shape";

const kinds = (line: string) =>
  highlightPython(line)[0]!.tokens.filter((token) => token.kind !== "plain").map((token) => `${token.kind}:${token.text}`);

describe("highlightPython", () => {
  it("keeps every character of every line", () => {
    const source = 'def f(x):\n    """Doc\n    more"""\n    if x > 0.5:  # note\n        return f"{x}"\r\n    return None\n';
    const lines = highlightPython(source);
    expect(lines.map((line) => line.tokens.map((token) => token.text).join(""))).toEqual(source.split("\n"));
  });

  it("colors keywords, names, strings, numbers, constants and comments", () => {
    expect(kinds("def shipping_cost(weight, express=False):")).toEqual([
      "keyword:def",
      "entity:shipping_cost",
      "number:False",
    ]);
    expect(kinds('    raise ValueError("weight must be positive")  # guard')).toEqual([
      "keyword:raise",
      "entity:ValueError",
      'string:"weight must be positive"',
      "comment:# guard",
    ]);
    expect(kinds("    return min(days * 0x1F, 1_500) if ok else 2.5e-3")).toEqual([
      "keyword:return",
      "entity:min",
      "number:0x1F",
      "number:1_500",
      "keyword:if",
      "keyword:else",
      "number:2.5e-3",
    ]);
  });

  it("treats string prefixes, escapes and names that only look like keywords correctly", () => {
    expect(kinds(String.raw`x = rb'\d' + 'it\'s' + iffy + self.len`)).toEqual([
      String.raw`string:rb'\d'`,
      String.raw`string:'it\'s'`,
    ]);
  });

  it("colors match and case only where they start a statement", () => {
    expect(kinds("    match command:")).toEqual(["keyword:match"]);
    expect(kinds("    match = 3")).toEqual(["number:3"]);
  });

  it("carries triple-quoted strings and brackets across lines", () => {
    const lines = highlightPython('"""a\nb\nc""" + d\nf(1,\n  2)\ng');
    expect(lines.map((line) => line.startsInString)).toEqual([false, true, true, false, false, false]);
    expect(lines[2]!.tokens[0]).toEqual({ kind: "string", text: 'c"""' });
    expect(lines.map((line) => line.startsInBracket)).toEqual([false, false, false, false, true, false]);
  });

  it("ends an unterminated short string at the end of its line", () => {
    const lines = highlightPython('x = "open\ny = 1');
    expect(lines[1]!.startsInString).toBe(false);
    expect(lines[1]!.tokens.map((token) => token.kind)).toContain("number");
  });
});

describe("codeShape", () => {
  const nested = [
    "def fine(days, member):",
    '    """Fine in cents."""',
    "    if days >= 0:",
    "        if days > 0:",
    "            rate = 20 if member else 35",
    "            return min(days * rate,",
    "                       1500)",
    "        else:",
    "            return 0",
    "    else:",
    "        raise ValueError('negative')",
    "",
  ].join("\n");
  const flat = [
    "def fine(days, member):",
    '    """Fine in cents."""',
    "    if days < 0:",
    "        raise ValueError('negative')",
    "    if days <= 0:",
    "        return 0",
    "    rate = 20 if member else 35",
    "    return min(days * rate, 1500)",
  ].join("\n");

  it("measures the deepest indentation level by Python's block rule", () => {
    expect(codeShape(nested).maxLevel).toBe(3);
    expect(codeShape(flat).maxLevel).toBe(2);
  });

  it("gives continuation, blank and comment lines no level", () => {
    const shape = codeShape("def f(x):\n    # check\n\n    return g(x,\n             1)\n");
    expect(shape.lines.map((line) => line.level)).toEqual([0, null, null, 1, null]);
    expect(shape.lines[3]).toMatchObject({ indent: 4, width: 15 });
  });

  it("handles empty input, tabs and CRLF", () => {
    expect(codeShape("  \n")).toEqual({ lines: [], maxLevel: 0 });
    const shape = codeShape("def f(x):\r\n\tif x:\r\n\t\treturn 1\r\n");
    expect(shape.maxLevel).toBe(2);
    expect(shape.lines[2]).toMatchObject({ indent: 8 });
  });
});
