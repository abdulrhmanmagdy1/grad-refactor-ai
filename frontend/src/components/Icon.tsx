import type { ReactNode } from "react";
import type { IconName } from "../lib/labels";

export type AnyIconName = IconName | "copy" | "download" | "trash" | "refresh" | "undo" | "info";

const SHAPES: Record<AnyIconName, ReactNode> = {
  check: <polyline points="3.5 8.5 6.5 11.5 12.5 4.5" />,
  cross: (
    <>
      <line x1="4.5" y1="4.5" x2="11.5" y2="11.5" />
      <line x1="11.5" y1="4.5" x2="4.5" y2="11.5" />
    </>
  ),
  dash: <line x1="4" y1="8" x2="12" y2="8" />,
  absent: <circle cx="8" cy="8" r="5" strokeDasharray="2 2.2" />,
  alert: (
    <>
      <path d="M8 2.5 14 13H2Z" strokeLinejoin="round" />
      <line x1="8" y1="6.5" x2="8" y2="9.2" />
      <line x1="8" y1="11.2" x2="8" y2="11.3" />
    </>
  ),
  question: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M6.3 6.4a1.8 1.8 0 1 1 2.6 1.6c-.6.3-.9.7-.9 1.3v.3" />
      <line x1="8" y1="11.4" x2="8" y2="11.5" />
    </>
  ),
  clock: (
    <>
      <circle cx="8" cy="8" r="6" />
      <polyline points="8 4.8 8 8 10.3 9.4" />
    </>
  ),
  spinner: <path d="M8 2.5a5.5 5.5 0 1 1-5.5 5.5" />,
  copy: (
    <>
      <rect x="5.5" y="5.5" width="8" height="8" rx="1.2" />
      <path d="M10.5 5.5V3.7c0-.7-.5-1.2-1.2-1.2H3.7c-.7 0-1.2.5-1.2 1.2v5.6c0 .7.5 1.2 1.2 1.2h1.8" />
    </>
  ),
  download: (
    <>
      <line x1="8" y1="2.5" x2="8" y2="10" />
      <polyline points="4.8 7 8 10.2 11.2 7" />
      <path d="M2.5 11v1.3c0 .7.5 1.2 1.2 1.2h8.6c.7 0 1.2-.5 1.2-1.2V11" />
    </>
  ),
  trash: (
    <>
      <line x1="2.8" y1="4.2" x2="13.2" y2="4.2" />
      <path d="M6.2 4.2V2.8h3.6v1.4M4.2 4.2l.7 9h6.2l.7-9" />
    </>
  ),
  refresh: (
    <>
      <path d="M13 8a5 5 0 1 1-1.5-3.6" />
      <polyline points="13 2.6 13 5.4 10.2 5.4" />
    </>
  ),
  undo: (
    <>
      <polyline points="5.5 3.5 2.8 6.2 5.5 8.9" />
      <path d="M2.8 6.2h6.7a3.6 3.6 0 0 1 0 7.2H6.5" />
    </>
  ),
  info: (
    <>
      <circle cx="8" cy="8" r="6" />
      <line x1="8" y1="7.2" x2="8" y2="11" />
      <line x1="8" y1="5" x2="8" y2="5.1" />
    </>
  ),
};

export function Icon({ name, className }: { name: AnyIconName; className?: string }) {
  return (
    <svg
      className={className ? `icon icon--${name} ${className}` : `icon icon--${name}`}
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      aria-hidden="true"
      focusable="false"
    >
      {SHAPES[name]}
    </svg>
  );
}
