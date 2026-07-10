# WP Auto Publisher Agent

## Project Overview
Automated WordPress blog post agent for etiaseuropa.eu. Scrapes etias.com/articles/ daily, generates original English articles using Claude AI, and publishes them to WordPress via REST API.

## Architecture
- scraper.py: Scrapes etias.com/articles/ for new articles, fetches full content
- agent.py: Uses Claude claude-haiku-4-5 to generate original 1,200-1,500 word English posts
- publisher.py: Posts to WordPress via REST API using Application Password auth
- scheduler.py: Main entry point, runs daily job at configured time
- config.yaml: Topics, schedule, category mappings
- posted_articles.json: tracks two independent lists — `urls` (every candidate visited, incl. skipped) and `titles` (only published post titles, for topic-dedup). Not index-paired, do not zip().
- last_run.json: heartbeat written every run (outcome + timestamp) so the daily workflow always has something to commit, even on a no-op day — protects against GitHub's 60-day auto-disable of scheduled workflows on zero repo activity.

## Commands
- Install: pip install -r requirements.txt
- Run: python scheduler.py
- Test single run: python -c "from scheduler import run_daily_job; run_daily_job()"

## Environment Variables (.env)
- WP_URL: WordPress site URL
- WP_USER: WordPress username
- WP_APP_PASSWORD: WordPress Application Password (generated in wp-admin/profile.php)
- ANTHROPIC_API_KEY: Anthropic API key

## WordPress Setup
Generate Application Password at: wp-admin/profile.php → "Contraseñas de aplicación"

## Notes
- Posts are published directly (post_status: publish), zero human review before going live
- Categories are auto-assigned based on content keywords
- 1 post per day maximum
- Source: https://etias.com/articles/
- Author byline is intentionally "the ETIASEuropa Editorial Team", not a named individual — see agent.py's AUTHOR_NAME comment. Do not attribute invented professional credentials to a real person's name in AI-generated, unreviewed content.
- `functions/` (Firebase Cloud Functions variant) is NOT the production path and has drifted significantly behind root (missing `_sanitize_internal_links`, old buggy substring category matching, fixed non-varied byline). Do not deploy it without first porting the fixes from root, or delete it if truly unused.
