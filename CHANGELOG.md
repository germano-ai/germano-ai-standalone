# Changelog

Tutte le modifiche a questo progetto saranno documentate in questo file.
Il formato è basato su [Keep a Changelog](https://keepachangelog.com/it-IT/1.0.0/).

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
