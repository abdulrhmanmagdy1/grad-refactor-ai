/**
 * The indentation shape of a piece of Python code, for the before/after outline drawn
 * next to a proposal. Guard clauses replace nested blocks with early exits, so the shape
 * of the code becomes flatter. This is measured from the text only, for display; the
 * service's own rubric check ("Reduces the nesting depth") remains the verdict.
 */

import { highlightPython } from "./highlight";

export interface ShapeLine {
  /** Indentation level of the statement, 0 for the def line. Null for lines that are not statements. */
  level: number | null;
  /** Leading whitespace width in columns (a tab counts as 4). */
  indent: number;
  /** Width of the line without trailing whitespace, in columns. */
  width: number;
}

export interface CodeShape {
  lines: ShapeLine[];
  /** Deepest indentation level of any statement; 0 when there is no statement. */
  maxLevel: number;
}

function columns(text: string): number {
  let width = 0;
  for (const char of text) width += char === "\t" ? 4 - (width % 4) : 1;
  return width;
}

/**
 * Levels follow Python's own rule: a line indented further than the enclosing block opens
 * a new level, and a dedent returns to the matching outer level. Blank lines, comment-only
 * lines, docstring continuations and lines inside brackets keep no level of their own.
 */
export function codeShape(code: string): CodeShape {
  const source = code.replace(/\r\n?/g, "\n").replace(/\n+$/, "");
  if (source.trim() === "") return { lines: [], maxLevel: 0 };
  const highlighted = highlightPython(source);
  const stack: number[] = [];
  let maxLevel = 0;
  const lines = source.split("\n").map((text, index): ShapeLine => {
    const trimmed = text.trimEnd();
    const indentText = /^[ \t]*/.exec(trimmed)?.[0] ?? "";
    const indent = columns(indentText);
    const width = columns(trimmed);
    const info = highlighted[index];
    const statement =
      trimmed.trim() !== "" &&
      !trimmed.trimStart().startsWith("#") &&
      info !== undefined &&
      !info.startsInString &&
      !info.startsInBracket;
    if (!statement) return { level: null, indent, width };
    if (stack.length === 0) stack.push(indent);
    else if (indent > stack[stack.length - 1]!) stack.push(indent);
    else while (stack.length > 1 && indent < stack[stack.length - 1]!) stack.pop();
    const level = stack.length - 1;
    maxLevel = Math.max(maxLevel, level);
    return { level, indent, width };
  });
  return { lines, maxLevel };
}
