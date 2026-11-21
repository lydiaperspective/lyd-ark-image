# Display the Lyd Ark banner in interactive login shells.
# This file is sourced by /etc/profile; keep it silent for scripts and non-TTY sessions.
if [[ $- == *i* ]] && [[ -t 1 ]] && [[ -x /usr/libexec/ark/terminal-banner ]]; then
    /usr/libexec/ark/terminal-banner
fi
