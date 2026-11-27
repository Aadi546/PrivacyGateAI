#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec .venv/bin/python -u -m backend.practical_server
