import { type ReactNode, useId } from "react";
import { type ModelReference, ROLES, type RunRecord } from "../api/contracts";
import { formatDateTime, formatDuration, formatTime, secondsBetween, shortHash } from "../lib/format";
import {
  DISPOSITION_META,
  PROVIDER_LABELS,
  ROLE_LABELS,
  STAGE_LABELS,
  TASK_LABEL,
  WORKFLOW_META,
  stopReasonLabel,
} from "../lib/labels";

function ModelText({ model }: { model: ModelReference | null }) {
  if (!model) return <>Not recorded (no model call was made)</>;
  return (
    <>
      <span className="mono">{model.model_id}</span> at revision{" "}
      <span className="mono" title={model.model_revision}>
        {shortHash(model.model_revision)}
      </span>
      <br />
      {model.adapter_id ? (
        <>
          Adapter <span className="mono">{model.adapter_id}</span>
          {model.adapter_sha256 ? (
            <>
              {" "}
              (sha256{" "}
              <span className="mono" title={model.adapter_sha256}>
                {shortHash(model.adapter_sha256)}
              </span>
              )
            </>
          ) : null}
          {model.use_adapter ? ", active for the refactoring call" : ", not active"}
        </>
      ) : (
        "Base model, no adapter"
      )}
    </>
  );
}

function Item({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="meta__item">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** Identity, configuration, timing and per-attempt evidence of a run (FR07). */
export function RunDetails({ record }: { record: RunRecord }) {
  const ids = useId();
  const queueWait = secondsBetween(record.created_at, record.started_at);
  const processing = secondsBetween(record.started_at, record.finished_at);
  const total = secondsBetween(record.created_at, record.finished_at);
  const settings = record.settings;
  return (
    <section className="result-section" aria-labelledby={`${ids}-heading`}>
      <div className="section-head">
        <h3 id={`${ids}-heading`}>Run record</h3>
      </div>
      <dl className="meta">
        <Item label="Run ID">
          <span className="mono break">{record.run_id}</span>
        </Item>
        <Item label="Workflow">{WORKFLOW_META[record.workflow_mode].label}</Item>
        <Item label="Task">
          {TASK_LABEL} <span className="mono muted">({record.task_type})</span>
        </Item>
        <Item label="Reference case">
          {record.reference_case_id ? <span className="mono">{record.reference_case_id}</span> : "None"}
        </Item>
        <Item label="Provider">{PROVIDER_LABELS[record.provider_mode]}</Item>
        <Item label="Model">
          <ModelText model={record.model} />
        </Item>
        <Item label="Refactoring weights">
          {settings.refactor_use_adapter ? "Fine-tuned LoRA adapter requested" : "Base model"}
          <span className="muted"> (analysis and review use the base model)</span>
        </Item>
        <Item label="Attempts">
          {record.attempt_count} (at most {settings.max_corrections + 1})
        </Item>
        <Item label="Model calls">
          {record.call_count} of at most {settings.max_calls}
        </Item>
        <Item label="Created">{formatDateTime(record.created_at)}</Item>
        <Item label="Started">{record.started_at ? formatDateTime(record.started_at) : "Not started"}</Item>
        <Item label="Finished">{record.finished_at ? formatDateTime(record.finished_at) : "Not finished"}</Item>
        <Item label="Duration">
          {total !== null ? formatDuration(total) : "Not finished"}
          {queueWait !== null && processing !== null ? (
            <span className="muted">
              {" "}
              ({formatDuration(queueWait)} queued, {formatDuration(processing)} processing)
            </span>
          ) : null}
        </Item>
        <Item label="Time limit">{formatDuration(settings.run_timeout_s)} per run</Item>
        <Item label="Stop reason">
          {record.stop_reason ? (
            <>
              {stopReasonLabel(record.stop_reason)} <span className="mono muted">({record.stop_reason})</span>
            </>
          ) : (
            "Not recorded"
          )}
        </Item>
        <Item label="Human decision">
          {record.human_decision === "accepted"
            ? "Accepted"
            : record.human_decision === "rejected"
              ? "Rejected"
              : "Not recorded"}
        </Item>
        <Item label="Schema version">{record.schema_version}</Item>
      </dl>

      <div className="code-scroll" role="region" aria-label="Generation limits" tabIndex={0}>
        <table className="mini-table">
          <caption>Generation limits per role</caption>
          <thead>
            <tr>
              <th scope="col">Role</th>
              <th scope="col">Max new tokens</th>
              <th scope="col">Max input tokens</th>
              <th scope="col">Time limit</th>
              <th scope="col">Temperature</th>
            </tr>
          </thead>
          <tbody>
            {ROLES.map((role) => {
              const config = settings.generation[role];
              return config ? (
                <tr key={role}>
                  <td>{ROLE_LABELS[role]}</td>
                  <td>{config.max_new_tokens}</td>
                  <td>{config.max_input_tokens}</td>
                  <td>{formatDuration(config.timeout_s)}</td>
                  <td>{config.temperature}</td>
                </tr>
              ) : null;
            })}
          </tbody>
        </table>
      </div>

      {record.stage_timings.length > 0 ? (
        <div className="code-scroll" role="region" aria-label="Stage timings" tabIndex={0}>
          <table className="mini-table">
            <caption>Stage timings</caption>
            <thead>
              <tr>
                <th scope="col">Stage</th>
                <th scope="col">Attempt</th>
                <th scope="col">Model calls</th>
                <th scope="col">Duration</th>
                <th scope="col">Started</th>
              </tr>
            </thead>
            <tbody>
              {record.stage_timings.map((timing, index) => (
                <tr key={index}>
                  <td>{STAGE_LABELS[timing.stage] ?? timing.stage}</td>
                  <td>{timing.attempt}</td>
                  <td>{timing.calls}</td>
                  <td>{formatDuration(timing.elapsed_s)}</td>
                  <td>{formatTime(timing.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {record.attempts.length > 0 ? (
        <div className="attempts">
          <div className="code-scroll" role="region" aria-label="Generation attempts" tabIndex={0}>
            <table className="mini-table">
              <caption>Generation attempts</caption>
              <thead>
                <tr>
                  <th scope="col">Attempt</th>
                  <th scope="col">Output</th>
                  <th scope="col">Outcome</th>
                  <th scope="col">Tokens in / out</th>
                  <th scope="col">Duration</th>
                </tr>
              </thead>
              <tbody>
                {record.attempts.map((attempt) => (
                  <tr key={attempt.attempt}>
                    <td>{attempt.attempt === 0 ? "0 (first)" : `${attempt.attempt} (correction)`}</td>
                    <td>
                      {attempt.parse_error
                        ? `Not parsed: ${attempt.parse_error}`
                        : attempt.proposed_code
                          ? attempt.parse_repaired
                            ? "Parsed after repair"
                            : "Parsed"
                          : "No code"}
                    </td>
                    <td>
                      {attempt.verification ? DISPOSITION_META[attempt.verification.disposition].label : "Not verified"}
                    </td>
                    <td>
                      {attempt.prompt_tokens ?? "n/a"} / {attempt.completion_tokens ?? "n/a"}
                    </td>
                    <td>{formatDuration(attempt.elapsed_s)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {record.attempts.map((attempt) =>
            attempt.raw_output ? (
              <details key={attempt.attempt} className="raw-output">
                <summary>Raw output of attempt {attempt.attempt}</summary>
                <pre tabIndex={0}>{attempt.raw_output}</pre>
              </details>
            ) : null,
          )}
        </div>
      ) : null}
    </section>
  );
}
