# Optional WHP mold host-linker preparation stage.
# SPDX-License-Identifier: GPL-2.0-or-later

# A host's OS name does not determine which linker its compiler can use.
# The real C/C++ link-and-run probes below are authoritative.
whp_linker_flags_compatible()
{
    local selected="$1" variable value token
    local -a tokens=()
    for variable in CC CXX OBJC CFLAGS CXXFLAGS OBJCFLAGS CPPFLAGS LDFLAGS; do
        value="${!variable:-}"
        tokens=()
        read -r -a tokens <<< "$value"
        for token in ${tokens[@]+"${tokens[@]}"}; do
            case "$token" in
                -fuse-ld=*)
                    if [[ "${token#-fuse-ld=}" != "$selected" &&
                          !( "$selected" == system && "${token#-fuse-ld=}" == ld ) ]]; then
                        return 1
                    fi
                    ;;
                --ld-path=*|--ld-path) return 1 ;;
            esac
        done
    done
}

# Exercise the actual C and C++ drivers, not a linker version string.
whp_linker_driver_probe()
{
    local selected="$1" path_prefix="${2:-}" temp_dir output source language
    local compiler_var status=0
    local -a command=() flags=()

    temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/whp-host-linker.XXXXXX")" || return 1
    read -r -a flags <<< "${LDFLAGS:-}"
    for compiler_var in CC CXX; do
        command=()
        if [[ "$compiler_var" == CC ]]; then
            whp_mold_compiler_command "${CC:-cc}" || { status=1; break; }
            command=("${WHP_MOLD_CC_CMD[@]}")
            language=c
            printf 'int main(void) { return 0; }\n' > "$temp_dir/probe.c"
            source="$temp_dir/probe.c"
        else
            whp_mold_compiler_command "${CXX:-c++}" || { status=1; break; }
            command=("${WHP_MOLD_CC_CMD[@]}")
            language=c++
            printf 'int main() { return 0; }\n' > "$temp_dir/probe.cpp"
            source="$temp_dir/probe.cpp"
        fi
        output="$temp_dir/$compiler_var"
        if ! PATH="${path_prefix:+$path_prefix:}$PATH" "${command[@]}" \
            -x "$language" "$source" -fuse-ld="$selected" \
            "${flags[@]}" -o "$output" || ! "$output"; then
            status=1
            break
        fi
    done
    rm -rf "$temp_dir"
    return "$status"
}

whp_mold_default_tools_dir()
{
    local host_tag

    host_tag="$(printf '%s-%s' "$HOST_ARCH" "$HOST_OS" |
        LC_ALL=C tr '[:upper:]' '[:lower:]' | LC_ALL=C tr -c '[:alnum:]_.-' '-')" || return 1
    [[ -n "$host_tag" ]] || return 1
    printf '%s/whp-mold-%s\n' "$(dirname "$BUILD_DIR")" "$host_tag"
}

whp_mold_prepare_submodule()
{
    local submodule_path="$1"

    if [[ -d "$SOURCE_DIR/$submodule_path" &&
          -f "$SOURCE_DIR/$submodule_path/CMakeLists.txt" ]]; then
        return 0
    fi
    if [[ ! -e "$SOURCE_DIR/.git" ]]; then
        printf 'error: mold source is unavailable: %s\n' \
            "$SOURCE_DIR/$submodule_path" >&2
        return 1
    fi
    if ! command -v git >/dev/null 2>&1; then
        printf 'error: git is required to initialize the WHP mold submodule\n' >&2
        return 1
    fi

    git -C "$SOURCE_DIR" submodule sync -- "$submodule_path" &&
        git -C "$SOURCE_DIR" submodule update --init --depth 1 -- "$submodule_path"
}

whp_mold_source_signature()
{
    local source_dir="$1"
    local revision

    revision="$(git -C "$source_dir" rev-parse HEAD 2>/dev/null || true)"
    if [[ -n "$revision" ]]; then
        printf 'git:%s\n' "$revision"
        return 0
    fi
    if command -v cksum >/dev/null 2>&1 && [[ -f "$source_dir/CMakeLists.txt" ]]; then
        printf 'cmake:%s\n' "$(cksum "$source_dir/CMakeLists.txt" | awk '{print $1 ":" $2}')"
        return 0
    fi
    printf 'source:%s\n' "$source_dir"
}

whp_mold_bootstrap()
{
    local source_dir="$1"
    local tools_dir="$2"
    local build_dir="$tools_dir/build"
    local install_dir="$tools_dir/install"
    local linker="$install_dir/bin/mold"
    local signature_file="$tools_dir/.whp-mold-signature"
    local signature_candidate="$signature_file.new.$$"
    local cmake_cmd="${CMAKE:-cmake}"
    local mold_cc="${MOLD_CC:-${CC_FOR_BUILD:-cc}}"
    local mold_cxx="${MOLD_CXX:-${CXX_FOR_BUILD:-c++}}"
    local signature

    if ! command -v "$cmake_cmd" >/dev/null 2>&1; then
        printf 'error: CMake is required to bootstrap the WHP mold linker\n' >&2
        return 1
    fi
    case "$mold_cc:$mold_cxx" in
        *' '*|*';'*|*'|'*|*'&'*|*'<'*|*'>')
            printf '%s\n' \
                'error: mold bootstrap compiler commands must be single executables.' \
                "MOLD_CC=$mold_cc" \
                "MOLD_CXX=$mold_cxx" >&2
            return 1
            ;;
    esac
    if ! command -v "$mold_cc" >/dev/null 2>&1 ||
       ! command -v "$mold_cxx" >/dev/null 2>&1; then
        printf '%s\n' \
            'error: mold bootstrap compiler is unavailable.' \
            "MOLD_CC=$mold_cc" \
            "MOLD_CXX=$mold_cxx" >&2
        return 1
    fi

    signature="$(whp_mold_source_signature "$source_dir")|cc=$mold_cc|cxx=$mold_cxx"
    if [[ -x "$linker" && -f "$signature_file" &&
          "$(cat "$signature_file")" == "$signature" ]]; then
        MOLD_LINKER="$linker"
        export MOLD_LINKER
        return 0
    fi

    mkdir -p "$build_dir" "$install_dir/bin"
    "$cmake_cmd" -S "$source_dir" -B "$build_dir" \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER="$mold_cc" \
        -DCMAKE_CXX_COMPILER="$mold_cxx" \
        -DCMAKE_INSTALL_PREFIX="$install_dir"
    "$cmake_cmd" --build "$build_dir" --target install --parallel "$JOBS"

    if [[ ! -x "$linker" ]]; then
        printf 'error: mold bootstrap did not produce %s\n' "$linker" >&2
        return 1
    fi

    # Both Clang and modern GCC understand -fuse-ld=mold by searching for
    # ld.mold.  Keep that shim inside the WHP-owned install prefix.
    ln -sf mold "$install_dir/bin/ld.mold"
    printf '%s\n' "$signature" > "$signature_candidate"
    mv -f "$signature_candidate" "$signature_file"

    MOLD_LINKER="$linker"
    export MOLD_LINKER
}

whp_mold_compiler_command()
{
    local command_string="$1"

    case "$command_string" in
        ''|*';'*|*'|'*|*'&'*|*'<'*|*'>') return 1 ;;
    esac
    WHP_MOLD_CC_CMD=()
    read -r -a WHP_MOLD_CC_CMD <<< "$command_string"
    [[ "${#WHP_MOLD_CC_CMD[@]}" -gt 0 ]] || return 1
    command -v "${WHP_MOLD_CC_CMD[0]}" >/dev/null 2>&1
}

whp_mold_archiver_command()
{
    local command_string="${AR:-}"

    if [[ -z "$command_string" ]]; then
        if command -v llvm-ar >/dev/null 2>&1; then
            command_string=llvm-ar
        else
            command_string=ar
        fi
    fi
    case "$command_string" in
        *';'*|*'|'*|*'&'*|*'<'*|*'>') return 1 ;;
    esac
    WHP_MOLD_AR_CMD=()
    read -r -a WHP_MOLD_AR_CMD <<< "$command_string"
    [[ "${#WHP_MOLD_AR_CMD[@]}" -gt 0 ]] || return 1
    command -v "${WHP_MOLD_AR_CMD[0]}" >/dev/null 2>&1
}

whp_mold_link_probe()
{
    local linker="$1"
    local probe_dir
    local source
    local output
    local linker_dir
    local status=0
    local ld_flags=()

    whp_mold_compiler_command "${CC:-cc}" || {
        printf 'error: cannot execute QEMU host compiler for mold probe: %s\n' \
            "${CC:-cc}" >&2
        return 1
    }

    linker_dir="$(dirname "$linker")"
    probe_dir="$(mktemp -d "${TMPDIR:-/tmp}/whp-mold-probe.XXXXXX")" || return 1
    source="$probe_dir/probe.c"
    output="$probe_dir/probe"

    if [[ -n "${LDFLAGS:-}" ]]; then
        read -r -a ld_flags <<< "$LDFLAGS"
    fi

    if [[ "${QEMU_HOST_LTO:-auto}" == 1 ]]; then
        local main_source="$probe_dir/main.c"
        local lib_source="$probe_dir/lib.c"
        local main_object="$probe_dir/main.o"
        local lib_object="$probe_dir/lib.o"
        local archive="$probe_dir/libprobe.a"
        local lto_flag=-flto
        [[ "${QEMU_HOST_LTO_MODE:-auto}" != thin ]] || lto_flag=-flto=thin

        if ! whp_mold_archiver_command; then
            printf 'error: cannot execute archiver for mold LTO probe: %s\n' \
                "${AR:-auto}" >&2
            rm -rf "$probe_dir"
            return 1
        fi

        cat > "$main_source" <<'EOF_MAIN'
extern int whp_mold_lto_value(void);
int main(void)
{
    return whp_mold_lto_value() == 42 ? 0 : 1;
}
EOF_MAIN
        cat > "$lib_source" <<'EOF_LIB'
int whp_mold_lto_value(void)
{
    return 42;
}
EOF_LIB

        # QEMU links many static libraries.  Compile the probe as separate IR
        # objects and put one in an archive so we validate LLVM/GCC plugin
        # activation, archive indexing/extraction, and mold's final LTO link.
        if ! PATH="$linker_dir:$PATH" "${WHP_MOLD_CC_CMD[@]}" \
            "$lto_flag" -c "$main_source" -o "$main_object"; then
            status=1
        elif ! PATH="$linker_dir:$PATH" "${WHP_MOLD_CC_CMD[@]}" \
            "$lto_flag" -c "$lib_source" -o "$lib_object"; then
            status=1
        elif ! "${WHP_MOLD_AR_CMD[@]}" rcs "$archive" "$lib_object"; then
            status=1
        elif ! PATH="$linker_dir:$PATH" "${WHP_MOLD_CC_CMD[@]}" \
            "$lto_flag" -fuse-ld=mold "$main_object" "$archive" -o "$output" \
            "${ld_flags[@]}"; then
            status=1
        elif ! "$output"; then
            status=1
        fi
    else
        printf 'int main(void) { return 0; }\n' > "$source"
        if ! PATH="$linker_dir:$PATH" "${WHP_MOLD_CC_CMD[@]}" \
            "$source" -o "$output" -fuse-ld=mold "${ld_flags[@]}"; then
            status=1
        elif ! "$output"; then
            status=1
        fi
    fi

    rm -rf "$probe_dir"
    return "$status"
}

whp_prepare_mold()
{
    local mode="${BOOTSTRAP_MOLD:-auto}"
    local selected="${QEMU_HOST_LINKER:-auto}"
    local submodule_path="${MOLD_SUBMODULE_PATH:-toolchains/fast-linker}"
    local source_dir="${MOLD_SOURCE_DIR:-$SOURCE_DIR/$submodule_path}"
    local tools_dir="${MOLD_TOOLS_DIR:-}"
    local linker

    case "$selected" in
        auto|system|lld|mold) ;;
        *) printf 'error: QEMU_HOST_LINKER must be auto, system, lld, or mold\n' >&2; return 1 ;;
    esac
    case "$mode" in
        auto|0|1) ;;
        *) printf 'error: BOOTSTRAP_MOLD must be auto, 0, or 1\n' >&2; return 1 ;;
    esac
    if [[ "$selected" == mold ]]; then
        if [[ "$mode" == 0 ]]; then
            printf 'error: QEMU_HOST_LINKER=mold conflicts with BOOTSTRAP_MOLD=0\n' >&2
            return 1
        fi
        mode=1
    elif [[ "$selected" != auto && "$mode" == 1 ]]; then
        printf 'error: QEMU_HOST_LINKER=%s conflicts with BOOTSTRAP_MOLD=1\n' "$selected" >&2
        return 1
    fi

    # The ARM64e authenticated-fixup and macOS ASan runtime contracts are
    # more specific than the host OS and need their own validation.  Do not
    # bypass those contracts with a trivial C/C++ linker smoke test.
    if [[ "${HOST_OS:-}" == Darwin ]]; then
        case "${QEMU_ASAN:-n}:$selected" in
            1:lld|y:lld|1:mold|y:mold)
                printf 'error: macOS ASan requires the validated Apple linker path\n' >&2
                return 1
                ;;
            1:auto|y:auto)
                if [[ "$mode" == 1 ]]; then
                    printf 'error: forced mold requires a validated macOS ASan runtime\n' >&2
                    return 1
                fi
                BOOTSTRAP_MOLD=0
                MOLD_LINKER=
                export BOOTSTRAP_MOLD MOLD_LINKER
                return 0
                ;;
        esac
        if [[ "${WHP_MACOS_ARCH:-auto}" == arm64e ]]; then
            if [[ "$selected" == lld &&
                  ( "${WHP_ARM64E_USE_LLD:-0}" != 1 ||
                    "${NATIVE_LLVM_LDFLAG:-}" != -fuse-ld=lld ) ]]; then
                printf 'error: ARM64e LLD requires the authenticated-fixup linker selection\n' >&2
                return 1
            fi
            if [[ "$selected" == mold || ( "$selected" == auto && "$mode" == 1 ) ]]; then
                printf 'error: ARM64e mold needs authenticated-fixup validation before use\n' >&2
                return 1
            fi
            if [[ "$selected" == auto ]]; then
                # Keep the already-validated native linker for this ABI.
                BOOTSTRAP_MOLD=0
                MOLD_LINKER=
                export BOOTSTRAP_MOLD MOLD_LINKER
                return 0
            fi
        fi
    fi

    if [[ "$selected" == system || "$selected" == lld ]]; then
        if ! whp_linker_flags_compatible "$selected"; then
            printf 'error: QEMU_HOST_LINKER=%s conflicts with an inherited linker override\n' "$selected" >&2
            return 1
        fi
        if [[ "$selected" == lld ]]; then
            if ! whp_linker_driver_probe lld; then
                printf 'error: LLD failed the host C and C++ compiler probes\n' >&2
                return 1
            fi
            case " ${LDFLAGS:-} " in
                *' -fuse-ld=lld '*) ;;
                *) whp_append_flag LDFLAGS '-fuse-ld=lld' ;;
            esac
        fi
        BOOTSTRAP_MOLD=0
        MOLD_LINKER=
        export BOOTSTRAP_MOLD MOLD_LINKER
        printf 'QEMU host linker:         %s\n' "$selected"
        return 0
    fi

    if [[ "$mode" == 0 ]]; then
        MOLD_LINKER=
        export BOOTSTRAP_MOLD MOLD_LINKER
        return 0
    fi

    # Auto must respect an LLD or custom linker previously chosen by the user.
    if ! whp_linker_flags_compatible mold; then
        if [[ "$mode" == 1 ]]; then
            printf 'error: mold conflicts with the existing compiler/linker flags\n' >&2
            return 1
        fi
        BOOTSTRAP_MOLD=0
        MOLD_LINKER=
        export BOOTSTRAP_MOLD MOLD_LINKER
        return 0
    fi

    if [[ -z "$tools_dir" ]]; then
        tools_dir="$(whp_mold_default_tools_dir)" || return 1
    fi
    linker="$tools_dir/install/bin/mold"

    if [[ "$mode" == 1 ]]; then
        whp_mold_prepare_submodule "$submodule_path" || return 1
        whp_mold_bootstrap "$source_dir" "$tools_dir" || return 1
        linker="$MOLD_LINKER"
    elif [[ -x "$linker" ]]; then
        MOLD_LINKER="$linker"
    else
        BOOTSTRAP_MOLD=0
        MOLD_LINKER=
        export BOOTSTRAP_MOLD MOLD_LINKER
        return 0
    fi

    if [[ ! -x "$MOLD_LINKER" ]]; then
        printf 'error: selected mold linker is not executable: %s\n' "$MOLD_LINKER" >&2
        return 1
    fi
    if [[ ! -e "$(dirname "$MOLD_LINKER")/ld.mold" ]]; then
        ln -sf mold "$(dirname "$MOLD_LINKER")/ld.mold"
    fi

    # Keep the LTO archive probe as well as the real C/C++ driver tests.
    if ! whp_mold_link_probe "$MOLD_LINKER" ||
       ! whp_linker_driver_probe mold "$(dirname "$MOLD_LINKER")"; then
        if [[ "$mode" == auto ]]; then
            printf 'mold auto: host linker probe failed; retaining compiler default\n' >&2
            BOOTSTRAP_MOLD=0
            MOLD_LINKER=
            export BOOTSTRAP_MOLD MOLD_LINKER
            return 0
        fi
        printf 'error: selected mold failed host linker probes: %s\n' "$MOLD_LINKER" >&2
        return 1
    fi

    PATH="$(dirname "$MOLD_LINKER"):$PATH"
    export PATH
    case " ${LDFLAGS:-} " in
        *' -fuse-ld=mold '*) ;;
        *) whp_append_flag LDFLAGS '-fuse-ld=mold' ;;
    esac
    BOOTSTRAP_MOLD=1
    export BOOTSTRAP_MOLD MOLD_LINKER
    printf 'QEMU host linker:         %s\n' "$MOLD_LINKER"
}
