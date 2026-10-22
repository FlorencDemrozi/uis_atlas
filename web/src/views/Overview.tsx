import { useMemo } from "preact/hooks";
import type { Atlas } from "../data";
import { dept, NOT_STATED, orderedDepts } from "../departments";
import { useI18n } from "../i18n";
import { links } from "../router";
import { BarList, ColumnChart, seqClass, type ColumnDatum } from "../components/charts";
import { DeptLabel, TableView } from "../components/common";

export function OverviewView({ atlas }: { atlas: Atlas }) {
  const { t, num, deptName } = useI18n();
  const { stats, meta } = atlas;
  const depts = orderedDepts(Object.keys(stats.departments));
  const realDepts = depts.filter((d) => d.key !== NOT_STATED);
  const totalCitations = atlas.researchers.length
    ? Object.values(atlas.papers).reduce((s, p) => s + (p.citations ?? 0), 0) : 0;

  const crossDeptPapers = useMemo(() => Object.values(atlas.papers).filter((p) =>
    new Set(p.uis_author_ids.map((id) => atlas.byId.get(id)?.department).filter((d) => d && d !== NOT_STATED)).size > 1).length,
  [atlas]);

  const lastYear = new Date(meta.generated).getFullYear();
  const years = useMemo(() => {
    const ys: string[] = [];
    for (let y = meta.period.first_year; y <= lastYear; y++) ys.push(String(y));
    return ys;
  }, [meta, lastYear]);
  const facultyPerYear: ColumnDatum[] = useMemo(() => {
    const c = new Map<string, number>();
    for (const p of Object.values(atlas.papers)) c.set(p.year, (c.get(p.year) ?? 0) + 1);
    return years.map((y) => ({ x: y, y: c.get(y) ?? 0, partial: Number(y) === lastYear }));
  }, [atlas, years, lastYear]);
  const deptYearMax = Math.max(1, ...depts.flatMap((d) => years.map((y) => stats.papers_per_year[d.key]?.[y] ?? 0)));

  const collab = useMemo(() => {
    const m = new Map<string, number>();
    for (const c of stats.department_collaboration) { m.set(`${c.a}|${c.b}`, c.papers); m.set(`${c.b}|${c.a}`, c.papers); }
    return m;
  }, [stats]);
  const collabMax = Math.max(1, ...stats.department_collaboration
    .filter((c) => c.a !== NOT_STATED && c.b !== NOT_STATED).map((c) => c.papers));

  return (
    <>
      <div class="page-head">
        <h1>{t("ov.title")}</h1>
        <p>{t("ov.lede", { from: String(meta.period.first_year), inclusion: meta.inclusion })}</p>
      </div>

      <div class="tiles">
        <div class="tile hero"><div class="label">{t("ov.researchers")}</div><div class="value">{num(meta.n_researchers)}</div>
          <div class="hint">{t("ov.researchersHint", { y: String(meta.period.recent_from) })}</div></div>
        <div class="tile"><div class="label">{t("ov.publications")}</div><div class="value">{num(meta.n_papers)}</div>
          <div class="hint">{t("ov.since", { y: String(meta.period.first_year) })}</div></div>
        <div class="tile"><div class="label">{t("ov.citations")}</div><div class="value">{num(totalCitations)}</div>
          <div class="hint">{t("ov.citationsHint")}</div></div>
        <div class="tile"><div class="label">{t("ov.departments")}</div><div class="value">{realDepts.length}</div>
          <div class="hint">{t("ov.crossDept", { n: crossDeptPapers })}</div></div>
      </div>

      <section class="section" aria-labelledby="h-depts">
        <h2 id="h-depts">{t("ov.byDept")}</h2>
        <p class="sub">{t("ov.byDeptSub")}</p>
        <div class="cols-2">
          <div class="panel">
            <h3 style={{ marginBottom: "12px" }}>{t("ov.researchers")}</h3>
            <BarList ariaLabel={t("ov.researchers")} rows={depts.map((d) => ({
              key: d.key, label: <DeptLabel name={d.key} />, value: stats.departments[d.key].researchers,
              color: d.color, href: `#/?dept=${encodeURIComponent(d.key)}` }))} />
          </div>
          <div class="panel">
            <h3 style={{ marginBottom: "12px" }}>{t("ov.publications")}</h3>
            <BarList ariaLabel={t("ov.publications")} rows={depts.map((d) => ({
              key: d.key, label: <DeptLabel name={d.key} />, value: stats.departments[d.key].papers, color: d.color }))} />
          </div>
        </div>
        <TableView summary={t("chart.table")}>
          <table class="data-table">
            <thead><tr><th>{t("filter.department")}</th><th class="n">{t("ov.researchers")}</th>
              <th class="n">{t("ov.publications")}</th><th class="n">{t("ov.citations")}</th></tr></thead>
            <tbody>{depts.map((d) => (
              <tr key={d.key}><td>{deptName(d.key)}</td><td class="n">{num(stats.departments[d.key].researchers)}</td>
                <td class="n">{num(stats.departments[d.key].papers)}</td><td class="n">{num(stats.departments[d.key].citations)}</td></tr>
            ))}</tbody>
          </table>
        </TableView>
      </section>

      <section class="section" aria-labelledby="h-years">
        <h2 id="h-years">{t("ov.perYear")}</h2>
        <p class="sub">{t("ov.perYearSub", { y: String(lastYear) })}</p>
        <div class="panel" style={{ marginBottom: "20px" }}>
          <h3 style={{ marginBottom: "8px" }}>{t("ov.wholeFaculty")}</h3>
          <ColumnChart data={facultyPerYear} color="var(--accent)" height={190} unit={t("chart.papers")}
            ariaLabel={t("ov.perYear")} />
        </div>
        <div class="panel">
          <div class="small-multiples">
            {depts.map((d) => (
              <div key={d.key}>
                <h3><DeptLabel name={d.key} /></h3>
                <ColumnChart color={d.color} yMax={deptYearMax} unit={t("chart.papers")} height={130}
                  ariaLabel={`${deptName(d.key)}: ${t("ov.perYear")}`}
                  data={years.map((y) => ({ x: y, y: stats.papers_per_year[d.key]?.[y] ?? 0, partial: Number(y) === lastYear }))} />
              </div>
            ))}
          </div>
        </div>
        <TableView summary={t("chart.table")}>
          <table class="data-table">
            <thead><tr><th>{t("filter.department")}</th>{years.map((y) => <th class="n" key={y}>{y}</th>)}</tr></thead>
            <tbody>{depts.map((d) => (
              <tr key={d.key}><td>{deptName(d.key, true)}</td>
                {years.map((y) => <td class="n" key={y}>{num(stats.papers_per_year[d.key]?.[y] ?? 0)}</td>)}</tr>
            ))}</tbody>
          </table>
        </TableView>
      </section>

      <section class="section" aria-labelledby="h-collab">
        <h2 id="h-collab">{t("ov.collab")}</h2>
        <p class="sub">{t("ov.collabSub")}</p>
        <div class="panel scroll-x">
          <table class="matrix">
            <caption class="visually-hidden">{t("ov.collab")}</caption>
            <thead>
              <tr><td />{realDepts.map((d) => <th key={d.key} scope="col">{deptName(d.key, true)}</th>)}</tr>
            </thead>
            <tbody>
              {realDepts.map((row) => (
                <tr key={row.key}>
                  <th scope="row"><DeptLabel name={row.key} /></th>
                  {realDepts.map((col) => {
                    if (row.key === col.key) return <td key={col.key} class="diag" aria-label="—">—</td>;
                    const v = collab.get(`${row.key}|${col.key}`) ?? 0;
                    return (
                      <td key={col.key} class={seqClass(v, collabMax)}
                        title={`${deptName(row.key, true)} × ${deptName(col.key, true)}: ${num(v)} ${t("chart.papers")}`}>
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

      <section class="section" aria-labelledby="h-themes">
        <h2 id="h-themes">{t("ov.themes")}</h2>
        <p class="sub">{t("ov.themesSub")}</p>
        <div class="panel">
          <div class="small-multiples">
            {depts.map((d) => {
              const themes = (stats.top_themes[d.key] ?? []).slice(0, 8);
              return (
                <div key={d.key}>
                  <h3><DeptLabel name={d.key} /></h3>
                  <BarList ariaLabel={`${deptName(d.key)}: ${t("ov.themes")}`} rows={themes.map(([k, n]) => ({
                    key: k, label: k, value: n, color: dept(d.key).color, href: links.search(k) }))} />
                </div>
              );
            })}
          </div>
        </div>
      </section>
    </>
  );
}
