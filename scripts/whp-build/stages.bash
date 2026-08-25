# WHP build-stage loader.  builder.sh sources this file and runs the loaded
# stages in order; this file is not a public entry point.

if [[ -z "${BASH_VERSION:-}" ]]; then
    printf 'error: the WHP build system requires GNU Bash\n' >&2
    return 1 2>/dev/null || exit 1
fi
: "${SOURCE_DIR:?builder.sh must define SOURCE_DIR before loading the build system}"

source "$SOURCE_DIR/scripts/whp-build/common.bash"

for build_stage_module in \
    prepare-build.bash \
    prepare-sources.bash \
    prepare-seabios-grub.bash \
    prepare-mold.bash \
    host-cpu-tuning.bash \
    configure.bash \
    build-targets.bash; do
    source "$SOURCE_DIR/scripts/whp-build/$build_stage_module"
done
unset build_stage_module
