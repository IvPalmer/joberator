# Joberator: Job Search

Search for jobs matching the user's criteria using the `joberator-jobs` MCP server.

## How to use

The user will ask to search for jobs. Use the `search_jobs` MCP tool to find matching positions.

### Examples

**Basic search:**
- "Find me remote Python developer jobs"
- "Search for data engineer positions in San Francisco"
- "Look for fullstack developer jobs paying over $150k"

### Process

1. Parse the user's request to extract: search terms, location, salary, remote preference, job type
2. Call the `search_jobs` tool with appropriate parameters
3. Present results in a clean, scannable format
4. Highlight the best matches and why they fit
5. Ask if the user wants to refine the search or see more details on specific jobs

### Tips

- Default to `is_remote: true` if the user mentions remote work
- Use `hours_old: 24` for "recent" or "new" jobs, `72` for default, `168` for "this week"
- If salary is mentioned, set `min_salary` accordingly
- For broader results, search all sites. For faster results, use just `linkedin,indeed`
- LinkedIn rate-limits after ~10 pages — keep `results_wanted` at 20-30 for best reliability
