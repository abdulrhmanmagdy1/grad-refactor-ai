import { useId } from "react";
import type { RunRecord } from "../api/contracts";
import { isFakeText } from "../lib/labels";

function lineRange(start: number, end: number): string {
  return start === end ? `Line ${start}` : `Lines ${start}–${end}`;
}

/** The explanation of the proposal and the findings the analysis reported. */
export function AnalysisSection({ record }: { record: RunRecord }) {
  const ids = useId();
  const fakeExplanation = record.provider_mode === "fake" || isFakeText(record.explanation);
  const source = record.analysis?.source ?? null;
  const findingsNote =
    source === "static"
      ? "Found by the deterministic task check, without a model call."
      : source === "model"
        ? record.provider_mode === "fake"
          ? "Reported by the analysis role (fake provider)."
          : "Reported by the analysis role."
        : record.workflow_mode === "single_role"
          ? "Single-role runs have no analysis step."
          : "No analysis was recorded.";

  return (
    <div className="analysis-grid">
      <section className="result-section" aria-labelledby={`${ids}-explanation`}>
        <div className="section-head">
          <h3 id={`${ids}-explanation`}>
            Explanation
            {fakeExplanation && record.explanation ? <span className="tag tag--fake">Fake provider</span> : null}
          </h3>
        </div>
        {record.explanation ? (
          <p className="prose">{record.explanation}</p>
        ) : (
          <p className="muted">No explanation was recorded for this run.</p>
        )}
      </section>

      <section className="result-section" aria-labelledby={`${ids}-findings`}>
        <div className="section-head">
          <h3 id={`${ids}-findings`}>Findings</h3>
          <p className="section-head__note">{findingsNote}</p>
        </div>
        {record.findings.length > 0 ? (
          <ul className="findings">
            {record.findings.map((finding, index) => (
              <li key={index} className="finding">
                <p className="finding__where">
                  <span className="finding__lines">{lineRange(finding.start_line, finding.end_line)}</span>
                  <code className="code-tag">{finding.type}</code>
                </p>
                <p className="finding__reason">{finding.reason}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No findings were reported.</p>
        )}
        {record.analysis?.unsupported_reason ? (
          <p className="notice" data-tone="neutral">
            Outside the supported task: {record.analysis.unsupported_reason}
          </p>
        ) : null}
      </section>
    </div>
  );
}
