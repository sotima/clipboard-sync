# Clipboard Sync

A lightweight, self-hosted clipboard sharing tool that works across any device with a browser — no software installation required.

Built with **FastAPI** and **WebSockets**, designed to run as a **Docker container**.

![Python](https://img.shields.io/badge/python-3.12-blue)
![Docker](https://img.shields.io/badge/docker-ready-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- **Browser-based** — works on any OS, no client software needed
- **Real-time sync** — content appears instantly on all connected clients via WebSockets
- **Secure** — password login, session cookies (httponly, samesite, secure), rate limiting on login attempts
- **Configurable** — password, cookie security and upload limit via environment variables
- **File transfer** — share files via drag & drop or file dialog, separate size limit via `MAX_FILE_MB`
- **Multilingual** — English and German UI, configurable default via `DEFAULT_LANG`, switchable per-user in the browser
- **Auto-reconnect** — clients reconnect automatically if the connection drops
- **Docker-ready** — single `docker compose up -d` to deploy

---

## Screenshots

| Login | Clipboard |
|-------|-----------|
| Clean password-protected login page | Textarea with copy/paste buttons and live sync status |
|<img width="250" height="250" alt="image" src="https://github.com/sotima/clipboard-sync/img/login.png" />


---

## Getting Started

### Prerequisites

- Docker + Docker Compose

### Installation

```bash
git clone https://github.com/sotima/clipboard-sync.git
cd clipboard-sync

# Create your config
cp .env.example .env
nano .env   # set a strong password
```

### Configuration (`.env`)

```env
# Required: password to access the app
CLIPBOARD_PASSWORD=your-secure-password-here

# Set to true when running behind HTTPS (recommended)
SECURE_COOKIES=true

# Maximum clipboard content size in KB (default: 512)
MAX_CONTENT_KB=512

# Maximum file upload size in MB (default: 10)
MAX_FILE_MB=10

# Default UI language: de or en (default: de)
DEFAULT_LANG=de
```

### Run

```bash
docker compose up -d
```

The app is now available at `http://localhost:8080`.

---

## Exposing via HTTPS

For internet access with a proper TLS certificate, place the container behind a reverse proxy such as **[Pangolin](https://github.com/fosrl/pangolin)**, **Nginx Proxy Manager**, **Caddy**, or **Traefik**.

The app listens on port `8080` internally. Set `SECURE_COOKIES=true` (default) when served over HTTPS.

Example with Pangolin: add a new tunnel resource pointing to `http://<docker-host>:8080`.

---

## Usage

1. Open the URL in any browser and log in with your password
2. **Type or paste** content into the textarea — it syncs to all other open sessions automatically
3. Use **"Paste from clipboard"** to read your local clipboard and broadcast it
4. Use **"Copy to clipboard"** to copy the synced content to your local clipboard
5. **Drop a file** onto the file zone (or click to select) — all connected clients get a download button instantly

> **Note:** The browser Clipboard API (`readText`) requires either HTTPS or `localhost`. The paste button works fully when accessed via HTTPS. On plain HTTP you can still type/paste manually into the textarea.

---

## Security

| Measure | Detail |
|---|---|
| Password login | Set via `CLIPBOARD_PASSWORD` env variable — never baked into the image |
| Timing-safe comparison | `secrets.compare_digest()` prevents timing attacks |
| Session cookie | `httponly`, `samesite=strict`, `secure` (configurable), 7-day expiry |
| Rate limiting | Max 5 login attempts per IP per 60 seconds |
| WebSocket auth | Session cookie verified before accepting the WS connection |
| Payload limit | Configurable via `MAX_CONTENT_KB` (default 512 KB) |
| No API docs | `/docs`, `/redoc` and `/openapi.json` are disabled |
| `.env` excluded | `.gitignore` prevents accidentally committing secrets |

---

## Project Structure

```
clipboard-sync/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── app/
    ├── main.py
    └── static/
        ├── index.html
        └── login.html
```

---

## License

MIT
