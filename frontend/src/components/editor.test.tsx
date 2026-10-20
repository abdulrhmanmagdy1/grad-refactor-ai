import { fireEvent, render, screen } from "@testing-library/react";
import { useRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { CodeEditor } from "./CodeEditor";

function Harness({ initial = "", errorLine = null }: { initial?: string; errorLine?: number | null }) {
  const [value, setValue] = useState(initial);
  const ref = useRef<HTMLTextAreaElement>(null);
  return (
    <>
      <label htmlFor="code">Python function</label>
      <CodeEditor
        id="code"
        value={value}
        onChange={setValue}
        errorLine={errorLine}
        describedBy=""
        invalid={false}
        textareaRef={ref}
      />
    </>
  );
}

function editor(): HTMLTextAreaElement {
  return screen.getByLabelText("Python function") as HTMLTextAreaElement;
}

describe("CodeEditor", () => {
  it("inserts four spaces for Tab at the caret, replacing a selection", () => {
    render(<Harness initial={"def f():\nreturn 1"} />);
    const textarea = editor();
    textarea.setSelectionRange(9, 9);
    const event = fireEvent.keyDown(textarea, { key: "Tab" });
    expect(event).toBe(false); // default prevented
    expect(textarea.value).toBe("def f():\n    return 1");
    expect(textarea.selectionStart).toBe(13);
    expect(textarea.selectionEnd).toBe(13);

    textarea.setSelectionRange(13, 19);
    fireEvent.keyDown(textarea, { key: "Tab" });
    expect(textarea.value).toBe("def f():\n         1");
  });

  it("uses the browser's editing command when available so undo keeps working", () => {
    const exec = vi.fn(() => true);
    Object.defineProperty(document, "execCommand", { value: exec, configurable: true });
    try {
      render(<Harness initial="x" />);
      fireEvent.keyDown(editor(), { key: "Tab" });
      expect(exec).toHaveBeenCalledWith("insertText", false, "    ");
    } finally {
      delete (document as unknown as { execCommand?: unknown }).execCommand;
    }
  });

  it("lets Escape then Tab move focus out, and never intercepts Shift+Tab", () => {
    render(<Harness initial="x" />);
    const textarea = editor();
    fireEvent.keyDown(textarea, { key: "Escape" });
    expect(fireEvent.keyDown(textarea, { key: "Tab" })).toBe(true);
    expect(textarea.value).toBe("x");
    // The escape applies to one Tab only.
    expect(fireEvent.keyDown(textarea, { key: "Tab" })).toBe(false);
    expect(fireEvent.keyDown(textarea, { key: "Tab", shiftKey: true })).toBe(true);
    expect(fireEvent.keyDown(textarea, { key: "Tab", ctrlKey: true })).toBe(true);
  });

  it("forgets a pending Escape after another key or leaving the editor", () => {
    render(<Harness initial="x" />);
    const textarea = editor();
    fireEvent.keyDown(textarea, { key: "Escape" });
    fireEvent.keyDown(textarea, { key: "a" });
    expect(fireEvent.keyDown(textarea, { key: "Tab" })).toBe(false);
    fireEvent.keyDown(textarea, { key: "Escape" });
    fireEvent.blur(textarea);
    expect(fireEvent.keyDown(textarea, { key: "Tab" })).toBe(false);
  });

  it("numbers every line, including the empty line after a final newline, and marks the error line", () => {
    render(<Harness initial={"a\nb\n"} errorLine={2} />);
    const gutter = screen.getByTestId("editor-gutter");
    expect(gutter).toHaveAttribute("aria-hidden", "true");
    expect([...gutter.children].map((child) => child.textContent)).toEqual(["1", "2", "3"]);
    expect(gutter.children[1]).toHaveAttribute("data-error", "true");
    fireEvent.change(editor(), { target: { value: "a\nb\nc\nd" } });
    expect(gutter.children).toHaveLength(4);
  });

  it("keeps the textarea free of spelling and capitalization helpers", () => {
    render(<Harness />);
    const textarea = editor();
    expect(textarea).toHaveAttribute("spellcheck", "false");
    expect(textarea).toHaveAttribute("autocapitalize", "off");
    expect(textarea).toHaveAttribute("wrap", "off");
  });
});
