import type { ComponentChildren } from "preact";
import { useLayoutEffect, useRef, useState } from "preact/hooks";
import { dept } from "../departments";
import { useI18n } from "../i18n";
import { STOPWORDS } from "../search";

export function DeptLabel({ name, short = true }: { name: string; short?: boolean }) {
  const { deptName } = useI18n();
  return (
    <span class="dept">
      <span class="dot" style={{ background: dept(name).color }} aria-hidden="true" />
      {deptName(name, short)}
    </span>
  );
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
