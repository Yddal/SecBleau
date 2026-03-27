<script lang="ts">
  import Map from '$lib/components/Map.svelte';
  import AreaPopup from '$lib/components/AreaPopup.svelte';
  import BoulderPopup from '$lib/components/BoulderPopup.svelte';
  import ClusterPopup from '$lib/components/ClusterPopup.svelte';
  import DrynessLegend from '$lib/components/DrynessLegend.svelte';
  import SearchBar from '$lib/components/SearchBar.svelte';
  import type { AreaProperties, BoulderSearchResult } from '$lib/api/client';
  import { api } from '$lib/api/client';

  // Selected entity for the side panel / popup
  let selectedArea: { id: number; name: string; lat: number; lon: number; props: Record<string, unknown> } | null = null;
  let selectedBoulder: { id: number; name: string | null; grade: string | null; props: Record<string, unknown> } | null = null;
  let selectedCluster: { name: string; areas: AreaProperties[] } | null = null;

  let mapComponent: Map;
  let mapLoading = true;
  let mapError: string | null = null;

  function handleAreaClick(e: CustomEvent) {
    selectedArea = e.detail;
    selectedBoulder = null;
    selectedCluster = null;
  }

  function handleBoulderClick(e: CustomEvent) {
    selectedBoulder = e.detail;
    selectedArea = null;
    selectedCluster = null;
  }

  function handleClusterClick(e: CustomEvent) {
    selectedCluster = e.detail;
    selectedArea = null;
    selectedBoulder = null;
  }

  function handleBoulderReported(e: CustomEvent) {
    if (selectedBoulder?.props?.area_id) {
      mapComponent.invalidateBoulderCache(selectedBoulder.props.area_id as number);
    }
  }

  function handleAreaReported() {
    // Invalidate boulder cache for this area so next zoom-in gets fresh data
    if (selectedArea?.id) {
      mapComponent.invalidateBoulderCache(selectedArea.id);
    }
  }

  function handleAreaSelect(e: CustomEvent) {
    const { lon, lat } = e.detail;
    if (lon != null && lat != null) {
      selectedCluster = null;
      mapComponent.flyToArea(lon, lat);
    }
  }

  async function handleSearchSelect(e: CustomEvent<BoulderSearchResult>) {
    const r = e.detail;
    selectedArea = null;
    selectedCluster = null;
    mapComponent.flyToBoulder(r.lon, r.lat);
    // Fetch full detail so the popup has dryness score, confidence, etc.
    try {
      const detail = await api.getBoulder(r.id);
      selectedBoulder = { id: r.id, name: r.name, grade: r.grade, props: detail as unknown as Record<string, unknown> };
    } catch {
      // Fly-to still happened; popup will open when user clicks the dot
    }
  }

  function handleMapReady() {
    mapLoading = false;
  }

  function handleMapLoadError(e: CustomEvent) {
    mapLoading = false;
    mapError = e.detail.message;
  }
</script>

<div class="app">
  <!-- Header bar -->
  <header class="header">
    <div class="logo">
      <span class="logo-sec">Sec</span><span class="logo-bleau">Bleau</span>
    </div>
    <SearchBar on:select={handleSearchSelect} />
    <a class="about-link" href="/conditions">Conditions</a>
    <a class="about-link" href="/about">About</a>
    <a class="about-link" href="/privacy">Privacy</a>
  </header>

  <!-- Full-screen map -->
  <div class="map-wrap">
    <Map
      bind:this={mapComponent}
      on:areaClick={handleAreaClick}
      on:boulderClick={handleBoulderClick}
      on:clusterClick={handleClusterClick}
      on:ready={handleMapReady}
      on:loadError={handleMapLoadError}
    />

    {#if mapLoading}
      <div class="loading-overlay" aria-label="Loading map data">
        <div class="spinner"></div>
        <span>Loading conditions…</span>
      </div>
    {/if}

    {#if mapError}
      <div class="error-banner" role="alert">
        {mapError}
        <button class="error-close" on:click={() => mapError = null} aria-label="Dismiss">✕</button>
      </div>
    {/if}

    <!-- Legend — bottom left -->
    <div class="legend-wrap">
      <DrynessLegend />
    </div>

    <!-- Attribution — bottom right (above OSM credit) -->
    <div class="attribution-wrap">
      Area data © <a href="https://www.boolder.com" target="_blank" rel="noopener">Boolder</a>
      (<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0</a>)
      · Weather: <a href="https://open-meteo.com" target="_blank" rel="noopener">Open-Meteo</a>
      · <a href="/privacy">Privacy</a>
    </div>

    <!-- Area popup panel -->
    {#if selectedArea}
      <div class="popup-panel" role="dialog" aria-label="Area details">
        <AreaPopup
          props={selectedArea.props}
          on:close={() => selectedArea = null}
          on:reported={handleAreaReported}
        />
      </div>
    {/if}

    <!-- Boulder popup panel -->
    {#if selectedBoulder}
      <div class="popup-panel" role="dialog" aria-label="Boulder details">
        <BoulderPopup
          props={selectedBoulder.props}
          on:close={() => selectedBoulder = null}
          on:reported={handleBoulderReported}
        />
      </div>
    {/if}

    <!-- Cluster popup panel -->
    {#if selectedCluster}
      <div class="popup-panel" role="dialog" aria-label="Sector details">
        <ClusterPopup
          name={selectedCluster.name}
          areas={selectedCluster.areas}
          on:areaSelect={handleAreaSelect}
          on:close={() => selectedCluster = null}
        />
      </div>
    {/if}
  </div>
</div>

<style>
  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }

  .header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0 16px;
    height: 48px;
    background: #111827;
    color: #fff;
    flex-shrink: 0;
    z-index: 10;
  }
  .logo { font-size: 22px; font-weight: 900; letter-spacing: -0.03em; }
  .logo-sec { color: #a6d96a; }
  .logo-bleau { color: #ffffff; }
  .about-link { color: #9ca3af; font-size: 12px; text-decoration: none; white-space: nowrap; }
  .about-link:hover { color: #fff; }

  .map-wrap {
    position: relative;
    flex: 1;
    overflow: hidden;
  }

  .legend-wrap {
    position: absolute;
    bottom: 30px;
    left: 12px;
    z-index: 5;
    pointer-events: none;
  }

  .attribution-wrap {
    position: absolute;
    bottom: 30px;
    right: 12px;
    z-index: 5;
    font-size: 10px;
    color: #555;
    background: rgba(255,255,255,0.85);
    padding: 3px 7px;
    border-radius: 4px;
    pointer-events: auto;
  }
  .attribution-wrap a { color: #333; text-decoration: none; }
  .attribution-wrap a:hover { text-decoration: underline; }

  .popup-panel {
    position: absolute;
    top: 12px;
    right: 12px;
    z-index: 10;
    background: #fff;
    border-radius: 10px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.18);
    padding: 14px;
    max-height: calc(100vh - 80px);
    overflow-y: auto;
    max-width: 300px;
  }

  .loading-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    background: rgba(255, 255, 255, 0.55);
    z-index: 20;
    pointer-events: none;
    font-size: 13px;
    color: #374151;
    font-weight: 500;
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid #e5e7eb;
    border-top-color: #2563eb;
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .error-banner {
    position: absolute;
    top: 12px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 15;
    background: #fef2f2;
    border: 1px solid #fca5a5;
    color: #991b1b;
    font-size: 12px;
    padding: 8px 36px 8px 14px;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.12);
    white-space: nowrap;
  }

  .error-close {
    position: absolute;
    right: 8px;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    cursor: pointer;
    color: #991b1b;
    font-size: 13px;
    line-height: 1;
    padding: 2px 4px;
  }
</style>
