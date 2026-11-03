# Anna knowledge site

Builds clean, text-only pages from Helloprint's Contentful content so Anna (Engaige) can sync them
through a **Sitemap knowledge folder** instead of CSV uploads.

**Now included:** category pages (Ireland pilot). Help-centre FAQs and products can be added later.

## How it works
1. Every night (and whenever `build.py` or `config/` changes) GitHub runs `build.py`.
2. It reads **published** category pages from Contentful with a read-only key (repository secrets
   `CONTENTFUL_SPACE_ID` and `CONTENTFUL_CDA_TOKEN`).
3. Per shop it keeps only the blocks that are visible on that shop (Contentful "per shop conditions"),
   fills in `{{shop_name}}` etc., and writes one page per category:
   `categories/<shop>/<category-slug>/`.
4. Each shop gets a sitemap: `categories/<shop>/sitemap.xml` → add that URL to an Engaige *Sitemap* folder.
5. Every page links to the real helloprint.com category page; Anna should cite that link.
6. `report.html` lists what was left out and why. A copy of every build is saved in `snapshot/`.

## What goes on a page
Category name, real URL, category path, summary, search terms, the text blocks, product lists
(names + highlights), related categories and the category-page FAQs.

Skipped on purpose: filters, reviews, banners, promo cards, blog teasers.

## Change things
| I want to… | Do this |
|---|---|
| Add a shop (e.g. Italy) | In `config/shops.json` set `"enabled": true` for that shop (or copy an entry). Then add its sitemap URL in Engaige. |
| Keep/drop certain FAQs | Edit the patterns in `config/faq_filters.json`. Dropped FAQs are listed in `report.html`. |
| Rebuild now | GitHub → **Actions** → **Build knowledge site** → **Run workflow**. |

## Run it on your own computer (optional)
```
pip install -r requirements.txt
export CONTENTFUL_SPACE_ID=wm1n7oady8a5 CONTENTFUL_CDA_TOKEN=<token>
python build.py --out _site --site-url https://quintenbauwens-a11y.github.io/anna-knowledge
```
