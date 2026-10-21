/**
 * A small, presentation-only Python highlighter. It splits each source line into colored
 * tokens for display; it never evaluates, rewrites or interprets the code, and the joined
 * token texts always equal the input line exactly. Triple-quoted strings and open brackets
 * are carried from one line to the next, so docstrings and wrapped calls are colored and
 * measured correctly.
 */

export type TokenKind = "plain" | "keyword" | "entity" | "string" | "number" | "comment";

export interface Token {
  kind: TokenKind;
  text: string;
}

export interface HighlightedLine {
  tokens: Token[];
  /** True when the line starts inside a triple-quoted string. */
  startsInString: boolean;
  /** True when the line starts inside an open bracket (a continuation line). */
  startsInBracket: boolean;
}

const KEYWORDS = new Set([
  "and",
  "as",
  "assert",
  "async",
  "await",
  "break",
  "class",
  "continue",
  "def",
  "del",
  "elif",
  "else",
  "except",
  "finally",
  "for",
  "from",
  "global",
  "if",
  "import",
  "in",
  "is",
  "lambda",
  "nonlocal",
  "not",
  "or",
  "pass",
  "raise",
  "return",
  "try",
  "while",
  "with",
  "yield",
]);

const SOFT_KEYWORDS = new Set(["match", "case"]);
const CONSTANTS = new Set(["True", "False", "None"]);

const BUILTINS = new Set([
  "abs",
  "all",
  "any",
  "bool",
  "callable",
  "dict",
  "divmod",
  "enumerate",
  "filter",
  "float",
  "frozenset",
  "getattr",
  "hasattr",
  "int",
  "isinstance",
  "issubclass",
  "len",
  "list",
  "map",
  "max",
  "min",
  "object",
  "pow",
  "print",
  "range",
  "repr",
  "reversed",
  "round",
  "set",
  "sorted",
  "str",
  "sum",
  "tuple",
  "type",
  "zip",
  "Exception",
  "ArithmeticError",
  "AssertionError",
  "AttributeError",
  "IndexError",
  "KeyError",
  "LookupError",
  "NotImplementedError",
  "OverflowError",
  "RuntimeError",
  "StopIteration",
  "TypeError",
  "ValueError",
  "ZeroDivisionError",
]);

const NUMBER = /^(?:0[xX][0-9a-fA-F_]+|0[oO][0-7_]+|0[bB][01_]+|(?:\d[\d_]*\.?[\d_]*|\.\d[\d_]*)(?:[eE][+-]?\d[\d_]*)?[jJ]?)/;
const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*/;
const STRING_START = /^([rRbBuUfF]{0,2})("""|'''|"|')/;

function push(tokens: Token[], kind: TokenKind, text: string) {
  if (text === "") return;
  const last = tokens[tokens.length - 1];
  if (last && last.kind === kind) last.text += text;
  else tokens.push({ kind, text });
}

/** Index just after the closing quote, or -1 when the string continues past the line. */
function findStringEnd(line: string, from: number, quote: string): number {
  for (let index = from; index < line.length; index += 1) {
    const char = line[index];
    if (char === "\\") {
      index += 1;
      continue;
    }
    if (line.startsWith(quote, index)) return index + quote.length;
  }
  return -1;
}

/** Splits source text into highlighted lines (split on \n; a \r before it is kept as text). */
export function highlightPython(source: string): HighlightedLine[] {
  const lines = source.split("\n");
  const result: HighlightedLine[] = [];
  let openQuote: string | null = null;
  let bracketDepth = 0;

  for (const line of lines) {
    const tokens: Token[] = [];
    const startsInString = openQuote !== null;
    const startsInBracket = !startsInString && bracketDepth > 0;
    let index = 0;
    let previousWord: string | null = null;

    if (openQuote !== null) {
      const end = findStringEnd(line, 0, openQuote);
      if (end === -1) {
        push(tokens, "string", line);
        result.push({ tokens, startsInString, startsInBracket });
        continue;
      }
      push(tokens, "string", line.slice(0, end));
      index = end;
      openQuote = null;
    }

    while (index < line.length) {
      const rest = line.slice(index);
      const char = line[index]!;

      if (char === "#") {
        push(tokens, "comment", rest);
        break;
      }

      const stringStart = STRING_START.exec(rest);
      if (stringStart && (stringStart[1] === "" || !/[A-Za-z0-9_]/.test(line[index - 1] ?? ""))) {
        const prefix = stringStart[1] ?? "";
        const quote = stringStart[2]!;
        const bodyStart = index + prefix.length + quote.length;
        const end = findStringEnd(line, bodyStart, quote);
        if (end === -1) {
          push(tokens, "string", rest);
          // Only triple quotes continue on the next line; an unterminated short string ends here.
          if (quote.length === 3) openQuote = quote;
          index = line.length;
          break;
        }
        push(tokens, "string", line.slice(index, end));
        index = end;
        previousWord = null;
        continue;
      }

      if (/[0-9]/.test(char) || (char === "." && /[0-9]/.test(line[index + 1] ?? ""))) {
        const number = NUMBER.exec(rest);
        if (number && number[0] !== "") {
          push(tokens, "number", number[0]);
          index += number[0].length;
          previousWord = null;
          continue;
        }
      }

      const identifier = IDENTIFIER.exec(rest);
      if (identifier) {
        const word = identifier[0];
        const before = line.slice(0, index);
        let kind: TokenKind = "plain";
        if (previousWord === "def" || previousWord === "class") kind = "entity";
        else if (KEYWORDS.has(word)) kind = "keyword";
        else if (SOFT_KEYWORDS.has(word) && before.trim() === "" && /^\s+[^=\s]/.test(line.slice(index + word.length)))
          kind = "keyword";
        else if (CONSTANTS.has(word)) kind = "number";
        else if (BUILTINS.has(word) && !before.endsWith(".")) kind = "entity";
        else if (before.endsWith("@") && before.trim() === "@") kind = "entity";
        push(tokens, kind, word);
        index += word.length;
        previousWord = word;
        continue;
      }

      if (char === "(" || char === "[" || char === "{") bracketDepth += 1;
      else if (char === ")" || char === "]" || char === "}") bracketDepth = Math.max(0, bracketDepth - 1);
      if (char === "@" && line.slice(0, index).trim() === "") push(tokens, "entity", char);
      else push(tokens, "plain", char);
      if (!/\s/.test(char)) previousWord = null;
      index += 1;
    }

    result.push({ tokens, startsInString, startsInBracket });
  }
  return result;
}
