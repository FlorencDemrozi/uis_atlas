import type { ComponentChildren } from "preact";
import { useEffect, useState } from "preact/hooks";
import type { Atlas } from "../data";
import { callTitle, isStale, pick, useFunding, type Call, type Eligibility, type Field, type Funding, type Match } from "../funding";
import { useI18n } from "../i18n";
import { links } from "../router";
import { DeptLabel, Position, doiUrl } from "./common";

// ------------------------------------------------------------- unlock gate
/** Renders children with the decrypted data, or the password form. */
export function FundingGate({ children, compact = false }:
  { children: (data: Funding) => ComponentChildren; compact?: boolean }) {
  const { t } = useI18n();
  const { state, load } = useFunding();
  useEffect(() => { load(); }, [load]);
  if (state.status === "ready") return <>{children(state.data)}</>;
  if (state.status === "idle" || state.status === "loading") {
    return compact ? null : <p class="loading" role="status">{t("f.loading")}</p>;
  }
  if (state.status === "missing") return compact ? null : <p class="muted">{t("f.missing")}</p>;
  if (state.status === "unsupported") return <p class="muted">{t("f.unsupported")}</p>;
  if (state.status === "error") return <p class="muted">{t("f.error")} ({state.error})</p>;
  return <UnlockForm compact={compact} />;
}

function UnlockForm({ compact }: { compact: boolean }) {
  const { t } = useI18n();
  const { unlock } = useFunding();
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [wrong, setWrong] = useState(false);
  const submit = async (e: Event) => {
    e.preventDefault();
    if (!pw || busy) return;
    setBusy(true);
    setWrong(false);
    const ok = await unlock(pw);
    setBusy(false);
    if (!ok) setWrong(true);
  };
  return (
    <form class={compact ? "unlock compact" : "unlock panel"} onSubmit={submit}>
      {compact ? <p class="small">{t("f.profileLocked")}</p> : <>
        <h1>{t("f.lockedTitle")}</h1>
        <p>{t("f.lockedText")}</p>
      </>}
      <div class="unlock-row">
        <label class="field">
          <span>{t("f.password")}</span>
          <input type="password" autoComplete="current-password" value={pw}
            onInput={(e) => setPw((e.target as HTMLInputElement).value)}
            aria-invalid={wrong} aria-describedby={wrong ? "unlock-error" : undefined} />
        </label>
        <button type="submit" class="btn primary" disabled={busy}>{busy ? t("f.unlocking") : t("f.unlock")}</button>
      </div>
      {wrong && <p id="unlock-error" class="error" role="alert">{t("f.wrongPassword")}</p>}
    </form>
  );
}

// ------------------------------------------------------------ formatting
export function useFmt() {
  const { lang, t } = useI18n();
  const locale = lang === "nb" ? "nb-NO" : "en-GB";
  const date = (iso: string | null | undefined, withTime = false) => {
    if (!iso) return "";
    const d = new Date(iso.length === 10 ? `${iso}T00:00` : iso);
    const s = d.toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" });
    return withTime && iso.length > 10 ? `${s}, ${d.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })}` : s;
  };
  const money = (n: number | null | undefined, currency = "NOK") => {
    if (n == null) return "";
    const compact = n >= 1e6;
    return new Intl.NumberFormat(locale, { style: "currency", currency, notation: compact ? "compact" : "standard",
      maximumFractionDigits: compact ? 1 : 0 }).format(n);
  };
  const range = (c: Call) => {
    const f = c.fields;
    const cur = f.currency?.v ?? "NOK";
    const a = f.min_amount?.v as number | null, b = f.max_amount?.v as number | null;
    if (a != null && b != null) return a === b ? money(b, cur) : t("f.range", { a: money(a, cur), b: money(b, cur) });
    if (b != null) return t("f.upTo", { b: money(b, cur) });
    if (a != null) return t("f.from", { a: money(a, cur) });
    return "";
  };
  const months = (c: Call) => {
    const a = c.fields.min_duration_months?.v as number | null, b = c.fields.max_duration_months?.v as number | null;
    if (a != null && b != null) return a === b ? t("f.monthsExact", { b }) : t("f.months", { a, b });
    if (b != null) return t("f.monthsMax", { b });
    if (a != null) return t("f.monthsMin", { a });
    return "";
  };
  return { date, money, range, months };
}

const DATE_FIELDS = new Set(["deadline", "preliminary_deadline", "full_proposal_deadline", "opening_date",
  "published", "updated", "earliest_start", "latest_start", "latest_end"]);
const MONEY_FIELDS = new Set(["min_amount", "max_amount", "total_budget"]);

export function StatusBadge({ status }: { status: string }) {
  const { t } = useI18n();
  return <span class={`status-badge ${status}`}>{t(`f.status.${status}`)}</span>;
}

function MethodBadge({ f }: { f: Field }) {
  const { t } = useI18n();
  const key = f.m === "ai" ? "ai" : f.m === "manual" ? "manual" : f.m === "rule" ? "rule"
    : f.s === "inferred" ? "inferred" : "explicit";
  return <span class={`src-badge ${key}`}>{t(`f.badge.${key}`)}</span>;
}

/** Long official passages are shown folded after the first paragraph. */
function LongText({ text }: { text: string }) {
  const { t } = useI18n();
  const paras = text.split("\n").filter(Boolean);
  const render = (ps: string[]) => ps.map((p, i) => p.startsWith("• ")
    ? <p key={i} class="bullet">{p.slice(2)}</p> : <p key={i}>{p}</p>);
  if (text.length < 500) return <div class="passage">{render(paras)}</div>;
  let n = 0, cut = 0;
  while (cut < paras.length && n < 380) n += paras[cut++].length;
  return (
    <div class="passage">
      {render(paras.slice(0, cut))}
      {cut < paras.length && (
        <details>
          <summary>{t("f.showMore")}</summary>
          {render(paras.slice(cut))}
        </details>
      )}
    </div>
  );
}

export function FieldValue({ name, f }: { name: string; f: Field<any> }) {
  const { t, lang } = useI18n();
  const fmt = useFmt();
  const v = f.v;
  if (v == null || f.s === "not_specified") return <span class="muted">{t("f.notSpecified")}</span>;
  if (DATE_FIELDS.has(name)) return <>{fmt.date(v, true)}</>;
  if (MONEY_FIELDS.has(name)) return <>{fmt.money(v, "NOK")}</>;
  if (typeof v === "boolean") return <>{t(v ? "f.yes" : "f.no")}</>;
  if (typeof v === "number") return <>{v}</>;
  if (name === "orientation") return <>{t(`f.orient.${v}`)}</>;
  if (name === "status") return <StatusBadge status={v} />;
  if (name === "documents") {
    return (
      <ul class="doc-list">
        {(v as { text: string; url: string; kind: string }[]).map((d) => (
          <li key={d.url}><span class="muted small">{t(`f.doc.${d.kind}`)}</span> <a href={d.url}>{d.text}</a></li>
        ))}
      </ul>
    );
  }
  if (typeof v === "string") return <>{v}</>;
  if (name === "url") {
    return <>{v.nb && <a href={v.nb}>{t("f.official")}</a>}{v.en && <> · <a href={v.en}>{t("f.officialEn")}</a></>}</>;
  }
  const { value, fallback } = pick<any>(v, lang);
  if (value == null) return <span class="muted">{t("f.notSpecified")}</span>;
  return (
    <>
      {fallback && <span class="muted small">{t("f.fallback")} · </span>}
      {Array.isArray(value) ? value.join(", ") : <LongText text={String(value)} />}
    </>
  );
}

export function FieldRow({ name, f }: { name: string; f: Field<any> }) {
  const { t } = useI18n();
  const missing = f.s === "not_specified";
  return (
    <div class={`field-row${missing ? " missing" : ""}`}>
      <dt>{t(`fld.${name}`)}</dt>
      <dd>
        <FieldValue name={name} f={f} />
        {!missing && (
          <div class="field-meta">
            <MethodBadge f={f} />
            {f.src && (f.url ? <a href={f.url}>{t("f.source", { src: f.src })}</a> : <span>{t("f.source", { src: f.src })}</span>)}
            {f.ev && f.m !== "section" && String(f.ev) !== String(f.v) && (
              <details class="ev"><summary>{t("f.showSource")}</summary><q>{f.ev}</q></details>
            )}
          </div>
        )}
        {f.ai && (
          <p class="ai-note small">
            <span class="src-badge ai">{t("f.badge.ai")}</span> {f.ai.v}
            {f.ai.ev && <details class="ev"><summary>{t("f.showSource")}</summary><q>{f.ai.ev}</q></details>}
          </p>
        )}
      </dd>
    </div>
  );
}

/** A group of fields; fields the call does not specify are folded away. */
export function FieldList({ names, call }: { names: string[]; call: Call }) {
  const { t } = useI18n();
  const present = names.filter((n) => call.fields[n] && call.fields[n].s !== "not_specified");
  const absent = names.filter((n) => call.fields[n] && call.fields[n].s === "not_specified");
  return (
    <>
      <dl class="fields">{present.map((n) => <FieldRow key={n} name={n} f={call.fields[n]} />)}</dl>
      {absent.length > 0 && (
        <details class="unspecified">
          <summary>{t("f.showUnspecified", { n: absent.length })}</summary>
          <dl class="fields">{absent.map((n) => <FieldRow key={n} name={n} f={call.fields[n]} />)}</dl>
        </details>
      )}
    </>
  );
}

// --------------------------------------------------------------- matches
export function CategoryBadge({ m }: { m: Match }) {
  const { t } = useI18n();
  return (
    <span class={`cat-badge ${m.category}`} title={t("f.scoreHelp")}>
      {t(`f.cat.${m.category}`)} <span class="num">{Math.round(m.score * 100)}</span>
    </span>
  );
}

export function EligibilityBadge({ e }: { e: Eligibility }) {
  const { t } = useI18n();
  return (
    <div class="elig">
      <span class={`elig-badge ${e.status}`}>{t(`f.elig.${e.status}`)}</span>
      <span class="small muted"> {t(`f.reason.${e.reason}`)}</span>
      {e.evidence && e.reason !== "none_found" && (
        <details class="ev"><summary>{t("f.showSource")}</summary><q>{e.evidence}</q></details>
      )}
    </div>
  );
}

/** Why a researcher matches one call: papers, covered and missing aspects, role,
 * eligibility and complementary colleagues. `who` shows the researcher header. */
export function MatchDetails({ atlas, call, m, who = false }: { atlas: Atlas; call: Call; m: Match; who?: boolean }) {
  const { t, num } = useI18n();
  const r = atlas.byId.get(m.id);
  const aspects = call.aspects ?? [];
  const pct = (x: number) => String(Math.round(x * 100));
  return (
    <div class="match">
      {who && r && (
        <div class="match-head">
          <h3><a href={links.profile(r.scopus_id)}>{r.name}</a></h3>
          <CategoryBadge m={m} />
          <div class="meta-line"><Position r={r} /><DeptLabel name={r.department} withFaculty /></div>
        </div>
      )}
      <p class="small muted">{t("f.score", { n: pct(m.score), a: pct(m.components.scope), b: pct(m.components.coverage),
        c: pct(m.components.evidence) })}</p>
      <div class="why">
        <h4>{t("f.whyPapers")}</h4>
        <ul>
          {m.papers.map((p) => {
            const paper = atlas.papers[p.eid];
            if (!paper) return null;
            const url = doiUrl(paper.doi);
            return (
              <li key={p.eid}>
                {url ? <a href={url}>{paper.title}</a> : paper.title}
                <span class="muted small"> · {paper.year}{paper.venue ? ` · ${paper.venue}` : ""}</span>
                {p.terms.length > 0 && <span class="small"> · {p.terms.map((x) => <mark key={x}>{x}</mark>)}</span>}
              </li>
            );
          })}
        </ul>
      </div>
      {aspects.length > 0 && (
        <div class="aspect-cover">
          {(m.specialist_for?.length ?? 0) > 0 && <p class="small"><strong>{t("f.specialistFor")}:</strong>{" "}
            {m.specialist_for!.map((j) => aspects[j]?.label).filter(Boolean).join(" · ")}</p>}
          {m.matched.length > 0 && <p class="small"><strong>{t("f.matchedAspects")}:</strong>{" "}
            {m.matched.map((x) => aspects[x.aspect]?.label).filter(Boolean).join(" · ")}</p>}
          {m.missing.length > 0 && <p class="small muted"><strong>{t("f.missingAspects")}:</strong>{" "}
            {m.missing.map((j) => aspects[j]?.label).filter(Boolean).join(" · ")}</p>}
        </div>
      )}
      <p class="small"><strong>{t("f.role")}:</strong> {t(`f.role.${m.role}`)}</p>
      <EligibilityBadge e={m.eligibility} />
      {m.collaborators.length > 0 && (
        <div class="collabs">
          <h4>{t("f.collabs")}</h4>
          <ul class="people">
            {m.collaborators.map((c) => {
              const co = atlas.byId.get(c.id);
              if (!co) return null;
              const why = [
                t("f.collabFills", { aspects: c.fills.map((j) => aspects[j]?.label).filter(Boolean).slice(0, 3).join("; ") }),
                c.joint_papers ? t("f.collabJoint", { n: num(c.joint_papers) }) : null,
                c.other_department ? t("f.collabOtherDept") : null,
              ].filter(Boolean).join(" · ");
              return (
                <li key={c.id}>
                  <span><a href={links.profile(c.id)}>{co.name}</a> <span class="muted small">· <DeptLabel name={co.department} /></span></span>
                  <span class="small muted">{why}</span>
                </li>
              );
            })}
          </ul>
          <p class="small muted">{t("f.collabNote")}</p>
        </div>
      )}
      {!who && <p class="small"><a href={links.call(call.id)}>{t("f.openCall")} →</a></p>}
    </div>
  );
}

export function Freshness({ data }: { data: Funding }) {
  const { t } = useI18n();
  const fmt = useFmt();
  const { lock } = useFunding();
  const m = data.meta;
  const ok = m.sync?.last_success ?? null;
  return (
    <div class="freshness small muted">
      {isStale(ok) && <p class="warn" role="status">{t("f.stale", { date: fmt.date(ok) || "–" })}</p>}
      {(m.sync?.errors?.length ?? 0) > 0 && <p class="warn">{t("f.syncErrors", { n: m.sync!.errors.length })}</p>}
      <p>{t("f.freshness", { sync: fmt.date(ok) || "–", matched: fmt.date(m.matches_generated),
        people: fmt.date(m.researchers_updated) || "–", algo: m.algorithm })}{" "}
        · <button type="button" class="linklike" onClick={lock}>{t("f.lock")}</button></p>
    </div>
  );
}

export { callTitle };
