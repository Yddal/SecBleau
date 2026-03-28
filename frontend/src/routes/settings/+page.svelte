<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type AreaSetting, type ClusterSettings } from '$lib/api/client';
  import { scoreToColor } from '$lib/dryness';

  // ── State ──────────────────────────────────────────────────────────────────
  let clusters: ClusterSettings[] = [];
  let loading = true;
  let loadError: string | null = null;

  // Per-area edit state: holds only the fields that have been modified
  let edits = new Map<number, Partial<AreaSetting>>();
  let saving = new Set<number>();
  let saved  = new Set<number>();
  let rowErrors = new Map<number, string>();

  let recalcStatus: 'idle' | 'running' | 'done' | 'error' = 'idle';
  let recalcMessage = '';

  onMount(async () => {
    try {
      const data = await api.getSettings();
      clusters = data.clusters ?? [];
    } catch (e: unknown) {
      loadError = e instanceof Error ? e.message : 'Failed to load settings';
    } finally {
      loading = false;
    }
  });

  // ── Helpers ────────────────────────────────────────────────────────────────
  const ASPECTS = ['N','NE','E','SE','S','SW','W','NW','flat'] as const;

  // Solar multiplier for display hint
  const ASPECT_SOLAR: Record<string, number> = {
    N: 0.15, NE: 0.35, E: 0.65, SE: 0.85, S: 1.0,
    SW: 0.85, W: 0.65, NW: 0.35, flat: 0.6,
  };

  // Generic getter — returns the edited value if one exists, otherwise the stored value.
  // The K extends keyof AreaSetting signature lets TypeScript infer the correct return type
  // for each specific field, so no `as` casts are needed at the call sites.
  function getField<K extends keyof AreaSetting>(area: AreaSetting, field: K): AreaSetting[K] {
    const e = edits.get(area.id);
    if (e && field in e) return e[field] as AreaSetting[K];
    return area[field];
  }

  function isDirty(areaId: number): boolean {
    return (edits.get(areaId) ?? null) !== null && Object.keys(edits.get(areaId)!).length > 0;
  }

  function setEdit(area: AreaSetting, field: keyof AreaSetting, value: unknown) {
    const existing = edits.get(area.id) ?? {};
    edits = new Map(edits).set(area.id, { ...existing, [field]: value });
    // Clear saved/error states when user edits again
    saved = new Set([...saved].filter(id => id !== area.id));
    rowErrors = new Map([...rowErrors].filter(([id]) => id !== area.id));
  }

  async function saveRow(area: AreaSetting) {
    const patch = edits.get(area.id);
    if (!patch || Object.keys(patch).length === 0) return;

    saving = new Set(saving).add(area.id);
    rowErrors = new Map([...rowErrors].filter(([id]) => id !== area.id));

    try {
      const updated = await api.saveAreaSettings(area.id, patch);
      // Apply returned values back to the source row so further edits diff correctly
      Object.assign(area, updated);
      edits = new Map([...edits].filter(([id]) => id !== area.id));
      saved = new Set(saved).add(area.id);
      // Auto-clear the "saved" tick after 3 s
      setTimeout(() => { saved = new Set([...saved].filter(id => id !== area.id)); }, 3000);
    } catch (e: unknown) {
      rowErrors = new Map(rowErrors).set(area.id, e instanceof Error ? e.message : 'Save failed');
    } finally {
      saving = new Set([...saving].filter(id => id !== area.id));
    }
  }

  async function recalculate() {
    recalcStatus = 'running';
    recalcMessage = '';
    try {
      const res = await api.recalculateScores();
      recalcStatus = 'done';
      recalcMessage = res.message;
    } catch (e: unknown) {
      recalcStatus = 'error';
      recalcMessage = e instanceof Error ? e.message : 'Failed to start recalculation';
    }
  }

  function fmt(v: number | null, decimals = 2): string {
    return v !== null ? v.toFixed(decimals) : '—';
  }

  // ── Event handlers (keep `as` casts out of template expressions) ────────────
  function onAspectChange(area: AreaSetting, e: Event) {
    setEdit(area, 'aspect', (e.currentTarget as HTMLSelectElement).value || null);
  }
  function onShadeInput(area: AreaSetting, e: Event) {
    setEdit(area, 'shade_factor', parseFloat((e.currentTarget as HTMLInputElement).value));
  }
  function onCanopyInput(area: AreaSetting, e: Event) {
    setEdit(area, 'canopy_factor', parseFloat((e.currentTarget as HTMLInputElement).value));
  }
  function onElevChange(area: AreaSetting, e: Event) {
    const v = parseInt((e.currentTarget as HTMLInputElement).value, 10);
    setEdit(area, 'elevation_m', isNaN(v) ? null : v);
  }
</script>

<svelte:head>
  <title>SecBleau — Sector Settings</title>
</svelte:head>

<div class="page">
  <!-- Header -->
  <header class="header">
    <a class="logo" href="/">
      <span class="logo-sec">Sec</span><span class="logo-bleau">Bleau</span>
    </a>
    <div class="tagline">Sector settings</div>
    <a class="nav-link" href="/">← Map</a>
    <a class="nav-link" href="/analysis">Analysis</a>
    <a class="nav-link" href="/conditions">Conditions</a>
    <div class="spacer"></div>
    <a class="nav-link" href="/about">About</a>
  </header>

  <main class="content">

    <!-- Top bar -->
    <div class="top-bar">
      <div class="top-info">
        <h1 class="page-title">Sector drying factors</h1>
        <p class="page-desc">
          Adjust the physical characteristics that control how fast each sector dries.
          Changes take effect on the next recalculation.
        </p>
      </div>
      <div class="top-actions">
        <button
          class="recalc-btn"
          class:running={recalcStatus === 'running'}
          disabled={recalcStatus === 'running'}
          on:click={recalculate}
        >
          {recalcStatus === 'running' ? '⟳ Recalculating…' : '↻ Recalculate scores'}
        </button>
        {#if recalcMessage}
          <span class="recalc-msg" class:error={recalcStatus === 'error'}>{recalcMessage}</span>
        {/if}
      </div>
    </div>

    <!-- Factor legend -->
    <div class="legend">
      <div class="legend-item">
        <span class="legend-key shade">Shade factor</span>
        <span class="legend-desc">Solar exposure — 0 = full shade, 1 = full sun. Higher = dries faster via solar heating.</span>
      </div>
      <div class="legend-item">
        <span class="legend-key canopy">Canopy factor</span>
        <span class="legend-desc">Tree cover density — 0 = open sky, 1 = dense canopy. Higher = dries 45% slower.</span>
      </div>
      <div class="legend-item">
        <span class="legend-key aspect">Aspect</span>
        <span class="legend-desc">Rock face direction. South-facing (100% solar) dries fastest; north-facing (15%) dries slowest.</span>
      </div>
    </div>

    {#if loading}
      <div class="state">Loading…</div>
    {:else if loadError}
      <div class="state error">{loadError}</div>
    {:else if clusters.length === 0}
      <div class="state">No sectors found — check that area_clusters.json is deployed.</div>

    {:else}

      <div class="table-wrap">
        <table class="settings-table">
          <thead>
            <tr>
              <th class="col-name">Sector</th>
              <th class="col-aspect">
                Aspect
                <span class="th-hint">direction</span>
              </th>
              <th class="col-slider">
                Shade factor
                <span class="th-hint">0 = shade · 1 = sun</span>
              </th>
              <th class="col-slider">
                Canopy factor
                <span class="th-hint">0 = open · 1 = forest</span>
              </th>
              <th class="col-elev">
                Elevation
                <span class="th-hint">metres</span>
              </th>
              <th class="col-score">Score</th>
              <th class="col-action"></th>
            </tr>
          </thead>
          <tbody>
            {#each clusters as cluster}
              <!-- Cluster header row -->
              <tr class="cluster-row">
                <td colspan="7" class="cluster-label">{cluster.name}</td>
              </tr>

              {#each cluster.areas as area}
                {@const dirty      = isDirty(area.id)}
                {@const isSaving   = saving.has(area.id)}
                {@const isSaved    = saved.has(area.id)}
                {@const rowError   = rowErrors.get(area.id) ?? null}
                {@const curAspect  = getField(area, 'aspect')}
                {@const curShade   = getField(area, 'shade_factor')}
                {@const curCanopy  = getField(area, 'canopy_factor')}
                {@const curElev    = getField(area, 'elevation_m')}
                {@const scoreVal   = area.dryness_score}
                {@const scoreColor = scoreToColor(scoreVal)}
                {@const solar      = curAspect ? ASPECT_SOLAR[curAspect] ?? null : null}

                <tr class="area-row" class:dirty class:saving={isSaving}>
                  <!-- Name -->
                  <td class="col-name area-name">{area.name}</td>

                  <!-- Aspect -->
                  <td class="col-aspect">
                    <select
                      class="aspect-select"
                      class:changed={curAspect !== area.aspect}
                      value={curAspect ?? ''}
                      on:change={(e) => onAspectChange(area, e)}
                    >
                      <option value="">—</option>
                      {#each ASPECTS as asp}
                        <option value={asp}>{asp}</option>
                      {/each}
                    </select>
                    {#if solar !== null}
                      <span class="solar-hint">{Math.round(solar * 100)}% solar</span>
                    {/if}
                  </td>

                  <!-- Shade factor -->
                  <td class="col-slider">
                    <div class="slider-cell">
                      <input
                        type="range" min="0" max="1" step="0.05"
                        class="factor-slider shade-slider"
                        class:changed={curShade !== area.shade_factor}
                        value={curShade ?? 0.5}
                        on:input={(e) => onShadeInput(area, e)}
                      />
                      <span class="factor-val" class:changed={curShade !== area.shade_factor}>
                        {fmt(curShade)}
                      </span>
                    </div>
                  </td>

                  <!-- Canopy factor -->
                  <td class="col-slider">
                    <div class="slider-cell">
                      <input
                        type="range" min="0" max="1" step="0.05"
                        class="factor-slider canopy-slider"
                        class:changed={curCanopy !== area.canopy_factor}
                        value={curCanopy ?? 0.5}
                        on:input={(e) => onCanopyInput(area, e)}
                      />
                      <span class="factor-val" class:changed={curCanopy !== area.canopy_factor}>
                        {fmt(curCanopy)}
                      </span>
                    </div>
                  </td>

                  <!-- Elevation -->
                  <td class="col-elev">
                    <input
                      type="number" min="0" max="5000" step="1"
                      class="elev-input"
                      class:changed={curElev !== area.elevation_m}
                      value={curElev ?? ''}
                      on:change={(e) => onElevChange(area, e)}
                    />
                  </td>

                  <!-- Score -->
                  <td class="col-score">
                    {#if scoreVal !== null}
                      <div class="score-pill" style="background:{scoreColor}22; color:{scoreColor}; border-color:{scoreColor}">
                        {Math.round(scoreVal * 100)}%
                      </div>
                    {:else}
                      <span class="no-score">—</span>
                    {/if}
                  </td>

                  <!-- Save action -->
                  <td class="col-action">
                    {#if rowError}
                      <span class="row-error" title={rowError}>⚠ {rowError}</span>
                    {:else if isSaving}
                      <span class="saving-spinner">…</span>
                    {:else if isSaved}
                      <span class="saved-tick">✓ Saved</span>
                    {:else if dirty}
                      <button class="save-btn" on:click={() => saveRow(area)}>Save</button>
                    {:else}
                      <span class="no-action"></span>
                    {/if}
                  </td>
                </tr>

                {#if rowError}
                  <tr class="error-row">
                    <td colspan="7" class="error-cell">{rowError}</td>
                  </tr>
                {/if}
              {/each}
            {/each}
          </tbody>
        </table>
      </div>

    {/if}
  </main>
</div>

<style>
  :global(html), :global(body) { overflow: auto !important; height: auto !important; }

  .page { min-height: 100vh; background: #f0f4f8; }

  /* ── Header ─────────────────────────────────────────────────────────────── */
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

  /* ── Content ─────────────────────────────────────────────────────────────── */
  .content { max-width: 1200px; margin: 0 auto; padding: 24px 16px 60px; }

  .state { text-align: center; padding: 60px; color: #6b7280; font-size: 15px; }
  .state.error { color: #dc2626; }

  /* ── Top bar ────────────────────────────────────────────────────────────── */
  .top-bar {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 20px; margin-bottom: 18px; flex-wrap: wrap;
  }
  .page-title { font-size: 20px; font-weight: 800; color: #111; margin: 0 0 4px; }
  .page-desc  { font-size: 13px; color: #6b7280; margin: 0; }
  .top-actions { display: flex; align-items: center; gap: 12px; flex-shrink: 0; padding-top: 4px; }

  .recalc-btn {
    padding: 8px 16px; font-size: 13px; font-weight: 600;
    background: #1f2937; color: #fff; border: none; border-radius: 6px;
    cursor: pointer; transition: background 0.15s; white-space: nowrap;
  }
  .recalc-btn:hover:not(:disabled) { background: #374151; }
  .recalc-btn:disabled { opacity: 0.6; cursor: not-allowed; }
  .recalc-btn.running { background: #374151; }
  .recalc-msg { font-size: 12px; color: #059669; max-width: 280px; }
  .recalc-msg.error { color: #dc2626; }

  /* ── Legend ─────────────────────────────────────────────────────────────── */
  .legend {
    display: flex; gap: 20px; flex-wrap: wrap;
    background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 10px 16px; margin-bottom: 18px;
  }
  .legend-item { display: flex; align-items: baseline; gap: 6px; font-size: 12px; }
  .legend-key {
    font-weight: 700; font-size: 11px; padding: 1px 6px; border-radius: 3px;
    white-space: nowrap;
  }
  .legend-key.shade  { background: #fef3c7; color: #92400e; }
  .legend-key.canopy { background: #d1fae5; color: #065f46; }
  .legend-key.aspect { background: #ede9fe; color: #5b21b6; }
  .legend-desc { color: #6b7280; }

  /* ── Table ─────────────────────────────────────────────────────────────── */
  .table-wrap {
    background: #fff; border-radius: 10px;
    border: 1px solid #e5e7eb;
    overflow-x: auto;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07);
  }

  .settings-table {
    width: 100%; border-collapse: collapse;
    font-size: 13px;
  }

  .settings-table thead th {
    padding: 10px 12px;
    background: #f9fafb;
    border-bottom: 2px solid #e5e7eb;
    text-align: left;
    font-size: 11px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.04em; color: #6b7280;
    white-space: nowrap;
  }
  .th-hint {
    display: block; font-size: 9px; font-weight: 400;
    letter-spacing: 0; color: #9ca3af; text-transform: none; margin-top: 1px;
  }

  /* Cluster separator row */
  .cluster-row .cluster-label {
    padding: 8px 12px 5px;
    background: #1f2937; color: #e5e7eb;
    font-size: 11px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  /* Area rows */
  .area-row td {
    padding: 7px 12px;
    border-bottom: 1px solid #f3f4f6;
    vertical-align: middle;
  }
  .area-row:last-child td { border-bottom: none; }
  .area-row:hover td { background: #f9fafb; }
  .area-row.dirty td  { background: #fffbeb; }
  .area-row.saving td { opacity: 0.6; }

  .col-name   { min-width: 160px; }
  .col-aspect { width: 130px; }
  .col-slider { width: 180px; }
  .col-elev   { width: 90px; }
  .col-score  { width: 70px; text-align: center; }
  .col-action { width: 90px; text-align: right; padding-right: 16px !important; }

  .area-name { font-weight: 600; color: #111; }

  /* Aspect select */
  .aspect-select {
    font-size: 12px; padding: 3px 6px; border-radius: 4px;
    border: 1px solid #d1d5db; background: #fff;
    cursor: pointer; width: 70px;
  }
  .aspect-select.changed { border-color: #f59e0b; background: #fffbeb; }
  .solar-hint { font-size: 10px; color: #9ca3af; display: block; margin-top: 2px; }

  /* Sliders */
  .slider-cell {
    display: flex; align-items: center; gap: 8px;
  }
  .factor-slider {
    flex: 1; height: 4px; cursor: pointer;
    accent-color: #9ca3af;
  }
  .shade-slider  { accent-color: #f59e0b; }
  .canopy-slider { accent-color: #10b981; }
  .factor-slider.changed { accent-color: #f59e0b; }
  .factor-val {
    font-size: 11px; color: #6b7280; font-variant-numeric: tabular-nums;
    width: 30px; text-align: right; flex-shrink: 0;
  }
  .factor-val.changed { color: #92400e; font-weight: 700; }

  /* Elevation input */
  .elev-input {
    width: 68px; padding: 3px 6px; border-radius: 4px;
    border: 1px solid #d1d5db; font-size: 12px;
    text-align: right;
  }
  .elev-input.changed { border-color: #f59e0b; background: #fffbeb; }

  /* Score pill */
  .score-pill {
    display: inline-block; font-size: 11px; font-weight: 700;
    padding: 2px 8px; border-radius: 10px; border: 1px solid;
    font-variant-numeric: tabular-nums;
  }
  .no-score { color: #9ca3af; font-size: 12px; }

  /* Action column */
  .save-btn {
    padding: 4px 12px; font-size: 12px; font-weight: 600;
    background: #f59e0b; color: #fff; border: none; border-radius: 4px;
    cursor: pointer; transition: background 0.15s;
  }
  .save-btn:hover { background: #d97706; }

  .saving-spinner { font-size: 12px; color: #9ca3af; }
  .saved-tick     { font-size: 12px; color: #059669; font-weight: 600; }
  .no-action      { display: inline-block; width: 60px; }

  .row-error  { font-size: 11px; color: #dc2626; cursor: help; }
  .error-row .error-cell {
    padding: 4px 12px 6px 24px;
    font-size: 11px; color: #dc2626;
    background: #fef2f2;
  }
</style>
