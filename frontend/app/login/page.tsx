"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void api.authStatus().then((status) => {
      setEnabled(status.enabled);
      if (status.authenticated) router.replace("/");
    }).catch(() => setError("Unable to reach the PulseWatch API"));
  }, [router]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true); setError("");
    try {
      await api.login(String(form.get("email")), String(form.get("password")));
      router.replace("/"); router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Authentication failed");
    } finally { setBusy(false); }
  }

  return <main className="login-page"><form className="login-card" onSubmit={submit}><div className="public-brand"><span className="brand-mark"><i /><i /><i /></span>PulseWatch</div><p className="eyebrow">Secure operations console</p><h1>Operator sign in</h1><p>Authenticate to manage monitors, incidents, and maintenance windows.</p>{error && <div className="login-error">{error}</div>}{enabled === false ? <div className="login-local">Authentication is disabled. PulseWatch is running in local operator mode.</div> : <><label>Email<input name="email" type="email" required autoComplete="username" placeholder="operator@company.com" /></label><label>Password<input name="password" type="password" required minLength={8} autoComplete="current-password" /></label><button className="primary" disabled={busy || enabled == null}>{busy ? "Signing in…" : "Sign in securely"}</button></>}</form></main>;
}
