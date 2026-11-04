// "International collaboration" on a profile: a world map of the countries of a
// researcher's external co-authors and their partner institutions. Downloaded with
// its map outline (world-atlas, Natural Earth 1:110m) only when a profile shows it.
import { geoNaturalEarth1, geoPath } from "d3-geo";
import { feature } from "topojson-client";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import type { GeometryCollection, Topology } from "topojson-specification";
import { useMemo, useState } from "preact/hooks";
import world from "world-atlas/countries-110m.json";
import { useI18n } from "../i18n";
import { countryName, scopusAffiliationUrl, usePartners } from "../partners";
import { BarList } from "./charts";
import { TableView, useWidth } from "./common";

type Country = Feature<Geometry, { name: string }>;

// Scopus country names -> the names in the map outline, where they differ.
const MAP_NAME: Record<string, string> = {
  "United States": "United States of America", "Bosnia and Herzegovina": "Bosnia and Herz.",
  "Czech Republic": "Czechia", "Dominican Republic": "Dominican Rep.", "North Macedonia": "Macedonia",
  "Russian Federation": "Russia", "Syrian Arab Republic": "Syria", "Viet Nam": "Vietnam",
  "Democratic Republic Congo": "Dem. Rep. Congo", "Central African Republic": "Central African Rep.",
  "South Sudan": "S. Sudan", "Equatorial Guinea": "Eq. Guinea", "Solomon Islands": "Solomon Is.",
  "Brunei Darussalam": "Brunei", "Cote d'Ivoire": "Côte d'Ivoire", "Western Sahara": "W. Sahara",
  "Eswatini": "eSwatini", "Swaziland": "eSwatini",
};
// Too small for the 1:110m outline: drawn as a dot at [longitude, latitude].
const DOT: Record<string, [number, number]> = {
  Singapore: [103.82, 1.35], "Hong Kong": [114.17, 22.32], Macao: [113.54, 22.2], Malta: [14.45, 35.9],
  Bahrain: [50.55, 26.07], Mauritius: [57.55, -20.3], Grenada: [-61.68, 12.12], "American Samoa": [-170.7, -14.3],
  "Faroe Islands": [-6.9, 62.0], Luxembourg: [6.13, 49.61], Monaco: [7.42, 43.74], Liechtenstein: [9.55, 47.16],
  Andorra: [1.52, 42.51], Maldives: [73.22, 3.2], Barbados: [-59.54, 13.19], Seychelles: [55.49, -4.68],
  Bermuda: [-64.75, 32.3], Reunion: [55.53, -21.11], Guadeloupe: [-61.55, 16.25], Martinique: [-61.02, 14.64],
  "Brunei Darussalam": [114.73, 4.54], "Saint Kitts and Nevis": [-62.78, 17.34], Tonga: [-175.2, -21.18],
  Samoa: [-171.75, -13.76], "Cape Verde": [-23.6, 15.1], Comoros: [43.33, -11.7],
};
const STAVANGER: [number, number] = [5.73, 58.97];
const ASPECT = 0.46;   // map height / width (Antarctica left out)
const SHOW = 10;       // countries and institutions listed before "show all"

const topo = world as unknown as Topology<{ countries: GeometryCollection<{ name: string }> }>;
const COUNTRIES = (feature(topo, topo.objects.countries) as FeatureCollection<Geometry, { name: string }>)
  .features.filter((f) => f.properties.name !== "Antarctica") as Country[];

/** Six sequential steps on a log scale (counts are very skewed: Norway, USA, UK...). */
function step(value: number, max: number): number {
  if (value <= 0 || max <= 0) return 0;
  return Math.min(6, Math.max(1, Math.ceil((Math.log1p(value) / Math.log1p(max)) * 6)));
}

function WorldMap({ countries, label }: { countries: [string, number][]; label: string }) {
  const { t, num, lang } = useI18n();
  const [wrapRef, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<{ x: number; y: number; name: string; n: number } | null>(null);
  const w = Math.max(320, width || 720), h = Math.round(w * ASPECT);
  const { path, project } = useMemo(() => {
    const projection = geoNaturalEarth1().fitExtent([[4, 4], [w - 4, h - 4]], { type: "FeatureCollection", features: COUNTRIES });
    return { path: geoPath(projection), project: (p: [number, number]) => projection(p) };
  }, [w, h]);
  const show = (e: PointerEvent, scopusName: string, n: number) => {
    const box = wrapRef.current?.getBoundingClientRect();
    if (box) setTip({ x: e.clientX - box.left, y: e.clientY - box.top, name: countryName(scopusName, lang), n });
  };
  const hide = () => setTip(null);
  // The country shapes are computed and drawn once per size and data, not on every
  // pointer move (the tooltip is the only thing that changes then).
  const shapes = useMemo(() => {
    const value = new Map(countries.map(([c, n]) => [MAP_NAME[c] ?? c, n]));
    const max = Math.max(1, ...countries.map(([, n]) => n));
    const nameOf = new Map(countries.map(([c]) => [MAP_NAME[c] ?? c, c]));
    const onMap = new Set(COUNTRIES.map((f) => f.properties.name));
    const dots = countries.filter(([c]) => !onMap.has(MAP_NAME[c] ?? c) && DOT[c]);
    return (<>
      <g>
        {COUNTRIES.map((f) => {
          const n = value.get(f.properties.name) ?? 0;
          const s = step(n, max);
          return (
            <path key={f.properties.name} d={path(f) ?? ""} class={`country${s ? ` seq-${s}` : ""}`}
              onPointerMove={n ? (e) => show(e, nameOf.get(f.properties.name)!, n) : undefined}
              onPointerLeave={hide} />
          );
        })}
      </g>
      <g>
        {dots.map(([c, n]) => {
          const p = project(DOT[c]);
          return p && <circle key={c} class={`country dot seq-${step(n, max)}`} cx={p[0]} cy={p[1]} r={4}
            onPointerMove={(e) => show(e, c, n)} onPointerLeave={hide} />;
        })}
      </g>
    </>);
  }, [countries, path, project, lang]);
  const uis = project(STAVANGER);

  return (
    <div class="world-map" ref={wrapRef}>
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" role="img" aria-label={label} onPointerLeave={hide}>
        {shapes}
        {uis && (
          <g class="home" aria-hidden="true">
            <circle cx={uis[0]} cy={uis[1]} r={4.5} />
            <text x={uis[0] + 8} y={uis[1] - 6}>UiS</text>
          </g>
        )}
      </svg>
      {tip && (
        <div class="tooltip" style={{ left: `${tip.x}px`, top: `${tip.y}px` }}>
          <strong>{tip.name}</strong>{t("map.papers", { n: num(tip.n) })}
        </div>
      )}
      <div class="scale" aria-hidden="true">
        <span style={{ marginRight: "6px" }}>{t("chart.fewer")}</span>
        {[1, 2, 3, 4, 5, 6].map((i) => <span key={i} class={`sw seq-${i}`} />)}
        <span style={{ marginLeft: "6px" }}>{t("chart.more")}</span>
        <span class="muted" style={{ marginLeft: "12px" }}>{t("map.scale")}</span>
      </div>
    </div>
  );
}

/** Profile section; renders nothing for researchers without external co-authors. */
export function PartnerSection({ id }: { id: string }) {
  const { t, num, lang } = useI18n();
  const { data, error } = usePartners();
  const [allCountries, setAllCountries] = useState(false);
  const [allInst, setAllInst] = useState(false);
  if (error) return null;
  if (!data) return <p class="loading small" role="status">{t("app.loading")}</p>;
  const p = data.byResearcher.get(id);
  if (!p) return null;
  const countries = p.countries;
  const institutions = p.institutions.map(([afid, n]) => ({ inst: data.institutions.get(afid)!, n }))
    .filter((x) => x.inst);
  const where = (c: string | null, city: string | null) =>
    [city, c && countryName(c, lang)].filter(Boolean).join(", ");

  return (
    <section class="section" aria-labelledby="h-partners">
      <h2 id="h-partners">{t("map.title")}</h2>
      <p class="sub">{t("map.sub", { i: num(institutions.length), c: num(countries.length) })}</p>
      <WorldMap countries={countries} label={t("map.aria", { c: num(countries.length) })} />
      <div class="partner-lists">
        <div>
          <h3>{t("map.countries")}</h3>
          <BarList ariaLabel={t("map.countries")} rows={(allCountries ? countries : countries.slice(0, SHOW)).map(([c, n]) => ({
            key: c, label: countryName(c, lang), value: n, color: "var(--seq-4)" }))} max={countries[0]?.[1]} />
          {countries.length > SHOW && (
            <button type="button" class="link-btn small" onClick={() => setAllCountries(!allCountries)}>
              {allCountries ? t("map.fewer") : t("map.all", { n: countries.length })}</button>
          )}
        </div>
        <div>
          <h3>{t("map.institutions")}</h3>
          <ul class="people partner-inst">
            {(allInst ? institutions : institutions.slice(0, SHOW)).map(({ inst, n }) => (
              <li key={inst.afid}>
                <span><a href={scopusAffiliationUrl(inst.afid)}>{inst.name}</a>
                  <span class="muted small"> · {where(inst.country, inst.city)}</span></span>
                <span class="muted num">{t("p.jointPapers", { n })}</span>
              </li>
            ))}
          </ul>
          {institutions.length > SHOW && (
            <button type="button" class="link-btn small" onClick={() => setAllInst(!allInst)}>
              {allInst ? t("map.fewer") : t("map.all", { n: institutions.length })}</button>
          )}
        </div>
      </div>
      <TableView summary={t("chart.tableOpen")}>
        <table class="data-table">
          <thead><tr><th>{t("map.country")}</th><th class="n">{t("chart.papers")}</th></tr></thead>
          <tbody>{countries.map(([c, n]) => (
            <tr key={c}><td>{countryName(c, lang)}</td><td class="n">{num(n)}</td></tr>
          ))}</tbody>
        </table>
      </TableView>
      <p class="note">{t("map.note")}</p>
    </section>
  );
}
