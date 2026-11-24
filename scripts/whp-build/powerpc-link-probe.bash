# SPDX-License-Identifier: GPL-2.0-or-later
# Validate the actual compiler-driven link, not just -print-prog-name=ld.
whp_powerpc_verify_driver_link()
{
    local driver="$1" prefix="$2" object="$3" layout="$4" output="$5"
    local entry="$6" trace header
    local args=(-m32 -nostdlib -Xlinker -T -Xlinker "$layout"
                -o "$output" "$object")

    if ! trace="$("$driver" -### "${args[@]}" 2>&1)"; then
        printf 'error: PowerPC Clang link job could not be constructed: %s\n' "$trace" >&2
        return 1
    fi
    if ! grep -Fq "\"$prefix/libexec/powerpc-clang-gnu/ld\"" <<< "$trace" &&
       ! grep -Fq "\"$prefix/llvm/bin/ld.lld\"" <<< "$trace"; then
        printf 'error: PowerPC Clang did not select the private ELF LLD linker:\n%s\n' "$trace" >&2
        return 1
    fi
    "$driver" "${args[@]}" || return 1
    header="$(LC_ALL=C "$prefix/llvm/bin/llvm-readelf" -hW "$output")" || return 1
    if ! grep -Eq 'Class:[[:space:]]+ELF32' <<< "$header" ||
       ! grep -Eq "Data:[[:space:]]+2's complement, big endian" <<< "$header" ||
       ! grep -Eq 'Type:[[:space:]]+EXEC' <<< "$header" ||
       ! grep -Eq 'Machine:[[:space:]]+PowerPC[[:space:]]*$' <<< "$header" ||
       ! grep -Eq "Entry point address:[[:space:]]+$entry[[:space:]]*$" <<< "$header"; then
        printf 'error: PowerPC compiler-driven link produced an unexpected ELF ABI or entry point\n%s\n' "$header" >&2
        return 1
    fi
}
