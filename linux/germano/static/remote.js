/* Germano AI - Remote Control: lo stesso codice gira nel browser di qualsiasi dispositivo della rete locale
   (pagina /remote del Germano Server) e in Germano Client (che lo serve in locale e inoltra le richieste al server).
   Tutto il testo ricevuto dal server viene inserito come testo (mai come HTML). */
'use strict';
(function () {
    const CLIENT = Boolean(window.GERMANO_CLIENT);
    const $ = id => document.getElementById(id);
    const MAX_FILES = 12;
    const K = { lang: 'germano_lang', opts: 'germano_rc_options', conv: 'germano_rc_conv', map: 'germano_rc_map',
                keys: 'germano_rc_keys', target: 'germano_rc_target', model: 'germano_rc_model' };
    let lang = 'it';
    let info = null;
    let chatFiles = [];
    let protFiles = [];
    let conv = [];
    let restoreMap = {};
    let rendered = false;
    let keyOpen = '';           // servizio di cui e' aperto il modulo della chiave API (scheda AI)
    let lastSig = '';           // disponibilita' delle AI all'ultimo rilevamento (aggiornamento automatico)
    const DETECT_MS = 12000;    // rilevamento automatico: ogni 12 secondi e quando la pagina torna in primo piano

    // ------------------------------------------------------------------ lingua
    function T(it, en) { return lang === 'en' ? en : it; }

    function initLang() {
        let saved = '';
        try { saved = localStorage.getItem(K.lang) || ''; } catch (e) { /* archiviazione non disponibile */ }
        lang = saved === 'en' || saved === 'it' ? saved : ((navigator.language || 'it').toLowerCase().startsWith('it') ? 'it' : 'en');
    }

    function setLang(value) {
        lang = value === 'en' ? 'en' : 'it';
        try { localStorage.setItem(K.lang, lang); } catch (e) { /* ignorato */ }
        document.cookie = `germano_lang=${lang}; path=/; SameSite=Strict; max-age=31536000`;
        applyLang();
        if (info) renderAll();
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
        let data = {};
        try { data = await r.json(); } catch (e) { data = {}; }
        if (r.status === 401 && data.auth_required && !opts.noLoginRedirect) showLogin();
        return { ok: r.ok, status: r.status, data };
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

    // ------------------------------------------------------------------ stato del server
    async function loadInfo(full = true) {
        const { ok, status, data } = await api('/api/remote/v1/info', { noLoginRedirect: true });
        if (!ok) {
            info = null;
            renderHeader();
            banner(errText(data, status), true);
            if (CLIENT) showClientServer(true);
            if (!CLIENT) { $('rcApp').hidden = true; }
            return;
        }
        info = data;
        renderHeader();
        if (info.auth.required && !info.auth.logged_in) {
            showLogin();
            return;
        }
        $('rcLogin').hidden = true;
        $('rcApp').hidden = false;
        const sig = availabilitySignature();
        if (full || !rendered) {
            renderAll();
        } else if (sig !== lastSig) {
            // rilevamento automatico: un modello o una CLI appena installati (o spenti) aggiornano subito la pagina
            if (editingKey()) return;
            renderAi();
            renderTargets(true);
        }
        lastSig = sig;
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
            prof.textContent = pa ? T('🔒 Profilo PA', '🔒 PA profile') : T('Profilo PD', 'PD profile');
            prof.classList.toggle('pa', pa);
            prof.title = pa ? T('Pubblica Amministrazione: protezione massima imposta dal server.',
                                'Public Administration: maximum protection enforced by the server.')
                : T('Privati e professionisti: le opzioni si possono personalizzare.', 'Private use: options can be customized.');
        }
        const userBtn = $('rcUser');
        const auth = (info && info.auth) || {};
        userBtn.hidden = !(auth.enabled && auth.user);
        userBtn.textContent = auth.user ? `👤 ${auth.user} · ${T('Esci', 'Sign out')}` : '';
        $('rcSub').textContent = CLIENT ? 'Germano Client' : 'Remote Control';
        $('rcConnectBtn').hidden = !CLIENT;
        if (info && !s.engine_ready && info.auth.logged_in) {
            banner(T('Il motore di Germano sul server non è pronto: le richieste vengono bloccate e nessun dato esce. Riprova tra poco.',
                     'The Germano engine on the server is not ready: requests are blocked and no data leaves. Try again shortly.'), false);
        } else if (info) {
            banner('');
        }
    }

    function showLogin() {
        $('rcApp').hidden = true;
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
        conv = [];
        store('session', K.conv);
        restoreMap = {};
        store('session', K.map);
        await loadInfo(true);
    }

    // ------------------------------------------------------------------ schede
    function selectTab(name) {
        document.querySelectorAll('.rc-tabs [role="tab"]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
        document.querySelectorAll('.rc-tab').forEach(p => { p.hidden = p.dataset.panel !== name; });
        if (name === 'chat') setTimeout(() => $('rcPrompt').focus(), 30);
    }

    function renderAll() {
        rendered = true;
        renderAi();
        renderTargets();
        renderConv();
        renderOptions();
        renderConnect();
    }

    // ------------------------------------------------------------------ AI del server
    const KIND = { cli: ['CLI', 'CLI'], app: ['applicazione', 'app'], service: ['modelli locali', 'local models'] };

    function renderAi() {
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
                : T('L\'amministratore non ha attivato la condivisione delle AI del server (Impostazioni › Accesso dalla rete). Puoi usare i servizi qui sotto con la tua chiave.',
                    'The administrator has not enabled sharing of the server AIs (Settings › Network access). You can use the services below with your own key.') }));
        }
        usable.forEach(t => tl.append(aiItem(t.name, `${t.vendor || ''}${t.version ? ' · v' + t.version : ''}`,
            [el('span', { class: 'rc-pill ok', text: T('eseguita dal server', 'run by the server') })],
            T('Senza strumenti né file: il server la esegue per te e il Proxy di Germano protegge i dati.',
              'No tools or files: the server runs it for you and the Germano Proxy protects the data.'),
            el('button', { class: 'rc-btn rc-btn-sm', type: 'button', text: T('Chatta', 'Chat'), onclick: () => openChat('tool:' + t.id) }), true)));

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
                    reason = none ? T('Installa un modello sul server: compare qui da solo, senza ricaricare la pagina.',
                                      'Install a model on the server: it shows up here by itself, without reloading the page.')
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
            const btn = ready ? el('button', { class: 'rc-btn rc-btn-sm', type: 'button', text: T('Chatta', 'Chat'),
                onclick: () => openChat('service:' + s.id) }) : null;
            const keyBtn = !s.local && s.key === 'user' ? el('button', { class: 'rc-btn rc-btn-sec rc-btn-sm', type: 'button',
                text: own ? T('🔑 Chiave', '🔑 Key') : T('🔑 Inserisci la chiave', '🔑 Enter the key'),
                'aria-expanded': String(keyOpen === s.id), onclick: () => {
                    keyOpen = keyOpen === s.id ? '' : s.id;
                    renderAi();
                    const input = keyOpen && document.querySelector('#rcServices .rc-keyform input[type="password"]');
                    if (input) input.focus();
                } }) : null;
            const card = aiItem(s.name, sub, pills, reason, [keyBtn, btn], ready);
            if (keyOpen === s.id && keyBtn) card.append(keyForm(s));
            sl.append(card);
        });

        const ol = $('rcOthers');
        ol.replaceChildren();
        $('rcOthersBox').hidden = !others.length;
        others.forEach(t => {
            const rm = t.remote || {};
            const svc = rm.service || t.service;
            const target = svc && services.find(x => x.id === svc && x.available);
            const btn = target ? el('button', { class: 'rc-btn rc-btn-sec rc-btn-sm', type: 'button',
                text: T(`Usa via «${target.name}»`, `Use via «${target.name}»`), onclick: () => openChat('service:' + target.id) }) : null;
            const kind = KIND[t.kind] ? T(KIND[t.kind][0], KIND[t.kind][1]) : (t.kind || '');
            ol.append(aiItem(t.name, `${t.vendor || ''} · ${kind}${t.version ? ' · v' + t.version : ''}`,
                [el('span', { class: 'rc-pill warn', text: T('non da qui', 'not from here') })], rm.reason || '', btn, false));
        });
    }

    function aiItem(name, sub, pills, reason, button, usable) {
        return el('div', { class: 'rc-item' + (usable ? ' usable' : '') },
            el('div', { class: 'rc-item-head' }, el('div', {}, el('div', { class: 'rc-item-name', text: name }),
                sub ? el('div', { class: 'rc-item-sub', text: sub }) : null), el('div', { class: 'rc-row' }, pills, button)),
            reason ? el('div', { class: 'rc-item-reason', text: reason }) : null);
    }

    // Chiave API di un servizio via API inserita dall'utente: resta su questo dispositivo (sessione o «ricorda») e
    // viaggia solo con le richieste; con la chiave il servizio diventa selezionabile nella chat.
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
            renderTargets();
        };
        input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); save(); } });
        return el('div', { class: 'rc-keyform' },
            el('div', { class: 'rc-row rc-tight' }, input,
                el('button', { class: 'rc-btn rc-btn-sm', type: 'button', text: T('Salva', 'Save'), onclick: save }),
                deviceKey(s.id) ? el('button', { class: 'rc-btn rc-btn-sec rc-btn-sm', type: 'button', text: T('Togli', 'Remove'),
                    onclick: () => { setDeviceKey(s.id, ''); keyOpen = ''; renderAi(); renderTargets(); } }) : null),
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

    // l'utente sta scrivendo una chiave: il rilevamento periodico non ridisegna la scheda (riprova al giro dopo)
    function editingKey() {
        const a = document.activeElement;
        return Boolean(a && a.closest && a.closest('.rc-keyform'));
    }

    // ------------------------------------------------------------------ chat
    // Chiave API di un servizio salvata su questo dispositivo (sessione o «ricorda»): mai inviata al server se non
    // con la richiesta.
    function deviceKey(id) {
        return Object.assign({}, load('local', K.keys, {}), load('session', K.keys, {}))[id] || '';
    }

    // Tutte le destinazioni, rilevate o no: solo quelle rilevate (enabled) si possono scegliere, le altre restano in
    // grigio con il motivo. CLI eseguite dal server: installate e condivise. Modelli locali (Ollama, LM Studio): una
    // voce per ogni modello installato. Servizi via API: con la chiave del server o una chiave su questo dispositivo.
    function targets() {
        const out = [];
        (info.runnable || []).forEach(r => out.push({ value: 'tool:' + r.id, target: 'tool:' + r.id, label: r.name,
            group: 'tool', enabled: Boolean(r.usable), why: r.reason || '', item: r }));
        (info.services || []).forEach(s => {
            if (s.local) {
                const models = s.models_detected ? (s.models || []) : null;
                if (s.available && models && models.length) {
                    models.forEach(m => out.push({ value: `service:${s.id}|${m}`, target: 'service:' + s.id, model: m,
                        label: `${s.name.replace(/ \(.*\)$/, '')} · ${m}`, group: 'local', enabled: true, item: s }));
                } else {
                    out.push({ value: 'service:' + s.id, target: 'service:' + s.id, label: s.name.replace(/ \(.*\)$/, ''),
                        group: 'local', enabled: Boolean(s.available), item: s,
                        why: s.available ? '' : (s.reason === 'nessun modello installato' ? T('nessun modello installato', 'no model installed')
                            : T('non in esecuzione sul server', 'not running on the server')) });
                }
            } else {
                const ok = s.key === 'server' || Boolean(deviceKey(s.id));
                out.push({ value: 'service:' + s.id, target: 'service:' + s.id, label: s.name, group: 'service',
                    enabled: ok, item: s, why: ok ? '' : T('serve la chiave API: inseriscila nella scheda AI', 'API key needed: enter it in the AI tab') });
            }
        });
        return out;
    }

    // Impronta della disponibilita': se non cambia, il rilevamento periodico non tocca la pagina
    function availabilitySignature() {
        if (!info) return '';
        return JSON.stringify([(info.runnable || []).map(r => [r.id, r.usable]),
            (info.services || []).map(s => [s.id, s.available, s.key, s.models_detected ? s.models : null]),
            (info.tools || []).map(t => [t.id, (t.remote || {}).usable])]);
    }

    function renderTargets(notify) {
        const sel = $('rcTarget');
        const before = sel.value;
        const beforeLabel = sel.selectedOptions[0] ? sel.selectedOptions[0].textContent : '';
        const typed = { model: $('rcModel').value, key: $('rcKey').value };
        const current = before || load('local', K.target, '');
        sel.replaceChildren();
        const list = targets();
        const groups = { tool: el('optgroup', { label: T('Eseguite dal server', 'Run by the server') }),
                         local: el('optgroup', { label: T('Modelli locali del server (rilevati in automatico)', 'Server local models (detected automatically)') }),
                         service: el('optgroup', { label: T('Servizi via API (filtrati da Germano)', 'API services (filtered by Germano)') }) };
        list.forEach(t => {
            const o = el('option', { value: t.value, text: t.enabled ? t.label : `${t.label} — ${t.why || T('non rilevata', 'not detected')}` });
            if (!t.enabled) { o.disabled = true; o.className = 'rc-opt-off'; }
            groups[t.group].append(o);
        });
        Object.values(groups).forEach(g => { if (g.children.length) sel.append(g); });
        const usable = list.filter(t => t.enabled);
        if (!usable.length) {
            const none = el('option', { value: '', text: T('(nessuna AI rilevata: installa o avvia un modello sul server)', '(no AI detected: install or start a model on the server)') });
            sel.prepend(none);
            sel.value = '';
        } else if (usable.some(t => t.value === current)) {
            sel.value = current;
        } else {
            sel.value = usable[0].value;           // destinazione predefinita: la prima AI rilevata
            // la destinazione scelta non c'e' piu' (servizio spento, modello disinstallato): la chat lo dice
            if (notify && before && beforeLabel) addBubble('wait', T(`«${beforeLabel}» non è più disponibile: ora la destinazione è «${usable[0].label}».`,
                                                                     `«${beforeLabel}» is no longer available: the destination is now «${usable[0].label}».`));
        }
        $('rcSend').disabled = !usable.length;
        onTargetChange();
        if (before && sel.value === before) {      // stessa destinazione: resta cio' che l'utente aveva scritto
            if (!$('rcModel').readOnly) $('rcModel').value = typed.model;
            if (!$('rcKeyBox').hidden && typed.key) $('rcKey').value = typed.key;
        }
    }

    function currentTarget() {
        return targets().find(t => t.value === $('rcTarget').value && t.enabled) || null;
    }

    function onTargetChange() {
        const t = currentTarget();
        if ($('rcTarget').value) store('local', K.target, $('rcTarget').value);
        const isService = t && (t.group === 'service' || t.group === 'local');
        const fixed = Boolean(t && t.model);           // modello locale rilevato: e' gia' scelto con la destinazione
        const models = load('local', K.model, {});
        $('rcModel').value = fixed ? t.model : ((t && models[t.value]) || (isService && t.item.models && t.item.models[0]) || '');
        $('rcModel').readOnly = fixed;
        $('rcModel').placeholder = isService ? T('obbligatorio: scegli o scrivi il modello', 'required: choose or type the model')
            : T('facoltativo (es. sonnet)', 'optional (e.g. sonnet)');
        const dl = $('rcModelList');
        dl.replaceChildren();
        ((t && !fixed && t.item.models) || []).forEach(m => dl.append(el('option', { value: m })));
        $('rcModelLoad').hidden = !isService || fixed;
        const needKey = Boolean(t && t.group === 'service' && t.item.key === 'user');
        $('rcKeyBox').hidden = !needKey;
        $('rcKeyRemember').hidden = !needKey;
        if (needKey) {
            const keys = Object.assign({}, load('local', K.keys, {}), load('session', K.keys, {}));
            $('rcKey').value = keys[t.item.id] || '';
            $('rcKeyRememberBox').checked = Boolean(load('local', K.keys, {})[t.item.id]);
        }
    }

    function serviceKey(target) {
        if (!target || target.group !== 'service' || target.item.key !== 'user') return '';
        if (!$('rcKey').value.trim()) $('rcKey').value = deviceKey(target.item.id);
        const key = $('rcKey').value.trim();
        setDeviceKey(target.item.id, key, $('rcKeyRememberBox').checked);
        return key;
    }

    function openChat(value) {
        selectTab('chat');
        // per i modelli locali si apre il primo modello rilevato di quel servizio
        const t = targets().find(x => x.enabled && (x.value === value || x.target === value));
        if (t) $('rcTarget').value = t.value;
        onTargetChange();
    }

    async function loadModels() {
        const t = currentTarget();
        if (!t || (t.group !== 'service' && t.group !== 'local')) return;
        const headers = {};
        const key = serviceKey(t);
        if (key) headers['X-Germano-Provider-Key'] = key;
        $('rcModelLoad').disabled = true;
        const { ok, status, data } = await api('/api/remote/v1/models?service=' + encodeURIComponent(t.item.id), { headers });
        $('rcModelLoad').disabled = false;
        if (!ok) { addBubble('err', errText(data, status)); return; }
        const dl = $('rcModelList');
        dl.replaceChildren();
        (data.models || []).forEach(m => dl.append(el('option', { value: m })));
        addBubble('wait', T(`${(data.models || []).length} modelli disponibili: scegli dall'elenco del campo «Modello».`,
                            `${(data.models || []).length} models available: pick one from the «Model» field list.`));
    }

    function renderFiles(box, list, onRemove) {
        box.replaceChildren();
        list.forEach((f, i) => box.append(el('span', { class: 'rc-file' }, el('span', { text: `📄 ${f.name}` }),
            el('button', { type: 'button', 'aria-label': T('Togli', 'Remove'), text: '✕', onclick: () => onRemove(i) }))));
    }

    function addFiles(list, files, box, rerender) {
        for (const f of files) {
            if (list.length >= MAX_FILES) {
                banner(T(`Al massimo ${MAX_FILES} allegati per richiesta.`, `At most ${MAX_FILES} attachments per request.`), true);
                break;
            }
            list.push(f);
        }
        rerender();
    }

    function bubbleNode(m) {
        if (m.role === 'user') {
            return el('div', { class: 'rc-msg user' }, m.display || m.text,
                m.files && m.files.length ? el('div', { class: 'rc-msg-meta', text: '📎 ' + m.files.join(', ') }) : null);
        }
        if (m.role === 'assistant') {
            const meta = m.meta || {};
            const masks = { numbered: T('etichette ripristinate', 'tags restored'), generic: T('etichette generiche (irreversibili)', 'generic tags (irreversible)'),
                            blackout: T('oscuramento ████ (irreversibile)', 'blackout ████ (irreversible)') };
            return el('div', { class: 'rc-msg ai' }, m.text,
                el('div', { class: 'rc-msg-meta', text: `${meta.target_name || ''}${meta.model ? ' · ' + meta.model : ''} · 🛡️ ` +
                    T(`${meta.entity_count || 0} dati oscurati`, `${meta.entity_count || 0} data masked`) +
                    ` · ${masks[meta.masking] || ''}${meta.seconds !== undefined ? ' · ' + meta.seconds + ' s' : ''}` }),
                meta.protected ? el('details', {}, el('summary', { text: T('Cosa ha ricevuto l\'AI (testo protetto)', 'What the AI received (protected text)') }),
                    el('pre', { text: meta.protected })) : null,
                meta.answer_protected && meta.answer_protected !== m.text ? el('details', {},
                    el('summary', { text: T('Risposta originale dell\'AI (con le etichette)', 'Original AI answer (with tags)') }),
                    el('pre', { text: meta.answer_protected })) : null);
        }
        return el('div', { class: 'rc-msg ' + m.role, text: m.text });
    }

    function renderConv() {
        conv = load('session', K.conv, []) || [];
        const box = $('rcConv');
        box.replaceChildren();
        if (!conv.length) {
            box.append(el('p', { class: 'rc-empty', text: T('Scegli un\'AI e scrivi la richiesta: Germano oscura i dati personali prima che escano dal server e li rimette nella risposta.',
                'Choose an AI and write your request: Germano masks personal data before it leaves the server and puts it back in the answer.') }));
        }
        conv.forEach(m => box.append(bubbleNode(m)));
        box.scrollTop = box.scrollHeight;
    }

    function addBubble(role, text) {
        const node = bubbleNode({ role, text });
        $('rcConv').append(node);
        $('rcConv').scrollTop = $('rcConv').scrollHeight;
        return node;
    }

    function optionsForRequest() {
        if (!info || info.locked) return null;
        return load('local', K.opts, null);
    }

    async function sendChat(e) {
        e.preventDefault();
        const t = currentTarget();
        const prompt = $('rcPrompt').value.trim();
        if (!t) { banner(T('Scegli un\'AI.', 'Choose an AI.'), true); return; }
        if (!prompt && !chatFiles.length) return;
        const model = t.model || $('rcModel').value.trim();
        if (!t.model) {
            const models = load('local', K.model, {});
            models[t.value] = model;
            store('local', K.model, models);
        }
        const fd = new FormData();
        fd.append('target', t.target);
        fd.append('model', model);
        fd.append('prompt', prompt);
        fd.append('history', JSON.stringify(conv.filter(m => m.role === 'user' || m.role === 'assistant').map(m => ({ role: m.role, text: m.text }))));
        const opts = optionsForRequest();
        if (opts) fd.append('options', JSON.stringify(opts));
        chatFiles.forEach(f => fd.append('files', f, f.name));
        const headers = {};
        const key = serviceKey(t);
        if (key) headers['X-Germano-Provider-Key'] = key;
        const names = chatFiles.map(f => f.name);
        if (!conv.length) $('rcConv').replaceChildren();
        $('rcConv').append(bubbleNode({ role: 'user', text: prompt, files: names }));
        const wait = addBubble('wait', T('Il server protegge i dati e interroga l\'AI…', 'The server protects the data and asks the AI…'));
        $('rcSend').disabled = true;
        const { ok, status, data } = await api('/api/remote/v1/ask', { method: 'POST', body: fd, headers });
        $('rcSend').disabled = false;
        wait.remove();
        if (!ok || data.status !== 'success') {
            addBubble('err', errText(data, status));
            if (status === 403 && data.code === 'compliance_lock') { await loadInfo(true); selectTab('chat'); }
            return;
        }
        conv.push({ role: 'user', text: data.user_text || prompt, display: prompt, files: names });
        conv.push({ role: 'assistant', text: data.answer, meta: { target_name: data.target_name, model: data.model,
            entity_count: data.entity_count, masking: data.masking, seconds: data.seconds, protected: data.protected,
            answer_protected: data.answer_protected } });
        store('session', K.conv, conv);
        $('rcPrompt').value = '';
        chatFiles = [];
        renderFiles($('rcFiles'), chatFiles, removeChatFile);
        renderConv();
    }

    function removeChatFile(i) { chatFiles.splice(i, 1); renderFiles($('rcFiles'), chatFiles, removeChatFile); }
    function removeProtFile(i) { protFiles.splice(i, 1); renderFiles($('rcProtFiles'), protFiles, removeProtFile); }

    // ------------------------------------------------------------------ proteggi e ripristina
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
        restoreMap = Object.assign(load('session', K.map, {}), data.map || {});
        store('session', K.map, restoreMap);
        const skipped = (data.attachments || []).filter(a => !a.textual).map(a => a.name);
        $('rcProtMeta').textContent = '🛡️ ' + T(`${data.entity_count} dati oscurati`, `${data.entity_count} data masked`) +
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
            (Object.keys(restoreMap).length ? '' : T(' (proteggi prima un testo da questa pagina)', ' (protect a text from this page first)'));
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
            selectTab('options');
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
    function showClientServer(show) {
        $('rcClientServer').hidden = !show;
        if (show) {
            api('/client/config').then(({ ok, data }) => { if (ok) $('rcServerAddr').value = data.server_url || ''; });
        }
    }

    async function saveClientServer() {
        const { ok, status, data } = await api('/client/config', { json: { server: $('rcServerAddr').value.trim() } });
        if (!ok) { banner(errText(data, status), true); return; }
        $('rcClientServer').hidden = true;
        await loadInfo(true);
    }

    async function findServers() {
        const list = $('rcServerList');
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
            el('button', { class: 'rc-btn rc-btn-sm', type: 'button', text: T('Usa', 'Use'), onclick: () => { $('rcServerAddr').value = s.url; saveClientServer(); } }), true)));
    }

    // ------------------------------------------------------------------ avvio
    function bind() {
        $('rcIt').addEventListener('click', () => setLang('it'));
        $('rcEn').addEventListener('click', () => setLang('en'));
        $('rcUser').addEventListener('click', logout);
        $('rcLoginForm').addEventListener('submit', login);
        document.querySelectorAll('.rc-tabs [role="tab"]').forEach(b => b.addEventListener('click', () => {
            selectTab(b.dataset.tab);
            if (b.dataset.tab === 'ai' || b.dataset.tab === 'chat') loadInfo(false);   // AI aggiornate all'apertura
        }));
        $('rcAiRefresh').addEventListener('click', () => loadInfo(true));
        $('rcTarget').addEventListener('change', onTargetChange);
        $('rcModelLoad').addEventListener('click', loadModels);
        $('rcComposer').addEventListener('submit', sendChat);
        $('rcPrompt').addEventListener('keydown', e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) $('rcComposer').requestSubmit(); });
        $('rcAttach').addEventListener('change', e => { addFiles(chatFiles, e.target.files, $('rcFiles'), () => renderFiles($('rcFiles'), chatFiles, removeChatFile)); e.target.value = ''; });
        $('rcNewChat').addEventListener('click', () => { conv = []; store('session', K.conv); renderConv(); });
        $('rcProtectForm').addEventListener('submit', protect);
        $('rcProtAttach').addEventListener('change', e => { addFiles(protFiles, e.target.files, $('rcProtFiles'), () => renderFiles($('rcProtFiles'), protFiles, removeProtFile)); e.target.value = ''; });
        $('rcProtCopy').addEventListener('click', async () => {
            const ok = await copyText($('rcProtText2').textContent);
            $('rcProtCopy').textContent = ok ? T('✅ Copiato', '✅ Copied') : T('Seleziona e copia a mano', 'Select and copy by hand');
            setTimeout(() => applyLang(), 2500);
        });
        $('rcRestoreBtn').addEventListener('click', restore);
        $('optThreshold').addEventListener('input', () => { $('optThresholdOut').textContent = Number($('optThreshold').value).toFixed(2); });
        $('optSave').addEventListener('click', saveOptions);
        $('optReset').addEventListener('click', resetOptions);
        $('rcTokenBtn').addEventListener('click', createToken);
        $('rcConnectBtn').addEventListener('click', () => showClientServer($('rcClientServer').hidden));
        $('rcServerSave').addEventListener('click', saveClientServer);
        $('rcServerFind').addEventListener('click', findServers);
        document.addEventListener('visibilitychange', () => { if (!document.hidden) loadInfo(false); });
        window.addEventListener('focus', () => loadInfo(false));
    }

    initLang();
    applyLang();
    bind();
    loadInfo(true);
    setInterval(() => { if (!document.hidden) loadInfo(false); }, DETECT_MS);
})();
