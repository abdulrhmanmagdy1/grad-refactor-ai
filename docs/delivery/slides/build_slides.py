"""Build the presentation slides from the committed records.

Run from the repository root (python-pptx is not part of the locked environment):

    uv run --no-project --with python-pptx==1.0.2 python docs/delivery/slides/build_slides.py

The slides follow docs/delivery/presentation-outline.md. Every number on them comes from a
committed record that the speaker notes name.
"""

from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("grad-refactor-ai-presentation.pptx")
SHOTS = ROOT / "docs" / "report" / "screenshots"
TRAINING = ROOT / "experiments" / "training" / "full-2026-10-21.json"
RESULTS = "experiments/evaluation/test-2026-10-21/targets-report/summary.md"

NAVY = RGBColor(0x1E, 0x2A, 0x78)
BLUE = RGBColor(0x25, 0x46, 0xC8)
INK = RGBColor(0x1F, 0x29, 0x37)
MUTED = RGBColor(0x5B, 0x64, 0x72)
LIGHT = RGBColor(0xF1, 0xF4, 0xFA)
LINE = RGBColor(0xD5, 0xDB, 0xE5)
GREEN = RGBColor(0x1F, 0x8A, 0x4C)
RED = RGBColor(0xC2, 0x35, 0x35)
AMBER = RGBColor(0xC7, 0x7C, 0x0E)
GRAY = RGBColor(0x9A, 0xA3, 0xAE)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

W, H = Inches(13.333), Inches(7.5)
M = Inches(0.6)
FONT = "Calibri"
MONO = "Consolas"

# Speaker notes: the full statement behind each slide and the record it comes from.
NOTES = {
    "title": """Abdelrahman Magdy, 0:30. One sentence: a local tool that proposes one refactoring
for one small Python function, reports every check separately, and a study of whether
fine-tuning and role coordination make the proposals more reliable.""",
    "problem": """A model's refactoring can look cleaner and still be unnecessary, invalid or
behaviorally wrong. The three research questions come from the project proposal
(docs/proposal/project-proposal.md). Improvement was a hypothesis, not a promise; a negative
result is a valid outcome of the study.""",
    "related": """From the reading table in docs/research/related-work.md: Fowler defines the task
(R1); language models produce unsafe refactorings (R3); multi-agent refactoring and role-based
generation exist with large closed models (R5, R6); self-repair gains depend on feedback quality
and cost (R8); LoRA and PEFT make adaptation fit a small GPU (R9, R10); tests can be insufficient
(R14); code datasets leak through duplicates (R15).""",
    "task": """Example from docs/requirements/task-scope.md. Scope: one synchronous top-level
function, at most 3,000 characters and 60 lines. Out-of-scope input ends as no_change with a
reason code and no model call. The rubric has eight structural checks, and a deterministic
reference transformation produces the training targets. Why this task (ADR12): the rubric is
deterministic and behavior is checkable on pure functions.""",
    "architecture": """Browser, FastAPI service, workflow coordinator, then the model worker
process and the isolated reference runner, with SQLite run history behind the service. A bounded
queue and one worker thread. The API parses code and never executes it. /health reports the
actual mode (fake or local model) and the exact model identity (docs/architecture/contracts.md).""",
    "workflow": """Deterministic validation first: out-of-scope input ends as no_change with zero
calls. Single-role (Fast in the interface): exactly 1 call. Multi-role (With review): analysis,
refactoring and review, at most 5 calls and 1 correction. Strict parsing with at most one
deterministic repair; the model is never asked again. A run deadline; a run fails when the
provider reports another adapter state than requested (docs/architecture/workflow.md).""",
    "verification": """Syntax, rubric, trusted reference tests and model review are reported
separately. Disposition order: failed, no_change, rejected, uncertain, proposal_ready. The runner:
static admission, a separate interpreter, Job Object or rlimits, an audit hook, and 19
self-checks that disable execution if any fails. Honest limit: it is not a sandbox for hostile
code (docs/development/runner-safety.md).""",
    "model": """Qwen2.5-Coder-0.5B-Instruct at revision ea3f2471 (Apache-2.0), on an RTX 2050 with
4 GB. Measured: 17.6 s warm load, about 1.0 GB of GPU memory, 13.8 to 26.1 tokens per second;
the 1.5B candidate was not measured because of the disk limit (experiments/models/README.md).
The explanation-first prompt gave no code block on the pilot functions; the code-first
refactor-v2 format parsed 24 of 24 validation outputs, but 14 were unchanged copies
(experiments/models/2026-10-20-prompt-format-selection.md).""",
    "training": """LoRA rank 8, alpha 16 on the refactoring role; 4,399,104 trainable parameters.
The pilot was saved, reloaded in a fresh process, interrupted and resumed. The full run failed on
the laptop after 22 of 237 steps (out of virtual memory) and moved to Kaggle's T4 in fp32.
Training record experiments/training/full-2026-10-21.json: 627 training records, 3 epochs, 120
optimizer steps with an effective batch of 16 (two GPUs were visible), 20.5 GPU minutes, best
validation loss 0.0360 at epoch 3, adapter weights sha256 dff9ae02... The selection rule was
written before any comparison; on validation, arm C was accepted in 69 of 84 cases against 6 of
84 for arm A, so the adapter was adopted
(experiments/training/validation-selection-2026-10-20.json).""",
    "data": """Real code rarely fits the task: 4 of 974 MBPP, 1 of 164 HumanEval and 4 of 2,630
TheAlgorithms functions. 799 records: 81 team template families plus 4 real functions. 5,168
trusted reference tests, which detect 95.1% of single-point mutants. Splits 627 / 84 / 88 by
source group; no near-duplicates; the test split frozen by its case-content hash. The license of
the team-authored data is pending (docs/data-and-training/data-plan.md).""",
    "protocol": """Arms A to D and four paired comparisons: B vs A, C vs A, D vs C, D vs B. Primary
measure: proposal_ready over all attempted cases. Exact McNemar tests with a Holm adjustment;
results also by family. Targets come from the validation baseline and were frozen in
experiments/evaluation/protocol-freeze.json before the test run. The correction's oracle feedback
(up to three failing tests) goes only to the multi-role arms (docs/evaluation/protocol.md).""",
    "results": f"""One run of protocol eval-v1 on a Kaggle T4 in float32, from the clean commit
9582c66 ({RESULTS}). Denominator: all 88 attempted cases per arm. Ready (proposal_ready): A 7
(8.0%), B 1 (1.1%), C 70 (79.5%), D 35 (39.8%). Rejected: 80, 85, 18, 19. Uncertain: 0, 2, 0,
34. Failed: A 1 (unparseable_output). No timeouts. These are test results; the validation
results are reported separately and must not be mixed with them.""",
    "comparisons": """Paired exact McNemar with Holm adjustment over the four comparisons
(targets-report/paired.csv). C vs A: 65 cases only C accepts, 2 only A, p < 0.0001. D vs B: 34
vs 0, p < 0.0001. D vs C: 36 only C, 1 only D, p < 0.0001. B vs A: 6 only A, 0 only B,
p = 0.031 (no direction was expected). Targets: 11 of 12 met; D's floor of 43.52% was missed
with 39.8%. Why the review step hurts: the review role uses the original model; it often repeated
itself until the 384-token limit, its verdict could not be read, and the run became uncertain
(34 of D's 88). Cost: median latency A 3.0 s, C 7.7 s, B 16.0 s, D 17.9 s; mean calls per case
1.00, 1.00, 4.93, 3.43. The 88 cases come from 16 source groups and are not independent.""",
    "interface": """Screenshot docs/report/screenshots/s05-proposal-ready-light.png: one real run
with the fine-tuned model (Fast, Library fine case), not a measured rate. The four results are
shown separately; missing evidence is drawn as absent, never as a pass. The diff is computed by
the application; decisions are records only. Demo mode carries a permanent banner. WCAG AA
contrast is checked by tests in both themes (docs/report/notes/frontend.md).""",
    "demo": """Follow docs/delivery/demo-script.md. Say the mode before the first run: the header
pill shows "Fine-tuned model ready"; demo mode would show an amber banner. Abdullah Tarek and
Abdelrahman Adel answer questions on the checks and the model.""",
    "limits": """Limitations: one task; a 0.5B model; template-based data; tests that are not
proof; a runner that is not a sandbox; one laptop, with training and evaluation on Kaggle in
fp32 while the laptop serves in bf16. The declaration of coding-agent assistance must use the
wording agreed with the supervisor (R1 question 5, ADR16); it is not written here because that
meeting has not taken place. Future work: the candidates in
docs/supervisor-reviews/r5-delivery.md, question 5.""",
    "questions": """Likely questions with grounded answers are in
docs/delivery/presentation-outline.md.""",
}

SHIPPING_BEFORE = '''def shipping_cost(weight, express):
    """Return the shipping cost."""
    if weight > 0:
        if express:
            return weight * 3
        else:
            return weight * 2
    else:
        raise ValueError("weight must be positive")'''

SHIPPING_AFTER = '''def shipping_cost(weight, express):
    """Return the shipping cost."""
    if weight <= 0:
        raise ValueError("weight must be positive")
    if express:
        return weight * 3
    return weight * 2'''

# Outcomes on the frozen test split: ready, rejected, uncertain, failed (summary.md).
ARMS = {
    "A": ("A  original, Fast", (7, 80, 0, 1)),
    "B": ("B  original, review", (1, 85, 2, 0)),
    "C": ("C  fine-tuned, Fast", (70, 18, 0, 0)),
    "D": ("D  fine-tuned, review", (35, 19, 34, 0)),
}


def text(
    slide,
    left,
    top,
    width,
    height,
    lines,
    size=20,
    color=INK,
    bold=False,
    font=FONT,
    align=PP_ALIGN.LEFT,
    spacing=6,
):
    """A text box; `lines` is one string or a list of strings."""
    frame = slide.shapes.add_textbox(left, top, width, height).text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = Inches(0.05)
    for index, line in enumerate([lines] if isinstance(lines, str) else lines):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = align
        paragraph.space_after = Pt(spacing)
        run = paragraph.add_run()
        run.text = line
        run.font.name = font
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color


def bullets(slide, left, top, width, height, items, size=22):
    text(slide, left, top, width, height, [f"•  {item}" for item in items], size=size, spacing=12)


def box(
    slide,
    left,
    top,
    width,
    height,
    label=None,
    fill=WHITE,
    border=BLUE,
    size=18,
    color=INK,
    shape=MSO_SHAPE.ROUNDED_RECTANGLE,
):
    """A shape with a bold first line and a muted second line."""
    item = slide.shapes.add_shape(shape, left, top, width, height)
    item.fill.solid()
    item.fill.fore_color.rgb = fill
    item.line.color.rgb = border
    item.line.width = Pt(1.25)
    item.shadow.inherit = False
    frame = item.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    lines = [] if label is None else [label] if isinstance(label, str) else label
    for index, line in enumerate(lines):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = PP_ALIGN.CENTER
        run = paragraph.add_run()
        run.text = line
        run.font.name = FONT
        run.font.size = Pt(size if index == 0 else size - 3)
        run.font.bold = index == 0
        run.font.color.rgb = color if index == 0 else MUTED


def arrow(slide, x1, y1, x2, y2):
    connector = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x1, y1, x2, y2)
    connector.line.color.rgb = MUTED
    connector.line.width = Pt(2)
    line = connector.line._get_or_add_ln()
    line.append(line.makeelement(qn("a:tailEnd"), {"type": "triangle"}))


def table(slide, left, top, rows, widths, size=16, row_height=0.5):
    total = Inches(sum(widths))
    grid = slide.shapes.add_table(
        len(rows), len(rows[0]), left, top, total, Inches(row_height * len(rows))
    ).table
    for index, width in enumerate(widths):
        grid.columns[index].width = Inches(width)
    for r, row in enumerate(rows):
        grid.rows[r].height = Inches(row_height)
        for c, value in enumerate(row):
            cell = grid.cell(r, c)
            cell.text = value
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY if r == 0 else (WHITE if r % 2 else LIGHT)
            paragraph = cell.text_frame.paragraphs[0]
            paragraph.alignment = PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER
            for run in paragraph.runs:
                run.font.name = FONT
                run.font.size = Pt(size)
                run.font.bold = r == 0
                run.font.color.rgb = WHITE if r == 0 else INK


def facts(slide, items, top, size=40, width=3.05):
    """A row of big numbers with a caption under each."""
    for index, (number, caption) in enumerate(items):
        left = M + Inches(width * index)
        text(
            slide,
            left,
            top,
            Inches(width - 0.15),
            Inches(0.9),
            number,
            size=size,
            color=BLUE,
            bold=True,
        )
        text(
            slide,
            left,
            top + Inches(0.85),
            Inches(width - 0.15),
            Inches(0.8),
            caption,
            size=18,
            color=MUTED,
        )


class Deck:
    def __init__(self):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = W, H
        self.count = 0

    def slide(self, title, notes, speaker="", minutes=""):
        self.count += 1
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, Inches(0.12))
        band.fill.solid()
        band.fill.fore_color.rgb = BLUE
        band.line.fill.background()
        if title:
            text(
                slide,
                M,
                Inches(0.35),
                W - 2 * M,
                Inches(0.8),
                title,
                size=34,
                color=NAVY,
                bold=True,
            )
        if speaker:
            text(
                slide,
                M,
                H - Inches(0.5),
                Inches(8),
                Inches(0.35),
                f"{speaker}  ·  {minutes}",
                size=12,
                color=MUTED,
            )
        text(
            slide,
            W - M - Inches(1),
            H - Inches(0.5),
            Inches(1),
            Inches(0.35),
            str(self.count),
            size=12,
            color=MUTED,
            align=PP_ALIGN.RIGHT,
        )
        slide.notes_slide.notes_text_frame.text = " ".join(NOTES[notes].split())
        return slide


def title_slide(deck):
    s = deck.slide("", "title")
    text(
        s,
        M,
        Inches(1.6),
        W - 2 * M,
        Inches(1.2),
        "Multi-Agent Refactoring for Python",
        size=46,
        color=NAVY,
        bold=True,
    )
    text(
        s,
        M,
        Inches(2.6),
        W - 2 * M,
        Inches(1),
        "Fine-tuning a small local code model for guard-clause refactoring",
        size=26,
        color=MUTED,
    )
    team = [
        ("Abdelrahman Magdy", "Backend, integration and coordination"),
        ("Abdullah Tarek", "Agent workflow and verification"),
        ("Abdelrahman Adel", "Models and training"),
        ("Shahd Abdelhay", "Data, research and evaluation"),
        ("Dania El-Walily", "Frontend, report and presentation"),
    ]
    for index, (name, role) in enumerate(team):
        top = Inches(3.9 + 0.55 * index)
        text(s, M, top, Inches(3.6), Inches(0.5), name, size=20, bold=True)
        text(s, M + Inches(3.7), top, Inches(7), Inches(0.5), role, size=20, color=MUTED)


def intro_slides(deck):
    s = deck.slide("The problem and our questions", "problem", "Abdelrahman Magdy", "1:00")
    bullets(
        s,
        M,
        Inches(1.5),
        Inches(6.2),
        Inches(4.8),
        [
            "AI can rewrite code that looks cleaner but behaves differently",
            "So every proposal must be checked, and each check reported on its own",
            "We study one refactoring on one small Python function",
        ],
    )
    box(s, Inches(7.2), Inches(1.5), Inches(5.5), Inches(4.6), fill=LIGHT, border=LINE)
    text(
        s,
        Inches(7.5),
        Inches(1.7),
        Inches(5),
        Inches(0.5),
        "Research questions",
        size=22,
        color=NAVY,
        bold=True,
    )
    text(
        s,
        Inches(7.5),
        Inches(2.35),
        Inches(5),
        Inches(3.6),
        [
            "1. Do several coordinated roles beat one model call?",
            "2. Does fine-tuning a small model help?",
            "3. Is any gain worth its cost in time and calls?",
        ],
        spacing=16,
    )

    s = deck.slide("What others found", "related", "Shahd Abdelhay", "1:00")
    rows = [
        ("Fowler", "Defines guard clauses, the refactoring we use"),
        ("LLM refactoring studies", "Models often break behavior, so checks must be separate"),
        ("Multi-agent tools", "Shown with large closed models; we test a 0.5B local model"),
        ("Self-repair", "Corrections help only when the feedback is good"),
        ("LoRA / PEFT", "Lets a 4 GB GPU adapt a model"),
        ("Tests and datasets", "Tests can miss bugs; duplicates leak between splits"),
    ]
    for index, (name, finding) in enumerate(rows):
        top = Inches(1.55 + 0.82 * index)
        box(
            s, M, top, Inches(3.6), Inches(0.66), name, fill=NAVY, border=NAVY, size=17, color=WHITE
        )
        text(s, M + Inches(3.85), top + Inches(0.1), Inches(8), Inches(0.6), finding, size=19)

    s = deck.slide("The task: flatten nested if statements", "task", "Abdullah Tarek", "1:00")
    for index, (label, code, accent) in enumerate(
        (("Before: depth 2", SHIPPING_BEFORE, RED), ("After: depth 1", SHIPPING_AFTER, GREEN))
    ):
        left = M + Inches(6.15 * index)
        text(s, left, Inches(1.45), Inches(5.9), Inches(0.5), label, color=accent, bold=True)
        box(
            s,
            left,
            Inches(2.0),
            Inches(5.9),
            Inches(3.4),
            fill=LIGHT,
            border=accent,
            shape=MSO_SHAPE.RECTANGLE,
        )
        text(
            s,
            left + Inches(0.15),
            Inches(2.1),
            Inches(5.7),
            Inches(3.2),
            code.split("\n"),
            size=13,
            font=MONO,
            spacing=0,
        )
    bullets(
        s,
        M,
        Inches(5.6),
        W - 2 * M,
        Inches(1.2),
        [
            "One function, at most 60 lines; anything else gets “Nothing to change” "
            "with no model call",
        ],
        size=20,
    )


def system_slides(deck):
    s = deck.slide("How the system fits together", "architecture", "Abdelrahman Magdy", "1:00")
    top, bw, bh, step = Inches(2.3), Inches(2.35), Inches(1.4), Inches(3.05)
    xs = [M + step * i for i in range(4)]
    labels = [
        ["Browser", "React interface"],
        ["Web service", "FastAPI, queue, SQLite"],
        ["Coordinator", "find, rewrite, review"],
        ["Model worker", "Qwen 0.5B + LoRA"],
    ]
    for x, label in zip(xs, labels, strict=True):
        box(s, x, top, bw, bh, label, size=19)
    for x in xs[:-1]:
        arrow(s, x + bw, top + bh // 2, x + step, top + bh // 2)
    low = Inches(4.6)
    box(s, xs[2], low, bw, bh, ["Checks", "syntax, rubric, tests, review"], border=GREEN, size=19)
    box(s, xs[3], low, bw, bh, ["Test runner", "separate, limited process"], border=GREEN, size=19)
    arrow(s, xs[2] + bw // 2, top + bh, xs[2] + bw // 2, low)
    arrow(s, xs[2] + bw, low + bh // 2, xs[3], low + bh // 2)
    text(
        s,
        M,
        Inches(4.75),
        Inches(5.6),
        Inches(1.6),
        ["The web service never runs your code.", "It only reads it with Python's parser."],
        size=19,
        color=MUTED,
    )

    s = deck.slide("Two ways to run", "workflow", "Abdullah Tarek", "1:00")
    modes = [
        ("Fast", ["Rewrite", "1 model call"]),
        ("With review", ["Find → Rewrite → Review", "3 calls, up to 5 with one retry"]),
    ]
    for index, (name, label) in enumerate(modes):
        top = Inches(1.6 + 1.75 * index)
        box(s, M, top, Inches(2.6), Inches(1.4), name, fill=NAVY, border=NAVY, size=24, color=WHITE)
        box(s, M + Inches(2.9), top, Inches(6.2), Inches(1.4), label, size=22)
    bullets(
        s,
        M,
        Inches(5.25),
        W - 2 * M,
        Inches(1.6),
        [
            "Input outside the task stops before any model call",
            "Model output must match a strict format; one automatic repair at most",
        ],
        size=20,
    )

    s = deck.slide("Four checks, never merged", "verification", "Abdullah Tarek", "1:00")
    checks = [
        ["Valid Python", "Python's parser"],
        ["Guard clauses", "8 structure checks"],
        ["Tests", "trusted examples, isolated"],
        ["Review", "the model's opinion"],
    ]
    for index, label in enumerate(checks):
        box(
            s,
            M + Inches(3.05 * index),
            Inches(1.6),
            Inches(2.8),
            Inches(1.5),
            label,
            border=GREEN,
            size=21,
        )
    text(s, M, Inches(3.5), Inches(6), Inches(0.5), "The result is one of five:", color=MUTED)
    outcomes = [
        ("Ready to use", GREEN),
        ("Not safe to use", RED),
        ("Not sure", AMBER),
        ("Nothing to change", GRAY),
        ("Something went wrong", RED),
    ]
    for index, (name, color) in enumerate(outcomes):
        box(
            s,
            M + Inches(2.45 * index),
            Inches(4.1),
            Inches(2.3),
            Inches(0.8),
            name,
            fill=color,
            border=color,
            size=16,
            color=WHITE,
        )
    bullets(
        s,
        M,
        Inches(5.3),
        W - 2 * M,
        Inches(1.4),
        [
            "A missing check is never shown as a pass; the review never overrides a failed test",
            "Passing tests cover the tested inputs only, not every possible input",
        ],
        size=19,
    )


def model_slides(deck, training):
    s = deck.slide("The model and the laptop", "model", "Abdelrahman Adel", "1:00")
    facts(
        s,
        [
            ("0.5B", "Qwen2.5-Coder, Apache-2.0"),
            ("4 GB", "laptop GPU (RTX 2050)"),
            ("~1 GB", "GPU memory in use"),
            ("14-26", "tokens per second"),
        ],
        Inches(1.7),
        size=44,
    )
    bullets(
        s,
        M,
        Inches(3.9),
        W - 2 * M,
        Inches(2.6),
        [
            "The original model mostly copied the input back unchanged (14 of 24)",
            "Putting the code block first fixed the output format (24 of 24 parsed)",
            "So the open question was: can fine-tuning teach the actual rewrite?",
        ],
        size=21,
    )

    s = deck.slide("Fine-tuning with LoRA", "training", "Abdelrahman Adel", "1:00")
    losses = training["train_loss_history"]
    data = CategoryChartData()
    data.categories = [str(step) for step, _ in losses]
    data.add_series("Training loss", [value for _, value in losses])
    chart = s.shapes.add_chart(
        XL_CHART_TYPE.LINE, M, Inches(1.5), Inches(6.6), Inches(4.6), data
    ).chart
    chart.has_legend = False
    chart.has_title = True
    chart.chart_title.text_frame.text = "Training loss by optimizer step"
    chart.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(16)
    series = chart.plots[0].series[0]
    series.format.line.color.rgb = BLUE
    series.format.line.width = Pt(2.5)
    series.smooth = False
    chart.category_axis.tick_labels.font.size = Pt(11)
    # Label every fourth step (20 optimizer steps) so the axis stays readable.
    axis = chart.category_axis._element
    skip = axis.makeelement(qn("c:tickLblSkip"), {"val": "4"})
    anchor = axis.find(qn("c:noMultiLvlLbl"))
    if anchor is None:
        axis.append(skip)
    else:
        anchor.addprevious(skip)
    chart.value_axis.tick_labels.font.size = Pt(11)
    chart.value_axis.has_major_gridlines = False
    first, last = losses[0][1], losses[-1][1]
    items = [
        (f"{training['data']['records']['train']}", "training functions"),
        (f"{training['kaggle_session']['gpu_minutes']} min", "on a free Kaggle T4 GPU"),
        (f"{first:.2f} → {last:.2f}", "training loss"),
        ("69 vs 6", "of 84 validation cases ready, with vs without the adapter"),
    ]
    for index, (number, caption) in enumerate(items):
        top = Inches(1.5 + 1.15 * index)
        text(s, Inches(7.6), top, Inches(5.2), Inches(0.6), number, size=30, color=BLUE, bold=True)
        text(
            s,
            Inches(7.6),
            top + Inches(0.55),
            Inches(5.2),
            Inches(0.5),
            caption,
            size=16,
            color=MUTED,
        )

    s = deck.slide("The dataset", "data", "Shahd Abdelhay", "1:00")
    facts(
        s,
        [
            ("799", "functions"),
            ("5,168", "trusted tests"),
            ("95.1%", "of injected bugs caught"),
            ("627 / 84 / 88", "train / validation / test"),
        ],
        Inches(1.7),
        size=36,
    )
    bullets(
        s,
        M,
        Inches(3.7),
        W - 2 * M,
        Inches(3),
        [
            "Real code rarely has this pattern, so most functions come from team-written templates",
            "Splits keep whole template families apart, and duplicates were checked",
            "The 88 test cases were frozen before any final run",
        ],
        size=21,
    )


def result_slides(deck):
    s = deck.slide("How we compared", "protocol", "Shahd Abdelhay", "1:00")
    table(
        s,
        M,
        Inches(1.6),
        [
            ["", "Original model", "Fine-tuned model"],
            ["Fast (1 call)", "A", "C"],
            ["With review (3-5 calls)", "B", "D"],
        ],
        [3.0, 2.1, 2.1],
        size=22,
        row_height=0.85,
    )
    bullets(
        s,
        Inches(8.3),
        Inches(1.6),
        Inches(4.5),
        Inches(4.8),
        [
            "Same 88 test cases for all four",
            "Score: share marked “Ready to use”",
            "Targets fixed on validation first",
            "Paired tests: exact McNemar + Holm",
        ],
        size=20,
    )

    s = deck.slide("Results on the 88 frozen test cases", "results", "Shahd Abdelhay", "1:00")
    order = ["D", "C", "B", "A"]
    data = CategoryChartData()
    data.categories = [ARMS[arm][0] for arm in order]
    outcomes = ("Ready to use", "Not safe to use", "Not sure", "Something went wrong")
    for index, name in enumerate(outcomes):
        data.add_series(name, [ARMS[arm][1][index] for arm in order])
    chart = s.shapes.add_chart(
        XL_CHART_TYPE.BAR_STACKED, M, Inches(1.4), Inches(8.4), Inches(5.2), data
    ).chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout = False
    chart.legend.font.size = Pt(14)
    plot = chart.plots[0]
    for series, color in zip(plot.series, (GREEN, RED, AMBER, GRAY), strict=True):
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = color
    plot.gap_width = 60
    plot.has_data_labels = True
    labels = plot.data_labels
    labels.font.size = Pt(13)
    labels.font.bold = True
    labels.font.color.rgb = WHITE
    labels.position = XL_LABEL_POSITION.CENTER
    labels.number_format = "0;;;"
    labels.number_format_is_linked = False
    chart.category_axis.tick_labels.font.size = Pt(15)
    chart.value_axis.minimum_scale = 0
    chart.value_axis.maximum_scale = 88
    chart.value_axis.major_unit = 22
    chart.value_axis.has_major_gridlines = False
    chart.value_axis.tick_labels.font.size = Pt(12)
    for index, (number, caption, color) in enumerate(
        (
            ("79.5%", "fine-tuned, Fast (C)", GREEN),
            ("8.0%", "original, Fast (A)", MUTED),
            ("39.8%", "fine-tuned, with review (D)", AMBER),
        )
    ):
        top = Inches(1.6 + 1.6 * index)
        text(s, Inches(9.3), top, Inches(3.6), Inches(0.8), number, size=40, color=color, bold=True)
        text(
            s,
            Inches(9.3),
            top + Inches(0.75),
            Inches(3.6),
            Inches(0.6),
            caption,
            size=17,
            color=MUTED,
        )

    s = deck.slide(
        "What the comparisons show", "comparisons", "Abdelrahman Adel and Shahd Abdelhay", "1:00"
    )
    table(
        s,
        M,
        Inches(1.5),
        [
            ["Comparison", "Only first ready", "Only second ready", "p (Holm)"],
            ["Fine-tuning, Fast (C vs A)", "65", "2", "< 0.0001"],
            ["Fine-tuning, with review (D vs B)", "34", "0", "< 0.0001"],
            ["Adding review, fine-tuned (D vs C)", "1", "36", "< 0.0001"],
            ["Adding review, original (B vs A)", "0", "6", "0.031"],
        ],
        [4.2, 1.5, 1.6, 1.1],
        row_height=0.6,
    )
    bullets(
        s,
        M,
        Inches(4.7),
        Inches(8.4),
        Inches(2.2),
        [
            "Fine-tuning helped a lot",
            "The review step lowered results: the untuned reviewer was often cut off",
            "11 of 12 targets met; the with-review target was missed",
        ],
        size=19,
    )
    text(
        s,
        Inches(9.4),
        Inches(1.5),
        Inches(3.4),
        Inches(0.5),
        "Cost per case",
        size=18,
        color=NAVY,
        bold=True,
    )
    table(
        s,
        Inches(9.4),
        Inches(2.0),
        [
            ["Arm", "Median time", "Calls"],
            ["A", "3.0 s", "1.0"],
            ["C", "7.7 s", "1.0"],
            ["B", "16.0 s", "4.9"],
            ["D", "17.9 s", "3.4"],
        ],
        [0.8, 1.4, 1.1],
        row_height=0.55,
    )


def closing_slides(deck):
    s = deck.slide("The interface", "interface", "Dania El-Walily", "0:45")
    s.shapes.add_picture(
        str(SHOTS / "s05-proposal-ready-light.png"), M, Inches(1.4), width=Inches(8.3)
    )
    bullets(
        s,
        Inches(9.2),
        Inches(1.5),
        Inches(3.6),
        Inches(5),
        [
            "Verdict first, in plain words",
            "Four check chips",
            "The change as a diff",
            "Accept or reject only records a decision",
            "Your files are never changed",
        ],
        size=19,
    )

    s = deck.slide("Live demonstration", "demo", "Dania El-Walily", "9:30")
    steps = [
        ("1  A success", "a demo case → Ready to use", GREEN),
        ("2  Out of scope", "an already flat function → Nothing to change", GRAY),
        ("3  A failed check", "invalid syntax, and a result without trusted tests", RED),
    ]
    for index, (name, detail, color) in enumerate(steps):
        top = Inches(1.7 + 1.45 * index)
        box(
            s,
            M,
            top,
            Inches(3.4),
            Inches(1.15),
            name,
            fill=color,
            border=color,
            size=22,
            color=WHITE,
        )
        text(s, M + Inches(3.7), top + Inches(0.3), Inches(8), Inches(0.7), detail, size=22)

    s = deck.slide("Limits and next steps", "limits", "Abdelrahman Magdy", "1:30")
    text(s, M, Inches(1.45), Inches(6), Inches(0.5), "Limits", size=22, color=NAVY, bold=True)
    bullets(
        s,
        M,
        Inches(2.0),
        Inches(6),
        Inches(4.2),
        [
            "One refactoring type, one small model",
            "Most data comes from templates",
            "Tests are examples, not proof",
            "The test runner is not a full sandbox",
            "Reproduced on one laptop only",
        ],
        size=19,
    )
    text(
        s,
        Inches(7.0),
        Inches(1.45),
        Inches(5.7),
        Inches(0.5),
        "Next steps",
        size=22,
        color=NAVY,
        bold=True,
    )
    bullets(
        s,
        Inches(7.0),
        Inches(2.0),
        Inches(5.7),
        Inches(4.2),
        [
            "A reliable reviewer (tuned, or not cut off)",
            "A second refactoring type",
            "More real code in the data",
            "A stronger isolation layer",
            "Try the 1.5B model",
        ],
        size=19,
    )
    text(
        s,
        M,
        Inches(6.2),
        W - 2 * M,
        Inches(0.5),
        "Built with AI coding assistance; each of us owns and explains our part.",
        size=16,
        color=MUTED,
    )

    s = deck.slide("", "questions")
    text(
        s,
        M,
        Inches(2.6),
        W - 2 * M,
        Inches(1.2),
        "Thank you",
        size=54,
        color=NAVY,
        bold=True,
        align=PP_ALIGN.CENTER,
    )
    text(
        s,
        M,
        Inches(3.8),
        W - 2 * M,
        Inches(0.8),
        "Questions?",
        size=30,
        color=MUTED,
        align=PP_ALIGN.CENTER,
    )


def build():
    training = json.loads(TRAINING.read_text(encoding="utf-8"))
    deck = Deck()
    title_slide(deck)
    intro_slides(deck)
    system_slides(deck)
    model_slides(deck, training)
    result_slides(deck)
    closing_slides(deck)
    deck.prs.save(OUT)
    return deck.count


if __name__ == "__main__":
    count = build()
    print(f"{OUT.relative_to(ROOT).as_posix()}: {count} slides, {OUT.stat().st_size:,} bytes")
