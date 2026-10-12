# JobPilot Web Dashboard

The control plane for JobPilot (`PLAN.md` §5.6) — React + Vite + TypeScript + TailwindCSS. It is a
client of the REST API and nothing else: every state change goes through `/api`, and live updates
arrive over the WebSocket.

Eleven pages: Deck, Jobs (and Job detail / CV Review), CV Studio, Applications, Companies, Runs,
Market, Models, Backup, Settings, Guide. The UI is bilingual, Vietnamese by default.

## Run

```bash
cp .env.example .env.local   # set VITE_API_TOKEN to match JOBPILOT_API_TOKEN in the backend .env
npm ci
npm run dev                  # http://127.0.0.1:5173, proxies /api to :8000
```

Needs the backend running: `python -m jobpilot.cli serve` (http://127.0.0.1:8000).

`npm run build` type-checks and writes `dist/`. FastAPI serves that build same-origin, so a
deployed install has one address and no dev server. Vite compiles `VITE_API_TOKEN` into the
bundle, which is why the network boundary, not the token, is what keeps strangers out — see
`jobpilot/api/CLAUDE.md`.

## Design

"Flight deck" — warm-neutral surfaces, a marigold accent (runway light), aqua
LIVE indicator. Charts use the validated `dataviz` palette (categorical hues by
source, ordinal blue for the funnel). Display face Space Grotesk; JetBrains Mono
for job IDs and metrics. Dark mode is a selected palette, not an auto-flip.

## Layout

```
src/
  App.tsx            routes + realtime version nudge
  pages/             one file per page
  components/
    ui.tsx           Card/Button/Badge/Input/Select/Skeleton (shadcn-style)
    Layout.tsx       sidebar + LIVE indicator + theme and language toggles
    charts/          chart components + palette (dataviz)
    cv/              CV Studio: section editors, PDF preview, version history, template picker
    review/          CV Review pieces
  hooks/             useApi, usePaging, useTask, useWebSocket
  i18n/              en + vi dictionaries; `vi` is typed against `en`
  lib/               api, format, labels, statuses, theme, utils
```

Rules and traps for this code are in `src/CLAUDE.md` and `src/i18n/CLAUDE.md` (in Vietnamese).
