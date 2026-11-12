import { useEffect, useRef } from 'react';

export interface Hotkey {
  /**
   * Combination such as `mod+enter`, `mod+k`, `shift+?`.
   * `mod` maps to Ctrl on Windows/Linux and Cmd on macOS.
   */
  combo: string;
  handler: (event: KeyboardEvent) => void;
  /** Optional description used by the shortcuts dialog. */
  description?: string;
  /** Set to false to disable a hotkey without removing it from the registry. */
  enabled?: boolean;
}

interface ParsedCombo {
  key: string;
  mod: boolean;
  ctrl: boolean;
  meta: boolean;
  alt: boolean;
  shift: boolean;
}

function parseCombo(combo: string): ParsedCombo {
  const parts = combo
    .toLowerCase()
    .split('+')
    .map((part) => part.trim())
    .filter(Boolean);
  const key = parts.pop() ?? '';
  return {
    key,
    mod: parts.includes('mod'),
    ctrl: parts.includes('ctrl'),
    meta: parts.includes('meta'),
    alt: parts.includes('alt'),
    shift: parts.includes('shift'),
  };
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    tag === 'SELECT' ||
    target.isContentEditable
  );
}

/**
 * Registers global keyboard shortcuts.
 *
 * A single listener handles every shortcut, so the app never stacks many
 * window handlers. Shortcuts without a modifier are ignored while the user is
 * typing in a field.
 */
export function useHotkeys(hotkeys: Hotkey[], enabled = true): void {
  const registry = useRef(hotkeys);
  registry.current = hotkeys;

  useEffect(() => {
    if (!enabled) return undefined;

    const onKeyDown = (event: KeyboardEvent) => {
      const pressed = event.key.toLowerCase();
      const modPressed = event.ctrlKey || event.metaKey;

      for (const hotkey of registry.current) {
        if (hotkey.enabled === false) continue;
        const combo = parseCombo(hotkey.combo);
        if (combo.key !== pressed) continue;

        const modMatches = combo.mod ? modPressed : !modPressed;
        const ctrlMatches = combo.ctrl ? event.ctrlKey : !event.ctrlKey;
        const metaMatches = combo.meta ? event.metaKey : !event.metaKey;
        const altMatches = combo.alt ? event.altKey : !event.altKey;
        const shiftMatches = combo.shift ? event.shiftKey : !event.shiftKey;

        if (!modMatches || !ctrlMatches || !metaMatches || !altMatches || !shiftMatches) continue;

        const hasModifier = combo.mod || combo.ctrl || combo.meta || combo.alt;
        if (!hasModifier && isEditableTarget(event.target)) continue;

        event.preventDefault();
        hotkey.handler(event);
        return;
      }
    };

    window.addEventListener('keydown', onKeyDown, { capture: true });
    return () => window.removeEventListener('keydown', onKeyDown, { capture: true });
  }, [enabled]);
}
