#!/usr/bin/env bash
set -euo pipefail
umask 077
install -d -m 0700 /srv/incident-room/backups
exec 9>/srv/incident-room/backups/.lock
flock -n 9 || exit 0
backup_stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_root=/srv/incident-room/backups
docker exec incident-room-db-1 pg_dump -U incident -d incident -Fc > "$backup_root/$backup_stamp-app.dump"
docker exec incident-switch-postgres-1 pg_dumpall -U postgres | gzip > "$backup_root/$backup_stamp-switch.sql.gz"
active_repo=$(docker inspect --format='{{range .Mounts}}{{if eq .Destination "/workspace/retail-warehouse"}}{{.Source}}{{end}}{{end}}' incident-room-api-1)
case "$active_repo" in
    /srv/incident-room/retail-warehouse|/srv/incident-room/presentation-warehouse) ;;
    *) echo 'Unexpected SQL repository mount; backup stopped.' >&2; exit 1 ;;
esac
runuser -u incident-room -- git -C "$active_repo" bundle create - --all > "$backup_root/$backup_stamp-warehouse.bundle"
cp /opt/incident-room/config/project.container.json "$backup_root/$backup_stamp-project.json"
docker exec -i incident-room-db-1 pg_restore --list < "$backup_root/$backup_stamp-app.dump" >/dev/null
gzip -t "$backup_root/$backup_stamp-switch.sql.gz"
echo "$backup_stamp Backup archive structure verified."
python3 /opt/incident-room/deploy/gcp/upload-backups.py "$backup_stamp"
