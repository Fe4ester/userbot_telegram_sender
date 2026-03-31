#!/usr/bin/env zsh
set -euo pipefail

poetry install
poetry run tg-ui --host 127.0.0.1 --port 8787
