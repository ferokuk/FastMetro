export interface Station {
  id: string;
  name: string;
  line_name: string;
  line_color: string;
}

export interface PathStep {
  station_id: string;
  station_name: string;
  line_name: string;
  is_transfer: boolean;
}

export interface PathResponse {
  from_station: Station;
  to_station: Station;
  path: PathStep[];
  total_steps: number;
  stations_count: number;
  transfers_count: number;
  total_time_minutes: number;
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

