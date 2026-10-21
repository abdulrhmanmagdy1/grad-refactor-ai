import { useMemo } from "react";
import { type CodeShape, codeShape } from "../lib/shape";

interface Scale {
  rows: number;
  columns: number;
}

const WIDTH = 96;
const MAX_HEIGHT = 108;
/** Statement text is drawn at most this many columns wide, so the indentation dominates. */
const TEXT_COLUMNS = 14;

function ShapeGraphic({ shape, scale, tone }: { shape: CodeShape; scale: Scale; tone: "original" | "proposed" }) {
  const rowHeight = Math.max(2, Math.min(6, MAX_HEIGHT / Math.max(1, scale.rows)));
  const barHeight = Math.max(1.5, rowHeight * 0.6);
  const columnWidth = WIDTH / Math.max(20, scale.columns);
  const height = Math.max(rowHeight * scale.rows, rowHeight);
  return (
    <svg
      className="shape__graphic"
      data-tone={tone}
      viewBox={`0 0 ${WIDTH} ${height}`}
      width={WIDTH}
      height={height}
      aria-hidden="true"
      focusable="false"
    >
      {shape.lines.map((line, index) =>
        line.width > line.indent ? (
          <rect
            key={index}
            x={line.indent * columnWidth}
            y={index * rowHeight + (rowHeight - barHeight) / 2}
            width={Math.max(columnWidth, Math.min(TEXT_COLUMNS, line.width - line.indent) * columnWidth)}
            height={barHeight}
            rx={Math.min(1.25, barHeight / 2)}
            className={line.level === null ? "shape__bar shape__bar--soft" : "shape__bar"}
          />
        ) : null,
      )}
    </svg>
  );
}

function levels(count: number): string {
  return count === 1 ? "1 level" : `${count} levels`;
}

function scaleFor(shapes: CodeShape[]): Scale {
  return {
    rows: Math.max(...shapes.map((shape) => shape.lines.length)),
    columns: Math.max(...shapes.flatMap((shape) => shape.lines.map((line) => line.indent))) + TEXT_COLUMNS,
  };
}

function Arrow() {
  return (
    <svg className="shape__arrow" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path
        d="M2.5 8h10M9 4.5 12.5 8 9 11.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * The outline of the original and the proposed code, line by line, drawn to the same
 * scale: each bar starts at the line's indentation. Guard clauses show up as a flatter
 * right-hand outline.
 */
export function ShapeComparison({ original, proposed }: { original: string; proposed: string }) {
  const before = useMemo(() => codeShape(original), [original]);
  const after = useMemo(() => codeShape(proposed), [proposed]);
  if (before.lines.length === 0 || after.lines.length === 0) return null;
  const scale = scaleFor([before, after]);
  return (
    <figure className="shape">
      <div className="shape__pair" aria-hidden="true">
        <div className="shape__side">
          <ShapeGraphic shape={before} scale={scale} tone="original" />
          <span className="shape__label">Original</span>
          <span className="shape__value">{levels(before.maxLevel)}</span>
        </div>
        <Arrow />
        <div className="shape__side">
          <ShapeGraphic shape={after} scale={scale} tone="proposed" />
          <span className="shape__label">Proposed</span>
          <span className="shape__value">{levels(after.maxLevel)}</span>
        </div>
      </div>
      <figcaption className="visually-hidden">
        Outline of the indentation: the deepest statement is indented {levels(before.maxLevel)} in the original and{" "}
        {levels(after.maxLevel)} in the proposal.
      </figcaption>
    </figure>
  );
}

const NESTED_EXAMPLE = [
  "def check(order):",
  "    if order:",
  "        if order.paid:",
  "            if order.items:",
  "                ship(order)",
  "                return True",
  "            else:",
  "                return False",
  "        else:",
  "            raise Unpaid()",
  "    return False",
].join("\n");

const FLAT_EXAMPLE = [
  "def check(order):",
  "    if not order:",
  "        return False",
  "    if not order.paid:",
  "        raise Unpaid()",
  "    if not order.items:",
  "        return False",
  "    ship(order)",
  "    return True",
].join("\n");

/** A decorative outline for the empty state: nested conditionals, then guard clauses. */
export function ShapeIllustration() {
  const before = useMemo(() => codeShape(NESTED_EXAMPLE), []);
  const after = useMemo(() => codeShape(FLAT_EXAMPLE), []);
  const scale = scaleFor([before, after]);
  return (
    <div className="shape shape--illustration" aria-hidden="true">
      <div className="shape__pair">
        <div className="shape__side">
          <ShapeGraphic shape={before} scale={scale} tone="original" />
          <span className="shape__label">Nested conditionals</span>
        </div>
        <Arrow />
        <div className="shape__side">
          <ShapeGraphic shape={after} scale={scale} tone="proposed" />
          <span className="shape__label">Guard clauses</span>
        </div>
      </div>
    </div>
  );
}
