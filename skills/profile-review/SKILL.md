# Joberator: LinkedIn Profile Review

Review the user's LinkedIn profile against a field-tested rubric and produce concrete, prioritized fixes.

## When to use

The user asks to review, audit, or improve their LinkedIn profile (or asks "why am I not getting recruiter messages?").

## Getting the profile

Ask for ONE of these, in order of preference:

1. **PDF export** - on LinkedIn: your profile → "More"/"Mais" → "Save to PDF"/"Salvar como PDF". Best structured source.
2. **Pasted text** - the user copies their profile sections into the chat.
3. **Synced profile** - if joberator is installed locally and the profile was synced, read `~/.joberator/profile.json`.

Do not start the review without profile content. Do not invent facts about the user.

Respond in the user's language (match the language they write in, or the profile's language).

## Rubric

Evaluate each section, in this order:

1. **Headline** - A searchable formula, not a job title: role + core tools/skills + differentiator + location or remote signal. Example shape: "Senior Data Engineer | Python, SQL, AWS | AI Pipelines | Remote LATAM". Recruiters search keywords; the headline is the highest-weight field.
2. **About** - First 2 lines must hook (the rest is hidden behind "see more"). Concrete scope and outcomes with numbers. No buzzword soup ("passionate", "results-driven"). End with what the user is looking for. Every claim must be backed elsewhere in the profile (don't claim fluency the Languages section contradicts).
3. **Experience** - Titles should match what recruiters type into title filters (filters only match the position-title field). Suggest aligned, defensible titles; adding scope in parentheses is fine, e.g. "Analyst (Data Engineering)". Warn against retitles a background check would contradict, especially on older roles. Employment type (full-time vs contract) must be accurate. Each role needs 2-4 bullets with real numbers; flag bullets without one and ask for the number rather than inventing it. Strip internal/confidential system or people names; keep the metrics.
4. **Skills** - Only pin/feature skills the user could defend in a live interview. Lead with disciplines ("Data Engineering") over tools. The top 3 pinned matter most. 15-25 relevant skills beat 50 noisy ones. Flag stuffing.
5. **Projects & Featured** - Recent, real, defensible. Link public repos or demos. Remove junior-era artifacts that undercut seniority. No self-deprecating copy. Dates accurate.
6. **Open to Work** - If the user is searching: is it enabled (recruiter-only mode exists)? All title slots filled with titles that exist in LinkedIn's own taxonomy (the typeahead must match)? Employment types, locations + remote, and start date set?
7. **Consistency** - Headline, titles, and dates should match the user's resume, personal site, and GitHub. Flag mismatches to fix everywhere at once.
8. **Bilingual profiles** (when relevant) - LinkedIn supports per-language profile versions: headline, About, and experience descriptions are per-language; skills, education, languages, and featured are shared. For non-English markets with international ambitions, recommend an English primary + local-language secondary, and review both.

## Output format

1. **Scorecard** - one line per rubric section: solid / needs work / missing, with a one-clause reason.
2. **Top 5 fixes** - ordered by impact, each with a concrete before → after rewrite the user can paste.
3. **Headline & About rewrites** - 2 headline options and 1 full About proposal.
4. **Questions for the user** - missing metrics, target roles, target market. Ask, don't invent.

Be direct, don't flatter. If a section is fine, say so in one line and move on.
