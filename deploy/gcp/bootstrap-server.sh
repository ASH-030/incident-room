#!/usr/bin/env bash
set -euo pipefail
umask 027
install -d -m 0755 /var/lib/incident-room
exec > >(tee -a /var/log/incident-room-bootstrap.log) 2>&1
trap 'echo failed > /var/lib/incident-room/bootstrap.status' ERR
echo installing > /var/lib/incident-room/bootstrap.status
export DEBIAN_FRONTEND=noninteractive
apt-get -o Acquire::Retries=3 -o Acquire::https::Timeout=30 update
apt-get install -y --no-install-recommends ca-certificates curl git python3 unzip
install -m 0755 -d /etc/apt/keyrings
curl --fail --silent --show-error --location --retry 3 --connect-timeout 15 --max-time 90 https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod 0644 /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<'EOF'
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: bookworm
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get -o Acquire::Retries=3 -o Acquire::https::Timeout=30 update
apt-get -o Acquire::Retries=3 -o Acquire::https::Timeout=30 install -y --no-install-recommends docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
if ! getent passwd 10001 >/dev/null; then
  useradd --uid 10001 --create-home --shell /usr/sbin/nologin incident-room
fi
install -d -m 0755 /opt/incident-room
install -d -m 0750 -o 10001 -g 10001 /srv/incident-room /srv/incident-room/runtime /srv/incident-room/retail-warehouse /srv/incident-room/switch
docker version --format '{{.Server.Version}}' > /var/lib/incident-room/docker.version
docker compose version --short > /var/lib/incident-room/compose.version
echo ready > /var/lib/incident-room/bootstrap.status
echo 'Incident Room server bootstrap ready.'
