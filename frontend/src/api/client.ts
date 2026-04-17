import type {
  Factor,
  FactorUpdate,
  GraphResponse,
  HealthResponse,
  PathResponse,
  RefreshResponse,
  Station,
  WeatherState
} from "../types/api";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL && import.meta.env.VITE_API_BASE_URL.trim().length > 0
    ? import.meta.env.VITE_API_BASE_URL
    : "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  const resp = await fetch(url, {
    headers: {
      "Content-Type": "application/json"
    },
    ...init
  });

  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`Request failed: ${resp.status} ${resp.statusText} ${text}`);
  }

  return (await resp.json()) as T;
}

export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export async function fetchStations(limit = 500, search?: string): Promise<Station[]> {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (search && search.trim()) {
    params.set("search", search.trim());
  }
  const query = params.toString();
  return request<Station[]>(`/stations${query ? `?${query}` : ""}`);
}

export interface FetchPathOptions {
  overrideTime?: string;
  overrideWeather?: string;
  apiKey?: string;
}

export async function fetchPath(
  fromId: string,
  toId: string,
  opts?: FetchPathOptions
): Promise<PathResponse> {
  const params = new URLSearchParams({
    from_id: fromId,
    to_id: toId
  });
  if (opts?.overrideTime) params.set("override_time", opts.overrideTime);
  if (opts?.overrideWeather) params.set("override_weather", opts.overrideWeather);
  const query = params.toString();
  const init: RequestInit | undefined = opts?.apiKey
    ? { headers: { "Content-Type": "application/json", "X-API-Key": opts.apiKey } }
    : undefined;
  return request<PathResponse>(`/path?${query}`, init);
}

export async function refreshMetro(): Promise<RefreshResponse> {
  return request<RefreshResponse>("/admin/refresh", {
    method: "POST"
  });
}

export async function fetchGraph(): Promise<GraphResponse> {
  return request<GraphResponse>("/graph");
}

export async function fetchFactors(): Promise<Factor[]> {
  return request<Factor[]>("/factors");
}

export async function updateFactor(
  id: number,
  payload: FactorUpdate,
  apiKey: string
): Promise<Factor> {
  return request<Factor>(`/admin/factors/${id}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey
    },
    body: JSON.stringify(payload)
  });
}

export async function fetchWeather(): Promise<WeatherState> {
  return request<WeatherState>("/weather");
}

export async function setWeather(
  condition: string,
  apiKey: string
): Promise<WeatherState> {
  return request<WeatherState>("/admin/weather", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey
    },
    body: JSON.stringify({ condition })
  });
}

