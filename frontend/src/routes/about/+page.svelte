<svelte:head>
  <title>SecBleau — About</title>
</svelte:head>

<div class="page">
  <header class="header">
    <a class="logo" href="/">
      <span class="logo-sec">Sec</span><span class="logo-bleau">Bleau</span>
    </a>
    <div class="tagline">About</div>
    <a class="nav-link" href="/">← Map</a>
    <a class="nav-link" href="/conditions">Conditions</a>
  </header>

  <main class="content">

    <section class="card">
      <h2>What is SecBleau?</h2>
      <p>
        SecBleau predicts whether the sandstone boulders of Fontainebleau forest are dry enough
        to climb safely. It combines open weather data with a physics-based evaporation model
        and crowd-sourced condition reports from climbers on the ground.
      </p>
      <p>
        <strong>Why it matters:</strong> Fontainebleau sandstone is fragile when wet. Climbing on
        damp rock tears holds permanently and degrades the surface for everyone. The yellow-green
        threshold (≥ 70% dryness score) indicates rock that is safe to climb on.
      </p>
    </section>

    <section class="card">
      <h2>How the prediction works</h2>
      <p>
        A physics model simulates moisture in the rock hour by hour using:
      </p>
      <ul>
        <li><strong>Precipitation</strong> — how much rain fell and when</li>
        <li><strong>Temperature &amp; humidity</strong> — vapour pressure deficit drives evaporation</li>
        <li><strong>Wind</strong> — removes the humid boundary layer above the rock</li>
        <li><strong>Solar radiation</strong> — direct sun heats the rock surface</li>
        <li><strong>Aspect &amp; shade</strong> — north-facing and canopy-covered areas dry slower</li>
      </ul>
      <p>
        Condition reports from climbers are fed into a Bayesian updater that adjusts
        per-boulder drying rate multipliers over time, making the model progressively more
        accurate for each location.
      </p>
      <p>
        Weather data is fetched hourly from <strong>Open-Meteo</strong> (free, open-source weather API).
      </p>
    </section>

    <section class="card">
      <h2>Data sources &amp; attribution</h2>

      <div class="attribution-list">
        <div class="attribution">
          <div class="attr-name">Climbing areas &amp; boulder data</div>
          <div class="attr-detail">
            <a href="https://www.boolder.com" target="_blank" rel="noopener">Boolder</a>
            — climbing area and problem data for Fontainebleau, licensed under
            <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0</a>.
            Data sourced from the
            <a href="https://github.com/boolder-org/boolder-data" target="_blank" rel="noopener">boolder-org/boolder-data</a>
            repository.
          </div>
        </div>

        <div class="attribution">
          <div class="attr-name">Weather data</div>
          <div class="attr-detail">
            <a href="https://open-meteo.com" target="_blank" rel="noopener">Open-Meteo</a>
            — free, open-source weather API. Hourly historical and forecast data
            (temperature, precipitation, humidity, wind, solar radiation).
            Used under their non-commercial free tier.
          </div>
        </div>

        <div class="attribution">
          <div class="attr-name">Map tiles</div>
          <div class="attr-detail">
            <a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a>
            using <a href="https://www.maplibre.org" target="_blank" rel="noopener">MapLibre GL JS</a>.
            Map data © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>
            contributors (ODbL).
          </div>
        </div>

        <div class="attribution">
          <div class="attr-name">Historical weather archive</div>
          <div class="attr-detail">
            <a href="https://www.meteoblue.com" target="_blank" rel="noopener">Météoblue</a>
            — linked from condition cards for reference to historical weather records.
          </div>
        </div>
      </div>
    </section>

    <section class="card">
      <h2>Privacy</h2>
      <p>
        SecBleau collects no personal data. Condition reports are anonymised using a
        one-way hash of your IP address and browser type — only the hash is stored,
        and it is used solely to prevent duplicate reports.
      </p>
      <p>
        <a href="/privacy">Read the full privacy notice →</a>
      </p>
    </section>

    <section class="card">
      <h2>Open source</h2>
      <p>
        SecBleau is a personal project built with FastAPI, PostgreSQL/PostGIS, SvelteKit,
        and MapLibre GL JS. Contributions and feedback are welcome.
      </p>
    </section>

  </main>
</div>

<style>
  :global(html), :global(body) { overflow: auto !important; height: auto !important; }

  .page { min-height: 100vh; background: #f8fafc; }

  .header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0 20px;
    height: 48px;
    background: #111827;
    color: #fff;
    position: sticky;
    top: 0;
    z-index: 10;
  }
  .logo { font-size: 20px; font-weight: 900; letter-spacing: -0.03em; text-decoration: none; }
  .logo-sec { color: #a6d96a; }
  .logo-bleau { color: #fff; }
  .tagline { font-size: 13px; color: #9ca3af; flex: 1; }
  .nav-link { color: #9ca3af; font-size: 12px; text-decoration: none; }
  .nav-link:hover { color: #fff; }

  .content {
    max-width: 720px;
    margin: 0 auto;
    padding: 28px 16px 60px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .card {
    background: #fff;
    border-radius: 12px;
    padding: 20px 24px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.07);
  }
  .card h2 {
    font-size: 15px;
    font-weight: 700;
    color: #111;
    margin-bottom: 12px;
  }
  .card p {
    font-size: 13px;
    color: #374151;
    line-height: 1.6;
    margin-bottom: 10px;
  }
  .card p:last-child { margin-bottom: 0; }
  .card ul {
    font-size: 13px;
    color: #374151;
    line-height: 1.7;
    padding-left: 20px;
    margin-bottom: 10px;
  }
  .card a { color: #2563eb; }
  .card a:hover { text-decoration: underline; }

  .attribution-list { display: flex; flex-direction: column; gap: 14px; }
  .attribution { font-size: 13px; }
  .attr-name { font-weight: 700; color: #111; margin-bottom: 3px; }
  .attr-detail { color: #374151; line-height: 1.5; }
</style>
