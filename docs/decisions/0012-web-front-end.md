# ADR-0012: Web front end on FastAPI and Next.js

Status: accepted
Date: 2026-10-22

## Context

The Streamlit "My team" view looked generic, and Streamlit cannot draw an FPL-style pitch
with player cards well. The roadmap already planned FastAPI and a Next.js UI (Phase 7).
Managers need two things now: this GW's plan for their team, and stats pages.

## Decision

- `diffpl.api` (FastAPI) serves read-only JSON:
  - `GET /api/plan/{team_id}`: top EV plans for the next deadline (ADR-0010), cached per team
    for 10 minutes; one solve per team at a time.
  - `GET /api/stats/players`, `/players/{id}`, `/teams`, `/fixtures`: from the live season.
    Player detail includes the champion's next-GW points distribution.
- `web/` (Next.js 15 App Router, React 19, TypeScript, Tailwind 4) draws the pages.
  Charts are hand-built SVG, following one sequential hue and a validated diverging scale.
  Shirts are SVG in approximate club colours; no club or FPL artwork is used.
- No accounts. The team id lives in the URL and, as a convenience, in localStorage.
- Streamlit stays as the internal dashboard (league, replay, models).

Stats definitions: team xG is the sum of its players' xG; fixture difficulty is expected goals
for and against, league average times own attack times opponent defence, from xG over each
team's last 6 matches shrunk toward the average by 3 matches.

## Alternatives considered

- Restyle Streamlit with CSS and a full-page HTML component: quicker, but still limited.
- A third-party stats sheet as a source: it repackages the FPL API without a license and on
  someone else's schedule; everything in it is derivable from our own ingest.

## Consequences

- A cold plan takes about 1 to 2 minutes (projections plus up to 5 MILP solves); the page
  shows progress and later requests are cached.
- API types are mirrored by hand in `web/src/lib/api.ts`; a schema change must update both.
- Event-location charts (shot or take-on maps) need licensed event data and are out of scope.
