#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

whp_openbios_file_signature()
{
    cksum "$1" | awk '{print $1 ":" $2}'
}

whp_openbios_source_signature()
{
    local source_dir="$1"
    local file

    {
        git -C "$source_dir" rev-parse HEAD
        git -C "$source_dir" diff --binary --no-ext-diff HEAD --
        git -C "$source_dir" submodule status --recursive 2>/dev/null || true
        while IFS= read -r -d '' file; do
            printf 'UNTRACKED\0%s\0' "$file"
            cksum "$source_dir/$file"
        done < <(git -C "$source_dir" ls-files --others --exclude-standard -z)
    } | cksum | awk '{print $1 ":" $2}'
}

whp_openbios_cache_record()
{
    local output="$1"
    local input_signature="$2"

    printf 'INPUT=%s\n' "$input_signature"
    printf 'OUTPUT=%s\n' "$(whp_openbios_file_signature "$output")"
}

whp_openbios_cache_is_fresh()
{
    local state_file="$1"
    local output="$2"
    local expected_signature="$3"
    local force_rebuild="$4"
    local expected_record

    [[ "$force_rebuild" == 0 ]] || return 1
    [[ -s "$output" ]] || return 1
    [[ -f "$state_file" ]] || return 1
    expected_record="$(whp_openbios_cache_record "$output" "$expected_signature")"
    [[ "$(cat "$state_file" 2>/dev/null || true)" == "$expected_record" ]]
}

whp_openbios_cache_write()
{
    local state_file="$1"
    local output="$2"
    local signature="$3"
    local state_dir

    state_dir="$(dirname -- "$state_file")"
    mkdir -p "$state_dir"
    whp_openbios_cache_record "$output" "$signature" > "$state_file.new"
    mv -f "$state_file.new" "$state_file"
}
