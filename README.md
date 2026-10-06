# J AI Real Browser Computer

This project connects the attached J AI interface to a browser computer running in the backend. The Railway image installs **official Google Chrome Stable** and launches it headless; the app mirrors current Chrome screenshots into both **Workspace → Live Computer** and the app's **Mini Computer** display. The preview refreshes about every 1.8 seconds while connected (it is a live screenshot preview, not an exported video recording).

## Search

- **Google Chrome is tried first**: the backend opens the real Google results page and extracts public result titles, links and snippets.
- If Google returns a CAPTCHA, blocks extraction, or has no readable results, the combined search uses the user's two configured **Tavily API keys**, in order, with the second key as automatic fallback.
- Both Tavily keys stay server-side in protected Railway variables or the ignored local `secrets.env`; they are not embedded in the app HTML or sent to the AI model.
- The explicit **Search Google in Chrome** button shows the real Google page and does not silently switch providers. If Google blocks extraction, the combined-search button and J AI web search can use Tavily fallback.

## What it can do

- Open real Google Chrome pages, perform Google searches, read public page text and mirror browser screenshots in the app.
- Let J AI request a bounded sequence of up to five browser actions for a task. Public downloads are saved in the backend workspace and never run automatically.
- Show an approval preview before a page click or text entry; the user must approve the exact target. Form submission, payment, login secrets, account/security changes and other consequential actions remain manual.
- Keep Chrome's browser profile and downloaded files in the configured workspace. A Railway persistent volume mounted at `/data` preserves them across deploys/restarts. Each download is limited to 25 MB.

## Limits and safety

This is a **browser computer**, not a complete remote desktop or Google product. On Railway, Google Chrome runs headless; the live screen is shown inside J AI rather than as a separate desktop window. CAPTCHA, login challenges, blocked pages, anti-bot controls and websites that prohibit automation are not bypassed. Screenshots refresh periodically; this package does not create a downloadable MP4/WebM recording.

Arbitrary shell execution, downloaded-file execution, credentials/OTP/payment entry, purchases, official submissions, destructive changes and account-security changes are not offered. Downloads are checked against public destinations and saved only to the backend workspace.

## Local install (Linux/macOS)

Python 3.10+ is required. The default local setup uses Playwright's bundled Chromium. To use locally installed official Google Chrome, set `JAI_BROWSER_CHANNEL=chrome` and install Chrome on that machine.

```bash
unzip JAI-Local-Computer.zip
cd jai-real-computer
cp secrets.env.example secrets.env
# Edit secrets.env locally: use a long private JAI_COMPUTER_TOKEN and your Tavily keys.
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
python app.py
```

Open the URL printed in the terminal, go to **Workspace → Live Computer**, paste the local pairing token and press **Connect**. Keep the token private. `secrets.env` is ignored by Git and excluded from the Docker build context.

## Local install (Windows PowerShell)

```powershell
Expand-Archive .\JAI-Local-Computer.zip .
cd .\jai-real-computer
Copy-Item .\secrets.env.example .\secrets.env
# Edit secrets.env locally before starting.
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
python app.py
```

The service is headless by default. On a local desktop only, `JAI_HEADLESS=0` opens the browser visibly. Railway remains headless and shows screenshots in the app.

## Railway deployment

The `Dockerfile` installs Google Chrome Stable and binds to Railway's injected `PORT`. Deploy this project to a Railway service, generate its HTTPS domain, then mount a persistent volume at `/data`. The image sets `JAI_WORKSPACE=/data` and `JAI_BROWSER_CHANNEL=chrome`.

Set these **service variables** in Railway:

- `JAI_COMPUTER_TOKEN` — a long random pairing token (the service intentionally does not print this value in Railway logs).
- `JAI_TAVILY_API_KEY_1` and `JAI_TAVILY_API_KEY_2` — the two Tavily keys, used only by the backend as fallback.
- `JAI_HEADLESS=1` and `JAI_WORKSPACE=/data` (already set by the Docker image, shown here for clarity).

The bundled J AI HTML and API are served on the **same Railway origin**. Open that deployed URL, go to **Workspace → Live Computer**, enter the private `JAI_COMPUTER_TOKEN`, and connect. API routes require the token. Do not publish it or place it in browser HTML. If serving a separate UI domain, configure the exact origin in `JAI_ALLOWED_ORIGINS` and the host in `JAI_ALLOWED_HOSTS`; avoid wildcard origins.

`secrets.env.example` is a placeholder template only. If no persistent volume is attached, browser profile and downloaded files in `/data` may be lost when the container is replaced.
