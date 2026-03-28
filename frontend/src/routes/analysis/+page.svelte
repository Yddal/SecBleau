<script lang="ts">
  import { onMount } from 'svelte';
  import {
    api,
    type AreaAnalysis,
    type ClusterAnalysis,
    type RecentReport,
    type WeatherHour,
  } from '$lib/api/client';
  import { scoreToColor, scoreToLabel } from '$lib/dryness';

  // ── State ──────────────────────────────────────────────────────────────────
  type Tab = 'analysis' | 'reports';
  let activeTab: Tab = 'analysis';

  let clusters: ClusterAnalysis[] = [];
  let reports: RecentReport[] = [];
  let loadingAnalysis = true;
  let loadingReports = true;
  let errorAnalysis: string | null = null;
  let errorReports: string | null = null;
  let reportsGeneratedAt: string | null = null;

  // Expand / collapse
  let expandedClusters = new Set<string>();
  let expandedAreas    = new Set<number>();

  function toggleCluster(name: string) {
    if (expandedClusters.has(name)) expandedClusters.delete(name);
    else expandedClusters.add(name);
    expandedClusters = expandedClusters;
  }

  function toggleArea(id: number) {
    if (expandedAreas.has(id)) expandedAreas.delete(id);
    else expandedAreas.add(id);
    expandedAreas = expandedAreas;
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────────
  onMount(() => {
    loadAnalysis();
    loadReports();
    const interval = setInterval(() => {
      if (activeTab === 'reports') loadReports();
    }, 30_000);
    return () => clearInterval(interval);
  });

  async function loadAnalysis() {
    try {
      const data = await api.getAnalysis();
      clusters = data.clusters;
    } catch (e: unknown) {
      errorAnalysis = e instanceof Error ? e.message : 'Failed to load analysis';
    } finally {
      loadingAnalysis = false;
    }
  }

  async function loadReports() {
    loadingReports = true;
    try {
      const data = await api.getRecentReports(48, 200);
      reports = data.reports;
      reportsGeneratedAt = data.generated_at;
    } catch (e: unknown) {
      errorReports = e instanceof Error ? e.message : 'Failed to load reports';
    } finally {
      loadingReports = false;
    }
  }

  // ── General helpers ────────────────────────────────────────────────────────
  const PARIS = 'Europe/Paris';

  function fmtTime(iso: string): string {
    return new Date(iso).toLocaleString('en-GB', {
      timeZone: PARIS, day: 'numeric', month: 'short',
      hour: '2-digit', minute: '2-digit',
    });
  }

  function timeAgo(iso: string): string {
    const diffMs = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diffMs / 60_000);
    if (mins < 1)  return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const h = Math.floor(mins / 60);
    if (h < 24)    return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  }

  function clusterAvg(areas: AreaAnalysis[]): number | null {
    const scores = areas.map(a => a.dryness_score).filter((v): v is number => v !== null);
    if (!scores.length) return null;
    return scores.reduce((a, b) => a + b, 0) / scores.length;
  }

  // ── Sector analysis helpers ────────────────────────────────────────────────
  const ASPECT_LABELS: Record<string, string> = {
    N:    'North-facing — minimal direct sunlight, dries very slowly',
    NE:   'North-east facing — limited morning sun',
    E:    'East-facing — morning sun only',
    SE:   'South-east facing — good morning sun',
    S:    'South-facing — maximum solar exposure, dries fastest',
    SW:   'South-west facing — good afternoon sun',
    W:    'West-facing — afternoon sun only',
    NW:   'North-west facing — limited afternoon sun',
    flat: 'Flat/horizontal surface — exposed to overhead sun and rainfall',
  };

  function getConsiderations(area: AreaAnalysis): string[] {
    const items: string[] = [];

    // Quick-drying flag first (most useful info)
    if (area.shade_factor !== null && area.canopy_factor !== null &&
        area.shade_factor >= 0.85 && area.canopy_factor <= 0.15) {
      items.push('Known quick-drying sector (Boolder guidebook)');
    }

    if (area.aspect && ASPECT_LABELS[area.aspect]) {
      items.push(ASPECT_LABELS[area.aspect]);
    }

    if (area.shade_factor !== null) {
      if (area.shade_factor >= 0.85)
        items.push('Highly exposed, open area — strong solar drying potential');
      else if (area.shade_factor < 0.3)
        items.push('Heavily shaded — minimal solar drying');
      else if (area.shade_factor < 0.7)
        items.push('Partially shaded — moderate solar exposure');
      else
        items.push('Mostly open, sunny area — good solar drying');
    }

    if (area.canopy_factor !== null) {
      if (area.canopy_factor <= 0.15)
        items.push('Very open sky — excellent air circulation and evaporation');
      else if (area.canopy_factor > 0.7)
        items.push('Dense tree canopy — traps moisture, significantly slows drying');
      else if (area.canopy_factor > 0.4)
        items.push('Partial tree canopy — some moisture retention');
      else
        items.push('Mostly open sky — good air circulation');
    }

    if (area.elevation_m !== null) {
      if (area.elevation_m > 120)
        items.push(`Higher elevation (${area.elevation_m}\u202fm) — more wind exposure, less sheltered`);
      else if (area.elevation_m < 70)
        items.push(`Low elevation (${area.elevation_m}\u202fm) — sheltered valley, slower wind drying`);
      else
        items.push(`Mid-range elevation (${area.elevation_m}\u202fm)`);
    }

    if (area.ml_correction !== null && Math.abs(area.ml_correction) > 0.05) {
      if (area.ml_correction > 0.1)
        items.push('Dries faster than physics model predicts — confirmed by user reports');
      else if (area.ml_correction < -0.1)
        items.push('Dries slower than physics model predicts — confirmed by user reports');
    }

    if (area.is_estimated) {
      items.push('Score estimated from physics model — no direct reports yet for this area');
    } else if (area.confidence > 0.7) {
      items.push('Well calibrated — validated by multiple user reports');
    } else if (area.confidence > 0.4) {
      items.push('Partially calibrated from user reports');
    }

    return items;
  }

  function getWhySummary(area: AreaAnalysis): string {
    const score = area.dryness_score;
    if (score === null) return 'No dryness data available.';
    if (score >= 0.85) {
      return 'Excellent conditions. Evaporation factors are strong and sustained.';
    } else if (score >= 0.70) {
      return 'Climbable. Rock moisture is below the safe threshold.';
    } else if (score >= 0.55) {
      return 'Still drying. Evaporation is progressing but rock moisture remains elevated.';
    } else if (score >= 0.30) {
      const slow: string[] = [];
      if (area.aspect && ['N', 'NE', 'NW'].includes(area.aspect)) slow.push('north-facing aspect');
      if (area.shade_factor !== null && area.shade_factor < 0.35)  slow.push('heavy shade');
      if (area.canopy_factor !== null && area.canopy_factor > 0.65) slow.push('dense canopy');
      return `Damp.${slow.length ? ` Drying is slowed by ${slow.join(' and ')}.` : ''}`;
    } else {
      return 'Wet. Avoid climbing — sandstone is fragile when wet.';
    }
  }

  // ── Weather chart ──────────────────────────────────────────────────────────
  interface ChartBar   { x: number; y: number; w: number; h: number; }
  interface ChartLabel { x: number; label: string; }
  interface ChartPoint {
    x: number; ms: number;
    t:  number | null; yT:  number | null;
    hu: number | null; yHu: number | null;
    w:  number | null; yW:  number | null;
    p: number;
    timeLabel: string;
  }
  interface ChartResult {
    tempPath: string; humidPath: string; windPath: string;
    rainBars: ChartBar[]; xLabels: ChartLabel[];
    precipMax: number; windMax: number;
    tempLo: number; tempHi: number;
    svgH: number; lineBotY: number; rainTopY: number; rainBotY: number;
    x0: number;
    points: ChartPoint[];
  }

  function makeChart(data: WeatherHour[]): ChartResult | null {
    if (data.length < 2) return null;

    const X0 = 22, CHART_W = 694;        // leave 22px left for y-labels
    const LINE_TOP = 5, LINE_H = 72;
    const LINE_BOT = LINE_TOP + LINE_H;   // 77
    const RAIN_TOP = LINE_BOT + 10;       // 87
    const RAIN_H   = 26;
    const RAIN_BOT = RAIN_TOP + RAIN_H;   // 113
    const SVG_H    = RAIN_BOT + 9;        // 122

    const ms = data.map(d => new Date(d.h).getTime());
    const t0 = ms[0], t1 = ms[ms.length - 1];
    const tSpan = t1 - t0 || 3_600_000;
    const xOf = (i: number) => X0 + ((ms[i] - t0) / tSpan) * CHART_W;

    const temps  = data.map(d => d.t).filter((v): v is number => v !== null);
    const winds  = data.map(d => d.w).filter((v): v is number => v !== null);
    const precips = data.map(d => d.p ?? 0);

    const tempLo    = temps.length  ? Math.min(...temps) - 1  : 0;
    const tempHi    = temps.length  ? Math.max(...temps) + 1  : 30;
    const windMax   = Math.max(3, ...winds);
    const precipMax = Math.max(0.5, ...precips);

    const yLine  = (n: number) => LINE_BOT - Math.max(0, Math.min(1, n)) * LINE_H;
    const yTemp  = (v: number) => yLine((v - tempLo) / (tempHi - tempLo));
    const yHumid = (v: number) => yLine(v / 100);
    const yWind  = (v: number) => yLine(v / windMax);

    function buildPath(yFn: (v: number) => number, vals: (number | null)[]): string {
      let d = '', inSeg = false;
      for (let i = 0; i < data.length; i++) {
        const v = vals[i];
        if (v === null || !Number.isFinite(v)) { inSeg = false; continue; }
        const pt = `${xOf(i).toFixed(1)},${yFn(v).toFixed(1)}`;
        d += inSeg ? ` L${pt}` : ` M${pt}`;
        inSeg = true;
      }
      return d.trim();
    }

    const barW = Math.max(2, (CHART_W / data.length) * 0.85);
    const rainBars: ChartBar[] = data.flatMap((d, i) => {
      const p = d.p ?? 0;
      if (p < 0.05) return [];
      const bh = Math.min(RAIN_H, (p / precipMax) * RAIN_H);
      return [{ x: xOf(i) - barW / 2, y: RAIN_BOT - bh, w: barW, h: bh }];
    });

    const xLabels: ChartLabel[] = [];
    const nowMs = Date.now();
    for (let ago = 72; ago >= 0; ago -= 24) {
      const t = nowMs - ago * 3_600_000;
      if (t >= t0 && t <= t1) {
        xLabels.push({ x: X0 + ((t - t0) / tSpan) * CHART_W, label: ago === 0 ? 'now' : `-${ago}h` });
      }
    }

    const points: ChartPoint[] = data.map((d, i) => ({
      x:  xOf(i),
      ms: ms[i],
      t:   d.t  ?? null,
      yT:  d.t  != null ? yTemp(d.t)   : null,
      hu:  d.hu ?? null,
      yHu: d.hu != null ? yHumid(d.hu) : null,
      w:   d.w  ?? null,
      yW:  d.w  != null ? yWind(d.w)   : null,
      p:   d.p  ?? 0,
      timeLabel: new Date(ms[i]).toLocaleString('en-GB', {
        timeZone: PARIS, day: 'numeric', month: 'short',
        hour: '2-digit', minute: '2-digit',
      }),
    }));

    return {
      tempPath: buildPath(yTemp,  data.map(d => d.t)),
      humidPath: buildPath(yHumid, data.map(d => d.hu)),
      windPath:  buildPath(yWind,  data.map(d => d.w)),
      rainBars, xLabels,
      precipMax, windMax: Math.round(windMax),
      tempLo: Math.round(tempLo), tempHi: Math.round(tempHi),
      svgH: SVG_H, lineBotY: LINE_BOT, rainTopY: RAIN_TOP, rainBotY: RAIN_BOT,
      x0: X0, points,
    };
  }

  // ── Chart line visibility (per area) ──────────────────────────────────────
  const ALL_LINES = new Set(['temp', 'humid', 'wind', 'rain']);
  let visibleLines = new Map<number, Set<string>>();

  function toggleLine(areaId: number, line: string) {
    const current = visibleLines.get(areaId) ?? new Set(ALL_LINES);
    const next = new Set(current);
    if (next.has(line)) next.delete(line); else next.add(line);
    visibleLines = new Map(visibleLines).set(areaId, next);
  }

  // ── Chart hover / click ────────────────────────────────────────────────────
  interface ChartInteraction { areaId: number; ptIdx: number; }
  let chartHover:  ChartInteraction | null = null;
  let chartPinned: ChartInteraction | null = null;

  function chartNearestIdx(e: MouseEvent, chart: ChartResult): number {
    const svg = (e.currentTarget as SVGElement).closest('svg') as SVGSVGElement;
    const { left, width } = svg.getBoundingClientRect();
    const svgX = ((e.clientX - left) / width) * 720;
    let best = 0, bestD = Infinity;
    for (let i = 0; i < chart.points.length; i++) {
      const d = Math.abs(chart.points[i].x - svgX);
      if (d < bestD) { bestD = d; best = i; }
    }
    return best;
  }

  function chartMouseMove(e: MouseEvent, areaId: number, chart: ChartResult) {
    chartHover = { areaId, ptIdx: chartNearestIdx(e, chart) };
  }

  function chartMouseLeave(areaId: number) {
    if (chartHover?.areaId === areaId) chartHover = null;
  }

  function chartClick(e: MouseEvent, areaId: number, chart: ChartResult) {
    const idx = chartNearestIdx(e, chart);
    if (chartPinned?.areaId === areaId && chartPinned.ptIdx === idx) {
      chartPinned = null;
    } else {
      chartPinned = { areaId, ptIdx: idx };
    }
    e.stopPropagation();
  }

  // ── Report status tab ──────────────────────────────────────────────────────
  const CONDITION_COLOR: Record<string, string> = {
    wet: '#d73027', drying: '#fdae61', some_boulders_dry: '#a6d96a',
    dry: '#1a9641', climbable: '#1a9641',
  };
  const CONDITION_LABEL: Record<string, string> = {
    wet: 'Wet', drying: 'Drying', some_boulders_dry: 'Some dry',
    dry: 'Dry', climbable: 'Climbable',
  };
</script>

<svelte:head>
  <title>SecBleau — Analysis</title>
</svelte:head>

<div class="page">
  <!-- Header -->
  <header class="header">
    <a class="logo" href="/">
      <span class="logo-sec">Sec</span><span class="logo-bleau">Bleau</span>
    </a>
    <div class="tagline">Sector analysis</div>
    <a class="nav-link" href="/">← Map</a>
    <a class="nav-link" href="/conditions">Conditions</a>

    <div class="spacer"></div>
    <a class="nav-link" href="/about">About</a>
    <a class="nav-link" href="/privacy">Privacy</a>
  </header>

  <!-- Tab bar -->
  <div class="tab-bar">
    <button class="tab-btn" class:active={activeTab === 'analysis'}
      on:click={() => (activeTab = 'analysis')}>Sector Analysis</button>
    <button class="tab-btn" class:active={activeTab === 'reports'}
      on:click={() => { activeTab = 'reports'; loadReports(); }}>Report Status</button>
  </div>

  <main class="content">

    <!-- ═══════════════════════ TAB 1: SECTOR ANALYSIS ═══════════════════════ -->
    {#if activeTab === 'analysis'}
      {#if loadingAnalysis}
        <div class="state">Loading analysis…</div>
      {:else if errorAnalysis}
        <div class="state error">{errorAnalysis}</div>
      {:else if clusters.length === 0}
        <div class="state">No sector data available.</div>
      {:else}
        <div class="cluster-list">
          {#each clusters as cluster}
            {@const avgScore = clusterAvg(cluster.areas)}
            {@const avgColor = scoreToColor(avgScore)}
            {@const isOpen   = expandedClusters.has(cluster.name)}

            <div class="cluster-folder">
              <!-- Cluster header (clickable folder) -->
              <button class="cluster-header" on:click={() => toggleCluster(cluster.name)}>
                <span class="chevron" class:open={isOpen}>▸</span>
                <span class="cluster-name">{cluster.name}</span>
                <span class="cluster-meta">{cluster.areas.length} areas</span>
                {#if avgScore !== null}
                  <div class="cluster-score-bar">
                    <div class="cluster-score-fill" style="width:{Math.round(avgScore*100)}%; background:{avgColor}"></div>
                    <div class="cluster-threshold"></div>
                  </div>
                  <span class="cluster-score-pct" style="color:{avgColor}">{Math.round(avgScore*100)}%</span>
                {/if}
              </button>

              {#if isOpen}
                <div class="area-list">
                  {#each cluster.areas as area}
                    {@const color      = scoreToColor(area.dryness_score)}
                    {@const label      = scoreToLabel(area.dryness_score)}
                    {@const pct        = area.dryness_score !== null ? Math.round(area.dryness_score * 100) : null}
                    {@const isAreaOpen = expandedAreas.has(area.id)}
                    {@const chart      = isAreaOpen ? makeChart(area.weather_72h) : null}
                    {@const items      = isAreaOpen ? getConsiderations(area) : []}
                    {@const why        = isAreaOpen ? getWhySummary(area) : ''}
                    {@const vis        = isAreaOpen ? (visibleLines.get(area.id) ?? ALL_LINES) : ALL_LINES}

                    <div class="area-item">
                      <!-- Area row (collapsed summary) -->
                      <button class="area-row" on:click={() => toggleArea(area.id)}>
                        <span class="chevron small" class:open={isAreaOpen}>▸</span>
                        <span class="area-name">{area.name}</span>
                        <div class="score-bar-track">
                          <div class="score-bar-fill" style="width:{pct ?? 0}%; background:{color}"></div>
                          <div class="score-threshold"></div>
                        </div>
                        <span class="score-pct" style="color:{color}">{pct !== null ? pct + '%' : '—'}</span>
                        <span class="badge" style="background:{color}22; color:{color}; border-color:{color}">{label}</span>
                      </button>

                      <!-- Expanded area detail -->
                      {#if isAreaOpen}
                        <div class="area-detail">

                          <!-- Weather chart -->
                          {#if area.weather_72h.length >= 2}
                            <div class="chart-wrap">
                              <div class="chart-legend">
                                <button class="legend-item temp"  class:dim={!vis.has('temp')}  on:click={() => toggleLine(area.id, 'temp')}>— Temperature</button>
                                <button class="legend-item humid" class:dim={!vis.has('humid')} on:click={() => toggleLine(area.id, 'humid')}>— Humidity</button>
                                <button class="legend-item wind"  class:dim={!vis.has('wind')}  on:click={() => toggleLine(area.id, 'wind')}>- - Wind</button>
                                <button class="legend-item rain"  class:dim={!vis.has('rain')}  on:click={() => toggleLine(area.id, 'rain')}>▊ Rain</button>
                              </div>
                              {#if chart}
                                {@const _isPinned = chartPinned !== null && chartPinned.areaId === area.id}
                                {@const _isHover  = chartHover  !== null && chartHover.areaId  === area.id}
                                {@const _activeIdx = _isPinned && chartPinned ? chartPinned.ptIdx
                                                   : _isHover  && chartHover  ? chartHover.ptIdx
                                                   : null}
                                <svg viewBox="0 0 720 {chart.svgH}" class="weather-svg" xmlns="http://www.w3.org/2000/svg">

                                  <!-- Horizontal grid lines (line zone) -->
                                  {#each [0.25, 0.5, 0.75] as frac}
                                    <line x1={chart.x0} y1={chart.lineBotY - frac * 72}
                                          x2={chart.x0 + 694} y2={chart.lineBotY - frac * 72}
                                          stroke="#e5e7eb" stroke-width="0.5" />
                                  {/each}

                                  <!-- Zone separator (line / rain) -->
                                  <line x1={chart.x0} y1={chart.rainTopY - 3}
                                        x2={chart.x0 + 694} y2={chart.rainTopY - 3}
                                        stroke="#d1d5db" stroke-width="0.5" stroke-dasharray="3,3" />

                                  <!-- Rain bars -->
                                  {#if vis.has('rain')}
                                    {#each chart.rainBars as bar}
                                      <rect x={bar.x} y={bar.y} width={bar.w} height={bar.h}
                                            fill="#3b82f6" opacity="0.7" rx="1" />
                                    {/each}
                                  {/if}

                                  <!-- Humidity line (solid, teal) -->
                                  {#if vis.has('humid') && chart.humidPath}
                                    <path d={chart.humidPath} fill="none"
                                          stroke="#06b6d4" stroke-width="1.5" />
                                  {/if}

                                  <!-- Wind line (dashed, purple) -->
                                  {#if vis.has('wind') && chart.windPath}
                                    <path d={chart.windPath} fill="none"
                                          stroke="#8b5cf6" stroke-width="1.5" stroke-dasharray="5,3" />
                                  {/if}

                                  <!-- Temperature line (solid, orange — on top) -->
                                  {#if vis.has('temp') && chart.tempPath}
                                    <path d={chart.tempPath} fill="none" stroke="#f97316" stroke-width="2" />
                                  {/if}

                                  <!-- X-axis tick marks and labels -->
                                  {#each chart.xLabels as lbl}
                                    <line x1={lbl.x} y1={chart.rainTopY - 4}
                                          x2={lbl.x} y2={chart.rainTopY + 2}
                                          stroke="#9ca3af" stroke-width="0.8" />
                                    <text x={lbl.x} y={chart.svgH - 1}
                                          font-size="8" fill="#9ca3af" text-anchor="middle">{lbl.label}</text>
                                  {/each}

                                  <!-- Y-axis scale: temperature (left, top and bottom) -->
                                  <text x={chart.x0 - 2} y={chart.lineBotY - 72 + 8}
                                        font-size="7" fill="#f97316" text-anchor="end">{chart.tempHi}°C</text>
                                  <text x={chart.x0 - 2} y={chart.lineBotY}
                                        font-size="7" fill="#f97316" text-anchor="end">{chart.tempLo}°C</text>

                                  <!-- Y-axis scale: rain max (left, rain zone) -->
                                  <text x={chart.x0 - 2} y={chart.rainBotY}
                                        font-size="7" fill="#3b82f6" text-anchor="end">{chart.precipMax.toFixed(1)}mm</text>

                                  <!-- Crosshair + tooltip (rendered before overlay so overlay is topmost for events) -->
                                  {#if _activeIdx !== null}
                                    {@const pt = chart.points[_activeIdx]}
                                    {@const TIP_W = 110}
                                    {@const TIP_H = _isPinned ? 76 : 64}
                                    {@const tipX = pt.x + 8 + TIP_W > 716 ? pt.x - TIP_W - 8 : pt.x + 8}
                                    <g pointer-events="none">
                                      <!-- Vertical crosshair -->
                                      <line x1={pt.x} y1={chart.lineBotY - 72} x2={pt.x} y2={chart.rainBotY}
                                            stroke="#6b7280" stroke-width="0.8" stroke-dasharray="2,2" />
                                      <!-- Dot markers on visible lines -->
                                      {#if vis.has('temp') && pt.yT !== null}
                                        <circle cx={pt.x} cy={pt.yT} r="2.5" fill="#f97316" stroke="white" stroke-width="0.8" />
                                      {/if}
                                      {#if vis.has('humid') && pt.yHu !== null}
                                        <circle cx={pt.x} cy={pt.yHu} r="2.5" fill="#06b6d4" stroke="white" stroke-width="0.8" />
                                      {/if}
                                      {#if vis.has('wind') && pt.yW !== null}
                                        <circle cx={pt.x} cy={pt.yW} r="2.5" fill="#8b5cf6" stroke="white" stroke-width="0.8" />
                                      {/if}
                                      <!-- Tooltip box -->
                                      <g transform="translate({tipX}, 4)">
                                        <rect width={TIP_W} height={TIP_H} rx="3"
                                              fill="white"
                                              stroke={_isPinned ? '#1f2937' : '#d1d5db'}
                                              stroke-width={_isPinned ? 1.2 : 0.7} />
                                        <text x="5" y="12" font-size="7.5" fill="#374151" font-weight="bold">{pt.timeLabel}</text>
                                        <text x="5" y="24" font-size="7.5" fill="#f97316">{pt.t  !== null ? pt.t.toFixed(1)  + ' °C'  : '—'}</text>
                                        <text x="5" y="36" font-size="7.5" fill="#06b6d4">{pt.hu !== null ? pt.hu.toFixed(0) + ' %'   : '—'}</text>
                                        <text x="5" y="48" font-size="7.5" fill="#8b5cf6">{pt.w  !== null ? pt.w.toFixed(1)  + ' m/s' : '—'}</text>
                                        <text x="5" y="60" font-size="7.5" fill="#3b82f6">{pt.p.toFixed(1)} mm</text>
                                        {#if _isPinned}
                                          <line x1="4" y1="65" x2={TIP_W - 4} y2="65" stroke="#e5e7eb" stroke-width="0.5" />
                                          <text x={TIP_W / 2} y="73" font-size="6.5" fill="#9ca3af" text-anchor="middle">click chart to close</text>
                                        {/if}
                                      </g>
                                    </g>
                                  {/if}

                                  <!-- Transparent overlay — last child so it's topmost for event capture -->
                                  <rect x={chart.x0} y={0} width={694} height={chart.svgH}
                                        fill="none" pointer-events="all" style="cursor: crosshair"
                                        on:mousemove={(e) => chartMouseMove(e, area.id, chart)}
                                        on:mouseleave={() => chartMouseLeave(area.id)}
                                        on:click={(e) => chartClick(e, area.id, chart)} />
                                </svg>
                              {/if}
                            </div>
                          {:else}
                            <p class="no-chart">No weather history available for this area yet.</p>
                          {/if}

                          <!-- Why this score -->
                          <div class="detail-section">
                            <div class="detail-label">Current conditions</div>
                            <p class="why-text">{why}</p>
                          </div>

                          <!-- Assumptions & physical characteristics -->
                          {#if items.length > 0}
                            <div class="detail-section">
                              <div class="detail-label">Assumptions &amp; characteristics</div>
                              <ul class="considerations">
                                {#each items as item}
                                  <li>{item}</li>
                                {/each}
                              </ul>
                            </div>
                          {/if}

                          <!-- Report counts -->
                          <div class="detail-section">
                            <div class="detail-label">Reports received</div>
                            <div class="report-counts">
                              <div class="count-pill" class:has-reports={area.report_count_4h > 0}>
                                <span class="count-val">{area.report_count_4h}</span>
                                <span class="count-lbl">last 4h</span>
                              </div>
                              <div class="count-pill" class:has-reports={area.report_count_12h > 0}>
                                <span class="count-val">{area.report_count_12h}</span>
                                <span class="count-lbl">last 12h</span>
                              </div>
                              <div class="count-pill" class:has-reports={area.report_count_24h > 0}>
                                <span class="count-val">{area.report_count_24h}</span>
                                <span class="count-lbl">last 24h</span>
                              </div>
                            </div>
                          </div>

                        </div>
                      {/if}
                    </div>
                  {/each}
                </div>
              {/if}
            </div>
          {/each}
        </div>
      {/if}

    <!-- ═══════════════════════ TAB 2: REPORT STATUS ═════════════════════════ -->
    {:else}
      <div class="reports-header">
        <span class="reports-meta">
          {#if reportsGeneratedAt}Updated {timeAgo(reportsGeneratedAt)}{/if}
        </span>
        <button class="refresh-btn" on:click={loadReports} disabled={loadingReports}>
          {loadingReports ? 'Refreshing…' : '↻ Refresh'}
        </button>
      </div>

      {#if errorReports}
        <div class="state error">{errorReports}</div>
      {:else if !loadingReports && reports.length === 0}
        <div class="state">No reports in the last 48 hours.</div>
      {:else}
        <div class="reports-list">
          <div class="report-row header-row">
            <span class="col-time">Time</span>
            <span class="col-area">Area</span>
            <span class="col-target">Boulder / Level</span>
            <span class="col-condition">Condition</span>
            <span class="col-notes">Notes</span>
          </div>
          {#each reports as r}
            {@const cColor = CONDITION_COLOR[r.condition] ?? '#6b7280'}
            {@const cLabel = CONDITION_LABEL[r.condition] ?? r.condition}
            <div class="report-row">
              <span class="col-time" title={fmtTime(r.reported_at)}>{timeAgo(r.reported_at)}</span>
              <span class="col-area">{r.area_name}</span>
              <span class="col-target">
                {#if r.boulder_name}
                  <span class="boulder-tag">{r.boulder_name}</span>
                {:else}
                  <span class="level-tag">area report</span>
                {/if}
              </span>
              <span class="col-condition">
                <span class="condition-badge"
                  style="background:{cColor}20; color:{cColor}; border:1px solid {cColor}"
                >{cLabel}</span>
              </span>
              <span class="col-notes">{r.notes ?? ''}</span>
            </div>
          {/each}
        </div>
      {/if}
    {/if}

  </main>
</div>

<style>
  :global(html), :global(body) { overflow: auto !important; height: auto !important; }

  .page { min-height: 100vh; background: #f0f4f8; }

  /* ── Header ──────────────────────────────────────────────────────────────── */
  .header {
    display: flex; align-items: center; gap: 12px;
    padding: 0 20px; height: 48px;
    background: #111827; color: #fff;
    position: sticky; top: 0; z-index: 10;
  }
  .logo { font-size: 20px; font-weight: 900; letter-spacing: -0.03em; text-decoration: none; }
  .logo-sec  { color: #a6d96a; }
  .logo-bleau { color: #fff; }
  .tagline { font-size: 13px; color: #9ca3af; flex: 1; }
  .nav-link { color: #9ca3af; font-size: 12px; text-decoration: none; }
  .nav-link:hover { color: #fff; }
  .spacer { flex: 1; }

  /* ── Tabs ────────────────────────────────────────────────────────────────── */
  .tab-bar {
    display: flex; background: #fff;
    border-bottom: 1px solid #e5e7eb; padding: 0 20px;
    position: sticky; top: 48px; z-index: 9;
  }
  .tab-btn {
    padding: 12px 20px; font-size: 13px; font-weight: 600;
    border: none; background: none; cursor: pointer; color: #6b7280;
    border-bottom: 2px solid transparent; margin-bottom: -1px;
    transition: color 0.15s, border-color 0.15s;
  }
  .tab-btn:hover { color: #111; }
  .tab-btn.active { color: #111; border-bottom-color: #a6d96a; }

  /* ── Content ─────────────────────────────────────────────────────────────── */
  .content { max-width: 1000px; margin: 0 auto; padding: 20px 16px 60px; }
  .state { text-align: center; padding: 60px; color: #6b7280; font-size: 15px; }
  .state.error { color: #dc2626; }

  /* ── Cluster folder ──────────────────────────────────────────────────────── */
  .cluster-list { display: flex; flex-direction: column; gap: 10px; }

  .cluster-folder {
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1);
  }

  .cluster-header {
    display: flex; align-items: center; gap: 10px;
    width: 100%; padding: 13px 16px;
    background: #1f2937; color: #fff;
    border: none; cursor: pointer; text-align: left;
    transition: background 0.15s;
  }
  .cluster-header:hover { background: #374151; }

  .chevron {
    font-size: 10px; color: #9ca3af; flex-shrink: 0;
    transition: transform 0.2s; display: inline-block;
  }
  .chevron.open { transform: rotate(90deg); }
  .chevron.small { font-size: 9px; color: #9ca3af; }

  .cluster-name { font-size: 14px; font-weight: 700; color: #fff; flex: 1; }
  .cluster-meta { font-size: 11px; color: #6b7280; flex-shrink: 0; }

  .cluster-score-bar {
    width: 70px; height: 6px; background: #374151; border-radius: 3px;
    position: relative; overflow: visible; flex-shrink: 0;
  }
  .cluster-score-fill { height: 100%; border-radius: 3px; min-width: 2px; }
  .cluster-threshold {
    position: absolute; left: 70%; top: -3px;
    width: 2px; height: 12px; background: #9ca3af; border-radius: 1px;
  }
  .cluster-score-pct {
    font-size: 12px; font-weight: 700; width: 32px; text-align: right;
    font-variant-numeric: tabular-nums; flex-shrink: 0;
  }

  /* ── Area list ───────────────────────────────────────────────────────────── */
  .area-list { background: #fff; }

  .area-item { border-bottom: 1px solid #f3f4f6; }
  .area-item:last-child { border-bottom: none; }

  .area-row {
    display: flex; align-items: center; gap: 10px;
    width: 100%; padding: 9px 16px 9px 28px;
    background: #fff; border: none; cursor: pointer; text-align: left;
    transition: background 0.1s;
  }
  .area-row:hover { background: #f9fafb; }

  .area-name { font-size: 13px; font-weight: 600; color: #111; flex: 1; text-align: left; }

  .score-bar-track {
    width: 90px; height: 8px; background: #f3f4f6; border-radius: 4px;
    position: relative; overflow: visible; flex-shrink: 0;
  }
  .score-bar-fill { height: 100%; border-radius: 4px; min-width: 2px; }
  .score-threshold {
    position: absolute; left: 70%; top: -3px;
    width: 2px; height: 14px; background: #9ca3af; opacity: 0.5; border-radius: 1px;
  }
  .score-pct {
    font-size: 12px; font-weight: 700; width: 30px; text-align: right;
    font-variant-numeric: tabular-nums; flex-shrink: 0;
  }
  .badge {
    font-size: 10px; font-weight: 700; border-radius: 10px;
    padding: 2px 7px; white-space: nowrap; border: 1px solid; flex-shrink: 0;
  }

  /* ── Area detail (expanded) ──────────────────────────────────────────────── */
  .area-detail {
    padding: 14px 18px 16px 28px;
    background: #f8fafc;
    border-top: 1px solid #e5e7eb;
  }

  /* ── Weather chart ───────────────────────────────────────────────────────── */
  .chart-wrap {
    background: #fff; border-radius: 8px; padding: 10px 12px;
    margin-bottom: 14px; border: 1px solid #e5e7eb;
  }
  .chart-legend {
    display: flex; gap: 6px; margin-bottom: 6px; flex-wrap: wrap;
  }
  .legend-item {
    font-size: 10px; font-weight: 600;
    background: none; border: 1px solid transparent; border-radius: 4px;
    padding: 2px 7px; cursor: pointer;
    transition: opacity 0.15s;
  }
  .legend-item:hover { border-color: currentColor; }
  .legend-item.dim   { opacity: 0.3; }
  .legend-item.temp  { color: #f97316; }
  .legend-item.humid { color: #06b6d4; }
  .legend-item.wind  { color: #8b5cf6; }
  .legend-item.rain  { color: #3b82f6; }

  .weather-svg { width: 100%; display: block; }

  .no-chart { font-size: 12px; color: #9ca3af; font-style: italic; margin-bottom: 12px; }

  /* ── Detail sections ─────────────────────────────────────────────────────── */
  .detail-section { margin-bottom: 12px; }
  .detail-label {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.06em; color: #6b7280; margin-bottom: 6px;
  }
  .why-text { font-size: 12px; color: #374151; line-height: 1.5; }

  .considerations { list-style: none; display: flex; flex-direction: column; gap: 4px; }
  .considerations li {
    font-size: 12px; color: #374151; padding-left: 14px;
    position: relative; line-height: 1.45;
  }
  .considerations li::before { content: '•'; position: absolute; left: 0; color: #9ca3af; }

  /* ── Report count pills ──────────────────────────────────────────────────── */
  .report-counts { display: flex; gap: 8px; }
  .count-pill {
    flex: 1; background: #f3f4f6; border-radius: 8px; padding: 6px 4px;
    display: flex; flex-direction: column; align-items: center; gap: 2px;
  }
  .count-pill.has-reports { background: #ecfdf5; }
  .count-val { font-size: 16px; font-weight: 800; color: #111; font-variant-numeric: tabular-nums; }
  .count-pill.has-reports .count-val { color: #059669; }
  .count-lbl { font-size: 9px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.05em; }

  /* ── Report status tab ───────────────────────────────────────────────────── */
  .reports-header {
    display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px;
  }
  .reports-meta { font-size: 12px; color: #9ca3af; }
  .refresh-btn {
    font-size: 12px; font-weight: 600; padding: 5px 12px; border-radius: 6px;
    border: 1px solid #d1d5db; background: #fff; color: #374151; cursor: pointer;
  }
  .refresh-btn:hover:not(:disabled) { background: #f3f4f6; }
  .refresh-btn:disabled { opacity: 0.5; cursor: default; }

  .reports-list {
    background: #fff; border-radius: 12px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.07); overflow: hidden;
  }
  .report-row {
    display: grid; grid-template-columns: 70px 1fr 130px 90px 1fr;
    gap: 8px; align-items: center; padding: 10px 16px;
    border-bottom: 1px solid #f3f4f6; font-size: 12px; color: #374151;
  }
  .report-row:last-child { border-bottom: none; }
  .header-row {
    background: #f8fafc; font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.06em; color: #6b7280;
    padding-top: 8px; padding-bottom: 8px;
  }
  .col-time  { color: #9ca3af; white-space: nowrap; }
  .col-area  { font-weight: 600; color: #111; }
  .col-notes { color: #6b7280; font-style: italic; }
  .boulder-tag {
    background: #eff6ff; color: #1d4ed8; border-radius: 4px;
    padding: 1px 6px; font-size: 11px; font-weight: 600;
  }
  .level-tag { color: #9ca3af; font-size: 11px; }
  .condition-badge {
    font-size: 10px; font-weight: 700; border-radius: 10px;
    padding: 2px 8px; white-space: nowrap; display: inline-block;
  }

  @media (max-width: 600px) {
    .area-row { padding-left: 20px; }
    .score-bar-track { width: 60px; }
    .report-row { grid-template-columns: 60px 1fr 80px; grid-template-rows: auto auto; }
    .col-target { display: none; }
    .col-notes  { grid-column: 1 / -1; }
  }
</style>
