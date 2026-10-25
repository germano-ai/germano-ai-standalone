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
let batch = { active: false, baseDone: 0, baseFailed: 0, done: 0, failed: 0, summary: null, startedAt: 0 };
let updateInstalling = false;
let pageVersion = null;
let currentApp = 'batch';         // 'batch' (Anonimizza file) | 'studio' (Studio AI)
let studioFiles = [];             // allegati in attesa di invio nello Studio
let studioDetected = null;        // ultimo risultato di /api/ai/detect
let configReturn = null;          // dove rimettere i pannelli di configurazione quando il cassetto si chiude
let tooltipsEnabled = true;       // preferenza salvata (enable_tooltips): suggerimenti attivi di default
let initialConfig = null;         // configurazione letta all'apertura (serve a riconoscere la prima apertura)
let modeState = null;             // ultimo stato di /api/mode (modalita' operativa, rete, motore)
let settingsWelcome = false;      // la finestra Impostazioni fa da benvenuto alla prima apertura
let settingsDone = false;         // dopo il salvataggio in modalita' Server la finestra resta aperta per il token

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

// Studio: destinazioni sempre disponibili (oltre alle CLI locali rilevate). mode: come si inoltra il testo protetto.
const STUDIO_CLOUD_TARGETS = [
    { id: 'deepseek', name: 'DeepSeek', mode: 'cloud' },
    { id: 'kimi', name: 'Kimi (Moonshot)', mode: 'cloud' },
    { id: 'qwen', name: 'Qwen (DashScope)', mode: 'cloud' },
    { id: 'clipboard', name: 'Copia testo protetto', mode: 'clipboard' }
];
// Come si comporta Germano con il testo protetto, per tipo di destinazione.
const STUDIO_TARGET_MODE = { cli: 'harness locale', app: 'harness locale', service: 'servizio locale', cloud: 'gateway cloud', clipboard: 'copia manuale' };

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
    'Vault ed estratti': 'Vault & extracted',
    'Attivo': 'Active',
    'Disattivo': 'Inactive',
    'Elaborazione in corso...': 'Processing in progress...',
    'Completato': 'Completed',
    'Nessun documento in attesa': 'No pending documents',
    'Standalone': 'Standalone',
    'Server': 'Server',
    'Client': 'Client',
    'Server + Client': 'Server + Client',
    'Profilo PA': 'PA Profile',
    'Profilo PD': 'PD Profile'
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
    showToast('Copiato negli appunti.', 'success', 2200);
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
        renderNetSummary();
    }
}

// ------------------------------------------------------------------ MODALITÀ APP (Batch / Studio)
function applyAppMode(app, save = true) {
    currentApp = app === 'studio' ? 'studio' : 'batch';
    document.body.dataset.app = currentApp;
    $('btnAppBatch')?.classList.toggle('active', currentApp === 'batch');
    $('btnAppStudio')?.classList.toggle('active', currentApp === 'studio');
    if (save) {
        try { localStorage.setItem('germano_app', currentApp); } catch (e) { /* archivio non disponibile */ }
    }
    if (currentApp === 'studio') {
        window.scrollTo(0, 0);
        if (!studioDetected) detectAI(false);
        if (!$('studioTarget').options.length) populateStudioTargets();
    }
}

// ------------------------------------------------------------------ RILEVAMENTO AI (Studio)
function aiChip(t) {
    const ver = t.version ? ` <span class="ai-ver">${escapeHtml(t.version)}</span>` : '';
    const mark = t.detected ? ' ✓' : '';
    const where = t.path || (t.detected ? '' : 'non rilevato');   // dalla rete il server non comunica i percorsi
    return `<span class="ai-chip ${t.detected ? 'on' : ''}" title="${escapeHtml(where)}"><span class="dot"></span>${escapeHtml(t.name)}${ver}${mark}</span>`;
}

function populateStudioTargets() {
    const sel = $('studioTarget');
    if (!sel) return;
    const prev = sel.value;
    const detected = (studioDetected || []).filter(t => t.detected && (t.kind === 'cli' || t.kind === 'app'));
    const opts = detected.map(t => `<option value="${escapeHtml(t.id)}" data-kind="${t.kind}">${escapeHtml(t.name)}</option>`);
    opts.push(...STUDIO_CLOUD_TARGETS.map(t => `<option value="${t.id}" data-kind="clipboard">${escapeHtml(t.name)}</option>`));
    sel.innerHTML = opts.join('');
    if (prev && [...sel.options].some(o => o.value === prev)) sel.value = prev;
    updateStudioTargetBadge();
}

function updateStudioTargetBadge() {
    const sel = $('studioTarget');
    const badge = $('studioTargetBadge');
    if (!sel || !badge) return;
    const opt = sel.selectedOptions[0];
    const kind = opt ? opt.dataset.kind : 'clipboard';
    const label = STUDIO_TARGET_MODE[kind] || '';
    badge.textContent = label;
    badge.hidden = !label;
}

async function detectAI(force) {
    const strip = $('aiStrip');
    if (strip && force) strip.innerHTML = '<span class="ai-strip-empty">Ricerca in corso…</span>';
    try {
        const { ok, data } = await fetchJson('/api/ai/detect' + (force ? '?refresh=1' : ''));
        if (!ok || !data.tools) return;
        studioDetected = data.tools;
        const found = data.tools.filter(t => t.detected);
        if (strip) {
            strip.innerHTML = found.length
                ? found.map(aiChip).join('')
                : '<span class="ai-strip-empty">Nessuna AI o CLI rilevata su questo computer.</span>';
        }
        populateStudioTargets();
        if (force) showToast(`Rilevate ${plural(found.length, 'AI', 'AI')} su questo computer.`, found.length ? 'success' : 'info', 3000);
    } catch (e) {
        if (strip) strip.innerHTML = '<span class="ai-strip-empty">Rilevamento non riuscito.</span>';
    }
}

// ------------------------------------------------------------------ STUDIO AI: allegati e invio
function renderAttachChips() {
    const box = $('attachChips');
    if (!box) return;
    box.hidden = studioFiles.length === 0;
    box.innerHTML = studioFiles.map((f, i) =>
        `<span class="attach-chip">${iconSvg('i-files')}${escapeHtml(f.name)} <small>(${formatBytes(f.size)})</small>` +
        `<button type="button" data-remove-attach="${i}" title="Rimuovi" aria-label="Rimuovi allegato">✕</button></span>`
    ).join('');
}

function addStudioFiles(fileList) {
    for (const file of fileList) {
        if (studioFiles.length >= 12) { showToast('Massimo 12 allegati per invio.', 'warn'); break; }
        studioFiles.push(file);
    }
    renderAttachChips();
}

function appendStudioMessage(role, html) {
    const chat = $('studioChat');
    if (!chat) return null;
    $('studioHint')?.remove();
    const msg = document.createElement('div');
    msg.className = `msg msg-${role}`;
    msg.innerHTML = html;
    chat.appendChild(msg);
    chat.scrollTop = chat.scrollHeight;
    return msg;
}

async function sendStudio() {
    const promptEl = $('studioPrompt');
    const prompt = (promptEl.value || '').trim();
    if (!prompt && !studioFiles.length) { showToast('Scrivi un prompt o allega un file.', 'error'); return; }

    const target = $('studioTarget').value || 'clipboard';
    const targetName = $('studioTarget').selectedOptions[0]?.textContent || target;
    const fileNames = studioFiles.map(f => f.name);
    appendStudioMessage('user',
        `<div class="msg-bubble">${escapeHtml(prompt) || '<em>(solo allegati)</em>'}</div>` +
        (fileNames.length ? `<div class="msg-meta">${iconSvg('i-files')} ${fileNames.map(escapeHtml).join(', ')}</div>` : ''));

    const fd = new FormData();
    fd.append('prompt', prompt);
    fd.append('target', target);
    studioFiles.forEach(f => fd.append('files', f, f.name));

    const btn = $('btnStudioSend');
    btn.disabled = true;
    const waiting = appendStudioMessage('germano', `<div class="msg-bubble"><span class="spinner"></span> Protezione in corso…</div>`);
    promptEl.value = '';
    promptEl.style.height = 'auto';
    studioFiles = [];
    renderAttachChips();

    try {
        const r = await fetch('/api/studio/send', { method: 'POST', body: fd });
        const data = await r.json().catch(() => ({}));
        waiting?.remove();
        if (r.status === 503 || data.status === 'blocked') {
            appendStudioMessage('germano',
                `<div class="msg-bubble blocked">⛔ ${escapeHtml(data.message || 'Motore non attivo: nessun dato è uscito dal computer.')}</div>` +
                `<div class="msg-actions"><button type="button" class="btn btn-primary btn-sm" data-studio-start>Avvia motore</button></div>`);
            return;
        }
        if (!r.ok || data.status !== 'success') {
            appendStudioMessage('germano', `<div class="msg-bubble blocked">⚠️ ${escapeHtml(data.message || 'Protezione non riuscita.')}</div>`);
            return;
        }
        const labels = (data.labels || []).map(l => `<span class="msg-label">${escapeHtml(l)}</span>`).join('');
        const nonTextual = (data.attachments || []).filter(a => !a.textual).map(a => a.name);
        const note = nonTextual.length
            ? `<div class="msg-meta">ℹ️ Allegati non testuali (es. immagini): ${nonTextual.map(escapeHtml).join(', ')} — usa «Anonimizza file» per oscurarli.</div>` : '';
        const m = appendStudioMessage('germano',
            `<div class="msg-meta">🛡️ Protetto da Germano · ${plural(data.entity_count || 0, 'dato oscurato', 'dati oscurati')} · pronto per <strong>${escapeHtml(targetName)}</strong></div>` +
            (labels ? `<div class="msg-labels">${labels}</div>` : '') +
            `<div class="msg-bubble protected">${escapeHtml(data.composed || '')}</div>` +
            note +
            `<div class="msg-actions">` +
            `<button type="button" class="btn btn-secondary btn-sm" data-copy-protected>${iconSvg('i-copy')}Copia testo protetto</button>` +
            `</div>`);
        if (m) m._protected = data.composed || '';
    } catch (e) {
        waiting?.remove();
        appendStudioMessage('germano', `<div class="msg-bubble blocked">⚠️ Errore di comunicazione con Germano.</div>`);
    } finally {
        btn.disabled = false;
    }
}

// ------------------------------------------------------------------ CASSETTO CONFIGURAZIONE GRANULARE
function openConfigDrawer() {
    const body = $('configDrawerBody');
    const filters = document.querySelector('.view-filters');
    if (!body || !filters) return;
    configReturn = { parent: filters, nodes: Array.from(filters.children) };
    configReturn.nodes.forEach(n => body.appendChild(n));   // sposta i pannelli reali: stesse id, stessi eventi
    $('configScrim').hidden = false;
    $('configDrawer').hidden = false;
}

function closeConfigDrawer() {
    if (configReturn) {
        configReturn.nodes.forEach(n => configReturn.parent.appendChild(n));
        configReturn = null;
    }
    $('configScrim').hidden = true;
    $('configDrawer').hidden = true;
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
        auto_update: $('auto_update')?.checked ?? true,
        enable_tooltips: tooltipsEnabled
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
    tooltipsEnabled = cfg.enable_tooltips !== false;
    Tips.setEnabled(tooltipsEnabled);
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
        initialConfig = data;
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
// Fonte unica: download.germano.ai (version.json + installer in un solo file). L'installer scaricato si avvia con
// «Installa ora» o al successivo avvio di Germano: chiude Germano, lo aggiorna e lo riapre.
function updText(it, en) {
    return currentLang === 'en' ? en : it;
}

function renderUpdate(u) {
    if (!u) return;
    const pct = u.progress && u.progress.total ? Math.min(100, Math.round((100 * u.progress.done) / u.progress.total)) : 0;
    const li = u.last_install;
    let text = '', cls = 'banner-info', progress = false, download = false, install = false, ack = false;
    switch (u.state) {
        case 'available':
            if (u.manual) {   // macOS e Linux: il nuovo installer si scarica e si avvia a mano
                text = updText(`È disponibile la nuova versione ${u.latest} di Germano AI: scarica il nuovo installer da ${u.url || 'https://download.germano.ai/'} e aprilo con un doppio clic. Cartelle di lavoro, Vault e impostazioni restano intatti.`,
                               `Germano AI version ${u.latest} is available: download the new installer from ${u.url || 'https://download.germano.ai/'} and open it with a double click. Work folders, Vault and settings are kept.`);
            } else {
                text = updText(`È disponibile la nuova versione ${u.latest} di Germano AI.`,
                               `Germano AI version ${u.latest} is available.`);
                download = true;
            }
            break;
        case 'downloading':
            text = u.progress && u.progress.total
                ? updText(`Download dell'aggiornamento ${u.latest}: ${pct}% (${formatBytes(u.progress.done)} di ${formatBytes(u.progress.total)}).`,
                          `Downloading update ${u.latest}: ${pct}% (${formatBytes(u.progress.done)} of ${formatBytes(u.progress.total)}).`)
                : updText(`Download dell'aggiornamento ${u.latest}: ${formatBytes((u.progress || {}).done || 0)} scaricati.`,
                          `Downloading update ${u.latest}: ${formatBytes((u.progress || {}).done || 0)} downloaded.`);
            progress = true;
            break;
        case 'ready':
            if (li && li.status !== 'ok' && li.target === u.latest) {
                text = updText(`L'aggiornamento alla versione ${u.latest} non è stato completato (${li.error || 'interrotto'}): la versione in uso non è cambiata. Puoi riprovare con «Installa ora».`,
                               `The update to version ${u.latest} was not completed (${li.error || 'interrupted'}): the version in use has not changed. You can retry with “Install now”.`);
                cls = 'banner-danger';
            } else {
                text = updText(`La versione ${u.latest} è stata scaricata: verrà installata al prossimo avvio di Germano.`,
                               `Version ${u.latest} has been downloaded: it will be installed the next time Germano starts.`);
            }
            install = true;
            break;
        case 'installing':
            text = updText('Installazione dell\'aggiornamento in corso: Germano si chiude e si riaprirà da solo.',
                           'Installing the update: Germano closes and will reopen by itself.');
            updateInstalling = true;
            break;
        case 'error':
            text = updText(`Aggiornamento non riuscito: ${u.error || 'errore sconosciuto'}`,
                           `Update failed: ${u.error || 'unknown error'}`);
            cls = 'banner-danger';
            download = Boolean(u.latest);
            break;
        default:
            if (li && li.status === 'ok' && li.to === u.current) {
                text = updText(`Germano AI è stato aggiornato alla versione ${li.to}.`,
                               `Germano AI has been updated to version ${li.to}.`);
                cls = 'banner-ok';
                ack = true;
            } else if (li && li.status !== 'ok') {
                text = updText(`L'aggiornamento alla versione ${li.target} non è stato completato (${li.error || 'interrotto'}): la versione precedente è stata mantenuta.`,
                               `The update to version ${li.target} was not completed (${li.error || 'interrupted'}): the previous version was kept.`);
                cls = 'banner-danger';
                ack = true;
            }
    }
    const banner = $('updateBanner');
    banner.hidden = !text;
    banner.className = `banner ${cls}`;
    setText('updateBannerText', text);
    $('updateProgress').hidden = !progress;
    $('updateProgressBar').style.width = `${pct}%`;
    $('btnUpdateDownload').hidden = !download;
    setText('btnUpdateDownload', u.state === 'error' ? updText('Riprova', 'Retry') : updText('Scarica aggiornamento', 'Download update'));
    $('btnUpdateInstall').hidden = !install;
    $('btnUpdateAck').hidden = !ack;

    let info = updText(`Versione installata ${u.current}`, `Installed version ${u.current}`);
    if (u.checked_at) {
        info += updText(' · ultimo controllo ', ' · last check ') +
            new Date(u.checked_at * 1000).toLocaleString(currentLang === 'en' ? 'en-GB' : 'it-IT');
    }
    if (u.state === 'uptodate') info += updText(' · nessun aggiornamento disponibile', ' · no update available');
    if (u.online === false) {
        info += updText(' · Windows non segnala una connessione a Internet: nessun controllo eseguito',
                        ' · Windows reports no Internet connection: no check performed');
    }
    info += updText(' · fonte: ', ' · source: ') + (u.source || 'https://download.germano.ai/');
    setText('updateInfo', info);
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

async function installUpdate() {
    const p = (lastStatus && lastStatus.progress) || {};
    const pending = lastStatus && lastStatus.stats ? lastStatus.stats.pending : 0;
    let msg = updText('Installare ora l\'aggiornamento?\nGermano si chiude, l\'installer sostituisce il programma e lo riapre da solo (qualche minuto).\nCartelle di lavoro, archivio delle corrispondenze (Vault) e impostazioni non vengono toccati.',
                      'Install the update now?\nGermano closes, the installer replaces the program and reopens it by itself (a few minutes).\nWork folders, the mapping archive (Vault) and settings are not touched.');
    if (p.state === 'working' || pending > 0) {
        msg += updText('\n\nL\'elaborazione in corso verrà interrotta e ripresa automaticamente dopo l\'aggiornamento.',
                       '\n\nThe processing in progress will be interrupted and resumed automatically after the update.');
    }
    if (!confirm(msg)) return;
    updateInstalling = true;
    await updateAction('/api/update/install', updText('Installazione dell\'aggiornamento avviata: Germano si riaprirà da solo.',
                                                      'Update installation started: Germano will reopen by itself.'));
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
        if (sig !== filesSignature || Date.now() - lastFilesFetch > 10000) {
            filesSignature = sig;
            fetchFiles();
        }
    }
    renderJob(data);
    renderFileManager();
    if (!fmPaths) loadFmPaths();
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
    const ext = (String(name).split('.').pop() || '').toLowerCase();
    if (ext === 'pdf') return '📕';
    if (['doc', 'docx', 'docm', 'dotx', 'odt', 'rtf', 'txt', 'md'].includes(ext)) return '📝';
    if (['xls', 'xlsx', 'xlsm', 'xltx', 'ods', 'csv', 'tsv'].includes(ext)) return '📊';
    if (['ppt', 'pptx', 'pptm', 'potx', 'ppsx', 'odp'].includes(ext)) return '📽️';
    if (['png', 'jpg', 'jpeg', 'jfif', 'bmp', 'tif', 'tiff', 'webp', 'gif'].includes(ext)) return '🖼️';
    if (['eml', 'msg'].includes(ext)) return '✉️';
    if (['zip', 'p7m'].includes(ext)) return '🗜️';
    return '📄';
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

// ------------------------------------------------------------------ SUGGERIMENTI (TOOLTIPS)
// Un suggerimento per ogni elemento dell'interfaccia: [selettore, titolo, testo]. Titolo e testo possono essere
// funzioni (elemento, titolo_nativo) => stringa per i contenuti che dipendono dall'elemento. Hanno la precedenza
// gli attributi data-tip / data-tip-title; i "title" nativi diventano suggerimenti (mai due finestrelle insieme).
const NOTE_CINA = ' Server in Cina: i dati, anche se pseudonimizzati, escono dall\'Unione Europea verso un Paese senza ' +
    'decisione di adeguatezza. Verifica con il DPO prima di usarlo con dati della PA.';
const optTitle = (el) => (el.querySelector('.option-title')?.childNodes[0]?.textContent || '').trim();
const TIPS = [
    // --- intestazione
    ['.brand', 'Germano AI', 'Torna alla pagina iniziale della Dashboard.'],
    ['#btnAppBatch', '📂 Anonimizza file', 'Elaborazione in blocco di documenti (PDF, Word, Excel, immagini, e-mail): i risultati vanno nella cartella output.'],
    ['#btnAppStudio', '🧠 Studio AI', 'Scrivi un prompt e allega file: Germano li anonimizza prima dell\'invio a un\'AI e ti mostra esattamente cosa viene inviato.'],
    ['#btnModeSimple', 'Modalità Semplice', 'Solo le funzioni essenziali: aggiungi documenti, segui l\'avanzamento, scarica i risultati.'],
    ['#btnModeAdvanced', 'Modalità Avanzata', 'Aggiunge le schede Agenti AI e API, Filtri e modelli, Sistema e registro.'],
    ['#profilePill', 'Profilo di protezione', (el, n) => n || 'PA: tutti i modelli e tutte le categorie con sensibilità massima. PD: configurazione personalizzata.'],
    ['#engineStatusPill', 'Stato del motore', () => {
        let t = 'Il motore esegue i modelli di anonimizzazione. Verde = attivo, giallo = in avvio, grigio = in pausa, rosso = fermo per errore.';
        const eng = (lastStatus && lastStatus.running && lastStatus.engine) || null;
        if (eng && eng.mode === 'remote') t += ` Calcolo affidato al Germano Server «${eng.server_name || eng.server}» (${eng.server}).`;
        else if (eng && eng.device) t += ` Calcolo su ${String(eng.device).toUpperCase()}${eng.precision ? `, precisione ${String(eng.precision).toUpperCase()}` : ''}.`;
        return t;
    }],
    ['#modeChip', 'Modalità operativa', (el) => `Questo computer è in modalità «${(el.textContent || '').trim()}». Clicca per scegliere Standalone, Server, Client o Server + Client.`],
    ['#mainToggleBtn', 'Avvia / arresta il motore', 'Avvia il motore per elaborare i documenti e proteggere le richieste del Proxy. A motore fermo il Proxy blocca ogni richiesta: nessun dato esce in chiaro.'],
    ['#btnSettings', 'Impostazioni', 'Modalità operativa (Standalone, Server, Client) e preferenze dell\'interfaccia, compresi questi suggerimenti.'],
    ['#btnOpenGuide', 'Guida', 'Manuale d\'uso e documentazione tecnica, consultabili offline in una nuova scheda.'],
    ['.view-tab[data-view="work"]', 'Elaborazione', 'Cartelle di lavoro, aggiunta di documenti, avanzamento e risultati.'],
    ['.view-tab[data-view="agents"]', 'Agenti AI e API', 'Indirizzi del Proxy per Claude Code, Codex, Cursor e altri strumenti, servizi di destinazione ed esempi delle API REST.'],
    ['.view-tab[data-view="filters"]', 'Filtri e modelli', 'Profilo di protezione, sensibilità, modelli di analisi attivi e categorie di dati da oscurare.'],
    ['.view-tab[data-view="system"]', 'Sistema e registro', 'Rete e modalità operativa, esecuzione, cartelle, aggiornamenti, archivio delle corrispondenze e registro attività.'],
    // --- avvisi
    ['#retryEngineBtn', 'Riprova', 'Riavvia il motore dopo l\'errore indicato.'],
    ['#killOrphansBtn', 'Chiudi processi secondari', 'Chiude i processi del motore rimasti aperti da una sessione precedente e libera memoria.'],
    ['#btnUpdateDownload', 'Scarica aggiornamento', 'Scarica il nuovo installer da download.germano.ai, la fonte ufficiale degli aggiornamenti.'],
    ['#btnUpdateInstall', 'Installa ora', 'Chiude Germano, installa l\'aggiornamento e lo riapre. Cartelle, archivio e impostazioni non vengono toccati.'],
    ['#btnUpdateAck', 'Chiudi avviso', 'Nasconde questo messaggio.'],
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
    ['#btnOpenCurrentFolder', 'Apri cartella', 'Apre in Esplora file la cartella della scheda selezionata.'],
    ['#btnExportCsv', 'Esporta elenco', 'Scarica l\'elenco in formato CSV (si apre con Excel; separatore «;»).'],
    ['[data-action="open"]', 'Apri', 'Apre il documento con il programma predefinito di Windows.'],
    ['[data-action="reveal"]', 'Mostra nella cartella', 'Apre Esplora file con il documento selezionato.'],
    ['[data-action="retry"]', 'Rimetti in coda', 'Sposta il documento di nuovo nella cartella input per elaborarlo un\'altra volta.'],
    ['.row-actions a[download]', 'Scarica una copia', 'Scarica una copia del documento tramite il browser.'],
    // --- testo
    ['#manualInputText', 'Testo', 'Incolla un testo da anonimizzare, oppure la risposta di un\'AI con etichette come [PERSONA_1] da ripristinare.'],
    ['#anonymizeTextBtn', 'Anonimizza testo', 'Sostituisce i dati personali con etichette numerate, pronte da inviare a un servizio di AI.'],
    ['#manualOutputText', 'Risultato', 'Testo anonimizzato oppure ripristinato con i dati originali.'],
    ['#copyTextBtn', 'Copia risultato', 'Copia il risultato negli appunti.'],
    // --- agenti AI e API
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
    // --- filtri e modelli
    ['#btnPresetPA', 'Tutto attivo (profilo PA)', 'Attiva tutti i modelli e tutte le categorie con sensibilità massima.'],
    ['#btnPresetEssential', 'Solo dati essenziali', 'Oscura soltanto nomi, indirizzi, codici fiscali e partite IVA, email e telefoni.'],
    ['#btnPresetNone', 'Nessuna categoria', 'Disattiva tutte le categorie: non viene oscurato alcun dato.'],
    ['.field-range:has(#ai_threshold)', 'Sensibilità dei modelli', 'Soglia 0% = si oscura ogni possibile dato personale. Alzandola si riducono i falsi positivi, ma alcuni dati incerti possono restare in chiaro.'],
    ['#btnModelsAllOn', 'Attiva tutti i modelli', 'Usa tutti i modelli locali e le regole deterministiche.'],
    ['#btnModelsAllOff', 'Disattiva tutti i modelli', 'Nessun modello di analisi: verrebbe oscurato poco o nulla.'],
    ['.option:has(.model-check)', optTitle, (el) => `${(el.querySelector('.option-desc')?.textContent || '').trim()} Clicca per attivare o disattivare il modello.`],
    ['.option:has(.cat-check)', optTitle, (el) => `Etichetta usata nei documenti: ${(el.querySelector('.option-desc')?.textContent || '').trim()}. Clicca per oscurare o lasciare in chiaro questa categoria.`],
    // --- sistema
    ['#btnNetChange', 'Cambia modalità', 'Apre le Impostazioni per scegliere Standalone, Server, Client o Server + Client.'],
    ['#netSummary', 'Rete e modalità operativa', 'Stato attuale: ascolto sulla rete, collegamento al Germano Server e token per i client.'],
    ['.field:has(#hardware_mode)', 'Calcolo', 'Automatico usa una scheda video NVIDIA se presente, altrimenti il processore.'],
    ['.field:has(#precision)', 'Precisione del modello', 'FP32 è più veloce ma usa più memoria; BF16 la dimezza ed è più lento sui processori meno recenti. Vale dal prossimo avvio del motore.'],
    ['.field:has(#file_timeout_minutes)', 'Tempo massimo per documento', 'Oltre questo tempo il documento viene interrotto e spostato tra i non riusciti.'],
    ['.check-row:has(#anonymize_filenames)', 'Anonimizza i nomi dei file', 'Anche i nomi di file e cartelle in uscita vengono anonimizzati (es. CV_[PERSONA_1].pdf).'],
    ['.check-row:has(#check_updates)', 'Controllo aggiornamenti', 'Solo quando Windows segnala una connessione a Internet, Germano controlla se esiste una nuova versione.'],
    ['.check-row:has(#auto_update)', 'Aggiornamento automatico', 'Scarica gli aggiornamenti e li installa al successivo avvio di Germano.'],
    ['#btnUpdateCheck', 'Controlla ora', 'Controlla subito se è disponibile una nuova versione.'],
    ['#btnShowVault', 'Mostra archivio', 'Mostra le corrispondenze tra etichette e dati originali (dati in chiaro).'],
    ['#btnClearVault', 'Svuota archivio', 'Cancella tutte le corrispondenze: i documenti già anonimizzati non potranno più essere ripristinati.'],
    ['#sysUsagePill', 'Risorse del computer', 'Uso del processore e della memoria; a seguire la precisione del modello principale.'],
    ['#clearLogsBtn', 'Pulisci registro', 'Svuota il registro attività visualizzato.'],
    ['#logTerminal', 'Registro attività', 'Messaggi del motore in tempo reale: elaborazioni, avvisi ed errori.'],
    ['.folder-row [data-open-folder]', 'Apri', 'Apre la cartella in Esplora file di Windows.'],
    // --- Studio AI
    ['#studioTarget', 'Destinazione', 'Dove inviare il testo protetto: una CLI rilevata su questo computer oppure la copia negli appunti.'],
    ['#aiStrip', 'AI rilevate', 'AI e CLI trovate su questo computer leggendo il disco e le porte locali, senza avviare programmi né usare la rete.'],
    ['.ai-chip', (el) => (el.textContent || '').replace('✓', '').trim(), (el, n) => {
        if (!el.classList.contains('on')) return 'Non trovata su questo computer.';
        return n ? `Installata in: ${n}` : 'Installata sul computer che esegue Germano.';
    }],
    ['#btnStudioAttach', 'Allega file', 'Il testo degli allegati viene estratto e anonimizzato insieme al prompt (le immagini vanno elaborate con «Anonimizza file»).'],
    ['#studioPrompt', 'Prompt', 'Scrivi la richiesta. Invio = invia, Maiusc+Invio = a capo. Il testo viene protetto prima dell\'invio.'],
    ['#btnStudioSend', 'Proteggi e invia', 'Anonimizza prompt e allegati con il motore e mostra esattamente cosa riceverà l\'AI.'],
    ['#btnDetectAI', 'Rileva AI', 'Cerca di nuovo le AI e le CLI installate su questo computer.'],
    ['#btnGranularConfig', 'Configurazione granulare', 'Apre in un pannello laterale profilo di protezione, modelli e categorie di dati.'],
    ['[data-copy-protected]', 'Copia testo protetto', 'Copia negli appunti il testo anonimizzato, pronto da incollare nell\'AI.'],
    ['[data-studio-start]', 'Avvia motore', 'Avvia il motore: senza motore nessun dato viene inviato.'],
    ['.attach-chip button', 'Rimuovi allegato', 'Toglie questo file dall\'invio.'],
    ['#btnCloseConfig', 'Chiudi', 'Chiude il pannello di configurazione.'],
    // --- Impostazioni e modalità operativa
    ['#cardStandalone', 'Standalone', 'Disattiva Server e Client: Germano lavora solo su questo computer, senza alcuna attività di rete.'],
    ['#cardServer', 'Server', 'Al primo avvio Windows può chiedere di consentire Python sulle reti private: rispondi Consenti, altrimenti gli altri computer non raggiungono il server.'],
    ['#cardClient', 'Client', 'Serve il token che il Germano Server mostra nelle sue Impostazioni (sezione «Accesso dalla rete»).'],
    ['.field:has(#remoteServer)', 'Indirizzo del server', 'Lascia vuoto per la ricerca automatica in rete, oppure scrivi ad esempio http://192.168.1.10:8181.'],
    ['.field:has(#remoteToken)', 'Token del server', 'Lo trovi sul server in Impostazioni › Accesso dalla rete, oppure nella sua finestra all\'avvio.'],
    ['#btnFindServers', 'Cerca server in rete', 'Invia un breve messaggio di rilevamento (UDP 8182) sulla rete locale ed elenca i Germano Server che rispondono.'],
    ['.check-row:has(#clientFallback)', 'Ripiego sul motore locale', 'Se nessun server risponde, i modelli vengono caricati su questo computer (serve più memoria). Disattivato: i documenti restano in coda finché il server non risponde.'],
    ['.server-row', 'Usa questo server', 'Imposta questo Germano Server come destinazione della modalità Client.'],
    ['[data-regen-token]', 'Nuovo token', 'Genera un nuovo token: quello attuale smette subito di funzionare e va aggiornato su tutti i client.'],
    ['.toggle-row .switch', 'Suggerimenti', 'Attiva o disattiva queste spiegazioni al passaggio del mouse.'],
    ['#btnSaveSettings', 'Salva', 'Applica subito la modalità scelta: l\'ascolto sulla rete si accende o si spegne senza riavviare Germano.'],
    ['#btnCancelSettings', 'Annulla', 'Chiude senza modificare nulla.'],
    ['#btnCloseSettings', 'Chiudi', 'Chiude le Impostazioni.'],
];


const TIPS_EN = {
    // --- header
    '.brand': ['Germano AI', 'Return to the Dashboard home page.'],
    '#btnAppBatch': ['📂 Anonymize files', 'Batch processing of documents (PDF, Word, Excel, images, email): results are placed in the output folder.'],
    '#btnAppStudio': ['🧠 AI Studio', 'Write a prompt and attach files: Germano anonymizes them before sending to an AI and shows you exactly what is sent.'],
    '#btnModeSimple': ['Simple Mode', 'Only essential features: add documents, monitor progress, download ready files.'],
    '#btnModeAdvanced': ['Advanced Mode', 'Adds AI Agents & APIs, Filters & Models, System & Log tabs.'],
    '#profilePill': ['Protection profile', (el, n) => n || 'PA: all models and categories with maximum sensitivity. PD: custom configuration.'],
    '#engineStatusPill': ['Engine status', () => {
        let t = 'The engine runs anonymization models. Green = active, yellow = starting, gray = paused, red = error.';
        const eng = (lastStatus && lastStatus.running && lastStatus.engine) || null;
        if (eng && eng.mode === 'remote') t += ` Computing delegated to Germano Server «${eng.server_name || eng.server}» (${eng.server}).`;
        else if (eng && eng.device) t += ` Running on ${String(eng.device).toUpperCase()}${eng.precision ? `, precision ${String(eng.precision).toUpperCase()}` : ''}.`;
        return t;
    }],
    '#modeChip': ['Operating mode', (el) => `This computer is in «${(el.textContent || '').trim()}» mode. Click to choose Standalone, Server, Client, or Server + Client.`],
    '#mainToggleBtn': ['Start / stop engine', 'Starts the engine to process documents and protect Proxy requests. While stopped, the Proxy blocks all requests: zero data leaves in the clear.'],
    '#btnSettings': ['Settings', 'Operating mode (Standalone, Server, Client) and interface preferences, including these tooltips.'],
    '#btnOpenGuide': ['Guide', 'User manual and technical documentation, accessible offline in a new tab.'],
    '.view-tab[data-view="work"]': ['Processing', 'Work folders, document ingestion, live progress and results.'],
    '.view-tab[data-view="agents"]': ['AI Agents & APIs', 'Proxy endpoints for Claude Code, Codex, Cursor and other tools, upstream targets and REST API examples.'],
    '.view-tab[data-view="filters"]': ['Filters & models', 'Protection profile, sensitivity threshold, active analysis models and masked categories.'],
    '.view-tab[data-view="system"]': ['System & log', 'Network and operating mode, execution runtime, folders, updates, mappings vault and activity log.'],
    // --- banners
    '#retryEngineBtn': ['Retry', 'Restarts the engine after the indicated error.'],
    '#killOrphansBtn': ['Close leftover processes', 'Closes leftover engine processes from previous sessions and frees RAM.'],
    '#btnUpdateDownload': ['Download update', 'Downloads the new installer from download.germano.ai, the official update source.'],
    '#btnUpdateInstall': ['Install now', 'Closes Germano, installs the update and reopens. Folders, vault and settings remain intact.'],
    '#btnUpdateAck': ['Dismiss alert', 'Hides this notification.'],
    // --- folders & stats
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
    // --- documents table
    '.tab[data-folder="output"]': ['Ready', 'Anonymized (or restored) documents available in output folder.'],
    '.tab[data-folder="input"]': ['Pending', 'Documents in input folder, queued or currently processing.'],
    '.tab[data-folder="failed"]': ['Failed', 'Unprocessed documents with reason and retry button.'],
    '.tab[data-folder="processed"]': ['Originals', 'Archived original documents after processing.'],
    '#fileFilter': ['Filter', 'Filter documents by name, path or failure reason.'],
    '#btnRetryAll': ['Retry all', 'Moves all failed documents back to input folder.'],
    '#btnOpenCurrentFolder': ['Open folder', 'Opens File Explorer for the currently selected tab.'],
    '#btnExportCsv': ['Export list', 'Downloads document list as CSV (Excel compatible).'],
    '[data-action="open"]': ['Open', 'Opens document with Windows default application.'],
    '[data-action="reveal"]': ['Show in folder', 'Opens File Explorer with document highlighted.'],
    '[data-action="retry"]': ['Retry', 'Moves document back to input folder for re-processing.'],
    '.row-actions a[download]': ['Download copy', 'Downloads a copy of the document via browser.'],
    // --- text tab
    '#manualInputText': ['Text', 'Paste text to anonymize, or AI response with tags like [PERSON_1] to restore.'],
    '#anonymizeTextBtn': ['Anonymize text', 'Replaces personal data with numbered tags, ready for AI services.'],
    '#deanonymizeTextBtn': ['Restore text', 'Restores real data into AI responses containing numbered tags.'],
    '#copyManualOutputBtn': ['Copy text', 'Copies result to clipboard.'],
    // --- AI agents & API
    '.preset-chip': ['AI Preset', (el) => `Configures Proxy port and model settings for ${(el.textContent || '').trim()}.`],
    '#proxyPort': ['Proxy port', 'Local port for HTTP proxy (default 8181).'],
    '#customUpstreamUrl': ['Custom upstream URL', 'Base URL of target AI service if not using default.'],
    '#saveProxyBtn': ['Save proxy settings', 'Applies proxy configuration changes.'],
    '#copyApiKeyBtn': ['Copy API key', 'Copies dummy API key for local proxy auth.'],
    // --- settings & operational mode
    '#cardStandalone': ['Standalone', 'Disables Server and Client: Germano runs strictly locally with zero network activity.'],
    '#cardServer': ['Server', 'Listens on local network and provides anonymization engine to other PCs with token authentication.'],
    '#cardClient': ['Client', 'Delegates compute to a remote Germano Server while keeping Vault and files locally.'],
    '.field:has(#remoteServer)': ['Server address', 'Leave blank for automatic LAN discovery, or enter IP (e.g. http://192.168.1.10:8181).'],
    '.field:has(#remoteToken)': ['Server token', 'Found on the server under Settings › Network Access.'],
    '#btnFindServers': ['Scan network for servers', 'Sends UDP discovery beacon (port 8182) and lists available Germano Servers.'],
    '.check-row:has(#clientFallback)': ['Fallback to local engine', 'If no remote server responds, loads models locally.'],
    '.server-row': ['Use this server', 'Sets this Germano Server as the remote compute target.'],
    '[data-regen-token]': ['Generate new token', 'Generates a new security token, revoking the previous one.'],
    '.toggle-row .switch': ['Tooltips', 'Toggle hover tooltips across the entire interface.'],
    '#btnSaveSettings': ['Save', 'Immediately applies mode settings without restarting Germano.'],
    '#btnCancelSettings': ['Cancel', 'Closes without making changes.'],
    '#btnCloseSettings': ['Close', 'Closes Settings modal.'],
    // --- Studio AI
    '#studioTarget': ['Destination', 'Target AI: detected local CLI or copy to clipboard.'],
    '#aiStrip': ['Detected AIs', 'AIs and CLIs found on this machine by filesystem scan, safely offline.'],
    '#btnStudioAttach': ['Attach file', 'Extracts and anonymizes attachments alongside the prompt.'],
    '#studioPrompt': ['Prompt', 'Type request. Enter = send, Shift+Enter = newline. Protected before sending.'],
    '#btnStudioSend': ['Protect & send', 'Anonymizes prompt and attachments with local engine.'],
    '#btnDetectAI': ['Detect AI', 'Scans again for installed AIs and CLIs on this PC.'],
    '#btnGranularConfig': ['Granular Settings', 'Opens sidebar for models, threshold and PII categories.'],
    '[data-copy-protected]': ['Copy protected text', 'Copies anonymized text to clipboard ready for AI.'],
    '[data-studio-start]': ['Start engine', 'Starts engine: required before sending prompts.'],
    '.attach-chip button': ['Remove attachment', 'Removes this file from submission.'],
    '#btnCloseConfig': ['Close', 'Closes configuration panel.']
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
        box.innerHTML = '<span class="muted">Dopo il salvataggio Germano si mette in ascolto sulla rete e qui compaiono gli ' +
            'indirizzi e il token da comunicare ai client. Al primo avvio Windows può chiedere di consentire Python sulle ' +
            'reti private: rispondi «Consenti».</span>';
        return;
    }
    const ips = (s.ips || []).map(ip => `<code>http://${escapeHtml(ip)}:${escapeHtml(s.port)}</code>`).join(' ');
    box.innerHTML = `
        <div><strong>In ascolto sulla rete</strong> · ${ips || '<span class="muted">nessun indirizzo IPv4 trovato</span>'}</div>
        <div class="copy-line">Token per i client: <code>${escapeHtml(s.token)}</code>${copyButton(s.token, 'Copia token')}
            <button type="button" class="btn btn-secondary btn-sm" data-regen-token>Nuovo token</button></div>
        <div class="muted">Rilevamento automatico: ${s.discovery ? `attivo (UDP ${escapeHtml(s.discovery_port)})` : 'non attivo'}.
            I client Germano inseriscono il token nelle loro Impostazioni; le CLI possono usare
            <code>http://&lt;IP&gt;:${escapeHtml(s.port)}/g/&lt;token&gt;/v1</code>.</div>`;
}

async function openSettings(opts = {}) {
    settingsWelcome = Boolean(opts.welcome);
    settingsDone = false;
    const modal = $('settingsModal');
    modal.classList.toggle('is-welcome', settingsWelcome);
    setText('settingsTitle', settingsWelcome ? '👋 Benvenuto in Germano AI' : 'Impostazioni');
    setText('settingsSub', settingsWelcome
        ? 'Prima di iniziare scegli come usare Germano su questo computer. Nel dubbio lascia Standalone: tutto resta su questo PC.'
        : 'Modalità operativa di questo computer e preferenze dell\'interfaccia.');
    setText('btnSaveSettings', settingsWelcome ? 'Conferma e inizia' : 'Salva');
    $('btnCancelSettings').hidden = settingsWelcome;
    setSettingsMsg('');
    $('enable_tooltips').checked = tooltipsEnabled;
    $('serverList').innerHTML = '';
    let remoteViewer = '';   // Dashboard aperta da un altro computer: la modalità si sceglie solo sul server
    try {
        const { ok, status, data } = await fetchJson('/api/mode', { cache: 'no-store' });
        if (ok) modeState = data;
        else if (status === 403) remoteViewer = data.error || 'Le Impostazioni si cambiano solo dal computer su cui è installato Germano.';
    } catch (e) { /* si usa l'ultimo stato noto */ }
    const st = modeState || {};
    const cl = st.client || {};
    setModeChecks(st.saved || 'standalone');
    $('remoteServer').value = cl.remote_server || '';
    $('remoteToken').value = '';
    $('remoteToken').placeholder = cl.token_set
        ? '•••••••• già impostato (lascia vuoto per non cambiarlo)'
        : 'Lo mostra il server nelle sue Impostazioni';
    $('clientFallback').checked = cl.fallback_local !== false;
    $('shareAiTools').checked = Boolean((st.server || {}).share_ai_tools);
    const locked = Boolean(st.locked) || Boolean(remoteViewer);
    ['optStandalone', 'optServer', 'optClient', 'remoteServer', 'remoteToken', 'clientFallback', 'btnFindServers', 'shareAiTools']
        .forEach(id => { if ($(id)) $(id).disabled = locked; });
    $('enable_tooltips').disabled = Boolean(remoteViewer);
    $('btnSaveSettings').disabled = Boolean(remoteViewer);
    document.querySelectorAll('.mode-card').forEach(c => c.classList.toggle('is-disabled', locked));
    if (remoteViewer) {
        setSettingsMsg(remoteViewer, true);
    } else if (st.locked) {
        setSettingsMsg('Modalità bloccata dall\'amministratore (lock_settings): si possono cambiare solo le preferenze dell\'interfaccia.');
    } else if (st.forced_by) {
        setSettingsMsg(`Per questo avvio la modalità è «${MODE_TEXT[st.effective] || st.effective}», impostata da ` +
            `${FORCED_TEXT[st.forced_by] || st.forced_by}: la scelta salvata qui vale dai prossimi avvii senza quella variabile.`);
    }
    Tips.hide();
    $('settingsScrim').hidden = false;
    modal.hidden = false;
    setTimeout(() => (settingsWelcome ? $('btnSaveSettings') : $('btnCloseSettings')).focus(), 30);
}

function hideSettings() {
    $('settingsModal').hidden = true;
    $('settingsScrim').hidden = true;
    settingsWelcome = false;
    settingsDone = false;
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
        if (($('remoteToken').value || '').trim()) body.remote_token = $('remoteToken').value.trim();
        body.client_fallback_local = $('clientFallback').checked;
    }
    if (!keepMode && mode.includes('server')) body.share_ai_tools = $('shareAiTools').checked;
    const btn = $('btnSaveSettings');
    btn.disabled = true;
    try {
        const { ok, status, data } = await postJson('/api/mode', body);
        if (status === 403 && data.status === 'locked') {
            applyTooltipsPref(body.enable_tooltips);   // le preferenze dell'interfaccia vengono comunque salvate
            setSettingsMsg(data.message, true);
            return;
        }
        if (!ok) {
            setSettingsMsg(data.message || data.error || 'Impossibile salvare le impostazioni.', true);
            return;
        }
        modeState = data;
        applyTooltipsPref(body.enable_tooltips);
        if (initialConfig) initialConfig.first_run_done = true;
        const label = MODE_TEXT[data.saved] || data.saved;
        let msg = 'Impostazioni salvate.';
        if (settingsWelcome) msg = `Modalità ${label} confermata.`;
        else if (data.saved !== (st.saved || 'standalone')) msg = `Modalità ${label} attivata.`;
        if (data.forced_by && data.effective !== data.saved) {
            msg += ` Per questo avvio resta «${MODE_TEXT[data.effective] || data.effective}» (${FORCED_TEXT[data.forced_by] || data.forced_by}).`;
        }
        if (data.server && data.server.listening) msg += ' Germano è in ascolto sulla rete locale.';
        if (data.engine_action === 'restart') msg += ' Il motore si riavvia per applicarla.';
        if (data.engine_action === 'start') msg += ' Avvio del motore in corso.';
        (data.notes || []).forEach(n => showToast(n, 'warn', 9000));
        pollStatus();
        renderNetSummary();
        if (!keepMode && String(data.saved).includes('server') && data.server && data.server.listening) {
            // La finestra resta aperta: l'amministratore deve vedere indirizzi e token da dare ai client.
            settingsWelcome = false;
            settingsDone = true;
            $('settingsModal').classList.remove('is-welcome');
            $('btnCancelSettings').hidden = true;
            setText('btnSaveSettings', 'Fatto');
            renderServerInfo();
            setSettingsMsg(`✅ ${msg} Comunica ai client l'indirizzo e il token qui sopra.`);
            return;
        }
        hideSettings();
        showToast(msg, 'success', 5000);
    } catch (e) {
        setSettingsMsg('Germano non risponde: impossibile salvare.', true);
    } finally {
        btn.disabled = false;
    }
}

async function findServers() {
    const list = $('serverList');
    const btn = $('btnFindServers');
    list.innerHTML = '<div class="server-empty">Ricerca in corso…</div>';
    btn.disabled = true;
    try {
        const { ok, data } = await fetchJson('/api/remote/servers', { cache: 'no-store' });
        const servers = (ok && data.servers) || [];
        list.innerHTML = servers.length ? servers.map(s => {
            const engine = s.engine_shared ? (s.engine_ready ? '🟢 motore pronto' : '🟡 motore in avvio') : '⚪ motore non condiviso';
            const dev = s.device ? ` · ${escapeHtml(String(s.device).toUpperCase())}` : '';
            return `<button type="button" class="server-row" data-server-url="${escapeHtml(s.url)}">
                <span class="server-name">${escapeHtml(s.name || s.url)}</span><code>${escapeHtml(s.url)}</code>
                <span class="server-meta">${engine}${dev} · v${escapeHtml(s.version || '?')}</span></button>`;
        }).join('') : '<div class="server-empty">Nessun Germano Server trovato sulla rete locale. Sul server scegli la modalità ' +
            'Server nelle Impostazioni e verifica che il firewall di Windows consenta le reti private.</div>';
    } catch (e) {
        list.innerHTML = '<div class="server-empty">Ricerca non riuscita: Germano non risponde.</div>';
    } finally {
        btn.disabled = Boolean(modeState && modeState.locked);
    }
}

async function regenToken() {
    if (!confirm('Generare un nuovo token?\nIl token attuale smette subito di funzionare e va inserito di nuovo su tutti i client.')) return;
    try {
        const { ok, data } = await postJson('/api/mode/token', {});
        if (ok && data.token) {
            if (modeState && modeState.server) modeState.server.token = data.token;
            renderServerInfo();
            renderNetSummary();
            showToast('Nuovo token generato: aggiornalo sui client.', 'success');
        } else {
            showToast(data.message || 'Operazione non riuscita.', 'error');
        }
    } catch (e) {
        showToast('Germano non risponde.', 'error');
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
            if (eng.ok === false) { text += ' (non raggiungibile)'; cls.push('is-warn'); }
        } else if (eng.fallback) {
            text += ' · motore locale';
            cls.push('is-warn');
        }
    }
    chip.className = ['mode-chip', ...cls].join(' ');
    setText('modeChipText', text);
    chip.dataset.mode = eff;
}

async function renderNetSummary() {
    const box = $('netSummary');
    if (!box || currentUiMode !== 'advanced' || currentView !== 'system') return;
    try {
        const { ok, data } = await fetchJson('/api/mode', { cache: 'no-store' });
        if (!ok) return;
        modeState = data;
        const s = data.server || {};
        const c = data.client || {};
        const eng = data.engine || {};
        let clientValue = 'disattivato';
        let clientSub = 'il calcolo avviene su questo computer';
        if (c.enabled) {
            if (eng.mode === 'remote' && eng.ok === false) {
                clientValue = `${eng.server_name || eng.server} non raggiungibile`;
                clientSub = `${eng.server} · nessun dato inviato, i documenti restano in coda`;
            } else if (eng.mode === 'remote') {
                clientValue = `collegato a ${eng.server_name || eng.server}`;
                clientSub = `${eng.server} · ${eng.latency_ms ?? '?'} ms`;
            } else if (data.engine_running && eng.fallback) {
                clientValue = 'motore locale (nessun server)';
                clientSub = eng.fallback;
            } else {
                clientValue = data.engine_running ? 'collegamento in corso…' : 'motore non avviato';
                clientSub = c.remote_server || 'ricerca automatica in rete';
            }
        }
        const items = [
            ['Modalità', MODE_TEXT[data.effective] || data.effective,
                data.forced_by ? `impostata da ${FORCED_TEXT[data.forced_by] || data.forced_by} per questo avvio` : 'modificabile in qualsiasi momento'],
            ['Server', s.enabled ? (s.listening ? 'in ascolto sulla rete' : 'non in ascolto') : 'disattivato',
                s.enabled && s.listening ? (s.ips || []).map(ip => `${ip}:${s.port}`).join(', ') || 'nessun IPv4' : 'nessuna porta aperta verso la rete'],
            ['Client', clientValue, clientSub],
            ['Token per i client', s.enabled && s.token ? `${s.token.slice(0, 6)}…` : '—',
                s.enabled ? 'completo in Impostazioni › Accesso dalla rete' : 'serve solo in modalità Server'],
        ];
        box.innerHTML = items.map(([l, v, sub]) => `<div class="net-item"><div class="net-item-label">${escapeHtml(l)}</div>` +
            `<div class="net-item-value">${escapeHtml(v)}</div><div class="net-item-sub">${escapeHtml(sub)}</div></div>`).join('');
    } catch (e) { /* Germano non risponde: gestito da pollStatus */ }
}

// ------------------------------------------------------------------ AVVIO PAGINA

// ------------------------------------------------------------------ INTERNAZIONALIZZAZIONE (i18n)
let currentLang = 'it';
function getLang() { return currentLang; }

function setLanguage(lang) {
    currentLang = (lang === 'en') ? 'en' : 'it';
    try { localStorage.setItem('germano_lang', currentLang); } catch (e) {}
    
    // Aggiorna attributo documento
    document.documentElement.lang = currentLang;

    // Aggiorna stato pulsanti bandierina
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

    // I collegamenti alla Guida aprono la stessa lingua (la Guida legge ?lang e condivide germano_lang)
    document.querySelectorAll('a[href^="/guide"]').forEach(a => {
        const raw = (a.getAttribute('href') || '/guide').split('?')[0];
        const [path, hash] = raw.split('#');
        a.setAttribute('href', `${path}?lang=${currentLang}` + (hash ? `#${hash}` : ''));
    });

    // Aggiorna elementi dinamici
    if (typeof lastStatus !== 'undefined' && lastStatus) {
        try { renderStatus(lastStatus); } catch (e) {}
        try { renderJob(lastStatus); } catch (e) {}
    }
    try { renderFileManager(true); } catch (e) {}
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

document.addEventListener('DOMContentLoaded', async () => {
    initLanguage();
    Tips.init();
    await loadInitialSettings();
    Tips.setEnabled(tooltipsEnabled);
    let savedApp = 'batch';
    try { savedApp = localStorage.getItem('germano_app') || 'batch'; } catch (e) { /* archivio non disponibile */ }
    applyAppMode(savedApp, false);
    renderAgents();
    await pollStatus();
    await fetchFiles();

    // Impostazioni: modalità operativa (Standalone / Server / Client) e preferenze dell'interfaccia
    $('optStandalone').addEventListener('change', () => onModeCheck('standalone'));
    $('optServer').addEventListener('change', () => onModeCheck('server'));
    $('optClient').addEventListener('change', () => onModeCheck('client'));
    $('btnFindServers').addEventListener('click', findServers);
    ['input', 'change'].forEach(ev => $('settingsModal').addEventListener(ev, () => {
        if (!settingsDone) return;   // modificata di nuovo dopo il salvataggio: «Fatto» torna «Salva»
        settingsDone = false;
        setText('btnSaveSettings', 'Salva');
    }));
    $('btnSaveSettings').addEventListener('click', () => (settingsDone ? hideSettings() : saveSettings()));
    $('btnCancelSettings').addEventListener('click', hideSettings);
    $('btnCloseSettings').addEventListener('click', dismissSettings);
    $('settingsScrim').addEventListener('click', dismissSettings);
    $('serverList').addEventListener('click', (e) => {
        const row = e.target.closest('[data-server-url]');
        if (!row) return;
        $('remoteServer').value = row.dataset.serverUrl;
        $('serverList').querySelectorAll('.server-row').forEach(r => r.classList.toggle('is-selected', r === row));
        $('remoteToken').focus();
        const tokenSet = Boolean(modeState && modeState.client && modeState.client.token_set);
        setSettingsMsg(`Server selezionato: ${row.dataset.serverUrl}. ` + (tokenSet
            ? 'Salva per usarlo (scrivi il token solo se è diverso da quello già impostato).'
            : 'Inserisci il suo token e salva.'));
    });
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
    // Prima apertura: la finestra fa da benvenuto e chiede la modalità operativa (predefinita Standalone)
    if (initialConfig && initialConfig.first_run_done !== true) openSettings({ welcome: true });

    $('btnModeSimple').addEventListener('click', () => applyUiMode('simple', true));
    $('btnModeAdvanced').addEventListener('click', () => applyUiMode('advanced', true));
    document.querySelectorAll('.view-tab').forEach(t => t.addEventListener('click', () => applyView(t.dataset.view)));

    // Commutatore Anonimizza file / Studio AI
    $('btnAppBatch').addEventListener('click', () => applyAppMode('batch', true));
    $('btnAppStudio').addEventListener('click', () => applyAppMode('studio', true));

    // Studio AI: rilevamento, destinazione, allegati, invio
    $('btnDetectAI').addEventListener('click', () => detectAI(true));
    $('studioTarget').addEventListener('change', updateStudioTargetBadge);
    $('btnStudioAttach').addEventListener('click', () => $('studioFileInput').click());
    $('studioFileInput').addEventListener('change', (e) => { addStudioFiles(e.target.files); e.target.value = ''; });
    $('attachChips').addEventListener('click', (e) => {
        const rm = e.target.closest('[data-remove-attach]');
        if (rm) { studioFiles.splice(parseInt(rm.dataset.removeAttach, 10), 1); renderAttachChips(); }
    });
    $('studioComposer').addEventListener('submit', (e) => { e.preventDefault(); sendStudio(); });
    const promptBox = $('studioPrompt');
    promptBox.addEventListener('input', () => { promptBox.style.height = 'auto'; promptBox.style.height = Math.min(200, promptBox.scrollHeight) + 'px'; });
    promptBox.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendStudio(); }
    });
    $('studioChat').addEventListener('click', (e) => {
        const copyBtn = e.target.closest('[data-copy-protected]');
        if (copyBtn) { const m = copyBtn.closest('.msg'); if (m && m._protected) copyText(m._protected); return; }
        if (e.target.closest('[data-studio-start]')) { startEngine().then(pollStatus); showToast('Avvio del motore in corso…', 'info'); }
    });

    // Preset rapidi per target_api_url (OpenAI, DeepSeek, Kimi, Qwen, Ollama)
    document.querySelectorAll('.preset-target').forEach(btn => {
        btn.addEventListener('click', () => {
            const input = $('target_api_url');
            if (input && btn.dataset.url) {
                input.value = btn.dataset.url;
                input.dispatchEvent(new Event('change', { bubbles: true }));
                showToast(`Servizio impostato su ${btn.textContent}`, 'success', 2500);
            }
        });
    });

    // Cassetto «Configurazione Granulare»
    $('btnGranularConfig').addEventListener('click', openConfigDrawer);
    $('btnCloseConfig').addEventListener('click', closeConfigDrawer);
    $('configScrim').addEventListener('click', closeConfigDrawer);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('configDrawer').hidden) closeConfigDrawer(); });

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

    // Pulsanti generici: Impostazioni, apertura cartelle, nuovo token e copia negli appunti
    document.addEventListener('click', (e) => {
        if (e.target.closest('[data-open-settings]')) {
            openSettings();
            return;
        }
        if (e.target.closest('[data-regen-token]')) {
            regenToken();
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
    // un file lasciato fuori dal riquadro non deve essere aperto dal browser
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
    loadFmPaths();

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
    $('btnUpdateDownload').addEventListener('click', () => updateAction('/api/update/download', updText('Download dell\'aggiornamento avviato.', 'Update download started.')));
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
    setInterval(renderNetSummary, 5000);   // aggiorna solo se è aperta la scheda Sistema
});
