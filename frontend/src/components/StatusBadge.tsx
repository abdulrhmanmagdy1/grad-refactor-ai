import type { Evidence, IconName, Tone } from "../lib/labels";
import { Icon } from "./Icon";

export interface BadgeMeta {
  label: string;
  tone: Tone;
  icon: IconName;
  evidence?: Evidence;
}

/**
 * A status word with an icon. The word always carries the meaning; tone and icon only
 * reinforce it, so the badge works without color. data-tone and data-evidence are used
 * by the stylesheet and by tests that check missing evidence is never drawn as a pass.
 */
export function StatusBadge({
  meta,
  label,
  hiddenPrefix,
}: {
  meta: BadgeMeta;
  label?: string;
  hiddenPrefix?: string;
}) {
  return (
    <span className="badge" data-tone={meta.tone} data-evidence={meta.evidence ?? "present"}>
      <Icon name={meta.icon} />
      {hiddenPrefix ? <span className="visually-hidden">{hiddenPrefix} </span> : null}
      <span className="badge__label">{label ?? meta.label}</span>
    </span>
  );
}
