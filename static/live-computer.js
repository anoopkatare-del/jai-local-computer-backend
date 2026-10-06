(() => {
  'use strict';
  const $ = (s) => document.querySelector(s);
  const root = $('#jw');
  if (!root) return;

  const css = document.createElement('style');
  css.textContent = `
    #lcStatus{display:inline-flex;align-items:center;gap:6px}
    #lcStatus:before{content:"";width:8px;height:8px;border-radius:50%;background:#a66a00}
    #lcStatus.online:before{background:#16803c}
    #lcShot{display:none;width:100%;max-height:48vh;object-fit:contain;border:1px solid var(--ln);border-radius:12px;background:#fff;margin-top:8px}
    #lcLiveStamp{display:block;margin-top:6px;font-size:12px;color:var(--mut)}
    #jaiRealBrowserMirror{position:absolute;left:8px;top:38px;width:calc(100% - 16px);height:calc(100% - 46px);object-fit:contain;background:#fff;z-index:20;border-radius:10px;pointer-events:none}
    #jaiChromeBadge{position:absolute;right:14px;top:42px;z-index:21;background:#16803c;color:#fff;padding:3px 8px;border-radius:10px;font:11px/1.3 system-ui;pointer-events:none}
    #lcResults,#lcFiles{display:flex;flex-direction:column;gap:8px;margin-top:8px}
    .lcResult,.lcFile{padding:10px;border:1px solid var(--ln);border-radius:12px;background:var(--tile);overflow-wrap:anywhere}
    .lcResult b,.lcFile b{display:block;margin-bottom:3px}
    .lcResult small,.lcFile small{color:var(--mut);display:block}
    .lcResult a{color:var(--bl);text-decoration:none}
    #lcOutput{max-height:240px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 ui-monospace,monospace;background:var(--tile);padding:10px;border-radius:10px}
    #jwp-live .jwtextarea{min-height:92px}
    #lcToken{font-family:ui-monospace,monospace}
  `;
  document.head.append(css);

  const nav = root.querySelector('.jws');
  const body = root.querySelector('.jwb');
  if (!nav || !body || root.querySelector('[data-jw="live"]')) return;
  const tabBtn = document.createElement('button');
  tabBtn.className = 'jwt';
  tabBtn.dataset.jw = 'live';
  tabBtn.textContent = 'Live Computer';
  nav.append(tabBtn);
  const section = document.createElement('section');
  section.className = 'jwp';
  section.id = 'jwp-live';
  section.innerHTML = `
    <div class="jwcard">
      <b>Google Chrome Computer</b>
      <p class="jwmut">This connects the app to the real Google Chrome browser on its backend. The server runs headless and mirrors live screen frames here and in the Mini Computer display. Pair once with the private backend token.</p>
      <input class="jwinput" id="lcToken" type="password" autocomplete="off" placeholder="Paste private computer pairing token">
      <button class="jwbtn primary" id="lcConnect">Connect</button>
      <span class="jwmut" id="lcStatus">Not connected</span>
    </div>
    <div class="jwcard">
      <b>Ask J AI to use this computer</b>
      <p class="jwmut">For this one request, J AI may Google-search, open/read public pages, or save a download into its workspace. Page clicks and form filling ask you first. Purchases, submissions, account changes, secrets, and running downloads stay manual.</p>
      <textarea class="jwtextarea" id="lcTask" placeholder="Example: Search Google for the official Python download page, open it, and tell me which version is current."></textarea>
      <button class="jwbtn primary" id="lcAsk">Run task with J AI</button>
    </div>
    <div class="jwcard">
      <b>Google Search in Chrome</b>
      <p class="jwmut">The real Chrome browser opens Google. If Google presents a CAPTCHA or blocks result extraction, the server falls back to your configured Tavily keys for answer results.</p>
      <input class="jwinput" id="lcQuery" placeholder="Search Google from the real browser">
      <button class="jwbtn primary" id="lcGoogle">Search Google in Chrome</button>
      <button class="jwbtn" id="lcSearch">Search Google, then Tavily fallback</button>
      <div id="lcResults"></div>
    </div>
    <div class="jwcard">
      <b>Live Google Chrome screen</b>
      <input class="jwinput" id="lcUrl" value="https://www.google.com" placeholder="https://example.com">
      <button class="jwbtn primary" id="lcOpen">Open page in Chrome</button>
      <span class="jwmut" id="lcPageTitle"></span>
      <span id="lcLiveStamp">Live screen preview appears after pairing.</span>
      <img id="lcShot" alt="Live screenshot of the current Google Chrome page">
      <div id="lcPageText" class="jwmut" style="white-space:pre-wrap;max-height:180px;overflow:auto;margin-top:8px"></div>
    </div>
    <div class="jwcard"><b>Workspace downloads (25 MB max each)</b><div id="lcFiles" class="jwmut">Connect to view files.</div><button class="jwbtn" id="lcRefresh">Refresh files</button></div>
    <div class="jwcard"><b>Computer activity</b><div id="lcOutput">No computer action yet.</div></div>`;
  body.append(section);
  tabBtn.addEventListener('click', () => {
    document.querySelectorAll('.jwt').forEach((x) => x.classList.toggle('on', x === tabBtn));
    document.querySelectorAll('.jwp').forEach((x) => x.classList.toggle('on', x === section));
  });

  const savedToken = localStorage.getItem('jai_local_computer_token') || '';
  $('#lcToken').value = savedToken;
  let connected = false;
  let liveTimer = null;
  let screenBusy = false;
  const output = (text) => { $('#lcOutput').textContent = String(text); };
  const token = () => $('#lcToken').value.trim();
  const setStatus = (text, ok = false) => {
    $('#lcStatus').textContent = text;
    $('#lcStatus').classList.toggle('online', !!ok);
    connected = !!ok;
    if (liveTimer) { clearInterval(liveTimer); liveTimer = null; }
    if (connected) liveTimer = setInterval(refreshScreen, 1800);
  };
  function showBrowser(data, updateText = true, updateWorkspaceFrame = false) {
    if (!data || !data.screenshot) return;
    const image = $('#lcShot'); image.src = data.screenshot; image.style.display = 'block';
    const browser = data.browser || 'Google Chrome';
    const pageTitle = data.title || '';
    const pageUrl = data.url || '';
    $('#lcPageTitle').textContent = `${browser} · ${pageTitle} · ${pageUrl}`;
    $('#lcLiveStamp').textContent = `LIVE preview · ${browser} · refreshed ${new Date().toLocaleTimeString()}`;
    if (updateText && (data.text || data.page_text)) $('#lcPageText').textContent = data.text || data.page_text;
    const mini = document.querySelector('#mc .mcs');
    if (mini) {
      mini.style.position = 'relative';
      let mirror = mini.querySelector('#jaiRealBrowserMirror');
      if (!mirror) { mirror = document.createElement('img'); mirror.id = 'jaiRealBrowserMirror'; mirror.alt = 'Live Google Chrome screen'; mini.append(mirror); }
      mirror.src = data.screenshot;
      let badge = mini.querySelector('#jaiChromeBadge');
      if (!badge) { badge = document.createElement('span'); badge.id = 'jaiChromeBadge'; badge.textContent = 'Google Chrome · LIVE'; mini.append(badge); }
    }
    if (updateWorkspaceFrame) {
      const frame = $('#jwFrame');
      if (frame) frame.srcdoc = `<!doctype html><html><body style="margin:0;background:#10131a;height:100vh;display:grid;place-items:center"><img alt="Live Google Chrome screen" style="max-width:100%;max-height:100%;object-fit:contain" src="${data.screenshot}"></body></html>`;
    }
  }
  window.__jaiShowBrowserSnapshot = (data) => showBrowser(data, true, false);
  async function refreshScreen() {
    if (!connected || screenBusy) return;
    screenBusy = true;
    try { const data = await api('/api/screenshot'); if (data.ok) showBrowser(data, false, false); }
    catch (e) { if (/401|403/.test(String(e.message))) setStatus('Pairing expired or rejected', false); }
    finally { screenBusy = false; }
  }
  async function api(path, method = 'GET', payload = undefined) {
    const headers = { 'X-JAI-Token': token() };
    if (payload !== undefined) headers['Content-Type'] = 'application/json';
    const response = await fetch(path, { method, headers, body: payload === undefined ? undefined : JSON.stringify(payload), cache: 'no-store' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
    return data;
  }
  async function connect() {
    const r = await fetch('/api/health', { cache: 'no-store' });
    if (!r.ok) throw new Error('Computer backend is not available at this app URL.');
    const h = await r.json();
    if (!h.ok) throw new Error('Local computer service did not report ready.');
    await api('/api/state');
    localStorage.setItem('jai_local_computer_token', token());
    setStatus(`Connected · ${h.browser || 'Google Chrome'} ${h.headless ? '(headless with live view)' : '(visible)'}`, true);
    await refreshFiles();
    await refreshScreen();
    output(`Connected to ${h.browser || 'Google Chrome'}; live screen preview is on.`);
  }
  function requireConnection() {
    if (!connected) throw new Error('Connect the Google Chrome computer first.');
  }
  function showSearch(data) {
    const list = $('#lcResults');
    list.replaceChildren();
    if (!data.results?.length) {
      const p = document.createElement('p'); p.className = 'jwmut';
      p.textContent = data.notice || data.page_text || 'No results returned.'; list.append(p); return;
    }
    for (const item of data.results) {
      const card = document.createElement('div'); card.className = 'lcResult';
      const a = document.createElement('a'); a.href = item.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.textContent = item.title || item.url;
      const b = document.createElement('b'); b.append(a);
      const small = document.createElement('small'); small.textContent = item.snippet || item.content || item.url;
      card.append(b, small); list.append(card);
    }
  }
  async function runSearch(query) {
    requireConnection();
    if (!query || !query.trim()) throw new Error('Enter a search query.');
    const data = await api('/api/search', 'POST', { query: query.trim() });
    data.provider ||= 'Google Chrome / Tavily';
    showSearch(data);
    showBrowser(data, true, false);
    const summaries = (data.results || []).map((x, i) => `${i + 1}. ${x.title}\n${x.url}\n${x.snippet || x.content || ''}`).join('\n\n');
    output(`${data.provider}: ${query}\n${data.answer ? data.answer + '\n\n' : ''}${summaries || data.notice || data.google_notice || data.page_text || 'No results.'}`);
    return data;
  }
  async function runGoogleSearch(query) {
    requireConnection();
    if (!query || !query.trim()) throw new Error('Enter a Google search query.');
    const data = await api('/api/google-search', 'POST', { query: query.trim() });
    showSearch(data);
    showBrowser(data, true, true);
    const summaries = (data.results || []).map((x, i) => `${i + 1}. ${x.title}\n${x.url}\n${x.snippet || ''}`).join('\n\n');
    output(`${data.provider || 'Google Chrome'}: ${query}\n${summaries || data.notice || data.page_text || 'Google returned no extractable results.'}`);
    return data;
  }
  async function runOpen(url) {
    requireConnection();
    const data = await api('/api/open', 'POST', { url });
    showBrowser(data, true, true);
    if (!data.screenshot) $('#lcPageText').textContent = data.text || data.error || '';
    output(`Opened: ${data.title || data.url}\n${data.url}\n\n${data.text || data.error || ''}`);
    return data;
  }
  async function refreshFiles() {
    requireConnection();
    const data = await api('/api/files');
    const list = $('#lcFiles'); list.replaceChildren();
    if (!data.files?.length) { list.textContent = 'No downloads yet.'; return; }
    for (const file of data.files) {
      const row = document.createElement('div'); row.className = 'lcFile';
      const b = document.createElement('b'); b.textContent = file.name;
      const small = document.createElement('small'); small.textContent = `${Math.ceil(file.size / 1024)} KB · backend workspace; never executed`;
      const btn = document.createElement('button'); btn.className = 'jwbtn'; btn.textContent = 'Save to this device';
      btn.onclick = async () => {
        try {
          const res = await fetch('/api/files/' + encodeURIComponent(file.name), { headers: { 'X-JAI-Token': token() } });
          if (!res.ok) throw new Error('Download failed');
          const blob = await res.blob(); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = file.name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1500);
        } catch (e) { output(e.message); }
      };
      row.append(b, small, btn); list.append(row);
    }
  }
  $('#lcConnect').onclick = async () => { try { await connect(); } catch (e) { setStatus(e.message, false); output(e.message); } };
  $('#lcSearch').onclick = async () => { try { await runSearch($('#lcQuery').value.trim()); } catch (e) { output(e.message); } };
  $('#lcGoogle').onclick = async () => { try { await runGoogleSearch($('#lcQuery').value.trim()); } catch (e) { output(e.message); } };
  $('#lcQuery').onkeydown = (e) => { if (e.key === 'Enter') $('#lcGoogle').click(); };
  $('#lcOpen').onclick = async () => { try { await runOpen($('#lcUrl').value.trim()); } catch (e) { output(e.message); } };
  $('#lcRefresh').onclick = async () => { try { await refreshFiles(); } catch (e) { output(e.message); } };
  const jwGo = $('#jwGo');
  if (jwGo) jwGo.onclick = async () => { $('#lcUrl').value = $('#jwUrl').value.trim(); try { await runOpen($('#lcUrl').value); } catch (e) { output(e.message); } };
  const jwNew = $('#jwNew');
  if (jwNew) { jwNew.textContent = 'Open in real Chrome'; jwNew.onclick = async () => { $('#lcUrl').value = $('#jwUrl').value.trim(); try { await runOpen($('#lcUrl').value); } catch (e) { output(e.message); } }; }
  $('#lcAsk').onclick = () => {
    const task = $('#lcTask').value.trim();
    if (!task) return output('Write the computer task first.');
    if (!connected) return output('Connect the Google Chrome computer first.');
    if (typeof window.send !== 'function') return output('This J AI build does not expose its chat send function.');
    $('#lcTask').value = '';
    window.__jaiComputerNext = true;
    window.send('Use the local computer to complete this task: ' + task);
  };

  // Opt-in tool loop: only messages sent through the Live Computer task button are computer-enabled.
  const originalAsk = window.ask;
  if (typeof originalAsk === 'function') {
    const prefix = '\n\nLIVE COMPUTER TOOL PROTOCOL (use only for the explicit computer task in this turn). You can request one action at a time by outputting exactly one fenced block named jai-computer-json, with valid JSON. Supported actions: {"action":"web_search","query":"..."} (real Google Chrome first, then server-side Tavily fallback); {"action":"google_search","query":"..."} (Google-only, opened in the real Chrome browser); {"action":"open_page","url":"https://..."}; {"action":"read_page"}; {"action":"download","url":"https://...","filename":"optional.ext"}; {"action":"click","selector":"CSS selector or text=Visible text"}; {"action":"fill","selector":"CSS selector","text":"non-secret text"}. After each tool result, decide the next useful action, up to 5 actions total, then answer the user. Use real Google Chrome first and the server-side Tavily fallback if needed; then open/read relevant public pages in the same Chrome session. Never request passwords, payment details, one-time codes, account/security changes, purchases, official submissions, or irreversible actions. Do not claim a download was run; files are saved only in the isolated workspace and are never executed. If a page requires login, CAPTCHA, or an action blocked by policy, explain that and ask the user to finish manually. For click/fill, the user will see a browser approval dialog. Do not output a tool block unless you need a real computer action.';
    window.ask = async function (chat, options) {
      const isComputer = !!window.__jaiComputerNext;
      window.__jaiComputerNext = false;
      if (!isComputer) return originalAsk.apply(this, arguments);
      if (!connected) throw new Error('Live Computer is not connected. Open the Workspace → Live Computer tab and connect with the token from the backend terminal.');
      const work = { ...chat, m: (chat.m || []).map(x => ({ ...x })) };
      let lastUser = -1;
      for (let i = work.m.length - 1; i >= 0; i--) if (work.m[i].r === 'u') { lastUser = i; break; }
      if (lastUser < 0) throw new Error('No user task found.');
      work.m[lastUser].t = (work.m[lastUser].t || '') + prefix;
      let reply = await originalAsk.call(this, work, options);
      for (let n = 0; n < 5; n++) {
        const match = String(reply?.c || '').match(/```jai-computer-json\s*([\s\S]*?)```/i);
        if (!match) return reply;
        let action;
        try { action = JSON.parse(match[1]); }
        catch { return { ...reply, c: String(reply.c).replace(match[0], '').trim() + '\n\nI could not parse the computer action, so I stopped safely.' }; }
        if (!action || !['web_search', 'google_search', 'open_page', 'read_page', 'download', 'click', 'fill'].includes(action.action)) {
          return { ...reply, c: String(reply.c).replace(match[0], '').trim() + '\n\nThat computer action is not supported, so I stopped safely.' };
        }
        let result;
        try {
          if (action.action === 'web_search') {
            result = await runSearch(action.query);
          } else if (action.action === 'google_search') {
            result = await runGoogleSearch(action.query);
          } else {
          let safeAction = { ...action, approved: false };
          result = await api('/api/agent/step', 'POST', safeAction);
          if (result.needs_confirmation) {
            const exactTarget = result.target || action.selector || action.text || '(unknown target)';
            const description = action.action === 'click'
              ? `J AI asks to click “${exactTarget}” on ${result.page_url}. No click has happened yet. Continue?`
              : `J AI asks to enter “${String(result.value_preview || '').slice(0, 160)}” into ${exactTarget} on ${result.page_url}. The form will not be submitted. Continue?`;
            if (window.confirm(description)) {
              safeAction = { ...action, approved: true };
              result = await api('/api/agent/step', 'POST', safeAction);
            } else {
              result = { ok: false, user_declined: true, note: 'The user declined the action. No click or text entry occurred.' };
            }
          }
          if (result.screenshot) {
            showBrowser(result, true, true);
            delete result.screenshot;
          }
          output(JSON.stringify(result, null, 2));
          if (action.action === 'download') await refreshFiles();
          }
        } catch (e) { result = { ok: false, error: e.message }; output(e.message); }
        const visibleReply = String(reply.c).replace(match[0], '').trim();
        const modelResult = result && typeof result === 'object' ? { ...result } : result;
        if (modelResult && typeof modelResult === 'object') delete modelResult.screenshot;
        work.m.push({ r: 'a', t: visibleReply || '[Computer action requested]' }, { r: 'u', t: 'COMPUTER_RESULT: ' + JSON.stringify(modelResult).slice(0, 18000) });
        reply = await originalAsk.call(this, work, options);
      }
      const remaining = String(reply?.c || '').replace(/```jai-computer-json[\s\S]*?```/ig, '').trim();
      return { ...reply, c: remaining + (remaining ? '\n\n' : '') + 'I stopped after five computer actions for this request.' };
    };
  }

  // Try reconnecting when the panel is opened if a saved token is present.
  const originalLiveTab = tabBtn.onclick;
  tabBtn.addEventListener('click', () => { if (savedToken && !connected) $('#lcConnect').click(); });
})();
