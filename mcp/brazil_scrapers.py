"""
Scrapers for Brazilian job platforms: Gupy and Vagas.com.br.
No external dependencies beyond requests + BeautifulSoup (stdlib-compatible fallback).
"""

import json
import re
import html as html_mod
from datetime import datetime
from urllib.parse import quote

import requests

# Gupy API — public, no auth required
GUPY_API = "https://portal.api.gupy.io/api/job"

# Vagas.com.br — HTML scraping
VAGAS_BASE = "https://www.vagas.com.br"


def search_gupy(query, results_wanted=15, is_remote=False, location=""):
    """Search Gupy's public API. Returns list of job dicts."""
    jobs = []
    offset = 0
    per_page = 10  # API caps at 10

    while len(jobs) < results_wanted:
        params = {"name": query, "offset": offset, "limit": per_page}
        if location:
            params["state"] = location

        try:
            resp = requests.get(GUPY_API, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[Gupy] Error fetching offset {offset}: {e}")
            break

        items = data.get("data", [])
        total = data.get("pagination", {}).get("total", 0)

        if not items:
            break

        for item in items:
            workplace = item.get("workplaceType", "")
            if is_remote and workplace not in ("remote", "hybrid"):
                continue

            # Extract salary from description HTML if present
            desc_html = item.get("description", "")
            salary = _extract_salary_from_html(desc_html)
            desc_text = _html_to_text(desc_html)

            job_url = item.get("jobUrl", "")

            # Skip inactive listings with broken URLs
            if "&" in job_url.split("?")[0] or "inactive.gupy.io" in job_url:
                continue

            jobs.append({
                "title": item.get("name", ""),
                "company": item.get("careerPageName", ""),
                "location": _gupy_location(item),
                "job_url": job_url,
                "job_url_direct": job_url,  # Gupy apply is always on their site
                "salary": salary,
                "site": "gupy",
                "date_posted": _parse_date(item.get("publishedDate", "")),
                "description": desc_text[:3000],
                "is_remote": workplace == "remote",
                "workplace_type": workplace,
            })

            if len(jobs) >= results_wanted:
                break

        offset += per_page
        if offset >= total:
            break

    return jobs


def search_vagas(query, results_wanted=15, is_remote=False):
    """Scrape Vagas.com.br search results. Returns list of job dicts."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("[Vagas] BeautifulSoup not available, skipping")
        return []

    jobs = []
    page = 1
    slug = quote(query.replace(" ", "-"))

    while len(jobs) < results_wanted:
        url = f"{VAGAS_BASE}/vagas-de-{slug}?pagina={page}&ordenar_por=mais_recentes"
        if is_remote:
            url += "&m[]=100%25+Home+Office"

        try:
            resp = requests.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            })
            resp.raise_for_status()
        except Exception as e:
            print(f"[Vagas] Error fetching page {page}: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        listings = soup.select("li.vaga")

        if not listings:
            break

        for li in listings:
            title_el = li.select_one("a.link-detalhes-vaga")
            if not title_el:
                continue

            title = title_el.get("title", "") or title_el.get_text(strip=True)
            href = title_el.get("href", "")
            job_url = VAGAS_BASE + href if href.startswith("/") else href

            company_el = li.select_one("span.emprVaga")
            company = company_el.get_text(strip=True) if company_el else ""

            location_el = li.select_one("span.vaga-local")
            location = location_el.get_text(strip=True) if location_el else ""

            date_el = li.select_one("span.data-publicacao")
            date_text = date_el.get_text(strip=True) if date_el else ""

            desc_el = li.select_one("div.detalhes")
            description = desc_el.get_text(strip=True) if desc_el else ""

            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "job_url": job_url,
                "job_url_direct": job_url,
                "salary": "",
                "site": "vagas",
                "date_posted": _parse_br_date(date_text),
                "description": description[:3000],
                "is_remote": is_remote,
            })

            if len(jobs) >= results_wanted:
                break

        page += 1

    # Fetch full descriptions for top results (detail pages have JSON-LD)
    for job in jobs[:min(results_wanted, 20)]:
        try:
            _enrich_vagas_detail(job)
        except Exception:
            pass

    return jobs


def _enrich_vagas_detail(job):
    """Fetch Vagas.com.br detail page for full description and JSON-LD data."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return

    resp = requests.get(job["job_url"], timeout=10, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract JSON-LD
    ld_script = soup.select_one('script[type="application/ld+json"]')
    if ld_script:
        try:
            ld = json.loads(ld_script.string)
            if ld.get("description"):
                job["description"] = _html_to_text(ld["description"])[:3000]
            loc = ld.get("jobLocation", {})
            if isinstance(loc, dict):
                addr = loc.get("address", {})
                city = addr.get("addressLocality", "")
                state = addr.get("addressRegion", "")
                if city or state:
                    job["location"] = f"{city} / {state}".strip(" /")
        except (json.JSONDecodeError, AttributeError):
            pass

    # Try to extract salary
    salary_el = soup.select_one("span.info-icon--salary")
    if salary_el:
        salary_text = salary_el.find_next_sibling(string=True)
        if salary_text and "combinar" not in salary_text.lower():
            job["salary"] = salary_text.strip()


# --- Helpers ---

def _gupy_location(item):
    parts = []
    if item.get("city"):
        parts.append(item["city"])
    if item.get("state"):
        parts.append(item["state"])
    if not parts and item.get("country"):
        parts.append(item["country"])
    wt = item.get("workplaceType", "")
    if wt == "remote":
        parts.append("Remote")
    elif wt == "hybrid":
        parts.append("Hybrid")
    return " / ".join(parts) if parts else ""


def _parse_date(iso_str):
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return ""


def _parse_br_date(text):
    """Parse Brazilian date format like '16/01/2026'."""
    try:
        return datetime.strptime(text.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return ""


def _html_to_text(html_str):
    """Simple HTML to text conversion."""
    if not html_str:
        return ""
    text = re.sub(r'<br\s*/?>', '\n', html_str)
    text = re.sub(r'<li[^>]*>', '\n- ', text)
    text = re.sub(r'<p[^>]*>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = html_mod.unescape(text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _extract_salary_from_html(html_str):
    """Try to find salary info in Gupy description HTML."""
    if not html_str:
        return ""
    text = _html_to_text(html_str).lower()
    patterns = [
        r'(?:sal[aá]rio|remunera[çc][aã]o)\s*:?\s*(r\$[\d\.,]+(?:\s*(?:a|até|-)\s*r\$[\d\.,]+)?)',
        r'(r\$\s*[\d\.,]+(?:\s*(?:a|até|-)\s*r\$\s*[\d\.,]+)?)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return ""
