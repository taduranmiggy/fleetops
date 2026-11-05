#!/bin/sh
set -eu

# Keep every deployment path on the validated, fail-closed Python entrypoint.
exec python run_server.py
