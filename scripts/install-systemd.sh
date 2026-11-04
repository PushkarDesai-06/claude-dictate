#!/usr/bin/env bash
# Links the claude-dictate user units into systemd and enables the daemon.
# Sessions that activate graphical-session.target (GNOME, KDE, uwsm) start it on login.
# Others (plain Hyprland, Sway, river) must start it from the compositor's autostart:
#   systemctl --user import-environment WAYLAND_DISPLAY && systemctl --user start claude-dictated.service
set -euo pipefail

readonly PROJECT_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
readonly BIN_DIR="$HOME/.local/bin"

mkdir -p "$BIN_DIR"
for command in claude-dictate-start claude-dictated claude-dictate-ctl; do
    ln -sf "$PROJECT_DIR/bin/$command" "$BIN_DIR/$command"
done

systemctl --user link \
    "$PROJECT_DIR/systemd/claude-dictate-session.service" \
    "$PROJECT_DIR/systemd/claude-dictated.service"
systemctl --user daemon-reload
systemctl --user enable claude-dictated.service

echo "Installed. Start now with: systemctl --user start claude-dictated.service"
