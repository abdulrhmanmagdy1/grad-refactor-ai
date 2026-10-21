import type { RunStatus, WorkflowMode } from "../api/contracts";
import { type ActiveRunStatus, stepForStage } from "../lib/labels";
import { Icon } from "./Icon";

type ActiveStatus = ActiveRunStatus;
export type StepState = "done" | "current" | "pending" | "failed";

export interface Step {
  key: ActiveStatus | "result";
  label: string;
  state: StepState;
}

const MULTI_ROLE_STEPS: ActiveStatus[] = ["queued", "analyzing", "generating", "verifying"];
const SINGLE_ROLE_STEPS: ActiveStatus[] = ["queued", "generating", "verifying"];

function hasCorrection(trail: RunStatus[]): boolean {
  const verifying = trail.indexOf("verifying");
  return verifying !== -1 && trail.indexOf("generating", verifying + 1) !== -1;
}

function lastActiveStatus(trail: RunStatus[]): ActiveStatus | null {
  for (let index = trail.length - 1; index >= 0; index -= 1) {
    const status = trail[index];
    if (status === "queued" || status === "analyzing" || status === "generating" || status === "verifying") {
      return status;
    }
  }
  return null;
}

/** Step states for the run progress; single-role runs have no analysis step. */
export function buildSteps(
  mode: WorkflowMode,
  status: RunStatus | null,
  trail: RunStatus[],
  errorStage: string | null,
): Step[] {
  const keys = mode === "single_role" ? SINGLE_ROLE_STEPS : MULTI_ROLE_STEPS;
  const correcting = status === "generating" && hasCorrection(trail);
  const labels: Record<ActiveStatus, string> = {
    queued: "Queued",
    analyzing: "Find",
    generating: correcting ? "Rewrite (retry)" : "Rewrite",
    verifying: mode === "single_role" ? "Check" : "Check and review",
  };

  let states: StepState[];
  let result: Step;
  if (status === "completed") {
    states = keys.map(() => "done");
    result = { key: "result", label: "Done", state: "done" };
  } else if (status === "failed") {
    const failedAt = stepForStage(errorStage) ?? lastActiveStatus(trail);
    const index = failedAt ? keys.indexOf(failedAt) : -1;
    states = keys.map((_, i) => (index === -1 ? "pending" : i < index ? "done" : i === index ? "failed" : "pending"));
    result = { key: "result", label: "Failed", state: "failed" };
  } else {
    const index = status ? keys.indexOf(status) : 0;
    const current = index === -1 ? 0 : index;
    states = keys.map((_, i) => (i < current ? "done" : i === current ? "current" : "pending"));
    result = { key: "result", label: "Result", state: "pending" };
  }
  return [...keys.map((key, i) => ({ key, label: labels[key], state: states[i] ?? "pending" })), result];
}

const STATE_TEXT: Record<StepState, string> = {
  done: "done",
  current: "in progress",
  pending: "not started",
  failed: "failed here",
};

export function ProgressStepper({
  mode,
  status,
  trail,
  errorStage,
}: {
  mode: WorkflowMode;
  status: RunStatus | null;
  trail: RunStatus[];
  errorStage: string | null;
}) {
  const steps = buildSteps(mode, status, trail, errorStage);
  return (
    <ol className="stepper" aria-label="Run progress">
      {steps.map((step, index) => (
        <li
          key={step.key}
          className="stepper__step"
          data-state={step.state}
          data-step={step.key}
          aria-current={step.state === "current" ? "step" : undefined}
        >
          <span className="stepper__marker" aria-hidden="true">
            {step.state === "done" ? (
              <Icon name="check" />
            ) : step.state === "failed" ? (
              <Icon name="cross" />
            ) : step.state === "current" ? (
              <Icon name="spinner" className="spin" />
            ) : (
              <span className="stepper__number">{index + 1}</span>
            )}
          </span>
          <span className="stepper__label">
            {step.label}
            <span className="visually-hidden">, {STATE_TEXT[step.state]}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}
