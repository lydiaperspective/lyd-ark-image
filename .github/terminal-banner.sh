#!/usr/bin/env bash
# Lyd Ark interactive terminal welcome banner.
# Prints only to an interactive terminal and only advertises installed commands.
set -euo pipefail

[[ -t 1 ]] || exit 0

if [[ -n "${NO_COLOR:-}" || "${TERM:-}" == "dumb" ]]; then
    accent=""
    highlight=""
    muted=""
    reset=""
else
    # Wicca palette: violet, sage, and soft lavender.
    accent=$'\033[38;5;141m'
    highlight=$'\033[38;5;151m'
    muted=$'\033[38;5;246m'
    reset=$'\033[0m'
fi

printf '%b\n' "${accent}       ☽  L Y D   A R K  ☾${reset}"
printf '%b\n' "${muted}       Immutable Linux · Wicca edition${reset}"
printf '\n'
printf '%b\n' "${highlight}Quick commands${reset}"

if command -v ark >/dev/null 2>&1; then
    printf '  %-18s %s\n' 'ark' 'Lyd Ark System Manager — ark --help'
fi
if command -v lydsys >/dev/null 2>&1; then
    printf '  %-18s %s\n' 'lydsys' 'Compatibility alias for ark — lydsys --help'
fi
if command -v lydstore >/dev/null 2>&1; then
    printf '  %-18s %s\n' 'lydstore' 'Lyd Ark Storage Manager — lydstore --help'
fi
if command -v alga >/dev/null 2>&1; then
    printf '  %-18s %s\n' 'alga' 'Graphical installer and system updater'
fi

printf '\n'
printf '%b\n' "${muted}Run a command with --help for usage details where supported.${reset}"
