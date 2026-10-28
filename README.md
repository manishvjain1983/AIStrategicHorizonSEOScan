# AI Strategic Horizon SEO Scan

Twice a week, GitHub Actions crawls https://ai.strategichorizon.net and pulls Google Search Console data. Results land in `data/latest/` and `data/history/<date>/`. A Claude scheduled task reads them later the same morning and writes the top 10 SEO actions to the "SEO Check Log" doc.

Nothing here needs your laptop.

## Schedule

- Scan: Wednesday and Saturday, 11:00 UTC (7:00 AM Toronto in summer, 6:00 AM in winter).
- Claude report: same days, 7:45 AM Toronto.
- Run it any time from the Actions tab: SEO scan, then Run workflow.

## One-time setup

1. **Create a key for the service account.** In Google Cloud Console, open IAM & Admin, then Service Accounts. Click `aistrategichorizon-seo@aistrategichorizonwebsite.iam.gserviceaccount.com`, open the Keys tab, click Add key, then Create new key, and pick JSON. A file downloads.
2. **Enable the API.** In the same project, open APIs & Services, then Library. Search "Google Search Console API" and click Enable.
3. **Add the key to GitHub.** In this repo, open Settings, then Secrets and variables, then Actions. Click New repository secret. Name it `GSC_SA_KEY` and paste the whole JSON file content. Save. Delete the downloaded file from your computer afterwards.
4. **Optional: name the property.** If the scan reports it can't find the property, add a repository variable (same page, Variables tab) named `GSC_SITE` with the exact property name, for example `https://ai.strategichorizon.net/` or `sc-domain:strategichorizon.net`.
5. **Test.** Open the Actions tab, pick SEO scan, click Run workflow. After about 2 minutes, `data/latest/summary.md` should show crawl results and Search Console numbers.

## What the scan collects

Crawl: status codes, redirects, titles, meta descriptions, canonicals, H1s, raw HTML word counts, schema, image alt text, sitemap coverage, `.html` duplicates, robots.txt, llms.txt.

Search Console: clicks, impressions, top queries and pages (last 28 days, ending 3 days ago), quick-win queries at positions 8 to 20, sitemap status, and URL Inspection results for every sitemap URL (index verdict, coverage reason, last crawl, Google's chosen canonical).

## Safety

The service account has read-only scope. Never commit the JSON key. `.gitignore` blocks common key file names.
