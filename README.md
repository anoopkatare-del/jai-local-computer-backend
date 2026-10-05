# J AI Local Computer (prototype)

Yeh project attached J AI interface ke saath **local browser-computer backend** jodta hai. Backend Playwright Chromium chalata hai, public pages kholta/padhta hai, screenshot deta hai aur files ko alag workspace mein download karta hai. J AI ko computer tools sirf tab milte hain jab user **Workspace → Live Computer** se explicit task chalata hai.

## Search integration

Live Computer aur J AI web search **Tavily API** ko local backend se call karte hain—**Google Custom Search API nahi**. `secrets.env` mein di hui pehli key try hoti hai; request fail ho to doosri key automatically try hoti hai. Keys browser HTML, network response, aur AI prompt ko nahin bheji jaati. Search result ke baad Chromium se public pages khol/padh sakta hai. Google ka direct page alag se khola ja sakta hai, lekin CAPTCHA/anti-bot challenge aa sakta hai.

## Kya kaam karta hai

- Existing J AI search API se web results aur answer lena.
- Public website navigate/read karna; current page ka screenshot aur text J AI ko dena.
- AI ko ek request ke liye maximum 5 browser steps dena: `web_search` (app ka existing search API), `open_page`, `read_page`, `download`; page `click`/`fill` ke har attempt se pehle exact target dikhakar user se confirmation.
- Download ko `workspace/downloads/` mein rakhna; UI se download ko user ke device par save karna.
- Browser profile ko `workspace/.browser-profile/` mein local rakhna. Visible mode mein user apne account mein khud login kar sakta hai; agent ko credentials ya OTP nahi dene chahiye.

## Jo yeh nahin karta

Yeh complete desktop OS / Google ka official product nahin hai. Browser **Playwright Chromium** par chalta hai—Chrome-compatible engine, official Google Chrome distribution nahin. Headless mode mein websites khulengi; `JAI_HEADLESS=0` karne par local desktop par visible Chromium khulta hai. CAPTCHA, login challenges, blocked sites aur anti-bot controls ko bypass nahin karta.

Arbitrary shell command execution, downloaded file execution, passwords/payment/OTP entry, purchase, deletion, account-security change, official form submission ya doosre high-impact action nahin hain. Clicks/fills ke liye user prompt aata hai; potentially consequential buttons backend rokta hai. Downloads 25 MB per file tak seemit hain, aur kabhi auto-run nahin hote. Yeh controls perfect security boundary ka daawa nahin hain—personal credentials ya public-facing hosting ke liye production security review alag se zaroori hai.

## Install (Linux/macOS)

Python 3.10+ chahiye.

```bash
unzip JAI-Local-Computer.zip
cd jai-real-computer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
python app.py
```

Terminal mein pairing token print hoga. Apne browser mein `http://127.0.0.1:8765` kholo, **Workspace → Live Computer** jao, token paste karke **Connect** dabao. Token kisi ke saath share mat karo.

Headless mode default hai. Apne computer par **visible browser window** kholna ho to service ko environment variable ke saath chalao:

```bash
JAI_HEADLESS=0 python app.py
```

macOS shell syntax shell ke mutabik ho sakti hai. Server band karne ke liye terminal mein `Ctrl+C` dabao.

## Install (Windows PowerShell)

```powershell
Expand-Archive .\JAI-Local-Computer.zip .
cd .\jai-real-computer
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
python app.py
```

Visible browser ke liye:

```powershell
$env:JAI_HEADLESS="0"
python app.py
```

## AI aur backend connection

Yeh backend khud koi paid AI model key nahin maangta. Packaged J AI UI apni pehle-se configured model/provider setting use karta hai; us model ke liye internet/configuration zaroori hai. Tavily keys local-only `secrets.env` mein hoti hain; file ko private rakhein, GitHub/public hosting par upload ya kisi aur ko ZIP share na karein. `secrets.env` `.gitignore` mein hai.

Service jaanbujhkar `127.0.0.1` par bind hoti hai—public internet par nahin. Bundled J AI UI aur computer API ek hi localhost origin se serve hote hain; pairing token har server start par naya banta hai. `JAI_PORT` se port badal sakte ho; usi port par UI ko kholna hoga.

Isi computer par chal raha doosra local process `/api/search`, `/api/open`, `/api/agent/step`, `/api/files` routes use kar sakta hai, har protected request ke `X-JAI-Token` header mein terminal token bhejkar. **Remote cloud AI backend localhost service tak seedhe nahin pahunch sakta**—uske liye alag, authenticated secure gateway/relay banana aur security review karna hoga. Ise reverse proxy/VPS par seedhe public na karein.

Downloads `workspace/downloads/` mein rehte hain; browser login profile `workspace/.browser-profile/` mein store hoti hai. Profile delete karne se browser ke saved sessions/logout ho jaayenge.


## Railway hosting

`Dockerfile` Railway par Chromium aur API ko ek hi service mein chalata hai. Bundled J AI UI bhi wahi serve hota hai, isliye uska `/api` computer backend se same-origin rehta hai. Railway mein `JAI_COMPUTER_TOKEN`, `JAI_TAVILY_API_KEY_1`, `JAI_TAVILY_API_KEY_2`, `JAI_HEADLESS=1`, aur `JAI_WORKSPACE=/data` server-side variables set karein; persistent volume ko `/data` par mount karein. `PORT` Railway khud deta hai. `secrets.env` local development ke liye hai aur Git/Docker context se ignore hoti hai.

Public Railway domain kholkar **Workspace → Live Computer** mein private config ka pairing token paste karke Connect karein. API routes token-protected hain. Agar is UI ke bajay kisi doosre domain se connect karna ho, Railway variable `JAI_ALLOWED_ORIGINS` mein us exact origin (scheme ke saath) set karein; ise `*` na rakhein.
