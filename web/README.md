# Website

Static single-page app (Vite + TypeScript + Preact). It reads only the
licence-safe export in `data/public/` (written by `pipeline/export_public.py`),
which `scripts/sync-data.mjs` copies to `public/data/` (gitignored) on every
`dev` and `build`.

```powershell
python pipeline\build_profiles.py    # stage 2
python pipeline\export_public.py     # stage 5 – refresh data/public/
cd web
npm install
npm run dev                          # http://localhost:5173
npm run build                        # static site in web/dist/
```

Layout:

```
web/
  index.html
  scripts/sync-data.mjs  ← copies data/public/ into public/data/
  src/
    main.tsx, app.tsx    ← shell: header, routing (hash URLs), footer
    theme.css            ← ALL colours and fonts (swap in UiS brand here)
    departments.ts       ← department colours (fixed slots) and nb/en names
    data.ts              ← loads and types the public JSON
    search.ts            ← affinity ranking (keyword now, semantic later)
    search-config.json   ← shared settings, must match pipeline/config.py
    components/          ← charts (bar list, columns, heatmap), helpers
    views/               ← Search, Overview, Network, Profile
    i18n/                ← nb.json, en.json
```

Notes:
- Department colours are a validated colour-blind-safe palette; if you change
  them, re-validate and keep the fixed order (colour follows the department).
- Every chart has visible values or a table view; the network has a keyboard-
  accessible "most connected" table.
- Semantic search (multilingual-e5-small in the browser) is added once stage 4
  produces `vectors.bin`.
