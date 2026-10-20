// @vitest-environment node
import { describe, expect, it } from "vitest";
import { DIFF_TEXT, ORIGINAL_CODE, PROPOSED_CODE } from "../test/fixtures";
import { DiffParseError, buildSplitRows, parseUnifiedDiff, splitSourceLines } from "./diff";

describe("parseUnifiedDiff", () => {
  it.each([null, undefined, "", "   \n\n"])("returns an empty diff for %j", (input) => {
    expect(parseUnifiedDiff(input)).toEqual({ oldFile: null, newFile: null, hunks: [], additions: 0, deletions: 0 });
  });

  it("parses the service's difflib output with file names, counts and line numbers", () => {
    const parsed = parseUnifiedDiff(DIFF_TEXT);
    expect(parsed.oldFile).toBe("original.py");
    expect(parsed.newFile).toBe("proposed.py");
    expect(parsed.additions).toBe(5);
    expect(parsed.deletions).toBe(7);
    expect(parsed.hunks).toHaveLength(1);
    const hunk = parsed.hunks[0]!;
    expect(hunk).toMatchObject({ oldStart: 1, oldCount: 9, newStart: 1, newCount: 7, section: "" });
    expect(hunk.lines).toHaveLength(14);
    expect(hunk.lines[0]).toEqual({
      kind: "context",
      text: "def shipping_cost(weight, express):",
      oldNumber: 1,
      newNumber: 1,
      noNewlineAtEnd: false,
    });
    expect(hunk.lines[2]).toEqual({
      kind: "remove",
      text: "    if weight > 0:",
      oldNumber: 3,
      newNumber: null,
      noNewlineAtEnd: false,
    });
    expect(hunk.lines[8]).toMatchObject({ kind: "remove", oldNumber: 9 });
    expect(hunk.lines[9]).toEqual({
      kind: "add",
      text: "    if weight <= 0:",
      oldNumber: null,
      newNumber: 3,
      noNewlineAtEnd: false,
    });
    expect(hunk.lines[13]).toMatchObject({ kind: "add", newNumber: 7, text: "    return weight * 2" });
  });

  it("parses several hunks and keeps their own numbering and section text", () => {
    const diff = [
      "--- a/f.py\t2026-10-20 09:00:00",
      "+++ b/f.py\t2026-10-20 09:01:00",
      "@@ -1,3 +1,3 @@ def f(x):",
      " a",
      "-b",
      "+B",
      " c",
      "@@ -10,2 +10,3 @@",
      " j",
      "+k2",
      " l",
    ].join("\n");
    const parsed = parseUnifiedDiff(diff);
    expect(parsed.oldFile).toBe("a/f.py");
    expect(parsed.newFile).toBe("b/f.py");
    expect(parsed.hunks).toHaveLength(2);
    expect(parsed.hunks[0]!.section).toBe("def f(x):");
    expect(parsed.hunks[1]!.lines.map((line) => [line.kind, line.oldNumber, line.newNumber])).toEqual([
      ["context", 10, 10],
      ["add", null, 11],
      ["context", 11, 12],
    ]);
    expect(parsed.additions).toBe(2);
    expect(parsed.deletions).toBe(1);
  });

  it("reads hunk headers without counts as one line", () => {
    const parsed = parseUnifiedDiff("@@ -3 +3 @@\n-old\n+new\n");
    expect(parsed.hunks[0]).toMatchObject({ oldStart: 3, oldCount: 1, newStart: 3, newCount: 1 });
    expect(parsed.hunks[0]!.lines.map((line) => line.kind)).toEqual(["remove", "add"]);
  });

  it("handles insertion into an empty file and deletion of every line", () => {
    const inserted = parseUnifiedDiff("--- /dev/null\n+++ b.py\n@@ -0,0 +1,2 @@\n+x = 1\n+y = 2\n");
    expect(inserted.oldFile).toBe("/dev/null");
    expect(inserted.hunks[0]!.lines.map((line) => line.newNumber)).toEqual([1, 2]);
    const deleted = parseUnifiedDiff("@@ -1,2 +0,0 @@\n-x = 1\n-y = 2\n");
    expect(deleted.hunks[0]!.lines.map((line) => line.oldNumber)).toEqual([1, 2]);
    expect(deleted.deletions).toBe(2);
  });

  it("attaches no-newline markers to the line before them on either side", () => {
    const diff = [
      "@@ -1,2 +1,2 @@",
      " keep",
      "-return a",
      "\\ No newline at end of file",
      "+return b",
      "\\ No newline at end of file",
    ].join("\n");
    const lines = parseUnifiedDiff(diff).hunks[0]!.lines;
    expect(lines.map((line) => [line.kind, line.noNewlineAtEnd])).toEqual([
      ["context", false],
      ["remove", true],
      ["add", true],
    ]);
  });

  it("accepts CRLF line endings", () => {
    const parsed = parseUnifiedDiff("--- a\r\n+++ b\r\n@@ -1,2 +1,2 @@\r\n x\r\n-y\r\n+z\r\n");
    expect(parsed.hunks[0]!.lines.map((line) => line.text)).toEqual(["x", "y", "z"]);
  });

  it("treats an empty line inside a hunk as an empty context line", () => {
    const parsed = parseUnifiedDiff("@@ -1,3 +1,3 @@\n a\n\n-b\n+c\n");
    expect(parsed.hunks[0]!.lines.map((line) => [line.kind, line.text, line.oldNumber])).toEqual([
      ["context", "a", 1],
      ["context", "", 2],
      ["remove", "b", 3],
      ["add", "c", null],
    ]);
  });

  it("uses the hunk counts so removed lines starting with dashes are not file headers", () => {
    const parsed = parseUnifiedDiff("@@ -1 +1 @@\n--- not a header\n+++ not a header either\n");
    expect(parsed.oldFile).toBeNull();
    expect(parsed.newFile).toBeNull();
    expect(parsed.hunks[0]!.lines.map((line) => [line.kind, line.text])).toEqual([
      ["remove", "-- not a header"],
      ["add", "++ not a header either"],
    ]);
  });

  it("ignores git metadata lines", () => {
    const diff = ["diff --git a/f.py b/f.py", "index 123..456 100644", "--- a/f.py", "+++ b/f.py", "@@ -1 +1 @@", "-a", "+b"].join("\n");
    expect(parseUnifiedDiff(diff).hunks).toHaveLength(1);
  });

  it("rejects a truncated hunk", () => {
    expect(() => parseUnifiedDiff("@@ -1,3 +1,3 @@\n a\n-b\n")).toThrow(DiffParseError);
  });

  it("rejects lines that do not belong to a diff", () => {
    expect(() => parseUnifiedDiff("this is not a diff")).toThrow(/outside a hunk/);
    expect(() => parseUnifiedDiff("@@ -1,2 +1,2 @@\n a\n?b\n c\n")).toThrow(/inside a hunk/);
    expect(() => parseUnifiedDiff("@@ -1 +1 @@\n-a\n-b\n+c\n")).toThrow(/Removed line exceeds/);
  });

  it("rejects a no-newline marker with no line before it", () => {
    expect(() => parseUnifiedDiff("\\ No newline at end of file\n")).toThrow(DiffParseError);
  });

  it("reports the diff line number of a problem", () => {
    try {
      parseUnifiedDiff("@@ -1,2 +1,2 @@\n a\n?b\n");
      expect.unreachable();
    } catch (error) {
      expect(error).toBeInstanceOf(DiffParseError);
      expect((error as DiffParseError).lineNumber).toBe(3);
    }
  });
});

describe("splitSourceLines", () => {
  it("follows Python's splitlines for LF, CRLF and CR", () => {
    expect(splitSourceLines("")).toEqual([]);
    expect(splitSourceLines("a")).toEqual(["a"]);
    expect(splitSourceLines("a\n")).toEqual(["a"]);
    expect(splitSourceLines("a\r\nb\rc\n\n")).toEqual(["a", "b", "c", ""]);
  });
});

describe("buildSplitRows", () => {
  it("aligns the full texts and pairs removals with their replacements", () => {
    const rows = buildSplitRows(ORIGINAL_CODE, PROPOSED_CODE, parseUnifiedDiff(DIFF_TEXT));
    expect(rows).not.toBeNull();
    expect(rows).toHaveLength(9);
    expect(rows![0]).toEqual({
      left: { kind: "context", number: 1, text: "def shipping_cost(weight, express):" },
      right: { kind: "context", number: 1, text: "def shipping_cost(weight, express):" },
    });
    expect(rows![2]).toEqual({
      left: { kind: "remove", number: 3, text: "    if weight > 0:" },
      right: { kind: "add", number: 3, text: "    if weight <= 0:" },
    });
    // Seven removed lines against five added lines: the last two rows have an empty right side.
    expect(rows![7]!.right.kind).toBe("empty");
    expect(rows![8]).toEqual({
      left: { kind: "remove", number: 9, text: '        raise ValueError("weight must be positive")' },
      right: { kind: "empty", number: null, text: "" },
    });
  });

  it("adds unchanged lines outside the hunks on both sides", () => {
    const original = "a\nb\nc\nd\ne\n";
    const proposed = "a\nb\nC\nd\ne\nf\n";
    const diff = "@@ -3 +3 @@\n-c\n+C\n@@ -5,0 +6 @@\n+f\n";
    const rows = buildSplitRows(original, proposed, parseUnifiedDiff(diff));
    expect(rows?.map((row) => [row.left.number, row.left.kind, row.right.number, row.right.kind])).toEqual([
      [1, "context", 1, "context"],
      [2, "context", 2, "context"],
      [3, "remove", 3, "add"],
      [4, "context", 4, "context"],
      [5, "context", 5, "context"],
      [null, "empty", 6, "add"],
    ]);
  });

  it("returns identical rows when there is no diff and the texts are equal", () => {
    const rows = buildSplitRows("x = 1\n", "x = 1\n", parseUnifiedDiff(""));
    expect(rows).toEqual([
      { left: { kind: "context", number: 1, text: "x = 1" }, right: { kind: "context", number: 1, text: "x = 1" } },
    ]);
  });

  it("returns null when the diff does not describe the two texts", () => {
    expect(buildSplitRows("a\n", "b\n", parseUnifiedDiff(""))).toBeNull();
    expect(buildSplitRows(ORIGINAL_CODE, PROPOSED_CODE.replace("<= 0", "< 0"), parseUnifiedDiff(DIFF_TEXT))).toBeNull();
    expect(buildSplitRows("a\nb\n", "a\nb\nc\n", parseUnifiedDiff(""))).toBeNull();
  });
});
