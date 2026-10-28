"""SEO scan for ai.strategichorizon.net.

Runs on GitHub Actions. Crawls the site and pulls Google Search Console data
through the official API with a service account. Writes results to data/.

Environment:
  GSC_SA_KEY   service account JSON key (GitHub secret). If missing, the
               Search Console part is skipped and the crawl still runs.
  GSC_SITE     optional. Search Console property, e.g.
               "https://ai.strategichorizon.net/" or "sc-domain:strategichorizon.net".
               If unset, the script picks the matching property it can see.
"""

import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://ai.strategichorizon.net"
HOST = urlparse(BASE).netloc
UA = "Mozilla/5.0 (compatible; SHR-SEO-Scan/1.0; +https://ai.strategichorizon.net)"
TIMEOUT = 30
THIN_WORDS = 150
OUT = Path("data")
TODAY = dt.date.today().isoformat()

session = requests.Session()
session.headers["User-Agent"] = UA


# ---------------------------------------------------------------- crawl

def fetch(url, follow=True):
    try:
        r = session.get(url, timeout=TIMEOUT, allow_redirects=follow)
        return r
    except requests.RequestException as e:
        print(f"fetch failed {url}: {e}", file=sys.stderr)
        return None


def norm(url):
    url = url.split("#")[0].split("?")[0]
    return url


def path_of(url):
    p = urlparse(url).path or "/"
    return p


def page_facts(url):
    r = fetch(url, follow=True)
    if r is None:
        return {"url": url, "status": "ERR"}
    facts = {
        "url": url,
        "path": path_of(url),
        "status": r.status_code,
        "final_url": r.url if r.url != url else "",
        "redirect_chain": [h.status_code for h in r.history],
    }
    if "text/html" not in r.headers.get("Content-Type", ""):
        return facts
    soup = BeautifulSoup(r.text, "html.parser")
    desc = soup.find("meta", attrs={"name": "description"})
    robots = soup.find("meta", attrs={"name": "robots"})
    canon = soup.find("link", rel="canonical")
    schema_count = len(soup.find_all("script", type="application/ld+json"))
    for t in soup(["script", "style", "noscript", "template"]):
        t.decompose()
    text = soup.get_text(" ", strip=True)
    imgs = soup.find_all("img")
    facts.update({
        "title": (soup.title.string or "").strip() if soup.title else "",
        "description_len": len(desc["content"]) if desc and desc.get("content") else 0,
        "canonical": canon["href"] if canon and canon.get("href") else "",
        "robots_meta": robots["content"] if robots and robots.get("content") else "",
        "noindex": bool(robots and "noindex" in (robots.get("content") or "").lower()),
        "h1_count": len(soup.find_all("h1")),
        "raw_html_words": len(text.split()),
        "schema_count": schema_count,
        "images": len(imgs),
        "images_no_alt": sum(1 for i in imgs if not (i.get("alt") or "").strip()),
        "internal_links": sorted({
            norm(urljoin(url, a["href"]))
            for a in soup.find_all("a", href=True)
            if urlparse(urljoin(url, a["href"])).netloc == HOST
        }),
    })
    facts["thin"] = facts["raw_html_words"] < THIN_WORDS
    return facts


def crawl():
    sm = fetch(f"{BASE}/sitemap.xml")
    sitemap_urls = re.findall(r"<loc>\s*(.*?)\s*</loc>", sm.text) if sm is not None and sm.ok else []
    lastmods = dict(re.findall(r"<loc>\s*(.*?)\s*</loc>\s*<lastmod>\s*(.*?)\s*</lastmod>", sm.text)) if sm is not None and sm.ok else {}

    home = page_facts(BASE + "/")
    to_visit = list(dict.fromkeys(sitemap_urls + home.get("internal_links", [])))
    pages, seen = {}, set()
    while to_visit and len(seen) < 200:
        u = to_visit.pop(0)
        if u in seen:
            continue
        seen.add(u)
        f = page_facts(u)
        f["in_sitemap"] = u in sitemap_urls
        f["lastmod"] = lastmods.get(u, "")
        pages[u] = f
        for link in f.get("internal_links", []):
            if link not in seen and link not in to_visit:
                to_visit.append(link)
        time.sleep(0.3)

    # .html duplicates: check raw status without following redirects
    html_dupes = []
    for u, f in pages.items():
        if u.endswith(".html"):
            raw = fetch(u, follow=False)
            html_dupes.append({
                "url": u,
                "status_no_follow": raw.status_code if raw is not None else "ERR",
                "location": raw.headers.get("Location", "") if raw is not None else "",
            })

    # which internal links point to .html
    html_links = sorted({l for f in pages.values() for l in f.get("internal_links", []) if l.endswith(".html")})

    robots = fetch(f"{BASE}/robots.txt")
    llms = fetch(f"{BASE}/llms.txt")

    clean_pages = [f for u, f in pages.items() if not u.endswith(".html")]
    noindex_pages = sorted(f["path"] for f in clean_pages if f.get("noindex"))
    clean_pages = [f for f in clean_pages if not f.get("noindex")]
    summary = {
        "date": TODAY,
        "sitemap_count": len(sitemap_urls),
        "pages_crawled": len(pages),
        "noindex_pages": noindex_pages,
        "broken": [f["url"] for f in pages.values() if f.get("status") != 200],
        "not_in_sitemap": sorted(f["url"] for f in clean_pages if not f.get("in_sitemap") and f.get("status") == 200),
        "thin_pages": sorted(f["path"] for f in clean_pages if f.get("thin")),
        "no_h1": sorted(f["path"] for f in clean_pages if f.get("h1_count") == 0),
        "no_schema": sorted(f["path"] for f in clean_pages if f.get("schema_count") == 0),
        "no_description": sorted(f["path"] for f in clean_pages if f.get("description_len") == 0),
        "indexable_profile": any(f["path"].startswith("/profile") and not f.get("noindex") for f in clean_pages),
        "internal_links_to_html": html_links,
        "html_duplicates": html_dupes,
        "home_images": home.get("images", 0),
        "home_images_no_alt": home.get("images_no_alt", 0),
        "home_h1": home.get("h1_count", 0),
        "titles": sorted({f.get("title", "") for f in clean_pages if f.get("title")}),
        "robots_txt": robots.text[:500] if robots is not None and robots.ok else f"status {getattr(robots, 'status_code', 'ERR')}",
        "llms_txt_exists": bool(llms is not None and llms.ok and "<html" not in llms.text[:200].lower()),
    }
    return {"summary": summary, "pages": pages, "sitemap_urls": sitemap_urls}


# ---------------------------------------------------------------- search console

def gsc(sitemap_urls):
    key = os.environ.get("GSC_SA_KEY", "").strip()
    if not key:
        return {"skipped": "GSC_SA_KEY secret not set"}
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_info(
        json.loads(key), scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)

    sites = [s["siteUrl"] for s in svc.sites().list().execute().get("siteEntry", [])]
    site = os.environ.get("GSC_SITE", "").strip()
    if not site:
        for cand in (BASE + "/", "sc-domain:strategichorizon.net", "https://strategichorizon.net/"):
            if cand in sites:
                site = cand
                break
    if not site:
        return {"error": "No matching Search Console property visible to the service account", "visible_sites": sites}

    out = {"site": site, "visible_sites": sites}
    end = dt.date.today() - dt.timedelta(days=3)
    start = end - dt.timedelta(days=27)
    host_filter = [{"filters": [{"dimension": "page", "operator": "contains", "expression": HOST}]}]

    def query(dims, limit):
        body = {"startDate": start.isoformat(), "endDate": end.isoformat(),
                "dimensions": dims, "rowLimit": limit, "dimensionFilterGroups": host_filter}
        return svc.searchanalytics().query(siteUrl=site, body=body).execute().get("rows", [])

    try:
        tot = query([], 1)
        out["period"] = f"{start} to {end}"
        out["totals"] = tot[0] if tot else {"clicks": 0, "impressions": 0}
        out["top_queries"] = query(["query"], 50)
        out["top_pages"] = query(["page"], 50)
        out["quick_wins"] = [r for r in out["top_queries"] if 8 <= r.get("position", 0) <= 20]
    except Exception as e:
        out["performance_error"] = str(e)

    try:
        out["sitemaps"] = svc.sitemaps().list(siteUrl=site).execute().get("sitemap", [])
    except Exception as e:
        out["sitemaps_error"] = str(e)

    inspections, counts = [], {}
    for u in sitemap_urls[:60]:
        try:
            res = svc.urlInspection().index().inspect(
                body={"inspectionUrl": u, "siteUrl": site}).execute()
            ir = res.get("inspectionResult", {}).get("indexStatusResult", {})
            row = {
                "url": u,
                "verdict": ir.get("verdict"),
                "coverage": ir.get("coverageState"),
                "last_crawl": ir.get("lastCrawlTime"),
                "google_canonical": ir.get("googleCanonical"),
                "user_canonical": ir.get("userCanonical"),
                "sitemaps": ir.get("sitemap", []),
                "page_fetch": ir.get("pageFetchState"),
                "robots": ir.get("robotsTxtState"),
                "indexing": ir.get("indexingState"),
            }
        except Exception as e:
            row = {"url": u, "error": str(e)[:300]}
        inspections.append(row)
        key_ = row.get("coverage") or "error"
        counts[key_] = counts.get(key_, 0) + 1
        time.sleep(0.5)
    out["inspection_counts"] = counts
    out["indexed_count"] = sum(1 for r in inspections if r.get("verdict") == "PASS")
    out["inspections"] = inspections
    return out


# ---------------------------------------------------------------- report

def write_markdown(c, g):
    s = c["summary"]
    lines = [f"# SEO scan data, {TODAY}", ""]
    lines += ["## Crawl", f"- Sitemap URLs: {s['sitemap_count']}; pages crawled: {s['pages_crawled']}",
              f"- Broken: {s['broken'] or 'none'}",
              f"- Pages marked noindex (excluded from checks below): {s['noindex_pages'] or 'none'}",
              f"- Live pages missing from sitemap: {s['not_in_sitemap'] or 'none'}",
              f"- Thin raw HTML (<{THIN_WORDS} words): {s['thin_pages'] or 'none'}",
              f"- Pages without H1: {s['no_h1'] or 'none'}",
              f"- Pages without schema: {s['no_schema'] or 'none'}",
              f"- Internal links pointing to .html: {len(s['internal_links_to_html'])}",
              f"- .html URLs returning 200 instead of 301: {sum(1 for d in s['html_duplicates'] if d['status_no_follow'] == 200)}",
              f"- /profile indexable: {s['indexable_profile']}",
              f"- Homepage images without alt: {s['home_images_no_alt']} of {s['home_images']}",
              f"- llms.txt present: {s['llms_txt_exists']}", ""]
    lines += ["## Search Console"]
    if "skipped" in g or "error" in g:
        lines.append(f"- {g.get('skipped') or g.get('error')}")
    else:
        t = g.get("totals", {})
        lines += [f"- Property: {g['site']}; period: {g.get('period', '')}",
                  f"- Clicks: {t.get('clicks', 0)}; impressions: {t.get('impressions', 0)}",
                  f"- Indexed (of {len(g.get('inspections', []))} inspected): {g.get('indexed_count', 0)}",
                  f"- Coverage states: {g.get('inspection_counts', {})}",
                  f"- Sitemaps: {[(m.get('path'), m.get('lastDownloaded'), m.get('errors')) for m in g.get('sitemaps', [])]}",
                  "", "### Quick wins (position 8 to 20)"]
        for r in g.get("quick_wins", [])[:15]:
            lines.append(f"- {r['keys'][0]}: pos {r['position']:.1f}, {r['impressions']} impressions")
    return "\n".join(lines) + "\n"


def main():
    c = crawl()
    try:
        g = gsc(c["sitemap_urls"])
    except Exception as e:
        g = {"error": f"Search Console call failed: {e}"}
    for folder in (OUT / "latest", OUT / "history" / TODAY):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "crawl.json").write_text(json.dumps(c, indent=2))
        (folder / "gsc.json").write_text(json.dumps(g, indent=2))
        (folder / "summary.md").write_text(write_markdown(c, g))
    print(write_markdown(c, g))


if __name__ == "__main__":
    main()
