# DigitalOcean Deployment

PulseWatch includes a guarded GitHub Actions deployment workflow. Continuous integration runs on every push and pull request. Production deployment runs only after the repository variable `ENABLE_DEPLOY` is explicitly set to `true` and all required secrets are configured.

## Server requirements

- Ubuntu server with Docker Engine and Docker Compose
- A dedicated deployment directory such as `/opt/pulsewatch`
- Public ports `3001` and `8000`, or a reverse proxy that exposes the services through HTTPS
- A non-root deployment user with permission to run Docker

## Initial server setup

Run these commands on the server after choosing a dedicated deployment user:

```bash
sudo mkdir -p /opt/pulsewatch
sudo chown "$USER":"$USER" /opt/pulsewatch
git clone https://github.com/Adityagithubhack/pulsewatch.git /opt/pulsewatch
cd /opt/pulsewatch
cp .env.example .env
```

Edit `/opt/pulsewatch/.env` and set:

```env
POSTGRES_PASSWORD=replace-with-a-strong-password
DATABASE_URL=postgresql+asyncpg://pulsewatch:replace-with-a-strong-password@postgres:5432/pulsewatch
NEXT_PUBLIC_API_URL=http://YOUR_SERVER_IP:8000
FRONTEND_ORIGIN=http://YOUR_SERVER_IP:3001
```

Start the first deployment manually:

```bash
docker compose up -d --build
docker compose ps
```

## Dedicated CI deployment key

Generate a deployment-only SSH key on a trusted computer:

```bash
ssh-keygen -t ed25519 -C "pulsewatch-github-actions" -f ~/.ssh/pulsewatch_actions
```

Append the public key to the deployment user's `~/.ssh/authorized_keys` on the server. Store the complete private key from `~/.ssh/pulsewatch_actions` in the GitHub environment secret `DEPLOY_SSH_KEY`.

Capture and verify the server host key from a trusted network:

```bash
ssh-keyscan -H YOUR_SERVER_IP
```

Store the verified output in `DEPLOY_KNOWN_HOSTS`.

## GitHub production environment

In the repository, open **Settings → Environments** and create an environment named `production`.

Add these environment secrets:

| Secret | Value |
| --- | --- |
| `DEPLOY_HOST` | Server IP address or hostname |
| `DEPLOY_USER` | Dedicated server deployment user |
| `DEPLOY_SSH_KEY` | Complete private deployment key |
| `DEPLOY_KNOWN_HOSTS` | Verified SSH host-key entry |
| `DEPLOY_PATH` | `/opt/pulsewatch` |

In **Settings → Secrets and variables → Actions → Variables**, create:

```text
ENABLE_DEPLOY=true
```

The deployment workflow remains skipped until this variable is present and equals `true`.

## Deployment behavior

After CI succeeds on `main`, the deployment workflow:

1. Validates that all deployment secrets exist.
2. Establishes an SSH connection using the dedicated key and pinned host identity.
3. Runs a fast-forward-only pull in the deployment directory.
4. Rebuilds and restarts the Docker Compose services.
5. Prints service status to the GitHub Actions log.

The workflow can also be started manually from the repository's **Actions → Deploy → Run workflow** page.

## Production hardening roadmap

Before sharing the deployment broadly:

- Put the frontend and API behind Caddy or Nginx with HTTPS.
- Restrict ports `3001` and `8000` at the firewall after the reverse proxy is active.
- Replace the default PostgreSQL password.
- Create a dedicated non-root deployment user.
- Back up the PostgreSQL Docker volume.
- Add authentication before storing private monitoring targets.

