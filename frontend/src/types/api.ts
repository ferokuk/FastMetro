export interface Station {
  id: string;
  name: string;
  line_name: string;
  line_color: string;
}

export type FactorType = "rush_hour" | "weekend" | "line" | "weather";

export interface PathStep {
  station_id: string;
  station_name: string;
  line_name: string;
  is_transfer: boolean;
  base_minutes?: number | null;
  multiplier?: number | null;
  final_minutes?: number | null;
  factors_applied: string[];
}

export interface AppliedFactor {
  name: string;
  type: FactorType;
  multiplier: number;
  segments_affected: number;
}

export interface RouteContext {
  evaluated_at: string;
  weekday: number;
  hour: number;
  weather: string;
}

export interface PathResponse {
  from_station: Station;
  to_station: Station;
  path: PathStep[];
  total_steps: number;
  stations_count: number;
  transfers_count: number;
  total_time_minutes: number;
  base_total_minutes: number;
  applied_factors_summary: AppliedFactor[];
  context: RouteContext;
}

export interface HealthResponse {
  status: string;
}

export interface RefreshResponse {
  stations: number;
  trips: number;
}

export interface GraphStation {
  id: string;
  name: string;
  line_id: string;
  line_name: string;
  line_color: string;
  lat: number;
  lng: number;
}

export interface GraphEdge {
  from_id: string;
  to_id: string;
  is_transfer: boolean;
}

export interface GraphResponse {
  stations: GraphStation[];
  edges: GraphEdge[];
}

export interface Factor {
  id: number;
  name: string;
  factor_type: FactorType;
  multiplier: number;
  applies_to_segment: boolean;
  applies_to_transfer: boolean;
  line_id: string | null;
  hour_start: number | null;
  hour_end: number | null;
  weekday_mask: number | null;
  weather_condition: string | null;
  is_active: boolean;
  priority: number;
}

export type FactorUpdate = Omit<Factor, "id">;

export type WeatherCondition = "clear" | "rain" | "snow" | "fog";
export type WeatherSource = "manual" | "openweather";

export interface WeatherState {
  condition: WeatherCondition;
  source: WeatherSource;
  updated_at: string | null;
}
