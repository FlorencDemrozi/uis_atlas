// Privacy and cookies: what the site stores in the browser (no cookies, no tracking),
// what the server records, and where the researcher profiles come from. Texts in the
// translation files (priv.*). Keep in step with docs/DATA_POLICY.md §7.
import { useI18n } from "../i18n";
import { links } from "../router";

const STORAGE = ["settings", "work", "news", "funding", "model"];

export function PrivacyView() {
  const { t } = useI18n();
  return (
    <div class="prose">
      <div class="page-head">
        <h1>{t("priv.title")}</h1>
        <p>{t("priv.lede")}</p>
      </div>
      <p class="note">{t("priv.draft")}</p>

      <h2>{t("priv.storageTitle")}</h2>
      <p>{t("priv.storageText")}</p>
      <table>
        <caption class="visually-hidden">{t("priv.storageTitle")}</caption>
        <thead><tr><th scope="col">{t("priv.colWhat")}</th><th scope="col">{t("priv.colWhy")}</th>
          <th scope="col">{t("priv.colHow")}</th></tr></thead>
        <tbody>
          {STORAGE.map((k) => (
            <tr key={k}><th scope="row">{t(`priv.s.${k}.what`)}</th><td>{t(`priv.s.${k}.why`)}</td>
              <td>{t(`priv.s.${k}.how`)}</td></tr>
          ))}
        </tbody>
      </table>
      <p>{t("priv.storageClear")}</p>

      <h2>{t("priv.serverTitle")}</h2>
      <p>{t("priv.serverText")}</p>

      <h2>{t("priv.thirdTitle")}</h2>
      <p>{t("priv.thirdText")}</p>

      <h2>{t("priv.profilesTitle")}</h2>
      <p>{t("priv.profilesText")}</p>

      <h2>{t("priv.rightsTitle")}</h2>
      <p>{t("priv.rightsText")}{" "}
        <a href={links.feedback}>{t("nav.feedback")}</a> · <a href="mailto:personvernombud@uis.no">personvernombud@uis.no</a>
        {" "}· <a href="https://www.datatilsynet.no/">Datatilsynet</a></p>
    </div>
  );
}
