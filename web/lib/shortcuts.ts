/**
 * Window-wide keys: `/` jumps to the question box. Never while the visitor is
 * typing somewhere (a field, an editable region) or holding a modifier.
 * ↑ recalling the last question belongs to the box itself (composer.tsx).
 */
export interface KeyInfo {
  key: string;
  /** The event target's tag name ("INPUT", "TEXTAREA", "SELECT", …). */
  targetTag: string;
  /** The target is contenteditable. */
  editable: boolean;
  /** Ctrl, Meta or Alt is held. */
  modifier: boolean;
}

const TYPING = new Set(["INPUT", "TEXTAREA", "SELECT"]);

export function shortcutFor({ key, targetTag, editable, modifier }: KeyInfo): "focus-composer" | null {
  if (modifier || editable || TYPING.has(targetTag.toUpperCase())) return null;
  return key === "/" ? "focus-composer" : null;
}
