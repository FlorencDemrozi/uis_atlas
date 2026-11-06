// "Build a team": describe a project, get UiS researchers who together cover its
// aspects. Everything runs in the browser (team.ts, team-core.ts); the description is
// never sent anywhere. docs/SPEC.md "Build a team".
import { useMemo, useState } from "preact/hooks";
import type { Atlas, Researcher } from "../data";
import { useI18n } from "../i18n";
import { links } from "../router";
import { inScope, isAll, useSelection } from "../selection";
import { useShortlist } from "../shortlist";
import { DeptLabel, Position, paperUrl } from "../components/common";
import { OrgFilter } from "../components/OrgFilter";
import { ShortlistButton } from "../components/results";
import { takeHandedText } from "../handover";
import { loadTeamIndex, matchTeam, relevanceFor, type TeamIndex, type TeamResult } from "../team";
import { splitAspectsWithContext, type Evidence } from "../team-core";

type Status =
  | { kind: "idle" }
  | { kind: "working"; percent: number | null }
  | { kind: "error"; error: string }
  | { kind: "done" };

/** context: listed item -> the sentence it was listed in (team-core applyContext). */
interface Run { index: TeamIndex; aspects: string[]; rel: Float64Array[]; whole: string; context: Map<string, string> }

const MIN_WORDS = 4;
const short = (s: string, n = 90) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);

export function TeamView({ atlas }: { atlas: Atlas }) {
  const { t, num } = useI18n();
  const { sel } = useSelection();
  const shortlist = useShortlist();
  const [text, setText] = useState(takeHandedText);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [run, setRun] = useState<Run | null>(null);
  const [extra, setExtra] = useState("");

  const words = text.trim().split(/\s+/).filter(Boolean).length;
  const compute = async (aspects: string[], whole: string, known?: TeamIndex, context?: Map<string, string>) => {
    setStatus({ kind: "working", percent: null });
    try {
      const index = known ?? await loadTeamIndex(atlas);
      const pairs = aspects.length ? null
        : splitAspectsWithContext(whole, index.settings.max_aspects, index.settings.max_item_words);
      const list = pairs ? pairs.map(([a]) => a) : aspects;
      const rel = await relevanceFor(index, list, (percent) => setStatus({ kind: "working", percent }));
      // The first aspect is the whole description (shown as "Whole description") until removed.
      setRun({ index, aspects: list, rel, whole: !aspects.length || list[0] === whole ? list[0] : "",
        context: pairs ? new Map(pairs.filter(([, c]) => c)) : context ?? new Map() });
      setStatus({ kind: "done" });
    } catch (e) {
      setStatus({ kind: "error", error: String(e) });
    }
  };
  const submit = (e: Event) => {
    e.preventDefault();
    if (words < MIN_WORDS || status.kind === "working") return;
    void compute([], text.trim().replace(/\s+/g, " "));
  };
  const setAspects = (aspects: string[]) =>
    run && aspects.length && void compute(aspects, run.whole, run.index, run.context);
  const addAspect = (e: Event) => {
    e.preventDefault();
    const x = extra.trim();
    if (!run || !x || run.aspects.some((a) => a.toLowerCase() === x.toLowerCase())) return;
    setExtra("");
    setAspects([...run.aspects, x]);
  };

  const eligible = useMemo(() => atlas.researchers.map((r) => inScope(sel, r.department)), [atlas, sel]);
  const result = useMemo(() => run
    ? matchTeam(run.index, run.aspects, run.aspects.map((a) => run.context.get(a) ?? ""), run.rel, eligible,
      atlas.researchers.map((r) => r.department)) : null,
  [run, eligible, atlas]);
  const label = (j: number) => (run && j === 0 && run.whole ? t("team.whole") : run?.aspects[j] ?? "");

  return (
    <>
      <section class="page-head" aria-labelledby="team-title">
        <h1 id="team-title">{t("team.title")} <span class="badge beta">{t("idea.beta")}</span></h1>
        <p>{t("team.lede")}</p>
      </section>

      <form class="team-form" onSubmit={submit}>
        <label class="field grow" for="team-text">{t("team.label")}</label>
        {/* Writing-assistant extensions send typed text to their servers: keep the description local. */}
        <textarea id="team-text" rows={7} value={text} placeholder={t("team.placeholder")} data-gramm="false"
          data-gramm_editor="false" data-enable-grammarly="false"
          onInput={(e) => setText((e.target as HTMLTextAreaElement).value)} />
        <p class="small muted">{t("team.privacy")}</p>
        <button type="submit" class="btn primary" disabled={words < MIN_WORDS || status.kind === "working"}>
          {t("team.find")}
        </button>
      </form>

      {status.kind === "working" && (
        <p class="loading" role="status">
          {status.percent != null && status.percent < 100 ? t("idea.loadingModel", { p: String(status.percent) }) : t("team.working")}
        </p>
      )}
      {status.kind === "error" && <p class="warn" role="alert">{t("team.error")} ({status.error})</p>}

      {run && result && (
        <div aria-live="polite">
          <section class="section" aria-labelledby="h-aspects">
            <h2 id="h-aspects">{t("team.aspects")}</h2>
            <p class="sub small muted">{t("team.aspectsHelp")}</p>
            <ul class="aspect-chips">
              {run.aspects.map((a, j) => (
                <li key={a} class={`aspect-chip${result.gaps.includes(j) ? " gap" : ""}`} title={a}>
                  <span class="aspect-n">{j + 1}</span> {short(label(j), 70)}
                  {run.aspects.length > 1 && (
                    <button type="button" aria-label={t("team.removeAspect", { a: label(j) })}
                      disabled={status.kind === "working"}
                      onClick={() => setAspects(run.aspects.filter((_, k) => k !== j))}>×</button>
                  )}
                </li>
              ))}
            </ul>
            <form class="aspect-add" onSubmit={addAspect}>
              <label class="visually-hidden" for="team-extra">{t("team.addLabel")}</label>
              <input id="team-extra" type="text" value={extra} placeholder={t("team.addPlaceholder")}
                data-gramm="false" data-enable-grammarly="false" maxLength={200}
                onInput={(e) => setExtra((e.target as HTMLInputElement).value)} />
              <button type="submit" class="btn" disabled={!extra.trim() || status.kind === "working"}>{t("team.add")}</button>
            </form>
          </section>

          <OrgFilter atlas={atlas} />

          <section class="section" aria-labelledby="h-team">
            <h2 id="h-team">{t("team.suggested")}</h2>
            <p class="warn small" role="note">{t("team.note", { y: String(run.index.fromYear) })}</p>
            {result.team.length === 0 ? <p class="muted">{t("team.noTeam")}</p> : (
              <>
                <ol class="team-list">
                  {result.team.map((m) => (
                    <MemberCard key={m.person} atlas={atlas} result={result} person={m.person} adds={m.adds}
                      team={result.team.map((x) => x.person)} label={label} paperIds={run.index.paperIds}
                      covers={run.index.settings.covers} />
                  ))}
                </ol>
                <p>
                  <button type="button" class="btn"
                    onClick={() => shortlist.set([...shortlist.ids, ...result.team.map((m) => atlas.researchers[m.person].scopus_id)])}>
                    {t("team.addAll")}
                  </button>{" "}
                  <a href={links.shortlist()}>{t("team.toShortlist")}</a>
                </p>
              </>
            )}
            {!isAll(sel) && <p class="small muted">{t("team.scoped")}</p>}
          </section>

          {result.gaps.length > 0 && (
            <section class="section" aria-labelledby="h-gaps">
              <h2 id="h-gaps">{t("team.gaps")}</h2>
              <p class="sub small muted">{t("team.gapsHelp")}</p>
              <ul>{result.gaps.map((j) => <li key={j}>{label(j)}</li>)}</ul>
            </section>
          )}

          <section class="section" aria-labelledby="h-per-aspect">
            <h2 id="h-per-aspect">{t("team.perAspect")}</h2>
            {run.aspects.map((_, j) => (
              <details key={j} class="aspect-block" open={j > 0 && j < 4}>
                <summary><span class="aspect-n">{j + 1}</span> {label(j)}
                  <span class="muted small"> · {t("team.people", { n: num(result.top[j].length) })}</span></summary>
                {result.top[j].length === 0 ? <p class="muted small">{t("team.nobody")}</p> : (
                  <ol class="aspect-people">
                    {result.top[j].map((r) => (
                      <li key={r}>
                        <PersonLine r={atlas.researchers[r]} />
                        <Cover score={result.score[j][r]} />
                        <Papers atlas={atlas} ev={result.evidence[j].get(r) ?? []} paperIds={run.index.paperIds} n={2} />
                      </li>
                    ))}
                  </ol>
                )}
              </details>
            ))}
          </section>
          <p class="small muted">{t("team.tool")}</p>
        </div>
      )}
    </>
  );
}

function PersonLine({ r }: { r: Researcher }) {
  return (
    <div class="result-title">
      <h3><a href={links.profile(r.scopus_id)}>{r.name}</a></h3>
      <ShortlistButton r={r} compact />
      <span class="meta-line"><Position r={r} /><DeptLabel name={r.department} withFaculty /></span>
    </div>
  );
}

function Cover({ score }: { score: number }) {
  const { t } = useI18n();
  const pct = Math.round(score * 100);
  return (
    <span class="affinity" title={t("team.coverHelp")}>
      <span class="track" aria-hidden="true"><span class="fill" style={{ display: "block", width: `${pct}%` }} /></span>
      {t("team.cover", { n: pct })}
    </span>
  );
}

function Papers({ atlas, ev, paperIds, n }: { atlas: Atlas; ev: Evidence; paperIds: string[]; n: number }) {
  const papers = ev.slice(0, n).map(([, row]) => atlas.papers[paperIds[row]]).filter(Boolean);
  if (!papers.length) return null;
  return (
    <ul class="team-papers">
      {papers.map((p) => {
        const url = paperUrl(p);
        return (
          <li key={p.eid}>{url ? <a href={url}>{p.title}</a> : p.title}
            <span class="muted"> — {p.year}{p.venue ? `, ${p.venue}` : ""}</span></li>
        );
      })}
    </ul>
  );
}

function MemberCard({ atlas, result, person, adds, team, label, paperIds, covers }: {
  atlas: Atlas; result: TeamResult; person: number; adds: [number, number][]; team: number[];
  label: (j: number) => string; paperIds: string[]; covers: number;
}) {
  const { t } = useI18n();
  const r = atlas.researchers[person];
  const brings = adds.slice(0, 4);
  const withTeam = team.filter((x) => x !== person && atlas.researchers[x] &&
    r.paper_ids.some((e) => atlas.papers[e]?.uis_author_ids.includes(atlas.researchers[x].scopus_id)));
  const main = brings[0]?.[0];
  return (
    <li class="team-member">
      <PersonLine r={r} />
      <p class="team-brings">
        <span class="muted">{t("team.brings")} </span>
        {brings.map(([j], k) => {
          const strong = result.score[j][person] >= covers;
          return (
            <span key={j}>{k > 0 && ", "}
              <span class={strong ? "" : "muted"} title={short(result.aspects[j], 300)}>
                {short(label(j), 60)}{strong ? "" : ` ${t("team.partly")}`}
              </span>
            </span>
          );
        })}
      </p>
      {withTeam.length > 0 && (
        <p class="small muted">{t("team.withTeam")} {withTeam.map((x) => atlas.researchers[x].name).join(", ")}</p>
      )}
      {main !== undefined && <Papers atlas={atlas} ev={result.evidence[main].get(person) ?? []} paperIds={paperIds} n={2} />}
    </li>
  );
}
