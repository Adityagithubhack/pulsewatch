export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Check = {
  id: string;
  endpoint_id: string;
  status: "up" | "down";
  status_code: number | null;
  latency_ms: number | null;
  error: string | null;
  checked_at: string;
};

export type Endpoint = {
  id: string;
  name: string;
  url: string;
  method: "GET" | "HEAD";
  interval_seconds: number;
  timeout_seconds: number;
  expected_status: number;
  is_active: boolean;
  created_at: string;
  latest_check: Check | null;
};

export type Summary = {
  total: number;
  up: number;
  down: number;
  paused: number;
  average_latency_ms: number | null;
};

export type Metrics = {
  endpoint_id: string;
  window_hours: number;
  total_checks: number;
  successful_checks: number;
  uptime_percentage: number | null;
  average_latency_ms: number | null;
  p95_latency_ms: number | null;
  incident_count: number;
  series: Check[];
};

export type Incident = {
  id: string;
  endpoint_id: string;
  endpoint_name: string;
  endpoint_url: string;
  opened_at: string;
  resolved_at: string | null;
  opening_status_code: number | null;
  cause: string | null;
};

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(payload.detail ?? "Request failed");
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const api = {
  endpoints: () => json<Endpoint[]>("/api/endpoints"),
  summary: () => json<Summary>("/api/dashboard/summary"),
  metrics: (id: string) => json<Metrics>(`/api/endpoints/${id}/metrics?hours=24`),
  incidents: () => json<Incident[]>("/api/incidents?limit=20"),
  create: (payload: Record<string, unknown>) =>
    json<Endpoint>("/api/endpoints", { method: "POST", body: JSON.stringify(payload) }),
  check: (id: string) => json<Check>(`/api/endpoints/${id}/check`, { method: "POST" }),
  remove: (id: string) => json<void>(`/api/endpoints/${id}`, { method: "DELETE" }),
};
