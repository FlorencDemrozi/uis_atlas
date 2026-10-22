// Co-authorship network of included researchers. The layout is computed once (no
// animation); departments are pulled towards their own sector so groups stay readable.
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY,
  type SimulationNodeDatum } from "d3-force";
import { useMemo, useRef, useState } from "preact/hooks";
import type { Atlas, Researcher } from "../data";
import { dept, orderedDepts } from "../departments";
import { useI18n } from "../i18n";
import { links } from "../router";
import { DeptLabel, TableView, useWidth } from "../components/common";

interface Node extends SimulationNodeDatum { id: string; r: Researcher; degree: number; joint: number; rad: number }
interface Edge { source: Node; target: Node; w: number }

function buildGraph(atlas: Atlas, includeIsolated: boolean) {
  const weights = new Map<string, number>();
  for (const p of Object.values(atlas.papers)) {
    const ids = p.uis_author_ids;
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const key = ids[i] < ids[j] ? `${ids[i]}|${ids[j]}` : `${ids[j]}|${ids[i]}`;
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
  return { nodes, edges, box, neighbours, depts };
}

export function NetworkView({ atlas }: { atlas: Atlas }) {
  const { t, num, deptName } = useI18n();
  const [isolated, setIsolated] = useState(false);
  const g = useMemo(() => buildGraph(atlas, isolated), [atlas, isolated]);
  const [hover, setHover] = useState<Node | null>(null);
  const [focusDept, setFocusDept] = useState<string | null>(null);
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; vx: number; vy: number; moved: boolean } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [wrapRef, wrapWidth] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<{ x: number; y: number } | null>(null);

  const vb = {
    w: g.box.w / view.k, h: g.box.h / view.k,
    x: g.box.x + view.x + (g.box.w - g.box.w / view.k) / 2, y: g.box.y + view.y + (g.box.h - g.box.h / view.k) / 2,
  };
  const zoom = (f: number) => setView((v) => ({ ...v, k: Math.min(6, Math.max(1, v.k * f)) }));

  const onDown = (e: PointerEvent) => {
    if ((e.target as Element).classList.contains("node")) return;
    drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false };
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
  };
  const onMove = (e: PointerEvent) => {
    const d = drag.current;
    const svg = svgRef.current;
    if (!d || !svg) return;
    const scale = vb.w / svg.clientWidth;
    d.moved = true;
    setView((v) => ({ ...v, x: d.vx - (e.clientX - d.x) * scale, y: d.vy - (e.clientY - d.y) * scale }));
  };
  const onUp = () => { drag.current = null; };

  const active = (n: Node) => {
    if (hover) return n.id === hover.id || g.neighbours.get(hover.id)?.has(n.id);
    if (focusDept) return n.r.department === focusDept;
    return true;
  };
  const edgeActive = (e: Edge) => {
    if (hover) return e.source.id === hover.id || e.target.id === hover.id;
    if (focusDept) return e.source.r.department === focusDept || e.target.r.department === focusDept;
    return true;
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

  // Label the most connected researchers, skipping any label that would overlap one already placed.
  const labels = useMemo(() => {
    if (hover) return [hover];
    const placed: { x0: number; x1: number; y0: number; y1: number }[] = [];
    const out: Node[] = [];
    for (const n of [...g.nodes].sort((a, b) => b.degree - a.degree)) {
      if (out.length >= 16) break;
      if (focusDept && n.r.department !== focusDept) continue;
      const w = n.r.name.length * fontSize * 0.56, y = (n.y ?? 0) - n.rad - 4;
      const box = { x0: (n.x ?? 0) - w / 2, x1: (n.x ?? 0) + w / 2, y0: y - fontSize, y1: y + 2 };
      if (placed.some((p) => box.x0 < p.x1 && box.x1 > p.x0 && box.y0 < p.y1 && box.y1 > p.y0)) continue;
      placed.push(box);
      out.push(n);
    }
    return out;
  }, [g, hover, focusDept, fontSize]);

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
            onClick={() => setFocusDept(focusDept === d.key ? null : d.key)}>
            <span class="dot" style={{ background: d.color }} aria-hidden="true" />{deptName(d.key, true)}
          </button>
        ))}
      </div>

      <div class="net-wrap" ref={wrapRef}>
        <svg ref={svgRef} viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`} role="img" aria-label={t("net.aria")}
          class={drag.current?.moved ? "dragging" : ""}
          onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp}>
          <g>
            {g.edges.map((e, i) => (
              <line key={i} class={`edge${hover && edgeActive(e) ? " hl" : ""}${edgeActive(e) ? "" : " dim"}`}
                x1={e.source.x} y1={e.source.y} x2={e.target.x} y2={e.target.y}
                stroke-width={(0.5 + Math.log2(1 + e.w) * 0.6) / Math.sqrt(view.k)}
                stroke-opacity={hover ? 0.9 : 0.45} />
            ))}
          </g>
          <g>
            {g.nodes.map((n) => (
              <a key={n.id} href={links.profile(n.id)} tabIndex={-1} aria-label={`${n.r.name}, ${deptName(n.r.department, true)}`}
                onPointerEnter={() => showTip(n)} onPointerLeave={hideTip}
                onFocus={() => showTip(n)} onBlur={hideTip}>
                <circle class={`node${active(n) ? "" : " dim"}`} cx={n.x} cy={n.y} r={n.rad}
                  fill={dept(n.r.department).color} stroke-width={2 / Math.sqrt(view.k)} />
              </a>
            ))}
          </g>
          <g>
            {labels.map((n) => (
              <text key={n.id} class="node-label" x={n.x} y={(n.y ?? 0) - n.rad - 4} text-anchor="middle"
                font-size={fontSize}>{n.r.name}</text>
            ))}
          </g>
        </svg>
        <div class="net-tools">
          <button type="button" aria-label={t("net.zoomIn")} onClick={() => zoom(1.4)}>+</button>
          <button type="button" aria-label={t("net.zoomOut")} onClick={() => zoom(1 / 1.4)}>−</button>
          <button type="button" aria-label={t("net.reset")} onClick={() => setView({ k: 1, x: 0, y: 0 })}>⟲</button>
        </div>
        {hover && tip && (
          <div class="tooltip" style={{ left: `${tip.x}px`, top: `${tip.y}px` }}>
            <strong>{hover.r.name}</strong>
            <DeptLabel name={hover.r.department} /><br />
            {t("net.tip", { p: num(hover.r.n_publications), c: num(hover.degree), j: num(hover.joint) })}
          </div>
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
              <tr key={n.id}><td><a href={links.profile(n.id)}>{n.r.name}</a></td>
                <td><DeptLabel name={n.r.department} /></td>
                <td class="n">{num(n.degree)}</td><td class="n">{num(n.joint)}</td></tr>
            ))}</tbody>
          </table>
        </TableView>
      </section>
    </>
  );
}
