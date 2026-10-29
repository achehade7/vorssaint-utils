#!/bin/zsh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
# Self-signed identities need search-list membership for codesign chain lookup.
# Expose this unlocked build keychain only for the signing command.
set -euo pipefail
KC="$HOME/Library/Keychains/vorssaint-signing.keychain-db"
[[ -f "$KC" ]] || { echo "Local signing keychain is missing." >&2; exit 1; }
zmodload zsh/system
touch "$KC.signing-lock"
zsystem flock -t 60 -f signing_lock "$KC.signing-lock"
security unlock-keychain -p vorssaint-signing "$KC"
local_added=0
read_search_list() {
    security list-keychains -d user | sed -E 's/^[[:space:]]*"//; s/"[[:space:]]*$//'
}
cleanup() {
    if (( local_added )); then
        local item
        local -a retained=()
        while IFS= read -r item; do
            [[ "$item" == "$KC" ]] || retained+=("$item")
        done < <(read_search_list)
        security list-keychains -d user -s "${retained[@]}"
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
keychains=("${(@f)$(read_search_list)}")
if (( ! ${keychains[(Ie)$KC]} )); then
    local_added=1
    security list-keychains -d user -s "${keychains[@]}" "$KC"
fi
codesign --keychain "$KC" "$@"
