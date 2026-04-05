import os
import secrets
import time
from collections import defaultdict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PASSWORD = os.environ.get("CLIPBOARD_PASSWORD", "").strip()
if not PASSWORD:
    raise SystemExit("ERROR: CLIPBOARD_PASSWORD environment variable is required")

SECURE_COOKIES  = os.environ.get("SECURE_COOKIES",  "true").lower() == "true"
MAX_CONTENT_SIZE = int(os.environ.get("MAX_CONTENT_KB", "512")) * 1024
MAX_FILE_SIZE    = int(os.environ.get("MAX_FILE_MB",   "10"))  * 1024 * 1024
DEFAULT_LANG     = os.environ.get("DEFAULT_LANG", "de").strip().lower()
if DEFAULT_LANG not in ("de", "en"):
    DEFAULT_LANG = "de"

# ---------------------------------------------------------------------------
# Session store  (in-memory, resets on container restart)
# ---------------------------------------------------------------------------
sessions: set[str] = set()

# ---------------------------------------------------------------------------
# Login rate limiting  (5 attempts / 60 s per IP)
# ---------------------------------------------------------------------------
_login_attempts: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT  = 5
RATE_WINDOW = 60  # seconds


def _check_rate_limit(ip: str) -> bool:
    now = time.monotonic()
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < RATE_WINDOW]
    if len(_login_attempts[ip]) >= RATE_LIMIT:
        return False
    _login_attempts[ip].append(now)
    return True


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host  # type: ignore[union-attr]


def _authenticated(request: Request) -> bool:
    token = request.cookies.get("session")
    return bool(token and token in sessions)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

def _render(filename: str) -> str:
    return (Path(f"static/{filename}").read_text()
            .replace("{{DEFAULT_LANG}}",   DEFAULT_LANG)
            .replace("{{MAX_CONTENT_KB}}", str(MAX_CONTENT_SIZE // 1024))
            .replace("{{MAX_FILE_MB}}",    str(MAX_FILE_SIZE    // (1024 * 1024))))


@app.get("/")
async def index(request: Request):
    if not _authenticated(request):
        return RedirectResponse("/login")
    return HTMLResponse(_render("index.html"))


@app.get("/login")
async def login_page(request: Request):
    if _authenticated(request):
        return RedirectResponse("/")
    return HTMLResponse(_render("login.html"))


@app.post("/login")
async def login(request: Request):
    ip = _client_ip(request)
    if not _check_rate_limit(ip):
        return HTMLResponse("Too many attempts. Please wait a minute.", status_code=429)

    form = await request.form()
    password = str(form.get("password", ""))

    if not secrets.compare_digest(password, PASSWORD):
        return RedirectResponse("/login?error=1", status_code=303)

    token = secrets.token_hex(32)
    sessions.add(token)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        "session", token,
        httponly=True,
        samesite="strict",
        secure=SECURE_COOKIES,
        max_age=86400 * 7,
    )
    return response


@app.post("/logout")
async def logout(request: Request):
    token = request.cookies.get("session")
    if token:
        sessions.discard(token)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session")
    return response


# ---------------------------------------------------------------------------
# File upload / download
# ---------------------------------------------------------------------------
@app.post("/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    if not _authenticated(request):
        return Response(status_code=401)

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        return Response("TOO_LARGE", status_code=413)

    filename = Path(file.filename or "file").name  # strip any path components
    mime     = file.content_type or "application/octet-stream"

    manager.store_file(filename, data, mime)
    await manager.broadcast_all(f"__FILE__|{filename}|{len(data)}")
    return Response(status_code=204)


@app.get("/download")
async def download(request: Request):
    if not _authenticated(request):
        return Response(status_code=401)
    if not manager.current_file:
        return Response(status_code=404)

    f = manager.current_file
    return Response(
        content=f["data"],
        media_type=f["mime"],
        headers={"Content-Disposition": f'attachment; filename="{f["name"]}"'},
    )


# ---------------------------------------------------------------------------
# WebSocket clipboard sync
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self) -> None:
        self.connections: list[WebSocket] = []
        self.current_content: str = ""
        self.current_file: dict | None = None

    def store_file(self, name: str, data: bytes, mime: str) -> None:
        self.current_file = {"name": name, "data": data, "mime": mime, "size": len(data)}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.append(ws)
        if self.current_content:
            await ws.send_text(self.current_content)
        if self.current_file:
            f = self.current_file
            await ws.send_text(f"__FILE__|{f['name']}|{f['size']}")

    def disconnect(self, ws: WebSocket) -> None:
        self.connections = [c for c in self.connections if c is not ws]

    async def broadcast(self, message: str, sender: WebSocket) -> None:
        self.current_content = message
        for conn in self.connections:
            if conn is not sender:
                await conn.send_text(message)

    async def broadcast_all(self, message: str) -> None:
        for conn in self.connections:
            await conn.send_text(message)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.cookies.get("session")
    if not token or token not in sessions:
        await websocket.close(code=4001)
        return

    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if len(data.encode()) > MAX_CONTENT_SIZE:
                await websocket.send_text("__ERROR__:TOO_LARGE")
                continue
            await manager.broadcast(data, websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
