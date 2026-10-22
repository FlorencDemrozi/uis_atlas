// Small, dependency-free charts following the dataviz rules: thin marks, 4px rounded
// data ends, hairline grid, values reachable without hover (labels or table view).
import type { ComponentChildren } from "preact";
import { useState } from "preact/hooks";
import { useI18n } from "../i18n";
import { useWidth } from "./common";

// ------------------------------------------------------------------ bar list
export interface BarRow { key: string; label: ComponentChildren; value: number; color: string; href?: string }

export function BarList({ rows, max, ariaLabel }: { rows: BarRow[]; max?: number; ariaLabel: string }) {
  const { num } = useI18n();
  const top = max ?? Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul class="barlist" aria-label={ariaLabel}>
      {rows.map((r) => (
        <li key={r.key}>
          <span class="lbl">{r.href ? <a href={r.href}>{r.label}</a> : r.label}</span>
          <span class="track" aria-hidden="true">
            <span class="bar" style={{ display: "block", width: `${(r.value / top) * 100}%`, background: r.color }} />
          </span>
          <span class="val">{num(r.value)}</span>
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------------ columns over years
function niceMax(v: number) {
  if (v <= 5) return 5;
  const mag = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * mag >= v) return m * mag;
  return 10 * mag;
}

function colPath(x: number, y: number, w: number, h: number) {
  const r = Math.min(4, h, w / 2);
  if (h <= 0) return "";
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

export interface ColumnDatum { x: string; y: number; partial?: boolean }

export function ColumnChart({ data, color, height = 150, yMax, ariaLabel, unit }: {
  data: ColumnDatum[]; color: string; height?: number; yMax?: number; ariaLabel: string; unit: string;
}) {
  const { num, t } = useI18n();
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const m = { top: 18, right: 4, bottom: 22, left: 30 };
  const w = Math.max(0, width - m.left - m.right);
  const h = height - m.top - m.bottom;
  const max = niceMax(yMax ?? Math.max(1, ...data.map((d) => d.y)));
  const band = data.length ? w / data.length : 0;
  const colW = Math.min(24, band * 0.62);
  const ticks = [0, max / 2, max];
  // Thin out x labels when they would collide (~28px per short label).
  const labelEvery = Math.max(1, Math.ceil((data.length > 8 ? 28 : 40) / Math.max(band, 1)));
  const peak = data.reduce((best, d, i) => (d.y > data[best].y ? i : best), 0);

  return (
    <div class="chart" ref={ref}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={ariaLabel}>
          <g transform={`translate(${m.left},${m.top})`}>
            {ticks.map((v) => (
              <g key={v}>
                <line class={v === 0 ? "axis" : "gridline"} x1={0} x2={w} y1={h - (v / max) * h} y2={h - (v / max) * h} />
                <text x={-6} y={h - (v / max) * h + 4} text-anchor="end" class="num">{num(v)}</text>
              </g>
            ))}
            {data.map((d, i) => {
              const ch = (d.y / max) * h;
              const x = i * band + (band - colW) / 2;
              return (
                <g key={d.x}>
                  <path class={`col${hover !== null && hover !== i ? " dim" : ""}`} d={colPath(x, h - ch, colW, ch)}
                    fill={color} opacity={d.partial ? 0.45 : 1} />
                  {(i === peak || hover === i) && d.y > 0 && (
                    <text x={x + colW / 2} y={h - ch - 5} text-anchor="middle" class="label-strong num">{num(d.y)}</text>
                  )}
                  {(data.length - 1 - i) % labelEvery === 0 && (
                    <text x={x + colW / 2} y={h + 15} text-anchor="middle">
                      {data.length > 8 ? `’${d.x.slice(2)}` : d.x}
                    </text>
                  )}
                  <rect class="hit" x={i * band} y={0} width={band} height={h} tabIndex={0}
                    aria-label={`${d.x}: ${num(d.y)} ${unit}${d.partial ? ` (${t("chart.partial")})` : ""}`}
                    onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)}
                    onFocus={() => setHover(i)} onBlur={() => setHover(null)} />
                </g>
              );
            })}
          </g>
        </svg>
      )}
      {hover !== null && data[hover] && (
        <div class="tooltip" style={{ left: `${m.left + hover * band + band / 2}px`, top: `${m.top + h - (data[hover].y / max) * h}px` }}>
          <strong class="num">{num(data[hover].y)}</strong>
          {unit}, {data[hover].x}{data[hover].partial ? ` · ${t("chart.partial")}` : ""}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ matrix heatmap
export function seqClass(value: number, max: number) {
  if (value <= 0 || max <= 0) return "zero";
  return `seq-${Math.min(6, Math.max(1, Math.ceil((value / max) * 6)))}`;
}
