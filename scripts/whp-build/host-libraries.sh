# WHP QEMU-linked host library preparation.
# Defines whp_prepare_qemu_host_libraries(); build.sh controls when it runs.

whp_prepare_foundation_zlib()
{
    if [ "${WHP_ZLIB_PREPARED:-0}" = 1 ]; then
        return 0
    fi

    BOOTSTRAP_ZLIB=${BOOTSTRAP_ZLIB:-auto}
    BOOTSTRAP_ZLIB=$(whp_normalize_auto_switch BOOTSTRAP_ZLIB "$BOOTSTRAP_ZLIB") || exit 1
    export BOOTSTRAP_ZLIB

    # zlib is a required QEMU host dependency and is also consumed by libisofs.
    # auto keeps a usable host zlib; 1 forces the pinned WHP fork; 0 disables
    # only the managed fallback. Publish one private prefix for Meson/CMake and
    # downstream dependency bootstraps.
    if [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ] &&
       [ "${WHP_PORTABLE_PROBE_ONLY:-0}" != 1 ] &&
       [ "$BOOTSTRAP_ZLIB" != 0 ]; then
        ZLIB_BOOTSTRAP_MODE=auto
        if [ "$BOOTSTRAP_ZLIB" = 1 ]; then
            ZLIB_BOOTSTRAP_MODE=force
        fi
        WHP_ZLIB_PREFIX=$(
            "$PYTHON" "$SOURCE_DIR/scripts/ensure-zlib.py" \
                --build-dir "$BUILD_DIR" --mode "$ZLIB_BOOTSTRAP_MODE"
        ) || exit 1
        unset ZLIB_BOOTSTRAP_MODE

        if [ -n "$WHP_ZLIB_PREFIX" ]; then
            WHP_ZLIB_PC_PATH=
            for WHP_ZLIB_PC_DIR in \
                "$WHP_ZLIB_PREFIX/lib/pkgconfig" \
                "$WHP_ZLIB_PREFIX/lib64/pkgconfig" \
                "$WHP_ZLIB_PREFIX/libdata/pkgconfig"; do
                if [ -d "$WHP_ZLIB_PC_DIR" ]; then
                    WHP_ZLIB_PC_PATH="${WHP_ZLIB_PC_PATH:+$WHP_ZLIB_PC_PATH:}$WHP_ZLIB_PC_DIR"
                fi
            done
            if [ -n "$WHP_ZLIB_PC_PATH" ]; then
                PKG_CONFIG_PATH="$WHP_ZLIB_PC_PATH${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
                export PKG_CONFIG_PATH
            fi
            CMAKE_PREFIX_PATH="$WHP_ZLIB_PREFIX${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
            ZLIB_ROOT="$WHP_ZLIB_PREFIX"
            export WHP_ZLIB_PREFIX CMAKE_PREFIX_PATH ZLIB_ROOT
            unset WHP_ZLIB_PC_PATH WHP_ZLIB_PC_DIR
        fi
    fi

    WHP_ZLIB_PREPARED=1
    export WHP_ZLIB_PREPARED
}

whp_prepare_qemu_host_libraries()
{
    # This call is an idempotent drift guard. Normal builds prepare zlib in the
    # pre-Git host-tool phase so managed Git can consume the same pinned zlib.
    whp_prepare_foundation_zlib

    BOOTSTRAP_SDL=${BOOTSTRAP_SDL:-auto}
    case "$BOOTSTRAP_SDL" in
        y) BOOTSTRAP_SDL=1 ;;
        n) BOOTSTRAP_SDL=0 ;;
        auto|0|1) ;;
        *)
            printf 'error: BOOTSTRAP_SDL must be auto, 0, or 1\n' >&2
            exit 1
            ;;
    esac
    export BOOTSTRAP_SDL

    # SDL3 is a normal QEMU host dependency, so keep QEMU's Meson dependency
    # detection authoritative. The WHP bootstrap only provides a pinned private
    # prefix and makes it visible through pkg-config/CMake. auto keeps a usable
    # host SDL3, otherwise it falls back to the pinned SDL fork when the bootstrap
    # prerequisites are available. 1 forces the fork; 0 disables only the bundled
    # fallback and leaves normal host dependency discovery untouched.
    if [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ] &&
       [ "${WHP_PORTABLE_PROBE_ONLY:-0}" != 1 ] &&
       [ "$BOOTSTRAP_SDL" != 0 ]; then
        SDL_BOOTSTRAP_MODE=auto
        if [ "$BOOTSTRAP_SDL" = 1 ]; then
            SDL_BOOTSTRAP_MODE=force
        fi
        WHP_SDL_PREFIX=$(
            "$PYTHON" "$SOURCE_DIR/scripts/ensure-sdl.py" \
                --build-dir "$BUILD_DIR" --mode "$SDL_BOOTSTRAP_MODE"
        ) || exit 1
        unset SDL_BOOTSTRAP_MODE

        if [ -n "$WHP_SDL_PREFIX" ]; then
            WHP_SDL_PC_PATH=
            for WHP_SDL_PC_DIR in \
                "$WHP_SDL_PREFIX/lib/pkgconfig" \
                "$WHP_SDL_PREFIX/lib64/pkgconfig" \
                "$WHP_SDL_PREFIX/libdata/pkgconfig"; do
                if [ -d "$WHP_SDL_PC_DIR" ]; then
                    WHP_SDL_PC_PATH="${WHP_SDL_PC_PATH:+$WHP_SDL_PC_PATH:}$WHP_SDL_PC_DIR"
                fi
            done
            if [ -n "$WHP_SDL_PC_PATH" ]; then
                PKG_CONFIG_PATH="$WHP_SDL_PC_PATH${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
                export PKG_CONFIG_PATH
            fi
            CMAKE_PREFIX_PATH="$WHP_SDL_PREFIX${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
            SDL3_ROOT="$WHP_SDL_PREFIX"
            export WHP_SDL_PREFIX CMAKE_PREFIX_PATH SDL3_ROOT
            unset WHP_SDL_PC_PATH WHP_SDL_PC_DIR
        fi
    fi

    BOOTSTRAP_JACK=${BOOTSTRAP_JACK:-auto}
    case "$BOOTSTRAP_JACK" in
        y) BOOTSTRAP_JACK=1 ;;
        n) BOOTSTRAP_JACK=0 ;;
        auto|0|1) ;;
        *)
            printf 'error: BOOTSTRAP_JACK must be auto, 0, or 1\n' >&2
            exit 1
            ;;
    esac
    export BOOTSTRAP_JACK

    # JACK remains a normal QEMU Meson dependency. The WHP bootstrap only stages
    # the pinned client library and development files into a private prefix, then
    # exposes that prefix through pkg-config. auto keeps a usable host JACK,
    # 1 forces the fork, and 0 disables only the bundled fallback.
    if [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ] &&
       [ "${WHP_PORTABLE_PROBE_ONLY:-0}" != 1 ] &&
       [ "$BOOTSTRAP_JACK" != 0 ]; then
        JACK_BOOTSTRAP_MODE=auto
        if [ "$BOOTSTRAP_JACK" = 1 ]; then
            JACK_BOOTSTRAP_MODE=force
        fi
        WHP_JACK_PREFIX=$(
            "$PYTHON" "$SOURCE_DIR/scripts/ensure-jack.py" \
                --build-dir "$BUILD_DIR" --mode "$JACK_BOOTSTRAP_MODE"
        ) || exit 1
        unset JACK_BOOTSTRAP_MODE

        if [ -n "$WHP_JACK_PREFIX" ]; then
            WHP_JACK_PC_PATH=
            for WHP_JACK_PC_DIR in \
                "$WHP_JACK_PREFIX/lib/pkgconfig" \
                "$WHP_JACK_PREFIX/lib64/pkgconfig" \
                "$WHP_JACK_PREFIX/libdata/pkgconfig"; do
                if [ -d "$WHP_JACK_PC_DIR" ]; then
                    WHP_JACK_PC_PATH="${WHP_JACK_PC_PATH:+$WHP_JACK_PC_PATH:}$WHP_JACK_PC_DIR"
                fi
            done
            if [ -n "$WHP_JACK_PC_PATH" ]; then
                PKG_CONFIG_PATH="$WHP_JACK_PC_PATH${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
                export PKG_CONFIG_PATH
            fi

            # The private JACK bootstrap is intentionally dynamic on POSIX hosts.
            # Keep build-tree QEMU and its tests able to resolve that exact library
            # without installing the dependency globally.
            if [ -d "$WHP_JACK_PREFIX/lib" ]; then
                case "$WHP_HOST_OS" in
                    macos)
                        DYLD_FALLBACK_LIBRARY_PATH="$WHP_JACK_PREFIX/lib${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"
                        export DYLD_FALLBACK_LIBRARY_PATH
                        ;;
                    linux|freebsd|netbsd|openbsd|dragonfly|solaris)
                        LD_LIBRARY_PATH="$WHP_JACK_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
                        export LD_LIBRARY_PATH
                        ;;
                esac
            fi
            export WHP_JACK_PREFIX
            unset WHP_JACK_PC_PATH WHP_JACK_PC_DIR
        fi
    fi

}
