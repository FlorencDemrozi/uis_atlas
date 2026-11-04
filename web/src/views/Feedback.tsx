// Feedback: a short introduction and a link to the questionnaire in Microsoft Forms.
// The form opens in its own tab (not embedded): it works the same on every device and
// needs no change to the site's Content-Security-Policy.
import { useI18n } from "../i18n";

/** The questionnaire (Microsoft Forms, owned by the project owner). */
export const FEEDBACK_FORM_URL = "https://forms.cloud.microsoft/e/stEfQPPAZJ";

export function FeedbackView() {
  const { t } = useI18n();
  return (
    <>
      <div class="page-head">
        <h1>{t("fb.title")}</h1>
        <p>{t("fb.lede")}</p>
      </div>
      <section class="panel feedback-panel" aria-labelledby="h-fb">
        <h2 id="h-fb">{t("fb.what")}</h2>
        <ul>
          <li>{t("fb.point1")}</li>
          <li>{t("fb.point2")}</li>
          <li>{t("fb.point3")}</li>
        </ul>
        <p>
          <a class="btn primary" href={FEEDBACK_FORM_URL} target="_blank" rel="noopener noreferrer">
            {t("fb.open")} <span aria-hidden="true">↗</span>
          </a>
          <span class="muted small" style={{ marginLeft: "12px" }}>{t("fb.newTab")}</span>
        </p>
        <p class="note">{t("fb.privacy")}</p>
      </section>
    </>
  );
}
