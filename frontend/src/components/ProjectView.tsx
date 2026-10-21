import { type ChangeEvent, type DragEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type ApiError, toApiError } from "../api/client";
import type { HumanDecision } from "../api/contracts";
import {
  CATEGORIES,
  type Category,
  type Finding,
  type Fix,
  type FixCheck,
  PROJECT_TERMINAL,
  type ProjectInfo,
  type ProjectRecord,
  type ProjectSummary,
  type Severity,
  decideFix,
  deleteProject,
  fetchFixedProject,
  fetchPatch,
  getProject,
  getProjectInfo,
  listProjects,
  uploadProject,
} from "../api/projects";
import { useResource } from "../hooks/useResource";
import { saveBlob } from "../lib/browser";
import { formatDateTime, formatDuration, plural, shortId } from "../lib/format";
import { DISPOSITION_META, type Tone } from "../lib/labels";
import { DiffViewer } from "./DiffViewer";
import { Icon, type AnyIconName } from "./Icon";

const POLL_MS = 1500;
const HISTORY_LIMIT = 20;

export const CATEGORY_LABEL: Record<Category, string> = {
  bug: "Bugs",
  security: "Security",
  architecture: "Architecture",
  quality: "Code quality",
  refactoring: "Refactoring",
};

const SEVERITY_META: Record<Severity, { label: string; tone: Tone }> = {
  high: { label: "High", tone: "fail" },
  medium: { label: "Medium", tone: "warn" },
  low: { label: "Low", tone: "neutral" },
};

const STAGES: { status: string; label: string }[] = [
  { status: "indexing", label: "Read" },
  { status: "scanning", label: "Check" },
  { status: "reviewing", label: "AI agents" },
  { status: "fixing", label: "Fixes" },
];

/** Where a finding came from, in a few words. */
export function sourceLabel(finding: Finding): string {
  const [kind, tool, rule] = finding.source.split(":");
  if (kind === "static" && tool === "ruff") return `ruff ${rule}`;
  if (kind === "static" && tool === "task") return "guard-clause check";
  if (kind === "static") return "static check";
  const checked = finding.also_reported_by.some((s) => s.endsWith("checker"));
  return checked ? "AI agent, double-checked" : "AI agent";
}

interface CheckMeta {
  label: string;
  tone: Tone;
  icon: AnyIconName;
  absent: boolean;
}

/** One fix check as a chip: only pass and accept look like success. */
export function checkMeta(kind: "syntax" | "static" | "tests" | "review", check: FixCheck): CheckMeta {
  const status = check.status;
  if (status === "pass" || status === "accept") return { label: "Passed", tone: "pass", icon: "check", absent: false };
  if (status === "partial") return { label: "Partly", tone: "warn", icon: "alert", absent: false };
  if (status === "fail" || status === "reject") return { label: kind === "review" ? "Rejected" : "Failed", tone: "fail", icon: "cross", absent: false };
  if (status === "uncertain") return { label: "Not sure", tone: "warn", icon: "question", absent: false };
  if (status === "error") return { label: "Could not check", tone: "warn", icon: "alert", absent: true };
  if (status === "not_available") return { label: "No related test", tone: "neutral", icon: "absent", absent: true };
  return { label: kind === "tests" ? "Off" : "Not checked", tone: "neutral", icon: "dash", absent: true };
}

function Chip({ name, check, kind }: { name: string; check: FixCheck; kind: Parameters<typeof checkMeta>[0] }) {
  const meta = checkMeta(kind, check);
  return (
    <li
      className="check-chip"
      data-tone={meta.tone}
      data-evidence={meta.absent ? "absent" : "present"}
      title={check.detail ?? undefined}
    >
      <Icon name={meta.icon} />
      <span className="check-chip__name">{name}</span>
      <span className="check-chip__value">{meta.label}</span>
    </li>
  );
}

function SeverityTag({ severity }: { severity: Severity }) {
  const meta = SEVERITY_META[severity];
  return (
    <span className="severity" data-tone={meta.tone}>
      {meta.label}
    </span>
  );
}

function place(finding: Finding): string {
  if (!finding.file) return "Whole project";
  return finding.line_start ? `${finding.file}:${finding.line_start}` : finding.file;
}

function FindingCard({ finding, fix, onShowFix }: { finding: Finding; fix: Fix | null; onShowFix: (fixId: string) => void }) {
  const explanation = finding.explanation !== finding.title ? finding.explanation : null;
  return (
    <li className="finding" data-category={finding.category}>
      <div className="finding__head">
        <SeverityTag severity={finding.severity} />
        <h4 className="finding__title">{finding.title}</h4>
      </div>
      <p className="finding__meta">
        <span className="mono">{place(finding)}</span>
        {finding.symbol ? <span> · {finding.symbol}</span> : null}
        <span className="finding__source"> · {sourceLabel(finding)}</span>
      </p>
      {explanation ? <p className="finding__text">{explanation}</p> : null}
      {finding.recommendation ? (
        <p className="finding__fix">
          <strong>How to fix:</strong> {finding.recommendation}
        </p>
      ) : null}
      {fix ? (
        <button type="button" className="link-button" onClick={() => onShowFix(fix.id)}>
          See the proposed fix ({DISPOSITION_META[fix.disposition].label})
        </button>
      ) : null}
    </li>
  );
}

function FixCard({
  fix,
  findings,
  decision,
  onDecide,
  highlighted,
}: {
  fix: Fix;
  findings: Finding[];
  decision: { pending: HumanDecision | null; error: ApiError | null };
  onDecide: (fixId: string, decision: HumanDecision) => void;
  highlighted: boolean;
}) {
  const meta = DISPOSITION_META[fix.disposition];
  const fixed = findings.filter((f) => fix.finding_ids.includes(f.id));
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (highlighted) ref.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [highlighted]);
  return (
    <article className="fix-card" ref={ref} data-highlighted={highlighted ? "true" : undefined} aria-label={`Fix for ${fix.symbol}`}>
      <div className="fix-card__head">
        <div>
          <h4 className="fix-card__title">
            <span className="mono">{fix.symbol}</span>
          </h4>
          <p className="muted mono">{fix.file}</p>
        </div>
        <span className="verdict" data-tone={meta.tone}>
          <Icon name={meta.icon} />
          {meta.title}
        </span>
      </div>
      {fixed.length > 0 ? (
        <ul className="fix-card__problems">
          {fixed.map((finding) => (
            <li key={finding.id}>
              <SeverityTag severity={finding.severity} /> {finding.title}
            </li>
          ))}
        </ul>
      ) : null}
      <ul className="check-row" aria-label="Checks">
        <Chip name="Valid Python" check={fix.syntax} kind="syntax" />
        <Chip name="Static check" check={fix.static_recheck} kind="static" />
        <Chip name="Tests" check={fix.tests} kind="tests" />
        <Chip name="Review" check={fix.review} kind="review" />
      </ul>
      {fix.diff && fix.proposed ? (
        <DiffViewer original={fix.original} proposed={fix.proposed} diff={fix.diff} findings={[]} />
      ) : (
        <p className="notice" data-tone="neutral">
          No change could be proposed.
        </p>
      )}
      {fix.disposition !== "proposal_ready" && fix.disposition_reasons.length > 0 ? (
        <details className="fix-card__why">
          <summary>Why not ready</summary>
          <ul>
            {fix.disposition_reasons.map((reason) => (
              <li key={reason}>{reason.replace(/^[a-z_]+: /, "")}</li>
            ))}
          </ul>
        </details>
      ) : null}
      {fix.diff ? (
        <div className="fix-card__decision">
          <button
            type="button"
            className="button button--small"
            data-selected={fix.decision === "accepted" ? "true" : undefined}
            disabled={decision.pending !== null}
            onClick={() => onDecide(fix.id, "accepted")}
          >
            <Icon name="check" /> Accept
          </button>
          <button
            type="button"
            className="button button--small button--quiet"
            data-selected={fix.decision === "rejected" ? "true" : undefined}
            disabled={decision.pending !== null}
            onClick={() => onDecide(fix.id, "rejected")}
          >
            <Icon name="cross" /> Reject
          </button>
          <span className="muted" role="status">
            {fix.decision === "accepted" ? "Accepted" : fix.decision === "rejected" ? "Rejected" : ""}
          </span>
          {decision.error ? <span className="field-message">{decision.error.message}</span> : null}
        </div>
      ) : null}
    </article>
  );
}

function Progress({ record }: { record: ProjectRecord }) {
  const current = STAGES.findIndex((stage) => stage.status === record.status);
  return (
    <div className="project-progress" aria-live="polite">
      <ol className="project-stages">
        {STAGES.map((stage, index) => (
          <li
            key={stage.status}
            data-state={record.status === "queued" ? "pending" : index < current ? "done" : index === current ? "active" : "pending"}
          >
            <span className="project-stages__dot" aria-hidden="true" />
            {stage.label}
          </li>
        ))}
      </ol>
      <p className="project-progress__text">
        <Icon name="spinner" className="spin" /> {record.progress ?? "Working"}
      </p>
    </div>
  );
}

function Summary({ record }: { record: ProjectRecord }) {
  const s = record.summary as Record<string, number | Record<string, number> | boolean | null>;
  const bySeverity = (s.by_severity as Record<string, number> | undefined) ?? {};
  const fixes = (s.fix_dispositions as Record<string, number> | undefined) ?? {};
  const cards: { value: string; label: string; tone?: Tone }[] = [
    { value: String(s.python_files ?? 0), label: "Python files" },
    { value: String(s.code_lines ?? 0), label: "Lines of code" },
    { value: String(record.findings.length), label: "Problems found", tone: (bySeverity.high ?? 0) > 0 ? "fail" : undefined },
    { value: String(bySeverity.high ?? 0), label: "High severity", tone: (bySeverity.high ?? 0) > 0 ? "fail" : undefined },
    { value: String(fixes.proposal_ready ?? 0), label: "Fixes ready", tone: (fixes.proposal_ready ?? 0) > 0 ? "pass" : undefined },
  ];
  return (
    <ul className="summary-cards">
      {cards.map((card) => (
        <li key={card.label} className="summary-card" data-tone={card.tone}>
          <span className="summary-card__value">{card.value}</span>
          <span className="summary-card__label">{card.label}</span>
        </li>
      ))}
    </ul>
  );
}

function Architecture({ record }: { record: ProjectRecord }) {
  const arch = record.architecture as {
    cycles?: string[][];
    most_imported?: [string, number][];
    most_dependent?: [string, number][];
    agent_summary?: string | null;
  };
  const findings = record.findings.filter((f) => f.category === "architecture");
  return (
    <div className="architecture">
      {arch.agent_summary ? (
        <p className="architecture__summary">
          <strong>AI summary:</strong> {arch.agent_summary}
        </p>
      ) : null}
      <div className="architecture__grid">
        <section>
          <h4>Import cycles</h4>
          {arch.cycles && arch.cycles.length > 0 ? (
            <ul>
              {arch.cycles.map((cycle) => (
                <li key={cycle.join()} className="mono">
                  {[...cycle, cycle[0]].join(" → ")}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">None</p>
          )}
        </section>
        <section>
          <h4>Most used modules</h4>
          <ul>
            {(arch.most_imported ?? []).filter(([, n]) => n > 0).map(([name, count]) => (
              <li key={name}>
                <span className="mono">{name}</span> <span className="muted">used by {count}</span>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h4>Most dependent modules</h4>
          <ul>
            {(arch.most_dependent ?? []).filter(([, n]) => n > 0).map(([name, count]) => (
              <li key={name}>
                <span className="mono">{name}</span> <span className="muted">uses {count}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
      {findings.length === 0 ? <p className="muted">No architecture problems found.</p> : null}
    </div>
  );
}

type Tab = "problems" | "fixes" | "architecture";

function Results({
  record,
  onRecord,
}: {
  record: ProjectRecord;
  onRecord: (record: ProjectRecord) => void;
}) {
  const [tab, setTab] = useState<Tab>("problems");
  const [category, setCategory] = useState<Category | "all">("all");
  const [highlight, setHighlight] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, { pending: HumanDecision | null; error: ApiError | null }>>({});
  const [download, setDownload] = useState<{ pending: boolean; error: ApiError | null }>({ pending: false, error: null });

  const fixFor = useMemo(() => {
    const map = new Map<string, Fix>();
    for (const fix of record.fixes) for (const id of fix.finding_ids) map.set(id, fix);
    return map;
  }, [record.fixes]);
  const counts = useMemo(() => {
    const result: Record<string, number> = {};
    for (const f of record.findings) result[f.category] = (result[f.category] ?? 0) + 1;
    return result;
  }, [record.findings]);
  const shown = record.findings.filter((f) => category === "all" || f.category === category);
  const accepted = record.fixes.filter((f) => f.decision === "accepted").length;

  const decide = async (fixId: string, decision: HumanDecision) => {
    setDecisions((d) => ({ ...d, [fixId]: { pending: decision, error: null } }));
    try {
      onRecord(await decideFix(record.project_id, fixId, decision));
      setDecisions((d) => ({ ...d, [fixId]: { pending: null, error: null } }));
    } catch (error) {
      setDecisions((d) => ({ ...d, [fixId]: { pending: null, error: toApiError(error) } }));
    }
  };

  const save = async (which: "patch" | "zip") => {
    setDownload({ pending: true, error: null });
    try {
      const file = which === "patch" ? await fetchPatch(record.project_id) : await fetchFixedProject(record.project_id);
      saveBlob(file.blob, file.filename);
      setDownload({ pending: false, error: null });
    } catch (error) {
      setDownload({ pending: false, error: toApiError(error) });
    }
  };

  return (
    <div className="project-results">
      <Summary record={record} />
      {record.warnings.length > 0 ? (
        <ul className="project-warnings">
          {record.warnings.map((warning) => (
            <li key={warning} className="notice" data-tone="warn">
              {warning}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="tabs" role="tablist" aria-label="Review results">
        {(
          [
            ["problems", `Problems (${record.findings.length})`],
            ["fixes", `Fixes (${record.fixes.length})`],
            ["architecture", "Architecture"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            className="tabs__tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "problems" ? (
        <div role="tabpanel" aria-label="Problems">
          <div className="filter-chips" role="group" aria-label="Filter by kind">
            <button type="button" className="filter-chip" aria-pressed={category === "all"} onClick={() => setCategory("all")}>
              All {record.findings.length}
            </button>
            {CATEGORIES.filter((c) => counts[c]).map((c) => (
              <button key={c} type="button" className="filter-chip" aria-pressed={category === c} onClick={() => setCategory(c)}>
                {CATEGORY_LABEL[c]} {counts[c]}
              </button>
            ))}
          </div>
          {shown.length === 0 ? (
            <p className="muted">No problems found.</p>
          ) : (
            <ul className="finding-list">
              {shown.map((finding) => (
                <FindingCard
                  key={finding.id}
                  finding={finding}
                  fix={fixFor.get(finding.id) ?? null}
                  onShowFix={(fixId) => {
                    setHighlight(fixId);
                    setTab("fixes");
                  }}
                />
              ))}
            </ul>
          )}
        </div>
      ) : null}

      {tab === "fixes" ? (
        <div role="tabpanel" aria-label="Fixes">
          <div className="fix-toolbar">
            <p className="muted">
              {record.fixes.length === 0
                ? "No fix was proposed."
                : `Accept the fixes you want, then download them. ${plural(accepted, "fix", "fixes")} accepted.`}
            </p>
            <div className="fix-toolbar__actions">
              <button type="button" className="button button--small" disabled={accepted === 0 || download.pending} onClick={() => void save("patch")}>
                <Icon name="download" /> Patch file
              </button>
              <button type="button" className="button button--small button--primary" disabled={accepted === 0 || download.pending} onClick={() => void save("zip")}>
                <Icon name="download" /> Fixed project (.zip)
              </button>
            </div>
          </div>
          {download.error ? <p className="field-message">{download.error.message}</p> : null}
          {record.fixes.map((fix) => (
            <FixCard
              key={fix.id}
              fix={fix}
              findings={record.findings}
              decision={decisions[fix.id] ?? { pending: null, error: null }}
              onDecide={(fixId, decision) => void decide(fixId, decision)}
              highlighted={highlight === fix.id}
            />
          ))}
          {record.fixes.length > 0 ? <p className="checks__note">Tests check examples, not every possible input.</p> : null}
        </div>
      ) : null}

      {tab === "architecture" ? (
        <div role="tabpanel" aria-label="Architecture">
          <Architecture record={record} />
          <ul className="finding-list">
            {record.findings
              .filter((f) => f.category === "architecture")
              .map((finding) => (
                <FindingCard key={finding.id} finding={finding} fix={null} onShowFix={() => undefined} />
              ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function History({
  items,
  selectedId,
  onOpen,
  onDelete,
  onRefresh,
}: {
  items: ProjectSummary[] | null;
  selectedId: string | null;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onRefresh: () => void;
}) {
  return (
    <section className="panel project-history" aria-labelledby="project-history-heading">
      <div className="panel__head">
        <h2 id="project-history-heading">Past reviews</h2>
        <button type="button" className="button button--small button--quiet" onClick={onRefresh}>
          <Icon name="refresh" /> Refresh
        </button>
      </div>
      {items === null ? (
        <p className="muted">Loading…</p>
      ) : items.length === 0 ? (
        <p className="muted">No reviews yet.</p>
      ) : (
        <ul className="project-history__list">
          {items.map((item) => (
            <li key={item.project_id} data-selected={item.project_id === selectedId ? "true" : undefined}>
              <div>
                <p className="project-history__name">{item.name}</p>
                <p className="muted">
                  {formatDateTime(item.created_at)} · {item.status === "completed" ? `${(item.summary.findings as number | undefined) ?? 0} problems` : item.status}
                </p>
              </div>
              <div className="project-history__actions">
                <button type="button" className="button button--small" onClick={() => onOpen(item.project_id)}>
                  Open
                </button>
                <button
                  type="button"
                  className="button button--small button--quiet"
                  aria-label={`Delete ${item.name}`}
                  onClick={() => onDelete(item.project_id)}
                >
                  <Icon name="trash" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** The whole-project review: upload a zip, follow the review, read problems, accept fixes. */
export function ProjectView() {
  const info = useResource<ProjectInfo>(getProjectInfo);
  const history = useResource<ProjectSummary[]>((signal) => listProjects(HISTORY_LIMIT, signal));
  const [file, setFile] = useState<File | null>(null);
  const [runTests, setRunTests] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<ApiError | null>(null);
  const [record, setRecord] = useState<ProjectRecord | null>(null);
  const [pollError, setPollError] = useState<ApiError | null>(null);
  const refreshHistory = history.refresh;

  const projectId = record?.project_id ?? null;
  const running = record !== null && !PROJECT_TERMINAL.includes(record.status);

  useEffect(() => {
    if (!projectId || !running) return undefined;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      getProject(projectId, controller.signal).then(
        (next) => {
          setPollError(null);
          setRecord(next);
          if (PROJECT_TERMINAL.includes(next.status)) refreshHistory();
        },
        (error: unknown) => {
          const apiError = toApiError(error);
          if (apiError.kind !== "aborted") setPollError(apiError);
          setRecord((current) => (current ? { ...current } : current)); // keep polling
        },
      );
    }, POLL_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [projectId, running, record, refreshHistory]);

  const choose = (chosen: File | null | undefined) => {
    setUploadError(null);
    if (!chosen) return;
    setFile(chosen);
  };

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files?.[0]);
  };

  const submit = async () => {
    if (!file || uploading) return;
    setUploading(true);
    setUploadError(null);
    try {
      const name = file.name.replace(/\.zip$/i, "") || "project";
      const accepted = await uploadProject(file, name, runTests && (info.data?.tests_allowed ?? false));
      setRecord(await getProject(accepted.project_id));
      refreshHistory();
    } catch (error) {
      setUploadError(toApiError(error));
    } finally {
      setUploading(false);
    }
  };

  const open = useCallback(async (id: string) => {
    try {
      setPollError(null);
      setRecord(await getProject(id));
    } catch (error) {
      setPollError(toApiError(error));
    }
  }, []);

  const remove = async (id: string) => {
    try {
      await deleteProject(id);
    } catch (error) {
      if (toApiError(error).code !== "project_not_found") return;
    }
    if (record?.project_id === id) setRecord(null);
    refreshHistory();
  };

  const tooLarge = file !== null && info.data !== null && file.size > info.data.max_zip_bytes;
  const testsAllowed = info.data?.tests_allowed ?? false;

  return (
    <div className="project-layout">
      <div className="project-layout__side">
        <section className="panel project-upload" aria-labelledby="project-upload-heading">
          <div className="panel__head">
            <h2 id="project-upload-heading">Review a project</h2>
          </div>
          <p className="muted">Upload a zip of a Python project. You get its bugs, security and design problems, and fixes to accept.</p>
          <label
            className="dropzone"
            data-dragging={dragging ? "true" : undefined}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <input
              type="file"
              accept=".zip,application/zip"
              className="visually-hidden"
              onChange={(event: ChangeEvent<HTMLInputElement>) => choose(event.target.files?.[0])}
            />
            <Icon name="download" />
            {file ? (
              <span>
                <strong>{file.name}</strong> <span className="muted">({Math.ceil(file.size / 1024)} KB)</span>
              </span>
            ) : (
              <span>
                <strong>Choose a .zip file</strong> or drop it here
              </span>
            )}
          </label>
          {tooLarge ? <p className="field-message">The file is larger than 5 MB.</p> : null}
          <label className="checkbox" data-disabled={testsAllowed ? undefined : "true"}>
            <input
              type="checkbox"
              checked={runTests && testsAllowed}
              disabled={!testsAllowed}
              onChange={(event) => setRunTests(event.target.checked)}
            />
            <span>
              Run my project's tests to check the fixes
              <span className="field__hint">
                {testsAllowed
                  ? "Only for your own projects: the tests run your code on this computer."
                  : "Turned off on this server (REFACTOR_AI_PROJECT_TESTS)."}
              </span>
            </span>
          </label>
          <p className="project-model">
            {info.data === null
              ? "Checking the model…"
              : info.data.uses_model
                ? `AI model: ${info.data.model_id ?? "local model"}`
                : "Static checks only (no AI model)"}
          </p>
          <button
            type="button"
            className="button button--primary project-upload__submit"
            disabled={!file || uploading || tooLarge || running}
            onClick={() => void submit()}
          >
            {uploading ? "Uploading…" : running ? "A review is running" : "Review project"}
          </button>
          {uploadError ? (
            <p className="notice" data-tone="fail" role="alert">
              {uploadError.message}
            </p>
          ) : null}
        </section>
        <History
          items={history.data}
          selectedId={projectId}
          onOpen={(id) => void open(id)}
          onDelete={(id) => void remove(id)}
          onRefresh={refreshHistory}
        />
      </div>

      <section className="panel project-main" aria-labelledby="project-main-heading">
        <div className="panel__head">
          <h2 id="project-main-heading">{record ? record.name : "Project review"}</h2>
          {record ? (
            <p className="panel__sub">
              {shortId(record.project_id)} · {formatDateTime(record.created_at)}
              {record.finished_at && record.started_at
                ? ` · ${formatDuration((Date.parse(record.finished_at) - Date.parse(record.started_at)) / 1000)}`
                : ""}
            </p>
          ) : null}
        </div>
        {pollError ? <p className="notice" data-tone="warn">{pollError.message}</p> : null}
        {record === null ? (
          <ol className="pipeline">
            <li>
              <span className="pipeline__num">1</span>
              <strong>Upload</strong> a zip of your project.
            </li>
            <li>
              <span className="pipeline__num">2</span>
              <strong>Check</strong>: static analysis and AI agents look for problems.
            </li>
            <li>
              <span className="pipeline__num">3</span>
              <strong>Fix</strong>: each proposed fix is checked before you accept it.
            </li>
          </ol>
        ) : record.status === "failed" ? (
          <p className="notice" data-tone="fail">
            {record.error?.message ?? "The review failed."}
          </p>
        ) : running ? (
          <Progress record={record} />
        ) : (
          <Results record={record} onRecord={setRecord} />
        )}
      </section>
    </div>
  );
}
