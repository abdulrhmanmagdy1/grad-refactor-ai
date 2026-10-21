import type { ReactNode } from "react";
import type {
  ModelReviewResult,
  ReferenceTestsResult,
  ReviewResult,
  RubricCheck,
  SyntaxCheck,
  VerificationResult,
  WorkflowMode,
} from "../api/contracts";
import { formatDuration, plural } from "../lib/format";
import {
  FAILURE_KIND_LABELS,
  MODEL_REVIEW_META,
  REFERENCE_TESTS_META,
  RUBRIC_META,
  type StatusMeta,
  SYNTAX_META,
  rubricCheckLabel,
} from "../lib/labels";
import { ReasonList } from "./DispositionBanner";
import { Icon } from "./Icon";
import { StatusBadge } from "./StatusBadge";

function EvidenceCard({
  title,
  meta,
  dimension,
  children,
  footnote,
}: {
  title: string;
  meta: StatusMeta;
  dimension: string;
  children: ReactNode;
  footnote?: string;
}) {
  const headingId = `evidence-${dimension}`;
  return (
    <article
      className="evidence"
      data-dimension={dimension}
      data-tone={meta.tone}
      data-evidence={meta.evidence}
      aria-labelledby={headingId}
    >
      <span className="evidence__tile" aria-hidden="true">
        <Icon name={meta.icon} />
      </span>
      <div className="evidence__main">
        <header className="evidence__head">
          <h4 id={headingId} className="evidence__title">
            {title}
          </h4>
          <StatusBadge meta={meta} />
        </header>
        <div className="evidence__body">{children}</div>
        {footnote ? <p className="evidence__foot">{footnote}</p> : null}
      </div>
    </article>
  );
}

function SyntaxCard({ syntax, hasProposal }: { syntax: SyntaxCheck; hasProposal: boolean }) {
  const meta = SYNTAX_META[syntax.status];
  return (
    <EvidenceCard title="Syntax" meta={meta} dimension="syntax">
      {syntax.status === "pass" ? <p>The proposal parses as Python.</p> : null}
      {syntax.status === "fail" ? (
        <p>
          The proposal does not parse as Python{syntax.error ? ":" : "."}{" "}
          {syntax.error ? <code className="code-inline">{syntax.error}</code> : null}
        </p>
      ) : null}
      {syntax.status === "not_run" ? (
        <p>{hasProposal ? "The syntax check did not run." : "Not checked: there was no proposal to check."}</p>
      ) : null}
    </EvidenceCard>
  );
}

function RubricCard({ rubric }: { rubric: RubricCheck }) {
  const meta = RUBRIC_META[rubric.status];
  const checks = Object.entries(rubric.checks);
  return (
    <EvidenceCard
      title="Task rubric"
      meta={meta}
      dimension="rubric"
      footnote="Structural checks only. Passing them does not show that the behavior is unchanged."
    >
      {checks.length > 0 ? (
        <p className="evidence__figure">
          <strong>
            {checks.filter(([, passed]) => passed).length} of {plural(checks.length, "check")} passed
          </strong>
        </p>
      ) : null}
      {checks.length > 0 ? (
        <ul className="checklist">
          {checks.map(([name, passed]) => (
            <li key={name} className="checklist__item" data-passed={passed ? "true" : "false"}>
              <Icon name={passed ? "check" : "cross"} />
              <span>
                {rubricCheckLabel(name)}
                <span className="visually-hidden">: {passed ? "passed" : "failed"}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p>{rubric.status === "not_run" ? "No rubric checks were run." : "No individual checks were reported."}</p>
      )}
      <ReasonList reasons={rubric.reasons} className="reasons reasons--compact" />
    </EvidenceCard>
  );
}

function ReferenceTestsCard({ tests }: { tests: ReferenceTestsResult }) {
  const meta = REFERENCE_TESTS_META[tests.status];
  const counts: string[] = [];
  if (tests.failed) counts.push(`${tests.failed} failed`);
  if (tests.errored) counts.push(`${tests.errored} errored`);
  let summary: ReactNode = null;
  if (tests.total !== null && tests.passed !== null) {
    summary = (
      <p className="evidence__figure">
        <strong>
          {tests.passed} of {plural(tests.total, "test")} passed
        </strong>
        {counts.length > 0 ? <span>, {counts.join(", ")}</span> : null}
        {tests.duration_s !== null ? <span className="muted"> in {formatDuration(tests.duration_s)}</span> : null}
      </p>
    );
  }
  let fallback: string | null = null;
  if (!tests.reason) {
    if (tests.status === "not_available") {
      fallback =
        "No trusted reference tests exist for this input. They run only for demonstration cases submitted unchanged.";
    } else if (tests.status === "not_run") {
      fallback = "The trusted test runner did not run for this proposal.";
    } else if (tests.status === "error") {
      fallback = "The test runner reported an error, so behavior was not checked.";
    }
  }
  return (
    <EvidenceCard
      title="Reference tests"
      meta={meta}
      dimension="reference-tests"
      footnote={
        tests.status === "pass"
          ? "Passed for these trusted inputs only. This is not proof of identical behavior for every input."
          : undefined
      }
    >
      {summary}
      {tests.case_id ? (
        <p>
          Case <code className="code-inline">{tests.case_id}</code>
        </p>
      ) : null}
      {tests.reason ? <p>{tests.reason}</p> : null}
      {fallback ? <p>{fallback}</p> : null}
      {tests.failures.length > 0 ? (
        <table className="mini-table">
          <caption className="visually-hidden">Failed reference tests</caption>
          <thead>
            <tr>
              <th scope="col">Test index</th>
              <th scope="col">Problem</th>
              <th scope="col">Detail</th>
            </tr>
          </thead>
          <tbody>
            {tests.failures.map((failure, index) => (
              <tr key={`${failure.index}-${index}`}>
                <td className="mono">{failure.index}</td>
                <td>{FAILURE_KIND_LABELS[failure.kind] ?? failure.kind}</td>
                <td>{failure.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </EvidenceCard>
  );
}

function ModelReviewCard({
  review,
  detail,
  mode,
  fake,
}: {
  review: ModelReviewResult;
  detail: ReviewResult | null;
  mode: WorkflowMode;
  fake: boolean;
}) {
  const base = MODEL_REVIEW_META[review.status];
  // A fake provider's verdict is a fixed placeholder: no model judged the code, so it is
  // drawn as missing evidence (no check mark, no pass color).
  const meta: StatusMeta =
    fake && review.status !== "not_run"
      ? { ...base, label: `${base.label} (placeholder)`, tone: "neutral", icon: "absent", evidence: "absent" }
      : base;
  return (
    <EvidenceCard
      title="Model review"
      meta={meta}
      dimension="model-review"
      footnote="A model verdict is not proof of correctness and never overrides a failed check."
    >
      {fake && review.status !== "not_run" ? (
        <p>The fake test provider returned this verdict. No language model reviewed the proposal.</p>
      ) : null}
      {review.status === "not_run" ? (
        <p>
          {mode === "single_role"
            ? "Single-role runs have no review step."
            : "The review did not run, for example because there was no proposal."}
        </p>
      ) : null}
      {review.error ? (
        <p>
          Review error: <span className="mono">{review.error}</span>
        </p>
      ) : null}
      <ReasonList reasons={review.reasons} className="reasons reasons--compact" />
      {detail?.suggested_correction ? (
        <p>
          <span className="muted">Suggested correction:</span> {detail.suggested_correction}
        </p>
      ) : null}
    </EvidenceCard>
  );
}

export function VerificationPanel({
  verification,
  review,
  mode,
  fake,
  hasProposal,
}: {
  verification: VerificationResult;
  review: ReviewResult | null;
  mode: WorkflowMode;
  fake: boolean;
  hasProposal: boolean;
}) {
  return (
    <section className="result-section" aria-labelledby="verification-heading">
      <div className="section-head">
        <h3 id="verification-heading">Verification</h3>
        <p className="section-head__note">
          Each check is reported on its own. A check that did not run is shown as not run or not available, never as
          passed.
        </p>
      </div>
      <div className="evidence-grid">
        <SyntaxCard syntax={verification.syntax} hasProposal={hasProposal} />
        <RubricCard rubric={verification.rubric} />
        <ReferenceTestsCard tests={verification.reference_tests} />
        <ModelReviewCard review={verification.model_review} detail={review} mode={mode} fake={fake} />
      </div>
      <p className="equivalence-note" role="note">
        <Icon name="info" />
        <span>
          Passing reference tests shows that the proposal gave the expected results for the trusted test inputs only.
          It does not prove that the proposal behaves like the original for every possible input.
        </span>
      </p>
    </section>
  );
}
