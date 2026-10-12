#!/bin/bash
# Linux: запуск из исходников (нужны python3 и служба usbmuxd)
cd "$(dirname "$0")"
[ -f .deps-ok ] || { python3 -m pip install -r requirements.txt && python3 app/setup_tools.py && touch .deps-ok; }
python3 app/server.py
