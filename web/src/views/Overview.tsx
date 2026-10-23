import { useMemo, useState } from "preact/hooks";
import type { Atlas } from "../data";
import { dept, isNotStated, unit } from "../org";
import { useI18n } from "../i18n";
import { links } from "../router";
import { facultiesIn, inScope, isAll, naturalLevel, useSelection, type Level } from "../selection";
import { scopedStats } from "../stats";
import { BarList, ColumnChart, seqClass, type ColumnDatum } from "../components/charts";
import { DeptLabel, TableView } from "../components/common";
import { OrgFilter } from "../components/OrgFilter";

export function OverviewView({ atlas }: { atlas: Atlas }) {
  const { t, num, deptName } = useI18n();
  const { sel } = useSelection();
  const { meta } = atlas;
  const multi = facultiesIn(sel).length > 1;
  const [chosenLevel, setLevel] = useState<Level | null>(null);
  const level: Level = multi ? chosenLevel ?? naturalLevel(sel) : "department";
  const people = useMemo(() => atlas.researchers.filter((r) => inScope(sel, r.department)), [atlas, sel]);
  const s = useMemo(() => scopedStats(atlas, people, level), [atlas, people, level]);
  const units = s.order;
  const realUnits = units.filter((u) => !isNotStated(u));
  const single = facultiesIn(sel).length === 1 ? facultiesIn(sel)[0] : null;
  const color = (key: string) => level === "faculty" ? unit(key).color : single ? dept(key).ownColor : dept(key).color;
  const label = (key: string) => <DeptLabel name={key} own={!!single && level === "department"} />;
  const scopeLink = (key: string) => `#/?org=${unit(key).code}`;

  const lastYear = new Date(meta.generated).getFullYear();
  const years = useMemo(() => {
    const ys: string[] = [];
    for (let y = meta.period.first_year; y <= lastYear; y++) ys.push(String(y));
    return ys;
  }, [meta, lastYear]);
  const scopePerYear: ColumnDatum[] = years.map((y) => ({ x: y, y: s.perYearAll.get(y) ?? 0, partial: Number(y) === lastYear }));
  const unitYearMax = Math.max(1, ...units.flatMap((u) => years.map((y) => s.perYear.get(u)?.get(y) ?? 0)));
  const unitWord = t(level === "faculty" ? "ov.faculties" : "ov.departments");
  const title = isAll(sel) ? t("ov.titleAll") : single && level === "department" && single.depts.every((d) => sel.has(d.key))
    ? deptName(single.key) : t("ov.titleScope");

  return (
    <>
      <div class="page-head">
        <h1>{title}</h1>
        <p>{t("ov.lede", {
          from: String(meta.period.first_year),
          min: meta.inclusion.confirmed.min, since: String(meta.inclusion.confirmed.from),
          umin: meta.inclusion.unconfirmed.min, usince: String(meta.inclusion.unconfirmed.from),
        })}</p>
      </div>
      <OrgFilter atlas={atlas} />

      {multi && (
        <div class="filters" style={{ margin: "4px 0 8px" }}>
          <span class="field" style={{ flexDirection: "row", alignItems: "center", gap: "8px" }}>
            {t("ov.groupBy")}
            <span class="segmented" role="group" aria-label={t("ov.groupBy")}>
              <button type="button" aria-pressed={level === "faculty"} onClick={() => setLevel("faculty")}>{t("ov.faculties")}</button>
              <button type="button" aria-pressed={level === "department"} onClick={() => setLevel("department")}>{t("ov.departments")}</button>
            </span>
          </span>
        </div>
      )}

      <div class="tiles">
        <div class="tile hero"><div class="label">{t("ov.researchers")}</div><div class="value">{num(s.totals.researchers)}</div>
          <div class="hint">{t("ov.researchersHint", { y: String(meta.period.recent_from) })}</div></div>
        <div class="tile"><div class="label">{t("ov.publications")}</div><div class="value">{num(s.totals.papers)}</div>
          <div class="hint">{t("ov.since", { y: String(meta.period.first_year) })}</div></div>
        <div class="tile"><div class="label">{t("ov.citations")}</div><div class="value">{num(s.totals.citations)}</div>
          <div class="hint">{t("ov.citationsHint")}</div></div>
        <div class="tile"><div class="label">{unitWord}</div><div class="value">{realUnits.length}</div>
          <div class="hint">{t(level === "faculty" ? "ov.crossFac" : "ov.crossDept", { n: s.totals.crossUnit })}</div></div>
      </div>

      <section class="section" aria-labelledby="h-units">
        <h2 id="h-units">{unitWord}</h2>
        <p class="sub">{t("ov.byUnitSub")}</p>
        <div class="cols-2">
          <div class="panel">
            <h3 style={{ marginBottom: "12px" }}>{t("ov.researchers")}</h3>
            <BarList ariaLabel={t("ov.researchers")} rows={units.map((u) => ({
              key: u, label: label(u), value: s.units.get(u)!.researchers, color: color(u), href: scopeLink(u) }))} />
          </div>
          <div class="panel">
            <h3 style={{ marginBottom: "12px" }}>{t("ov.publications")}</h3>
            <BarList ariaLabel={t("ov.publications")} rows={units.map((u) => ({
              key: u, label: label(u), value: s.units.get(u)!.papers, color: color(u) }))} />
          </div>
        </div>
        <TableView summary={t("chart.table")}>
          <table class="data-table">
            <thead><tr><th>{level === "faculty" ? t("filter.faculty") : t("filter.department")}</th>
              <th class="n">{t("ov.researchers")}</th><th class="n">{t("ov.publications")}</th><th class="n">{t("ov.citations")}</th></tr></thead>
            <tbody>{units.map((u) => (
              <tr key={u}><td>{deptName(u)}</td><td class="n">{num(s.units.get(u)!.researchers)}</td>
                <td class="n">{num(s.units.get(u)!.papers)}</td><td class="n">{num(s.units.get(u)!.citations)}</td></tr>
            ))}</tbody>
          </table>
        </TableView>
      </section>

      <section class="section" aria-labelledby="h-years">
        <h2 id="h-years">{t("ov.perYear")}</h2>
        <p class="sub">{t("ov.perYearSub", { y: String(lastYear) })}</p>
        <div class="panel" style={{ marginBottom: "20px" }}>
          <h3 style={{ marginBottom: "8px" }}>{t("ov.wholeScope")}</h3>
          <ColumnChart data={scopePerYear} color="var(--accent)" height={190} unit={t("chart.papers")}
            ariaLabel={t("ov.perYear")} />
        </div>
        <div class="panel">
          <div class="small-multiples">
            {units.map((u) => (
              <div key={u}>
                <h3>{label(u)}</h3>
                <ColumnChart color={color(u)} yMax={unitYearMax} unit={t("chart.papers")} height={130}
                  ariaLabel={`${deptName(u)}: ${t("ov.perYear")}`}
                  data={years.map((y) => ({ x: y, y: s.perYear.get(u)?.get(y) ?? 0, partial: Number(y) === lastYear }))} />
              </div>
            ))}
          </div>
        </div>
        <TableView summary={t("chart.table")}>
          <table class="data-table">
            <thead><tr><th>{level === "faculty" ? t("filter.faculty") : t("filter.department")}</th>
              {years.map((y) => <th class="n" key={y}>{y}</th>)}</tr></thead>
            <tbody>{units.map((u) => (
              <tr key={u}><td>{deptName(u, true)}</td>
                {years.map((y) => <td class="n" key={y}>{num(s.perYear.get(u)?.get(y) ?? 0)}</td>)}</tr>
            ))}</tbody>
          </table>
        </TableView>
      </section>

      {realUnits.length > 1 && (
        <section class="section" aria-labelledby="h-collab">
          <h2 id="h-collab">{t(level === "faculty" ? "ov.collabFac" : "ov.collab")}</h2>
          <p class="sub">{t("ov.collabSub")}</p>
          <div class="panel scroll-x">
            <table class="matrix">
              <caption class="visually-hidden">{t(level === "faculty" ? "ov.collabFac" : "ov.collab")}</caption>
              <thead>
                <tr><td />{realUnits.map((u) => <th key={u} scope="col">{deptName(u, true)}</th>)}</tr>
              </thead>
              <tbody>
                {realUnits.map((row) => (
                  <tr key={row}>
                    <th scope="row">{label(row)}</th>
                    {realUnits.map((col) => {
                      if (row === col) return <td key={col} class="diag" aria-label="—">—</td>;
                      const v = s.collab.get(`${row}|${col}`) ?? 0;
                      return (
                        <td key={col} class={seqClass(v, s.collabMax)}
                          title={`${deptName(row, true)} × ${deptName(col, true)}: ${num(v)} ${t("chart.papers")}`}>
                          {num(v)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            <div class="scale" aria-hidden="true">
              <span style={{ marginRight: "6px" }}>{t("chart.fewer")}</span>
              {[1, 2, 3, 4, 5, 6].map((i) => <span key={i} class={`sw seq-${i}`} />)}
              <span style={{ marginLeft: "6px" }}>{t("chart.more")}</span>
            </div>
          </div>
        </section>
      )}

      <section class="section" aria-labelledby="h-themes">
        <h2 id="h-themes">{t("ov.themes")}</h2>
        <p class="sub">{t("ov.themesSub")}</p>
        <div class="panel">
          <div class="small-multiples">
            {units.map((u) => (
              <div key={u}>
                <h3>{label(u)}</h3>
                <BarList ariaLabel={`${deptName(u)}: ${t("ov.themes")}`} rows={(s.themes.get(u) ?? []).slice(0, 8).map(([k, n]) => ({
                  key: k, label: k, value: n, color: color(u), href: links.search(k) }))} />
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
