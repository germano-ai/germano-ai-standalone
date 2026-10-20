let currentUiMode = 'simple';
let currentComplianceMode = 'PA';
let currentStatus = 'stopped';
let activeFileTab = 'output';
let cachedFiles = { input: [], output: [], processed: [], failed: [] };

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

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.25s ease';
        setTimeout(() => toast.remove(), 250);
    }, 3200);
}

function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatTime(epoch) {
    if (!epoch) return '';
    const d = new Date(epoch * 1000);
    return d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function applyUiMode(mode, save = true) {
    currentUiMode = (mode === 'advanced') ? 'advanced' : 'simple';
    document.body.classList.toggle('mode-simple', currentUiMode === 'simple');
    document.body.classList.toggle('mode-advanced', currentUiMode === 'advanced');

    const slider = document.getElementById('modeSlider');
    const btnSimple = document.getElementById('btnModeSimple');
    const btnAdv = document.getElementById('btnModeAdvanced');
    if (slider) slider.dataset.mode = currentUiMode;
    if (btnSimple) btnSimple.classList.toggle('active', currentUiMode === 'simple');
    if (btnAdv) btnAdv.classList.toggle('active', currentUiMode === 'advanced');

    if (currentUiMode === 'simple') {
        activeFileTab = 'output';
        renderFileList();
    }
    if (save) {
        persistSettings(false);
    }
}

function applyDeanonSwitchState(enabled) {
    const heroBar = document.getElementById('deanonHeroBar');
    const badge = document.getElementById('deanonStateBadge');
    const vaultPill = document.getElementById('vaultInfoPill');

    if (heroBar) heroBar.classList.toggle('off', !enabled);
    if (badge) badge.textContent = enabled ? 'AUTOMATICO ATTIVO' : 'DISATTIVATO';
    if (vaultPill) vaultPill.style.display = enabled ? 'inline-block' : 'none';
}

function updateThresholdBadge(val) {
    const badge = document.getElementById('thresholdValue');
    if (!badge) return;
    const pct = Math.round(parseFloat(val || 0) * 100);
    badge.textContent = pct === 0 ? 'Massima Sicurezza (0%)' : `Soglia: ${pct}%`;
}

function updatePresetButtonsHighlight() {
    const allModelsChecked = ALL_MODEL_IDS.every(id => {
        const el = document.getElementById(id);
        return el && el.checked;
    });
    const noModelsChecked = ALL_MODEL_IDS.every(id => {
        const el = document.getElementById(id);
        return el && !el.checked;
    });
    const btnModelsOn = document.getElementById('btnModelsAllOn');
    const btnModelsOff = document.getElementById('btnModelsAllOff');
    if (btnModelsOn) btnModelsOn.classList.toggle('active', allModelsChecked);
    if (btnModelsOff) btnModelsOff.classList.toggle('active', noModelsChecked);

    const allCatsChecked = ALL_CATEGORY_IDS.every(id => {
        const el = document.getElementById(id);
        return el && el.checked;
    });
    const noCatsChecked = ALL_CATEGORY_IDS.every(id => {
        const el = document.getElementById(id);
        return el && !el.checked;
    });
    const btnPA = document.getElementById('btnPresetPA');
    const btnNone = document.getElementById('btnPresetNone');
    if (btnPA) btnPA.classList.toggle('active', allModelsChecked && allCatsChecked && currentComplianceMode === 'PA');
    if (btnNone) btnNone.classList.toggle('active', noCatsChecked);
}

function gatherSettings() {
    const out = {
        ui_mode: currentUiMode,
        compliance_mode: currentComplianceMode,
        enable_deanonymize: document.getElementById('enable_deanonymize')?.checked ?? true,
        target_api_url: (document.getElementById('target_api_url')?.value || '').trim(),
        ai_threshold: parseFloat(document.getElementById('ai_threshold')?.value || '0') || 0.0,
        hardware_mode: document.getElementById('hardware_mode')?.value || 'gpu_fallback'
    };
    ALL_MODEL_IDS.forEach(k => {
        out[k] = document.getElementById(k)?.checked ?? true;
    });
    ALL_CATEGORY_IDS.forEach(k => {
        out[k] = document.getElementById(k)?.checked ?? true;
    });
    return out;
}

async function persistSettings(notify = true) {
    try {
        const settings = gatherSettings();
        const r = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ settings })
        });
        if (r.ok && notify) {
            showToast('Impostazioni aggiornate.', 'success');
        }
    } catch (e) {
        console.error('Errore salvataggio impostazioni:', e);
    }
}

async function loadInitialSettings() {
    try {
        const r = await fetch('/api/settings');
        if (!r.ok) return;
        const cfg = await r.json();

        currentComplianceMode = cfg.compliance_mode || 'PA';
        const deanonEl = document.getElementById('enable_deanonymize');
        if (deanonEl) deanonEl.checked = cfg.enable_deanonymize !== false;
        applyDeanonSwitchState(cfg.enable_deanonymize !== false);

        const boolKeys = [...ALL_MODEL_IDS, ...ALL_CATEGORY_IDS];
        boolKeys.forEach(k => {
            const el = document.getElementById(k);
            if (el && cfg[k] !== undefined) el.checked = Boolean(cfg[k]);
        });

        if (cfg.ai_threshold !== undefined) {
            const th = document.getElementById('ai_threshold');
            if (th) th.value = cfg.ai_threshold;
            updateThresholdBadge(cfg.ai_threshold);
        }
        if (cfg.hardware_mode) {
            const hw = document.getElementById('hardware_mode');
            if (hw) hw.value = cfg.hardware_mode;
        }
        if (cfg.target_api_url) {
            const tu = document.getElementById('target_api_url');
            if (tu) tu.value = cfg.target_api_url;
        }

        applyUiMode(cfg.ui_mode || 'simple', false);
        updatePresetButtonsHighlight();
    } catch (e) {
        console.error('Errore caricamento impostazioni:', e);
    }
}

async function openLocalFolder(folderName) {
    try {
        const r = await fetch('/api/open_folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder: folderName })
        });
        if (!r.ok) showToast('Impossibile aprire la cartella.', 'error');
    } catch (e) {
        showToast('Errore apertura cartella.', 'error');
    }
}
window.openLocalFolder = openLocalFolder;

async function ensureEngineRunning() {
    if (currentStatus === 'running' || currentStatus === 'loading_models') {
        return true;
    }
    showToast('Avvio automatico di Germano in corso...', 'info');
    try {
        await fetch('/api/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ settings: gatherSettings() })
        });
        await pollStatus();
        return true;
    } catch (e) {
        return false;
    }
}

async function uploadFilesToProtect(fileList) {
    if (!fileList || fileList.length === 0) return;
    const formData = new FormData();
    for (let i = 0; i < fileList.length; i++) {
        formData.append('files', fileList[i]);
    }
    try {
        const r = await fetch('/api/upload_files', { method: 'POST', body: formData });
        const data = await r.json();
        if (r.ok && data.status === 'success') {
            if (data.auto_restored_files && data.auto_restored_files.length > 0) {
                showToast(`🔄 Rilevato file di ritorno dall'AI: dati veri rimessi a posto in automatico!`, 'success');
                data.auto_restored_files.forEach(f => {
                    const a = document.createElement('a');
                    a.href = f.download_url;
                    a.download = f.name;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                });
            }
            if (data.saved_count > 0) {
                showToast(`${data.saved_count} documento/i caricato/i per la protezione!`, 'success');
                await ensureEngineRunning();
            }
            fetchRecentFiles();
            pollStatus();
        } else {
            showToast(data.message || 'Errore durante il caricamento.', 'error');
        }
    } catch (e) {
        showToast('Errore di connessione durante il caricamento.', 'error');
    }
}

function renderFileList() {
    const container = document.getElementById('fileListContainer');
    if (!container) return;
    const folderToRender = (currentUiMode === 'simple') ? 'output' : activeFileTab;
    const list = cachedFiles[folderToRender] || [];

    if (list.length === 0) {
        const emptyMessages = {
            output: 'Nessun documento pronto. Trascina un file nel riquadro "Passo 1" qui sopra per iniziare!',
            input: 'Nessun documento in attesa di elaborazione.',
            processed: 'Nessun documento originale archiviato.',
            failed: 'Nessun documento con errori.'
        };
        container.innerHTML = `<div class="empty-files-msg">${emptyMessages[folderToRender] || 'Nessun file.'}</div>`;
        return;
    }

    container.innerHTML = list.map(item => {
        const isRestored = item.name.startsWith('ripristinato_');
        const badgeHtml = isRestored
            ? `<span style="background:rgba(139,92,246,0.22);color:#c4b5fd;padding:2px 8px;border-radius:99px;font-size:0.75rem;font-weight:700;">🔄 Dati Veri Ripristinati</span>`
            : (folderToRender === 'output' ? `<span style="background:rgba(16,185,129,0.18);color:#6ee7b7;padding:2px 8px;border-radius:99px;font-size:0.75rem;font-weight:700;">🛡️ Protetto</span>` : '');

        const canDownload = ['output', 'processed', 'failed'].includes(folderToRender);
        const dlBtn = canDownload
            ? `<a class="file-download-btn" href="/api/download/${folderToRender}/${encodeURIComponent(item.name)}" download>⬇ Scarica</a>`
            : `<span class="file-row-meta">In lavorazione...</span>`;

        return `
            <div class="file-row">
                <div class="file-row-left">
                    <span>📄</span>
                    <span class="file-row-name" title="${item.name}">${item.name}</span>
                    ${badgeHtml}
                </div>
                <div class="file-row-right">
                    <span class="file-row-meta">${formatBytes(item.size)} • ${formatTime(item.mtime)}</span>
                    ${dlBtn}
                </div>
            </div>
        `;
    }).join('');
}

async function fetchRecentFiles() {
    try {
        const r = await fetch('/api/files');
        if (!r.ok) return;
        cachedFiles = await r.json();
        renderFileList();
    } catch (e) {}
}

async function pollStatus() {
    try {
        const r = await fetch('/api/status');
        if (!r.ok) return;
        const data = await r.json();
        currentStatus = data.status;

        const dot = document.getElementById('statusDot');
        const txt = document.getElementById('statusText');
        const btn = document.getElementById('mainToggleBtn');
        const btnIcon = document.getElementById('mainToggleIcon');
        const btnLbl = document.getElementById('mainToggleLabel');

        if (data.status === 'running') {
            dot.className = 'status-dot running';
            txt.textContent = 'Protezione Attiva (Pronto)';
            btn.className = 'btn-power stop';
            btn.disabled = false;
            btnIcon.textContent = '■';
            btnLbl.textContent = 'FERMA GERMANO';
        } else if (data.status === 'loading_models') {
            dot.className = 'status-dot loading';
            txt.textContent = 'Avvio in corso (Caricamento IA)...';
            btn.className = 'btn-power stop';
            btn.disabled = false;
            btnIcon.textContent = '■';
            btnLbl.textContent = 'ANNULLA AVVIO';
        } else if (data.status === 'shutting_down') {
            dot.className = 'status-dot loading';
            txt.textContent = 'Arresto in corso...';
            btn.disabled = true;
        } else {
            dot.className = 'status-dot stopped';
            txt.textContent = 'In Pausa';
            btn.className = 'btn-power start';
            btn.disabled = false;
            btnIcon.textContent = '▶';
            btnLbl.textContent = 'ATTIVA GERMANO';
        }

        if (data.stats) {
            const setTxt = (id, v) => {
                const el = document.getElementById(id);
                if (el) el.textContent = v;
            };
            setTxt('countInput', data.stats.pending);
            setTxt('countOutput', data.stats.outputs);
            setTxt('tabCountOutput', data.stats.outputs);
            setTxt('tabCountInput', data.stats.pending);
            setTxt('tabCountProcessed', data.stats.processed);
            setTxt('tabCountFailed', data.stats.failed);
            setTxt('vaultCountLabel', data.stats.vault_count || 0);
            setTxt('vaultCountBadge', data.stats.vault_count || 0);
            setTxt('advVaultCount', data.stats.vault_count || 0);
        }

        if (data.system) {
            const sysPill = document.getElementById('sysUsagePill');
            if (sysPill) {
                sysPill.textContent = `CPU: ${data.system.cpu_percent}% • RAM: ${data.system.ram_used_gb}/${data.system.ram_total_gb} GB`;
            }
        }
    } catch (e) {}
}

async function pollLogs() {
    if (currentUiMode !== 'advanced') return;
    try {
        const r = await fetch('/api/logs');
        if (!r.ok) return;
        const data = await r.json();
        const term = document.getElementById('logTerminal');
        if (!term || !data.logs || data.logs.length === 0) return;

        const isAtBottom = term.scrollHeight - term.clientHeight <= term.scrollTop + 30;
        term.innerHTML = data.logs.map(line => {
            let cls = 'log-line';
            if (line.includes('Completato:') || line.includes('PRONTO') || line.includes('ripristinato')) cls += ' success';
            else if (line.includes('ATTENZIONE') || line.includes('Avviso')) cls += ' warn';
            else if (line.includes('ERRORE') || line.includes('FATALE')) cls += ' error';
            const safe = line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            return `<div class="${cls}">${safe}</div>`;
        }).join('');
        if (isAtBottom) term.scrollTop = term.scrollHeight;
    } catch (e) {}
}

document.addEventListener('DOMContentLoaded', async () => {
    await loadInitialSettings();
    await pollStatus();
    await fetchRecentFiles();

    // SLIDER SEMPLICE / AVANZATA
    document.getElementById('btnModeSimple')?.addEventListener('click', () => applyUiMode('simple', true));
    document.getElementById('btnModeAdvanced')?.addEventListener('click', () => applyUiMode('advanced', true));

    // SWITCH GLOBALE DE-ANONIMIZZAZIONE
    document.getElementById('enable_deanonymize')?.addEventListener('change', (e) => {
        applyDeanonSwitchState(e.target.checked);
        persistSettings(true);
    });

    // PULSANTE PRINCIPALE ATTIVA / FERMA GERMANO
    document.getElementById('mainToggleBtn')?.addEventListener('click', async () => {
        const btn = document.getElementById('mainToggleBtn');
        btn.disabled = true;
        if (currentStatus === 'stopped') {
            showToast('Avvio di Germano AI in corso...', 'info');
            await fetch('/api/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings: gatherSettings() })
            });
        } else {
            showToast('Arresto di Germano AI in corso...', 'info');
            await fetch('/api/stop', { method: 'POST' });
        }
        await pollStatus();
    });

    // GRIGLIA MODELLI IA E SINGOLE CATEGORIE (MODALITÀ AVANZATA)
    document.querySelectorAll('.model-check, .cat-check').forEach(chk => {
        chk.addEventListener('change', () => {
            if (!chk.checked) {
                currentComplianceMode = 'PD';
            }
            updatePresetButtonsHighlight();
            persistSettings(true);
        });
    });

    // PULSANTI RAPIDI MODELLI IA
    document.getElementById('btnModelsAllOn')?.addEventListener('click', () => {
        ALL_MODEL_IDS.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.checked = true;
        });
        updatePresetButtonsHighlight();
        persistSettings(true);
    });

    document.getElementById('btnModelsAllOff')?.addEventListener('click', () => {
        currentComplianceMode = 'PD';
        ALL_MODEL_IDS.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.checked = false;
        });
        updatePresetButtonsHighlight();
        persistSettings(true);
    });

    // PRESET PULSANTI GRIGLIA CATEGORIE
    document.getElementById('btnPresetPA')?.addEventListener('click', () => {
        currentComplianceMode = 'PA';
        [...ALL_MODEL_IDS, ...ALL_CATEGORY_IDS].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.checked = true;
        });
        const th = document.getElementById('ai_threshold');
        if (th) th.value = 0.0;
        updateThresholdBadge(0.0);
        updatePresetButtonsHighlight();
        persistSettings(true);
    });

    document.getElementById('btnPresetEssential')?.addEventListener('click', () => {
        currentComplianceMode = 'PD';
        const essentials = new Set(['censor_person', 'censor_address', 'censor_cf_iva', 'censor_email', 'censor_phone']);
        ALL_CATEGORY_IDS.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.checked = essentials.has(id);
        });
        updatePresetButtonsHighlight();
        persistSettings(true);
    });

    document.getElementById('btnPresetNone')?.addEventListener('click', () => {
        currentComplianceMode = 'PD';
        ALL_CATEGORY_IDS.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.checked = false;
        });
        updatePresetButtonsHighlight();
        persistSettings(true);
    });

    // SENSIBILITA', HARDWARE, PROXY
    const thSlider = document.getElementById('ai_threshold');
    if (thSlider) {
        thSlider.addEventListener('input', (e) => updateThresholdBadge(e.target.value));
        thSlider.addEventListener('change', () => {
            if (parseFloat(thSlider.value) > 0) currentComplianceMode = 'PD';
            persistSettings(true);
        });
    }
    document.getElementById('hardware_mode')?.addEventListener('change', () => persistSettings(true));
    document.getElementById('target_api_url')?.addEventListener('change', () => persistSettings(true));

    // DROPZONE 1: PROTEGGI FILE
    const protectDrop = document.getElementById('protectDropzone');
    const protectInput = document.getElementById('protectFileInput');
    if (protectDrop && protectInput) {
        protectDrop.addEventListener('click', () => protectInput.click());
        protectInput.addEventListener('change', (e) => {
            uploadFilesToProtect(e.target.files);
            protectInput.value = '';
        });
        ['dragenter', 'dragover'].forEach(ev => protectDrop.addEventListener(ev, (e) => {
            e.preventDefault();
            protectDrop.classList.add('dragover');
        }));
        ['dragleave', 'drop'].forEach(ev => protectDrop.addEventListener(ev, (e) => {
            e.preventDefault();
            protectDrop.classList.remove('dragover');
        }));
        protectDrop.addEventListener('drop', (e) => {
            if (e.dataTransfer?.files?.length) uploadFilesToProtect(e.dataTransfer.files);
        });
    }

    // TABS FILE MANAGER (AVANZATA)
    document.querySelectorAll('.folder-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.folder-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            activeFileTab = tab.dataset.folder;
            renderFileList();
        });
    });

    // PROTEGGI O RIPRISTINA AUTOMATICAMENTE TESTO
    const inputTextEl = document.getElementById('manualInputText');
    let autoRestoreDebounce = null;

    async function checkAndAutoRestoreText(text) {
        const deanonOn = document.getElementById('enable_deanonymize')?.checked ?? true;
        if (!deanonOn || !text || !/\[\s*[A-ZÀ-Ÿ\.\s\/_]+[\_\s]\d+\s*\]/i.test(text)) {
            return false;
        }
        try {
            const r = await fetch('/api/v1/deanonymize_text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });
            const data = await r.json();
            if (r.ok && data.restored && data.restored !== text) {
                const outputEl = document.getElementById('manualOutputText');
                const badgeEl = document.getElementById('textEntityBadge');
                if (outputEl) outputEl.value = data.restored;
                if (badgeEl) {
                    badgeEl.style.display = 'inline-block';
                    badgeEl.textContent = '🔄 Dati veri rimessi in automatico';
                }
                showToast('🔄 Risposta AI rilevata: dati veri rimessi a posto automaticamente!', 'success');
                return true;
            }
        } catch (e) {}
        return false;
    }

    if (inputTextEl) {
        inputTextEl.addEventListener('input', () => {
            clearTimeout(autoRestoreDebounce);
            autoRestoreDebounce = setTimeout(() => {
                checkAndAutoRestoreText((inputTextEl.value || '').trim());
            }, 220);
        });
    }

    document.getElementById('anonymizeTextBtn')?.addEventListener('click', async () => {
        const inputEl = document.getElementById('manualInputText');
        const outputEl = document.getElementById('manualOutputText');
        const badgeEl = document.getElementById('textEntityBadge');
        const btn = document.getElementById('anonymizeTextBtn');

        const text = (inputEl?.value || '').trim();
        if (!text) {
            showToast('Scrivi o incolla prima un testo.', 'error');
            return;
        }

        // Se contiene già etichette del Vault e lo switch è attivo, ripristina in automatico
        if (await checkAndAutoRestoreText(text)) {
            return;
        }

        if (currentStatus !== 'running') {
            await ensureEngineRunning();
            if (currentStatus !== 'running') {
                showToast('Attendi qualche secondo che Germano completi l\'avvio e riprova.', 'info');
                return;
            }
        }

        btn.disabled = true;
        const origLabel = btn.textContent;
        btn.textContent = '⏳ Elaborazione in corso...';

        try {
            const r = await fetch('/api/v1/anonymize_text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });
            const data = await r.json();
            if (r.ok && data.anonymized !== undefined) {
                outputEl.value = data.anonymized;
                if (data.auto_restored) {
                    if (badgeEl) {
                        badgeEl.style.display = 'inline-block';
                        badgeEl.textContent = '🔄 Dati veri rimessi in automatico';
                    }
                    showToast('🔄 Dati originali rimessi a posto automaticamente!', 'success');
                } else {
                    const count = (data.extracted_data || []).length;
                    if (badgeEl) {
                        badgeEl.style.display = 'inline-block';
                        badgeEl.textContent = `${count} dati protetti`;
                    }
                    showToast(`Testo protetto con successo (${count} dati nascosti).`, 'success');
                }
                pollStatus();
            } else {
                showToast(data.error || 'Errore durante l\'elaborazione del testo.', 'error');
            }
        } catch (e) {
            showToast('Errore di comunicazione con il motore locale.', 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = origLabel;
        }
    });

    // COPIA TESTO
    document.getElementById('copyTextBtn')?.addEventListener('click', () => {
        const outputEl = document.getElementById('manualOutputText');
        if (!outputEl || !outputEl.value) {
            showToast('Nessun risultato da copiare.', 'error');
            return;
        }
        navigator.clipboard.writeText(outputEl.value).then(() => {
            showToast('Testo copiato negli appunti!', 'success');
        });
    });

    // ARCHIVIO CORRISPONDENZE (VAULT) IN MODALITA' AVANZATA
    document.getElementById('btnShowVault')?.addEventListener('click', async () => {
        const box = document.getElementById('vaultPreviewBox');
        if (!box) return;
        if (box.style.display === 'block') {
            box.style.display = 'none';
            return;
        }
        try {
            const r = await fetch('/api/vault');
            const data = await r.json();
            box.style.display = 'block';
            if (!data.items || data.items.length === 0) {
                box.innerHTML = '<div>Nessuna corrispondenza salvata in memoria.</div>';
            } else {
                box.innerHTML = data.items.map(it =>
                    `<div class="vault-item"><strong>${it.tag}</strong> <span>→ ${it.value}</span></div>`
                ).join('');
            }
        } catch (e) {}
    });

    document.getElementById('btnClearVault')?.addEventListener('click', async () => {
        await fetch('/api/clear_vault', { method: 'POST' });
        const box = document.getElementById('vaultPreviewBox');
        if (box) box.style.display = 'none';
        showToast('Archivio corrispondenze svuotato.', 'info');
        pollStatus();
    });

    // PULISCI REGISTRO
    document.getElementById('clearLogsBtn')?.addEventListener('click', async () => {
        await fetch('/api/clear_logs', { method: 'POST' });
        pollLogs();
        showToast('Registro attività pulito.', 'info');
    });

    // PROCESSI SECONDARI E AGGIORNAMENTO
    fetch('/api/check_orphans').then(r => r.json()).then(d => {
        if (d.orphans > 0) {
            document.getElementById('orphanCount').textContent = d.orphans;
            document.getElementById('orphanWarning').style.display = 'block';
        }
    }).catch(() => {});

    document.getElementById('killOrphansBtn')?.addEventListener('click', async () => {
        await fetch('/api/kill_orphans', { method: 'POST' });
        document.getElementById('orphanWarning').style.display = 'none';
        showToast('Processi secondari chiusi.', 'success');
    });

    fetch('/api/check_update').then(r => r.json()).then(d => {
        if (d.update_available) {
            document.getElementById('latestVersionSpan').textContent = d.latest_version;
            document.getElementById('updateBanner').style.display = 'block';
        }
    }).catch(() => {});

    setInterval(pollStatus, 1500);
    setInterval( pollLogs, 1500);
    setInterval(fetchRecentFiles, 2500);
});
