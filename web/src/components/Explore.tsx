// Entry points for visitors who don't know what to type: one card per faculty
// (size and main themes) and the topics that are most frequent in recent papers.
import { useMemo } from "preact/hooks";
import type { Atlas } from "../data";
import { fac } from "../org";
import { useI18n } from "../i18n";
import { links } from "../router";
import { inScope, useSelection } from "../selection";
import { recentTopics, scopedStats } from "../stats";

export function Explore({ atlas }: { atlas: Atlas }) {
  const { t, num, deptName } = useI18n();
  const { sel, setSel } = useSelection();
  const stats = useMemo(() => scopedStats(atlas, atlas.researchers, "faculty"), [atlas]);
  const trending = useMemo(() => recentTopics(atlas,
    atlas.researchers.filter((r) => inScope(sel, r.department)), 14), [atlas, sel]);

  return (
    <section class="explore" aria-labelledby="explore-title">
      <h2 id="explore-title">{t("ex.title")}</h2>
      <ul class="fac-cards">
        {stats.order.map((key) => {
          const f = fac(key)!;
          const u = stats.units.get(key)!;
          const picked = f.depts.every((d) => sel.has(d.key));
          return (
            <li key={key} class={`fac-card${picked ? " on" : ""}`} style={{ "--fc": f.color }}>
              <button type="button" class="fac-card-main" aria-pressed={picked}
                onClick={() => setSel(new Set(f.depts.map((d) => d.key)))}>
                <span class="fac-card-name">{deptName(key, true)}</span>
                <span class="fac-card-n">{t("ex.counts", { r: num(u.researchers), p: num(u.papers) })}</span>
              </button>
              <div class="fac-card-themes">
                {(stats.themes.get(key) ?? []).slice(0, 4).map(([k]) => (
                  <a key={k} class="tag" href={`#/?q=${encodeURIComponent(k)}&org=${f.code}`}>{k}</a>
                ))}
              </div>
            </li>
          );
        })}
      </ul>
      {trending.length > 0 && (
        <div class="trending">
          <h3>{t("ex.trending", { y: String(atlas.meta.period.recent_from) })}</h3>
          <div class="tags">
            {trending.map(([k, n]) => <a key={k} class="tag" href={links.search(k)}>{k}<span class="n">{n}</span></a>)}
          </div>
        </div>
      )}
    </section>
  );
}
