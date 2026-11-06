// Project builder (#/builder): the researchers on your shortlist and the funding calls
// you saved, side by side, plus "Find a team" from a project description. Calls appear
// only here and only once Funding is unlocked. docs/SPEC.md §5.6.
import type { Atlas } from "../data";
import { changedFacts, isClosed, type SavedCall } from "../builder-core";
import { useBuilderCalls } from "../builder";
import { callTitle, nextDeadline, pick, useFunding, type Call, type Funding } from "../funding";
import { useI18n } from "../i18n";
import { links } from "../router";
import { useShortlist } from "../shortlist";
import { DeptLabel } from "../components/common";
import { FundingGate, SourceBadge, StatusBadge, useFmt } from "../components/funding";
import { ConfirmButton } from "../components/builder";
import { TeamFinder } from "./Team";
import { PromptBuilder } from "../components/PromptBuilder";
import { IdeasPanel } from "../components/IdeasPanel";

export function BuilderView({ atlas }: { atlas: Atlas }) {
  const { t } = useI18n();
  return (
    <>
      <div class="page-head">
        <h1>{t("builder.title")}</h1>
        <p>{t("builder.lede")}</p>
      </div>
      <section class="section builder-selection" aria-labelledby="h-selection">
        <h2 id="h-selection">{t("builder.selection")}</h2>
        <p class="sub">{t("builder.selectionHelp")}</p>
        <div class="builder-grid">
          <ResearchersPanel atlas={atlas} />
          <CallsPanel />
        </div>
      </section>
      <PromptBuilder atlas={atlas} />
      <IdeasPanel />
      <TeamFinder atlas={atlas} />
    </>
  );
}

const toTeamFinder = () => {
  const h = document.getElementById("team-title");
  h?.scrollIntoView({ behavior: "smooth", block: "start" });
  document.getElementById("team-text")?.focus({ preventScroll: true });
};

function ResearchersPanel({ atlas }: { atlas: Atlas }) {
  const { t, num } = useI18n();
  const { ids, remove, set } = useShortlist();
  const people = ids.map((id) => atlas.byId.get(id)).filter((r) => r !== undefined);
  return (
    <div class="panel builder-panel" aria-labelledby="h-b-people">
      <h3 id="h-b-people">{t("builder.researchers")} <span class="muted num">{num(people.length)}</span></h3>
      {people.length === 0 ? (
        <p class="muted small">{t("builder.noResearchers")}{" "}
          <a href={links.search()}>{t("nav.search")}</a> · <button type="button" class="link-btn"
            onClick={toTeamFinder}>{t("team.title")}</button></p>
      ) : (
        <ul class="builder-list">
          {people.map((r) => (
            <li key={r.scopus_id}>
              <div class="builder-item">
                <a href={links.profile(r.scopus_id)}>{r.name}</a>
                <span class="small"><DeptLabel name={r.department} withFaculty /></span>
              </div>
              <button type="button" class="link-btn remove" aria-label={`${t("sl.remove")}: ${r.name}`}
                onClick={() => remove(r.scopus_id)}>×</button>
            </li>
          ))}
        </ul>
      )}
      {people.length > 0 && (
        <div class="panel-actions">
          <a href={links.shortlist(ids)}>{t("builder.compare")}</a>
          <ConfirmButton label={t("builder.clear")} confirm={t("builder.clearConfirm")} onConfirm={() => set([])} />
        </div>
      )}
    </div>
  );
}

function CallsPanel() {
  const { t, num } = useI18n();
  const { calls } = useBuilderCalls();
  const { state } = useFunding();
  const locked = state.status !== "ready";
  return (
    <div class="panel builder-panel" aria-labelledby="h-b-calls">
      <h3 id="h-b-calls">{t("builder.calls")} <span class="muted num">{num(calls.length)}</span></h3>
      {calls.length === 0 && (
        <p class="muted small">{t("builder.noCalls")} <a href={links.funding()}>{t("nav.funding")}</a></p>
      )}
      {calls.length > 0 && locked && state.status !== "missing" && (
        <p class="small">{t("builder.locked", { n: num(calls.length) })}</p>
      )}
      <FundingGate compact>
        {(data) => calls.length > 0 && <CallList data={data} calls={calls} />}
      </FundingGate>
    </div>
  );
}

function CallList({ data, calls }: { data: Funding; calls: SavedCall[] }) {
  const { t } = useI18n();
  const { clear } = useBuilderCalls();
  const today = new Date().toISOString().slice(0, 10);
  const closed = calls.filter((s) => { const c = data.byId.get(s.id); return c && isClosed(c.fields, today); }).length;
  return (
    <>
      {closed > 0 && <p class="warn small" role="note">{t("builder.someClosed", { n: closed })}</p>}
      <ul class="builder-list calls">
        {calls.map((s) => <CallItem key={s.id} saved={s} call={data.byId.get(s.id)} today={today} />)}
      </ul>
      <div class="panel-actions">
        <a href={links.funding()}>{t("builder.moreCalls")}</a>
        <ConfirmButton label={t("builder.clear")} confirm={t("builder.clearConfirm")} onConfirm={clear} />
      </div>
    </>
  );
}

function CallItem({ saved, call, today }: { saved: SavedCall; call: Call | undefined; today: string }) {
  const { t, lang } = useI18n();
  const fmt = useFmt();
  const { remove, refresh } = useBuilderCalls();
  const removeBtn = (name: string) => (
    <button type="button" class="link-btn remove" aria-label={`${t("builder.callRemove")}: ${name}`}
      onClick={() => remove(saved.id)}>×</button>
  );
  if (!call) {
    return (
      <li>
        <div class="builder-item"><span class="muted">{t("builder.gone", { id: saved.id })}</span></div>
        {removeBtn(saved.id)}
      </li>
    );
  }
  const f = call.fields;
  const title = callTitle(call, lang);
  const d = nextDeadline(call, today) ?? f.deadline.v;
  const body = pick<string>((call.source === "eu" ? f.programme : f.funder).v, lang).value;
  const changed = changedFacts(saved, f);
  const closed = isClosed(f, today);
  return (
    <li class={closed ? "closed" : undefined}>
      <div class="builder-item">
        <a href={links.call(call.id)}>{title}</a>
        <span class="meta-line small">
          <StatusBadge status={closed ? "closed" : f.status.v} />
          <SourceBadge call={call} />
          {body && <span>{body}</span>}
          {f.scheme.v && <span>{pick<string>(f.scheme.v, lang).value}</span>}
          <span>{t("f.deadline")}: {d ? fmt.date(d, true) : f.rolling.v ? t("f.rolling") : t("f.noDeadline")}</span>
        </span>
        <span class="muted small">{t("builder.savedOn", { d: fmt.date(saved.saved.slice(0, 10)) })}</span>
        {changed.length > 0 && (
          <p class="warn small" role="note">
            {t("builder.changed", { what: changed.map((k) => t(`fld.${k}`).toLowerCase()).join(", ") })}{" "}
            <button type="button" class="link-btn" onClick={() => refresh(call)}>{t("builder.markChecked")}</button>
          </p>
        )}
      </div>
      {removeBtn(title)}
    </li>
  );
}
