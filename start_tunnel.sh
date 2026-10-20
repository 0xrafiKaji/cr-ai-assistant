#!/usr/bin/env bash
# Mobile Access & Public Hosting Tunnel for CR's AI Assistant Control Center

LOCAL_IP=$(ip -4 addr show wlan0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n1)
[ -z "$LOCAL_IP" ] && LOCAL_IP=$(ip -4 addr show eth0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n1)
[ -z "$LOCAL_IP" ] && LOCAL_IP=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $7}')
[ -z "$LOCAL_IP" ] && LOCAL_IP="localhost"
MY_PUBLIC_IP=$(curl -s https://loca.lt/mytunnelpassword 2>/dev/null || curl -s https://api.ipify.org 2>/dev/null)

echo "=================================================================="
echo "📱 CR'S AI ASSISTANT - MOBILE & PUBLIC ACCESS HOSTING"
echo "=================================================================="
echo ""
echo "📶 1. SAME WI-FI ACCESS (Fastest on Local Wi-Fi):"
echo "👉 Open on Phone:   http://${LOCAL_IP}:8000"
echo "   ⚠️ Note: If Wi-Fi doesn't load, firewall is blocking port 8000."
echo "   Fix once by running:  sudo ufw allow 8000/tcp"
echo ""
echo "🌐 2. WORLDWIDE TUNNEL ACCESS (Phone / Mobile Data / Any Wi-Fi):"
echo "👉 Use the 'https://...trycloudflare.com' link generated below!"
echo ""
echo "🔒 DASHBOARD PASSWORD: (Configured in your .env file)"
echo "=================================================================="

if command -v cloudflared >/dev/null 2>&1; then
    echo "⚡ Launching Cloudflare Tunnel (Free HTTPS, No password screen needed)..."
    echo "   Wait 5 seconds for the 'https://...trycloudflare.com' link to appear below:"
    echo ""
    cloudflared tunnel --url http://localhost:8000
else
    echo "⚡ Launching Localtunnel..."
    echo "   (If Localtunnel asks for 'Tunnel Password' on phone, enter: ${MY_PUBLIC_IP})"
    echo ""
    npx -y localtunnel --port 8000
fi
