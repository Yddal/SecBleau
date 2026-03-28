/**
 * Typed API client for the SecBleau backend.
 */

const BASE = '/api/v1';

export interface AreaProperties {
  id: number;
  name: string;
  slug: string | null;
  dryness_score: number | null;
  confidence: number;
  is_estimated: boolean;
  hours_since_rain: number | null;
  last_rain_at: string | null;
  last_rain_mm: number | null;
  boulder_count: number;
  aspect: string | null;
  elevation_m: number | null;
  temperature_c: number | null;
  humidity_pct: number | null;
  wind_speed_ms: number | null;
  bbox_sw_lon: number | null;
  bbox_sw_lat: number | null;
  bbox_ne_lon: number | null;
  bbox_ne_lat: number | null;
}

export interface AreaFeature {
  type: 'Feature';
  geometry: { type: 'Point'; coordinates: [number, number] };
  properties: AreaProperties;
}

export interface AreaFeatureCollection {
  type: 'FeatureCollection';
  features: AreaFeature[];
}

export interface BoulderProperties {
  id: number;
  name: string | null;
  grade: string | null;
  area_id: number;
  area_name: string | null;
  dryness_score: number | null;
  confidence: number;
  is_estimated: boolean;
  has_recent_reports: boolean;
  hours_since_rain: number | null;
  last_rain_at: string | null;
  report_count: number;
}

export interface BoulderFeature {
  type: 'Feature';
  geometry: { type: 'Point'; coordinates: [number, number] };
  properties: BoulderProperties;
}

export interface BoulderFeatureCollection {
  type: 'FeatureCollection';
  features: BoulderFeature[];
}

export interface BoulderSearchResult {
  id: number;
  name: string | null;
  grade: string | null;
  lat: number;
  lon: number;
  area_id: number;
  area_name: string | null;
}

export interface BoulderDetail {
  id: number;
  name: string | null;
  grade: string | null;
  lat: number;
  lon: number;
  area_id: number;
  area_name: string | null;
  dryness_score: number | null;
  confidence: number;
  is_estimated: boolean;
  has_recent_reports: boolean;
  hours_since_rain: number | null;
  last_rain_at: string | null;
  recent_reports: Array<{ reported_at: string; condition: string; report_level: string }>;
}

export interface ReportOut {
  id: number;
  report_level: string;
  condition: string;
  reported_at: string;
  updated_score: number | null;
  message: string;
}

export interface ClusterProperties {
  clusterId: number;
  name: string;
  southWestLat: string;
  southWestLon: string;
  northEastLat: string;
  northEastLon: string;
  dryness_score: number | null;
  area_count: number;
  hull: { type: string; coordinates: unknown } | null;
}

export interface ClusterFeature {
  type: 'Feature';
  geometry: { type: string; coordinates: [number, number] };
  properties: ClusterProperties;
}

export interface ClusterFeatureCollection {
  type: 'FeatureCollection';
  features: ClusterFeature[];
}

export interface ConditionsCluster {
  name: string;
  area_count: number;
  dryness_score: number | null;
  hours_since_rain: number | null;
  last_rain_mm: number | null;
  rain_24h_mm: number;
  rain_48h_mm: number;
  rain_72h_mm: number;
  temperature_c: number | null;
  humidity_pct: number | null;
  wind_speed_ms: number | null;
  solar_radiation_wm2: number | null;
  hourly_rain: Array<{ hour: string; mm: number }>;
  data_last_updated_at: string | null;
  data_next_update_at: string | null;
  source_url: string;
}

export interface ConditionsResponse {
  generated_at: string;
  clusters: ConditionsCluster[];
}

const TIMEOUT_MS = 15_000;

async function get<T>(path: string): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}${path}`, { signal: ctrl.signal });
    clearTimeout(timer);
    if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
    return res.json() as Promise<T>;
  } catch (e) {
    clearTimeout(timer);
    throw e;
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    if (res.status === 429) {
      const data = await res.json();
      throw new Error(data.detail || 'Too many reports. Please wait before reporting again.');
    }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `API error ${res.status}`);
    }
    return res.json() as Promise<T>;
  } catch (e) {
    clearTimeout(timer);
    throw e;
  }
}

export interface WeatherHour {
  h: string;          // ISO hour timestamp
  t: number | null;   // temperature_c
  hu: number | null;  // humidity_pct
  w: number | null;   // wind_speed_ms
  p: number | null;   // precipitation_mm (hourly sum)
}

export interface AreaAnalysis {
  id: number;
  name: string;
  aspect: string | null;
  shade_factor: number | null;
  canopy_factor: number | null;
  elevation_m: number | null;
  dryness_score: number | null;
  physics_score: number | null;
  ml_correction: number | null;
  confidence: number;
  is_estimated: boolean;
  hours_since_rain: number | null;
  last_rain_mm: number | null;
  report_count_4h: number;
  report_count_12h: number;
  report_count_24h: number;
  weather_72h: WeatherHour[];
}

export interface ClusterAnalysis {
  name: string;
  areas: AreaAnalysis[];
}

export interface AnalysisResponse {
  generated_at: string;
  clusters: ClusterAnalysis[];
}

export interface RecentReport {
  id: number;
  report_level: string;
  condition: string;
  reported_at: string;
  notes: string | null;
  area_id: number;
  area_name: string;
  boulder_id: number | null;
  boulder_name: string | null;
}

export interface RecentReportsResponse {
  generated_at: string;
  reports: RecentReport[];
}

export interface AreaSetting {
  id: number;
  name: string;
  aspect: string | null;
  shade_factor: number | null;
  canopy_factor: number | null;
  elevation_m: number | null;
  dryness_score: number | null;
  hours_since_rain: number | null;
}

export interface ClusterSettings {
  name: string;
  areas: AreaSetting[];
}

export interface SettingsResponse {
  clusters: ClusterSettings[];
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error((data as { detail?: string }).detail || `API error ${res.status}`);
    }
    return res.json() as Promise<T>;
  } catch (e) {
    clearTimeout(timer);
    throw e;
  }
}

export const api = {
  getAreas: () => get<AreaFeatureCollection>('/areas'),
  getAreaBoulders: (areaId: number) => get<BoulderFeatureCollection>(`/areas/${areaId}/boulders`),
  getAreaDetail: (areaId: number) => get<unknown>(`/areas/${areaId}`),
  getBoulder: (boulderId: number) => get<BoulderDetail>(`/boulders/${boulderId}`),
  searchBoulders: (q: string, limit = 20) =>
    get<BoulderSearchResult[]>(`/boulders/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  getClusters: () => get<ClusterFeatureCollection>('/areas/clusters'),
  getConditions: () => get<ConditionsResponse>('/weather/conditions'),

  reportArea: (areaId: number, condition: string, notes?: string) =>
    post<ReportOut>(`/areas/${areaId}/reports`, { condition, notes }),

  reportBoulder: (boulderId: number, condition: string, notes?: string) =>
    post<ReportOut>(`/boulders/${boulderId}/reports`, { condition, notes }),

  getAnalysis: () => get<AnalysisResponse>('/areas/analysis'),
  getRecentReports: (hours = 48, limit = 100) =>
    get<RecentReportsResponse>(`/reports/recent?hours=${hours}&limit=${limit}`),

  getSettings: () => get<SettingsResponse>('/areas/settings'),
  saveAreaSettings: (id: number, body: Partial<AreaSetting>) =>
    patch<AreaSetting>(`/areas/${id}/settings`, body),
  recalculateScores: () =>
    patch<{ status: string; message: string }>('/areas/recalculate', {}),
};
