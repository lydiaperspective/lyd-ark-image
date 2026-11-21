# Display the Lyd Ark banner in interactive Fish sessions.
if status is-interactive; and test -t 1; and test -x /usr/libexec/ark/terminal-banner
    /usr/libexec/ark/terminal-banner
end
