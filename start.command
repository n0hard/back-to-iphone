#!/bin/bash
# macOS: двойной клик (после chmod +x start.command)
cd "$(dirname "$0")"
[ -f .deps-ok ] || { python3 -m pip install -r requirements.txt && python3 app/setup_tools.py && touch .deps-ok; }
python3 app/server.py
