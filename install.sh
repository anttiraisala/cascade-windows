#!/usr/bin/env bash
# Install cascade-windows for the current user. No root access is needed.
set -eu

usage() {
    cat <<USAGE
Usage: ./install.sh [options]

Options:
  --install-deps     install python3-xlib with apt (asks for sudo)
  --no-keybinding    do not register the Super+Shift+C shortcut
  --no-nemo          do not install the desktop right-click menu entries
  --force            install even on a Wayland session
  -h, --help         show this help
USAGE
}

install_deps=0
keybinding=1
nemo=1
force=0
for argument in "$@"; do
    case "$argument" in
        --install-deps) install_deps=1 ;;
        --no-keybinding) keybinding=0 ;;
        --no-nemo) nemo=0 ;;
        --force) force=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $argument" >&2; usage >&2; exit 2 ;;
    esac
done

source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
install_dir="$data_dir/cascade-windows"
bin_dir="$HOME/.local/bin"
command_path="$bin_dir/cascade-windows"
nemo_dir="$data_dir/nemo/actions"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required but was not found." >&2
    exit 1
fi

if [ "${XDG_SESSION_TYPE:-}" = "wayland" ] && [ "$force" -eq 0 ]; then
    echo "This is a Wayland session. This version moves X11 windows only, so it would not work" >&2
    echo "for most applications. Log in with an X11 session (Linux Mint Cinnamon, Ubuntu Unity 7)," >&2
    echo "or run ./install.sh --force to install anyway." >&2
    exit 1
fi

if ! python3 -c "import Xlib" >/dev/null 2>&1; then
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

if [ "$nemo" -eq 1 ]; then
    mkdir -p "$nemo_dir"
    rm -f "$nemo_dir"/cascade-windows-*.nemo_action
    for template in "$source_dir"/nemo/*.nemo_action; do
        sed "s|@COMMAND@|$command_path|g" "$template" > "$nemo_dir/$(basename "$template")"
    done
    echo "Installed the desktop right-click menu entries (Nemo actions) in $nemo_dir"
    echo "If they do not appear, restart the desktop file manager with: nemo --quit"
fi

# An untouched configuration file from an older version only freezes outdated defaults.
"$command_path" --migrate-config || true
echo "Settings: built-in defaults unless ${XDG_CONFIG_HOME:-$HOME/.config}/cascade-windows/config.json exists."
echo "          Run 'cascade-windows --edit-config' to create and edit it, 'cascade-windows --show-config' to see what is in effect."

if [ "$keybinding" -eq 1 ]; then
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

echo "Done. Try: $command_path --diagnose"
