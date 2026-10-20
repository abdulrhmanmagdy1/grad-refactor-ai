// @vitest-environment node
import { describe, expect, it } from "vitest";
import {
  DISPOSITIONS,
  MODEL_REVIEW_STATUSES,
  REFERENCE_TEST_STATUSES,
  RUBRIC_STATUSES,
  SYNTAX_STATUSES,
  hasProposal,
} from "../api/contracts";
import {
  formatDuration,
  formatElapsed,
  parseServerTime,
  plural,
  secondsBetween,
  shortHash,
} from "./format";
import {
  DISPOSITION_META,
  MODEL_REVIEW_META,
  REFERENCE_TESTS_META,
  RUBRIC_META,
  SYNTAX_META,
  isFakeText,
  rubricCheckLabel,
  splitReason,
  stepForStage,
} from "./labels";
import {
  countCodePoints,
  countEditorRows,
  countLines,
  isBlank,
  lineOffsets,
  matchesCaseCode,
  normalizeNewlines,
  replaceSelection,
} from "./text";

describe("text helpers mirror the Python service", () => {
  it("counts code points like Python's len()", () => {
    expect(countCodePoints("")).toBe(0);
    expect(countCodePoints("abc")).toBe(3);
    expect(countCodePoints("a\nb")).toBe(3);
    expect(countCodePoints("😀")).toBe(1);
    expect("😀".length).toBe(2);
    expect(countCodePoints("\ud800x")).toBe(2);
  });

  it("counts lines like len(str.splitlines())", () => {
    expect(countLines("")).toBe(0);
    expect(countLines("a")).toBe(1);
    expect(countLines("a\n")).toBe(1);
    expect(countLines("a\nb")).toBe(2);
    expect(countLines("a\r\nb\r\n")).toBe(2);
    expect(countLines("\n\n")).toBe(2);
    expect(countEditorRows("a\n")).toBe(2);
    expect(countEditorRows("")).toBe(1);
  });

  it("normalizes newlines and compares case code like matches_reference_case()", () => {
    expect(normalizeNewlines("a\r\nb\rc")).toBe("a\nb\nc");
    expect(matchesCaseCode("def f():\r\n    return 1\r\n", "def f():\n    return 1\n")).toBe(true);
    expect(matchesCaseCode("def f():\n    return 1\n\n\n  ", "def f():\n    return 1")).toBe(true);
    expect(matchesCaseCode(" def f():\n    return 1\n", "def f():\n    return 1\n")).toBe(false);
    expect(matchesCaseCode("def f():\n    return 2\n", "def f():\n    return 1\n")).toBe(false);
  });

  it("finds line offsets and replaces selections", () => {
    expect(lineOffsets("ab\ncd\nef", 2)).toEqual({ start: 3, end: 5 });
    expect(lineOffsets("ab\ncd", 3)).toBeNull();
    expect(lineOffsets("ab", 0)).toBeNull();
    expect(replaceSelection("abcdef", 2, 4, "    ")).toEqual({ value: "ab    ef", caret: 6 });
    expect(replaceSelection("ab", 5, 9, "x")).toEqual({ value: "abx", caret: 3 });
    expect(isBlank(" \n\t")).toBe(true);
    expect(isBlank(" x ")).toBe(false);
  });
});

describe("format helpers", () => {
  it("reads service timestamps, with or without a zone, and microseconds", () => {
    expect(parseServerTime("2026-10-20T09:16:05Z")).toBe(Date.UTC(2026, 9, 20, 9, 16, 5));
    expect(parseServerTime("2026-10-20T09:16:00.100000Z")).toBe(Date.UTC(2026, 9, 20, 9, 16, 0, 100));
    expect(parseServerTime("2026-10-20T09:16:00.5+02:00")).toBe(Date.UTC(2026, 9, 20, 7, 16, 0, 500));
    expect(parseServerTime("2026-10-20T09:16:05")).toBe(Date.UTC(2026, 9, 20, 9, 16, 5));
    expect(parseServerTime("not a date")).toBeNull();
    expect(parseServerTime(null)).toBeNull();
  });

  it("formats durations and elapsed time", () => {
    expect(formatDuration(0.0004)).toBe("< 1 ms");
    expect(formatDuration(0.42)).toBe("420 ms");
    expect(formatDuration(4.25)).toBe("4.3 s");
    expect(formatDuration(42.4)).toBe("42 s");
    expect(formatDuration(59.6)).toBe("1 min 00 s");
    expect(formatDuration(125)).toBe("2 min 05 s");
    expect(formatDuration(3725)).toBe("1 h 02 min");
    expect(formatDuration(null)).toBe("Not recorded");
    expect(formatElapsed(0)).toBe("0 s");
    expect(formatElapsed(65_900)).toBe("1 min 05 s");
    expect(formatElapsed(3_723_000)).toBe("1 h 02 min 03 s");
    expect(secondsBetween("2026-10-20T09:02:00Z", "2026-10-20T09:02:01.5Z")).toBe(1.5);
    expect(secondsBetween("2026-10-20T09:02:00Z", null)).toBeNull();
  });

  it("formats counts and hashes", () => {
    expect(plural(1, "test")).toBe("1 test");
    expect(plural(20000, "character")).toBe("20,000 characters");
    expect(shortHash("abcdef0123456789")).toBe("abcdef012345…");
    expect(shortHash("fake-v1")).toBe("fake-v1");
  });
});

describe("status vocabulary", () => {
  it("covers every contract value", () => {
    expect(Object.keys(SYNTAX_META).sort()).toEqual([...SYNTAX_STATUSES].sort());
    expect(Object.keys(RUBRIC_META).sort()).toEqual([...RUBRIC_STATUSES].sort());
    expect(Object.keys(REFERENCE_TESTS_META).sort()).toEqual([...REFERENCE_TEST_STATUSES].sort());
    expect(Object.keys(MODEL_REVIEW_META).sort()).toEqual([...MODEL_REVIEW_STATUSES].sort());
    expect(Object.keys(DISPOSITION_META).sort()).toEqual([...DISPOSITIONS].sort());
  });

  it("never gives missing evidence the pass tone", () => {
    const absent = [
      SYNTAX_META.not_run,
      RUBRIC_META.not_run,
      REFERENCE_TESTS_META.not_available,
      REFERENCE_TESTS_META.not_run,
      REFERENCE_TESTS_META.error,
      MODEL_REVIEW_META.not_run,
      MODEL_REVIEW_META.error,
    ];
    for (const meta of absent) {
      expect(meta.tone).not.toBe("pass");
      expect(meta.icon).not.toBe("check");
      expect(meta.evidence).toBe("absent");
    }
    expect(REFERENCE_TESTS_META.not_available.label).not.toBe(REFERENCE_TESTS_META.not_run.label);
    expect(REFERENCE_TESTS_META.error.tone).toBe("warn");
  });

  it("maps the free-text error stage to a progress step", () => {
    expect(stepForStage("generation")).toBe("generating");
    expect(stepForStage("generating")).toBe("generating");
    expect(stepForStage("analysis")).toBe("analyzing");
    expect(stepForStage("review")).toBe("verifying");
    expect(stepForStage("verification")).toBe("verifying");
    expect(stepForStage("validation")).toBe("queued");
    expect(stepForStage("elsewhere")).toBeNull();
    expect(stepForStage(null)).toBeNull();
  });

  it("splits coded reasons and expands bare task codes", () => {
    expect(splitReason("no_opportunity: No nested conditional can be flattened with guard clauses.")).toEqual({
      code: "no_opportunity",
      text: "No nested conditional can be flattened with guard clauses.",
    });
    expect(splitReason("timeout: Generation exceeded 120.0 s")).toEqual({
      code: "timeout",
      text: "Generation exceeded 120.0 s",
    });
    expect(splitReason("too_long")).toEqual({ code: "too_long", text: "The input exceeds 3000 characters or 60 lines." });
    expect(splitReason("denied_call:print")).toEqual({
      code: "denied_call:print",
      text: "Calls to print() are outside the supported scope.",
    });
    expect(splitReason("1 of 4 reference tests failed.")).toEqual({ code: null, text: "1 of 4 reference tests failed." });
    expect(splitReason("Reference tests are not available; behavior was not checked.").code).toBeNull();
  });

  it("labels rubric checks and recognizes fake text", () => {
    expect(rubricCheckLabel("nesting_reduced")).toBe("Reduces the nesting depth");
    expect(rubricCheckLabel("brand_new_check")).toBe("Brand new check");
    expect(isFakeText("FAKE PROVIDER (not a model): placeholder")).toBe(true);
    expect(isFakeText("A real explanation")).toBe(false);
  });
});

describe("hasProposal mirrors proposal_problem()", () => {
  it.each([
    [{ status: "completed", proposed_code: "def f():\n    return 1\n" }, true],
    [{ status: "completed", proposed_code: " " }, true],
    [{ status: "completed", proposed_code: "" }, false],
    [{ status: "completed", proposed_code: null }, false],
    [{ status: "failed", proposed_code: "def f(): pass\n" }, false],
    [{ status: "verifying", proposed_code: "def f(): pass\n" }, false],
  ] as const)("%j -> %s", (record, expected) => {
    expect(hasProposal(record)).toBe(expected);
  });
});
