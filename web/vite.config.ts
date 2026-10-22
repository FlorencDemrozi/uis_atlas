import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

// base "./" so the built site works from any folder (GitHub Pages, UiS web server).
export default defineConfig({
  base: "./",
  plugins: [preact()],
});
