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

/** The overall outcome of a completed run, derived by the service from the separate checks. */
export function DispositionBanner({
  verification,
  fake,
}: {
  verification: VerificationResult | null;
  fake: boolean;
}) {
  if (!verification) {
    return (
      <section className="disposition" data-tone="neutral" aria-label="Outcome">
        <span className="disposition__icon" aria-hidden="true">
          <Icon name="dash" />
        </span>
        <div className="disposition__body">
          <h3 className="disposition__title">No verification result was recorded</h3>
          <p className="disposition__summary">The service stored no verification result for this run.</p>
        </div>
      </section>
    );
  }
  const meta = DISPOSITION_META[verification.disposition];
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
          {fake ? <span className="tag tag--fake">Fake provider output</span> : null}
        </h3>
        <p className="disposition__summary">{meta.summary}</p>
        {fake ? (
          <p className="disposition__fake">
            This run used the deterministic test provider, not a language model. Its result is not evidence of
            model behavior.
          </p>
        ) : null}
        {verification.disposition_reasons.length > 0 ? (
          <div className="disposition__reasons">
            <p className="disposition__reasons-title">Reasons given by the service</p>
            <ReasonList reasons={verification.disposition_reasons} />
          </div>
        ) : null}
      </div>
    </section>
  );
}
