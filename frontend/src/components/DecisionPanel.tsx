import { useId } from "react";
import type { ApiError } from "../api/client";
import type { Disposition, HumanDecision } from "../api/contracts";
import { DISPOSITION_META } from "../lib/labels";
import { Icon } from "./Icon";

export interface DecisionState {
  pending: HumanDecision | null;
  error: ApiError | null;
}

/**
 * Records the person's accept or reject decision. It never edits the input or any file;
 * using the proposal means downloading or copying it.
 */
export function DecisionPanel({
  decision,
  disposition,
  state,
  onDecide,
}: {
  decision: HumanDecision | null;
  disposition: Disposition | null;
  state: DecisionState;
  onDecide: (decision: HumanDecision) => void;
}) {
  const ids = useId();
  const busy = state.pending !== null;
  return (
    <section className="result-section decision" aria-labelledby={`${ids}-heading`}>
      <div className="section-head">
        <h3 id={`${ids}-heading`}>Your decision</h3>
        <p className="section-head__note">
          Your files are never changed. Copy or download the new code to use it.
        </p>
      </div>
      {disposition !== null && disposition !== "proposal_ready" ? (
        <p className="notice" data-tone="warn">
          The checks say: {DISPOSITION_META[disposition].label}. Be careful before you accept.
        </p>
      ) : null}
      <div className="decision__buttons" role="group" aria-label="Decision on the proposal">
        <button
          type="button"
          className="button"
          data-variant="accept"
          aria-pressed={decision === "accepted"}
          disabled={busy}
          onClick={() => onDecide("accepted")}
        >
          <Icon name="check" />
          {state.pending === "accepted" ? "Recording…" : "Accept proposal"}
        </button>
        <button
          type="button"
          className="button"
          data-variant="reject"
          aria-pressed={decision === "rejected"}
          disabled={busy}
          onClick={() => onDecide("rejected")}
        >
          <Icon name="cross" />
          {state.pending === "rejected" ? "Recording…" : "Reject proposal"}
        </button>
      </div>
      <p className="decision__status" role="status">
        {decision === "accepted" ? "Decision recorded: accepted." : null}
        {decision === "rejected" ? "Decision recorded: rejected." : null}
        {decision === null && !busy ? "No decision recorded yet." : null}
      </p>
      {state.error ? (
        <p className="field-message" data-tone="fail" role="alert">
          The decision was not recorded: {state.error.message}
        </p>
      ) : null}
    </section>
  );
}
