document.addEventListener('DOMContentLoaded', () => {
    const toggleBtn = document.getElementById('toggle-daemon');
    const toggleText = document.getElementById('toggle-text');
    const statusText = document.getElementById('daemon-status-text');
    const logContainer = document.getElementById('log-container');
    
    // Stats
    const statInput = document.getElementById('stat-input');
    const statProcessed = document.getElementById('stat-processed');
    const statOutput = document.getElementById('stat-output');
    
    const loadingContainer = document.getElementById('loading-container');
    
    let currentDaemonState = 'stopped'; // 'stopped', 'loading_models', 'running'
    let pollInterval = null;
    let autoScroll = true;
    let sessionTotalFiles = 0;

    // Check for orphaned daemons on startup
    fetch('/api/check_orphans').then(res => res.json()).then(data => {
        if (data.orphans && data.orphans > 0) {
            const kill = confirm(`Attenzione: Sono state rilevate ${data.orphans} istanze del demone rimaste attive in background da sessioni precedenti. Vuoi terminarle per evitare accavallamenti e problemi sui file?`);
            if (kill) {
                fetch('/api/kill_orphans', { method: 'POST' }).then(() => {
                    alert("Processi fantasma terminati con successo.");
                });
            }
        }
    }).catch(e => console.error("Error checking orphans", e));

    // Check for updates
    fetch('/api/check_update').then(res => res.json()).then(data => {
        if (data.update_available) {
            document.getElementById('update-version').innerText = data.latest_version;
            document.getElementById('update-banner').style.display = 'block';
        }
    }).catch(e => console.error("Error checking updates", e));

    const preFlightStats = document.getElementById('pre-flight-stats');
    const progressContainer = document.getElementById('session-progress-container');
    const lblInputFiles = document.getElementById('lbl_input_files');
    const lblInputFolders = document.getElementById('lbl_input_folders');
    const lblInputSize = document.getElementById('lbl_input_size');
    const progressFill = document.getElementById('session-progress-fill');
    const lblProgressPercent = document.getElementById('lbl_progress_percent');
    const lblProgressDone = document.getElementById('lbl_progress_done');
    const lblProgressTotal = document.getElementById('lbl_progress_total');

    function formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // Detect manual scrolling to stop autoscroll
    logContainer.addEventListener('scroll', () => {
        const isAtBottom = logContainer.scrollHeight - logContainer.scrollTop <= logContainer.clientHeight + 10;
        autoScroll = isAtBottom;
    });

    function setUIState(state) {
        currentDaemonState = state;
        
        if (state === 'running') {
            toggleBtn.classList.remove('hidden');
            loadingContainer.classList.add('hidden');
            toggleBtn.className = 'btn-toggle on';
            toggleText.textContent = 'STOP DAEMON';
            statusText.textContent = 'System is ONLINE. Monitoring for files...';
            statusText.className = 'status-text-on';
            toggleBtn.disabled = false;
            if (preFlightStats) preFlightStats.classList.add('hidden');
            if (progressContainer) progressContainer.classList.remove('hidden');
        } else if (state === 'loading_models') {
            toggleBtn.classList.add('hidden');
            loadingContainer.classList.remove('hidden');
            statusText.textContent = '';
            if (preFlightStats) preFlightStats.classList.add('hidden');
            if (progressContainer) progressContainer.classList.remove('hidden');
        } else {
            toggleBtn.classList.remove('hidden');
            loadingContainer.classList.add('hidden');
            toggleBtn.className = 'btn-toggle off';
            toggleText.textContent = 'START DAEMON';
            statusText.textContent = 'System is offline. AI model is not loaded.';
            statusText.className = 'status-text-off';
            toggleBtn.disabled = false;
            sessionTotalFiles = 0;
            if (preFlightStats) preFlightStats.classList.remove('hidden');
            if (progressContainer) progressContainer.classList.add('hidden');
        }
    }

    const thresholdSlider = document.getElementById('setting_ai_threshold');
    const thresholdVal = document.getElementById('threshold_val');
    const modePA = document.getElementById('mode_pa');
    const modePD = document.getElementById('mode_pd');
    
    function updateThresholdText(val) {
        if (val == 0) thresholdVal.textContent = '0% (Tutto)';
        else if (val == 100) thresholdVal.textContent = '100% (Estrema certezza)';
        else thresholdVal.textContent = val + '%';
    }
    
    function applyComplianceMode() {
        const isPA = modePA.checked;
        const ocr = document.getElementById('setting_ocr');
        const faces = document.getElementById('setting_faces');
        const regex = document.getElementById('setting_regex');
        const slider = document.getElementById('setting_ai_threshold');
        
        const tooltipText = "Passa a Germano PD per sbloccare questa funzionalità";
        
        if (isPA) {
            ocr.checked = true;
            faces.checked = true;
            regex.checked = true;
            slider.value = 0;
            updateThresholdText(0);
            
            ocr.disabled = true;
            faces.disabled = true;
            regex.disabled = true;
            slider.disabled = true;
            
            [ocr, faces, regex].forEach(el => {
                if(el) {
                    const parent = el.closest('.switch-container');
                    if (parent) {
                        parent.style.opacity = '0.5';
                        parent.style.cursor = 'not-allowed';
                        parent.title = tooltipText;
                        const sl = parent.querySelector('.slider');
                        if(sl) sl.style.cursor = 'not-allowed';
                    }
                }
            });
            if(slider) {
                const sliderParent = slider.closest('.slider-container');
                if (sliderParent) {
                    sliderParent.style.opacity = '0.5';
                    sliderParent.title = tooltipText;
                    slider.style.cursor = 'not-allowed';
                }
            }
        } else {
            ocr.disabled = false;
            faces.disabled = false;
            regex.disabled = false;
            slider.disabled = false;
            
            [ocr, faces, regex].forEach(el => {
                if(el) {
                    const parent = el.closest('.switch-container');
                    if (parent) {
                        parent.style.opacity = '1';
                        parent.style.cursor = 'pointer';
                        parent.removeAttribute('title');
                        const sl = parent.querySelector('.slider');
                        if(sl) sl.style.cursor = 'pointer';
                    }
                }
            });
            if(slider) {
                const sliderParent = slider.closest('.slider-container');
                if (sliderParent) {
                    sliderParent.style.opacity = '1';
                    sliderParent.removeAttribute('title');
                    slider.style.cursor = 'pointer';
                }
            }
        }
    }

    if (modePA && modePD) {
        modePA.addEventListener('change', applyComplianceMode);
        modePD.addEventListener('change', applyComplianceMode);
    }
    
    if (thresholdSlider) {
        thresholdSlider.addEventListener('input', (e) => updateThresholdText(e.target.value));
    }

    function getSettingsFromUI() {
        // Se PA è attivo, forza i valori al massimo livello di restrizione, altrimenti leggi i controlli
        const isPA = modePA ? modePA.checked : false;
        
        return {
            compliance_mode: isPA ? "PA" : "PD",
            enable_ocr: isPA ? true : document.getElementById('setting_ocr').checked,
            enable_faces: isPA ? true : document.getElementById('setting_faces').checked,
            enable_regex: isPA ? true : document.getElementById('setting_regex').checked,
            ai_threshold: isPA ? 0.0 : parseInt(document.getElementById('setting_ai_threshold').value) / 100.0,
            hardware_mode: document.getElementById('setting_hardware').value
        };
    }

    function setSettingsToUI(s) {
        if (s.compliance_mode === "PA" && modePA) {
            modePA.checked = true;
        } else if (s.compliance_mode === "PD" && modePD) {
            modePD.checked = true;
        }
        
        if (s.enable_ocr !== undefined) document.getElementById('setting_ocr').checked = s.enable_ocr;
        if (s.enable_faces !== undefined) document.getElementById('setting_faces').checked = s.enable_faces;
        if (s.enable_regex !== undefined) document.getElementById('setting_regex').checked = s.enable_regex;
        if (s.ai_threshold !== undefined) {
            const val = Math.round(s.ai_threshold * 100);
            document.getElementById('setting_ai_threshold').value = val;
            updateThresholdText(val);
        }
        if (s.hardware_mode !== undefined) document.getElementById('setting_hardware').value = s.hardware_mode;
        
        applyComplianceMode();
    }

    let previousSettings = getSettingsFromUI();

    fetch('/api/settings').then(res => res.json()).then(data => {
        if (Object.keys(data).length > 0) {
            setSettingsToUI(data);
            previousSettings = getSettingsFromUI();
        }
    }).catch(() => {});

    const settingInputs = document.querySelectorAll('.settings-panel input, .settings-panel select');
    settingInputs.forEach(input => {
        input.addEventListener('change', async () => {
            if (currentDaemonState === 'running' || currentDaemonState === 'loading_models') {
                const confirmed = confirm("La modifica di questa impostazione richiede il riavvio del demone. Continuare?");
                if (confirmed) {
                    previousSettings = getSettingsFromUI();
                    statusText.textContent = 'Riavvio in corso...';
                    await fetch('/api/stop');
                    setTimeout(async () => {
                        await fetch('/api/start', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ settings: previousSettings })
                        });
                    }, 1500);
                } else {
                    // Revert to previous
                    setSettingsToUI(previousSettings);
                }
            } else {
                previousSettings = getSettingsFromUI();
            }
        });
    });

    async function toggleDaemon() {
        // Optimistic UI update
        toggleBtn.disabled = true;
        
        try {
            if (currentDaemonState === 'running' || currentDaemonState === 'loading_models') {
                statusText.textContent = 'Sending stop signal...';
                await fetch('/api/stop');
            } else {
                statusText.textContent = 'Booting AI System...';
                
                await fetch('/api/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ settings: getSettingsFromUI() })
                });
            }
        } catch (error) {
            console.error("Failed to toggle daemon:", error);
        }
        
        setTimeout(() => { toggleBtn.disabled = false; }, 2000);
    }

    async function pollStatus() {
        try {
            // Check status & stats
            const resStatus = await fetch('/api/status');
            const dataStatus = await resStatus.json();
            
            // If the state changed in the backend, update UI
            if (dataStatus.status !== currentDaemonState) {
                setUIState(dataStatus.status);
            }
            
            // Update stats
            if (dataStatus.stats) {
                const currentPending = dataStatus.stats.pending;
                statInput.textContent = currentPending;
                statOutput.textContent = dataStatus.stats.outputs;
                statProcessed.textContent = dataStatus.stats.processed;
                
                if (currentDaemonState === 'stopped') {
                    if (lblInputFiles) lblInputFiles.textContent = currentPending;
                    if (lblInputFolders) lblInputFolders.textContent = dataStatus.stats.pending_folders || 0;
                    if (lblInputSize) lblInputSize.textContent = formatBytes(dataStatus.stats.pending_bytes || 0);
                } else {
                    if (sessionTotalFiles === 0 || currentPending > sessionTotalFiles) {
                        sessionTotalFiles = currentPending;
                    }
                    if (sessionTotalFiles > 0) {
                        const done = sessionTotalFiles - currentPending;
                        const percent = Math.round((done / sessionTotalFiles) * 100);
                        if (progressFill) progressFill.style.width = percent + '%';
                        if (lblProgressPercent) lblProgressPercent.textContent = percent;
                        if (lblProgressDone) lblProgressDone.textContent = done;
                        if (lblProgressTotal) lblProgressTotal.textContent = sessionTotalFiles;
                    } else {
                        if (progressFill) progressFill.style.width = '100%';
                        if (lblProgressPercent) lblProgressPercent.textContent = 100;
                        if (lblProgressDone) lblProgressDone.textContent = 0;
                        if (lblProgressTotal) lblProgressTotal.textContent = 0;
                    }
                }
            }

            // Fetch logs
            const resLogs = await fetch('/api/logs');
            const dataLogs = await resLogs.json();
            
            if (dataLogs.logs) {
                let logsText = dataLogs.logs.join("");
                // Only update if logs changed
                if (logContainer.textContent !== logsText) {
                    logContainer.textContent = logsText;
                    if (autoScroll) {
                        logContainer.scrollTop = logContainer.scrollHeight;
                    }
                }
            }
        } catch (error) {
            console.error("Polling error:", error);
        }
    }

    toggleBtn.addEventListener('click', toggleDaemon);

    // Initial check
    pollStatus();
    // Poll every 1 second
    pollInterval = setInterval(pollStatus, 1000);
});
