"""Parsing helpers for Research Council of Norway (RCN, forskningsradet.no) pages.

The site renders its pages from JSON props embedded in the HTML
(window.__REACT_COMPONENTS__.push({name: "...", props: {...}})). We read those
props instead of scraping markup. Pure functions only, so they can be tested on
saved pages without network access.
"""
import html as htmllib
import json
import re
from html.parser import HTMLParser

BASE_URL = "https://www.forskningsradet.no"

MONTHS = {  # Norwegian and English month names/abbreviations
    "jan": 1, "januar": 1, "january": 1, "feb": 2, "februar": 2, "february": 2,
    "mar": 3, "mars": 3, "march": 3, "apr": 4, "april": 4, "mai": 5, "may": 5,
    "jun": 6, "juni": 6, "june": 6, "jul": 7, "juli": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "okt": 10, "oktober": 10, "oct": 10, "october": 10, "nov": 11, "november": 11,
    "des": 12, "desember": 12, "dec": 12, "december": 12,
}


def react_props(page: str, name_suffix: str) -> dict | None:
    """Props of the first embedded React component whose name ends with name_suffix."""
    for m in re.finditer(r'name:\s*"(\w+)",\s*props:\s*', page):
        if m.group(1).endswith(name_suffix):
            obj, _ = json.JSONDecoder().raw_decode(page, m.end())
            return obj
    return None


def english_url(page: str) -> str | None:
    m = re.search(r'href="(/en/call-for-proposals/[^"]+)"', page)
    return BASE_URL + htmllib.unescape(m.group(1)) if m else None


class _Text(HTMLParser):
    """HTML fragment -> plain text with list items on their own lines, plus links."""
    BLOCK = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "ul", "ol"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[dict] = []
        self._href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK:
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n• ")
        elif tag == "a":
            self._href = dict(attrs).get("href")
            self._link_text = []

    def handle_endtag(self, tag):
        if tag in self.BLOCK or tag == "li":
            self.parts.append("\n")
        elif tag == "a" and self._href:
            text = " ".join("".join(self._link_text).split())
            self.links.append({"text": text, "url": absolute(self._href)})
            self._href = None

    def handle_data(self, data):
        self.parts.append(data)
        if self._href is not None:
            self._link_text.append(data)


def absolute(url: str) -> str:
    return BASE_URL + url if url.startswith("/") else url


def html_text(fragment: str) -> tuple[str, list[dict]]:
    p = _Text()
    p.feed(fragment or "")
    lines = [" ".join(line.replace("\xa0", " ").split()) for line in "".join(p.parts).split("\n")]
    text = "\n".join(line for line in lines if line and line != "•")
    return text, p.links


def blocks_html(blocks: dict | None) -> str:
    """Concatenate the HtmlString blocks of an RCN content area."""
    out = []
    for b in (blocks or {}).get("blocks", []):
        data = b.get("componentData") or {}
        if isinstance(data.get("text"), str):
            out.append(data["text"])
        elif isinstance(data.get("text"), dict):
            out.append(blocks_html(data["text"]))
    return "\n".join(out)


HEADING = re.compile(r"<h([2-5])[^>]*>(.*?)</h\1>", re.S | re.I)


def _split_headings(path: list[str], fragment: str) -> list[dict]:
    """One passage per heading inside an HTML fragment (headings extend the path)."""
    out = []
    pieces = HEADING.split(fragment or "")
    # pieces: [before, level, heading, body, level, heading, body, ...]
    chunks = [(path, pieces[0])]
    for k in range(1, len(pieces), 3):
        heading = clean(html_text(pieces[k + 1])[0])
        chunks.append((path + [heading] if heading else path, pieces[k + 2]))
    for p, frag in chunks:
        text, links = html_text(frag)
        if text:
            out.append({"path": p, "text": text, "links": links})
    return out


def sections(props: dict) -> list[dict]:
    """Flatten the call text into [{"path": [section, subsection, ...], "text", "links"}].

    Two page layouts exist: structured calls ("TibiProposalPage": tabs with
    sections and subsections) and simpler pages, mostly international joint
    calls ("ProposalPage": one description with headings inside)."""
    out = []
    for tab in props.get("tabs", {}).get("items", []):
        content = tab.get("content") or {}
        for key in ("tibi", "proposal"):
            if key not in content:
                continue
            for sec in content[key].get("contentSections", []):
                title = clean(sec.get("sectionTitle"))
                out += _split_headings([title], blocks_html(sec.get("sectionText")))
                for sub in sec.get("subSections", []):
                    out += _split_headings([title, clean(sub.get("title")) or title], blocks_html(sub.get("text")))
    if "descriptionText" in props:
        title = clean(props.get("descriptionTitle")) or "Description"
        out += _split_headings([title], blocks_html(props["descriptionText"]))
    return out


def preamble(props: dict) -> str:
    if isinstance(props.get("descriptionIngress"), str):
        return clean(html_text(props["descriptionIngress"])[0])
    return clean(html_text(blocks_html(props.get("preamble")))[0])


def byline_dates(props: dict) -> dict[str, str]:
    """{"published": iso, "updated": iso} from 'Publisert 21. jan. 2026' etc."""
    out = {}
    for item in ((props.get("header") or {}).get("byline") or {}).get("items", []):
        text = clean(item.get("text")).lower()
        key = ("published" if text.startswith(("publisert", "published"))
               else "updated" if text.startswith(("oppdatert", "updated")) else None)
        if key and parse_date(text):
            out[key] = parse_date(text)
    return out


def timeline(props: dict) -> list[dict]:
    out = []
    for item in (props.get("timelineHorizontal") or {}).get("items", []):
        label = clean(item.get("subTitle")) or clean(html_text(blocks_html(item.get("text")))[0])[:120]
        date = parse_date(clean(item.get("title")))
        if date:
            out.append({"label": label, "date": date})
    return out


def clean(s: str | None) -> str:
    return " ".join(htmllib.unescape(s or "").replace("\xa0", " ").split())


def metadata(props: dict) -> dict[str, str]:
    """Label -> text from the metadata boxes at the top of a call page."""
    out = {}
    for box in ("metadataLeft", "metadataRight", "arbitraryMetadata"):
        for item in (props.get(box) or {}).get("items", []):
            label, text = clean(item.get("label")), item.get("text")
            if isinstance(text, list):
                text = "; ".join(clean(t if isinstance(t, str) else " ".join(t)) for t in text)
            if label and text:
                out[label] = clean(text)
    return out


# ---------------------------------------------------------------- values
MONEY = re.compile(r"(kr\.?|nok|€|eur)\s*(\d[\d ]*\d|\d)(?:\s*[-–]\s*(\d[\d ]*\d|\d))?")


def parse_money(text: str | None) -> dict:
    """RCN amount field -> {"min", "max"} or {"value"}, plus "currency".

    'Kr 4 000 000-14 000 000' -> min/max; 'inntil kr 500 000' -> max;
    'minimum kr 100 000' -> min; 'Kr 118 000 000. 5 mill. kroner er …' -> value
    (only the leading figure counts; the rest is RCN's comment)."""
    if not text:
        return {}
    t = text.lower().replace("\xa0", " ")
    m = MONEY.search(t)
    if not m:
        return {}
    num = lambda g: int(g.replace(" ", ""))
    out = {"currency": "EUR" if m.group(1) in ("€", "eur") else "NOK"}
    before = t[:m.start()]
    if m.group(3):
        out.update(min=num(m.group(2)), max=num(m.group(3)))
    elif re.search(r"inntil|up to|maks", before):
        out["max"] = num(m.group(2))
    elif re.search(r"minimum|minst|at least", before):
        out["min"] = num(m.group(2))
    else:
        out["value"] = num(m.group(2))
    return out


def parse_months(text: str | None) -> dict:
    """'36-72 måneder' -> {"min": 36, "max": 72}; 'maksimum 12 måneder' -> {"max": 12}."""
    if not text:
        return {}
    t = text.lower()
    nums = [int(n) for n in re.findall(r"\d+", t)]
    if re.search(r"\bår\b|\byears?\b", t) and not re.search(r"måned|month", t):
        nums = [n * 12 for n in nums]
    if len(nums) >= 2:
        return {"min": min(nums[:2]), "max": max(nums[:2])}
    if len(nums) == 1:
        return {"min": nums[0]} if re.search(r"minimum|minst|at least", t) else {"max": nums[0]}
    return {}


def parse_date(text: str | None) -> str | None:
    """'27. mai 2026, kl. 13.00 CEST' -> '2026-05-27T13:00'; '1. jan. 2027' -> '2027-01-01'."""
    if not text:
        return None
    t = text.lower()
    m = re.search(r"(\d{1,2})\.?\s+([a-zæøå]+)\.?\s+(\d{4})", t)
    if not m or m.group(2) not in MONTHS:
        m2 = re.search(r"([a-z]+)\s+(\d{1,2}),?\s+(\d{4})", t)  # English "May 27, 2026"
        if not m2 or m2.group(1) not in MONTHS:
            return None
        day, month, year = int(m2.group(2)), MONTHS[m2.group(1)], int(m2.group(3))
    else:
        day, month, year = int(m.group(1)), MONTHS[m.group(2)], int(m.group(3))
    out = f"{year:04d}-{month:02d}-{day:02d}"
    tm = re.search(r"(?:kl\.?|at)\s*(\d{1,2})[.:](\d{2})", t)
    if tm:
        out += f"T{int(tm.group(1)):02d}:{tm.group(2)}"
    return out
