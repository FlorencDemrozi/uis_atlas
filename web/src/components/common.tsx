import type { ComponentChildren } from "preact";
import { useLayoutEffect, useRef, useState } from "preact/hooks";
import type { Researcher } from "../data";
import { dept, unit } from "../org";
import { useI18n } from "../i18n";
import { STOPWORDS } from "../search";

/** Department (or faculty) name with its faculty's colour dot; "own" colours a
 * department by its own slot (views scoped to one faculty). */
export function DeptLabel({ name, short = true, withFaculty = false, own = false }:
  { name: string; short?: boolean; withFaculty?: boolean; own?: boolean }) {
  const { deptName } = useI18n();
  const d = dept(name);
  const notStated = d.notStated && d.faculty;
  return (
    <span class="dept">
      <span class="dot" style={{ background: own ? d.ownColor : unit(name).color }} aria-hidden="true" />
      {notStated && withFaculty ? deptName(d.faculty, short)
        : withFaculty && d.faculty ? <>{deptName(name, short)}<span class="muted"> · {deptName(d.faculty, true)}</span></>
        : deptName(name, short)}
    </span>
  );
}

/** Job title from the UiS employee directory, in the current language. */
export function Position({ r }: { r: Researcher }) {
  const { lang } = useI18n();
  const p = r.position && (r.position[lang] ?? r.position.nb ?? r.position.en);
  return p ? <span class="position">{p}</span> : null;
}

/** Wraps matched query terms in <mark> without using innerHTML. */
export function Highlight({ text, terms }: { text: string; terms: string[] }) {
  const usable = terms.filter((t) => t.length > 1 && !STOPWORDS.has(t.toLowerCase()));
  if (!usable.length) return <>{text}</>;
  const esc = usable.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).sort((a, b) => b.length - a.length);
  const re = new RegExp(`(${esc.join("|")})`, "gi");
  return <>{text.split(re).map((part, i) => (i % 2 ? <mark key={i}>{part}</mark> : part))}</>;
}

export function TableView({ summary, children }: { summary: string; children: ComponentChildren }) {
  return (
    <details class="table-view">
      <summary>{summary}</summary>
      <div class="scroll-x">{children}</div>
    </details>
  );
}

export function useWidth<T extends HTMLElement>(): [{ current: T | null }, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth);
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

export function doiUrl(doi: string | null) {
  return doi ? `https://doi.org/${doi}` : null;
}
