// Co-authorship network of included researchers. The layout is computed once;
// departments are pulled towards their own sector so groups stay readable.
// Click a researcher to focus on them (profile panel + their collaborators),
// click a collaborator to move on, double-click to open the full profile.
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY,
  type SimulationNodeDatum } from "d3-force";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import type { Atlas, Researcher } from "../data";
import { dept, orderedDepts } from "../departments";
import { useI18n } from "../i18n";
import { links, parseHash, type Route } from "../router";
import { ColumnChart } from "../components/charts";
import { DeptLabel, TableView, useWidth } from "../components/common";

interface Node extends SimulationNodeDatum { id: string; r: Researcher; degree: number; joint: number; rad: number }
interface Edge { source: Node; target: Node; w: number }
interface View { k: number; x: number; y: number }

const pairKey = (a: string, b: string) => (a < b ? `${a}|${b}` : `${b}|${a}`);

function buildGraph(atlas: Atlas, includeIsolated: boolean) {
  const weights = new Map<string, number>();
  for (const p of Object.values(atlas.papers)) {
    const ids = p.uis_author_ids;
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const key = pairKey(ids[i], ids[j]);
        weights.set(key, (weights.get(key) ?? 0) + 1);
      }
    }
  }
  const degree = new Map<string, number>();
  const joint = new Map<string, number>();
  for (const [key, w] of weights) {
    for (const id of key.split("|")) {
      degree.set(id, (degree.get(id) ?? 0) + 1);
      joint.set(id, (joint.get(id) ?? 0) + w);
    }
  }
  const nodes: Node[] = atlas.researchers
    .filter((r) => includeIsolated || degree.has(r.scopus_id))
    .map((r) => ({
      id: r.scopus_id, r, degree: degree.get(r.scopus_id) ?? 0, joint: joint.get(r.scopus_id) ?? 0,
      rad: 3 + Math.sqrt(r.n_publications) * 0.9,
    }));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const edges: Edge[] = [];
  for (const [key, w] of weights) {
    const [a, b] = key.split("|");
    if (byId.has(a) && byId.has(b)) edges.push({ source: byId.get(a)!, target: byId.get(b)!, w });
  }

  // Department anchors on a circle, in the fixed department order.
  const depts = orderedDepts(nodes.map((n) => n.r.department));
  const anchor = new Map(depts.map((d, i) => {
    const a = (i / depts.length) * 2 * Math.PI - Math.PI / 2;
    return [d.key, { x: Math.cos(a) * 260, y: Math.sin(a) * 260 }];
  }));
  forceSimulation<Node>(nodes)
    .force("link", forceLink<Node, Edge>(edges).distance(34).strength((e) => Math.min(1, 0.15 + e.w * 0.08)))
    .force("charge", forceManyBody<Node>().strength(-40))
    .force("collide", forceCollide<Node>().radius((n) => n.rad + 2))
    .force("x", forceX<Node>((n) => anchor.get(n.r.department)?.x ?? 0).strength(0.11))
    .force("y", forceY<Node>((n) => anchor.get(n.r.department)?.y ?? 0).strength(0.11))
    .stop()
    .tick(420);

  const xs = nodes.map((n) => n.x ?? 0), ys = nodes.map((n) => n.y ?? 0);
  const pad = 40;
  const box = {
    x: Math.min(...xs) - pad, y: Math.min(...ys) - pad,
    w: Math.max(...xs) - Math.min(...xs) + 2 * pad, h: Math.max(...ys) - Math.min(...ys) + 2 * pad,
  };
  const neighbours = new Map<string, Set<string>>();
  for (const e of edges) {
    (neighbours.get(e.source.id) ?? neighbours.set(e.source.id, new Set()).get(e.source.id)!).add(e.target.id);
    (neighbours.get(e.target.id) ?? neighbours.set(e.target.id, new Set()).get(e.target.id)!).add(e.source.id);
  }
  return { nodes, edges, box, neighbours, depts, byId, weight: (a: string, b: string) => weights.get(pairKey(a, b)) ?? 0 };
}

type Graph = ReturnType<typeof buildGraph>;

export function NetworkView({ atlas, route }: { atlas: Atlas; route: Route }) {
  const { t, num, deptName } = useI18n();
  // Read the live address: focus changes are written with replaceState, which the router does not see.
  const startParams = parseHash(location.hash).params;
  const initialFocus = startParams.get("focus");
  const [isolated, setIsolated] = useState(() => !!initialFocus && !hasCoauthors(atlas, initialFocus));
  const g = useMemo(() => buildGraph(atlas, isolated), [atlas, isolated]);
  const [trail, setTrail] = useState<string[]>(() =>
    initialFocus && atlas.byId.has(initialFocus) ? [initialFocus] : []);
  const focus = trail.length ? trail[trail.length - 1] : null;
  const [depth, setDepth] = useState<1 | 2>(startParams.get("depth") === "2" ? 2 : 1);
  const [hover, setHover] = useState<Node | null>(null);
  const [peek, setPeek] = useState<string | null>(null);
  const [focusDept, setFocusDept] = useState<string | null>(null);
  const [view, setView] = useState<View>({ k: 1, x: 0, y: 0 });
  const viewRef = useRef(view);
  viewRef.current = view;
  const anim = useRef(0);
  const drag = useRef<{ x: number; y: number; vx: number; vy: number; moved: boolean } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [wrapRef, wrapWidth] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<{ x: number; y: number } | null>(null);

  // Follow later navigation to #/network?focus=<id> (e.g. "Explore network" on a profile).
  const firstRoute = useRef(true);
  useEffect(() => {
    if (firstRoute.current) { firstRoute.current = false; return; }
    const id = route.params.get("focus");
    if (id && atlas.byId.has(id) && id !== focus) {
      if (!hasCoauthors(atlas, id)) setIsolated(true);
      setTrail([id]);
    }
  }, [route.params.toString()]);

  // Keep the address shareable.
  useEffect(() => {
    const p = new URLSearchParams();
    if (focus) p.set("focus", focus);
    if (focus && depth === 2) p.set("depth", "2");
    const hash = `#/network${p.toString() ? `?${p}` : ""}`;
    if (location.hash !== hash) history.replaceState(null, "", hash);
  }, [focus, depth]);

  // Distance from the focused researcher: 0 = focus, 1 = direct collaborator, 2 = two steps.
  const levels = useMemo(() => {
    const m = new Map<string, number>();
    if (!focus || !g.byId.has(focus)) return m;
    m.set(focus, 0);
    const first = g.neighbours.get(focus) ?? new Set<string>();
    first.forEach((n) => m.set(n, 1));
    if (depth === 2) first.forEach((n1) => g.neighbours.get(n1)?.forEach((n2) => { if (!m.has(n2)) m.set(n2, 2); }));
    return m;
  }, [g, focus, depth]);

  // Glide to the focused group (or back to the whole network).
  const flyTo = (target: View) => {
    cancelAnimationFrame(anim.current);
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) { setView(target); return; }
    const from = viewRef.current, t0 = performance.now(), dur = 450;
    const step = (now: number) => {
      const p = Math.min(1, (now - t0) / dur), e = 1 - (1 - p) ** 3;
      setView({ k: from.k + (target.k - from.k) * e, x: from.x + (target.x - from.x) * e, y: from.y + (target.y - from.y) * e });
      if (p < 1) anim.current = requestAnimationFrame(step);
    };
    anim.current = requestAnimationFrame(step);
  };
  useEffect(() => {
    if (!focus || !levels.size) { flyTo({ k: 1, x: 0, y: 0 }); return; }
    const pts = [...levels.keys()].map((id) => g.byId.get(id)!).filter(Boolean);
    const pad = 36;
    const x0 = Math.min(...pts.map((n) => (n.x ?? 0) - n.rad)) - pad, x1 = Math.max(...pts.map((n) => (n.x ?? 0) + n.rad)) + pad;
    const y0 = Math.min(...pts.map((n) => (n.y ?? 0) - n.rad)) - pad, y1 = Math.max(...pts.map((n) => (n.y ?? 0) + n.rad)) + pad;
    const k = Math.min(5, Math.max(1, Math.min(g.box.w / (x1 - x0), g.box.h / (y1 - y0))));
    flyTo({ k, x: (x0 + x1) / 2 - (g.box.x + g.box.w / 2), y: (y0 + y1) / 2 - (g.box.y + g.box.h / 2) });
  }, [focus, depth, g, levels]);

  useEffect(() => () => cancelAnimationFrame(anim.current), []);
  useEffect(() => {
    if (!focus) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setTrail([]); };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [focus]);

  const goTo = (id: string) => {
    setHover(null); setTip(null); setPeek(null);
    setTrail((tr) => {
      const at = tr.indexOf(id);
      return at >= 0 ? tr.slice(0, at + 1) : [...tr, id];
    });
  };
  const clearFocus = () => setTrail([]);

  const vb = {
    w: g.box.w / view.k, h: g.box.h / view.k,
    x: g.box.x + view.x + (g.box.w - g.box.w / view.k) / 2, y: g.box.y + view.y + (g.box.h - g.box.h / view.k) / 2,
  };
  const zoom = (f: number) => setView((v) => ({ ...v, k: Math.min(6, Math.max(1, v.k * f)) }));

  const onDown = (e: PointerEvent) => {
    if ((e.target as Element).closest(".node-g")) return;
    cancelAnimationFrame(anim.current);
    drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false };
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
  };
  const onMove = (e: PointerEvent) => {
    const d = drag.current;
    const svg = svgRef.current;
    if (!d || !svg) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y;
    if (!d.moved && Math.hypot(dx, dy) < 4) return;
    d.moved = true;
    const scale = vb.w / svg.clientWidth;
    setView((v) => ({ ...v, x: d.vx - dx * scale, y: d.vy - dy * scale }));
  };
  const onUp = () => {
    if (drag.current && !drag.current.moved && focus) clearFocus();   // click on the background
    drag.current = null;
  };

  const nodeClass = (n: Node) => {
    if (focus) {
      const l = levels.get(n.id);
      if (l === undefined) return " dim";
      return l === 0 ? " focus" : l === 2 ? " far" : "";
    }
    if (hover) return n.id === hover.id || g.neighbours.get(hover.id)?.has(n.id) ? "" : " dim";
    if (focusDept) return n.r.department === focusDept ? "" : " dim";
    return "";
  };
  const edgeClass = (e: Edge) => {
    if (focus) {
      const a = levels.get(e.source.id), b = levels.get(e.target.id);
      if (a === undefined || b === undefined) return " dim";
      if (a === 0 || b === 0) return " hl";
      return a === 2 && b === 2 ? " dim" : " soft";
    }
    if (hover) return e.source.id === hover.id || e.target.id === hover.id ? " hl" : " dim";
    if (focusDept) return e.source.r.department === focusDept || e.target.r.department === focusDept ? "" : " dim";
    return "";
  };

  const showTip = (n: Node) => {
    setHover(n);
    const svg = svgRef.current;
    const ctm = svg?.getScreenCTM();
    const wrap = svg?.parentElement?.getBoundingClientRect();
    if (!svg || !ctm || !wrap) return;
    const top = new DOMPoint(n.x ?? 0, (n.y ?? 0) - n.rad).matrixTransform(ctm);
    setTip({ x: top.x - wrap.left, y: top.y - wrap.top });
  };
  const hideTip = () => { setHover(null); setTip(null); };

  const mostConnected = [...g.nodes].sort((a, b) => b.degree - a.degree || b.joint - a.joint).slice(0, 25);
  // Keep labels ~12px on screen whatever the zoom level.
  const unitsPerPx = Math.max(vb.w / (wrapWidth || 1000), vb.h / (svgRef.current?.clientHeight || 640));
  const fontSize = 12 * unitsPerPx;

  // Labels: in focus mode the person and their direct collaborators, otherwise the most
  // connected researchers; any label that would overlap one already placed is skipped.
  const labels = useMemo(() => {
    let candidates: Node[];
    if (focus) {
      candidates = [...levels.entries()].filter(([, l]) => l <= 1).map(([id]) => g.byId.get(id)!)
        .sort((a, b) => (levels.get(a.id)! - levels.get(b.id)!) || g.weight(focus, b.id) - g.weight(focus, a.id));
    } else if (hover) {
      return [hover];
    } else {
      candidates = [...g.nodes].sort((a, b) => b.degree - a.degree)
        .filter((n) => !focusDept || n.r.department === focusDept);
    }
    const placed: { x0: number; x1: number; y0: number; y1: number }[] = [];
    const out: Node[] = [];
    for (const n of candidates) {
      if (out.length >= (focus ? 30 : 16)) break;
      const w = n.r.name.length * fontSize * 0.56, y = (n.y ?? 0) - n.rad / Math.sqrt(viewRef.current.k) - 4 * unitsPerPx;
      const box = { x0: (n.x ?? 0) - w / 2, x1: (n.x ?? 0) + w / 2, y0: y - fontSize, y1: y + 2 };
      if (placed.some((p) => box.x0 < p.x1 && box.x1 > p.x0 && box.y0 < p.y1 && box.y1 > p.y0)) continue;
      placed.push(box);
      out.push(n);
    }
    if (focus && hover && !out.includes(hover)) out.push(hover);
    return out;
  }, [g, hover, focus, levels, focusDept, fontSize, unitsPerPx]);

  // Joint-paper counts on the strongest links of the focused person.
  const edgeLabels = focus
    ? g.edges.filter((e) => e.source.id === focus || e.target.id === focus).sort((a, b) => b.w - a.w).slice(0, 8)
    : [];
  const focusNode = focus ? g.byId.get(focus) ?? null : null;
  const radius = (n: Node) => n.rad * (focus === n.id ? 1.25 : 1) / Math.sqrt(view.k);

  return (
    <>
      <div class="page-head">
        <h1>{t("net.title")}</h1>
        <p>{t("net.lede", { n: num(g.nodes.length), e: num(g.edges.length) })}</p>
      </div>

      <div class="filters" style={{ marginBottom: "4px" }}>
        <label class="field" style={{ flexDirection: "row", alignItems: "center", gap: "8px" }}>
          <input type="checkbox" checked={isolated} onChange={(e) => setIsolated((e.target as HTMLInputElement).checked)} />
          {t("net.isolated")}
        </label>
      </div>
      <div class="legend" role="group" aria-label={t("net.legend")}>
        {g.depts.map((d) => (
          <button key={d.key} class="chip-btn" aria-pressed={focusDept === null || focusDept === d.key}
            onClick={() => { clearFocus(); setFocusDept(focusDept === d.key ? null : d.key); }}>
            <span class="dot" style={{ background: d.color }} aria-hidden="true" />{deptName(d.key, true)}
          </button>
        ))}
      </div>

      {focus && (
        <div class="net-bar">
          <nav class="trail" aria-label={t("net.trail")}>
            <button type="button" class="link-btn" onClick={clearFocus}>{t("net.whole")}</button>
            {trail.map((id, i) => (
              <span key={id + i}>
                <span class="sep" aria-hidden="true">›</span>
                {i === trail.length - 1
                  ? <strong aria-current="true">{atlas.byId.get(id)?.name}</strong>
                  : <button type="button" class="link-btn" onClick={() => goTo(id)}>{atlas.byId.get(id)?.name}</button>}
              </span>
            ))}
          </nav>
          <div class="segmented" role="group" aria-label={t("net.depth")}>
            <button type="button" aria-pressed={depth === 1} onClick={() => setDepth(1)}>{t("net.depth1")}</button>
            <button type="button" aria-pressed={depth === 2} onClick={() => setDepth(2)}>{t("net.depth2")}</button>
          </div>
        </div>
      )}

      <div class={`net-layout${focusNode ? " has-focus" : ""}`}>
        <div class="net-wrap" ref={wrapRef}>
          <svg ref={svgRef} viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`} role="img"
            aria-label={focusNode ? t("net.focusAria", { name: focusNode.r.name }) : t("net.aria")}
            class={drag.current?.moved ? "dragging" : ""}
            onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={() => { drag.current = null; }}>
            <g>
              {g.edges.map((e, i) => (
                <line key={i} class={`edge${edgeClass(e)}`}
                  x1={e.source.x} y1={e.source.y} x2={e.target.x} y2={e.target.y}
                  stroke-width={(0.5 + Math.log2(1 + e.w) * 0.6) / Math.sqrt(view.k)} />
              ))}
            </g>
            <g>
              {g.nodes.map((n) => (
                <g key={n.id} class="node-g"
                  onClick={() => goTo(n.id)}
                  onDblClick={() => { location.hash = links.profile(n.id); }}
                  onPointerEnter={() => showTip(n)} onPointerLeave={hideTip}>
                  <circle class={`node${nodeClass(n)}${peek === n.id ? " peek" : ""}`} cx={n.x} cy={n.y}
                    r={radius(n)} fill={dept(n.r.department).color}
                    stroke-width={(focus === n.id || peek === n.id ? 3 : 2) / Math.sqrt(view.k)} />
                </g>
              ))}
            </g>
            <g>
              {edgeLabels.map((e) => {
                const [f, o] = e.source.id === focus ? [e.source, e.target] : [e.target, e.source];
                const mx = (f.x ?? 0) + ((o.x ?? 0) - (f.x ?? 0)) * 0.68, my = (f.y ?? 0) + ((o.y ?? 0) - (f.y ?? 0)) * 0.68;
                return <text key={`${e.source.id}-${e.target.id}`} class="edge-label" x={mx} y={my + fontSize * 0.35}
                  text-anchor="middle" font-size={fontSize * 0.85}>{e.w}</text>;
              })}
              {labels.map((n) => (
                <text key={n.id} class={`node-label${focus === n.id ? " focus" : ""}`} x={n.x}
                  y={(n.y ?? 0) - radius(n) - 4 * unitsPerPx} text-anchor="middle"
                  font-size={fontSize * (focus === n.id ? 1.15 : 1)}>{n.r.name}</text>
              ))}
            </g>
          </svg>
          <div class="net-tools">
            <button type="button" aria-label={t("net.zoomIn")} onClick={() => zoom(1.4)}>+</button>
            <button type="button" aria-label={t("net.zoomOut")} onClick={() => zoom(1 / 1.4)}>−</button>
            <button type="button" aria-label={t("net.reset")} onClick={() => { clearFocus(); flyTo({ k: 1, x: 0, y: 0 }); }}>⟲</button>
          </div>
          {hover && tip && (
            <div class="tooltip" style={{ left: `${tip.x}px`, top: `${tip.y}px` }}>
              <strong>{hover.r.name}</strong>
              <DeptLabel name={hover.r.department} /><br />
              {focus && hover.id !== focus && g.weight(focus, hover.id) > 0
                ? t("net.tipJoint", { n: num(g.weight(focus, hover.id)), name: focusNode?.r.name ?? "" })
                : t("net.tip", { p: num(hover.r.n_publications), c: num(hover.degree), j: num(hover.joint) })}
            </div>
          )}
        </div>
        {focusNode && (
          <ProfilePanel atlas={atlas} g={g} node={focusNode} onGo={goTo} onPeek={setPeek} onClose={clearFocus} />
        )}
      </div>
      <p class="note">{t("net.help")}</p>

      <section class="section" aria-labelledby="h-connected">
        <h2 id="h-connected">{t("net.mostConnected")}</h2>
        <p class="sub">{t("net.mostConnectedSub")}</p>
        <TableView summary={t("chart.tableOpen")}>
          <table class="data-table">
            <thead><tr><th>{t("net.name")}</th><th>{t("filter.department")}</th>
              <th class="n">{t("net.colleagues")}</th><th class="n">{t("net.joint")}</th></tr></thead>
            <tbody>{mostConnected.map((n) => (
              <tr key={n.id}>
                <td><button type="button" class="link-btn" onClick={() => { goTo(n.id); scrollTo({ top: 0, behavior: "smooth" }); }}>
                  {n.r.name}</button></td>
                <td><DeptLabel name={n.r.department} /></td>
                <td class="n">{num(n.degree)}</td><td class="n">{num(n.joint)}</td></tr>
            ))}</tbody>
          </table>
        </TableView>
      </section>
    </>
  );
}

function hasCoauthors(atlas: Atlas, id: string) {
  return (atlas.byId.get(id)?.top_coauthors.length ?? 0) > 0;
}

function ProfilePanel({ atlas, g, node, onGo, onPeek, onClose }: {
  atlas: Atlas; g: Graph; node: Node; onGo: (id: string) => void; onPeek: (id: string | null) => void; onClose: () => void;
}) {
  const { t, num } = useI18n();
  const r = node.r;
  const recent = atlas.recent.get(r.scopus_id) ?? 0;
  const lastYear = new Date(atlas.meta.generated).getFullYear();
  const years: string[] = [];
  for (let y = lastYear - 9; y <= lastYear; y++) years.push(String(y));
  const topics = (r.tags.length ? r.tags : (atlas.keywords.get(r.scopus_id) ?? []).map(([k]) => k)).slice(0, 6);
  const collaborators = [...(g.neighbours.get(node.id) ?? [])]
    .map((id) => ({ n: g.byId.get(id)!, w: g.weight(node.id, id) }))
    .sort((a, b) => b.w - a.w || a.n.r.name.localeCompare(b.n.r.name));
  const headingRef = useRef<HTMLHeadingElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (panelRef.current) panelRef.current.scrollTop = 0;
    headingRef.current?.focus({ preventScroll: true });
  }, [node.id]);

  return (
    <aside class="net-panel" ref={panelRef} aria-labelledby="net-panel-name">
      <button type="button" class="close" aria-label={t("net.close")} onClick={onClose}>×</button>
      <h2 id="net-panel-name" ref={headingRef} tabIndex={-1}>{r.name}</h2>
      <div class="meta-line"><DeptLabel name={r.department} short={false} /></div>
      {r.summary ? <p class="summary small">{r.summary}</p> : null}

      <dl class="mini-stats">
        <div><dt>{t("ov.publications")}</dt><dd>{num(r.n_publications)}</dd></div>
        <div><dt>{t("ov.since", { y: String(atlas.meta.period.recent_from) })}</dt><dd>{num(recent)}</dd></div>
        <div><dt>{t("ov.citations")}</dt><dd>{num(r.citations)}</dd></div>
        <div><dt>{t("net.colleagues")}</dt><dd>{num(node.degree)}</dd></div>
      </dl>
      <p class="muted small">{t("p.active", { a: String(r.first_year), b: String(r.last_year) })}</p>

      <h3>{t("net.lastYears")}</h3>
      <ColumnChart color={dept(r.department).color} unit={t("chart.papers")} height={110} ariaLabel={t("net.lastYears")}
        data={years.map((y) => ({ x: y, y: r.pubs_per_year[y] ?? 0, partial: Number(y) === lastYear }))} />

      {topics.length > 0 && (<>
        <h3>{t("p.topics")}</h3>
        <div class="tags">{topics.map((k) => <a class="tag" key={k} href={links.search(k)}>{k}</a>)}</div>
      </>)}

      <h3>{t("net.collaborators", { n: collaborators.length })}</h3>
      {collaborators.length ? (
        <ul class="collab-list">
          {collaborators.map(({ n, w }) => (
            <li key={n.id}>
              <button type="button" onClick={() => onGo(n.id)}
                onPointerEnter={() => onPeek(n.id)} onPointerLeave={() => onPeek(null)}
                onFocus={() => onPeek(n.id)} onBlur={() => onPeek(null)}>
                <span class="dept"><span class="dot" style={{ background: dept(n.r.department).color }} aria-hidden="true" />{n.r.name}</span>
                <span class="muted num">{t("p.jointPapers", { n: w })}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : <p class="muted small">{t("net.noCollaborators")}</p>}

      <div class="panel-actions">
        <a class="btn primary" href={links.profile(r.scopus_id)}>{t("net.openProfile")}</a>
        {r.links.scopus && <a class="btn" href={r.links.scopus}>Scopus</a>}
      </div>
    </aside>
  );
}
