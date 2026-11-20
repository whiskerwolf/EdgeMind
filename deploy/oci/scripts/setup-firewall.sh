#!/usr/bin/env bash
# EdgeMind Host Firewall Configuration Script
# Hardens the OCI VM host firewall to expose ONLY SSH (22), HTTP (80), and HTTPS (443).
# Explicitly blocks all external access to internal ports (5432, 6379, 6380, 8000, 11434).

set -euo pipefail

echo "Configuring host firewall for EdgeMind production environment..."

if command -v ufw >/dev/null 2>&1; then
    echo "Configuring Ubuntu UFW firewall..."
    ufw --force reset
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp comment 'Restricted SSH administration'
    ufw allow 80/tcp comment 'Caddy HTTP ACME challenge and redirect'
    ufw allow 443/tcp comment 'Caddy HTTPS EdgeMind API'
    ufw --force enable
    ufw status verbose
elif command -v firewall-cmd >/dev/null 2>&1; then
    echo "Configuring Oracle Linux firewalld..."
    firewall-cmd --permanent --remove-service=cockpit || true
    firewall-cmd --permanent --add-service=ssh
    firewall-cmd --permanent --add-service=http
    firewall-cmd --permanent --add-service=https
    firewall-cmd --reload
    firewall-cmd --list-all
else
    echo "Configuring standard Linux iptables..."
    # Flush existing rules
    iptables -F
    # Default policies: DROP incoming and forwarding, ACCEPT outgoing
    iptables -P INPUT DROP
    iptables -P FORWARD DROP
    iptables -P OUTPUT ACCEPT
    # Allow established connections and loopback
    iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
    iptables -A INPUT -i lo -j ACCEPT
    # Allow SSH, HTTP, and HTTPS
    iptables -A INPUT -p tcp --dport 22 -j ACCEPT
    iptables -A INPUT -p tcp --dport 80 -j ACCEPT
    iptables -A INPUT -p tcp --dport 443 -j ACCEPT
    echo "iptables rules applied successfully."
fi

echo "Host firewall configuration complete. Internal database and Ollama ports remain strictly private."
