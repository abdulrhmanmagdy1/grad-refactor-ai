import type { ReactNode } from "react";
import { type HighlightedLine, type Token, highlightPython } from "../lib/highlight";

/** Tokens for a line of a highlighted text, or the line highlighted on its own when the
 * line number does not point at the same text (for example a diff that disagrees). */
export function tokensFor(lines: HighlightedLine[], number: number | null, text: string): Token[] {
  if (number !== null) {
    const line = lines[number - 1];
    if (line) {
      const joined = line.tokens.map((token) => token.text).join("");
      if (joined === text || joined.replace(/\r$/, "") === text) return line.tokens;
    }
  }
  return highlightPython(text)[0]?.tokens ?? [];
}

/**
 * One line of code with syntax colors and indentation guides. The rendered text content is
 * exactly the line's text, so copying, searching and tests see the original characters.
 */
export function CodeText({ tokens }: { tokens: Token[] }) {
  const text = tokens.map((token) => token.text).join("");
  const indentLength = /^[ \t]*/.exec(text)?.[0].length ?? 0;
  const parts: ReactNode[] = [];
  if (indentLength > 0) {
    parts.push(
      <span key="indent" className="indent">
        {text.slice(0, indentLength)}
      </span>,
    );
  }
  let consumed = 0;
  tokens.forEach((token, index) => {
    const start = consumed;
    consumed += token.text.length;
    const visible = start < indentLength ? token.text.slice(Math.min(token.text.length, indentLength - start)) : token.text;
    if (visible === "") return;
    parts.push(
      token.kind === "plain" ? (
        <span key={index}>{visible}</span>
      ) : (
        <span key={index} className={`tok tok--${token.kind}`}>
          {visible}
        </span>
      ),
    );
  });
  return <>{parts}</>;
}
