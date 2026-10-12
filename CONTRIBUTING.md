# Contributing to JobPilot

**English** · [Tiếng Việt](CONTRIBUTING.vi.md)

Thanks for looking. JobPilot is a single-user tool that runs on your own machine, so the most
useful contributions are the ones you needed yourself: a parser that reads a site correctly, a new
source that allows crawling, a CV template, a bug that only shows up against live data.

## Rules a change has to keep

These are not style preferences. A pull request that breaks one will not be merged.

1. **No invented experience.** Tailoring may reorder, drop or rephrase what is already in the CV. It
   never adds a skill, a job or a number. The guard is in `jobpilot/tailor/`; the rules are in
   [`SKILL.md`](SKILL.md) §0.
2. **A person approves anything that leaves the machine.** The only exception is the email channel
   after the user has switched it on. LinkedIn is never auto-applied to and never scraped.
3. **No personal data in the repo.** This repository is public. Do not commit a real CV, a real
   recruiter's address, or a real inbox message — not in code, tests, docs, commit messages or pull
   requests. Tests use the fictional CV in `jobpilot/cv/sample.py`. If you export your own CV, keep
   the `.local.json` suffix (`my-cv.local.json`); that suffix is what `.gitignore` matches.
4. **The Master CV is never overwritten.** Tailored builds go to `out/cv/<scope>/`.
5. **robots.txt, terms of service and rate limits are respected.** Read the whole `robots.txt`
   before writing a scraper. A source that fails is logged and skipped, not retried forever.
6. **Secrets stay in `.env`.** Never log or commit a token, and never commit a database file.

## Setup

You need Python 3.11+, Node 20, PostgreSQL and
[tectonic](https://tectonic-typesetting.github.io/) (to build PDFs).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[all,dev]'
playwright install chromium          # only for the ITviec / VietnamWorks scrapers

cp .env.example .env                 # set DATABASE_URL and JOBPILOT_API_TOKEN
python -c "from jobpilot.api.security import generate_token; print(generate_token())"
psql -U postgres -c "CREATE DATABASE jobpilot;"
alembic upgrade head

make api                             # backend on :8000
make web                             # dashboard on :5173, in a second terminal
```

The backend refuses to start on a placeholder token or one shorter than 20 characters. The same
value goes in `web/.env.local` as `VITE_API_TOKEN` (see `web/.env.example`).

A new database starts with an empty CV. Fill it in through the CV Studio; you do not need a real one
to work on most of the code.

## Before you open a pull request

Run what CI runs:

```bash
ruff check jobpilot                                   # ruff is pinned in the dev extra
pytest jobpilot/tests -q
cd web && npx tsc --noEmit && npm run build
```

- The tests run on a SQLite fixture, so they need no Postgres. CI sets `JOBPILOT_API_TOKEN` to a
  20+ character value for the run; do the same if you have no `.env`.
- CI does not run `black --check`, and `make lint` does. The tree has never been reformatted, so
  `make lint` fails on files you did not touch. Use `ruff check jobpilot`.
- Migrations are not covered by the test suite. If you change the schema, run
  `alembic upgrade head` against a real Postgres.

Green tests are not enough for code that touches the outside world. This project has repeatedly had
parsers that passed their tests and were wrong on the live site.

- Changed a scraper, the tailor or the apply flow? Run that flow for real and read the output.
- Changed a Jinja template, `jobpilot/cv/latex.py`, `awesome-cv.cls` or `fontawesome.sty`? Build a
  PDF again.
- Say in the pull request what you ran and what you saw.

## Workflow

- Branch from `main`: `feat/…`, `fix/…`, `docs/…`, `chore/…`.
- `main` is protected. Changes arrive by pull request, the `backend` and `frontend` checks must
  pass, and force pushes are blocked.
- Fork the repo and open a pull request from your fork. Only the maintainer can merge, so every
  outside change is reviewed and approved by them first. CI on a pull request from a fork also
  waits for the maintainer to approve the run.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/), for example
  `fix(crawl): measure the dedup window from first sight`.
- **Everything on GitHub is in English**: commit messages, pull request titles and descriptions,
  issues. Design docs in the repo may be in Vietnamese.
- Keep a pull request to one change. Describe what it does, why, how you verified it, and what you
  are unsure about.

## Conventions

- **Python**: 3.11+, type hints, code and comments in English.
- **Database**: Postgres is the single source of truth. A schema change needs an Alembic migration;
  do not edit the schema by hand.
- **State**: every state change goes through the REST API. The web dashboard and Slack are both
  clients of it.
- **Scrapers** subclass `crawler/base.py:BaseScraper` and normalise to the shared `Job` schema, with
  `id = "<source>:<native_id>"`.
- **CV text** never contains raw LaTeX. It uses a small markdown subset — `**bold**`, `` `tech` ``,
  `~tech~`, `[label](url)` — and everything else is escaped in `jobpilot/cv/latex.py`.
- **Frontend**: React, Vite, TypeScript, Tailwind, shadcn/ui. The dashboard is bilingual; a new UI
  string goes in both `en` and `vi` under `web/src/i18n/`, and a missing one is a `tsc` error.
- **Network**: uvicorn binds `127.0.0.1` only. Do not add a code path that binds `0.0.0.0`.

## Where the detailed rules are

The rules for each area, and the traps already paid for, are in a `CLAUDE.md` inside that directory.
They are written for [Claude Code](https://claude.com/claude-code) but they are the conventions for
people too. **They are in Vietnamese**, as are `PLAN.md`, `SKILL.md`, `PHASES.md` and `DEPLOY.md`.

| File | Covers |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | principles, commands, conventions that cut across areas |
| [`jobpilot/crawler/CLAUDE.md`](jobpilot/crawler/CLAUDE.md) | adding a source, robots, sources already rejected, selector and fetch traps |
| [`jobpilot/cv/CLAUDE.md`](jobpilot/cv/CLAUDE.md) | adding a template, required macros, Jinja and LaTeX traps |
| [`jobpilot/intake/CLAUDE.md`](jobpilot/intake/CLAUDE.md) | reading a pasted job description and scoring fit |
| [`jobpilot/companies/CLAUDE.md`](jobpilot/companies/CLAUDE.md) | folding employer names, HR contacts, apply targets |
| [`jobpilot/llm/CLAUDE.md`](jobpilot/llm/CLAUDE.md) | providers and models per task, schemas, cost tracking |
| [`jobpilot/api/CLAUDE.md`](jobpilot/api/CLAUDE.md) | the `/api` prefix, auth and the network boundary, the pagination contract |
| [`jobpilot/apply/CLAUDE.md`](jobpilot/apply/CLAUDE.md) | outcomes, inbox sync, cover letter PDF |
| [`jobpilot/analytics/CLAUDE.md`](jobpilot/analytics/CLAUDE.md) | facets and coverage, salary parsing |
| [`web/src/CLAUDE.md`](web/src/CLAUDE.md) | colours and charts, React traps, pagination in the frontend |
| [`web/src/i18n/CLAUDE.md`](web/src/i18n/CLAUDE.md) | how the bilingual dashboard works |

[`PHASES.md`](PHASES.md) is the log of each phase: the decisions and the bugs that only appeared in
real runs. Read the part for the area you are about to change.

## Issues

Open an issue in English. For a bug, include what you ran, what you expected, and what happened.
For a parser bug, include the source and the job URL. Remove tokens, your CV and anyone's email
address before you paste a log.

## License

By contributing you agree that your contribution is released under the [MIT license](LICENSE).
Third-party files keep their own terms; see the License section of the [README](README.md).
