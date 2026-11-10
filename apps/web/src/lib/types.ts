import type { Feature, FeatureCollection, Geometry } from 'geojson';

export type Place = {
  city_id: string;
  provider_id: string;
  provider: string;
  label: string;
  country: string;
  country_code: string;
  longitude: number;
  latitude: number;
  admin_labels: string[];
  admin_codes: Record<string, string>;
  alternate_names: string[];
  extent_provenance: string;
  source_url: string;
};
export type Source = {
  id?: string;
  publisher: string;
  title?: string;
  url?: string;
  year?: number;
  geographic_unit?: string;
  citation?: string;
  retrieval_timestamp?: string;
  license?: string;
  license_url?: string;
  reason?: string;
  status?: string;
};
export type Metric = {
  id: string;
  label: string;
  value: number | null;
  definition: string;
  interpretation: string;
  target_groups: string;
  unavailable_reason: string | null;
  warnings: string[];
  input_coverage: Record<string, number | string>;
};
export type AreaProperties = {
  area_id: string;
  name: string;
  parent_city: string;
  geometry_vintage: number;
  households: number;
  low_households: number;
  high_households: number;
  low_share: number | null;
  high_share: number | null;
  income_counts: number[];
  income_moe_90: (number | null)[];
  total_moe_90: number | null;
  quality_flags: string[];
};
export type Areas = FeatureCollection<Geometry, AreaProperties>;
export type Area = Feature<Geometry, AreaProperties>;
export type Income = {
  concept: string;
  currency: string;
  period: string;
  price_basis: string;
  reference_period: string;
  low_group: string;
  high_group: string;
  middle_group: string;
  bins: { variable: string; label: string; lower: number | null; upper: number | null }[];
};
export type MapResult = {
  geojson: Areas;
  coverage: { areas: number; populated_areas: number; households: number; fraction: number };
  warnings: string[];
  income: Income;
  year: number;
  composition: number[];
  sources: Source[];
  export_allowed: boolean;
  status: 'measured';
};
export type Diagnostic = {
  reason: string;
  code?: string;
  missing?: string[];
  sources_attempted?: Source[];
  ai_discovery?: string;
  connector_proposals?: ConnectorReport[];
  web_discovery?: { status: string; reason: string };
  availability?: 'integration_required' | 'data_not_verified';
};
export type ConnectorReport = {
  status: string;
  activated: boolean;
  template: string;
  message?: string;
  checks?: string[];
  missing?: string[];
};
export type DiscoveryProgress = {
  agent: string;
  status: string;
  message: string;
  report?: ConnectorReport;
};
export type AnalysisEvent =
  | { event: 'started'; data: { message: string; place: Place } }
  | {
      event: 'geography_ready';
      data: {
        place: Place;
        boundary: FeatureCollection | null;
        extent_description: string;
        source?: Source;
      };
    }
  | { event: 'source_found'; data: { source: Source } }
  | { event: 'discovery_progress'; data: DiscoveryProgress }
  | { event: 'downloading' | 'validating'; data: { message: string } }
  | { event: 'metric_computed'; data: { metric: Metric } }
  | { event: 'map_ready'; data: MapResult }
  | { event: 'insufficient_data' | 'failed'; data: Diagnostic }
  | {
      event: 'complete';
      data: { status: 'measured' | 'insufficient_data' | 'failed'; message?: string };
    };
export type Indicator = 'low_share' | 'high_share';
