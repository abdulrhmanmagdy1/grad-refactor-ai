import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  DISPOSITIONS,
  type Disposition,
  MODEL_REVIEW_STATUSES,
  type ModelReviewStatus,
  REFERENCE_TEST_STATUSES,
  type ReferenceTestsStatus,
  RUBRIC_STATUSES,
  SYNTAX_STATUSES,
} from "../api/contracts";
import { DIFF_TEXT, ORIGINAL_CODE, PROPOSED_CODE, runRecord, verification } from "../test/fixtures";
import { CheckRow } from "./CheckRow";
import { DiffViewer } from "./DiffViewer";
import { DispositionBanner } from "./DispositionBanner";
import { buildSteps } from "./ProgressStepper";
import { VerificationPanel } from "./VerificationPanel";

function card(dimension: string): HTMLElement {
  const element = document.querySelector<HTMLElement>(`[data-dimension="${dimension}"]`);
  if (!element) throw new Error(`No card for ${dimension}`);
  return element;
}

function badgeOf(dimension: string): HTMLElement {
  const badge = card(dimension).querySelector<HTMLElement>(".badge");
  if (!badge) throw new Error(`No badge in ${dimension}`);
  return badge;
}

function renderPanel(overrides: Parameters<typeof verification>[0] = {}, options: { fake?: boolean; mode?: "multi_role" | "single_role" } = {}) {
  return render(
    <VerificationPanel
      verification={verification(overrides)}
      review={null}
      mode={options.mode ?? "multi_role"}
      fake={options.fake ?? false}
      hasProposal
    />,
  );
}

describe("DispositionBanner", () => {
  const expectations: Record<Disposition, { title: RegExp; tone: string }> = {
    proposal_ready: { title: /Ready to use/, tone: "pass" },
    rejected: { title: /Not safe to use/, tone: "fail" },
    uncertain: { title: /^Not sure$/, tone: "warn" },
    no_change: { title: /Nothing to change/, tone: "neutral" },
    failed: { title: /Something went wrong/, tone: "fail" },
  };

  it.each(DISPOSITIONS.map((value) => [value]))("renders %s with its own title and tone", (disposition) => {
    render(
      <DispositionBanner
        verification={verification({ disposition, disposition_reasons: ["1 of 4 reference tests failed."] })}
        fake={false}
      />,
    );
    const region = screen.getByRole("region", { name: /Outcome/ });
    expect(region).toHaveAttribute("data-disposition", disposition);
    expect(region).toHaveAttribute("data-tone", expectations[disposition].tone);
    expect(within(region).getByRole("heading", { level: 3 })).toHaveTextContent(expectations[disposition].title);
    // Reasons sit in the Details drawer; the banner shows at most one short reason.
    if (disposition === "proposal_ready") {
      expect(within(region).queryByText("1 of 4 reference tests failed.")).toBeNull();
    } else {
      expect(within(region).getByText("1 of 4 reference tests failed.")).toBeInTheDocument();
    }
    expect(within(region).queryByText(/^Demo$/)).toBeNull();
  });

  it("only proposal_ready uses the pass tone", () => {
    const passing = DISPOSITIONS.filter((value) => expectations[value].tone === "pass");
    expect(passing).toEqual(["proposal_ready"]);
  });

  it("shows the short reason without its code", () => {
    render(
      <DispositionBanner
        verification={verification({
          disposition: "no_change",
          disposition_reasons: ["no_opportunity: No nested conditional can be flattened with guard clauses."],
        })}
        fake={false}
      />,
    );
    expect(screen.getByText(/No nested conditional can be flattened/)).toBeInTheDocument();
    expect(screen.queryByText("no_opportunity")).toBeNull();
  });

  it("labels fake-provider results so they cannot pass for model output", () => {
    render(<DispositionBanner verification={verification()} fake />);
    expect(screen.getByText("Demo")).toBeInTheDocument();
  });

  it("says when no verification was recorded", () => {
    render(<DispositionBanner verification={null} fake={false} />);
    expect(screen.getByRole("heading", { name: "No result saved" })).toBeInTheDocument();
  });
});

describe("VerificationPanel", () => {
  it("shows four separate cards and the equivalence note", () => {
    renderPanel();
    for (const name of ["Syntax", "Task rubric", "Reference tests", "Model review"]) {
      expect(screen.getByRole("article", { name })).toBeInTheDocument();
    }
    expect(screen.getByRole("note")).toHaveTextContent(
      "It does not prove that the proposal behaves like the original for every possible input.",
    );
  });

  it.each(SYNTAX_STATUSES.map((value) => [value]))("renders syntax %s", (status) => {
    renderPanel({ syntax: { status, error: status === "fail" ? "invalid syntax (line 3)" : null } });
    const badge = badgeOf("syntax");
    expect(badge).toHaveTextContent({ pass: "Passed", fail: "Failed", not_run: "Not checked" }[status]);
    expect(badge).toHaveAttribute("data-tone", { pass: "pass", fail: "fail", not_run: "neutral" }[status]);
    if (status === "fail") expect(card("syntax")).toHaveTextContent("invalid syntax (line 3)");
  });

  it.each(RUBRIC_STATUSES.map((value) => [value]))("renders rubric %s", (status) => {
    renderPanel({
      rubric: {
        status,
        checks: status === "not_run" ? {} : { nesting_reduced: status === "pass", same_name: true },
        reasons: status === "fail" ? ["Nesting depth did not decrease (2 -> 2)."] : [],
      },
    });
    const badge = badgeOf("rubric");
    expect(badge).toHaveAttribute("data-tone", { pass: "pass", fail: "fail", not_run: "neutral" }[status]);
    if (status === "not_run") {
      expect(card("rubric")).toHaveTextContent("No rubric checks were run.");
    } else {
      const items = within(card("rubric")).getAllByRole("listitem");
      expect(items[0]).toHaveTextContent(`Reduces the nesting depth: ${status === "pass" ? "passed" : "failed"}`);
      expect(items[1]).toHaveTextContent("Keeps the function name: passed");
    }
    if (status === "fail") expect(card("rubric")).toHaveTextContent("Nesting depth did not decrease (2 -> 2).");
  });

  const referenceExpectations: Record<ReferenceTestsStatus, { label: string; tone: string; evidence: string }> = {
    pass: { label: "Passed", tone: "pass", evidence: "present" },
    fail: { label: "Failed", tone: "fail", evidence: "present" },
    not_available: { label: "No tests", tone: "neutral", evidence: "absent" },
    not_run: { label: "Not checked", tone: "neutral", evidence: "absent" },
    error: { label: "Could not check", tone: "warn", evidence: "absent" },
  };

  it.each(REFERENCE_TEST_STATUSES.map((value) => [value]))("renders reference tests %s", (status) => {
    const counted = status === "pass" || status === "fail";
    renderPanel({
      reference_tests: {
        status,
        case_id: counted ? "shipping_cost" : null,
        total: counted ? 4 : null,
        passed: status === "pass" ? 4 : status === "fail" ? 3 : null,
        failed: status === "fail" ? 1 : counted ? 0 : null,
        errored: counted ? 0 : null,
        reason: status === "error" ? "The runner crashed." : null,
        duration_s: counted ? 0.44 : null,
        failures:
          status === "fail" ? [{ index: 2, kind: "missing_exception", detail: "Expected ValueError, but the call returned 0." }] : [],
      },
    });
    const expected = referenceExpectations[status];
    const badge = badgeOf("reference-tests");
    expect(badge).toHaveTextContent(expected.label);
    expect(badge).toHaveAttribute("data-tone", expected.tone);
    expect(card("reference-tests")).toHaveAttribute("data-evidence", expected.evidence);
    const text = card("reference-tests").textContent ?? "";
    if (status === "pass") expect(text).toContain("4 of 4 tests passed");
    if (status === "fail") {
      expect(text).toContain("3 of 4 tests passed, 1 failed");
      const table = within(card("reference-tests")).getByRole("table", { name: "Failed reference tests" });
      expect(table).toHaveTextContent("Expected exception not raised");
      expect(table).toHaveTextContent("Expected ValueError, but the call returned 0.");
    }
    if (status === "not_available") expect(text).toContain("No trusted reference tests exist for this input.");
    if (status === "not_run") expect(text).toContain("The trusted test runner did not run");
    if (status === "error") expect(text).toContain("The runner crashed.");
    if (status !== "pass") expect(text).not.toContain("Passed for these trusted inputs only");
  });

  it("never draws missing reference tests or review like a pass", () => {
    for (const status of ["not_available", "not_run", "error"] as const) {
      const { unmount } = renderPanel({
        reference_tests: { ...verification().reference_tests, status, total: null, passed: null, failed: null, errored: null },
        model_review: { status: status === "not_available" ? "not_run" : status, reasons: [], error: null },
      });
      for (const dimension of ["reference-tests", "model-review"]) {
        const badge = badgeOf(dimension);
        expect(badge).not.toHaveAttribute("data-tone", "pass");
        expect(badge).toHaveAttribute("data-evidence", "absent");
        expect(badge).not.toHaveTextContent(/Passed|Accepted/);
        expect(badge.querySelector(".icon--check")).toBeNull();
      }
      unmount();
    }
  });

  const reviewExpectations: Record<ModelReviewStatus, { label: string; tone: string }> = {
    accept: { label: "Accepted", tone: "pass" },
    reject: { label: "Rejected", tone: "fail" },
    uncertain: { label: "Not sure", tone: "warn" },
    error: { label: "Could not check", tone: "warn" },
    not_run: { label: "Not checked", tone: "neutral" },
  };

  it.each(MODEL_REVIEW_STATUSES.map((value) => [value]))("renders model review %s", (status) => {
    renderPanel({
      model_review: {
        status,
        reasons: status === "reject" ? ["A weight of 0 no longer raises ValueError."] : [],
        error: status === "error" ? "The review output was not valid JSON." : null,
      },
    });
    const badge = badgeOf("model-review");
    expect(badge).toHaveTextContent(reviewExpectations[status].label);
    expect(badge).toHaveAttribute("data-tone", reviewExpectations[status].tone);
    if (status === "reject") expect(card("model-review")).toHaveTextContent("A weight of 0 no longer raises ValueError.");
    if (status === "error") expect(card("model-review")).toHaveTextContent("The review output was not valid JSON.");
  });

  it("explains a missing review in single-role runs", () => {
    renderPanel({ model_review: { status: "not_run", reasons: [], error: null } }, { mode: "single_role" });
    expect(card("model-review")).toHaveTextContent("Single-role runs have no review step.");
  });

  it("marks a fake provider's accept as a placeholder without the pass tone", () => {
    renderPanel({}, { fake: true });
    const badge = badgeOf("model-review");
    expect(badge).toHaveTextContent("Accepted (placeholder)");
    expect(badge).toHaveAttribute("data-tone", "neutral");
    expect(badge).toHaveAttribute("data-evidence", "absent");
    expect(badge.querySelector(".icon--check")).toBeNull();
    expect(card("model-review")).toHaveTextContent("No language model reviewed the proposal.");
  });

  it("shows the reviewer's suggested correction", () => {
    render(
      <VerificationPanel
        verification={verification({ model_review: { status: "reject", reasons: ["Zero is accepted."], error: null } })}
        review={{ schema_version: 1, verdict: "reject", reasons: ["Zero is accepted."], suggested_correction: "Use weight <= 0." }}
        mode="multi_role"
        fake={false}
        hasProposal
      />,
    );
    expect(card("model-review")).toHaveTextContent("Suggested correction: Use weight <= 0.");
  });
});

describe("DiffViewer", () => {
  function renderDiff(diff: string | null = DIFF_TEXT, proposed = PROPOSED_CODE) {
    return render(
      <DiffViewer original={ORIGINAL_CODE} proposed={proposed} diff={diff} findings={runRecord().findings} />,
    );
  }

  it("renders the unified diff with line numbers and change markers", () => {
    renderDiff();
    const table = screen.getByRole("table", { name: /Unified diff/ });
    const rows = within(table).getAllByRole("row").filter((row) => row.classList.contains("diff-row"));
    expect(rows).toHaveLength(14);
    const added = rows.filter((row) => row.getAttribute("data-kind") === "add");
    const removed = rows.filter((row) => row.getAttribute("data-kind") === "remove");
    expect(added).toHaveLength(5);
    expect(removed).toHaveLength(7);
    const firstRemoved = within(removed[0]!).getAllByRole("cell");
    expect(firstRemoved[0]).toHaveTextContent("3");
    expect(firstRemoved[1]!.textContent).toBe("");
    expect(firstRemoved[2]).toHaveTextContent("Removed");
    expect(firstRemoved[3]).toHaveTextContent("if weight > 0:");
    const firstAdded = within(added[0]!).getAllByRole("cell");
    expect(firstAdded[1]).toHaveTextContent("3");
    expect(firstAdded[2]).toHaveTextContent("Added");
    expect(screen.getByText("5 lines added, 7 lines removed")).toBeInTheDocument();
    expect(within(table).getByText("@@ -1,9 +1,7 @@")).toBeInTheDocument();
  });

  it("switches to the side-by-side view of the full texts", () => {
    renderDiff();
    fireEvent.click(screen.getByRole("radio", { name: "Side by side" }));
    const table = screen.getByRole("table", { name: "Original and proposed code side by side" });
    expect(within(table).getByRole("columnheader", { name: "Original" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Proposed" })).toBeInTheDocument();
    const bodyRows = within(table).getAllByRole("row").slice(1);
    expect(bodyRows).toHaveLength(9);
    expect(bodyRows[2]).toHaveTextContent("if weight > 0:");
    expect(bodyRows[2]).toHaveTextContent("if weight <= 0:");
    // Lines 3 to 9 of the original were flagged by the analysis.
    expect(table.querySelectorAll('td[data-flagged="true"]')).toHaveLength(7);
  });

  it("falls back to the raw text when the diff cannot be parsed", () => {
    renderDiff("this is not a diff");
    expect(screen.getByText(/could not be read/)).toBeInTheDocument();
    expect(screen.getByText("this is not a diff")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Side by side" }));
    expect(screen.getByText(/could not be aligned/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Original" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Proposed" })).toBeInTheDocument();
  });

  it("says so when the service reports no differences", () => {
    renderDiff("", ORIGINAL_CODE);
    expect(screen.getByText(/no differences/)).toBeInTheDocument();
  });

  it("shows the no-newline marker", () => {
    renderDiff("@@ -1 +1 @@\n-a\n\\ No newline at end of file\n+b\n", "b");
    expect(screen.getByText("No newline at end of file")).toBeInTheDocument();
  });
});

describe("buildSteps", () => {
  const labels = (steps: ReturnType<typeof buildSteps>) => steps.map((step) => `${step.label}:${step.state}`);

  it("shows the analysis step only for multi-role runs", () => {
    expect(labels(buildSteps("multi_role", "analyzing", ["queued", "analyzing"], null))).toEqual([
      "Queued:done",
      "Find:current",
      "Rewrite:pending",
      "Check and review:pending",
      "Result:pending",
    ]);
    expect(labels(buildSteps("single_role", "generating", ["queued", "generating"], null))).toEqual([
      "Queued:done",
      "Rewrite:current",
      "Check:pending",
      "Result:pending",
    ]);
  });

  it("labels the single correction attempt", () => {
    const steps = buildSteps("multi_role", "generating", ["queued", "analyzing", "generating", "verifying", "generating"], null);
    expect(steps[2]).toMatchObject({ label: "Rewrite (retry)", state: "current" });
  });

  it("marks every step done for a completed run", () => {
    expect(labels(buildSteps("single_role", "completed", [], null))).toEqual([
      "Queued:done",
      "Rewrite:done",
      "Check:done",
      "Done:done",
    ]);
  });

  it("marks the failing step from the error stage, in either vocabulary", () => {
    const byStage = buildSteps("multi_role", "failed", [], "generation");
    expect(labels(byStage)).toEqual([
      "Queued:done",
      "Find:done",
      "Rewrite:failed",
      "Check and review:pending",
      "Failed:failed",
    ]);
    expect(labels(buildSteps("multi_role", "failed", [], "generating"))).toEqual(labels(byStage));
    expect(labels(buildSteps("multi_role", "failed", ["queued", "analyzing"], null))[1]).toBe("Find:failed");
    expect(labels(buildSteps("multi_role", "failed", [], null)).slice(0, 4).every((label) => label.endsWith(":pending"))).toBe(true);
  });

  it("starts at the queued step before the first status arrives", () => {
    expect(buildSteps("multi_role", null, [], null)[0]!.state).toBe("current");
  });
});

describe("CheckRow", () => {
  const chip = (name: string) => screen.getByText(name).closest("li") as HTMLElement;

  it("shows the four checks with counts, and missing evidence is never a pass", () => {
    render(
      <CheckRow
        verification={verification({
          reference_tests: { ...verification().reference_tests, status: "pass", total: 6, passed: 6 },
        })}
        mode="multi_role"
        fake={false}
      />,
    );
    expect(chip("Valid Python")).toHaveAttribute("data-tone", "pass");
    expect(chip("Tests")).toHaveTextContent("6/6 passed");
    expect(screen.getByText(/not every possible input/)).toBeInTheDocument();
  });

  it("marks tests that did not run as not checked, not passed", () => {
    render(
      <CheckRow
        verification={verification({
          reference_tests: { ...verification().reference_tests, status: "not_available", total: null, passed: null },
        })}
        mode="multi_role"
        fake={false}
      />,
    );
    expect(chip("Tests")).toHaveAttribute("data-evidence", "absent");
    expect(chip("Tests")).not.toHaveAttribute("data-tone", "pass");
    expect(chip("Tests")).toHaveTextContent("No tests");
  });

  it("never shows a fake review as accepted, and marks the skipped review in fast mode", () => {
    const { unmount } = render(<CheckRow verification={verification()} mode="multi_role" fake />);
    expect(chip("Review")).toHaveTextContent("Demo only");
    expect(chip("Review")).not.toHaveAttribute("data-tone", "pass");
    unmount();
    render(
      <CheckRow
        verification={verification({ model_review: { status: "not_run", reasons: [], error: null } })}
        mode="single_role"
        fake={false}
      />,
    );
    expect(chip("Review")).toHaveTextContent("Skipped (Fast)");
  });
});
