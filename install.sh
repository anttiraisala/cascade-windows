#!/usr/bin/env bash
# Install cascade-windows for the current user. No root access is needed.
set -eu

usage() {
    cat <<USAGE
Usage: ./install.sh [options]

Options:
  --backend NAME     x11, gnome or auto (default): auto installs the GNOME Shell extension on GNOME
                     desktops and the X11 version (Nemo menu, shortcut) everywhere else
  --install-deps     install python3-xlib with apt (asks for sudo); only needed for the X11 version
  --no-keybinding    do not register the Super+Shift+C shortcut
  --no-nemo          do not install the desktop right-click menu entries
  --no-submenu       show the right-click entries as a flat list instead of one submenu
  --reset-config     replace the configuration file with a fresh one holding all defaults
                     (the old file is kept as config.json.bak)
  --force            install even on a Wayland session
  -h, --help         show this help
USAGE
}

install_deps=0
keybinding=1
nemo=1
submenu=1
force=0
reset_config=0
backend=auto
while [ $# -gt 0 ]; do
    argument="$1"
    shift
    case "$argument" in
        --backend)
            [ $# -gt 0 ] || { echo "--backend needs a value (x11, gnome or auto)" >&2; exit 2; }
            backend="$1"
            shift
            ;;
        --backend=*) backend="${argument#--backend=}" ;;
        --install-deps) install_deps=1 ;;
        --no-keybinding) keybinding=0 ;;
        --no-nemo) nemo=0 ;;
        --no-submenu) submenu=0 ;;
        --reset-config) reset_config=1 ;;
        --force) force=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $argument" >&2; usage >&2; exit 2 ;;
    esac
done

case "$backend" in
    auto)
        case ":${XDG_CURRENT_DESKTOP:-}:" in
            *:GNOME:*) backend=gnome ;;
            *) backend=x11 ;;
        esac
        ;;
    x11|gnome) ;;
    *) echo "Unknown backend: $backend (use x11, gnome or auto)" >&2; exit 2 ;;
esac

source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
install_dir="$data_dir/cascade-windows"
bin_dir="$HOME/.local/bin"
command_path="$bin_dir/cascade-windows"
nemo_dir="$data_dir/nemo/actions"
extension_uuid="cascade-windows@anttiraisala.github.io"
extension_dir="$data_dir/gnome-shell/extensions/$extension_uuid"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required but was not found." >&2
    exit 1
fi

if [ "$backend" = "x11" ] && [ "${XDG_SESSION_TYPE:-}" = "wayland" ] && [ "$force" -eq 0 ]; then
    echo "This is a Wayland session and the X11 version moves X11 windows only, so it would not work" >&2
    echo "for most applications. On GNOME, run ./install.sh --backend gnome. Otherwise log in with an" >&2
    echo "X11 session (Linux Mint Cinnamon, Ubuntu Unity 7), or run ./install.sh --force to install anyway." >&2
    exit 1
fi

if [ "$backend" = "x11" ] && ! python3 -c "import Xlib" >/dev/null 2>&1; then
    if [ "$install_deps" -eq 1 ]; then
        sudo apt-get install -y python3-xlib
    else
        echo "The Python X11 library is missing. Install it with:" >&2
        echo "    sudo apt install python3-xlib" >&2
        echo "or run ./install.sh --install-deps" >&2
        exit 1
    fi
fi

echo "Installing to $install_dir"
rm -rf "$install_dir/lib"
mkdir -p "$install_dir/lib" "$bin_dir"
cp -r "$source_dir/cascade_windows" "$install_dir/lib/"
find "$install_dir/lib" -name '__pycache__' -type d -prune -exec rm -rf {} +

cat > "$command_path" <<WRAPPER
#!/bin/sh
exec env PYTHONPATH="$install_dir/lib\${PYTHONPATH:+:\$PYTHONPATH}" python3 -m cascade_windows "\$@"
WRAPPER
chmod +x "$command_path"
echo "Installed the command: $command_path"

if [ "$backend" = "gnome" ]; then
    echo "Installing the GNOME Shell extension to $extension_dir"
    rm -rf "$extension_dir"
    mkdir -p "$extension_dir"
    cp -r "$source_dir/gnome-extension/metadata.json" "$source_dir/gnome-extension/extension.js" \
        "$source_dir/gnome-extension/lib" "$source_dir/gnome-extension/schemas" \
        "$source_dir/gnome-extension/icons" "$extension_dir/"
    if command -v glib-compile-schemas >/dev/null 2>&1; then
        glib-compile-schemas "$extension_dir/schemas"
    else
        echo "glib-compile-schemas was not found (package libglib2.0-bin); the extension cannot load its settings." >&2
    fi
    command -v busctl >/dev/null 2>&1 || echo "Warning: busctl (part of systemd) was not found; the command cannot reach the extension." >&2
    "$command_path" --enable-gnome-extension || echo "Could not enable the extension automatically. Enable it in the Extensions app." >&2
fi

if [ "$backend" = "x11" ] && [ "$nemo" -eq 1 ]; then
    mkdir -p "$nemo_dir"
    rm -f "$nemo_dir"/cascade-windows-*.nemo_action
    for template in "$source_dir"/nemo/*.nemo_action; do
        sed "s|@COMMAND@|$command_path|g" "$template" > "$nemo_dir/$(basename "$template")"
    done
    echo "Installed the desktop right-click menu entries (Nemo actions) in $nemo_dir"
    if [ "$submenu" -eq 1 ]; then
        "$command_path" --install-nemo-menu || echo "The entries will be shown as a flat list instead." >&2
    else
        "$command_path" --remove-nemo-menu >/dev/null 2>&1 || true
    fi
    echo "If they do not appear, restart the desktop file manager with: nemo --quit"
fi

if [ "$reset_config" -eq 1 ]; then
    "$command_path" --reset-config
fi
# An untouched configuration file from an older version only freezes outdated defaults.
"$command_path" --migrate-config || true
echo "Settings: built-in defaults unless ${XDG_CONFIG_HOME:-$HOME/.config}/cascade-windows/config.json exists."
echo "          Run 'cascade-windows --edit-config' to create and edit it, 'cascade-windows --show-config' to see what is in effect."

if [ "$backend" = "x11" ] && [ "$keybinding" -eq 1 ]; then
    if "$command_path" --install-keybinding "$command_path --scope monitor" 2>/dev/null; then
        :
    else
        echo "Could not register the keyboard shortcut automatically." >&2
        echo "Add one yourself in the keyboard settings with the command:" >&2
        echo "    $command_path --scope monitor" >&2
    fi
fi

case ":$PATH:" in
    *":$bin_dir:"*) ;;
    *) echo "Note: $bin_dir is not in your PATH yet. Log out and in again, or add it to your PATH." ;;
esac

if [ "$backend" = "gnome" ]; then
    echo "The extension provides the Super+Shift+C shortcut and a panel menu."
    echo "Log out and in again so that GNOME Shell loads the extension (needed on Wayland)."
    echo "After that, try: $command_path --backend gnome --diagnose"
else
    echo "Done. Try: $command_path --diagnose"
fi
