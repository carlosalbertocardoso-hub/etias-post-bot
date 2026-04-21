# WP Auto Publisher Agent

## Project Overview
Automated WordPress blog post agent for etiaseuropa.eu. Scrapes etias.com/articles/ daily, generates original English articles using Claude AI, and saves them as drafts in WordPress via REST API.

## Architecture
- scraper.py: Scrapes etias.com/articles/ for new articles, fetches full content
- agent.py: Uses Claude claude-opus-4-5 to generate original 400-600 word English posts
- publisher.py: Posts to WordPress via REST API using Application Password auth
- scheduler.py: Main entry point, runs daily job at configured time
- config.yaml: Topics, schedule, category mappings
- posted_articles.json: Tracks already-processed URLs to avoid duplicates

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
- Posts are saved as drafts (post_status: draft) for manual review before publishing
- Categories are auto-assigned based on content keywords
- 1 post per day maximum
- Source: https://etias.com/articles/
