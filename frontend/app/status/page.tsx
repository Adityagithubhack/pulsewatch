"use client";

import { useEffect, useState } from "react";
import { API_URL } from "../../lib/api";

type PublicService = { name: string; status: string; checked_at: string | null };
type PublicStatus = { name: string; state: string; updated_at: string; services: PublicService[] };

export default function StatusPage() {
  const [data, setData] = useState<PublicStatus | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch(`${API_URL}/api/public/status`, { cache: "no-store" });
        if (!response.ok) throw new Error("Status feed unavailable");
        setData(await response.json());
        setError("");
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Status feed unavailable");
      }
    }
    void load();
    const timer = window.setInterval(() => void load(), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const operational = data?.state === "operational";
  return <main className="public-status-page"><header><a href="/" className="public-brand"><span className="brand-mark"><i /><i /><i /></span>PulseWatch</a><span>Service Status</span></header><section className="status-hero"><p className="eyebrow">Live service health</p><h1>{data?.name ?? "System status"}</h1><p>Availability and incident information for monitored services.</p></section>{error && <div className="public-state error-state"><i />{error}</div>}{!error && <div className={`public-state ${operational ? "operational" : "degraded"}`}><i /><div><strong>{!data ? "Loading current status…" : operational ? "All systems operational" : data.state.replaceAll("_", " ")}</strong><span>{data ? `Last updated ${new Date(data.updated_at).toLocaleString()}` : "Connecting to telemetry"}</span></div></div>}<section className="public-services"><div className="public-section-title"><h2>Services</h2><span>{data?.services.length ?? 0} components</span></div>{data?.services.map((service) => <article key={service.name}><div><strong>{service.name}</strong><span>{service.checked_at ? `Checked ${new Date(service.checked_at).toLocaleString()}` : "Awaiting first check"}</span></div><span className={`public-service-state ${service.status}`}>{service.status === "up" ? "Operational" : service.status}</span></article>)}{data && !data.services.length && <div className="empty-state"><strong>No public services configured</strong></div>}</section><footer>Powered by PulseWatch · Automatic updates every 30 seconds</footer></main>;
}
