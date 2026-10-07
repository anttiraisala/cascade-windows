#!/usr/bin/env bash
# Remove cascade-windows from the current user's account.
set -eu

purge=0
for argument in "$@"; do
    case "$argument" in
        --purge) purge=1 ;;
        -h|--help)
            echo "Usage: ./uninstall.sh [--purge]"
            echo "  --purge   also delete the configuration file and the undo state"
            exit 0
            ;;
        *) echo "Unknown option: $argument" >&2; exit 2 ;;
    esac
done

data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
install_dir="$data_dir/cascade-windows"
command_path="$HOME/.local/bin/cascade-windows"

if [ -x "$command_path" ]; then
    "$command_path" --remove-keybinding >/dev/null 2>&1 || true
fi
rm -f "$command_path"
rm -rf "$install_dir"
rm -f "$data_dir"/nemo/actions/cascade-windows-*.nemo_action

if [ "$purge" -eq 1 ]; then
    rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/cascade-windows"
    rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/cascade-windows"
    echo "Removed cascade-windows, its configuration and its state."
else
    echo "Removed cascade-windows. The configuration file was kept (use --purge to delete it)."
fi
