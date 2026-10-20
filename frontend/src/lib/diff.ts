/**
 * Unified diff parsing for the server's RunRecord.diff and alignment of the full original
 * and proposed texts for the side-by-side view.
 *
 * The parser follows the hunk counts in each "@@ -a,b +c,d @@" header, so a removed line
 * whose text starts with "--" is not mistaken for a file header. It accepts difflib and
 * git output, CRLF line endings, "\ No newline at end of file" markers and context lines
 * whose leading space was stripped. Anything else raises DiffParseError so the view can
 * fall back to the raw text instead of showing a wrong diff.
 */

export type DiffLineKind = "context" | "add" | "remove";

export interface DiffLine {
  kind: DiffLineKind;
  text: string;
  /** 1-based line number in the original text, or null for added lines. */
  oldNumber: number | null;
  /** 1-based line number in the proposed text, or null for removed lines. */
  newNumber: number | null;
  /** True when a "\ No newline at end of file" marker follows this line. */
  noNewlineAtEnd: boolean;
}

export interface DiffHunk {
  header: string;
  oldStart: number;
  oldCount: number;
  newStart: number;
  newCount: number;
  /** Text after the closing "@@", for example a function signature. */
  section: string;
  lines: DiffLine[];
}

export interface ParsedDiff {
  oldFile: string | null;
  newFile: string | null;
  hunks: DiffHunk[];
  additions: number;
  deletions: number;
}

export class DiffParseError extends Error {
  override readonly name = "DiffParseError";
  readonly lineNumber: number;

  constructor(message: string, lineNumber: number) {
    super(message);
    this.lineNumber = lineNumber;
  }
}

const HUNK_HEADER = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$/;
const GIT_HEADER =
  /^(diff |index |old mode |new mode |deleted file mode |new file mode |similarity index |dissimilarity index |rename from |rename to |copy from |copy to |Binary files )/;

function preview(line: string): string {
  return line.length > 60 ? `${line.slice(0, 57)}...` : line;
}

function fileName(raw: string): string {
  const name = raw.split("\t")[0]?.trim() ?? "";
  return name.length >= 2 && name.startsWith('"') && name.endsWith('"') ? name.slice(1, -1) : name;
}

export function emptyDiff(): ParsedDiff {
  return { oldFile: null, newFile: null, hunks: [], additions: 0, deletions: 0 };
}

export function parseUnifiedDiff(diff: string | null | undefined): ParsedDiff {
  const parsed = emptyDiff();
  if (diff == null || diff.trim() === "") return parsed;

  const lines = diff.split("\n");
  if (lines[lines.length - 1] === "") lines.pop();

  let hunk: DiffHunk | null = null;
  let oldLeft = 0;
  let newLeft = 0;
  let oldNumber = 0;
  let newNumber = 0;

  for (let index = 0; index < lines.length; index += 1) {
    const raw = lines[index] ?? "";
    const line = raw.endsWith("\r") ? raw.slice(0, -1) : raw;
    const position = index + 1;

    if (line.startsWith("\\")) {
      const last = hunk?.lines[hunk.lines.length - 1];
      if (!last) throw new DiffParseError("A no-newline marker appears before any diff line.", position);
      last.noNewlineAtEnd = true;
      continue;
    }

    if (hunk !== null && (oldLeft > 0 || newLeft > 0)) {
      const marker = line.charAt(0);
      if (marker === " " || line === "") {
        if (oldLeft === 0 || newLeft === 0) {
          throw new DiffParseError(`Context line exceeds the hunk size: "${preview(line)}".`, position);
        }
        hunk.lines.push({
          kind: "context",
          text: line.slice(1),
          oldNumber,
          newNumber,
          noNewlineAtEnd: false,
        });
        oldNumber += 1;
        newNumber += 1;
        oldLeft -= 1;
        newLeft -= 1;
      } else if (marker === "-") {
        if (oldLeft === 0) {
          throw new DiffParseError(`Removed line exceeds the hunk size: "${preview(line)}".`, position);
        }
        hunk.lines.push({
          kind: "remove",
          text: line.slice(1),
          oldNumber,
          newNumber: null,
          noNewlineAtEnd: false,
        });
        oldNumber += 1;
        oldLeft -= 1;
        parsed.deletions += 1;
      } else if (marker === "+") {
        if (newLeft === 0) {
          throw new DiffParseError(`Added line exceeds the hunk size: "${preview(line)}".`, position);
        }
        hunk.lines.push({
          kind: "add",
          text: line.slice(1),
          oldNumber: null,
          newNumber,
          noNewlineAtEnd: false,
        });
        newNumber += 1;
        newLeft -= 1;
        parsed.additions += 1;
      } else {
        throw new DiffParseError(`Unexpected line inside a hunk: "${preview(line)}".`, position);
      }
      continue;
    }

    const header = HUNK_HEADER.exec(line);
    if (header) {
      const oldStart = Number(header[1]);
      const oldCount = header[2] === undefined ? 1 : Number(header[2]);
      const newStart = Number(header[3]);
      const newCount = header[4] === undefined ? 1 : Number(header[4]);
      hunk = {
        header: line,
        oldStart,
        oldCount,
        newStart,
        newCount,
        section: (header[5] ?? "").trim(),
        lines: [],
      };
      parsed.hunks.push(hunk);
      oldLeft = oldCount;
      newLeft = newCount;
      oldNumber = oldStart;
      newNumber = newStart;
      continue;
    }
    if (line.startsWith("--- ")) {
      parsed.oldFile = fileName(line.slice(4));
      hunk = null;
      continue;
    }
    if (line.startsWith("+++ ")) {
      parsed.newFile = fileName(line.slice(4));
      hunk = null;
      continue;
    }
    if (GIT_HEADER.test(line) || line.trim() === "") continue;
    throw new DiffParseError(`Unexpected line outside a hunk: "${preview(line)}".`, position);
  }

  if (hunk !== null && (oldLeft > 0 || newLeft > 0)) {
    throw new DiffParseError("The diff ends before its last hunk is complete.", lines.length);
  }
  return parsed;
}

/** Splits source text into lines the way Python's str.splitlines() treats \n, \r\n and \r. */
export function splitSourceLines(text: string): string[] {
  if (text === "") return [];
  const lines = text.split(/\r\n|\r|\n/);
  if (lines[lines.length - 1] === "") lines.pop();
  return lines;
}

export type SplitCellKind = "context" | "remove" | "add" | "empty";

export interface SplitCell {
  kind: SplitCellKind;
  number: number | null;
  text: string;
}

export interface SplitRow {
  left: SplitCell;
  right: SplitCell;
}

const EMPTY_CELL: SplitCell = { kind: "empty", number: null, text: "" };

/**
 * Aligns the complete original and proposed texts using the parsed hunks: unchanged lines
 * sit side by side, and each block of removals is paired row by row with the additions
 * that replace it. Returns null when the diff does not describe these two texts, so the
 * caller can show both versions unaligned instead of a misleading alignment.
 */
export function buildSplitRows(original: string, proposed: string, diff: ParsedDiff): SplitRow[] | null {
  const oldLines = splitSourceLines(original);
  const newLines = splitSourceLines(proposed);
  const rows: SplitRow[] = [];
  let nextOld = 1;
  let nextNew = 1;

  const copyUnchanged = (untilOld: number): boolean => {
    while (nextOld < untilOld) {
      const left = oldLines[nextOld - 1];
      const right = newLines[nextNew - 1];
      if (left === undefined || right === undefined || left !== right) return false;
      rows.push({
        left: { kind: "context", number: nextOld, text: left },
        right: { kind: "context", number: nextNew, text: right },
      });
      nextOld += 1;
      nextNew += 1;
    }
    return true;
  };

  for (const hunk of diff.hunks) {
    const firstOld = hunk.oldCount === 0 ? hunk.oldStart + 1 : hunk.oldStart;
    const firstNew = hunk.newCount === 0 ? hunk.newStart + 1 : hunk.newStart;
    if (firstOld < nextOld || firstNew < nextNew) return null;
    if (firstOld - nextOld !== firstNew - nextNew) return null;
    if (!copyUnchanged(firstOld)) return null;

    let removed: SplitCell[] = [];
    let added: SplitCell[] = [];
    const flush = () => {
      const count = Math.max(removed.length, added.length);
      for (let k = 0; k < count; k += 1) {
        rows.push({ left: removed[k] ?? EMPTY_CELL, right: added[k] ?? EMPTY_CELL });
      }
      removed = [];
      added = [];
    };

    for (const line of hunk.lines) {
      if (line.kind === "context") {
        flush();
        const oldIndex = (line.oldNumber ?? 0) - 1;
        const newIndex = (line.newNumber ?? 0) - 1;
        if (oldLines[oldIndex] !== line.text || newLines[newIndex] !== line.text) return null;
        rows.push({
          left: { kind: "context", number: line.oldNumber, text: line.text },
          right: { kind: "context", number: line.newNumber, text: line.text },
        });
      } else if (line.kind === "remove") {
        if (added.length > 0) flush();
        if (oldLines[(line.oldNumber ?? 0) - 1] !== line.text) return null;
        removed.push({ kind: "remove", number: line.oldNumber, text: line.text });
      } else {
        if (newLines[(line.newNumber ?? 0) - 1] !== line.text) return null;
        added.push({ kind: "add", number: line.newNumber, text: line.text });
      }
    }
    flush();
    nextOld = firstOld + hunk.oldCount;
    nextNew = firstNew + hunk.newCount;
  }

  if (oldLines.length - nextOld !== newLines.length - nextNew) return null;
  if (!copyUnchanged(oldLines.length + 1)) return null;
  return rows;
}
