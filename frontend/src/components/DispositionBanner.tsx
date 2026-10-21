import type { ReactNode } from "react";
import type { VerificationResult } from "../api/contracts";
import { DISPOSITION_META, splitReason } from "../lib/labels";
import { Icon } from "./Icon";

export function ReasonList({ reasons, className = "reasons" }: { reasons: string[]; className?: string }) {
  if (reasons.length === 0) return null;
  return (
    <ul className={className}>
      {reasons.map((reason, index) => {
        const parts = splitReason(reason);
        return (
          <li key={index}>
            {parts.text}
            {parts.code ? (
              <>
                {" "}
                <code className="code-tag">{parts.code}</code>
              </>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

/** Shortest useful reason: the first service reason when it is brief, otherwise nothing. */
function shortReason(reasons: string[]): string | null {
  const first = reasons[0];
  if (!first) return null;
  const text = splitReason(first).text;
  return text.split(/\s+/).length <= 16 ? text : null;
}

/** The overall outcome of a completed run, derived by the service from the separate checks. */
export function DispositionBanner({
  verification,
  fake,
  aside = null,
}: {
  verification: VerificationResult | null;
  fake: boolean;
  /** Optional figure shown beside the outcome, such as the outline of the change. */
  aside?: ReactNode;
}) {
  if (!verification) {
    return (
      <section className="disposition" data-tone="neutral" aria-label="Outcome">
        <span className="disposition__icon" aria-hidden="true">
          <Icon name="dash" />
        </span>
        <div className="disposition__body">
          <h3 className="disposition__title">No result saved</h3>
          <p className="disposition__summary">The service saved no checks for this run.</p>
        </div>
      </section>
    );
  }
  const meta = DISPOSITION_META[verification.disposition];
  const reason = verification.disposition === "proposal_ready" ? null : shortReason(verification.disposition_reasons);
  return (
    <section
      className="disposition"
      data-tone={meta.tone}
      data-disposition={verification.disposition}
      aria-label={`Outcome: ${meta.label}`}
    >
      <span className="disposition__icon" aria-hidden="true">
        <Icon name={meta.icon} />
      </span>
      <div className="disposition__body">
        <h3 className="disposition__title">
          {meta.title}
          {fake ? <span className="tag tag--fake">Demo</span> : null}
        </h3>
        <p className="disposition__summary">{meta.summary}</p>
        {reason ? <p className="disposition__reason">{reason}</p> : null}
      </div>
      {aside ? <div className="disposition__aside">{aside}</div> : null}
    </section>
  );
}
