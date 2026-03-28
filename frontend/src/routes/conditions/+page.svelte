<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type ConditionsCluster } from '$lib/api/client';
  import { scoreToColor, scoreToLabel } from '$lib/dryness';

  let clusters: ConditionsCluster[] = [];
  let loading = true;
  let error: string | null = null;

  onMount(async () => {
    try {
      const data = await api.getConditions();
      clusters = data.clusters;
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : 'Failed to load conditions';
    } finally {
      loading = false;
    }
  });

  const PARIS = 'Europe/Paris';

  function fmtDateTime(iso: string | null): string {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('en-GB', { timeZone: PARIS, hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' });
  }

  function fmtTime(iso: string | null): string {
    if (!iso) return '—';
    return new Date(iso).toLocaleTimeString('en-GB', { timeZone: PARIS, hour: '2-digit', minute: '2-digit' });
  }

  function fmt(v: number | null, unit: string, decimals = 1): string {
    if (v == null) return '—';
    return v.toFixed(decimals) + '\u202f' + unit;
  }

  function fmtHours(h: number | null): string {
    if (h == null) return '—';
    if (h < 1) return 'just now';
    if (h < 24) return Math.round(h) + 'h ago';
    return Math.round(h / 24) + 'd ago';
  }

  // SVG rain bar chart — 72 hours, each bar = 1 hour
  function rainBars(hourly: Array<{ hour: string; mm: number }>): string {
    const W = 360, H = 48;
    const maxMm = Math.max(...hourly.map((r) => r.mm), 0.5);
    const barW = Math.max(1, W / 72);
    const now = Date.now();
    const startMs = now - 72 * 3600 * 1000;

    return hourly
      .map((r) => {
        const x = ((new Date(r.hour).getTime() - startMs) / (72 * 3600 * 1000)) * W;
        const barH = (r.mm / maxMm) * (H - 4);
        const color = r.mm < 0.1 ? '#d1fae5' : r.mm < 1 ? '#6ee7b7' : r.mm < 3 ? '#3b82f6' : '#1d4ed8';
        return `<rect x="${x.toFixed(1)}" y="${(H - barH).toFixed(1)}" width="${barW.toFixed(1)}" height="${barH.toFixed(1)}" fill="${color}" />`;
      })
      .join('');
  }

  function rainBarsSvg(hourly: Array<{ hour: string; mm: number }>): string {
    return `<svg viewBox="0 0 360 48" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">${rainBars(hourly)}</svg>`;
  }

  $: maxRain72h = Math.max(...clusters.map((c) => c.rain_72h_mm), 1);
</script>

<svelte:head>
  <title>SecBleau — Conditions</title>
</svelte:head>

<div class="page">
  <!-- Header -->
  <header class="header">
    <a class="logo" href="/">
      <span class="logo-sec">Sec</span><span class="logo-bleau">Bleau</span>
    </a>
    <div class="tagline">Drying conditions — last 72 h</div>
    <a class="nav-link" href="/">← Map</a>
    <a class="nav-link" href="/analysis">Analysis</a>

    <div class="spacer"></div>
    <a class="nav-link" href="/about">About</a>
    <a class="nav-link" href="/privacy">Privacy</a>
  </header>

  <main class="content">
    {#if loading}
      <div class="state">Loading conditions…</div>
    {:else if error}
      <div class="state error">{error}</div>
    {:else}

      <!-- What affects drying? explanation -->
      <section class="explainer">
        <h2>What affects drying?</h2>
        <div class="factors">
          <div class="factor">
            <span class="icon">🌧</span>
            <strong>Rainfall</strong>
            <span>Recent precipitation is the main input — sandstone absorbs water and needs time to release it.</span>
          </div>
          <div class="factor">
            <span class="icon">🌡</span>
            <strong>Temperature</strong>
            <span>Higher air temperature increases vapour pressure deficit, driving faster evaporation.</span>
          </div>
          <div class="factor">
            <span class="icon">💧</span>
            <strong>Humidity</strong>
            <span>High relative humidity slows evaporation — the air is already near saturation.</span>
          </div>
          <div class="factor">
            <span class="icon">💨</span>
            <strong>Wind</strong>
            <span>Wind removes the thin humid layer above the rock surface, accelerating drying.</span>
          </div>
          <div class="factor">
            <span class="icon">☀️</span>
            <strong>Solar radiation</strong>
            <span>Direct sun warms rock and drives evaporation — aspect and shade factor matter here.</span>
          </div>
          <div class="factor">
            <span class="icon">🌲</span>
            <strong>Canopy &amp; aspect</strong>
            <span>North-facing and heavily shaded sectors dry much slower than open south-facing ones.</span>
          </div>
        </div>
      </section>

      <!-- Cluster cards -->

      <div class="grid">
        {#each clusters as c}
          {@const color = scoreToColor(c.dryness_score)}
          <div class="card">
            <div class="card-header">
              <span class="cluster-name">{c.name}</span>
              <span class="badge" style="background:{color}20; color:{color}; border:1px solid {color}">
                {scoreToLabel(c.dryness_score)}
              </span>
              <span class="area-count">{c.area_count} areas</span>
            </div>

            <!-- Rainfall section -->
            <div class="section-label">Rainfall last 72 h</div>
            <div class="rain-bars">
              <div class="rain-row">
                <span class="rain-period">24 h</span>
                <div class="rain-track">
                  <div class="rain-fill" style="width:{Math.min(100, (c.rain_24h_mm / maxRain72h) * 100)}%; background:{c.rain_24h_mm < 1 ? '#10b981' : c.rain_24h_mm < 5 ? '#f59e0b' : '#ef4444'}"></div>
                </div>
                <span class="rain-val">{fmt(c.rain_24h_mm, 'mm', 1)}</span>
              </div>
              <div class="rain-row">
                <span class="rain-period">48 h</span>
                <div class="rain-track">
                  <div class="rain-fill" style="width:{Math.min(100, (c.rain_48h_mm / maxRain72h) * 100)}%; background:{c.rain_48h_mm < 2 ? '#10b981' : c.rain_48h_mm < 10 ? '#f59e0b' : '#ef4444'}"></div>
                </div>
                <span class="rain-val">{fmt(c.rain_48h_mm, 'mm', 1)}</span>
              </div>
              <div class="rain-row">
                <span class="rain-period">72 h</span>
                <div class="rain-track">
                  <div class="rain-fill" style="width:{Math.min(100, (c.rain_72h_mm / maxRain72h) * 100)}%; background:{c.rain_72h_mm < 3 ? '#10b981' : c.rain_72h_mm < 15 ? '#f59e0b' : '#ef4444'}"></div>
                </div>
                <span class="rain-val">{fmt(c.rain_72h_mm, 'mm', 1)}</span>
              </div>
            </div>

            <!-- Hourly rain chart -->
            {#if c.hourly_rain.length > 0}
              <div class="chart-wrap">
                <div class="chart-label-row">
                  <span>72 h ago</span><span>now</span>
                </div>
                <!-- svelte-ignore a11y-missing-attribute -->
                <div class="chart">{@html rainBarsSvg(c.hourly_rain)}</div>
              </div>
            {/if}

            <!-- Current conditions -->
            <div class="section-label">Current conditions</div>
            <div class="conditions-grid">
              <div class="cond">
                <span class="cond-icon">🌡</span>
                <span class="cond-val">{fmt(c.temperature_c, '°C')}</span>
                <span class="cond-lbl">Temp</span>
              </div>
              <div class="cond">
                <span class="cond-icon">💧</span>
                <span class="cond-val">{fmt(c.humidity_pct, '%', 0)}</span>
                <span class="cond-lbl">Humidity</span>
              </div>
              <div class="cond">
                <span class="cond-icon">💨</span>
                <span class="cond-val">{fmt(c.wind_speed_ms, 'm/s')}</span>
                <span class="cond-lbl">Wind</span>
              </div>
              <div class="cond">
                <span class="cond-icon">☀️</span>
                <span class="cond-val">{fmt(c.solar_radiation_wm2, 'W/m²', 0)}</span>
                <span class="cond-lbl">Solar</span>
              </div>
            </div>

            <!-- Summary line -->
            <div class="summary-line">
              Last rain <strong>{fmtHours(c.hours_since_rain)}</strong>
              {#if c.last_rain_mm != null}
                · <strong>{fmt(c.last_rain_mm, 'mm', 1)}</strong>
              {/if}
            </div>

            <!-- Data freshness + source -->
            <div class="data-meta">
              <span class="meta-item">
                Updated <strong>{fmtDateTime(c.data_last_updated_at)}</strong>
                · next <strong>{fmtTime(c.data_next_update_at)}</strong>
              </span>
              <a class="source-link" href={c.source_url} target="_blank" rel="noopener">
                Météoblue ↗
              </a>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </main>
</div>

<style>
  /* Override layout's overflow:hidden so this page scrolls */
  :global(html), :global(body) {
    overflow: auto !important;
    height: auto !important;
  }

  .page {
    min-height: 100vh;
    background: #f8fafc;
  }

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
  .spacer { flex: 1; }

  .content {
    max-width: 1100px;
    margin: 0 auto;
    padding: 24px 16px 48px;
  }

  .state { text-align: center; padding: 60px; color: #6b7280; font-size: 15px; }
  .state.error { color: #dc2626; }

  /* Explainer */
  .explainer {
    background: #fff;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 24px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.07);
  }
  .explainer h2 { font-size: 15px; font-weight: 700; color: #111; margin-bottom: 14px; }
  .factors {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 12px;
  }
  .factor {
    display: flex;
    flex-direction: column;
    gap: 3px;
    font-size: 12px;
    color: #374151;
  }
  .factor .icon { font-size: 18px; }
  .factor strong { font-size: 12px; color: #111; }


  /* Cards grid */
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 16px;
  }

  .card {
    background: #fff;
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.07);
  }

  .card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 14px;
  }
  .cluster-name { font-size: 15px; font-weight: 800; color: #111; flex: 1; }
  .badge {
    font-size: 10px;
    font-weight: 700;
    border-radius: 10px;
    padding: 2px 8px;
    white-space: nowrap;
  }
  .area-count { font-size: 11px; color: #9ca3af; white-space: nowrap; }

  .section-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #6b7280;
    margin-bottom: 8px;
    margin-top: 14px;
  }
  .card-header + .section-label { margin-top: 0; }

  /* Rainfall bars */
  .rain-bars { display: flex; flex-direction: column; gap: 5px; margin-bottom: 2px; }
  .rain-row { display: flex; align-items: center; gap: 8px; }
  .rain-period { font-size: 11px; color: #6b7280; width: 26px; flex-shrink: 0; }
  .rain-track {
    flex: 1;
    height: 8px;
    background: #f3f4f6;
    border-radius: 4px;
    overflow: hidden;
  }
  .rain-fill { height: 100%; border-radius: 4px; transition: width 0.4s; min-width: 2px; }
  .rain-val { font-size: 11px; color: #374151; width: 42px; text-align: right; flex-shrink: 0; font-variant-numeric: tabular-nums; }

  /* Hourly chart */
  .chart-wrap { margin-top: 8px; margin-bottom: 4px; }
  .chart-label-row {
    display: flex;
    justify-content: space-between;
    font-size: 9px;
    color: #9ca3af;
    margin-bottom: 2px;
  }
  .chart {
    width: 100%;
    height: 48px;
    background: #f8fafc;
    border-radius: 4px;
    overflow: hidden;
  }
  .chart :global(svg) { width: 100%; height: 100%; display: block; }

  /* Current conditions */
  .conditions-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
    margin-bottom: 12px;
  }
  .cond {
    background: #f8fafc;
    border-radius: 8px;
    padding: 8px 4px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }
  .cond-icon { font-size: 16px; }
  .cond-val { font-size: 12px; font-weight: 700; color: #111; font-variant-numeric: tabular-nums; }
  .cond-lbl { font-size: 9px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.05em; }

  .summary-line {
    font-size: 12px;
    color: #6b7280;
    border-top: 1px solid #f3f4f6;
    padding-top: 10px;
    margin-bottom: 8px;
  }
  .summary-line strong { color: #111; }

  .data-meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    font-size: 10px;
    color: #9ca3af;
    border-top: 1px solid #f3f4f6;
    padding-top: 8px;
  }
  .meta-item strong { color: #6b7280; }
  .source-link {
    color: #6b7280;
    text-decoration: none;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .source-link:hover { color: #111; text-decoration: underline; }
</style>
