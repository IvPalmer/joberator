"""
Profile fingerprinting, query generation, and job scoring engine.
No external dependencies — importable from both MCP server and dashboard.
"""

import re
from datetime import datetime


def build_profile_fingerprint(profile: dict) -> dict:
    """Extract a rich matching fingerprint from the full profile."""

    skills = [s.lower().strip() for s in profile.get("skills", []) if s.strip()]

    # Extract tech/tools from experience descriptions
    all_desc_text = " ".join(
        pos.get("description", "") for pos in profile.get("positions", [])
    ).lower()
    # Also include summary
    all_desc_text += " " + (profile.get("summary", "") or "").lower()

    # Common tech patterns to extract from descriptions
    tech_patterns = [
        r'\b(?:python|javascript|typescript|java|ruby|go|rust|c\+\+|c#|php|scala|kotlin|swift)\b',
        r'\b(?:react|angular|vue|node\.?js|express|django|flask|fastapi|spring|rails)\b',
        r'\b(?:aws|gcp|azure|docker|kubernetes|terraform|jenkins|circleci|github\s*actions)\b',
        r'\b(?:postgresql|mysql|mongodb|redis|elasticsearch|snowflake|bigquery|redshift)\b',
        r'\b(?:tableau|power\s*bi|metabase|looker|quicksight|d3\.?js|streamlit)\b',
        r'\b(?:airflow|dbt|spark|kafka|flink|etl|elt|data\s*pipeline)\b',
        r'\b(?:obiee|oracle|sql\s*server|informatica|qlik)\b',
        r'\b(?:html|css|sass|tailwind|figma|ux|ui)\b',
    ]
    desc_techs = set()
    for pattern in tech_patterns:
        for match in re.findall(pattern, all_desc_text):
            desc_techs.add(match.strip())

    # Unique job titles
    titles = list({
        pos.get("title", "").strip()
        for pos in profile.get("positions", [])
        if pos.get("title", "").strip()
    })

    # Current title (end_date is Present or empty)
    current_title = ""
    for pos in profile.get("positions", []):
        end = pos.get("end_date", "") or pos.get("finished_on", "")
        if end in ("Present", ""):
            current_title = pos.get("title", "").strip()
            if current_title:
                break

    # Headline parts
    headline_parts = []
    if profile.get("headline"):
        headline_parts = [
            p.strip() for p in re.split(r'[|/,]', profile["headline"])
            if p.strip() and len(p.strip()) > 3
        ]

    # Seniority level from titles
    seniority_keywords = []
    all_titles_lower = " ".join(titles).lower()
    for level in ["senior", "lead", "principal", "staff", "director", "manager", "head"]:
        if level in all_titles_lower:
            seniority_keywords.append(level)

    # Domain/industry keywords from descriptions
    domain_keywords = set()
    domain_patterns = [
        r'\b(?:healthcare|pharma|fintech|e-?commerce|saas|media|telecom|government)\b',
        r'\b(?:business\s*intelligence|data\s*analytics|data\s*engineering|data\s*viz)\b',
        r'\b(?:full\s*stack|front.?end|back.?end|devops|mlops|machine\s*learning)\b',
        r'\b(?:dashboard|reporting|visualization|analytics|etl|pipeline|warehouse)\b',
    ]
    for pattern in domain_patterns:
        for match in re.findall(pattern, all_desc_text):
            domain_keywords.add(match.strip())

    # Companies worked at (for industry signal)
    companies = [
        pos.get("company", "").strip()
        for pos in profile.get("positions", [])
        if pos.get("company", "").strip()
    ]

    # Years of experience (rough estimate from positions)
    years_exp = 0
    for pos in profile.get("positions", []):
        start = pos.get("start_date", "") or pos.get("started_on", "")
        end = pos.get("end_date", "") or pos.get("finished_on", "")
        try:
            start_year = int(str(start)[:4])
            end_year = int(str(end)[:4]) if end and end != "Present" else datetime.now().year
            years_exp += max(0, end_year - start_year)
        except (ValueError, IndexError):
            pass

    return {
        "skills": skills,
        "desc_techs": list(desc_techs),
        "titles": titles,
        "current_title": current_title,
        "headline_parts": headline_parts,
        "seniority": seniority_keywords,
        "domains": list(domain_keywords),
        "companies": companies,
        "years_exp": years_exp,
        "languages": [l.get("name", "").lower() for l in profile.get("languages", [])],
        "_positions": profile.get("positions", []),  # raw positions for query generation
    }


def generate_search_queries(fp: dict) -> list:
    """Generate diverse search queries from profile fingerprint.

    Prioritizes current role and recent titles. Skips intern/junior/old
    titles that would waste a search slot for senior candidates.
    """
    queries = []
    skip_keywords = {"intern", "student", "trainee", "apprentice", "junior", "assistant"}

    def _is_relevant_title(title: str) -> bool:
        """Skip titles that are too junior for a senior candidate."""
        words = set(title.lower().split())
        if fp["seniority"] and words & skip_keywords:
            return False
        return True

    # Current/most recent title (highest priority)
    if fp["current_title"]:
        queries.append(fp["current_title"])

    # Headline parts that differ from current title
    for part in fp["headline_parts"]:
        if part.lower() != (fp["current_title"] or "").lower() and _is_relevant_title(part):
            queries.append(part)

    # Recent titles only — skip roles older than 7 years and irrelevant ones
    seen_lower = {q.lower() for q in queries}
    current_year = datetime.now().year
    for pos in fp.get("_positions", []):
        title = (pos.get("title") or "").strip()
        if not title or title.lower() in seen_lower:
            continue
        # Check recency
        end = pos.get("end_date", "") or pos.get("finished_on", "") or "Present"
        try:
            end_year = current_year if end == "Present" else int(str(end)[:4])
        except (ValueError, IndexError):
            end_year = current_year
        if current_year - end_year > 7:
            continue
        if not _is_relevant_title(title):
            continue
        queries.append(title)
        seen_lower.add(title.lower())

    # Tech-stack combo (top 3 desc_techs that are most distinctive)
    top_techs = [t for t in fp["desc_techs"] if t not in ("ui", "ux", "css", "html")][:3]
    if top_techs and len(queries) < 5:
        queries.append(" ".join(top_techs))

    # Cap at 5 queries to avoid excessive API calls
    return queries[:5]


def score_job(job_text: str, job_title: str, fp: dict) -> tuple:
    """Score a job against the profile fingerprint. Returns (score, pct, breakdown)."""
    text = job_text.lower()
    title = job_title.lower()
    breakdown = {}

    # --- Skills match (0-20 pts) ---
    matched_skills = [s for s in fp["skills"] if s in text or s in title]
    skill_score = min(len(matched_skills) * 2, 20)
    breakdown["skills"] = matched_skills

    # --- Tech from descriptions match (0-15 pts) ---
    matched_techs = [t for t in fp["desc_techs"] if t in text]
    tech_score = min(len(matched_techs) * 2, 15)
    breakdown["techs"] = matched_techs

    # --- Title/role match (0-15 pts) ---
    title_score = 0
    matched_title = ""
    for past_title in fp["titles"]:
        past_words = [w.lower() for w in past_title.split() if len(w) > 2]
        if not past_words:
            continue
        overlap = sum(1 for w in past_words if w in title)
        ratio = overlap / len(past_words)
        pts = round(ratio * 15)
        if pts > title_score:
            title_score = pts
            matched_title = past_title
    if matched_title:
        breakdown["title_match"] = matched_title

    # --- Seniority match (0-10 pts) ---
    seniority_score = 0
    for level in fp["seniority"]:
        if level in title or level in text[:500]:
            seniority_score = 10
            breakdown["seniority"] = level
            break

    # --- Domain overlap (0-10 pts) ---
    matched_domains = [d for d in fp["domains"] if d in text]
    domain_score = min(len(matched_domains) * 3, 10)
    if matched_domains:
        breakdown["domains"] = matched_domains

    # --- Experience level alignment (0-10 pts) ---
    exp_score = 0
    years_mentioned = re.findall(r'(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)', text)
    if years_mentioned:
        required_years = max(int(y) for y in years_mentioned)
        if fp["years_exp"] >= required_years:
            exp_score = 10
        elif fp["years_exp"] >= required_years - 2:
            exp_score = 5
        breakdown["years_required"] = required_years
        breakdown["years_have"] = fp["years_exp"]

    # --- Bonus: description depth (0-5 pts) ---
    all_profile_terms = set(fp["skills"] + fp["desc_techs"] + [d for d in fp["domains"]])
    unique_hits = sum(1 for t in all_profile_terms if t in text)
    depth_score = min(unique_hits, 5)

    total = skill_score + tech_score + title_score + seniority_score + domain_score + exp_score + depth_score
    max_possible = 85
    pct = round(total / max_possible * 100)
    breakdown["pct"] = pct

    return total, pct, breakdown
