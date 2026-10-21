import { type ReactNode, useId, useMemo, useState } from "react";
import type { RoleFinding } from "../api/contracts";
import {
  DiffParseError,
  type ParsedDiff,
  type SplitCell,
  buildSplitRows,
  parseUnifiedDiff,
  splitSourceLines,
} from "../lib/diff";
import { plural } from "../lib/format";
import { type HighlightedLine, highlightPython } from "../lib/highlight";
import { CodeText, tokensFor } from "./CodeText";

export type DiffLayout = "unified" | "split";

interface DiffViewerProps {
  original: string;
  proposed: string;
  diff: string | null;
  findings: RoleFinding[];
  actions?: ReactNode;
}

type ParseOutcome = { parsed: ParsedDiff; error: null } | { parsed: null; error: string };

function parse(diff: string | null): ParseOutcome {
  try {
    return { parsed: parseUnifiedDiff(diff), error: null };
  } catch (error) {
    const message = error instanceof DiffParseError ? `${error.message} (diff line ${error.lineNumber})` : String(error);
    return { parsed: null, error: message };
  }
}

/** Syntax tokens for every line of a source text, numbered like splitSourceLines(). */
function useHighlighted(text: string): HighlightedLine[] {
  return useMemo(() => highlightPython(splitSourceLines(text).join("\n")), [text]);
}

const SIGN: Record<string, string> = { add: "+", remove: "-", context: " " };
const KIND_TEXT: Record<string, string> = { add: "Added", remove: "Removed", context: "Unchanged" };

function inFindings(line: number | null, findings: RoleFinding[]): boolean {
  return line !== null && findings.some((finding) => line >= finding.start_line && line <= finding.end_line);
}

function UnifiedView({
  parsed,
  label,
  oldLines,
  newLines,
}: {
  parsed: ParsedDiff;
  label: string;
  oldLines: HighlightedLine[];
  newLines: HighlightedLine[];
}) {
  return (
    <div className="code-scroll" role="region" aria-label={label} tabIndex={0}>
      <table className="diff-table">
        <caption className="visually-hidden">{label}</caption>
        <thead className="visually-hidden">
          <tr>
            <th scope="col">Original line</th>
            <th scope="col">Proposed line</th>
            <th scope="col">Change</th>
            <th scope="col">Code</th>
          </tr>
        </thead>
        {parsed.hunks.map((hunk, hunkIndex) => (
          <tbody key={hunkIndex}>
            <tr className="diff-hunk">
              <td colSpan={4}>
                <span className="mono">{hunk.header}</span>
              </td>
            </tr>
            {hunk.lines.map((line, lineIndex) => (
              <tr key={lineIndex} className="diff-row" data-kind={line.kind}>
                <td className="diff-num">{line.oldNumber ?? ""}</td>
                <td className="diff-num">{line.newNumber ?? ""}</td>
                <td className="diff-sign">
                  <span aria-hidden="true">{SIGN[line.kind]}</span>
                  <span className="visually-hidden">{KIND_TEXT[line.kind]}</span>
                </td>
                <td className="diff-code">
                  <span className="diff-text">
                    <CodeText
                      tokens={
                        line.kind === "remove"
                          ? tokensFor(oldLines, line.oldNumber, line.text)
                          : tokensFor(newLines, line.newNumber, line.text)
                      }
                    />
                  </span>
                  {line.noNewlineAtEnd ? <span className="diff-eof">No newline at end of file</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        ))}
      </table>
    </div>
  );
}

function SplitCellView({ cell, flagged, lines }: { cell: SplitCell; flagged: boolean; lines: HighlightedLine[] }) {
  const kindText = cell.kind === "remove" ? "Removed" : cell.kind === "add" ? "Added" : null;
  return (
    <>
      <td className="diff-num" data-kind={cell.kind}>
        {cell.number ?? ""}
      </td>
      <td className="diff-code" data-kind={cell.kind} data-flagged={flagged ? "true" : undefined}>
        {kindText ? <span className="visually-hidden">{kindText}: </span> : null}
        {cell.kind === "empty" ? <span className="visually-hidden">No line</span> : null}
        <span className="diff-text">
          {cell.kind === "empty" ? null : <CodeText tokens={tokensFor(lines, cell.number, cell.text)} />}
        </span>
      </td>
    </>
  );
}

function SplitView({
  original,
  proposed,
  parsed,
  findings,
  oldLines,
  newLines,
}: {
  original: string;
  proposed: string;
  parsed: ParsedDiff | null;
  findings: RoleFinding[];
  oldLines: HighlightedLine[];
  newLines: HighlightedLine[];
}) {
  const rows = useMemo(
    () => (parsed ? buildSplitRows(original, proposed, parsed) : null),
    [original, proposed, parsed],
  );
  const flagged = findings.length > 0;
  if (rows === null) {
    return (
      <div className="split-fallback-wrap">
        <p className="diff-note">
          The two versions could not be aligned line by line with the service's diff, so both are shown in full.
        </p>
        <div className="split-fallback">
          <CodeListing title="Original" code={original} findings={findings} />
          <CodeListing title="Proposed" code={proposed} findings={[]} />
        </div>
      </div>
    );
  }
  return (
    <>
      <div className="code-scroll" role="region" aria-label="Original and proposed code side by side" tabIndex={0}>
        <table className="diff-table diff-table--split">
          <caption className="visually-hidden">Original and proposed code side by side</caption>
          <colgroup>
            <col className="diff-col-num" />
            <col />
            <col className="diff-col-num" />
            <col />
          </colgroup>
          <thead>
            <tr>
              <th scope="colgroup" colSpan={2}>
                Original
              </th>
              <th scope="colgroup" colSpan={2}>
                Proposed
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="diff-row">
                <SplitCellView cell={row.left} flagged={inFindings(row.left.number, findings)} lines={oldLines} />
                <SplitCellView cell={row.right} flagged={false} lines={newLines} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {flagged ? (
        <p className="diff-note">
          <span className="flag-swatch" aria-hidden="true" /> A bar beside an original line marks lines that the
          analysis flagged.
        </p>
      ) : null}
    </>
  );
}

export function CodeListing({ title, code, findings }: { title: string; code: string; findings: RoleFinding[] }) {
  const lines = splitSourceLines(code);
  const highlighted = useHighlighted(code);
  return (
    <div className="code-scroll code-scroll--listing" role="region" aria-label={title} tabIndex={0}>
      <table className="diff-table">
        <caption className="listing-caption">{title}</caption>
        <tbody>
          {lines.map((text, index) => (
            <tr key={index} className="diff-row" data-kind="context">
              <td className="diff-num">{index + 1}</td>
              <td className="diff-code" data-flagged={inFindings(index + 1, findings) ? "true" : undefined}>
                <span className="diff-text">
                  <CodeText tokens={tokensFor(highlighted, index + 1, text)} />
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DiffViewer({ original, proposed, diff, findings, actions }: DiffViewerProps) {
  const ids = useId();
  const [layout, setLayout] = useState<DiffLayout>("unified");
  const outcome = useMemo(() => parse(diff), [diff]);
  const oldLines = useHighlighted(original);
  const newLines = useHighlighted(proposed);
  const parsed = outcome.parsed;
  const empty = parsed !== null && parsed.hunks.length === 0;

  return (
    <section className="result-section diff-section" aria-labelledby={`${ids}-heading`}>
      <div className="section-head section-head--row">
        <h3 id={`${ids}-heading`}>Proposed change</h3>
        <div className="section-head__actions">{actions}</div>
      </div>

      <div className="code-frame">
        <div className="code-frame__bar">
          <fieldset className="segmented">
            <legend className="visually-hidden">Diff layout</legend>
            {(["unified", "split"] as const).map((value) => (
              <label key={value} className="segmented__option">
                <input
                  type="radio"
                  name={`${ids}-layout`}
                  value={value}
                  checked={layout === value}
                  onChange={() => setLayout(value)}
                />
                <span>{value === "unified" ? "Unified" : "Side by side"}</span>
              </label>
            ))}
          </fieldset>
          {parsed && !empty ? (
            <p className="diff-stats">
              <span className="diff-stats__add" aria-hidden="true">
                +{parsed.additions}
              </span>
              <span className="diff-stats__del" aria-hidden="true">
                −{parsed.deletions}
              </span>
              <span className="visually-hidden">
                {plural(parsed.additions, "line")} added, {plural(parsed.deletions, "line")} removed
              </span>
            </p>
          ) : null}
        </div>

        {layout === "unified" ? (
          outcome.error !== null ? (
            <div className="code-frame__fallback">
              <p className="diff-note" data-tone="warn">
                The diff from the service could not be read ({outcome.error}). It is shown as plain text.
              </p>
              <pre className="raw-diff" tabIndex={0}>
                {diff}
              </pre>
            </div>
          ) : empty ? (
            <p className="diff-note diff-note--empty">
              The service reported no differences between the original and the proposal.
            </p>
          ) : (
            <UnifiedView
              parsed={outcome.parsed}
              label="Unified diff of the original and proposed code"
              oldLines={oldLines}
              newLines={newLines}
            />
          )
        ) : (
          <SplitView
            original={original}
            proposed={proposed}
            parsed={parsed}
            findings={findings}
            oldLines={oldLines}
            newLines={newLines}
          />
        )}
      </div>
    </section>
  );
}
