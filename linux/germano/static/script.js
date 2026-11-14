'use strict';
/* Germano AI 0.91 - Dashboard: Harness AI (scheda predefinita, static/harness.js), Sanitizzazione manuale e Vault
   (cartelle di lavoro, documenti, testo), Impostazioni (modalita' e rete, protezione, AI e chiavi, Proxy e API, sistema,
   aggiornamenti silenziosi) e Guida offline. */

let currentUiMode = 'advanced';   // dalla 0.70 tutte le funzioni sono sempre visibili (valore conservato in config.json)
let currentComplianceMode = 'PA';
let currentStatus = 'stopped';
let settingsLocked = false;
let activeFileTab = 'output';
let cachedFiles = { output: [], input: [], failed: [], processed: [], totals: {} };
let lastStatus = null;
let serverDown = false;
let filesSignature = '';
let lastFilesFetch = 0;
let foldersLoaded = false;
let batch = { active: false, baseDone: 0, baseFailed: 0, done: 0, failed: 0, summary: null, startedAt: 0 };
let updateInstalling = false;
let pageVersion = null;
let tooltipsEnabled = true;       // preferenza salvata (enable_tooltips): suggerimenti attivi di default
let initialConfig = null;         // configurazione letta all'apertura (serve a riconoscere la prima apertura)
let modeState = null;             // ultimo stato di /api/mode (modalita' operativa, rete, motore)
let settingsWelcome = false;      // la sezione «Modalita'» e' nella finestra di benvenuto (prima apertura)
let settingsDone = false;         // benvenuto in modalita' Server: la finestra resta aperta per mostrare gli indirizzi
let harness = null;               // Harness AI (static/harness.js)
let lastUpdate = null;            // ultimo stato degli aggiornamenti (germano/updater.py)
let lastEngineKey = '';

const TABS = ['harness', 'sanitize', 'settings', 'guide'];
const PANES = ['general', 'protection', 'ai', 'proxy', 'system', 'updates', 'about'];
let currentTab = 'harness';
let currentPane = 'general';

const ALL_MODEL_IDS = [
    'enable_model_velvet', 'enable_model_italian_ner', 'enable_ocr',
    'enable_faces', 'enable_signatures', 'enable_plate_vision', 'enable_regex'
];
const ALL_CATEGORY_IDS = [
    'censor_person', 'censor_profession', 'censor_address', 'censor_cadastre',
    'censor_cf_iva', 'censor_email', 'censor_phone', 'censor_account',
    'censor_financial', 'censor_date', 'censor_org', 'censor_plates_docs',
    'censor_medical', 'censor_medicine', 'censor_legal', 'censor_civil_status',
    'censor_secret', 'censor_url'
];
const ESSENTIAL_CATEGORIES = new Set(['censor_person', 'censor_address', 'censor_cf_iva', 'censor_email', 'censor_phone']);

const EMPTY_MESSAGES = {
    output: 'Nessun documento pronto. Aggiungi documenti qui sopra oppure copiali nella cartella input.',
    input: 'Nessun documento in attesa.',
    failed: 'Nessun documento non riuscito.',
    processed: 'Nessun originale archiviato.'
};
const STATUS_LABELS = { output: 'Anonimizzato', input: 'In attesa', failed: 'Non riuscito', processed: 'Originale' };

// Strumenti che possono usare il Proxy: indirizzo da impostare e dove si imposta.
const AGENTS = [
    { name: 'Claude Code', format: 'Anthropic', base: 'anthropic',
      where: 'Variabile di ambiente, da impostare prima di avviare claude (PowerShell):',
      snippet: (o, a) => `$env:ANTHROPIC_BASE_URL = "${a}"` },
    { name: 'OpenAI Codex CLI', format: 'OpenAI Responses', base: 'openai',
      where: 'Variabile di ambiente, da impostare prima di avviare codex (PowerShell):',
      snippet: (o) => `$env:OPENAI_BASE_URL = "${o}"` },
    { name: 'Cursor', format: 'OpenAI', base: 'openai',
      where: 'Settings › Models › Override OpenAI Base URL, con la tua chiave OpenAI.' },
    { name: 'Google Antigravity', format: 'OpenAI', base: 'openai',
      where: 'Impostazioni del provider OpenAI: endpoint di base (Base URL).' },
    { name: 'Windsurf', format: 'OpenAI', base: 'openai',
      where: 'Impostazioni del provider compatibile OpenAI: Base URL.' },
    { name: 'OpenCode', format: 'OpenAI', base: 'openai',
      where: 'File opencode.json: provider › options › baseURL.' },
    { name: 'Continue (VS Code, JetBrains)', format: 'OpenAI', base: 'openai',
      where: 'File config.yaml: nel modello, campo apiBase.' },
    { name: 'Aider', format: 'OpenAI', base: 'openai',
      where: 'Opzione da riga di comando:',
      snippet: (o) => `aider --openai-api-base ${o}` },
    { name: 'SDK OpenAI (Python, Node.js)', format: 'OpenAI', base: 'openai',
      where: 'Parametro base_url (Python) o baseURL (Node.js), oppure variabile OPENAI_BASE_URL:',
      snippet: (o) => `client = OpenAI(base_url="${o}")` },
    { name: 'SDK Anthropic (Python, Node.js)', format: 'Anthropic', base: 'anthropic',
      where: 'Parametro base_url (Python) o baseURL (Node.js), oppure variabile ANTHROPIC_BASE_URL:',
      snippet: (o, a) => `client = Anthropic(base_url="${a}")` }
];

const REST_ENDPOINTS = [
    { method: 'POST', path: '/api/v1/anonymize',
      desc: 'Invia un file (campo file) e ricevi il file anonimizzato nello stesso formato.',
      example: (b) => `curl.exe -X POST ${b}/api/v1/anonymize -F "file=@documento.pdf" -o documento_anonimizzato.pdf` },
    { method: 'POST', path: '/api/v1/anonymize_text',
      desc: 'Anonimizza un testo (corpo JSON {"text": "..."}): restituisce il testo e l\'elenco dei dati trovati.',
      example: (b) => `curl.exe -X POST ${b}/api/v1/anonymize_text -H "Content-Type: application/json" --data-binary "@testo.json"` },
    { method: 'POST', path: '/api/v1/deanonymize_text',
      desc: 'Ripristina i dati originali in un testo che contiene etichette (corpo JSON {"text": "..."}).',
      example: (b) => `curl.exe -X POST ${b}/api/v1/deanonymize_text -H "Content-Type: application/json" --data-binary "@risposta.json"` },
    { method: 'POST', path: '/api/v1/deanonymize_file',
      desc: 'Ripristina i dati originali in un file restituito dall\'AI; con ?raw=1 la risposta è il file.',
      example: (b) => `curl.exe -X POST "${b}/api/v1/deanonymize_file?raw=1" -F "file=@risposta_ai.docx" -o risposta_ripristinata.docx` },
    { method: 'GET', path: '/api/status',
      desc: 'Stato del motore, documenti in coda e risorse del computer.',
      example: (b) => `curl.exe ${b}/api/status` }
];

const FOLDER_INFO = [
    ['input', 'Input', 'documenti da elaborare'],
    ['output', 'Output', 'documenti pronti'],
    ['failed', 'Non riusciti', 'con il motivo (cartella failed)'],
    ['processed', 'Originali', 'archiviati dopo l\'elaborazione'],
    ['extracted', 'Report e archivio', 'report di audit, registri del proxy, corrispondenze']
];

// ------------------------------------------------------------------ UTILITÀ
const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

const UI_STRINGS = {
    'Motore in pausa': 'Engine paused',
    'Motore attivo': 'Engine running',
    'Avvio del motore...': 'Starting engine...',
    'Arresto del motore...': 'Stopping engine...',
    'Avvia motore': 'Start engine',
    'Arresta motore': 'Stop engine',
    'Annulla avvio': 'Cancel start',
    'Germano non risponde': 'Germano is not responding',
    'Aggiornamento in corso...': 'Updating...',
    'In attesa': 'Pending',
    'Pronti': 'Ready',
    'Errori': 'Failed',
    'Originali': 'Originals',
    'Attivo': 'Active',
    'Disattivo': 'Inactive',
    'Disattivato': 'Off',
    'Elaborazione in corso...': 'Processing in progress...',
    'Completato': 'Completed',
    'Nessun documento in attesa': 'No pending documents',
    'Standalone': 'Standalone',
    'Server': 'Server',
    'Client': 'Client',
    'Server + Client': 'Server + Client',
    'Profilo PA': 'PA Profile',
    'Profilo PD': 'PD Profile',
    'Mostra': 'Show',
    'Nascondi': 'Hide',
    'Applica': 'Apply',
    'Conferma e inizia': 'Confirm and start',
    'Fatto': 'Done',
    'Motore fermo per errore': 'Engine stopped by an error',
    'Arresto in corso...': 'Stopping...',
    'Arresto...': 'Stopping...'
};

function setText(id, value) {
    const el = $(id);
    if (el) {
        if (typeof currentLang !== 'undefined' && currentLang === 'en' && typeof value === 'string' && UI_STRINGS[value]) {
            el.textContent = UI_STRINGS[value];
        } else {
            el.textContent = value;
        }
    }
}

function plural(n, one, many) {
    return `${n} ${n === 1 ? one : many}`;
}

function showToast(message, type = 'info', ms = 4200) {
    const container = $('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 260);
    }, ms);
}

function uiLocale() {
    return typeof currentLang !== 'undefined' && currentLang === 'en' ? 'en-GB' : 'it-IT';
}

function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
    return `${parseFloat((bytes / Math.pow(1024, i)).toFixed(1)).toLocaleString(uiLocale())} ${units[i]}`;
}

function formatDate(epoch) {
    if (!epoch) return '';
    const d = new Date(epoch * 1000);
    const time = d.toLocaleTimeString(uiLocale(), { hour: '2-digit', minute: '2-digit' });
    if (d.toDateString() === new Date().toDateString()) return `${updText('oggi', 'today')} ${time}`;
    return `${d.toLocaleDateString(uiLocale(), { day: '2-digit', month: '2-digit', year: 'numeric' })} ${time}`;
}

function splitPath(name) {
    const i = name.lastIndexOf('/');
    return i < 0 ? ['', name] : [name.slice(0, i), name.slice(i + 1)];
}

async function fetchJson(url, options) {
    const r = await fetch(url, options);
    let data = {};
    try { data = await r.json(); } catch (e) { data = {}; }
    return { ok: r.ok, status: r.status, data };
}

function postJson(url, body) {
    return fetchJson(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {})
    });
}

async function copyText(text) {
    try {
        await navigator.clipboard.writeText(text);
    } catch (e) {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
    }
    showToast(updText('Copiato negli appunti.', 'Copied to the clipboard.'), 'success', 2200);
}

function proxyBase() {
    // In locale si usa 127.0.0.1 (alcuni strumenti risolvono "localhost" in IPv6, su cui Germano non è in ascolto).
    // Se la Dashboard è aperta dalla rete, si usa l'host con cui è stata raggiunta (l'IP del server), così gli
    // indirizzi da copiare funzionano anche dai client della LAN.
    const h = location.hostname;
    const host = (!h || h === 'localhost' || h === '127.0.0.1' || h === '[::1]' || h === '::1') ? '127.0.0.1' : h;
    return `http://${host}:${location.port || '80'}`;
}

function iconSvg(name) {
    return `<svg class="icon" aria-hidden="true"><use href="#${name}"/></svg>`;
}

function copyButton(text, title = 'Copia') {
    return `<button type="button" class="btn-icon" data-copy="${escapeHtml(text)}" title="${title}" aria-label="${title}">${iconSvg('i-copy')}</button>`;
}

function engineActive() {
    return currentStatus === 'running' || currentStatus === 'loading_models';
}

function updText(it, en) {
    return currentLang === 'en' ? en : it;
}

// ------------------------------------------------------------------ SCHEDE PRINCIPALI E SEZIONI DELLE IMPOSTAZIONI
function applyTab(tab, remember = true) {
    if (!TABS.includes(tab)) tab = 'harness';
    currentTab = tab;
    document.body.dataset.tab = tab;
    document.querySelectorAll('.main-tab').forEach(b => {
        const on = b.dataset.tab === tab;
        b.classList.toggle('active', on);
        b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    if (remember) {
        try { sessionStorage.setItem('germano_tab', tab); } catch (e) { /* archivio del browser non disponibile */ }
    }
    if (tab === 'guide') loadGuide();
    if (tab === 'settings') applyPane(currentPane, false);
    if (tab === 'sanitize') { fetchFiles(); if (!fmPaths) loadFmPaths(); }
    if (tab === 'harness' && harness) harness.refreshTargets(false);
    Tips.hide();
}

function applyPane(pane, remember = true) {
    if (!PANES.includes(pane)) pane = 'general';
    currentPane = pane;
    document.querySelectorAll('.settings-link').forEach(b => b.classList.toggle('active', b.dataset.pane === pane));
    document.querySelectorAll('.settings-pane').forEach(p => p.classList.toggle('active', p.dataset.pane === pane));
    if (remember) {
        try { sessionStorage.setItem('germano_pane', pane); } catch (e) { /* archivio non disponibile */ }
        const body = document.querySelector('.view-settings');
        if (body) body.scrollTop = 0;
    }
    if (pane === 'general') { if (!settingsWelcome) refreshModeSection(); renderNetSummary(); }
    if (pane === 'system') { loadFolders(); pollLogs(); }
    if (pane === 'ai') { renderAiSettings(); renderAssistOverview(); if (harness) harness.refreshTargets(false).then(renderAiSettings); }
    if (pane === 'updates') { renderUpdatePanel(lastUpdate); acknowledgeInstallResult(); }
}

function loadGuide(hash) {
    const frame = $('guideFrame');
    if (!frame) return;
    const url = `/guide?lang=${currentLang}` + (hash ? `#${hash}` : '');
    if (frame.dataset.loaded !== url) {
        frame.src = url;
        frame.dataset.loaded = url;
    }
}

// ------------------------------------------------------------------ HARNESS AI
function engineSnapshot() {
    return { ready: currentStatus === 'running', running: engineActive() };
}

function mountHarness() {
    if (!window.GermanoHarness || !$('harnessRoot')) return;
    harness = window.GermanoHarness.mount($('harnessRoot'), {
        host: 'suite',
        lang: () => currentLang,
        keysKey: 'germano_keys',
        convKey: 'germano_harness_v1',
        persistDefault: true,
        canStartEngine: true,
        engine: engineSnapshot,
        startEngine: async () => { await startEngine(); await pollStatus(); },
        engineState: async () => {
            await pollStatus();
            return { ready: currentStatus === 'running', running: engineActive(), failed: currentStatus === 'error' };
        },
        toast: (msg, type) => showToast(msg, type === 'success' ? 'success' : type),
        onKeysChanged: () => renderAiSettings(),
        onAssistChanged: () => { renderAiSettings(); if (currentPane === 'ai') renderAssistOverview(); },
    });
}

// Assistente di configurazione (Impostazioni > AI): schede per Antigravity, Qwen, GLM, Ollama, LM Studio, Jan e per le
// chiavi trovate su questo computer; la finestra con le azioni e' quella dell'Harness (static/harness.js).
function renderAssistOverview() {
    const box = $('aiAssistList');
    if (box && harness && harness.renderAssistOverview) harness.renderAssistOverview(box);
}

const KIND_LABEL = { cli: ['CLI', 'CLI'], local: ['modelli locali', 'local models'], other: ['non utilizzabile', 'not usable'] };

function renderAiSettings() {
    const list = $('aiDetectedList');
    const keys = $('keyList');
    if (!list || !keys) return;
    const targets = harness && harness.targets;
    if (!targets) {
        list.innerHTML = `<span class="muted">${escapeHtml(updText('Rilevamento in corso…', 'Detecting…'))}</span>`;
        return;
    }
    const shown = targets.filter(t => t.kind === 'cli' || t.kind === 'local' || (t.kind === 'other' && t.detected));
    list.innerHTML = shown.length ? shown.map(t => {
        const kind = KIND_LABEL[t.kind] ? updText(KIND_LABEL[t.kind][0], KIND_LABEL[t.kind][1]) : t.kind;
        const sub = t.enabled ? `${kind}${t.version ? ' · v' + t.version : ''}${t.vendor && t.kind !== 'local' ? ' · ' + t.vendor : ''}` : (t.reason || '');
        // pulsante dell'assistente accanto alla voce (es. «Installa CLI» accanto ad Antigravity, «Avvia» accanto a Ollama)
        const assist = t.assist ? `<button type="button" class="hx-pick-assist ai-item-assist" data-assist-open="${escapeHtml(t.assist)}">${escapeHtml(t.assist_label || updText('Configura', 'Set up'))}</button>` : '';
        return `<div class="ai-item${t.enabled ? ' on' : ''}" title="${escapeHtml(t.reason || t.name)}"><span class="hx-dot${t.enabled ? ' ok' : ''}"></span>
            <span class="ai-item-main"><span class="ai-item-name">${escapeHtml(t.name)}</span><span class="ai-item-sub">${escapeHtml(sub)}</span></span>${assist}</div>`;
    }).join('') : `<span class="muted">${escapeHtml(updText('Nessuna AI o CLI rilevata su questo computer: quando ne installi una (o avvii Ollama, LM Studio o Jan) compare qui da sola.',
                                                              'No AI or CLI detected on this computer: when you install one (or start Ollama, LM Studio or Jan) it shows up here by itself.'))}</span>`;
    const clouds = targets.filter(t => t.kind === 'cloud');
    const remembered = (() => { try { return JSON.parse(localStorage.getItem('germano_keys') || '{}'); } catch (e) { return {}; } })();
    keys.innerHTML = clouds.map(t => {
        const own = harness.key(t.service);
        let state;
        if (t.key === 'server') state = `<span class="badge badge-ok">${escapeHtml(updText('chiave di questo computer', 'this computer\'s key'))}</span><code>${escapeHtml((t.key_vars || []).join(', '))}</code>`;
        else if (own) state = `<span class="badge badge-info">${escapeHtml(updText('chiave su questo dispositivo', 'key on this device'))}</span>${remembered[t.service] ? '' : `<span class="muted">${escapeHtml(updText('(solo per questa sessione)', '(this session only)'))}</span>`}`;
        else state = `<span class="badge badge-off">${escapeHtml(updText('nessuna chiave: in grigio nei Chatbot', 'no key: greyed out in Chatbot'))}</span>`;
        const actions = t.key === 'server' ? '' : `<input type="password" class="input" data-key-input="${escapeHtml(t.service)}" placeholder="${escapeHtml(updText('incolla la chiave API', 'paste the API key'))}" autocomplete="off" spellcheck="false">
            <label><input type="checkbox" data-key-remember="${escapeHtml(t.service)}"${remembered[t.service] ? ' checked' : ''}>${escapeHtml(updText('ricorda', 'remember'))}</label>
            <button type="button" class="btn btn-secondary btn-sm" data-key-save="${escapeHtml(t.service)}">${escapeHtml(updText('Salva', 'Save'))}</button>
            ${own ? `<button type="button" class="btn btn-danger-outline btn-sm" data-key-remove="${escapeHtml(t.service)}">${escapeHtml(updText('Togli', 'Remove'))}</button>` : ''}`;
        return `<div class="key-row"><span class="key-row-name">${escapeHtml(t.name)}</span><span class="key-row-state">${state}</span><span class="key-row-actions">${actions}</span></div>`;
    }).join('');
    document.querySelectorAll('#harnessPrefs [data-hpref]').forEach(box => { box.checked = Boolean(harness.prefs[box.dataset.hpref]); });
}

function onKeyListClick(e) {
    const save = e.target.closest('[data-key-save]');
    const remove = e.target.closest('[data-key-remove]');
    if (save) {
        const sid = save.dataset.keySave;
        const input = document.querySelector(`[data-key-input="${CSS.escape(sid)}"]`);
        const remember = document.querySelector(`[data-key-remember="${CSS.escape(sid)}"]`);
        const value = (input && input.value || '').trim();
        if (!/^[\x21-\x7e]{8,512}$/.test(value)) {
            showToast(updText('Chiave non valida (almeno 8 caratteri, senza spazi).', 'Invalid key (at least 8 characters, no spaces).'), 'error');
            return;
        }
        harness.setKey(sid, value, Boolean(remember && remember.checked));
        harness.renderPicker();
        renderAiSettings();
        showToast(updText('Chiave salvata: il servizio ora si può scegliere nell\'Harness.', 'Key saved: the service can now be chosen in the Harness.'), 'success');
    } else if (remove) {
        harness.setKey(remove.dataset.keyRemove, '');
        harness.renderPicker();
        renderAiSettings();
    }
}

// ------------------------------------------------------------------ IMPOSTAZIONI (motore, filtri, modelli)
function updateThresholdBadge(val) {
    const pct = Math.round(parseFloat(val || 0) * 100);
    setText('thresholdValue', pct === 0 ? updText('Massima (soglia 0%)', 'Maximum (0% threshold)') : updText(`Soglia ${pct}%`, `Threshold ${pct}%`));
}

function updateProfilePill() {
    const pill = $('profilePill');
    const pa = currentComplianceMode === 'PA';
    pill.innerHTML = (settingsLocked ? iconSvg('i-lock') : '') + escapeHtml(pa ? updText('Profilo PA', 'PA Profile') : updText('Profilo PD', 'PD Profile'));
    pill.title = pa
        ? updText('Profilo PA: tutti i modelli e tutte le categorie attivi, sensibilità massima.', 'PA profile: all models and categories on, maximum sensitivity.')
        : updText('Profilo PD: configurazione personalizzata di modelli, categorie o sensibilità.', 'PD profile: custom configuration of models, categories or sensitivity.');
    if (settingsLocked) pill.title += updText(' Impostazioni bloccate dall\'amministratore.', ' Settings locked by the administrator.');
    document.body.classList.toggle('settings-locked', settingsLocked);
    $('lockedBanner').hidden = !settingsLocked;
    document.querySelectorAll('.model-check, .cat-check, .btn-preset, #ai_threshold, #check_updates, #auto_update, #enable_system2, #speech_language').forEach(el => {
        el.disabled = settingsLocked;
    });
}

function updatePresetButtons() {
    const checked = (id) => Boolean($(id)?.checked);
    const allModels = ALL_MODEL_IDS.every(checked);
    const noModels = !ALL_MODEL_IDS.some(checked);
    const allCats = ALL_CATEGORY_IDS.every(checked);
    const noCats = !ALL_CATEGORY_IDS.some(checked);
    const essential = ALL_CATEGORY_IDS.every(id => checked(id) === ESSENTIAL_CATEGORIES.has(id));
    const mark = (id, on) => {
        const b = $(id);
        if (!b) return;
        b.classList.toggle('is-active', on);
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
    };
    mark('btnModelsAllOn', allModels);
    mark('btnModelsAllOff', noModels);
    mark('btnPresetPA', allModels && allCats && currentComplianceMode === 'PA');
    mark('btnPresetEssential', essential);
    mark('btnPresetNone', noCats);
    updateProfilePill();
}

function applyDeanonState(enabled) {
    const badge = $('deanonStateBadge');
    badge.textContent = enabled ? updText('Attivo', 'Active') : updText('Disattivato', 'Off');
    badge.className = 'badge ' + (enabled ? 'badge-info' : 'badge-off');
}

function gatherSettings() {
    const val = (id, def) => ($(id) ? $(id).value : def);
    const out = {
        ui_mode: currentUiMode,
        compliance_mode: currentComplianceMode,
        enable_deanonymize: $('enable_deanonymize')?.checked ?? true,
        target_api_url: (val('target_api_url', '') || '').trim(),
        target_anthropic_url: (val('target_anthropic_url', '') || '').trim(),
        ai_threshold: parseFloat(val('ai_threshold', '0')) || 0.0,
        hardware_mode: val('hardware_mode', 'gpu_fallback'),
        precision: val('precision', 'auto'),
        file_timeout_minutes: parseInt(val('file_timeout_minutes', '60'), 10) || 60,
        speech_language: val('speech_language', 'auto'),
        anonymize_filenames: $('anonymize_filenames')?.checked ?? false,
        check_updates: $('check_updates')?.checked ?? true,
        auto_update: $('auto_update')?.checked ?? true,
        enable_system2: $('enable_system2')?.checked ?? true,
        enable_tooltips: tooltipsEnabled
    };
    ALL_MODEL_IDS.forEach(k => { out[k] = $(k)?.checked ?? true; });
    ALL_CATEGORY_IDS.forEach(k => { out[k] = $(k)?.checked ?? true; });
    return out;
}

function applySettingsToUi(cfg) {
    currentComplianceMode = cfg.compliance_mode || 'PA';
    settingsLocked = Boolean(cfg.lock_settings);
    currentUiMode = cfg.ui_mode || currentUiMode;
    const deanon = cfg.enable_deanonymize !== false;
    $('enable_deanonymize').checked = deanon;
    applyDeanonState(deanon);
    [...ALL_MODEL_IDS, ...ALL_CATEGORY_IDS].forEach(k => {
        const el = $(k);
        if (el && cfg[k] !== undefined) el.checked = Boolean(cfg[k]);
    });
    const setVal = (id, v) => {
        const el = $(id);
        if (el && v !== undefined && v !== null) el.value = v;
    };
    setVal('ai_threshold', cfg.ai_threshold);
    updateThresholdBadge(cfg.ai_threshold);
    setVal('hardware_mode', cfg.hardware_mode);
    setVal('precision', cfg.precision);
    setVal('file_timeout_minutes', cfg.file_timeout_minutes);
    setVal('speech_language', cfg.speech_language || 'auto');
    setVal('target_api_url', cfg.target_api_url);
    setVal('target_anthropic_url', cfg.target_anthropic_url);
    $('anonymize_filenames').checked = Boolean(cfg.anonymize_filenames);
    $('check_updates').checked = cfg.check_updates !== false;
    $('auto_update').checked = cfg.auto_update !== false;
    if ($('enable_system2')) $('enable_system2').checked = cfg.enable_system2 !== false;
    tooltipsEnabled = cfg.enable_tooltips !== false;
    Tips.setEnabled(tooltipsEnabled);
    updatePresetButtons();
}

async function persistSettings(notify = true) {
    try {
        const { ok, data } = await postJson('/api/settings', { settings: gatherSettings() });
        if (!ok || !data.settings) return;
        if (data.status === 'locked') {
            showToast(data.message || updText('Impostazioni bloccate dall\'amministratore.', 'Settings locked by the administrator.'), 'error', 6000);
            applySettingsToUi(data.settings);
            return;
        }
        currentComplianceMode = data.settings.compliance_mode || currentComplianceMode;
        updatePresetButtons();
        if (notify) showToast(updText('Impostazioni salvate.', 'Settings saved.'), 'success', 2200);
    } catch (e) {
        showToast(updText('Impossibile salvare le impostazioni: Germano non risponde.', 'Cannot save the settings: Germano is not responding.'), 'error');
    }
}

async function loadInitialSettings() {
    try {
        const { ok, data } = await fetchJson('/api/settings');
        if (!ok) return;
        initialConfig = data;
        applySettingsToUi(data);
    } catch (e) { /* server non raggiungibile: gestito da pollStatus */ }
}

// ------------------------------------------------------------------ MOTORE
async function startEngine() {
    await postJson('/api/start', { settings: gatherSettings() });
}

async function ensureEngineRunning() {
    if (engineActive()) return true;
    showToast(updText('Avvio del motore in corso...', 'Starting the engine...'), 'info');
    try {
        await startEngine();
        await pollStatus();
        return true;
    } catch (e) {
        return false;
    }
}

async function waitForEngineReady(maxSeconds = 300) {
    const start = Date.now();
    while (Date.now() - start < maxSeconds * 1000) {
        await pollStatus();
        if (currentStatus === 'running') return true;
        if (currentStatus === 'error' || currentStatus === 'stopped') return false;
        await new Promise(r => setTimeout(r, 1500));
    }
    return currentStatus === 'running';
}

async function openLocalFolder(folder) {
    try {
        const { ok, data } = await postJson('/api/open_folder', { folder });
        if (!ok) showToast(data.message || updText('Impossibile aprire la cartella.', 'Cannot open the folder.'), 'error');
    } catch (e) {
        showToast(updText('Impossibile aprire la cartella: Germano non risponde.', 'Cannot open the folder: Germano is not responding.'), 'error');
    }
}

// ------------------------------------------------------------------ STATO
function setServerDown(down) {
    if (down === serverDown) return;
    serverDown = down;
    const banner = $('serverDownBanner');
    banner.hidden = !down || updateInstalling;
    if (down) {
        $('engineErrorBanner').hidden = true;
        $('statusDot').className = 'status-dot ' + (updateInstalling ? 'loading' : 'error');
        setText('statusText', updateInstalling ? 'Aggiornamento in corso...' : 'Germano non risponde');
    }
}

// ------------------------------------------------------------------ AGGIORNAMENTI SILENZIOSI (come Google Chrome)
// Nessun avviso che interrompe: controllo, download e preparazione avvengono in background; quando la nuova versione
// e' pronta compare solo un indicatore discreto «Riavvia per aggiornare» e la sezione Impostazioni › Aggiornamenti la
// descrive come chrome://settings/help. Al successivo avvio di Germano si applica da sola, in pochi secondi.
function updFmtTime(ts) {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    const time = d.toLocaleTimeString(uiLocale(), { hour: '2-digit', minute: '2-digit' });
    if (d.toDateString() === new Date().toDateString()) return updText(`oggi alle ${time}`, `today at ${time}`);
    return `${d.toLocaleDateString(uiLocale(), { day: '2-digit', month: '2-digit', year: 'numeric' })} ${time}`;
}

function renderUpdate(u) {
    if (!u) return;
    lastUpdate = u;
    const ready = u.state === 'ready';
    const pill = $('updatePill');
    pill.hidden = !ready;
    if (ready) {
        const days = u.ready_since ? (Date.now() / 1000 - u.ready_since) / 86400 : 0;
        pill.classList.toggle('is-old', days > 3);
        setText('updatePillText', u.manual ? updText('Aggiornamento pronto', 'Update ready') : updText('Riavvia per aggiornare', 'Restart to update'));
    } else {
        $('updatePop').hidden = true;
    }
    $('settingsDot').hidden = !ready;
    $('updatesDot').hidden = !(ready || u.state === 'error');
    if (u.state === 'installing') updateInstalling = true;
    if (currentTab === 'settings' && currentPane === 'updates') renderUpdatePanel(u);
}

function renderUpdatePanel(u) {
    if (!u) return;
    const box = $('updStatus');
    const pct = u.progress && u.progress.total ? Math.min(100, Math.round((100 * u.progress.done) / u.progress.total)) : 0;
    let cls = 'upd-status', icon = iconSvg('i-info'), title = '', sub = '', progress = false, install = false, check = true;
    const latest = u.latest || '';
    const checked = u.checked_at ? updText(`Ultimo controllo silenzioso: ${updFmtTime(u.checked_at)}`, `Last silent check: ${updFmtTime(u.checked_at)}`) : '';
    switch (u.state) {
        case 'checking':
            cls += ' is-busy'; icon = '<span class="spinner"></span>';
            title = updText('Controllo degli aggiornamenti…', 'Checking for updates…');
            check = false;
            break;
        case 'uptodate':
            cls += ' is-ok'; icon = iconSvg('i-check-circle');
            title = updText(`Germano AI è aggiornato (v${u.current})`, `Germano AI is up to date (v${u.current})`);
            sub = checked;
            break;
        case 'available':
            cls += ' is-busy';
            title = updText(`È disponibile la versione ${latest}`, `Version ${latest} is available`);
            sub = updText('L\'aggiornamento automatico è disattivato: attivalo qui sotto, oppure usa «Controlla ora» per scaricarla subito.',
                          'Automatic updating is off: turn it on below, or use «Check now» to download it right away.');
            break;
        case 'downloading':
            cls += ' is-busy'; icon = '<span class="spinner"></span>';
            title = updText('Download dell\'aggiornamento in background…', 'Downloading the update in the background…');
            sub = u.progress && u.progress.total
                ? updText(`Versione ${latest}: ${pct}% (${formatBytes(u.progress.done)} di ${formatBytes(u.progress.total)}) · bassa priorità, puoi continuare a lavorare`,
                          `Version ${latest}: ${pct}% (${formatBytes(u.progress.done)} of ${formatBytes(u.progress.total)}) · low priority, you can keep working`)
                : updText(`Versione ${latest}: ${formatBytes((u.progress || {}).done || 0)} scaricati`, `Version ${latest}: ${formatBytes((u.progress || {}).done || 0)} downloaded`);
            progress = true;
            check = false;
            break;
        case 'staging':
            cls += ' is-busy'; icon = '<span class="spinner"></span>';
            title = updText('Preparazione dell\'aggiornamento in background…', 'Preparing the update in the background…');
            sub = updText(`La versione ${latest} viene copiata accanto a quella in uso, con la priorità minima: al riavvio basteranno pochi secondi.`,
                          `Version ${latest} is being copied next to the one in use, at the lowest priority: restarting will take just a few seconds.`);
            check = false;
            break;
        case 'ready':
            cls += ' is-ready'; icon = iconSvg('i-refresh');
            if (u.manual) {
                title = updText(`La versione ${latest} è pronta da installare`, `Version ${latest} is ready to install`);
                sub = (u.platform === 'linux'
                    ? updText(`Pacchetto scaricato: ${u.package || ''}. Si installa con il gestore dei pacchetti (serve la password di amministratore)`, `Package downloaded: ${u.package || ''}. It installs with the package manager (administrator password needed)`)
                      + (u.install_command ? ` — ${u.install_command}` : '')
                    : updText(`Pacchetto scaricato: ${u.package || ''}. Si apre con il programma di installazione di macOS.`, `Package downloaded: ${u.package || ''}. It opens with the macOS installer.`));
                setText('btnUpdateInstall', updText('Apri il pacchetto', 'Open the package'));
            } else {
                title = updText(`Quasi aggiornato! Riavvia Germano per completare l'aggiornamento alla versione ${latest}`,
                                `Nearly up to date! Restart Germano to finish updating to version ${latest}`);
                sub = u.staged
                    ? updText('La nuova versione è già pronta: si applica in pochi secondi al prossimo avvio, oppure subito con il pulsante.',
                              'The new version is already prepared: it is applied in a few seconds at the next start, or right away with the button.')
                    : updText('Scaricata: la preparazione si completa in background; con il pulsante l\'installazione mostra il suo avanzamento.',
                              'Downloaded: preparation completes in the background; with the button the installation shows its progress.');
                setText('btnUpdateInstall', updText('Riavvia Germano per applicare l\'aggiornamento', 'Restart Germano to apply the update'));
            }
            install = true;
            break;
        case 'installing':
            cls += ' is-busy'; icon = '<span class="spinner"></span>';
            title = updText('Installazione dell\'aggiornamento…', 'Installing the update…');
            sub = updText('Germano si chiude e si riapre da solo tra pochi secondi.', 'Germano closes and reopens by itself in a few seconds.');
            check = false;
            break;
        case 'error':
            cls += ' is-error'; icon = iconSvg('i-alert');
            title = updText('Ultimo tentativo di aggiornamento non riuscito', 'Last update attempt failed');
            sub = (u.error || '') + updText(' Germano riproverà da solo al prossimo controllo.', ' Germano will try again by itself at the next check.');
            break;
        default:
            if (u.online === false) {
                title = updText('Nessuna connessione a Internet segnalata dal sistema', 'No Internet connection reported by the system');
                sub = updText('Il controllo silenzioso riprenderà da solo appena il computer è in linea.', 'The silent check resumes by itself as soon as the computer is online.');
            } else {
                title = updText(`Germano AI v${u.current}`, `Germano AI v${u.current}`);
                sub = updText('Il primo controllo silenzioso avviene pochi secondi dopo l\'avvio, poi ogni 6 ore.', 'The first silent check happens a few seconds after start, then every 6 hours.');
            }
    }
    box.className = cls;
    $('updIcon').innerHTML = icon;
    $('updTitle').textContent = title;
    $('updSub').textContent = sub;
    $('updProgress').hidden = !progress;
    $('updProgressBar').style.width = `${pct}%`;
    $('btnUpdateInstall').hidden = !install;
    $('btnUpdateCheck').hidden = !check;
    setText('updCurrent', u.current || '');
    setText('updPlatform', { windows: 'Windows', macos: 'macOS', linux: 'Linux' }[u.platform] || '');
    let info = updText('Fonte unica: ', 'Only source: ') + (u.source || 'https://download.germano.ai/') +
        updText(' · controllo automatico ogni 6 ore, solo con la connessione a Internet · download a bassa priorità',
                ' · automatic check every 6 hours, only with an Internet connection · low-priority download');
    const li = u.last_install;
    if (li && li.status === 'ok' && li.to === u.current) {
        info = updText(`✓ Aggiornato alla versione ${li.to} ${updFmtTime(li.time)}. `, `✓ Updated to version ${li.to} ${updFmtTime(li.time)}. `) + info;
    } else if (li && li.status !== 'ok' && li.target) {
        info = updText(`L'aggiornamento alla versione ${li.target} non è stato completato (${li.error || 'interrotto'}): la versione in uso non è cambiata. `,
                       `The update to version ${li.target} was not completed (${li.error || 'interrupted'}): the version in use has not changed. `) + info;
    }
    setText('updateInfo', info);
}

async function acknowledgeInstallResult() {
    const li = lastUpdate && lastUpdate.last_install;
    if (li && li.status === 'ok' && lastUpdate && li.to === lastUpdate.current) {
        setTimeout(() => postJson('/api/update/ack', {}).catch(() => {}), 8000);
    }
}

async function updateAction(path, okMessage) {
    try {
        const { ok, data } = await postJson(path, {});
        if (!ok) showToast(data.message || updText('Operazione non riuscita.', 'Operation failed.'), 'error', 6000);
        else if (okMessage) showToast(okMessage, 'info');
    } catch (e) {
        showToast(updText('Germano non risponde.', 'Germano is not responding.'), 'error');
    }
    pollStatus();
}

function openUpdatePop() {
    const u = lastUpdate;
    if (!u || u.state !== 'ready') return;
    const p = (lastStatus && lastStatus.progress) || {};
    const pending = lastStatus && lastStatus.stats ? lastStatus.stats.pending : 0;
    $('updatePopTitle').textContent = u.manual
        ? updText(`Germano AI ${u.latest} è pronto da installare`, `Germano AI ${u.latest} is ready to install`)
        : updText(`Germano AI ${u.latest} è pronto`, `Germano AI ${u.latest} is ready`);
    let text = u.manual
        ? updText('Il pacchetto è stato scaricato in background: aprilo quando vuoi con il programma di installazione del sistema.',
                  'The package was downloaded in the background: open it whenever you want with the system installer.')
        : updText('Riavvia Germano per applicarlo: richiede pochi secondi e Germano si riapre da solo. Cartelle, Vault e impostazioni restano intatti. Se non lo fai ora, si applica da solo al prossimo avvio.',
                  'Restart Germano to apply it: it takes a few seconds and Germano reopens by itself. Folders, Vault and settings are kept. If you do not do it now, it is applied by itself at the next start.');
    if (!u.manual && (p.state === 'working' || pending > 0)) {
        text += updText(' L\'elaborazione in corso verrà ripresa automaticamente dopo il riavvio.', ' The processing in progress will resume automatically after the restart.');
    }
    $('updatePopText').textContent = text;
    setText('btnUpdateRestart', u.manual ? updText('Apri il pacchetto', 'Open the package') : updText('Riavvia ora', 'Restart now'));
    $('updatePop').hidden = false;
}

async function installUpdate() {
    $('updatePop').hidden = true;
    const manual = lastUpdate && lastUpdate.manual;
    if (!manual) updateInstalling = true;
    try {
        const { ok, data } = await postJson('/api/update/install', {});
        if (!ok) {
            updateInstalling = false;
            showToast(data.message || updText('Operazione non riuscita.', 'Operation failed.'), 'error', 6000);
            return;
        }
        if (data.how === 'opened') showToast(updText('Pacchetto aperto con il programma di installazione del sistema.', 'Package opened with the system installer.'), 'info', 6000);
        else if (data.how === 'staged') showToast(updText('Germano si riavvia per aggiornarsi: tornerà tra pochi secondi.', 'Germano is restarting to update: it will be back in a few seconds.'), 'info', 8000);
        else showToast(updText('Installazione dell\'aggiornamento avviata: compare l\'avanzamento e Germano si riapre da solo.', 'Update installation started: the progress appears and Germano reopens by itself.'), 'info', 8000);
    } catch (e) {
        updateInstalling = false;
        showToast(updText('Germano non risponde.', 'Germano is not responding.'), 'error');
    }
    pollStatus();
}

function renderEngine(data) {
    const btn = $('mainToggleBtn');
    let dot = 'stopped', text = 'Motore in pausa', label = 'Avvia motore', active = false, disabled = false;
    if (data.status === 'running') {
        dot = 'running'; text = 'Motore attivo'; label = 'Arresta motore'; active = true;
    } else if (data.status === 'loading_models') {
        dot = 'loading'; text = 'Avvio del motore...'; label = 'Annulla avvio'; active = true;
    } else if (data.status === 'shutting_down') {
        dot = 'loading'; text = 'Arresto in corso...'; label = 'Arresto...'; active = true; disabled = true;
    } else if (data.status === 'error') {
        dot = 'error'; text = 'Motore fermo per errore';
    }
    $('statusDot').className = 'status-dot ' + dot;
    setText('statusText', text);
    setText('mainToggleLabel', label);
    btn.className = 'btn btn-sm ' + (active ? 'btn-stop' : 'btn-start');
    if (!btn.dataset.busy) btn.disabled = disabled;

    $('engineErrorBanner').hidden = data.status !== 'error';
    setText('engineErrorText', data.error || '');

    const proxy = $('proxyStatus');
    if (data.status === 'running') {
        proxy.className = 'badge badge-ok';
        proxy.textContent = updText('Proxy attivo', 'Proxy active');
    } else if (data.status === 'loading_models') {
        proxy.className = 'badge badge-warn';
        proxy.textContent = updText('Proxy in avvio', 'Proxy starting');
    } else {
        proxy.className = 'badge badge-off';
        proxy.textContent = updText('Proxy non attivo: avvia il motore', 'Proxy not active: start the engine');
    }
    const key = `${data.status}`;
    if (key !== lastEngineKey) {
        lastEngineKey = key;
        if (harness) harness.onEngineChange();
    }
}

function renderCounts(stats) {
    setText('tabCountOutput', stats.outputs);
    setText('tabCountInput', stats.pending);
    setText('tabCountFailed', stats.failed);
    setText('tabCountProcessed', stats.processed);
    setText('vaultCountBadge', stats.vault_count || 0);
    setText('advVaultCount', stats.vault_count || 0);
    document.querySelector('.tab-failed')?.classList.toggle('has-items', stats.failed > 0);

    // Cartelle di lavoro: numero di documenti in ogni riquadro
    const counts = { input: stats.pending, output: stats.outputs, processed: stats.processed, failed: stats.failed };
    FM_FOLDERS.forEach(folder => {
        const n = counts[folder] || 0;
        setText(`fmCount-${folder}`, n);
        $(`fmBox-${folder}`)?.classList.toggle('has-items', n > 0);
    });
    $('btnStartFromCta').hidden = !(stats.pending > 0 && (currentStatus === 'stopped' || currentStatus === 'error'));
}

function updateBatch(data, pending, running, working) {
    const p = data.progress || {};
    const done = (p.done || 0) + (p.restored || 0);
    const failed = p.failed || 0;
    if (!running) {
        batch.active = false;
        return;
    }
    if (done < batch.baseDone || failed < batch.baseFailed) {  // motore riavviato: contatori azzerati
        batch.baseDone = done;
        batch.baseFailed = failed;
    }
    if (!batch.active && (pending > 0 || working)) {
        batch = { active: true, baseDone: done, baseFailed: failed, done: 0, failed: 0, summary: null, startedAt: Date.now() };
    }
    if (!batch.active) return;
    batch.done = done - batch.baseDone;
    batch.failed = failed - batch.baseFailed;
    if (pending === 0 && !working) {
        batch.active = false;
        if (batch.done + batch.failed > 0) {
            batch.summary = { done: batch.done, failed: batch.failed, at: Date.now() };
            const msg = updText(`Lotto completato: ${plural(batch.done, 'documento elaborato', 'documenti elaborati')}`
                + (batch.failed ? `, ${plural(batch.failed, 'non riuscito', 'non riusciti')} (cartella failed).` : '.'),
                `Batch completed: ${plural(batch.done, 'document processed', 'documents processed')}`
                + (batch.failed ? `, ${batch.failed} failed (failed folder).` : '.'));
            showToast(msg, batch.failed ? 'warn' : 'success', 7000);
            fetchFiles();
        }
    }
}

function renderJob(data) {
    const p = data.progress || {};
    const pending = data.stats ? data.stats.pending : 0;
    const running = data.status === 'running';
    const working = running && p.state === 'working' && Boolean(p.current);
    updateBatch(data, pending, running, working);

    let title, file = '', detail, spin = false, cls = '';
    if (data.status === 'loading_models') {
        title = updText('Avvio del motore in corso', 'Starting the engine');
        detail = updText('Caricamento dei modelli di analisi: la prima volta può richiedere qualche minuto.',
            'Loading the analysis models: the first time it can take a few minutes.');
        spin = true;
    } else if (working) {
        title = updText('In lavorazione:', 'Processing:');
        file = p.current;
        detail = p.detail ? updText(`Fase: ${p.detail}`, `Stage: ${p.detail}`) : updText('Elaborazione in corso', 'Processing');
        spin = true;
    } else if (running && pending > 0) {
        title = updText('Documenti in arrivo', 'Documents arriving');
        detail = updText('Attendo che la copia dei file nella cartella input sia completata...',
            'Waiting for the files to finish copying into the input folder...');
        spin = true;
    } else if (batch.summary && Date.now() - batch.summary.at < 15 * 60 * 1000) {
        const s = batch.summary;
        const at = new Date(s.at).toLocaleTimeString(currentLang === 'en' ? 'en-GB' : 'it-IT', { hour: '2-digit', minute: '2-digit' });
        title = updText('Lotto completato', 'Batch completed');
        detail = updText(plural(s.done, 'documento elaborato', 'documenti elaborati')
            + (s.failed ? `, ${plural(s.failed, 'non riuscito', 'non riusciti')}` : '') + ` alle ${at}.`,
            plural(s.done, 'document processed', 'documents processed')
            + (s.failed ? `, ${s.failed} failed` : '') + ` at ${at}.`);
        cls = s.failed ? 'done-with-errors' : 'done';
    } else if (running) {
        title = updText('Motore attivo', 'Engine running');
        detail = updText('In attesa di documenti: trascinali nella cartella input qui sotto oppure copiali con il file manager.',
            'Waiting for documents: drag them into the input folder below or copy them with the file manager.');
    } else if (data.status === 'error') {
        title = updText('Motore fermo per errore', 'Engine stopped by an error');
        detail = updText('Il motivo è indicato in alto; il dettaglio è nel registro attività.',
            'The reason is shown at the top; the details are in the activity log.');
    } else {
        title = updText('Motore in pausa', 'Engine paused');
        detail = pending > 0
            ? updText(`${plural(pending, 'documento in attesa', 'documenti in attesa')} nella cartella input: verranno elaborati all'avvio del motore.`,
                `${plural(pending, 'document', 'documents')} waiting in the input folder: they will be processed when the engine starts.`)
            : updText('Aggiungi documenti: il motore si avvia automaticamente.', 'Add documents: the engine starts automatically.');
    }

    const progress = $('batchProgress');
    if (batch.active) {
        const processed = batch.done + batch.failed;
        const total = processed + pending;
        progress.hidden = false;
        $('batchProgressBar').style.width = `${total ? Math.round((100 * processed) / total) : 0}%`;
        detail += updText(` · Lotto: ${processed} di ${total}` + (batch.failed ? ` (${batch.failed} non riusciti)` : ''),
            ` · Batch: ${processed} of ${total}` + (batch.failed ? ` (${batch.failed} failed)` : ''));
    } else {
        progress.hidden = true;
    }
    $('currentJob').className = 'job fm-status' + (cls ? ' ' + cls : '');
    $('jobSpinner').hidden = !spin;
    setText('jobTitle', title);
    setText('jobFile', file);
    setText('jobDetail', detail);
}

function renderSystem(data) {
    if (!data.system) return;
    let t = `CPU ${data.system.cpu_percent}% · RAM ${data.system.ram_used_gb} / ${data.system.ram_total_gb} GB`;
    if (data.engine && data.engine.precision) t += ` · ${updText('modello', 'model')} ${String(data.engine.precision).toUpperCase()}`;
    setText('sysUsagePill', t);
}

function renderLiveStats(data) {
    const stats = data.stats || {};
    const pending = stats.pending || 0;
    const processed = batch.active ? batch.done + batch.failed : 0;
    const total = batch.active ? processed + pending : 0;
    setText('lsDone', processed);
    setText('lsTotal', total);
    // PII oscurate: somma dei dati oscurati nei documenti pronti (dato reale, da /api/files)
    const pii = (cachedFiles.output || []).reduce((s, it) => s + (typeof it.entities === 'number' ? it.entities : 0), 0);
    setText('lsPii', pii);
    // Throughput: documenti al minuto nel lotto in corso
    let tput = 0;
    if (batch.active && batch.startedAt) {
        const mins = (Date.now() - batch.startedAt) / 60000;
        if (mins > 0.05) tput = Math.round(processed / mins);
    }
    setText('lsThroughput', tput);
    if (data.system) {
        setText('lsCpu', data.system.cpu_percent);
        setText('lsRam', data.system.ram_percent);
    }
}

async function pollStatus() {
    let data;
    try {
        const r = await fetch('/api/status', { cache: 'no-store' });
        if (!r.ok) return;
        data = await r.json();
        setServerDown(false);
    } catch (e) {
        setServerDown(true);
        return;
    }
    if (pageVersion && data.version && data.version !== pageVersion) {
        location.reload();  // Germano è stato aggiornato: si carica la nuova Dashboard
        return;
    }
    pageVersion = pageVersion || data.version;
    lastStatus = data;
    currentStatus = data.status;
    renderUpdate(data.update);
    if (data.profile && data.profile !== currentComplianceMode) {
        currentComplianceMode = data.profile;
        updatePresetButtons();
    }
    if (typeof data.locked === 'boolean' && data.locked !== settingsLocked) {
        settingsLocked = data.locked;
        updateProfilePill();
    }
    renderEngine(data);
    if (data.stats) {
        renderCounts(data.stats);
        const sig = [data.stats.pending, data.stats.outputs, data.stats.failed, data.stats.processed,
            (data.progress || {}).current || ''].join('|');
        if (currentTab === 'sanitize' && (sig !== filesSignature || Date.now() - lastFilesFetch > 10000)) {
            filesSignature = sig;
            fetchFiles();
        }
    }
    renderJob(data);
    if (currentTab === 'sanitize') {
        renderFileManager();
        if (!fmPaths) loadFmPaths();
    }
    renderSystem(data);
    renderLiveStats(data);
    renderModeChip(data);
}

// ------------------------------------------------------------------ DOCUMENTI
async function fetchFiles() {
    lastFilesFetch = Date.now();
    try {
        const { ok, data } = await fetchJson('/api/files', { cache: 'no-store' });
        if (!ok) return;
        cachedFiles = data;
        renderFiles();
        renderFileManager();
    } catch (e) { /* server non raggiungibile: gestito da pollStatus */ }
}

// ------------------------------------------------------------------ CARTELLE DI LAVORO (anteprima del file manager)
// Quattro riquadri come in Esplora file: percorso completo sopra, i documenti dentro (aggiornati mentre il motore li
// prende da input e li sposta in output, processed o failed), trascinamento sulla cartella input, clic = apri cartella.
const FM_FOLDERS = ['input', 'output', 'processed', 'failed'];
const FM_MAX_ROWS = 200;
const FM_EMPTY = {
    input: ['Nessun documento in attesa.', 'No documents waiting.'],
    output: ['Nessun documento anonimizzato.', 'No anonymized documents yet.'],
    processed: ['Nessun originale archiviato.', 'No originals archived yet.'],
    failed: ['Nessun documento non riuscito.', 'No failed documents.']
};
let fmPaths = null;
let fmSeen = null;
let fmSignature = '';

async function loadFmPaths() {
    try {
        const { ok, data } = await fetchJson('/api/folders', { cache: 'no-store' });
        if (!ok || !data) return;
        fmPaths = data;
        [...FM_FOLDERS, 'extracted'].forEach(folder => {
            const el = $(`fmPath-${folder}`);
            if (!el || !data[folder]) return;
            setPathText(el, data[folder]);
            el.closest('[data-open-folder]')?.setAttribute('title', data[folder]);
        });
    } catch (e) { /* riprova al prossimo aggiornamento */ }
}

// Percorso che va a capo solo dopo una barra: i nomi delle cartelle restano interi (anche «Germano AI»), il testo
// copiato resta il percorso vero. Un nome lunghissimo può comunque andare a capo dove serve.
function setPathText(el, path) {
    el.textContent = '';
    (String(path).match(/[^\\/]*[\\/]?/g) || []).filter(Boolean).forEach((part, i) => {
        if (i) el.appendChild(document.createElement('wbr'));
        const seg = document.createElement('span');
        if (part.length <= 32) seg.className = 'fm-seg';
        seg.textContent = part;
        el.appendChild(seg);
    });
}

function fileIcon(name) {
    return iconSvg('i-files');
}

function fmRow(folder, it, current, isNew) {
    const name = String(it.name || '');
    const [dir, base] = splitPath(name);
    const busy = folder === 'input' && name === current;
    const info = `${name} · ${formatBytes(it.size)} · ${formatDate(it.mtime)}` + (it.reason ? `\n${it.reason}` : '');
    let meta;
    if (busy) {
        const phase = (lastStatus && lastStatus.progress && lastStatus.progress.detail) || '';
        meta = `<span class="badge badge-warn"><span class="spinner"></span>${escapeHtml(updText('in lavorazione', 'processing'))}${phase ? ' · ' + escapeHtml(phase) : ''}</span>`;
    } else if (folder === 'output' && (it.mode === 'restore' || base.startsWith('ripristinato_'))) {
        meta = `<span class="badge badge-info">${escapeHtml(updText('ripristinato', 'restored'))}</span>`;
    } else if (folder === 'output' && typeof it.entities === 'number') {
        meta = `<span class="fm-file-meta">${escapeHtml(updText(plural(it.entities, 'dato oscurato', 'dati oscurati'), plural(it.entities, 'item masked', 'items masked')))}</span>`;
    } else {
        meta = `<span class="fm-file-meta">${escapeHtml(folder === 'processed' ? formatDate(it.mtime) : formatBytes(it.size))}</span>`;
    }
    const reason = folder === 'failed'
        ? `<span class="fm-file-reason">${escapeHtml(it.reason || updText('Motivo non disponibile: vedi il registro attività.', 'Reason not available: see the activity log.'))}</span>`
        : '';
    const retry = folder === 'failed'
        ? `<button type="button" class="btn-icon fm-retry" data-fm-retry="${escapeHtml(name)}" title="${escapeHtml(updText('Rimetti in coda', 'Queue again'))}" aria-label="${escapeHtml(updText('Rimetti in coda', 'Queue again'))}">${iconSvg('i-retry')}</button>`
        : '';
    return `<li class="fm-file${busy ? ' fm-busy' : ''}${isNew ? ' fm-new' : ''}" title="${escapeHtml(info)}">
        <span class="fm-file-ico" aria-hidden="true">${fileIcon(base)}</span>
        <span class="fm-file-main"><span class="fm-file-name">${escapeHtml(base)}</span>${dir ? `<span class="fm-file-dir">${escapeHtml(dir)}/</span>` : ''}${reason}</span>
        ${meta}${retry}
    </li>`;
}

function renderFileManager(force = false) {
    if (!$('fmGrid')) return;
    const current = lastStatus && lastStatus.status === 'running' ? ((lastStatus.progress || {}).current || '') : '';
    const phase = current ? ((lastStatus.progress || {}).detail || '') : '';
    const totals = cachedFiles.totals || {};
    const sig = [currentLang, current, phase].concat(FM_FOLDERS.map(folder =>
        `${totals[folder] ?? ''}:` + (cachedFiles[folder] || []).slice(0, FM_MAX_ROWS)
            .map(it => `${it.name}@${it.mtime}@${it.entities ?? ''}@${it.reason ?? ''}`).join('|'))).join('#');
    if (!force && sig === fmSignature) return;
    fmSignature = sig;
    const first = fmSeen === null;
    const seen = {};
    FM_FOLDERS.forEach(folder => {
        let items = (cachedFiles[folder] || []).slice();
        if (folder === 'input' && current) {      // il documento in lavorazione sta in cima
            items.sort((a, b) => (b.name === current) - (a.name === current));
        }
        const total = totals[folder] ?? items.length;
        const shown = items.slice(0, FM_MAX_ROWS);
        const before = (fmSeen && fmSeen[folder]) || new Set();
        seen[folder] = new Set(items.map(it => it.name));
        let html = shown.map(it => fmRow(folder, it, current, !first && !before.has(it.name))).join('');
        if (!shown.length) {
            html = `<li class="fm-empty">${escapeHtml(updText(...FM_EMPTY[folder]))}</li>`;
        } else if (total > shown.length) {
            html += `<li class="fm-more">${escapeHtml(updText(`... e altri ${total - shown.length} documenti`, `... and ${total - shown.length} more documents`))}</li>`;
        }
        const list = $(`fmList-${folder}`);
        if (list) list.innerHTML = html;
    });
    fmSeen = seen;
}

async function retryFailedDocument(name) {
    const { ok, data } = await postJson('/api/retry_failed', { names: [name] });
    if (ok && (data.moved || []).length) {
        showToast(engineActive()
            ? updText('Documento rimesso in coda.', 'Document queued again.')
            : updText('Documento rimesso in coda: avvia il motore per elaborarlo.', 'Document queued again: start the engine to process it.'), 'success');
    } else {
        showToast((data.errors || [])[0] || data.message || updText('Impossibile rimettere in coda il documento.', 'The document could not be queued again.'), 'error');
    }
    await fetchFiles();
    pollStatus();
}

function setFileTab(folder) {
    activeFileTab = folder;
    document.querySelectorAll('.tab[data-folder]').forEach(t => {
        const on = t.dataset.folder === folder;
        t.classList.toggle('active', on);
        t.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    renderFiles();
}

function statusCell(folder, it, base, current) {
    if (folder === 'output') {
        if (it.mode === 'restore' || base.startsWith('ripristinato_')) {
            return `<span class="badge badge-info">${escapeHtml(updText('Dati ripristinati', 'Data restored'))}</span>`;
        }
        let html = `<span class="badge badge-ok">${escapeHtml(updText('Anonimizzato', 'Anonymized'))}</span>`;
        if (typeof it.entities === 'number') {
            html += `<span class="status-sub">${escapeHtml(updText(plural(it.entities, 'dato oscurato', 'dati oscurati'), plural(it.entities, 'item masked', 'items masked')))}</span>`;
        }
        if (it.notes) html += `<span class="status-sub">${escapeHtml(updText(`${plural(it.notes, 'avviso', 'avvisi')} nel report`, `${plural(it.notes, 'note', 'notes')} in the report`))}</span>`;
        return html;
    }
    if (folder === 'input') {
        return it.name === current
            ? `<span class="badge badge-warn"><span class="spinner"></span>${escapeHtml(updText('In lavorazione', 'Processing'))}</span>`
            : `<span class="badge">${escapeHtml(updText('In attesa', 'Pending'))}</span>`;
    }
    if (folder === 'failed') return `<span class="badge badge-danger">${escapeHtml(updText('Non riuscito', 'Failed'))}</span>`;
    return `<span class="badge badge-off">${escapeHtml(updText('Originale', 'Original'))}</span>`;
}

function actionsCell(folder, it) {
    const btn = (action, icon, title) =>
        `<button type="button" class="btn-icon" data-action="${action}" title="${title}" aria-label="${title}">${iconSvg(icon)}</button>`;
    const href = '/api/download/' + folder + '/' + it.name.split('/').map(encodeURIComponent).join('/');
    const dl = escapeHtml(updText('Scarica una copia', 'Download a copy'));
    const download = `<a class="btn-icon" href="${escapeHtml(href)}" download title="${dl}" aria-label="${dl}">${iconSvg('i-download')}</a>`;
    const reveal = btn('reveal', 'i-locate', escapeHtml(updText('Mostra nella cartella', 'Show in folder')));
    if (folder === 'input') return reveal;
    if (folder === 'failed') {
        return `<button type="button" class="btn btn-secondary btn-sm" data-action="retry">${iconSvg('i-retry')}${escapeHtml(updText('Rimetti in coda', 'Queue again'))}</button>${reveal}${download}`;
    }
    return btn('open', 'i-external', escapeHtml(updText('Apri', 'Open'))) + reveal + download;
}

function renderFiles() {
    const folder = activeFileTab;
    const all = cachedFiles[folder] || [];
    const totals = cachedFiles.totals || {};
    const total = totals[folder] ?? all.length;
    const q = ($('fileFilter').value || '').trim().toLowerCase();
    const items = q ? all.filter(it => `${it.name} ${it.reason || ''}`.toLowerCase().includes(q)) : all;
    const current = lastStatus && lastStatus.status === 'running' ? (lastStatus.progress || {}).current : null;

    $('fileTableBody').innerHTML = items.map(it => {
        const name = String(it.name || '');
        const [dir, base] = splitPath(name);
        const reason = folder === 'failed'
            ? `<div class="file-reason">${escapeHtml(it.reason || updText('Motivo non disponibile: vedi il registro attività.', 'Reason not available: see the activity log.'))}</div>`
            : '';
        return `<tr data-name="${escapeHtml(name)}">
            <td class="col-name"><div class="file-name">${escapeHtml(base)}</div>${dir ? `<div class="file-dir">${escapeHtml(dir)}/</div>` : ''}${reason}</td>
            <td class="col-status">${statusCell(folder, it, base, current)}</td>
            <td class="col-size">${formatBytes(it.size)}</td>
            <td class="col-date">${formatDate(it.mtime)}</td>
            <td class="col-actions"><div class="row-actions">${actionsCell(folder, it)}</div></td>
        </tr>`;
    }).join('');

    const empty = $('fileEmpty');
    empty.hidden = items.length > 0;
    empty.textContent = q ? updText('Nessun documento corrisponde al filtro.', 'No document matches the filter.') : updText(EMPTY_MESSAGES[folder], {
        output: 'No ready documents. Add documents above or copy them into the input folder.', input: 'No pending documents.',
        failed: 'No failed documents.', processed: 'No archived originals.' }[folder]);

    let info = '';
    if (q) info = updText(`${items.length} di ${all.length} documenti`, `${items.length} of ${all.length} documents`);
    else if (total > all.length) info = updText(`Mostrati i ${all.length} più recenti su ${total}`, `Showing the ${all.length} most recent of ${total}`);
    else if (total) info = updText(plural(total, 'documento', 'documenti'), plural(total, 'document', 'documents'));
    setText('fileListInfo', info);
    $('btnRetryAll').hidden = !(folder === 'failed' && all.length > 0);
    setText('btnOpenCurrentFolderLabel', updText(`Apri cartella ${folder}`, `Open ${folder} folder`));
    $('btnExportCsv').disabled = all.length === 0;
}

async function fileAction(action, name) {
    const folder = activeFileTab;
    if (action === 'retry') {
        await retryFailedDocument(name);
        return;
    }
    const { ok, data } = await postJson('/api/file_action', { folder, name, action });
    if (!ok) showToast(data.message || updText('Operazione non riuscita.', 'Operation failed.'), 'error', 6000);
}

async function retryAllFailed() {
    const n = (cachedFiles.totals || {}).failed || (cachedFiles.failed || []).length;
    if (!n || !confirm(updText(`Rimettere in coda ${plural(n, 'documento non riuscito', 'documenti non riusciti')}?\nVerranno spostati di nuovo nella cartella input.`,
                               `Queue again ${plural(n, 'failed document', 'failed documents')}?\nThey will be moved back to the input folder.`))) return;
    const { ok, data } = await postJson('/api/retry_failed', { all: true });
    if (ok) {
        const moved = (data.moved || []).length;
        showToast(updText(`${plural(moved, 'documento rimesso', 'documenti rimessi')} in coda.`, `${plural(moved, 'document', 'documents')} queued again.`)
                  + (engineActive() ? '' : updText(' Avvia il motore per elaborarli.', ' Start the engine to process them.')), 'success');
        (data.errors || []).slice(0, 3).forEach(err => showToast(err, 'error', 6000));
    } else {
        showToast(data.message || updText('Operazione non riuscita.', 'Operation failed.'), 'error');
    }
    await fetchFiles();
    pollStatus();
}

function csvCell(value) {
    let s = String(value ?? '');
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;  // evita che Excel interpreti il testo come formula
    return /[";\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function exportCsv() {
    const folder = activeFileTab;
    const items = cachedFiles[folder] || [];
    if (!items.length) return;
    const head = ['Documento', 'Sottocartella', 'Cartella', 'Esito', 'Dati oscurati', 'Motivo', 'Dimensione (byte)', 'Data'];
    const rows = items.map(it => {
        const [dir, base] = splitPath(String(it.name || ''));
        let esito = STATUS_LABELS[folder];
        if (folder === 'output' && (it.mode === 'restore' || base.startsWith('ripristinato_'))) esito = 'Dati ripristinati';
        const date = it.mtime ? new Date(it.mtime * 1000).toLocaleString('it-IT') : '';
        return [base, dir, folder, esito, typeof it.entities === 'number' ? it.entities : '', it.reason || '', it.size, date];
    });
    const csv = [head, ...rows].map(r => r.map(csvCell).join(';')).join('\r\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `germano_${folder}_${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

// ------------------------------------------------------------------ CARICAMENTO FILE E CARTELLE
function readAllEntries(dirReader) {
    return new Promise((resolve) => {
        const all = [];
        const next = () => dirReader.readEntries(entries => {
            if (!entries.length) return resolve(all);
            all.push(...entries);
            next();
        }, () => resolve(all));
        next();
    });
}

async function collectEntry(entry, prefix, out) {
    if (!entry) return;
    if (entry.isFile) {
        await new Promise(res => entry.file(f => { out.push({ file: f, path: prefix + f.name }); res(); }, () => res()));
    } else if (entry.isDirectory) {
        const entries = await readAllEntries(entry.createReader());
        for (const e of entries) await collectEntry(e, prefix + entry.name + '/', out);
    }
}

async function filesFromDrop(dataTransfer) {
    const items = dataTransfer.items ? Array.from(dataTransfer.items) : [];
    const entries = items.map(it => (it.webkitGetAsEntry ? it.webkitGetAsEntry() : null)).filter(Boolean);
    if (entries.length) {
        const out = [];
        for (const e of entries) await collectEntry(e, '', out);
        return out;
    }
    return Array.from(dataTransfer.files || []).map(f => ({ file: f, path: f.name }));
}

async function uploadFiles(list) {
    if (!list || !list.length) return;
    const formData = new FormData();
    list.forEach(({ file, path }) => {
        formData.append('files', file, file.name);
        formData.append('paths', path || file.name);
    });
    showToast(list.length === 1
        ? updText('Copia del documento nella cartella input...', 'Copying the document into the input folder...')
        : updText(`Copia di ${list.length} documenti nella cartella input...`, `Copying ${list.length} documents into the input folder...`), 'info');
    try {
        const { ok, data } = await fetchJson('/api/upload_files', { method: 'POST', body: formData });
        if (!ok || data.status !== 'success') {
            showToast(data.message || updText('Errore durante il caricamento.', 'Upload error.'), 'error');
            return;
        }
        if (data.auto_restored_count > 0) {
            showToast(updText(`${plural(data.auto_restored_count, 'file restituito', 'file restituiti')} dall'AI: dati originali ripristinati (cartella output).`,
                `${plural(data.auto_restored_count, 'file returned', 'files returned')} by the AI: original data restored (output folder).`), 'success', 6000);
            setFileTab('output');
        }
        if (data.saved_count > 0) {
            showToast(updText(`${plural(data.saved_count, 'documento aggiunto', 'documenti aggiunti')} alla cartella input.`,
                `${plural(data.saved_count, 'document added', 'documents added')} to the input folder.`), 'success');
            await ensureEngineRunning();
        }
        (data.errors || []).forEach(err => showToast(updText(`Errore: ${err}`, `Error: ${err}`), 'error', 7000));
        fetchFiles();
        pollStatus();
    } catch (e) {
        showToast(updText('Errore di connessione durante il caricamento.', 'Connection error during the upload.'), 'error');
    }
}

// ------------------------------------------------------------------ PROXY E API
function renderAgents() {
    const base = proxyBase();
    const openai = `${base}/v1`;
    const anthropic = base;
    setText('openaiBase', openai);
    setText('anthropicBase', anthropic);
    $('agentsTableBody').innerHTML = AGENTS.map(a => {
        const url = a.base === 'anthropic' ? anthropic : openai;
        const snippet = a.snippet ? a.snippet(openai, anthropic) : '';
        return `<tr>
            <td class="agent-name">${escapeHtml(a.name)}</td>
            <td><span class="badge">${escapeHtml(a.format)}</span></td>
            <td><div class="copy-line"><code>${escapeHtml(url)}</code>${copyButton(url, 'Copia indirizzo')}</div></td>
            <td>${escapeHtml(a.where)}${snippet ? `<div class="copy-line"><code>${escapeHtml(snippet)}</code>${copyButton(snippet, 'Copia comando')}</div>` : ''}</td>
        </tr>`;
    }).join('');
    $('restTableBody').innerHTML = REST_ENDPOINTS.map(e => {
        const example = e.example(base);
        return `<tr>
            <td><span class="method${e.method === 'GET' ? ' method-get' : ''}">${e.method}</span></td>
            <td><code>${escapeHtml(e.path)}</code></td>
            <td>${escapeHtml(e.desc)}</td>
            <td>${copyButton(example, 'Copia esempio curl')}</td>
        </tr>`;
    }).join('');
}

// ------------------------------------------------------------------ SISTEMA
async function loadFolders() {
    if (foldersLoaded) return;
    try {
        const { ok, data } = await fetchJson('/api/folders');
        if (!ok) return;
        foldersLoaded = true;
        $('foldersList').innerHTML = FOLDER_INFO.map(([key, label, sub]) => `
            <div class="folder-row">
                <div class="folder-name">${escapeHtml(label)}<small>${escapeHtml(sub)}</small></div>
                <div class="folder-path">${escapeHtml(data[key] || '')}</div>
                <div class="btn-group">
                    ${copyButton(data[key] || '', 'Copia percorso')}
                    <button type="button" class="btn btn-secondary btn-sm" data-open-folder="${key}">${iconSvg('i-folder')}${escapeHtml(updText('Apri', 'Open'))}</button>
                </div>
            </div>`).join('');
    } catch (e) { /* riprova alla prossima apertura della sezione */ }
}

async function pollLogs() {
    if (currentTab !== 'settings' || currentPane !== 'system') return;
    try {
        const { ok, data } = await fetchJson('/api/logs', { cache: 'no-store' });
        const term = $('logTerminal');
        if (!ok || !data.logs || !data.logs.length) return;
        const atBottom = term.scrollHeight - term.clientHeight <= term.scrollTop + 30;
        term.innerHTML = data.logs.map(line => {
            let cls = 'log-line';
            if (/ERRORE|FATALE|Traceback/.test(line)) cls += ' error';
            else if (/ATTENZIONE|Avviso|nota:/.test(line)) cls += ' warn';
            else if (/Completato|PRONTO|ripristin/.test(line)) cls += ' success';
            return `<div class="${cls}">${escapeHtml(line.replace(/\s+$/, ''))}</div>`;
        }).join('');
        if (atBottom) term.scrollTop = term.scrollHeight;
    } catch (e) { /* ignora */ }
}

let vaultItems = [];

function renderVaultRows() {
    const box = $('vaultPreviewBox');
    const q = ($('vaultFilter').value || '').trim().toLowerCase();
    const items = q ? vaultItems.filter(it => `${it.tag} ${it.value}`.toLowerCase().includes(q)) : vaultItems;
    box.innerHTML = items.length
        ? items.slice(0, 2000).map(it => `<div class="vault-row"><code>${escapeHtml(it.tag)}</code><span>${escapeHtml(it.value)}</span></div>`).join('')
        : `<div class="vault-empty">${escapeHtml(vaultItems.length ? updText('Nessuna corrispondenza trovata.', 'No mapping found.') : updText('Nessuna corrispondenza in archivio.', 'No mapping in the archive.'))}</div>`;
}

async function toggleVault() {
    const box = $('vaultPreviewBox');
    if (!box.hidden) {
        box.hidden = true;
        $('vaultSearchRow').hidden = true;
        vaultItems = [];
        setText('btnShowVault', 'Mostra');
        return;
    }
    try {
        const { data } = await fetchJson('/api/vault', { cache: 'no-store' });
        vaultItems = data.items || [];
        renderVaultRows();
        box.hidden = false;
        $('vaultSearchRow').hidden = vaultItems.length < 8;
        setText('btnShowVault', 'Nascondi');
    } catch (e) { /* ignora */ }
}

// ------------------------------------------------------------------ TESTO
function setTextBadge(text) {
    const badge = $('textEntityBadge');
    badge.hidden = !text;
    badge.textContent = text || '';
}

async function restoreTextIfTagged(text) {
    const deanonOn = $('enable_deanonymize')?.checked ?? true;
    if (!deanonOn || !text || !/\[\s*[A-ZÀ-Ÿ.\s\/_]+[_\s]\d+\s*\]/i.test(text)) return false;
    try {
        const { ok, data } = await postJson('/api/v1/deanonymize_text', { text });
        if (ok && data.restored && data.restored !== text) {
            $('manualOutputText').value = data.restored;
            setTextBadge(updText('Dati originali ripristinati', 'Original data restored'));
            showToast(updText('Risposta dell\'AI riconosciuta: dati originali ripristinati.', 'AI answer recognized: original data restored.'), 'success');
            return true;
        }
    } catch (e) { /* ignora */ }
    return false;
}

async function anonymizeText() {
    const btn = $('anonymizeTextBtn');
    const label = btn.querySelector('span');
    const text = ($('manualInputText').value || '').trim();
    if (!text) {
        showToast(updText('Scrivi o incolla prima un testo.', 'Type or paste a text first.'), 'error');
        return;
    }
    if (await restoreTextIfTagged(text)) return;
    btn.disabled = true;
    const original = label.textContent;
    try {
        if (currentStatus !== 'running') {
            label.textContent = updText('Avvio del motore...', 'Starting the engine...');
            await ensureEngineRunning();
            if (!(await waitForEngineReady())) {
                showToast(updText('Il motore non si è avviato: controlla il messaggio in alto.', 'The engine did not start: check the message at the top.'), 'error', 6000);
                return;
            }
        }
        label.textContent = updText('Elaborazione...', 'Processing...');
        const { ok, data } = await postJson('/api/v1/anonymize_text', { text });
        if (ok && data.anonymized !== undefined) {
            $('manualOutputText').value = data.anonymized;
            if (data.auto_restored) {
                setTextBadge(updText('Dati originali ripristinati', 'Original data restored'));
            } else {
                const n = (data.extracted_data || []).length;
                setTextBadge(updText(plural(n, 'dato oscurato', 'dati oscurati'), plural(n, 'item masked', 'items masked')));
                showToast(updText(`Testo anonimizzato: ${plural(n, 'dato oscurato', 'dati oscurati')}.`, `Text anonymized: ${plural(n, 'item masked', 'items masked')}.`), 'success');
            }
            pollStatus();
        } else {
            showToast(data.error || updText('Errore durante l\'elaborazione del testo.', 'Error while processing the text.'), 'error');
        }
    } catch (e) {
        showToast(updText('Errore di comunicazione con il motore locale.', 'Communication error with the local engine.'), 'error');
    } finally {
        btn.disabled = false;
        label.textContent = original;
    }
}

// ------------------------------------------------------------------ SUGGERIMENTI (TOOLTIPS)
// Un suggerimento per ogni elemento dell'interfaccia: [selettore, titolo, testo]. Titolo e testo possono essere
// funzioni (elemento, titolo_nativo) => stringa per i contenuti che dipendono dall'elemento. Hanno la precedenza
// gli attributi data-tip / data-tip-title; i "title" nativi diventano suggerimenti (mai due finestrelle insieme).
const NOTE_CINA = ' Server in Cina: i dati, anche se pseudonimizzati, escono dall\'Unione Europea verso un Paese senza ' +
    'decisione di adeguatezza. Verifica con il DPO prima di usarlo con dati della PA.';
const optTitle = (el) => (el.querySelector('.option-title')?.childNodes[0]?.textContent || '').trim();
const TIPS = [
    // --- intestazione
    ['.brand', 'Germano AI', 'Torna alla pagina iniziale.'],
    ['#tabHarness', '🧠 Harness AI', 'Conversazione con l\'AI che scegli in basso a destra (CLI, modelli locali o servizi via API): Germano oscura i dati personali prima dell\'invio e li rimette nella risposta. La Glass Window mostra tutto in tempo reale.'],
    ['#tabSanitize', '📂 Sanitizzazione manuale e Vault', 'Cartelle di lavoro con trascinamento dei file, documenti elaborati, testo da anonimizzare o ripristinare e archivio delle corrispondenze (Vault).'],
    ['#tabSettings', '⚙️ Impostazioni', 'Modalità operativa e rete, profilo e modelli, AI e chiavi, Proxy e API, sistema e registro, aggiornamenti.'],
    ['#tabGuide', '📖 Guida', 'Manuale d\'uso completo e documentazione tecnica, consultabili offline.'],
    ['#updatePill', 'Aggiornamento pronto', 'La nuova versione è stata scaricata e preparata in background: riavvia Germano quando vuoi (pochi secondi), altrimenti si applica da sola al prossimo avvio.'],
    ['#profilePill', 'Profilo di protezione', (el, n) => n || 'PA: tutti i modelli e tutte le categorie con sensibilità massima. PD: configurazione personalizzata.'],
    ['#engineStatusPill', 'Stato del motore', () => {
        let t = 'Il motore esegue i modelli di anonimizzazione. Verde = attivo, giallo = in avvio, grigio = in pausa, rosso = fermo per errore.';
        const eng = (lastStatus && lastStatus.running && lastStatus.engine) || null;
        if (eng && eng.mode === 'remote') t += ` Calcolo affidato al Germano Server «${eng.server_name || eng.server}» (${eng.server}).`;
        else if (eng && eng.device) t += ` Calcolo su ${String(eng.device).toUpperCase()}${eng.threads ? ` (${eng.threads} thread su ${eng.cpus || '?'} processori)` : ''}${eng.precision ? `, precisione ${String(eng.precision).toUpperCase()}` : ''}${eng.vm ? `, macchina virtuale ${eng.vm}` : ''}.`;
        return t;
    }],
    ['#modeChip', 'Modalità operativa', (el) => `Questo computer è in modalità «${(el.textContent || '').trim()}». Clicca per scegliere Standalone, Server, Client o Server + Client.`],
    ['#mainToggleBtn', 'Avvia / arresta il motore', 'Avvia il motore per proteggere le richieste dell\'Harness e del Proxy ed elaborare i documenti. A motore fermo nessun dato esce in chiaro: le richieste vengono bloccate (l\'Harness lo avvia da solo al primo invio).'],
    // --- avvisi
    ['#retryEngineBtn', 'Riprova', 'Riavvia il motore dopo l\'errore indicato.'],
    ['#killOrphansBtn', 'Chiudi processi secondari', 'Chiude i processi del motore rimasti aperti da una sessione precedente e libera memoria.'],
    // --- cartelle e statistiche
    ['.fm-box[data-fm-box="input"]', '📥 input — documenti da elaborare', 'Trascina qui file o intere cartelle (oppure copiali con il file manager): il motore li anonimizza uno alla volta. Clicca il riquadro per aprire la cartella.'],
    ['.fm-box[data-fm-box="output"]', '📤 output — documenti anonimizzati', 'I risultati, con la stessa struttura di sottocartelle degli originali. Clicca il riquadro per aprire la cartella.'],
    ['.fm-box[data-fm-box="processed"]', '🗂️ processed — originali', 'Gli originali, spostati qui dopo l\'elaborazione: contengono dati personali in chiaro. Clicca il riquadro per aprire la cartella.'],
    ['.fm-box[data-fm-box="failed"]', '⚠️ failed — non riusciti', 'Documenti che non è stato possibile elaborare, con il motivo; il pulsante ↻ li rimette in coda. Clicca il riquadro per aprire la cartella.'],
    ['.fm-path', 'Percorso della cartella', (el, n) => `${n || ''}${n ? '\n' : ''}Percorso completo della cartella sul disco. Clicca per aprirla.`],
    ['.fm-vault', '🔐 Vault e report — cartella extracted', 'Archivio delle corrispondenze etichetta ↔ dato reale, report di audit e registri. Contiene dati in chiaro: conservala su un disco protetto (es. BitLocker). Clicca per aprire la cartella.'],
    ['.ls:has(#lsDone)', 'Documenti del lotto', 'Documenti già elaborati sul totale del lotto in corso.'],
    ['.ls:has(#lsPii)', 'Dati personali oscurati', 'Totale dei dati personali sostituiti con etichette nei documenti pronti.'],
    ['.ls:has(#lsThroughput)', 'Velocità', 'Documenti elaborati al minuto nel lotto in corso.'],
    ['.ls:has(#lsCpu)', 'Processore', 'Uso attuale del processore di questo computer.'],
    ['.ls:has(#lsRam)', 'Memoria', 'Uso attuale della memoria RAM di questo computer.'],
    ['#btnPickFiles', 'Seleziona file', 'Scegli uno o più documenti da copiare nella cartella input.'],
    ['#btnPickFolder', 'Seleziona cartella', 'Aggiungi un\'intera cartella: la struttura delle sottocartelle viene mantenuta in output.'],
    ['.fm-retry', 'Rimetti in coda', 'Sposta il documento di nuovo nella cartella input per elaborarlo un\'altra volta.'],
    ['#currentJob', 'Lavorazione in corso', 'Stato del motore, documento in elaborazione, fase attuale e avanzamento del lotto.'],
    ['#btnStartFromCta', 'Avvia elaborazione', 'Avvia il motore per elaborare i documenti in attesa.'],
    ['.restore-row .switch', 'Ripristino automatico dei dati', 'Le etichette sono numerate e le corrispondenze restano nell\'archivio locale: quando un testo o un file restituito dall\'AI le contiene, i dati originali tornano al loro posto. Disattivato: anonimizzazione irreversibile.'],
    // --- documenti
    ['.tab[data-folder="output"]', 'Pronti', 'Documenti anonimizzati (o ripristinati) disponibili nella cartella output.'],
    ['.tab[data-folder="input"]', 'In attesa', 'Documenti nella cartella input, in coda o in lavorazione.'],
    ['.tab[data-folder="failed"]', 'Non riusciti', 'Documenti non elaborati, con il motivo e il pulsante per rimetterli in coda.'],
    ['.tab[data-folder="processed"]', 'Originali', 'Documenti originali archiviati dopo l\'elaborazione.'],
    ['#fileFilter', 'Filtro', 'Mostra solo i documenti il cui nome, cartella o motivo contiene il testo scritto.'],
    ['#btnRetryAll', 'Rimetti tutti in coda', 'Sposta di nuovo nella cartella input tutti i documenti non riusciti.'],
    ['#btnOpenCurrentFolder', 'Apri cartella', 'Apre nel file manager la cartella della scheda selezionata.'],
    ['#btnExportCsv', 'Esporta elenco', 'Scarica l\'elenco in formato CSV (si apre con Excel; separatore «;»).'],
    ['[data-action="open"]', 'Apri', 'Apre il documento con il programma predefinito del sistema.'],
    ['[data-action="reveal"]', 'Mostra nella cartella', 'Apre il file manager con il documento selezionato.'],
    ['[data-action="retry"]', 'Rimetti in coda', 'Sposta il documento di nuovo nella cartella input per elaborarlo un\'altra volta.'],
    ['.row-actions a[download]', 'Scarica una copia', 'Scarica una copia del documento.'],
    // --- testo e Vault
    ['#manualInputText', 'Testo', 'Incolla un testo da anonimizzare, oppure la risposta di un\'AI con etichette come [PERSONA_1] da ripristinare.'],
    ['#anonymizeTextBtn', 'Anonimizza testo', 'Sostituisce i dati personali con etichette numerate, pronte da inviare a un servizio di AI.'],
    ['#manualOutputText', 'Risultato', 'Testo anonimizzato oppure ripristinato con i dati originali.'],
    ['#copyTextBtn', 'Copia risultato', 'Copia il risultato negli appunti.'],
    ['#btnShowVault', 'Mostra archivio', 'Mostra le corrispondenze tra etichette e dati originali (dati in chiaro), con la ricerca.'],
    ['#btnClearVault', 'Svuota archivio', 'Cancella tutte le corrispondenze: i documenti già anonimizzati non potranno più essere ripristinati.'],
    // --- impostazioni
    ['.settings-link[data-pane="general"]', 'Modalità e rete', 'Standalone, Server, Client o Server + Client; accesso dalla rete e utenti; suggerimenti.'],
    ['.settings-link[data-pane="protection"]', 'Protezione e modelli', 'Profilo PA/PD, sensibilità, modelli di analisi attivi e categorie di dati da oscurare.'],
    ['.settings-link[data-pane="ai"]', 'AI, chiavi e Harness', 'AI rilevate, chiavi API dei servizi e preferenze dell\'Harness (revisione prima dell\'invio, anteprima, cronologia).'],
    ['.settings-link[data-pane="proxy"]', 'Proxy e API', 'Indirizzi del Proxy per Claude Code, Codex, Cursor e altri strumenti, servizi di destinazione ed esempi delle API REST.'],
    ['.settings-link[data-pane="system"]', 'Sistema e registro', 'Esecuzione del motore, cartelle di lavoro e registro attività.'],
    ['.settings-link[data-pane="updates"]', 'Aggiornamenti', 'Aggiornamenti silenziosi come Google Chrome: stato, ultimo controllo e riavvio per applicare.'],
    ['#proxyStatus', 'Stato del Proxy', 'Il Proxy protegge le richieste solo con il motore attivo; altrimenti le blocca e nessun dato esce in chiaro.'],
    ['.endpoint:has(#openaiBase)', 'Indirizzo formato OpenAI', 'Base URL da impostare negli strumenti compatibili OpenAI (Chat Completions e Responses).'],
    ['.endpoint:has(#anthropicBase)', 'Indirizzo formato Anthropic', 'Base URL per Claude Code e gli SDK Anthropic (variabile ANTHROPIC_BASE_URL).'],
    ['#target_api_url', 'Servizio OpenAI o compatibile', 'Indirizzo a cui il Proxy inoltra le richieste in formato OpenAI dopo averle anonimizzate.'],
    ['#target_anthropic_url', 'Servizio Anthropic (Claude)', 'Indirizzo a cui il Proxy inoltra le richieste in formato Anthropic dopo averle anonimizzate.'],
    ['.preset-target', (el) => `Preimposta: ${(el.textContent || '').trim()}`, (el) => {
        const url = el.dataset.url || '';
        let t = `Imposta come servizio di destinazione in formato OpenAI: ${url}. La chiave API resta quella del servizio, inserita nel tuo strumento.`;
        if (/deepseek\.com|moonshot\.cn|dashscope\.aliyuncs\.com/i.test(url)) t += NOTE_CINA;
        if (/127\.0\.0\.1|localhost/i.test(url)) t += ' Modelli eseguiti su questo computer con Ollama: nessun dato esce in rete.';
        return t;
    }],
    ['#btnPresetPA', 'Tutto attivo (profilo PA)', 'Attiva tutti i modelli e tutte le categorie con sensibilità massima.'],
    ['#btnPresetEssential', 'Solo dati essenziali', 'Oscura soltanto nomi, indirizzi, codici fiscali e partite IVA, email e telefoni.'],
    ['#btnPresetNone', 'Nessuna categoria', 'Disattiva tutte le categorie: non viene oscurato alcun dato.'],
    ['.field-range:has(#ai_threshold)', 'Sensibilità dei modelli', 'Soglia 0% = si oscura ogni possibile dato personale. Alzandola si riducono i falsi positivi, ma alcuni dati incerti possono restare in chiaro.'],
    ['#btnModelsAllOn', 'Attiva tutti i modelli', 'Usa tutti i modelli locali e le regole deterministiche.'],
    ['#btnModelsAllOff', 'Disattiva tutti i modelli', 'Nessun modello di analisi: verrebbe oscurato poco o nulla.'],
    ['.option:has(.model-check)', optTitle, (el) => `${(el.querySelector('.option-desc')?.textContent || '').trim()} Clicca per attivare o disattivare il modello.`],
    ['.option:has(.cat-check)', optTitle, (el) => `Etichetta usata nei documenti: ${(el.querySelector('.option-desc')?.textContent || '').trim()}. Clicca per oscurare o lasciare in chiaro questa categoria.`],
    ['#netSummary', 'Modalità e rete', 'Stato attuale: ascolto sulla rete, collegamento al Germano Server e accesso dalla rete (libero o con utente e password).'],
    ['.field:has(#hardware_mode)', 'Calcolo', 'Automatico usa una scheda video NVIDIA se presente, altrimenti il processore.'],
    ['.field:has(#precision)', 'Precisione del modello', 'FP32 è più veloce ma usa più memoria; BF16 la dimezza ed è più lento sui processori meno recenti. Vale dal prossimo avvio del motore.'],
    ['.field:has(#file_timeout_minutes)', 'Tempo massimo per documento', 'Oltre questo tempo il documento viene interrotto e spostato tra i non riusciti. Per le registrazioni audio il tempo si allunga da solo in base alla durata.'],
    ['.field:has(#speech_language)', 'Lingua delle registrazioni audio', 'I file audio vengono trascritti su questo computer, senza Internet, e la trascrizione passa dal filtro di privacy come ogni altro documento. «Automatica» riconosce la lingua dai primi secondi di parlato; se le tue registrazioni sono sempre in una lingua, sceglila.'],
    ['.check-row:has(#anonymize_filenames)', 'Anonimizza i nomi dei file', 'Anche i nomi di file e cartelle in uscita vengono anonimizzati (es. CV_[PERSONA_1].pdf).'],
    ['.check-row:has(#check_updates)', 'Controllo aggiornamenti', 'Solo quando il sistema segnala una connessione a Internet, Germano controlla in silenzio se esiste una nuova versione.'],
    ['.check-row:has(#auto_update)', 'Aggiornamento automatico', 'Scarica e prepara gli aggiornamenti in background, a bassa priorità, e li applica al successivo avvio di Germano in pochi secondi.'],
    ['.option:has(#enable_system2)', 'Sistema 2', 'Solo per i casi in cui i modelli sono incerti: un modello linguistico locale (Qwen3.5 con llama.cpp, nessun dato esce dal computer) legge il contesto e decide. Rilascia un dato solo se è sicuro che non sia personale; spento, tutti i casi dubbi restano oscurati.'],
    ['#btnUpdateCheck', 'Controlla ora', 'Controlla subito se è disponibile una nuova versione (anche se il sistema non segnala la rete).'],
    ['#btnUpdateInstall', 'Riavvia per aggiornare', 'Chiude Germano, applica la nuova versione già preparata e lo riapre: pochi secondi. Cartelle, archivio e impostazioni non vengono toccati.'],
    ['#sysUsagePill', 'Risorse del computer', 'Uso del processore e della memoria; a seguire la precisione del modello principale.'],
    ['#clearLogsBtn', 'Pulisci registro', 'Svuota il registro attività visualizzato.'],
    ['#logTerminal', 'Registro attività', 'Messaggi del motore in tempo reale: elaborazioni, avvisi ed errori.'],
    ['.folder-row [data-open-folder]', 'Apri', 'Apre la cartella nel file manager.'],
    ['#btnRedetectAi', 'Rileva di nuovo', 'Il rilevamento è automatico (ogni 12 secondi): questo pulsante cerca subito di nuovo le AI, le CLI e i modelli installati.'],
    // --- modalità operativa
    ['#cardStandalone', 'Standalone', 'Disattiva Server e Client: Germano lavora solo su questo computer, senza alcuna attività di rete.'],
    ['#cardServer', 'Server', 'Con l\'installer la regola del firewall (reti private e di dominio) è già pronta: gli altri computer raggiungono il server e il suo Remote Control.'],
    ['#cardClient', 'Client', 'Affida il calcolo a un Germano Server della rete. Se il server ha la gestione utenti attiva, inserisci utente e password che ti ha dato l\'amministratore.'],
    ['.field:has(#remoteServer)', 'Indirizzo del server', 'Lascia vuoto per la ricerca automatica in rete, oppure scrivi ad esempio http://192.168.1.10:8181.'],
    ['.field:has(#remoteUser)', 'Utente del server', 'Solo se il Germano Server ha la gestione utenti attiva: Germano accede con utente e password e conserva solo la sessione (mai la password).'],
    ['#btnFindServers', 'Cerca server in rete', 'Invia un breve messaggio di rilevamento (UDP 8182) sulla rete locale ed elenca i Germano Server che rispondono.'],
    ['.check-row:has(#clientFallback)', 'Ripiego sul motore locale', 'Se nessun server risponde, i modelli vengono caricati su questo computer (serve più memoria). Disattivato: i documenti restano in coda finché il server non risponde.'],
    ['.server-row', 'Usa questo server', 'Imposta questo Germano Server come destinazione della modalità Client.'],
    ['.check-row:has(#authEnabled)', 'Gestione utenti', 'Attiva: dalla rete servono utente e password (Remote Control e Germano Client). Disattiva: accesso libero a chiunque sia nella rete locale. Dal server stesso non servono mai.'],
    ['#authAddBtn', 'Aggiungi utente', 'Crea un utente (o cambia la password di uno esistente). La password è salvata solo come impronta PBKDF2-SHA256.'],
    ['[data-auth-pass]', 'Nuova password', 'Imposta una nuova password: le sessioni aperte di questo utente vengono chiuse.'],
    ['[data-auth-del]', 'Elimina utente', 'Elimina l\'utente e chiude le sue sessioni. Senza utenti l\'accesso dalla rete torna libero.'],
    ['.toggle-row .switch', 'Suggerimenti', 'Attiva o disattiva queste spiegazioni al passaggio del mouse.'],
    ['#btnSaveSettings', 'Applica', 'Applica subito la modalità scelta: l\'ascolto sulla rete si accende o si spegne senza riavviare Germano.'],
    ['#btnCancelSettings', 'Annulla modifiche', 'Rimette i valori attualmente in vigore.'],
    ['#btnCloseSettings', 'Chiudi', 'Conferma la modalità predefinita (Standalone) e chiude il benvenuto.'],
];

const TIPS_EN = {
    '.brand': ['Germano AI', 'Back to the start page.'],
    '#tabHarness': ['🧠 AI Harness', 'Conversation with the AI you pick at the bottom right (CLIs, local models or API services): Germano masks personal data before sending and puts it back in the answer. The Glass Window shows everything in real time.'],
    '#tabSanitize': ['📂 Manual Sanitization & Vault', 'Work folders with drag & drop, processed documents, text to anonymize or restore and the mapping archive (Vault).'],
    '#tabSettings': ['⚙️ Settings', 'Operating mode and network, profile and models, AI and keys, Proxy and APIs, system and log, updates.'],
    '#tabGuide': ['📖 Guide', 'Complete user manual and technical documentation, available offline.'],
    '#updatePill': ['Update ready', 'The new version was downloaded and prepared in the background: restart Germano whenever you want (a few seconds), otherwise it is applied by itself at the next start.'],
    '#profilePill': ['Protection profile', (el, n) => n || 'PA: all models and categories with maximum sensitivity. PD: custom configuration.'],
    '#engineStatusPill': ['Engine status', () => {
        let t = 'The engine runs anonymization models. Green = active, yellow = starting, gray = paused, red = error.';
        const eng = (lastStatus && lastStatus.running && lastStatus.engine) || null;
        if (eng && eng.mode === 'remote') t += ` Computing delegated to Germano Server «${eng.server_name || eng.server}» (${eng.server}).`;
        else if (eng && eng.device) t += ` Running on ${String(eng.device).toUpperCase()}${eng.threads ? ` (${eng.threads} threads on ${eng.cpus || '?'} processors)` : ''}${eng.precision ? `, precision ${String(eng.precision).toUpperCase()}` : ''}${eng.vm ? `, virtual machine ${eng.vm}` : ''}.`;
        return t;
    }],
    '#modeChip': ['Operating mode', (el) => `This computer is in «${(el.textContent || '').trim()}» mode. Click to choose Standalone, Server, Client, or Server + Client.`],
    '#mainToggleBtn': ['Start / stop engine', 'Starts the engine to protect Harness and Proxy requests and process documents. While stopped, no data leaves in the clear: requests are blocked (the Harness starts it by itself on the first send).'],
    '#retryEngineBtn': ['Retry', 'Restarts the engine after the indicated error.'],
    '#killOrphansBtn': ['Close leftover processes', 'Closes leftover engine processes from previous sessions and frees RAM.'],
    '.fm-box[data-fm-box="input"]': ['📥 input — documents to process', 'Drag files or whole folders here (or copy them with the file manager): the engine anonymizes them one at a time. Click the box to open the folder.'],
    '.fm-box[data-fm-box="output"]': ['📤 output — anonymized documents', 'The results, with the same subfolder structure as the originals. Click the box to open the folder.'],
    '.fm-box[data-fm-box="processed"]': ['🗂️ processed — originals', 'The originals, moved here after processing: they contain personal data in clear text. Click the box to open the folder.'],
    '.fm-box[data-fm-box="failed"]': ['⚠️ failed — not processed', 'Documents that could not be processed, with the reason; the ↻ button queues them again. Click the box to open the folder.'],
    '.fm-path': ['Folder path', (el, n) => `${n || ''}${n ? '\n' : ''}Full path of the folder on disk. Click to open it.`],
    '.fm-vault': ['🔐 Vault & reports — extracted folder', 'Mapping archive between tags ↔ real data, audit reports and logs. Contains data in the clear: keep it on a protected disk (e.g. BitLocker). Click to open the folder.'],
    '.ls:has(#lsDone)': ['Batch documents', 'Documents processed out of total in current batch.'],
    '.ls:has(#lsPii)': ['Masked personal data', 'Total personal data entries replaced with tags in ready documents.'],
    '.ls:has(#lsThroughput)': ['Throughput', 'Documents processed per minute in current batch.'],
    '.ls:has(#lsCpu)': ['CPU Usage', 'Current processor usage of this computer.'],
    '.ls:has(#lsRam)': ['RAM Usage', 'Current memory usage of this computer.'],
    '#btnPickFiles': ['Select files', 'Choose one or more documents to copy into the input folder.'],
    '#btnPickFolder': ['Select folder', 'Add an entire folder: subdirectory hierarchy is preserved in output.'],
    '.fm-retry': ['Queue again', 'Moves the document back to the input folder to process it again.'],
    '#currentJob': ['Active job', 'Engine status, document being processed, current stage and batch progress.'],
    '#btnStartFromCta': ['Start processing', 'Starts the engine to process pending documents.'],
    '.restore-row .switch': ['Automatic de-anonymization', 'Tags are numbered and mappings saved locally: when an AI response contains them, real data is restored. If disabled: irreversible anonymization.'],
    '.tab[data-folder="output"]': ['Ready', 'Anonymized (or restored) documents available in output folder.'],
    '.tab[data-folder="input"]': ['Pending', 'Documents in input folder, queued or currently processing.'],
    '.tab[data-folder="failed"]': ['Failed', 'Unprocessed documents with reason and retry button.'],
    '.tab[data-folder="processed"]': ['Originals', 'Archived original documents after processing.'],
    '#fileFilter': ['Filter', 'Filter documents by name, path or failure reason.'],
    '#btnRetryAll': ['Retry all', 'Moves all failed documents back to input folder.'],
    '#btnOpenCurrentFolder': ['Open folder', 'Opens the file manager for the currently selected tab.'],
    '#btnExportCsv': ['Export list', 'Downloads document list as CSV (Excel compatible).'],
    '[data-action="open"]': ['Open', 'Opens the document with the default application.'],
    '[data-action="reveal"]': ['Show in folder', 'Opens the file manager with the document highlighted.'],
    '[data-action="retry"]': ['Retry', 'Moves document back to input folder for re-processing.'],
    '.row-actions a[download]': ['Download copy', 'Downloads a copy of the document.'],
    '#manualInputText': ['Text', 'Paste text to anonymize, or AI response with tags like [PERSONA_1] to restore.'],
    '#anonymizeTextBtn': ['Anonymize text', 'Replaces personal data with numbered tags, ready for AI services.'],
    '#manualOutputText': ['Result', 'Anonymized text or text restored with the original data.'],
    '#copyTextBtn': ['Copy result', 'Copies the result to the clipboard.'],
    '#btnShowVault': ['Show archive', 'Shows the mappings between tags and original data (data in clear), with search.'],
    '#btnClearVault': ['Clear archive', 'Deletes all mappings: documents already anonymized can no longer be restored.'],
    '.settings-link[data-pane="general"]': ['Mode & network', 'Standalone, Server, Client or Server + Client; network access and users; tooltips.'],
    '.settings-link[data-pane="protection"]': ['Protection & models', 'PA/PD profile, sensitivity, active analysis models and data categories to mask.'],
    '.settings-link[data-pane="ai"]': ['AI, keys & Harness', 'Detected AIs, API keys of the services and Harness preferences (review before sending, preview, history).'],
    '.settings-link[data-pane="proxy"]': ['Proxy & APIs', 'Proxy addresses for Claude Code, Codex, Cursor and other tools, destination services and REST API examples.'],
    '.settings-link[data-pane="system"]': ['System & log', 'Engine execution, work folders and activity log.'],
    '.settings-link[data-pane="updates"]': ['Updates', 'Silent updates like Google Chrome: status, last check and restart to apply.'],
    '#proxyStatus': ['Proxy status', 'The Proxy protects requests only with the engine running; otherwise it blocks them and no data leaves in clear.'],
    '.endpoint:has(#openaiBase)': ['OpenAI-format address', 'Base URL for OpenAI-compatible tools (Chat Completions and Responses).'],
    '.endpoint:has(#anthropicBase)': ['Anthropic-format address', 'Base URL for Claude Code and the Anthropic SDKs (ANTHROPIC_BASE_URL variable).'],
    '#target_api_url': ['OpenAI or compatible service', 'Address to which the Proxy forwards OpenAI-format requests after anonymizing them.'],
    '#target_anthropic_url': ['Anthropic service (Claude)', 'Address to which the Proxy forwards Anthropic-format requests after anonymizing them.'],
    '#btnPresetPA': ['All on (PA profile)', 'Turns on all models and all categories with maximum sensitivity.'],
    '#btnPresetEssential': ['Essential data only', 'Masks only names, addresses, tax codes and VAT numbers, emails and phone numbers.'],
    '#btnPresetNone': ['No categories', 'Turns off all categories: no data is masked.'],
    '.field-range:has(#ai_threshold)': ['Model sensitivity', '0% threshold = every possible personal data item is masked. Raising it reduces false positives, but some uncertain data may stay in clear.'],
    '#btnModelsAllOn': ['Enable all models', 'Uses all local models and the deterministic rules.'],
    '#btnModelsAllOff': ['Disable all models', 'No analysis model: little or nothing would be masked.'],
    '#netSummary': ['Mode & network', 'Current state: network listening, connection to the Germano Server and network access (open or with user and password).'],
    '.check-row:has(#check_updates)': ['Update check', 'Only when the system reports an Internet connection, Germano silently checks whether a new version exists.'],
    '.check-row:has(#auto_update)': ['Automatic update', 'Downloads and prepares updates in the background, at low priority, and applies them at the next start of Germano in a few seconds.'],
    '.option:has(#enable_system2)': ['System 2', 'Only for the cases where the models are uncertain: a local language model (Qwen3.5 with llama.cpp, no data leaves the computer) reads the context and decides. It releases data only when it is sure it is not personal; when off, all doubtful cases stay masked.'],
    '.field:has(#speech_language)': ['Language of audio recordings', 'Audio files are transcribed on this computer, without Internet, and the transcript goes through the privacy filter like any other document. «Automatic» recognizes the language from the first seconds of speech; if your recordings are always in one language, choose it.'],
    '#btnUpdateCheck': ['Check now', 'Checks right away whether a new version is available (even if the system reports no network).'],
    '#btnUpdateInstall': ['Restart to update', 'Closes Germano, applies the already prepared version and reopens it: a few seconds. Folders, archive and settings are not touched.'],
    '#sysUsagePill': ['Computer resources', 'Processor and memory usage; then the precision of the main model.'],
    '#clearLogsBtn': ['Clear log', 'Clears the activity log shown.'],
    '#logTerminal': ['Activity log', 'Engine messages in real time: processing, warnings and errors.'],
    '#btnRedetectAi': ['Detect again', 'Detection is automatic (every 12 seconds): this button scans again right away for the installed AIs, CLIs and models.'],
    '#cardStandalone': ['Standalone', 'Disables Server and Client: Germano runs strictly locally with zero network activity.'],
    '#cardServer': ['Server', 'With the installer the firewall rule (private and domain networks) is already in place: the other computers reach the server and its Remote Control.'],
    '#cardClient': ['Client', 'Delegates compute to a remote Germano Server while keeping Vault and files locally.'],
    '.field:has(#remoteServer)': ['Server address', 'Leave blank for automatic LAN discovery, or enter IP (e.g. http://192.168.1.10:8181).'],
    '.field:has(#remoteUser)': ['Server user', 'Only if the Germano Server has user management enabled: Germano signs in and keeps only the session (never the password).'],
    '#btnFindServers': ['Scan network for servers', 'Sends UDP discovery beacon (port 8182) and lists available Germano Servers.'],
    '.check-row:has(#clientFallback)': ['Fallback to local engine', 'If no remote server responds, loads models locally.'],
    '.server-row': ['Use this server', 'Sets this Germano Server as the remote compute target.'],
    '.check-row:has(#authEnabled)': ['User management', 'On: network access requires user name and password (Remote Control and Germano Client). Off: open access for anyone on the local network. Never needed on the server itself.'],
    '#authAddBtn': ['Add user', 'Creates a user (or changes the password of an existing one). The password is stored only as a PBKDF2-SHA256 hash.'],
    '[data-auth-pass]': ['New password', 'Sets a new password: the open sessions of this user are closed.'],
    '[data-auth-del]': ['Delete user', 'Deletes the user and closes their sessions. Without users, network access is open again.'],
    '.toggle-row .switch': ['Tooltips', 'Toggle hover tooltips across the entire interface.'],
    '#btnSaveSettings': ['Apply', 'Immediately applies the chosen mode without restarting Germano.'],
    '#btnCancelSettings': ['Discard changes', 'Puts back the values currently in force.'],
    '#btnCloseSettings': ['Close', 'Confirms the default mode (Standalone) and closes the welcome.'],
};

const Tips = (() => {
    let enabled = true;
    let timer = null;
    let current = null;
    let keyboard = false;
    const SELECTOR = ['[data-tip]', '[title]', '[data-native-title]'].concat(TIPS.map(t => t[0])).join(',');

    function lookup(el) {
        const native = el.getAttribute('title') || el.dataset.nativeTitle || '';
        if (el.hasAttribute('title')) {   // il title diventa suggerimento: niente doppia finestrella del browser
            el.dataset.nativeTitle = native;
            if (!el.getAttribute('aria-label') && !(el.textContent || '').trim()) el.setAttribute('aria-label', native);
            el.removeAttribute('title');
        }
        if (el.dataset.tip) return { title: el.dataset.tipTitle || '', text: el.dataset.tip };
        const isEn = (typeof currentLang !== 'undefined' && currentLang === 'en');
        for (const [sel, t, d] of TIPS) {
            let match = false;
            try { match = el.matches(sel); } catch (e) { match = false; }
            if (!match) continue;
            let titleVal = t;
            let textVal = d;
            if (isEn && typeof TIPS_EN !== 'undefined' && TIPS_EN[sel]) {
                titleVal = TIPS_EN[sel][0];
                textVal = TIPS_EN[sel][1];
            }
            const title = typeof titleVal === 'function' ? titleVal(el, native) : titleVal;
            const text = typeof textVal === 'function' ? textVal(el, native) : textVal;
            if (title || text) return { title: title || '', text: text || '' };
        }
        return native ? { title: '', text: native } : null;
    }

    function candidate(node) {
        if (!(node instanceof Element)) return null;
        try { return node.closest(SELECTOR); } catch (e) { return null; }
    }

    function place(target, box) {
        const r = target.getBoundingClientRect();
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const w = box.offsetWidth;
        const h = box.offsetHeight;
        let top = r.top - h - 10;
        let below = false;
        if (top < 8) {
            top = r.bottom + 10;
            below = true;
            if (top + h > vh - 8) top = Math.max(8, vh - h - 8);
        }
        const left = Math.max(8, Math.min(r.left + r.width / 2 - w / 2, vw - w - 8));
        box.style.left = `${Math.round(left)}px`;
        box.style.top = `${Math.round(top)}px`;
        box.style.setProperty('--tip-arrow-x', `${Math.round(Math.max(12, Math.min(w - 12, r.left + r.width / 2 - left)))}px`);
        box.classList.toggle('is-below', below);
        box.classList.toggle('is-above', !below);
    }

    function show(target) {
        timer = null;
        if (!enabled || !document.body.contains(target)) return;
        const tip = lookup(target);
        const box = $('gTip');
        if (!tip || !box) return;
        $('gTipTitle').textContent = tip.title;
        $('gTipText').textContent = tip.text;
        box.classList.remove('is-visible');
        box.hidden = false;
        place(target, box);
        requestAnimationFrame(() => box.classList.add('is-visible'));
        target.setAttribute('aria-describedby', 'gTip');
        current = target;
    }

    function hide() {
        clearTimeout(timer);
        timer = null;
        const box = $('gTip');
        if (box) {
            box.classList.remove('is-visible');
            box.hidden = true;
        }
        if (current) {
            current.removeAttribute('aria-describedby');
            current = null;
        }
    }

    function schedule(el) {
        clearTimeout(timer);
        if (current && current !== el) hide();
        timer = setTimeout(() => show(el), 350);
    }

    function onOver(e) {
        const el = candidate(e.target);
        if (!el || el === current) return;
        if (!enabled) {
            if (el.hasAttribute('title')) lookup(el);   // suggerimenti spenti: niente finestrelle, neppure native
            return;
        }
        schedule(el);
    }

    function onOut(e) {
        const el = candidate(e.target);
        if (!el) return;
        if (e.relatedTarget instanceof Node && el.contains(e.relatedTarget)) return;
        if (el === current || timer) hide();
    }

    function init() {
        document.addEventListener('mouseover', onOver, true);
        document.addEventListener('mouseout', onOut, true);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') keyboard = true;
            if (e.key === 'Escape') hide();
        }, true);
        document.addEventListener('mousedown', () => { keyboard = false; hide(); }, true);
        document.addEventListener('focusin', (e) => {   // tastiera: il suggerimento compare anche con il Tab
            if (!enabled || !keyboard) return;
            const el = candidate(e.target);
            if (el) schedule(el);
        });
        document.addEventListener('focusout', hide);
        ['scroll', 'resize', 'blur'].forEach(ev => window.addEventListener(ev, hide, true));
        document.body.dataset.tipsReady = '1';
        document.body.dataset.tipsCount = String(document.querySelectorAll(SELECTOR).length);
    }

    return {
        init,
        hide,
        setEnabled(v) {
            enabled = Boolean(v);
            if (!enabled) hide();
            if (document.body) document.body.dataset.tips = enabled ? 'on' : 'off';
        },
        isEnabled: () => enabled,
    };
})();

// ------------------------------------------------------------------ MODALITÀ OPERATIVA E IMPOSTAZIONI
const MODE_TEXT = { standalone: 'Standalone', server: 'Server', client: 'Client', 'server+client': 'Server + Client' };
const FORCED_TEXT = { GERMANO_MODE: 'la variabile GERMANO_MODE', GERMANO_HOST: 'la variabile GERMANO_HOST' };

function setSettingsMsg(text, isError = false) {
    const el = $('settingsMsg');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('error', Boolean(isError));
}

function modeFromChecks() {
    const s = $('optServer').checked;
    const c = $('optClient').checked;
    if (s && c) return 'server+client';
    if (s) return 'server';
    if (c) return 'client';
    return 'standalone';
}

function setModeChecks(mode) {
    const m = String(mode || 'standalone');
    $('optServer').checked = m.includes('server');
    $('optClient').checked = m.includes('client');
    $('optStandalone').checked = !m.includes('server') && !m.includes('client');
    syncModeDetails();
}

function onModeCheck(which) {
    const st = $('optStandalone');
    const sv = $('optServer');
    const cl = $('optClient');
    if (which === 'standalone') {
        if (st.checked) {
            sv.checked = false;
            cl.checked = false;
        } else if (!sv.checked && !cl.checked) {
            st.checked = true;   // serve sempre una scelta: Standalone resta finché non si sceglie altro
        }
    } else {
        st.checked = !sv.checked && !cl.checked;
    }
    syncModeDetails();
}

function syncModeDetails() {
    $('clientDetail').hidden = !$('optClient').checked;
    $('serverDetail').hidden = !$('optServer').checked;
    renderServerInfo();
}

function renderServerInfo() {
    const box = $('serverInfo');
    if (!box || !$('optServer').checked) return;
    const s = (modeState && modeState.server) || {};
    if (!s.enabled || !s.listening) {
        box.innerHTML = `<span class="muted">${escapeHtml(updText(
            'Dopo «Applica» Germano si mette in ascolto sulla rete e qui compaiono gli indirizzi del Remote Control, da ' +
            'aprire nel browser dei computer, dei tablet e degli smartphone della rete. Con l\'installer la regola del firewall ' +
            'di Windows (reti private e di dominio) è già pronta; eseguendo Germano dai sorgenti Windows può chiedere di ' +
            'consentire Python: rispondi «Consenti».',
            'After «Apply», Germano listens on the network and the Remote Control addresses appear here, to open in the ' +
            'browser of the network computers, tablets and smartphones. With the installer the Windows Firewall rule (private ' +
            'and domain networks) is already in place; when running Germano from source Windows may ask to allow Python: ' +
            'answer «Allow».'))}</span>`;
        renderAuthAdmin(null);
        return;
    }
    const urls = (s.ips || []).map(ip => `http://${ip}:${s.port}/remote`);
    const list = urls.length
        ? urls.map(u => `<div class="copy-line"><code>${escapeHtml(u)}</code>${copyButton(u, updText('Copia indirizzo', 'Copy address'))}</div>`).join('')
        : `<span class="muted">${escapeHtml(updText('nessun indirizzo IPv4 trovato', 'no IPv4 address found'))}</span>`;
    // Reti «Pubbliche», regola del firewall, criteri di gruppo: perché i client potrebbero non raggiungere il server
    const warns = (s.network_warnings || []).map(w => `<div class="net-warning">⚠️ ${escapeHtml(updText(w.it, w.en))}${
        w.command ? `<div class="copy-line"><code>${escapeHtml(w.command)}</code>${copyButton(w.command, updText('Copia comando', 'Copy command'))}</div>` : ''}</div>`).join('');
    if (s.network_warnings === null && !renderServerInfo.retry) {   // primo controllo ancora in corso (circa 2 s)
        renderServerInfo.retry = setTimeout(async () => {
            try {
                const { ok, data } = await fetchJson('/api/mode', { cache: 'no-store' });
                if (ok) modeState = data;
            } catch (e) { /* si resta con l'ultimo stato */ }
            renderServerInfo.retry = null;
            if (modeState && modeState.server && modeState.server.network_warnings !== null) renderServerInfo();
        }, 3500);
    }
    box.innerHTML = `
        <div><strong>${escapeHtml(updText('In ascolto sulla rete · Remote Control (Harness AI e Glass Window), da qualsiasi browser senza installare nulla:',
                                          'Listening on the network · Remote Control (AI Harness and Glass Window), from any browser without installing anything:'))}</strong></div>
        ${list}
        ${warns}
        <div class="muted">${escapeHtml(updText(
            `Rilevamento automatico: ${s.discovery ? `attivo (UDP ${s.discovery_port})` : 'non attivo'}. Le CLI dei computer della ` +
            `rete usano http://<IP>:${s.port}/v1 (e http://<IP>:${s.port}/p/<servizio>/v1 per DeepSeek, Kimi, Muse, Mistral, Grok…).`,
            `Auto-discovery: ${s.discovery ? `on (UDP ${s.discovery_port})` : 'off'}. The CLIs of the network computers use ` +
            `http://<IP>:${s.port}/v1 (and http://<IP>:${s.port}/p/<service>/v1 for DeepSeek, Kimi, Muse, Mistral, Grok…).`))}</div>`;
    loadAuthAdmin();
}

// ------------------------------------------------------------------ GESTIONE UTENTI (accesso dalla rete)
let authState = null;

async function loadAuthAdmin() {
    try {
        const { ok, data } = await fetchJson('/api/auth/users', { cache: 'no-store' });
        if (ok) authState = data;
    } catch (e) { /* Germano non risponde */ }
    renderAuthAdmin(authState);
}

function renderAuthAdmin(st) {
    const box = $('authAdmin');
    if (!box) return;
    const s = (modeState && modeState.server) || {};
    if (!st || !s.enabled || !s.listening) {
        box.innerHTML = '';
        return;
    }
    const locked = Boolean(st.locked);
    const dis = locked ? ' disabled' : '';
    const users = st.users || [];
    const rows = users.map(u => `<div class="auth-user"><span>👤 <strong>${escapeHtml(u.username)}</strong>
            <span class="muted">${escapeHtml(updText('dal', 'since'))} ${escapeHtml(u.created || '')}</span></span>
        <span class="auth-user-actions">
            <button type="button" class="btn btn-secondary btn-sm" data-auth-pass="${escapeHtml(u.username)}"${dis}>${escapeHtml(updText('Nuova password', 'New password'))}</button>
            <button type="button" class="btn btn-secondary btn-sm" data-auth-del="${escapeHtml(u.username)}"${dis}>${escapeHtml(updText('Elimina', 'Delete'))}</button>
        </span></div>`).join('');
    box.innerHTML = `
        <h4 class="mode-detail-title">${escapeHtml(updText('Gestione utenti', 'User management'))}</h4>
        <label class="check-row"><input type="checkbox" id="authEnabled"${st.enabled ? ' checked' : ''}${locked || !users.length ? ' disabled' : ''}>
            <span>${escapeHtml(updText(
                'Richiedi utente e password per l\'accesso dalla rete (Remote Control nel browser e Germano Client). Dal computer del server si accede sempre senza credenziali.',
                'Require user name and password for network access (Remote Control in the browser and Germano Client). From the server computer access never needs credentials.'))}</span></label>
        <p class="auth-state ${st.enabled ? 'is-on' : 'is-off'}">${escapeHtml(st.enabled
            ? updText(`🔐 Accesso con utente e password · ${st.sessions} sessioni aperte.`, `🔐 Sign-in with user name and password · ${st.sessions} open sessions.`)
            : updText('🔓 Accesso dalla rete LIBERO: chiunque sia collegato alla rete locale può usare Germano (motore, Proxy, Remote Control).',
                      '🔓 Network access OPEN: anyone on the local network can use Germano (engine, Proxy, Remote Control).'))}</p>
        <div class="auth-users">${rows || `<span class="muted">${escapeHtml(updText('Nessun utente: aggiungine uno per poter attivare l\'accesso con password.',
                                                                                  'No users: add one to enable password sign-in.'))}</span>`}</div>
        <div class="auth-add">
            <input type="text" id="authNewUser" class="input" placeholder="${escapeHtml(updText('nuovo utente', 'new user'))}" autocomplete="off" spellcheck="false"${dis}>
            <input type="password" id="authNewPass" class="input" placeholder="${escapeHtml(updText(`password (almeno ${st.min_password} caratteri)`, `password (at least ${st.min_password} characters)`))}" autocomplete="new-password"${dis}>
            <button type="button" class="btn btn-secondary btn-sm" id="authAddBtn"${dis}>${escapeHtml(updText('Aggiungi utente', 'Add user'))}</button>
        </div>
        <p class="muted">${escapeHtml(updText(
            'Le password sono salvate solo come impronta (PBKDF2-SHA256). In rete locale il collegamento non è cifrato (HTTP): usa Germano su reti fidate.',
            'Passwords are stored only as a hash (PBKDF2-SHA256). On the local network the connection is not encrypted (HTTP): use Germano on trusted networks.'))}</p>
        ${locked ? `<p class="muted">🔒 ${escapeHtml(updText('Bloccato dall\'amministratore (lock_settings).', 'Locked by the administrator (lock_settings).'))}</p>` : ''}`;
}

async function authCall(url, body, okMsg) {
    try {
        const { ok, data } = await postJson(url, body);
        if (!ok) {
            showToast(data.message || data.error || updText('Operazione non riuscita.', 'Operation failed.'), 'error', 7000);
            return false;
        }
        authState = data;
        renderAuthAdmin(authState);
        renderNetSummary();
        if (okMsg) showToast(okMsg, 'success');
        return true;
    } catch (e) {
        showToast(updText('Germano non risponde.', 'Germano is not responding.'), 'error');
        return false;
    }
}

async function onAuthAdminClick(e) {
    if (e.target.id === 'authAddBtn') {
        const user = ($('authNewUser').value || '').trim();
        const pass = $('authNewPass').value || '';
        if (!user || !pass) {
            showToast(updText('Scrivi nome utente e password.', 'Type user name and password.'), 'warn');
            return;
        }
        if (await authCall('/api/auth/users', { username: user, password: pass },
                           updText(`Utente «${user}» salvato.`, `User «${user}» saved.`))) {
            $('authNewUser').value = '';
            $('authNewPass').value = '';
        }
        return;
    }
    const del = e.target.closest('[data-auth-del]');
    if (del) {
        const user = del.dataset.authDel;
        if (!confirm(updText(`Eliminare l'utente «${user}»? Le sue sessioni aperte vengono chiuse.`,
                             `Delete the user «${user}»? Their open sessions are closed.`))) return;
        await authCall('/api/auth/users/delete', { username: user }, updText(`Utente «${user}» eliminato.`, `User «${user}» deleted.`));
        return;
    }
    const pw = e.target.closest('[data-auth-pass]');
    if (pw) {
        const user = pw.dataset.authPass;
        const pass = prompt(updText(`Nuova password per «${user}» (le sue sessioni aperte vengono chiuse):`,
                                    `New password for «${user}» (their open sessions are closed):`));
        if (pass) await authCall('/api/auth/users', { username: user, password: pass }, updText('Password cambiata.', 'Password changed.'));
    }
}

async function onAuthAdminChange(e) {
    if (e.target.id !== 'authEnabled') return;
    const enabled = e.target.checked;
    const done = await authCall('/api/auth/enable', { enabled }, enabled
        ? updText('Accesso con utente e password attivato.', 'Sign-in with user name and password enabled.')
        : updText('Accesso dalla rete libero (senza credenziali).', 'Network access open (no credentials).'));
    if (!done) e.target.checked = !enabled;
}

// Sezione «Modalita'»: di norma nelle Impostazioni; alla prima apertura si sposta nella finestra di benvenuto.
async function refreshModeSection() {
    $('enable_tooltips').checked = tooltipsEnabled;
    $('serverList').innerHTML = '';
    let remoteViewer = '';   // Dashboard aperta da un altro computer: la modalità si sceglie solo sul server
    try {
        const { ok, status, data } = await fetchJson('/api/mode', { cache: 'no-store' });
        if (ok) modeState = data;
        else if (status === 403) remoteViewer = data.error || updText('Le Impostazioni si cambiano solo dal computer su cui è installato Germano.', 'Settings can be changed only from the computer where Germano is installed.');
    } catch (e) { /* si usa l'ultimo stato noto */ }
    const st = modeState || {};
    const cl = st.client || {};
    setModeChecks(st.saved || 'standalone');
    $('remoteServer').value = cl.remote_server || '';
    $('remoteUser').value = cl.remote_user || '';
    $('remotePassword').value = '';
    $('remotePassword').placeholder = cl.remote_user
        ? updText('•••••••• accesso già fatto (lascia vuoto)', '•••••••• already signed in (leave empty)')
        : '';
    $('clientFallback').checked = cl.fallback_local !== false;
    $('shareAiTools').checked = Boolean((st.server || {}).share_ai_tools);
    const locked = Boolean(st.locked) || Boolean(remoteViewer);
    ['optStandalone', 'optServer', 'optClient', 'remoteServer', 'remoteUser', 'remotePassword', 'clientFallback', 'btnFindServers', 'shareAiTools']
        .forEach(id => { if ($(id)) $(id).disabled = locked; });
    $('enable_tooltips').disabled = Boolean(remoteViewer);
    $('btnSaveSettings').disabled = Boolean(remoteViewer);
    document.querySelectorAll('.mode-card').forEach(c => c.classList.toggle('is-disabled', locked));
    setSettingsMsg('');
    if (remoteViewer) {
        setSettingsMsg(remoteViewer, true);
    } else if (st.locked) {
        setSettingsMsg(updText('Modalità bloccata dall\'amministratore (lock_settings): si possono cambiare solo le preferenze dell\'interfaccia.',
                               'Mode locked by the administrator (lock_settings): only the interface preferences can be changed.'));
    } else if (st.forced_by) {
        setSettingsMsg(updText(`Per questo avvio la modalità è «${MODE_TEXT[st.effective] || st.effective}», impostata da ` +
            `${FORCED_TEXT[st.forced_by] || st.forced_by}: la scelta salvata qui vale dai prossimi avvii senza quella variabile.`,
            `For this start the mode is «${MODE_TEXT[st.effective] || st.effective}», set by ${st.forced_by}: the choice saved here applies from the next starts without that variable.`));
    }
}

async function openSettings(opts = {}) {
    settingsWelcome = Boolean(opts.welcome);
    settingsDone = false;
    if (!settingsWelcome) {           // dalla 0.70 le Impostazioni sono una scheda
        applyTab('settings');
        applyPane('general');
        return;
    }
    $('modalBodyHost').appendChild($('modeSection'));
    setText('btnSaveSettings', 'Conferma e inizia');
    $('btnCancelSettings').hidden = true;
    Tips.hide();
    $('settingsScrim').hidden = false;
    $('settingsModal').hidden = false;
    await refreshModeSection();
    setTimeout(() => $('btnSaveSettings').focus(), 30);
}

function hideSettings() {
    if (!$('settingsModal').hidden) {
        $('modeSectionHome').appendChild($('modeSection'));
        $('settingsModal').hidden = true;
        $('settingsScrim').hidden = true;
    }
    settingsWelcome = false;
    settingsDone = false;
    setText('btnSaveSettings', 'Applica');
    $('btnCancelSettings').hidden = false;
}

function dismissSettings() {
    // Chiudere il benvenuto senza scegliere conferma la modalità predefinita (Standalone): non viene richiesto di nuovo.
    if (settingsWelcome) saveSettings({ keepMode: true });
    else hideSettings();
}

function applyTooltipsPref(value) {
    tooltipsEnabled = Boolean(value);
    Tips.setEnabled(tooltipsEnabled);
    if (initialConfig) initialConfig.enable_tooltips = tooltipsEnabled;
}

async function saveSettings({ keepMode = false } = {}) {
    const st = modeState || {};
    const mode = keepMode ? (st.saved || 'standalone') : modeFromChecks();
    const body = { operating_mode: mode, enable_tooltips: $('enable_tooltips').checked };
    if (!keepMode && mode.includes('client')) {
        body.remote_server = ($('remoteServer').value || '').trim();
        const ru = ($('remoteUser').value || '').trim();
        const rp = $('remotePassword').value || '';
        if (ru && rp) {
            body.remote_user = ru;          // il server di Germano accede al server remoto e conserva solo la sessione
            body.remote_password = rp;
        }
        body.client_fallback_local = $('clientFallback').checked;
    }
    if (!keepMode && mode.includes('server')) body.share_ai_tools = $('shareAiTools').checked;
    const btn = $('btnSaveSettings');
    btn.disabled = true;
    const welcome = settingsWelcome;
    try {
        const { ok, status, data } = await postJson('/api/mode', body);
        if (status === 403 && data.status === 'locked') {
            applyTooltipsPref(body.enable_tooltips);   // le preferenze dell'interfaccia vengono comunque salvate
            setSettingsMsg(data.message, true);
            return;
        }
        if (!ok) {
            setSettingsMsg(data.message || data.error || updText('Impossibile salvare le impostazioni.', 'Cannot save the settings.'), true);
            return;
        }
        modeState = data;
        applyTooltipsPref(body.enable_tooltips);
        if (initialConfig) initialConfig.first_run_done = true;
        const label = MODE_TEXT[data.saved] || data.saved;
        let msg = updText('Impostazioni salvate.', 'Settings saved.');
        if (welcome) msg = updText(`Modalità ${label} confermata.`, `${label} mode confirmed.`);
        else if (data.saved !== (st.saved || 'standalone')) msg = updText(`Modalità ${label} attivata.`, `${label} mode enabled.`);
        if (data.forced_by && data.effective !== data.saved) {
            msg += updText(` Per questo avvio resta «${MODE_TEXT[data.effective] || data.effective}» (${FORCED_TEXT[data.forced_by] || data.forced_by}).`,
                           ` For this start it stays «${MODE_TEXT[data.effective] || data.effective}» (${data.forced_by}).`);
        }
        if (data.server && data.server.listening) msg += updText(' Germano è in ascolto sulla rete locale.', ' Germano is listening on the local network.');
        if (data.engine_action === 'restart') msg += updText(' Il motore si riavvia per applicarla.', ' The engine restarts to apply it.');
        if (data.engine_action === 'start') msg += updText(' Avvio del motore in corso.', ' Starting the engine.');
        (data.notes || []).forEach(n => showToast(n, 'warn', 9000));
        pollStatus();
        renderNetSummary();
        syncModeDetails();
        if (welcome && !keepMode && String(data.saved).includes('server') && data.server && data.server.listening) {
            // Benvenuto in modalità Server: la finestra resta aperta perché l'amministratore veda gli indirizzi.
            settingsDone = true;
            setText('btnSaveSettings', 'Fatto');
            renderServerInfo();
            setSettingsMsg(`✅ ${msg} ` + updText('Comunica ai client l\'indirizzo qui sopra (e, se la gestione utenti è attiva, utente e password).',
                                                   'Give the clients the address above (and, with user management on, user name and password).'));
            return;
        }
        if (welcome) {
            hideSettings();
            showToast(msg, 'success', 5000);
            return;
        }
        setSettingsMsg(`✅ ${msg}`);
        showToast(msg, 'success', 4000);
    } catch (e) {
        setSettingsMsg(updText('Germano non risponde: impossibile salvare.', 'Germano is not responding: cannot save.'), true);
    } finally {
        btn.disabled = false;
    }
}

async function findServers() {
    const list = $('serverList');
    const btn = $('btnFindServers');
    list.innerHTML = `<div class="server-empty">${escapeHtml(updText('Ricerca in corso…', 'Searching…'))}</div>`;
    btn.disabled = true;
    try {
        const { ok, data } = await fetchJson('/api/remote/servers', { cache: 'no-store' });
        const servers = (ok && data.servers) || [];
        list.innerHTML = servers.length ? servers.map(s => {
            const engine = s.engine_shared ? (s.engine_ready ? updText('🟢 motore pronto', '🟢 engine ready') : updText('🟡 motore in avvio', '🟡 engine starting'))
                                           : updText('⚪ motore non condiviso', '⚪ engine not shared');
            const dev = s.device ? ` · ${escapeHtml(String(s.device).toUpperCase())}` : '';
            return `<button type="button" class="server-row" data-server-url="${escapeHtml(s.url)}">
                <span class="server-name">${escapeHtml(s.name || s.url)}</span><code>${escapeHtml(s.url)}</code>
                <span class="server-meta">${engine}${dev} · v${escapeHtml(s.version || '?')}</span></button>`;
        }).join('') : `<div class="server-empty">${escapeHtml(updText('Nessun Germano Server trovato sulla rete locale. Sul server scegli la modalità Server nelle Impostazioni e verifica che il firewall consenta le reti private.',
                                                                       'No Germano Server found on the local network. On the server choose Server mode in Settings and check that the firewall allows private networks.'))}</div>`;
    } catch (e) {
        list.innerHTML = `<div class="server-empty">${escapeHtml(updText('Ricerca non riuscita: Germano non risponde.', 'Search failed: Germano is not responding.'))}</div>`;
    } finally {
        btn.disabled = Boolean(modeState && modeState.locked);
    }
}

function renderModeChip(data) {
    const chip = $('modeChip');
    if (!chip || !data || !data.mode) return;
    const m = data.mode;
    const eng = data.engine || {};
    const eff = m.effective || 'standalone';
    let text = m.label || MODE_TEXT[eff] || 'Standalone';
    const cls = [];
    const wantServer = eff.includes('server');
    if (m.server && m.client) cls.push('is-both');
    else if (m.server) cls.push('is-server');
    else if (m.client) cls.push('is-client');
    if (wantServer && !m.server) cls.push('is-warn');   // Server richiesto ma non in ascolto (es. porta occupata)
    if (m.client && data.running) {
        if (eng.mode === 'remote') {
            text += ` · ${eng.server_name || 'server'}`;
            if (eng.ok === false) { text += updText(' (non raggiungibile)', ' (unreachable)'); cls.push('is-warn'); }
        } else if (eng.fallback) {
            text += updText(' · motore locale', ' · local engine');
            cls.push('is-warn');
        }
    }
    chip.className = ['mode-chip', ...cls].join(' ');
    setText('modeChipText', text);
    chip.dataset.mode = eff;
}

async function renderNetSummary() {
    const box = $('netSummary');
    if (!box || currentTab !== 'settings' || currentPane !== 'general') return;
    try {
        const { ok, data } = await fetchJson('/api/mode', { cache: 'no-store' });
        if (!ok) return;
        modeState = data;
        const s = data.server || {};
        const c = data.client || {};
        const eng = data.engine || {};
        let clientValue = updText('disattivato', 'off');
        let clientSub = updText('il calcolo avviene su questo computer', 'computing happens on this computer');
        if (c.enabled) {
            if (eng.mode === 'remote' && eng.ok === false) {
                clientValue = updText(`${eng.server_name || eng.server} non raggiungibile`, `${eng.server_name || eng.server} unreachable`);
                clientSub = updText(`${eng.server} · nessun dato inviato, i documenti restano in coda`, `${eng.server} · no data sent, documents stay queued`);
            } else if (eng.mode === 'remote') {
                clientValue = updText(`collegato a ${eng.server_name || eng.server}`, `connected to ${eng.server_name || eng.server}`);
                clientSub = `${eng.server} · ${eng.latency_ms ?? '?'} ms`;
            } else if (data.engine_running && eng.fallback) {
                clientValue = updText('motore locale (nessun server)', 'local engine (no server)');
                clientSub = eng.fallback;
            } else {
                clientValue = data.engine_running ? updText('collegamento in corso…', 'connecting…') : updText('motore non avviato', 'engine not started');
                clientSub = c.remote_server || updText('ricerca automatica in rete', 'automatic network search');
            }
        }
        const items = [
            [updText('Modalità', 'Mode'), MODE_TEXT[data.effective] || data.effective,
                data.forced_by ? updText(`impostata da ${FORCED_TEXT[data.forced_by] || data.forced_by} per questo avvio`, `set by ${data.forced_by} for this start`)
                               : updText('modificabile in qualsiasi momento', 'can be changed at any time')],
            ['Server', s.enabled ? (s.listening ? updText('in ascolto sulla rete', 'listening on the network') : updText('non in ascolto', 'not listening')) : updText('disattivato', 'off'),
                s.enabled && s.listening ? (s.ips || []).map(ip => `${ip}:${s.port}`).join(', ') || updText('nessun IPv4', 'no IPv4') : updText('nessuna porta aperta verso la rete', 'no port open to the network')],
            ['Client', clientValue, clientSub],
            [updText('Accesso dalla rete', 'Network access'),
                s.enabled ? (s.auth_enabled ? updText(`utente e password (${s.users})`, `user and password (${s.users})`)
                                            : updText('libero (senza credenziali)', 'open (no credentials)')) : '—',
                s.enabled ? 'Remote Control: http://<IP>:' + s.port + '/remote' : updText('serve solo in modalità Server', 'only in Server mode')],
        ];
        box.innerHTML = items.map(([l, v, sub]) => `<div class="net-item"><div class="net-item-label">${escapeHtml(l)}</div>` +
            `<div class="net-item-value">${escapeHtml(v)}</div><div class="net-item-sub">${escapeHtml(sub)}</div></div>`).join('');
    } catch (e) { /* Germano non risponde: gestito da pollStatus */ }
}

// ------------------------------------------------------------------ INTERNAZIONALIZZAZIONE (i18n)
let currentLang = 'it';
function getLang() { return currentLang; }

function setLanguage(lang) {
    currentLang = (lang === 'en') ? 'en' : 'it';
    try { localStorage.setItem('germano_lang', currentLang); } catch (e) {}
    document.cookie = `germano_lang=${currentLang}; path=/; SameSite=Strict; max-age=31536000`;
    document.documentElement.lang = currentLang;

    const btnIt = $('btn-it');
    const btnEn = $('btn-en');
    if (btnIt && btnEn) {
        btnIt.classList.toggle('active', currentLang === 'it');
        btnIt.setAttribute('aria-pressed', currentLang === 'it');
        btnEn.classList.toggle('active', currentLang === 'en');
        btnEn.setAttribute('aria-pressed', currentLang === 'en');
    }

    // Scambia contenuti con data-en
    document.querySelectorAll('[data-en]').forEach(el => {
        if (!el.hasAttribute('data-it')) {
            el.setAttribute('data-it', el.innerHTML);
        }
        el.innerHTML = (currentLang === 'en') ? el.getAttribute('data-en') : el.getAttribute('data-it');
    });

    // Scambia attributi title
    document.querySelectorAll('[data-en-title]').forEach(el => {
        if (!el.hasAttribute('data-it-title')) {
            el.setAttribute('data-it-title', el.getAttribute('title') || el.dataset.nativeTitle || '');
        }
        const val = (currentLang === 'en') ? el.getAttribute('data-en-title') : el.getAttribute('data-it-title');
        if (el.hasAttribute('title')) el.setAttribute('title', val);
        if (el.dataset.nativeTitle) el.dataset.nativeTitle = val;
    });

    // Scambia placeholder
    document.querySelectorAll('[data-en-placeholder]').forEach(el => {
        if (!el.hasAttribute('data-it-placeholder')) {
            el.setAttribute('data-it-placeholder', el.getAttribute('placeholder') || '');
        }
        el.setAttribute('placeholder', (currentLang === 'en') ? el.getAttribute('data-en-placeholder') : el.getAttribute('data-it-placeholder'));
    });

    // Scambia aria-label
    document.querySelectorAll('[data-en-aria-label]').forEach(el => {
        if (!el.hasAttribute('data-it-aria-label')) {
            el.setAttribute('data-it-aria-label', el.getAttribute('aria-label') || '');
        }
        el.setAttribute('aria-label', (currentLang === 'en') ? el.getAttribute('data-en-aria-label') : el.getAttribute('data-it-aria-label'));
    });

    // Elementi dinamici
    if (typeof lastStatus !== 'undefined' && lastStatus) {
        try { renderEngine(lastStatus); } catch (e) {}
        try { renderJob(lastStatus); } catch (e) {}
    }
    try { updatePresetButtons(); applyDeanonState($('enable_deanonymize').checked); updateThresholdBadge($('ai_threshold').value); } catch (e) {}
    try { renderFileManager(true); renderFiles(); } catch (e) {}
    try { if (harness) harness.setLang(); } catch (e) {}
    try { renderAiSettings(); } catch (e) {}
    try { if (lastUpdate) { renderUpdate(lastUpdate); renderUpdatePanel(lastUpdate); } } catch (e) {}
    try { if (currentTab === 'guide') loadGuide(); else { const f = $('guideFrame'); if (f) f.dataset.loaded = ''; } } catch (e) {}
    try { if (currentTab === 'settings' && currentPane === 'general') renderNetSummary(); } catch (e) {}
}

function initLanguage() {
    // Ordine: ?lang nell'indirizzo (condiviso con la Guida) -> scelta salvata -> lingua del browser.
    let initialLang = null;
    try {
        const urlLang = new URLSearchParams(location.search).get('lang');
        if (urlLang === 'en' || urlLang === 'it') {
            initialLang = urlLang;
        } else {
            const saved = localStorage.getItem('germano_lang');
            if (saved === 'en' || saved === 'it') {
                initialLang = saved;
            }
        }
    } catch (e) {}
    if (!initialLang) {
        const navLang = ((navigator.languages && navigator.languages[0]) || navigator.language ||
                         navigator.userLanguage || 'it').toLowerCase();
        initialLang = navLang.startsWith('it') ? 'it' : 'en';
    }
    const btnIt = $('btn-it');
    const btnEn = $('btn-en');
    if (btnIt) btnIt.addEventListener('click', () => setLanguage('it'));
    if (btnEn) btnEn.addEventListener('click', () => setLanguage('en'));
    setLanguage(initialLang);
}

// ------------------------------------------------------------------ AVVIO PAGINA
document.addEventListener('DOMContentLoaded', async () => {
    initLanguage();
    Tips.init();
    await loadInitialSettings();
    Tips.setEnabled(tooltipsEnabled);
    mountHarness();
    // all'apertura si parte sempre dall'Harness AI (la scheda scelta resta solo durante la sessione, es. dopo un ricaricamento)
    let tab = 'harness';
    let pane = 'general';
    try { tab = sessionStorage.getItem('germano_tab') || 'harness'; pane = sessionStorage.getItem('germano_pane') || 'general'; } catch (e) { /* archivio non disponibile */ }
    currentPane = PANES.includes(pane) ? pane : 'general';
    applyTab(tab, false);
    renderAgents();
    await pollStatus();

    // Schede principali e sezioni delle Impostazioni
    document.querySelectorAll('.main-tab').forEach(b => b.addEventListener('click', () => applyTab(b.dataset.tab)));
    document.querySelectorAll('.settings-link').forEach(b => b.addEventListener('click', () => applyPane(b.dataset.pane)));
    document.addEventListener('click', (e) => {
        const g = e.target.closest('[data-goto-guide]');
        if (g) { applyTab('guide'); loadGuide(g.dataset.gotoGuide); }
    });

    // Modalità operativa (Standalone / Server / Client) e preferenze dell'interfaccia
    $('optStandalone').addEventListener('change', () => onModeCheck('standalone'));
    $('optServer').addEventListener('change', () => onModeCheck('server'));
    $('optClient').addEventListener('change', () => onModeCheck('client'));
    $('btnFindServers').addEventListener('click', findServers);
    ['input', 'change'].forEach(ev => $('modeSection').addEventListener(ev, () => {
        if (!settingsDone) return;   // modificata di nuovo dopo il salvataggio: «Fatto» torna «Conferma»
        settingsDone = false;
        setText('btnSaveSettings', settingsWelcome ? 'Conferma e inizia' : 'Applica');
    }));
    $('btnSaveSettings').addEventListener('click', () => (settingsDone ? hideSettings() : saveSettings()));
    $('btnCancelSettings').addEventListener('click', () => { refreshModeSection(); showToast(updText('Valori in vigore ripristinati.', 'Current values restored.'), 'info', 2500); });
    $('btnCloseSettings').addEventListener('click', dismissSettings);
    $('settingsScrim').addEventListener('click', dismissSettings);
    $('serverList').addEventListener('click', (e) => {
        const row = e.target.closest('[data-server-url]');
        if (!row) return;
        $('remoteServer').value = row.dataset.serverUrl;
        $('serverList').querySelectorAll('.server-row').forEach(r => r.classList.toggle('is-selected', r === row));
        $('remoteUser').focus();
        setSettingsMsg(updText(`Server selezionato: ${row.dataset.serverUrl}. Se richiede l'accesso inserisci utente e password, poi applica.`,
                               `Server selected: ${row.dataset.serverUrl}. If it requires sign-in enter user name and password, then apply.`));
    });
    $('authAdmin').addEventListener('click', onAuthAdminClick);
    $('authAdmin').addEventListener('change', onAuthAdminChange);
    $('settingsModal').addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            e.preventDefault();
            dismissSettings();
            return;
        }
        if (e.key !== 'Tab') return;   // il Tab resta dentro la finestra
        const items = Array.from($('settingsModal').querySelectorAll('button, input, select, textarea, a[href]'))
            .filter(el => !el.disabled && el.offsetParent !== null);
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    });
    $('enable_tooltips').addEventListener('change', () => applyTooltipsPref($('enable_tooltips').checked));
    // Prima apertura: la finestra fa da benvenuto e chiede la modalità operativa (predefinita Standalone)
    if (initialConfig && initialConfig.first_run_done !== true) openSettings({ welcome: true });

    // AI, chiavi e Harness
    $('btnRedetectAi').addEventListener('click', async () => { if (harness) { await harness.refreshTargets(true); renderAiSettings(); renderAssistOverview(); } });
    $('aiDetectedList').addEventListener('click', e => {
        const b = e.target.closest('[data-assist-open]');
        if (b && harness) harness.openAssist(b.dataset.assistOpen);
    });
    $('keyList').addEventListener('click', onKeyListClick);
    document.querySelectorAll('#harnessPrefs [data-hpref]').forEach(box => box.addEventListener('change', () => {
        if (harness) harness.setPref(box.dataset.hpref, box.checked);
    }));

    // Preset rapidi per target_api_url (OpenAI, DeepSeek, Kimi, Qwen, Ollama)
    document.querySelectorAll('.preset-target').forEach(btn => {
        btn.addEventListener('click', () => {
            const input = $('target_api_url');
            if (input && btn.dataset.url) {
                input.value = btn.dataset.url;
                input.dispatchEvent(new Event('change', { bubbles: true }));
                showToast(updText(`Servizio impostato su ${btn.textContent}`, `Service set to ${btn.textContent}`), 'success', 2500);
            }
        });
    });

    // Avvio / arresto del motore
    $('mainToggleBtn').addEventListener('click', async () => {
        const btn = $('mainToggleBtn');
        btn.disabled = true;
        btn.dataset.busy = '1';
        try {
            if (currentStatus === 'stopped' || currentStatus === 'error') {
                await startEngine();
            } else {
                await fetch('/api/stop', { method: 'POST' });
            }
        } catch (e) {
            showToast(updText('Germano non risponde: la finestra del programma è aperta?', 'Germano is not responding: is the program window open?'), 'error');
        } finally {
            delete btn.dataset.busy;
            btn.disabled = false;
            await pollStatus();
        }
    });
    $('retryEngineBtn').addEventListener('click', async () => {
        await startEngine();
        pollStatus();
    });
    $('btnStartFromCta').addEventListener('click', async () => {
        await startEngine();
        pollStatus();
    });

    // Pulsanti generici: Impostazioni, apertura cartelle e copia negli appunti
    document.addEventListener('click', (e) => {
        if (e.target.closest('[data-open-settings]')) {
            openSettings();
            return;
        }
        const folderBtn = e.target.closest('[data-open-folder]');
        if (folderBtn) {
            // i pulsanti dentro un riquadro delle cartelle (Seleziona file, Rimetti in coda...) fanno altro
            const inner = e.target.closest('button, a, input, label');
            if (inner && inner !== folderBtn && folderBtn.contains(inner)) return;
            openLocalFolder(folderBtn.dataset.openFolder);
            return;
        }
        const copyBtn = e.target.closest('[data-copy], [data-copy-from]');
        if (copyBtn) {
            const text = copyBtn.dataset.copy ?? $(copyBtn.dataset.copyFrom)?.textContent ?? '';
            if (text) copyText(text);
        }
    });

    // Ripristino automatico dei dati originali
    $('enable_deanonymize').addEventListener('change', (e) => {
        applyDeanonState(e.target.checked);
        persistSettings(true);
    });

    // Cartelle di lavoro: trascinamento dei file sulla cartella input, scelta di file o di una cartella
    const drop = $('fmBox-input');
    const fileInput = $('protectFileInput');
    const folderInput = $('protectFolderInput');
    $('btnPickFiles').addEventListener('click', () => fileInput.click());
    $('btnPickFolder').addEventListener('click', () => folderInput.click());
    [fileInput, folderInput].forEach(input => input.addEventListener('change', (e) => {
        const list = Array.from(e.target.files || []).map(f => ({ file: f, path: f.webkitRelativePath || f.name }));
        uploadFiles(list);
        input.value = '';
    }));
    const hasFiles = (e) => Array.from((e.dataTransfer && e.dataTransfer.types) || []).includes('Files');
    ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, (e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
        drop.classList.add('dragover');
    }));
    drop.addEventListener('dragleave', (e) => {
        if (!drop.contains(e.relatedTarget)) drop.classList.remove('dragover');
    });
    drop.addEventListener('drop', async (e) => {
        e.preventDefault();
        drop.classList.remove('dragover');
        if (!e.dataTransfer) return;
        const list = await filesFromDrop(e.dataTransfer);
        if (list.length) uploadFiles(list);
    });
    // le altre cartelle (output, processed, failed) si riempiono solo con il lavoro del motore
    document.querySelectorAll('.fm-box:not(.fm-input)').forEach(box => box.addEventListener('dragover', (e) => {
        e.preventDefault();
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'none';
    }));
    // un file lasciato fuori da un'area di rilascio non deve essere aperto dal browser
    window.addEventListener('dragover', e => e.preventDefault());
    window.addEventListener('drop', e => e.preventDefault());
    // riquadri delle cartelle: Invio o barra spaziatrice aprono la cartella come il clic
    document.querySelectorAll('.fm-box').forEach(box => box.addEventListener('keydown', (e) => {
        if ((e.key === 'Enter' || e.key === ' ') && e.target === box) {
            e.preventDefault();
            openLocalFolder(box.dataset.openFolder);
        }
    }));
    $('fmList-failed').addEventListener('click', (e) => {
        const btn = e.target.closest('[data-fm-retry]');
        if (btn) retryFailedDocument(btn.dataset.fmRetry);
    });

    // Documenti
    document.querySelectorAll('.tab[data-folder]').forEach(t => t.addEventListener('click', () => setFileTab(t.dataset.folder)));
    $('fileFilter').addEventListener('input', renderFiles);
    $('fileTableBody').addEventListener('click', (e) => {
        const btn = e.target.closest('[data-action]');
        const row = e.target.closest('tr[data-name]');
        if (btn && row) fileAction(btn.dataset.action, row.dataset.name);
    });
    $('btnRetryAll').addEventListener('click', retryAllFailed);
    $('btnOpenCurrentFolder').addEventListener('click', () => openLocalFolder(activeFileTab));
    $('btnExportCsv').addEventListener('click', exportCsv);

    // Testo
    let restoreTimer = null;
    $('manualInputText').addEventListener('input', () => {
        clearTimeout(restoreTimer);
        restoreTimer = setTimeout(() => restoreTextIfTagged(($('manualInputText').value || '').trim()), 300);
    });
    $('anonymizeTextBtn').addEventListener('click', anonymizeText);
    $('copyTextBtn').addEventListener('click', () => {
        const value = $('manualOutputText').value;
        if (value) copyText(value);
        else showToast(updText('Nessun risultato da copiare.', 'No result to copy.'), 'error');
    });

    // Filtri e modelli
    document.querySelectorAll('.model-check, .cat-check').forEach(chk => chk.addEventListener('change', () => {
        if (!chk.checked) currentComplianceMode = 'PD';
        updatePresetButtons();
        persistSettings(true);
    }));
    const setChecks = (ids, value) => ids.forEach(id => { if ($(id)) $(id).checked = typeof value === 'function' ? value(id) : value; });
    $('btnModelsAllOn').addEventListener('click', () => {
        setChecks(ALL_MODEL_IDS, true);
        updatePresetButtons();
        persistSettings(true);
    });
    $('btnModelsAllOff').addEventListener('click', () => {
        currentComplianceMode = 'PD';
        setChecks(ALL_MODEL_IDS, false);
        updatePresetButtons();
        persistSettings(true);
    });
    $('btnPresetPA').addEventListener('click', () => {
        currentComplianceMode = 'PA';
        setChecks([...ALL_MODEL_IDS, ...ALL_CATEGORY_IDS], true);
        $('ai_threshold').value = 0;
        updateThresholdBadge(0);
        updatePresetButtons();
        persistSettings(true);
    });
    $('btnPresetEssential').addEventListener('click', () => {
        currentComplianceMode = 'PD';
        setChecks(ALL_CATEGORY_IDS, id => ESSENTIAL_CATEGORIES.has(id));
        updatePresetButtons();
        persistSettings(true);
    });
    $('btnPresetNone').addEventListener('click', () => {
        currentComplianceMode = 'PD';
        setChecks(ALL_CATEGORY_IDS, false);
        updatePresetButtons();
        persistSettings(true);
    });
    const threshold = $('ai_threshold');
    threshold.addEventListener('input', () => updateThresholdBadge(threshold.value));
    threshold.addEventListener('change', () => {
        if (parseFloat(threshold.value) > 0) currentComplianceMode = 'PD';
        persistSettings(true);
    });
    ['hardware_mode', 'precision', 'target_api_url', 'target_anthropic_url', 'file_timeout_minutes', 'anonymize_filenames',
        'check_updates', 'auto_update', 'enable_system2', 'speech_language']
        .forEach(id => $(id)?.addEventListener('change', () => persistSettings(true)));

    // Aggiornamenti silenziosi
    $('btnUpdateCheck').addEventListener('click', () => updateAction(lastUpdate && lastUpdate.state === 'available' ? '/api/update/download' : '/api/update/check',
                                                                     updText('Controllo degli aggiornamenti in corso…', 'Checking for updates…')));
    $('btnUpdateInstall').addEventListener('click', installUpdate);
    $('updatePill').addEventListener('click', (e) => { e.stopPropagation(); if ($('updatePop').hidden) openUpdatePop(); else $('updatePop').hidden = true; });
    $('btnUpdateRestart').addEventListener('click', installUpdate);
    $('btnUpdateLater').addEventListener('click', () => { $('updatePop').hidden = true; });
    document.addEventListener('mousedown', (e) => { if (!$('updatePop').hidden && !e.target.closest('.update-wrap')) $('updatePop').hidden = true; });

    // Archivio delle corrispondenze e registro
    $('btnShowVault').addEventListener('click', toggleVault);
    $('vaultFilter').addEventListener('input', renderVaultRows);
    $('btnClearVault').addEventListener('click', async () => {
        if (!confirm(updText('Svuotare l\'archivio delle corrispondenze?\nI documenti già anonimizzati non potranno più essere ripristinati con i dati originali.',
                             'Clear the mapping archive?\nDocuments already anonymized can no longer be restored with the original data.'))) return;
        const { ok, data } = await postJson('/api/clear_vault', {});
        $('vaultPreviewBox').hidden = true;
        $('vaultSearchRow').hidden = true;
        setText('btnShowVault', 'Mostra');
        showToast(ok ? updText('Archivio delle corrispondenze svuotato.', 'Mapping archive cleared.') : (data.message || updText('Operazione non riuscita.', 'Operation failed.')), ok ? 'info' : 'error');
        pollStatus();
    });
    $('clearLogsBtn').addEventListener('click', async () => {
        await fetch('/api/clear_logs', { method: 'POST' });
        pollLogs();
        showToast(updText('Registro attività pulito.', 'Activity log cleared.'), 'info', 2200);
    });

    // Processi rimasti da una sessione precedente
    fetchJson('/api/check_orphans').then(({ data }) => {
        if (data.orphans > 0) {
            setText('orphanCount', data.orphans);
            $('orphanWarning').hidden = false;
        }
    }).catch(() => {});
    $('killOrphansBtn').addEventListener('click', async () => {
        await fetch('/api/kill_orphans', { method: 'POST' });
        $('orphanWarning').hidden = true;
        showToast(updText('Processi secondari chiusi.', 'Leftover processes closed.'), 'success');
    });
    setInterval(pollStatus, 1500);
    setInterval(pollLogs, 2000);
    setInterval(renderNetSummary, 5000);   // aggiorna solo se è aperta la sezione Modalità e rete
});
