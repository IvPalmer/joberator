"""
Joberator Job Search MCP Server
Searches LinkedIn, Indeed, Glassdoor, ZipRecruiter, and Google Jobs
using python-jobspy. No login required.
"""

import csv
import io
import json
import os
import re
import sqlite3
import zipfile
from datetime import datetime
from mcp.server.fastmcp import FastMCP
import pandas as pd
from jobspy import scrape_jobs
from linkedin_auth import (
    refresh_cookies,
    get_li_at_cookie,
    get_jsessionid,
    is_connected,
    clear_session,
    open_linkedin_in_browser,
)
from matching import (
    build_profile_fingerprint as _build_profile_fingerprint,
    generate_search_queries as _generate_search_queries,
    score_job as _score_job,
)

mcp = FastMCP("joberator-jobs")

# --- Job Tracking Database ---

DB_DIR = os.path.expanduser("~/.joberator")
DB_PATH = os.path.join(DB_DIR, "jobs.db")
PROFILE_PATH = os.path.join(DB_DIR, "profile.json")

VALID_STATUSES = [
    "interested", "applied", "interviewing", "offered", "rejected", "archived"
]


def init_db():
    """Create the ~/.joberator directory and jobs table if they don't exist."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT,
            url TEXT,
            salary TEXT,
            source TEXT,
            description TEXT,
            notes TEXT,
            status TEXT DEFAULT 'interested',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


init_db()


@mcp.tool()
def search_jobs(
    search_term: str,
    location: str = "",
    results_wanted: int = 20,
    hours_old: int = 72,
    is_remote: bool = False,
    job_type: str = "",
    min_salary: int = 0,
    sites: str = "linkedin,indeed,glassdoor,zip_recruiter,google",
    country: str = "USA",
    linkedin_fetch_description: bool = True,
    distance: int = 50,
) -> str:
    """Search for jobs across multiple job boards simultaneously.

    Args:
        search_term: Job title or keywords (e.g. "python developer", "data engineer")
        location: City, state, or region (e.g. "San Francisco, CA", "Remote")
        results_wanted: Number of results per site (default 20)
        hours_old: Only show jobs posted within this many hours (default 72)
        is_remote: Filter for remote jobs only
        job_type: Filter by type: fulltime, parttime, internship, contract
        min_salary: Minimum annual salary filter (USD)
        sites: Comma-separated job boards: linkedin,indeed,glassdoor,zip_recruiter,google
        country: Country for Indeed search (default USA)
        linkedin_fetch_description: Fetch full job descriptions from LinkedIn (slower but more detail)
        distance: Distance in miles from location (default 50)
    """
    site_list = [s.strip() for s in sites.split(",") if s.strip()]

    # Split: LinkedIn has native remote filter; Indeed/Google need "remote" in query text
    native_remote = {"linkedin", "zip_recruiter"}
    text_remote = {"indeed", "google", "glassdoor"}

    all_frames = []
    if is_remote:
        native = [s for s in site_list if s in native_remote]
        text = [s for s in site_list if s in text_remote]
        groups = []
        if native:
            groups.append((native, search_term))
        if text:
            rq = search_term + " remote" if "remote" not in search_term.lower() else search_term
            groups.append((text, rq))
    else:
        groups = [(site_list, search_term)]

    for sites_grp, query in groups:
        kwargs = {
            "site_name": sites_grp,
            "search_term": query,
            "results_wanted": results_wanted,
            "hours_old": hours_old,
            "country_indeed": country,
            "linkedin_fetch_description": linkedin_fetch_description,
        }
        if location:
            kwargs["location"] = location
        if is_remote:
            kwargs["is_remote"] = True
        if job_type:
            kwargs["job_type"] = job_type
        if not is_remote and distance:
            kwargs["distance"] = distance
        try:
            result = scrape_jobs(**kwargs)
            if not result.empty:
                all_frames.append(result)
        except Exception as e:
            continue

    if not all_frames:
        return "No jobs found matching your criteria."

    jobs = pd.concat(all_frames, ignore_index=True)
    if "job_url" in jobs.columns:
        jobs = jobs.drop_duplicates(subset=["job_url"], keep="first")

    if jobs.empty:
        return "No jobs found matching your criteria."

    # Filter by minimum salary if set
    if min_salary > 0:
        if "min_amount" in jobs.columns:
            jobs = jobs[
                (jobs["min_amount"].isna())
                | (jobs["min_amount"] >= min_salary)
            ]

    # Sort by date posted (newest first)
    if "date_posted" in jobs.columns:
        jobs = jobs.sort_values("date_posted", ascending=False)

    # Format output as markdown
    output_lines = [f"# Job Search Results: {search_term}"]
    output_lines.append(f"*{len(jobs)} jobs found across {', '.join(site_list)}*\n")

    for i, (_, job) in enumerate(jobs.iterrows(), 1):
        title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        loc = job.get("location", "N/A")
        site = job.get("site", "")
        url = job.get("job_url", "")
        posted = job.get("date_posted", "")
        desc = job.get("description", "")
        min_amt = job.get("min_amount", "")
        max_amt = job.get("max_amount", "")

        salary_str = ""
        if min_amt and max_amt:
            salary_str = f"${min_amt:,.0f} - ${max_amt:,.0f}"
        elif min_amt:
            salary_str = f"${min_amt:,.0f}+"
        elif max_amt:
            salary_str = f"Up to ${max_amt:,.0f}"

        output_lines.append(f"## {i}. {title}")
        output_lines.append(f"**Company:** {company}")
        output_lines.append(f"**Location:** {loc}")
        if salary_str:
            output_lines.append(f"**Salary:** {salary_str}")
        output_lines.append(f"**Source:** {site}")
        if posted:
            output_lines.append(f"**Posted:** {posted}")
        if url:
            output_lines.append(f"**URL:** {url}")
        if desc:
            # Truncate long descriptions
            short_desc = desc[:500] + "..." if len(str(desc)) > 500 else desc
            output_lines.append(f"\n{short_desc}")
        output_lines.append("")

    return "\n".join(output_lines)


# --- Job Tracking Tools ---


@mcp.tool()
def save_job(
    title: str,
    company: str,
    location: str = "",
    url: str = "",
    salary: str = "",
    source: str = "",
    description: str = "",
    notes: str = "",
) -> str:
    """Save a job from search results to the tracking database.

    Args:
        title: Job title
        company: Company name
        location: Job location
        url: Job posting URL
        salary: Salary info (e.g. "$120,000 - $150,000")
        source: Where the job was found (e.g. linkedin, indeed)
        description: Job description text
        notes: Personal notes about this job
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        """INSERT INTO jobs (title, company, location, url, salary, source, description, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, company, location, url, salary, source, description, notes),
    )
    job_id = cur.lastrowid
    conn.commit()
    conn.close()
    return f"Saved job #{job_id}: **{title}** at **{company}** (status: interested)"


@mcp.tool()
def list_saved_jobs(status: str = "all") -> str:
    """List saved jobs filtered by status.

    Args:
        status: Filter by status — all, interested, applied, interviewing, offered, rejected, archived
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if status == "all":
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY updated_at DESC"
        ).fetchall()
    else:
        if status not in VALID_STATUSES:
            conn.close()
            return f"Invalid status '{status}'. Valid options: {', '.join(VALID_STATUSES)}"
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY updated_at DESC", (status,)
        ).fetchall()

    conn.close()

    if not rows:
        label = f"with status '{status}'" if status != "all" else ""
        return f"No saved jobs {label}.".strip()

    lines = [f"# Saved Jobs ({status})\n"]
    lines.append("| ID | Title | Company | Location | Status | Salary | Source | Saved |")
    lines.append("|---|---|---|---|---|---|---|---|")

    for r in rows:
        saved = r["created_at"][:10] if r["created_at"] else ""
        lines.append(
            f"| {r['id']} | {r['title']} | {r['company']} | {r['location'] or ''} "
            f"| {r['status']} | {r['salary'] or ''} | {r['source'] or ''} | {saved} |"
        )

    lines.append(f"\n*{len(rows)} job(s)*")
    return "\n".join(lines)


@mcp.tool()
def update_job_status(job_id: int, status: str, notes: str = "") -> str:
    """Update a saved job's status and optionally add notes.

    Args:
        job_id: The job ID to update
        status: New status — interested, applied, interviewing, offered, rejected, archived
        notes: Optional notes to append (leave empty to keep existing notes)
    """
    if status not in VALID_STATUSES:
        return f"Invalid status '{status}'. Valid options: {', '.join(VALID_STATUSES)}"

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        conn.close()
        return f"Job #{job_id} not found."

    if notes:
        existing = row["notes"] or ""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        updated_notes = f"{existing}\n[{timestamp}] ({status}) {notes}".strip()
        conn.execute(
            "UPDATE jobs SET status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, updated_notes, job_id),
        )
    else:
        conn.execute(
            "UPDATE jobs SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, job_id),
        )

    conn.commit()
    conn.close()
    return f"Updated job #{job_id} (**{row['title']}** at **{row['company']}**) to status: **{status}**"


@mcp.tool()
def delete_job(job_id: int) -> str:
    """Remove a job from tracking.

    Args:
        job_id: The job ID to delete
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    row = conn.execute("SELECT title, company FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        conn.close()
        return f"Job #{job_id} not found."

    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    return f"Deleted job #{job_id}: **{row['title']}** at **{row['company']}**"


@mcp.tool()
def job_stats() -> str:
    """Get summary statistics for saved jobs: total count, count by status, and recent activity."""
    conn = sqlite3.connect(DB_PATH)

    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    if total == 0:
        conn.close()
        return "No saved jobs yet. Use `save_job` to start tracking jobs."

    status_counts = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status ORDER BY cnt DESC"
    ).fetchall()

    recent = conn.execute(
        "SELECT id, title, company, status, updated_at FROM jobs ORDER BY updated_at DESC LIMIT 5"
    ).fetchall()

    conn.close()

    lines = ["# Job Tracking Stats\n"]
    lines.append(f"**Total saved jobs:** {total}\n")
    lines.append("## By Status")
    for status, count in status_counts:
        lines.append(f"- **{status}:** {count}")

    lines.append("\n## Recent Activity")
    for job_id, title, company, status, updated in recent:
        updated_short = updated[:16] if updated else ""
        lines.append(f"- #{job_id} **{title}** at {company} — {status} ({updated_short})")

    return "\n".join(lines)


@mcp.tool()
def linkedin_connect() -> str:
    """Connect your LinkedIn account by reading cookies from your browser.

    Just be logged into LinkedIn in Chrome or Brave — that's it.
    On first use, macOS will ask for Keychain access (click Allow).
    If no session is found, opens LinkedIn in your browser so you can log in.
    """
    result = refresh_cookies()

    if result["success"]:
        return f"LinkedIn connected via {result['source']}.\n\nRun `sync_profile` to import your profile data."

    # No cookie found — open LinkedIn in browser to trigger login/cookie refresh
    opened = open_linkedin_in_browser()
    if opened:
        return (
            "No active LinkedIn session found in your browser.\n"
            "LinkedIn has been opened in your browser — please log in or wait for the page to load,\n"
            "then run `linkedin_connect` again to pick up the session."
        )
    else:
        return f"LinkedIn connection failed: {result['error']}"


@mcp.tool()
def linkedin_status() -> str:
    """Check if your LinkedIn account is connected."""
    if is_connected():
        return "LinkedIn: **Connected**\n\nYour session is active. Use `sync_profile` to pull your latest profile data."
    else:
        return "LinkedIn: **Not connected**\n\nRun `linkedin_connect` to log in through your browser."


@mcp.tool()
def linkedin_disconnect() -> str:
    """Disconnect your LinkedIn account and clear saved session data."""
    clear_session()
    return "LinkedIn session cleared. Run `linkedin_connect` to reconnect."


def _voyager_session():
    """Create an authenticated requests session for LinkedIn Voyager API."""
    import requests as req

    li_at = get_li_at_cookie()
    jsessionid = get_jsessionid()
    if not li_at or not jsessionid:
        return None, None, None

    session = req.Session()
    session.cookies.set("li_at", li_at, domain=".linkedin.com")
    session.cookies.set("JSESSIONID", '"' + jsessionid + '"', domain=".linkedin.com")
    session.headers.update({
        "csrf-token": jsessionid,
        "x-restli-protocol-version": "2.0.0",
        "accept": "application/vnd.linkedin.normalized+json+2.1",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    })
    return session, li_at, jsessionid


def _fetch_full_profile(session, vanity_name: str) -> dict:
    """Fetch full profile data from LinkedIn Voyager API."""
    url = (
        "https://www.linkedin.com/voyager/api/identity/dash/profiles"
        f"?q=memberIdentity&memberIdentity={vanity_name}"
        "&decorationId=com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-93"
    )
    resp = session.get(url)
    if resp.status_code != 200:
        raise Exception(f"LinkedIn API returned {resp.status_code}")

    data = resp.json()
    included = data.get("included", [])

    # Parse entities by type
    profile_data = {}
    target_urn = ""
    positions = []
    education = []
    skills = []
    languages = []
    companies = {}

    # First pass: find the target profile by vanity name and extract member ID
    target_member_id = ""
    for item in included:
        if (
            item.get("$type") == "com.linkedin.voyager.dash.identity.profile.Profile"
            and item.get("publicIdentifier") == vanity_name
        ):
            profile_data = item
            target_urn = item.get("entityUrn", "")
            # Extract member ID from URN like urn:li:fsd_profile:ACoAAA0U0c4B...
            parts = target_urn.split(":")
            if len(parts) >= 4:
                target_member_id = parts[-1]
            break

    def _belongs_to_target(item):
        """Check if an entity belongs to the target profile by member ID in URN."""
        if not target_member_id:
            return True  # Can't filter, include everything
        urn = item.get("entityUrn", "")
        return target_member_id in urn

    for item in included:
        item_type = item.get("$type", "")

        if item_type == "com.linkedin.voyager.dash.identity.profile.Position" and _belongs_to_target(item):
            date_range = item.get("dateRange", {})
            start = date_range.get("start", {})
            end = date_range.get("end", {})
            company_urn = item.get("companyUrn", "")
            positions.append({
                "title": item.get("title", ""),
                "company": item.get("companyName", ""),
                "company_urn": company_urn,
                "description": item.get("description", ""),
                "location": item.get("locationName", ""),
                "start_date": f"{start.get('year', '')}-{start.get('month', 1):02d}" if start.get("year") else "",
                "end_date": f"{end.get('year', '')}-{end.get('month', 1):02d}" if end.get("year") else "Present",
            })

        elif item_type == "com.linkedin.voyager.dash.identity.profile.Education" and _belongs_to_target(item):
            date_range = item.get("dateRange", {})
            start = date_range.get("start", {})
            end = date_range.get("end", {})
            education.append({
                "school": item.get("schoolName", ""),
                "degree": item.get("degreeName", ""),
                "field_of_study": item.get("fieldOfStudy", ""),
                "start_date": f"{start.get('year', '')}-{start.get('month', 1):02d}" if start.get("year") else "",
                "end_date": f"{end.get('year', '')}-{end.get('month', 1):02d}" if end.get("year") else "",
            })

        elif item_type == "com.linkedin.voyager.dash.identity.profile.Skill" and _belongs_to_target(item):
            name = item.get("name", "")
            if name:
                skills.append(name)

        elif item_type == "com.linkedin.voyager.dash.identity.profile.Language" and _belongs_to_target(item):
            languages.append({
                "name": item.get("name", ""),
                "proficiency": item.get("proficiency", ""),
            })

        elif item_type == "com.linkedin.voyager.dash.organization.Company":
            urn = item.get("entityUrn", "")
            companies[urn] = item.get("name", "")

    # Resolve company names from URNs
    for pos in positions:
        if not pos["company"] and pos.get("company_urn") in companies:
            pos["company"] = companies[pos["company_urn"]]
        pos.pop("company_urn", None)

    # Get geo/industry from profile
    geo_name = ""
    industry_name = ""
    for item in included:
        item_type = item.get("$type", "")
        if item_type == "com.linkedin.voyager.dash.common.Geo":
            if not geo_name:
                geo_name = item.get("defaultLocalizedName", "")
        elif item_type == "com.linkedin.voyager.dash.common.Industry":
            if not industry_name:
                industry_name = item.get("name", "")

    return {
        "source": "linkedin_voyager",
        "synced_at": datetime.now().isoformat(),
        "first_name": profile_data.get("firstName", ""),
        "last_name": profile_data.get("lastName", ""),
        "headline": profile_data.get("headline", ""),
        "summary": profile_data.get("summary", ""),
        "industry": industry_name,
        "location": geo_name,
        "skills": skills,
        "positions": positions,
        "education": education,
        "languages": languages,
    }


@mcp.tool()
def sync_profile(linkedin_url: str = "") -> str:
    """Sync your LinkedIn profile using your connected browser session.

    Reads cookies directly from Chrome/Brave — just be logged into LinkedIn.

    Args:
        linkedin_url: Your LinkedIn profile URL (e.g. https://linkedin.com/in/yourname). If empty, fetches the authenticated user's profile.
    """
    session, li_at, jsessionid = _voyager_session()
    if not session:
        return (
            "Not connected to LinkedIn.\n"
            "Make sure you're logged into LinkedIn in Chrome or Brave,\n"
            "then run `linkedin_connect`."
        )

    # Resolve vanity name
    vanity_name = ""
    if linkedin_url:
        parts = linkedin_url.rstrip("/").split("/in/")
        if len(parts) == 2:
            vanity_name = parts[1].split("/")[0].split("?")[0]
        else:
            return f"Could not extract profile name from URL: {linkedin_url}\nExpected format: https://linkedin.com/in/yourname"

    if not vanity_name:
        try:
            resp = session.get("https://www.linkedin.com/voyager/api/me")
            if resp.status_code != 200:
                return f"LinkedIn API error ({resp.status_code}). Try running `linkedin_connect` to refresh."
            me = resp.json()
            # Find our own miniProfile URN from data.*miniProfile
            my_urn = me.get("data", {}).get("*miniProfile", "")
            for item in me.get("included", []):
                if item.get("entityUrn") == my_urn and item.get("publicIdentifier"):
                    vanity_name = item["publicIdentifier"]
                    break
            if not vanity_name:
                return "Could not determine your profile. Please provide your LinkedIn URL."
        except Exception as e:
            return f"Failed to fetch profile: {e}"

    # Fetch full profile
    try:
        profile = _fetch_full_profile(session, vanity_name)
    except Exception as e:
        return f"Failed to fetch profile for '{vanity_name}': {e}"

    # Save to profile.json
    os.makedirs(DB_DIR, exist_ok=True)
    with open(PROFILE_PATH, "w") as f:
        json.dump(profile, f, indent=2)

    lines = [
        f"# LinkedIn Profile Synced",
        f"**Name:** {profile['first_name']} {profile['last_name']}",
        f"**Headline:** {profile['headline']}",
        f"**Location:** {profile['location']}",
        f"**Industry:** {profile['industry']}",
        f"**Skills:** {len(profile['skills'])}",
        f"**Positions:** {len(profile['positions'])}",
        f"**Education:** {len(profile['education'])}",
        f"**Languages:** {len(profile['languages'])}",
        f"",
        f"Profile saved to `{PROFILE_PATH}`",
        f"Synced at: {profile['synced_at']}",
    ]
    return "\n".join(lines)


@mcp.tool()
def sync_profile_from_export(zip_path: str) -> str:
    """Import your LinkedIn profile from a LinkedIn data export ZIP file.

    To get your export: LinkedIn Settings > Data Privacy > Get a copy of your data.

    Args:
        zip_path: Path to the LinkedIn data export ZIP file
    """
    zip_path = os.path.expanduser(zip_path)
    if not os.path.exists(zip_path):
        return f"File not found: {zip_path}"

    profile = {
        "source": "linkedin_export",
        "synced_at": datetime.now().isoformat(),
        "first_name": "",
        "last_name": "",
        "headline": "",
        "summary": "",
        "industry": "",
        "location": "",
        "skills": [],
        "positions": [],
        "education": [],
        "certifications": [],
        "languages": [],
    }

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

            # Helper to find a CSV by basename (may be nested in folders)
            def find_csv(basename):
                for name in names:
                    if name.endswith(basename):
                        return name
                return None

            # Profile.csv
            profile_csv = find_csv("Profile.csv")
            if profile_csv:
                with zf.open(profile_csv) as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                    for row in reader:
                        profile["first_name"] = row.get("First Name", "")
                        profile["last_name"] = row.get("Last Name", "")
                        profile["headline"] = row.get("Headline", "")
                        profile["summary"] = row.get("Summary", "")
                        profile["industry"] = row.get("Industry", "")
                        profile["location"] = row.get("Geo Location", "")
                        break  # Only need first row

            # Skills.csv
            skills_csv = find_csv("Skills.csv")
            if skills_csv:
                with zf.open(skills_csv) as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                    for row in reader:
                        name = row.get("Name", "").strip()
                        if name:
                            profile["skills"].append(name)

            # Positions.csv
            positions_csv = find_csv("Positions.csv")
            if positions_csv:
                with zf.open(positions_csv) as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                    for row in reader:
                        profile["positions"].append({
                            "title": row.get("Title", ""),
                            "company": row.get("Company Name", ""),
                            "description": row.get("Description", ""),
                            "started_on": row.get("Started On", ""),
                            "finished_on": row.get("Finished On", ""),
                            "location": row.get("Location", ""),
                        })

            # Education.csv
            education_csv = find_csv("Education.csv")
            if education_csv:
                with zf.open(education_csv) as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                    for row in reader:
                        profile["education"].append({
                            "school": row.get("School Name", ""),
                            "degree": row.get("Degree Name", ""),
                            "field": row.get("Notes", ""),
                            "started_on": row.get("Start Date", ""),
                            "finished_on": row.get("End Date", ""),
                        })

            # Certifications.csv
            certs_csv = find_csv("Certifications.csv")
            if certs_csv:
                with zf.open(certs_csv) as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                    for row in reader:
                        profile["certifications"].append({
                            "name": row.get("Name", ""),
                            "authority": row.get("Authority", ""),
                            "started_on": row.get("Started On", ""),
                            "finished_on": row.get("Finished On", ""),
                        })

            # Languages.csv
            languages_csv = find_csv("Languages.csv")
            if languages_csv:
                with zf.open(languages_csv) as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                    for row in reader:
                        profile["languages"].append({
                            "name": row.get("Name", ""),
                            "proficiency": row.get("Proficiency", ""),
                        })

    except zipfile.BadZipFile:
        return f"Error: {zip_path} is not a valid ZIP file."
    except Exception as e:
        return f"Error reading export: {e}"

    os.makedirs(DB_DIR, exist_ok=True)
    with open(PROFILE_PATH, "w") as f:
        json.dump(profile, f, indent=2)

    full_name = f"{profile['first_name']} {profile['last_name']}".strip()
    summary_lines = [
        f"Profile synced for **{full_name}**",
        f"**Headline:** {profile['headline']}" if profile["headline"] else "",
        f"**Skills:** {len(profile['skills'])}",
        f"**Positions:** {len(profile['positions'])}",
        f"**Education:** {len(profile['education'])}",
        f"**Certifications:** {len(profile['certifications'])}",
        f"**Languages:** {len(profile['languages'])}",
        f"\nProfile saved to `{PROFILE_PATH}`",
    ]
    return "\n".join(line for line in summary_lines if line)


@mcp.tool()
def get_profile() -> str:
    """View your saved LinkedIn profile data used for job matching."""
    if not os.path.exists(PROFILE_PATH):
        return (
            "No profile saved yet.\n\n"
            "To sync your LinkedIn profile:\n"
            "1. Go to LinkedIn Settings > Data Privacy > Get a copy of your data\n"
            "2. Download your data export ZIP\n"
            "3. Use `sync_profile_from_export` with the path to the ZIP file"
        )

    with open(PROFILE_PATH) as f:
        profile = json.load(f)

    full_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
    lines = [f"# {full_name}"]

    if profile.get("headline"):
        lines.append(f"*{profile['headline']}*")
    if profile.get("location"):
        lines.append(f"**Location:** {profile['location']}")
    if profile.get("industry"):
        lines.append(f"**Industry:** {profile['industry']}")
    if profile.get("summary"):
        lines.append(f"\n## Summary\n{profile['summary']}")

    if profile.get("skills"):
        lines.append(f"\n## Skills ({len(profile['skills'])})")
        lines.append(", ".join(profile["skills"]))

    if profile.get("positions"):
        lines.append(f"\n## Experience ({len(profile['positions'])})")
        for pos in profile["positions"]:
            date_range = pos.get("started_on", "") or pos.get("start_date", "")
            finished = pos.get("finished_on", "") or pos.get("end_date", "")
            if finished:
                date_range += f" - {finished}"
            elif date_range:
                date_range += " - Present"
            lines.append(f"\n### {pos.get('title', 'Untitled')} at {pos.get('company', 'Unknown')}")
            if date_range:
                lines.append(f"*{date_range}*")
            if pos.get("location"):
                lines.append(f"**Location:** {pos['location']}")
            if pos.get("description"):
                lines.append(pos["description"])

    if profile.get("education"):
        lines.append(f"\n## Education ({len(profile['education'])})")
        for edu in profile["education"]:
            degree_str = edu.get("degree", "")
            field = edu.get("field", "") or edu.get("field_of_study", "")
            if field:
                degree_str += f" - {field}" if degree_str else field
            lines.append(f"\n### {edu.get('school', 'Unknown')}")
            if degree_str:
                lines.append(degree_str)
            date_range = edu.get("started_on", "") or edu.get("start_date", "")
            finished = edu.get("finished_on", "") or edu.get("end_date", "")
            if finished:
                date_range += f" - {finished}"
            if date_range:
                lines.append(f"*{date_range}*")

    if profile.get("certifications"):
        lines.append(f"\n## Certifications ({len(profile['certifications'])})")
        for cert in profile["certifications"]:
            lines.append(f"- **{cert.get('name', '')}**")
            if cert.get("authority"):
                lines.append(f"  Issued by {cert['authority']}")

    if profile.get("languages"):
        lines.append(f"\n## Languages ({len(profile['languages'])})")
        for lang in profile["languages"]:
            prof = f" ({lang['proficiency']})" if lang.get("proficiency") else ""
            lines.append(f"- {lang.get('name', '')}{prof}")

    synced = profile.get("synced_at", "")
    if synced:
        lines.append(f"\n---\n*Synced: {synced}*")

    return "\n".join(lines)


@mcp.tool()
def match_jobs(
    search_term: str = "",
    location: str = "",
    results_wanted: int = 20,
    hours_old: int = 72,
    is_remote: bool = False,
    job_type: str = "",
    min_salary: int = 0,
    sites: str = "linkedin,indeed,glassdoor,zip_recruiter,google",
    country: str = "USA",
    distance: int = 50,
) -> str:
    """Search for jobs and rank them by how well they match your full LinkedIn profile.

    Analyzes your skills, experience descriptions, tech stack, seniority level,
    and domain expertise to score each result. Runs multiple searches based on
    your profile to cast a wide net, then deduplicates and ranks.

    Args:
        search_term: Override search query (leave empty for smart auto-generation from profile)
        location: City, state, or region
        results_wanted: Number of results per search query (default 20)
        hours_old: Only show jobs posted within this many hours (default 72)
        is_remote: Filter for remote jobs only
        job_type: Filter by type: fulltime, parttime, internship, contract
        min_salary: Minimum annual salary filter (USD)
        sites: Comma-separated job boards: linkedin,indeed,glassdoor,zip_recruiter,google
        country: Country for Indeed search (default USA)
        distance: Distance in miles from location (default 50)
    """
    if not os.path.exists(PROFILE_PATH):
        return (
            "No profile found. Connect LinkedIn first:\n"
            "1. Run `linkedin_connect` to log in (one-time)\n"
            "2. Run `sync_profile` to import your profile"
        )

    with open(PROFILE_PATH) as f:
        profile = json.load(f)

    fp = _build_profile_fingerprint(profile)

    # Determine search queries
    if search_term:
        queries = [search_term]
    else:
        queries = _generate_search_queries(fp)

    site_list = [s.strip() for s in sites.split(",") if s.strip()]

    # Run searches for each query, splitting sites for proper remote handling
    native_remote = {"linkedin", "zip_recruiter"}
    text_remote = {"indeed", "google", "glassdoor"}
    all_jobs = []
    queries_used = []
    for query in queries:
        if is_remote:
            groups = []
            native = [s for s in site_list if s in native_remote]
            text = [s for s in site_list if s in text_remote]
            if native:
                groups.append((native, query))
            if text:
                rq = query + " remote" if "remote" not in query.lower() else query
                groups.append((text, rq))
        else:
            groups = [(site_list, query)]

        for sites_grp, search_query in groups:
            kwargs = {
                "site_name": sites_grp,
                "search_term": search_query,
                "results_wanted": results_wanted,
                "hours_old": hours_old,
                "country_indeed": country,
                "linkedin_fetch_description": True,
            }
            if location:
                kwargs["location"] = location
            if is_remote:
                kwargs["is_remote"] = True
            if job_type:
                kwargs["job_type"] = job_type
            if not is_remote and distance:
                kwargs["distance"] = distance

            try:
                result = scrape_jobs(**kwargs)
                if not result.empty:
                    all_jobs.append(result)
                    queries_used.append(f"{search_query} ({len(result)})")
            except Exception:
                continue

    if not all_jobs:
        return f"No jobs found. Tried queries: {', '.join(queries)}"

    # Combine and deduplicate by job URL
    jobs = pd.concat(all_jobs, ignore_index=True)
    if "job_url" in jobs.columns:
        jobs = jobs.drop_duplicates(subset=["job_url"], keep="first")

    # Filter by minimum salary
    if min_salary > 0 and "min_amount" in jobs.columns:
        jobs = jobs[(jobs["min_amount"].isna()) | (jobs["min_amount"] >= min_salary)]

    # Score every job
    scored_jobs = []
    for _, job in jobs.iterrows():
        desc = str(job.get("description", ""))
        title = str(job.get("title", ""))
        total, pct, breakdown = _score_job(desc, title, fp)
        scored_jobs.append((total, pct, breakdown, job))

    # Sort by score descending
    scored_jobs.sort(key=lambda x: x[0], reverse=True)

    # Format output
    full_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
    output_lines = [f"# Job Matches for {full_name}"]
    output_lines.append(
        f"*Profile: {len(fp['skills'])} skills, {len(fp['desc_techs'])} techs from experience, "
        f"{fp['years_exp']}y exp, seniority: {', '.join(fp['seniority']) or 'N/A'}*"
    )
    output_lines.append(f"*Queries: {' | '.join(queries_used)}*")
    output_lines.append(f"*{len(scored_jobs)} unique jobs scored*\n")

    for i, (total, pct, breakdown, job) in enumerate(scored_jobs[:30], 1):
        title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        loc = job.get("location", "N/A")
        site = job.get("site", "")
        url = job.get("job_url", "")
        posted = job.get("date_posted", "")
        min_amt = job.get("min_amount", "")
        max_amt = job.get("max_amount", "")

        salary_str = ""
        if min_amt and max_amt:
            salary_str = f"${min_amt:,.0f} - ${max_amt:,.0f}"
        elif min_amt:
            salary_str = f"${min_amt:,.0f}+"
        elif max_amt:
            salary_str = f"Up to ${max_amt:,.0f}"

        # Match bar visualization
        bar_filled = round(pct / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)

        output_lines.append(f"## {i}. {title}")
        output_lines.append(f"**Match: {pct}%** `{bar}`")

        # Show what matched
        match_details = []
        if breakdown.get("skills"):
            match_details.append(f"Skills: {', '.join(breakdown['skills'][:8])}")
        if breakdown.get("techs"):
            match_details.append(f"Tech: {', '.join(breakdown['techs'][:6])}")
        if breakdown.get("title_match"):
            match_details.append(f"Title: ~{breakdown['title_match']}")
        if breakdown.get("seniority"):
            match_details.append(f"Level: {breakdown['seniority']}")
        if breakdown.get("domains"):
            match_details.append(f"Domain: {', '.join(breakdown['domains'][:3])}")
        if match_details:
            output_lines.append(f"**Why:** {' · '.join(match_details)}")

        output_lines.append(f"**Company:** {company}")
        output_lines.append(f"**Location:** {loc}")
        if salary_str:
            output_lines.append(f"**Salary:** {salary_str}")
        output_lines.append(f"**Source:** {site}")
        if posted:
            output_lines.append(f"**Posted:** {posted}")
        if url:
            output_lines.append(f"**URL:** {url}")
        output_lines.append("")

    return "\n".join(output_lines)


if __name__ == "__main__":
    mcp.run()
