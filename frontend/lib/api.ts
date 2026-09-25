export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Check = {
  id: string;
  endpoint_id: string;
  status: "up" | "down";
  availability: "up" | "blocked" | "down";
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
  failure_threshold: number;
  recovery_threshold: number;
  ssl_expiry_enabled: boolean;
  is_active: boolean;
  created_at: string;
  latest_check: Check | null;
};

export type Summary = {
  total: number;
  up: number;
  down: number;
  blocked: number;
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
  severity: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  notes: string | null;
};

export type MaintenanceWindow = {
  id: string;
  endpoint_id: string | null;
  title: string;
  starts_at: string;
  ends_at: string;
  created_at: string;
};

export type Diagnostics = {
  hostname: string;
  resolved_addresses: string[];
  dns_latency_ms: number | null;
  tls_enabled: boolean;
  tls_issuer: string | null;
  tls_expires_at: string | null;
  tls_days_remaining: number | null;
  tls_status: "valid" | "warning" | "expired" | "not_applicable";
};

export type AuditEntry = {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  actor: string;
  detail: string | null;
  created_at: string;
};

export type NotificationStatus = { telegram: boolean; webhook: boolean; email: boolean };
export type AuthStatus = { enabled: boolean; authenticated: boolean; email: string | null; role: string | null };

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(payload.detail ?? "Request failed");
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const api = {
  authStatus: () => json<AuthStatus>("/api/auth/status"),
  login: (email: string, password: string) => json<AuthStatus>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => json<void>("/api/auth/logout", { method: "POST" }),
  endpoints: () => json<Endpoint[]>("/api/endpoints"),
  summary: () => json<Summary>("/api/dashboard/summary"),
  metrics: (id: string, hours = 24) => json<Metrics>(`/api/endpoints/${id}/metrics?hours=${hours}`),
  incidents: () => json<Incident[]>("/api/incidents?limit=20"),
  updateIncident: (id: string, payload: Record<string, unknown>) =>
    json<Incident>(`/api/incidents/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  maintenance: () => json<MaintenanceWindow[]>("/api/maintenance"),
  createMaintenance: (payload: Record<string, unknown>) =>
    json<MaintenanceWindow>("/api/maintenance", { method: "POST", body: JSON.stringify(payload) }),
  removeMaintenance: (id: string) => json<void>(`/api/maintenance/${id}`, { method: "DELETE" }),
  diagnostics: (id: string) => json<Diagnostics>(`/api/endpoints/${id}/diagnostics`),
  notificationStatus: () => json<NotificationStatus>("/api/notifications/status"),
  audit: () => json<AuditEntry[]>("/api/audit?limit=50"),
  create: (payload: Record<string, unknown>) =>
    json<Endpoint>("/api/endpoints", { method: "POST", body: JSON.stringify(payload) }),
  update: (id: string, payload: Record<string, unknown>) =>
    json<Endpoint>(`/api/endpoints/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  check: (id: string) => json<Check>(`/api/endpoints/${id}/check`, { method: "POST" }),
  remove: (id: string) => json<void>(`/api/endpoints/${id}`, { method: "DELETE" }),
};
