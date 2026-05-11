# Changelog

Tutte le modifiche a questo progetto saranno documentate in questo file.
Il formato è basato su [Keep a Changelog](https://keepachangelog.com/it-IT/1.0.0/).

## [0.09-alpha] - 2026-05-12
### Aggiunto
- **API REST Locale Sincrona**: Aggiunto l'endpoint `POST /api/v1/anonymize` al server Flask. Ora software di terze parti (CRM, Gestionali) possono inviare un file a Germano AI e ricevere come risposta HTTP diretta il file PDF/Word anonimizzato, delegando il calcolo asincrono al background.
- **Nuovo Layout Knowledge Base**: Riprogettata la pagina `guide.html` con un vero layout da Knowledge Base (sidebar sticky a sinistra per la navigazione rapida e contenuti estesi a destra).
- **Documentazione API**: Inserita nella KB una sezione dedicata per spiegare le chiamate API con esempi in cURL.
- **Scroll-spy Navigazione**: Aggiunto Intersection Observer in Javascript per evidenziare dinamicamente i link della sidebar durante lo scorrimento della documentazione.

## [0.08-alpha] - 2026-05-12
### Aggiunto
- **Pagina "Documentazione / Guida"**: Creata la pagina `guide.html` nel sito web ufficiale, completamente bilingue, contenente i Primi Passi, Struttura delle Cartelle, Requisiti di Sistema e Tecnologie Utilizzate.
- **Sistema Auto-Update**: Inserito un sistema di notifica automatica in `server.py` e `script.js` (Standalone). All'avvio della dashboard, il sistema verifica l'ultima release dal file `VERSION` su GitHub e mostra un banner se c'è un aggiornamento disponibile.

## [0.07-alpha] - 2026-05-12
### Modificato
- Scambiato l'ordine degli elementi nella navbar: il selettore lingua ora è al centro-destra e il pulsante Download è posizionato all'estrema destra.
- Migliorata la fluidità e il layout della navbar su dispositivi mobili.

## [0.06-alpha] - 2026-05-12
### Modificato
- Rimosse 3 voci superflue dal menu di navigazione ("Cos'è", "PA vs PD", "Casi d'Uso").
- Spostato a destra il pulsante principale "Download" sulla navbar.

## [0.05-alpha] - 2026-05-12
### Aggiunto
- Inserita firma "Sviluppato da Yes Consulting - www.yesc.it" sia nel file README.md del repository GitHub che nel footer dinamico (IT/EN) del sito web ufficiale.

## [0.04-alpha] - 2026-05-12
### Aggiunto
- **SEO Multilingua e Indicizzazione Inglese**: Inseriti tag `hreflang` e traduzione dinamica di `title` e `meta description` tramite manipolazione del DOM.
- **Supporto URL Parameter**: Aggiunta logica `?lang=en` o `?lang=it` con `history.pushState` al click sulle bandierine per permettere la condivisione diretta di una lingua specifica e aiutare l'indicizzazione dei motori di ricerca.

## [0.03-alpha] - 2026-05-12
### Aggiunto
- **Supporto Multilingua (IT/EN)**: Implementata architettura JSON `data-i18n` con rilevamento automatico della lingua via `navigator.language` e selettore bandierine (🇮🇹/🇬🇧).
- **SEO Optimization**: Aggiunti tag meta e Open Graph per una perfetta indicizzazione e condivisione sui social.
- **Spiegazione Licenza GNU GPL v3**: Aggiunto paragrafo esplicativo sui diritti e doveri del software libero.
- **Made in Sassari**: Aggiunto badge nel footer per evidenziare l'origine del progetto in Italia.

## [0.02-alpha] - 2026-05-12
### Aggiunto
- Aggiornamento della Landing Page con specifiche di legge (CAD e GDPR).
- Spiegazione estesa della differenza tra Pubblica Amministrazione (Germano PA) e Pubblico Dominio (Germano PD).
- Inserita sezione di collaborazione Open Source su GitHub.
- Esempio esplicito di censura biometria e OCR su documenti d'identità.

## [0.01-alpha] - 2026-05-11
### Aggiunto
- Prima release Standalone ufficiale.
- Riorganizzazione del layout UI in CSS Grid a colonne.
- Sistema "Killer" di processi orfani all'avvio.
- Gestione timeout, fallback CPU/GPU e quarantena documenti danneggiati.
- Supporto a file PDF, DOCX, XLSX, TXT, RTF.
