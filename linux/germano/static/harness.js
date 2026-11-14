/* Germano AI 0.95 - Harness AI e Glass Window.
   Componente condiviso dalla Dashboard (index.html), dal Remote Control (/remote) e dal pannello di Germano Client:
   stessa interfaccia ovunque, stesse rotte del server (/api/harness/v2/*), che applica le regole di chi chiede
   (questo computer o un dispositivo della rete).
   Sicurezza: tutto il testo ricevuto (risposte delle AI comprese) viene sempre convertito in testo o passato dal
   renderer Markdown, che parte dal testo gia' «escaped»: nessun HTML del modello arriva alla pagina, nessuna immagine
   esterna viene caricata (un'AI potrebbe usarle per far uscire dati nell'indirizzo), i collegamenti sono solo
   http/https/mailto e si aprono a parte. */
'use strict';
(function () {
    // ------------------------------------------------------------------ testi (IT / EN)
    const S = {
        newChat: ['Nuova conversazione', 'New conversation'],
        search: ['Cerca nelle conversazioni', 'Search conversations'],
        today: ['Oggi', 'Today'], yesterday: ['Ieri', 'Yesterday'], week: ['Ultimi 7 giorni', 'Last 7 days'], older: ['Meno recenti', 'Older'],
        noConvs: ['Nessuna conversazione. Scrivi qui sotto per iniziare.', 'No conversations yet. Type below to start.'],
        noMatch: ['Nessuna conversazione trovata.', 'No conversation found.'],
        keepDevice: ['Conserva le conversazioni su questo dispositivo', 'Keep conversations on this device'],
        keepSession: ['Le conversazioni restano solo in questa sessione del browser', 'Conversations stay only in this browser session'],
        clearAll: ['Elimina tutte le conversazioni', 'Delete all conversations'],
        confirmClearAll: ['Eliminare tutte le conversazioni salvate su questo dispositivo?', 'Delete all conversations saved on this device?'],
        confirmDelete: ['Eliminare questa conversazione?', 'Delete this conversation?'],
        rename: ['Rinomina', 'Rename'], del: ['Elimina', 'Delete'], temporary: ['temporanea', 'temporary'],
        untitled: ['Nuova conversazione', 'New conversation'],
        sidebar: ['Mostra o nascondi le conversazioni', 'Show or hide conversations'],
        system: ['Istruzioni', 'Instructions'],
        systemTitle: ['Istruzioni per l\'assistente (anche loro protette da Germano)', 'Instructions for the assistant (protected by Germano too)'],
        systemPh: ['Es. «Rispondi in modo sintetico, in italiano, con elenchi puntati.»', 'E.g. “Answer concisely, in English, with bullet points.”'],
        export: ['Esporta', 'Export'],
        exportTitle: ['Scarica la conversazione in Markdown (contiene i dati originali)', 'Download the conversation as Markdown (contains the original data)'],
        glass: ['Glass Window', 'Glass Window'],
        glassTitle: ['Glass Window (Ispezione Trasparente): vedi in tempo reale tutto ciò che viene comunicato al modello e interrompi quando vuoi (Ctrl+Maiusc+G)',
                     'Glass Window (Transparent Inspection): see in real time everything sent to the model and stop it whenever you want (Ctrl+Shift+G)'],
        welcomeTitle: ['Chatbot e Agenti AI protetti da Germano', 'AI Chatbot & Agents protected by Germano'],
        welcomeText: ['Scrivi, allega file e scegli il modello in basso a destra. Ogni dato personale viene oscurato sul tuo computer prima di uscire e rimesso al suo posto nella risposta. Con la Glass Window vedi tutto ciò che viene inviato, in tempo reale, e puoi fermarlo.',
                      'Type, attach files and pick the model at the bottom right. Every piece of personal data is masked on your computer before it leaves and put back in the answer. With the Glass Window you see everything that is sent, in real time, and you can stop it.'],
        welcomeTextRemote: ['Scrivi, allega file e scegli il modello in basso a destra. Ogni dato personale viene oscurato dal Germano Server della tua rete prima di uscire e rimesso al suo posto nella risposta. Con la Glass Window vedi tutto ciò che viene inviato, in tempo reale, e puoi fermarlo.',
                            'Type, attach files and pick the model at the bottom right. Every piece of personal data is masked by the Germano Server of your network before it leaves and put back in the answer. With the Glass Window you see everything that is sent, in real time, and you can stop it.'],
        cardEngine: ['Protezione', 'Protection'], cardModels: ['Modelli', 'Models'], cardGlass: ['Trasparenza', 'Transparency'],
        engineOk: ['Motore attivo', 'Engine running'], engineOff: ['Motore in pausa', 'Engine paused'], engineStarting: ['Motore in avvio', 'Engine starting'],
        engineOffSub: ['Si avvia da solo al primo invio.', 'It starts by itself on the first send.'],
        engineRemoteOff: ['Motore del server non pronto', 'Server engine not ready'],
        engineOkSub: ['I dati vengono protetti prima di ogni invio.', 'Data are protected before every send.'],
        modelsAvail: ['disponibili', 'available'], modelAvail1: ['disponibile', 'available'], modelsNone: ['Nessuna AI rilevata', 'No AI detected'],
        modelsSub: ['Rilevamento automatico ogni 12 secondi.', 'Detected automatically every 12 seconds.'],
        glassCard: ['Ispezione in tempo reale', 'Real-time inspection'], openGlass: ['Apri la Glass Window', 'Open the Glass Window'],
        sug1: ['Riassumi il documento allegato in 5 punti', 'Summarize the attached document in 5 points'],
        sug2: ['Scrivi una risposta cortese a questa email', 'Write a polite reply to this email'],
        sug3: ['Estrai scadenze e importi da questo contratto', 'Extract deadlines and amounts from this contract'],
        sug4: ['Traduci in inglese con tono formale', 'Translate into Italian with a formal tone'],
        placeholder: ['Scrivi un messaggio… I dati personali vengono protetti da Germano prima dell\'invio.', 'Type a message… Personal data are protected by Germano before sending.'],
        attach: ['Allega file (anche trascinandoli qui)', 'Attach files (or drag them here)'],
        drop: ['Rilascia i file: Germano ne protegge il testo e li allega alla richiesta', 'Drop the files: Germano protects their text and attaches them'],
        review: ['Revisione prima dell\'invio', 'Review before sending'],
        reviewTitle: ['Prima di inviare, Germano si ferma e mostra nella Glass Window il payload esatto: lo invii o lo blocchi tu.', 'Before sending, Germano stops and shows the exact payload in the Glass Window: you send it or block it.'],
        send: ['Invia (Invio)', 'Send (Enter)'], stop: ['Interrompi operazione', 'Stop operation'],
        hintKeys: ['Invio per inviare · Maiusc+Invio per andare a capo', 'Enter to send · Shift+Enter for a new line'],
        hintSafe: ['Testo e allegati protetti sul tuo computer prima di uscire', 'Text and attachments protected on your computer before leaving'],
        hintSafeRemote: ['Testo e allegati protetti dal Germano Server prima di uscire', 'Text and attachments protected by the Germano Server before leaving'],
        shieldOk: ['Protezione attiva', 'Protection on'], shieldStart: ['Motore in pausa: si avvia all\'invio', 'Engine paused: it starts when you send'],
        shieldStarting: ['Avvio del motore…', 'Starting the engine…'], shieldRemote: ['Motore del server non pronto', 'Server engine not ready'],
        profile: ['Profilo', 'Profile'],
        pickTitle: ['Scegli il modello con cui parlare', 'Choose the model to talk to'],
        pickSearch: ['Cerca un modello o un servizio', 'Search a model or service'],
        pickNone: ['Scegli un modello', 'Choose a model'], pickDetecting: ['Rilevamento delle AI…', 'Detecting AIs…'],
        gProtect: ['Germano', 'Germano'], gCli: ['CLI su questo computer', 'CLIs on this computer'], gCliRemote: ['CLI del server', 'Server CLIs'],
        gLocal: ['Modelli locali (rilevati in automatico)', 'Local models (detected automatically)'],
        gLocalRemote: ['Modelli locali del server', 'Server local models'], gCloud: ['Servizi via API (filtrati da Germano)', 'API services (filtered by Germano)'],
        gOther: ['Non utilizzabili per Chatbot e Agenti', 'Not usable for Chatbot & Agents'],
        redetect: ['Rileva di nuovo', 'Detect again'], autoDetect: ['Rilevamento automatico ogni 12 s', 'Automatic detection every 12 s'],
        keyNeeded: ['serve la chiave API', 'API key needed'], enterKey: ['Chiave', 'Key'],
        keyServer: ['chiave di questo computer', 'this computer\'s key'], keyServerRemote: ['chiave condivisa dal server', 'key shared by the server'],
        keyDevice: ['chiave su questo dispositivo', 'key on this device'],
        keyLabel: ['Chiave API di', 'API key of'], keyPh: ['incolla la chiave del servizio', 'paste the service key'],
        keyRemember: ['Ricorda la chiave su questo dispositivo (altrimenti si dimentica chiudendo la pagina)', 'Remember the key on this device (otherwise it is forgotten when the page is closed)'],
        keySave: ['Salva', 'Save'], keyRemove: ['Togli', 'Remove'], keyInvalid: ['Chiave non valida (almeno 8 caratteri, senza spazi).', 'Invalid key (at least 8 characters, no spaces).'],
        keyNote: ['La chiave non viene salvata dal server: viaggia solo con le tue richieste e nella Glass Window compare oscurata.', 'The key is not saved by the server: it travels only with your requests and is masked in the Glass Window.'],
        model: ['Modello', 'Model'], modelPh: ['nome del modello (es. quello suggerito)', 'model name (e.g. the suggested one)'],
        modelOptional: ['Modello (facoltativo, es. sonnet)', 'Model (optional, e.g. sonnet)'], listModels: ['Elenca', 'List'],
        notDetected: ['non rilevata', 'not detected'],
        protectOnly: ['Solo protezione', 'Protection only'],
        you: ['Tu', 'You'],
        filterWorking: ['Germano sta proteggendo la richiesta…', 'Germano is protecting the request…'],
        filterAudio: ['Germano sta trascrivendo l\'audio su questo computer e proteggendo la richiesta… (circa un terzo della durata della registrazione)', 'Germano is transcribing the audio on this computer and protecting the request… (about one third of the recording length)'],
        filterArchive: ['Germano sta aprendo l\'archivio in sicurezza e proteggendo la richiesta…', 'Germano is opening the archive safely and protecting the request…'],
        audioFile: ['Registrazione audio: Germano la trascrive sul computer del motore (senza Internet) e protegge il testo prima dell\'invio.', 'Audio recording: Germano transcribes it on the engine\'s computer (no Internet) and protects the text before sending.'],
        archiveFile: ['Archivio compresso: Germano lo apre in sicurezza e usa, protetto, il testo dei documenti che contiene.', 'Compressed archive: Germano opens it safely and uses, protected, the text of the documents it contains.'],
        filterDone: ['Germano Privacy Filter', 'Germano Privacy Filter'],
        masked: ['dati oscurati', 'data masked'], maskedOne: ['dato oscurato', 'item masked'], noneMasked: ['nessun dato personale trovato', 'no personal data found'],
        fromCache: ['dalla cache', 'from cache'],
        reviewWait: ['In attesa della tua revisione: controlla il payload nella Glass Window. Nulla è ancora stato inviato.', 'Waiting for your review: check the payload in the Glass Window. Nothing has been sent yet.'],
        sendNow: ['Invia ora', 'Send now'], blockSend: ['Blocca invio', 'Block sending'],
        inGlass: ['Apri nella Glass Window', 'Open in the Glass Window'],
        skipped: ['Allegati senza testo non inclusi (usa la scheda Sanitizzazione manuale): ', 'Attachments without text not included (use the Manual Sanitization tab): '],
        protectedReady: ['Testo protetto pronto da incollare in qualsiasi AI', 'Protected text ready to paste into any AI'],
        copyProtected: ['Copia il testo protetto', 'Copy the protected text'],
        sending: ['Invio a', 'Sending to'], waitingFirst: ['in attesa della risposta…', 'waiting for the answer…'],
        copy: ['Copia', 'Copy'], copied: ['Copiato', 'Copied'], copyCode: ['Copia codice', 'Copy code'],
        regenerate: ['Rigenera', 'Regenerate'], edit: ['Modifica', 'Edit'], showLabels: ['Mostra etichette', 'Show tags'], showRestored: ['Mostra dati ripristinati', 'Show restored data'],
        restoredFrom: ['Ripristinato da', 'Restored from'],
        badgeTime: ['tempo totale', 'total time'], badgeFirst: ['primo token', 'first token'], badgeTokens: ['token', 'tokens'], badgeWords: ['parole', 'words'], badgeWord1: ['parola', 'word'],
        badgeRestored: ['ripristinati', 'restored'], badgeRestored1: ['ripristinato', 'restored'], badgeMasked: ['oscurati', 'masked'], badgeMasked1: ['oscurato', 'masked'],
        abortedTitle: ['Operazione interrotta', 'Operation stopped'],
        abortedLocal: ['Operazione interrotta dall\'utente tramite Glass Window: nessun dato ulteriore è stato trasmesso o ricevuto.', 'Operation stopped by the user via Glass Window: no further data was transmitted or received.'],
        errorTitle: ['Richiesta non riuscita', 'Request failed'], blockedTitle: ['Richiesta bloccata: nessun dato è uscito', 'Request blocked: no data left'],
        netError: ['Germano non risponde: controlla che il programma (o il server) sia aperto.', 'Germano is not responding: check that the program (or the server) is open.'],
        startingEngine: ['Avvio del motore di protezione… La prima volta il caricamento dei modelli può richiedere qualche minuto: la richiesta parte da sola appena è pronto.', 'Starting the protection engine… The first time loading the models can take a few minutes: the request leaves by itself as soon as it is ready.'],
        engineFailed: ['Il motore non si è avviato: controlla le Impostazioni › Sistema e registro.', 'The engine did not start: check Settings › System & log.'],
        chooseAi: ['Scegli un\'AI in basso a destra.', 'Choose an AI at the bottom right.'],
        writeSomething: ['Scrivi un messaggio o allega un file.', 'Type a message or attach a file.'],
        maxFiles: ['Al massimo 12 allegati per richiesta.', 'At most 12 attachments per request.'],
        nonTextFile: ['Allegato senza testo (immagine o video): il suo contenuto non viene inviato. Per oscurare le immagini usa la scheda Sanitizzazione manuale.', 'Attachment without text (image or video): its content is not sent. To mask images use the Manual Sanitization tab.'],
        busy: ['Attendi la fine della richiesta in corso o interrompila.', 'Wait for the current request to finish or stop it.'],
        exportNote: ['Conversazione esportata da Germano AI', 'Conversation exported from Germano AI'],
        // Glass Window
        gwSub: ['Ispezione trasparente in tempo reale', 'Transparent real-time inspection'],
        gwClose: ['Chiudi la Glass Window', 'Close the Glass Window'],
        gwIdle: ['In attesa', 'Idle'], gwStarting: ['Avvio…', 'Starting…'], gwProtecting: ['Protezione con il motore di Germano…', 'Protecting with the Germano engine…'],
        gwReview: ['Revisione: in attesa della tua conferma', 'Review: waiting for your confirmation'], gwTransmitting: ['Invio al modello…', 'Sending to the model…'],
        gwStreaming: ['Ricezione della risposta in streaming…', 'Receiving the streamed answer…'], gwDone: ['Completata', 'Completed'],
        gwAborted: ['Interrotta dall\'utente', 'Stopped by the user'], gwError: ['Non riuscita', 'Failed'], gwPreview: ['Anteprima mentre scrivi', 'Preview while typing'],
        gwStop: ['Interrompi operazione', 'Stop operation'],
        gwStep1: ['Originale', 'Original'], gwStep2: ['Filtro privacy', 'Privacy filter'], gwStep3: ['Testo inviato', 'Sent text'], gwStep4: ['Payload', 'Payload'], gwStep5: ['Risposta', 'Answer'],
        gwSec1: ['Testo originale inserito', 'Original text entered'], gwSec2: ['Filtro di privacy Germano e corrispondenze del Vault', 'Germano privacy filter and Vault mappings'],
        gwSec3: ['Testo effettivo inviato al modello AI', 'Actual text sent to the AI model'], gwSec4: ['Payload HTTP / CLI grezzo', 'Raw HTTP / CLI payload'],
        gwSec5: ['Stream in tempo reale della risposta (prima del ripristino)', 'Real-time answer stream (before restoration)'],
        gwEmpty: ['Qui vedrai, passo per passo e in tempo reale, tutto ciò che Germano comunica al modello: testo originale, dati oscurati, testo inviato, payload esatto e risposta grezza. Puoi tenerla aperta mentre scrivi.', 'Here you will see, step by step and in real time, everything Germano sends to the model: original text, masked data, sent text, exact payload and raw answer. You can keep it open while typing.'],
        gwPrompt: ['Richiesta', 'Request'], gwSystem: ['Istruzioni', 'Instructions'], gwAttach: ['Allegati', 'Attachments'],
        gwHistory: ['turni precedenti della conversazione, ri-protetti a ogni invio', 'previous conversation turns, re-protected at every send'],
        gwNoEnt: ['Nessun dato personale rilevato in questa richiesta.', 'No personal data detected in this request.'],
        gwVaultNote: ['Etichette numerate e stabili: lo stesso dato ha sempre la stessa etichetta (Vault). Il ripristino usa solo le corrispondenze di questa richiesta.', 'Numbered, stable tags: the same data always gets the same tag (Vault). Restoration uses only the mappings of this request.'],
        gwOriginal: ['Originale', 'Original'], gwLabel: ['Etichetta', 'Tag'], gwCategory: ['Categoria', 'Category'], gwScore: ['Affidabilità', 'Confidence'],
        gwHistoryEnt: ['dati nella cronologia', 'data in the history'],
        gwS2: ['Sistema 2 · casi dubbi decisi nel contesto (modello locale)', 'System 2 · doubtful cases decided in context (local model)'],
        gwS2rel: ['rilasciato', 'released'],
        gwS2conf: ['confermato', 'confirmed'],
        gwS2kept: ['resta oscurato', 'kept masked'],
        gwS2note: ['Il Sistema 2 lascia in chiaro un dubbio solo se è sicuro che non sia un dato personale; nel dubbio resta oscurato.', 'System 2 leaves a doubtful item in clear only when it is sure it is not personal data; otherwise it stays masked.'],
        gwHint: ['istruzione di Germano sulle etichette', 'Germano instruction about tags'],
        gwCopy: ['Copia', 'Copy'], gwHeaders: ['Intestazioni (chiavi oscurate)', 'Headers (keys masked)'], gwBody: ['Corpo JSON', 'JSON body'],
        gwCli: ['Comando della CLI (nessun testo tra gli argomenti)', 'CLI command (no text among the arguments)'], gwEnv: ['Variabili impostate da Germano', 'Variables set by Germano'],
        gwStdin: ['Standard input (testo già protetto)', 'Standard input (already protected text)'],
        gwViaProxy: ['Payload HTTP inviato dalla CLI, catturato dal Proxy di Germano', 'HTTP payload sent by the CLI, captured by the Germano Proxy'],
        gwLocalOnly: ['Destinazione su questo computer: nessun dato esce dalla rete.', 'Destination on this computer: no data leaves the network.'],
        gwCloud: ['Destinazione esterna: esce solo il testo protetto mostrato qui.', 'External destination: only the protected text shown here leaves.'],
        gwChars: ['caratteri', 'characters'], gwTps: ['token/s', 'tokens/s'],
        gwThinking: ['Ragionamento esposto dal modello', 'Reasoning exposed by the model'], gwFrames: ['Frame SSE grezzi', 'Raw SSE frames'],
        gwCliLines: ['Messaggi della CLI', 'CLI messages'],
        gwOptPreview: ['Anteprima della protezione mentre scrivi', 'Protection preview while typing'], gwOptFrames: ['Frame SSE grezzi', 'Raw SSE frames'],
        gwOptHint: ['Istruzione sulle etichette', 'Instruction about tags'],
        gwPreviewNote: ['Anteprima: niente è stato inviato. Il testo completo (con allegati e cronologia) viene protetto di nuovo all\'invio.', 'Preview: nothing has been sent. The full text (with attachments and history) is protected again when sent.'],
        gwPreviewLong: ['Testo lungo: l\'anteprima si ferma qui, la protezione completa avviene all\'invio.', 'Long text: the preview stops here, full protection happens when sent.'],
        gwPreviewOff: ['Motore non pronto: l\'anteprima compare quando il motore è attivo.', 'Engine not ready: the preview appears when the engine is running.'],
        gwRun: ['Richiesta', 'Request'], gwLive: ['in corso', 'running'],
        gwStoppedBefore: ['Interrotta prima dell\'invio: nessun dato è stato trasmesso al servizio di AI.', 'Stopped before sending: no data was transmitted to the AI service.'],
        gwNotSent: ['Solo protezione: nessun invio a un modello.', 'Protection only: nothing sent to a model.'],
        gwWaitingPayload: ['Il payload compare qui prima dell\'invio.', 'The payload appears here before it is sent.'],
        gwWaitingStream: ['La risposta grezza, con le etichette, compare qui man mano che arriva.', 'The raw answer, with the tags, appears here as it arrives.'],
        gwDirect: ['Destinazione esterna raggiunta direttamente dalla CLI (non dal Proxy): esce solo il testo protetto mostrato qui, più le istruzioni interne della CLI.', 'External destination reached directly by the CLI (not through the Proxy): only the protected text shown here leaves, plus the CLI\'s internal instructions.'],
        // Assistente di configurazione (solo su questo computer)
        assistKicker: ['Assistente di configurazione', 'Configuration assistant'],
        assistTitle: ['Configura le AI di questo computer', 'Set up the AIs of this computer'],
        assistLoading: ['Controllo di questo computer…', 'Checking this computer…'],
        assistState: ['Stato', 'Status'], assistActions: ['Cosa può fare Germano', 'What Germano can do'], assistLinks: ['Pagine ufficiali', 'Official pages'],
        assistLog: ['Avanzamento', 'Progress'], assistCancel: ['Annulla', 'Cancel'], assistClose: ['Chiudi', 'Close'], assistGo: ['Esegui', 'Run'],
        assistRunning: ['In corso…', 'Running…'], assistDone: ['Completato', 'Completed'], assistError: ['Non riuscito', 'Failed'], assistCancelled: ['Annullato', 'Cancelled'],
        assistSafe: ['Le operazioni girano solo su questo computer, con comandi fissi e download verificati; le chiavi non vengono mai mostrate né copiate.', 'Operations run only on this computer, with fixed commands and verified downloads; keys are never shown or copied.'],
        assistOpen: ['Configura', 'Set up'], assistNothing: ['Nessuna azione necessaria.', 'No action needed.'],
        assistReady: ['pronto', 'ready'], assistTodo: ['da configurare', 'to set up'], assistFailed: ['L\'assistente non risponde.', 'The assistant does not respond.'],
    };
    const ICON = {
        plus: '<path d="M12 5v14M5 12h14"/>',
        search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/>',
        menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
        clip: '<path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>',
        send: '<path d="M12 19V5M5 12l7-7 7 7"/>',
        stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
        shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/>',
        glass: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 9h18"/><path d="M8 14l2.5 2.5L16 11"/>',
        eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
        copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
        check: '<path d="M20 6L9 17l-5-5"/>',
        x: '<path d="M18 6L6 18M6 6l12 12"/>',
        edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/>',
        trash: '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/>',
        refresh: '<path d="M23 4v6h-6"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
        download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>',
        sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
        bot: '<rect x="4" y="7" width="16" height="12" rx="3"/><path d="M12 7V4"/><circle cx="9" cy="13" r="1.2"/><circle cx="15" cy="13" r="1.2"/>',
        chevron: '<path d="M6 9l6 6 6-6"/>',
        alert: '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4M12 17h.01"/>',
        lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
        file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
        sparkle: '<path d="M12 3l1.8 4.6L18 9.5l-4.2 1.9L12 16l-1.8-4.6L6 9.5l4.2-1.9z"/><path d="M19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/>',
        key: '<circle cx="7.5" cy="15.5" r="4.5"/><path d="M10.7 12.3L21 2M16 7l3 3M14 9l2 2"/>',
        clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
        zap: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
        hash: '<line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/>',
    };
    const svg = (name, cls = 'hx-icon-svg') => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICON[name] || ''}</svg>`;
    const MAX_FILES = 12;
    // Allegati che il motore di Germano trasforma in testo (dalla 0.80): registrazioni audio (trascrizione offline)
    // e archivi compressi (testo dei documenti contenuti). Stesse estensioni di germano/formats/__init__.py.
    const AUDIO_EXT_RE = /\.(mp3|wav|m4a|ogg|oga|opus|flac|aac|wma|amr|aiff?|m4b|mka|weba)$/i;
    const ARCHIVE_EXT_RE = /\.(zip|tar|tgz|tbz2?|txz|gz|bz2|xz|7z|rar)$/i;
    function isAudioFile(f) { return Boolean(f) && (AUDIO_EXT_RE.test(f.name || '') || /^audio\//.test(f.type || '')); }
    function isArchiveFile(f) { return Boolean(f) && ARCHIVE_EXT_RE.test(f.name || ''); }
    const DETECT_MS = 12000;
    const KEY_RE = /^[\x21-\x7e]{8,512}$/;
    const TAG_RE = /\[\s*([A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ./]*(?:[ _]+[A-Za-zÀ-ÖØ-öø-ÿ./]+)*?)[ _]+(\d{1,7})\s*\]/g;

    // ------------------------------------------------------------------ utilita'
    function esc(v) {
        return String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
    function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 8); }
    function normTag(base, num) { return '[' + base.trim().replace(/[ _]+/g, '_').toUpperCase() + '_' + String(parseInt(num, 10)) + ']'; }
    function fmtBytes(n) {
        if (!n) return '0 B';
        const u = ['B', 'KB', 'MB', 'GB'];
        const i = Math.min(u.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
        return `${(n / Math.pow(1024, i)).toFixed(i ? 1 : 0)} ${u[i]}`;
    }
    function fmtSec(ms) { return ms == null ? '—' : (ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`); }
    function store(kind) { try { return kind === 'session' ? window.sessionStorage : window.localStorage; } catch (e) { return null; } }
    function load(kind, key, fallback) {
        try { const raw = store(kind)?.getItem(key); return raw ? JSON.parse(raw) : fallback; } catch (e) { return fallback; }
    }
    function save(kind, key, value) {
        try {
            const s = store(kind);
            if (!s) return false;
            if (value === undefined) s.removeItem(key); else s.setItem(key, JSON.stringify(value));
            return true;
        } catch (e) { return false; }
    }
    async function copyText(text) {
        try { if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true; } } catch (e) { /* metodo classico */ }
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.cssText = 'position:fixed;top:-1000px;opacity:0';
        document.body.append(ta);
        ta.select();
        let ok = false;
        try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
        ta.remove();
        return ok;
    }
    // Colore stabile per categoria di dato (Glass Window, etichette nella conversazione)
    const CAT_COLORS = [[/PERSON|NOME/, 0], [/INDIRIZZ|LUOG|ADDRESS|CATAST/, 1], [/FISCAL|P\.IVA|IVA|TAX/, 2], [/EMAIL|PEC/, 3],
        [/TELEF|PHONE|IMEI/, 4], [/CONTO|CARTA|IBAN|CARD|ACCOUNT/, 5], [/DATA|DATE|ETA/, 6], [/AZIEND|ENTE|ORG/, 7],
        [/SANIT|FARMAC|MEDIC|HEALTH/, 8], [/GIUDIZ|LEGAL/, 9], [/SEGRET|PASSWORD|SECRET|PIN/, 10], [/URL|IP|MAC/, 11]];
    function catColor(cat) {
        const c = String(cat || '').toUpperCase();
        for (const [re, n] of CAT_COLORS) if (re.test(c)) return 'c-' + n;
        let h = 0;
        for (const ch of c) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
        return 'c-' + (h % 12);
    }
    function labelCat(label) { const m = /^\[\s*(.+?)(?:[ _]+\d{1,7})?\s*\]$/.exec(String(label || '')); return (m ? m[1] : String(label || '')).trim().toUpperCase(); }

    // ------------------------------------------------------------------ evidenziazione del codice
    const KW = {
        js: 'abstract async await boolean break case catch class const continue debugger default delete do else enum export extends false finally for from function get if implements import in instanceof interface let new null of package private protected public return set static super switch this throw true try type typeof undefined var void while with yield',
        py: 'and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return self True try while with yield print',
        sh: 'if then else elif fi for in do done while until case esac function return export local echo exit set unset source alias cd sudo apt pip npm git curl',
        ps: 'function param begin process end if elseif else foreach for while do switch return try catch finally throw break continue exit trap Write-Host Get-ChildItem Set-Location New-Item Remove-Item',
        sql: 'select from where and or not insert into values update set delete create table drop alter index join left right inner outer on group by order having limit offset as distinct union all null is in like between case when then else end primary key foreign references',
        c: 'auto break case char const continue default do double else enum extern float for goto if inline int long register return short signed sizeof static struct switch typedef union unsigned void volatile while class public private protected namespace using template typename new delete true false nullptr bool string var func fn let mut impl trait pub use mod match struct enum package import go defer chan select interface map range type val fun object when',
    };
    const LANG_MAP = { javascript: 'js', js: 'js', ts: 'js', typescript: 'js', jsx: 'js', tsx: 'js', json: 'json', python: 'py', py: 'py',
        bash: 'sh', sh: 'sh', shell: 'sh', zsh: 'sh', console: 'sh', powershell: 'ps', ps1: 'ps', pwsh: 'ps', sql: 'sql',
        html: 'html', xml: 'html', svg: 'html', css: 'css', c: 'c', cpp: 'c', 'c++': 'c', cs: 'c', csharp: 'c', java: 'c', go: 'c', rust: 'c',
        rs: 'c', kotlin: 'c', kt: 'c', swift: 'c', php: 'c', yaml: 'yaml', yml: 'yaml', toml: 'yaml', ini: 'yaml', dockerfile: 'sh', md: '', markdown: '' };
    function highlight(code, lang) {
        const fam = LANG_MAP[(lang || '').toLowerCase()] ?? '';
        if (!fam) return esc(code);
        let rules;
        if (fam === 'json') {
            rules = [[/"(?:\\.|[^"\\])*"(?=\s*:)/y, 'hl-key'], [/"(?:\\.|[^"\\])*"/y, 'hl-str'], [/-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b/y, 'hl-num'], [/\b(?:true|false|null)\b/y, 'hl-lit']];
        } else if (fam === 'html') {
            rules = [[/<!--[\s\S]*?-->/y, 'hl-com'], [/<\/?[A-Za-z][\w:-]*/y, 'hl-tag'], [/\s[\w:-]+(?==)/y, 'hl-attr'], [/"[^"]*"|'[^']*'/y, 'hl-str'], [/\/?>/y, 'hl-tag']];
        } else if (fam === 'css') {
            rules = [[/\/\*[\s\S]*?\*\//y, 'hl-com'], [/"[^"]*"|'[^']*'/y, 'hl-str'], [/#[0-9a-fA-F]{3,8}\b/y, 'hl-num'], [/-?\b\d+(?:\.\d+)?(?:px|em|rem|%|vh|vw|s|ms)?\b/y, 'hl-num'], [/[\w-]+(?=\s*:)/y, 'hl-attr'], [/[.#]?[A-Za-z_][\w-]*(?=[^{}]*\{)/y, 'hl-tag']];
        } else if (fam === 'yaml') {
            rules = [[/#.*/y, 'hl-com'], [/^[ \t-]*[\w.-]+(?=\s*[:=])/my, 'hl-key'], [/"(?:\\.|[^"\\])*"|'[^']*'/y, 'hl-str'], [/\b(?:true|false|null|yes|no|on|off)\b/y, 'hl-lit'], [/-?\b\d+(?:\.\d+)?\b/y, 'hl-num']];
        } else {
            const words = KW[fam] || KW.c;
            const kw = new RegExp('\\b(?:' + words.split(' ').map(w => w.replace(/[-]/g, '\\-')).join('|') + ')\\b', fam === 'sql' || fam === 'ps' ? 'iy' : 'y');
            const comment = fam === 'py' || fam === 'sh' || fam === 'ps' ? /#.*/y : fam === 'sql' ? /--.*|\/\*[\s\S]*?\*\//y : /\/\/.*|\/\*[\s\S]*?\*\//y;
            rules = [[comment, 'hl-com'], [/`(?:\\.|[^`\\])*`|"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'/y, 'hl-str'],
                     [kw, 'hl-kw'], [/\b0x[0-9a-fA-F]+\b|-?\b\d+(?:\.\d+)?\b/y, 'hl-num'], [/\$[\w{][\w}]*/y, 'hl-var'], [/\b[A-Za-z_][\w]*(?=\s*\()/y, 'hl-fn']];
        }
        let out = '', i = 0, plain = '';
        while (i < code.length) {
            let hit = null;
            for (const [re, cls] of rules) {
                re.lastIndex = i;
                const m = re.exec(code);
                if (m && m.index === i && m[0].length) { hit = [m[0], cls]; break; }
            }
            if (hit) {
                if (plain) { out += esc(plain); plain = ''; }
                out += `<span class="${hit[1]}">${esc(hit[0])}</span>`;
                i += hit[0].length;
            } else {
                plain += code[i];
                i += 1;
            }
        }
        return out + esc(plain);
    }

    // ------------------------------------------------------------------ Markdown sicuro
    // I segnaposti \uE000n\uE001 marcano i dati ripristinati (o le etichette): sopravvivono all'escape e diventano span.
    function inline(text) {
        const codes = [];
        let s = text.replace(/`([^`\n]+)`/g, (m, c) => { codes.push(c); return `\uE010${codes.length - 1}\uE011`; });
        s = esc(s);
        s = s.replace(/!\[([^\]\n]*)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)/g, (m, alt) => `<span class="hx-img">[🖼 ${alt || 'immagine'}]</span>`);
        s = s.replace(/\[([^\]\n]+)\]\(([^)\s]+)\)/g, (m, label, url) => {
            const u = url.replace(/&amp;/g, '&');
            if (!/^(https?:|mailto:)/i.test(u)) return label;
            return `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer nofollow" title="${esc(u)}">${label}</a>`;
        });
        s = s.replace(/(^|[\s(])((?:https?:\/\/)[^\s<>"']+[^\s<>"'.,;:!?)])/g, (m, pre, url) => {
            const u = url.replace(/&amp;/g, '&');
            return `${pre}<a href="${esc(u)}" target="_blank" rel="noopener noreferrer nofollow">${url}</a>`;
        });
        s = s.replace(/\*\*([^*\n]+)\*\*|__([^_\n]+)__/g, (m, a, b) => `<strong>${a || b}</strong>`);
        s = s.replace(/(^|[^\w*])\*([^*\n]+)\*(?!\w)|(^|[^\w])_([^_\n]+)_(?!\w)/g, (m, p1, a, p2, b) => `${p1 ?? p2 ?? ''}<em>${a || b}</em>`);
        s = s.replace(/~~([^~\n]+)~~/g, '<del>$1</del>');
        s = s.replace(/\uE010(\d+)\uE011/g, (m, n) => `<code>${esc(codes[+n])}</code>`);
        return s;
    }
    function renderMarkdown(src) {
        const lines = String(src || '').replace(/\r\n?/g, '\n').split('\n');
        const out = [];
        let i = 0;
        const isFence = l => /^\s{0,3}(```|~~~)/.test(l);
        const isTableSep = l => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l);
        const splitRow = l => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim());
        while (i < lines.length) {
            const line = lines[i];
            if (isFence(line)) {
                const fence = line.trim().slice(0, 3);
                const lang = line.trim().slice(3).trim().split(/\s+/)[0] || '';
                const body = [];
                i += 1;
                while (i < lines.length && !lines[i].trim().startsWith(fence)) { body.push(lines[i]); i += 1; }
                i += 1;
                const code = body.join('\n');
                out.push(`<div class="hx-code"><div class="hx-code-head"><span>${esc(lang || 'testo')}</span>` +
                    `<button type="button" class="hx-copy-code" data-copy-code>${svg('copy')}<span data-t="copyCode"></span></button></div>` +
                    `<pre><code>${highlight(code, lang)}</code></pre></div>`);
                continue;
            }
            if (!line.trim()) { i += 1; continue; }
            let m = /^\s{0,3}(#{1,6})\s+(.*)$/.exec(line);
            if (m) { out.push(`<h${m[1].length}>${inline(m[2].replace(/\s#+\s*$/, ''))}</h${m[1].length}>`); i += 1; continue; }
            if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line)) { out.push('<hr>'); i += 1; continue; }
            if (/^\s{0,3}>/.test(line)) {
                const quote = [];
                while (i < lines.length && /^\s{0,3}>/.test(lines[i])) { quote.push(lines[i].replace(/^\s{0,3}>\s?/, '')); i += 1; }
                out.push(`<blockquote>${renderMarkdown(quote.join('\n'))}</blockquote>`);
                continue;
            }
            if (line.includes('|') && i + 1 < lines.length && isTableSep(lines[i + 1])) {
                const head = splitRow(line);
                i += 2;
                const rows = [];
                while (i < lines.length && lines[i].includes('|') && lines[i].trim()) { rows.push(splitRow(lines[i])); i += 1; }
                out.push('<table><thead><tr>' + head.map(h => `<th>${inline(h)}</th>`).join('') + '</tr></thead><tbody>' +
                    rows.map(r => '<tr>' + head.map((_, k) => `<td>${inline(r[k] || '')}</td>`).join('') + '</tr>').join('') + '</tbody></table>');
                continue;
            }
            m = /^(\s*)([-*+]|\d{1,3}[.)])\s+(.*)$/.exec(line);
            if (m) {
                const ordered = /\d/.test(m[2]);
                const base = m[1].length;
                const items = [];
                while (i < lines.length) {
                    const mm = /^(\s*)([-*+]|\d{1,3}[.)])\s+(.*)$/.exec(lines[i]);
                    if (mm && mm[1].length <= base + 1) { items.push({ text: mm[3], sub: [] }); i += 1; continue; }
                    if (mm && items.length) { items[items.length - 1].sub.push(lines[i].slice(base + 2)); i += 1; continue; }
                    if (lines[i].trim() && /^\s{2,}/.test(lines[i]) && items.length) { items[items.length - 1].sub.push(lines[i].trim()); i += 1; continue; }
                    break;
                }
                const tag = ordered ? 'ol' : 'ul';
                const start = ordered ? parseInt(m[2], 10) : 1;
                out.push(`<${tag}${ordered && start !== 1 ? ` start="${start}"` : ''}>` + items.map(it => {
                    const task = /^\[([ xX])\]\s+(.*)$/.exec(it.text);
                    const body = task ? `${task[1] === ' ' ? '☐' : '☑'} ${inline(task[2])}` : inline(it.text);
                    const sub = it.sub.length ? renderMarkdown(it.sub.join('\n')) : '';
                    return `<li>${body}${sub}</li>`;
                }).join('') + `</${tag}>`);
                continue;
            }
            const para = [];
            while (i < lines.length && lines[i].trim() && !isFence(lines[i]) && !/^\s{0,3}(#{1,6}\s|>|([-*+]|\d{1,3}[.)])\s)/.test(lines[i])
                   && !(lines[i].includes('|') && i + 1 < lines.length && isTableSep(lines[i + 1]))) {
                para.push(lines[i]);
                i += 1;
            }
            if (!para.length) { para.push(lines[i]); i += 1; }
            out.push(`<p>${para.map(inline).join('<br>')}</p>`);
        }
        return out.join('');
    }
    // Testo protetto + mappa -> HTML con i dati ripristinati evidenziati (oppure con le etichette, se richiesto)
    function renderAnswer(protectedText, map, showLabels, lang) {
        const marks = [];
        const keyed = String(protectedText || '').replace(TAG_RE, (m, base, num) => {
            const key = normTag(base, num);
            if (!map || !Object.prototype.hasOwnProperty.call(map, key)) return m;
            marks.push([key, map[key]]);
            return `\uE000${marks.length - 1}\uE001`;
        });
        let html = renderMarkdown(keyed);
        html = html.replace(/\uE000(\d+)\uE001/g, (m, n) => {
            const [label, value] = marks[+n];
            const cls = catColor(labelCat(label));
            if (showLabels) return `<span class="hx-label-inline ${cls}" title="${esc(value)}">${esc(label)}</span>`;
            return `<span class="hx-restored" title="${esc((lang === 'en' ? 'Restored from ' : 'Ripristinato da ') + label)}">${esc(value)}</span>`;
        });
        return html;
    }
    function restorePlain(text, map) {
        return String(text || '').replace(TAG_RE, (m, base, num) => {
            const key = normTag(base, num);
            return map && Object.prototype.hasOwnProperty.call(map, key) ? map[key] : m;
        });
    }
    function highlightLabels(text) {
        return esc(text).replace(/\[[A-ZÀ-Ý][A-ZÀ-Ý0-9./_ ]{0,48}?_\d{1,7}\]/g, m => `<span class="gw-label ${catColor(labelCat(m))}">${m}</span>`);
    }

    // ------------------------------------------------------------------ componente
    class Harness {
        constructor(root, opts) {
            this.root = root;
            this.o = Object.assign({ host: 'suite', lang: () => 'it', keysKey: 'germano_keys', convKey: 'germano_harness_v1',
                                     persistDefault: true, canStartEngine: false, toast: null, options: () => null,
                                     onAuthRequired: null, engine: null }, opts || {});
            this.remote = this.o.host !== 'suite';
            this.prefs = Object.assign({ persist: this.o.persistDefault, review: false, preview: true, frames: false, hint: true, side: true },
                                       load('local', this.o.convKey + '_prefs', {}));
            this.convs = this.loadConvs();
            this.currentId = this.convs[0] ? this.convs[0].id : null;
            this.files = [];
            this.targets = null;
            this.meta = {};
            this.targetSig = '';
            this.runs = [];
            this.glassRun = null;
            this.follow = true;
            this.active = null;
            this.preview = null;
            this.renderQueued = false;
            this.build();
            this.renderAll();
            this.refreshTargets(false);
            this.timer = setInterval(() => { if (!document.hidden) this.refreshTargets(false); }, DETECT_MS);
            document.addEventListener('visibilitychange', () => { if (!document.hidden) this.refreshTargets(false); });
            window.addEventListener('focus', () => this.refreshTargets(false));
        }

        T(key) { const s = S[key]; return s ? (this.o.lang() === 'en' ? s[1] : s[0]) : key; }
        get lang() { return this.o.lang() === 'en' ? 'en' : 'it'; }
        toast(msg, type = 'info') { if (this.o.toast) this.o.toast(msg, type); }

        // -------------------------------------------------------------- conversazioni (archivio locale)
        convStore() { return this.prefs.persist ? 'local' : 'session'; }
        loadConvs() {
            const list = load(this.prefs.persist ? 'local' : 'session', this.o.convKey, []);
            return Array.isArray(list) ? list.filter(c => c && c.id && Array.isArray(c.messages)) : [];
        }
        saveConvs() {
            const keep = this.convs.filter(c => !c.temporary && c.messages.length);
            let list = keep.slice(0, 100).map(c => Object.assign({}, c, { messages: c.messages.slice(-240).map(m => {
                const x = Object.assign({}, m);
                delete x.live;
                if (x.status === 'streaming' || x.status === 'waiting') x.status = 'aborted';
                return x;
            }) }));
            let json = JSON.stringify(list);
            while (json.length > 4_500_000 && list.length > 1) { list = list.slice(0, -1); json = JSON.stringify(list); }
            save(this.convStore(), this.o.convKey, list);
            save(this.prefs.persist ? 'session' : 'local', this.o.convKey, undefined);
        }
        savePrefs() { save('local', this.o.convKey + '_prefs', this.prefs); }
        setPref(name, value) {
            this.prefs[name] = Boolean(value);
            this.savePrefs();
            const box = { review: this.$review, preview: this.$optPreview, frames: this.$optFrames, hint: this.$optHint, persist: this.$persist }[name];
            if (box) box.checked = this.prefs[name];
            if (name === 'persist') this.saveConvs();
            this.renderAll();
            this.renderGlass();
        }
        get conv() { return this.convs.find(c => c.id === this.currentId) || null; }
        newConversation(focus = true) {
            if (this.active) { this.toast(this.T('busy'), 'warn'); return; }
            const cur = this.conv;
            if (cur && !cur.messages.length) { this.currentId = cur.id; }
            else {
                const c = { id: uid(), title: '', created: Date.now(), updated: Date.now(), messages: [], system: '' };
                this.convs.unshift(c);
                this.currentId = c.id;
            }
            this.renderAll();
            if (focus) this.$input.focus();
        }
        ensureConv() {
            if (!this.conv) {
                const c = { id: uid(), title: '', created: Date.now(), updated: Date.now(), messages: [], system: '' };
                this.convs.unshift(c);
                this.currentId = c.id;
            }
            return this.conv;
        }

        // -------------------------------------------------------------- struttura della pagina
        build() {
            const r = this.root;
            r.classList.add('hx');
            r.dataset.glass = 'closed';
            r.dataset.side = this.prefs.side ? 'open' : 'closed';
            r.innerHTML = `
<aside class="hx-side" aria-label="Conversazioni"><div class="hx-side-inner">
  <div class="hx-side-head"><button type="button" class="hx-new" data-act="new">${svg('plus')}<span data-t="newChat"></span></button></div>
  <div class="hx-search">${svg('search')}<input type="search" data-ref="search" data-t-ph="search" data-t-aria="search"></div>
  <nav class="hx-convs" data-ref="convs"></nav>
  <div class="hx-side-foot"><label><input type="checkbox" data-ref="persist"><span data-t="keepDevice"></span></label>
    <span data-ref="persistNote"></span><button type="button" data-act="clear-all" data-t="clearAll"></button></div>
</div></aside>
<section class="hx-main">
  <header class="hx-head">
    <button type="button" class="hx-btn-icon" data-act="side" data-t-title="sidebar" data-t-aria="sidebar">${svg('menu')}</button>
    <div class="hx-title" data-ref="title"></div>
    <div class="hx-head-actions">
      <button type="button" class="hx-chip-btn" data-act="system" data-t-title="systemTitle">${svg('sliders')}<span data-t="system"></span></button>
      <button type="button" class="hx-chip-btn" data-act="export" data-t-title="exportTitle">${svg('download')}<span data-t="export"></span></button>
      <button type="button" class="hx-glass-btn" data-act="glass" aria-pressed="false" data-t-title="glassTitle" data-ref="glassBtn">
        ${svg('glass', 'hx-icon-svg gw-glyph')}<span data-t="glass"></span><span class="gw-live"></span></button>
    </div>
  </header>
  <div class="hx-timeline" data-ref="timeline" role="log" aria-live="polite" aria-relevant="additions">
    <div class="hx-empty" data-ref="empty"></div>
    <div class="hx-thread" data-ref="thread"></div>
  </div>
  <footer class="hx-composer-wrap"><div class="hx-composer-inner">
    <div class="hx-system-bar" data-ref="systemBar" hidden><label><span data-t="systemTitle"></span>
      <button type="button" class="hx-btn-icon" data-act="system" style="width:24px;height:24px">${svg('x')}</button></label>
      <textarea data-ref="system" data-t-ph="systemPh" maxlength="20000"></textarea></div>
    <div class="hx-composer" data-ref="composer">
      <div class="hx-attachments" data-ref="attachments"></div>
      <textarea class="hx-input" data-ref="input" rows="1" data-t-ph="placeholder" aria-label="Prompt"></textarea>
      <div class="hx-bar">
        <div class="hx-bar-left">
          <button type="button" class="hx-btn-icon" data-act="attach" data-t-title="attach" data-t-aria="attach">${svg('clip')}</button>
          <input type="file" data-ref="file" multiple hidden>
          <span class="hx-shield" data-ref="shield"></span>
          <label class="hx-toggle" data-ref="reviewToggle" data-t-title="reviewTitle"><input type="checkbox" data-ref="review"><span class="hx-toggle-text" data-t="review"></span></label>
        </div>
        <div class="hx-bar-right">
          <div class="hx-picker" data-ref="picker">
            <button type="button" class="hx-picker-btn" data-act="picker" aria-haspopup="listbox" aria-expanded="false" data-t-title="pickTitle" data-ref="pickerBtn">
              <span class="hx-dot" data-ref="pickerDot"></span><span class="hx-picker-name" data-ref="pickerName"></span>${svg('chevron')}</button>
            <div class="hx-picker-pop" data-ref="pickerPop" hidden>
              <div class="hx-picker-top"><input type="search" data-ref="pickerSearch" data-t-ph="pickSearch"></div>
              <ul class="hx-picker-list" role="listbox" data-ref="pickerList"></ul>
              <div class="hx-picker-detail" data-ref="pickerDetail"></div>
              <div class="hx-picker-foot"><span data-t="autoDetect"></span>
                <button type="button" class="hx-mini" data-act="redetect">${svg('refresh')}<span data-t="redetect"></span></button></div>
            </div>
          </div>
          <button type="button" class="hx-send" data-ref="send" data-act="send" data-t-title="send" data-t-aria="send">${svg('send')}</button>
        </div>
      </div>
      <div class="hx-drop-overlay">${svg('clip')}<span data-t="drop"></span></div>
    </div>
    <div class="hx-hint"><span class="hx-hint-keys" data-t="hintKeys"></span><span data-ref="hintSafe"></span></div>
  </div></footer>
</section>
<aside class="hx-glass" aria-label="Glass Window" data-ref="glass"><div class="gw-inner">
  <header class="gw-head">
    <div class="gw-title"><strong>${svg('glass')}<span data-t="glass"></span></strong><span data-t="gwSub"></span></div>
    <select class="gw-run-select" data-ref="runSelect" aria-label="Richiesta"></select>
    <button type="button" class="hx-btn-icon" data-act="glass" data-t-title="gwClose" data-t-aria="gwClose">${svg('x')}</button>
  </header>
  <div class="gw-status">
    <span class="gw-state"><span class="hx-dot" data-ref="gwDot"></span><span class="gw-state-text" data-ref="gwState"></span></span>
    <span class="gw-timer" data-ref="gwTimer"></span>
    <button type="button" class="gw-stop" data-act="stop" data-ref="gwStop" disabled>${svg('stop')}<span data-t="gwStop"></span></button>
  </div>
  <div class="gw-pipeline" data-ref="pipeline"></div>
  <div class="gw-review" data-ref="gwReview" hidden></div>
  <div class="gw-body" data-ref="gwBody"></div>
  <footer class="gw-foot">
    <label><input type="checkbox" data-ref="optPreview"><span data-t="gwOptPreview"></span></label>
    <label><input type="checkbox" data-ref="optFrames"><span data-t="gwOptFrames"></span></label>
    <label><input type="checkbox" data-ref="optHint"><span data-t="gwOptHint"></span></label>
  </footer>
</div></aside>`;
            r.querySelectorAll('[data-ref]').forEach(el => { this['$' + el.dataset.ref] = el; });
            this.bind();
            this.applyLang();
        }

        applyLang() {
            const r = this.root;
            r.querySelectorAll('[data-t]').forEach(el => { el.textContent = this.T(el.dataset.t); });
            r.querySelectorAll('[data-t-ph]').forEach(el => { el.placeholder = this.T(el.dataset.tPh); });
            r.querySelectorAll('[data-t-title]').forEach(el => { el.title = this.T(el.dataset.tTitle); });
            r.querySelectorAll('[data-t-aria]').forEach(el => { el.setAttribute('aria-label', this.T(el.dataset.tAria)); });
        }
        setLang() { this.applyLang(); this.renderAll(); this.renderPicker(); this.renderGlass(); }

        bind() {
            const r = this.root;
            r.addEventListener('click', e => this.onClick(e));
            this.$input.addEventListener('input', () => { this.autosize(); this.schedulePreview(); this.updateSend(); });
            this.$input.addEventListener('keydown', e => {
                if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); this.submit(); }
            });
            this.$input.addEventListener('paste', e => {
                const files = Array.from(e.clipboardData?.files || []);
                if (files.length) { e.preventDefault(); this.addFiles(files); }
            });
            this.$file.addEventListener('change', () => { this.addFiles(Array.from(this.$file.files || [])); this.$file.value = ''; });
            this.$search.addEventListener('input', () => this.renderConvs());
            this.$persist.checked = Boolean(this.prefs.persist);
            this.$persist.addEventListener('change', () => {
                this.prefs.persist = this.$persist.checked;
                this.savePrefs();
                this.saveConvs();
                this.renderConvs();
            });
            this.$review.checked = Boolean(this.prefs.review);
            this.$review.addEventListener('change', () => { this.prefs.review = this.$review.checked; this.savePrefs(); this.renderShield(); });
            this.$optPreview.checked = Boolean(this.prefs.preview);
            this.$optFrames.checked = Boolean(this.prefs.frames);
            this.$optHint.checked = Boolean(this.prefs.hint);
            this.$optPreview.addEventListener('change', () => { this.prefs.preview = this.$optPreview.checked; this.savePrefs(); this.schedulePreview(); this.renderGlass(); });
            this.$optFrames.addEventListener('change', () => { this.prefs.frames = this.$optFrames.checked; this.savePrefs(); });
            this.$optHint.addEventListener('change', () => { this.prefs.hint = this.$optHint.checked; this.savePrefs(); });
            this.$system.addEventListener('input', () => {
                const c = this.conv;
                if (c) { c.system = this.$system.value; this.saveConvs(); }
            });
            this.$title.addEventListener('dblclick', () => this.renameConv(this.currentId));
            this.$runSelect.addEventListener('change', () => {
                const run = this.runs.find(x => x.key === this.$runSelect.value);
                this.glassRun = run || null;
                this.follow = !run || run === this.runs[this.runs.length - 1];
                this.renderGlass();
            });
            this.$pickerSearch.addEventListener('input', () => this.renderPicker());
            this.$pickerSearch.addEventListener('keydown', e => this.pickerKey(e));
            document.addEventListener('mousedown', e => {
                if (!this.$pickerPop.hidden && !this.$picker.contains(e.target)) this.closePicker();
            });
            document.addEventListener('keydown', e => {
                if (e.key === 'Escape' && !this.$pickerPop.hidden) { this.closePicker(); this.$pickerBtn.focus(); }
                if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'G' || e.key === 'g') && this.visible()) { e.preventDefault(); this.toggleGlass(); }
            });
            // trascinamento di file sull'Harness
            let depth = 0;
            const hasFiles = e => Array.from(e.dataTransfer?.types || []).includes('Files');
            const main = r.querySelector('.hx-main');
            main.addEventListener('dragenter', e => { if (!hasFiles(e)) return; e.preventDefault(); depth += 1; r.classList.add('is-dragover'); });
            main.addEventListener('dragover', e => { if (!hasFiles(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
            main.addEventListener('dragleave', e => { if (!hasFiles(e)) return; depth = Math.max(0, depth - 1); if (!depth) r.classList.remove('is-dragover'); });
            main.addEventListener('drop', async e => {
                if (!hasFiles(e)) return;
                e.preventDefault();
                e.stopPropagation();
                depth = 0;
                r.classList.remove('is-dragover');
                this.addFiles(await filesFromDrop(e.dataTransfer));
            });
            this.timeTimer = setInterval(() => this.tick(), 100);
        }

        visible() { return this.root.offsetParent !== null; }

        onClick(e) {
            const t = e.target.closest('[data-act], [data-copy-code], [data-conv], [data-pick], [data-run], [data-key-for], [data-assist-for]');
            if (!t || !this.root.contains(t)) return;
            if (t.dataset.assistFor) { e.stopPropagation(); this.openAssist(t.dataset.assistFor); return; }
            if (t.dataset.copyCode !== undefined) {
                const code = t.closest('.hx-code')?.querySelector('pre')?.textContent || '';
                copyText(code).then(ok => {
                    if (!ok) return;
                    t.classList.add('is-done');
                    const label = t.querySelector('span');
                    if (label) label.textContent = this.T('copied');
                    setTimeout(() => { t.classList.remove('is-done'); if (label) label.textContent = this.T('copyCode'); }, 1600);
                });
                return;
            }
            if (t.dataset.conv && !t.dataset.act) { this.selectConv(t.dataset.conv); return; }
            if (t.dataset.keyFor) { e.stopPropagation(); this.openKeyForm(t.dataset.keyFor); return; }
            if (t.dataset.pick !== undefined && !t.dataset.act) { this.choose(t.dataset.pick); return; }
            const act = t.dataset.act;
            const mid = t.closest('[data-mid]')?.dataset.mid;
            switch (act) {
                case 'new': this.newConversation(); break;
                case 'side': this.prefs.side = this.root.dataset.side !== 'open'; this.root.dataset.side = this.prefs.side ? 'open' : 'closed'; this.savePrefs(); break;
                case 'system': this.toggleSystem(); break;
                case 'export': this.exportConv(); break;
                case 'glass': this.toggleGlass(); break;
                case 'attach': this.$file.click(); break;
                case 'send': if (this.active) this.stop(); else this.submit(); break;
                case 'stop': this.stop(); break;
                case 'picker': this.togglePicker(); break;
                case 'redetect': this.refreshTargets(true); break;
                case 'clear-all': this.clearAll(); break;
                case 'rename-conv': e.stopPropagation(); this.renameConv(t.dataset.conv); break;
                case 'delete-conv': e.stopPropagation(); this.deleteConv(t.dataset.conv); break;
                case 'rm-file': this.files.splice(+t.dataset.i, 1); this.renderFiles(); this.updateSend(); break;
                case 'suggest': this.$input.value = t.textContent; this.autosize(); this.$input.focus(); this.updateSend(); break;
                case 'copy-msg': this.copyMessage(mid, t); break;
                case 'regen': this.regenerate(mid); break;
                case 'edit-msg': this.editMessage(mid); break;
                case 'labels': this.toggleLabels(mid); break;
                case 'open-run': this.openRun(t.dataset.run); break;
                case 'approve': this.approve(); break;
                case 'block': this.stop(); break;
                case 'copy-protected': this.copyProtected(mid, t); break;
                case 'start-engine': this.startEngineNow(); break;
                case 'gw-sec': { const sec = t.closest('.gw-sec'); if (sec) sec.dataset.open = sec.dataset.open === 'false' ? 'true' : 'false'; break; }
                case 'gw-jump': {
                    const sec = this.$gwBody.querySelector(`.gw-sec[data-sec="${(+t.dataset.sec || 0) + 1}"]`);
                    if (sec) { sec.dataset.open = 'true'; sec.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
                    break;
                }
                case 'gw-copy': this.copyGlass(t.dataset.what, t); break;
                case 'key-save': this.saveKeyForm(t.dataset.service); break;
                case 'key-remove': this.setKey(t.dataset.service, ''); this.renderPicker(); this.openKeyForm(t.dataset.service); break;
                case 'list-models': this.listModels(t.dataset.service); break;
                case 'model-set': break;
                default: break;
            }
        }

        // -------------------------------------------------------------- rendering generale
        renderAll() {
            this.renderConvs();
            this.renderThread();
            this.renderShield();
            this.renderFiles();
            this.updateSend();
            const c = this.conv;
            this.$system.value = c ? (c.system || '') : '';
            this.$systemBar.hidden = !(c && c.system && c.showSystem !== false && this.systemOpen);
            this.$hintSafe.textContent = this.T(this.remote ? 'hintSafeRemote' : 'hintSafe');
            this.$persistNote.textContent = this.prefs.persist ? '' : this.T('keepSession');
        }

        renderConvs() {
            const q = (this.$search.value || '').trim().toLowerCase();
            const list = this.convs.filter(c => c.messages.length || c.id === this.currentId)
                .filter(c => !q || (c.title || '').toLowerCase().includes(q) || c.messages.some(m => (m.text || '').toLowerCase().includes(q)));
            if (!list.length) {
                this.$convs.innerHTML = `<div class="hx-side-empty">${esc(this.T(q ? 'noMatch' : 'noConvs'))}</div>`;
                return;
            }
            const now = new Date();
            const day0 = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
            const groups = [['today', c => c.updated >= day0], ['yesterday', c => c.updated >= day0 - 86400000],
                            ['week', c => c.updated >= day0 - 6 * 86400000], ['older', () => true]];
            const used = new Set();
            let html = '';
            groups.forEach(([key, test]) => {
                const items = list.filter(c => !used.has(c.id) && test(c)).sort((a, b) => b.updated - a.updated);
                if (!items.length) return;
                items.forEach(c => used.add(c.id));
                html += `<div class="hx-group-label">${esc(this.T(key))}</div>`;
                html += items.map(c => `<button type="button" class="hx-conv${c.id === this.currentId ? ' is-active' : ''}" data-conv="${esc(c.id)}">
                    <span class="hx-conv-title">${esc(c.title || this.T('untitled'))}</span>
                    ${c.temporary ? `<span class="hx-conv-temp">${esc(this.T('temporary'))}</span>` : ''}
                    <span class="hx-conv-actions">
                      <span class="hx-conv-act" role="button" data-act="rename-conv" data-conv="${esc(c.id)}" title="${esc(this.T('rename'))}">${svg('edit')}</span>
                      <span class="hx-conv-act" role="button" data-act="delete-conv" data-conv="${esc(c.id)}" title="${esc(this.T('del'))}">${svg('trash')}</span>
                    </span></button>`).join('');
            });
            this.$convs.innerHTML = html;
        }

        selectConv(id) {
            if (this.active) { this.toast(this.T('busy'), 'warn'); return; }
            this.currentId = id;
            this.renderAll();
            if (window.innerWidth <= 1180) { this.root.dataset.side = 'closed'; }
        }
        renameConv(id) {
            const c = this.convs.find(x => x.id === id);
            if (!c) return;
            const name = window.prompt(this.T('rename'), c.title || '');
            if (name === null) return;
            c.title = name.trim().slice(0, 120);
            this.saveConvs();
            this.renderAll();
        }
        deleteConv(id) {
            if (this.active && id === this.currentId) { this.toast(this.T('busy'), 'warn'); return; }
            if (!window.confirm(this.T('confirmDelete'))) return;
            this.convs = this.convs.filter(c => c.id !== id);
            if (this.currentId === id) this.currentId = this.convs[0] ? this.convs[0].id : null;
            this.saveConvs();
            this.renderAll();
        }
        clearAll() {
            if (this.active) { this.toast(this.T('busy'), 'warn'); return; }
            if (!window.confirm(this.T('confirmClearAll'))) return;
            this.convs = [];
            this.currentId = null;
            save('local', this.o.convKey, undefined);
            save('session', this.o.convKey, undefined);
            this.renderAll();
        }
        toggleSystem() {
            this.systemOpen = !this.systemOpen || this.$systemBar.hidden;
            if (this.$systemBar.hidden) { this.$systemBar.hidden = false; this.systemOpen = true; this.$system.focus(); }
            else { this.$systemBar.hidden = true; this.systemOpen = false; }
            this.root.querySelector('[data-act="system"]').setAttribute('aria-pressed', String(!this.$systemBar.hidden));
        }

        renderEmpty() {
            const eng = this.engineInfo();
            const usable = (this.targets || []).filter(t => t.kind !== 'protect' && t.kind !== 'other' && this.usable(t)).length;
            const engCls = eng.ready ? 'ok' : (eng.running ? 'warn' : (this.remote ? 'err' : 'warn'));
            const engText = eng.ready ? this.T('engineOk') : eng.running ? this.T('engineStarting') : this.T(this.remote ? 'engineRemoteOff' : 'engineOff');
            const engSub = eng.ready ? this.T('engineOkSub') : (this.remote ? '' : this.T('engineOffSub'));
            this.$empty.innerHTML = `
                <div class="hx-empty-logo">${svg('shield')}</div>
                <h2>${esc(this.T('welcomeTitle'))}</h2>
                <p>${esc(this.T(this.remote ? 'welcomeTextRemote' : 'welcomeText'))}</p>
                <div class="hx-cards">
                  <div class="hx-card"><span class="hx-card-k">${esc(this.T('cardEngine'))}</span>
                    <span class="hx-card-v"><span class="hx-dot ${engCls}"></span>${esc(engText)}</span><span class="hx-card-s">${esc(engSub)}</span>
                    ${!eng.ready && !eng.running && this.o.canStartEngine ? `<button type="button" class="hx-mini" data-act="start-engine">${esc(this.lang === 'en' ? 'Start now' : 'Avvia ora')}</button>` : ''}</div>
                  <div class="hx-card"><span class="hx-card-k">${esc(this.T('cardModels'))}</span>
                    <span class="hx-card-v">${svg('bot')}${this.targets ? (usable ? `${usable} ${esc(this.T(usable === 1 ? 'modelAvail1' : 'modelsAvail'))}` : esc(this.T('modelsNone'))) : esc(this.T('pickDetecting'))}</span>
                    <span class="hx-card-s">${esc(this.T('modelsSub'))}</span></div>
                  <div class="hx-card"><span class="hx-card-k">${esc(this.T('cardGlass'))}</span>
                    <span class="hx-card-v">${svg('eye')}${esc(this.T('glassCard'))}</span>
                    <button type="button" class="hx-mini" data-act="glass">${esc(this.T('openGlass'))}</button></div>
                </div>
                <div class="hx-suggest">${['sug1', 'sug2', 'sug3', 'sug4'].map(k => `<button type="button" data-act="suggest">${esc(this.T(k))}</button>`).join('')}</div>`;
        }

        renderThread() {
            const c = this.conv;
            const msgs = c ? c.messages : [];
            this.$empty.hidden = msgs.length > 0;
            if (!msgs.length) this.renderEmpty();
            this.$title.textContent = c && c.title ? c.title : this.T('untitled');
            this.$thread.innerHTML = msgs.map(m => this.msgHtml(m)).join('');
            this.applyLangIn(this.$thread);
            this.scrollEnd(true);
        }
        applyLangIn(el) { el.querySelectorAll('[data-t]').forEach(x => { x.textContent = this.T(x.dataset.t); }); }

        msgHtml(m) {
            if (m.role === 'user') {
                const files = (m.files || []).length ? `<div class="hx-files">${m.files.map(f => `<span class="hx-file-chip">${svg('file')}<span>${esc(f.name)}</span><small>${fmtBytes(f.size)}</small></span>`).join('')}</div>` : '';
                return `<div class="hx-msg hx-msg-user" data-mid="${esc(m.id)}">
                    <div class="hx-bubble-user">${esc(m.text) || '<em>(…)</em>'}</div>${files}
                    <div class="hx-msg-actions">
                      <button type="button" class="hx-act" data-act="copy-msg">${svg('copy')}${esc(this.T('copy'))}</button>
                      <button type="button" class="hx-act" data-act="edit-msg">${svg('edit')}${esc(this.T('edit'))}</button>
                    </div></div>`;
            }
            if (m.role === 'filter') return this.filterHtml(m);
            if (m.role === 'notice') {
                return `<div class="hx-notice ${esc(m.level || 'error')}" data-mid="${esc(m.id)}">${svg(m.level === 'info' ? 'shield' : 'alert')}
                    <div class="hx-notice-body"><span class="hx-notice-title">${esc(m.title || '')}</span>
                    ${m.detail ? `<span class="hx-notice-detail">${esc(m.detail)}</span>` : ''}
                    ${m.runKey ? `<div class="hx-filter-actions"><button type="button" class="hx-mini" data-act="open-run" data-run="${esc(m.runKey)}">${svg('glass')}${esc(this.T('inGlass'))}</button></div>` : ''}</div></div>`;
            }
            return this.aiHtml(m);
        }

        filterHtml(m) {
            const labels = (m.labels || []).slice(0, 24).map(l => `<span class="hx-label-chip ${catColor(labelCat(l))}">${esc(l)}</span>`).join('');
            let cls = 'hx-filter', title, meta = '', actions = '';
            if (m.state === 'working') {
                cls += ' is-working';
                title = `<span class="hx-typing"><i></i><i></i><i></i></span> ${esc(m.message || this.T('filterWorking'))}`;
            } else if (m.state === 'review') {
                cls += ' is-review';
                title = esc(this.T('filterDone'));
                meta = esc(this.T('reviewWait'));
                actions = `<button type="button" class="hx-mini primary" data-act="approve">${esc(this.T('sendNow'))}</button>
                           <button type="button" class="hx-mini danger" data-act="block">${esc(this.T('blockSend'))}</button>`;
            } else if (m.state === 'blocked') {
                cls += ' is-blocked';
                title = esc(m.message || this.T('blockedTitle'));
            } else {
                title = esc(this.T('filterDone'));
            }
            const n = m.count || 0;
            const count = m.state === 'working' || m.state === 'blocked' ? '' :
                `<span class="hx-filter-meta">· ${n ? `${n} ${esc(this.T(n === 1 ? 'maskedOne' : 'masked'))}` : esc(this.T('noneMasked'))}` +
                `${m.protect_ms != null ? ` · ${fmtSec(m.protect_ms)}` : ''}${m.cached ? ` · ${m.cached} ${esc(this.T('fromCache'))}` : ''}</span>`;
            const skipped = (m.skipped || []).length ? `<span class="hx-filter-meta">${esc(this.T('skipped'))}${esc(m.skipped.join(', '))}</span>` : '';
            const prot = m.protected ? `<div class="gw-pre">${highlightLabels(m.protected)}</div>
                <div class="hx-filter-actions"><button type="button" class="hx-mini primary" data-act="copy-protected">${svg('copy')}${esc(this.T('copyProtected'))}</button></div>` : '';
            const runBtn = m.runKey ? `<button type="button" class="hx-mini" data-act="open-run" data-run="${esc(m.runKey)}">${svg('glass')}${esc(this.T('inGlass'))}</button>` : '';
            return `<div class="hx-msg" data-mid="${esc(m.id)}"><div class="${cls}">
                <div class="hx-filter-ico">${svg('shield')}</div>
                <div class="hx-filter-body"><div class="hx-filter-title">${title}${count}</div>
                ${meta ? `<div class="hx-filter-meta">${meta}</div>` : ''}
                ${labels ? `<div class="hx-labels">${labels}</div>` : ''}${skipped}
                ${m.protected ? `<div class="hx-filter-meta">${esc(this.T('protectedReady'))}</div>` : ''}${prot}
                <div class="hx-filter-actions">${actions}${runBtn}</div></div></div></div>`;
        }

        aiHtml(m) {
            const meta = m.meta || {};
            const name = esc(meta.target_name || m.targetName || 'AI') + (meta.model || m.model ? ` <span class="hx-filter-meta">· ${esc(meta.model || m.model)}</span>` : '');
            let body;
            if (m.status === 'waiting') {
                body = `<span class="hx-waiting"><span class="hx-typing"><i></i><i></i><i></i></span>${esc(this.T('sending'))} ${esc(meta.target_name || m.targetName || '')} · ${esc(this.T('waitingFirst'))}</span>`;
            } else if (!m.protectedText && !m.text && m.status === 'streaming') {
                body = '<span class="hx-caret-only"></span>';
            } else {
                body = `<div class="hx-md">${renderAnswer(m.protectedText || m.text || '', m.masking === 'numbered' ? m.map : null, m.showLabels, this.lang)}</div>`;
            }
            const think = m.thinking ? `<details class="hx-thinking"><summary>${esc(this.T('gwThinking'))}</summary><pre>${esc(m.thinking)}</pre></details>` : '';
            let badges = '';
            if (m.status === 'done') {
                const u = meta.usage || {};
                const b = [];
                if (meta.elapsed_ms != null) b.push(`<span class="hx-badge" title="${esc(this.T('badgeTime'))}">${svg('clock')} <b>${fmtSec(meta.elapsed_ms)}</b></span>`);
                if (meta.first_token_ms != null) b.push(`<span class="hx-badge" title="${esc(this.T('badgeFirst'))}">${svg('zap')} ${fmtSec(meta.first_token_ms)}</span>`);
                if (u.input_tokens != null || u.output_tokens != null) b.push(`<span class="hx-badge">${svg('hash')} <b>${u.input_tokens ?? '?'}</b> → <b>${u.output_tokens ?? '?'}</b> ${esc(this.T('badgeTokens'))}</span>`);
                else if (meta.words != null) b.push(`<span class="hx-badge">≈ <b>${meta.words}</b> ${esc(this.T(meta.words === 1 ? 'badgeWord1' : 'badgeWords'))}</span>`);
                if (meta.entity_count != null) b.push(`<span class="hx-badge ok">${svg('shield')} <b>${meta.entity_count}</b> ${esc(this.T(meta.entity_count === 1 ? 'badgeMasked1' : 'badgeMasked'))}</span>`);
                if (meta.restored) b.push(`<span class="hx-badge info">↩ <b>${meta.restored}</b> ${esc(this.T(meta.restored === 1 ? 'badgeRestored1' : 'badgeRestored'))}</span>`);
                badges = `<div class="hx-badges">${b.join('')}</div>`;
            }
            const actions = m.status === 'done' ? `<div class="hx-msg-actions">
                <button type="button" class="hx-act" data-act="copy-msg">${svg('copy')}${esc(this.T('copy'))}</button>
                <button type="button" class="hx-act" data-act="regen">${svg('refresh')}${esc(this.T('regenerate'))}</button>
                ${m.masking === 'numbered' && m.map && Object.keys(m.map).length ? `<button type="button" class="hx-act" data-act="labels">${svg('eye')}${esc(this.T(m.showLabels ? 'showRestored' : 'showLabels'))}</button>` : ''}
                ${m.runKey ? `<button type="button" class="hx-act" data-act="open-run" data-run="${esc(m.runKey)}">${svg('glass')}${esc(this.T('glass'))}</button>` : ''}
                </div>` : '';
            return `<div class="hx-msg hx-msg-ai" data-mid="${esc(m.id)}">
                <div class="hx-ai-head"><span class="hx-avatar">${svg('bot')}</span><span class="hx-ai-name">${name}</span></div>
                ${think}<div class="hx-ai-body${m.status === 'streaming' ? ' is-streaming' : ''}">${body}</div>${badges}${actions}</div>`;
        }

        updateMsg(m) {
            const el = this.$thread.querySelector(`[data-mid="${CSS.escape(m.id)}"]`);
            const html = this.msgHtml(m);
            if (!el) { this.$thread.insertAdjacentHTML('beforeend', html); }
            else {
                const tmp = document.createElement('div');
                tmp.innerHTML = html;
                el.replaceWith(tmp.firstElementChild);
            }
            this.applyLangIn(this.$thread);
            this.$empty.hidden = true;
            this.scrollEnd();
        }
        scrollEnd(force) {
            const tl = this.$timeline;
            const near = tl.scrollHeight - tl.clientHeight - tl.scrollTop < 160;
            if (force || near) requestAnimationFrame(() => { tl.scrollTop = tl.scrollHeight; });
        }

        // -------------------------------------------------------------- stato del motore e scudo
        engineInfo() {
            const e = (this.o.engine && this.o.engine()) || this.meta.engine || {};
            return { ready: Boolean(e.ready), running: Boolean(e.running) };
        }
        renderShield() {
            const eng = this.engineInfo();
            const prof = !this.meta.profile ? '' : this.lang === 'en' ? `${this.meta.profile} profile` : `${this.T('profile')} ${this.meta.profile}`;
            let cls = 'hx-shield', text, withProf = false;
            if (this.starting) { cls += ' warn'; text = this.T('shieldStarting'); }
            else if (eng.ready) { text = this.T('shieldOk'); withProf = Boolean(prof); }
            else if (this.remote) { cls += ' err'; text = this.T('shieldRemote'); }
            else { cls += ' warn'; text = eng.running ? this.T('shieldStarting') : this.T('shieldStart'); }
            this.$shield.className = cls;
            this.$shield.title = withProf ? `${text} · ${prof}` : text;
            this.$shield.innerHTML = `${svg('shield')}<span>${esc(text)}</span>${withProf ? `<span class="hx-shield-prof">· ${esc(prof)}</span>` : ''}`;
            this.$reviewToggle.classList.toggle('is-on', this.$review.checked);
            if (!(this.conv && this.conv.messages.length)) this.renderEmpty();
        }
        onEngineChange() { this.renderShield(); }

        // -------------------------------------------------------------- allegati
        addFiles(list) {
            for (const f of list) {
                if (!f) continue;
                if (this.files.length >= MAX_FILES) { this.toast(this.T('maxFiles'), 'warn'); break; }
                this.files.push(f);
                // dalla 0.80 audio e archivi compressi hanno testo: trascrizione offline e apertura sicura nel motore
                if (isAudioFile(f)) this.toast(this.T('audioFile'), 'info');
                else if (isArchiveFile(f)) this.toast(this.T('archiveFile'), 'info');
                else if (/^(image|video)\//.test(f.type || '')) this.toast(this.T('nonTextFile'), 'warn');
            }
            this.renderFiles();
            this.updateSend();
            this.$input.focus();
        }
        renderFiles() {
            this.$attachments.innerHTML = this.files.map((f, i) => `<span class="hx-attach-chip" title="${esc(f.name)}">${svg('file')}<span>${esc(f.name)}</span>
                <small>${fmtBytes(f.size)}</small><button type="button" data-act="rm-file" data-i="${i}" aria-label="${esc(this.T('del'))}">${svg('x')}</button></span>`).join('');
        }
        autosize() { const t = this.$input; t.style.height = 'auto'; t.style.height = Math.min(260, t.scrollHeight) + 'px'; }
        updateSend() {
            const busy = Boolean(this.active);
            this.$send.classList.toggle('is-stop', busy);
            this.$send.innerHTML = svg(busy ? 'stop' : 'send');
            this.$send.title = this.T(busy ? 'stop' : 'send');
            this.$send.setAttribute('aria-label', this.$send.title);
            this.$send.disabled = !busy && !((this.$input.value || '').trim() || this.files.length);
            this.$composer.classList.toggle('is-busy', busy);
            this.$glassBtn.classList.toggle('is-live', busy);
            this.$gwStop.disabled = !busy;
        }

        // -------------------------------------------------------------- destinazioni (rilevamento automatico)
        async api(path, init = {}) {
            const headers = Object.assign({ 'X-Germano-Lang': this.lang }, init.headers || {});
            const r = await fetch(path, Object.assign({}, init, { headers, credentials: 'same-origin', cache: 'no-store' }));
            return r;
        }
        async refreshTargets(force) {
            if (this.detecting) return;
            this.detecting = true;
            try {
                const r = await this.api('/api/harness/v2/targets' + (force ? '?refresh=1' : ''));
                if (r.status === 401) { if (this.o.onAuthRequired) this.o.onAuthRequired(); return; }
                if (!r.ok) return;
                const data = await r.json();
                const prev = this.targets;
                this.meta = data;
                this.targets = data.targets || [];
                const sig = JSON.stringify(this.targets.map(t => [t.id, t.enabled, t.key, t.reason]));
                if (force || sig !== this.targetSig) {
                    const before = new Set((prev || []).filter(t => this.usable(t)).map(t => t.id));
                    this.targetSig = sig;
                    if (prev && !force) {
                        const fresh = this.targets.filter(t => this.usable(t) && t.kind !== 'protect' && !before.has(t.id));
                        if (fresh.length) this.toast((this.lang === 'en' ? 'Detected automatically: ' : 'Rilevata in automatico: ') + fresh.slice(0, 3).map(t => t.name).join(', '), 'success');
                    }
                    this.ensureSelection(Boolean(prev));
                    if (this.$pickerPop.hidden || force) this.renderPicker();
                }
                if (force) this.toast(this.lang === 'en' ? 'AI detection updated.' : 'Rilevamento delle AI aggiornato.', 'info');
                this.renderShield();
                this.renderPickerButton();
            } catch (e) {
                /* Germano non risponde: si riprova al prossimo giro */
            } finally {
                this.detecting = false;
            }
        }
        keys() { return Object.assign({}, load('local', this.o.keysKey, {}), load('session', this.o.keysKey, {})); }
        key(service) { return this.keys()[service] || ''; }
        setKey(service, value, remember) {
            const l = load('local', this.o.keysKey, {});
            const s = load('session', this.o.keysKey, {});
            delete l[service];
            delete s[service];
            if (value) (remember ? l : s)[service] = value;
            save('local', this.o.keysKey, l);
            save('session', this.o.keysKey, s);
            if (this.$empty && !this.$empty.hidden) this.renderEmpty();   // il conteggio dei modelli disponibili cambia
        }
        usable(t) {
            if (!t || !t.enabled) return false;
            if (t.kind === 'cloud') return t.key === 'server' || Boolean(this.key(t.service));
            return true;
        }
        reason(t) {
            if (t.kind === 'cloud' && t.enabled && !this.usable(t)) return this.T('keyNeeded');
            return t.reason || this.T('notDetected');
        }
        get selectedId() { return load('local', this.o.convKey + '_target', ''); }
        set selectedId(v) { save('local', this.o.convKey + '_target', v); }
        currentTarget() { return (this.targets || []).find(t => t.id === this.selectedId) || null; }
        ensureSelection(notify) {
            const cur = this.currentTarget();
            if (cur && this.usable(cur)) return;
            const ordered = this.orderedTargets().filter(t => this.usable(t));
            const def = ordered.find(t => t.kind !== 'protect') || ordered[0];
            if (def) {
                if (notify && cur) this.toast((this.lang === 'en' ? `«${cur.name}» is no longer available: now using «${def.name}».` : `«${cur.name}» non è più disponibile: ora la destinazione è «${def.name}».`), 'warn');
                this.selectedId = def.id;
            }
        }
        orderedTargets() {
            const order = { local: 0, cli: 1, cloud: 2, protect: 3, other: 4 };
            return (this.targets || []).slice().sort((a, b) => (order[a.kind] - order[b.kind]) || (this.usable(b) - this.usable(a)) || a.name.localeCompare(b.name));
        }
        modelFor(t) {
            if (!t) return '';
            if (t.model) return t.model;
            const saved = load('local', this.o.convKey + '_models', {});
            return saved[t.id] || (t.models && t.kind === 'cloud' ? t.models[0] : '') || '';
        }
        setModel(t, m) {
            const saved = load('local', this.o.convKey + '_models', {});
            saved[t.id] = m;
            save('local', this.o.convKey + '_models', saved);
        }
        renderPickerButton() {
            const t = this.currentTarget();
            const ok = t && this.usable(t);
            this.$pickerDot.className = 'hx-dot ' + (ok ? 'ok' : (this.targets ? 'err' : ''));
            let name = this.targets ? this.T('pickNone') : this.T('pickDetecting');
            if (t) {
                const m = t.kind === 'cloud' || t.kind === 'cli' ? this.modelFor(t) : '';
                name = t.kind === 'protect' ? this.T('protectOnly') : (m && t.kind !== 'local' ? `${t.vendor || t.name} · ${m}` : t.name);
            }
            this.$pickerName.textContent = name;
            this.$pickerBtn.title = t ? `${t.name}${t.model ? ' · ' + t.model : ''}` : this.T('pickTitle');
        }
        togglePicker() { if (this.$pickerPop.hidden) this.openPicker(); else this.closePicker(); }
        openPicker() {
            this.$pickerPop.hidden = false;
            this.$pickerBtn.setAttribute('aria-expanded', 'true');
            this.$pickerSearch.value = '';
            this.renderPicker();
            this.refreshTargets(false);
            setTimeout(() => this.$pickerSearch.focus(), 20);
        }
        closePicker() {
            this.$pickerPop.hidden = true;
            this.$pickerBtn.setAttribute('aria-expanded', 'false');
            this.renderPickerButton();
        }
        renderPicker() {
            this.renderPickerButton();
            if (this.$pickerPop.hidden) return;
            const q = (this.$pickerSearch.value || '').trim().toLowerCase();
            const all = this.orderedTargets().filter(t => !q || `${t.name} ${t.vendor || ''} ${t.model || ''} ${t.service || ''}`.toLowerCase().includes(q));
            const groups = [['protect', 'gProtect'], ['local', this.remote ? 'gLocalRemote' : 'gLocal'], ['cli', this.remote ? 'gCliRemote' : 'gCli'], ['cloud', 'gCloud']];
            const cur = this.selectedId;
            let html = '';
            const row = t => {
                const ok = this.usable(t);
                const sub = t.kind === 'cloud' ? (t.key === 'server' ? this.T(this.remote ? 'keyServerRemote' : 'keyServer') : (this.key(t.service) ? this.T('keyDevice') : this.T('keyNeeded')))
                    : t.kind === 'cli' ? (t.version ? `v${t.version}` : (t.vendor || '')) : t.kind === 'local' ? (t.vendor || '') : (t.vendor || '');
                const keyBtn = t.kind === 'cloud' && t.key !== 'server' ? `<span class="hx-pick-key" role="button" data-key-for="${esc(t.service)}">${esc(this.T('enterKey'))}</span>` : '';
                // Assistente di configurazione (solo su questo computer): «Installa CLI», «Avvia», «Recupera chiave»…
                const assistBtn = !this.remote && t.assist && !(t.kind === 'cloud' && ok && !t.assist_hint)
                    ? `<span class="hx-pick-assist" role="button" data-assist-for="${esc(t.assist)}" title="${esc(t.assist_hint || this.T('assistKicker'))}">${esc(t.assist_label || this.T('assistOpen'))}</span>` : '';
                const tag = ok ? (t.kind === 'local' ? `<span class="hx-pick-tag ok">${this.remote ? 'LAN' : 'locale'}</span>` : '') : `<span class="hx-pick-tag">${esc(t.assist_hint || this.reason(t))}</span>`;
                return `<li class="hx-pick" role="option" data-pick="${esc(t.id)}" aria-selected="${t.id === cur}" aria-disabled="${!ok}" tabindex="-1">
                    <span class="hx-dot ${ok ? 'ok' : ''}"></span><span class="hx-pick-main"><span class="hx-pick-name">${esc(t.kind === 'protect' ? t.name : t.name)}</span>
                    <span class="hx-pick-sub">${esc(sub)}</span></span>${tag}${keyBtn}${assistBtn}</li>`;
            };
            groups.forEach(([kind, label]) => {
                const items = all.filter(t => t.kind === kind);
                if (!items.length) return;
                html += `<li class="hx-pick-group" role="presentation"><span>${esc(this.T(label))}</span><span>${items.filter(t => this.usable(t)).length}/${items.length}</span></li>`;
                html += items.map(row).join('');
            });
            const others = all.filter(t => t.kind === 'other');
            if (others.length) {
                html += `<li class="hx-pick-more" role="presentation"><details${q ? ' open' : ''}><summary>${esc(this.T('gOther'))} (${others.length})</summary>
                    <ul class="hx-picker-list" style="padding:0">${others.map(row).join('')}</ul></details></li>`;
            }
            this.$pickerList.innerHTML = html || `<li class="hx-pick-group">${esc(this.T('noMatch'))}</li>`;
            this.renderPickerDetail();
        }
        renderPickerDetail(keyFor) {
            const t = this.currentTarget();
            const service = keyFor || (t && t.kind === 'cloud' ? t.service : null);
            let html = '';
            if (t && (t.kind === 'cloud' || t.kind === 'cli' || (t.kind === 'local' && !t.model)) && !keyFor) {
                const models = Array.from(new Set([...(t.models || []), ...(this.fetchedModels?.[t.service] || [])]));
                html += `<label class="hx-field"><span>${esc(this.T(t.kind === 'cli' ? 'modelOptional' : 'model'))}</span>
                    <span class="hx-row"><input type="text" data-model-input list="hx-models-${esc(t.id)}" value="${esc(this.modelFor(t))}" placeholder="${esc(this.T('modelPh'))}" spellcheck="false" autocapitalize="off">
                    ${t.kind === 'cloud' ? `<button type="button" class="hx-mini" data-act="list-models" data-service="${esc(t.service)}">${esc(this.T('listModels'))}</button>` : ''}</span>
                    <datalist id="hx-models-${esc(t.id)}">${models.map(m => `<option value="${esc(m)}">`).join('')}</datalist></label>`;
            }
            if (service) {
                const svc = (this.targets || []).find(x => x.kind === 'cloud' && x.service === service);
                if (svc && svc.key !== 'server') {
                    const has = Boolean(this.key(service));
                    const remembered = Boolean(load('local', this.o.keysKey, {})[service]);
                    html += `<div class="hx-field" data-keyform="${esc(service)}"><span>${esc(this.T('keyLabel'))} ${esc(svc.name)}</span>
                        <span class="hx-row"><input type="password" data-key-input autocomplete="off" spellcheck="false" placeholder="${esc(this.T('keyPh'))}" value="${has ? '••••••••' : ''}">
                        <button type="button" class="hx-mini primary" data-act="key-save" data-service="${esc(service)}">${esc(this.T('keySave'))}</button>
                        ${has ? `<button type="button" class="hx-mini" data-act="key-remove" data-service="${esc(service)}">${esc(this.T('keyRemove'))}</button>` : ''}</span>
                        <label class="hx-row" style="font-size:11.5px"><input type="checkbox" data-key-remember${remembered ? ' checked' : ''}> ${esc(this.T('keyRemember'))}</label>
                        <span class="hx-small-note">${esc(this.T('keyNote'))}</span><span class="hx-small-note" data-key-msg></span></div>`;
                } else if (svc && svc.key === 'server') {
                    html += `<span class="hx-small-note">🔑 ${esc(this.T(this.remote ? 'keyServerRemote' : 'keyServer'))}${svc.key_vars ? ` (${esc(svc.key_vars.join(', '))})` : ''}</span>`;
                }
            }
            this.$pickerDetail.innerHTML = html;
            const mi = this.$pickerDetail.querySelector('[data-model-input]');
            if (mi && t) mi.addEventListener('change', () => { this.setModel(t, mi.value.trim()); this.renderPickerButton(); });
            const ki = this.$pickerDetail.querySelector('[data-key-input]');
            if (ki) {
                ki.addEventListener('focus', () => { if (ki.value === '••••••••') ki.value = ''; });
                ki.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); this.saveKeyForm(service); } });
            }
        }
        openKeyForm(service) {
            if (this.$pickerPop.hidden) this.openPicker();
            this.renderPickerDetail(service);
            const ki = this.$pickerDetail.querySelector('[data-key-input]');
            if (ki) ki.focus();
        }
        saveKeyForm(service) {
            const box = this.$pickerDetail.querySelector(`[data-keyform="${CSS.escape(service)}"]`);
            if (!box) return;
            const v = box.querySelector('[data-key-input]').value.trim();
            const remember = box.querySelector('[data-key-remember]').checked;
            if (v === '••••••••') { this.setKey(service, this.key(service), remember); this.renderPicker(); return; }
            if (!KEY_RE.test(v)) { box.querySelector('[data-key-msg]').textContent = this.T('keyInvalid'); return; }
            this.setKey(service, v, remember);
            const t = (this.targets || []).find(x => x.kind === 'cloud' && x.service === service);
            if (t) this.selectedId = t.id;
            this.renderPicker();
            this.renderPickerButton();
            if (this.o.onKeysChanged) this.o.onKeysChanged();
        }
        async listModels(service) {
            const t = (this.targets || []).find(x => x.kind === 'cloud' && x.service === service);
            if (!t) return;
            const headers = {};
            if (this.key(service)) headers['X-Germano-Provider-Key'] = this.key(service);
            try {
                const r = await this.api('/api/harness/v2/models?service=' + encodeURIComponent(service), { headers });
                const data = await r.json().catch(() => ({}));
                if (!r.ok) { this.toast(data.message || 'Errore', 'error'); return; }
                this.fetchedModels = this.fetchedModels || {};
                this.fetchedModels[service] = data.models || [];
                this.renderPickerDetail();
                this.toast(`${(data.models || []).length} ${this.lang === 'en' ? 'models available' : 'modelli disponibili'}`, 'success');
            } catch (e) { this.toast(this.T('netError'), 'error'); }
        }
        choose(id) {
            const t = (this.targets || []).find(x => x.id === id);
            if (!t) return;
            if (!this.usable(t)) {
                if (t.kind === 'cloud' && t.enabled && t.key !== 'server') this.openKeyForm(t.service);
                return;
            }
            this.selectedId = id;
            this.renderPicker();
            if (t.kind !== 'cloud' && t.kind !== 'cli') this.closePicker();
            else { const mi = this.$pickerDetail.querySelector('[data-model-input]'); if (mi && !mi.value) mi.focus(); }
            this.renderPickerButton();
        }
        // -------------------------------------------------------------- assistente di configurazione (solo suite)
        // Finestra montata su document.body: si apre dal selettore dei modelli e dalle Impostazioni (dove la vista
        // dell'Harness e' nascosta). Tutto passa da /api/ai/assist/*, che risponde solo a questo computer.
        ensureAssistDom() {
            if (this.$assist) return this.$assist;
            const el = document.createElement('div');
            el.className = 'hx-assist';
            el.hidden = true;
            el.setAttribute('role', 'dialog');
            el.setAttribute('aria-modal', 'true');
            el.innerHTML = `<div class="hx-assist-card" data-assist-card>
                <header class="hx-assist-head"><div class="hx-assist-titles"><span class="hx-assist-kicker" data-ax="kicker"></span>
                  <h3 data-ax="title"></h3><p data-ax="summary"></p></div>
                  <button type="button" class="hx-btn-icon" data-ax-act="close">${svg('x')}</button></header>
                <div class="hx-assist-body" data-ax="body"></div>
                <footer class="hx-assist-foot" data-ax="foot"></footer></div>`;
            el.addEventListener('click', e => this.onAssistClick(e));
            el.addEventListener('mousedown', e => { if (e.target === el) this.closeAssist(); });
            document.addEventListener('keydown', e => { if (e.key === 'Escape' && !el.hidden) this.closeAssist(); });
            document.body.append(el);
            this.$assist = el;
            return el;
        }
        async openAssist(id) {
            if (this.remote || !id) return;
            const el = this.ensureAssistDom();
            this.assistId = id;
            this.assistItem = null;
            el.hidden = false;
            this.closePicker();
            this.renderAssist();
            await this.loadAssist();
        }
        closeAssist() {
            if (!this.$assist) return;
            this.$assist.hidden = true;
            this.assistId = null;
        }
        async loadAssist() {
            const id = this.assistId;
            if (!id) return;
            try {
                const r = await this.api('/api/ai/assist?id=' + encodeURIComponent(id));
                const data = await r.json().catch(() => ({}));
                if (id !== this.assistId) return;
                if (!r.ok) { this.assistItem = { id, name: id, error: data.message || this.T('assistFailed'), facts: [], actions: [], links: [] }; }
                else this.assistItem = data.item;
            } catch (e) {
                this.assistItem = { id, name: id, error: this.T('netError'), facts: [], actions: [], links: [] };
            }
            this.renderAssist();
            const job = this.assistItem && this.assistItem.job;
            if (job && job.state === 'running') this.followJob(job);
        }
        renderAssist() {
            const el = this.$assist;
            if (!el || el.hidden) return;
            const it = this.assistItem;
            const q = s => el.querySelector(`[data-ax="${s}"]`);
            q('kicker').textContent = this.T('assistKicker');
            q('title').textContent = it ? it.name : this.T('assistTitle');
            q('summary').textContent = it ? (it.error || it.summary || '') : this.T('assistLoading');
            if (!it) { q('body').innerHTML = `<div class="hx-assist-wait"><span class="hx-spinner"></span>${esc(this.T('assistLoading'))}</div>`; q('foot').textContent = ''; return; }
            const job = this.assistJob && this.assistJob.assist === it.id ? this.assistJob : it.job;
            const busy = Boolean(job && job.state === 'running');
            let html = '';
            if ((it.facts || []).length) {
                html += `<div class="hx-assist-sec"><div class="hx-assist-k">${esc(this.T('assistState'))}</div><ul class="hx-assist-facts">${it.facts.map(f =>
                    `<li class="${f.ok === true ? 'ok' : f.ok === false ? 'no' : 'info'}"><span class="hx-dot ${f.ok === true ? 'ok' : f.ok === false ? 'err' : ''}"></span><span>${esc(f.text)}</span></li>`).join('')}</ul></div>`;
            }
            const acts = it.actions || [];
            html += `<div class="hx-assist-sec"><div class="hx-assist-k">${esc(this.T('assistActions'))}</div>`;
            if (!acts.length) html += `<p class="hx-small-note">${esc(this.T('assistNothing'))}</p>`;
            acts.forEach((a, i) => {
                const choice = a.choices && a.choices.length ? `<select data-ax-choice="${i}">${a.choices.map(c => `<option value="${esc(c.value)}">${esc(c.label)}</option>`).join('')}</select>` : '';
                html += `<div class="hx-assist-act"><div class="hx-row">${choice}<button type="button" class="hx-mini${a.primary ? ' primary' : ''}" data-ax-act="run" data-i="${i}"${busy ? ' disabled' : ''}>${esc(a.label)}</button></div>
                    ${a.note ? `<span class="hx-small-note">${esc(a.note)}</span>` : ''}</div>`;
            });
            html += '</div>';
            if (job) {
                const st = job.state;
                const label = st === 'running' ? this.T('assistRunning') : st === 'done' ? this.T('assistDone') : st === 'cancelled' ? this.T('assistCancelled') : this.T('assistError');
                const pct = typeof job.progress === 'number' ? Math.round(job.progress * 100) : null;
                const lines = (this.assistLines && this.assistLines.id === job.id ? this.assistLines.lines : job.lines || []).slice(-14);
                html += `<div class="hx-assist-sec hx-assist-job ${esc(st)}"><div class="hx-assist-k">${esc(this.T('assistLog'))} · ${esc(job.title || '')}
                    <span class="hx-assist-state">${st === 'running' ? '<span class="hx-spinner"></span>' : ''}${esc(label)}${pct !== null && st === 'running' ? ` · ${pct}%` : ''}</span></div>
                    ${pct !== null && st === 'running' ? `<div class="hx-assist-bar"><span style="width:${pct}%"></span></div>` : ''}
                    <pre class="hx-assist-log">${esc(lines.map(l => l.text).join('\n'))}</pre>
                    ${job.message && st !== 'running' ? `<p class="hx-assist-msg">${esc(job.message)}</p>` : ''}
                    ${st === 'running' ? `<button type="button" class="hx-mini danger" data-ax-act="cancel">${esc(this.T('assistCancel'))}</button>` : ''}</div>`;
            }
            if ((it.links || []).length) {
                html += `<div class="hx-assist-sec"><div class="hx-assist-k">${esc(this.T('assistLinks'))}</div><div class="hx-assist-links">${it.links.map(l =>
                    /^https:\/\//.test(l.url || '') ? `<a href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">${esc(l.label)}</a>` : '').join('')}</div></div>`;
            }
            q('body').innerHTML = html;
            const log = q('body').querySelector('.hx-assist-log');
            if (log) log.scrollTop = log.scrollHeight;
            q('foot').innerHTML = `<span>🔒 ${esc(this.T('assistSafe'))}</span><button type="button" class="hx-mini" data-ax-act="close">${esc(this.T('assistClose'))}</button>`;
        }
        onAssistClick(e) {
            const b = e.target.closest('[data-ax-act]');
            if (!b) return;
            const act = b.dataset.axAct;
            if (act === 'close') { this.closeAssist(); return; }
            if (act === 'cancel') { this.cancelAssistJob(); return; }
            if (act === 'run') {
                const a = (this.assistItem && this.assistItem.actions || [])[+b.dataset.i];
                if (!a) return;
                let param = a.param || '';
                if (a.choices) {
                    const sel = this.$assist.querySelector(`[data-ax-choice="${b.dataset.i}"]`);
                    param = sel ? sel.value : param;
                }
                if (a.confirm && !window.confirm(a.confirm)) return;
                this.runAssist(a.id, param);
            }
        }
        async runAssist(action, param) {
            try {
                const r = await this.api('/api/ai/assist/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, param }) });
                const data = await r.json().catch(() => ({}));
                if (!r.ok) { this.toast(data.message || this.T('assistFailed'), 'error'); return; }
                this.followJob(data.job);
            } catch (e) { this.toast(this.T('netError'), 'error'); }
        }
        followJob(job) {
            this.assistJob = job;
            this.assistLines = { id: job.id, lines: (job.lines || []).slice() };
            this.renderAssist();
            if (this.assistTimer) clearTimeout(this.assistTimer);
            const tick = async () => {
                const cur = this.assistJob;
                if (!cur || cur.id !== job.id) return;
                try {
                    const r = await this.api(`/api/ai/assist/jobs/${encodeURIComponent(job.id)}?since=${this.assistLines.lines.length}`);
                    const data = await r.json().catch(() => ({}));
                    if (r.ok && data.job) {
                        this.assistLines.lines.push(...(data.job.lines || []));
                        this.assistJob = Object.assign({}, data.job, { lines: this.assistLines.lines });
                        if (data.job.state !== 'running') {
                            this.renderAssist();
                            this.toast(data.job.message || this.T('assistDone'), data.job.state === 'done' ? 'success' : data.job.state === 'cancelled' ? 'warn' : 'error');
                            await this.refreshTargets(true);
                            await this.loadAssist();
                            if (this.o.onAssistChanged) this.o.onAssistChanged();
                            return;
                        }
                    }
                } catch (e) { /* si riprova */ }
                this.renderAssist();
                this.assistTimer = setTimeout(tick, 700);
            };
            this.assistTimer = setTimeout(tick, 500);
        }
        async cancelAssistJob() {
            const job = this.assistJob;
            if (!job) return;
            try { await this.api(`/api/ai/assist/jobs/${encodeURIComponent(job.id)}/cancel`, { method: 'POST' }); } catch (e) { /* nulla */ }
        }
        // Elenco per le Impostazioni (pannello «Assistente di configurazione»): una scheda per voce
        async renderAssistOverview(container) {
            if (this.remote || !container) return;
            if (!container.dataset.axBound) {
                container.dataset.axBound = '1';
                container.addEventListener('click', e => {
                    const b = e.target.closest('[data-assist-open]');
                    if (b) this.openAssist(b.dataset.assistOpen);
                });
            }
            try {
                const r = await this.api('/api/ai/assist');
                const data = await r.json().catch(() => ({}));
                if (!r.ok) { container.innerHTML = `<span class="muted">${esc(data.message || this.T('assistFailed'))}</span>`; return; }
                container.innerHTML = (data.items || []).map(it => {
                    const ready = it.status === 'ready';
                    const next = (it.actions || []).find(a => a.primary) || (it.actions || [])[0];
                    return `<div class="ax-card${ready ? ' ready' : ''}"><div class="ax-card-head"><span class="hx-dot ${ready ? 'ok' : 'warn'}"></span>
                        <span class="ax-card-name">${esc(it.name || it.id)}</span><span class="ax-card-state">${esc(this.T(ready ? 'assistReady' : 'assistTodo'))}</span></div>
                        <p class="ax-card-sub">${esc(it.summary || '')}</p>
                        <ul class="ax-card-facts">${(it.facts || []).slice(0, 3).map(f => `<li class="${f.ok === true ? 'ok' : f.ok === false ? 'no' : 'info'}">${esc(f.text)}</li>`).join('')}</ul>
                        <button type="button" class="btn btn-secondary btn-sm" data-assist-open="${esc(it.id)}">${esc(next ? next.label : this.T('assistOpen'))}</button></div>`;
                }).join('');
            } catch (e) { container.innerHTML = `<span class="muted">${esc(this.T('netError'))}</span>`; }
        }

        pickerKey(e) {
            const opts = Array.from(this.$pickerList.querySelectorAll('.hx-pick[aria-disabled="false"]'));
            if (!opts.length) return;
            let i = opts.findIndex(o => o.classList.contains('is-focus'));
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                if (i >= 0) opts[i].classList.remove('is-focus');
                i = e.key === 'ArrowDown' ? (i + 1) % opts.length : (i <= 0 ? opts.length - 1 : i - 1);
                opts[i].classList.add('is-focus');
                opts[i].scrollIntoView({ block: 'nearest' });
            } else if (e.key === 'Enter') {
                e.preventDefault();
                const o = i >= 0 ? opts[i] : opts[0];
                this.choose(o.dataset.pick);
            }
        }

        // -------------------------------------------------------------- invio
        submit() {
            const text = (this.$input.value || '').trim();
            if (!text && !this.files.length) { this.toast(this.T('writeSomething'), 'warn'); return; }
            if (this.active) { this.toast(this.T('busy'), 'warn'); return; }
            const t = this.currentTarget();
            if (!t || !this.usable(t)) { this.toast(this.T('chooseAi'), 'warn'); this.openPicker(); return; }
            if ((t.kind === 'cloud' || (t.kind === 'local' && t.model_required)) && !this.modelFor(t)) { this.openPicker(); this.toast(this.T('modelPh'), 'warn'); return; }
            const files = this.files.slice();
            this.files = [];
            this.$input.value = '';
            this.autosize();
            this.renderFiles();
            this.run(text, files, t);
        }

        historyFor(conv, upto) {
            const out = [];
            for (const m of conv.messages) {
                if (m.id === upto) break;
                if (m.role === 'user' && m.done) out.push({ role: 'user', text: m.userText || m.text || '' });
                else if (m.role === 'assistant' && m.status === 'done' && m.text) out.push({ role: 'assistant', text: m.text });
            }
            return out.filter(h => h.text.trim());
        }

        async run(text, files, target, opts = {}) {
            const conv = this.ensureConv();
            const userMsg = opts.userMsg || { id: uid(), role: 'user', text, files: files.map(f => ({ name: f.name, size: f.size })) };
            if (!opts.userMsg) conv.messages.push(userMsg);
            if (!conv.title) conv.title = (text || files.map(f => f.name).join(', ')).replace(/\s+/g, ' ').slice(0, 60);
            conv.updated = Date.now();
            const filterMsg = { id: uid(), role: 'filter', state: 'working' };
            const slowNote = files.some(isAudioFile) ? this.T('filterAudio') : (files.some(isArchiveFile) ? this.T('filterArchive') : '');
            if (slowNote) filterMsg.message = slowNote;
            conv.messages.push(filterMsg);
            const aiMsg = target.kind === 'protect' ? null : { id: uid(), role: 'assistant', status: 'waiting', targetName: target.name, model: this.modelFor(target),
                                                               protectedText: '', text: '', map: {}, masking: 'numbered' };
            if (aiMsg) conv.messages.push(aiMsg);
            this.renderConvs();
            if (!opts.userMsg) this.updateMsg(userMsg);
            this.updateMsg(filterMsg);
            if (aiMsg) this.updateMsg(aiMsg);
            const run = { key: uid(), id: null, n: this.runs.length + 1, started: Date.now(), target, model: this.modelFor(target), phase: 'starting',
                          original: { prompt: text, system: conv.system || '', attachments: files.map(f => ({ name: f.name, size: f.size })), history: [] },
                          entities: null, sanitized: null, payloads: [], raw: '', thinking: '', frames: [], cli: [], usage: null, done: null, aborted: null,
                          error: null, review: Boolean(this.prefs.review), ctrl: new AbortController(), userMsg, filterMsg, aiMsg, conv, transmitted: false, receivedAt: null,
                          slowNote };
            filterMsg.runKey = run.key;
            if (aiMsg) aiMsg.runKey = run.key;
            this.runs.push(run);
            if (this.runs.length > 25) this.runs.shift();
            if (this.follow || !this.glassRun) { this.glassRun = run; this.follow = true; }
            this.active = run;
            this.updateSend();
            this.renderRunSelect();
            this.renderGlass();
            try {
                await this.stream(run, text, files);
            } finally {
                if (this.active === run) this.active = null;
                run.ended = run.ended || Date.now();
                this.updateSend();
                this.renderRunSelect();
                this.renderGlass();
                conv.updated = Date.now();
                this.saveConvs();
                this.renderConvs();
            }
        }

        formFor(run, text, files) {
            const fd = new FormData();
            fd.append('target', run.target.id);
            const model = run.model;
            if (model) fd.append('model', model);
            fd.append('prompt', text);
            if (run.conv.system) fd.append('system', run.conv.system);
            const hist = this.historyFor(run.conv, run.userMsg.id);
            run.original.history = hist.map(h => ({ role: h.role, chars: h.text.length }));
            if (hist.length) fd.append('history', JSON.stringify(hist));
            if (run.review) fd.append('review', '1');
            if (this.prefs.frames && this.glassOpen) fd.append('raw_frames', '1');
            if (!this.prefs.hint) fd.append('label_hint', '0');
            const options = this.o.options && this.o.options();
            if (options) fd.append('options', JSON.stringify(options));
            files.forEach(f => fd.append('files', f, f.name));
            return fd;
        }

        async stream(run, text, files, retried) {
            const headers = {};
            if (run.target.kind === 'cloud' && run.target.key !== 'server' && this.key(run.target.service)) headers['X-Germano-Provider-Key'] = this.key(run.target.service);
            let resp;
            try {
                resp = await this.api('/api/harness/v2/run', { method: 'POST', body: this.formFor(run, text, files), headers, signal: run.ctrl.signal });
            } catch (e) {
                if (run.stopRequested) return this.localAbort(run);
                return this.fail(run, this.T('netError'));
            }
            if (!resp.ok) {
                const data = await resp.json().catch(() => ({}));
                if (resp.status === 503 && data.code === 'engine_not_ready' && this.o.canStartEngine && !retried && !run.stopRequested) {
                    const ok = await this.startEngineAndWait(run);
                    if (ok && !run.stopRequested) return this.stream(run, text, files, true);
                    if (run.stopRequested) return this.localAbort(run);
                    return this.fail(run, this.T('engineFailed'), 'blocked');
                }
                if (resp.status === 401 && data.auth_required && this.o.onAuthRequired) this.o.onAuthRequired();
                if (data.code === 'key_needed' && run.target.kind === 'cloud') this.openKeyForm(run.target.service);
                if (data.code === 'compliance_lock' && this.o.onCompliance) this.o.onCompliance();
                return this.fail(run, data.message || data.error || `HTTP ${resp.status}`, resp.status === 503 ? 'blocked' : 'error');
            }
            const reader = resp.body.getReader();
            const dec = new TextDecoder();
            let buf = '';
            try {
                for (;;) {
                    const { value, done } = await reader.read();
                    if (done) break;
                    buf += dec.decode(value, { stream: true });
                    let nl;
                    while ((nl = buf.indexOf('\n')) >= 0) {
                        const line = buf.slice(0, nl);
                        buf = buf.slice(nl + 1);
                        if (line.trim()) { try { this.onEvent(run, JSON.parse(line)); } catch (e) { /* riga non valida: ignorata */ } }
                    }
                }
            } catch (e) {
                if (!run.done && !run.aborted && !run.error) {
                    if (run.stopRequested) return this.localAbort(run);
                    return this.fail(run, this.T('netError'));
                }
            }
            if (!run.done && !run.aborted && !run.error) {
                if (run.stopRequested) this.localAbort(run);
                else this.fail(run, this.T('netError'));
            }
        }

        async startEngineAndWait(run) {
            this.starting = true;
            this.renderShield();
            run.filterMsg.state = 'working';
            run.filterMsg.message = this.T('startingEngine');
            this.updateMsg(run.filterMsg);
            run.phase = 'engine';
            this.renderGlass();
            try {
                await this.o.startEngine();
                const t0 = Date.now();
                while (Date.now() - t0 < 10 * 60 * 1000) {
                    if (run.stopRequested) return false;
                    await new Promise(r => setTimeout(r, 1500));
                    const st = this.o.engineState ? await this.o.engineState() : null;
                    if (st && st.ready) return true;
                    if (st && st.failed) return false;
                }
                return false;
            } catch (e) {
                return false;
            } finally {
                this.starting = false;
                run.filterMsg.message = run.slowNote || '';
                this.renderShield();
            }
        }
        async startEngineNow() {
            if (!this.o.canStartEngine) return;
            this.starting = true;
            this.renderShield();
            try { await this.o.startEngine(); } catch (e) { /* stato aggiornato dalla Dashboard */ }
            setTimeout(() => { this.starting = false; this.renderShield(); }, 2500);
        }

        onEvent(run, ev) {
            const conv = run.conv;
            switch (ev.type) {
                case 'start':
                    run.id = ev.run_id;
                    run.serverModel = ev.model;
                    run.phase = 'start';
                    break;
                case 'original':
                    run.original = Object.assign({}, run.original, { prompt: ev.prompt, system: ev.system, attachments: ev.attachments, history: ev.history });
                    break;
                case 'phase':
                    run.phase = ev.phase === 'approved' ? 'transmitting' : ev.phase;
                    if (ev.phase === 'transmitting') { run.transmitted = true; if (run.aiMsg) { run.aiMsg.status = 'waiting'; this.updateMsg(run.aiMsg); } }
                    if (ev.phase === 'streaming') { run.firstToken = ev.first_token_ms; if (run.aiMsg) { run.aiMsg.status = 'streaming'; this.updateMsg(run.aiMsg); } }
                    if (ev.phase === 'approved' && run.filterMsg.state === 'review') { run.filterMsg.state = 'done'; this.updateMsg(run.filterMsg); }
                    break;
                case 'entities': {
                    run.entities = ev;
                    const labels = Array.from(new Set((ev.items || []).map(x => x.label)));
                    Object.assign(run.filterMsg, { state: 'done', count: ev.count, labels, protect_ms: ev.protect_ms, cached: ev.cached });
                    if (run.aiMsg) { run.aiMsg.map = ev.map || {}; run.aiMsg.masking = ev.masking || 'numbered'; }
                    this.updateMsg(run.filterMsg);
                    break;
                }
                case 'sanitized':
                    run.sanitized = ev;
                    if ((ev.skipped || []).length) { run.filterMsg.skipped = ev.skipped; this.updateMsg(run.filterMsg); }
                    break;
                case 'payload':
                    run.payloads.push(ev);
                    break;
                case 'gate':
                    run.phase = 'review';
                    run.filterMsg.state = 'review';
                    this.updateMsg(run.filterMsg);
                    if (!this.glassOpen) this.openGlass();
                    break;
                case 'delta':
                    run.raw += ev.text;
                    if (!run.receivedAt) run.receivedAt = Date.now();
                    if (run.aiMsg) { run.aiMsg.protectedText += ev.text; run.aiMsg.status = 'streaming'; }
                    this.queueRender(run);
                    break;
                case 'thinking':
                    run.thinking += ev.text;
                    if (run.aiMsg) run.aiMsg.thinking = (run.aiMsg.thinking || '') + ev.text;
                    this.queueRender(run);
                    break;
                case 'usage': run.usage = ev.usage; break;
                case 'frame': if (run.frames.join('').length < 200000) run.frames.push(ev.text); break;
                case 'cli': run.cli.push(ev.line); if (run.cli.length > 200) run.cli.shift(); break;
                case 'ping': break;
                case 'done':
                    run.done = ev;
                    run.phase = 'done';
                    run.ended = Date.now();
                    run.userMsg.done = true;
                    run.userMsg.userText = ev.user_text || run.userMsg.text;
                    if (ev.protect_only) {
                        run.filterMsg.protected = ev.protected;
                        run.filterMsg.state = 'done';
                        this.updateMsg(run.filterMsg);
                    } else if (run.aiMsg) {
                        Object.assign(run.aiMsg, { status: 'done', text: ev.answer, protectedText: ev.answer_protected || run.aiMsg.protectedText, masking: ev.masking || run.aiMsg.masking,
                                                   meta: { target_name: ev.target_name || run.target.name, model: ev.model || run.model, elapsed_ms: ev.elapsed_ms, first_token_ms: ev.first_token_ms,
                                                           usage: ev.usage, entity_count: ev.entity_count, restored: ev.restored, words: ev.words } });
                        this.updateMsg(run.aiMsg);
                    }
                    break;
                case 'aborted':
                    run.aborted = ev;
                    run.phase = 'aborted';
                    run.ended = Date.now();
                    this.markAborted(run, ev.message, ev.detail, ev.transmitted);
                    break;
                case 'error':
                    run.error = ev;
                    run.phase = 'error';
                    run.ended = Date.now();
                    this.fail(run, ev.message, ev.status === 'blocked' ? 'blocked' : 'error', ev.partial);
                    break;
                default: break;
            }
            if (!['delta', 'thinking', 'frame', 'ping', 'usage', 'cli'].includes(ev.type)) this.renderGlassSoon(run);
            else if (ev.type === 'usage' || ev.type === 'cli') this.renderGlassSoon(run, true);
            if (conv !== this.conv) this.renderStatus();
        }

        queueRender(run) {
            if (this.renderQueued) return;
            this.renderQueued = true;
            setTimeout(() => {
                this.renderQueued = false;
                if (run.aiMsg && run.conv === this.conv && !run.done) this.updateMsg(run.aiMsg);
                this.renderGlassSoon(run, true);
            }, 60);
        }

        markAborted(run, message, detail, transmitted) {
            const m = run.aiMsg;
            if (m) {
                if (m.protectedText) { m.status = 'done'; m.text = restorePlain(m.protectedText, m.map); m.meta = { target_name: run.target.name, model: run.model }; m.partial = true; }
                else { run.conv.messages = run.conv.messages.filter(x => x !== m); }
                if (run.conv === this.conv) { const el = this.$thread.querySelector(`[data-mid="${CSS.escape(m.id)}"]`); if (el && !m.protectedText) el.remove(); else if (m.protectedText) this.updateMsg(m); }
            }
            if (run.filterMsg.state === 'working' || run.filterMsg.state === 'review') { run.filterMsg.state = transmitted ? 'done' : 'blocked'; run.filterMsg.message = this.T('abortedTitle'); this.updateMsg(run.filterMsg); }
            const notice = { id: uid(), role: 'notice', level: 'warn', title: message || this.T('abortedLocal'),
                             detail: detail || (transmitted ? '' : this.T('gwStoppedBefore')), runKey: run.key };
            run.conv.messages.push(notice);
            if (run.conv === this.conv) this.updateMsg(notice);
        }
        localAbort(run) {
            if (run.aborted || run.done) return;
            run.aborted = { message: this.T('abortedLocal'), transmitted: run.transmitted, local: true };
            run.phase = 'aborted';
            run.ended = Date.now();
            this.markAborted(run, this.T('abortedLocal'), run.transmitted ? '' : this.T('gwStoppedBefore'), run.transmitted);
        }
        fail(run, message, level = 'error', partial = '') {
            if (run.done || (run.aborted && !run.error)) return;
            run.error = run.error || { message };
            run.phase = 'error';
            run.ended = Date.now();
            const m = run.aiMsg;
            if (m) {
                if (partial || m.protectedText) { m.status = 'done'; m.protectedText = m.protectedText || partial; m.text = restorePlain(m.protectedText, m.map); m.partial = true; this.updateMsg(m); }
                else { run.conv.messages = run.conv.messages.filter(x => x !== m); const el = this.$thread.querySelector(`[data-mid="${CSS.escape(m.id)}"]`); if (el) el.remove(); }
            }
            if (run.filterMsg.state === 'working' || run.filterMsg.state === 'review') {
                run.filterMsg.state = 'blocked';
                run.filterMsg.message = level === 'blocked' ? this.T('blockedTitle') : this.T('errorTitle');
                this.updateMsg(run.filterMsg);
            }
            const notice = { id: uid(), role: 'notice', level: 'error', title: level === 'blocked' ? this.T('blockedTitle') : this.T('errorTitle'), detail: message, runKey: run.key };
            run.conv.messages.push(notice);
            if (run.conv === this.conv) this.updateMsg(notice);
        }

        async stop() {
            const run = this.active;
            if (!run || run.stopRequested) return;
            run.stopRequested = true;
            this.renderGlass();
            if (run.id) {
                try { await this.api(`/api/harness/v2/runs/${encodeURIComponent(run.id)}/abort`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); } catch (e) { /* si chiude comunque la lettura */ }
                setTimeout(() => { if (!run.aborted && !run.done) run.ctrl.abort(); }, 1500);
            } else {
                run.ctrl.abort();
            }
        }
        async approve() {
            const run = this.active;
            if (!run || !run.id || run.phase !== 'review') return;
            try { await this.api(`/api/harness/v2/runs/${encodeURIComponent(run.id)}/approve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); } catch (e) { /* ignorato */ }
        }

        // -------------------------------------------------------------- azioni sui messaggi
        findMsg(id) { const c = this.conv; return c ? c.messages.find(m => m.id === id) : null; }
        async copyMessage(id, btn) {
            const m = this.findMsg(id);
            if (!m) return;
            const ok = await copyText(m.role === 'assistant' ? (m.text || restorePlain(m.protectedText, m.map)) : m.text);
            if (ok) { btn.innerHTML = `${svg('check')}${esc(this.T('copied'))}`; setTimeout(() => { btn.innerHTML = `${svg('copy')}${esc(this.T('copy'))}`; }, 1500); }
        }
        async copyProtected(id, btn) {
            const m = this.findMsg(id);
            if (m && m.protected && await copyText(m.protected)) { btn.innerHTML = `${svg('check')}${esc(this.T('copied'))}`; }
        }
        toggleLabels(id) { const m = this.findMsg(id); if (m) { m.showLabels = !m.showLabels; this.updateMsg(m); } }
        regenerate(id) {
            if (this.active) { this.toast(this.T('busy'), 'warn'); return; }
            const c = this.conv;
            const idx = c.messages.findIndex(m => m.id === id);
            let u = null;
            for (let k = idx; k >= 0; k -= 1) if (c.messages[k].role === 'user') { u = c.messages[k]; break; }
            if (!u) return;
            const t = this.currentTarget();
            if (!t || !this.usable(t)) { this.openPicker(); return; }
            c.messages = c.messages.slice(0, c.messages.indexOf(u) + 1);
            u.done = false;
            this.renderThread();
            this.run(u.userText || u.text, [], t, { userMsg: u });
        }
        editMessage(id) {
            if (this.active) { this.toast(this.T('busy'), 'warn'); return; }
            const c = this.conv;
            const idx = c.messages.findIndex(m => m.id === id);
            if (idx < 0) return;
            this.$input.value = c.messages[idx].text || '';
            c.messages = c.messages.slice(0, idx);
            this.saveConvs();
            this.renderThread();
            this.autosize();
            this.updateSend();
            this.$input.focus();
        }
        exportConv() {
            const c = this.conv;
            if (!c || !c.messages.length) return;
            const lines = [`# ${c.title || this.T('untitled')}`, '', `> ${this.T('exportNote')} · ${new Date().toLocaleString(this.lang === 'en' ? 'en-GB' : 'it-IT')}`, ''];
            c.messages.forEach(m => {
                if (m.role === 'user') lines.push(`## ${this.T('you')}`, '', m.text || '', ...(m.files || []).map(f => `- 📎 ${f.name}`), '');
                else if (m.role === 'assistant' && m.text) lines.push(`## ${(m.meta && m.meta.target_name) || m.targetName || 'AI'}${m.model ? ' · ' + m.model : ''}`, '', m.text, '');
                else if (m.role === 'filter' && m.count) lines.push(`_🛡️ Germano: ${m.count} ${this.T('masked')} (${(m.labels || []).join(', ')})_`, '');
            });
            const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
            const a = document.createElement('a');
            const d = new Date();
            const p = n => String(n).padStart(2, '0');
            a.href = URL.createObjectURL(blob);
            a.download = `germano-conversazione-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}.md`;
            document.body.append(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(a.href), 2000);
        }
        openRun(key) {
            const run = this.runs.find(r => r.key === key);
            if (!run) { this.openGlass(); return; }
            this.glassRun = run;
            this.follow = run === this.runs[this.runs.length - 1];
            this.openGlass();
            this.renderRunSelect();
            this.renderGlass();
        }

        // -------------------------------------------------------------- Glass Window
        get glassOpen() { return this.root.dataset.glass === 'open'; }
        toggleGlass() { if (this.glassOpen) this.closeGlass(); else this.openGlass(); }
        openGlass() {
            this.root.dataset.glass = 'open';
            this.$glassBtn.setAttribute('aria-pressed', 'true');
            this.renderRunSelect();
            this.renderGlass();
            this.schedulePreview(true);
        }
        closeGlass() {
            this.root.dataset.glass = 'closed';
            this.$glassBtn.setAttribute('aria-pressed', 'false');
        }
        renderRunSelect() {
            const sel = this.$runSelect;
            if (!this.runs.length) { sel.hidden = true; return; }
            sel.hidden = false;
            const fmtTime = ts => new Date(ts).toLocaleTimeString(this.lang === 'en' ? 'en-GB' : 'it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            sel.innerHTML = this.runs.slice().reverse().map(r => {
                const st = r === this.active ? this.T('gwLive') : r.done ? '✓' : r.aborted ? '⛔' : r.error ? '⚠' : '';
                return `<option value="${esc(r.key)}"${r === this.glassRun ? ' selected' : ''}>#${r.n} · ${fmtTime(r.started)} · ${esc(r.target.kind === 'protect' ? this.T('protectOnly') : r.target.name)} ${st}</option>`;
            }).join('');
        }
        renderGlassSoon(run, streaming) {
            if (!this.glassOpen || run !== this.glassRun) {
                this.renderStatus();
                return;
            }
            if (streaming) {
                if (this.glassQueued) return;
                this.glassQueued = true;
                setTimeout(() => { this.glassQueued = false; this.renderStream(); this.renderStatus(); }, 90);
                return;
            }
            this.renderGlass();
        }
        tick() {
            const run = this.glassRun;
            if (!this.glassOpen || !run) return;
            if (!run.ended) this.$gwTimer.textContent = fmtSec(Date.now() - run.started);
        }
        phaseText(run) {
            if (!run) return [this.preview ? this.T('gwPreview') : this.T('gwIdle'), ''];
            if (run.stopRequested && !run.ended) return [this.lang === 'en' ? 'Stopping…' : 'Interruzione in corso…', 'warn'];
            switch (run.phase) {
                case 'starting': case 'start': return [this.T('gwStarting'), 'live'];
                case 'engine': return [this.T('shieldStarting'), 'warn'];
                case 'protecting': return [this.T('gwProtecting'), 'live'];
                case 'review': return [this.T('gwReview'), 'warn'];
                case 'transmitting': return [this.T('gwTransmitting'), 'live'];
                case 'streaming': return [this.T('gwStreaming'), 'live'];
                case 'done': return [this.T('gwDone'), 'ok'];
                case 'aborted': return [this.T('gwAborted'), 'err'];
                case 'error': return [this.T('gwError'), 'err'];
                default: return [this.T('gwIdle'), ''];
            }
        }
        renderStatus() {
            const run = this.glassRun;
            const [text, cls] = this.phaseText(run);
            this.$gwState.textContent = text;
            this.$gwDot.className = 'hx-dot ' + (cls === 'live' ? 'live' : cls);
            this.$gwStop.disabled = !(this.active && run === this.active);
            if (run && run.ended) this.$gwTimer.textContent = fmtSec(run.ended - run.started);
            else if (!run) this.$gwTimer.textContent = '';
            // fasi
            const steps = ['gwStep1', 'gwStep2', 'gwStep3', 'gwStep4', 'gwStep5'];
            let state = ['', '', '', '', ''];
            if (run) {
                let at = 0;
                if (run.original && run.phase !== 'starting') at = 1;
                if (run.entities) at = 2;
                if (run.sanitized) at = 3;
                if (run.payloads.length && run.phase !== 'review') at = 4;
                if (run.phase === 'transmitting' || run.phase === 'streaming') at = 4;
                if (run.done) at = 5;
                state = steps.map((_, k) => (k < at ? 'is-done' : k === at && !run.ended ? 'is-active' : ''));
                if (run.done && run.done.protect_only) state = ['is-done', 'is-done', 'is-done', 'is-skip', 'is-skip'];
                if (run.aborted || run.error) { const k = Math.min(at, 4); state[k] = 'is-stopped'; for (let j = k + 1; j < 5; j += 1) state[j] = ''; }
            }
            this.$pipeline.innerHTML = steps.map((s, k) => `<button type="button" class="gw-step ${state[k]}" data-act="gw-jump" data-sec="${k}"><i></i><span>${k + 1} · ${esc(this.T(s))}</span></button>`).join('');
            const review = run && run.phase === 'review' && run === this.active;
            this.$gwReview.hidden = !review;
            if (review) {
                this.$gwReview.innerHTML = `<strong>${esc(this.T('gwReview'))}</strong><span>${esc(this.T('reviewWait'))}</span>
                    <div class="hx-filter-actions"><button type="button" class="hx-mini primary" data-act="approve">${esc(this.T('sendNow'))}</button>
                    <button type="button" class="hx-mini danger" data-act="block">${esc(this.T('blockSend'))}</button></div>`;
            }
        }
        sec(n, key, meta, body, live, open = true) {
            return `<section class="gw-sec${live ? ' is-live' : ''}" data-sec="${n}" data-open="${open}">
                <button type="button" class="gw-sec-head" data-act="gw-sec"><span class="gw-num">${n}</span><span class="gw-sec-title">${esc(this.T(key))}</span>
                <span class="gw-sec-meta">${meta || ''}</span>${svg('chevron', 'hx-icon-svg gw-chev')}</button>
                <div class="gw-sec-body">${body}</div></section>`;
        }
        system2Html(list) {
            // decisioni del Sistema 2: rilasciato (in chiaro), confermato (oscurato), resta oscurato (incerto o non deciso)
            if (!(list || []).length) return '';
            const tag = { rilasciato: ['info', 'gwS2rel'], confermato: ['ok', 'gwS2conf'] };
            return `<div class="gw-k">${esc(this.T('gwS2'))}</div>
                <table class="gw-table"><tbody>${list.map(d => {
                    const [cls, key] = tag[d.decision] || ['warn', 'gwS2kept'];
                    return `<tr><td class="orig">${esc(d.word)}</td><td><span class="gw-tag ${cls}">${esc(this.T(key))}</span></td>
                        <td>${esc(d.reason || '')}</td><td class="score">${d.p != null ? Math.round((1 - d.p) * 100) + '% NO' : ''}</td></tr>`;
                }).join('')}</tbody></table><div class="gw-note">${esc(this.T('gwS2note'))}</div>`;
        }
        highlightOriginal(text, items) {
            const words = Array.from(new Set((items || []).map(e => e.word).filter(w => w && w.length > 1))).sort((a, b) => b.length - a.length);
            if (!words.length) return esc(text);
            const byWord = {};
            (items || []).forEach(e => { if (e.word) byWord[e.word] = e; });
            const re = new RegExp(words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'g');
            let out = '', last = 0, m;
            while ((m = re.exec(text))) {
                const e = byWord[m[0]];
                out += esc(text.slice(last, m.index)) + `<mark class="gw-ent ${catColor(e.category)}" title="→ ${esc(e.label)}">${esc(m[0])}</mark>`;
                last = m.index + m[0].length;
            }
            return out + esc(text.slice(last));
        }
        renderGlass() {
            if (!this.glassOpen) { this.renderStatus(); return; }
            this.renderStatus();
            const run = this.glassRun;
            const body = this.$gwBody;
            const keepOpen = {};
            body.querySelectorAll('.gw-sec').forEach(s => { keepOpen[s.dataset.sec] = s.dataset.open; });
            if (!run) { body.innerHTML = this.previewHtml(); return; }
            let html = '';
            if (run.aborted) html += `<div class="gw-aborted"><strong>⛔ ${esc(run.aborted.message || this.T('abortedLocal'))}</strong>${esc(run.aborted.detail || (run.aborted.transmitted ? '' : this.T('gwStoppedBefore')))}</div>`;
            if (run.error) html += `<div class="gw-aborted"><strong>⚠ ${esc(this.T('errorTitle'))}</strong>${esc(run.error.message || '')}</div>`;
            // 1. testo originale
            const o = run.original || {};
            let b1 = `<div class="gw-k">${esc(this.T('gwPrompt'))}<button type="button" data-act="gw-copy" data-what="original">${esc(this.T('gwCopy'))}</button></div>
                <div class="gw-pre">${esc(o.prompt || '') || '<em>—</em>'}</div>`;
            if (o.system) b1 += `<div class="gw-k">${esc(this.T('gwSystem'))}</div><div class="gw-pre">${esc(o.system)}</div>`;
            if ((o.attachments || []).length) b1 += `<div class="gw-k">${esc(this.T('gwAttach'))}</div><div class="gw-line">${o.attachments.map(a => `📎 <b>${esc(a.name)}</b> (${fmtBytes(a.size)})`).join('<br>')}</div>`;
            if ((o.history || []).length) b1 += `<div class="gw-note">+ ${o.history.length} ${esc(this.T('gwHistory'))}</div>`;
            html += this.sec(1, 'gwSec1', `${(o.prompt || '').length} ${esc(this.T('gwChars'))}`, b1, false, keepOpen[1] !== 'false');
            // 2. filtro privacy
            const ent = run.entities;
            let b2;
            if (!ent) b2 = `<div class="gw-note">${esc(this.T('gwProtecting'))}</div>`;
            else {
                const items = ent.items || [];
                const cats = {};
                items.forEach(e => { cats[e.category] = (cats[e.category] || 0) + 1; });
                b2 = items.length ? `<div class="gw-cats">${Object.entries(cats).map(([c, n]) => `<span class="gw-label ${catColor(c)}">${esc(c)} × ${n}</span>`).join('')}</div>
                    <div class="gw-pre">${this.highlightOriginal(o.prompt || '', items)}</div>
                    <table class="gw-table"><thead><tr><th>${esc(this.T('gwOriginal'))}</th><th></th><th>${esc(this.T('gwLabel'))}</th><th>${esc(this.T('gwScore'))}</th></tr></thead><tbody>
                    ${items.map(e => `<tr><td class="orig">${esc(e.word)}</td><td class="arrow">→</td><td><span class="gw-label ${catColor(e.category)}">${esc(e.label)}</span></td>
                    <td class="score">${e.score != null ? Math.round(e.score * 100) + '%' : ''}</td></tr>`).join('')}</tbody></table>`
                    : `<div class="gw-note ok">✓ ${esc(this.T('gwNoEnt'))}</div>`;
                if ((ent.history_items || []).length) b2 += `<div class="gw-note">+ ${ent.history_items.length} ${esc(this.T('gwHistoryEnt'))}</div>`;
                b2 += this.system2Html(ent.system2);
                b2 += `<div class="gw-note">${esc(this.T('gwVaultNote'))}</div>`;
            }
            html += this.sec(2, 'gwSec2', ent ? `${ent.count || 0} · ${fmtSec(ent.protect_ms)}${ent.cached ? ' · cache ' + ent.cached : ''}` : '', b2, run.phase === 'protecting', keepOpen[2] !== 'false');
            // 3. testo inviato
            const s = run.sanitized;
            let b3;
            if (!s) b3 = `<div class="gw-note">${esc(this.T('gwProtecting'))}</div>`;
            else {
                b3 = (s.messages || []).map(m => {
                    if (m._html === undefined) m._html = highlightLabels(m.content || '');
                    return `<div class="gw-msg"><div class="gw-msg-role ${esc(m.role)}"><span>${esc(m.role)}</span><span>${(m.content || '').length} ${esc(this.T('gwChars'))}</span></div>
                    <div class="gw-pre">${m._html}</div></div>`;
                }).join('');
                if (s.hint) b3 += `<div class="gw-note">ℹ︎ ${esc(this.T('gwHint'))}</div>`;
                if (run.done && run.done.protect_only) b3 += `<div class="gw-note">${esc(this.T('gwNotSent'))}</div>`;
                b3 += `<div class="gw-k"><span></span><button type="button" data-act="gw-copy" data-what="sent">${esc(this.T('gwCopy'))}</button></div>`;
            }
            html += this.sec(3, 'gwSec3', s ? `${(s.messages || []).length} msg` : '', b3, false, keepOpen[3] !== 'false');
            // 4. payload
            let b4 = '';
            if (!run.payloads.length) b4 = `<div class="gw-note">${esc(run.done && run.done.protect_only ? this.T('gwNotSent') : this.T('gwWaitingPayload'))}</div>`;
            run.payloads.forEach((p, k) => {
                if (p.transport === 'cli') {
                    b4 += `<div class="gw-k">${esc(this.T('gwCli'))}<span class="gw-tag info">--${esc(p.profile || '')}</span></div>
                        <div class="gw-pre">${esc((p.argv || []).map(a => (a === '' ? '""' : /\s/.test(a) ? `"${a}"` : a)).join(' '))}</div>
                        <div class="gw-k">${esc(this.T('gwEnv'))}</div><div class="gw-headers">${Object.entries(p.env || {}).map(([a, v]) => `<span>${esc(a)}</span><span>${esc(v)}</span>`).join('')}</div>
                        <div class="gw-k">${esc(this.T('gwStdin'))}</div><div class="gw-pre">${highlightLabels(p.stdin || '')}</div>
                        ${p.via === 'direct' ? `<div class="gw-note">🌐 ${esc(this.T('gwDirect'))}</div>` : ''}
                        ${p.note ? `<div class="gw-note">${esc(p.note)}</div>` : ''}`;
                } else {
                    const viaProxy = p.via === 'proxy';
                    // evidenziazione calcolata una volta sola: i payload con allegati possono essere molto lunghi
                    if (p._html === undefined) {
                        const json = JSON.stringify(p.body ?? {}, null, 2);
                        p._html = json.length > 300000 ? esc(json) : highlight(json, 'json');
                    }
                    b4 += `${viaProxy ? `<div class="gw-k">${esc(this.T('gwViaProxy'))}</div>` : ''}
                        <div class="gw-line"><span class="gw-method">${esc(p.method || 'POST')}</span><b>${esc(p.url || '')}</b></div>
                        ${p.local_only ? `<div class="gw-note ok">🏠 ${esc(this.T('gwLocalOnly'))}</div>` : `<div class="gw-note">🌐 ${esc(this.T('gwCloud'))}</div>`}
                        <div class="gw-k">${esc(this.T('gwHeaders'))}</div><div class="gw-headers">${Object.entries(p.headers || {}).map(([a, v]) => `<span>${esc(a)}</span><span>${esc(v)}</span>`).join('')}</div>
                        <div class="gw-k">${esc(this.T('gwBody'))}<button type="button" data-act="gw-copy" data-what="payload" data-i="${k}">${esc(this.T('gwCopy'))}</button></div>
                        <div class="gw-pre json tall">${p._html}</div>`;
                }
            });
            html += this.sec(4, 'gwSec4', run.payloads.length ? `${run.payloads.length}×` : '', b4, run.phase === 'review', keepOpen[4] !== 'false');
            // 5. stream grezzo
            html += this.sec(5, 'gwSec5', '<span data-ref-stream-meta></span>', `<div class="gw-stream-counters" data-gw-counters></div>
                <div class="gw-pre tall gw-stream" data-gw-stream></div><div data-gw-extra></div>`, run.phase === 'streaming', keepOpen[5] !== 'false');
            body.innerHTML = html;
            this.renderStream(true);
        }
        renderStream(full) {
            const run = this.glassRun;
            if (!run || !this.glassOpen) return;
            const box = this.$gwBody.querySelector('[data-gw-stream]');
            if (!box) return;
            const nearEnd = box.scrollHeight - box.clientHeight - box.scrollTop < 40;
            box.innerHTML = run.raw ? highlightLabels(run.raw) : `<span class="gw-note">${esc(run.done && run.done.protect_only ? this.T('gwNotSent') : this.T('gwWaitingStream'))}</span>`;
            if (nearEnd || full) box.scrollTop = box.scrollHeight;
            const secs = run.receivedAt ? ((run.ended || Date.now()) - run.receivedAt) / 1000 : 0;
            const toks = (run.usage && run.usage.output_tokens) || Math.round(run.raw.length / 4);
            const counters = this.$gwBody.querySelector('[data-gw-counters]');
            if (counters) counters.innerHTML = `<span class="gw-tag">${run.raw.length} ${esc(this.T('gwChars'))}</span>
                <span class="gw-tag">${run.usage && run.usage.output_tokens != null ? '' : '≈'}${toks} ${esc(this.T('badgeTokens'))}</span>
                ${secs > 0.3 ? `<span class="gw-tag">${(toks / secs).toFixed(1)} ${esc(this.T('gwTps'))}</span>` : ''}
                ${run.firstToken != null ? `<span class="gw-tag info">⚡ ${fmtSec(run.firstToken)}</span>` : ''}`;
            const meta = this.$gwBody.querySelector('[data-ref-stream-meta]');
            if (meta) meta.textContent = run.raw ? `${run.raw.length}` : '';
            const extra = this.$gwBody.querySelector('[data-gw-extra]');
            if (extra) {
                let x = '';
                if (run.thinking) x += `<details><summary class="gw-k">${esc(this.T('gwThinking'))}</summary><div class="gw-pre">${esc(run.thinking)}</div></details>`;
                if (run.frames.length) x += `<details><summary class="gw-k">${esc(this.T('gwFrames'))} (${run.frames.length})</summary><div class="gw-pre">${esc(run.frames.join(''))}</div></details>`;
                if (run.cli.length) x += `<details><summary class="gw-k">${esc(this.T('gwCliLines'))} (${run.cli.length})</summary><div class="gw-pre">${esc(run.cli.join('\n'))}</div></details>`;
                if (extra.dataset.sig !== `${run.thinking.length}|${run.frames.length}|${run.cli.length}`) { extra.innerHTML = x; extra.dataset.sig = `${run.thinking.length}|${run.frames.length}|${run.cli.length}`; }
            }
        }
        async copyGlass(what, btn) {
            const run = this.glassRun;
            let text = '';
            if (what === 'original' && run) text = run.original?.prompt || '';
            else if (what === 'sent' && run && run.sanitized) text = (run.sanitized.messages || []).map(m => `[${m.role}]\n${m.content}`).join('\n\n');
            else if (what === 'payload' && run) { const p = run.payloads[+btn.dataset.i || 0]; text = JSON.stringify(p && p.body, null, 2); }
            else if (what === 'preview' && this.preview) text = this.preview.anonymized || '';
            if (text && await copyText(text)) { const old = btn.textContent; btn.textContent = this.T('copied'); setTimeout(() => { btn.textContent = old; }, 1400); }
        }

        // -------------------------------------------------------------- anteprima mentre si scrive
        schedulePreview(now) {
            clearTimeout(this.previewTimer);
            if (!this.glassOpen || !this.prefs.preview) return;
            this.previewTimer = setTimeout(() => this.runPreview(), now ? 50 : 900);
        }
        async runPreview() {
            const text = (this.$input.value || '').trim();
            if (!this.glassOpen || !this.prefs.preview) return;
            if (this.active || (this.glassRun && !this.glassRun.ended)) return;
            if (!text) { this.preview = null; if (!this.glassRun || this.follow) { this.glassRun = this.glassRun && this.follow ? this.glassRun : null; } this.renderGlass(); return; }
            const limit = (this.meta.limits && this.meta.limits.preview_chars) || 12000;
            if (!this.engineInfo().ready) { this.preview = { text, off: true }; this.showPreview(); return; }
            if (text.length > limit) { this.preview = { text: text.slice(0, 400), long: true }; this.showPreview(); return; }
            if (this.previewCtrl) this.previewCtrl.abort();
            const ctrl = new AbortController();
            this.previewCtrl = ctrl;
            try {
                const r = await this.api('/api/harness/v2/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                                                         body: JSON.stringify({ text, options: this.o.options && this.o.options() }), signal: ctrl.signal });
                const data = await r.json().catch(() => ({}));
                if (ctrl !== this.previewCtrl) return;
                if (!r.ok || data.status !== 'success') { this.preview = { text, off: r.status === 503 }; this.showPreview(); return; }
                this.preview = { text, anonymized: data.anonymized, entities: data.entities || [], ms: data.elapsed_ms, cached: data.cached };
                this.showPreview();
            } catch (e) { /* anteprima superata da una piu' recente */ }
        }
        showPreview() {
            if (!this.glassOpen) return;
            if (this.active) return;
            const last = this.runs[this.runs.length - 1];
            if (this.glassRun && this.glassRun !== last) return;   // l'utente sta guardando una richiesta precedente
            this.glassRun = null;
            this.renderGlass();
        }
        previewHtml() {
            const p = this.preview;
            if (!p) return `<div class="gw-empty">${svg('glass')}<span>${esc(this.T('gwEmpty'))}</span></div>`;
            let html = `<div class="gw-k"><span class="gw-preview-tag">${esc(this.T('gwPreview'))}</span></div><div class="gw-note">${esc(this.T('gwPreviewNote'))}</div>`;
            if (p.off) return html + `<div class="gw-note">${esc(this.T('gwPreviewOff'))}</div>`;
            if (p.long) return html + `<div class="gw-note">${esc(this.T('gwPreviewLong'))}</div>`;
            const items = p.entities || [];
            html += this.sec(1, 'gwSec1', `${p.text.length} ${esc(this.T('gwChars'))}`, `<div class="gw-pre">${esc(p.text)}</div>`, false);
            html += this.sec(2, 'gwSec2', `${items.length} · ${fmtSec(p.ms)}${p.cached ? ' · cache' : ''}`, items.length
                ? `<div class="gw-pre">${this.highlightOriginal(p.text, items)}</div><table class="gw-table"><tbody>${items.map(e => `<tr><td class="orig">${esc(e.word)}</td><td class="arrow">→</td><td><span class="gw-label ${catColor(e.category)}">${esc(e.label)}</span></td><td class="score">${e.score != null ? Math.round(e.score * 100) + '%' : ''}</td></tr>`).join('')}</tbody></table>`
                : `<div class="gw-note ok">✓ ${esc(this.T('gwNoEnt'))}</div>`, true);
            html += this.sec(3, 'gwSec3', '', `<div class="gw-pre">${highlightLabels(p.anonymized || '')}</div><div class="gw-k"><span></span><button type="button" data-act="gw-copy" data-what="preview">${esc(this.T('gwCopy'))}</button></div>`, false);
            return html;
        }
    }

    // ------------------------------------------------------------------ file trascinati (anche cartelle)
    function readEntries(reader) {
        return new Promise(resolve => {
            const all = [];
            const next = () => reader.readEntries(list => { if (!list.length) return resolve(all); all.push(...list); next(); }, () => resolve(all));
            next();
        });
    }
    async function collect(entry, out) {
        if (!entry || out.length >= MAX_FILES) return;
        if (entry.isFile) await new Promise(res => entry.file(f => { out.push(f); res(); }, () => res()));
        else if (entry.isDirectory) { for (const e of await readEntries(entry.createReader())) await collect(e, out); }
    }
    async function filesFromDrop(dt) {
        const entries = Array.from(dt.items || []).map(it => (it.webkitGetAsEntry ? it.webkitGetAsEntry() : null)).filter(Boolean);
        if (entries.length) { const out = []; for (const e of entries) await collect(e, out); return out; }
        return Array.from(dt.files || []);
    }

    window.GermanoHarness = {
        mount(root, opts) { return new Harness(root, opts); },
        renderMarkdown, highlight, restorePlain, esc,
    };
})();
