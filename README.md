# Anna knowledge site

Builds clean, text-only pages from Helloprint's Contentful content so Anna (Engaige) can sync them
through a **Sitemap knowledge folder** instead of CSV uploads.

**Now included:** category pages for all shops, and **product pages** for every shop (`"products": true` in
`config/shops.json`). Help-centre FAQs can be added later.

## How it works
1. Every night (and whenever `build.py` or `config/` changes) GitHub runs `build.py`.
2. It reads **published** category pages from Contentful with a read-only key (repository secrets
   `CONTENTFUL_SPACE_ID` and `CONTENTFUL_CDA_TOKEN`).
3. Per shop it keeps only the blocks that are visible on that shop (Contentful "per shop conditions"),
   fills in `{{shop_name}}` etc., and writes one page per category:
   `categories/<shop>/<category-slug>/`.
4. Each shop gets a sitemap: `categories/<shop>/sitemap.xml` → add that URL to an Engaige *Sitemap* folder.
5. Every page links to the real helloprint.com category page; Anna should cite that link.
6. `report.html` lists what was left out and why. A copy of every build (categories + report, not the ~100k
   product pages) is saved in `snapshot/`.
7. If products fail for a shop, the run stops before publishing: yesterday's site stays online and GitHub emails you.

## Products (`products.py`)
- One page per live product: `products/<shop>/<product-url>/`, sitemap `products/<shop>/sitemap.xml`.
- Live = published in Contentful + has a URL for the shop's language. `noindex` products are skipped unless the shop has
  `"products_include_noindex": true` (Ireland: yes – they are hidden from Google but can still be ordered via their link).
  Shops with `"products_respect_unavailable": true` also skip products whose *Unavailable* condition matches the
  shop (the Irish V4 shop ignores that condition, so Ireland has it set to `false`).
- On the page: name, real product link, category, description, specifications, advantages, print options
  (colours, print colours, print methods, print sizes), file guidelines, product FAQs (delivery/status questions
  filtered out) and content blocks. **Not** on the page: prices, stock, delivery dates (they are not in Contentful).

## What goes on a page
Category name, real URL, category path, summary, search terms, the text blocks, product lists
(names + highlights), related categories and the category-page FAQs.

Skipped on purpose: filters, reviews, banners, promo cards, blog teasers.

## Change things
| I want to… | Do this |
|---|---|
| Turn on products for a shop | In `config/shops.json` add `"products": true` to that shop. Then add `products/<shop>/sitemap.xml` in Engaige. |
| Add a shop (e.g. Italy) | In `config/shops.json` set `"enabled": true` for that shop (or copy an entry). Then add its sitemap URL in Engaige. |
| Keep/drop certain FAQs | Edit the patterns in `config/faq_filters.json`. Dropped FAQs are listed in `report.html`. |
| Rebuild now | GitHub → **Actions** → **Build knowledge site** → **Run workflow**. |

## Run it on your own computer (optional)
```
pip install -r requirements.txt
export CONTENTFUL_SPACE_ID=wm1n7oady8a5 CONTENTFUL_CDA_TOKEN=<token>
python build.py --out _site --site-url https://quintenbauwens-a11y.github.io/anna-knowledge
```
