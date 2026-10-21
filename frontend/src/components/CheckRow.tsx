import type { VerificationResult, WorkflowMode } from "../api/contracts";
import {
  MODEL_REVIEW_META,
  REFERENCE_TESTS_META,
  RUBRIC_META,
  type StatusMeta,
  SYNTAX_META,
} from "../lib/labels";
import { Icon } from "./Icon";

const DEMO_ONLY: StatusMeta = { label: "Demo only", tone: "neutral", icon: "dash", evidence: "absent" };
const SKIPPED: StatusMeta = { label: "Skipped (Fast)", tone: "neutral", icon: "dash", evidence: "absent" };

function Chip({ name, meta, value }: { name: string; meta: StatusMeta; value?: string }) {
  return (
    <li className="check-chip" data-tone={meta.tone} data-evidence={meta.evidence}>
      <Icon name={meta.icon} />
      <span className="check-chip__name">{name}</span>
      <span className="check-chip__value">{value ?? meta.label}</span>
    </li>
  );
}

/** The four checks at a glance. Missing evidence is neutral grey, never a pass. */
export function CheckRow({
  verification,
  mode,
  fake,
}: {
  verification: VerificationResult;
  mode: WorkflowMode;
  fake: boolean;
}) {
  const tests = verification.reference_tests;
  const testsMeta = REFERENCE_TESTS_META[tests.status];
  const counted = (tests.status === "pass" || tests.status === "fail") && tests.total !== null;
  const review = verification.model_review.status;
  let reviewMeta = MODEL_REVIEW_META[review];
  if (fake && review !== "not_run") reviewMeta = DEMO_ONLY;
  else if (mode === "single_role" && review === "not_run") reviewMeta = SKIPPED;
  return (
    <div className="checks">
      <ul className="check-row" aria-label="Checks">
        <Chip name="Valid Python" meta={SYNTAX_META[verification.syntax.status]} />
        <Chip name="Guard clauses" meta={RUBRIC_META[verification.rubric.status]} />
        <Chip
          name="Tests"
          meta={testsMeta}
          value={counted ? `${tests.passed ?? 0}/${tests.total} passed` : undefined}
        />
        <Chip name="Review" meta={reviewMeta} />
      </ul>
      <p className="checks__note">Tests check examples, not every possible input.</p>
    </div>
  );
}
