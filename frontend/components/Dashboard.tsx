"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, Endpoint, Incident, Metrics, Summary } from "../lib/api";

const emptySummary: Summary = { total: 0, up: 0, down: 0, paused: 0, average_latency_ms: null };

export function Dashboard() {
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [summary, setSummary] = useState<Summary>(emptySummary);
  const [metrics, setMetrics] = useState<Record<string, Metrics>>({});
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);

  const load = useCallback(async () => {
    try {
      const [endpointData, summaryData, incidentData] = await Promise.all([
        api.endpoints(),
        api.summary(),
        api.incidents(),
      ]);
      const metricData = await Promise.all(endpointData.map((endpoint) => api.metrics(endpoint.id)));
      setEndpoints(endpointData);
      setSummary(summaryData);
      setIncidents(incidentData);
      setMetrics(Object.fromEntries(metricData.map((metric) => [metric.endpoint_id, metric])));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load PulseWatch");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 15_000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function addEndpoint(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy("create");
    try {
      const endpoint = await api.create({
        name: form.get("name"),
        url: form.get("url"),
        interval_seconds: Number(form.get("interval_seconds")),
        timeout_seconds: 10,
        expected_status: Number(form.get("expected_status")),
      });
      setShowForm(false);
      event.currentTarget.reset();
      await api.check(endpoint.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to add monitor");
    } finally {
      setBusy(null);
    }
  }

  async function checkNow(id: string) {
    setBusy(id);
    try {
      await api.check(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Check failed");
    } finally {
      setBusy(null);
    }
  }

  async function remove(id: string) {
    setBusy(id);
    try {
      await api.remove(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusy(null);
    }
  }

  const statusText = useMemo(() => {
    if (!summary.total) return "No monitors configured";
    if (summary.down) return `${summary.down} service${summary.down > 1 ? "s" : ""} need attention`;
    return "All monitored services are operational";
  }, [summary]);

  return (
    <main>
      <header className="topbar">
        <div className="brand"><span className="pulse" />PulseWatch</div>
        <button className="primary" onClick={() => setShowForm(!showForm)}>{showForm ? "Close" : "+ New monitor"}</button>
      </header>

      <section className="hero">
        <p className="eyebrow">Infrastructure overview</p>
        <h1>Know when your services fail.</h1>
        <p className="lede">Monitor APIs and websites, inspect latency, and receive incident alerts from one focused dashboard.</p>
        <div className={`system-state ${summary.down ? "danger" : "healthy"}`}>
          <span />{statusText}
        </div>
      </section>

      {showForm && (
        <form className="monitor-form" onSubmit={addEndpoint}>
          <label>Name<input name="name" required minLength={2} placeholder="Production API" /></label>
          <label>URL<input name="url" required type="url" placeholder="https://api.example.com/health" /></label>
          <label>Interval<select name="interval_seconds" defaultValue="60"><option value="30">30 seconds</option><option value="60">1 minute</option><option value="300">5 minutes</option></select></label>
          <label>Expected status<input name="expected_status" type="number" min="100" max="599" defaultValue="200" /></label>
          <button className="primary" disabled={busy === "create"}>{busy === "create" ? "Creating…" : "Start monitoring"}</button>
        </form>
      )}

      {error && <div className="error" role="alert">{error}</div>}

      <section className="stats">
        <article><span>Total monitors</span><strong>{summary.total}</strong></article>
        <article><span>Operational</span><strong className="green">{summary.up}</strong></article>
        <article><span>Incidents</span><strong className="red">{summary.down}</strong></article>
        <article><span>Average latency</span><strong>{summary.average_latency_ms == null ? "—" : `${Math.round(summary.average_latency_ms)} ms`}</strong></article>
      </section>

      <section className="monitors">
        <div className="section-title"><div><p className="eyebrow">Live monitors</p><h2>Services</h2></div><button className="ghost" onClick={load}>Refresh</button></div>
        {loading ? <div className="empty">Loading monitors…</div> : endpoints.length === 0 ? (
          <div className="empty"><strong>No services yet</strong><p>Add your first public API or website to begin collecting uptime data.</p></div>
        ) : (
          <div className="monitor-list">
            {endpoints.map((endpoint) => {
              const state = !endpoint.is_active ? "paused" : endpoint.latest_check?.status ?? "pending";
              return (
                <article className="monitor" key={endpoint.id}>
                  <div className={`status-dot ${state}`} />
                  <div className="monitor-main"><strong>{endpoint.name}</strong><a href={endpoint.url} target="_blank" rel="noreferrer">{endpoint.url}</a></div>
                  <div className="metric"><span>24h uptime</span><strong>{metrics[endpoint.id]?.uptime_percentage == null ? "—" : `${metrics[endpoint.id].uptime_percentage}%`}</strong></div>
                  <div className="metric"><span>HTTP</span><strong>{endpoint.latest_check?.status_code ?? "—"}</strong></div>
                  <div className="metric"><span>P95 latency</span><strong>{metrics[endpoint.id]?.p95_latency_ms == null ? "—" : `${Math.round(metrics[endpoint.id].p95_latency_ms!)} ms`}</strong></div>
                  <div className="actions"><button onClick={() => checkNow(endpoint.id)} disabled={busy === endpoint.id}>Check</button><button className="delete" onClick={() => remove(endpoint.id)} disabled={busy === endpoint.id}>Remove</button></div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="incidents">
        <div className="section-title"><div><p className="eyebrow">Operational timeline</p><h2>Recent incidents</h2></div></div>
        {incidents.length === 0 ? (
          <div className="empty"><strong>No incidents recorded</strong><p>Service failures and recoveries will appear here automatically.</p></div>
        ) : (
          <div className="incident-list">
            {incidents.map((incident) => (
              <article className="incident" key={incident.id}>
                <div className={`incident-state ${incident.resolved_at ? "resolved" : "open"}`}>{incident.resolved_at ? "Resolved" : "Open"}</div>
                <div><strong>{incident.endpoint_name}</strong><span>{incident.cause ?? `HTTP ${incident.opening_status_code ?? "failure"}`}</span></div>
                <time>{new Date(incident.opened_at).toLocaleString()}</time>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
