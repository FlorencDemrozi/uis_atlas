import { Component, type ComponentChildren } from "preact";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { loadAtlas, type Atlas } from "./data";
import { I18n, useI18n, useI18nState } from "./i18n";
import { links, parseHash, replaceHash, setOrgParam, useRoute, type View } from "./router";
import { decodeOrg, encodeOrg, SelectionContext, type Selection } from "./selection";
import { ShortlistContext, useShortlist, useShortlistState } from "./shortlist";
import { nextTheme, useTheme, type Theme } from "./theme";
import { SearchView } from "./views/Search";
import { ProfileView } from "./views/Profile";
import { FundingContext, callTitle, useFundingState } from "./funding";
import { lazyView } from "./lazy";

const OverviewView = lazyView(() => import("./views/Overview").then((m) => m.OverviewView));
const NetworkView = lazyView(() => import("./views/Network").then((m) => m.NetworkView));
const ShortlistView = lazyView(() => import("./views/Shortlist").then((m) => m.ShortlistView));
const FundingView = lazyView(() => import("./views/Funding").then((m) => m.FundingView));
const CallView = lazyView(() => import("./views/Call").then((m) => m.CallView));
const FeedbackView = lazyView(() => import("./views/Feedback").then((m) => m.FeedbackView));

export function App() {
  const i18n = useI18nState();
  const route = useRoute();
  const shortlist = useShortlistState();
  const funding = useFundingState();
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
    const call = route.view === "call" && funding.state.status === "ready"
      ? funding.state.data.byId.get(route.id ?? "") : null;
    const name = route.view === "profile" && atlas ? atlas.byId.get(route.id ?? "")?.name
      : call ? callTitle(call, i18n.lang) : null;
    document.title = `${name ?? title} – ${i18n.t("app.name")}`;
  }, [route, atlas, i18n, funding.state]);

  let content;
  if (error) content = <p class="loading">{i18n.t("app.loadError")} ({error})</p>;
  else if (!atlas) content = <p class="loading" role="status">{i18n.t("app.loading")}</p>;
  else if (route.view === "overview") content = <OverviewView atlas={atlas} />;
  else if (route.view === "network") content = <NetworkView atlas={atlas} route={route} />;
  else if (route.view === "shortlist") content = <ShortlistView atlas={atlas} route={route} />;
  else if (route.view === "profile") content = <ProfileView atlas={atlas} id={route.id!} key={route.id} />;
  else if (route.view === "funding") content = <FundingView atlas={atlas} route={route} />;
  else if (route.view === "feedback") content = <FeedbackView />;
  else if (route.view === "call") content = <CallView atlas={atlas} id={route.id!} key={route.id} />;
  else content = <SearchView atlas={atlas} route={route} />;

  return (
    <I18n.Provider value={i18n}>
    <SelectionContext.Provider value={selection}>
    <ShortlistContext.Provider value={shortlist}>
    <FundingContext.Provider value={funding}>
      <a class="skip" href="#main" onClick={(e) => { e.preventDefault(); mainRef.current?.focus(); }}>
        {i18n.t("app.skip")}
      </a>
      <Header view={route.view} />
      <main id="main" ref={mainRef} tabIndex={-1}>
        <div class="wrap"><ErrorBoundary key={`${route.view}/${route.id ?? ""}`}>{content}</ErrorBoundary></div>
      </main>
      <Footer atlas={atlas} />
    </FundingContext.Provider>
    </ShortlistContext.Provider>
    </SelectionContext.Provider>
    </I18n.Provider>
  );
}

/** A view that fails while rendering shows a message and a way home instead of a blank page. */
class ErrorBoundary extends Component<{ children: ComponentChildren }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: unknown) { console.error(error); }
  render() { return this.state.failed ? <RenderError /> : this.props.children; }
}

function RenderError() {
  const { t } = useI18n();
  return (
    <div class="page-head" role="alert">
      <h1>{t("app.renderError")}</h1>
      <p><a href={links.search()}>{t("app.renderErrorHome")}</a></p>
    </div>
  );
}

// Icons of the theme switch (the current theme; 1.5px strokes in currentColor).
const THEME_ICON: Record<Theme, preact.JSX.Element> = {
  light: <><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" /></>,
  dark: <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />,
  sepia: <><path d="M4 5.5c2.7-1 5.3-1 8 .8 2.7-1.8 5.3-1.8 8-.8v13c-2.7-1-5.3-1-8 .8-2.7-1.8-5.3-1.8-8-.8z" /><path d="M12 6.3v13" /></>,
};

function Header({ view }: { view: View }) {
  const { t, lang, setLang } = useI18n();
  const [theme, cycleTheme] = useTheme();
  const { ids } = useShortlist();
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => setMenuOpen(false), [view]);   // a link was followed
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setMenuOpen(false); };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [menuOpen]);
  const items: [View, string][] = [["search", links.search()], ["overview", links.overview], ["network", links.network],
    ["feedback", links.feedback],
    ["funding", links.funding()], ["shortlist", links.shortlist()]];
  const switchLabel = t("theme.switch", { current: t(`theme.${theme}`), next: t(`theme.${nextTheme(theme)}`) });
  return (
    <header class="topbar">
      <div class="wrap">
        <a class="wordmark" href={links.search()}><b>UiS</b> <span>{t("app.name")}</span></a>
        <button type="button" class="menu-toggle" aria-expanded={menuOpen} aria-controls="main-nav"
          onClick={() => setMenuOpen((o) => !o)}>
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor"
            stroke-width="1.6" stroke-linecap="round">
            {menuOpen ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
          </svg>
          <span>{t("nav.menu")}</span>
        </button>
        <nav id="main-nav" class={`nav${menuOpen ? " open" : ""}`} aria-label={t("nav.label")}>
          {items.map(([v, href]) => (
            <a key={v} href={href} aria-current={view === v || (v === "search" && view === "profile") || (v === "funding" && view === "call")
              ? "page" : undefined}>
              {t(`nav.${v}`)}
              {v === "shortlist" && ids.length > 0 && <span class="nav-count">{ids.length}</span>}
            </a>
          ))}
        </nav>
        <div class="topbar-tools">
          <div class="lang" role="group" aria-label={t("nav.language")}>
            <button type="button" aria-pressed={lang === "nb"} onClick={() => setLang("nb")} lang="nb" title="Norsk"
              aria-label="Norsk">NB</button>
            <button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")} lang="en" title="English"
              aria-label="English">EN</button>
          </div>
          <button type="button" class="theme-toggle" onClick={cycleTheme} aria-label={switchLabel} title={switchLabel}>
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor"
              stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{THEME_ICON[theme]}</svg>
          </button>
        </div>
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
        <p class="credit">{t("footer.designedWith")}{" "}
          <span role="img" aria-label={t("footer.love")}>❤️</span> {t("footer.and")}{" "}
          <span role="img" aria-label={t("footer.coffee")}>☕</span> {t("footer.designedAt")}{" "}
          <a href="https://florencdemrozi.github.io/">Florenc Demrozi</a>, {t("footer.designerRole")}
        </p>
      </div>
    </footer>
  );
}
