# Canonical inventory of WHP-owned shell build entry points and modules.
# Keep this list as data: runtime preflight and CI should consume it instead of
# maintaining independent copies that can drift when a script is added.

WHP_POSIX_BUILD_SCRIPTS=(
    "$SOURCE_DIR/build.sh"
    "$SOURCE_DIR/scripts/macos-builder.sh"
)

WHP_BASH_BUILD_SCRIPTS=(
    "$SOURCE_DIR/builder.sh"
    "$SOURCE_DIR/scripts/macos-builder.bash"
    "$SOURCE_DIR/scripts/macos-build-hygiene.bash"
    "$SOURCE_DIR/scripts/macos-compiler-policy.bash"
    "$SOURCE_DIR/scripts/macos-gtk-environment.bash"
    "$SOURCE_DIR/scripts/verify-macos-gtk.sh"
    "$SOURCE_DIR/scripts/verify-macos-toolchain.sh"
    "$SOURCE_DIR/scripts/verify-macos-lto.sh"
    "$SOURCE_DIR/scripts/bootstrap-powerpc-toolchain.sh"
    "$SOURCE_DIR/scripts/bootstrap-powerpc-toolchain-host.sh"
    "$SOURCE_DIR/scripts/bootstrap-powerpc-toolchain-git.sh"
    "$SOURCE_DIR/scripts/bootstrap-powerpc-clang.sh"
    "$SOURCE_DIR/scripts/bootstrap-powerpc-clang-core.sh"
    "$SOURCE_DIR/scripts/bootstrap-powerpc-clang-base.sh"
    "$SOURCE_DIR/scripts/bootstrap-powerpc-llvm-source-cache.sh"
    "$SOURCE_DIR/scripts/bootstrap-powerpc-llvm-ar.sh"
    "$SOURCE_DIR/scripts/bootstrap-powerpc-llvm-nm.sh"
    "$SOURCE_DIR/scripts/bootstrap-powerpc-llvm-strip.sh"
    "$SOURCE_DIR/scripts/meson-build-openbios.sh"
    "$SOURCE_DIR/scripts/build-openbios.sh"
    "$SOURCE_DIR/scripts/whp-build/common.bash"
    "$SOURCE_DIR/scripts/whp-build/gnu-make.bash"
    "$SOURCE_DIR/scripts/whp-build/stages.bash"
    "$SOURCE_DIR/scripts/whp-build/prepare-build.bash"
    "$SOURCE_DIR/scripts/whp-build/prepare-sources.bash"
    "$SOURCE_DIR/scripts/whp-build/prepare-mold.bash"
    "$SOURCE_DIR/scripts/whp-build/host-cpu-tuning.bash"
    "$SOURCE_DIR/scripts/whp-build/configure.bash"
    "$SOURCE_DIR/scripts/whp-build/build-targets.bash"
    "$SOURCE_DIR/scripts/whp-build/configure-openbios.bash"
    "$SOURCE_DIR/scripts/whp-build/preflight.bash"
    "$SOURCE_DIR/scripts/whp-build/post-build.bash"
    "$SOURCE_DIR/scripts/whp-build/shell-inventory.bash"
)
