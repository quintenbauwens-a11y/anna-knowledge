#!/usr/bin/env python3
"""
Anna knowledge site builder — categories (+ products for shops with "products": true, see products.py).

Reads Helloprint category pages from Contentful (Content Delivery API, published content only),
keeps the blocks that are visible on each shop, cleans them up and writes one plain HTML page per
category per shop, plus a sitemap per shop that Engaige's "Sitemap" knowledge folder can sync from.

Usage
  python build.py                      # live: needs CONTENTFUL_SPACE_ID + CONTENTFUL_CDA_TOKEN
  python build.py --fixture store.json # offline test with an exported entry store
Options
  --out _site          output folder (default _site)
  --site-url URL       public base URL of the site (for the sitemap), e.g. https://user.github.io/anna-knowledge
  --only slug,slug     build only these category slugs (testing)
"""
import argparse, datetime as dt, html, json, os, re, sys, time
from xml.sax.saxutils import escape as xml_escape

import markdown  # pip install markdown
import requests  # pip install requests

ROOT = os.path.dirname(os.path.abspath(__file__))
CATEGORY_TYPE = "pageHomeModular"
CATEGORY_VARIATION = "Category - Modular page"

# Block types (Contentful content type ids) and how they are used
TEXT_BLOCKS = {"homeBlockTypeAC", "homeBlockTypeS"}          # title + markdown content
FAQ_BLOCKS = {"homeBlockTypeV"}                               # title + faqItem -> questionAndAnswer
PRODUCT_BLOCKS = {"homeBlockTypeD", "homeBlockTypeAL"}        # title + description + products
LINK_BLOCKS = {"homeBlockTypeBI", "homeBlockTypeBH", "homeBlockTypeZ"}  # related categories
USP_BLOCKS = {"homeBlockTypeBB"}                              # title + subtitle + icon grid items
PERSONA_BLOCKS = {"homeBlockTypeN"}                           # "who is this for" tiles: title + description + subitems
FORM_BLOCKS = {"homeBlockTypeAW"}                             # contact form on the page (quote, design service...)
SKIPPED_BLOCKS = {  # layout / marketing blocks with nothing useful for customer service
    "homeBlockTypeAZ": "product filter", "homeBlockTypeP": "reviews", "homeBlockTypeAJ": "blog teasers",
    "homeBlockTypeA": "banner", "homeBlockTypeAI": "promo", "homeBlockTypeC": "brand logos",
    "homeBlockTypeG": "generic USPs", "homeBlockTypeBG": "promo cards",
    "homeBlockTypeAH": "in-page menu (anchor links)", "modBlockAHAnchorReference": "in-page menu anchor",
}


# --------------------------------------------------------------------------------------------
# Data sources. Both return "resolved" entries for ONE locale:
#   {"id", "type", "updated", "fields": {field: value}}  (links stay as {"sys": {"type": "Link", ...}})
# --------------------------------------------------------------------------------------------
class CDASource:
    """Contentful Content Delivery API. Only published content; locale fallbacks applied by Contentful."""

    def __init__(self, space, token, environment="master"):
        self.base = f"https://cdn.contentful.com/spaces/{space}/environments/{environment}"
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {token}"
        self.cache = {}  # (locale, id) -> entry

    def _get(self, params):
        for attempt in range(8):
            r = self.s.get(self.base + "/entries", params=params, timeout=60)
            if r.status_code == 429:
                time.sleep(float(r.headers.get("X-Contentful-RateLimit-Reset", 2 ** attempt)))
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("Contentful rate limit: gave up after retries")

    @staticmethod
    def _norm(e):
        sys_ = e["sys"]
        return {"id": sys_["id"], "type": sys_.get("contentType", {}).get("sys", {}).get("id"),
                "updated": sys_.get("updatedAt"), "fields": e.get("fields", {})}

    def _absorb(self, data, locale):
        for e in data.get("items", []) + data.get("includes", {}).get("Entry", []):
            self.cache[(locale, e["sys"]["id"])] = self._norm(e)

    def category_pages(self, locale):
        out, skip = [], 0
        while True:
            data = self._get({"content_type": CATEGORY_TYPE, "locale": locale, "include": 2, "limit": 40,
                              "skip": skip, "fields.analyticsPageTypeVariation": CATEGORY_VARIATION,
                              "order": "sys.id"})
            self._absorb(data, locale)
            out += [self._norm(e) for e in data["items"]]
            skip += len(data["items"])
            if skip >= data["total"] or not data["items"]:
                return out

    def entries(self, content_type, locale, page_size=30):
        """All published entries of one content type for one locale (linked entries 2 levels deep are cached too)."""
        out, skip = [], 0
        while True:
            data = self._get({"content_type": content_type, "locale": locale, "include": 2, "limit": page_size,
                              "skip": skip, "order": "sys.id"})
            self._absorb(data, locale)
            out += [self._norm(e) for e in data["items"]]
            skip += len(data["items"])
            if skip >= data["total"] or not data["items"]:
                return out

    def get(self, ids, locale):
        missing = [i for i in dict.fromkeys(ids) if (locale, i) not in self.cache]
        for k in range(0, len(missing), 100):
            chunk = missing[k:k + 100]
            data = self._get({"sys.id[in]": ",".join(chunk), "locale": locale, "include": 1, "limit": 1000})
            self._absorb(data, locale)
            for i in chunk:  # remember unknown/unpublished ids so we don't ask again
                self.cache.setdefault((locale, i), None)
        return {i: self.cache.get((locale, i)) for i in ids}


class FixtureSource:
    """Offline source: an exported multi-locale entry store (used for testing without the API key)."""
    FALLBACKS = {"en-IE": ["en-IE", "en"], "en-GB": ["en-GB", "en"], "en-US": ["en-US", "en"],
                 "it": ["it", "en"], "nl": ["nl", "en"], "nl-BE": ["nl-BE", "en"], "de-DE": ["de-DE", "en"],
                 "fr-FR": ["fr-FR", "en"], "fr-BE": ["fr-BE", "en"], "es-ES": ["es-ES", "en"], "sv-SE": ["sv-SE", "en"]}

    def __init__(self, path):
        self.store = json.load(open(path, encoding="utf-8"))

    def _resolve(self, e, locale):
        if not e or not e["sys"].get("published", True):
            return None
        chain = self.FALLBACKS.get(locale, [locale, "en"])
        fields = {}
        for f, byloc in e["fields"].items():
            for loc in chain:
                if loc in byloc:
                    fields[f] = byloc[loc]
                    break
        return {"id": e["sys"]["id"], "type": e["sys"]["contentType"], "updated": None, "fields": fields}

    def category_pages(self, locale):
        out = []
        for e in self.store.values():
            r = self._resolve(e, locale)
            if r and r["type"] == CATEGORY_TYPE and r["fields"].get("analyticsPageTypeVariation") == CATEGORY_VARIATION:
                out.append(r)
        return out

    def entries(self, content_type, locale, page_size=30):
        return [r for r in (self._resolve(e, locale) for e in self.store.values()) if r and r["type"] == content_type]

    def get(self, ids, locale):
        return {i: self._resolve(self.store.get(i), locale) for i in ids}


# --------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------
def link_ids(value):
    if isinstance(value, dict) and value.get("sys", {}).get("type") == "Link" and value["sys"].get("linkType") == "Entry":
        return [value["sys"]["id"]]
    if isinstance(value, list):
        return [i for v in value for i in link_ids(v)]
    return []


def as_bool(v, default=None):
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() == "true"


class Report:
    def __init__(self):
        self.filtered, self.skipped_pages, self.unknown_blocks, self.template_vars, self.missing = [], [], {}, {}, set()
        self.written = []
        self.errors = []
        self.product_stats = {}  # shop id -> {reason: count}


def fill_template(text, shop, report, where):
    if not text:
        return ""
    def sub(m):
        key = m.group(1).strip()
        if key in shop["template_vars"]:
            return shop["template_vars"][key]
        report.template_vars[key] = report.template_vars.get(key, 0) + 1
        return ""
    return re.sub(r"\{\{\s*([a-zA-Z_]+)\s*\}\}", sub, text)


def md_to_html(text, shift=1):
    """Markdown (as used in Contentful text fields) -> clean HTML, headings shifted down below the block heading."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n\n", text, flags=re.I)
    text = re.sub(r"</?(p|div|span|font|center)[^>]*>", "\n", text, flags=re.I)
    out = markdown.markdown(text, extensions=["sane_lists"])
    def shift_h(m):
        level = min(6, int(m.group(2)) + shift)
        return f"<{m.group(1)}h{level}>"
    out = re.sub(r"<(/?)h([1-6])>", shift_h, out)
    out = re.sub(r"<(script|style|iframe)[\s\S]*?</\1>", "", out, flags=re.I)
    return out.strip()


def plain(text):
    """HTML -> one line of plain text; list items separated by '; '."""
    t = re.sub(r"</li>\s*", "; ", text or "", flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return re.sub(r"\s*;\s*$", "", t).replace(" ;", ";")


INTERNAL_NAME = re.compile(r"^\s*CARD\s*-", re.I)


def clean_name(s):
    return re.sub(r"^\s*(PLP|PC|BI|D|S|V)\s*-\s*", "", s or "").strip()


# --------------------------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------------------------
class Builder:
    def __init__(self, src, shop, filters, report):
        self.src, self.shop, self.report = src, shop, report
        self.loc = shop["locale"]
        self.domains = {d.lower() for d in shop["domains"]}
        self.touched = []
        # shop language + English (some non-English pages still contain English FAQs)
        pats = filters.get(shop["lang"], []) + ([] if shop["lang"] == "en" else filters.get("en", []))
        self.patterns = [re.compile(p, re.I) for p in pats]

    def _touch(self, e):
        """Remember the last-published time of every entry used for the current page (for the sitemap lastmod)."""
        if e and e.get("updated"):
            self.touched.append(e["updated"])
        return e

    def get1(self, i):
        return self._touch(self.src.get([i], self.loc).get(i)) if i else None

    def getmany(self, ids):
        found = self.src.get(ids, self.loc)
        for i, e in found.items():
            if e is None:
                self.report.missing.add(i)
        return [self._touch(found[i]) for i in ids if found.get(i)]

    def visible(self, block):
        cond_ids = link_ids(block["fields"].get("shouldShowPerShop"))
        if not cond_ids:
            return True
        cond = self.get1(cond_ids[0])
        if not cond:
            return True
        applies = {str(d).lower() for d in (cond["fields"].get("appliesTo") or [])}
        matched = bool(self.domains & applies)
        show_only_matched = as_bool(cond["fields"].get("effectForAnyMatchedDomain"), True)
        return matched if show_only_matched else not matched

    def t(self, text, where=""):
        return fill_template(text, self.shop, self.report, where)

    def path(self, page):
        names, seen, cur = [], set(), page
        for _ in range(6):
            pid = (link_ids(cur["fields"].get("parentCategory")) or [None])[0]
            if not pid or pid in seen:
                break
            seen.add(pid)
            cur = self.get1(pid)
            if not cur:
                break
            n = cur["fields"].get("searchName") or clean_name(cur["fields"].get("title"))
            if n:
                names.append(self.t(n))
        return list(reversed(names))

    def render_block(self, b, page_name):
        typ, f = b["type"], b["fields"]
        title = self.t(f.get("title") or "")
        if typ in TEXT_BLOCKS:
            body = md_to_html(self.t(f.get("content"))) + md_to_html(self.t(f.get("contentRight")))
            if not plain(body) and not title:
                return None
            return ("text", title, body)
        if typ in FAQ_BLOCKS:
            qa = []
            for item in self.getmany(link_ids(f.get("faqItem"))):
                q = self.t(item["fields"].get("question") or "").strip()
                a = self.t(item["fields"].get("answer") or "").strip()
                if not q or not a:
                    continue
                hit = next((p.pattern for p in self.patterns if p.search(q)), None)
                if hit:
                    self.report.filtered.append((self.shop["id"], page_name, q, hit))
                    continue
                qa.append((q, md_to_html(a, shift=3)))
            return ("faq", title, qa) if qa else None
        if typ in PRODUCT_BLOCKS:
            items = []
            for p in self.getmany(link_ids(f.get("products"))):
                if p["type"] == "bundleItem" and not self.visible(p):
                    continue
                name = self.t(p["fields"].get("name") or p["fields"].get("title") or "")
                if INTERNAL_NAME.match(name):
                    # internal card label (e.g. "CARD - Flags PLP - Beach flags"): use the linked page's name, else drop
                    target = (link_ids(p["fields"].get("link")) or [None])[0]
                    tp = self.get1(target) if target else None
                    name = tp and (tp["fields"].get("searchName") or clean_name(tp["fields"].get("title")))
                    name = self.t(re.sub(r"\s*\([^)]*\)", "", name).strip()) if name else ""
                    if not name or INTERNAL_NAME.match(name):
                        continue
                if not name:
                    continue
                items.append((name, plain(md_to_html(self.t(p["fields"].get("highlights") or "")))))
            desc = md_to_html(self.t(f.get("description")))
            return ("products", title, (desc, items)) if items or plain(desc) else None
        if typ in LINK_BLOCKS:
            names = []
            for c in self.getmany(link_ids(f.get("subitems")) + link_ids(f.get("categories"))):
                n = c["fields"].get("searchName")
                target = (link_ids(c["fields"].get("link")) or [None])[0]  # pageCard -> linked category page
                if not n and target:
                    tp = self.get1(target)
                    n = tp and (tp["fields"].get("searchName") or clean_name(tp["fields"].get("title")))
                if not n:
                    n = c["fields"].get("title") or clean_name(c["fields"].get("name"))
                if n:
                    names.append(self.t(re.sub(r"\s*\([^)]*\)", "", n).strip()))
            return ("links", title, names) if names else None
        if typ in USP_BLOCKS:
            pts = []
            for it in self.getmany(link_ids(f.get("iconGridItems"))):
                txt = " – ".join(x for x in [self.t(it["fields"].get("title") or ""), plain(md_to_html(self.t(it["fields"].get("description") or it["fields"].get("text") or "")))] if x)
                if txt:
                    pts.append(txt)
            sub = self.t(f.get("subtitle") or "")
            return ("usps", title, (sub, pts)) if pts or sub else None
        if typ in PERSONA_BLOCKS:
            pts = []
            for it in self.getmany(link_ids(f.get("subitems"))):
                if not self.visible(it):
                    continue
                txt = " – ".join(x for x in [plain(self.t(it["fields"].get("title") or "")), plain(md_to_html(self.t(it["fields"].get("subtitle") or "")))] if x)
                if txt:
                    pts.append(txt)
            sub = plain(md_to_html(self.t(f.get("description") or "")))
            return ("usps", title, (sub, pts)) if pts or sub else None
        if typ in FORM_BLOCKS:
            form = f.get("formType") or "contact"
            desc = md_to_html(self.t(f.get("description")))
            note = f"<p><em>The category page has a “{html.escape(form)}” form for this.</em></p>"
            return ("text", title or form, desc + note)
        if typ not in SKIPPED_BLOCKS:
            self.report.unknown_blocks[typ] = self.report.unknown_blocks.get(typ, 0) + 1
        return None

    def build_page(self, page):
        self.touched = [page["updated"]] if page.get("updated") else []
        f = page["fields"]
        name = self.t(f.get("searchName") or clean_name(f.get("title")))
        slug = f.get("curl")
        block_ids = link_ids(f.get("bodyBlocks")) or link_ids(f.get("topBlock"))
        sections = []
        for b in self.getmany(block_ids):
            if not self.visible(b):
                continue
            r = self.render_block(b, name)
            if r:
                sections.append(r)
        tags = [self.t(x) for x in (f.get("searchTags") or []) if x]
        return {"name": name, "slug": slug, "url": f"{self.shop['url_prefix']}/{slug}", "path": self.path(page),
                "summary": self.t(f.get("meta_description") or ""), "tags": tags, "sections": sections,
                # newest publish date of the page OR anything on it (blocks, FAQs, products, ...)
                "updated": max(self.touched) if self.touched else None, "id": page["id"]}


LABELS = {  # page labels per language (shops.json "lang"); add a language here when enabling a new country
    "en": {"title": "category", "page": "Category page on {shop}", "path": "Category path", "summary": "Summary",
           "tags": "Also searched as", "products": "Products in {name}", "related": "Related categories",
           "faq": "Questions answered on the {name} category page (before ordering)",
           "footer": "Generated from Contentful (entry {id}) for Anna's knowledge base. Always refer customers to the category page above."},
    "it": {"title": "categoria", "page": "Pagina categoria su {shop}", "path": "Percorso categoria", "summary": "Riepilogo",
           "tags": "Cercato anche come", "products": "Prodotti in {name}", "related": "Categorie correlate",
           "faq": "Domande sulla pagina categoria {name} (prima dell'ordine)",
           "footer": "Generato da Contentful (entry {id}) per la knowledge base di Anna. Rimanda sempre il cliente alla pagina categoria qui sopra."},
    "es": {"title": "categoría", "page": "Página de categoría en {shop}", "path": "Ruta de la categoría", "summary": "Resumen",
           "tags": "También buscado como", "products": "Productos en {name}", "related": "Categorías relacionadas",
           "faq": "Preguntas sobre la página de categoría {name} (antes de pedir)",
           "footer": "Generado desde Contentful (entrada {id}) para la base de conocimiento de Anna. Remite siempre al cliente a la página de categoría indicada arriba."},
    "nl": {"title": "categorie", "page": "Categoriepagina op {shop}", "path": "Categoriepad", "summary": "Samenvatting",
           "tags": "Ook gezocht als", "products": "Producten in {name}", "related": "Gerelateerde categorieën",
           "faq": "Vragen op de categoriepagina {name} (voor het bestellen)",
           "footer": "Gegenereerd uit Contentful (entry {id}) voor de kennisbank van Anna. Verwijs de klant altijd naar de categoriepagina hierboven."},
    "fr": {"title": "catégorie", "page": "Page catégorie sur {shop}", "path": "Chemin de la catégorie", "summary": "Résumé",
           "tags": "Aussi recherché comme", "products": "Produits dans {name}", "related": "Catégories associées",
           "faq": "Questions sur la page catégorie {name} (avant la commande)",
           "footer": "Généré depuis Contentful (entrée {id}) pour la base de connaissances d'Anna. Renvoyez toujours le client vers la page catégorie ci-dessus."},
    "de": {"title": "Kategorie", "page": "Kategorieseite bei {shop}", "path": "Kategoriepfad", "summary": "Zusammenfassung",
           "tags": "Auch gesucht als", "products": "Produkte in {name}", "related": "Verwandte Kategorien",
           "faq": "Fragen auf der Kategorieseite {name} (vor der Bestellung)",
           "footer": "Aus Contentful generiert (Eintrag {id}) für Annas Wissensdatenbank. Verweise Kunden immer auf die Kategorieseite oben."},
    "sv": {"title": "kategori", "page": "Kategorisida på {shop}", "path": "Kategorisökväg", "summary": "Sammanfattning",
           "tags": "Söks även som", "products": "Produkter i {name}", "related": "Relaterade kategorier",
           "faq": "Frågor på kategorisidan {name} (före beställning)",
           "footer": "Genererad från Contentful (post {id}) för Annas kunskapsbas. Hänvisa alltid kunden till kategorisidan ovan."},
}


def page_html(c, shop, noindex):
    e = html.escape
    L = LABELS.get(shop.get("lang"), LABELS["en"])
    out = [f"<!doctype html><html lang=\"{e(shop['locale'])}\"><head><meta charset=\"utf-8\">",
           f"<title>{e(c['name'])} – {L['title']} – {e(shop['name'])}</title>"]
    if noindex:  # off by default: Engaige's scraper stores empty documents when these tags are present
        out.append(f"<link rel=\"canonical\" href=\"{e(c['url'])}\">")
        out.append("<meta name=\"robots\" content=\"noindex\">")
    out.append(f"<meta name=\"description\" content=\"{e(plain(c['summary']))}\"></head><body>")
    out.append(f"<h1>{e(c['name'])}</h1>")
    out.append(f"<p><strong>{e(L['page'].format(shop=shop['name']))}:</strong> <a href=\"{e(c['url'])}\">{e(c['url'])}</a></p>")
    if c["path"]:
        out.append(f"<p><strong>{L['path']}:</strong> {e(' › '.join(c['path'] + [c['name']]))}</p>")
    if c["summary"]:
        out.append(f"<p><strong>{L['summary']}:</strong> {e(plain(c['summary']))}</p>")
    if c["tags"]:
        out.append(f"<p><strong>{L['tags']}:</strong> {e(', '.join(c['tags']))}</p>")
    faqs = []
    for kind, title, data in c["sections"]:
        if kind == "faq":
            faqs.append((title, data))
            continue
        if title:
            out.append(f"<h2>{e(title)}</h2>")
        if kind == "text":
            out.append(data)
        elif kind == "products":
            desc, items = data
            if not title:
                out.append(f"<h2>{e(L['products'].format(name=c['name']))}</h2>")
            out.append(desc)
            out.append("<ul>" + "".join(f"<li><strong>{e(n)}</strong>{(' – ' + e(h)) if h else ''}</li>" for n, h in items) + "</ul>")
        elif kind == "links":
            out.append(f"<p><strong>{L['related']}:</strong> " + e(", ".join(data)) + "</p>")
        elif kind == "usps":
            sub, pts = data
            if sub:
                out.append(f"<p>{e(plain(sub))}</p>")
            out.append("<ul>" + "".join(f"<li>{e(p)}</li>" for p in pts) + "</ul>")
    for title, qa in faqs:
        out.append(f"<h2>{e(L['faq'].format(name=c['name']))}</h2>")
        if title:
            out.append(f"<p><em>{e(title)}</em></p>")
        for q, a in qa:
            out.append(f"<h3>{e(q)}</h3>{a}")
    out.append(f"<hr><p><small>{e(L['footer'].format(id=c['id']))}</small></p></body></html>")
    return "\n".join(out)


def blocks_html(sections, shop):
    """Content blocks of a product page (same block types as category pages), FAQs inline under their own title."""
    e, L, out = html.escape, LABELS.get(shop.get("lang"), LABELS["en"]), []
    for kind, title, data in sections:
        if title:
            out.append(f"<h2>{e(title)}</h2>")
        if kind == "text":
            out.append(data)
        elif kind == "products":
            desc, items = data
            out.append(desc)
            out.append("<ul>" + "".join(f"<li><strong>{e(n)}</strong>{(' – ' + e(h)) if h else ''}</li>" for n, h in items) + "</ul>")
        elif kind == "links":
            out.append(f"<p><strong>{L['related']}:</strong> " + e(", ".join(data)) + "</p>")
        elif kind == "usps":
            sub, pts = data
            if sub:
                out.append(f"<p>{e(plain(sub))}</p>")
            out.append("<ul>" + "".join(f"<li>{e(p)}</li>" for p in pts) + "</ul>")
        elif kind == "faq":
            for q, a in data:
                out.append(f"<h3>{e(q)}</h3>{a}")
    return "\n".join(out)


def build_products(src, shop, b, report, out_dir, site_url, today):
    """One page per live product + products/<shop>/sitemap.xml. Returns the number of pages written."""
    import products as P
    pb = P.ProductBuilder(b, md_to_html, plain, link_ids, as_bool)
    stats, built, seen = {}, [], set()
    for ctype in P.PRODUCT_TYPES:  # PCM products first; an old-style product with the same URL is skipped
        for e in sorted(src.entries(ctype, shop["locale"]), key=lambda x: x["id"]):
            ok, why = pb.is_live(e, report)
            if why:
                stats[why] = stats.get(why, 0) + 1
            if not ok:
                continue
            slug = e["fields"]["url"].strip("/")
            if not slug or "/" in slug or slug in seen:
                stats["duplicate or unusable URL"] = stats.get("duplicate or unusable URL", 0) + 1
                continue
            seen.add(slug)
            c = pb.build(e)
            if not c["name"] or not (c["desc"] or c["specs"] or c["options"] or c["sections"]):
                stats["no content"] = stats.get("no content", 0) + 1
                continue
            d = os.path.join(out_dir, "products", shop["id"], slug)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
                fh.write(P.product_html(c, shop, lambda secs, name: blocks_html(secs, shop)))
            built.append(c)
    base = f"{site_url}/products/{shop['id']}"
    with open(os.path.join(out_dir, "products", shop["id"], "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for c in sorted(built, key=lambda x: x["slug"]):
            lm = (c["updated"] or today)[:10]
            fh.write(f"  <url><loc>{xml_escape(base + '/' + c['slug'] + '/')}</loc><lastmod>{lm}</lastmod></url>\n")
        fh.write("</urlset>\n")
    stats["built"] = len(built)
    report.product_stats[shop["id"]] = stats
    return len(built), base + "/sitemap.xml"


def keep_previous(kind, shop_id, out_dir, report, ex):
    import shutil, traceback
    traceback.print_exc()
    report.errors.append((f"{shop_id} ({kind})", f"{type(ex).__name__}: {ex}"))
    prev = os.path.join(ROOT, "snapshot", kind, shop_id)
    dst = os.path.join(out_dir, kind, shop_id)
    shutil.rmtree(dst, ignore_errors=True)
    if os.path.isdir(prev):
        shutil.copytree(prev, dst)
        print(f"   ! {kind} build failed for {shop_id} — kept the previous version from snapshot/")
    else:
        print(f"   ! {kind} build failed for {shop_id} — no previous version available")


LIVE_STATUS = {}  # live sitemap url -> "OK (n categories)" or the error, shown in report.html
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en;q=0.9",
}


def fetch_live_slugs(url, prefix):
    """Slugs listed in the live shop's category sitemap, or None if it can't be read (then no live check)."""
    if url not in LIVE_STATUS:
        _download_live(url)
    locs = LIVE_STATUS[url][1]
    if locs is None:
        return None
    return {l[len(prefix) + 1:].strip("/") for l in locs if l.startswith(prefix + "/")}


def _download_live(url):
    err = None
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=60, headers=BROWSER_HEADERS)
            r.raise_for_status()
            locs = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", r.text)
            if not locs:
                raise ValueError(f"no <loc> entries (HTTP {r.status_code}, {len(r.text)} bytes)")
            LIVE_STATUS[url] = (f"OK ({len(locs)} categories)", locs)
            return
        except Exception as ex:  # noqa
            err = f"{type(ex).__name__}: {ex}"[:200]
            time.sleep(3 * (attempt + 1))
    LIVE_STATUS[url] = (f"FAILED – {err} – built WITHOUT live check", None)
    print(f"  ! could not read live sitemap {url}: {err} — building without that check")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture")
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"))
    ap.add_argument("--site-url", default=os.environ.get("SITE_URL", "").rstrip("/"))
    ap.add_argument("--only")
    ap.add_argument("--no-live-check", action="store_true")
    ap.add_argument("--noindex", action="store_true", help="add noindex + canonical tags (Engaige then stores empty docs)")
    a = ap.parse_args()

    shops = [s for s in json.load(open(os.path.join(ROOT, "config/shops.json")))["shops"] if s.get("enabled")]
    filters = json.load(open(os.path.join(ROOT, "config/faq_filters.json")))
    if a.fixture:
        src = FixtureSource(a.fixture)
    else:
        space, token = os.environ.get("CONTENTFUL_SPACE_ID"), os.environ.get("CONTENTFUL_CDA_TOKEN")
        if not space or not token:
            sys.exit("Missing CONTENTFUL_SPACE_ID / CONTENTFUL_CDA_TOKEN")
        src = CDASource(space, token)
    only = set(a.only.split(",")) if a.only else None
    report = Report()
    today = dt.date.today().isoformat()
    os.makedirs(a.out, exist_ok=True)
    open(os.path.join(a.out, ".nojekyll"), "w").close()
    index_rows, product_rows = [], []

    for shop in shops:
        try:
            print(f"== {shop['name']} ({shop['locale']})")
            b = Builder(src, shop, filters, report)
            # live check: only build categories that exist in the shop's own sitemap. A shop without its own category
            # sitemap (e.g. Connect) can point to another shop's sitemap via live_sitemap + live_sitemap_prefix.
            live = None
            if not (a.fixture or a.no_live_check) and shop.get("live_sitemap"):
                live = fetch_live_slugs(shop["live_sitemap"], shop.get("live_sitemap_prefix", shop["url_prefix"]))
            pages = src.category_pages(shop["locale"])
            seen, built = set(), []
            for p in sorted(pages, key=lambda x: x["id"]):
                slug, f = p["fields"].get("curl"), p["fields"]
                if not slug or "/" in slug:
                    continue
                if only and slug not in only:
                    continue
                if (f.get("robots_content") or "").startswith("noindex"):
                    report.skipped_pages.append((shop["id"], slug, "noindex in Contentful")); continue
                if live is not None and slug not in live:
                    report.skipped_pages.append((shop["id"], slug, "not in the live shop sitemap")); continue
                if slug in seen:
                    report.skipped_pages.append((shop["id"], slug, "duplicate slug")); continue
                seen.add(slug)
                c = b.build_page(p)
                if not c["sections"] and not c["summary"]:
                    report.skipped_pages.append((shop["id"], slug, "no content")); continue
                d = os.path.join(a.out, "categories", shop["id"], slug)
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
                    fh.write(page_html(c, shop, noindex=a.noindex))
                built.append(c)
            # sitemap
            smdir = os.path.join(a.out, "categories", shop["id"])
            os.makedirs(smdir, exist_ok=True)
            base = f"{a.site_url}/categories/{shop['id']}"
            with open(os.path.join(smdir, "sitemap.xml"), "w", encoding="utf-8") as fh:
                fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
                for c in sorted(built, key=lambda x: x["slug"]):
                    lm = (c["updated"] or today)[:10]
                    fh.write(f"  <url><loc>{xml_escape(base + '/' + c['slug'] + '/')}</loc><lastmod>{lm}</lastmod></url>\n")
                fh.write("</urlset>\n")
            print(f"   {len(built)} category pages written")
            index_rows.append((shop, len(built), base + "/sitemap.xml"))
        except Exception as ex:  # one shop failing must not take the whole site down
            keep_previous("categories", shop["id"], a.out, report, ex)
        if shop.get("products") and not a.only:
            try:
                n, url = build_products(src, shop, Builder(src, shop, filters, report), report, a.out, a.site_url, today)
                print(f"   {n} product pages written")
                product_rows.append((shop, n, url))
            except Exception as ex:
                keep_previous("products", shop["id"], a.out, report, ex)

    # index + report
    e = html.escape
    rep = [f"<!doctype html><html><head><meta charset='utf-8'><meta name='robots' content='noindex'><title>Build report</title></head><body>",
           f"<h1>Build report – {today}</h1>"]
    rep.append("<h2>Live shop check</h2><ul>")
    for shop in shops:
        u = shop.get("live_sitemap")
        st = LIVE_STATUS.get(u, ("not checked",))[0] if u else "no live sitemap configured"
        rep.append(f"<li>{html.escape(shop['id'])}: {html.escape(st)}</li>")
    rep.append("</ul>")
    if report.errors:
        rep.append(f"<h2>Shops that failed this run ({len(report.errors)}) – previous version kept</h2><ul>")
        rep += [f"<li>{html.escape(i)}: {html.escape(m)}</li>" for i, m in report.errors]
        rep.append("</ul>")
    if report.product_stats:
        rep.append("<h2>Products</h2><ul>")
        for sid, st in report.product_stats.items():
            rep.append(f"<li><strong>{e(sid)}</strong>: " + ", ".join(f"{e(k)}: {v}" for k, v in st.items()) + "</li>")
        rep.append("</ul>")
    rep.append(f"<h2>FAQs left out by the filter ({len(report.filtered)})</h2><p>Edit <code>config/faq_filters.json</code> to change this.</p><ul>")
    rep += [f"<li>[{e(s)}] <strong>{e(p)}</strong>: {e(q)} <small>(rule: <code>{e(r)}</code>)</small></li>" for s, p, q, r in report.filtered]
    rep.append(f"</ul><h2>Category pages not built ({len(report.skipped_pages)})</h2><ul>")
    rep += [f"<li>[{e(s)}] {e(sl)} – {e(why)}</li>" for s, sl, why in report.skipped_pages]
    rep.append("</ul><h2>Block types not handled</h2><ul>" + "".join(f"<li>{e(k)}: {v}×</li>" for k, v in report.unknown_blocks.items()) + "</ul>")
    rep.append("<h2>Unknown template variables (removed)</h2><ul>" + "".join(f"<li>{{{{{e(k)}}}}}: {v}×</li>" for k, v in report.template_vars.items()) + "</ul>")
    rep.append(f"<h2>Linked entries not found / unpublished ({len(report.missing)})</h2></body></html>")
    with open(os.path.join(a.out, "report.html"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(rep))
    with open(os.path.join(a.out, "index.html"), "w", encoding="utf-8") as fh:
        fh.write("<!doctype html><html><head><meta charset='utf-8'><meta name='robots' content='noindex'><title>Anna knowledge</title></head><body>"
                 f"<h1>Anna knowledge site</h1><p>Last build: {today}. <a href='report.html'>Build report</a></p><ul>"
                 + "".join(f"<li>{e(s['name'])} – categories: {n} pages – sitemap: <a href='{e(u)}'>{e(u)}</a></li>" for s, n, u in index_rows)
                 + "".join(f"<li>{e(s['name'])} – <strong>products</strong>: {n} pages – sitemap: <a href='{e(u)}'>{e(u)}</a></li>" for s, n, u in product_rows)
                 + "</ul></body></html>")
    print(f"Filtered FAQs: {len(report.filtered)} | skipped pages: {len(report.skipped_pages)} | unknown blocks: {report.unknown_blocks} | unknown vars: {report.template_vars}")


if __name__ == "__main__":
    main()
