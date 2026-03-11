"""
Joberator Dashboard — job search + tracker + settings UI.
Run: python scripts/kanban.py
Opens at http://localhost:5151
"""

import json
import os
import sys
import sqlite3
import subprocess
import threading
import webbrowser
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Add mcp/ to path so we can import matching.py and job_search_server
_mcp_dir = os.path.join(os.path.dirname(__file__), "..", "mcp")
sys.path.insert(0, _mcp_dir)

# Auto-relaunch with the MCP venv Python if jobspy isn't available
_venv_python = os.path.join(_mcp_dir, ".venv", "bin", "python")
if os.path.exists(_venv_python):
    try:
        from jobspy import scrape_jobs  # noqa: F401
    except ImportError:
        os.execv(_venv_python, [_venv_python] + sys.argv)

DB_PATH = os.path.expanduser("~/.joberator/jobs.db")
PROFILE_PATH = os.path.expanduser("~/.joberator/profile.json")
CONFIG_PATH = os.path.expanduser("~/.joberator/config.json")
PORT = 5151

VALID_STATUSES = ["interested", "applied", "interviewing", "offered", "rejected", "archived"]

DEFAULT_CONFIG = {
    "search_defaults": {
        "is_remote": True,
        "location": "",
        "results_wanted": 15,
        "hours_old": 4320,
        "job_type": "",
        "min_salary": 0,
        "sites": "linkedin,indeed,google,gupy,vagas",
        "country": "Brazil",
        "distance": 50,
    },
    "cron_jobs": [],  # [{id, name, search_params, schedule, enabled, last_run}]
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        # Merge with defaults for any missing keys
        for k, v in DEFAULT_CONFIG.items():
            if k not in cfg:
                cfg[k] = v
            elif isinstance(v, dict):
                for dk, dv in v.items():
                    if dk not in cfg[k]:
                        cfg[k][dk] = dv
        return cfg
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def get_jobs():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM jobs ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]



def delete_job(job_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()


def save_job(title, company, location, url, salary, source, description):
    """Save job, returning (True, id) or (False, 'duplicate') if URL exists."""
    conn = sqlite3.connect(DB_PATH)
    if url:
        existing = conn.execute("SELECT id FROM jobs WHERE url = ?", (url,)).fetchone()
        if existing:
            conn.close()
            return False, "duplicate"
    cur = conn.execute(
        """INSERT INTO jobs (title, company, location, url, salary, source, description, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'interested', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (title, company, location, url, salary, source, description),
    )
    job_id = cur.lastrowid
    conn.commit()
    conn.close()
    return True, job_id


def update_job(job_id, fields):
    """Update multiple fields on a job (status, notes)."""
    conn = sqlite3.connect(DB_PATH)
    allowed = {"status", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if "status" in updates and updates["status"] not in VALID_STATUSES:
        conn.close()
        return False
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [job_id]
        conn.execute(
            f"UPDATE jobs SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values,
        )
        conn.commit()
    conn.close()
    return True


def get_profile():
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH) as f:
            return json.load(f)
    return None


def run_search(params):
    """Run a job search using jobspy + brazilian scrapers + scoring engine."""
    from jobspy import scrape_jobs
    from matching import build_profile_fingerprint, generate_search_queries, score_job
    from brazil_scrapers import search_gupy, search_vagas

    profile = get_profile()
    if not profile:
        return {"error": "No profile found. Sync your LinkedIn profile first."}

    fp = build_profile_fingerprint(profile)

    search_term = params.get("search_term", "")
    if search_term:
        queries = [search_term]
    else:
        queries = generate_search_queries(fp)

    site_list = [s.strip() for s in params.get("sites", "linkedin,indeed,google,gupy,vagas").split(",") if s.strip()]

    is_remote = params.get("is_remote", False)
    results_wanted = int(params.get("results_wanted", 15))

    # Separate Brazilian scrapers from jobspy sites
    brazil_sites = {"gupy", "vagas"}
    jobspy_sites = {"linkedin", "indeed", "google"}
    native_remote_sites = {"linkedin"}
    text_remote_sites = {"indeed", "google"}

    br_site_list = [s for s in site_list if s in brazil_sites]
    js_site_list = [s for s in site_list if s in jobspy_sites]

    # Portuguese equivalents for common English job titles (for BR platforms)
    _title_pt = {
        "analytics engineer": "engenheiro de dados",
        "data analytics engineer": "engenheiro de dados",
        "data engineer": "engenheiro de dados",
        "data analyst": "analista de dados",
        "data analytics": "analista de dados",
        "business intelligence": "business intelligence",
        "business intelligence analyst": "analista BI",
        "software engineer": "engenheiro de software",
        "full stack developer": "desenvolvedor full stack",
        "frontend developer": "desenvolvedor frontend",
        "backend developer": "desenvolvedor backend",
        "web developer": "desenvolvedor web",
        "web designer": "web designer",
        "product manager": "gerente de produto",
        "project manager": "gerente de projetos",
        "devops engineer": "engenheiro devops",
        "machine learning": "machine learning",
        "qa engineer": "analista de qualidade",
    }

    def _get_br_queries(q):
        """Get Portuguese query variants for Brazilian platforms."""
        ql = q.lower().strip()
        variants = [q]  # always include original
        for en, pt in _title_pt.items():
            if en in ql:
                variants.append(pt)
                break
        return list(dict.fromkeys(variants))  # dedupe preserving order

    all_jobs = []
    queries_used = []
    for query in queries:
        # --- Brazilian scrapers (use PT variants) ---
        br_queries = _get_br_queries(query) if br_site_list else []
        for br_site in br_site_list:
            for br_q in br_queries:
                try:
                    if br_site == "gupy":
                        br_jobs = search_gupy(br_q, results_wanted=results_wanted,
                                              is_remote=is_remote, location=params.get("location", ""))
                    elif br_site == "vagas":
                        br_jobs = search_vagas(br_q, results_wanted=results_wanted,
                                               is_remote=is_remote)
                    else:
                        continue

                    if br_jobs:
                        import pandas as pd
                        all_jobs.append(pd.DataFrame(br_jobs))
                        queries_used.append({"query": f"{br_q} ({br_site})", "count": len(br_jobs)})
                except Exception as e:
                    queries_used.append({"query": f"{br_q} ({br_site})", "count": 0, "error": str(e)})

        # --- jobspy sites ---
        if not js_site_list:
            continue

        native_sites = [s for s in js_site_list if s in native_remote_sites]
        text_sites = [s for s in js_site_list if s in text_remote_sites]

        search_groups = []
        if native_sites:
            search_groups.append((native_sites, query))
        if text_sites and is_remote:
            rq = query + " remote" if "remote" not in query.lower() else query
            search_groups.append((text_sites, rq))
        elif text_sites:
            search_groups.append((text_sites, query))

        if not is_remote:
            search_groups = [(js_site_list, query)]

        for sites_group, search_query in search_groups:
            kwargs = {
                "site_name": sites_group,
                "search_term": search_query,
                "results_wanted": results_wanted,
                "country_indeed": params.get("country", "USA"),
                "linkedin_fetch_description": True,
            }
            hours_old = int(params.get("hours_old", 4320))
            if hours_old > 0:
                kwargs["hours_old"] = hours_old
            if params.get("location"):
                kwargs["location"] = params["location"]
            if is_remote:
                kwargs["is_remote"] = True
            if params.get("job_type"):
                kwargs["job_type"] = params["job_type"]

            try:
                import pandas as pd
                result = scrape_jobs(**kwargs)
                if not result.empty:
                    all_jobs.append(result)
                    queries_used.append({"query": search_query, "count": len(result)})
            except Exception as e:
                queries_used.append({"query": search_query, "count": 0, "error": str(e)})
                continue

    if not all_jobs:
        return {"jobs": [], "queries": queries_used, "total": 0}

    import pandas as pd
    jobs = pd.concat(all_jobs, ignore_index=True)
    if "job_url" in jobs.columns:
        jobs = jobs.drop_duplicates(subset=["job_url"], keep="first")

    min_salary = int(params.get("min_salary", 0))
    if min_salary > 0 and "min_amount" in jobs.columns:
        jobs = jobs[(jobs["min_amount"].isna()) | (jobs["min_amount"] >= min_salary)]

    scored_jobs = []
    for _, job in jobs.iterrows():
        desc = str(job.get("description", ""))
        title = str(job.get("title", ""))
        total, pct, breakdown = score_job(desc, title, fp)

        min_amt = job.get("min_amount")
        max_amt = job.get("max_amount")
        salary_str = ""
        try:
            if pd.notna(min_amt) and pd.notna(max_amt):
                salary_str = f"${min_amt:,.0f} - ${max_amt:,.0f}"
            elif pd.notna(min_amt):
                salary_str = f"${min_amt:,.0f}+"
            elif pd.notna(max_amt):
                salary_str = f"Up to ${max_amt:,.0f}"
        except (TypeError, ValueError):
            pass

        # Determine apply URL and easy-apply status
        direct_url = str(job.get("job_url_direct", "") or "")
        if direct_url in ("", "nan", "None"):
            direct_url = ""
        job_url = str(job.get("job_url", ""))
        is_easy_apply = not direct_url and "linkedin.com" in job_url
        if is_easy_apply:
            apply_url = job_url.split("?")[0].rstrip("/") + "/apply/"
        elif direct_url:
            apply_url = direct_url
        else:
            apply_url = job_url

        scored_jobs.append({
            "title": str(job.get("title", "")),
            "company": str(job.get("company", "")),
            "location": str(job.get("location", "")),
            "url": job_url,
            "apply_url": apply_url,
            "easy_apply": is_easy_apply,
            "salary": salary_str,
            "source": str(job.get("site", "")),
            "posted": str(job.get("date_posted", "")),
            "description": str(job.get("description", ""))[:3000],
            "score": pct,
            "breakdown": breakdown,
        })

    scored_jobs.sort(key=lambda x: x["score"], reverse=True)

    return {
        "jobs": scored_jobs[:50],
        "queries": queries_used,
        "total": len(scored_jobs),
        "profile": {
            "name": f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(),
            "skills": len(fp["skills"]),
            "techs": len(fp["desc_techs"]),
            "years": fp["years_exp"],
            "seniority": fp["seniority"],
        },
    }


# Track running searches
_search_results = {}
_search_lock = threading.Lock()
_search_counter = 0


def start_search_async(params):
    global _search_counter
    with _search_lock:
        _search_counter += 1
        search_id = str(_search_counter)
        _search_results[search_id] = {"status": "running"}

    def _run():
        try:
            result = run_search(params)
            with _search_lock:
                _search_results[search_id] = {"status": "done", "result": result}
        except Exception as e:
            with _search_lock:
                _search_results[search_id] = {"status": "error", "error": str(e)}

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return search_id


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Joberator</title>
<style>
  :root {
    --bg: #0a0a0c;
    --surface: #141418;
    --surface2: #1c1c22;
    --border: #26262e;
    --border-hover: #38384a;
    --text: #eeeef0;
    --text-dim: #8888a0;
    --text-faint: #55556a;
    --accent: #6366f1;
    --accent-dim: #4f46e5;
    --accent-glow: rgba(99,102,241,0.12);
    --green: #22c55e;
    --green-dim: rgba(34,197,94,0.12);
    --yellow: #eab308;
    --yellow-dim: rgba(234,179,8,0.12);
    --red: #ef4444;
    --red-dim: rgba(239,68,68,0.12);
    --purple: #a855f7;
    --purple-dim: rgba(168,85,247,0.12);
    --blue: #3b82f6;
    --blue-dim: rgba(59,130,246,0.12);
    --interested: #3b82f6;
    --applied: #a855f7;
    --interviewing: #eab308;
    --offered: #22c55e;
    --rejected: #ef4444;
    --archived: #52525b;
    --radius: 10px;
    --radius-sm: 6px;
    --radius-lg: 14px;
    --src-linkedin: #0a66c2;
    --src-indeed: #ff5a1f;
    --src-google: #34a853;
    --src-gupy: #f22d8a;
    --src-vagas: #ff6600;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Inter', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }

  /* --- NAV --- */
  nav {
    display: flex;
    align-items: center;
    padding: 0 24px;
    height: 52px;
    border-bottom: 1px solid var(--border);
    gap: 4px;
    position: sticky;
    top: 0;
    background: var(--bg);
    z-index: 50;
  }

  .logo {
    font-size: 15px;
    font-weight: 700;
    letter-spacing: -0.5px;
    margin-right: 24px;
    color: var(--text);
  }

  .nav-tab {
    padding: 8px 14px;
    font-size: 13px;
    font-weight: 500;
    color: var(--text-dim);
    cursor: pointer;
    border-radius: var(--radius-sm);
    transition: all 0.15s;
    border: none;
    background: none;
    user-select: none;
  }

  .nav-tab:hover { color: var(--text); background: var(--surface); }
  .nav-tab.active { color: var(--text); background: var(--accent-glow); }

  .nav-right {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .profile-badge {
    font-size: 12px;
    color: var(--text-dim);
    padding: 4px 10px;
    border-radius: 20px;
    background: var(--surface);
    border: 1px solid var(--border);
  }

  /* --- TAB CONTENT --- */
  .tab-content { display: none; }
  .tab-content.active { display: block; }

  /* --- SEARCH TAB --- */
  .search-layout {
    display: grid;
    grid-template-columns: 260px 1fr;
    min-height: calc(100vh - 52px);
  }

  .search-sidebar {
    border-right: 1px solid var(--border);
    padding: 12px 14px;
    overflow-y: auto;
    max-height: calc(100vh - 52px);
    position: sticky;
    top: 52px;
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .sidebar-section {
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
  }
  .sidebar-section:last-child { border-bottom: none; }

  .sidebar-section-title {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: var(--text-faint);
    margin-bottom: 8px;
  }

  .search-sidebar h3 { display: none; }

  .form-group {
    margin-bottom: 8px;
  }

  .form-group label {
    display: block;
    font-size: 11px;
    color: var(--text-dim);
    margin-bottom: 3px;
    font-weight: 500;
  }

  .form-group input[type="text"],
  .form-group input[type="number"],
  .form-group select {
    width: 100%;
    padding: 6px 8px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text);
    font-size: 12px;
    font-family: inherit;
    outline: none;
    transition: border-color 0.15s;
  }

  .form-group input:focus,
  .form-group select:focus {
    border-color: var(--accent);
  }

  .form-group input::placeholder { color: var(--text-faint); }

  .form-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }

  .toggle-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 4px 0;
  }

  .toggle-row span {
    font-size: 12px;
    color: var(--text);
  }

  .toggle {
    position: relative;
    width: 36px;
    height: 20px;
    cursor: pointer;
  }

  .toggle input {
    opacity: 0;
    width: 0;
    height: 0;
  }

  .toggle-slider {
    position: absolute;
    inset: 0;
    background: var(--border);
    border-radius: 10px;
    transition: background 0.2s;
  }

  .toggle-slider::before {
    content: '';
    position: absolute;
    width: 14px;
    height: 14px;
    left: 3px;
    bottom: 3px;
    background: var(--text);
    border-radius: 50%;
    transition: transform 0.2s;
  }

  .toggle input:checked + .toggle-slider {
    background: var(--accent);
  }

  .toggle input:checked + .toggle-slider::before {
    transform: translateX(16px);
  }

  .site-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .site-chip {
    padding: 3px 8px;
    font-size: 11px;
    border-radius: 4px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text-faint);
    cursor: pointer;
    transition: all 0.15s;
    user-select: none;
  }

  .site-chip:hover { border-color: var(--border-hover); }

  .site-chip.active { color: white; border-color: transparent; }
  .site-chip.active[data-site="linkedin"] { background: var(--src-linkedin); }
  .site-chip.active[data-site="indeed"] { background: var(--src-indeed); }
  .site-chip.active[data-site="google"] { background: var(--src-google); }
  .site-chip.active[data-site="gupy"] { background: var(--src-gupy); }
  .site-chip.active[data-site="vagas"] { background: var(--src-vagas); }

  .btn {
    padding: 9px 16px;
    border-radius: var(--radius-sm);
    font-size: 13px;
    font-weight: 600;
    font-family: inherit;
    cursor: pointer;
    border: none;
    transition: all 0.15s;
  }

  .btn-primary {
    background: var(--accent);
    color: white;
    width: 100%;
    margin-top: 10px;
    padding: 8px 14px;
  }

  .btn-primary:hover { background: var(--accent-dim); }

  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-small {
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 500;
  }

  .btn-ghost {
    background: none;
    color: var(--text-dim);
    border: 1px solid var(--border);
  }

  .btn-ghost:hover { border-color: var(--border-hover); color: var(--text); }

  .btn-save {
    background: var(--green-dim);
    color: var(--green);
    border: 1px solid transparent;
  }

  .btn-save:hover { border-color: var(--green); }

  .btn-save.saved {
    opacity: 0.5;
    cursor: default;
  }

  /* --- SEARCH RESULTS --- */
  .results-area {
    padding: 14px 18px;
    overflow-y: auto;
    max-height: calc(100vh - 52px);
  }

  .results-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 10px;
    gap: 8px;
  }

  .results-header h2 {
    font-size: 14px;
    font-weight: 600;
  }

  .results-meta {
    font-size: 11px;
    color: var(--text-dim);
  }

  .platform-legend {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 10px;
  }

  .platform-legend-item {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 10px;
    color: var(--text-dim);
  }

  .platform-legend-dot {
    width: 8px;
    height: 8px;
    border-radius: 2px;
  }


  .queries-bar {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    margin-bottom: 10px;
  }

  .query-chip {
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 12px;
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text-dim);
  }

  .query-chip .count {
    color: var(--accent);
    font-weight: 600;
  }

  .results-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 6px;
  }

  .job-card-result {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    border-left: 3px solid var(--border);
    padding: 10px 12px 8px;
    transition: border-color 0.15s, background 0.15s;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .job-card-result:hover { background: var(--surface2); border-color: var(--border-hover); }

  /* Platform color-coded left border */
  .job-card-result[data-source="linkedin"] { border-left-color: var(--src-linkedin); }
  .job-card-result[data-source="indeed"] { border-left-color: var(--src-indeed); }
  .job-card-result[data-source="google"] { border-left-color: var(--src-google); }
  .job-card-result[data-source="gupy"] { border-left-color: var(--src-gupy); }
  .job-card-result[data-source="vagas"] { border-left-color: var(--src-vagas); }

  .job-card-result .top-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
  }

  .job-card-result .title {
    font-size: 12.5px;
    font-weight: 600;
    line-height: 1.25;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
    min-width: 0;
  }

  .score-pct {
    font-size: 12px;
    font-weight: 700;
    flex-shrink: 0;
    padding: 0 2px;
  }
  .score-pct.high { color: var(--green); }
  .score-pct.mid { color: var(--yellow); }
  .score-pct.low { color: var(--text-faint); }

  .job-card-result .subtitle {
    font-size: 11px;
    color: var(--text-dim);
    display: flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .easy-apply-badge {
    display: inline-block;
    font-size: 8px;
    font-weight: 700;
    padding: 1px 4px;
    border-radius: 2px;
    background: #0a66c2;
    color: white;
    flex-shrink: 0;
    letter-spacing: 0.3px;
    text-transform: uppercase;
  }

  .source-dot {
    width: 7px;
    height: 7px;
    border-radius: 2px;
    flex-shrink: 0;
    display: inline-block;
  }

  .match-tags {
    display: flex;
    gap: 3px;
    flex-wrap: wrap;
  }

  .match-tag {
    font-size: 9.5px;
    padding: 1px 5px;
    border-radius: 3px;
    background: var(--surface2);
    color: var(--text-dim);
  }

  .match-tag.skill { background: var(--blue-dim); color: var(--blue); }
  .match-tag.tech { background: var(--purple-dim); color: var(--purple); }
  .match-tag.domain { background: var(--green-dim); color: var(--green); }

  .job-card-result .card-footer {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 10px;
    color: var(--text-faint);
    margin-top: auto;
  }

  .card-footer .salary { color: var(--green); font-weight: 500; }

  .card-footer .actions {
    margin-left: auto;
    display: flex;
    gap: 3px;
  }

  .card-footer .actions .btn {
    font-size: 10px;
    padding: 2px 7px;
    border-radius: 4px;
  }

  /* Hide score bar in grid — just show percentage */
  .score-badge, .score-bar { display: none; }

  .spinner {
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }

  .spinner-large {
    width: 28px;
    height: 28px;
    border-width: 3px;
  }

  @keyframes spin { to { transform: rotate(360deg); } }

  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 80px 20px;
    gap: 16px;
    color: var(--text-dim);
    font-size: 14px;
  }

  .empty-results {
    text-align: center;
    padding: 80px 20px;
    color: var(--text-dim);
    font-size: 14px;
  }

  .empty-results .icon { font-size: 36px; margin-bottom: 12px; }

  /* Profile card in search sidebar */
  .profile-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 10px 12px;
    margin-bottom: 0;
  }

  .profile-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
  }

  .profile-header .profile-name {
    font-size: 12px;
    font-weight: 600;
  }

  .profile-header .profile-brief {
    font-size: 10px;
    color: var(--text-dim);
  }

  .profile-toggle-icon {
    font-size: 10px;
    color: var(--text-faint);
    transition: transform 0.2s;
  }

  .profile-card.collapsed .profile-details { display: none; }
  .profile-card.collapsed .profile-toggle-icon { transform: rotate(-90deg); }

  .profile-details {
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--border);
  }

  .profile-skills-cloud {
    display: flex;
    flex-wrap: wrap;
    gap: 3px;
    margin-bottom: 8px;
  }

  .profile-skills-cloud .skill-tag {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 3px;
    background: var(--accent-glow);
    color: var(--accent);
  }

  .profile-searches-label {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-faint);
    margin-bottom: 4px;
  }

  .profile-searches {
    display: flex;
    flex-wrap: wrap;
    gap: 3px;
  }

  .search-query-chip {
    font-size: 10px;
    padding: 2px 7px;
    border-radius: 3px;
    background: var(--surface2);
    color: var(--text-dim);
    cursor: pointer;
    transition: background 0.15s;
  }
  .search-query-chip:hover {
    background: var(--accent-glow);
    color: var(--accent);
  }

  .profile-card .no-profile {
    font-size: 11px;
    color: var(--text-faint);
  }

  .hint {
    font-size: 9px;
    color: var(--text-faint);
    margin-top: 2px;
    display: block;
    line-height: 1.2;
  }

  /* --- BOARD TAB --- */
  .board {
    display: flex;
    gap: 12px;
    padding: 20px 24px;
    min-height: calc(100vh - 52px);
    align-items: flex-start;
    overflow-x: auto;
  }

  .column {
    flex: 1;
    min-width: 220px;
    max-width: 300px;
  }

  .column-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    margin-bottom: 8px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
  }

  .column-header .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  .column-header .count {
    margin-left: auto;
    font-weight: 400;
    font-size: 11px;
    opacity: 0.6;
  }

  .column[data-status="interested"] .dot { background: var(--interested); }
  .column[data-status="applied"] .dot { background: var(--applied); }
  .column[data-status="interviewing"] .dot { background: var(--interviewing); }
  .column[data-status="offered"] .dot { background: var(--offered); }
  .column[data-status="rejected"] .dot { background: var(--rejected); }
  .column[data-status="archived"] .dot { background: var(--archived); }

  .drop-zone {
    min-height: 60px;
    border-radius: var(--radius);
    transition: background 0.15s;
  }

  .drop-zone.drag-over {
    background: var(--accent-glow);
  }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px 14px;
    margin-bottom: 6px;
    cursor: grab;
    transition: border-color 0.15s, transform 0.1s, opacity 0.15s;
    position: relative;
  }

  .card:hover { border-color: var(--border-hover); }
  .card:active { cursor: grabbing; }
  .card.dragging { opacity: 0.4; transform: scale(0.97); }

  .card-title { font-size: 13px; font-weight: 500; line-height: 1.3; margin-bottom: 3px; }
  .card-company { font-size: 12px; color: var(--text-dim); margin-bottom: 4px; }
  .card-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--text-faint);
  }
  .card-salary { color: var(--green); font-weight: 500; }

  .card-actions {
    position: absolute;
    top: 8px;
    right: 8px;
    display: flex;
    gap: 4px;
    opacity: 0;
    transition: opacity 0.15s;
  }

  .card:hover .card-actions { opacity: 1; }

  .card-actions button {
    background: none;
    border: none;
    color: var(--text-dim);
    cursor: pointer;
    font-size: 13px;
    padding: 2px 4px;
    border-radius: 4px;
    line-height: 1;
  }

  .card-actions button:hover { color: var(--text); background: var(--border); }
  .card-actions .delete-btn:hover { color: var(--red); }

  .empty-board {
    text-align: center;
    padding: 60px 20px;
    color: var(--text-dim);
    font-size: 14px;
    grid-column: 1 / -1;
  }

  /* --- SETTINGS TAB --- */
  .settings-layout {
    max-width: 640px;
    margin: 0 auto;
    padding: 32px 24px;
  }

  .settings-section {
    margin-bottom: 32px;
  }

  .settings-section h2 {
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 4px;
  }

  .settings-section .desc {
    font-size: 13px;
    color: var(--text-dim);
    margin-bottom: 16px;
  }

  .settings-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }

  .settings-grid .full-width {
    grid-column: 1 / -1;
  }

  .cron-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .cron-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px 16px;
  }

  .cron-card .cron-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }

  .cron-card .cron-name {
    font-size: 14px;
    font-weight: 600;
  }

  .cron-card .cron-schedule {
    font-size: 12px;
    color: var(--text-dim);
    margin-bottom: 4px;
  }

  .cron-card .cron-params {
    font-size: 11px;
    color: var(--text-faint);
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .cron-card .cron-actions {
    display: flex;
    gap: 6px;
    margin-top: 8px;
  }

  .cron-modal {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.6);
    z-index: 100;
    align-items: center;
    justify-content: center;
  }

  .cron-modal.active { display: flex; }

  .cron-modal-inner {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    width: 90%;
    max-width: 480px;
    padding: 24px;
    max-height: 80vh;
    overflow-y: auto;
  }

  .cron-modal-inner h3 {
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 16px;
  }

  /* --- MODAL (shared) --- */
  .modal-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.6);
    z-index: 100;
    align-items: center;
    justify-content: center;
  }

  .modal-overlay.active { display: flex; }

  .modal {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    width: 90%;
    max-width: 560px;
    max-height: 80vh;
    overflow-y: auto;
    padding: 24px;
  }

  .modal h2 { font-size: 17px; font-weight: 600; margin-bottom: 4px; }
  .modal .company { font-size: 13px; color: var(--text-dim); margin-bottom: 14px; }
  .modal .detail { margin-bottom: 12px; }
  .modal .detail-label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
    margin-bottom: 3px;
  }
  .modal .detail-value { font-size: 13px; line-height: 1.5; }
  .modal .detail-value a { color: var(--accent); text-decoration: none; }
  .modal .detail-value a:hover { text-decoration: underline; }
  .modal .notes-text { font-size: 12px; color: var(--text-dim); white-space: pre-wrap; line-height: 1.5; }

  /* --- TOAST --- */
  .toast-container {
    position: fixed;
    bottom: 20px;
    right: 20px;
    z-index: 200;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .toast {
    padding: 10px 16px;
    border-radius: var(--radius-sm);
    font-size: 13px;
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text);
    animation: fadeIn 0.2s;
    max-width: 320px;
  }

  .toast.success { border-color: var(--green); }
  .toast.error { border-color: var(--red); }

  @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } }
</style>
</head>
<body>

<nav>
  <div class="logo">Joberator</div>
  <button class="nav-tab active" data-tab="search" onclick="switchTab('search')">Search</button>
  <button class="nav-tab" data-tab="board" onclick="switchTab('board')">Board</button>
  <button class="nav-tab" data-tab="settings" onclick="switchTab('settings')">Settings</button>
  <div class="nav-right">
    <span class="profile-badge" id="profile-badge">No profile</span>
  </div>
</nav>

<!-- ==================== SEARCH TAB ==================== -->
<div class="tab-content active" id="tab-search">
  <div class="search-layout">
    <div class="search-sidebar">
      <!-- Profile card (collapsible) -->
      <div class="sidebar-section" style="padding-top:0">
        <div class="profile-card" id="search-profile-card">
          <div class="no-profile">Loading profile...</div>
        </div>
      </div>

      <!-- Search -->
      <div class="sidebar-section">
        <div class="sidebar-section-title">Search</div>
        <div class="form-group">
          <input type="text" id="s-term" placeholder="Role / Keywords (auto from profile)">
        </div>
        <div class="toggle-row">
          <span>Remote only</span>
          <label class="toggle">
            <input type="checkbox" id="s-remote">
            <span class="toggle-slider"></span>
          </label>
        </div>
        <input type="hidden" id="s-location" value="">
        <div class="form-row">
          <div class="form-group">
            <label>Market</label>
            <select id="s-country">
              <option value="worldwide">Worldwide</option>
              <option value="USA">USA</option>
              <option value="UK">UK</option>
              <option value="Canada">Canada</option>
              <option value="Australia">Australia</option>
              <option value="Brazil" selected>Brazil</option>
              <option value="Germany">Germany</option>
              <option value="France">France</option>
              <option value="India">India</option>
              <option value="Netherlands">Netherlands</option>
              <option value="Spain">Spain</option>
              <option value="Italy">Italy</option>
              <option value="Mexico">Mexico</option>
              <option value="Argentina">Argentina</option>
              <option value="Japan">Japan</option>
              <option value="Singapore">Singapore</option>
              <option value="Ireland">Ireland</option>
            </select>
          </div>
          <div class="form-group">
            <label>Posted within</label>
            <select id="s-hours">
              <option value="24">24 hours</option>
              <option value="72">3 days</option>
              <option value="168">1 week</option>
              <option value="336">2 weeks</option>
              <option value="720">1 month</option>
              <option value="2160">3 months</option>
              <option value="4320" selected>6 months</option>
              <option value="8760">1 year</option>
              <option value="0">All time</option>
            </select>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Job type</label>
            <select id="s-jobtype">
              <option value="">Any</option>
              <option value="fulltime">Full-time</option>
              <option value="parttime">Part-time</option>
              <option value="contract">Contract</option>
              <option value="internship">Internship</option>
            </select>
          </div>
          <div class="form-group">
            <label>Results/query</label>
            <input type="number" id="s-results" value="15" min="5" max="50">
          </div>
        </div>
        <div class="form-group">
          <label>Min salary (USD/yr)</label>
          <input type="number" id="s-salary" placeholder="0" step="10000">
        </div>
      </div>

      <!-- Job boards -->
      <div class="sidebar-section">
        <div class="sidebar-section-title">Platforms</div>
        <div class="site-chips" id="site-chips">
          <span class="site-chip active" data-site="linkedin">LinkedIn</span>
          <span class="site-chip active" data-site="indeed">Indeed</span>
          <span class="site-chip active" data-site="google">Google</span>
          <span class="site-chip active" data-site="gupy">Gupy</span>
          <span class="site-chip active" data-site="vagas">Vagas.com.br</span>
        </div>
      </div>

      <button class="btn btn-primary" id="search-btn" onclick="runSearch()">
        Search Jobs
      </button>
    </div>

    <div class="results-area" id="results-area">
      <div class="empty-results">
        <div class="icon">&#128270;</div>
        <p>Hit "Search Jobs" to find matches</p>
        <p style="margin-top:6px;font-size:12px;color:var(--text-faint)">Your profile is used to auto-generate search queries and score every result</p>
      </div>
    </div>
  </div>
</div>

<!-- ==================== BOARD TAB ==================== -->
<div class="tab-content" id="tab-board">
  <div class="board" id="board"></div>
</div>

<!-- ==================== SETTINGS TAB ==================== -->
<div class="tab-content" id="tab-settings">
  <div class="settings-layout">
    <div class="settings-section">
      <h2>Search Defaults</h2>
      <p class="desc">These values pre-fill the search form. Changes save automatically.</p>
      <div class="settings-grid">
        <div class="form-group">
          <label>Default location</label>
          <input type="text" id="cfg-location" placeholder="e.g. Remote">
        </div>
        <div class="form-group">
          <label>Search region</label>
          <select id="cfg-country">
            <option value="worldwide">Worldwide</option>
            <option value="USA">USA</option>
            <option value="UK">UK</option>
            <option value="Canada">Canada</option>
            <option value="Australia">Australia</option>
            <option value="Brazil">Brazil</option>
            <option value="Germany">Germany</option>
            <option value="France">France</option>
            <option value="India">India</option>
            <option value="Netherlands">Netherlands</option>
          </select>
        </div>
        <div class="form-group">
          <label>Results per query</label>
          <input type="number" id="cfg-results" value="15">
        </div>
        <div class="form-group">
          <label>Posted within</label>
          <select id="cfg-hours">
            <option value="24">Last 24 hours</option>
            <option value="72">Last 3 days</option>
            <option value="168">Last week</option>
            <option value="336">Last 2 weeks</option>
            <option value="720">Last month</option>
            <option value="2160">Last 3 months</option>
            <option value="4320" selected>Last 6 months</option>
            <option value="8760">Last year</option>
            <option value="0">All time</option>
          </select>
        </div>
        <div class="form-group">
          <label>Min salary (USD)</label>
          <input type="number" id="cfg-salary" value="0" step="10000">
        </div>
        <div class="form-group full-width">
          <label>Default sites (comma-separated)</label>
          <input type="text" id="cfg-sites" value="linkedin,indeed,google,gupy,vagas">
        </div>
        <div class="form-group full-width">
          <div class="toggle-row">
            <span>Remote by default</span>
            <label class="toggle">
              <input type="checkbox" id="cfg-remote">
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>
      </div>
      <button class="btn btn-primary" style="max-width:200px" onclick="saveDefaults()">Save Defaults</button>
    </div>

    <div class="settings-section">
      <h2>Scheduled Searches</h2>
      <p class="desc">Set up automated searches that run on a schedule. Results are saved to your board automatically.</p>
      <div class="cron-list" id="cron-list"></div>
      <button class="btn btn-ghost btn-small" style="margin-top:12px" onclick="openCronModal()">+ Add Schedule</button>
    </div>

    <div class="settings-section">
      <h2>Profile</h2>
      <p class="desc">Your LinkedIn profile powers the smart matching engine.</p>
      <div id="profile-info" style="font-size:13px;color:var(--text-dim)">Loading...</div>
    </div>
  </div>
</div>

<!-- Detail modal (board) -->
<div class="modal-overlay" id="modal-overlay" onclick="if(event.target===this)closeModal()">
  <div class="modal" id="modal"></div>
</div>

<!-- Search result detail modal -->
<div class="modal-overlay" id="result-modal-overlay" onclick="if(event.target===this)closeResultModal()">
  <div class="modal" id="result-modal" style="max-width:640px"></div>
</div>

<!-- Cron modal -->
<div class="cron-modal" id="cron-modal" onclick="if(event.target===this)closeCronModal()">
  <div class="cron-modal-inner">
    <h3 id="cron-modal-title">Add Scheduled Search</h3>
    <div class="form-group">
      <label>Name</label>
      <input type="text" id="cron-name" placeholder="e.g. Daily remote analytics jobs">
    </div>
    <div class="form-group">
      <label>Schedule</label>
      <select id="cron-schedule">
        <option value="6h">Every 6 hours</option>
        <option value="12h">Every 12 hours</option>
        <option value="daily" selected>Daily</option>
        <option value="2d">Every 2 days</option>
        <option value="weekly">Weekly</option>
      </select>
    </div>
    <div class="form-group">
      <label>Role / Keywords (empty = auto)</label>
      <input type="text" id="cron-term" placeholder="Leave empty for profile-based search">
    </div>
    <div class="form-group">
      <label>Location</label>
      <input type="text" id="cron-location">
    </div>
    <div class="toggle-row" style="margin-bottom:8px">
      <span style="font-size:13px">Remote only</span>
      <label class="toggle">
        <input type="checkbox" id="cron-remote">
        <span class="toggle-slider"></span>
      </label>
    </div>
    <div class="form-group">
      <label>Job type</label>
      <select id="cron-jobtype">
        <option value="">Any</option>
        <option value="fulltime">Full-time</option>
        <option value="contract">Contract</option>
      </select>
    </div>
    <div class="form-group">
      <label>Min salary (USD)</label>
      <input type="number" id="cron-salary" value="0" step="10000">
    </div>
    <div class="form-group">
      <label>Sites (comma-separated)</label>
      <input type="text" id="cron-sites" value="linkedin,indeed,google,gupy,vagas">
    </div>
    <div class="form-group">
      <label>Min match score to auto-save (%)</label>
      <input type="number" id="cron-min-score" value="50" min="0" max="100">
    </div>
    <div style="display:flex;gap:8px;margin-top:16px">
      <button class="btn btn-primary" style="flex:1" onclick="saveCronJob()">Save</button>
      <button class="btn btn-ghost" onclick="closeCronModal()">Cancel</button>
    </div>
  </div>
</div>

<div class="toast-container" id="toasts"></div>

<script>
// --- State ---
const COLUMNS = ['interested', 'applied', 'interviewing', 'offered', 'rejected', 'archived'];
let boardJobs = [];
let searchResults = [];
let config = null;
let draggedId = null;
let currentSearchId = null;
let editingCronId = null;

// --- Init ---
async function init() {
  await Promise.all([loadBoardJobs(), loadConfig(), loadProfile(), loadFingerprint()]);
  applyDefaults();
}

// --- Tabs ---
function switchTab(tab) {
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.toggle('active', t.id === 'tab-' + tab));
  if (tab === 'board') renderBoard();
  if (tab === 'settings') renderSettings();
}

// --- Toast ---
function toast(msg, type = '') {
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  document.getElementById('toasts').appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// --- Config ---
async function loadConfig() {
  const res = await fetch('/api/config');
  config = await res.json();
}

function applyDefaults() {
  if (!config) return;
  const d = config.search_defaults || {};
  const $ = id => document.getElementById(id);
  $('s-location').value = d.location || '';
  $('s-remote').checked = !!d.is_remote;
  $('s-salary').value = d.min_salary || '';
  $('s-hours').value = d.hours_old || 4320;
  $('s-results').value = d.results_wanted || 15;
  $('s-country').value = d.country || 'worldwide';

  // Set site chips
  const activeSites = (d.sites || 'linkedin,indeed,google').split(',').map(s=>s.trim());
  document.querySelectorAll('.site-chip').forEach(chip => {
    chip.classList.toggle('active', activeSites.includes(chip.dataset.site));
  });
}

async function saveDefaults() {
  const $ = id => document.getElementById(id);
  config.search_defaults = {
    location: $('cfg-location').value,
    country: $('cfg-country').value,
    results_wanted: parseInt($('cfg-results').value) || 15,
    hours_old: parseInt($('cfg-hours').value) || 4320,
    min_salary: parseInt($('cfg-salary').value) || 0,
    sites: $('cfg-sites').value,
    is_remote: $('cfg-remote').checked,
  };
  await fetch('/api/config', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(config)
  });
  applyDefaults();
  toast('Defaults saved', 'success');
}

// --- Profile ---
async function loadProfile() {
  const res = await fetch('/api/profile');
  const profile = await res.json();
  const badge = document.getElementById('profile-badge');
  const info = document.getElementById('profile-info');

  if (profile && profile.first_name) {
    const name = `${profile.first_name} ${profile.last_name || ''}`.trim();
    badge.textContent = name;
    info.innerHTML = `
      <strong>${esc(name)}</strong><br>
      ${esc(profile.headline || '')}<br>
      <span style="color:var(--text-faint)">${(profile.skills || []).length} skills &middot; ${(profile.positions || []).length} positions</span>
    `;
  } else {
    badge.textContent = 'No profile';
    info.textContent = 'No profile synced. Use Claude to run sync_profile.';
  }
}

// --- Fingerprint / Profile card ---
let fingerprint = null;

async function loadFingerprint() {
  try {
    const res = await fetch('/api/fingerprint');
    fingerprint = await res.json();
    renderProfileCard();
  } catch(e) {}
}

function renderProfileCard() {
  const card = document.getElementById('search-profile-card');
  if (!fingerprint || !fingerprint.name) {
    card.innerHTML = '<div class="no-profile">No LinkedIn profile synced. Use Claude to run <code>sync_profile</code>.</div>';
    return;
  }

  const fp = fingerprint;
  const topSkills = [...new Set([...fp.skills, ...fp.techs])];
  const skillTags = topSkills.map(s => `<span class="skill-tag">${esc(s)}</span>`).join('');

  card.innerHTML = `
    <div class="profile-header" onclick="this.parentElement.classList.toggle('collapsed')">
      <div>
        <div class="profile-name">${esc(fp.name)}</div>
        <div class="profile-brief">${fp.seniority.length ? esc(fp.seniority[0]) : ''} &middot; ${fp.years_exp}y exp</div>
      </div>
      <span class="profile-toggle-icon">&#9660;</span>
    </div>
    <div class="profile-details">
      <div class="profile-skills-cloud">${skillTags}</div>
      <div class="profile-searches-label">Will search for:</div>
      <div class="profile-searches">${fp.queries.map(q => `<span class="search-query-chip" onclick="document.getElementById('s-term').value=this.textContent">${esc(q)}</span>`).join('')}</div>
    </div>
  `;
}

// --- Site chips ---
document.querySelectorAll('.site-chip').forEach(chip => {
  chip.addEventListener('click', () => chip.classList.toggle('active'));
});

// --- Search ---
function getSearchParams() {
  const $ = id => document.getElementById(id);
  const region = $('s-country').value;

  // When "Worldwide", only use globally-capable boards (LinkedIn, Google)
  let sites;
  if (region === 'worldwide') {
    const globalSites = ['linkedin', 'google', 'gupy'];
    sites = [...document.querySelectorAll('.site-chip.active')]
      .map(c => c.dataset.site)
      .filter(s => globalSites.includes(s))
      .join(',');
    if (!sites) sites = 'linkedin,google,gupy';
  } else {
    sites = [...document.querySelectorAll('.site-chip.active')].map(c => c.dataset.site).join(',');
  }

  return {
    search_term: $('s-term').value.trim(),
    location: $('s-location').value.trim(),
    is_remote: $('s-remote').checked,
    job_type: $('s-jobtype').value,
    min_salary: parseInt($('s-salary').value) || 0,
    hours_old: parseInt($('s-hours').value) || 4320,
    results_wanted: parseInt($('s-results').value) || 15,
    country: region === 'worldwide' ? 'USA' : region,
    sites: sites || 'linkedin',
  };
}

async function runSearch() {
  const btn = document.getElementById('search-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Searching...';

  const area = document.getElementById('results-area');
  area.innerHTML = '<div class="loading-state"><div class="spinner spinner-large"></div><div>Searching job boards...</div><div style="font-size:12px;color:var(--text-faint)">This may take 30-60 seconds</div></div>';

  try {
    const params = getSearchParams();
    const startRes = await fetch('/api/search', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(params)
    });
    const {search_id} = await startRes.json();
    currentSearchId = search_id;
    pollSearch(search_id);
  } catch (e) {
    area.innerHTML = `<div class="empty-results"><div class="icon">&#9888;</div><p>Search failed: ${esc(e.message)}</p></div>`;
    btn.disabled = false;
    btn.textContent = 'Search Jobs';
  }
}

async function pollSearch(id) {
  const res = await fetch('/api/search/' + id);
  const data = await res.json();

  if (data.status === 'running') {
    setTimeout(() => pollSearch(id), 2000);
    return;
  }

  const btn = document.getElementById('search-btn');
  btn.disabled = false;
  btn.textContent = 'Search Jobs';

  if (data.status === 'error') {
    document.getElementById('results-area').innerHTML =
      `<div class="empty-results"><div class="icon">&#9888;</div><p>${esc(data.error)}</p></div>`;
    return;
  }

  searchResults = data.result.jobs || [];
  renderResults(data.result);
}

function renderResults(data) {
  const area = document.getElementById('results-area');
  const jobs = data.jobs || [];

  if (jobs.length === 0) {
    area.innerHTML = '<div class="empty-results"><div class="icon">&#128566;</div><p>No jobs found. Try adjusting your filters.</p></div>';
    return;
  }

  // Get saved URLs to mark already-saved jobs
  const savedUrls = new Set(boardJobs.map(j => j.url));

  let html = '';

  // Header
  html += `<div class="results-header">
    <div>
      <h2>${data.total} jobs found</h2>
      <span class="results-meta">${data.profile ? data.profile.name + ' &middot; ' : ''}${data.profile ? data.profile.skills + ' skills, ' + data.profile.techs + ' techs, ' + data.profile.years + 'y exp' : ''}</span>
    </div>
  </div>`;

  // Queries
  if (data.queries && data.queries.length > 0) {
    html += '<div class="queries-bar">';
    for (const q of data.queries) {
      html += `<span class="query-chip">${esc(q.query)} <span class="count">${q.count}</span></span>`;
    }
    html += '</div>';
  }

  // Platform legend (only show platforms that have results)
  const platforms = [...new Set(jobs.map(j => (j.source || '').toLowerCase().replace(/\s+/g, '_')))];
  const platformNames = {linkedin:'LinkedIn', indeed:'Indeed', google:'Google', gupy:'Gupy', vagas:'Vagas.com.br'};
  if (platforms.length > 1) {
    html += '<div class="platform-legend">';
    for (const p of platforms) {
      html += `<span class="platform-legend-item"><span class="platform-legend-dot" style="background:var(--src-${p})"></span>${platformNames[p] || p}</span>`;
    }
    html += '</div>';
  }

  // Jobs grid
  html += '<div class="results-grid">';
  for (let i = 0; i < jobs.length; i++) {
    const j = jobs[i];
    const sClass = j.score >= 60 ? 'high' : j.score >= 35 ? 'mid' : 'low';
    const isSaved = savedUrls.has(j.url);
    const src = (j.source || '').toLowerCase().replace(/\s+/g, '_');

    html += `<div class="job-card-result" data-source="${esc(src)}" onclick="showResultDetail(${i})">
      <div class="top-row">
        <div class="title" title="${esc(j.title)}">${esc(j.title)}</div>
        <span class="score-pct ${sClass}">${j.score}%</span>
      </div>
      <div class="subtitle">
        <span class="source-dot" style="background:var(--src-${src})"></span>
        ${esc(j.company)}${j.location ? ' &middot; ' + esc(j.location) : ''}
        ${j.easy_apply ? '<span class="easy-apply-badge">easy apply</span>' : ''}
      </div>`;

    // Tags — max 5 total, deduplicate techs that already appear in skills
    const bd = j.breakdown || {};
    const tags = [];
    const seen = new Set();
    if (bd.skills) bd.skills.slice(0,3).forEach(s => { seen.add(s.toLowerCase()); tags.push(`<span class="match-tag skill">${esc(s)}</span>`); });
    if (bd.techs) bd.techs.filter(t => !seen.has(t.toLowerCase())).slice(0,2).forEach(t => tags.push(`<span class="match-tag tech">${esc(t)}</span>`));
    if (bd.seniority) tags.push(`<span class="match-tag">${esc(bd.seniority)}</span>`);
    if (tags.length) html += `<div class="match-tags">${tags.join('')}</div>`;

    // Footer: date + salary + actions
    html += `<div class="card-footer">`;
    if (j.posted && j.posted !== 'nan') html += `<span>${esc(j.posted)}</span>`;
    if (j.salary) html += `<span class="salary">${esc(j.salary)}</span>`;
    html += `<span class="actions">
      <button class="btn btn-save btn-small ${isSaved ? 'saved' : ''}" onclick="event.stopPropagation();saveResult(${i}, this)" ${isSaved ? 'disabled' : ''}>
        ${isSaved ? '✓' : 'Save'}
      </button>
      ${j.apply_url || j.url ? `<a href="${esc(j.apply_url || j.url)}" target="_blank" class="btn btn-small" style="background:var(--accent);color:white" onclick="event.stopPropagation()">Apply</a>` : ''}
    </span>`;
    html += `</div>`;

    html += '</div>';
  }
  html += '</div>';

  area.innerHTML = html;
}

function showResultDetail(idx) {
  const j = searchResults[idx];
  if (!j) return;
  const modal = document.getElementById('result-modal');
  const bd = j.breakdown || {};

  let descHtml = '';
  if (j.description) {
    descHtml = esc(j.description).replace(/\n/g, '<br>');
  }

  modal.innerHTML = `
    <h2>${esc(j.title)}</h2>
    <div class="company">${esc(j.company)} ${j.location ? '&middot; ' + esc(j.location) : ''}</div>
    <div style="margin-bottom:14px">
      <span class="score-badge ${j.score >= 60 ? 'score-high' : j.score >= 35 ? 'score-mid' : 'score-low'}">
        ${j.score}% match
      </span>
    </div>
    ${j.salary ? `<div class="detail"><div class="detail-label">Salary</div><div class="detail-value">${esc(j.salary)}</div></div>` : ''}
    ${j.url ? `<div class="detail"><div class="detail-label">Link</div><div class="detail-value"><a href="${esc(j.url)}" target="_blank">${esc(j.url)}</a></div></div>` : ''}
    ${j.source ? `<div class="detail"><div class="detail-label">Source</div><div class="detail-value">${esc(j.source)}</div></div>` : ''}
    ${bd.skills && bd.skills.length ? `<div class="detail"><div class="detail-label">Matching Skills</div><div class="detail-value">${bd.skills.map(s => esc(s)).join(', ')}</div></div>` : ''}
    ${bd.techs && bd.techs.length ? `<div class="detail"><div class="detail-label">Matching Tech</div><div class="detail-value">${bd.techs.map(t => esc(t)).join(', ')}</div></div>` : ''}
    ${bd.domains && bd.domains.length ? `<div class="detail"><div class="detail-label">Domain Match</div><div class="detail-value">${bd.domains.map(d => esc(d)).join(', ')}</div></div>` : ''}
    ${descHtml ? `<div class="detail"><div class="detail-label">Description</div><div class="detail-value" style="font-size:12px;max-height:300px;overflow-y:auto">${descHtml}</div></div>` : ''}
  `;

  document.getElementById('result-modal-overlay').classList.add('active');
}

function closeResultModal() {
  document.getElementById('result-modal-overlay').classList.remove('active');
}

async function saveResult(idx, btn) {
  const j = searchResults[idx];
  if (!j) return;
  try {
    const res = await fetch('/api/jobs', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        title: j.title,
        company: j.company,
        location: j.location,
        url: j.url,
        salary: j.salary,
        source: j.source,
        description: j.description,
      })
    });
    const data = await res.json();
    if (data.ok) {
      btn.textContent = '✓';
      btn.classList.add('saved');
      btn.disabled = true;
      toast('Job saved to board', 'success');
      loadBoardJobs();
    } else {
      btn.textContent = '✓';
      btn.classList.add('saved');
      btn.disabled = true;
      toast('Already saved', 'success');
    }
  } catch(e) {
    toast('Failed to save', 'error');
  }
}

// --- Board ---
async function loadBoardJobs() {
  const res = await fetch('/api/jobs');
  boardJobs = await res.json();
}

function renderBoard() {
  const board = document.getElementById('board');

  if (boardJobs.length === 0) {
    board.innerHTML = '<div class="empty-board"><p style="font-size:28px;margin-bottom:10px">&#9744;</p><p>No jobs saved yet.<br>Search and save jobs from the Search tab.</p></div>';
    return;
  }

  board.innerHTML = COLUMNS.map(status => {
    const col = boardJobs.filter(j => j.status === status);
    return `
      <div class="column" data-status="${status}">
        <div class="column-header">
          <span class="dot"></span>
          ${status}
          <span class="count">${col.length}</span>
        </div>
        <div class="drop-zone"
          ondragover="onDragOver(event)"
          ondragleave="onDragLeave(event)"
          ondrop="onDrop(event, '${status}')">
          ${col.map(j => boardCardHTML(j)).join('')}
        </div>
      </div>
    `;
  }).join('');
}

function boardCardHTML(job) {
  const salary = job.salary || '';
  const source = job.source || '';
  const date = job.created_at ? job.created_at.slice(0, 10) : '';
  return `
    <div class="card" draggable="true"
      ondragstart="onDragStart(event, ${job.id})"
      ondragend="onDragEnd(event)"
      onclick="showBoardDetail(${job.id})">
      <div class="card-actions">
        <button class="delete-btn" onclick="event.stopPropagation();deleteBoardJob(${job.id})" title="Delete">&#x2715;</button>
      </div>
      <div class="card-title">${esc(job.title)}</div>
      <div class="card-company">${esc(job.company)}</div>
      <div class="card-meta">
        ${salary ? `<span class="card-salary">${esc(salary)}</span>` : ''}
        ${source ? `<span>${esc(source)}</span>` : ''}
        ${date ? `<span>${date}</span>` : ''}
      </div>
    </div>
  `;
}

function onDragStart(e, id) {
  draggedId = id;
  e.target.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
}
function onDragEnd(e) {
  e.target.classList.remove('dragging');
  document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
}
function onDragOver(e) {
  e.preventDefault();
  e.currentTarget.classList.add('drag-over');
}
function onDragLeave(e) {
  e.currentTarget.classList.remove('drag-over');
}

async function onDrop(e, status) {
  e.preventDefault();
  e.currentTarget.classList.remove('drag-over');
  if (draggedId === null) return;
  const job = boardJobs.find(j => j.id === draggedId);
  if (job && job.status !== status) {
    job.status = status;
    renderBoard();
    await fetch('/api/jobs/' + draggedId, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({status})
    });
  }
  draggedId = null;
}

async function deleteBoardJob(id) {
  if (!confirm('Delete this job?')) return;
  await fetch('/api/jobs/' + id, {method: 'DELETE'});
  boardJobs = boardJobs.filter(j => j.id !== id);
  renderBoard();
  closeModal();
}

function showBoardDetail(id) {
  const job = boardJobs.find(j => j.id === id);
  if (!job) return;
  const modal = document.getElementById('modal');
  const url = job.url ? `<a href="${esc(job.url)}" target="_blank">${esc(job.url)}</a>` : 'N/A';
  const desc = job.description ? esc(job.description).slice(0, 2000).replace(/\n/g, '<br>') : '';

  modal.innerHTML = `
    <h2>${esc(job.title)}</h2>
    <div class="company">${esc(job.company)} ${job.location ? '&middot; ' + esc(job.location) : ''}</div>
    <div style="display:flex;gap:8px;margin:10px 0">
      ${job.url ? `<a href="${esc(job.url)}" target="_blank" class="btn btn-small" style="background:var(--accent);color:white">Apply</a>` : ''}
      <select onchange="updateJobField(${job.id},'status',this.value)" style="font-size:12px;padding:4px 8px;border-radius:4px;background:var(--surface2);color:var(--text);border:1px solid var(--border)">
        ${COLUMNS.map(s => `<option value="${s}" ${job.status === s ? 'selected' : ''}>${s}</option>`).join('')}
      </select>
    </div>
    ${job.salary ? `<div class="detail"><div class="detail-label">Salary</div><div class="detail-value">${esc(job.salary)}</div></div>` : ''}
    ${job.source ? `<div class="detail"><div class="detail-label">Source</div><div class="detail-value">${esc(job.source)}</div></div>` : ''}
    <div class="detail">
      <div class="detail-label">Notes</div>
      <textarea id="job-notes-${job.id}" style="width:100%;min-height:60px;font-size:12px;padding:6px;border-radius:4px;background:var(--surface2);color:var(--text);border:1px solid var(--border);resize:vertical"
        onblur="updateJobField(${job.id},'notes',this.value)"
        placeholder="Add notes...">${esc(job.notes || '')}</textarea>
    </div>
    ${desc ? `<div class="detail"><div class="detail-label">Description</div><div class="detail-value" style="font-size:12px;max-height:300px;overflow-y:auto">${desc}</div></div>` : ''}
  `;
  document.getElementById('modal-overlay').classList.add('active');
}

async function updateJobField(id, field, value) {
  await fetch('/api/jobs/' + id, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({[field]: value})
  });
  const job = boardJobs.find(j => j.id === id);
  if (job) {
    job[field] = value;
    renderBoard();
  }
  if (field === 'status') toast('Status updated', 'success');
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('active');
}

// --- Settings ---
function renderSettings() {
  if (!config) return;
  const d = config.search_defaults || {};
  const $ = id => document.getElementById(id);
  $('cfg-location').value = d.location || '';
  $('cfg-country').value = d.country || 'worldwide';
  $('cfg-results').value = d.results_wanted || 15;
  $('cfg-hours').value = d.hours_old || 4320;
  $('cfg-salary').value = d.min_salary || 0;
  $('cfg-sites').value = d.sites || 'linkedin,indeed,google,gupy,vagas';
  $('cfg-remote').checked = !!d.is_remote;

  renderCronList();
}

function renderCronList() {
  const list = document.getElementById('cron-list');
  const crons = (config.cron_jobs || []);

  if (crons.length === 0) {
    list.innerHTML = '<div style="font-size:13px;color:var(--text-faint);padding:8px 0">No scheduled searches yet.</div>';
    return;
  }

  list.innerHTML = crons.map((c, i) => {
    const params = c.search_params || {};
    const tags = [];
    if (params.search_term) tags.push(params.search_term);
    if (params.is_remote) tags.push('remote');
    if (params.location) tags.push(params.location);
    if (params.min_salary) tags.push('$' + params.min_salary.toLocaleString() + '+');
    if (params.sites) tags.push(params.sites);

    return `<div class="cron-card">
      <div class="cron-top">
        <span class="cron-name">${esc(c.name || 'Search ' + (i+1))}</span>
        <label class="toggle">
          <input type="checkbox" ${c.enabled ? 'checked' : ''} onchange="toggleCron(${i}, this.checked)">
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="cron-schedule">${esc(formatSchedule(c.schedule))} ${c.last_run ? '&middot; Last: ' + esc(c.last_run) : ''}</div>
      <div class="cron-params">${tags.map(t => '<span>' + esc(t) + '</span>').join('')}</div>
      <div class="cron-params" style="margin-top:2px">
        ${c.min_score ? '<span>Min score: ' + c.min_score + '%</span>' : ''}
      </div>
      <div class="cron-actions">
        <button class="btn btn-ghost btn-small" onclick="editCron(${i})">Edit</button>
        <button class="btn btn-ghost btn-small" onclick="runCronNow(${i})">Run Now</button>
        <button class="btn btn-ghost btn-small" style="color:var(--red)" onclick="deleteCron(${i})">Delete</button>
      </div>
    </div>`;
  }).join('');
}

function formatSchedule(s) {
  const map = {'6h': 'Every 6 hours', '12h': 'Every 12 hours', 'daily': 'Daily', '2d': 'Every 2 days', 'weekly': 'Weekly'};
  return map[s] || s;
}

function openCronModal(data) {
  editingCronId = null;
  const $ = id => document.getElementById(id);
  $('cron-modal-title').textContent = 'Add Scheduled Search';
  $('cron-name').value = '';
  $('cron-schedule').value = 'daily';
  $('cron-term').value = '';
  $('cron-location').value = '';
  $('cron-remote').checked = true;
  $('cron-jobtype').value = '';
  $('cron-salary').value = '0';
  $('cron-sites').value = 'linkedin,indeed,google,gupy,vagas';
  $('cron-min-score').value = '50';
  $('cron-modal').classList.add('active');
}

function editCron(idx) {
  const c = config.cron_jobs[idx];
  if (!c) return;
  editingCronId = idx;
  const p = c.search_params || {};
  const $ = id => document.getElementById(id);
  $('cron-modal-title').textContent = 'Edit Scheduled Search';
  $('cron-name').value = c.name || '';
  $('cron-schedule').value = c.schedule || 'daily';
  $('cron-term').value = p.search_term || '';
  $('cron-location').value = p.location || '';
  $('cron-remote').checked = !!p.is_remote;
  $('cron-jobtype').value = p.job_type || '';
  $('cron-salary').value = p.min_salary || 0;
  $('cron-sites').value = p.sites || 'linkedin,indeed,google,gupy,vagas';
  $('cron-min-score').value = c.min_score || 50;
  $('cron-modal').classList.add('active');
}

function closeCronModal() {
  document.getElementById('cron-modal').classList.remove('active');
  editingCronId = null;
}

async function saveCronJob() {
  const $ = id => document.getElementById(id);
  const cron = {
    name: $('cron-name').value.trim() || 'Search',
    schedule: $('cron-schedule').value,
    enabled: true,
    min_score: parseInt($('cron-min-score').value) || 50,
    last_run: null,
    search_params: {
      search_term: $('cron-term').value.trim(),
      location: $('cron-location').value.trim(),
      is_remote: $('cron-remote').checked,
      job_type: $('cron-jobtype').value,
      min_salary: parseInt($('cron-salary').value) || 0,
      sites: $('cron-sites').value.trim(),
    }
  };

  if (editingCronId !== null) {
    cron.last_run = config.cron_jobs[editingCronId].last_run;
    config.cron_jobs[editingCronId] = cron;
  } else {
    config.cron_jobs = config.cron_jobs || [];
    config.cron_jobs.push(cron);
  }

  await fetch('/api/config', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(config)
  });

  closeCronModal();
  renderCronList();
  toast(editingCronId !== null ? 'Schedule updated' : 'Schedule created', 'success');
}

async function toggleCron(idx, enabled) {
  config.cron_jobs[idx].enabled = enabled;
  await fetch('/api/config', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(config)
  });
  toast(enabled ? 'Schedule enabled' : 'Schedule paused', 'success');
}

async function deleteCron(idx) {
  if (!confirm('Delete this scheduled search?')) return;
  config.cron_jobs.splice(idx, 1);
  await fetch('/api/config', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(config)
  });
  renderCronList();
  toast('Schedule deleted');
}

async function runCronNow(idx) {
  const c = config.cron_jobs[idx];
  if (!c) return;

  // Fill search form and run
  const p = c.search_params || {};
  const $ = id => document.getElementById(id);
  $('s-term').value = p.search_term || '';
  $('s-location').value = p.location || '';
  $('s-remote').checked = !!p.is_remote;
  $('s-jobtype').value = p.job_type || '';
  $('s-salary').value = p.min_salary || '';
  $('s-hours').value = p.hours_old || 4320;
  if (p.sites) {
    document.querySelectorAll('.site-chip').forEach(chip => {
      chip.classList.toggle('active', p.sites.split(',').map(s=>s.trim()).includes(chip.dataset.site));
    });
  }

  switchTab('search');
  runSearch();
}

// --- Helpers ---
function esc(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function getApplyUrl(job) {
  return job.apply_url || job.url || '';
}


document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeModal();
    closeResultModal();
    closeCronModal();
  }
});

init();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def _html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/jobs":
            self._json(get_jobs())

        elif path == "/api/config":
            self._json(load_config())

        elif path == "/api/profile":
            profile = get_profile()
            self._json(profile or {})

        elif path == "/api/fingerprint":
            profile = get_profile()
            if profile:
                from matching import build_profile_fingerprint, generate_search_queries
                fp = build_profile_fingerprint(profile)
                queries = generate_search_queries(fp)
                self._json({
                    "name": f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(),
                    "headline": profile.get("headline", ""),
                    "skills": fp["skills"][:12],
                    "techs": fp["desc_techs"][:12],
                    "seniority": fp["seniority"],
                    "years_exp": fp["years_exp"],
                    "domains": fp["domains"][:6],
                    "queries": queries,
                })
            else:
                self._json({})

        elif path.startswith("/api/search/"):
            search_id = path.split("/")[-1]
            with _search_lock:
                result = _search_results.get(search_id, {"status": "not_found"})
            self._json(result)

        else:
            self._html(HTML)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/search":
            params = self._read_body()
            search_id = start_search_async(params)
            self._json({"search_id": search_id})

        elif path == "/api/jobs":
            body = self._read_body()
            ok, result = save_job(
                body.get("title", ""),
                body.get("company", ""),
                body.get("location", ""),
                body.get("url", ""),
                body.get("salary", ""),
                body.get("source", ""),
                body.get("description", ""),
            )
            if ok:
                self._json({"ok": True, "id": result})
            else:
                self._json({"ok": False, "error": result}, 409)

        else:
            self._json({"error": "not found"}, 404)

    def do_PUT(self):
        path = urlparse(self.path).path

        if path == "/api/config":
            cfg = self._read_body()
            save_config(cfg)
            self._json({"ok": True})
        else:
            self._json({"error": "not found"}, 404)

    def do_PATCH(self):
        path = urlparse(self.path).path
        if path.startswith("/api/jobs/"):
            try:
                job_id = int(path.split("/")[-1])
                body = self._read_body()
                update_job(job_id, body)
                self._json({"ok": True})
            except (ValueError, json.JSONDecodeError):
                self._json({"error": "bad request"}, 400)
        else:
            self._json({"error": "not found"}, 404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith("/api/jobs/"):
            try:
                job_id = int(path.split("/")[-1])
                delete_job(job_id)
                self._json({"ok": True})
            except ValueError:
                self._json({"error": "bad request"}, 400)
        else:
            self._json({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


# --- Cron scheduler ---
def run_cron_scheduler():
    """Background thread that checks cron jobs and runs them on schedule."""
    import time

    schedule_seconds = {
        "6h": 6 * 3600,
        "12h": 12 * 3600,
        "daily": 24 * 3600,
        "2d": 2 * 24 * 3600,
        "weekly": 7 * 24 * 3600,
    }

    while True:
        time.sleep(60)  # Check every minute
        try:
            cfg = load_config()
            now = datetime.now()
            changed = False

            for cron in cfg.get("cron_jobs", []):
                if not cron.get("enabled"):
                    continue

                interval = schedule_seconds.get(cron.get("schedule", "daily"), 86400)
                last_run = cron.get("last_run")

                should_run = False
                if not last_run:
                    should_run = True
                else:
                    try:
                        last_dt = datetime.fromisoformat(last_run)
                        if (now - last_dt).total_seconds() >= interval:
                            should_run = True
                    except (ValueError, TypeError):
                        should_run = True

                if should_run:
                    try:
                        params = cron.get("search_params", {})
                        result = run_search(params)
                        min_score = cron.get("min_score", 50)

                        # Auto-save jobs above min_score
                        saved_urls = set()
                        try:
                            for j in get_jobs():
                                if j.get("url"):
                                    saved_urls.add(j["url"])
                        except Exception:
                            pass

                        saved_count = 0
                        for job in result.get("jobs", []):
                            if job["score"] >= min_score and job["url"] not in saved_urls:
                                ok, _ = save_job(
                                    job["title"], job["company"], job["location"],
                                    job["url"], job["salary"], job["source"], job["description"]
                                )
                                if ok:
                                    saved_urls.add(job["url"])
                                    saved_count += 1

                        cron["last_run"] = now.isoformat()[:19]
                        changed = True
                        print(f"[cron] Ran '{cron.get('name')}': {len(result.get('jobs',[]))} found, {saved_count} saved")
                    except Exception as e:
                        print(f"[cron] Error running '{cron.get('name')}': {e}")
                        cron["last_run"] = now.isoformat()[:19]
                        changed = True

            if changed:
                save_config(cfg)
        except Exception:
            pass


def _ensure_schema():
    """Ensure DB has all required columns (safe migration)."""
    conn = sqlite3.connect(DB_PATH)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "notes" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN notes TEXT DEFAULT ''")
        conn.commit()
        print("[db] Added 'notes' column")
    conn.close()


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        print("Run job searches via Claude first to create the database.")
        exit(1)

    _ensure_schema()

    # Start cron scheduler in background
    cron_thread = threading.Thread(target=run_cron_scheduler, daemon=True)
    cron_thread.start()
    print("[cron] Scheduler started")

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Joberator Dashboard -> http://localhost:{PORT}")
    webbrowser.open(f"http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
