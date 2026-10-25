#!/bin/bash
# Germano AI v0.60 - avvio su Linux (finestra dedicata, nessun terminale). Un solo lanciatore per tutti i pacchetti:
# la suite completa apre la Dashboard unificata, il pacchetto client il pannello. Installato con il pacchetto .deb il
# programma usa sempre il proprio Python (runtime/); solo la copia di sviluppo ripiega sul python3 del sistema.
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$DIR/runtime/bin/python3"
if [ ! -x "$PY" ] && [ ! -f "$DIR/germano_install.json" ]; then PY="$(command -v python3)"; fi
if [ -z "$PY" ] || [ ! -x "$PY" ]; then
  MSG="Germano AI non trova il proprio Python ($DIR/runtime/bin/python3): reinstalla il pacchetto .deb di Germano AI."
  command -v zenity >/dev/null 2>&1 && zenity --error --title="Germano AI" --text="$MSG"
  echo "$MSG" >&2
  exit 1
fi
exec "$PY" "$DIR/germano_desktop.py" auto
