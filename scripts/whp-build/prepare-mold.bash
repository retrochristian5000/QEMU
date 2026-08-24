# Optional WHP mold host-linker preparation stage.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_mold_host_supported()
{
    # The WHP fast-linker fork currently links ELF, not Mach-O.  Keep the
    # Darwin QEMU host path on ld64 until the fork grows a Mach-O backend.
    [[ "$HOST_OS" != Darwin ]]
}

whp_mold_default_tools_dir()
{
    local host_tag

    host_tag="$(printf '%s-%s' "$HOST_ARCH" "$HOST_OS" |
        tr '[:upper:]' '[:lower:]' | tr -c '[:alnum:]_.-\n' '-')"
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

whp_mold_link_probe()
{
    local linker="$1"
    local probe_dir
    local source
    local output
    local linker_dir
    local status=0
    local ld_flags=()
    local lto_flags=()

    whp_mold_compiler_command "${CC:-cc}" || {
        printf 'error: cannot execute QEMU host compiler for mold probe: %s\n' \
            "${CC:-cc}" >&2
        return 1
    }

    linker_dir="$(dirname "$linker")"
    probe_dir="$(mktemp -d "${TMPDIR:-/tmp}/whp-mold-probe.XXXXXX")" || return 1
    source="$probe_dir/probe.c"
    output="$probe_dir/probe"
    printf 'int main(void) { return 0; }\n' > "$source"

    if [[ -n "${LDFLAGS:-}" ]]; then
        read -r -a ld_flags <<< "$LDFLAGS"
    fi
    if [[ "${QEMU_HOST_LTO:-auto}" == 1 ]]; then
        lto_flags=(-flto)
    fi

    if ! PATH="$linker_dir:$PATH" "${WHP_MOLD_CC_CMD[@]}" \
        "${lto_flags[@]}" "$source" -o "$output" \
        -fuse-ld=mold "${ld_flags[@]}"; then
        status=1
    elif ! "$output"; then
        status=1
    fi
    rm -rf "$probe_dir"
    return "$status"
}

whp_prepare_mold()
{
    local mode="${BOOTSTRAP_MOLD:-auto}"
    local submodule_path="${MOLD_SUBMODULE_PATH:-toolchains/fast-linker}"
    local source_dir="${MOLD_SOURCE_DIR:-$SOURCE_DIR/$submodule_path}"
    local tools_dir="${MOLD_TOOLS_DIR:-$(whp_mold_default_tools_dir)}"
    local linker="$tools_dir/install/bin/mold"

    case "$mode" in
        auto|0|1) ;;
        *)
            printf 'error: BOOTSTRAP_MOLD must be auto, 0, or 1\n' >&2
            return 1
            ;;
    esac

    if [[ "$mode" == 0 ]]; then
        MOLD_LINKER=
        export BOOTSTRAP_MOLD MOLD_LINKER
        return 0
    fi

    if ! whp_mold_host_supported; then
        if [[ "$mode" == 1 ]]; then
            printf '%s\n' \
                'mold linker: requested but disabled for this QEMU host.' \
                'The WHP fast-linker fork currently emits ELF and cannot link macOS Mach-O binaries; keeping Apple ld64.' >&2
        fi
        BOOTSTRAP_MOLD=0
        MOLD_LINKER=
        export BOOTSTRAP_MOLD MOLD_LINKER
        return 0
    fi

    if [[ "$mode" == 1 ]]; then
        whp_mold_prepare_submodule "$submodule_path" || return 1
        whp_mold_bootstrap "$source_dir" "$tools_dir" || return 1
        linker="$MOLD_LINKER"
    elif [[ -x "$linker" ]]; then
        MOLD_LINKER="$linker"
    else
        # auto never downloads or builds a new host linker.  Once the WHP fork
        # has been bootstrapped explicitly, auto reuses it on later builds.
        BOOTSTRAP_MOLD=0
        MOLD_LINKER=
        export BOOTSTRAP_MOLD MOLD_LINKER
        return 0
    fi

    if [[ ! -x "$MOLD_LINKER" ]]; then
        printf 'error: selected mold linker is not executable: %s\n' \
            "$MOLD_LINKER" >&2
        return 1
    fi
    if [[ ! -e "$(dirname "$MOLD_LINKER")/ld.mold" ]]; then
        ln -sf mold "$(dirname "$MOLD_LINKER")/ld.mold"
    fi

    if ! whp_mold_link_probe "$MOLD_LINKER"; then
        if [[ "$mode" == auto ]]; then
            printf '%s\n' \
                'mold linker auto: existing WHP mold could not link a host probe; using the platform linker.' >&2
            BOOTSTRAP_MOLD=0
            MOLD_LINKER=
            export BOOTSTRAP_MOLD MOLD_LINKER
            return 0
        fi
        printf '%s\n' \
            'error: the bootstrapped WHP mold linker cannot link a QEMU host probe.' \
            "linker: $MOLD_LINKER" >&2
        return 1
    fi

    PATH="$(dirname "$MOLD_LINKER"):$PATH"
    export PATH
    whp_append_flag LDFLAGS '-fuse-ld=mold'
    BOOTSTRAP_MOLD=1
    export BOOTSTRAP_MOLD MOLD_LINKER
    printf 'QEMU host linker:         %s\n' "$MOLD_LINKER"
}
