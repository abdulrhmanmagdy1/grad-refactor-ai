import { type KeyboardEvent, type RefObject, memo, useLayoutEffect, useMemo, useRef } from "react";
import { highlightPython } from "../lib/highlight";
import { countEditorRows, normalizeNewlines, replaceSelection } from "../lib/text";
import { CodeText } from "./CodeText";

export const INDENT = "    ";

interface GutterProps {
  rows: number;
  errorLine: number | null;
  gutterRef: RefObject<HTMLDivElement | null>;
}

const Gutter = memo(function Gutter({ rows, errorLine, gutterRef }: GutterProps) {
  const numbers = [];
  for (let line = 1; line <= rows; line += 1) {
    numbers.push(
      <span key={line} className="editor__number" data-error={line === errorLine ? "true" : undefined}>
        {line}
      </span>,
    );
  }
  return (
    <div className="editor__gutter" aria-hidden="true" ref={gutterRef} data-testid="editor-gutter">
      {numbers}
    </div>
  );
});

/** Inserts text through the browser's editing command so Ctrl+Z still undoes it. */
function insertWithUndo(text: string): boolean {
  const exec = (document as Document & { execCommand?: unknown }).execCommand;
  if (typeof exec !== "function") return false;
  try {
    return document.execCommand("insertText", false, text);
  } catch {
    return false;
  }
}

export interface CodeEditorProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  /** 1-based line to mark in the gutter, for example the line of a syntax error. */
  errorLine: number | null;
  describedBy: string;
  invalid: boolean;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
}

/**
 * A plain textarea with line numbers. Tab inserts four spaces; pressing Escape and then
 * Tab moves focus out as usual, and Shift+Tab is never intercepted, so keyboard users
 * cannot get trapped in the editor.
 */
export function CodeEditor({ id, value, onChange, errorLine, describedBy, invalid, textareaRef }: CodeEditorProps) {
  const gutterRef = useRef<HTMLDivElement>(null);
  const highlightRef = useRef<HTMLPreElement>(null);
  const pendingCaret = useRef<number | null>(null);
  const escapeArmed = useRef(false);
  const rows = countEditorRows(value);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (pendingCaret.current !== null && textarea) {
      textarea.setSelectionRange(pendingCaret.current, pendingCaret.current);
      pendingCaret.current = null;
    }
    // Keep the colored layer and the line numbers aligned after any change of content.
    if (textarea && highlightRef.current) {
      highlightRef.current.scrollTop = textarea.scrollTop;
      highlightRef.current.scrollLeft = textarea.scrollLeft;
    }
  });

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Escape") {
      escapeArmed.current = true;
      return;
    }
    if (event.key !== "Tab" || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) {
      if (event.key !== "Shift") escapeArmed.current = false;
      return;
    }
    if (escapeArmed.current) {
      // Escape then Tab: let the browser move focus to the next control.
      escapeArmed.current = false;
      return;
    }
    event.preventDefault();
    if (insertWithUndo(INDENT)) return;
    const textarea = event.currentTarget;
    const next = replaceSelection(textarea.value, textarea.selectionStart, textarea.selectionEnd, INDENT);
    pendingCaret.current = next.caret;
    onChange(next.value);
  };

  return (
    <div className="editor" data-invalid={invalid ? "true" : undefined}>
      <Gutter rows={rows} errorLine={errorLine} gutterRef={gutterRef} />
      <div className="editor__surface">
        <Highlight value={value} errorLine={errorLine} highlightRef={highlightRef} />
        <textarea
          id={id}
          ref={textareaRef}
          className="editor__input"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          onBlur={() => {
            escapeArmed.current = false;
          }}
          onScroll={(event) => {
            const { scrollTop, scrollLeft } = event.currentTarget;
            if (gutterRef.current) gutterRef.current.scrollTop = scrollTop;
            if (highlightRef.current) {
              highlightRef.current.scrollTop = scrollTop;
              highlightRef.current.scrollLeft = scrollLeft;
            }
          }}
          spellCheck={false}
          autoCapitalize="off"
          autoComplete="off"
          autoCorrect="off"
          wrap="off"
          rows={18}
          placeholder="Paste one Python function here"
          aria-describedby={describedBy}
          aria-invalid={invalid ? true : undefined}
        />
      </div>
    </div>
  );
}

interface HighlightProps {
  value: string;
  errorLine: number | null;
  highlightRef: RefObject<HTMLPreElement | null>;
}

/**
 * Syntax colors drawn behind the transparent text of the textarea. The textarea stays
 * the only control; this layer is hidden from assistive technology and from forced-colors
 * mode, where the textarea shows its own text.
 */
const Highlight = memo(function Highlight({ value, errorLine, highlightRef }: HighlightProps) {
  const lines = useMemo(() => highlightPython(normalizeNewlines(value)), [value]);
  return (
    <pre className="editor__highlight" aria-hidden="true" ref={highlightRef}>
      {lines.map((line, index) => (
        <span key={index} className="editor__line" data-error={index + 1 === errorLine ? "true" : undefined}>
          <CodeText tokens={line.tokens} />
        </span>
      ))}
    </pre>
  );
});
