import { useMemo } from "preact/hooks";
import type { Atlas } from "../data";
import { callTitle, nextDeadline, pick, type Call, type Funding } from "../funding";
import { useI18n } from "../i18n";
import { links, replaceHash, type Route } from "../router";
import { FundingGate, Freshness, StatusBadge, useFmt } from "../components/funding";

const AMOUNTS = [1e6, 5e6, 10e6, 25e6];
const SORTS = ["deadline", "amount", "published", "relevance"] as const;

export function FundingView({ atlas, route }: { atlas: Atlas; route: Route }) {
  return <FundingGate>{(data) => <FundingList atlas={atlas} data={data} route={route} />}</FundingGate>;
}

function FundingList({ atlas, data, route }: { atlas: Atlas; data: Funding; route: Route }) {
  const { t, lang, num } = useI18n();
  const fmt = useFmt();
  const p = route.params;
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(p);
    if (value) next.set(key, value); else next.delete(key);
    replaceHash("/funding", next);
    dispatchEvent(new HashChangeEvent("hashchange"));
  };
  const status = p.get("st") ?? "current";
  const sort = (p.get("sort") ?? "deadline") as typeof SORTS[number];
  const q = (p.get("q") ?? "").toLowerCase();

  const strong = (c: Call) => (data.matches[c.id] ?? []).filter((m) => m.category !== "low");
  const optionsOf = (get: (c: Call) => string[]) =>
    [...new Set(data.calls.flatMap(get))].filter(Boolean).sort((a, b) => a.localeCompare(b, lang));
  const schemes = useMemo(() => optionsOf((c) => [pick<string>(c.fields.scheme.v, lang).value ?? ""]), [data, lang]);
  const themes = useMemo(() => optionsOf((c) => pick<string[]>(c.fields.themes.v, lang).value ?? []), [data, lang]);
  const applicants = useMemo(() => optionsOf((c) => pick<string[]>(c.fields.target_groups.v, lang).value ?? []), [data, lang]);

  const shown = data.calls.filter((c) => {
    const f = c.fields;
    const st = f.status.v as string;
    if (status === "current" ? st === "closed" : status !== "all" && st !== status) return false;
    if (q && !callTitle(c, "nb").toLowerCase().includes(q) && !callTitle(c, "en").toLowerCase().includes(q)) return false;
    if (p.get("sch") && pick<string>(f.scheme.v, lang).value !== p.get("sch")) return false;
    if (p.get("th") && !(pick<string[]>(f.themes.v, lang).value ?? []).includes(p.get("th")!)) return false;
    if (p.get("ap") && !(pick<string[]>(f.target_groups.v, lang).value ?? []).includes(p.get("ap")!)) return false;
    if (p.get("intl") && String(!!f.international.v) !== (p.get("intl") === "yes" ? "true" : "false")) return false;
    if (p.get("or") && f.orientation.v !== p.get("or")) return false;
    if (p.get("amt") && !((f.max_amount.v ?? 0) >= Number(p.get("amt")))) return false;
    if (p.get("before")) {
      const d = nextDeadline(c);
      if (!d || d.slice(0, 10) > p.get("before")!) return false;
    }
    if (p.get("mt") && !strong(c).length) return false;
    return true;
  });
  const far = "9999";
  shown.sort((a, b) => {
    if (sort === "amount") return (b.fields.max_amount.v ?? 0) - (a.fields.max_amount.v ?? 0);
    if (sort === "published") return (b.fields.published.v ?? "").localeCompare(a.fields.published.v ?? "");
    if (sort === "relevance") return strong(b).length - strong(a).length
      || (data.matches[b.id]?.[0]?.score ?? 0) - (data.matches[a.id]?.[0]?.score ?? 0);
    return (nextDeadline(a) ?? (a.fields.rolling.v ? "9000" : far)).localeCompare(nextDeadline(b) ?? (b.fields.rolling.v ? "9000" : far));
  });

  const select = (key: string, label: string, opts: [string, string][]) => (
    <label class="field">
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

      <div class="filters funding-filters" role="search">
        <label class="field grow">
          <span>{t("f.search")}</span>
          <input type="search" value={p.get("q") ?? ""} onInput={(e) => set("q", (e.target as HTMLInputElement).value)} />
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
        {select("amt", t("f.amount"), AMOUNTS.map((a) => [String(a), t("f.amountAtLeast", { n: fmt.money(a) })]))}
        <label class="field">
          <span>{t("f.deadlineBefore")}</span>
          <input type="date" value={p.get("before") ?? ""} onInput={(e) => set("before", (e.target as HTMLInputElement).value)} />
        </label>
        <label class="check">
          <input type="checkbox" checked={!!p.get("mt")} onChange={(e) => set("mt", (e.target as HTMLInputElement).checked ? "1" : "")} />
          {t("f.withMatches")}
        </label>
      </div>

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
          {shown.map((c) => <CallCard key={c.id} atlas={atlas} data={data} call={c} />)}
        </ul>
      )}
      <Freshness data={data} />
    </>
  );
}

function CallCard({ atlas, data, call }: { atlas: Atlas; data: Funding; call: Call }) {
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
        <h2><a href={links.call(call.id)}>{callTitle(call, lang)}</a></h2>
        <p class="meta-line">
          <StatusBadge status={status} />
          <span>{pick<string>(f.funder.v, lang).value}</span>
          {f.scheme.v && <span>{pick<string>(f.scheme.v, lang).value}</span>}
          {call.review.length > 0 && <span class="review-flag" title={call.review.join("; ")}>{t("f.review")}</span>}
        </p>
        <dl class="call-facts">
          <div><dt>{pre ? t("f.preDeadline") : t("f.deadline")}</dt>
            <dd>{d ? fmt.date(d, true) : f.rolling.v ? t("f.rolling") : (f.deadline.v ? fmt.date(f.deadline.v, true) : t("f.noDeadline"))}</dd></div>
          {range && <div><dt>{t("f.funding")}</dt><dd>{range}
            {f.total_budget.v && <span class="muted small"> · {t("f.budget", { n: fmt.money(f.total_budget.v) })}</span>}</dd></div>}
          {months && <div><dt>{t("f.duration")}</dt><dd>{months}</dd></div>}
          {groups.length > 0 && <div><dt>{t("f.applicant")}</dt><dd>{groups.join(", ")}
            {f.uis_can_apply.v === false && <span class="muted small"> · {t("f.uisPartner")}</span>}</dd></div>}
        </dl>
        {themes.length > 0 && <div class="tags">{themes.map((x) => <span class="tag static" key={x}>{x}</span>)}</div>}
      </div>
      {status !== "closed" && (
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
          ) : <p class="muted small">{t("f.matchesNone")}</p>}
        </div>
      )}
    </li>
  );
}
