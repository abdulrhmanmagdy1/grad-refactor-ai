/** Text helpers that mirror how the Python service measures and compares code. */

/** Number of Unicode code points, which is what Python's len() counts for the API limit. */
export function countCodePoints(text: string): number {
  let count = 0;
  for (let index = 0; index < text.length; index += 1) {
    const unit = text.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff && index + 1 < text.length) {
      const next = text.charCodeAt(index + 1);
      if (next >= 0xdc00 && next <= 0xdfff) index += 1;
    }
    count += 1;
  }
  return count;
}

/** CRLF and lone CR become LF, as normalize_newlines() does on the server. */
export function normalizeNewlines(text: string): string {
  return text.replace(/\r\n?/g, "\n");
}

/** Line count as len(code.splitlines()) for \n, \r\n and \r line breaks. */
export function countLines(text: string): number {
  if (text === "") return 0;
  const lines = normalizeNewlines(text).split("\n");
  return text.endsWith("\n") || text.endsWith("\r") ? lines.length - 1 : lines.length;
}

/** Number of rows the editor shows, including an empty last line after a final newline. */
export function countEditorRows(text: string): number {
  return normalizeNewlines(text).split("\n").length;
}

/**
 * Mirrors matches_reference_case() in src/refactor_ai/runs/records.py: equal after
 * newline normalization, ignoring trailing whitespace at the end.
 */
export function matchesCaseCode(code: string, caseCode: string): boolean {
  return normalizeNewlines(code).trimEnd() === normalizeNewlines(caseCode).trimEnd();
}

/** Character offsets of a 1-based line in text, or null when the line does not exist. */
export function lineOffsets(text: string, line: number): { start: number; end: number } | null {
  if (!Number.isInteger(line) || line < 1) return null;
  let start = 0;
  for (let current = 1; current < line; current += 1) {
    const newline = text.indexOf("\n", start);
    if (newline === -1) return null;
    start = newline + 1;
  }
  const newline = text.indexOf("\n", start);
  return { start, end: newline === -1 ? text.length : newline };
}

/** Replaces the selection with `insert` and returns the new value and caret position. */
export function replaceSelection(
  value: string,
  selectionStart: number,
  selectionEnd: number,
  insert: string,
): { value: string; caret: number } {
  const start = Math.max(0, Math.min(selectionStart, value.length));
  const end = Math.max(start, Math.min(selectionEnd, value.length));
  return { value: value.slice(0, start) + insert + value.slice(end), caret: start + insert.length };
}

export function isBlank(text: string): boolean {
  return text.trim() === "";
}
