const translations = {
    "it": {
        "seo_title": "Germano AI - Anonimizzazione Documentale Intelligente",
        "seo_desc": "Germano AI è una potente suite open-source per l'anonimizzazione intelligente di documenti aziendali e della Pubblica Amministrazione.",
        "og_title": "Germano AI - Anonimizzazione Documentale",
        "og_desc": "Proteggi i tuoi dati offline con la potente suite AI open-source per Pubbliche Amministrazioni e aziende.",
        "nav_home": "Home",
        "nav_guide": "Documentazione",
        "nav_about": "Cos'è",
        "nav_modes": "PA vs PD",
        "nav_usecases": "Casi d'Uso",
        "nav_download": "Download",
        "hero_badge": "Open Source & 100% Offline",
        "hero_title_1": "La Privacy Documentale,<br>",
        "hero_title_2": "nell'Era dell'Intelligenza Artificiale.",
        "hero_subtitle": "Anonimizza contratti, sentenze e documenti sensibili direttamente sul tuo computer. Nessun cloud, nessuna fuga di dati. Gratuito per sempre.",
        "btn_download": "Scarica Standalone",
        "btn_github": "Sorgente su GitHub",
        "about_title_1": "Cos'è",
        "about_card1_title": "Intelligenza Artificiale Locale",
        "about_card1_desc": "Sfrutta potenti modelli Transformer e OCR (EasyOCR) che girano direttamente sulla tua CPU o GPU. I tuoi dati non lasciano mai il tuo ufficio.",
        "about_card2_title": "Multi-Formato e \"In-Place\"",
        "about_card2_desc": "Elabora PDF, DOCX, XLSX mantenendo intatto il layout originale, la formattazione, le tabelle e persino le macro VBA.",
        "about_card3_title": "Censura Testuale & Visiva (Biometria)",
        "about_card3_desc": "Intercetta dati sensibili nel testo. Nei PDF o nelle immagini (es. <strong>Carta di Identità</strong>), utilizza il riconoscimento facciale OpenCV per offuscare automaticamente le fototessere e l'OCR per leggere e censurare i dati anagrafici stampati.",
        "modes_title": "Profili di Conformità",
        "modes_desc": "Germano AI è progettato per adattarsi sia ad ambienti altamente regolamentati che a professionisti privati.",
        "pa_title": "Germano PA (Pubblica Amministrazione)",
        "pa_badge": "A Norma CAD/GDPR",
        "pa_feat1": "Filtri di censura bloccati e attivi al 100%.",
        "pa_feat2": "Nessuna possibilità di disabilitare l'OCR o la biometria facciale per garantire sicurezza assoluta.",
        "pa_feat3": "Garantisce il rispetto del <strong>GDPR (Regolamento UE 2016/679)</strong> sulla minimizzazione dei dati e del <strong>CAD (Codice dell'Amministrazione Digitale)</strong> per la gestione documentale.",
        "pd_title": "Germano PD (Pubblico Dominio)",
        "pd_badge": "Configurazione Libera",
        "pd_feat1": "Totale controllo su quali filtri (nomi, email, ecc.) attivare.",
        "pd_feat2": "Soglia di affidabilità dell'Intelligenza Artificiale regolabile a piacimento.",
        "pd_feat3": "Ideale per aziende private, avvocati e ricercatori che necessitano di flessibilità operativa.",
        "usecase_title_1": "Sblocca il potere di",
        "usecase_title_2": "(in sicurezza)",
        "usecase_desc": "Molte Pubbliche Amministrazioni e aziende esitano a utilizzare i Large Language Models commerciali per paura di caricare documenti contenenti <strong>Dati Personali Identificabili (PII)</strong> su server cloud esteri.",
        "step1_title": "Documento Originale",
        "step1_desc": "Contiene nomi, codici fiscali...",
        "step2_title": "Germano AI (Offline)",
        "step2_desc": "Anonimizza in locale",
        "step3_title": "LLM (Cloud)",
        "step3_desc": "Elaborazione sicura",
        "usecase_conclusion": "Con Germano AI, anonimizzi prima tutto offline. Una volta \"ripulito\", il documento può essere inviato a qualsiasi LLM commerciale per riassunti, traduzioni o estrazioni, mantenendo la totale compliance al GDPR.",
        "dl_title": "Inizia Subito (Gratis e Open Source)",
        "dl_desc": "Nessun installer complesso, nessuna configurazione. Estrai lo ZIP, fai doppio clic su <code>START.bat</code> e aprirai la fantastica <strong>Dashboard di Controllo</strong> locale nel tuo browser.",
        "dl_btn_standalone": "Download Versione Standalone (~4 GB)",
        "dl_btn_github": "Codice Sorgente su GitHub",
        "lic_title": "Licenza GNU GPL v3",
        "lic_desc": "Germano AI è orgogliosamente distribuito sotto licenza <strong>GNU General Public License v3.0</strong>. Questo significa che sei libero di usare, studiare e condividere il software a costo zero, perfino per uso commerciale. L'unica regola è che se modifichi o distribuisci una versione derivata di Germano AI, devi renderla anch'essa Open Source rilasciandola sotto la stessa licenza GPL v3. Vogliamo che la privacy sia un diritto accessibile a tutti!",
        "collab_title": "🤝 Collabora al Progetto!",
        "collab_desc": "Germano AI è un progetto guidato dalla community. Sei uno sviluppatore Python, un esperto legale o un appassionato di AI? Unisciti a noi! Fai un fork del repository su GitHub, apri una Pull Request e aiutaci a migliorare l'algoritmo, aggiungere nuovi formati supportati o ottimizzare l'interfaccia utente.",
        "footer_madein": "Orgogliosamente sviluppato a Sassari, Italia 🇮🇹",
        "footer_copy": "Un progetto Open Source di <a href='https://www.yesc.it/' target='_blank' style='color: var(--primary); font-weight: bold;'>Yes Consulting</a> per proteggere i tuoi dati.",
        
        "guide_title": "Manuale e",
        "guide_subtitle": "Tutto ciò che devi sapere per installare, configurare e padroneggiare Germano AI sul tuo computer.",
        "guide_h2_1": "1. Come si usa (Primi Passi)",
        "guide_p_1": "Germano AI Standalone è stato progettato per essere \"Plug & Play\". Non richiede installazione, server web o configurazioni di sistema complesse.",
        "guide_step_1": "Scarica l'archivio ZIP dal link in homepage e scompattalo in una cartella a tua scelta.",
        "guide_step_2": "Fai doppio clic sul file <code>START.bat</code> (su Windows). Questo avvierà il motore in background e aprirà automaticamente la Dashboard nel tuo browser.",
        "guide_step_3": "Copia i tuoi documenti da anonimizzare dentro la cartella <code>input/</code>.",
        "guide_step_4": "Dalla Dashboard, assicurati di aver selezionato il \"Profilo di Conformità\" desiderato (PA o PD) e clicca su <strong>START DAEMON</strong>.",
        "guide_step_5": "Attendi l'elaborazione. Troverai i file puliti nella cartella <code>output/</code>.",
        
        "guide_nav_title": "Indice Argomenti",
        "guide_nav_api": "2. Integrazione API REST",
        "guide_api_desc": "Germano AI Standalone include un endpoint API locale che ti permette di inviare documenti in modo programmatico dal tuo software (es. Gestionale, CRM o Portale Web PA) e ricevere immediatamente il file anonimizzato in risposta.",
        "guide_api_endpoint": "Endpoint",
        "guide_api_req": "Esempio di Richiesta (cURL)",
        "guide_api_res": "Risposta",
        "guide_api_res_desc": "L'API è sincrona. Attenderà l'elaborazione del demone IA in background (fino a 60 secondi) e restituirà direttamente il <strong>flusso binario del file anonimizzato</strong> come allegato scaricabile.",
        
        "guide_h2_2": "3. Struttura delle Cartelle",
        "guide_p_2": "Il sistema organizza il lavoro automaticamente spostando i file in base al loro stato:",
        "guide_folder_1": "La cartella di partenza. Inserisci qui i file. Il sistema supporta anche sottocartelle (che verranno replicate fedelmente nell'output).",
        "guide_folder_2": "Dove finiscono i documenti anonimizzati. Se il file era un DOCX, troverai un DOCX, formattato e impaginato come l'originale.",
        "guide_folder_3": "Dove vengono parcheggiati i file originali dopo essere stati elaborati, per evitare di sovrascriverli o perderli.",
        "guide_folder_4": "Se un documento è protetto da password, corrotto, o genera errori imprevisti, viene spostato qui per l'analisi manuale.",
        "guide_folder_5": "Contiene un file <code>.json</code> per ogni documento processato, con la mappa esatta (log) di cosa è stato trovato e sostituito (utile a fini di audit e controllo).",
        "guide_h2_3": "4. Tecnologie Utilizzate",
        "guide_p_3": "Dietro le quinte, Germano AI orchestra i migliori modelli Open Source disponibili per garantire massima affidabilità:",
        "guide_tech_1": "Utilizza il modello NLP `openai/privacy-filter` per la \"Named Entity Recognition\" (NER), per intercettare nomi di persona e luoghi all'interno del contesto di una frase.",
        "guide_tech_2": "Un solido dizionario di RegEx italiane per catturare inequivocabilmente Codici Fiscali, Partite IVA, Numeri di Telefono e Indirizzi Email.",
        "guide_tech_3": "L'Optical Character Recognition entra in azione quando elabori scansioni, PDF immagini o foto di documenti d'identità. Legge il testo \"pixelato\" per permettere ai motori NLP di censurarlo disegnando dei rettangoli neri.",
        "guide_tech_4": "Rilevamento facciale biometrico automatico tramite classificatori di Haar per l'oscuramento visivo delle fototessere sui documenti.",
        "guide_tech_5": "Consente di accelerare l'AI non solo su GPU Nvidia (CUDA), ma anche su GPU AMD e Intel.",
        "guide_h2_4": "5. Requisiti di Sistema Hardware",
        "guide_p_4": "Poiché il sistema esegue l'Intelligenza Artificiale localmente, richiede potenza di calcolo. Un PC lento riuscirà comunque ad anonimizzare i file, ma impiegherà più tempo."
    },
    "en": {
        "seo_title": "Germano AI - Smart Document Anonymization",
        "seo_desc": "Germano AI is a powerful open-source suite for intelligent document anonymization, built for Public Administrations and Enterprise.",
        "og_title": "Germano AI - Document Anonymization",
        "og_desc": "Protect your data offline with the powerful open-source AI suite for enterprise and public sector.",
        "nav_home": "Home",
        "nav_guide": "Documentation",
        "nav_about": "About",
        "nav_modes": "PA vs PD",
        "nav_usecases": "Use Cases",
        "nav_download": "Download",
        "hero_badge": "Open Source & 100% Offline",
        "hero_title_1": "Document Privacy,<br>",
        "hero_title_2": "in the Era of Artificial Intelligence.",
        "hero_subtitle": "Anonymize contracts, court sentences, and sensitive documents directly on your computer. No cloud, no data leaks. Free forever.",
        "btn_download": "Download Standalone",
        "btn_github": "Source Code on GitHub",
        "about_title_1": "What is",
        "about_card1_title": "Local Artificial Intelligence",
        "about_card1_desc": "Utilize powerful Transformer models and OCR (EasyOCR) running directly on your CPU or GPU. Your data never leaves your office.",
        "about_card2_title": "Multi-Format & \"In-Place\"",
        "about_card2_desc": "Process PDF, DOCX, XLSX keeping the original layout, formatting, tables, and even VBA macros fully intact.",
        "about_card3_title": "Textual & Visual Redaction (Biometrics)",
        "about_card3_desc": "Intercepts sensitive data in text. In PDFs or images (e.g. <strong>ID Cards</strong>), it uses OpenCV facial recognition to automatically blur ID photos and OCR to read and censor printed personal data.",
        "modes_title": "Compliance Profiles",
        "modes_desc": "Germano AI is designed to adapt to both highly regulated environments and private professionals.",
        "pa_title": "Germano PA (Public Administration)",
        "pa_badge": "GDPR Compliant",
        "pa_feat1": "Redaction filters locked and 100% active.",
        "pa_feat2": "No option to disable OCR or facial biometrics, ensuring absolute security.",
        "pa_feat3": "Guarantees compliance with <strong>GDPR (EU Regulation 2016/679)</strong> on data minimization and strict digital administration protocols.",
        "pd_title": "Germano PD (Public Domain)",
        "pd_badge": "Free Configuration",
        "pd_feat1": "Total control over which filters (names, emails, etc.) to activate.",
        "pd_feat2": "AI reliability threshold adjustable at will.",
        "pd_feat3": "Ideal for private companies, lawyers, and researchers who need operational flexibility.",
        "usecase_title_1": "Unlock the power of",
        "usecase_title_2": "(safely)",
        "usecase_desc": "Many Public Administrations and companies hesitate to use commercial Large Language Models for fear of uploading documents containing <strong>Personally Identifiable Information (PII)</strong> to foreign cloud servers.",
        "step1_title": "Original Document",
        "step1_desc": "Contains names, IDs...",
        "step2_title": "Germano AI (Offline)",
        "step2_desc": "Local Anonymization",
        "step3_title": "LLM (Cloud)",
        "step3_desc": "Safe Processing",
        "usecase_conclusion": "With Germano AI, you anonymize everything offline first. Once \"cleaned\", the document can be sent to any commercial LLM for summaries, translations, or data extraction, maintaining full GDPR compliance.",
        "dl_title": "Start Now (Free & Open Source)",
        "dl_desc": "No complex installers, no configuration. Extract the ZIP, double-click on <code>START.bat</code>, and you will open the amazing local <strong>Control Dashboard</strong> in your browser.",
        "dl_btn_standalone": "Download Standalone Version (~4 GB)",
        "dl_btn_github": "Source Code on GitHub",
        "lic_title": "GNU GPL v3 License",
        "lic_desc": "Germano AI is proudly distributed under the <strong>GNU General Public License v3.0</strong>. This means you are free to use, study, and share the software at zero cost, even for commercial use. The only rule is that if you modify or distribute a derivative version of Germano AI, you must make it Open Source as well, releasing it under the same GPL v3 license. We want privacy to be a right accessible to everyone!",
        "collab_title": "🤝 Collaborate with the Project!",
        "collab_desc": "Germano AI is a community-driven project. Are you a Python developer, a legal expert, or an AI enthusiast? Join us! Fork the repository on GitHub, open a Pull Request, and help us improve the algorithm, add new supported formats, or optimize the user interface.",
        "footer_madein": "Proudly developed in Sassari, Italy 🇮🇹",
        "footer_copy": "An Open Source project by <a href='https://www.yesc.it/' target='_blank' style='color: var(--primary); font-weight: bold;'>Yes Consulting</a> to protect your data.",
        
        "guide_title": "Manual and",
        "guide_subtitle": "Everything you need to know to install, configure, and master Germano AI on your computer.",
        "guide_h2_1": "1. How to Use (First Steps)",
        "guide_p_1": "Germano AI Standalone is designed to be \"Plug & Play\". It requires no installation, web servers, or complex system configurations.",
        "guide_step_1": "Download the ZIP archive from the link on the homepage and extract it to a folder of your choice.",
        "guide_step_2": "Double-click the <code>START.bat</code> file (on Windows). This will start the background engine and automatically open the Dashboard in your browser.",
        "guide_step_3": "Copy the documents you want to anonymize into the <code>input/</code> folder.",
        "guide_step_4": "From the Dashboard, make sure you have selected the desired \"Compliance Profile\" (PA or PD) and click <strong>START DAEMON</strong>.",
        "guide_step_5": "Wait for the processing. You will find the cleaned files in the <code>output/</code> folder.",
        
        "guide_nav_title": "Table of Contents",
        "guide_nav_api": "2. REST API Integration",
        "guide_api_desc": "Germano AI Standalone includes a local API endpoint that allows you to programmatically send documents from your software (e.g. ERP, CRM or Web Portal) and immediately receive the anonymized file in response.",
        "guide_api_endpoint": "Endpoint",
        "guide_api_req": "Request Example (cURL)",
        "guide_api_res": "Response",
        "guide_api_res_desc": "The API is synchronous. It will wait for the AI daemon to process the file in the background (up to 60 seconds) and will directly return the <strong>binary stream of the anonymized file</strong> as a downloadable attachment.",
        
        "guide_h2_2": "3. Folder Structure",
        "guide_p_2": "The system automatically organizes the work by moving files based on their status:",
        "guide_folder_1": "The starting folder. Place your files here. The system also supports subfolders (which will be faithfully replicated in the output).",
        "guide_folder_2": "Where the anonymized documents end up. If the file was a DOCX, you will find a DOCX, formatted and paginated like the original.",
        "guide_folder_3": "Where original files are parked after being processed, to avoid overwriting or losing them.",
        "guide_folder_4": "If a document is password-protected, corrupted, or generates unexpected errors, it is moved here for manual analysis.",
        "guide_folder_5": "Contains a <code>.json</code> file for each processed document, with the exact map (log) of what was found and replaced (useful for audit and control purposes).",
        "guide_h2_3": "4. Technologies Used",
        "guide_p_3": "Behind the scenes, Germano AI orchestrates the best Open Source models available to ensure maximum reliability:",
        "guide_tech_1": "Uses the NLP model `openai/privacy-filter` for \"Named Entity Recognition\" (NER), to intercept names of people and places within the context of a sentence.",
        "guide_tech_2": "A solid dictionary of Italian RegEx to unequivocally capture Fiscal Codes, VAT Numbers, Phone Numbers, and Email Addresses.",
        "guide_tech_3": "Optical Character Recognition kicks in when you process scans, PDF images, or photos of identity documents. It reads the \"pixelated\" text to allow NLP engines to censor it by drawing black rectangles.",
        "guide_tech_4": "Automatic biometric facial detection via Haar classifiers for the visual obscuration of passport photos on documents.",
        "guide_tech_5": "Allows accelerating AI not only on Nvidia GPUs (CUDA), but also on AMD and Intel GPUs.",
        "guide_h2_4": "5. Hardware System Requirements",
        "guide_p_4": "Since the system runs Artificial Intelligence locally, it requires computing power. A slower PC will still be able to anonymize files, but it will take more time."
    }
};

let currentLang = 'it';

function setLanguage(lang, updateUrl = true) {
    if (!translations[lang]) return;
    currentLang = lang;
    
    // Update HTML elements
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (translations[lang][key]) {
            el.innerHTML = translations[lang][key];
        }
    });

    // Update SEO Meta Tags dynamically
    document.getElementById('page-title').innerText = translations[lang]['seo_title'];
    document.getElementById('meta-desc').setAttribute('content', translations[lang]['seo_desc']);
    document.getElementById('og-title').setAttribute('content', translations[lang]['og_title']);
    document.getElementById('og-desc').setAttribute('content', translations[lang]['og_desc']);

    // Update buttons state
    document.querySelectorAll('.lang-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.getElementById(`btn-${lang}`).classList.add('active');
    document.documentElement.lang = lang;

    // Update URL parameter without reloading (for shareability and SEO hints)
    if (updateUrl) {
        const url = new URL(window.location);
        url.searchParams.set('lang', lang);
        window.history.pushState({}, '', url);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Check URL parameters first
    const urlParams = new URLSearchParams(window.location.search);
    const urlLang = urlParams.get('lang');

    if (urlLang === 'en' || urlLang === 'it') {
        setLanguage(urlLang, false);
    } else {
        // Detect User Agent Language if no URL parameter
        const userLang = navigator.language || navigator.userLanguage;
        if (!userLang.toLowerCase().startsWith('it')) {
            setLanguage('en', false);
        } else {
            setLanguage('it', false);
        }
    }

    // Language Buttons Event Listeners
    document.getElementById('btn-it').addEventListener('click', () => setLanguage('it'));
    document.getElementById('btn-en').addEventListener('click', () => setLanguage('en'));

    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // Intersection Observer for scroll animations
    const observerOptions = {
        root: null,
        rootMargin: '0px',
        threshold: 0.15
    };

    const observer = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    const elementsToAnimate = document.querySelectorAll('.fade-in, .slide-in-left, .slide-in-right');
    elementsToAnimate.forEach(el => observer.observe(el));
});


// KB Scroll Spy
document.addEventListener('DOMContentLoaded', () => {
    const sections = document.querySelectorAll('.kb-content section');
    const navLinks = document.querySelectorAll('.kb-nav a');
    
    if (sections.length > 0 && navLinks.length > 0) {
        const observerOptions = { root: null, rootMargin: '0px', threshold: 0.5 };
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const id = entry.target.getAttribute('id');
                    navLinks.forEach(link => {
                        link.classList.remove('active');
                        if (link.getAttribute('href') === '#' + id) {
                            link.classList.add('active');
                        }
                    });
                }
            });
        }, observerOptions);
        sections.forEach(section => observer.observe(section));
    }
});
