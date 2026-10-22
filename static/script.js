'use strict';
/* Germano AI - Dashboard: stato del motore, lavoro in batch, documenti, agenti AI, impostazioni. */

let currentUiMode = 'simple';
let currentView = 'work';
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
let batch = { active: false, baseDone: 0, baseFailed: 0, done: 0, failed: 0, summary: null };
let updateInstalling = false;
let pageVersion = null;

const VIEWS = ['work', 'agents', 'filters', 'system'];
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

function setText(id, value) {
    const el = $(id);
    if (el) el.textContent = value;
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

function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
    return `${parseFloat((bytes / Math.pow(1024, i)).toFixed(1)).toLocaleString('it-IT')} ${units[i]}`;
}

function formatDate(epoch) {
    if (!epoch) return '';
    const d = new Date(epoch * 1000);
    const time = d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
    if (d.toDateString() === new Date().toDateString()) return `oggi ${time}`;
    return `${d.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', year: 'numeric' })} ${time}`;
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
    showToast('Copiato negli appunti.', 'success', 2200);
}

function proxyBase() {
    // sempre 127.0.0.1: alcuni strumenti risolvono "localhost" in IPv6, su cui Germano non è in ascolto
    return `http://127.0.0.1:${location.port || '80'}`;
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

// ------------------------------------------------------------------ MODALITÀ E SEZIONI
function applyUiMode(mode, save = true) {
    currentUiMode = mode === 'advanced' ? 'advanced' : 'simple';
    document.body.classList.toggle('mode-simple', currentUiMode === 'simple');
    document.body.classList.toggle('mode-advanced', currentUiMode === 'advanced');
    $('btnModeSimple').classList.toggle('active', currentUiMode === 'simple');
    $('btnModeAdvanced').classList.toggle('active', currentUiMode === 'advanced');
    if (currentUiMode === 'simple' && activeFileTab === 'processed') setFileTab('output');
    let view = 'work';
    if (currentUiMode === 'advanced') {
        try { view = localStorage.getItem('germano_view') || 'work'; } catch (e) { view = 'work'; }
    }
    applyView(view, false);
    if (save) persistSettings(false);
}

function applyView(view, remember = true) {
    if (currentUiMode !== 'advanced' || !VIEWS.includes(view)) view = 'work';
    currentView = view;
    document.body.dataset.view = view;
    document.querySelectorAll('.view-tab').forEach(t => t.classList.toggle('active', t.dataset.view === view));
    if (remember) {
        try { localStorage.setItem('germano_view', view); } catch (e) { /* archivio del browser non disponibile */ }
        window.scrollTo(0, 0);
    }
    if (view === 'system') {
        loadFolders();
        pollLogs();
    }
}

// ------------------------------------------------------------------ IMPOSTAZIONI
function updateThresholdBadge(val) {
    const pct = Math.round(parseFloat(val || 0) * 100);
    setText('thresholdValue', pct === 0 ? 'Massima (soglia 0%)' : `Soglia ${pct}%`);
}

function updateProfilePill() {
    const pill = $('profilePill');
    const pa = currentComplianceMode === 'PA';
    pill.innerHTML = (settingsLocked ? iconSvg('i-lock') : '') + (pa ? 'Profilo PA' : 'Profilo PD');
    pill.title = pa
        ? 'Profilo PA: tutti i modelli e tutte le categorie attivi, sensibilità massima.'
        : 'Profilo PD: configurazione personalizzata di modelli, categorie o sensibilità.';
    if (settingsLocked) pill.title += ' Impostazioni bloccate dall\'amministratore.';
    document.body.classList.toggle('settings-locked', settingsLocked);
    $('lockedBanner').hidden = !settingsLocked;
    document.querySelectorAll('.model-check, .cat-check, .btn-preset, #ai_threshold, #check_updates, #auto_update').forEach(el => {
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
    badge.textContent = enabled ? 'Attivo' : 'Disattivato';
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
        anonymize_filenames: $('anonymize_filenames')?.checked ?? false,
        check_updates: $('check_updates')?.checked ?? true,
        auto_update: $('auto_update')?.checked ?? true
    };
    ALL_MODEL_IDS.forEach(k => { out[k] = $(k)?.checked ?? true; });
    ALL_CATEGORY_IDS.forEach(k => { out[k] = $(k)?.checked ?? true; });
    return out;
}

function applySettingsToUi(cfg) {
    currentComplianceMode = cfg.compliance_mode || 'PA';
    settingsLocked = Boolean(cfg.lock_settings);
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
    setVal('target_api_url', cfg.target_api_url);
    setVal('target_anthropic_url', cfg.target_anthropic_url);
    $('anonymize_filenames').checked = Boolean(cfg.anonymize_filenames);
    $('check_updates').checked = cfg.check_updates !== false;
    $('auto_update').checked = cfg.auto_update !== false;
    updatePresetButtons();
}

async function persistSettings(notify = true) {
    try {
        const { ok, data } = await postJson('/api/settings', { settings: gatherSettings() });
        if (!ok || !data.settings) return;
        if (data.status === 'locked') {
            showToast(data.message || 'Impostazioni bloccate dall\'amministratore.', 'error', 6000);
            applySettingsToUi(data.settings);
            return;
        }
        currentComplianceMode = data.settings.compliance_mode || currentComplianceMode;
        updatePresetButtons();
        if (notify) showToast('Impostazioni salvate.', 'success', 2200);
    } catch (e) {
        showToast('Impossibile salvare le impostazioni: Germano non risponde.', 'error');
    }
}

async function loadInitialSettings() {
    try {
        const { ok, data } = await fetchJson('/api/settings');
        if (!ok) return;
        applySettingsToUi(data);
        applyUiMode(data.ui_mode || 'simple', false);
    } catch (e) { /* server non raggiungibile: gestito da pollStatus */ }
}

// ------------------------------------------------------------------ MOTORE
async function startEngine() {
    await postJson('/api/start', { settings: gatherSettings() });
}

async function ensureEngineRunning() {
    if (engineActive()) return true;
    showToast('Avvio del motore in corso...', 'info');
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
        if (!ok) showToast(data.message || 'Impossibile aprire la cartella.', 'error');
    } catch (e) {
        showToast('Impossibile aprire la cartella: Germano non risponde.', 'error');
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

// ------------------------------------------------------------------ AGGIORNAMENTI
function renderUpdate(u) {
    if (!u) return;
    const pct = u.progress && u.progress.total ? Math.min(100, Math.round((100 * u.progress.done) / u.progress.total)) : 0;
    let text = '', cls = 'banner-info', progress = false, download = false, install = false, ack = false;
    switch (u.state) {
        case 'available':
            text = `È disponibile la nuova versione ${u.latest} di Germano AI.`;
            download = true;
            break;
        case 'downloading':
            text = `Download dell'aggiornamento ${u.latest}: ${pct}% (${formatBytes(u.progress.done)} di ${formatBytes(u.progress.total)}).`;
            progress = true;
            break;
        case 'verifying':
            text = `Verifica dell'impronta dell'aggiornamento ${u.latest}...`;
            break;
        case 'extracting':
            text = `Preparazione dell'aggiornamento ${u.latest}: ${pct}%.`;
            progress = true;
            break;
        case 'ready':
            text = `La versione ${u.latest} è pronta: verrà installata al prossimo avvio di Germano.`;
            install = true;
            break;
        case 'installing':
            text = 'Installazione dell\'aggiornamento in corso: Germano si riaprirà da solo tra qualche minuto.';
            updateInstalling = true;
            break;
        case 'error':
            text = `Aggiornamento non riuscito: ${u.error || 'errore sconosciuto'}`;
            cls = 'banner-danger';
            download = Boolean(u.latest);
            break;
        default: {
            const li = u.last_install;
            if (li && li.status === 'ok' && li.to === u.current) {
                text = `Germano AI è stato aggiornato alla versione ${li.to}.`;
                cls = 'banner-ok';
                ack = true;
            } else if (li && li.status === 'error') {
                text = `L'aggiornamento alla versione ${li.target} non è riuscito (${li.error}): la versione precedente è stata mantenuta. Dettagli in update/update.log.`;
                cls = 'banner-danger';
                ack = true;
            }
        }
    }
    const banner = $('updateBanner');
    banner.hidden = !text;
    banner.className = `banner ${cls}`;
    setText('updateBannerText', text);
    $('updateProgress').hidden = !progress;
    $('updateProgressBar').style.width = `${pct}%`;
    $('btnUpdateDownload').hidden = !download;
    setText('btnUpdateDownload', u.state === 'error' ? 'Riprova' : 'Scarica aggiornamento');
    $('btnUpdateInstall').hidden = !install;
    $('btnUpdateAck').hidden = !ack;

    let info = `Versione installata ${u.current}`;
    if (u.checked_at) info += ` · ultimo controllo ${new Date(u.checked_at * 1000).toLocaleString('it-IT')}`;
    if (u.state === 'uptodate') info += ' · nessun aggiornamento disponibile';
    if (u.online === false) info += ' · Windows non segnala una connessione a Internet: nessun controllo eseguito';
    setText('updateInfo', info);
}

async function updateAction(path, okMessage) {
    try {
        const { ok, data } = await postJson(path, {});
        if (!ok) showToast(data.message || 'Operazione non riuscita.', 'error', 6000);
        else if (okMessage) showToast(okMessage, 'info');
    } catch (e) {
        showToast('Germano non risponde.', 'error');
    }
    pollStatus();
}

async function installUpdate() {
    const p = (lastStatus && lastStatus.progress) || {};
    const pending = lastStatus && lastStatus.stats ? lastStatus.stats.pending : 0;
    let msg = 'Installare ora l\'aggiornamento?\nGermano si chiude, sostituisce i file del programma e si riapre da solo (qualche minuto).\nCartelle di lavoro, archivio delle corrispondenze e impostazioni non vengono toccati.';
    if (p.state === 'working' || pending > 0) {
        msg += '\n\nL\'elaborazione in corso verrà interrotta e ripresa automaticamente dopo l\'aggiornamento.';
    }
    if (!confirm(msg)) return;
    updateInstalling = true;
    await updateAction('/api/update/install', 'Installazione dell\'aggiornamento avviata: Germano si riaprirà da solo.');
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
    btn.className = 'btn ' + (active ? 'btn-stop' : 'btn-start');
    if (!btn.dataset.busy) btn.disabled = disabled;

    $('engineErrorBanner').hidden = data.status !== 'error';
    setText('engineErrorText', data.error || '');

    const proxy = $('proxyStatus');
    if (data.status === 'running') {
        proxy.className = 'badge badge-ok';
        proxy.textContent = 'Proxy attivo';
    } else if (data.status === 'loading_models') {
        proxy.className = 'badge badge-warn';
        proxy.textContent = 'Proxy in avvio';
    } else {
        proxy.className = 'badge badge-off';
        proxy.textContent = 'Proxy non attivo: avvia il motore';
    }
}

function renderCounts(stats) {
    setText('countInput', stats.pending);
    setText('countOutput', stats.outputs);
    setText('countFailed', stats.failed);
    setText('tabCountOutput', stats.outputs);
    setText('tabCountInput', stats.pending);
    setText('tabCountFailed', stats.failed);
    setText('tabCountProcessed', stats.processed);
    setText('vaultCountBadge', stats.vault_count || 0);
    setText('advVaultCount', stats.vault_count || 0);
    $('kpiFailed').classList.toggle('has-items', stats.failed > 0);
    document.querySelector('.tab-failed')?.classList.toggle('has-items', stats.failed > 0);
    $('kpiPending').classList.toggle('attention', stats.pending > 0 && !engineActive());

    const cta = stats.pending > 0 && (currentStatus === 'stopped' || currentStatus === 'error');
    $('pendingCta').hidden = !cta;
    setText('pendingCtaText', stats.pending === 1
        ? '1 documento in attesa nella cartella input'
        : `${stats.pending} documenti in attesa nella cartella input`);
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
        batch = { active: true, baseDone: done, baseFailed: failed, done: 0, failed: 0, summary: null };
    }
    if (!batch.active) return;
    batch.done = done - batch.baseDone;
    batch.failed = failed - batch.baseFailed;
    if (pending === 0 && !working) {
        batch.active = false;
        if (batch.done + batch.failed > 0) {
            batch.summary = { done: batch.done, failed: batch.failed, at: Date.now() };
            const msg = `Lotto completato: ${plural(batch.done, 'documento elaborato', 'documenti elaborati')}`
                + (batch.failed ? `, ${plural(batch.failed, 'non riuscito', 'non riusciti')} (vedi «Non riusciti»).` : '.');
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
        title = 'Avvio del motore in corso';
        detail = 'Caricamento dei modelli di analisi: la prima volta può richiedere qualche minuto.';
        spin = true;
    } else if (working) {
        title = 'In lavorazione';
        file = p.current;
        detail = p.detail ? `Fase: ${p.detail}` : 'Elaborazione in corso';
        spin = true;
    } else if (running && pending > 0) {
        title = 'Documenti in arrivo';
        detail = 'Attendo che la copia dei file nella cartella input sia completata...';
        spin = true;
    } else if (batch.summary && Date.now() - batch.summary.at < 15 * 60 * 1000) {
        const s = batch.summary;
        title = 'Lotto completato';
        detail = `${plural(s.done, 'documento elaborato', 'documenti elaborati')}`
            + (s.failed ? `, ${plural(s.failed, 'non riuscito', 'non riusciti')}` : '')
            + ` alle ${new Date(s.at).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}.`;
        cls = s.failed ? 'done-with-errors' : 'done';
    } else if (running) {
        title = 'Motore attivo';
        detail = 'In attesa di documenti: aggiungili qui a sinistra oppure copiali nella cartella input.';
    } else if (data.status === 'error') {
        title = 'Motore fermo per errore';
        detail = 'Il motivo è indicato in alto; il dettaglio è nel registro attività.';
    } else {
        title = 'Motore in pausa';
        detail = pending > 0
            ? 'I documenti in attesa verranno elaborati all\'avvio del motore.'
            : 'Aggiungi documenti: il motore si avvia automaticamente.';
    }

    const progress = $('batchProgress');
    if (batch.active) {
        const processed = batch.done + batch.failed;
        const total = processed + pending;
        progress.hidden = false;
        $('batchProgressBar').style.width = `${total ? Math.round((100 * processed) / total) : 0}%`;
        detail += ` · Lotto: ${processed} di ${total}` + (batch.failed ? ` (${batch.failed} non riusciti)` : '');
    } else {
        progress.hidden = true;
    }
    $('currentJob').className = 'job' + (cls ? ' ' + cls : '');
    $('jobSpinner').hidden = !spin;
    setText('jobTitle', title);
    setText('jobFile', file);
    setText('jobDetail', detail);
}

function renderSystem(data) {
    if (!data.system) return;
    let t = `CPU ${data.system.cpu_percent}% · RAM ${data.system.ram_used_gb} / ${data.system.ram_total_gb} GB`;
    if (data.engine && data.engine.precision) t += ` · modello ${String(data.engine.precision).toUpperCase()}`;
    setText('sysUsagePill', t);
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
        if (sig !== filesSignature || Date.now() - lastFilesFetch > 10000) {
            filesSignature = sig;
            fetchFiles();
        }
    }
    renderJob(data);
    renderSystem(data);
}

// ------------------------------------------------------------------ DOCUMENTI
async function fetchFiles() {
    lastFilesFetch = Date.now();
    try {
        const { ok, data } = await fetchJson('/api/files', { cache: 'no-store' });
        if (!ok) return;
        cachedFiles = data;
        renderFiles();
    } catch (e) { /* server non raggiungibile: gestito da pollStatus */ }
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
            return '<span class="badge badge-info">Dati ripristinati</span>';
        }
        let html = '<span class="badge badge-ok">Anonimizzato</span>';
        if (typeof it.entities === 'number') {
            html += `<span class="status-sub">${plural(it.entities, 'dato oscurato', 'dati oscurati')}</span>`;
        }
        if (it.notes) html += `<span class="status-sub">${plural(it.notes, 'avviso', 'avvisi')} nel report</span>`;
        return html;
    }
    if (folder === 'input') {
        return it.name === current
            ? '<span class="badge badge-warn"><span class="spinner"></span>In lavorazione</span>'
            : '<span class="badge">In attesa</span>';
    }
    if (folder === 'failed') return '<span class="badge badge-danger">Non riuscito</span>';
    return '<span class="badge badge-off">Originale</span>';
}

function actionsCell(folder, it) {
    const btn = (action, icon, title) =>
        `<button type="button" class="btn-icon" data-action="${action}" title="${title}" aria-label="${title}">${iconSvg(icon)}</button>`;
    const href = '/api/download/' + folder + '/' + it.name.split('/').map(encodeURIComponent).join('/');
    const download = `<a class="btn-icon" href="${escapeHtml(href)}" download title="Scarica una copia" aria-label="Scarica una copia">${iconSvg('i-download')}</a>`;
    const reveal = btn('reveal', 'i-locate', 'Mostra nella cartella');
    if (folder === 'input') return reveal;
    if (folder === 'failed') {
        return `<button type="button" class="btn btn-secondary btn-sm" data-action="retry">${iconSvg('i-retry')}Rimetti in coda</button>${reveal}${download}`;
    }
    return btn('open', 'i-external', 'Apri') + reveal + download;
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
            ? `<div class="file-reason">${escapeHtml(it.reason || 'Motivo non disponibile: vedi il registro attività.')}</div>`
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
    empty.textContent = q ? 'Nessun documento corrisponde al filtro.' : EMPTY_MESSAGES[folder];

    let info = '';
    if (q) info = `${items.length} di ${all.length} documenti`;
    else if (total > all.length) info = `Mostrati i ${all.length} più recenti su ${total}`;
    else if (total) info = plural(total, 'documento', 'documenti');
    setText('fileListInfo', info);
    $('btnRetryAll').hidden = !(folder === 'failed' && all.length > 0);
    setText('btnOpenCurrentFolderLabel', `Apri cartella ${folder}`);
    $('btnExportCsv').disabled = all.length === 0;
    document.querySelectorAll('.kpi[data-show-tab]').forEach(k => k.classList.toggle('selected', k.dataset.showTab === folder));
}

async function fileAction(action, name) {
    const folder = activeFileTab;
    if (action === 'retry') {
        const { ok, data } = await postJson('/api/retry_failed', { names: [name] });
        if (ok && (data.moved || []).length) {
            showToast(engineActive() ? 'Documento rimesso in coda.' : 'Documento rimesso in coda: avvia il motore per elaborarlo.', 'success');
        } else {
            showToast((data.errors || [])[0] || data.message || 'Impossibile rimettere in coda il documento.', 'error');
        }
        await fetchFiles();
        pollStatus();
        return;
    }
    const { ok, data } = await postJson('/api/file_action', { folder, name, action });
    if (!ok) showToast(data.message || 'Operazione non riuscita.', 'error', 6000);
}

async function retryAllFailed() {
    const n = (cachedFiles.totals || {}).failed || (cachedFiles.failed || []).length;
    if (!n || !confirm(`Rimettere in coda ${plural(n, 'documento non riuscito', 'documenti non riusciti')}?\nVerranno spostati di nuovo nella cartella input.`)) return;
    const { ok, data } = await postJson('/api/retry_failed', { all: true });
    if (ok) {
        const moved = (data.moved || []).length;
        showToast(`${plural(moved, 'documento rimesso', 'documenti rimessi')} in coda.` + (engineActive() ? '' : ' Avvia il motore per elaborarli.'), 'success');
        (data.errors || []).slice(0, 3).forEach(err => showToast(err, 'error', 6000));
    } else {
        showToast(data.message || 'Operazione non riuscita.', 'error');
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
    showToast(list.length === 1 ? 'Caricamento del documento...' : `Caricamento di ${list.length} documenti...`, 'info');
    try {
        const { ok, data } = await fetchJson('/api/upload_files', { method: 'POST', body: formData });
        if (!ok || data.status !== 'success') {
            showToast(data.message || 'Errore durante il caricamento.', 'error');
            return;
        }
        if (data.auto_restored_count > 0) {
            showToast(`${plural(data.auto_restored_count, 'file restituito', 'file restituiti')} dall'AI: dati originali ripristinati (vedi «Pronti»).`, 'success', 6000);
            setFileTab('output');
        }
        if (data.saved_count > 0) {
            showToast(`${plural(data.saved_count, 'documento aggiunto', 'documenti aggiunti')} alla coda.`, 'success');
            await ensureEngineRunning();
        }
        (data.errors || []).forEach(err => showToast(`Errore: ${err}`, 'error', 7000));
        fetchFiles();
        pollStatus();
    } catch (e) {
        showToast('Errore di connessione durante il caricamento.', 'error');
    }
}

// ------------------------------------------------------------------ AGENTI AI E API
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
                    <button type="button" class="btn btn-secondary btn-sm" data-open-folder="${key}">${iconSvg('i-folder')}Apri</button>
                </div>
            </div>`).join('');
    } catch (e) { /* riprova alla prossima apertura della sezione */ }
}

async function pollLogs() {
    if (currentUiMode !== 'advanced' || currentView !== 'system') return;
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

async function toggleVault() {
    const box = $('vaultPreviewBox');
    if (!box.hidden) {
        box.hidden = true;
        setText('btnShowVault', 'Mostra');
        return;
    }
    try {
        const { data } = await fetchJson('/api/vault', { cache: 'no-store' });
        const items = data.items || [];
        box.innerHTML = items.length
            ? items.map(it => `<div class="vault-row"><code>${escapeHtml(it.tag)}</code><span>${escapeHtml(it.value)}</span></div>`).join('')
            : '<div class="vault-empty">Nessuna corrispondenza in archivio.</div>';
        box.hidden = false;
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
            setTextBadge('Dati originali ripristinati');
            showToast('Risposta dell\'AI riconosciuta: dati originali ripristinati.', 'success');
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
        showToast('Scrivi o incolla prima un testo.', 'error');
        return;
    }
    if (await restoreTextIfTagged(text)) return;
    btn.disabled = true;
    const original = label.textContent;
    try {
        if (currentStatus !== 'running') {
            label.textContent = 'Avvio del motore...';
            await ensureEngineRunning();
            if (!(await waitForEngineReady())) {
                showToast('Il motore non si è avviato: controlla il messaggio in alto.', 'error', 6000);
                return;
            }
        }
        label.textContent = 'Elaborazione...';
        const { ok, data } = await postJson('/api/v1/anonymize_text', { text });
        if (ok && data.anonymized !== undefined) {
            $('manualOutputText').value = data.anonymized;
            if (data.auto_restored) {
                setTextBadge('Dati originali ripristinati');
            } else {
                const n = (data.extracted_data || []).length;
                setTextBadge(plural(n, 'dato oscurato', 'dati oscurati'));
                showToast(`Testo anonimizzato: ${plural(n, 'dato oscurato', 'dati oscurati')}.`, 'success');
            }
            pollStatus();
        } else {
            showToast(data.error || 'Errore durante l\'elaborazione del testo.', 'error');
        }
    } catch (e) {
        showToast('Errore di comunicazione con il motore locale.', 'error');
    } finally {
        btn.disabled = false;
        label.textContent = original;
    }
}

// ------------------------------------------------------------------ AVVIO PAGINA
document.addEventListener('DOMContentLoaded', async () => {
    await loadInitialSettings();
    renderAgents();
    await pollStatus();
    await fetchFiles();

    $('btnModeSimple').addEventListener('click', () => applyUiMode('simple', true));
    $('btnModeAdvanced').addEventListener('click', () => applyUiMode('advanced', true));
    document.querySelectorAll('.view-tab').forEach(t => t.addEventListener('click', () => applyView(t.dataset.view)));

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
            showToast('Germano non risponde: la finestra del programma è aperta?', 'error');
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

    // Pulsanti generici: apertura cartelle e copia negli appunti
    document.addEventListener('click', (e) => {
        const folderBtn = e.target.closest('[data-open-folder]');
        if (folderBtn) {
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

    // Aggiunta di documenti: trascinamento, scelta di file o di una cartella
    const drop = $('protectDropzone');
    const fileInput = $('protectFileInput');
    const folderInput = $('protectFolderInput');
    $('btnPickFiles').addEventListener('click', () => fileInput.click());
    $('btnPickFolder').addEventListener('click', () => folderInput.click());
    [fileInput, folderInput].forEach(input => input.addEventListener('change', (e) => {
        const list = Array.from(e.target.files || []).map(f => ({ file: f, path: f.webkitRelativePath || f.name }));
        uploadFiles(list);
        input.value = '';
    }));
    ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, (e) => {
        e.preventDefault();
        drop.classList.add('dragover');
    }));
    ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, (e) => {
        e.preventDefault();
        if (ev === 'drop' || !drop.contains(e.relatedTarget)) drop.classList.remove('dragover');
    }));
    drop.addEventListener('drop', async (e) => {
        if (!e.dataTransfer) return;
        const list = await filesFromDrop(e.dataTransfer);
        if (list.length) uploadFiles(list);
    });
    // un file lasciato fuori dal riquadro non deve essere aperto dal browser
    window.addEventListener('dragover', e => e.preventDefault());
    window.addEventListener('drop', e => e.preventDefault());

    // Documenti
    document.querySelectorAll('.tab[data-folder]').forEach(t => t.addEventListener('click', () => setFileTab(t.dataset.folder)));
    document.querySelectorAll('.kpi[data-show-tab]').forEach(k => k.addEventListener('click', () => {
        setFileTab(k.dataset.showTab);
        document.querySelector('.tabs')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }));
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
        else showToast('Nessun risultato da copiare.', 'error');
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
        'check_updates', 'auto_update']
        .forEach(id => $(id).addEventListener('change', () => persistSettings(true)));

    // Aggiornamenti
    $('btnUpdateCheck').addEventListener('click', () => updateAction('/api/update/check', 'Controllo degli aggiornamenti in corso...'));
    $('btnUpdateDownload').addEventListener('click', () => updateAction('/api/update/download', 'Download dell\'aggiornamento avviato.'));
    $('btnUpdateInstall').addEventListener('click', installUpdate);
    $('btnUpdateAck').addEventListener('click', () => updateAction('/api/update/ack'));

    // Archivio delle corrispondenze e registro
    $('btnShowVault').addEventListener('click', toggleVault);
    $('btnClearVault').addEventListener('click', async () => {
        if (!confirm('Svuotare l\'archivio delle corrispondenze?\nI documenti già anonimizzati non potranno più essere ripristinati con i dati originali.')) return;
        const { ok, data } = await postJson('/api/clear_vault', {});
        $('vaultPreviewBox').hidden = true;
        setText('btnShowVault', 'Mostra');
        showToast(ok ? 'Archivio delle corrispondenze svuotato.' : (data.message || 'Operazione non riuscita.'), ok ? 'info' : 'error');
        pollStatus();
    });
    $('clearLogsBtn').addEventListener('click', async () => {
        await fetch('/api/clear_logs', { method: 'POST' });
        pollLogs();
        showToast('Registro attività pulito.', 'info', 2200);
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
        showToast('Processi secondari chiusi.', 'success');
    });
    setInterval(pollStatus, 1500);
    setInterval(pollLogs, 2000);
});
