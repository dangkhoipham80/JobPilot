# `deploy/` — running JobPilot on the server

Full walkthrough in `../DEPLOY.md`. This file is the map.

| File | What it is |
|---|---|
| `jobpilot-api.service` | the API + dashboard, always on |
| `jobpilot-backup.service` / `.timer` | nightly `pg_dump` + CV export |
| `backup.sh` | what the timer runs |
| `update.sh` | pull, migrate, rebuild the bundle, restart, health-check |

## Why there is no crawl timer here

Crawling runs on the **laptop**, not on the server, writing to the server's
Postgres over Tailscale (`DEPLOY.md §6`).

Not an optimisation — it is the reason this deployment is free. ITviec, TopCV
and VietnamWorks sit behind Cloudflare, which challenges datacenter IPs far more
readily than residential ones, and the free server is in Singapore rather than
Vietnam. Crawling from the laptop uses a Vietnamese residential IP, which is the
best address this system will ever have for the job.

It also keeps the server small: no Chromium, no Playwright, no browser
dependencies — which is what lets everything fit in the free tier.

What the laptop being asleep costs: a crawl window. That is a batch job that
runs twice a day and catches up on the next run, not the dashboard — which is
what you actually wanted reachable from your phone, and which stays up.
