from __future__ import annotations

import asyncio
import base64
import email.message
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import socket
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit, urlunsplit
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from fastapi import FastAPI, Header, HTTPException, Request as FastRequest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
WORKSPACE = Path(os.environ.get("JAI_WORKSPACE", str(ROOT / "workspace"))).resolve()
DOWNLOADS = WORKSPACE / "downloads"
PROFILE = WORKSPACE / ".browser-profile"
MAX_DOWNLOAD = 25 * 1024 * 1024
MAX_PAGE_TEXT = 14_000


def load_local_secrets() -> None:
    """Load the ignored, local-only key file without ever printing its contents."""
    path = ROOT / "secrets.env"
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            name, value = name.strip(), value.strip().strip('"').strip("'")
            if name in {"JAI_TAVILY_API_KEY_1", "JAI_TAVILY_API_KEY_2", "JAI_COMPUTER_TOKEN"} and value:
                os.environ.setdefault(name, value)
    except FileNotFoundError:
        pass


load_local_secrets()
TAVILY_KEYS = tuple(dict.fromkeys(
    value.strip() for name in ("JAI_TAVILY_API_KEY_1", "JAI_TAVILY_API_KEY_2")
    if (value := os.environ.get(name, "").strip())
))
TOKEN = os.environ.get("JAI_COMPUTER_TOKEN") or secrets.token_urlsafe(32)
HEADLESS = os.environ.get("JAI_HEADLESS", "1").lower() not in {"0", "false", "no"}
PORT = int(os.environ.get("PORT", os.environ.get("JAI_PORT", "8765")))

app = FastAPI(title="J AI Local Computer", version="1.0.0", docs_url=None, redoc_url=None)
ALLOWED_ORIGINS = [x.strip().rstrip("/") for x in os.environ.get("JAI_ALLOWED_ORIGINS", "").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-JAI-Token"],
)


class SearchBody(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class OpenBody(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class StepBody(BaseModel):
    action: str = Field(min_length=1, max_length=32)
    query: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=2048)
    filename: str | None = Field(default=None, max_length=180)
    selector: str | None = Field(default=None, max_length=500)
    text: str | None = Field(default=None, max_length=1000)
    approved: bool = False


class Computer:
    def __init__(self) -> None:
        self.pw = None
        self.context = None
        self.page = None
        self.lock = asyncio.Lock()
        self.dns_cache: dict[str, tuple[float, bool, str]] = {}

    async def start(self) -> None:
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        DOWNLOADS.mkdir(parents=True, exist_ok=True)
        PROFILE.mkdir(parents=True, exist_ok=True)
        self.pw = await async_playwright().start()
        args = ["--no-sandbox", "--disable-dev-shm-usage"] if getattr(os, "geteuid", lambda: 1)() == 0 else []
        try:
            self.context = await self.pw.chromium.launch_persistent_context(
                str(PROFILE), headless=HEADLESS, viewport={"width": 1365, "height": 900},
                accept_downloads=True, args=args,
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            )
        except Exception as e:
            await self.pw.stop()
            self.pw = None
            raise RuntimeError(
                "Chromium is not installed. Run: python -m playwright install chromium. " + str(e)[:500]
            ) from e
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        self.page.set_default_timeout(9000)
        await self.context.route("**/*", self._route_guard)

    async def stop(self) -> None:
        if self.context:
            await self.context.close()
        if self.pw:
            await self.pw.stop()

    async def _is_public(self, url: str) -> tuple[bool, str]:
        try:
            p = urlsplit(url)
            if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
                return False, "Only public http(s) pages are allowed."
            host = p.hostname.rstrip(".").lower()
            if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal", ".lan", ".home", ".test")):
                return False, "Local/private network destinations are blocked."
            try:
                ip = ipaddress.ip_address(host)
                if not ip.is_global:
                    return False, "Local/private network destinations are blocked."
                return True, ""
            except ValueError:
                pass
            cached = self.dns_cache.get(host)
            if cached and cached[0] > time.monotonic():
                return cached[1], cached[2]
            loop = asyncio.get_running_loop()
            records = await asyncio.wait_for(loop.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM), timeout=3)
            ips = {r[4][0] for r in records}
            ok = bool(ips) and all(ipaddress.ip_address(ip).is_global for ip in ips)
            reason = "" if ok else "Destination resolves to a local/private network address."
            self.dns_cache[host] = (time.monotonic() + 60, ok, reason)
            return ok, reason
        except Exception as e:
            return False, "Could not verify a public destination: " + str(e)[:160]

    async def _route_guard(self, route) -> None:
        ok, _ = await self._is_public(route.request.url)
        if ok:
            await route.continue_()
        else:
            await route.abort("blockedbyclient")

    async def _public_url(self, url: str) -> str:
        url = url.strip()
        p = urlsplit(url)
        if not p.scheme:
            url = "https://" + url
        ok, reason = await self._is_public(url)
        if not ok:
            raise HTTPException(400, reason)
        return url

    async def _snapshot(self) -> dict:
        page = self.page
        try:
            title = await page.title()
            current = page.url
            text = (await page.locator("body").inner_text(timeout=5000))[:MAX_PAGE_TEXT]
            image = base64.b64encode(await page.screenshot(type="png", full_page=False, timeout=8000)).decode("ascii")
            return {"ok": True, "url": current, "title": title[:300], "text": text,
                    "screenshot": "data:image/png;base64," + image}
        except Exception as e:
            return {"ok": False, "url": page.url, "error": str(e)[:500]}

    async def google_search(self, query: str) -> dict:
        query = query.strip()
        if not query:
            raise HTTPException(400, "Enter a search query.")
        async with self.lock:
            url = "https://www.google.com/search?q=" + quote(query) + "&num=8"
            await self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
            try:
                await self.page.locator("a:has(h3)").first.wait_for(timeout=5000)
            except Exception:
                pass
            results = await self.page.locator("a:has(h3)").evaluate_all("els => els.slice(0,8).map(a => ({title:(a.querySelector('h3')?.innerText||'').trim(),url:a.href,snippet:(a.parentElement?.parentElement?.innerText||'').trim().slice(0,700)})).filter(x=>x.title&&/^https?:/.test(x.url)&&!x.url.includes('google.com/search'))")
            if not results:
                body = (await self.page.locator("body").inner_text())[:5000]
                return {"ok": True, "query": query, "results": [], "notice": "Google returned no extractable results. It may require a CAPTCHA or have changed its page layout.", "page_text": body}
            return {"ok": True, "query": query, "results": results, "url": self.page.url}

    async def open_page(self, url: str) -> dict:
        url = await self._public_url(url)
        async with self.lock:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                await self.page.wait_for_load_state("networkidle", timeout=1800)
            except Exception:
                pass
            return await self._snapshot()

    async def read_page(self) -> dict:
        async with self.lock:
            return await self._snapshot()

    async def click(self, selector: str, approved: bool) -> dict:
        if not selector:
            raise HTTPException(400, "A CSS selector or visible text is required.")
        async with self.lock:
            try:
                locator = self.page.get_by_text(selector[5:], exact=False).first if selector.startswith("text=") else self.page.locator(selector).first
                if not await locator.count():
                    raise HTTPException(404, "No matching element was found.")
                info = await locator.evaluate("el => ({tag:el.tagName.toLowerCase(), text:(el.innerText||el.textContent||'').trim().slice(0,240), aria:el.getAttribute('aria-label')||'', title:el.getAttribute('title')||'', type:el.getAttribute('type')||''})")
                label = " ".join([info.get("text", ""), info.get("aria", ""), info.get("title", "")]).strip() or selector
                if re.search(r"buy|pay|purchase|delete|remove|transfer|submit|order|book|send|confirm|checkout|unsubscribe|close account", label, re.I):
                    raise HTTPException(403, "This may be a consequential action; the computer will not click it. Please handle it manually.")
                if not approved:
                    return {"ok": True, "needs_confirmation": True, "action": "click", "target": label,
                            "page_url": self.page.url, "note": "No click was performed."}
                await locator.click()
                await self.page.wait_for_timeout(500)
                return await self._snapshot()
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(400, "Click failed: " + str(e)[:350]) from e

    async def fill(self, selector: str, text: str, approved: bool) -> dict:
        if not selector:
            raise HTTPException(400, "A CSS selector is required.")
        async with self.lock:
            try:
                locator = self.page.locator(selector).first
                if not await locator.count():
                    raise HTTPException(404, "No matching field was found.")
                info = await locator.evaluate("el => ({tag:el.tagName.toLowerCase(), type:el.getAttribute('type')||'', name:el.getAttribute('name')||'', id:el.id||'', placeholder:el.getAttribute('placeholder')||'', aria:el.getAttribute('aria-label')||'', autocomplete:el.getAttribute('autocomplete')||''})")
                field_hint = " ".join(str(v) for v in info.values())
                if info.get("type", "").lower() in {"password", "hidden"} or re.search(r"password|passwd|secret|token|card|cvv|cvc|otp|one.?time|recovery|credential", field_hint, re.I):
                    raise HTTPException(403, "Credential, payment and one-time-code fields are manual-only.")
                if not approved:
                    return {"ok": True, "needs_confirmation": True, "action": "fill", "target": field_hint[:300],
                            "value_preview": text[:160], "page_url": self.page.url, "note": "No text was entered."}
                await locator.fill(text)
                return {"ok": True, "url": self.page.url, "filled": field_hint[:200], "note": "The value was entered but not submitted."}
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(400, "Fill failed: " + str(e)[:350]) from e


computer = Computer()


@app.on_event("startup")
async def startup() -> None:
    await computer.start()
    print("\nJ AI local computer is ready.")
    print("Open: http://127.0.0.1:8765")
    print("Pairing token (enter it in Mini Computer → Live Computer):")
    print(TOKEN + "\n")
    print("Browser mode:", "headed (visible)" if not HEADLESS else "headless")


@app.on_event("shutdown")
async def shutdown() -> None:
    await computer.stop()


@app.middleware("http")
async def local_only(request: FastRequest, call_next):
    host = request.headers.get("host", "").split(":", 1)[0].strip("[]").lower()
    if host not in {"127.0.0.1", "localhost"}:
        return JSONResponse({"detail": "This local computer service only accepts localhost requests."}, status_code=403)
    origin = request.headers.get("origin")
    if origin:
        try:
            op = urlsplit(origin)
            local_origin = op.hostname in {"127.0.0.1", "localhost"} and op.port in {None, PORT}
            same_host = op.scheme in {"http", "https"} and op.hostname == request.url.hostname
            configured_origin = origin.rstrip("/") in ALLOWED_ORIGINS or "*" in ALLOWED_ORIGINS
            if not (local_origin or same_host or configured_origin):
                return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
        except Exception:
            return JSONResponse({"detail": "Invalid Origin header."}, status_code=403)
    return await call_next(request)


def require_token(x_jai_token: str | None) -> None:
    if not x_jai_token or not secrets.compare_digest(x_jai_token, TOKEN):
        raise HTTPException(401, "Pair this app with the local computer using the token shown in the server terminal.")


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "J AI local computer", "browser": "Chromium", "headless": HEADLESS,
            "connected": bool(computer.page), "downloads": "/api/files", "version": "1.0.0"}


@app.get("/api/state")
async def state(x_jai_token: str | None = Header(default=None)):
    require_token(x_jai_token)
    return {"ok": True, "url": computer.page.url, "title": await computer.page.title(), "headless": HEADLESS}


def tavily_search(query: str) -> dict:
    if not TAVILY_KEYS:
        raise HTTPException(503, "Tavily API keys are not configured in local secrets.env.")
    failures: list[str] = []
    for index, key in enumerate(TAVILY_KEYS, start=1):
        request = Request(
            "https://api.tavily.com/search",
            data=json.dumps({"query": query, "max_results": 5, "search_depth": "basic", "include_answer": True}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key, "User-Agent": "JAI-Local-Computer/1.0"},
            method="POST",
        )
        try:
            with build_opener().open(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
            if not isinstance(result, dict) or result.get("error"):
                raise ValueError("Invalid search response")
            rows = result.get("results") if isinstance(result.get("results"), list) else []
            return {
                "ok": True,
                "provider": "Tavily",
                "query": query,
                "answer": result.get("answer") or "",
                "results": [
                    {"title": str(row.get("title") or row.get("url") or "Search result")[:300],
                     "url": str(row.get("url") or ""),
                     "content": str(row.get("content") or "")[:1800],
                     "snippet": str(row.get("content") or "")[:1800]}
                    for row in rows[:8] if isinstance(row, dict) and str(row.get("url") or "").startswith(("https://", "http://"))
                ],
            }
        except HTTPError as exc:
            failures.append(f"key {index}: HTTP {exc.code}")
        except Exception as exc:
            failures.append(f"key {index}: {type(exc).__name__}")
    raise HTTPException(502, "Tavily search failed with both configured keys (" + "; ".join(failures) + ").")


@app.post("/api/search")
async def search(body: SearchBody, x_jai_token: str | None = Header(default=None)):
    require_token(x_jai_token)
    return await asyncio.to_thread(tavily_search, body.query.strip())


@app.post("/api/open")
async def open_page(body: OpenBody, x_jai_token: str | None = Header(default=None)):
    require_token(x_jai_token)
    try:
        return await computer.open_page(body.url)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, "Page navigation failed: " + str(e)[:500]) from e


def safe_filename(name: str) -> str:
    name = unquote(name or "download.bin").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9._() -]+", "_", name).strip(" .")
    name = name[:140]
    if not name or name in {".", ".."}:
        name = "download.bin"
    return name


def blocking_download(url: str, filename: str | None) -> dict:
    def verify_redirect(url: str) -> None:
        p = urlsplit(url)
        if p.scheme not in {"https", "http"} or not p.hostname or p.username or p.password:
            raise ValueError("Redirect to an invalid destination was blocked.")
        host = p.hostname.rstrip(".").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal", ".lan", ".home", ".test")):
            raise ValueError("Redirect to a local/private destination was blocked.")
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            try:
                addresses = [ipaddress.ip_address(record[4][0]) for record in socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM)]
            except Exception as e:
                raise ValueError("Redirect destination could not be verified.") from e
        if not addresses or any(not address.is_global for address in addresses):
            raise ValueError("Redirect to a local/private destination was blocked.")

    class PublicRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            verify_redirect(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    verify_redirect(url)

    req = Request(url, headers={"User-Agent": "JAI-Local-Computer/1.0"})
    with build_opener(PublicRedirect()).open(req, timeout=25) as response:
        content_type = response.headers.get_content_type() if response.headers else "application/octet-stream"
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_DOWNLOAD:
            raise ValueError("File exceeds the 25 MB download limit.")
        chunks = bytearray()
        while True:
            block = response.read(min(64 * 1024, MAX_DOWNLOAD + 1 - len(chunks)))
            if not block:
                break
            chunks.extend(block)
            if len(chunks) > MAX_DOWNLOAD:
                raise ValueError("File exceeds the 25 MB download limit.")
        final_url = response.geturl()
        if not filename:
            cd = email.message.Message()
            cd["content-disposition"] = response.headers.get("Content-Disposition", "")
            filename = cd.get_filename() or Path(urlsplit(final_url).path).name or "download.bin"
    filename = safe_filename(filename)
    target = DOWNLOADS / filename
    base = target
    suffix = 0
    while True:
        try:
            with target.open("xb") as out:
                out.write(chunks)
            break
        except FileExistsError:
            suffix += 1
            target = DOWNLOADS / f"{base.stem}-{int(time.time())}-{suffix}{base.suffix}"
    return {"ok": True, "name": target.name, "size": len(chunks), "content_type": content_type,
            "path": str(target.relative_to(WORKSPACE)), "note": "Saved in the J AI workspace only; never executed."}


@app.post("/api/download")
async def download(body: OpenBody, x_jai_token: str | None = Header(default=None), filename: str | None = None):
    require_token(x_jai_token)
    url = await computer._public_url(body.url)
    try:
        return await asyncio.to_thread(blocking_download, url, filename)
    except Exception as e:
        raise HTTPException(502, "Download failed: " + str(e)[:500]) from e


@app.post("/api/agent/step")
async def agent_step(body: StepBody, x_jai_token: str | None = Header(default=None)):
    require_token(x_jai_token)
    try:
        action = body.action.strip().lower()
        if action in {"web_search", "google_search"}:
            if not body.query:
                raise HTTPException(400, "Search query is required.")
            return await asyncio.to_thread(tavily_search, body.query.strip())
        if action == "open_page":
            if not body.url:
                raise HTTPException(400, "Page URL is required.")
            return await computer.open_page(body.url)
        if action == "read_page":
            return await computer.read_page()
        if action == "download":
            if not body.url:
                raise HTTPException(400, "Download URL is required.")
            url = await computer._public_url(body.url)
            return await asyncio.to_thread(blocking_download, url, body.filename)
        if action == "click":
            return await computer.click(body.selector or body.text or "", body.approved)
        if action == "fill":
            if body.text is None:
                raise HTTPException(400, "Text to enter is required.")
            return await computer.fill(body.selector or "", body.text, body.approved)
        raise HTTPException(400, "Supported actions: web_search, google_search (alias), open_page, read_page, download, click, fill.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, "Computer action failed: " + str(e)[:500]) from e


@app.get("/api/files")
async def files(x_jai_token: str | None = Header(default=None)):
    require_token(x_jai_token)
    items = []
    for p in sorted(DOWNLOADS.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.is_file() and not p.is_symlink():
            items.append({"name": p.name, "size": p.stat().st_size, "modified": int(p.stat().st_mtime)})
    return {"ok": True, "files": items[:100]}


@app.get("/api/files/{name}")
async def get_file(name: str, x_jai_token: str | None = Header(default=None)):
    require_token(x_jai_token)
    safe = safe_filename(name)
    p = (DOWNLOADS / safe).resolve()
    if p.parent != DOWNLOADS.resolve() or not p.is_file():
        raise HTTPException(404, "File not found.")
    return FileResponse(p, filename=p.name, media_type=mimetypes.guess_type(p.name)[0] or "application/octet-stream")


@app.get("/", response_class=HTMLResponse)
async def index():
    path = STATIC / "index.html"
    if not path.exists():
        raise HTTPException(404, "The J AI interface has not been installed in static/index.html")
    return HTMLResponse(path.read_text(encoding="utf-8"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=PORT, log_level="info")
