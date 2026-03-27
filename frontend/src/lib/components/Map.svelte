<script lang="ts">
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import maplibregl from 'maplibre-gl';
  import 'maplibre-gl/dist/maplibre-gl.css';
  import { scoreToColor, boulderOpacity } from '$lib/dryness';
  import type { AreaFeatureCollection, BoulderFeatureCollection, ClusterFeatureCollection } from '$lib/api/client';
  import { api } from '$lib/api/client';

  const dispatch = createEventDispatcher<{
    areaClick: { id: number; name: string; lat: number; lon: number; props: unknown };
    boulderClick: { id: number; name: string | null; grade: string | null; props: unknown };
    clusterClick: { name: string; areas: (import('$lib/api/client').AreaProperties & { _lon: number; _lat: number })[] };
    ready: void;
    loadError: { message: string };
  }>();

  // Fontainebleau forest bounds — restrict panning
  const FONT_BOUNDS: maplibregl.LngLatBoundsLike = [[2.1, 48.0], [3.1, 48.7]];

  // Zoom thresholds
  const CLUSTER_MAX_ZOOM = 13;    // below this: show cluster sectors
  const BOULDER_MIN_ZOOM = 15;    // above this: show individual boulders

  let mapContainer: HTMLDivElement;
  let map: maplibregl.Map;

  // All loaded areas — used for viewport intersection without querySourceFeatures
  let loadedAreas: AreaFeatureCollection | null = null;

  // Boulder cache: area_id → GeoJSON collection (capped at MAX_CACHE_AREAS to prevent memory growth)
  const MAX_CACHE_AREAS = 25;
  const boulderCache = new Map<number, BoulderFeatureCollection>();
  const boulderCacheOrder: number[] = []; // insertion-order for eviction

  function setCachedBoulders(areaId: number, data: BoulderFeatureCollection) {
    if (!boulderCache.has(areaId)) {
      if (boulderCacheOrder.length >= MAX_CACHE_AREAS) {
        const evict = boulderCacheOrder.shift()!;
        boulderCache.delete(evict);
      }
      boulderCacheOrder.push(areaId);
    }
    boulderCache.set(areaId, data);
  }

  // Zoom tracking for hint overlay
  let currentZoom: number = 12;

  // Debounce timer for boulder load on pan/zoom
  let _boulderLoadTimer: ReturnType<typeof setTimeout> | null = null;
  function scheduleBoulderLoad() {
    if (_boulderLoadTimer) clearTimeout(_boulderLoadTimer);
    _boulderLoadTimer = setTimeout(() => loadVisibleBoulders(), 300);
  }

  onMount(async () => {
    map = new maplibregl.Map({
      container: mapContainer,
      style: 'https://tiles.openfreemap.org/styles/bright',
      center: [2.70, 48.42],
      zoom: 12,
      minZoom: 9,
      maxZoom: 19,
      maxBounds: FONT_BOUNDS,
    });

    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.GeolocateControl({
      positionOptions: { enableHighAccuracy: true },
      trackUserLocation: true,
    }), 'top-right');

    map.on('load', async () => {
      currentZoom = map.getZoom();
      await initSources();
      await loadClusters();
      await loadAreas();
      setupBoulderLayer();
      setupZoomSwitching();
      applyZoomVisibility(currentZoom);
      // Load data for any layers already visible at the initial zoom
      if (currentZoom >= BOULDER_MIN_ZOOM) await loadVisibleBoulders();
      dispatch('ready');
    });
  });

  onDestroy(() => {
    if (_boulderLoadTimer) clearTimeout(_boulderLoadTimer);
    map?.remove();
  });

  // ── Sources & layers initialisation ──────────────────────────────────────

  async function initSources() {
    // Cluster source (major sectors)
    map.addSource('clusters', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });

    // Cluster fill polygons (bounding box rectangles)
    map.addSource('cluster-polys', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });

    // Area source
    map.addSource('areas', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });

    // Area bounding box polygons
    map.addSource('area-polys', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });

    // Boulders
    map.addSource('boulders', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });


    // ── Cluster layers ──────────────────────────────────────────────────────

    map.addLayer({
      id: 'cluster-fill',
      type: 'fill',
      source: 'cluster-polys',
      paint: {
        'fill-color': ['get', '_color'],
        'fill-opacity': 0.18,
      },
    });

    map.addLayer({
      id: 'cluster-outline',
      type: 'line',
      source: 'cluster-polys',
      paint: {
        'line-color': ['get', '_color'],
        'line-width': 2,
        'line-opacity': 0.6,
      },
    });

    map.addLayer({
      id: 'cluster-labels',
      type: 'symbol',
      source: 'clusters',
      layout: {
        'text-field': ['get', 'name'],
        'text-size': 16,
        'text-font': ['Noto Sans Bold'],
        'text-anchor': 'center',
        'text-max-width': 12,
        'text-letter-spacing': 0.05,
        visibility: 'visible',
      },
      paint: {
        'text-color': '#111111',
        'text-halo-color': 'rgba(255,255,255,0.95)',
        'text-halo-width': 3,
        'text-halo-blur': 0,
      },
    });

    // ── Area layers ─────────────────────────────────────────────────────────

    map.addLayer({
      id: 'area-fill',
      type: 'fill',
      source: 'area-polys',
      paint: {
        'fill-color': ['get', '_color'],
        'fill-opacity': 0.22,
      },
    });

    map.addLayer({
      id: 'area-outline',
      type: 'line',
      source: 'area-polys',
      paint: {
        'line-color': ['get', '_color'],
        'line-width': 2,
        'line-opacity': 0.75,
      },
    });

    map.addLayer({
      id: 'area-labels',
      type: 'symbol',
      source: 'areas',
      layout: {
        'text-field': ['get', 'name'],
        'text-size': 13,
        'text-font': ['Noto Sans Bold'],
        'text-anchor': 'center',
        'text-max-width': 10,
        'text-offset': [0, 0],
        'text-allow-overlap': false,
        'text-ignore-placement': false,
        visibility: 'none',
      },
      paint: {
        'text-color': '#1a1a1a',
        'text-halo-color': '#ffffff',
        'text-halo-width': 3,
        'text-halo-blur': 0,
      },
    });

    // ── Boulder layer ───────────────────────────────────────────────────────

    map.addLayer({
      id: 'boulder-circles',
      type: 'circle',
      source: 'boulders',
      layout: { visibility: 'none' },
      paint: {
        'circle-color': ['get', '_color'],
        'circle-radius': 6,
        'circle-opacity': ['get', '_opacity'],
        'circle-stroke-width': 1.5,
        'circle-stroke-color': '#ffffff',
        'circle-stroke-opacity': ['get', '_opacity'],
      },
    });
  }

  // ── Data loading ──────────────────────────────────────────────────────────

  async function loadClusters() {
    try {
      const data = await api.getClusters();

      // Point features for labels
      (map.getSource('clusters') as maplibregl.GeoJSONSource).setData({
        type: 'FeatureCollection',
        features: data.features.map((f) => ({
          ...f,
          properties: {
            ...f.properties,
            _color: scoreToColor(f.properties.dryness_score),
          },
        })),
      });

      // Polygon features for fill/outline — use hull blob if available, fall back to bbox
      const polyFeatures = data.features
        .map((f) => {
          const p = f.properties;
          const swLon = parseFloat(String(p.southWestLon));
          const swLat = parseFloat(String(p.southWestLat));
          const neLon = parseFloat(String(p.northEastLon));
          const neLat = parseFloat(String(p.northEastLat));
          if (isNaN(swLon) || isNaN(swLat) || isNaN(neLon) || isNaN(neLat)) return null;
          const sharedProps = { _color: scoreToColor(p.dryness_score), name: p.name, sw_lon: swLon, sw_lat: swLat, ne_lon: neLon, ne_lat: neLat };

          const hull = p.hull as { type: string; coordinates: unknown } | null | undefined;
          if (hull && hull.coordinates) {
            return { type: 'Feature' as const, geometry: hull as any, properties: sharedProps };
          }

          return {
            type: 'Feature' as const,
            geometry: {
              type: 'Polygon' as const,
              coordinates: [[
                [swLon, swLat],
                [neLon, swLat],
                [neLon, neLat],
                [swLon, neLat],
                [swLon, swLat],
              ]],
            },
            properties: sharedProps,
          };
        })
        .filter(Boolean);

      (map.getSource('cluster-polys') as maplibregl.GeoJSONSource).setData({
        type: 'FeatureCollection',
        features: polyFeatures as any,
      });

    } catch (e) {
      console.warn('Could not load clusters:', e);
      dispatch('loadError', { message: 'Could not load sector data. Check your connection.' });
    }
  }

  async function loadAreas() {
    try {
      const data = await api.getAreas();
      loadedAreas = data;

      (map.getSource('areas') as maplibregl.GeoJSONSource).setData({
        type: 'FeatureCollection',
        features: data.features.map((f) => ({
          ...f,
          properties: {
            ...f.properties,
            _color: scoreToColor(f.properties.dryness_score),
          },
        })),
      });

      // Build polygon features: use PostGIS hull if present, fall back to bbox rectangle
      const polyFeatures = data.features
        .map((f) => {
          const p = f.properties;
          const color = scoreToColor(p.dryness_score);
          const props = { id: p.id, name: p.name, _color: color };

          // Prefer the hull polygon computed from actual boulder positions
          if (p.hull && (p.hull as any).coordinates) {
            return { type: 'Feature' as const, geometry: p.hull as any, properties: props };
          }

          // Fallback: bounding box rectangle
          const { bbox_sw_lon: swLon, bbox_sw_lat: swLat, bbox_ne_lon: neLon, bbox_ne_lat: neLat } = p;
          if (swLon == null || swLat == null || neLon == null || neLat == null) return null;
          return {
            type: 'Feature' as const,
            geometry: {
              type: 'Polygon' as const,
              coordinates: [[[swLon, swLat], [neLon, swLat], [neLon, neLat], [swLon, neLat], [swLon, swLat]]],
            },
            properties: props,
          };
        })
        .filter(Boolean);

      (map.getSource('area-polys') as maplibregl.GeoJSONSource).setData({
        type: 'FeatureCollection',
        features: polyFeatures as any,
      });
    } catch (e) {
      console.warn('Could not load areas:', e);
      dispatch('loadError', { message: 'Could not load area data. Check your connection.' });
    }
  }

  function setupBoulderLayer() {
    map.on('click', 'boulder-circles', (e) => {
      if (!e.features?.length) return;
      const props = e.features[0].properties;
      dispatch('boulderClick', { id: props.id, name: props.name, grade: props.grade, props });
    });
    map.on('mouseenter', 'boulder-circles', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'boulder-circles', () => { map.getCanvas().style.cursor = ''; });

    // Click on cluster sector polygon
    map.on('click', 'cluster-fill', (e) => {
      if (!e.features?.length || !loadedAreas) return;
      const props = e.features[0].properties;
      const geom = e.features[0].geometry as { type: string; coordinates: number[][][] | number[][][][] };

      const areasInCluster = loadedAreas.features
        .filter((f) => {
          const [lon, lat] = f.geometry.coordinates as [number, number];
          return pointInPolygon(lon, lat, geom);
        })
        .map((f) => ({
          ...f.properties,
          _lon: f.geometry.coordinates[0] as number,
          _lat: f.geometry.coordinates[1] as number,
        }))
        .sort((a, b) => (b.dryness_score ?? -1) - (a.dryness_score ?? -1));

      dispatch('clusterClick', { name: props.name, areas: areasInCluster });
    });
    map.on('mouseenter', 'cluster-fill', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'cluster-fill', () => { map.getCanvas().style.cursor = ''; });

    // Click on area bbox polygon
    map.on('click', 'area-fill', (e) => {
      if (!e.features?.length) return;
      const props = e.features[0].properties;
      dispatch('areaClick', {
        id: props.id,
        name: props.name,
        lat: e.lngLat.lat,
        lon: e.lngLat.lng,
        props,
      });
    });
    map.on('mouseenter', 'area-fill', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'area-fill', () => { map.getCanvas().style.cursor = ''; });
  }

  function setupZoomSwitching() {
    map.on('zoom', () => {
      currentZoom = map.getZoom();
      applyZoomVisibility(currentZoom);
    });
    map.on('moveend', () => {
      if (map.getZoom() >= BOULDER_MIN_ZOOM) scheduleBoulderLoad();
    });
    map.on('zoomend', () => {
      if (map.getZoom() >= BOULDER_MIN_ZOOM) scheduleBoulderLoad();
    });
  }

  function applyZoomVisibility(zoom: number) {
    if (!map.isStyleLoaded()) return;
    const showClusters = zoom < CLUSTER_MAX_ZOOM;
    const showAreas = zoom >= CLUSTER_MAX_ZOOM;   // areas shown at both area zoom AND boulder zoom
    const showBoulders = zoom >= BOULDER_MIN_ZOOM;

    const set = (layer: string, vis: boolean) => {
      if (map.getLayer(layer)) {
        map.setLayoutProperty(layer, 'visibility', vis ? 'visible' : 'none');
      }
    };

    set('cluster-fill', showClusters);
    set('cluster-outline', showClusters);
    // Cluster names: visible at cluster + area zoom, hidden at boulder zoom (too cluttered)
    set('cluster-labels', showClusters || (showAreas && !showBoulders));

    // Area polygons: only between cluster zoom and boulder zoom
    const showAreaPolys = showAreas && !showBoulders;
    set('area-fill', showAreaPolys);
    set('area-outline', showAreaPolys);
    // Area names: visible at area zoom and boulder zoom
    set('area-labels', showAreas);

    set('boulder-circles', showBoulders);
  }

  async function loadVisibleBoulders() {
    if (!loadedAreas) return;

    const bounds = map.getBounds();
    const vpW = bounds.getWest(), vpE = bounds.getEast();
    const vpS = bounds.getSouth(), vpN = bounds.getNorth();

    // An area is "visible" if its bbox (or center point) intersects the viewport
    const areaIds = new Set<number>(
      loadedAreas.features
        .filter((f) => {
          const p = f.properties;
          // Use bbox intersection if available
          if (p.bbox_sw_lon != null && p.bbox_ne_lon != null) {
            return !(p.bbox_ne_lon < vpW || p.bbox_sw_lon > vpE ||
                     p.bbox_ne_lat < vpS || p.bbox_sw_lat > vpN);
          }
          // Fall back to center point
          const [lon, lat] = f.geometry.coordinates;
          return lon >= vpW && lon <= vpE && lat >= vpS && lat <= vpN;
        })
        .map((f) => f.properties.id)
    );

    if (areaIds.size === 0) return;

    const allFeatures: BoulderFeatureCollection['features'] = [];
    for (const areaId of areaIds) {
      let data = boulderCache.get(areaId);
      if (!data) {
        try {
          data = await api.getAreaBoulders(areaId);
          setCachedBoulders(areaId, data);
        } catch {
          continue;
        }
      }
      allFeatures.push(...data.features);
    }

    const colored = allFeatures.map((f) => ({
      ...f,
      properties: {
        ...f.properties,
        _color: scoreToColor(f.properties.dryness_score),
        _opacity: boulderOpacity(f.properties.has_recent_reports, f.properties.is_estimated),
      },
    }));

    (map.getSource('boulders') as maplibregl.GeoJSONSource).setData({
      type: 'FeatureCollection',
      features: colored,
    });
  }

  // Ray-casting point-in-polygon (works for convex and concave polygons)
  function pointInRing(lon: number, lat: number, ring: number[][]): boolean {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i];
      const [xj, yj] = ring[j];
      if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) {
        inside = !inside;
      }
    }
    return inside;
  }

  function pointInPolygon(lon: number, lat: number, geom: { type: string; coordinates: number[][][] | number[][][][] }): boolean {
    if (geom.type === 'Polygon') {
      return pointInRing(lon, lat, (geom.coordinates as number[][][])[0]);
    }
    if (geom.type === 'MultiPolygon') {
      return (geom.coordinates as number[][][][]).some((poly) => pointInRing(lon, lat, poly[0]));
    }
    return false;
  }

  export function invalidateBoulderCache(areaId: number) {
    boulderCache.delete(areaId);
    const idx = boulderCacheOrder.indexOf(areaId);
    if (idx !== -1) boulderCacheOrder.splice(idx, 1);
  }

  export function flyToArea(lon: number, lat: number) {
    map?.flyTo({ center: [lon, lat], zoom: 14, speed: 1.4 });
  }

  export function flyToBoulder(lon: number, lat: number) {
    map?.flyTo({ center: [lon, lat], zoom: 16, speed: 1.4 });
  }
</script>

<div class="map-root">
  <div bind:this={mapContainer} class="map-container"></div>
  {#if currentZoom >= CLUSTER_MAX_ZOOM && currentZoom < BOULDER_MIN_ZOOM}
    <div class="zoom-hint">Zoom in to see individual boulders</div>
  {/if}
</div>

<style>
  .map-root {
    position: relative;
    width: 100%;
    height: 100%;
  }
  .map-container {
    width: 100%;
    height: 100%;
  }
  .zoom-hint {
    position: absolute;
    bottom: 60px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(17, 24, 39, 0.72);
    color: #fff;
    font-size: 12px;
    padding: 6px 16px;
    border-radius: 20px;
    pointer-events: none;
    z-index: 5;
    white-space: nowrap;
    letter-spacing: 0.02em;
  }
</style>
