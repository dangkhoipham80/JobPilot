# 🤖 JobPilot — CV autopilot, on your own machine

**English** · [Tiếng Việt](README.vi.md)

> Crawl developer jobs → review them on a local dashboard → tailor your CV to one → approve the diff → apply → track what comes back.
> Built on the [Awesome-CV](https://github.com/posquit0/Awesome-CV) LaTeX template, which is also usable on its own.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)](https://www.python.org/)
[![Postgres](https://img.shields.io/badge/PostgreSQL-17-blue?logo=postgresql)](https://www.postgresql.org/)
[![Tectonic](https://img.shields.io/badge/Tectonic-LaTeX%20build-blue?logo=latex)](https://tectonic-typesetting.github.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

This repo has two layers:

1. **CV template** — the Awesome-CV LaTeX scaffolding (`awesome-cv.cls`, `fontawesome.sty`, `fonts/`),
   built with tectonic. Useful by itself; see [Just the CV builder](#-just-the-cv-builder).
2. **JobPilot** — a FastAPI + React + PostgreSQL pipeline that crawls jobs, tailors your CV per job
   with an LLM, dispatches applications and tracks what came back. Architecture in
   [`PLAN.md`](PLAN.md), CV-tailoring rules in [`SKILL.md`](SKILL.md), contributor guide in
   [`CONTRIBUTING.md`](CONTRIBUTING.md).

> **No CV lives in this repo.** Your name, email, history and every tailored version live in the
> `cv_versions` table of your local Postgres. A fresh database seeds an *empty* CV that you fill in
> through the CV Studio. `jobpilot/cv/sample.py` is fictional data used only by tests.

---

## 🧭 What it does

```
crawl sources ──▶ Jobs dashboard ──▶ you shortlist ──▶ a model tailors the CV
                                                              │
                           you approve / edit the diff ◀───────┘
                                      │
                     email (full-auto, 3 safety gates) │ portal & external (you press submit)
                                      │
                                      ▼
              replied · interview · offer · rejected ◀── your inbox suggests, you confirm
```

Three rules the code is built around:

- **No invented experience.** The tailor agent may only reorder, drop or rephrase things already in
  your CV — the plan schema is index-based, so "add a skill you don't have" is not expressible.
- **You approve anything that leaves the machine**, except the email channel once you explicitly
  enable it (and it stays dry-run until you turn that off too).
- **robots.txt and rate limits are respected.** A source that disallows automated access is not
  crawled — see [Sources](#-sources).

### The dashboard

Eleven pages, at `localhost:5173` in development (or at `:8000`, served by the API, once `web/` is built):

| Page | What it's for |
|---|---|
| **Deck** | The funnel and the day's numbers |
| **Jobs** | Everything crawled, filterable; shortlist or skip from the row |
| **CV Studio** | Structured editor for the Master CV, version history, diff any two versions; import an existing CV from an image, a PDF or pasted text as a draft you review before saving; paste a job description to save it as a job and tailor to it in one step |
| **Applications** | Board of what was dispatched, per stage; follow-up reminders and inbox suggestions |
| **Companies** | Employers and their HR contacts; an HR email can become a job's apply target |
| **Runs** | Start a crawl, watch the queue, read the run history |
| **Market** | What the crawled corpus looks like — skills, pay, cities, seniority |
| **Models** | Pick a provider and model per task; cost, latency and first-try rate per backend |
| **Backup** | Database backups: what exists, run one now, and the restore command |
| **Settings** | Sources, crawl scope, apply gates — written to a gitignored overlay |
| **Guide** | How the pipeline fits together |

Lists are paginated server-side with a page size you pick per list (10/25/50/100), remembered
between visits.

---

## 🚀 Quick start

```bash
# 1. install (extras are opt-in; `all` gets everything)
pip install -e '.[all]'
playwright install chromium          # only needed for ITviec / TopCV / VietnamWorks

# 2. point at a database and set a local API token
cp .env.example .env                 # DATABASE_URL + JOBPILOT_API_TOKEN, plus a key for
                                     # whichever provider you pick (see Models)
psql -U postgres -c "CREATE DATABASE jobpilot;"
alembic upgrade head

# 3. run it
uvicorn jobpilot.api.main:app --reload    # API + WebSocket on :8000
cd web && npm install && npm run dev      # dashboard on :5173
```

Replace the `changeme` token before step 3: the backend refuses to start on a placeholder or on
anything shorter than 20 characters. Put the same value in `web/.env.local` as `VITE_API_TOKEN`
(see `web/.env.example`), or the dashboard is answered with 401.

`make dev` brings up Postgres and the API; the dashboard needs its own terminal (`make web`), since
`uvicorn --reload` blocks and a Makefile runs its prerequisites in sequence.

Everything binds to `localhost` and is guarded by a token from `.env` — this is a single-user local
tool, not a service to expose.

### Day-to-day CLI

```bash
python -m jobpilot.cli crawl                          # crawl every enabled source
python -m jobpilot.cli crawl --query "java spring" --limit 30
python -m jobpilot.cli run --every 60                 # simple loop for cron
python -m jobpilot.cli backfill --force               # re-derive facets after fixing a parser
python -m jobpilot.cli cv seed                        # empty Master CV, if there isn't one
python -m jobpilot.cli cv read scan.png -o my-cv.local.json   # AI reads an image/PDF into a draft (saves nothing)
python -m jobpilot.cli cv read --text cv.txt -o my-cv.local.json   # the same, from a text file
python -m jobpilot.cli cv import my-cv.local.json     # load a CV into the DB
python -m jobpilot.cli cv export my-cv.local.json     # back it up (gitignored)
python -m jobpilot.cli cv build                       # render JSON → .tex → PDF
python -m jobpilot.cli tailor <job_id>                # needs a key for the configured provider
python -m jobpilot.cli apply <job_id>
python -m jobpilot.cli confirm-submit <job_id>        # you submitted a portal/external one by hand
python -m jobpilot.cli llm providers                  # what runs what, which keys are missing
python -m jobpilot.cli llm stats                      # cost, first-try rate, latency per backend
python -m jobpilot.cli llm bench --task classify      # score a backend on known answers
pytest jobpilot/tests
```

Keep the query short. It becomes a search term at each site, and an over-specific one
("Java Spring Boot Backend") can legitimately match nothing.

---

## 🧠 Models

Nothing is hard-wired to one vendor. Provider and model are chosen **per task** —
`tailor`, `letter`, `classify`, `intake` — in `jobpilot/config.yaml` or from the **Models** page, which writes
to the gitignored overlay:

```yaml
llm:
  provider: claude          # default for anything not set below
  tailor: ""                # "" = use `provider`
  letter: ""
  classify: ""              # e.g. openai — the cheap, easy call
  intake: ""                # reading a pasted JD and scoring it against the CV
  models:
    claude: claude-opus-4-8
    openai: gpt-4.1
    gemini: gemini-3.5-flash
```

Adding a backend is one entry in `llm/registry.PROVIDERS` plus a client module — not a `Literal`
edited in four places. The API providers do not accept the same JSON Schema, so `llm/schema.py`
adapts it (Gemini's subset, OpenAI's strict mode).

A fourth provider, `claude_cli`, runs the same Claude models through the local `claude` CLI, counted
against your Claude subscription instead of billed per token. It is for personal use on your own
machine.

**Measure, don't guess.** Every call — including ones the anti-fabrication guard rejects, and ones
that error — writes a row to `llm_calls`. Read it with `jobpilot llm stats` or the Models page:
cost, latency, and how often a plan cleared the guard first try. `jobpilot llm bench` re-runs a
fixed scoring set so "cheapest that still works" is a result rather than a hunch. Small samples show
`n=<count>` instead of a percentage — at n=5 this benchmark once ranked a model fastest that turned
out to be slowest at n=10.

Two honest limits:

- **Only one privacy warning matters: Gemini's free tier.** Paid Anthropic, OpenAI and Gemini do not
  train on API input. Unpaid Gemini does, and its terms say not to send personal information — which
  is exactly what `tailor` and `letter` send, since the whole Master CV goes in the system prompt.
  Set `llm.gemini_paid_tier: false` and JobPilot warns before every such call. It warns; it does not
  block.
- **"Credit remaining" is a budget counter, not an account balance.** Anthropic, OpenAI and Google
  all require an admin key for their cost endpoints, so the figure is your own `llm.budget_usd` minus
  what JobPilot measured. Models with no entry in `llm/pricing.py` count as unpriced rather than
  free, and every total says how many.

---

## 🔎 Sources

Configured in `jobpilot/config.yaml`, toggled on the Settings page. Adding one is a scraper plus a
line of config (`PLAN.md` §5.1.1).

| Source | Tier | How it's read | Notes |
|---|---|---|---|
| **ITviec** | 1 | Playwright | Cloudflare-protected; salaries are behind a login, so `salary` is `null` |
| **TopCV** | 1 | Playwright | Server-rendered + schema.org `JobPosting`. Keyword goes in the *path*, not `?keyword=` |
| **VietnamWorks** | 1 | Playwright | Jobs arrive by XHR; lazy-loads ~9–20 cards per page, so it is paged |
| **LinkedIn** | 1 | IMAP | Reads **Job Alert emails in your own inbox**. LinkedIn is never crawled |
| **We Work Remotely** | 2 | RSS | One feed per category, full JD inline, no browser needed |
| **Arbeitnow** | 2 | JSON API | Really paginated; mostly Germany/EU, descriptions often in German |
| **Greenhouse** | 3 | Board JSON API | Any company on Greenhouse. Off by default — list the boards you follow |
| **Lever** | 3 | Board JSON API | Any company on Lever. Off by default |
| TopDev, Ashby | — | — | Deliberately absent — see below |

Tier-2 sources are remote/worldwide roles. Turn them off in Settings if you only want Vietnam.

**Tier 3 — company career pages.** Most companies don't build a job board, they rent one, and a role
usually appears there before it reaches any aggregator. One adapter reaches every company on a
platform, so following a new company is one word in `config.yaml` — no code:

```yaml
ats:
  greenhouse: [gitlab, grafanalabs, elastic]   # the slug in job-boards.greenhouse.io/<slug>
  lever:      [palantir, spotify]              # the slug in jobs.lever.co/<slug>
  locations:  ["Ho Chi Minh"]                  # optional — keep only postings in these places
```

Then enable `greenhouse` / `lever` in Settings. Each board is one request per crawl, so a long list
is a slow crawl. A company board is worldwide, so set `locations` unless you want every office: it
is matched as whole words against the posting's own location label, accents ignored, and it knows
the common spellings of Vietnamese cities ("HCMC", "Saigon", "Ha Noi"). "Vietnam" also matches a
label that is only a Vietnamese city; for any other country the term has to be something the board
writes, and many label a posting with its city alone. Once `locations` is set, jobs from
these boards are kept even when the description names none of your `crawl.stacks` (you picked the
employer and the place) and show a match of 0% in that case; the title exclusions still apply.
With no `locations` the stack filter stays on, because a query matches any word of a title and a
whole worldwide board has a great many "engineers".

**Sources deliberately not added.** Several were evaluated and rejected — read
[`jobpilot/crawler/CLAUDE.md`](jobpilot/crawler/CLAUDE.md) → *"Nguồn tier-2 đã loại"* (in Vietnamese)
before adding one, so the checks aren't repeated:

- **Remotive**, **Jobicy** — `robots.txt` disallows `/api/`, which is the only useful endpoint.
- **RemoteOK**, **TopDev** — `Content-Signal: ai-train=no, use=reference` plus a `ClaudeBot` block.
  Not obviously fatal, but it needs a deliberate decision rather than a default.
- **Ashby** — `api.ashbyhq.com` serves no `robots.txt` at all (401) while `jobs.ashbyhq.com`
  disallows `/api/`. Absent robots is not permission.
- **Himalayas** — robots is fine, but the API ignores every filter parameter and silently caps
  `limit` at 20, so a crawl would "succeed" and hand back jobs for other professions.

An API that returns 200 while ignoring your filter is more dangerous than one that returns an
error. If the response echoes something like `appliedFilters`, check it.

> Read the **whole** `robots.txt` before writing a scraper. Jobicy's `Disallow: /api/` is on line 48;
> a `head -40` made it look permissive, and only a live run against `RobotsPolicy` caught it.

---

## 📬 After you apply

Applying is the middle of the story, not the end.

- **Follow-ups.** Applications that have gone quiet surface on the board with a suggested nudge.
  Nothing is sent — a follow-up is a message to a person deciding about you, and the same rule that
  gates apply gates this.
- **Outcomes.** Record `replied`, `interview`, `offer`, `rejected`, `withdrawn` or `ghosted` per
  application, with history. The last two are yours to declare — no counter decides you were
  ghosted. Rates are computed from what an application *ever reached*, not from where it sits now,
  or interview rate would fall when interviews turn into offers.
- **Inbox sync** (off by default). With IMAP credentials set, JobPilot reads *your* mailbox, matches
  messages to applications locally, and only then asks a model what a matched reply means. Mail that
  belongs to no application never leaves the machine. Every suggestion quotes the line it read, and
  nothing is recorded until you press the button.

Enable it under `apply.inbox` with `IMAP_USER` / `IMAP_PASSWORD` — for Gmail that must be an
[App Password](https://myaccount.google.com/apppasswords), not your account password.

---

## 📄 Just the CV builder

The LaTeX scaffolding works standalone — put a `cv.tex` next to `awesome-cv.cls` and run:

```bash
# tectonic — one static binary, no daemon (https://tectonic-typesetting.github.io)
tectonic -X compile cv.tex
```

Output is `cv.pdf` in the same directory. JobPilot runs the same engine, writing tailored builds to
`out/cv/<scope>/` and never touching your master.

Tectonic is the only engine: ~10 MB, nothing running, binaries for x86-64 and ARM64. (The
`csmith/awesome-cv-builder` Docker image, 3.18 GB behind a daemon, used to be a fallback and was
removed; a config still saying `cv.engine: docker` gets a build error that says so.)

Tectonic is looked for on `PATH` first, then in **`tools/`** inside the repo — so on a machine where
you would rather not touch `PATH`, dropping the downloaded binary in `tools/` is enough and needs no
configuration. (`cv.tectonic_bin` still works, but an absolute path there is true of one machine
only.)

Prefer editing through the **CV Studio** rather than by hand: content is structured JSON that is
serialized to `.tex` via Jinja2, so hand-edited `.tex` loses the round trip. Change the accent colour
with `theme.color` in the Studio, not in the `.cls`.

**Troubleshooting.** Tectonic downloads the TeX packages the document asks for on its first run and
caches them (~50 MB) per user, so build #1 needs network and is slow; later builds are offline.
Install the `[cv]` extra for `pypdf`, or the page count reads as unknown.

---

## 🗺️ Project layout

```
jobpilot/
  api/        FastAPI: REST + WebSocket, one route module per surface · paging.py
  crawler/    base.py (contract + paging loop) · one module per source · feed.py for RSS/JSON
  cv/         CvDocument schema · Jinja2 → .tex · LaTeX compile · version store · ats.py
  tailor/     index-based plan schema · anti-fabrication guard · model engine · diff
  apply/      cover letter · email (3 gates) · portal hand-off · dispatcher
              followup.py (reminders) · outcome.py (what happened) · inbox.py (read replies)
  intake/     read a pasted (or screenshotted) job description · score its fit against the CV
  companies/  employers and their HR contacts · folding employer names
  llm/        provider registry · per-task engines · schema adapters · cost & quality telemetry
  analytics/  market facets, each carrying how much of the corpus it actually saw
  store/      SQLAlchemy models + Alembic migrations
  slack/      optional secondary channel; a pure client of the REST API
  orchestrator.py   task queue behind the 202-and-a-task-id endpoints
  backup.py         database + CV backups, behind the CLI, the timer and the Backup page
web/          React + Vite + TS + Tailwind dashboard
```

## 🤝 Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, the checks CI runs and the rules a change has
to keep. The conventions themselves live in [`CLAUDE.md`](CLAUDE.md) and in a `CLAUDE.md` per code
area — written in Vietnamese — along with the bugs that only appeared against live sites.

## 📝 License

MIT — see [LICENSE](LICENSE) — for JobPilot's own code. Third-party material keeps its own terms:

- `awesome-cv.cls` and `fontawesome.sty` come from Awesome-CV (LPPL v1.3c); both are modified
  here.
- The templates in `jobpilot/cv/templates/awesome_cv/` derive from Awesome-CV's example
  templates (CC BY-SA 4.0).
- The fonts in `fonts/` are Apache 2.0 (Roboto) and SIL OFL 1.1 (Font Awesome); the licence
  texts sit next to them.
- The job-board logos in `web/public/logos/` are trademarks of their owners.

## ⭐ Acknowledgments

- [Awesome-CV](https://github.com/posquit0/Awesome-CV) by Claud D. Park
- [Tectonic](https://tectonic-typesetting.github.io/) — the LaTeX engine
- Job data from [We Work Remotely](https://weworkremotely.com/) and
  [Arbeitnow](https://www.arbeitnow.com/) via their public feeds
