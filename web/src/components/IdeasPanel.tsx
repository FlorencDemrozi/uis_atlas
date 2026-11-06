// "Project ideas" (Project builder, milestone 3): import the ideas file written by
// pipeline/project_ideas.py, keep the ideas in this browser, read them, flag calls that
// changed or closed since, and export each idea as Word or Markdown.
import { useMemo, useRef, useState } from "preact/hooks";
import { changedFacts, isClosed } from "../builder-core";
import { blocksToDocx } from "../docx";
import { useFunding } from "../funding";
import { useI18n } from "../i18n";
import { blocksToMarkdown, ideaBlocks, type Block, type Idea, type Labels } from "../ideas-core";
import { download } from "../prompt";
import { useProjectIdeas } from "../projectIdeas";
import { ConfirmButton } from "./builder";

const LABEL_KEYS: (keyof Labels)[] = ["draft", "call", "deadline", "researchers", "generated", "dataDates", "fit",
  "fitGood", "fitPartial", "fitPoor", "mismatch", "missingExpertise", "summary", "problem", "approach", "beneficiaries",
  "callFit", "quote", "unverified", "objectives", "innovation", "needsValidation", "roles", "evidence", "workPackages",
  "activities", "deliverables", "lead", "outcomes", "impact", "partners", "feasibility", "consortium", "duration",
  "budget", "trl", "eligibility", "stated", "assumptions", "sources", "warnings", "preferences", "notChecked"];

const slug = (s: string) => s.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 50) || "idea";

export function IdeasPanel() {
  const { t, num } = useI18n();
  const { ideas, error, importFile, remove } = useProjectIdeas();
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const labels = useMemo(() => Object.fromEntries(LABEL_KEYS.map((k) => [k, t(`ideas.l.${k}`)])) as Labels, [t]);

  const onFile = async (e: Event) => {
    const file = (e.target as HTMLInputElement).files?.[0];
    (e.target as HTMLInputElement).value = "";
    if (!file) return;
    try {
      if (file.size > 5_000_000) throw new Error(t("ideas.tooBig"));
      const n = importFile(await file.text());
      setMsg({ ok: true, text: t("ideas.imported", { n: num(n) }) });
    } catch (err) {
      setMsg({ ok: false, text: t("ideas.importError", { e: err instanceof Error ? err.message : String(err) }) });
    }
  };

  return (
    <section class="section ideas-panel" aria-labelledby="h-ideas">
      <h2 id="h-ideas">{t("ideas.title")} <span class="badge beta">{t("idea.beta")}</span></h2>
      <p class="sub">{t("ideas.lede")}</p>
      <ol class="ideas-steps small">
        <li>{t("ideas.step1")}</li>
        <li>{t("ideas.step2")} <code>python pipeline/project_ideas.py uis-atlas-selection-….json</code></li>
        <li>{t("ideas.step3")}</li>
      </ol>
      <p>
        <input ref={input} id="ideas-file" type="file" accept=".json,application/json" class="visually-hidden" onChange={onFile} />
        <button type="button" class="btn primary" onClick={() => input.current?.click()}>{t("ideas.import")}</button>
      </p>
      {msg && <p class={msg.ok ? "small" : "warn small"} role={msg.ok ? "status" : "alert"}>{msg.text}</p>}
      {error && <p class="warn small" role="alert">{t("ideas.storageError")}</p>}
      {ideas.length === 0 ? <p class="muted">{t("ideas.none")}</p> : (
        <ul class="ideas-list">
          {ideas.map((i) => <IdeaItem key={i.id} idea={i} labels={labels} onRemove={() => remove(i.id)} />)}
        </ul>
      )}
    </section>
  );
}

function CallStatus({ idea }: { idea: Idea }) {
  const { t } = useI18n();
  const { state } = useFunding();
  if (state.status !== "ready") return <span class="muted small">{t("ideas.unlockToCheck")}</span>;
  const call = state.data.byId.get(idea.call.id);
  if (!call) return <span class="warn-inline small">{t("ideas.callGone")}</span>;
  const today = new Date().toISOString().slice(0, 10);
  const changed = Object.keys(idea.call.facts).length
    ? changedFacts({ id: idea.call.id, saved: idea.generated, facts: idea.call.facts }, call.fields) : [];
  return (
    <>
      {isClosed(call.fields, today) && <span class="warn-inline small">{t("ideas.callClosed")}</span>}
      {changed.length > 0 && (
        <span class="warn-inline small">
          {t("ideas.callChanged", { what: changed.map((k) => t(`fld.${k}`).toLowerCase()).join(", ") })}
        </span>
      )}
    </>
  );
}

function IdeaItem({ idea, labels, onRemove }: { idea: Idea; labels: Labels; onRemove: () => void }) {
  const { t } = useI18n();
  const blocks = useMemo(() => ideaBlocks(idea, labels), [idea, labels]);
  const title = idea.concept ? `${idea.concept.acronym ? `${idea.concept.acronym}: ` : ""}${idea.concept.title}` : idea.call.title;
  const name = `${slug(idea.concept?.acronym || idea.call.id)}-${idea.generated.slice(0, 10)}`;
  return (
    <li class="idea-item">
      <details>
        <summary>
          <span class="idea-title">{title}</span>
          <span class="meta-line small">
            <span class={`fit-badge ${idea.fit}`}>{labels[idea.fit === "good" ? "fitGood" : idea.fit === "partial" ? "fitPartial" : "fitPoor"]}</span>
            {idea.concept && <span>{labels.call}: {idea.call.title}</span>}
            <span>{t("ideas.generatedOn", { d: idea.generated.slice(0, 10) })}</span>
            <span>{idea.researchers.map((r) => r.name).join(", ")}</span>
            <CallStatus idea={idea} />
          </span>
        </summary>
        <div class="idea-body"><Blocks blocks={blocks.slice(1)} /></div>
      </details>
      <div class="panel-actions">
        <button type="button" class="btn" onClick={() => download(`${name}.docx`, blocksToDocx(blocks, title, idea.generated),
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}>{t("ideas.exportDocx")}</button>
        <button type="button" class="btn" onClick={() => download(`${name}.md`, blocksToMarkdown(blocks), "text/markdown")}>
          {t("ideas.exportMd")}</button>
        <ConfirmButton label={t("ideas.delete")} confirm={t("ideas.deleteConfirm")} onConfirm={onRemove} />
      </div>
    </li>
  );
}

/** The idea on the page: the same blocks as the exports (headings one level down). */
function Blocks({ blocks }: { blocks: Block[] }) {
  return (
    <>
      {blocks.map((b, k) => {
        switch (b.kind) {
          case "title": return <h3 key={k}>{b.text}</h3>;
          case "h1": return <h4 key={k}>{b.text}</h4>;
          case "h2": return <h5 key={k}>{b.text}</h5>;
          case "note": return <p key={k} class="warn small" role="note">{b.text}</p>;
          case "bullets": return <ul key={k}>{b.items.map((x, j) => <li key={j}>{x}</li>)}</ul>;
          default: return <p key={k}>{b.text}</p>;
        }
      })}
    </>
  );
}
