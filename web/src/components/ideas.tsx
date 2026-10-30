import { useState } from "preact/hooks";
import { callTitle, isOpenField, nextDeadline, type Funding } from "../funding";
import { embedIdea, loadIdeaIndex, scoreIdea, type IdeaHit } from "../ideas";
import { useI18n } from "../i18n";
import { links } from "../router";
import { SourceBadge, StatusBadge, useFmt } from "./funding";

type State =
  | { status: "idle" }
  | { status: "working"; percent: number | null }
  | { status: "error"; error: string }
  | { status: "done"; hits: IdeaHit[]; idea: string };

/** "Find calls for a project idea": a shortlist of open calls by text similarity, computed in the browser. */
export function IdeaSearch({ data }: { data: Funding }) {
  const { t, lang, num } = useI18n();
  const fmt = useFmt();
  const [idea, setIdea] = useState("");
  const [state, setState] = useState<State>({ status: "idle" });
  if (!data.meta.has_ideas) return null;

  const run = async (e: Event) => {
    e.preventDefault();
    const text = idea.trim();
    if (text.split(/\s+/).length < 4 || state.status === "working") return;
    setState({ status: "working", percent: null });
    try {
      const [index, q] = await Promise.all([
        loadIdeaIndex(data),
        embedIdea(text, (percent) => setState({ status: "working", percent })),
      ]);
      const open = (id: string) => data.byId.get(id)?.fields.status.v !== "closed";
      const hits = scoreIdea(q, index).filter((h) => open(h.id)).slice(0, index.settings.shortlist);
      setState({ status: "done", hits, idea: text });
    } catch (err) {
      setState({ status: "error", error: String(err) });
    }
  };
  const openField = data.calls.filter((c) => isOpenField(c) && c.fields.status.v !== "closed").length;

  return (
    <details class="idea-search" open={state.status !== "idle"}>
      <summary><strong>{t("idea.title")}</strong> <span class="badge beta">{t("idea.beta")}</span>{" "}
        <span class="muted small">{t("idea.teaser")}</span></summary>
      <p class="warn small" role="note">{t("idea.betaNote")}</p>
      <form onSubmit={run}>
        <label class="field grow">
          <span>{t("idea.label")}</span>
          {/* Writing-assistant extensions send typed text to their servers: keep the idea local. */}
          <textarea rows={3} value={idea} placeholder={t("idea.placeholder")} data-gramm="false"
            data-gramm_editor="false" data-enable-grammarly="false"
            onInput={(e) => setIdea((e.target as HTMLTextAreaElement).value)} />
        </label>
        <p class="small muted">{t("idea.privacy")}</p>
        <button type="submit" class="btn primary" disabled={state.status === "working" || idea.trim().split(/\s+/).length < 4}>
          {t("idea.find")}
        </button>
      </form>
      {state.status === "working" && (
        <p class="loading" role="status">
          {state.percent != null && state.percent < 100 ? t("idea.loadingModel", { p: String(state.percent) }) : t("idea.working")}
        </p>
      )}
      {state.status === "error" && <p class="muted" role="alert">{t("idea.error")} ({state.error})</p>}
      {state.status === "done" && (
        <div aria-live="polite">
          <p class="warn small" role="note">{t("idea.shortlistNote", { n: num(state.hits.length) })}</p>
          <ol class="idea-hits">
            {state.hits.map((h) => {
              const call = data.byId.get(h.id);
              if (!call) return null;
              const d = nextDeadline(call) ?? call.fields.deadline.v;
              return (
                <li key={h.id}>
                  <a href={links.call(h.id)}>{callTitle(call, lang)}</a> <SourceBadge call={call} />{" "}
                  <StatusBadge status={call.fields.status.v} />
                  <span class="muted small"> · {d ? fmt.date(d, true) : call.fields.rolling.v ? t("f.rolling") : t("f.noDeadline")}</span>
                  <div class="small muted">{t(`idea.closest.${h.closest[0]}`)}: {h.closest[1]}</div>
                </li>
              );
            })}
          </ol>
          {openField > 0 && <p class="small">{t("idea.openField", { n: num(openField) })}</p>}
          <p class="small muted">{t("idea.tool")}</p>
        </div>
      )}
    </details>
  );
}
