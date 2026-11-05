"""
Anna knowledge site builder — products module (used by build.py).

One page per live product per shop, built from Contentful only:
  - PCM products (content type pcmProduct) and older "product" entries (flyers, panels, buttons, ...)
  - live = published + has a URL for the shop's locale (+ robots not "noindex", unless "products_include_noindex")
    (+ for shops with "products_respect_unavailable": the Contentful "Unavailable" per-shop condition,
     and for old-style products the "Available" switch)
Per product: name, real URL, category, description, key specs, pros & cons, print options
(colours / print colours / print methods / print sizes from productData), file guidelines, FAQs
(order-status / delivery-time questions filtered like on category pages) and content blocks.
Prices, stock and delivery dates are NOT in Contentful, so they are not on these pages.
"""
import html, re

PRODUCT_TYPES = ("pcmProduct", "product")
TEST_SLUG = re.compile(r"stresstest|donotdelete|donotuse|-test-|\(ade\)", re.I)

P_LABELS = {
    "en": {"title": "product", "page": "Product page on {shop}", "category": "Category", "tags": "Also searched as",
           "desc": "Description", "specs": "Specifications", "pros": "Advantages", "cons": "Good to know",
           "options": "Print options", "colours": "Product colours", "print_colours": "Print colours",
           "methods": "Print methods", "sizes": "Print sizes", "guide": "File guidelines",
           "faq": "Questions on the {name} product page",
           "footer": "Generated from Contentful (entry {id}) for Anna's knowledge base. Prices, stock and delivery dates "
                     "are not on this page: always refer customers to the product page above for those."},
    "it": {"title": "prodotto", "page": "Pagina prodotto su {shop}", "category": "Categoria", "tags": "Cercato anche come",
           "desc": "Descrizione", "specs": "Specifiche", "pros": "Vantaggi", "cons": "Da sapere",
           "options": "Opzioni di stampa", "colours": "Colori del prodotto", "print_colours": "Colori di stampa",
           "methods": "Tecniche di stampa", "sizes": "Formati di stampa", "guide": "Indicazioni per il file",
           "faq": "Domande sulla pagina prodotto {name}",
           "footer": "Generato da Contentful (entry {id}) per la knowledge base di Anna. Prezzi, disponibilità e date di "
                     "consegna non sono in questa pagina: rimanda sempre il cliente alla pagina prodotto qui sopra."},
    "es": {"title": "producto", "page": "Página de producto en {shop}", "category": "Categoría", "tags": "También buscado como",
           "desc": "Descripción", "specs": "Especificaciones", "pros": "Ventajas", "cons": "A tener en cuenta",
           "options": "Opciones de impresión", "colours": "Colores del producto", "print_colours": "Colores de impresión",
           "methods": "Técnicas de impresión", "sizes": "Tamaños de impresión", "guide": "Indicaciones para el archivo",
           "faq": "Preguntas sobre la página de producto {name}",
           "footer": "Generado desde Contentful (entrada {id}) para la base de conocimiento de Anna. Precios, stock y fechas "
                     "de entrega no están en esta página: remite siempre al cliente a la página de producto indicada arriba."},
    "nl": {"title": "product", "page": "Productpagina op {shop}", "category": "Categorie", "tags": "Ook gezocht als",
           "desc": "Omschrijving", "specs": "Specificaties", "pros": "Voordelen", "cons": "Goed om te weten",
           "options": "Drukopties", "colours": "Productkleuren", "print_colours": "Drukkleuren",
           "methods": "Druktechnieken", "sizes": "Drukformaten", "guide": "Bestandsrichtlijnen",
           "faq": "Vragen op de productpagina {name}",
           "footer": "Gegenereerd uit Contentful (entry {id}) voor de kennisbank van Anna. Prijzen, voorraad en levertijden "
                     "staan niet op deze pagina: verwijs de klant daarvoor altijd naar de productpagina hierboven."},
    "fr": {"title": "produit", "page": "Page produit sur {shop}", "category": "Catégorie", "tags": "Aussi recherché comme",
           "desc": "Description", "specs": "Spécifications", "pros": "Avantages", "cons": "Bon à savoir",
           "options": "Options d'impression", "colours": "Couleurs du produit", "print_colours": "Couleurs d'impression",
           "methods": "Techniques d'impression", "sizes": "Formats d'impression", "guide": "Consignes pour le fichier",
           "faq": "Questions sur la page produit {name}",
           "footer": "Généré depuis Contentful (entrée {id}) pour la base de connaissances d'Anna. Prix, stock et délais de "
                     "livraison ne figurent pas ici : renvoyez toujours le client vers la page produit ci-dessus."},
    "de": {"title": "Produkt", "page": "Produktseite bei {shop}", "category": "Kategorie", "tags": "Auch gesucht als",
           "desc": "Beschreibung", "specs": "Spezifikationen", "pros": "Vorteile", "cons": "Gut zu wissen",
           "options": "Druckoptionen", "colours": "Produktfarben", "print_colours": "Druckfarben",
           "methods": "Drucktechniken", "sizes": "Druckformate", "guide": "Hinweise zur Druckdatei",
           "faq": "Fragen auf der Produktseite {name}",
           "footer": "Aus Contentful generiert (Eintrag {id}) für Annas Wissensdatenbank. Preise, Bestand und Liefertermine "
                     "stehen nicht hier: Verweise Kunden dafür immer auf die Produktseite oben."},
    "sv": {"title": "produkt", "page": "Produktsida på {shop}", "category": "Kategori", "tags": "Söks även som",
           "desc": "Beskrivning", "specs": "Specifikationer", "pros": "Fördelar", "cons": "Bra att veta",
           "options": "Tryckalternativ", "colours": "Produktfärger", "print_colours": "Tryckfärger",
           "methods": "Tryckmetoder", "sizes": "Tryckstorlekar", "guide": "Riktlinjer för filen",
           "faq": "Frågor på produktsidan {name}",
           "footer": "Genererad från Contentful (post {id}) för Annas kunskapsbas. Priser, lager och leveransdatum finns inte "
                     "här: hänvisa alltid kunden till produktsidan ovan."},
}

# productData codes -> words (codes not listed are shown tidied up, e.g. "dark_blue" -> "Dark blue")
COLOURS = {
    "en": {"black": "Black", "white": "White", "blue": "Blue", "red": "Red", "green": "Green", "silver": "Silver",
           "gold": "Gold", "yellow": "Yellow", "orange": "Orange", "purple": "Purple", "pink": "Pink", "grey": "Grey",
           "gray": "Grey", "brown": "Brown", "beige": "Beige", "navy": "Navy", "turquoise": "Turquoise",
           "dark_blue": "Dark blue", "dark_red": "Dark red", "light_blue": "Light blue", "rose_gold": "Rose gold",
           "transparent": "Transparent", "natural": "Natural", "multicolor": "Multicolour", "anthracite": "Anthracite",
           "royal_blue": "Royal blue", "dark_green": "Dark green", "light_green": "Light green", "cream": "Cream",
           "stainless_steel": "Stainless steel"},
    "nl": {"black": "Zwart", "white": "Wit", "blue": "Blauw", "red": "Rood", "green": "Groen", "silver": "Zilver",
           "gold": "Goud", "yellow": "Geel", "orange": "Oranje", "purple": "Paars", "pink": "Roze", "grey": "Grijs",
           "gray": "Grijs", "brown": "Bruin", "beige": "Beige", "navy": "Marine", "transparent": "Transparant",
           "natural": "Naturel", "dark_blue": "Donkerblauw", "light_blue": "Lichtblauw", "multicolor": "Multicolor"},
    "fr": {"black": "Noir", "white": "Blanc", "blue": "Bleu", "red": "Rouge", "green": "Vert", "silver": "Argenté",
           "gold": "Doré", "yellow": "Jaune", "orange": "Orange", "purple": "Violet", "pink": "Rose", "grey": "Gris",
           "gray": "Gris", "brown": "Marron", "beige": "Beige", "navy": "Marine", "transparent": "Transparent",
           "natural": "Naturel", "dark_blue": "Bleu foncé", "light_blue": "Bleu clair", "multicolor": "Multicolore"},
    "de": {"black": "Schwarz", "white": "Weiß", "blue": "Blau", "red": "Rot", "green": "Grün", "silver": "Silber",
           "gold": "Gold", "yellow": "Gelb", "orange": "Orange", "purple": "Lila", "pink": "Pink", "grey": "Grau",
           "gray": "Grau", "brown": "Braun", "beige": "Beige", "navy": "Navy", "transparent": "Transparent",
           "natural": "Natur", "dark_blue": "Dunkelblau", "light_blue": "Hellblau", "multicolor": "Mehrfarbig"},
    "it": {"black": "Nero", "white": "Bianco", "blue": "Blu", "red": "Rosso", "green": "Verde", "silver": "Argento",
           "gold": "Oro", "yellow": "Giallo", "orange": "Arancione", "purple": "Viola", "pink": "Rosa", "grey": "Grigio",
           "gray": "Grigio", "brown": "Marrone", "beige": "Beige", "navy": "Navy", "transparent": "Trasparente",
           "natural": "Naturale", "dark_blue": "Blu scuro", "light_blue": "Azzurro", "multicolor": "Multicolore"},
    "es": {"black": "Negro", "white": "Blanco", "blue": "Azul", "red": "Rojo", "green": "Verde", "silver": "Plateado",
           "gold": "Dorado", "yellow": "Amarillo", "orange": "Naranja", "purple": "Morado", "pink": "Rosa", "grey": "Gris",
           "gray": "Gris", "brown": "Marrón", "beige": "Beige", "navy": "Azul marino", "transparent": "Transparente",
           "natural": "Natural", "dark_blue": "Azul oscuro", "light_blue": "Azul claro", "multicolor": "Multicolor"},
    "sv": {"black": "Svart", "white": "Vit", "blue": "Blå", "red": "Röd", "green": "Grön", "silver": "Silver",
           "gold": "Guld", "yellow": "Gul", "orange": "Orange", "purple": "Lila", "pink": "Rosa", "grey": "Grå",
           "gray": "Grå", "brown": "Brun", "beige": "Beige", "navy": "Marinblå", "transparent": "Transparent",
           "natural": "Natur", "dark_blue": "Mörkblå", "light_blue": "Ljusblå", "multicolor": "Flerfärgad"},
}
TECHNIQUES = {
    "en": {"digital": "Digital print", "digital_transfer": "Digital transfer", "laser_engraving": "Laser engraving",
           "screen_print": "Screen print", "pad_printing": "Pad printing", "embroidery": "Embroidery", "uv_print": "UV print",
           "full_color": "Full colour", "doming": "Doming", "sublimation": "Sublimation", "heat_transfer": "Heat transfer",
           "direct_to_garment": "Direct to garment (DTG)", "offset_print": "Offset print", "screen_transfer": "Screen transfer",
           "debossing": "Debossing", "embossing": "Embossing", "hot_foil": "Hot foil"},
    "nl": {"digital": "Digitaal", "laser_engraving": "Lasergravure", "screen_print": "Zeefdruk", "pad_printing": "Tampondruk",
           "embroidery": "Borduren", "uv_print": "UV-print", "full_color": "Full colour", "sublimation": "Sublimatie",
           "heat_transfer": "Transfer", "direct_to_garment": "Direct op textiel (DTG)", "offset_print": "Offsetdruk"},
    "fr": {"digital": "Numérique", "laser_engraving": "Gravure laser", "screen_print": "Sérigraphie", "pad_printing": "Tampographie",
           "embroidery": "Broderie", "uv_print": "Impression UV", "full_color": "Quadrichromie", "sublimation": "Sublimation",
           "heat_transfer": "Transfert", "direct_to_garment": "Impression directe (DTG)", "offset_print": "Offset"},
    "de": {"digital": "Digitaldruck", "laser_engraving": "Lasergravur", "screen_print": "Siebdruck", "pad_printing": "Tampondruck",
           "embroidery": "Stickerei", "uv_print": "UV-Druck", "full_color": "Vollfarbig", "sublimation": "Sublimation",
           "heat_transfer": "Transferdruck", "direct_to_garment": "Direktdruck (DTG)", "offset_print": "Offsetdruck"},
    "it": {"digital": "Stampa digitale", "laser_engraving": "Incisione laser", "screen_print": "Serigrafia", "pad_printing": "Tampografia",
           "embroidery": "Ricamo", "uv_print": "Stampa UV", "full_color": "Quadricromia", "sublimation": "Sublimazione",
           "heat_transfer": "Transfer", "direct_to_garment": "Stampa diretta (DTG)", "offset_print": "Offset"},
    "es": {"digital": "Impresión digital", "laser_engraving": "Grabado láser", "screen_print": "Serigrafía", "pad_printing": "Tampografía",
           "embroidery": "Bordado", "uv_print": "Impresión UV", "full_color": "A todo color", "sublimation": "Sublimación",
           "heat_transfer": "Transfer", "direct_to_garment": "Impresión directa (DTG)", "offset_print": "Offset"},
    "sv": {"digital": "Digitaltryck", "laser_engraving": "Lasergravyr", "screen_print": "Screentryck", "pad_printing": "Tampongtryck",
           "embroidery": "Broderi", "uv_print": "UV-tryck", "full_color": "Fyrfärgstryck", "sublimation": "Sublimering",
           "heat_transfer": "Transfertryck", "direct_to_garment": "Direkttryck (DTG)", "offset_print": "Offsettryck"},
}
N_COLOURS = {"en": ("{n} colour", "{n} colours"), "nl": ("{n} kleur", "{n} kleuren"), "fr": ("{n} couleur", "{n} couleurs"),
             "de": ("{n} Farbe", "{n} Farben"), "it": ("{n} colore", "{n} colori"), "es": ("{n} color", "{n} colores"),
             "sv": ("{n} färg", "{n} färger")}


def _vals(v):
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    if isinstance(v, dict):
        return [str(x) for x in v.values()]
    return [str(v)]


def _tidy(code):
    return code.replace("_", " ").strip().capitalize()


def _dims(s):
    """'12x36x54xno' -> '12 x 36 x 54' (raw PCM size codes); other text unchanged."""
    if re.fullmatch(r"\s*\d+(\.\d+)?(x(\d+(\.\d+)?|no))+\s*", s or "", re.I):
        parts = [p for p in s.strip().lower().split("x") if p and p != "no"]
        return " x ".join(parts)
    return s


def print_options(product_data, lang):
    """Colours / print colours / print methods / print sizes from pcmProduct.productData (PCM attribute codes)."""
    pa = ((product_data or {}).get("productAttributes") or {})
    sel, pre = pa.get("selectedAttributes") or {}, pa.get("presetAttributes") or {}
    cmap, tmap = COLOURS.get(lang, COLOURS["en"]), TECHNIQUES.get(lang, TECHNIQUES["en"])
    one, many = N_COLOURS.get(lang, N_COLOURS["en"])

    def uniq(xs):
        return list(dict.fromkeys(x for x in xs if x))

    colours = uniq(cmap.get(c, COLOURS["en"].get(c, _tidy(c))) for c in _vals(sel.get("color")) or _vals(pre.get("color")) if c != "no")
    pcols = []
    for c in _vals(sel.get("print_color")) or _vals(pre.get("print_color")):
        m = re.fullmatch(r"(\d+)_colou?r", c)
        if m:
            pcols.append((one if m.group(1) == "1" else many).format(n=m.group(1)))
        elif c != "no":
            pcols.append(tmap.get(c, TECHNIQUES["en"].get(c, _tidy(c))))
    methods = uniq(tmap.get(c, TECHNIQUES["en"].get(c, _tidy(c))) for c in _vals(sel.get("print_technique")) or _vals(pre.get("print_technique")) if c != "no")
    sizes = []
    for key in list(sel) + list(pre):
        if "print_format" not in key:
            continue
        for v in _vals(sel.get(key)) or _vals(pre.get(key)):
            m = re.match(r"(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)", v.split("#")[0])
            if m and float(m.group(1)) > 0 and float(m.group(2)) > 0:
                sizes.append(f"{m.group(1)} x {m.group(2)} mm")
    return {"colours": colours, "print_colours": uniq(pcols), "methods": methods, "sizes": uniq(sizes)}


def links_to_text(md):
    """Keep link text, drop (relative) shop links that would not work outside the website."""
    return re.sub(r"\[([^\]]+)\]\((?!https?://)[^)]*\)", r"\1", md or "")


class ProductBuilder:
    def __init__(self, b, md_to_html, plain, link_ids, as_bool):
        self.b, self.md, self.plain, self.link_ids, self.as_bool = b, md_to_html, plain, link_ids, as_bool
        self.shop = b.shop
        self.lang = self.shop.get("lang", "en")

    def tpl(self, text, name):
        text = re.sub(r"\{\{\s*product_name\s*\}\}", name or "", text or "")
        return self.b.t(text)

    def is_live(self, e, report):
        """(True, None) or (False, reason) – the same rules for both product content types."""
        f = e["fields"]
        if not f.get("url"):
            return False, None  # not sold in this shop (no URL for this locale) – not reported
        if TEST_SLUG.search(f.get("slug") or ""):
            return False, "test product"
        info = None
        if (f.get("robots_content") or "").startswith("noindex"):
            if not self.shop.get("products_include_noindex", False):
                return False, "noindex in Contentful"
            # hidden from Google/sitemap, but the product page still works and can be ordered
            info = "(info) built although noindex (hidden from Google, but orderable via its link)"
        if e["type"] == "product" and f.get("available") is not None and not self.as_bool(f.get("available"), True):
            return False, "'Available' switched off"
        cond_ids = self.link_ids(f.get("unavailable"))
        cond = self.b.get1(cond_ids[0]) if cond_ids else None
        if cond:
            applies = {str(d).lower() for d in (cond["fields"].get("appliesTo") or [])}
            matched = bool(self.b.domains & applies)
            offline = matched if self.as_bool(cond["fields"].get("effectForAnyMatchedDomain"), True) else not matched
            if offline:
                if self.shop.get("products_respect_unavailable", True):
                    return False, "'Unavailable' condition for this shop"
                # e.g. the V4 Irish shop shows these products anyway -> build them, but count them in the report
                return True, "(info) built although an 'Unavailable' condition matches this shop (the live shop ignores it)"
        return True, info

    def build(self, e):
        b, f = self.b, e["fields"]
        b.touched = [e["updated"]] if e.get("updated") else []
        name = b.t(f.get("title") or f.get("name") or f.get("searchName") or "").strip()
        url = f"{self.shop['url_prefix']}/{f['url']}"
        # category
        cat = None
        cid = (self.link_ids(f.get("categoryPage")) or [None])[0]
        cp = b.get1(cid) if cid else None
        if cp and cp["fields"].get("curl"):
            cat = (b.t(cp["fields"].get("searchName") or cp["fields"].get("title") or ""), f"{self.shop['url_prefix']}/{cp['fields']['curl']}")
        # description (+ intro paragraph of old-style products)
        desc = self.md(links_to_text(self.tpl(f.get("introParagraph"), name)), shift=2) + \
               self.md(links_to_text(self.tpl(f.get("description"), name)), shift=2)
        # key specs: entries come in pairs (label, value)
        specs = []
        ks = b.getmany(self.link_ids(f.get("productKeysSpecs")))
        for i in range(0, len(ks) - 1, 2):
            lab = self.plain(self.tpl(ks[i]["fields"].get("text"), name))
            val = _dims(self.plain(self.tpl(ks[i + 1]["fields"].get("text"), name)))
            if lab and val:
                specs.append((lab, val))
        pros, cons = [], []
        for pc in b.getmany(self.link_ids(f.get("proscons"))):
            t = self.plain(self.tpl(pc["fields"].get("description"), name))
            if t:
                (pros if self.as_bool(pc["fields"].get("prosorcons"), True) else cons).append(t)
        opts = print_options(f.get("productData"), self.lang) if e["type"] == "pcmProduct" else {}
        # file guidelines (groups -> specifications, or specifications linked directly)
        guides, seen = [], set()
        for s in b.getmany(self.link_ids(f.get("submissionSpecs"))):
            items = b.getmany(self.link_ids(s["fields"].get("linkedSubmissionSpecifications"))) \
                if s["type"] == "submissionSpecificationGroup" else [s]
            for it in items:
                if it["id"] in seen:
                    continue
                seen.add(it["id"])
                head = self.plain(self.tpl(it["fields"].get("name") or it["fields"].get("title"), name))
                body = self.md(links_to_text(self.tpl(it["fields"].get("description"), name)), shift=3)
                if head or self.plain(body):
                    guides.append((head, body))
        # FAQ: faqItem list = question entry followed by its answer entr(y/ies)
        qa, cur_q, cur_a = [], None, []

        def flush():
            if cur_q and self.plain("".join(cur_a)):
                hit = next((p.pattern for p in b.patterns if p.search(cur_q)), None)
                if hit:
                    b.report.filtered.append((self.shop["id"], f"product: {name}", cur_q, hit))
                else:
                    qa.append((cur_q, "".join(cur_a)))
        for it in b.getmany(self.link_ids(f.get("faqItem"))):
            txt = self.tpl(it["fields"].get("description"), name)
            if self.as_bool(it["fields"].get("isQuestion"), False):
                flush()
                cur_q, cur_a = self.plain(self.md(txt)), []
            else:
                cur_a.append(self.md(links_to_text(txt), shift=3))
        flush()
        # content blocks (same renderer as category pages)
        sections = []
        for blk in b.getmany(self.link_ids(f.get("contentBlocks"))):
            if b.visible(blk):
                r = b.render_block(blk, name)
                if r:
                    sections.append(r)
        tags = [b.t(x) for x in (f.get("searchTags") or []) if x]
        return {"name": name, "slug": f["url"], "url": url, "category": cat, "desc": desc, "specs": specs,
                "pros": pros, "cons": cons, "options": opts, "guides": guides, "faq": qa, "sections": sections,
                "tags": tags, "id": e["id"], "updated": max(b.touched) if b.touched else None}


def product_html(c, shop, section_html):
    e = html.escape
    L = P_LABELS.get(shop.get("lang"), P_LABELS["en"])
    out = [f"<!doctype html><html lang=\"{e(shop['locale'])}\"><head><meta charset=\"utf-8\">",
           f"<title>{e(c['name'])} – {L['title']} – {e(shop['name'])}</title></head><body>",
           f"<h1>{e(c['name'])}</h1>",
           f"<p><strong>{e(L['page'].format(shop=shop['name']))}:</strong> <a href=\"{e(c['url'])}\">{e(c['url'])}</a></p>"]
    if c["category"]:
        out.append(f"<p><strong>{L['category']}:</strong> {e(c['category'][0])} – <a href=\"{e(c['category'][1])}\">{e(c['category'][1])}</a></p>")
    if c["tags"]:
        out.append(f"<p><strong>{L['tags']}:</strong> {e(', '.join(c['tags']))}</p>")
    if c["desc"]:
        out.append(f"<h2>{L['desc']}</h2>{c['desc']}")
    if c["specs"]:
        out.append(f"<h2>{L['specs']}</h2><ul>" + "".join(f"<li><strong>{e(k)}:</strong> {e(v)}</li>" for k, v in c["specs"]) + "</ul>")
    if c["pros"]:
        out.append(f"<h2>{L['pros']}</h2><ul>" + "".join(f"<li>{e(p)}</li>" for p in c["pros"]) + "</ul>")
    if c["cons"]:
        out.append(f"<h2>{L['cons']}</h2><ul>" + "".join(f"<li>{e(p)}</li>" for p in c["cons"]) + "</ul>")
    o = c["options"] or {}
    rows = [(L[k], o.get(k)) for k in ("colours", "print_colours", "methods", "sizes") if o.get(k)]
    if rows:
        out.append(f"<h2>{L['options']}</h2><ul>" + "".join(f"<li><strong>{e(k)}:</strong> {e(', '.join(v))}</li>" for k, v in rows) + "</ul>")
    out.append(section_html(c["sections"], c["name"]))
    if c["guides"]:
        out.append(f"<h2>{L['guide']}</h2>")
        for head, body in c["guides"]:
            out.append((f"<h3>{e(head)}</h3>" if head else "") + body)
    if c["faq"]:
        out.append(f"<h2>{e(L['faq'].format(name=c['name']))}</h2>")
        for q, a in c["faq"]:
            out.append(f"<h3>{e(q)}</h3>{a}")
    out.append(f"<hr><p><small>{e(L['footer'].format(id=c['id']))}</small></p></body></html>")
    return "\n".join(x for x in out if x)
