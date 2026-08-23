#!/usr/bin/env bash
set -euo pipefail

prefix="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
clang="$prefix/llvm/bin/clang"

[[ -x "$clang" ]] || {
    printf 'error: SeaBIOS Clang compiler is missing: %s\n' "$clang" >&2
    exit 1
}

link_step=1
action=""
merge_constants=1
has_c_input=0
has_dependency=0
has_dependency_file=0
output=""
expect_output=0
expect_language=0
language=""
args=()

for arg in "$@"; do
    if ((expect_output)); then
        output="$arg"
        args+=("$arg")
        expect_output=0
        continue
    fi
    if ((expect_language)); then
        language="$arg"
        [[ "$language" == c || "$language" == c-header || "$language" == cpp-output ]] && has_c_input=1
        args+=("$arg")
        expect_language=0
        continue
    fi

    case "$arg" in
        -E)
            action=-E
            link_step=0
            args+=("$arg")
            ;;
        -S)
            # GCC stop stages are priorities, not last-option-wins. SeaBIOS
            # invokes its compile-to-assembly rule with both -S and -c.
            [[ "$action" == -E ]] || action=-S
            link_step=0
            args+=("$arg")
            ;;
        -c)
            [[ -n "$action" ]] || action=-c
            link_step=0
            args+=("$arg")
            ;;
        -o)
            args+=("$arg")
            expect_output=1
            ;;
        -o*)
            output="${arg#-o}"
            args+=("$arg")
            ;;
        -x)
            args+=("$arg")
            expect_language=1
            ;;
        -xc|-xc-header|-xcpp-output)
            has_c_input=1
            args+=("$arg")
            ;;
        -M|-MM)
            # Dependency-only modes imply preprocessing and take priority over
            # -S/-c just like GCC's -E stage.
            action=-E
            link_step=0
            args+=("$arg")
            ;;
        -MD|-MMD)
            has_dependency=1
            args+=("$arg")
            ;;
        -MF)
            has_dependency_file=1
            args+=("$arg")
            ;;
        -MF*)
            has_dependency_file=1
            args+=("$arg")
            ;;
        -mpreferred-stack-boundary=2)
            # GCC encodes the boundary as log2(bytes); SeaBIOS asks for 2^2.
            args+=(-mstack-alignment=4)
            ;;
        -fno-defer-pop|-fno-stack-protector-all|-fstack-check=no)
            # Clang either lacks these spellings or diagnoses them as ignored.
            # The SeaBIOS ABI checks cover the required behavior separately.
            ;;
        -fwhole-program)
            # SeaBIOS probes this option. Clang accepts the spelling while not
            # implementing GCC's whole-program semantics, so fail the probe.
            printf 'error: SeaBIOS whole-program optimization is unsupported by Clang\n' >&2
            exit 1
            ;;
        -fno-merge-constants)
            merge_constants=0
            ;;
        -fmerge-constants)
            merge_constants=1
            ;;
        -*)
            args+=("$arg")
            ;;
        *.c)
            has_c_input=1
            args+=("$arg")
            ;;
        *)
            args+=("$arg")
            ;;
    esac
done

((expect_output == 0)) || {
    printf 'error: -o requires an output path\n' >&2
    exit 1
}
((expect_language == 0)) || {
    printf 'error: -x requires a language\n' >&2
    exit 1
}

driver_args=(--target=i386-none-elf)
if ((link_step)); then
    driver_args+=(-fuse-ld=lld)
fi
if [[ "$action" == -S ]] && ((has_c_input)); then
    # GCC leaves inline assembly uninterpreted when emitting assembly.  This
    # is required by SeaBIOS's generated-offset source, which deliberately
    # emits -> markers for a later text-processing step.
    driver_args+=(-fno-integrated-as)
fi

# GCC's -fno-merge-constants is a correctness requirement for SeaBIOS's
# segmented layout: mergeable .rodata sections must remain distinct until the
# final firmware link. Clang currently accepts the spelling only as an ignored
# optimization option. For C compilation, emit assembly, rename mergeable
# .rodata sections, remove their ELF SHF_MERGE / SHF_STRINGS flags, and then use
# Clang's integrated assembler. This implements the missing GNU compiler ABI
# without adding binutils or another LLVM utility to the firmware toolchain.
if ((merge_constants == 0 && has_c_input == 1)) && [[ "$action" == -c || "$action" == -S ]]; then
    [[ -n "$output" ]] || {
        printf 'error: SeaBIOS -fno-merge-constants compilation requires -o\n' >&2
        exit 1
    }

    tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/whp-seabios-clang.XXXXXX")"
    trap 'rm -rf "$tmpdir"' EXIT
    raw_asm="$tmpdir/raw.s"
    fixed_asm="$tmpdir/fixed.s"

    compile_args=()
    skip_output=0
    for arg in "${args[@]}"; do
        if ((skip_output)); then
            skip_output=0
            continue
        fi
        case "$arg" in
            -c|-S)
                ;;
            -o)
                skip_output=1
                ;;
            -o*)
                ;;
            *)
                compile_args+=("$arg")
                ;;
        esac
    done

    if ((has_dependency && !has_dependency_file)) && [[ "$output" != /dev/null ]]; then
        depfile="${output%.*}.d"
        compile_args+=(-MF "$depfile")
    fi

    "$clang" "${driver_args[@]}" "${compile_args[@]}" -S -o "$raw_asm"

    awk '
    {
        line = $0
        if (line ~ /^[[:space:]]*\.section[[:space:]]+\.rodata[^,]*,"[^"]*M[^"]*",[@%]progbits/) {
            sub(/\.rodata[^,]*/, "&.nomerge", line)
            flag_start = match(line, /"[^"]*M[^"]*"/)
            flag_length = RLENGTH
            flags = substr(line, flag_start + 1, flag_length - 2)
            gsub(/M/, "", flags)
            gsub(/S/, "", flags)
            line = substr(line, 1, flag_start) flags \
                substr(line, flag_start + flag_length - 1)
            sub(/,[0-9]+[[:space:]]*$/, "", line)
        }
        print line
    }
    ' "$raw_asm" > "$fixed_asm"

    if [[ "$action" == -S ]]; then
        cp "$fixed_asm" "$output"
        exit 0
    fi

    "$clang" --target=i386-none-elf -m32 -c -x assembler \
        "$fixed_asm" -o "$output"
    exit $?
fi

exec "$clang" "${driver_args[@]}" "${args[@]}"
