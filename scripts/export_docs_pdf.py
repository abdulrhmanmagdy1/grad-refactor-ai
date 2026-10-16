import hashlib
import html
import json
import re
import subprocess
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/pdf"
OUT.mkdir(exist_ok=True, parents=True)
BASE = "https://github.com/abdulrhmanmagdy1/grad-refactor-ai"
W, H = A4
M = 46
BW = W - 2 * M
NAVY = colors.HexColor("#17334A")
TEAL = colors.HexColor("#067887")
INK = colors.HexColor("#263746")
GRAY = colors.HexColor("#596B78")
PALE = colors.HexColor("#F1F5F8")
LINE = colors.HexColor("#D8E2E8")
styles = {
    "body": ParagraphStyle(
        "Body", fontName="Helvetica", fontSize=10, leading=14.2, textColor=INK, spaceAfter=6
    ),
    "h1": ParagraphStyle(
        "Section",
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=23,
        textColor=NAVY,
        spaceAfter=10,
        keepWithNext=True,
    ),
    "h2": ParagraphStyle(
        "Subsection",
        fontName="Helvetica-Bold",
        fontSize=12.5,
        leading=15,
        textColor=NAVY,
        spaceBefore=8,
        spaceAfter=5,
        keepWithNext=True,
    ),
    "small": ParagraphStyle(
        "Small", fontName="Helvetica", fontSize=8.3, leading=12, textColor=GRAY, spaceAfter=9
    ),
    "cell": ParagraphStyle("Cell", fontName="Helvetica", fontSize=8.8, leading=12.3, textColor=INK),
    "cellhead": ParagraphStyle(
        "CellHead", fontName="Helvetica-Bold", fontSize=8.7, leading=12.2, textColor=colors.white
    ),
    "code": ParagraphStyle(
        "Code",
        fontName="Courier",
        fontSize=8,
        leading=11,
        backColor=PALE,
        borderPadding=8,
        spaceAfter=9,
    ),
    "cover": ParagraphStyle(
        "Cover", fontName="Helvetica-Bold", fontSize=31, leading=37, textColor=NAVY, spaceAfter=16
    ),
    "subtitle": ParagraphStyle(
        "Subtitle", fontName="Helvetica", fontSize=16, leading=22, textColor=TEAL, spaceAfter=23
    ),
}


def link_target(target, source):
    if re.match(r"https?://", target):
        return target
    if target.startswith("#"):
        return BASE + "/blob/main/" + source + target
    absolute = (ROOT / source).parent / target
    relative = absolute.resolve().relative_to(ROOT.resolve())
    return BASE + "/blob/main/" + str(relative)


def inline(text, source):
    text = text.replace("—", "-").replace("–", "-").replace("‑", "-")
    tokens = []

    def link(m):
        try:
            url = link_target(m[2], source)
        except ValueError:
            url = BASE
        tokens.append(
            f'<link href="{html.escape(url, quote=True)}" color="#067887">'
            f"{html.escape(m[1])}</link>"
        )
        return f"ZZLINK{len(tokens) - 1}ZZ"

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
    text = html.escape(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier" size="9">\1</font>', text)
    for i, value in enumerate(tokens):
        text = text.replace(f"ZZLINK{i}ZZ", value)
    return text


class Doc(BaseDocTemplate):
    def __init__(self, path, title):
        super().__init__(
            str(path),
            pagesize=A4,
            leftMargin=M,
            rightMargin=M,
            topMargin=57,
            bottomMargin=47,
            title=title,
            author="Graduation project team",
            subject="Multi-Agent Refactoring for Python - planning edition 0.3",
        )
        self.titletext = title
        f = Frame(M, 47, BW, H - 104, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates(
            [
                PageTemplate(id="cover", frames=[f], onPage=self.coverpage),
                PageTemplate(id="body", frames=[f], onPage=self.bodypage),
            ]
        )

    def coverpage(self, c, d):
        c.setFillColor(NAVY)
        c.rect(0, H - 18, W, 18, fill=1, stroke=0)
        self.footer(c, d)

    def bodypage(self, c, d):
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(NAVY)
        c.drawString(M, H - 32, self.titletext)
        c.setFont("Helvetica", 8)
        c.setFillColor(GRAY)
        c.drawRightString(W - M, H - 32, "PLANNING EDITION 0.3")
        c.setStrokeColor(LINE)
        c.line(M, H - 40, W - M, H - 40)
        self.footer(c, d)

    def footer(self, c, d):
        c.setStrokeColor(LINE)
        c.line(M, 35, W - M, 35)
        c.setFont("Helvetica", 8)
        c.setFillColor(GRAY)
        c.drawString(M, 22, "Multi-Agent Refactoring for Python")
        c.drawRightString(W - M, 22, str(d.page))

    def afterFlowable(self, f):
        if hasattr(f, "bookmark_key"):
            self.canv.bookmarkPage(f.bookmark_key)
            self.canv.addOutlineEntry(f.getPlainText(), f.bookmark_key, 0, False)
            self.notify("TOCEntry", (0, f.getPlainText(), self.page, f.bookmark_key))


class Diagram(Flowable):
    def __init__(self, nodes):
        Flowable.__init__(self)
        self.nodes = nodes
        self.height = len(nodes) * 47 + 8

    def wrap(self, w, h):
        self.width = w
        return w, self.height

    def draw(self):
        c = self.canv
        bw = min(420, self.width - 25)
        x = (self.width - bw) / 2
        for i, t in enumerate(self.nodes):
            y = self.height - 38 - i * 47
            c.setFillColor(PALE)
            c.setStrokeColor(LINE)
            c.roundRect(x, y, bw, 32, 5, fill=1, stroke=1)
            p = Paragraph(t, styles["cell"])
            pw, ph = p.wrap(bw - 22, 30)
            p.drawOn(c, x + 11, y + (32 - ph) / 2)
            if i < len(self.nodes) - 1:
                mid = self.width / 2
                c.setStrokeColor(TEAL)
                c.line(mid, y - 2, mid, y - 13)
                c.line(mid, y - 13, mid - 3, y - 9)
                c.line(mid, y - 13, mid + 3, y - 9)


def cover(title, subtitle, description):
    return [
        Spacer(1, 62),
        Paragraph("GRADUATION PROJECT", styles["small"]),
        Spacer(1, 13),
        Paragraph(title, styles["cover"]),
        Paragraph(subtitle, styles["subtitle"]),
        Paragraph(description, styles["body"]),
        Spacer(1, 22),
        Paragraph(
            "<b>Team</b><br/>Abdelrahman Magdy<br/>Abdullah Tarek<br/>Abdelrahman "
            "Adel<br/>Shahd Abdelhay<br/>Dania El-Walily",
            styles["body"],
        ),
        Spacer(1, 17),
        Paragraph(
            "<b>Scope:</b> Python; fine-tuning an existing model; no paid-services budget.",
            styles["body"],
        ),
        Paragraph(
            "<b>Schedule:</b> an initial three-week delivery window from the agreed "
            "kickoff. Official dates remain to be confirmed.",
            styles["body"],
        ),
        Paragraph(
            "<b>Status:</b> foundation implemented; model training, final evaluation, "
            "and the complete product remain planned work.",
            styles["body"],
        ),
        Spacer(1, 15),
        Paragraph(
            f'<link href="{BASE}" color="#067887">'
            "Private GitHub repository and editable sources</link>",
            styles["body"],
        ),
        Paragraph(
            "Version 0.3. Read task status in GitHub Issues and the Project board.", styles["small"]
        ),
        NextPageTemplate("body"),
        PageBreak(),
    ]


def table_widths(header):
    n = len(header)
    if n == 4 and header[0] == "Member":
        return [BW * 0.19, BW * 0.27, BW * 0.27, BW * 0.27]
    if n == 4 and header[0] == "ID" and header[-1] == "Priority":
        return [BW * 0.1, BW * 0.23, BW * 0.57, BW * 0.1]
    if n == 4 and header[0] == "ID":
        return [BW * 0.12, BW * 0.30, BW * 0.18, BW * 0.40]
    if n == 4 and header[0] == "Risk":
        return [BW * 0.20, BW * 0.20, BW * 0.40, BW * 0.20]
    if n == 4:
        return [BW * 0.18, BW * 0.12, BW * 0.43, BW * 0.27]
    if n == 3 and header[0] == "Task":
        return [BW * 0.59, BW * 0.1, BW * 0.31]
    if n == 3:
        return [BW * 0.23, BW * 0.27, BW * 0.50]
    if n == 2:
        return [BW * 0.28, BW * 0.72]
    return [BW / n] * n


def markdown(path, index):
    lines = (ROOT / path).read_text().splitlines()
    story = []
    i = 0
    buf = []

    def flush():
        if buf:
            story.append(Paragraph(inline(" ".join(buf), path), styles["body"]))
            buf.clear()

    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("```"):
            flush()
            lang = line[3:]
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            if lang == "mermaid":
                nodes = (
                    [
                        "Developer or student",
                        "Local refactoring platform",
                        "Diff, explanation, and verification results",
                    ]
                    if "flowchart LR" in "\n".join(code)
                    else [
                        "User interface and API",
                        "Analysis, refactoring, and review-agent workflow",
                        "Local model provider and deterministic checks",
                        "Separate runner for trusted examples, when verified",
                        "Run record and user-visible results",
                    ]
                )
                story.append(Paragraph("Proposed design; not yet implemented.", styles["small"]))
                story.append(Diagram(nodes))
            else:
                story.append(Preformatted("\n".join(code), styles["code"], maxLineLength=95))
        elif line.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [x.strip() for x in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"[:\- ]+", x or "-") for x in cells):
                    rows.append(cells)
                i += 1
            i -= 1
            if rows:
                data = [
                    [
                        Paragraph(inline(c, path), styles["cellhead" if r == 0 else "cell"])
                        for c in row
                    ]
                    for r, row in enumerate(rows)
                ]
                t = Table(data, colWidths=table_widths(rows[0]), repeatRows=1, hAlign="LEFT")
                t.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LINEBELOW", (0, 0), (-1, 0), 0.5, NAVY),
                            ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE),
                            ("LEFTPADDING", (0, 0), (-1, -1), 7),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                            ("TOPPADDING", (0, 0), (-1, -1), 7),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                        ]
                    )
                )
                story.extend([t, Spacer(1, 11)])
        elif line.startswith("#"):
            flush()
            level = len(line) - len(line.lstrip("#"))
            text = line.lstrip("#").strip()
            if text == "Three-week overview by person":
                story.append(PageBreak())
            p = Paragraph(inline(text, path), styles["h1" if level == 1 else "h2"])
            if level == 1:
                p.bookmark_key = f"chapter-{index}"
            story.append(p)
            if level == 1:
                story.append(
                    Paragraph(
                        f'<link href="{BASE}/blob/main/{path}" color="#067887">'
                        f"Source: {html.escape(path)}</link>",
                        styles["small"],
                    )
                )
        elif not line:
            flush()
        elif re.match(r"^[-*] ", line):
            flush()
            text = re.sub(r"^[-*] (\[[ x]\] )?", "", line)
            p = Paragraph(inline(text, path), styles["body"], bulletText="-")
            story.append(p)
        else:
            buf.append(line)
        i += 1
    flush()
    return story


def build(filename, title, subtitle, description, sections):
    story = cover(title, subtitle, description)
    if len(sections) > 1:
        story.append(Paragraph("Contents", styles["h1"]))
        toc = TableOfContents()
        toc.levelStyles = [
            ParagraphStyle(
                "TOC",
                fontName="Helvetica",
                fontSize=9.5,
                leading=12,
                textColor=INK,
                leftIndent=0,
                firstLineIndent=0,
                spaceBefore=0,
                spaceAfter=0,
            )
        ]
        story.extend([toc, PageBreak()])
    for i, s in enumerate(sections):
        if i:
            story.append(PageBreak())
        story += markdown(s, i)
    Doc(OUT / filename, title).multiBuild(story)


technical = [
    "docs/proposal/project-proposal.md",
    "docs/requirements/srs.md",
    "docs/planning/roadmap.md",
    "docs/planning/team.md",
    "docs/architecture/system-design.md",
    "docs/architecture/decisions.md",
    "docs/development/first-day.md",
    "docs/development/setup.md",
    "CONTRIBUTING.md",
    "docs/development/testing.md",
    "docs/research/related-work.md",
    "docs/data-and-training/data-plan.md",
    "docs/data-and-training/training-plan.md",
    "docs/data-and-training/model-card.md",
    "docs/evaluation/protocol.md",
    "docs/planning/risks.md",
    "docs/planning/github-workspace.md",
    "docs/supervisor-reviews/README.md",
    "docs/supervisor-reviews/review-template.md",
    "docs/delivery/user-guide.md",
    "docs/delivery/checklist.md",
    "docs/agent-execution/README.md",
    "docs/references.md",
]
build(
    "01-project-documentation.pdf",
    "Project documentation",
    "Multi-Agent Refactoring for Python",
    "The specification and technical plan for the first release. Prepared for "
    "the project team and supervisor, with implemented behavior distinguished "
    "from planned work.",
    technical,
)
build(
    "02-team-delivery-plan.pdf",
    "Team delivery plan",
    "Workstream ownership from kickoff to delivery",
    "A practical allocation for five members: main responsibilities, outputs in "
    "each phase, handoffs, and the GitHub task list. Each task has one owner; a "
    "second-person approval is not required.",
    ["docs/planning/assignments.md"],
)

manifest = {
    "edition": "0.3",
    "baseline_code_commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip(),
    "source_sha256": {
        p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
        for p in technical + ["docs/planning/assignments.md"]
    },
    "files": [],
}
for name in ["01-project-documentation.pdf", "02-team-delivery-plan.pdf"]:
    p = OUT / name
    reader = PdfReader(p)
    manifest["files"].append(
        {
            "file": name,
            "pages": len(reader.pages),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
    )
    print(name, len(reader.pages), "pages", p.stat().st_size, "bytes")
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
