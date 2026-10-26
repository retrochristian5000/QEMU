#!/usr/bin/env bash

# Normalize LLVM/Clang macOS target spellings for ABI comparisons only.
# Preserve the original reported triple when passing LLVM_HOST_TRIPLE or
# writing compiler identity manifests: Darwin and macOS version numbers are
# not interchangeable as literal toolchain configuration strings.
macos_target_abi_key()
{
    local target="$1"
    local target_arch arch os_name os_kind version major minor patch

    target_arch="${target%%-*}"
    [[ "$target" == "$target_arch-apple-"* ]] || return 1
    arch="$target_arch"
    case "$arch" in
        arm64|aarch64) arch=aarch64 ;;
        x86_64|amd64) arch=x86_64 ;;
        *) return 1 ;;
    esac
    os_name="${target#*-apple-}"
    # Reject iOS/simulator/Mac Catalyst and malformed extra target fields.
    [[ "$os_name" =~ ^(darwin|macosx|macos)([0-9]+(\.[0-9]+){0,2})?$ ]] || return 1
    os_kind="${BASH_REMATCH[1]}"
    version="${BASH_REMATCH[2]:-}"
    if [[ -z "$version" ]]; then
        printf '%s-apple-macosx\n' "$arch"
        return 0
    fi

    IFS=. read -r major minor patch <<< "$version"
    major=$((10#$major))
    minor=$((10#${minor:-0}))
    patch=$((10#${patch:-0}))
    if [[ "$os_kind" == darwin ]]; then
        if (( major < 4 )); then
            return 1
        elif (( major <= 19 )); then
            # Darwin 19.6 is macOS 10.15.6, not macOS 19.6.
            patch=$minor
            minor=$((major - 4))
            major=10
        elif (( major <= 24 )); then
            major=$((major - 9))
        elif (( major <= 26 )); then
            major=$((major + 1))
        fi
        # The WHP Darwin 27+ spelling uses the same major as macOS.
    fi
    printf '%s-apple-macosx%d.%d.%d\n' "$arch" "$major" "$minor" "$patch"
}
