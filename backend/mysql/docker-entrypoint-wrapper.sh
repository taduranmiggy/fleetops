#!/bin/sh
set -e
# Render persistent disks include lost+found. Official MySQL images treat a
# non-empty datadir as already initialized unless we keep data in a subdirectory.
mkdir -p /var/lib/mysql/data
exec docker-entrypoint.sh "$@"
