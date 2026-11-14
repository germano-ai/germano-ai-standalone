'use strict';
/* Germano AI 0.95 - Impostazioni > Integrazioni MCP e UTCP: indirizzi pronti all'uso (Server MCP Streamable HTTP, SSE e
   stdio, manuale UTCP, OpenAPI), configurazione da copiare per i client MCP, collegamento con 1 clic ai client
   rilevati (con copia di sicurezza del file), strumenti per i flussi in ingresso e in uscita, prova del ciclo
   Ingresso -> Uscita, token per la rete e politica dei percorsi. Usa le funzioni comuni di script.js. */
(function () {
    let state = null;
    let tokenShown = false;
    let timer = null;
    let loading = false;

    const L = (it, en) => (typeof currentLang !== 'undefined' && currentLang === 'en') ? en : it;
    const PHASES = {
        input: ['Ingresso', 'Input', 'badge-info'],
        output: ['Uscita', 'Output', 'badge-ok'],
        workflow: ['Verifica', 'Verify', 'badge-warn'],
        status: ['Stato', 'Status', 'badge-off']
    };
    const TOOL_TEXT = {
        germano_anonymize_text: ['Anonimizza un testo o un elenco di testi prima dell\'invio', 'Anonymizes a text or a list of texts before sending'],
        germano_anonymize_file: ['Anonimizza un documento (PDF, Office, immagini, audio, archivi) mantenendo il formato', 'Anonymizes a document (PDF, Office, images, audio, archives) keeping its format'],
        germano_inspect_entities: ['Rileva i dati personali senza modificare nulla (audit, instradamento)', 'Detects personal data without changing anything (audit, routing)'],
        germano_leak_check: ['Controlla che un testo o un payload JSON in uscita non contenga dati personali', 'Checks that an outgoing text or JSON payload contains no personal data'],
        germano_deanonymize_text: ['Ripristina i dati originali nella risposta (solo le etichette presenti)', 'Restores the original data in the reply (only the placeholders present)'],
        germano_deanonymize_file: ['Ripristina i dati originali in un documento restituito', 'Restores the original data in a returned document'],
        germano_workflow_roundtrip: ['Esegue e verifica un ciclo completo ingresso → uscita', 'Runs and verifies a complete input → output cycle'],
        germano_status: ['Stato del motore, del Vault (solo conteggi) e degli indirizzi', 'Status of the engine, the Vault (counts only) and the addresses']
    };
    const CLIENT_STATUS = {
        connected: ['Collegato', 'Connected', 'badge-ok'],
        outdated: ['Da aggiornare', 'Needs update', 'badge-warn'],
        available: ['Rilevato', 'Detected', 'badge-info'],
        not_detected: ['Non rilevato', 'Not detected', 'badge-off'],
        error: ['Da configurare a mano', 'Configure by hand', 'badge-danger']
    };

    function phaseOf(tags) {
        for (const p of ['input', 'output', 'workflow', 'status']) if ((tags || []).includes(p)) return p;
        return 'status';
    }

    function quoteArg(a) {
        return /[\s"]/.test(a) ? `"${String(a).replace(/"/g, '\\"')}"` : a;
    }

    function stdioLine() {
        if (!state) return '';
        return [state.stdio.command, ...state.stdio.args].map(quoteArg).join(' ');
    }

    function stdioConfig() {
        const entry = { command: state.stdio.command, args: state.stdio.args };
        if (state.stdio.env && Object.keys(state.stdio.env).length) entry.env = state.stdio.env;
        return JSON.stringify({ mcpServers: { germano: entry } }, null, 2);
    }

    function httpConfig() {
        return JSON.stringify({ mcpServers: { germano: { type: 'http', url: state.endpoints.mcp.streamable_http } } }, null, 2);
    }

    async function load() {
        if (loading) return;
        loading = true;
        try {
            const { ok, data } = await fetchJson('/api/integrations');
            if (ok && data && data.status === 'success') {
                state = data;
                render();
            }
        } catch (e) { /* Germano non risponde: lo segnala gia' la Dashboard */ }
        finally { loading = false; }
    }

    function render() {
        if (!state) return;
        const ep = state.endpoints;
        $('intMcpUrl').textContent = ep.mcp.streamable_http;
        $('intSseUrl').textContent = ep.mcp.sse;
        $('intUtcpUrl').textContent = ep.utcp.manual;
        $('intOpenapiUrl').textContent = ep.openapi;
        $('intStdioCmd').textContent = stdioLine();
        const st = $('intStatus');
        const valid = state.utcp_check && state.utcp_check.valid;
        st.className = 'badge ' + (valid ? 'badge-ok' : 'badge-warn');
        st.textContent = valid ? L(`${state.tools.length} strumenti attivi`, `${state.tools.length} tools active`)
                               : L('Manuale UTCP da verificare', 'UTCP manual to check');
        renderStats();
        renderClients();
        renderTools();
        renderSecurity();
    }

    function renderStats() {
        const c = state.calls || {};
        const items = [
            [L('Strumenti esposti', 'Exposed tools'), String(state.tools.length),
             L(`${state.resources.length} risorse, ${state.prompts.length} prompt`, `${state.resources.length} resources, ${state.prompts.length} prompts`)],
            [L('Invocazioni', 'Calls'), String(c.total || 0),
             L(`${c.success || 0} riuscite, ${c.blocked || 0} bloccate, ${c.errors || 0} errori (dall'avvio)`,
               `${c.success || 0} succeeded, ${c.blocked || 0} blocked, ${c.errors || 0} errors (since start)`)],
            [L('Sessioni MCP aperte', 'Open MCP sessions'), String((state.sessions.http || 0) + (state.sessions.sse || 0)),
             `Streamable HTTP ${state.sessions.http || 0} · SSE ${state.sessions.sse || 0}`],
            ['MCP · UTCP', `MCP ${state.protocol_versions[0]} · UTCP ${state.utcp_version}`,
             (state.utcp_check && state.utcp_check.valid) ? L('manuale UTCP valido', 'UTCP manual valid')
                 : L('manuale UTCP con errori', 'UTCP manual with errors')]
        ];
        if (c.last) {
            items.push([L('Ultima chiamata', 'Last call'), c.last.tool.replace('germano_', ''),
                        `${c.last.transport} · ${c.last.outcome} · ${c.last.ms} ms · ${c.last.at}`]);
        }
        $('intStats').innerHTML = items.map(([l, v, sub]) => `<div class="net-item"><div class="net-item-label">${escapeHtml(l)}</div>` +
            `<div class="net-item-value">${escapeHtml(v)}</div><div class="net-item-sub">${escapeHtml(sub)}</div></div>`).join('');
    }

    function renderClients() {
        $('intClientsBody').innerHTML = (state.clients || []).map(c => {
            const s = CLIENT_STATUS[c.status] || CLIENT_STATUS.not_detected;
            let action = '';
            if (c.status === 'available') action = `<button type="button" class="btn btn-primary btn-sm" data-int-connect="${escapeHtml(c.id)}">${escapeHtml(L('Collega', 'Connect'))}</button>`;
            else if (c.status === 'outdated') action = `<button type="button" class="btn btn-secondary btn-sm" data-int-connect="${escapeHtml(c.id)}">${escapeHtml(L('Aggiorna', 'Update'))}</button>`;
            else if (c.status === 'connected') action = `<button type="button" class="btn btn-secondary btn-sm" data-int-remove="${escapeHtml(c.id)}">${escapeHtml(L('Scollega', 'Disconnect'))}</button>`;
            const note = c.message ? `<div class="hint">${escapeHtml(c.message)}</div>` : '';
            return `<tr><td class="agent-name">${escapeHtml(c.name)}</td>` +
                `<td><span class="badge ${s[2]}">${escapeHtml(L(s[0], s[1]))}</span></td>` +
                `<td><code class="int-path">${escapeHtml(c.short_path || c.path)}</code>${note}</td><td>${action}</td></tr>`;
        }).join('');
    }

    function curlFor(t) {
        const url = `${state.endpoints.rest_base}/${t.route.split('/').pop()}`;
        if (t.method === 'GET') return `curl.exe ${url}`;
        return `curl.exe -X POST ${url} -H "Content-Type: application/json" --data-binary "@richiesta.json"`;
    }

    function renderTools() {
        $('intToolsBody').innerHTML = state.tools.map(t => {
            const p = PHASES[phaseOf(t.tags)];
            const txt = TOOL_TEXT[t.name] || ['', ''];
            const ex = curlFor(t);
            return `<tr><td><span class="badge ${p[2]}">${escapeHtml(L(p[0], p[1]))}</span></td>` +
                `<td><code>${escapeHtml(t.name)}</code><div class="hint">${escapeHtml(L(txt[0], txt[1]))}</div></td>` +
                `<td><span class="method${t.method === 'GET' ? ' method-get' : ''}">${t.method}</span> <code>${escapeHtml(t.route)}</code></td>` +
                `<td>${copyButton(ex, L('Copia esempio curl', 'Copy curl example'))}</td></tr>`;
        }).join('');
    }

    function renderSecurity() {
        $('intToken').textContent = tokenShown ? state.token : '•'.repeat(24);
        $('intAutostart').checked = !!state.autostart_engine;
        const lan = state.lan || {};
        $('intLan').innerHTML = lan.listening && (lan.bases || []).length
            ? `<div class="hint">${escapeHtml(L('In ascolto sulla rete locale (modalità Server). Dagli altri computer:', 'Listening on the local network (Server mode). From the other computers:'))}</div>` +
              lan.bases.map(b => `<div class="copy-line"><code>${escapeHtml(b + '/mcp')}</code>${copyButton(b + '/mcp', L('Copia', 'Copy'))}` +
                                 `<code>${escapeHtml(b + '/utcp')}</code>${copyButton(b + '/utcp', L('Copia', 'Copy'))}</div>`).join('')
            : `<div class="hint">${escapeHtml(L('La rete è spenta (modalità Standalone o Client): MCP, UTCP e API v1 rispondono solo a questo computer. Per usarli da altri computer attiva la modalità Server in «Modalità e rete».',
                                               'The network is off (Standalone or Client mode): MCP, UTCP and the v1 APIs answer only this computer. To use them from other computers enable the Server mode in «Mode & network».'))}</div>`;
        const pol = state.paths || {};
        $('intPaths').innerHTML = escapeHtml(L('Percorsi dei file (file_path, output_path), solo da questo computer, dentro: ',
                                               'File paths (file_path, output_path), only from this computer, inside: ')) +
            (pol.allowed_roots || []).map(r => `<code>${escapeHtml(r)}</code>`).join(' ') +
            escapeHtml(L(`. Mai: ${pol.never || ''}. Altre cartelle: «integration_allowed_dirs» in config.json.`,
                         `. Never: ${pol.never || ''}. More folders: «integration_allowed_dirs» in config.json.`));
    }

    async function connect(id, remove) {
        const { ok, data } = await postJson('/api/integrations/connect', { client: id, remove: !!remove });
        if (ok && data.status === 'success') {
            state = data;
            render();
            const r = data.result || {};
            const backup = r.backup ? L(` Copia di sicurezza: ${r.backup}`, ` Backup: ${r.backup}`) : '';
            showToast((r.message || L('Fatto.', 'Done.')) + backup, 'success', 7000);
        } else {
            showToast((data && data.message) || L('Operazione non riuscita.', 'Operation failed.'), 'error', 7000);
        }
    }

    function box(title, text, cls) {
        return `<div class="int-box ${cls || ''}"><div class="int-box-title">${escapeHtml(title)}</div><pre>${escapeHtml(text)}</pre></div>`;
    }

    function setBusy(on, label) {
        ['btnIntTest', 'btnIntLeak'].forEach(id => { const b = $(id); if (b) b.disabled = on; });
        const out = $('intTestResult');
        if (on) {
            out.hidden = false;
            out.innerHTML = `<div class="hint"><span class="spinner"></span> ${escapeHtml(label)}</div>`;
        }
    }

    function engineHint() {
        return (typeof currentStatus !== 'undefined' && currentStatus !== 'running')
            ? L('Avvio del motore e caricamento dei modelli (circa un minuto alla prima richiesta)…', 'Starting the engine and loading the models (about a minute on the first request)…')
            : L('Elaborazione in corso…', 'Processing…');
    }

    function blockedHtml(data, status) {
        const msg = (data && (data.message || data.error)) || L(`Errore ${status}`, `Error ${status}`);
        const cls = data && data.status === 'blocked' ? 'badge-warn' : 'badge-danger';
        return `<div class="int-badges"><span class="badge ${cls}">${escapeHtml(data && data.status === 'blocked' ? L('Bloccato (nessun dato è uscito)', 'Blocked (no data left)') : L('Errore', 'Error'))}</span></div><div class="hint">${escapeHtml(msg)}</div>`;
    }

    async function runCycle() {
        const text = $('intTestText').value;
        const reply = $('intTestReply').value.trim();
        if (!text.trim()) { showToast(L('Scrivi un testo in ingresso.', 'Write an input text.'), 'error'); return; }
        setBusy(true, engineHint());
        try {
            const body = { text };
            if (reply) body.external_reply = reply;
            const { ok, status, data } = await postJson('/api/v1/workflow-roundtrip', body);
            const out = $('intTestResult');
            if (!ok) { out.innerHTML = blockedHtml(data, status); return; }
            const cats = Object.entries(data.categories || {}).map(([k, v]) => `${k} ${v}`).join(', ');
            const ms = (data.steps || []).map(s => `${s.step} ${s.ms} ms`).join(' · ');
            const okBadge = data.roundtrip_ok ? `<span class="badge badge-ok">${escapeHtml(L('Ciclo verificato', 'Cycle verified'))}</span>`
                                              : `<span class="badge badge-warn">${escapeHtml(L('Etichette non ripristinate', 'Placeholders not restored'))}</span>`;
            const residual = data.residual_entities === 0 ? `<span class="badge badge-ok">${escapeHtml(L('Nessun dato personale nel testo uscito', 'No personal data in the text that left'))}</span>`
                                                         : (data.residual_entities ? `<span class="badge badge-danger">${escapeHtml(L(`${data.residual_entities} dati rilevati nel testo uscito`, `${data.residual_entities} items detected in the text that left`))}</span>` : '');
            out.innerHTML = `<div class="int-badges">${okBadge}${residual}<span class="badge">${escapeHtml(L(`${data.replacements} dati oscurati`, `${data.replacements} items masked`))}</span>` +
                (cats ? `<span class="badge badge-off">${escapeHtml(cats)}</span>` : '') + `</div>` +
                `<div class="int-cols">` +
                box(L('1 · Esce verso il sistema esterno (anonimizzato)', '1 · Leaves towards the external system (anonymized)'), data.anonymized_text, 'int-box-out') +
                box(data.reply_simulated ? L('2 · Risposta del sistema esterno (simulata)', '2 · Reply of the external system (simulated)')
                                         : L('2 · Risposta del sistema esterno', '2 · Reply of the external system'), data.external_reply) +
                box(L('3 · Torna a te (dati originali ripristinati)', '3 · Comes back to you (original data restored)'), data.restored_text, 'int-box-in') +
                `</div><div class="hint">${escapeHtml(ms)}${(data.unmatched_placeholders || []).length ? escapeHtml(L(' · non ripristinate: ', ' · not restored: ') + data.unmatched_placeholders.join(', ')) : ''}</div>`;
            load();
        } catch (e) {
            $('intTestResult').innerHTML = blockedHtml(null, '—');
        } finally {
            setBusy(false);
        }
    }

    async function runLeak() {
        const text = $('intTestReply').value.trim() || $('intTestText').value;
        if (!text.trim()) return;
        setBusy(true, engineHint());
        try {
            const { ok, status, data } = await postJson('/api/v1/leak-check', { text });
            const out = $('intTestResult');
            if (!ok) { out.innerHTML = blockedHtml(data, status); return; }
            const cats = Object.entries(data.categories || {}).map(([k, v]) => `${k} ${v}`).join(', ');
            out.innerHTML = `<div class="int-badges">` + (data.safe
                ? `<span class="badge badge-ok">${escapeHtml(L('Sicuro: nessun dato personale da proteggere', 'Safe: no personal data to protect'))}</span>`
                : `<span class="badge badge-danger">${escapeHtml(L(`Fuga: ${data.findings_count} dati personali in chiaro`, `Leak: ${data.findings_count} personal data in clear`))}</span>`) +
                (cats ? `<span class="badge badge-off">${escapeHtml(cats)}</span>` : '') +
                `<span class="badge">${escapeHtml(L(`${data.placeholders_present} etichette già presenti`, `${data.placeholders_present} placeholders already present`))}</span></div>` +
                `<div class="hint">${escapeHtml(L('Controllato il testo della risposta (se presente) o quello in ingresso, in sola lettura: nulla viene scritto nel Vault.',
                                                  'Checked the reply text (if any) or the input text, read-only: nothing is written to the Vault.'))}</div>`;
            load();
        } finally {
            setBusy(false);
        }
    }

    function bind() {
        if (!$('intPanel')) return;
        $('btnCopyMcpConfig').addEventListener('click', () => { if (state) copyText(stdioConfig()); });
        $('btnCopyMcpHttp').addEventListener('click', () => { if (state) copyText(httpConfig()); });
        $('btnCopyUtcpUrl').addEventListener('click', () => { if (state) copyText(state.endpoints.utcp.manual); });
        $('btnIntRefresh').addEventListener('click', () => load());
        $('btnIntTest').addEventListener('click', runCycle);
        $('btnIntLeak').addEventListener('click', runLeak);
        $('btnIntTokenShow').addEventListener('click', () => { tokenShown = !tokenShown; renderSecurity(); });
        $('btnIntTokenCopy').addEventListener('click', () => { if (state) copyText(state.token); });
        $('btnIntTokenNew').addEventListener('click', async () => {
            if (!confirm(L('Creare un nuovo token? Quello attuale smette subito di funzionare sugli altri computer.',
                           'Create a new token? The current one stops working on the other computers immediately.'))) return;
            const { ok, data } = await postJson('/api/integrations/token', {});
            if (ok && data.status === 'success') { state = data; tokenShown = true; render(); showToast(L('Nuovo token creato.', 'New token created.'), 'success'); }
            else showToast((data && data.message) || L('Operazione non riuscita.', 'Operation failed.'), 'error');
        });
        $('intAutostart').addEventListener('change', async (e) => {
            const { ok, data } = await postJson('/api/integrations/settings', { autostart_engine: e.target.checked });
            if (ok && data.status === 'success') { state = data; render(); }
            else { e.target.checked = !e.target.checked; showToast((data && data.message) || L('Impostazione non salvata.', 'Setting not saved.'), 'error'); }
        });
        $('intClientsBody').addEventListener('click', (e) => {
            const c = e.target.closest('[data-int-connect]');
            const r = e.target.closest('[data-int-remove]');
            if (c) connect(c.dataset.intConnect, false);
            if (r) connect(r.dataset.intRemove, true);
        });
        timer = setInterval(() => {
            if (typeof currentTab !== 'undefined' && currentTab === 'settings' && currentPane === 'integrations' && !document.hidden) load();
        }, 5000);
    }

    window.GermanoIntegrations = { load, render };
    document.addEventListener('DOMContentLoaded', bind);
})();
