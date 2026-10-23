#!/usr/bin/env bash
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$SRC_DIR/assets" ]; then
    ASSET_DIR="$SRC_DIR/assets"
    ICON_SRC="$SRC_DIR/icon.png"
else
    ASSET_DIR="$SRC_DIR/../src/cupcake/Assets.xcassets"
    ICON_SRC="$ASSET_DIR/AppIcon.appiconset/icon_256x256.png"
fi

DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_DIR/cupcake"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$DATA_DIR/applications"

if ! python3 -c 'import cairo, gi; gi.require_version("Gtk", "3.0")' 2>/dev/null; then
    echo "Missing GTK3 Python bindings. Install them with:"
    echo "  sudo apt install python3-gi gir1.2-gtk-3.0 python3-gi-cairo"
    exit 1
fi

if [ ! -d "$ASSET_DIR" ] || [ ! -f "$ICON_SRC" ]; then
    echo "Error: assets not found in $ASSET_DIR"
    echo "Run this script from an extracted or cloned copy of the repository."
    exit 1
fi

mkdir -p "$APP_DIR/assets" "$BIN_DIR" "$DESKTOP_DIR"
install -m 644 "$SRC_DIR/cupcake.py" "$APP_DIR/cupcake.py"
find "$ASSET_DIR" -name '*.png' -exec install -m 644 {} "$APP_DIR/assets/" \;
install -m 644 "$ICON_SRC" "$APP_DIR/icon.png"

cat > "$BIN_DIR/cupcake" <<EOF
#!/bin/sh
exec python3 "$APP_DIR/cupcake.py" "\$@"
EOF
chmod +x "$BIN_DIR/cupcake"

cat > "$DESKTOP_DIR/cupcake.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Cupcake
Comment=Adorable animated kitty for your desktop
Exec=$BIN_DIR/cupcake
Icon=$APP_DIR/icon.png
Terminal=false
Categories=Utility;
StartupNotify=false
EOF

update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true

echo "Installed Cupcake to $APP_DIR"
echo "Run 'cupcake' or open Cupcake from the application menu."
echo "If 'cupcake' is not found, add ~/.local/bin to your PATH (log out and back in)."
