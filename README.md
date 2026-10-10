# forge-followers

Live follower counts for Jayden Aj, powering the counter on the Forge-co
talent page (`https://forge-co.ca/talent/`).

- `followers.json` — `{"tiktok": N, "instagram": N, "updated_at": ISO-8601, ...}`
- Updated every 15 minutes by `poll.py` (cron on the Forge automation host).
- History is intentionally a single commit: each poll force-pushes a fresh
  root commit so the file stays tiny and the log stays clean.
- The talent page fetches
  `https://raw.githubusercontent.com/vigorous187/forge-followers/main/followers.json`
  with a 15-minute cache-buster and falls back to baked-in values if the
  fetch fails.

Sources: TikTok public profile page (anonymous scrape), Instagram via the
linked business account API.
