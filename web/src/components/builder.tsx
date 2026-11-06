import { useEffect, useState } from "preact/hooks";
import { useBuilderCalls } from "../builder";
import type { Call } from "../funding";
import { callTitle } from "../funding";
import { useI18n } from "../i18n";

/** "+ Project builder" on a funding call (list and call page); pressed when saved. */
export function CallBuilderButton({ call, compact = false }: { call: Call; compact?: boolean }) {
  const { t, lang } = useI18n();
  const { has, toggle } = useBuilderCalls();
  const on = has(call.id);
  const label = t(on ? "builder.callRemove" : "builder.callAdd");
  return (
    <button type="button" class={`shortlist-btn${on ? " on" : ""}${compact ? " compact" : ""}`} aria-pressed={on}
      title={label} aria-label={`${label}: ${callTitle(call, lang)}`}
      onClick={(e) => { e.stopPropagation(); toggle(call); }}>
      <span aria-hidden="true">{on ? "✓" : "+"}</span>
      {!compact && <span>{t(on ? "builder.callAdded" : "builder.callAddShort")}</span>}
    </button>
  );
}

/** A destructive button that asks for a second press instead of a browser dialog. */
export function ConfirmButton({ label, confirm, onConfirm }: { label: string; confirm: string; onConfirm: () => void }) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const id = setTimeout(() => setArmed(false), 4000);
    return () => clearTimeout(id);
  }, [armed]);
  return (
    <button type="button" class={`btn${armed ? " danger" : ""}`} aria-live="polite"
      onClick={() => { if (armed) { setArmed(false); onConfirm(); } else setArmed(true); }}
      onBlur={() => setArmed(false)}>
      {armed ? confirm : label}
    </button>
  );
}
