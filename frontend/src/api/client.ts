import type {
  GraphResponse,
  HealthResponse,
  PathResponse,
  RefreshResponse,
  Station
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

export async function fetchPath(fromId: string, toId: string): Promise<PathResponse> {
  const params = new URLSearchParams({
    from_id: fromId,
    to_id: toId
  });
  const query = params.toString();
  return request<PathResponse>(`/path?${query}`);
}

export async function refreshMetro(): Promise<RefreshResponse> {
  return request<RefreshResponse>("/admin/refresh", {
    method: "POST"
  });
}

export async function fetchGraph(): Promise<GraphResponse> {
  return request<GraphResponse>("/graph");
}

