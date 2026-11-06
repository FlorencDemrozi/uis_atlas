import { useMemo } from "preact/hooks";
import { CallBuilderButton } from "../components/builder";
import type { Atlas } from "../data";
import type { Researcher } from "../data";
import { EU_FAMILIES, FAMILIES, FUNDER_GROUPS, amountNok, callTitle, familyOf, isInstitutionLevel, isOpenField, nextDeadline,
  openFieldCallsFor, pick, type Call, type Eligibility, type Family, type Funding, type Match } from "../funding";
import { useI18n } from "../i18n";
import { links, replaceHash, type Route } from "../router";
import { CategoryBadge, EligibilityBadge, FundingGate, Freshness, SourceBadge, StatusBadge, useFmt } from "../components/funding";
import { IdeaSearch } from "../components/ideas";

const AMOUNTS = [1e6, 5e6, 10e6, 25e6];
/** Lower case without accents, so "tveteras" finds "Tveterås". */
const norm = (s: string) => s.toLowerCase().normalize("NFD").replace(/\p{M}/gu, "").replace(/ø/g, "o")
  .replace(/æ/g, "ae").replace(/\s+/g, " ").trim();
const ELIG_RANK = { no_restriction_found: 0, check: 1, partner_only: 2, likely_ineligible: 3 };
const SORTS = ["deadline", "amount", "published", "relevance"] as const;

/** The funder selection in the address (?fam=nfr,nordforsk): absent = every funder,
 * "none" = no funder. "eu" (older links) stands for every EU programme. */
function parseFamilies(value: string | null): Set<Family> | null {
  if (!value) return null;
  const known = new Set<string>(FAMILIES);
  return new Set(value.split(",").flatMap((x) => x === "eu" ? [...EU_FAMILIES] : known.has(x) ? [x as Family] : []));
}

export function FundingView({ atlas, route }: { atlas: Atlas; route: Route }) {
  return <FundingGate>{(data) => <FundingList atlas={atlas} data={data} route={route} />}</FundingGate>;
}

function FundingList({ atlas, data, route }: { atlas: Atlas; data: Funding; route: Route }) {
  const { t, lang, num } = useI18n();
  const fmt = useFmt();
  const p = route.params;
  const setMany = (values: Record<string, string>) => {
    const next = new URLSearchParams(p);
    for (const [key, value] of Object.entries(values)) {
      if (value) next.set(key, value); else next.delete(key);
    }
    replaceHash("/funding", next);
    dispatchEvent(new HashChangeEvent("hashchange"));
  };
  const set = (key: string, value: string) => setMany({ [key]: value });
  const status = p.get("st") ?? "current";
  const q = norm(p.get("q") ?? "");

  // The search box takes call titles or a researcher's name (any part, accents
  // ignored). A researcher – chosen (?who=) or the only name matching what was
  // typed – gets their matched calls plus every call open to all fields, with
  // their eligibility.
  // Name -> every researcher with it (two people can share a name).
  const byName = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const r of atlas.researchers) {
      const k = norm(r.name);
      const ids = m.get(k);
      if (ids) ids.push(r.scopus_id); else m.set(k, [r.scopus_id]);
    }
    return m;
  }, [atlas]);
  // Titles in both languages, and EU topic identifiers ("HORIZON-CL5-2027").
  const titleHit = (c: Call) => norm(callTitle(c, "nb")).includes(q) || norm(callTitle(c, "en")).includes(q)
    || (c.source === "eu" && norm(String(c.fields.call_id.v ?? "")).includes(q));
  const anyTitleHit = !!q && data.calls.some(titleHit);
  const peopleHits = q.length >= 3 && !anyTitleHit
    ? atlas.researchers.filter((r) => norm(r.name).includes(q)).slice(0, 12) : [];
  const chosen = p.get("who") ? atlas.byId.get(p.get("who")!) ?? null : null;
  const person = chosen ?? (peopleHits.length === 1 ? peopleHits[0] : null);
  // Nothing matched (no title, no single researcher): show the calls open to everyone.
  const openFallback = !!q && !anyTitleHit && !person;
  const personMatches = useMemo(() => new Map((person ? data.byResearcher.get(person.scopus_id) ?? [] : [])
    .map(({ call, match }) => [call.id, match])), [data, person]);
  const personOpen = useMemo(() => new Map((person ? openFieldCallsFor(data, person.scopus_id) : [])
    .map(({ call, eligibility }) => [call.id, eligibility])), [data, person]);
  const sort = (p.get("sort") ?? (person ? "relevance" : "deadline")) as typeof SORTS[number];
  // Switch to ?who= only when a name is picked from the list (not mid-typing) and is unique.
  const onSearch = (e: Event) => {
    const value = (e.target as HTMLInputElement).value;
    const picked = !(e instanceof InputEvent) || e.inputType === "insertReplacementText";
    const ids = picked ? byName.get(norm(value)) : undefined;
    setMany(ids?.length === 1 ? { who: ids[0], q: "" } : { q: value, who: "" });
  };
  const minAmount = Number(p.get("amt"));   // invalid ?amt= is no minimum

  const strong = (c: Call) => (data.matches[c.id] ?? []).filter((m) => m.category !== "low");
  const personRank = (c: Call) => personMatches.has(c.id) ? 10 + personMatches.get(c.id)!.score
    : personOpen.has(c.id) ? 5 - ELIG_RANK[personOpen.get(c.id)!.status] : 0;
  const optionsOf = (get: (c: Call) => string[]) =>
    [...new Set(data.calls.flatMap(get))].filter(Boolean).sort((a, b) => a.localeCompare(b, lang));
  const schemes = useMemo(() => optionsOf((c) => [pick<string>(c.fields.scheme.v, lang).value ?? ""]), [data, lang]);
  const themes = useMemo(() => optionsOf((c) => pick<string[]>(c.fields.themes.v, lang).value ?? []), [data, lang]);
  const applicants = useMemo(() => optionsOf((c) => pick<string[]>(c.fields.target_groups.v, lang).value ?? []), [data, lang]);

  const families = parseFamilies(p.get("fam"));
  // Every filter except the funders: the funder checkboxes count these calls.
  const passesOthers = (c: Call) => {
    const f = c.fields;
    const st = f.status.v as string;
    if (status === "current" ? st === "closed" : status !== "all" && st !== status) return false;
    if (q && anyTitleHit && !titleHit(c)) return false;
    if (openFallback && !isOpenField(c)) return false;
    if (p.get("sch") && pick<string>(f.scheme.v, lang).value !== p.get("sch")) return false;
    if (p.get("th") && !(pick<string[]>(f.themes.v, lang).value ?? []).includes(p.get("th")!)) return false;
    if (p.get("ap") && !(pick<string[]>(f.target_groups.v, lang).value ?? []).includes(p.get("ap")!)) return false;
    if (p.get("intl") && String(!!f.international.v) !== (p.get("intl") === "yes" ? "true" : "false")) return false;
    if (p.get("or") && f.orientation.v !== p.get("or")) return false;
    if (minAmount > 0 && !((amountNok(f.max_amount.v, f.currency.v) ?? 0) >= minAmount)) return false;
    if (p.get("before")) {
      const d = nextDeadline(c);
      if (!d || d.slice(0, 10) > p.get("before")!) return false;
    }
    if (p.get("mt") && !strong(c).length) return false;
    if (person && !personMatches.has(c.id) && !personOpen.has(c.id)) return false;
    return true;
  };
  const candidates = data.calls.filter(passesOthers);
  const shown = families ? candidates.filter((c) => families.has(familyOf(c))) : candidates;
  const far = "9999";
  shown.sort((a, b) => {
    if (sort === "amount") return (amountNok(b.fields.max_amount.v, b.fields.currency.v) ?? 0)
      - (amountNok(a.fields.max_amount.v, a.fields.currency.v) ?? 0);
    if (sort === "published") return (b.fields.published.v ?? "").localeCompare(a.fields.published.v ?? "");
    if (sort === "relevance" && person) return personRank(b) - personRank(a);
    if (sort === "relevance") return strong(b).length - strong(a).length
      || (data.matches[b.id]?.[0]?.score ?? 0) - (data.matches[a.id]?.[0]?.score ?? 0);
    return (nextDeadline(a) ?? (a.fields.rolling.v ? "9000" : far)).localeCompare(nextDeadline(b) ?? (b.fields.rolling.v ? "9000" : far));
  });

  const select = (key: string, label: string, opts: [string, string][], help?: string) => (
    <label class="field" title={help}>
      <span>{label}</span>
      <select value={p.get(key) ?? ""} onChange={(e) => set(key, (e.target as HTMLSelectElement).value)}>
        <option value="">{t("f.any")}</option>
        {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );

  return (
    <>
      <div class="page-head">
        <h1>{t("f.title")}</h1>
        <p>{t("f.lede", { years: String(new Date().getFullYear() - data.meta.papers_from_year + 1) })}</p>
      </div>

      <IdeaSearch data={data} />

      <div class="filters funding-filters" role="search">
        <FunderFilter calls={data.calls} candidates={candidates} selected={families}
          onChange={(next) => set("fam", next === null ? "" : next.size ? [...next].join(",") : "none")} />
        <label class="field grow">
          <span>{t("f.search")}</span>
          <input type="search" list="funding-people" value={p.get("q") ?? ""} placeholder={t("f.searchPlaceholder")}
            onInput={onSearch} />
          <datalist id="funding-people">
            {atlas.researchers.map((r) => <option key={r.scopus_id} value={r.name} />)}
          </datalist>
        </label>
        <label class="field">
          <span>{t("f.status")}</span>
          <select value={status} onChange={(e) => set("st", (e.target as HTMLSelectElement).value === "current" ? "" : (e.target as HTMLSelectElement).value)}>
            {["current", "open", "planned", "closed", "all"].map((s) => <option key={s} value={s}>{t(`f.status.${s}`)}</option>)}
          </select>
        </label>
        {select("sch", t("f.scheme"), schemes.map((s) => [s, s]))}
        {select("th", t("f.theme"), themes.map((s) => [s, s]))}
        {select("ap", t("f.applicant"), applicants.map((s) => [s, s]))}
        {select("or", t("f.orientation"), ["fundamental", "applied", "innovation", "support", "centre_infrastructure"]
          .map((o) => [o, t(`f.orient.${o}`)]))}
        {select("intl", t("f.international"), [["yes", t("f.intlOnly")], ["no", t("f.nationalOnly")]])}
        {select("amt", t("f.amount"), AMOUNTS.map((a) => [String(a), t("f.amountAtLeast", { n: fmt.money(a) })]),
          t("f.amountNote"))}
        <label class="field">
          <span>{t("f.deadlineBefore")}</span>
          <input type="date" value={p.get("before") ?? ""} onInput={(e) => set("before", (e.target as HTMLInputElement).value)} />
        </label>
        <label class="check">
          <input type="checkbox" checked={!!p.get("mt")} onChange={(e) => set("mt", (e.target as HTMLInputElement).checked ? "1" : "")} />
          {t("f.withMatches")}
        </label>
      </div>

      {person && (
        <div class="notice">
          <span>{t("f.forResearcher", { name: person.name })}</span>
          <a href={links.profile(person.scopus_id)}>{t("r.profile")}</a>
          <button type="button" class="btn" onClick={() => setMany({ who: "", q: "", sort: "" })}>{t("f.clearResearcher")}</button>
        </div>
      )}
      {!person && peopleHits.length > 1 && (
        <div class="notice">
          <span>{t("f.pickResearcher", { q: p.get("q") ?? "" })}</span>
          {peopleHits.map((r) => (
            <button type="button" class="chip-btn" key={r.scopus_id} onClick={() => setMany({ who: r.scopus_id, q: "" })}>
              {r.name}
            </button>
          ))}
        </div>
      )}
      {openFallback && (
        <p class="notice">{t(peopleHits.length ? "f.openFallbackPick" : "f.openFallback", { q: p.get("q") ?? "" })}</p>
      )}

      <div class="results-head">
        <p class="muted" role="status">{t("f.count", { n: num(shown.length) })}</p>
        <label class="field inline">
          <span>{t("f.sort")}</span>
          <select value={sort} onChange={(e) => set("sort", (e.target as HTMLSelectElement).value)}>
            {SORTS.map((s) => <option key={s} value={s}>{t(`f.sort.${s}`)}</option>)}
          </select>
        </label>
      </div>

      {shown.length === 0 ? (
        <p class="muted">{t("f.none")} <a href={links.funding()}>{t("f.reset")}</a></p>
      ) : (
        <ul class="call-list">
          {shown.map((c) => <CallCard key={c.id} atlas={atlas} data={data} call={c}
            person={person ? { r: person, match: personMatches.get(c.id), eligibility: personOpen.get(c.id) } : undefined} />)}
        </ul>
      )}
      <Freshness data={data} />
    </>
  );
}

/** Funders as checkboxes, grouped by region (Norway, Nordic, EU); a group's box
 * selects or clears all its funders. The number next to each is how many calls the
 * other filters leave for it. Only funders with calls in the data are listed. */
function FunderFilter({ calls, candidates, selected, onChange }: { calls: Call[]; candidates: Call[];
  selected: Set<Family> | null; onChange: (next: Set<Family> | null) => void }) {
  const { t, num } = useI18n();
  const present = useMemo(() => new Set(calls.map(familyOf)), [calls]);
  const count = new Map<Family, number>();
  for (const c of candidates) count.set(familyOf(c), (count.get(familyOf(c)) ?? 0) + 1);
  const groups = FUNDER_GROUPS.map((g) => ({ ...g, families: g.families.filter((x) => present.has(x)) }))
    .filter((g) => g.families.length);
  const every = groups.flatMap((g) => g.families);
  const isOn = (x: Family) => !selected || selected.has(x);
  const commit = (next: Set<Family>) => onChange(every.every((x) => next.has(x)) ? null : next);
  const current = () => new Set(selected ?? every);
  const toggle = (xs: readonly Family[], on: boolean) => {
    const next = current();
    xs.forEach((x) => on ? next.add(x) : next.delete(x));
    commit(next);
  };
  const allOn = every.every(isOn);
  return (
    <fieldset class="funder-filter">
      <legend>
        <span>{t("f.funders")}</span>
        <button type="button" class="link-btn" onClick={() => allOn ? onChange(new Set()) : onChange(null)}>
          {t(allOn ? "f.funders.clear" : "f.funders.all")}
        </button>
      </legend>
      <div class="funder-groups">
        {groups.map((g) => {
          const on = g.families.filter(isOn).length;
          const n = g.families.reduce((sum, x) => sum + (count.get(x) ?? 0), 0);
          return (
            <fieldset key={g.key} class="org-group">
              <legend>
                <label class="check strong">
                  <input type="checkbox" checked={on === g.families.length}
                    ref={(el) => { if (el) el.indeterminate = on > 0 && on < g.families.length; }}
                    onChange={() => toggle(g.families, on < g.families.length)} />
                  <span>{t(`f.region.${g.key}`)}</span>
                  <span class="muted num">{num(n)}</span>
                </label>
              </legend>
              {g.families.map((x) => (
                <label key={x} class="check">
                  <input type="checkbox" checked={isOn(x)} onChange={() => toggle([x], !isOn(x))} />
                  <span>{t(`f.family.${x}`)}</span>
                  <span class="muted num">{num(count.get(x) ?? 0)}</span>
                </label>
              ))}
            </fieldset>
          );
        })}
      </div>
    </fieldset>
  );
}

/** What one researcher has to do with a call: a topic match, or an open-field call with eligibility. */
function PersonFit({ person }: { person: { r: Researcher; match?: Match; eligibility?: Eligibility } }) {
  const { t } = useI18n();
  const atlasPaper = person.match?.papers[0];
  return (
    <div class="call-matches">
      {person.match ? (
        <>
          <p><CategoryBadge m={person.match} /> <span class="small">{t("f.matchFor", { name: person.r.name })}</span></p>
          {atlasPaper && atlasPaper.terms.length > 0 && <p class="small muted">{atlasPaper.terms.join(", ")}</p>}
          <EligibilityBadge e={person.match.eligibility} />
        </>
      ) : person.eligibility ? (
        <>
          <p class="small"><strong>{t("f.openFieldShort")}</strong></p>
          <EligibilityBadge e={person.eligibility} />
        </>
      ) : null}
    </div>
  );
}

function CallCard({ atlas, data, call, person }: { atlas: Atlas; data: Funding; call: Call;
  person?: { r: Researcher; match?: Match; eligibility?: Eligibility } }) {
  const { t, lang, num } = useI18n();
  const fmt = useFmt();
  const f = call.fields;
  const matches = data.matches[call.id] ?? [];
  const high = matches.filter((m) => m.category === "high").length;
  const medium = matches.filter((m) => m.category === "medium").length;
  const d = nextDeadline(call);
  const pre = f.preliminary_deadline.v && d === f.preliminary_deadline.v;
  const themes = pick<string[]>(f.themes.v, lang).value ?? [];
  const groups = pick<string[]>(f.target_groups.v, lang).value ?? [];
  const range = fmt.range(call), months = fmt.months(call);
  const status = f.status.v as string;
  return (
    <li class="call-card">
      <div class="call-main">
        <div class="title-row">
          <h2><a href={links.call(call.id)}>{callTitle(call, lang)}</a></h2>
          <CallBuilderButton call={call} />
        </div>
        <p class="meta-line">
          <StatusBadge status={status} />
          <SourceBadge call={call} />
          <span>{call.source === "eu" ? pick<string>(f.programme.v, lang).value : pick<string>(f.funder.v, lang).value}</span>
          {f.scheme.v && <span>{pick<string>(f.scheme.v, lang).value}</span>}
          {call.source === "eu" && <span class="muted small num">{f.call_id.v}</span>}
          {call.review.length > 0 && <span class="review-flag" title={call.review.join("; ")}>{t("f.review")}</span>}
        </p>
        <dl class="call-facts">
          <div><dt>{pre ? t("f.preDeadline") : t("f.deadline")}</dt>
            <dd>{d ? fmt.date(d, true) : f.rolling.v ? t("f.rolling") : (f.deadline.v ? fmt.date(f.deadline.v, true) : t("f.noDeadline"))}</dd></div>
          {range && <div><dt>{t("f.funding")}</dt><dd>{range}
            {f.total_budget.v && <span class="muted small"> · {t("f.budget", { n: fmt.money(f.total_budget.v, f.currency.v ?? "NOK") })}</span>}</dd></div>}
          {!range && f.total_budget.v && <div><dt>{t("f.funding")}</dt>
            <dd>{t("f.budget", { n: fmt.money(f.total_budget.v, f.currency.v ?? "NOK") })}</dd></div>}
          {f.expected_grants.v && <div><dt>{t("fld.expected_grants")}</dt><dd>{f.expected_grants.v}</dd></div>}
          {months && <div><dt>{t("f.duration")}</dt><dd>{months}</dd></div>}
          {groups.length > 0 && <div><dt>{t("f.applicant")}</dt><dd>{groups.join(", ")}
            {f.uis_can_apply.v === false && call.source === "rcn" && <span class="muted small"> · {t("f.uisPartner")}</span>}</dd></div>}
          {call.source === "eu" && f.norway_eligible.s !== "not_specified" && f.norway_eligible.v !== true && (
            <div><dt>{t("fld.norway_eligible")}</dt><dd>{t("f.norwayCheck")}</dd></div>)}
        </dl>
        {themes.length > 0 && <div class="tags">{themes.map((x) => <span class="tag static" key={x}>{x}</span>)}</div>}
      </div>
      {person && <PersonFit person={person} />}
      {!person && status !== "closed" && (
        <div class="call-matches">
          {high + medium > 0 ? (
            <>
              <p><strong>{t("f.matchesN", { n: num(high + medium) })}</strong>
                <span class="muted small"> · {t("f.matchesStrong", { h: num(high), m: num(medium) })}</span></p>
              <ul class="match-names">
                {matches.filter((m) => m.category !== "low").slice(0, 3).map((m) => {
                  const r = atlas.byId.get(m.id);
                  return r ? <li key={m.id}><a href={links.profile(m.id)}>{r.name}</a></li> : null;
                })}
              </ul>
            </>
          ) : <p class="muted small">{t(isInstitutionLevel(call) ? "f.institutionShort" : f.open_field?.v ? "f.openFieldShort" : "f.matchesNone")}</p>}
        </div>
      )}
    </li>
  );
}
