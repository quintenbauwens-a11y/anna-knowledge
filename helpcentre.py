"""
Help centre pages for Anna (Contentful content type helpCentreArticle).

Per shop with "helpcentre": {"enabled": true, ...} in config/shops.json:
  help/<shop>/<article-url>/index.html  +  help/<shop>/sitemap.xml

Only deterministic clean-up, no rewriting:
  - articles in excluded categories (test/internal) or covered by an Engaige policy are left out
    (config/helpcentre.json -> exclude_categories / exclude_articles)
  - "held" articles are left out only while their text still contains a known wrong phrase;
    once the content team fixes the article it comes back by itself (the report says so)
  - sentences that only send the customer to customer service ("contact us", "get in touch")
    are removed, because Anna IS customer service. Every removed sentence is listed in the report.
  - link placeholders ({{my_account_url}} ...) are filled per shop; unknown ones lose the link
    but keep their text
  - a shop only gets the language versions listed in its "locales" (no fallback to another shop's text)
"""
import hashlib, html, json, os, re
from xml.sax.saxutils import escape as xml_escape

CT = "helpCentreArticle"
TOKEN = re.compile(r"\{\{\s*([a-zA-Z_]+)(?:\|[a-z]+)?\s*\}\}")
LABELS = {
    "en": {"title": "help centre", "page": "Help centre article on {shop}", "cat": "Category",
           "footer": "Generated from Contentful (help centre entry {id}) for Anna's knowledge base."},
    "nl": {"title": "klantenservice", "page": "Klantenservice-artikel op {shop}", "cat": "Categorie",
           "footer": "Gegenereerd uit Contentful (klantenservice-item {id}) voor Anna's kennisbank."},
    "fr": {"title": "centre d'aide", "page": "Article du centre d'aide sur {shop}", "cat": "Catégorie",
           "footer": "Généré depuis Contentful (article d'aide {id}) pour la base de connaissances d'Anna."},
    "de": {"title": "Hilfecenter", "page": "Hilfecenter-Artikel auf {shop}", "cat": "Kategorie",
           "footer": "Aus Contentful erzeugt (Hilfecenter-Eintrag {id}) für Annas Wissensdatenbank."},
    "es": {"title": "centro de ayuda", "page": "Artículo del centro de ayuda en {shop}", "cat": "Categoría",
           "footer": "Generado desde Contentful (artículo de ayuda {id}) para la base de conocimiento de Anna."},
    "sv": {"title": "hjälpcenter", "page": "Hjälpcenterartikel på {shop}", "cat": "Kategori",
           "footer": "Genererad från Contentful (hjälpcenterpost {id}) för Annas kunskapsbas."},
    "it": {"title": "centro assistenza", "page": "Articolo del centro assistenza su {shop}", "cat": "Categoria",
           "footer": "Generato da Contentful (voce del centro assistenza {id}) per la knowledge base di Anna."},
}
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý<\"'(])")


def load_config(root):
    cfg = json.load(open(os.path.join(root, "config", "helpcentre.json"), encoding="utf-8"))
    cfg["_ref"] = {lang: [re.compile(p, re.I) for p in ps] for lang, ps in cfg.get("referral_patterns", {}).items()}
    cfg["_clause"] = {lang: [re.compile(p, re.I) for p in ps] for lang, ps in cfg.get("referral_clauses", {}).items()}
    return cfg


def pick(byloc, chain):
    """Value of a localized field for the first locale in the shop's chain (no other fallback)."""
    if not isinstance(byloc, dict):
        return None
    for loc in chain:
        v = byloc.get(loc)
        if v not in (None, "", {}):
            return v
    return None


class Renderer:
    def __init__(self, shop, hc, cfg, stats):
        self.shop, self.hc, self.cfg, self.stats = shop, hc, cfg, stats
        self.lang = shop.get("lang", "en")
        self.ref = cfg["_ref"].get(self.lang, [])
        self.clause = cfg["_clause"].get(self.lang, [])
        self.removed = []  # sentences taken out (for the report)

    # ---- placeholders -------------------------------------------------------------------
    def text_vars(self, s):
        def sub(m):
            k = m.group(1)
            v = self.shop.get("template_vars", {}).get(k)
            if v is None:
                self.stats.setdefault("unknown placeholders", {}).setdefault(k, 0)
                self.stats["unknown placeholders"][k] += 1
                return ""
            return v
        return TOKEN.sub(sub, s or "")

    def href(self, uri):
        """Filled link, or None to drop the link (keep its text)."""
        if not uri:
            return None
        tokens = TOKEN.findall(uri)
        for t in tokens:
            if t in self.cfg.get("contact_tokens", []):
                return None
            if t not in self.hc.get("link_vars", {}) and t not in self.shop.get("template_vars", {}):
                return None
        out = TOKEN.sub(lambda m: self.hc.get("link_vars", {}).get(m.group(1)) or self.shop["template_vars"].get(m.group(1), ""), uri)
        return out if re.match(r"^(https?:|mailto:|tel:)", out) else None

    # ---- rich text -> html ---------------------------------------------------------------
    def inline(self, nodes):
        out = []
        for n in nodes or []:
            nt = n.get("nodeType")
            if nt == "text":
                t = html.escape(self.text_vars(n.get("value", "")))
                for m in n.get("marks") or []:
                    tag = {"bold": "strong", "italic": "em", "underline": "u", "code": "code"}.get(m.get("type"))
                    if tag:
                        t = f"<{tag}>{t}</{tag}>"
                out.append(t)
            elif nt == "hyperlink":
                inner = self.inline(n.get("content"))
                h = self.href((n.get("data") or {}).get("uri"))
                if h:
                    out.append(f'<a href="{html.escape(h)}" data-contact="0">{inner}</a>')
                else:
                    raw = (n.get("data") or {}).get("uri") or ""
                    is_contact = any(t in self.cfg.get("contact_tokens", []) for t in TOKEN.findall(raw))
                    out.append(f'<span data-contact="{1 if is_contact else 0}">{inner}</span>')
            else:  # entry-hyperlink, inline entries etc.: keep the text only
                out.append(self.inline(n.get("content")))
        return "".join(out)

    def clean_block(self, inner):
        """Drop sentences that only refer the customer to customer service."""
        for c in self.clause:
            inner2 = c.sub("", inner)
            if inner2 != inner:
                self.removed.append(re.sub(r"<[^>]+>", "", c.search(inner).group(0)).strip(" ,"))
                inner = inner2
        keep = []
        for s in SENT_SPLIT.split(inner):
            txt = html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
            if txt and any(p.search(txt) for p in self.ref) and not (self.cfg.get("referral_keep_if_digits") and re.search(r"\d", txt)):
                # a lead-in question right before it ("Refund not arrived after 8 days?") goes too
                if keep and html.unescape(re.sub(r"<[^>]+>", "", keep[-1])).strip().endswith("?"):
                    txt = html.unescape(re.sub(r"<[^>]+>", "", keep.pop())).strip() + " " + txt
                self.removed.append(txt)
                continue
            keep.append(s)
        out = " ".join(keep).strip()
        out = re.sub(r'<span data-contact="\d">(.*?)</span>', r"\1", out)  # unwrap dropped links
        out = out.replace(' data-contact="0"', "")
        return out

    def blocks(self, nodes, depth=0):
        out = []
        for n in nodes or []:
            nt = n.get("nodeType", "")
            if nt == "paragraph":
                b = self.clean_block(self.inline(n.get("content")))
                if re.sub(r"<[^>]+>|\s", "", b):
                    out.append(f"<p>{b}</p>")
            elif nt.startswith("heading-"):
                lvl = min(6, int(nt.split("-")[1]) + 1)
                t = self.inline(n.get("content"))
                t = re.sub(r'<span data-contact="\d">(.*?)</span>', r"\1", t).replace(' data-contact="0"', "")
                if t.strip():
                    out.append(f"<h{lvl}>{t}</h{lvl}>")
            elif nt in ("unordered-list", "ordered-list"):
                tag = "ul" if nt == "unordered-list" else "ol"
                items = []
                for li in n.get("content") or []:
                    parts = []
                    for c in li.get("content") or []:
                        if c.get("nodeType") == "paragraph":
                            b = self.clean_block(self.inline(c.get("content")))
                            if re.sub(r"<[^>]+>|\s", "", b):
                                parts.append(b)
                        else:
                            parts.append(self.blocks([c], depth + 1))
                    if "".join(parts).strip():
                        items.append("<li>" + " ".join(parts) + "</li>")
                if items:
                    out.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            elif nt == "blockquote":
                inner = self.blocks(n.get("content"), depth + 1)
                if inner:
                    out.append(f"<blockquote>{inner}</blockquote>")
            elif nt == "hr":
                out.append("<hr>")
            elif nt == "table":
                rows = []
                for r in n.get("content") or []:
                    cells = []
                    for c in r.get("content") or []:
                        tag = "th" if c.get("nodeType") == "table-header-cell" else "td"
                        cells.append(f"<{tag}>{self.blocks(c.get('content'), depth + 1)}</{tag}>")
                    rows.append("<tr>" + "".join(cells) + "</tr>")
                out.append("<table>" + "".join(rows) + "</table>")
            # embedded entries / assets: nothing Anna can use
        return "\n".join(out)


def plain(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def page_html(shop, title, url, cat, body, entry_id):
    e = html.escape
    L = LABELS.get(shop.get("lang"), LABELS["en"])
    out = [f'<!doctype html><html lang="{e(shop["locale"])}"><head><meta charset="utf-8">',
           f"<title>{e(title)} – {L['title']} – {e(shop['name'])}</title>",
           f'<meta name="description" content="{e(plain(body)[:300])}"></head><body>',
           f"<h1>{e(title)}</h1>",
           f"<p><strong>{e(L['page'].format(shop=shop['name']))}:</strong> <a href=\"{e(url)}\">{e(url)}</a></p>"]
    if cat:
        out.append(f"<p><strong>{L['cat']}:</strong> {e(cat)}</p>")
    out.append(body)
    out.append(f"<hr><p><small>{e(L['footer'].format(id=entry_id))}</small></p></body></html>")
    return "\n".join(out)


def build_help(src, shop, cfg, report, out_dir, site_url, today):
    """Returns (pages written, sitemap url). Report details go to report.help[shop id]."""
    hc = shop["helpcentre"]
    chain = hc["locales"]
    stats = {"built": 0}
    info = {"stats": stats, "excluded": [], "held": [], "released": [], "removed": []}
    report.help[shop["id"]] = info
    entries = src.entries_all_locales(CT)
    cats = {}
    cat_ids = {(e["fields"].get("category") or {}).get("en", {}).get("sys", {}).get("id") for e in entries}
    cat_ids.discard(None)
    if hasattr(src, "entries_all_locales"):
        for c in src.entries_all_locales("helpCentreCategory"):
            if c["id"] in cat_ids:
                cats[c["id"]] = c
    built, seen = [], set()
    holds = {h["id"]: h for h in cfg.get("hold", [])}
    for e in sorted(entries, key=lambda x: x["id"]):
        f = e["fields"]
        cat_id = ((f.get("category") or {}).get("en") or {}).get("sys", {}).get("id")
        title = pick(f.get("title"), chain)
        slug = pick(f.get("url"), chain)
        body = pick(f.get("body"), chain)
        if hc.get("url") == "cs" and not e["id"].startswith("hcArt-"):  # new-website-only article
            stats["only on the new help centre"] = stats.get("only on the new help centre", 0) + 1
            continue
        if not (title and slug and body):
            stats["not on this shop (no text in its language)"] = stats.get("not on this shop (no text in its language)", 0) + 1
            continue
        robots = pick(f.get("robots"), chain) or ""
        if cat_id in cfg.get("exclude_categories", {}):
            stats["internal/test category"] = stats.get("internal/test category", 0) + 1
            continue
        if robots.startswith("noindex"):
            stats["noindex"] = stats.get("noindex", 0) + 1
            continue
        exa = cfg.get("exclude_articles", {}).get(e["id"])
        if exa and ("shops" not in exa or shop["id"] in exa["shops"]):
            stats["covered by a policy"] = stats.get("covered by a policy", 0) + 1
            info["excluded"].append((title, cfg["exclude_articles"][e["id"]].get("covered_by", "")))
            continue
        slug = slug.strip("/")
        if not slug or "/" in slug or slug in seen:
            stats["duplicate or unusable URL"] = stats.get("duplicate or unusable URL", 0) + 1
            continue
        r = Renderer(shop, hc, cfg, stats)
        body_html = r.blocks(body.get("content") if isinstance(body, dict) else [])
        title = r.text_vars(title)
        if e["id"] in holds:
            text = plain(body_html).lower().replace("–", "-")
            h = holds[e["id"]]
            if any(p.lower() in text for p in h.get("while_contains", [])):
                stats["held back (known wrong text)"] = stats.get("held back (known wrong text)", 0) + 1
                info["held"].append((title, h.get("reason", "")))
                continue
            info["released"].append((title, h.get("reason", "")))
        if not plain(body_html):
            stats["empty after clean-up"] = stats.get("empty after clean-up", 0) + 1
            continue
        seen.add(slug)
        info["removed"] += [(title, s) for s in r.removed]
        cat_name = None
        if cat_id in cats:
            cat_name = pick(cats[cat_id]["fields"].get("title") or cats[cat_id]["fields"].get("name"), chain)
        if hc.get("url") == "cs":  # old help centre: /cs/articles/<number of hcArt-<number>>
            url = f"{shop['url_prefix']}/cs/articles/{e['id'].split('-', 1)[1]}"
        else:
            url = f"{shop['url_prefix']}/{hc.get('path', 'help-centre')}/{slug}"
        d = os.path.join(out_dir, "help", shop["id"], slug)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(page_html(shop, title, url, cat_name, body_html, e["id"]))
        built.append((slug, e.get("updated")))
    base = f"{site_url}/help/{shop['id']}"
    os.makedirs(os.path.join(out_dir, "help", shop["id"]), exist_ok=True)
    with open(os.path.join(out_dir, "help", shop["id"], "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for slug, upd in sorted(built):
            fh.write(f"  <url><loc>{xml_escape(base + '/' + slug + '/')}</loc><lastmod>{(upd or today)[:10]}</lastmod></url>\n")
        fh.write("</urlset>\n")
    stats["built"] = len(built)
    return len(built), base + "/sitemap.xml"


def report_html(report):
    e = html.escape
    out = []
    for sid, info in getattr(report, "help", {}).items():
        out.append(f"<h3>{e(sid)}</h3><p>" + ", ".join(f"{e(k)}: {v}" for k, v in info["stats"].items() if not isinstance(v, dict)) + "</p>")
        if info["stats"].get("unknown placeholders"):
            out.append("<p>Unknown placeholders (removed): " + ", ".join(f"{{{{{e(k)}}}}} {v}×" for k, v in info["stats"]["unknown placeholders"].items()) + "</p>")
        if info["released"]:
            out.append("<p><strong>⚠️ Held-back article changed in Contentful and is included again – check the Anna-only answer:</strong></p><ul>"
                       + "".join(f"<li>{e(t)} – {e(r)}</li>" for t, r in info["released"]) + "</ul>")
        if info["held"]:
            out.append("<p>Held back (known wrong text):</p><ul>" + "".join(f"<li>{e(t)} – {e(r)}</li>" for t, r in info["held"]) + "</ul>")
        if info["removed"]:
            out.append(f"<details><summary>Sentences removed because they refer to customer service ({len(info['removed'])})</summary><ul>"
                       + "".join(f"<li><em>{e(t)}</em>: {e(s)}</li>" for t, s in info["removed"]) + "</ul></details>")
        if info["excluded"]:
            out.append(f"<details><summary>Left out because a policy covers them ({len(info['excluded'])})</summary><ul>"
                       + "".join(f"<li>{e(t)} → {e(p)}</li>" for t, p in info["excluded"]) + "</ul></details>")
    return "".join(out)
