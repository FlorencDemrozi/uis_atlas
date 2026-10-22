#!/usr/bin/env python3
"""
Local review page for stage 2 output (not the public website).

Input:  config.PROFILES, papers in config.RAW_ATLAS
Output: config.REVIEW_DIR / "preview.html" – contains licensed data, local only.
        Opens it in the default browser.
"""
import json
import webbrowser

import config

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Atlas profiles – local review</title>
<style>
 :root { --fg:#1d1d1f; --muted:#5f6368; --line:#d9dce1; --bg:#fff; --soft:#f4f5f7; --accent:#0b5cad; }
 * { box-sizing:border-box }
 body { margin:0; font:15px/1.5 system-ui, sans-serif; color:var(--fg); background:var(--bg) }
 header { padding:20px 24px 12px; border-bottom:1px solid var(--line); position:sticky; top:0; background:var(--bg); z-index:1 }
 h1 { font-size:20px; margin:0 0 4px } .note { color:var(--muted); font-size:13px; margin:0 0 12px }
 .controls { display:flex; flex-wrap:wrap; gap:8px }
 input, select { font:inherit; padding:8px 10px; border:1px solid var(--line); border-radius:6px }
 input { flex:1 1 280px }
 main { padding:16px 24px; max-width:1100px }
 .count { color:var(--muted); margin:0 0 12px }
 details { border-bottom:1px solid var(--line); padding:10px 0 }
 summary { cursor:pointer; display:flex; gap:12px; flex-wrap:wrap; align-items:baseline }
 summary b { font-size:16px } .dept, .nums { color:var(--muted); font-size:13px }
 .kw { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0 }
 .kw span { background:var(--soft); border-radius:4px; padding:2px 8px; font-size:13px }
 ol { margin:6px 0; padding-left:22px } li { margin:2px 0 }
 a { color:var(--accent) } :focus-visible { outline:3px solid var(--accent); outline-offset:2px }
 .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:4px 24px; font-size:14px }
 h3 { font-size:13px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); margin:12px 0 4px }
</style></head><body>
<header>
 <h1>Atlas researcher profiles – local review</h1>
 <p class="note">Stage 2 output, generated __GENERATED__. Inclusion: ≥__MIN__ papers since __FROM__.
 Licensed data – local only, do not share.</p>
 <div class="controls">
  <label class="sr" for="q" hidden>Search</label>
  <input id="q" type="search" placeholder="Filter by name, keyword or paper title…" aria-label="Filter">
  <select id="dept" aria-label="Department"><option value="">All departments</option></select>
  <select id="sort" aria-label="Sort">
   <option value="name">Sort: name</option><option value="recent">Sort: recent papers</option>
   <option value="pubs">Sort: all papers</option><option value="cites">Sort: citations</option>
  </select>
 </div>
</header>
<main><p class="count" id="count" aria-live="polite"></p><div id="list"></div></main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const byId = Object.fromEntries(D.researchers.map(r => [r.scopus_id, r]));
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const depts = [...new Set(D.researchers.map(r => r.department))].sort();
const sel = document.getElementById("dept");
depts.forEach(d => sel.add(new Option(`${d} (${D.researchers.filter(r => r.department === d).length})`, d)));
D.researchers.forEach(r => r._text = [r.name, ...r.keywords.map(k => k[0]),
  ...r.paper_ids.map(p => D.papers[p]?.title || "")].join(" ").toLowerCase());

function card(r) {
  const papers = r.paper_ids.map(p => {
    const x = D.papers[p] || {};
    const link = x.doi ? `<a href="https://doi.org/${esc(x.doi)}">${esc(x.title)}</a>` : esc(x.title);
    return `<li>${link} <span class="dept">— ${esc(x.year)}, ${esc(x.venue)} · ${x.citations ?? 0} cit.</span></li>`;
  }).join("");
  const co = r.top_coauthors.map(c => `${esc(c.name)} (${c.n_papers})`).join(", ") || "—";
  const cd = Object.entries(r.collab_departments).map(([d, n]) => `${esc(d)} (${n})`).join(", ") || "—";
  const years = Object.entries(r.pubs_per_year).map(([y, n]) => `${y}: ${n}`).join(" · ");
  const links = [`<a href="https://www.scopus.com/authid/detail.uri?authorId=${r.scopus_id}">Scopus</a>`,
    r.orcid ? `<a href="https://orcid.org/${esc(r.orcid)}">ORCID</a>` : ""].filter(Boolean).join(" · ");
  return `<details><summary><b>${esc(r.name)}</b><span class="dept">${esc(r.department)}</span>
    <span class="nums">${r.n_recent} recent · ${r.n_publications} papers · ${r.citations} citations · ${r.first_year}–${r.last_year}</span></summary>
    <div class="kw">${r.keywords.slice(0, 15).map(k => `<span>${esc(k[0])} (${k[1]})</span>`).join("")}</div>
    <div class="grid"><div><h3>UiS co-authors</h3>${co}</div><div><h3>Collaborating departments</h3>${cd}</div>
    <div><h3>Per year</h3>${years}</div><div><h3>Links</h3>${links}
    ${r.scopus_ids.length > 1 ? `<br><span class="dept">Merged IDs: ${r.scopus_ids.join(", ")}</span>` : ""}</div></div>
    <h3>Papers</h3><ol>${papers}</ol></details>`;
}
function render() {
  const q = document.getElementById("q").value.trim().toLowerCase().split(/\\s+/).filter(Boolean);
  const d = sel.value, s = document.getElementById("sort").value;
  const key = {name: r => r.name, recent: r => -r.n_recent, pubs: r => -r.n_publications, cites: r => -r.citations}[s];
  const rows = D.researchers.filter(r => (!d || r.department === d) && q.every(t => r._text.includes(t)))
    .sort((a, b) => { const x = key(a), y = key(b); return x < y ? -1 : x > y ? 1 : 0; });
  document.getElementById("count").textContent = `${rows.length} of ${D.researchers.length} researchers`;
  document.getElementById("list").innerHTML = rows.map(card).join("");
}
["q", "dept", "sort"].forEach(id => document.getElementById(id).addEventListener("input", render));
render();
</script></body></html>"""

PAPER_FIELDS = ["title", "year", "venue", "doi", "citations"]  # no abstracts on the page


def main() -> None:
    profiles = json.loads(config.PROFILES.read_text(encoding="utf-8"))
    atlas = json.loads(config.RAW_ATLAS.read_text(encoding="utf-8"))
    used = {p for r in profiles["researchers"] for p in r["paper_ids"]}
    papers = {p: {k: atlas["papers"][p].get(k) for k in PAPER_FIELDS} for p in used}
    data = json.dumps({"researchers": profiles["researchers"], "papers": papers}, ensure_ascii=False)
    html = (PAGE.replace("__DATA__", data.replace("</", "<\\/"))
                .replace("__GENERATED__", profiles["generated"])
                .replace("__MIN__", str(profiles["min_recent_publications"]))
                .replace("__FROM__", str(profiles["recent_from"])))
    out = config.REVIEW_DIR / "preview.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out} (local only). Opening in your browser…")
    webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
