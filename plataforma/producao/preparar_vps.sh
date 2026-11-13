#!/usr/bin/env bash
# Prepara um Ubuntu 24.04 novo para o AgroEdge. Roda NO SERVIDOR, como root, uma vez
# (pode repetir: cada passo confere antes de mudar). Foi o que se fez na VPS em 13/11/2026.
#
#   ssh agroedge-vps 'bash -s' < producao/preparar_vps.sh
#
# ANTES: cadastre a sua chave SSH no painel da VPS e confira que entra com ela. Este script
# desliga o login por senha.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

if [ -z "$(cat /root/.ssh/authorized_keys 2>/dev/null)" ]; then
	echo "nenhuma chave SSH em /root/.ssh/authorized_keys: cadastre antes (senão você se tranca fora)"
	exit 1
fi

echo "→ sistema atualizado e atualizações de segurança automáticas"
apt-get update -qq
apt-get -y -qq -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold upgrade
apt-get -y -qq install unattended-upgrades fail2ban ufw ca-certificates curl rsync python3
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
systemctl enable --now unattended-upgrades >/dev/null

echo "→ firewall: 22 (limitado), 80, 443 e 8883"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw limit 22/tcp comment "SSH" >/dev/null
ufw allow 80/tcp comment "HTTP (Caddy)" >/dev/null
ufw allow 443/tcp comment "HTTPS (Caddy)" >/dev/null
ufw allow 443/udp comment "HTTP/3 (Caddy)" >/dev/null
ufw allow 8883/tcp comment "MQTT TLS" >/dev/null
ufw --force enable >/dev/null

echo "→ fail2ban no SSH"
cat >/etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5
backend = systemd

[sshd]
enabled = true
EOF
systemctl enable fail2ban >/dev/null
systemctl restart fail2ban

echo "→ SSH só por chave"
cat >/etc/ssh/sshd_config.d/00-agroedge.conf <<'EOF'
# AgroEdge: acesso só por chave (o primeiro valor lido vale; este arquivo vem antes do cloud-init)
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
MaxAuthTries 3
X11Forwarding no
EOF
sshd -t
systemctl reload ssh

echo "→ swap de 2 GB"
if ! swapon --show | grep -q /swapfile; then
	fallocate -l 2G /swapfile
	chmod 600 /swapfile
	mkswap /swapfile >/dev/null
	swapon /swapfile
fi
grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >>/etc/fstab
echo 'vm.swappiness=10' >/etc/sysctl.d/99-agroedge.conf
sysctl -q -p /etc/sysctl.d/99-agroedge.conf

echo "→ Docker (repositório oficial) com log limitado"
if ! command -v docker >/dev/null; then
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
	chmod a+r /etc/apt/keyrings/docker.asc
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
		>/etc/apt/sources.list.d/docker.list
	apt-get update -qq
	apt-get -y -qq install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
cat >/etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
systemctl enable docker >/dev/null
systemctl restart docker

echo "pronto. Se existir /var/run/reboot-required, reinicie: systemctl reboot"
