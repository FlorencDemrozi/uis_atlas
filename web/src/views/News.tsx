// What's new: researchers and funding calls first seen in the last weekly runs
// (pipeline/build_changes.py). Opening the page marks them as seen (news.ts); items
// after the previous visit keep a "New" label until the page is left.
import { useEffect, useState } from "preact/hooks";
import type { Atlas } from "../data";
import { callTitle, nextDeadline, useFunding } from "../funding";
import { useI18n } from "../i18n";
import { callBatches, useNews, type Batch } from "../news";
import { links } from "../router";
import { DeptLabel, Position } from "../components/common";
import { FundingGate, SourceBadge, useFmt } from "../components/funding";

export function NewsView({ atlas }: { atlas: Atlas }) {
  const { t, lang } = useI18n();
  const { date } = useFmt();
  const { changes, seen, markSeen } = useNews();
  const { state } = useFunding();
  const [before] = useState(seen);   // the previous visit, kept while the page is open
  const calls = state.status === "ready" ? callBatches(state.data) : [];

  const people: Batch[] = (changes?.researchers ?? [])
    .map((b) => ({ date: b.date, ids: b.ids.filter((id) => atlas.byId.has(id)) }))
    .filter((b) => b.ids.length);
  useEffect(() => {
    const dates = [changes?.generated ?? "", ...calls.map((b) => b.date)];
    const latest = dates.reduce((m, d) => (d > m ? d : m), "");
    if (latest) markSeen(latest);
  }, [changes, calls.length]);

  const isNew = (d: string) => before !== null && d > before;
  const weekHead = (d: string) => (
    <h3 class="news-date">{t("news.update", { date: date(d) })}
      {isNew(d) && <> <span class="badge">{t("news.newLabel")}</span></>}</h3>
  );
  const weeks = changes ? Math.round(changes.days / 7) : 8;

  return (
    <>
      <div class="page-head">
        <h1>{t("news.title")}</h1>
        <p>{t("news.lede", { weeks })}</p>
      </div>

      <section aria-labelledby="h-news-r" class="news-section">
        <h2 id="h-news-r">{t("news.researchers")}</h2>
        <p class="note">{t("news.researchersNote")}</p>
        {!changes ? <p class="muted">{t("news.none")}</p>
          : !people.length ? <p class="muted">{t("news.noneSince", { date: date(changes.since), weeks })}</p>
          : people.map((b) => (
            <div key={b.date}>
              {weekHead(b.date)}
              <ul class="news-list">
                {b.ids.map((id) => {
                  const r = atlas.byId.get(id)!;
                  return (
                    <li key={id}>
                      <a href={links.profile(id)}>{r.name}</a>
                      <span class="muted small"> · <Position r={r} /> · <DeptLabel name={r.department} short={false} /></span>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
      </section>

      <section aria-labelledby="h-news-c" class="news-section">
        <h2 id="h-news-c">{t("news.calls")}</h2>
        <FundingGate compact>
          {(data) => {
            const batches = callBatches(data);
            if (!batches.length) return <p class="muted">{t("news.noCalls", { weeks })}</p>;
            return batches.map((b) => (
              <div key={b.date}>
                {weekHead(b.date)}
                <ul class="news-list">
                  {b.ids.map((id) => {
                    const c = data.byId.get(id)!;
                    const d = nextDeadline(c);
                    return (
                      <li key={id}>
                        <SourceBadge call={c} /> <a href={links.call(id)}>{callTitle(c, lang)}</a>
                        {d && <span class="muted small"> · {t("news.deadline", { date: date(d) })}</span>}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ));
          }}
        </FundingGate>
      </section>
    </>
  );
}
