# Visual redesign brief (saved 2026-11-05, not started)

Status: **implemented 2026-11-05** (awaiting review). Decisions taken with the owner:
fonts self-hosted (`@fontsource`, no Google Fonts, no CSP change); sepia values chosen
by Claude and AA-checked; the Search view restyled too. Department colours were
re-chosen so that they reach 3:1 against the page in every theme and stay apart for
deutan/protan vision. Saved as pasted below; a few phrases were cut off in the paste
and are marked *[cut off]*.

---

Using /ui-ux-pro-max:design, restyle the UiS Researcher Atlas
(https://florencdemrozi.github.io/uis_atlas/) in the same clean editorial academic style
as https://florencdemrozi.github.io. This is a visual redesign only: keep every view,
route, feature, the data and the EN/NB translations working exactly as they do now.

Views to restyle: Overview, Network, Researcher profile (`#/r/<id>`), Shortlist, Funding,
Call, Feedback.

## Typography

- Headings: Spectral (serif, 400–500, slightly tight letter-spacing)
- Body/UI: Public Sans (400–700), line-height ~1.65
- Numbers, IDs, counts, metrics: IBM Plex Mono with tabular figures
- Load from Google Fonts with preconnect; keep the s *[cut off]*

## Colour

Keep the existing token names (`--page`, `--sur` *[cut off]* `--brand`, `--accent`,
`--accent-wash`, `--mark`, `--good`, `--caution`, `--bad`, ...) and change only their values.

- Light: page `#FFFFFF`, surface `#F4F6FA`, ink `#16181D`, brand/accent `#2343A0`,
  accent-wash `#E6EBF8`, highlight gold `#9A6B00`
- Dark: page `#121419`, surface `#1A1D24`, ink `#E7E9EE`, accent `#8EA6EE`, gold `#D9A93F`
- Add a third sepia "paper" theme: page `#F6F0E4`, ink *[cut off]*
- Status colours (good/caution/bad) and department colours must stay distinguishable
  and reach WCAG AA in every theme

## Theme switch

- Turn the existing light/dark toggle into an icon-only button that cycles
  light / dark / sepia
- Keep the `atlas-theme` localStorage key and the pre-paint script, so the wrong theme
  never flashes on load

## Layout

- One-line top bar: "UiS Researcher Atlas" in serif, the view links, EN/NB, theme icon.
  It must never wrap; on narrow screens collapse it
- Each view gets a page hero: large serif H1 and a short muted subtitle
- Separate sections with thin rules and whitespace i *[cut off]* ack outlines
- Search and filters: calm inputs and an accent focus ring; results as dense, scannable rows
  (name, faculty/department, topics, metrics in mono *[cut off]*
- Profile: serif name, title and faculty, then sections for topics, publications,
  collaborators and the collaboration map
- Shortlist and Funding/Call: tidy tables or lists with mono numbers and clear status chips

## Network graph and maps

- Pan by dragging; zoom with the mouse wheel and *[cut off]* er gestures
- Node, edge and label colours come from the theme tokens, so they work in all three themes
- Keep the department-colour legend and the external *[cut off]*

## Quality

- Fully responsive with no horizontal scroll; at least a 16px gutter on mobile
- Visible keyboard focus; honour reduced motion
- Keep the `noindex` meta tag until the data-policy approval
- No neumorphism, decorative gradients or app-landin *[cut off — presumably "app-landing-page styling"]*
- Run the build and check every view in both languages and all three themes before committing

---

## To clarify before starting

1. Fonts: "keep the s…" – keep the system-font fallback? keep the self-hosting option?
2. Token list: full name of `--sur…` (`--surface`?) and the rest of the list.
3. Sepia theme: ink colour and the other sepia values (surface, accent, gold).
4. Sections: "whitespace i… ack outlines" – presumably "instead of boxes / black outlines".
5. Results rows: end of the list after "metrics in mono".
6. Network: "…er gestures" – pinch / two-finger gestures on touch screens?
7. Network: "Keep the department-colour legend and the external …" – the external
   partner-institution nodes?
8. The Search view (front page) is not in the list of views – restyle it too?
9. Fonts from Google Fonts need the CSP in `deploy/nginx.conf.template` to allow
   `fonts.googleapis.com` (style-src) and `fonts.gstatic.com` (font-src), or the fonts
   must be self-hosted; loading them also sends visitors' IP addresses to Google.
