import { render } from "preact";
import { App } from "./app";
// Self-hosted fonts (bundled by Vite, no third-party requests; docs/REDESIGN.md).
// Each file covers all scripts via unicode-range: browsers fetch only what a page uses.
import "@fontsource/spectral/400.css";
import "@fontsource/spectral/500.css";
import "@fontsource/spectral/400-italic.css";
import "@fontsource-variable/public-sans";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./theme.css";

render(<App />, document.getElementById("app")!);
