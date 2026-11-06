// "Prepare AI prompt" (Project builder, milestone 2): pick researchers and calls from the
// selection, add preferences, get an editable prompt package to copy or download for an
// external LLM. Nothing is sent anywhere by the site.
import { useMemo, useState } from "preact/hooks";
import type { Atlas } from "../data";
import { useBuilderCalls } from "../builder";
import { callTitle, useFunding, type Funding } from "../funding";
import { useI18n } from "../i18n";
import { useShortlist } from "../shortlist";
import { download, preparePrompt } from "../prompt";
import { toPlainText, type PromptInput, type PromptPackage } from "../prompt-core";

type Status = { kind: "idle" } | { kind: "working" } | { kind: "error"; error: string } | { kind: "done" };

export function PromptBuilder({ atlas }: { atlas: Atlas }) {
  const { t } = useI18n();
  const { state } = useFunding();
  return (
    <section class="section prompt-builder" aria-labelledby="h-prompt">
      <h2 id="h-prompt">{t("prompt.title")}</h2>
      <p class="sub">{t("prompt.lede")}</p>
      {state.status === "ready" ? <PromptForm atlas={atlas} data={state.data} />
        : <p class="muted">{t("prompt.needUnlock")}</p>}
    </section>
  );
}

function PromptForm({ atlas, data }: { atlas: Atlas; data: Funding }) {
  const { t, lang, num } = useI18n();
  const { ids } = useShortlist();
  const { calls } = useBuilderCalls();
  const people = ids.map((id) => atlas.byId.get(id)).filter((r) => r !== undefined);
  const saved = calls.map((s) => data.byId.get(s.id)).filter((c) => c !== undefined);
  // Unticked entries; everything newly added to the selection starts ticked.
  const [offPeople, setOffPeople] = useState<Set<string>>(new Set());
  const [offCalls, setOffCalls] = useState<Set<string>>(new Set());
  const [prefs, setPrefs] = useState({ direction: "", area: "", constraints: "" });
  const [language, setLanguage] = useState<PromptInput["answerLanguage"]>(lang === "nb" ? "Norwegian (bokmål)" : "English");
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [pkg, setPkg] = useState<PromptPackage | null>(null);
  const [prompt, setPrompt] = useState("");
  const [support, setSupport] = useState("");
  const [copied, setCopied] = useState<"" | "ok" | "manual">("");

  const chosenPeople = people.filter((r) => !offPeople.has(r.scopus_id)).map((r) => r.scopus_id);
  const chosenCalls = saved.filter((c) => !offCalls.has(c.id)).map((c) => c.id);
  const ready = chosenPeople.length > 0 && chosenCalls.length > 0;
  const toggle = (set: Set<string>, update: (s: Set<string>) => void, id: string) => {
    const next = new Set(set);
    if (next.has(id)) next.delete(id); else next.add(id);
    update(next);
  };

  const prepare = async (e: Event) => {
    e.preventDefault();
    if (!ready || status.kind === "working") return;
    setStatus({ kind: "working" });
    try {
      const out = await preparePrompt(atlas, data, chosenPeople, chosenCalls, prefs, language);
      setPkg(out); setPrompt(out.prompt); setSupport(out.support ?? ""); setCopied("");
      setStatus({ kind: "done" });
    } catch (err) {
      setStatus({ kind: "error", error: String(err) });
    }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(prompt); setCopied("ok"); setTimeout(() => setCopied(""), 2500); }
    catch { setCopied("manual"); }
  };
  const day = new Date().toISOString().slice(0, 10);
  const tokens = useMemo(() => Math.round((prompt.length + support.length) / 4), [prompt, support]);

  if (!people.length || !saved.length) {
    return <p class="muted">{t("prompt.needBoth")}</p>;
  }
  return (
    <>
      <form class="prompt-form" onSubmit={prepare}>
        <div class="builder-grid">
          <fieldset class="pick-list">
            <legend>{t("prompt.pickPeople")}</legend>
            {people.map((r) => (
              <label key={r.scopus_id} class="check">
                <input type="checkbox" checked={!offPeople.has(r.scopus_id)}
                  onChange={() => toggle(offPeople, setOffPeople, r.scopus_id)} />
                <span>{r.name}</span>
              </label>
            ))}
          </fieldset>
          <fieldset class="pick-list">
            <legend>{t("prompt.pickCalls")}</legend>
            {saved.map((c) => (
              <label key={c.id} class="check">
                <input type="checkbox" checked={!offCalls.has(c.id)} onChange={() => toggle(offCalls, setOffCalls, c.id)} />
                <span>{callTitle(c, lang)}</span>
              </label>
            ))}
          </fieldset>
        </div>
        {(["direction", "area", "constraints"] as const).map((k) => (
          <label key={k} class="field">
            <span>{t(`prompt.${k}`)}</span>
            <textarea rows={2} value={prefs[k]} placeholder={t(`prompt.${k}Hint`)} data-gramm="false"
              data-enable-grammarly="false"
              onInput={(e) => setPrefs({ ...prefs, [k]: (e.target as HTMLTextAreaElement).value })} />
          </label>
        ))}
        <label class="field narrow">
          <span>{t("prompt.language")}</span>
          <select value={language} onChange={(e) => setLanguage((e.target as HTMLSelectElement).value as PromptInput["answerLanguage"])}>
            <option value="English">English</option>
            <option value="Norwegian (bokmål)">Norsk bokmål</option>
          </select>
        </label>
        {!ready && <p class="warn small" role="note">{t("prompt.needBoth")}</p>}
        <p>
          <button type="submit" class="btn primary" disabled={!ready || status.kind === "working"}>
            {t(pkg ? "prompt.again" : "prompt.prepare")}
          </button>
          {pkg && <span class="muted small"> {t("prompt.againNote")}</span>}
        </p>
      </form>

      {status.kind === "working" && <p class="loading" role="status">{t("prompt.working")}</p>}
      {status.kind === "error" && <p class="warn" role="alert">{t("prompt.error")} ({status.error})</p>}

      {pkg && status.kind !== "working" && (
        <div class="prompt-result" aria-live="polite">
          <p class="warn small" role="note">{t("prompt.reviewNote")}</p>
          <p class="small muted">
            {t(support ? "prompt.statsSplit" : "prompt.stats", { c: num(prompt.length + support.length), k: num(tokens) })}
          </p>
          {pkg.omitted.length > 0 && (
            <details class="small">
              <summary>{t("prompt.omitted", { n: num(pkg.omitted.length) })}</summary>
              <ul>{pkg.omitted.map((o) => <li key={o}>{o}</li>)}</ul>
            </details>
          )}
          <label class="field" for="prompt-text">{t("prompt.preview")}</label>
          <textarea id="prompt-text" class="prompt-text" rows={18} value={prompt} spellcheck={false} data-gramm="false"
            data-enable-grammarly="false" onInput={(e) => setPrompt((e.target as HTMLTextAreaElement).value)} />
          <div class="panel-actions">
            <button type="button" class="btn primary" onClick={copy}>{t(copied === "ok" ? "prompt.copied" : "prompt.copy")}</button>
            <button type="button" class="btn" onClick={() => download(`atlas-prompt-${day}.md`, prompt, "text/markdown")}>
              {t("prompt.downloadMd")}</button>
            <button type="button" class="btn" onClick={() => download(`atlas-prompt-${day}.txt`, toPlainText(prompt), "text/plain")}>
              {t("prompt.downloadTxt")}</button>
          </div>
          {copied === "manual" && <p class="small muted" role="status">{t("prompt.copyManual")}</p>}
          {support && (
            <>
              <label class="field" for="support-text">{t("prompt.support")}</label>
              <p class="small muted">{t("prompt.supportHelp")}</p>
              <textarea id="support-text" class="prompt-text" rows={10} value={support} spellcheck={false} data-gramm="false"
                data-enable-grammarly="false" onInput={(e) => setSupport((e.target as HTMLTextAreaElement).value)} />
              <div class="panel-actions">
                <button type="button" class="btn" onClick={() => download(`atlas-supporting-information-${day}.md`, support, "text/markdown")}>
                  {t("prompt.downloadMd")}</button>
                <button type="button" class="btn" onClick={() => download(`atlas-supporting-information-${day}.txt`, toPlainText(support), "text/plain")}>
                  {t("prompt.downloadTxt")}</button>
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
