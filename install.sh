#!/usr/bin/env bash
set -e

echo "=== nova-vt installer ==="
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[1/5] Installing system packages..."
yay -S --needed --noconfirm \
    godot obs-studio v4l2loopback-dkms python python-pip git

echo "[2/5] Loading v4l2loopback..."
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="nova-vt-cam" exclusive_caps=1
echo "v4l2loopback" | sudo tee /etc/modules-load.d/v4l2loopback.conf > /dev/null
echo "options v4l2loopback devices=1 video_nr=10 card_label=nova-vt-cam exclusive_caps=1" \
    | sudo tee /etc/modprobe.d/v4l2loopback.conf > /dev/null

echo "[3/5] Setting up Python environment..."
cd "$SCRIPT_DIR"
python -m venv .venv
source .venv/bin/activate
pip install -e . --quiet

echo "[4/5] Downloading face landmarker model..."
curl -L --progress-bar -o face_landmarker.task \
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"

echo "[5/5] Creating config directory..."
mkdir -p ~/.config/nova-vt
if [ ! -f ~/.config/nova-vt/theme.toml ]; then
    cat > ~/.config/nova-vt/theme.toml << 'EOF'
[colors]
background   = "#1e1e2e"
surface      = "#313244"
primary      = "#cba6f7"
secondary    = "#89b4fa"
text         = "#cdd6f4"
text_muted   = "#6c7086"
success      = "#a6e3a1"
warning      = "#f9e2af"
error        = "#f38ba8"
EOF
    echo "Default theme written to ~/.config/nova-vt/theme.toml"
fi

echo ""
echo "=== Done! Run: source .venv/bin/activate && nova-vt-dashboard ==="
