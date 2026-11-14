/* Germano AI 0.91 - Remote Control: lo stesso codice gira nel browser di qualsiasi dispositivo della rete locale
   (pagina /remote del Germano Server) e in Germano Client (che lo serve in locale e inoltra le richieste al server).
   Stesso paradigma della Dashboard: Harness AI (static/harness.js, con la Glass Window), Sanitizzazione manuale,
   Impostazioni, Guida. Tutto il testo ricevuto dal server viene inserito come testo (mai come HTML). */
'use strict';
(function () {
    const CLIENT = Boolean(window.GERMANO_CLIENT);
    const $ = id => document.getElementById(id);
    const MAX_FILES = 12;
    const K = { lang: 'germano_lang', opts: 'germano_rc_options', map: 'germano_rc_map', keys: 'germano_rc_keys', tab: 'germano_rc_tab' };
    let lang = 'it';
    let info = null;
    let protFiles = [];
    let restoreMap = {};
    let rendered = false;
    let keyOpen = '';           // servizio di cui e' aperto il modulo della chiave API (Impostazioni › AI e chiavi)
    let lastSig = '';           // disponibilita' delle AI all'ultimo rilevamento (aggiornamento automatico)
    let harness = null;
    let currentTab = 'harness';
    let update = null;          // Germano Client: stato degli aggiornamenti silenziosi
    const DETECT_MS = 12000;    // rilevamento automatico: ogni 12 secondi e quando la pagina torna in primo piano

    // ------------------------------------------------------------------ lingua
    function T(it, en) { return lang === 'en' ? en : it; }

    function initLang() {
        let saved = '';
        try { saved = localStorage.getItem(K.lang) || ''; } catch (e) { /* archiviazione non disponibile */ }
        const url = new URLSearchParams(location.search).get('lang');
        lang = url === 'en' || url === 'it' ? url : saved === 'en' || saved === 'it' ? saved
            : ((navigator.language || 'it').toLowerCase().startsWith('it') ? 'it' : 'en');
    }

    function setLang(value) {
        lang = value === 'en' ? 'en' : 'it';
        try { localStorage.setItem(K.lang, lang); } catch (e) { /* ignorato */ }
        document.cookie = `germano_lang=${lang}; path=/; SameSite=Strict; max-age=31536000`;
        applyLang();
        if (info) renderAll();
        if (harness) harness.setLang();
        renderUpdate();
        const frame = $('rcGuideFrame');
        if (frame) frame.dataset.loaded = '';
        if (currentTab === 'guide') loadGuide();
    }

    function applyLang() {
        document.documentElement.lang = lang;
        document.querySelectorAll('[data-en]').forEach(el => {
            if (el.dataset.it === undefined) el.dataset.it = el.innerHTML;
            el.innerHTML = lang === 'en' ? el.dataset.en : el.dataset.it;   // testi statici scritti nella pagina
        });
        document.querySelectorAll('[data-en-placeholder]').forEach(el => {
            if (el.dataset.itPlaceholder === undefined) el.dataset.itPlaceholder = el.placeholder;
            el.placeholder = lang === 'en' ? el.dataset.enPlaceholder : el.dataset.itPlaceholder;
        });
        $('rcIt').setAttribute('aria-pressed', String(lang === 'it'));
        $('rcEn').setAttribute('aria-pressed', String(lang === 'en'));
    }

    // ------------------------------------------------------------------ utilita'
    function el(tag, attrs, ...children) {
        const node = document.createElement(tag);
        Object.entries(attrs || {}).forEach(([k, v]) => {
            if (v === undefined || v === null || v === false) return;
            if (k === 'class') node.className = v;
            else if (k === 'text') node.textContent = v;
            else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
            else node.setAttribute(k, v === true ? '' : v);
        });
        children.flat().forEach(c => { if (c !== null && c !== undefined && c !== false) node.append(c instanceof Node ? c : String(c)); });
        return node;
    }

    function store(kind, key, value) {
        try {
            const s = kind === 'session' ? sessionStorage : localStorage;
            if (value === undefined) s.removeItem(key); else s.setItem(key, JSON.stringify(value));
        } catch (e) { /* archiviazione non disponibile: si continua senza */ }
    }

    function load(kind, key, fallback) {
        try {
            const raw = (kind === 'session' ? sessionStorage : localStorage).getItem(key);
            return raw ? JSON.parse(raw) : fallback;
        } catch (e) { return fallback; }
    }

    async function api(path, opts = {}) {
        const headers = Object.assign({ 'X-Germano-Lang': lang }, opts.headers || {});
        let body = opts.body;
        if (opts.json !== undefined) {
            headers['Content-Type'] = 'application/json';
            body = JSON.stringify(opts.json);
        }
        let r;
        try {
            r = await fetch(path, { method: opts.method || (body ? 'POST' : 'GET'), headers, body, credentials: 'same-origin',
                                    cache: 'no-store' });
        } catch (e) {
            return { ok: false, status: 0, data: { error: T('Germano Server non raggiungibile.', 'Germano Server unreachable.') } };
        }
        if (opts.raw) return { ok: r.ok, status: r.status, response: r };
        let data = {};
        try { data = await r.json(); } catch (e) { data = {}; }
        if (r.status === 401 && data.auth_required && !opts.noLoginRedirect) showLogin();
        return { ok: r.ok, status: r.status, data };
    }

    function maskedText(n) {
        return n === 1 ? T('1 dato oscurato', '1 item masked') : T(`${n} dati oscurati`, `${n} items masked`);
    }

    function errText(data, status) {
        return (data && (data.message || data.error)) || T(`Errore (HTTP ${status}).`, `Error (HTTP ${status}).`);
    }

    function banner(text, isError) {
        const b = $('rcBanner');
        b.hidden = !text;
        b.textContent = text || '';
        b.classList.toggle('err', Boolean(isError));
    }

    function toast(text, type = 'info', ms = 4200) {
        const box = $('rcToasts');
        const t = el('div', { class: `rc-toast ${type}`, text });
        box.append(t);
        setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 250); }, ms);
    }

    async function copyText(text) {
        try {
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(text);
                return true;
            }
        } catch (e) { /* si prova il metodo classico */ }
        const ta = el('textarea', { style: 'position:fixed;top:-1000px;opacity:0' });
        ta.value = text;
        document.body.append(ta);
        ta.select();
        let ok = false;
        try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
        ta.remove();
        return ok;
    }

    function downloadBlob(blob, name) {
        const a = el('a', { href: URL.createObjectURL(blob), download: name });
        document.body.append(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    }

    // Etichette di Germano: [PERSONA_1], [PERSONA 1], [ persona_1 ] (stessa regola del server)
    const TAG_RE = /\[\s*([A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ./]*(?:[ _]+[A-Za-zÀ-ÖØ-öø-ÿ./]+)*?)[ _]+(\d{1,7})\s*\]/g;
    function restoreTags(text, map) {
        let count = 0;
        const out = String(text || '').replace(TAG_RE, (m, base, num) => {
            const key = '[' + base.trim().replace(/[ _]+/g, '_').toUpperCase() + '_' + String(parseInt(num, 10)) + ']';
            if (Object.prototype.hasOwnProperty.call(map, key)) { count += 1; return map[key]; }
            return m;
        });
        return { text: out, count };
    }

    function rememberMap(map) {
        restoreMap = Object.assign(load('session', K.map, {}), map || {});
        store('session', K.map, restoreMap);
    }

    // ------------------------------------------------------------------ stato del server
    async function loadInfo(full = true) {
        const { ok, status, data } = await api('/api/remote/v1/info', { noLoginRedirect: true });
        if (!ok) {
            info = null;
            renderHeader();
            if (CLIENT) {
                showGate(errText(data, status));
            } else {
                banner(errText(data, status), true);
                $('rcApp').hidden = true;
                $('rcTabs').hidden = true;
            }
            return;
        }
        info = data;
        $('rcClientServerGate').hidden = true;
        renderHeader();
        if (info.auth.required && !info.auth.logged_in) {
            showLogin();
            return;
        }
        $('rcLogin').hidden = true;
        $('rcApp').hidden = false;
        $('rcTabs').hidden = false;
        if (!harness) mountHarness();
        const sig = availabilitySignature();
        if (full || !rendered) {
            renderAll();
        } else if (sig !== lastSig && !editingKey()) {
            // rilevamento automatico: un modello o una CLI appena installati (o spenti) aggiornano subito la pagina
            renderAi();
        }
        lastSig = sig;
        if (harness) harness.onEngineChange();
    }

    function mountHarness() {
        if (!window.GermanoHarness) return;
        harness = window.GermanoHarness.mount($('harnessRoot'), {
            host: CLIENT ? 'client' : 'remote',
            lang: () => lang,
            keysKey: K.keys,
            convKey: CLIENT ? 'germano_client_harness_v1' : 'germano_rc_harness_v1',
            persistDefault: CLIENT,                 // nel browser di un altro dispositivo: solo la sessione, se non scegli diversamente
            canStartEngine: false,
            engine: () => ({ ready: Boolean(info && info.server.engine_ready), running: Boolean(info && info.server.engine_running) }),
            options: optionsForRequest,
            toast: (m, t) => toast(m, t),
            onAuthRequired: showLogin,
            onCompliance: () => loadInfo(true),
            onKeysChanged: () => renderAi(),
        });
    }

    function renderHeader() {
        const s = (info && info.server) || {};
        $('rcDot').className = 'rc-dot ' + (!info ? 'err' : s.engine_ready ? 'ok' : 'warn');
        if (!info) {
            $('rcServerText').textContent = T('Germano Server non raggiungibile', 'Germano Server unreachable');
        } else {
            const engine = s.engine_ready ? T('motore pronto', 'engine ready')
                : s.engine_running ? T('motore in avvio', 'engine starting') : T('motore spento', 'engine stopped');
            $('rcServerText').textContent = `${s.name || 'Germano'} · v${info.version} · ${engine}`;
        }
        const prof = $('rcProfile');
        prof.hidden = !info;
        if (info) {
            const pa = info.profile === 'PA';
            prof.textContent = pa ? T('Profilo PA', 'PA profile') : T('Profilo PD', 'PD profile');
            prof.classList.toggle('pa', pa);
            prof.title = pa ? T('Pubblica Amministrazione: protezione massima imposta dal server.',
                                'Public Administration: maximum protection enforced by the server.')
                : T('Privati e professionisti: le opzioni si possono personalizzare.', 'Private use: options can be customized.');
        }
        const userBtn = $('rcUser');
        const auth = (info && info.auth) || {};
        userBtn.hidden = !(auth.enabled && auth.user);
        userBtn.textContent = auth.user ? `${auth.user} · ${T('Esci', 'Sign out')}` : '';
        $('rcSub').textContent = CLIENT ? 'Germano Client' : 'Remote Control';
        if (info && olderThan(info.version, '0.70')) {
            banner(T(`Il Germano Server è alla versione ${info.version}: i Chatbot e Agenti AI e la sanitizzazione dei file richiedono la 0.70 o successiva. Aggiorna il server.`,
                     `The Germano Server is at version ${info.version}: the AI Chatbot & Agents and file sanitization require 0.70 or later. Update the server.`), true);
        } else if (info && !s.engine_ready && info.auth.logged_in) {
            banner(T('Il motore di Germano sul server non è pronto: le richieste vengono bloccate e nessun dato esce. Riprova tra poco.',
                     'The Germano engine on the server is not ready: requests are blocked and no data leaves. Try again shortly.'), false);
        } else if (info) {
            banner('');
        }
    }

    // confronto di versioni «0.60», «0.70», «0.71-beta»: solo la parte numerica
    function olderThan(v, ref) {
        const a = String(v || '').split(/[^0-9]+/).filter(Boolean).map(Number);
        const b = String(ref).split('.').map(Number);
        if (!a.length) return false;
        for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
            const x = a[i] || 0, y = b[i] || 0;
            if (x !== y) return x < y;
        }
        return false;
    }

    function showLogin() {
        $('rcApp').hidden = true;
        $('rcTabs').hidden = true;
        if (!$('rcLogin').hidden) return;      // gia' aperto: non si tocca cio' che l'utente sta scrivendo
        $('rcLogin').hidden = false;
        $('rcLoginError').textContent = '';
        setTimeout(() => $('rcLoginUser').focus(), 30);
    }

    async function login(e) {
        e.preventDefault();
        const btn = $('rcLoginBtn');
        btn.disabled = true;
        $('rcLoginError').textContent = '';
        const { ok, status, data } = await api('/api/auth/login', {
            json: { username: $('rcLoginUser').value.trim(), password: $('rcLoginPass').value }, noLoginRedirect: true });
        btn.disabled = false;
        if (!ok) {
            $('rcLoginError').textContent = errText(data, status);
            return;
        }
        $('rcLoginPass').value = '';
        $('rcLogin').hidden = true;
        await loadInfo(true);
    }

    async function logout() {
        await api('/api/auth/logout', { method: 'POST', json: {}, noLoginRedirect: true });
        restoreMap = {};
        store('session', K.map);
        await loadInfo(true);
    }

    // ------------------------------------------------------------------ schede
    function selectTab(name, remember = true) {
        if (!['harness', 'sanitize', 'settings', 'guide'].includes(name)) name = 'harness';
        currentTab = name;
        document.body.dataset.tab = name;
        document.querySelectorAll('.rc-tabs [role="tab"]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
        document.querySelectorAll('.rc-view').forEach(p => { p.hidden = p.dataset.view !== name; });
        if (remember) store('session', K.tab, name);
        if (name === 'guide') loadGuide();
        if (name === 'settings') {
            loadInfo(false);
            if (CLIENT) {
                refreshUpdate();
                // indirizzo del server in uso (non si tocca cio' che l'utente sta scrivendo)
                api('/client/config').then(({ ok, data }) => {
                    if (ok && document.activeElement !== $('rcServerAddr')) $('rcServerAddr').value = data.server_url || '';
                });
            }
        }
        if (name === 'harness' && harness) harness.refreshTargets(false);
    }

    function loadGuide() {
        const frame = $('rcGuideFrame');
        const url = `/guide?lang=${lang}`;
        if (frame.dataset.loaded !== url) {
            frame.src = url;
            frame.dataset.loaded = url;
        }
    }

    function renderAll() {
        rendered = true;
        renderAi();
        renderOptions();
        renderConnect();
    }

    // ------------------------------------------------------------------ AI del server e chiavi
    const KIND = { cli: ['CLI', 'CLI'], app: ['applicazione', 'app'], service: ['modelli locali', 'local models'] };

    function renderAi() {
        if (!info) return;
        const tools = info.tools || [];
        const services = info.services || [];
        const usable = tools.filter(t => (t.remote || {}).usable);
        const others = tools.filter(t => !(t.remote || {}).usable);
        $('rcAiSummary').textContent = T(
            `${tools.length} AI rilevate sul server «${info.server.name}»` + (info.sharing ? '' : ' · condivisione delle AI del server disattivata'),
            `${tools.length} AIs detected on the server «${info.server.name}»` + (info.sharing ? '' : ' · sharing of the server AIs disabled'));
        const tl = $('rcTools');
        tl.replaceChildren();
        if (!usable.length) {
            tl.append(el('p', { class: 'rc-empty', text: info.sharing
                ? T('Nessuna AI eseguibile dal server: usa i servizi qui sotto.', 'No AI runnable by the server: use the services below.')
                : T('L\'amministratore non ha attivato la condivisione delle AI del server (Impostazioni › Modalità e rete). Puoi usare i servizi qui sotto con la tua chiave.',
                    'The administrator has not enabled sharing of the server AIs (Settings › Mode & network). You can use the services below with your own key.') }));
        }
        usable.forEach(t => tl.append(aiItem(t.name, `${t.vendor || ''}${t.version ? ' · v' + t.version : ''}`,
            [el('span', { class: 'rc-pill ok', text: T('eseguita dal server', 'run by the server') })],
            T('Senza strumenti né file: il server la esegue per te e il Proxy di Germano protegge i dati. Si sceglie nell\'Harness, in basso a destra.',
              'No tools or files: the server runs it for you and the Germano Proxy protects the data. Pick it in the Harness, bottom right.'), null, true)));

        const sl = $('rcServices');
        sl.replaceChildren();
        services.forEach(s => {
            const pills = [];
            let reason = null;
            let ready = s.available;
            const own = !s.local && s.key === 'user' && Boolean(deviceKey(s.id));
            if (s.local) {
                const none = s.reason === 'nessun modello installato';
                pills.push(el('span', { class: 'rc-pill ' + (s.available ? 'local' : 'warn'), text: s.available
                    ? T('locale sul server', 'local on the server') : none ? T('nessun modello installato', 'no model installed')
                    : T('non in esecuzione', 'not running') }));
                const models = s.models_detected ? (s.models || []) : [];
                if (s.available && models.length) {
                    reason = T(`Modelli rilevati (${models.length}): `, `Detected models (${models.length}): `) +
                        models.slice(0, 8).join(', ') + (models.length > 8 ? '…' : '');
                } else if (!s.available) {
                    reason = none ? T('Installa un modello sul server: compare da solo, senza ricaricare la pagina.',
                                      'Install a model on the server: it shows up by itself, without reloading the page.')
                        : T('Avvialo sul server: Germano lo rileva da solo entro pochi secondi.',
                            'Start it on the server: Germano detects it by itself within a few seconds.');
                }
            } else if (s.key === 'server') {
                pills.push(el('span', { class: 'rc-pill ok', text: T('chiave del server', 'server key') }));
            } else if (own) {
                pills.push(el('span', { class: 'rc-pill ok', text: T('chiave su questo dispositivo', 'key on this device') }));
            } else {
                pills.push(el('span', { class: 'rc-pill', text: T('serve la tua chiave', 'needs your key') }));
                ready = false;
            }
            const sub = (s.formats || []).map(f => f === 'openai' ? T('formato OpenAI', 'OpenAI format') : T('formato Anthropic', 'Anthropic format')).join(' · ');
            const keyBtn = !s.local && s.key === 'user' ? el('button', { class: 'rc-btn rc-btn-sec rc-btn-sm', type: 'button',
                text: own ? T('Chiave', 'Key') : T('Inserisci la chiave', 'Enter the key'),
                'aria-expanded': String(keyOpen === s.id), onclick: () => {
                    keyOpen = keyOpen === s.id ? '' : s.id;
                    renderAi();
                    const input = keyOpen && document.querySelector('#rcServices .rc-keyform input[type="password"]');
                    if (input) input.focus();
                } }) : null;
            const card = aiItem(s.name, sub, pills, reason, keyBtn, ready);
            if (keyOpen === s.id && keyBtn) card.append(keyForm(s));
            sl.append(card);
        });

        const ol = $('rcOthers');
        ol.replaceChildren();
        $('rcOthersBox').hidden = !others.length;
        others.forEach(t => {
            const rm = t.remote || {};
            const kind = KIND[t.kind] ? T(KIND[t.kind][0], KIND[t.kind][1]) : (t.kind || '');
            ol.append(aiItem(t.name, `${t.vendor || ''} · ${kind}${t.version ? ' · v' + t.version : ''}`,
                [el('span', { class: 'rc-pill warn', text: T('non da qui', 'not from here') })], rm.reason || '', null, false));
        });
    }

    function aiItem(name, sub, pills, reason, button, usable) {
        return el('div', { class: 'rc-item' + (usable ? ' usable' : '') },
            el('div', { class: 'rc-item-head' }, el('div', {}, el('div', { class: 'rc-item-name', text: name }),
                sub ? el('div', { class: 'rc-item-sub', text: sub }) : null), el('div', { class: 'rc-row' }, pills, button)),
            reason ? el('div', { class: 'rc-item-reason', text: reason }) : null);
    }

    // Chiave API di un servizio via API inserita dall'utente: resta su questo dispositivo (sessione o «ricorda») e
    // viaggia solo con le richieste; con la chiave il servizio diventa selezionabile nell'Harness.
    function keyForm(s) {
        const input = el('input', { type: 'password', class: 'rc-input', autocomplete: 'off', spellcheck: 'false',
            'aria-label': T(`Chiave API di ${s.name}`, `${s.name} API key`), placeholder: T('chiave API del servizio', 'service API key') });
        input.value = deviceKey(s.id);
        const remember = el('input', { type: 'checkbox' });
        remember.checked = Boolean(load('local', K.keys, {})[s.id]);
        const msg = el('span', { class: 'rc-muted', role: 'status' });
        const save = () => {
            const key = input.value.trim();
            if (!/^[\x21-\x7e]{8,512}$/.test(key)) {
                msg.textContent = T('Chiave non valida (almeno 8 caratteri, senza spazi).', 'Invalid key (at least 8 characters, no spaces).');
                return;
            }
            setDeviceKey(s.id, key, remember.checked);
            keyOpen = '';
            renderAi();
            if (harness) { harness.renderPicker(); harness.renderShield(); }
            toast(T('Chiave salvata: il servizio ora si può scegliere nell\'Harness.', 'Key saved: the service can now be chosen in the Harness.'), 'success');
        };
        input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); save(); } });
        return el('div', { class: 'rc-keyform' },
            el('div', { class: 'rc-row rc-tight' }, input,
                el('button', { class: 'rc-btn rc-btn-sm', type: 'button', text: T('Salva', 'Save'), onclick: save }),
                deviceKey(s.id) ? el('button', { class: 'rc-btn rc-btn-sec rc-btn-sm', type: 'button', text: T('Togli', 'Remove'),
                    onclick: () => { setDeviceKey(s.id, ''); keyOpen = ''; renderAi(); if (harness) { harness.renderPicker(); harness.renderShield(); } } }) : null),
            el('label', { class: 'rc-check' }, remember, el('span', { text: T('Ricorda la chiave su questo dispositivo (altrimenti si dimentica chiudendo la pagina)',
                'Remember the key on this device (otherwise it is forgotten when the page is closed)') })), msg);
    }

    function setDeviceKey(id, key, remember) {
        const local = load('local', K.keys, {});
        const session = load('session', K.keys, {});
        delete local[id];
        delete session[id];
        if (key) (remember ? local : session)[id] = key;
        store('local', K.keys, local);
        store('session', K.keys, session);
    }

    function deviceKey(id) {
        return Object.assign({}, load('local', K.keys, {}), load('session', K.keys, {}))[id] || '';
    }

    // l'utente sta scrivendo una chiave: il rilevamento periodico non ridisegna la sezione (riprova al giro dopo)
    function editingKey() {
        const a = document.activeElement;
        return Boolean(a && a.closest && a.closest('.rc-keyform'));
    }

    // Impronta della disponibilita': se non cambia, il rilevamento periodico non tocca la pagina
    function availabilitySignature() {
        if (!info) return '';
        return JSON.stringify([(info.runnable || []).map(r => [r.id, r.usable]),
            (info.services || []).map(s => [s.id, s.available, s.key, s.models_detected ? s.models : null]),
            (info.tools || []).map(t => [t.id, (t.remote || {}).usable])]);
    }

    function optionsForRequest() {
        if (!info || info.locked) return null;
        return load('local', K.opts, null);
    }

    // ------------------------------------------------------------------ sanitizzazione manuale: testo
    function renderFiles(box, list, onRemove) {
        box.replaceChildren();
        list.forEach((f, i) => box.append(el('span', { class: 'rc-file' }, el('span', { text: `📄 ${f.name}` }),
            el('button', { type: 'button', 'aria-label': T('Togli', 'Remove'), text: '✕', onclick: () => onRemove(i) }))));
    }

    function addFiles(list, files, rerender) {
        for (const f of files) {
            if (list.length >= MAX_FILES) {
                toast(T(`Al massimo ${MAX_FILES} allegati per richiesta.`, `At most ${MAX_FILES} attachments per request.`), 'warn');
                break;
            }
            list.push(f);
        }
        rerender();
    }

    function removeProtFile(i) { protFiles.splice(i, 1); renderFiles($('rcProtFiles'), protFiles, removeProtFile); }

    async function protect(e) {
        e.preventDefault();
        const text = $('rcProtText').value.trim();
        if (!text && !protFiles.length) return;
        const fd = new FormData();
        fd.append('prompt', text);
        const opts = optionsForRequest();
        if (opts) fd.append('options', JSON.stringify(opts));
        protFiles.forEach(f => fd.append('files', f, f.name));
        $('rcProtBtn').disabled = true;
        const { ok, status, data } = await api('/api/remote/v1/protect', { method: 'POST', body: fd });
        $('rcProtBtn').disabled = false;
        $('rcProtOut').hidden = false;
        if (!ok || data.status !== 'success') {
            $('rcProtMeta').textContent = '⚠️ ' + errText(data, status);
            $('rcProtText2').textContent = '';
            return;
        }
        rememberMap(data.map);
        const skipped = (data.attachments || []).filter(a => !a.textual).map(a => a.name);
        $('rcProtMeta').textContent = '🛡️ ' + maskedText(data.entity_count) +
            ((data.labels || []).length ? ' · ' + data.labels.slice(0, 12).join(', ') + ((data.labels || []).length > 12 ? '…' : '') : '') +
            (skipped.length ? ' · ' + T('senza testo (non inclusi): ', 'no text (not included): ') + skipped.join(', ') : '');
        $('rcProtText2').textContent = data.protected || '';
    }

    function restore() {
        restoreMap = load('session', K.map, {});
        const res = restoreTags($('rcRestoreIn').value, restoreMap);
        $('rcRestoreOut').hidden = false;
        $('rcRestoreOut').textContent = res.text;
        $('rcRestoreInfo').textContent = T(`${res.count} etichette ripristinate`, `${res.count} tags restored`) +
            (Object.keys(restoreMap).length ? '' : T(' (proteggi prima un testo o un file da questa pagina)', ' (protect a text or a file from this page first)'));
    }

    // ------------------------------------------------------------------ sanitizzazione manuale: file interi
    function b64ToBlob(b64) {
        const bin = atob(b64 || '');
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
        return new Blob([bytes], { type: 'application/octet-stream' });
    }

    // Dalla 0.80: le registrazioni audio tornano come trascrizione, gli archivi compressi tornano ricomposti
    function slowKind(f) {
        const n = (f && f.name) || '';
        if (/\.(mp3|wav|m4a|ogg|oga|opus|flac|aac|wma|amr|aiff?|m4b|mka|weba)$/i.test(n)) return 'audio';
        if (/\.(zip|tar|tgz|tbz2?|txz|gz|bz2|xz|7z|rar)$/i.test(n)) return 'archive';
        return '';
    }

    async function anonymizeFiles(files) {
        const box = $('rcFileResults');
        for (const f of files) {
            const row = el('div', { class: 'rc-file-res' }, el('span', { class: 'rc-file-res-main' },
                el('span', { class: 'rc-file-res-name', text: f.name }),
                el('span', { class: 'rc-file-res-sub', text: slowKind(f) === 'audio'
                    ? T('Trascrizione e protezione in corso sul Germano Server… (circa un terzo della durata della registrazione)', 'Transcribing and protecting on the Germano Server… (about one third of the recording length)')
                    : (slowKind(f) === 'archive'
                        ? T('Apertura sicura dell\'archivio e protezione di ogni file sul Germano Server…', 'Opening the archive safely and protecting each file on the Germano Server…')
                        : T('Protezione in corso sul Germano Server…', 'Protecting on the Germano Server…')) })));
            box.prepend(row);
            const fd = new FormData();
            fd.append('file', f, f.name);
            const opts = optionsForRequest();
            if (opts) fd.append('options', JSON.stringify(opts));
            const { ok, status, data } = await api('/api/remote/v1/anonymize_file', { method: 'POST', body: fd });
            const sub = row.querySelector('.rc-file-res-sub');
            if (!ok || data.status !== 'success') {
                row.classList.add('err');
                sub.textContent = '⚠️ ' + errText(data, status);
                continue;
            }
            rememberMap(data.map);
            row.classList.add('ok');
            const name = `anonimizzato_${data.filename || f.name}`;
            sub.textContent = '🛡️ ' + maskedText(data.entity_count) +
                ((data.labels || []).length ? ' · ' + data.labels.slice(0, 8).join(', ') : '') +
                ((data.notes || []).length ? ' · ' + data.notes.slice(0, 2).join(' · ') : '');
            const blob = b64ToBlob(data.data_b64);
            row.append(el('button', { class: 'rc-btn rc-btn-sm', type: 'button', text: T('⬇ Scarica', '⬇ Download'), onclick: () => downloadBlob(blob, name) }));
        }
    }

    async function restoreFile(f) {
        restoreMap = load('session', K.map, {});
        if (!Object.keys(restoreMap).length) {
            toast(T('Nessuna corrispondenza su questo dispositivo: proteggi prima un testo o un file da questa pagina.',
                    'No mappings on this device: protect a text or a file from this page first.'), 'warn', 6000);
            return;
        }
        const fd = new FormData();
        fd.append('file', f, f.name);
        fd.append('map', JSON.stringify(restoreMap));
        $('rcRestoreFileInfo').textContent = T('Ripristino in corso…', 'Restoring…');
        const { ok, status, response } = await api('/api/remote/v1/restore_file', { method: 'POST', body: fd, raw: true });
        if (!ok) {
            let msg = '';
            try { msg = errText(await response.json(), status); } catch (e) { msg = `HTTP ${status}`; }
            $('rcRestoreFileInfo').textContent = '⚠️ ' + msg;
            return;
        }
        const blob = await response.blob();
        // il server indica il nome quando l'estensione cambia (es. un archivio RAR, non ricreabile, torna come ZIP)
        let outName = f.name.startsWith('ripristinato_') ? f.name : 'ripristinato_' + f.name;
        const cd = response.headers.get('Content-Disposition') || '';
        const m = /filename\*=UTF-8''([^;]+)/i.exec(cd) || /filename="?([^";]+)"?/i.exec(cd);
        if (m) { try { outName = decodeURIComponent(m[1]); } catch (e) { outName = m[1]; } }
        downloadBlob(blob, outName);
        $('rcRestoreFileInfo').textContent = T('✅ File ripristinato e scaricato.', '✅ File restored and downloaded.');
    }

    // ------------------------------------------------------------------ opzioni
    const MODEL_LABELS = {
        enable_model_velvet: ['Velvet Privacy Filter (modello contestuale)', 'Velvet Privacy Filter (contextual model)'],
        enable_model_italian_ner: ['Italian NER XXL (58 classi)', 'Italian NER XXL (58 classes)'],
        enable_regex: ['Regole validate (RegEx: codici fiscali, IBAN, carte…)', 'Validated rules (RegEx: tax codes, IBAN, cards…)'],
    };
    const CATEGORY_LABELS = {
        censor_person: ['Nomi e cognomi', 'Names'], censor_profession: ['Professioni e titoli', 'Professions and titles'],
        censor_address: ['Indirizzi', 'Addresses'], censor_cadastre: ['Dati catastali', 'Land registry data'],
        censor_cf_iva: ['Codici fiscali e P.IVA', 'Tax codes and VAT numbers'], censor_email: ['Email e PEC', 'Email and certified email'],
        censor_phone: ['Telefoni', 'Phone numbers'], censor_account: ['IBAN, conti e carte', 'IBAN, accounts and cards'],
        censor_financial: ['Importi e dati finanziari', 'Amounts and financial data'], censor_date: ['Date', 'Dates'],
        censor_org: ['Aziende ed enti', 'Companies and organizations'], censor_plates_docs: ['Targhe e documenti', 'Plates and ID documents'],
        censor_medical: ['Dati sanitari (art. 9 GDPR)', 'Health data (GDPR art. 9)'], censor_medicine: ['Farmaci e terapie', 'Medicines and therapies'],
        censor_legal: ['Dati giudiziari (art. 10 GDPR)', 'Judicial data (GDPR art. 10)'], censor_civil_status: ['Stato civile', 'Civil status'],
        censor_secret: ['Password e segreti', 'Passwords and secrets'], censor_url: ['URL e indirizzi IP', 'URLs and IP addresses'],
    };
    const MASK_LABELS = {
        numbered: ['Etichette numerate [PERSONA_1] — i dati tornano nella risposta', 'Numbered tags [PERSONA_1] — data comes back in the answer'],
        generic: ['Etichette generiche [PERSONA] — irreversibile', 'Generic tags [PERSONA] — irreversible'],
        blackout: ['Oscuramento ████ — irreversibile', 'Blackout ████ — irreversible'],
    };

    function currentOptions() {
        const saved = !info.locked && load('local', K.opts, null);
        return Object.assign({}, info.options || {}, saved || {});
    }

    function renderOptions() {
        const locked = Boolean(info.locked);
        const lock = $('rcLock');
        lock.hidden = !locked;
        lock.textContent = !locked ? '' : info.lock_reason === 'pa'
            ? T('🔒 Bloccato dal profilo di conformità PA del Server: le regole di protezione e i filtri di privacy sono imposti centralmente e non possono essere alterati dal client.',
                '🔒 Locked by the Server\'s PA compliance profile: protection rules and privacy filters are enforced centrally and cannot be changed by the client.')
            : T('🔒 Bloccato dall\'amministratore del Server (lock_settings): le opzioni di elaborazione non possono essere modificate dal client.',
                '🔒 Locked by the Server administrator (lock_settings): processing options cannot be changed by the client.');
        $('rcOptions').disabled = locked;
        const o = currentOptions();
        $('optThreshold').value = String(o.ai_threshold || 0);
        $('optThresholdOut').textContent = Number(o.ai_threshold || 0).toFixed(2);
        const models = $('optModels');
        models.replaceChildren();
        Object.keys(MODEL_LABELS).forEach(k => models.append(checkbox(k, MODEL_LABELS[k], o[k] !== false)));
        const cats = $('optCategories');
        cats.replaceChildren();
        Object.keys(CATEGORY_LABELS).forEach(k => cats.append(checkbox(k, CATEGORY_LABELS[k], o[k] !== false)));
        const mask = $('optMasking');
        mask.replaceChildren();
        Object.keys(MASK_LABELS).forEach(k => mask.append(el('label', {}, el('input', { type: 'radio', name: 'optMask', value: k,
            checked: (o.masking || 'numbered') === k }), el('span', { text: T(...MASK_LABELS[k]) }))));
        $('optMsg').textContent = !locked && load('local', K.opts, null)
            ? T('Opzioni personalizzate in uso su questo dispositivo.', 'Custom options in use on this device.') : '';
    }

    function checkbox(key, labels, checked) {
        return el('label', {}, el('input', { type: 'checkbox', 'data-opt': key, checked }), el('span', { text: T(...labels) }));
    }

    function gatherOptions() {
        const o = { ai_threshold: Number($('optThreshold').value) };
        document.querySelectorAll('#rcOptions [data-opt]').forEach(c => { o[c.dataset.opt] = c.checked; });
        const m = document.querySelector('#rcOptions input[name="optMask"]:checked');
        o.masking = m ? m.value : 'numbered';
        return o;
    }

    async function saveOptions() {
        $('optSave').disabled = true;
        const { ok, status, data } = await api('/api/remote/v1/options', { json: { options: gatherOptions() } });
        $('optSave').disabled = false;
        if (status === 403) {
            await loadInfo(true);
            $('optMsg').textContent = errText(data, status);
            return;
        }
        if (!ok) { $('optMsg').textContent = errText(data, status); return; }
        store('local', K.opts, data.options);
        renderOptions();
        $('optMsg').textContent = T('✅ Salvate: valgono per le tue prossime richieste da questo dispositivo.',
                                    '✅ Saved: they apply to your next requests from this device.');
    }

    function resetOptions() {
        store('local', K.opts);
        renderOptions();
        $('optMsg').textContent = T('Si usano le opzioni del server.', 'The server options are used.');
    }

    // ------------------------------------------------------------------ collega gli strumenti
    function renderConnect(token) {
        const p = info.proxy || {};
        const needToken = Boolean(p.session_in_url);
        $('rcTokenBox').hidden = !needToken;
        const base = token ? `${p.base}/g/${token}` : p.base;
        const rows = [[T('Formato OpenAI (Codex, Qwen Code, OpenCode, Aider, SDK OpenAI)', 'OpenAI format (Codex, Qwen Code, OpenCode, Aider, OpenAI SDK)'), `${base}/v1`],
                      [T('Formato Anthropic (Claude Code, SDK Anthropic)', 'Anthropic format (Claude Code, Anthropic SDK)'), base]];
        (info.services || []).filter(s => !s.local).forEach(s => {
            if ((s.formats || []).includes('openai')) rows.push([`${s.name} — ${T('formato OpenAI', 'OpenAI format')}`, `${base}/p/${s.id}/v1`]);
            if ((s.formats || []).includes('anthropic')) rows.push([`${s.name} — ${T('formato Anthropic', 'Anthropic format')}`, `${base}/p/${s.id}`]);
        });
        const table = $('rcUrls');
        table.replaceChildren(el('tr', {}, el('th', { text: T('Servizio', 'Service') }), el('th', { text: 'Base URL' })));
        rows.forEach(([label, url]) => table.append(el('tr', {}, el('td', { text: label }),
            el('td', {}, el('code', { text: needToken && !token ? url.replace(p.base, p.base + '/g/<token>') : url })))));
    }

    async function createToken() {
        const { ok, status, data } = await api('/api/remote/v1/token', { method: 'POST', json: {} });
        if (!ok) { $('rcTokenInfo').textContent = errText(data, status); return; }
        $('rcTokenInfo').textContent = T('Token creato (valido 30 giorni dall\'ultimo uso; non viene mostrato di nuovo): è già inserito negli indirizzi qui sotto.',
                                         'Token created (valid 30 days from last use; it is not shown again): it is already in the addresses below.');
        renderConnect(data.token);
    }

    // ------------------------------------------------------------------ Germano Client: collegamento al server
    function showGate(message) {
        $('rcApp').hidden = true;
        $('rcTabs').hidden = true;
        $('rcLogin').hidden = true;
        $('rcClientServerGate').hidden = false;
        banner(message, true);
        api('/client/config').then(({ ok, data }) => { if (ok && !$('rcGateAddr').value) $('rcGateAddr').value = data.server_url || ''; });
    }

    async function saveClientServer(addr) {
        const { ok, status, data } = await api('/client/config', { json: { server: addr } });
        if (!ok) { banner(errText(data, status), true); return; }
        banner('');
        await loadInfo(true);
    }

    async function findServers(listId, inputId) {
        const list = $(listId);
        list.replaceChildren(el('p', { class: 'rc-empty', text: T('Ricerca in corso…', 'Searching…') }));
        const { ok, data } = await api('/client/discover');
        list.replaceChildren();
        const servers = (ok && data.servers) || [];
        if (!servers.length) {
            list.append(el('p', { class: 'rc-empty', text: T('Nessun Germano Server trovato: sul server scegli la modalità Server nelle Impostazioni, oppure scrivi l\'indirizzo.',
                'No Germano Server found: on the server choose Server mode in Settings, or type the address.') }));
            return;
        }
        servers.forEach(s => list.append(aiItem(s.name || s.url, `${s.url} · v${s.version || '?'}`,
            [el('span', { class: 'rc-pill ' + (s.engine_ready ? 'ok' : 'warn'), text: s.engine_ready ? T('motore pronto', 'engine ready') : T('motore non pronto', 'engine not ready') })],
            s.auth_required ? T('Richiede utente e password.', 'Requires user name and password.') : '',
            el('button', { class: 'rc-btn rc-btn-sm', type: 'button', text: T('Usa', 'Use'), onclick: () => { $(inputId).value = s.url; saveClientServer(s.url); } }), true)));
    }

    // ------------------------------------------------------------------ Germano Client: aggiornamenti silenziosi
    async function refreshUpdate() {
        if (!CLIENT) return;
        const { ok, data } = await api('/client/update/status');
        if (ok) { update = data; renderUpdate(); }
    }

    function renderUpdate() {
        if (!CLIENT || !update) return;
        const u = update;
        const ready = u.state === 'ready';
        $('rcUpdateWrap').hidden = !ready;
        $('rcSettingsDot').hidden = !ready;
        $('rcUpdatePillText').textContent = u.manual ? T('Aggiornamento pronto', 'Update ready') : T('Riavvia per aggiornare', 'Restart to update');
        const box = $('rcUpd');
        let cls = 'rc-upd', ico = 'ⓘ', title = '', sub = '', progress = false, install = false;
        const pct = u.progress && u.progress.total ? Math.min(100, Math.round(100 * u.progress.done / u.progress.total)) : 0;
        const when = u.checked_at ? new Date(u.checked_at * 1000).toLocaleString(lang === 'en' ? 'en-GB' : 'it-IT') : '';
        if (u.state === 'uptodate') { cls += ' is-ok'; ico = '✓'; title = T(`Germano AI Client è aggiornato (v${u.current})`, `Germano AI Client is up to date (v${u.current})`); sub = when ? T(`Ultimo controllo silenzioso: ${when}`, `Last silent check: ${when}`) : ''; }
        else if (u.state === 'checking') { cls += ' is-busy'; ico = '…'; title = T('Controllo degli aggiornamenti…', 'Checking for updates…'); }
        else if (u.state === 'downloading') { cls += ' is-busy'; ico = '↓'; title = T('Download dell\'aggiornamento in background…', 'Downloading the update in the background…'); sub = `${pct}%`; progress = true; }
        else if (ready) {
            cls += ' is-ready'; ico = '⟳'; install = true;
            title = u.manual ? T(`La versione ${u.latest} è pronta da installare`, `Version ${u.latest} is ready to install`)
                             : T(`Riavvia Germano Client per completare l'aggiornamento alla versione ${u.latest}`, `Restart Germano Client to finish updating to version ${u.latest}`);
            sub = u.manual ? (u.install_command || u.package || '') : T('Si applica da solo al prossimo avvio, in pochi secondi.', 'It is applied by itself at the next start, in a few seconds.');
        } else if (u.state === 'error') { cls += ' is-error'; ico = '!'; title = T('Ultimo tentativo non riuscito', 'Last attempt failed'); sub = u.error || ''; }
        else if (u.online === false) { title = T('Nessuna connessione a Internet segnalata dal sistema', 'No Internet connection reported by the system'); }
        else { title = `Germano AI Client v${u.current}`; sub = T('Controllo silenzioso automatico ogni 6 ore.', 'Automatic silent check every 6 hours.'); }
        box.className = cls;
        $('rcUpdIco').textContent = ico;
        $('rcUpdTitle').textContent = title;
        $('rcUpdSub').textContent = sub;
        $('rcUpdProgress').hidden = !progress;
        $('rcUpdBar').style.width = `${pct}%`;
        $('rcUpdInstall').hidden = !install;
        $('rcUpdInstall').textContent = u.manual ? T('Apri il pacchetto', 'Open the package') : T('Riavvia per applicare l\'aggiornamento', 'Restart to apply the update');
        $('rcUpdAuto').checked = u.auto_update !== false;
        $('rcUpdCheckBox').checked = u.check_updates !== false;
    }

    async function installUpdate() {
        $('rcUpdatePop').hidden = true;
        const { ok, status, data } = await api('/client/update/install', { method: 'POST', json: {} });
        if (!ok) { toast(errText(data, status), 'error'); return; }
        toast(data.how === 'opened' ? T('Pacchetto aperto con il programma di installazione del sistema.', 'Package opened with the system installer.')
                                    : T('Germano Client si riavvia per aggiornarsi: tornerà tra pochi secondi.', 'Germano Client is restarting to update: it will be back in a few seconds.'), 'info', 8000);
    }

    // ------------------------------------------------------------------ avvio
    function bind() {
        $('rcIt').addEventListener('click', () => setLang('it'));
        $('rcEn').addEventListener('click', () => setLang('en'));
        $('rcUser').addEventListener('click', logout);
        $('rcLoginForm').addEventListener('submit', login);
        document.querySelectorAll('.rc-tabs [role="tab"]').forEach(b => b.addEventListener('click', () => selectTab(b.dataset.tab)));
        $('rcAiRefresh').addEventListener('click', async () => { await loadInfo(true); if (harness) harness.refreshTargets(true); });
        $('rcProtectForm').addEventListener('submit', protect);
        $('rcProtAttach').addEventListener('change', e => { addFiles(protFiles, e.target.files, () => renderFiles($('rcProtFiles'), protFiles, removeProtFile)); e.target.value = ''; });
        $('rcProtCopy').addEventListener('click', async () => {
            const ok = await copyText($('rcProtText2').textContent);
            toast(ok ? T('Testo protetto copiato.', 'Protected text copied.') : T('Seleziona e copia a mano.', 'Select and copy by hand.'), ok ? 'success' : 'warn', 2500);
        });
        $('rcRestoreBtn').addEventListener('click', restore);
        // file da anonimizzare: trascinamento o scelta
        const drop = $('rcFileDrop');
        const hasFiles = e => Array.from((e.dataTransfer && e.dataTransfer.types) || []).includes('Files');
        ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { if (!hasFiles(e)) return; e.preventDefault(); drop.classList.add('is-over'); }));
        drop.addEventListener('dragleave', e => { if (!drop.contains(e.relatedTarget)) drop.classList.remove('is-over'); });
        drop.addEventListener('drop', e => { e.preventDefault(); drop.classList.remove('is-over'); anonymizeFiles(Array.from(e.dataTransfer.files || []).slice(0, 50)); });
        drop.addEventListener('click', e => { if (!e.target.closest('label')) $('rcFilePick').click(); });
        drop.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('rcFilePick').click(); } });
        $('rcFilePick').addEventListener('change', e => { anonymizeFiles(Array.from(e.target.files || [])); e.target.value = ''; });
        $('rcRestoreFilePick').addEventListener('change', e => { const f = (e.target.files || [])[0]; if (f) restoreFile(f); e.target.value = ''; });
        window.addEventListener('dragover', e => e.preventDefault());
        window.addEventListener('drop', e => e.preventDefault());
        $('optThreshold').addEventListener('input', () => { $('optThresholdOut').textContent = Number($('optThreshold').value).toFixed(2); });
        $('optSave').addEventListener('click', saveOptions);
        $('optReset').addEventListener('click', resetOptions);
        $('rcTokenBtn').addEventListener('click', createToken);
        // Germano Client
        $('rcServerSave').addEventListener('click', () => saveClientServer($('rcServerAddr').value.trim()));
        $('rcServerFind').addEventListener('click', () => findServers('rcServerList', 'rcServerAddr'));
        $('rcGateSave').addEventListener('click', () => saveClientServer($('rcGateAddr').value.trim()));
        $('rcGateFind').addEventListener('click', () => findServers('rcGateList', 'rcGateAddr'));
        $('rcUpdCheck').addEventListener('click', async () => { await api('/client/update/check', { method: 'POST', json: {} }); setTimeout(refreshUpdate, 1500); });
        $('rcUpdInstall').addEventListener('click', installUpdate);
        $('rcUpdateRestart').addEventListener('click', installUpdate);
        $('rcUpdateLater').addEventListener('click', () => { $('rcUpdatePop').hidden = true; });
        $('rcUpdatePill').addEventListener('click', () => {
            const u = update || {};
            $('rcUpdatePopTitle').textContent = T(`Germano AI Client ${u.latest || ''} è pronto`, `Germano AI Client ${u.latest || ''} is ready`);
            $('rcUpdatePopText').textContent = u.manual ? T('Il pacchetto è stato scaricato in background: aprilo quando vuoi.', 'The package was downloaded in the background: open it whenever you want.')
                : T('Riavvia per applicarlo: pochi secondi, poi Germano Client si riapre da solo. Altrimenti si applica al prossimo avvio.',
                    'Restart to apply it: a few seconds, then Germano Client reopens by itself. Otherwise it is applied at the next start.');
            $('rcUpdateRestart').textContent = u.manual ? T('Apri il pacchetto', 'Open the package') : T('Riavvia ora', 'Restart now');
            $('rcUpdatePop').hidden = !$('rcUpdatePop').hidden;
        });
        ['rcUpdAuto', 'rcUpdCheckBox'].forEach(id => $(id).addEventListener('change', async () => {
            const { ok, data } = await api('/client/update/settings', { json: { auto_update: $('rcUpdAuto').checked, check_updates: $('rcUpdCheckBox').checked } });
            if (ok) { update = data; renderUpdate(); }
        }));
        document.addEventListener('visibilitychange', () => { if (!document.hidden) loadInfo(false); });
        window.addEventListener('focus', () => loadInfo(false));
    }

    if (CLIENT) document.body.classList.add('is-client');
    initLang();
    applyLang();
    bind();
    restoreMap = load('session', K.map, {});
    selectTab(load('session', K.tab, 'harness'), false);
    loadInfo(true);
    setInterval(() => { if (!document.hidden) loadInfo(false); }, DETECT_MS);
    if (CLIENT) { refreshUpdate(); setInterval(refreshUpdate, 30000); }
})();
