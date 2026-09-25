# PulseWatch Operations Guide

## Production controls

PulseWatch supports optional operator authentication, noise-resistant incident policies,
maintenance windows, multi-channel alert delivery, public status reporting, DNS/TLS
diagnostics, Prometheus metrics, readiness checks, and an audit log.

## Enable operator authentication

Set these values in `.env` before starting the containers:

```env
AUTH_ENABLED=true
ADMIN_EMAIL=operator@example.com
ADMIN_PASSWORD=use-a-long-unique-password
SESSION_TTL_HOURS=24
PUBLIC_BASE_URL=https://status.example.com
```

The first startup creates the owner account with an scrypt password hash. Sessions use
random opaque tokens; only SHA-256 token digests are persisted. Browser sessions are
HttpOnly and become Secure when `PUBLIC_BASE_URL` uses HTTPS.

## Notification channels

Every channel is optional and delivered independently. A failure in one destination does
not block the check pipeline or other destinations.

### Telegram

```env
TELEGRAM_BOT_TOKEN=123456:replace-me
TELEGRAM_CHAT_ID=123456789
```

### Generic webhook

```env
ALERT_WEBHOOK_URL=https://automation.example.com/hooks/pulsewatch
```

### SMTP email

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=alerts@example.com
SMTP_PASSWORD=replace-me
ALERT_EMAIL_FROM=alerts@example.com
ALERT_EMAIL_TO=oncall@example.com
```

## Operational endpoints

| Endpoint | Purpose |
| --- | --- |
| `/health` | Process liveness |
| `/health/ready` | PostgreSQL and Redis readiness |
| `/metrics` | Prometheus-compatible counters and gauges |
| `/status` | Customer-facing service status page |
| `/api/public/status` | Public JSON status feed |
| `/docs` | Interactive OpenAPI documentation |

## Incident noise control

Each monitor defines independent failure and recovery thresholds. An incident opens only
after the configured number of consecutive failures. Recovery follows the same confirmation
policy. HTTP 403 and 429 responses remain classified as blocked probes and do not consume
the availability SLO.

Active maintenance windows preserve check telemetry but suppress incident and recovery
transitions. Windows can apply to one service or the full monitored fleet.

## Security model

- URLs are restricted to HTTP and HTTPS.
- Direct private, loopback, link-local, and reserved IP targets are rejected.
- Hostnames are re-resolved before probing and private DNS results are rejected to reduce
  DNS-rebinding/SSRF risk.
- Secrets stay in environment variables and are never returned to the dashboard.
- Operator write actions can be protected with HttpOnly session authentication.
- Audit records capture monitor, incident, and maintenance lifecycle events.

## Distributed deployment boundary

`PROBE_REGION` labels every persisted check. Genuine multi-region monitoring requires
independent Celery worker deployments in each geographic region using region-specific
queues and network egress. A single Docker host cannot provide honest multi-region results.
The current schema is region-aware so remote probe workers can be added without rewriting
historical check data.
