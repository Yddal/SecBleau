# SecBleau

**SecBleau** predicts whether the sandstone boulders of Fontainebleau forest are dry enough to climb safely. It combines open weather data with a physics-based evaporation model and crowd-sourced condition reports from climbers on the ground.

> **Why it matters:** Fontainebleau sandstone is fragile when wet. Climbing on damp rock tears holds permanently and degrades the surface for everyone. The yellow-green threshold (≥ 70% dryness score) indicates rock that is safe to climb on.

---

## Features

- **Interactive map** — browse all climbing areas and boulders colour-coded by dryness score, from cluster view down to individual boulder level
- **Dryness prediction** — hourly physics model simulating moisture in the rock based on precipitation, temperature, humidity, wind, solar radiation, aspect and canopy shade
- **Conditions page** — rainfall totals (24h / 48h / 72h), current weather, and hourly rain chart per cluster
- **Analysis page** — per-area breakdown of score components (physics score, ML correction, shade, canopy, elevation) with 72-hour weather charts
- **Condition reports** — climbers can submit wet / drying / climbable reports; these feed a Bayesian updater that refines per-boulder drying rates over time
- **Boulder search** — find any problem by name across all sectors
- **Privacy-first** — no accounts, no personal data; reports are anonymised with a one-way hash

---

## How the prediction works

A physics model runs hour by hour over the past 7 days of weather data:

```
dM/dt = precipitation_input(t) − k_evap(t) × M(t)
```

where `M` is the moisture state [0 = bone dry, 1 = saturated] and `k_evap` is an evaporation coefficient driven by vapour pressure deficit, wind speed, solar radiation, and area-specific shade / canopy / aspect factors.

Condition reports from climbers are fed into a Bayesian updater (Kalman filter) that adjusts per-boulder `drying_rate_multiplier` parameters, making the model progressively more accurate for each location.

Weather is fetched hourly from Open-Meteo and scores are recomputed 5 minutes later — fully automatic.

---

## Quick start

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/) running.

```bat
start.bat
```

This will:
1. Create `.env` from `.env.example` if not present
2. Start the API, database, and frontend containers
3. Sync climbing area and boulder data from Boolder
4. Calibrate area drying parameters (elevation, aspect, shade)
5. Open the app at `http://localhost:5173`

To stop:

```bat
stop.bat
```

Data is preserved in Docker volumes between restarts.

### Optional configuration (`.env`)

| Variable | Purpose |
|---|---|
| `NETATMO_CLIENT_ID` / `SECRET` | Pull data from nearby Netatmo weather stations |
| `CLOUDFLARE_TUNNEL_TOKEN` | Expose the app publicly via Cloudflare Tunnel |
| `CORS_ORIGINS` | Allowed origins for the API |

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | SvelteKit 2 · TypeScript · MapLibre GL JS · Vite |
| Backend | FastAPI · Python 3.11 · APScheduler |
| Database | PostgreSQL 16 · PostGIS 3.4 · SQLAlchemy 2 · Alembic |
| Infrastructure | Docker Compose · Cloudflare Tunnel (optional) |

---

## Project structure

```
SecBleau/
├── backend/
│   ├── app/
│   │   ├── routers/        # FastAPI route handlers (areas, boulders, weather, reports)
│   │   ├── services/       # Physics model, Bayesian updater
│   │   ├── tasks/          # Scheduled jobs (weather fetch, score recompute, cleanup)
│   │   └── models/         # SQLAlchemy ORM models
│   └── data/
│       ├── boolder_import.py    # Sync climbing data from Boolder
│       └── calibrate_areas.py  # Set shade/canopy/elevation parameters per area
├── frontend/
│   └── src/
│       ├── routes/         # SvelteKit pages (map, conditions, analysis, about, privacy)
│       └── lib/
│           ├── components/ # Map, popups, charts
│           └── api/        # Typed API client
├── start.bat
└── stop.bat
```

---

## Data sources & attribution

**Climbing areas & boulder data**
[Boolder](https://www.boolder.com) — climbing area and problem data for Fontainebleau, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Data sourced from the [boolder-org/boolder-data](https://github.com/boolder-org/boolder-data) repository.

**Weather data**
[Open-Meteo](https://open-meteo.com) — free, open-source weather API. Hourly historical and forecast data (temperature, precipitation, humidity, wind, solar radiation). Used under their non-commercial free tier.

**Map tiles**
[OpenFreeMap](https://openfreemap.org) using [MapLibre GL JS](https://www.maplibre.org). Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL).

**Historical weather archive**
[Météoblue](https://www.meteoblue.com) — linked from condition cards for reference to historical weather records.

---

## Privacy

SecBleau collects no personal data. Condition reports are anonymised using a one-way hash of your IP address and browser type — only the hash is stored, and it is used solely to prevent duplicate reports within a 4-hour window. See the [Privacy notice](/privacy) in the app for full details.

---

## License

SecBleau is a personal project. Climbing area and boulder data is used under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) from Boolder — attribution required if redistributed.
