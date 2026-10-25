"""Germano AI - finestra dell'applicazione con pywebview (Linux: Qt WebEngine incluso nel programma; macOS: WebKit di
sistema tramite PyObjC). Su Linux il launcher (germano_desktop.py) la avvia in un processo separato: se il sistema
non avesse le librerie grafiche necessarie, la finestra non si apre, questo processo esce con il codice 3 e il
launcher ripiega su un browser, senza mai lasciare Germano a meta'. Su macOS il launcher usa run_window() nello stesso
processo, cosi' nel Dock compare l'app Germano.

Uso (Linux):  python germano_window.py URL TITOLO [ICONA]
Uscita: 0 = la finestra era aperta ed e' stata chiusa dall'utente; 3 = la finestra non si e' potuta aprire.
"""
import os
import sys


def run_window(url, title, icon=None, storage=None, gui=None, watchdog=None, on_shown=None):
    """Apre la finestra e ritorna quando l'utente la chiude. watchdog(window) gira in un thread a parte (per
    chiudere la finestra se il server si ferma); on_shown() viene chiamata quando la finestra e' visibile."""
    import webview
    window = webview.create_window(title, url, width=1280, height=860, min_size=(900, 640), text_select=True)
    if on_shown:
        window.events.shown += on_shown
    kwargs = {"gui": gui, "private_mode": False}
    if storage:
        os.makedirs(storage, exist_ok=True)
        kwargs["storage_path"] = storage       # preferenze dell'interfaccia (es. la lingua) tra un avvio e l'altro
    if icon and os.path.isfile(icon):
        kwargs["icon"] = icon
    if watchdog:
        webview.start(watchdog, window, **kwargs)
    else:
        webview.start(**kwargs)
    return window


def desktop_id():
    """Nome della voce di menu installata dal pacchetto .deb (germano-ai o germano-ai-client): GNOME associa la
    finestra alla voce di menu, e quindi al nome e all'icona del programma, tramite questo identificativo."""
    here = os.path.dirname(os.path.abspath(__file__))
    edition = None
    try:
        import json
        with open(os.path.join(here, "germano_install.json"), encoding="utf-8") as f:
            edition = json.load(f).get("edition")
    except (OSError, ValueError, AttributeError):
        pass
    if edition not in ("suite", "client"):
        edition = "client" if os.path.isfile(os.path.join(here, "client.py")) else "suite"
    return "germano-ai-client" if edition == "client" else "germano-ai"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    url, title = sys.argv[1], sys.argv[2]
    icon = sys.argv[3] if len(sys.argv) > 3 else None
    os.environ.setdefault("QT_API", "pyside6")
    # Ubuntu 24.04+ limita gli spazi utente non privilegiati usati dalla sandbox di Chromium: la finestra mostra solo
    # la Dashboard locale di Germano (127.0.0.1), quindi la sandbox del motore web non serve.
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    try:
        # Wayland: app_id = nome del file .desktop; X11: classe WM_CLASS = nome dell'applicazione (StartupWMClass)
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.setDesktopFileName(desktop_id())
        QGuiApplication.setApplicationName(desktop_id())
    except Exception:
        pass
    shown = {"ok": False}

    def ready():
        shown["ok"] = True
        print("pronto", flush=True)
    try:
        run_window(url, title, icon, os.environ.get("GERMANO_WEBVIEW_STORAGE"), "qt", on_shown=ready)
    except Exception as e:  # librerie grafiche mancanti, nessun display...
        print(f"errore: {type(e).__name__}: {e}", flush=True)
    return 0 if shown["ok"] else 3


if __name__ == "__main__":
    sys.exit(main())
