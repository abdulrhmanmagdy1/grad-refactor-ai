/**
 * Editor state: the code being written, the workflow choice and the demonstration case
 * that was loaded last. The reference-case link is derived, never stored: the request
 * carries reference_case_id only while the code still matches the case exactly (the
 * server's own rule), so any edit removes the link and undoing the edit restores it.
 */

import type { ReferenceCaseSummary, WorkflowMode } from "../api/contracts";
import { isBlank, matchesCaseCode, normalizeNewlines } from "../lib/text";

export interface RestorePoint {
  code: string;
  loadedCase: ReferenceCaseSummary | null;
  message: string;
}

export interface EditorState {
  code: string;
  workflowMode: WorkflowMode;
  loadedCase: ReferenceCaseSummary | null;
  /** The content replaced by the last explicit load, offered back to the person. */
  restore: RestorePoint | null;
}

export type EditorAction =
  | { type: "edit"; code: string }
  | { type: "set_mode"; mode: WorkflowMode }
  | { type: "load_case"; referenceCase: ReferenceCaseSummary }
  | {
      type: "load_input";
      code: string;
      mode: WorkflowMode;
      linkedCase: ReferenceCaseSummary | null;
      label: string;
    }
  | { type: "restore" }
  | { type: "dismiss_restore" }
  | { type: "reset_case_code" }
  | { type: "unlink_case" };

export const initialEditorState: EditorState = {
  code: "",
  workflowMode: "multi_role",
  loadedCase: null,
  restore: null,
};

export function caseTitle(referenceCase: ReferenceCaseSummary): string {
  return referenceCase.title?.trim() || referenceCase.function_name;
}

/** The case whose tests apply to the current code, or null. */
export function linkedCase(state: EditorState): ReferenceCaseSummary | null {
  const loaded = state.loadedCase;
  return loaded && matchesCaseCode(state.code, loaded.code) ? loaded : null;
}

function replaceContent(
  state: EditorState,
  code: string,
  loadedCase: ReferenceCaseSummary | null,
  message: string,
): EditorState {
  const current = state.code;
  // Unchanged case code can be reloaded at any time, so an older restore point is kept.
  const currentIsPristineCase = state.loadedCase !== null && matchesCaseCode(current, state.loadedCase.code);
  let restore: RestorePoint | null;
  if (currentIsPristineCase && state.restore) {
    restore = { ...state.restore, message };
  } else if (isBlank(current) || normalizeNewlines(current) === code || currentIsPristineCase) {
    restore = null;
  } else {
    restore = { code: current, loadedCase: state.loadedCase, message };
  }
  return { ...state, code, loadedCase, restore };
}

export function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "edit":
      return { ...state, code: action.code };
    case "set_mode":
      return { ...state, workflowMode: action.mode };
    case "load_case": {
      const code = normalizeNewlines(action.referenceCase.code);
      return replaceContent(
        state,
        code,
        action.referenceCase,
        `Your previous code was replaced by the demonstration case "${caseTitle(action.referenceCase)}".`,
      );
    }
    case "load_input": {
      const next = replaceContent(
        state,
        normalizeNewlines(action.code),
        action.linkedCase,
        `Your previous code was replaced by the input of ${action.label}.`,
      );
      return { ...next, workflowMode: action.mode };
    }
    case "restore":
      if (!state.restore) return state;
      return { ...state, code: state.restore.code, loadedCase: state.restore.loadedCase, restore: null };
    case "dismiss_restore":
      return { ...state, restore: null };
    case "reset_case_code":
      if (!state.loadedCase) return state;
      return { ...state, code: normalizeNewlines(state.loadedCase.code) };
    case "unlink_case":
      return { ...state, loadedCase: null };
  }
}
