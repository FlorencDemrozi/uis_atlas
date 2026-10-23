// Picks the faculties and departments every view is scoped to. One click on a
// faculty chip shows just that faculty; more clicks add (or remove) faculties.
// "Choose departments" opens a grouped checklist for finer selections.
import type { ComponentChildren } from "preact";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import type { Atlas } from "../data";
import { FACULTIES, type Faculty } from "../org";
import { useI18n } from "../i18n";
import { isAll, useSelection } from "../selection";

type State = "all" | "some" | "none";

/** children: further filters shown in the same box (e.g. minimum publications). */
export function OrgFilter({ atlas, children }: { atlas: Atlas; children?: ComponentChildren }) {
  const { t, num, deptName } = useI18n();
  const { sel, setSel } = useSelection();
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const all = isAll(sel);

  const counts = useMemo(() => {
    const c = new Map<string, number>();
    for (const r of atlas.researchers) {
      c.set(r.department, (c.get(r.department) ?? 0) + 1);
      c.set(r.faculty, (c.get(r.faculty) ?? 0) + 1);
    }
    return c;
  }, [atlas]);
  const present = (f: Faculty) => f.depts.filter((d) => counts.get(d.key));
  const faculties = FACULTIES.filter((f) => counts.get(f.key));

  const state = (f: Faculty): State => {
    if (all) return "none";
    const n = present(f).filter((d) => sel.has(d.key)).length;
    return n === 0 ? "none" : n === present(f).length ? "all" : "some";
  };
  const commit = (next: Set<string>) => {
    const complete = faculties.every((f) => present(f).every((d) => next.has(d.key)));
    setSel(complete ? new Set() : next);
  };
  const base = () => new Set(all ? [] : sel);
  const toggleFaculty = (f: Faculty) => {
    const next = base();
    if (state(f) === "all") f.depts.forEach((d) => next.delete(d.key));
    else f.depts.forEach((d) => next.add(d.key));
    commit(next);
  };
  const toggleDept = (key: string) => {
    const next = base();
    if (next.has(key)) next.delete(key); else next.add(key);
    commit(next);
  };

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setOpen(false); toggleRef.current?.focus(); }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [open]);

  const chosen = all ? [] : faculties.filter((f) => state(f) !== "none");
  const summary = all ? t("org.allUis")
    : chosen.map((f) => state(f) === "all" ? deptName(f.key, true)
      : `${deptName(f.key, true)} (${present(f).filter((d) => sel.has(d.key)).length}/${present(f).length})`).join(", ");

  return (
    <div class="org-filter" role="group" aria-labelledby="org-label">
      <div class="org-head">
        <span id="org-label" class="org-label">{t("org.label")}</span>
        <span class="org-summary" aria-live="polite">{summary}</span>
        {!all && <button type="button" class="link-btn" onClick={() => setSel(new Set())}>{t("org.clear")}</button>}
      </div>
      <div class="org-chips">
        <button type="button" class="chip-btn org-chip" aria-pressed={all} onClick={() => setSel(new Set())}>
          {t("org.allUis")} <span class="n">{num(atlas.researchers.length)}</span>
        </button>
        {faculties.map((f) => {
          const s = state(f);
          return (
            <button key={f.key} type="button" class={`chip-btn org-chip${s === "some" ? " partial" : ""}`}
              aria-pressed={s !== "none"} title={deptName(f.key)} onClick={() => toggleFaculty(f)}>
              <span class="dot" style={{ background: f.color }} aria-hidden="true" />
              {deptName(f.key, true)}
              <span class="n">{s === "some"
                ? t("org.partial", { a: present(f).filter((d) => sel.has(d.key)).length, b: present(f).length })
                : num(counts.get(f.key) ?? 0)}</span>
            </button>
          );
        })}
        <button type="button" ref={toggleRef} class="btn org-toggle" aria-expanded={open} aria-controls="org-panel"
          onClick={() => setOpen(!open)}>
          {t("org.chooseDepts")} <span aria-hidden="true">{open ? "▴" : "▾"}</span>
        </button>
      </div>
      {children && <div class="org-extra">{children}</div>}
      {open && (
        <div id="org-panel" class="org-panel" ref={panelRef}>
          <p class="muted small">{t("org.help")}</p>
          <div class="org-groups">
            {faculties.map((f) => {
              const s = state(f);
              return (
                <fieldset key={f.key} class="org-group">
                  <legend>
                    <label class="check strong">
                      <input type="checkbox" checked={s === "all"}
                        ref={(el) => { if (el) el.indeterminate = s === "some"; }}
                        onChange={() => toggleFaculty(f)} />
                      <span class="dot" style={{ background: f.color }} aria-hidden="true" />
                      {deptName(f.key, true)}
                    </label>
                  </legend>
                  {present(f).map((d) => (
                    <label key={d.key} class="check">
                      <input type="checkbox" checked={!all && sel.has(d.key)} onChange={() => toggleDept(d.key)} />
                      <span>{d.notStated ? t("org.notStated") : deptName(d.key, true)}</span>
                      <span class="muted num">{num(counts.get(d.key) ?? 0)}</span>
                    </label>
                  ))}
                </fieldset>
              );
            })}
          </div>
          <div class="org-actions">
            <button type="button" class="btn" onClick={() => setSel(new Set())}>{t("org.allUis")}</button>
            <button type="button" class="btn primary" onClick={() => { setOpen(false); toggleRef.current?.focus(); }}>
              {t("org.done")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
