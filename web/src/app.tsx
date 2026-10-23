import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { loadAtlas, type Atlas } from "./data";
import { I18n, useI18n, useI18nState } from "./i18n";
import { links, parseHash, replaceHash, setOrgParam, useRoute, type View } from "./router";
import { decodeOrg, encodeOrg, SelectionContext, type Selection } from "./selection";
import { useTheme } from "./theme";
import { SearchView } from "./views/Search";
import { OverviewView } from "./views/Overview";
import { NetworkView } from "./views/Network";
import { ProfileView } from "./views/Profile";

export function App() {
  const i18n = useI18nState();
  const route = useRoute();
  const [atlas, setAtlas] = useState<Atlas | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mainRef = useRef<HTMLElement>(null);
  const [sel, setSelState] = useState<Selection>(() => decodeOrg(route.params.get("org")));
  setOrgParam(encodeOrg(sel));

  // Links into the site (or the back button) may carry another ?org=.
  useEffect(() => {
    const next = decodeOrg(route.params.get("org"));
    if (encodeOrg(next) !== encodeOrg(sel)) setSelState(next);
  }, [route.params.get("org")]);

  const selection = useMemo(() => ({
    sel,
    setSel: (next: Selection) => {
      setOrgParam(encodeOrg(next));
      const { params } = parseHash(location.hash);
      replaceHash(location.hash.replace(/^#/, "").split("?")[0] || "/", params);
      setSelState(next);
    },
  }), [sel]);

  useEffect(() => { loadAtlas().then(setAtlas).catch((e) => setError(String(e))); }, []);
  useEffect(() => { window.scrollTo(0, 0); }, [route.view, route.id]);
  useEffect(() => {
    const title = i18n.t(`nav.${route.view === "profile" ? "search" : route.view}`);
    const name = route.view === "profile" && atlas ? atlas.byId.get(route.id ?? "")?.name : null;
    document.title = `${name ?? title} – ${i18n.t("app.name")}`;
  }, [route, atlas, i18n]);

  let content;
  if (error) content = <p class="loading">{i18n.t("app.loadError")} ({error})</p>;
  else if (!atlas) content = <p class="loading" role="status">{i18n.t("app.loading")}</p>;
  else if (route.view === "overview") content = <OverviewView atlas={atlas} />;
  else if (route.view === "network") content = <NetworkView atlas={atlas} route={route} />;
  else if (route.view === "profile") content = <ProfileView atlas={atlas} id={route.id!} key={route.id} />;
  else content = <SearchView atlas={atlas} route={route} />;

  return (
    <I18n.Provider value={i18n}>
    <SelectionContext.Provider value={selection}>
      <a class="skip" href="#main" onClick={(e) => { e.preventDefault(); mainRef.current?.focus(); }}>
        {i18n.t("app.skip")}
      </a>
      <Header view={route.view} />
      <main id="main" ref={mainRef} tabIndex={-1}>
        <div class="wrap">{content}</div>
      </main>
      <Footer atlas={atlas} />
    </SelectionContext.Provider>
    </I18n.Provider>
  );
}

function Header({ view }: { view: View }) {
  const { t, lang, setLang } = useI18n();
  const [theme, toggleTheme] = useTheme();
  const items: [View, string][] = [["search", links.search()], ["overview", links.overview], ["network", links.network]];
  return (
    <header class="topbar">
      <div class="wrap">
        <a class="wordmark" href={links.search()}><b>UiS</b><span>{t("app.name")}</span></a>
        <nav class="nav" aria-label={t("nav.label")}>
          {items.map(([v, href]) => (
            <a key={v} href={href} aria-current={view === v || (v === "search" && view === "profile") ? "page" : undefined}>
              {t(`nav.${v}`)}
            </a>
          ))}
        </nav>
        <div class="lang" role="group" aria-label={t("nav.language")}>
          <button type="button" aria-pressed={lang === "nb"} onClick={() => setLang("nb")} lang="nb">Norsk</button>
          <button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")} lang="en">English</button>
        </div>
        <button type="button" class="theme-toggle" onClick={toggleTheme}
          aria-label={t(theme === "dark" ? "theme.toLight" : "theme.toDark")}
          title={t(theme === "dark" ? "theme.toLight" : "theme.toDark")}>
          <span aria-hidden="true">{theme === "dark" ? "☀" : "☾"}</span>
          <span class="theme-label">{t(theme === "dark" ? "theme.light" : "theme.dark")}</span>
        </button>
      </div>
    </header>
  );
}

function Footer({ atlas }: { atlas: Atlas | null }) {
  const { t } = useI18n();
  const meta = atlas?.meta;
  return (
    <footer>
      <div class="wrap">
        <p><span class="badge">{t("footer.prototype")}</span> {t("footer.prototypeText")}</p>
        {meta && <p>{t("footer.source", { from: String(meta.period.first_year), date: meta.generated.slice(0, 10) })}</p>}
        <p>{t("footer.summaries")}</p>
        <p class="credit">{t("footer.designedBy")}{" "}
          <a href="https://florencdemrozi.github.io/">Florenc Demrozi</a>, {t("footer.designerRole")}
        </p>
      </div>
    </footer>
  );
}
