#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path
import ctypes
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
config = (ROOT / 'scripts/whp-config/config.py').read_text(encoding='utf-8')
build = (ROOT / 'build.sh').read_text(encoding='utf-8')
builder = (ROOT / 'builder.bash').read_text(encoding='utf-8')
bootstrap = (ROOT / 'scripts/bootstrap-native-clang.bash').read_text(encoding='utf-8')
i386_bootstrap = (ROOT / 'scripts/bootstrap-i386-clang.bash').read_text(encoding='utf-8')
powerpc_bootstrap = (ROOT / 'scripts/bootstrap-powerpc-clang-base.bash').read_text(encoding='utf-8')
inventory = (ROOT / 'scripts/whp-build/shell-inventory.bash').read_text(encoding='utf-8')
macos_builder = (ROOT / 'scripts/macos-builder.bash').read_text(encoding='utf-8')
macos_workflow = (ROOT / '.github/workflows/native-llvm-macos.yml').read_text(encoding='utf-8')
disas_objdump = (ROOT / 'scripts/disas-objdump.pl').read_text(encoding='utf-8')

# Syntax is the first guard. Keep the public POSIX entry parseable by /bin/sh,
# and require every Bash implementation touched by this lane to parse before
# semantic/string-contract assertions are evaluated.
subprocess.run(['sh', '-n', str(ROOT / 'build.sh')], check=True)
for bash_path in (
    ROOT / 'builder.bash',
    ROOT / 'scripts/bootstrap-native-clang.bash',
    ROOT / 'scripts/bootstrap-i386-clang.bash',
    ROOT / 'scripts/bootstrap-powerpc-clang-base.bash',
):
    subprocess.run(['bash', '-n', str(bash_path)], check=True)

assert "Option('BOOTSTRAP_NATIVE_LLVM', 'Host features'" in config
assert "Option('NATIVE_LLVM_CXX_STANDARD', 'Host features'" in config
assert "Option('NATIVE_LLVM_PCH', 'Host features', 'Native LLVM precompiled headers', 'choice', 'auto', ('auto', 'y', 'n'))" in config
assert 'scripts/bootstrap-native-clang.sh' in build
wrapper = (ROOT / 'scripts/bootstrap-native-clang.sh').read_text(encoding='utf-8')
assert 'llvm-nm llvm-objcopy' in wrapper
assert 'llvm-objdump llvm-readelf llvm-strip' in wrapper
assert 'native LLVM bootstrap did not provide llvm-lipo' in wrapper
assert 'CC="$NATIVE_LLVM_DIR/bin/clang"' in build
assert 'CXX="$NATIVE_LLVM_DIR/bin/clang++"' in build
assert 'AR="${AR:-$NATIVE_LLVM_DIR/bin/llvm-ar}"' in build
assert 'RANLIB="${RANLIB:-$NATIVE_LLVM_DIR/bin/llvm-ranlib}"' in build
configure = (ROOT / 'configure').read_text(encoding='utf-8')
assert 'ranlib="${RANLIB-${cross_prefix}ranlib}"' in configure
assert 'echo "ranlib = [$(meson_quote $ranlib)]" >> $cross' in configure
assert 'preserve_env RANLIB' in configure
assert 'native LLVM toolchain drifted before QEMU configure' not in build
assert '"RANLIB:$NATIVE_LLVM_DIR/bin/llvm-ranlib"' not in build
assert '"AR:$NATIVE_LLVM_DIR/bin/llvm-ar"' not in build
assert 'whp_archive_toolchain_smoke "$CC" "$AR" "$RANLIB" "$BUILD_DIR" "$NM"' in build
assert 'WHP_ARCHIVE_TOOL_SIGNATURE="$AR|$RANLIB|$NM"' in build
assert 'whp_archive_tool_signature_now="$AR|$RANLIB|$NM"' in build
capability_index = build.index('whp_archive_tool_signature_now="$AR|$RANLIB|$NM"')
portable_index = build.index('portable_core()')
libisofs_index = build.index('BOOTSTRAP_LIBISOFS=${BOOTSTRAP_LIBISOFS:-auto}')
shell_probe_index = build.index('WHP orchestration shell: %s')
assert portable_index < libisofs_index < capability_index < shell_probe_index
assert 'NM="${NM:-$NATIVE_LLVM_DIR/bin/llvm-nm}"' in build
assert 'OBJCOPY="$NATIVE_LLVM_DIR/bin/llvm-objcopy"' in build
assert 'OBJDUMP="$NATIVE_LLVM_DIR/bin/llvm-objdump"' in build
assert 'READELF="$NATIVE_LLVM_DIR/bin/llvm-readelf"' in build
assert 'STRIP="$NATIVE_LLVM_DIR/bin/llvm-strip"' in build
assert 'LIPO="$NATIVE_LLVM_DIR/bin/llvm-lipo"' in build
assert 'OBJC="$NATIVE_LLVM_DIR/bin/clang"' in build
assert 'OBJCOPY OBJDUMP READELF STRIP OBJC PATH' in build
assert 'export LD LIPO NATIVE_LLVM_LDFLAG LDFLAGS' in build
assert '$ENV{"OBJDUMP"} || "objdump"' in disas_objdump
assert 'LD="$NATIVE_LLVM_DIR/bin/ld64.lld"' in build
assert 'NATIVE_LLVM_LDFLAG=-fuse-ld=lld' in build
assert 'toolchains/llvm-project' in bootstrap
# Firmware LLVM variants must not accept cached cross-linker ABI choices.
for source in (i386_bootstrap, powerpc_bootstrap):
    for kind in ('EXE', 'SHARED', 'MODULE', 'STATIC'):
        assert f'-DCMAKE_{kind}_LINKER_FLAGS_RELEASE=' in source
        assert f'-DCMAKE_{kind}_LINKER_FLAGS=' in source
    for lang in ('C', 'CXX', 'ASM'):
        assert f'-UCMAKE_{lang}_COMPILER_TARGET' in source
    assert 'unset LIBRARY_PATH COMPILER_PATH GCC_EXEC_PREFIX LD_PRELOAD' in source
    assert 'unset DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH DYLD_INSERT_LIBRARIES' in source
assert 'case "${WHP_MACOS_ARCH:-auto}" in' in i386_bootstrap
assert 'arm64|arm64e|x86_64) i386_host_arch="$WHP_MACOS_ARCH"' in i386_bootstrap
assert '"-DCMAKE_OSX_ARCHITECTURES=$i386_host_arch"' in i386_bootstrap
assert 'git clone' not in bootstrap
assert "llvm_enable_projects='clang;lld'" in bootstrap
assert "llvm_distribution_components='clang;clang-resource-headers;lld;llvm-ar;llvm-ranlib;llvm-lib;llvm-dlltool;llvm-rc;llvm-windres;llvm-nm;llvm-objcopy;llvm-objdump;llvm-strip;llvm-readobj;llvm-readelf;llvm-config;llvm-tblgen;llvm-headers;llvm-libraries;cmake-exports'" in bootstrap
assert 'llvm_distribution_components="${llvm_distribution_components};llvm-otool;llvm-lipo;LTO;builtins;runtimes"' in bootstrap
assert 'for required_tool in llvm-otool llvm-lipo ld64.lld; do' in bootstrap
assert '"$prefix/bin/llvm-otool" --version >/dev/null 2>&1 || {' in bootstrap
# Keep llvm-objdump primary; the otool-style interface comes from its symlink.
assert 'llvm-objdump;llvm-strip' in bootstrap
assert '"-DLLVM_ENABLE_PROJECTS=$llvm_enable_projects"' in bootstrap
assert 'for required_tool in clang clang++ ld.lld lld-link llvm-ar llvm-ranlib' in bootstrap
assert 'llvm-nm llvm-objcopy llvm-objdump llvm-strip' in bootstrap
assert 'llvm-readobj llvm-readelf llvm-config llvm-tblgen' in bootstrap
assert 'llvm-lib llvm-dlltool llvm-rc llvm-windres' in bootstrap
assert 'windows_cross_target_usable()' in bootstrap
assert '--target=i686-w64-windows-gnu' in bootstrap
assert '--target=x86_64-w64-windows-gnu' in bootstrap
assert '"$prefix/bin/lld-link" /machine:x64' in bootstrap
assert '"$prefix/bin/ld.lld" -m i386pep' in bootstrap
assert 'native_llvm_validation_error tool "missing required tool: $required_tool"' in bootstrap
assert 'clang;clang-resource-headers' in bootstrap
assert "LLVM_TARGETS_TO_BUILD='AArch64;X86;PowerPC'" in bootstrap
assert "LLD_ENABLE_BACKENDS='ELF;COFF;MinGW;MachO'" in bootstrap
assert '"-DLLVM_TARGETS_TO_BUILD=$LLVM_TARGETS_TO_BUILD"' in bootstrap
assert '"-DLLD_ENABLE_BACKENDS=$LLD_ENABLE_BACKENDS"' in bootstrap
assert 'for target in aarch64 x86 ppc32; do' in bootstrap
assert 'missing required LLVM target backend: $target' in bootstrap
assert 'WHP_SHARED_LLVM_DIR="$NATIVE_LLVM_DIR"' in build
assert 'bootstrap-native-clang.sh' in inventory

# BOOTSTRAP_NATIVE_LLVM selects the compiler for QEMU host objects, not the
# compiler for firmware helpers or cross-toolchain host programs. Preserve an
# explicit *_FOR_BUILD override, but repair the old non-Darwin inheritance path
# before firmware preparation when CC/CXX were replaced by native LLVM.
assert 'cc_for_build_was_set=0' in builder
assert 'cxx_for_build_was_set=0' in builder
assert 'objc_for_build_was_set=0' in builder
assert 'CC_FOR_BUILD=cc' in builder
assert 'CXX_FOR_BUILD=c++' in builder
assert 'OBJC_FOR_BUILD="$CC_FOR_BUILD"' in builder
assert 'native_llvm_build_compiler_reset=1' in builder
prepare_index = builder.index('whp_prepare_build "$@"')
reset_index = builder.index('CC_FOR_BUILD=cc')
firmware_index = builder.index('whp_prepare_seabios_grub_sources')
assert prepare_index < reset_index < firmware_index
assert builder.index('whp_prepare_configure_args', reset_index) < firmware_index

# The public build entry selects one Ninja for the whole host build. Native LLVM
# must consume that same executable instead of independently searching PATH,
# because CMake's generator is part of the bootstrap producer/consumer boundary.
assert 'ninja_cmd="${NINJA_CMD:-${NINJA:-ninja}}"' in bootstrap
assert '"-DCMAKE_MAKE_PROGRAM=$ninja_cmd"' in bootstrap
assert 'WHP native LLVM Ninja:' in bootstrap

# The LLVM bootstrap language level is user-selectable but must be explicit and
# cache-identifying. C++26 probes both the final spelling and Clang's c++2c
# spelling so the bootstrap can work across compiler transition releases.
assert 'LLVM_CXX_STANDARD="${NATIVE_LLVM_CXX_STANDARD:-23}"' in bootstrap
assert 'compiler_supports_cxx_standard()' in bootstrap
assert 'standards=(c++26 c++2c)' in bootstrap
assert '"-DCMAKE_CXX_STANDARD=$LLVM_CXX_STANDARD"' in bootstrap
assert '    -DCMAKE_C_FLAGS=\n' in bootstrap
assert '    -DCMAKE_CXX_FLAGS=\n' in bootstrap
assert 'CMAKE_C_FLAGS=\nCMAKE_CXX_FLAGS=\n' in bootstrap
assert '-DCMAKE_CXX_STANDARD_REQUIRED=ON' in bootstrap
assert 'CMAKE_CXX_STANDARD=$LLVM_CXX_STANDARD' in bootstrap
assert 'CMAKE_CXX_STANDARD_REQUIRED=ON' in bootstrap
assert 'LLVM_PCH="${NATIVE_LLVM_PCH:-auto}"' in bootstrap
assert 'cmake_disable_precompile_headers=ON' in bootstrap
assert 'cmake_disable_precompile_headers=OFF' in bootstrap
assert '"-DCMAKE_DISABLE_PRECOMPILE_HEADERS=$cmake_disable_precompile_headers"' in bootstrap
assert 'CMAKE_DISABLE_PRECOMPILE_HEADERS=$cmake_disable_precompile_headers' in bootstrap
assert 'WHP native LLVM precompiled headers:' in bootstrap

# The public build exports menu choices as shell integers. 'auto' must remain
# unset so the native LLVM bootstrap can resolve the host compiler and cache
# itself; saved y/n must continue to mean explicit on/off.
assert "    'NATIVE_LLVM_PCH',\n" in config
assert 'NATIVE_LLVM_PCH|Host features|Native LLVM precompiled headers|choice|auto|auto,y,n|' in (
    ROOT / 'scripts/whp-config/menu-options.def'
).read_text(encoding='utf-8')
with tempfile.TemporaryDirectory() as temporary:
    pch_config = Path(temporary) / '.whpconfig'
    for selected, expected in (('auto', None), ('y', "NATIVE_LLVM_PCH='1'"),
                               ('n', "NATIVE_LLVM_PCH='0'")):
        pch_config.write_text(
            'WHP_CONFIG_VERSION=3\nNATIVE_LLVM_PCH=' + selected + '\n',
            encoding='utf-8',
        )
        env = os.environ.copy()
        env.pop('NATIVE_LLVM_PCH', None)
        result = subprocess.run(
            ['python3', str(ROOT / 'scripts/whp-config/config.py'),
             '--shell', str(pch_config)],
            env=env, text=True, capture_output=True, check=True,
        )
        if expected is None:
            assert 'NATIVE_LLVM_PCH=' not in result.stdout
        else:
            assert expected in result.stdout, (selected, result.stdout)
assert "NATIVE_LLVM_CXX_STANDARD: '26'" in macos_workflow
assert "WHP native LLVM C++ standard: C++26" in macos_workflow
assert "grep -Fxq 'CMAKE_CXX_STANDARD=26' \"$marker\"" in macos_workflow
assert "grep -Fxq 'CMAKE_CXX_STANDARD_REQUIRED=ON' \"$marker\"" in macos_workflow
assert "grep -Fxq 'BOOTSTRAP_SCHEMA=14' \"$marker\"" in macos_workflow

# Darwin Clang passes -lto_library <InstalledDir>/../lib/libLTO.dylib to ld64
# when LTO is active. A Clang-only distribution therefore creates a producer /
# consumer mismatch: WHP Clang emits current LLVM bitcode but the linker cannot
# load a matching reader. The same Darwin distribution also owns compiler-rt,
# so keep LTO and both runtime umbrella components in one exact platform policy.
assert 'llvm_distribution_components="${llvm_distribution_components};llvm-otool;llvm-lipo;LTO;builtins;runtimes"' in bootstrap
assert 'LLVM_DISTRIBUTION_COMPONENTS=$llvm_distribution_components' in bootstrap
assert '[[ -f "$prefix/lib/libLTO.dylib" ]] || {' in bootstrap

# A Darwin Clang driver accepts -fsanitize=undefined even when its matching
# compiler-rt runtime was never built or installed. Native macOS toolchains must
# therefore build compiler-rt with the just-built Clang, generate the runtimes
# graph, distribute both builtins and runtimes, and prove the installed driver
# can link an actual UBSan executable. Linux keeps its existing no-runtimes
# profile unless it is deliberately opted in later.
assert 'llvm_enable_runtimes=compiler-rt' in bootstrap
assert 'llvm_include_runtimes=ON' in bootstrap
assert '"-DLLVM_ENABLE_RUNTIMES=$llvm_enable_runtimes"' in bootstrap
assert '"-DLLVM_INCLUDE_RUNTIMES=$llvm_include_runtimes"' in bootstrap
assert 'LLVM_ENABLE_RUNTIMES=$llvm_enable_runtimes' in bootstrap
assert '-fsanitize=undefined' in bootstrap
assert '-fsanitize=undefined' in macos_workflow
assert 'BOOTSTRAP_SCHEMA=14' in bootstrap

# LLVM configures builtins and runtimes as separate ExternalProjects on Darwin.
# The parent CMAKE_OSX_SYSROOT is not a strong enough contract for every lane:
# Objective-C runtime links must carry the same SDK, architecture, and minimum
# OS version into both sub-builds. The installed toolchain must then prove that
# the selected Darwin linker can resolve libobjc and Cocoa before it is cached
# or published.
assert 'darwin_external_cmake_args=' in bootstrap
assert 'darwin_runtimes_cmake_args=' in bootstrap
assert '-DCMAKE_OSX_SYSROOT=$sdkroot' in bootstrap
assert '-DCMAKE_OSX_ARCHITECTURES=$darwin_cmake_arch' in bootstrap
assert '-DCMAKE_OSX_DEPLOYMENT_TARGET=$deployment_target' in bootstrap
assert '"-DRUNTIMES_CMAKE_ARGS=$darwin_runtimes_cmake_args"' in bootstrap
assert '"-DBUILTINS_CMAKE_ARGS=$darwin_external_cmake_args"' in bootstrap
assert '"${cmake_darwin_runtime_args[@]}"' in bootstrap
assert '-fobjc-link-runtime' in bootstrap
assert '-x objective-c' in bootstrap
assert '-framework Cocoa' in bootstrap
assert 'cannot link Objective-C against SDK' in bootstrap

# Clang can emit ld64-1250 class-message stubs such as
# _objc_msgSendClass$new$_OBJC_CLASS_$_NSTextField. The pinned WHP ld64.lld
# currently synthesizes only the older _objc_msgSend$selector family. Disable
# only the unsupported class-selector optimization when this exact native LLD
# pairing is active; Apple ld and non-native compiler paths must stay unchanged.
assert '${NATIVE_LLVM_LDFLAG:-}' in macos_builder
assert '"${LD:-}" == "$NATIVE_LLVM_DIR/bin/ld64.lld"' in macos_builder
assert 'whp_append_flag OBJCFLAGS "-fno-objc-msgsend-class-selector-stubs"' in macos_builder

# --read-workers is a relatively new, optional LLD setting. Do not pass it
# to Apple ld, older LLD, or LLD compiled without threads. A real link probe
# gates the flag; an explicit unsupported request is rejected, while the
# automatic default is safely omitted.
assert 'native_lld_read_workers="${NATIVE_LLVM_READ_WORKERS:-${JOBS:-1}}"' in macos_builder
assert 'NATIVE_LLVM_READ_WORKERS must be a non-negative integer' in macos_builder
assert 'whp_native_lld_accepts_read_workers "$native_lld_read_workers"' in macos_builder
assert 'whp_append_flag LDFLAGS "-Wl,--read-workers=$native_lld_read_workers"' in macos_builder
assert 'omitting optional link prefetch' in macos_builder
assert 'if [[ "$native_macho_lld" == 0 ]]; then' in macos_builder
assert 'whp_append_flag LDFLAGS "-Wl,-dead_strip"' in macos_builder

# Native LLVM may reuse a proven Mach-O LLD, including ARM64e when its
# authenticated-relocation probe passes and the developer explicitly opts in.
# Test the base linker before optional worker flags. Failed probes preserve
# the Apple ld fallback instead of mislabelling unsupported links.
assert 'bootstrap_lld_link_probe()' in bootstrap
assert 'if bootstrap_lld_link_probe;' in bootstrap
assert 'if bootstrap_lld_link_probe -Wl,--read-workers="$LLVM_LINK_JOBS"; then' in bootstrap
assert '[[ ! -s "$probe_output" || ! -x "$probe_output" ]]' in bootstrap
assert 'bootstrap_linker_args=()' in bootstrap
assert 'whp_bootstrap_arm64e_lld_auth_probe()' in bootstrap
assert '"$bootstrap_lld_arch_ok" == 1' in bootstrap
assert '-x "$TOOLCHAIN_DIR/bin/ld64.lld"' in bootstrap
assert 'PATH="$TOOLCHAIN_DIR/bin:$PATH"' in bootstrap
assert '"$bootstrap_cxx" -arch "$darwin_cmake_arch" -fuse-ld=lld' in bootstrap
assert '-Wl,--read-workers="$LLVM_LINK_JOBS"' in bootstrap
assert '"-DLLVM_USE_LINKER=lld"' in bootstrap
assert 'bootstrap_lld_link_flags=' in bootstrap
assert '"-DCMAKE_EXE_LINKER_FLAGS=$bootstrap_lld_link_flags"' in bootstrap
assert '"-DCMAKE_SHARED_LINKER_FLAGS=$bootstrap_lld_link_flags"' in bootstrap
assert '"-DCMAKE_MODULE_LINKER_FLAGS=$bootstrap_lld_link_flags"' in bootstrap
assert bootstrap.index('bootstrap_lld_link_flags=') < bootstrap.index('bootstrap_linker_args=(', bootstrap.index('bootstrap_lld_link_flags='))
assert '"${bootstrap_linker_args[@]}"' in bootstrap
assert 'WHP native LLVM bootstrap linker:' in bootstrap
assert 'local clang_link_driver=("$prefix/bin/clang")' in bootstrap
# A native macOS toolchain can use the Apple linker even if Mach-O LLD
# cannot yet link a new SDK's UBSan / Objective-C framework relocations.
# LLD is still installed and independently probed for explicit use.
usable_section = bootstrap.split('\nusable()\n{', 1)[1].split(
    '\n}\n\nverify_asan_when_requested()', 1)[0]
assert 'clang_link_driver+=(-fuse-ld=lld)' not in usable_section
assert 'local clang_link_driver=("$prefix/bin/clang")' in usable_section
assert 'native_llvm_validation_error tool "missing required tool: $required_tool"' in usable_section
assert 'bootstrap_linker_name="$TOOLCHAIN_DIR/bin/ld64.lld"' in bootstrap
assert '"${clang_link_driver[@]}" -arch "$darwin_cmake_arch"' in bootstrap
assert 'linker_driver_args' not in bootstrap

# The public build entry owns platform detection. Native LLVM consumes the same
# normalized OS/kernel/architecture identity instead of making an independent
# platform decision that can drift from QEMU's wrapper selection.
for host_os in ('macos', 'linux', 'windows'):
    assert f'WHP_HOST_OS={host_os}' in build
assert 'export WHP_HOST_OS WHP_HOST_KERNEL WHP_HOST_ARCH' in build
assert 'host_os="${WHP_HOST_OS:-}"' in bootstrap
assert 'HOST_OS=$host_os' in bootstrap
assert 'HOST_KERNEL=$host_kernel' in bootstrap
assert 'HOST_ARCH=$host_arch' in bootstrap

# Apple Silicon uses aarch64 as the backend architecture; arm64e is a
# Mach-O ABI choice. The host triple may contain the Darwin kernel version,
# while Clang's default target must be versioned macOS, not iOS/iPadOS.
assert 'host_tag=aarch64' in bootstrap
assert 'darwin_cmake_arch=arm64' in bootstrap
assert "arm64|aarch64) printf 'aarch64\\n'" in bootstrap
assert 'canonical_native_target_triple()' in bootstrap
assert 'llvm_host_triple="$bootstrap_cc_target_canonical"' in bootstrap
assert 'llvm_default_target_triple="$host_tag-apple-macosx$deployment_target"' in bootstrap
assert 'llvm_default_target_triple="$llvm_host_triple"' in bootstrap
assert '-DLLVM_MACOS_EXPLICIT_DEFAULT_TRIPLE=ON' in bootstrap
assert '"-DCMAKE_OSX_ARCHITECTURES=$darwin_cmake_arch"' in bootstrap
assert '"-DLLVM_HOST_TRIPLE=$llvm_host_triple"' in bootstrap
assert '"-DLLVM_DEFAULT_TARGET_TRIPLE=$llvm_default_target_triple"' in bootstrap
assert 'LLVM_HOST_TRIPLE=$llvm_host_triple' in bootstrap
assert 'LLVM_DEFAULT_TARGET_TRIPLE=$llvm_default_target_triple' in bootstrap
assert 'BOOTSTRAP_CC_TARGET_TRIPLE_CANONICAL=$bootstrap_cc_target_canonical' in bootstrap
assert 'BOOTSTRAP_CXX_TARGET_TRIPLE_CANONICAL=$bootstrap_cxx_target_canonical' in bootstrap
assert 'expected_target_abi="$(native_target_abi_key "$llvm_default_target_triple")"' in bootstrap
assert bootstrap.count('target_abi="$(native_target_abi_key "$target" 2>/dev/null || true)"') >= 2
assert bootstrap.count('"$target_abi" == "$expected_target_abi"') >= 2

# A cached compiler must exercise the frontend, resource headers, IR verifier,
# and backend before reuse. --version alone cannot detect mixed LLVM objects
# such as a verifier that rejects an attribute emitted by matching Clang.
assert '"$prefix/bin/clang" -x c -c - -o /dev/null' in bootstrap
assert '#include <stddef.h>' in bootstrap
assert '#include <stdarg.h>' in bootstrap
assert '-fno-omit-frame-pointer -momit-leaf-frame-pointer' in bootstrap
assert '"$prefix/bin/clang++" -x c++ -c - -o /dev/null' in bootstrap

# Native ABI identity is more than the CPU name. On macOS, follow LLVM's
# ARCH-VENDOR-OS[-ENV] boundary: `apple` must be the vendor field and the OS
# field must be Darwin/macOS. A loose `*-apple-darwin*` substring would accept
# malformed triples such as arm64-unknown-apple-darwin.
assert 'native_target_matches_host "$target"' in bootstrap
assert "IFS='-' read -r arch target_vendor target_os _ <<< \"$target\"" in bootstrap
assert '[[ "$target_vendor" == apple ]] || return 1' in bootstrap
assert '[[ "$target" == "$arch-$target_vendor-$target_os" ]] || return 1' in bootstrap
assert '[[ "$target_os" =~ ^(darwin|macosx|macos)' in bootstrap
assert 'native_target_abi_key()' in bootstrap
assert 'source "$SCRIPT_DIR/whp-build/macos-target-abi.bash"' in bootstrap
assert 'bootstrap_cc_abi="$(native_target_abi_key "$bootstrap_cc_target_canonical")"' in bootstrap
assert 'bootstrap_cxx_abi="$(native_target_abi_key "$bootstrap_cxx_target_canonical")"' in bootstrap
assert 'if [[ "$bootstrap_cc_abi" != "$bootstrap_cxx_abi" ]]; then' in bootstrap
assert 'native LLVM bootstrap C and C++ compiler target triples differ' in bootstrap
assert bootstrap.index('native LLVM bootstrap C and C++ compiler target triples differ') < bootstrap.index('llvm_host_triple="$bootstrap_cc_target_canonical"')
assert bootstrap.index('llvm_default_target_triple="$host_tag-apple-macosx$deployment_target"') < bootstrap.index('git -C "$SOURCE_DIR" submodule update')

for loose_match in ('*-apple-darwin*', '*-apple-macos*', '*-apple-macosx*'):
    assert loose_match not in bootstrap
assert 'linux_target_abi_key "$target"' in bootstrap
assert '*x32|*ilp32*' in bootstrap

# Evaluate the actual shell matcher so a broad prefix check cannot silently
# re-admit simulator, Catalyst, or malformed Darwin targets.
def extract_bootstrap_function(name):
    start = bootstrap.index(f'{name}()\n{{')
    end = bootstrap.index('\n}\n', start) + len('\n}\n')
    return bootstrap[start:end]

target_probe = '\n'.join([
    'set -euo pipefail',
    'host_os=macos',
    'host_tag=aarch64',
    extract_bootstrap_function('canonical_native_arch'),
    extract_bootstrap_function('native_target_matches_host'),
    'if native_target_matches_host "$1"; then echo accept; else echo reject; fi',
])
for target in (
    'arm64-apple-darwin25.0.0',
    'aarch64-apple-macos26.0',
    'aarch64-apple-macosx15.6',
    'aarch64-apple-darwin',
):
    result = subprocess.run(['bash', '-c', target_probe, '--', target],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == 'accept', (target, result.stderr)
for target in (
    'aarch64-apple-ios19.0',
    'aarch64-apple-tvos26.0',
    'aarch64-apple-watchos11',
    'aarch64-apple-xros2',
    'aarch64-apple-driverkit25',
    'aarch64-apple-darwin25-simulator',
    'aarch64-apple-darwin25-macabi',
    'aarch64-apple-darwin25-unknown',
    'aarch64-unknown-apple-darwin25',
    'aarch64-apple-macosgarbage',
    'arm64-apple-darwinX',
):
    result = subprocess.run(['bash', '-c', target_probe, '--', target],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == 'reject', (target, result.stderr)

# The Linux guard must accept vendor aliases without accidentally allowing
# x32/ILP32 compilers to emit the wrong native pointer-width ABI.
linux_probe = '\n'.join([
    'set -euo pipefail',
    'host_os=linux',
    'host_tag=x86_64',
    extract_bootstrap_function('canonical_native_arch'),
    extract_bootstrap_function('linux_target_abi_key'),
    extract_bootstrap_function('native_target_matches_host'),
    'if native_target_matches_host "$1"; then echo accept; else echo reject; fi',
])
for target in ('x86_64-pc-linux-gnu', 'amd64-linux-gnu',
               'x86_64-unknown-linux-musl'):
    result = subprocess.run(['bash', '-c', linux_probe, '--', target],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == 'accept', (target, result.stderr)
for target in ('x86_64-unknown-linux-gnux32', 'x86_64-linux-muslx32',
               'x86_64-unknown-linux-gnu_ilp32',
               'x86_64-unknown-linux-gnu-extra', 'i686-linux-gnu'):
    result = subprocess.run(['bash', '-c', linux_probe, '--', target],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == 'reject', (target, result.stderr)

arm_linux_probe = linux_probe.replace('host_tag=x86_64', 'host_tag=aarch64')
for target in ('aarch64-unknown-linux-gnu', 'arm64-linux-musl'):
    result = subprocess.run(['bash', '-c', arm_linux_probe, '--', target],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == 'accept', (target, result.stderr)
for target in ('aarch64-unknown-linux-gnu_ilp32', 'aarch64-linux-gnuilp32'):
    result = subprocess.run(['bash', '-c', arm_linux_probe, '--', target],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == 'reject', (target, result.stderr)

# Triple metadata is insufficient if a compiler wrapper silently injects
# -mx32 or an ILP32 ABI flag. Exercise the actual C/C++ LP64 compile probe
# using a host compiler when one is available, without producing binaries.
lp64_probe = extract_bootstrap_function('native_bootstrap_lp64_probe')
assert 'sizeof(void *) == 8 && sizeof(long) == 8' in lp64_probe
assert 'native_bootstrap_lp64_probe "$bootstrap_cc" c' in bootstrap
assert 'native_bootstrap_lp64_probe "$bootstrap_cxx" c++' in bootstrap
if ctypes.sizeof(ctypes.c_void_p) == 8:
    for compiler, language in (('gcc', 'c'), ('g++', 'c++')):
        if shutil.which(compiler):
            result = subprocess.run(
                ['bash', '-c', lp64_probe + '\nnative_bootstrap_lp64_probe "$1" "$2"',
                 '--', compiler, language],
                capture_output=True, text=True)
            assert result.returncode == 0, (compiler, result.stderr)
    if shutil.which('gcc'):
        source = ('typedef char check[(sizeof(void *) == 8 && '
                  'sizeof(long) == 8) ? 1 : -1];\n')
        x32 = subprocess.run(['gcc', '-mx32', '-x', 'c', '-fsyntax-only', '-'],
                             input=source, capture_output=True, text=True)
        if x32.returncode != 0 and 'size of array' in x32.stderr:
            wrapped = lp64_probe + ('\nwhp_x32() { gcc -mx32 "$@"; }\n'
                                    'native_bootstrap_lp64_probe whp_x32 c')
            result = subprocess.run(['bash', '-c', wrapped],
                                    capture_output=True, text=True)
            assert result.returncode != 0, result.stderr

# Do not pass CMake cache variables that the pinned LLVM revision no longer
# defines. CMake reports these as manually-specified variables that were not
# used by the project, which hides meaningful bootstrap warnings in noise.
assert 'CLANG_ENABLE_ARCMT' not in bootstrap
for llvm_bootstrap in (bootstrap, i386_bootstrap, powerpc_bootstrap):
    assert 'LLVM_ENABLE_TERMINFO' not in llvm_bootstrap

# CMake's Ninja generator already tracks CMakeLists.txt and re-runs CMake
# when those inputs change. Repeating explicit CMake configuration before
# every incremental retry is unnecessary if the generator and inputs match.
# Exercise the actual extracted shell block with a fake CMake executable.
assert '# Reuse the generated Ninja graph when the invocation is unchanged.' in bootstrap
configure_guard = bootstrap.split(
    '# Reuse the generated Ninja graph when the invocation is unchanged.\n', 1
)[1].split('\nif [[ "$TOOLCHAIN_FORCE_REBUILD" == 1 ]]; then', 1)[0]
assert 'WHP_CMAKE_CONFIG_SCHEMA=2' in configure_guard
assert 'for env_name in PATH AR RANLIB PKG_CONFIG' in configure_guard
assert 'CMAKE_FIND_ROOT_PATH' in configure_guard
assert 'CMakeCache.txt' in configure_guard and 'build.ninja' in configure_guard
assert 'cmake "${cmake_args[@]}"' in configure_guard
assert 'rm -f "$cmake_config_marker"' in configure_guard
assert 'LLVM_GIT_COMMIT=' in configure_guard
assert 'cmake --build "$LLVM_BUILD_DIR" --target distribution' in bootstrap

with tempfile.TemporaryDirectory(prefix='whp-llvm-cmake-reuse-') as scratch:
    fixture = Path(scratch)
    fake_bin = fixture / 'bin'
    fake_bin.mkdir()
    fake_cmake = fake_bin / 'cmake'
    fake_cmake.write_text(
        '#!/bin/sh\n'
        'if [ "$1" = "--version" ]; then echo "cmake version fixture"; exit 0; fi\n'
        'printf "configure\\n" >> "$WHP_CMAKE_TEST_LOG"\n'
        'mkdir -p "$LLVM_BUILD_DIR"\n'
        'printf "CMAKE_GENERATOR:INTERNAL=Ninja\\n" > "$LLVM_BUILD_DIR/CMakeCache.txt"\n'
        'touch "$LLVM_BUILD_DIR/build.ninja"\n'
        '[ "${WHP_CMAKE_TEST_FAIL:-0}" != 1 ]\n', encoding='utf-8'
    )
    fake_cmake.chmod(0o755)
    build_root = fixture / 'build'
    calls = fixture / 'calls'
    def check_reconfigure(args='-DTEST=1', *, force=False, fail=False,
                          prefix='', expected_calls=1, expected_ok=True):
        env = os.environ.copy()
        env['PATH'] = str(fake_bin) + os.pathsep + env.get('PATH', '')
        env['LLVM_BUILD_DIR'] = str(build_root)
        env['WHP_CMAKE_TEST_LOG'] = str(calls)
        env['PKG_CONFIG_PATH'] = prefix
        env['TOOLCHAIN_FORCE_REBUILD'] = '1' if force else '0'
        env['WHP_CMAKE_TEST_FAIL'] = '1' if fail else '0'
        probe = (
            'set -euo pipefail\n'
            'cmake_args=(-S test -B "$LLVM_BUILD_DIR" ' + args + ')\n'
            'bootstrap_cc_version="clang test"\n'
            'bootstrap_cxx_version="clang++ test"\n'
            'llvm_revision="fixture-revision"\n'
            'LLVM_SOURCE_DIR="/fixture/llvm"\n'
            + '# Reuse the generated Ninja graph when the invocation is unchanged.\n'
            + configure_guard
        )
        outcome = subprocess.run(
            ['bash', '-c', probe], env=env, capture_output=True, text=True
        )
        assert (outcome.returncode == 0) == expected_ok, outcome.stderr
        assert calls.read_text().count('configure\n') == expected_calls
    check_reconfigure(expected_calls=1)
    check_reconfigure(expected_calls=1)
    check_reconfigure('-DTEST=2', expected_calls=2)
    check_reconfigure('-DTEST=2', prefix='/changed/prefix', expected_calls=3)
    (build_root / 'build.ninja').unlink()
    check_reconfigure('-DTEST=2', prefix='/changed/prefix', expected_calls=4)
    check_reconfigure('-DTEST=2', prefix='/changed/prefix', force=True,
                      expected_calls=5)
    # A failing configure requires changed inputs; identical inputs must
    # correctly reuse the previous graph instead of invoking CMake.
    check_reconfigure('-DTEST=3', prefix='/changed/prefix', fail=True,
                      expected_calls=6, expected_ok=False)
    assert not (build_root / '.whp-native-llvm-cmake-config').exists()
    check_reconfigure('-DTEST=3', prefix='/changed/prefix',
                      expected_calls=7)
    # Even if marker text matches, an injected cross toolchain forces
    # another in-place configure rather than preserving a poisoned cache.
    (build_root / 'CMakeCache.txt').write_text(
        'CMAKE_GENERATOR:INTERNAL=Ninja\n'
        'CMAKE_TOOLCHAIN_FILE:FILEPATH=/cross/toolchain.cmake\n',
        encoding='utf-8',
    )
    check_reconfigure('-DTEST=3', prefix='/changed/prefix',
                      expected_calls=8)

# WHP Ninja reuses recorded compile/link durations to prioritize the critical
# path on subsequent LLVM builds. It is a scheduling-only switch, not an ABI
# or installed-compiler cache input. Preserve Ninja's job and link pools.
assert 'LLVM_NINJA_CRITICAL_PATH_TIMES="${NATIVE_LLVM_CRITICAL_PATH_TIMES:-1}"' in bootstrap
assert 'NATIVE_LLVM_CRITICAL_PATH_TIMES must be 0 or 1' in bootstrap
assert 'NINJA_CRITICAL_PATH_TIMES="$LLVM_NINJA_CRITICAL_PATH_TIMES" \\' in bootstrap
assert 'cmake --build "$LLVM_BUILD_DIR" --target distribution ' in bootstrap
marker_block = bootstrap.split('expected_marker="$(cat <<EOF', 1)[1].split('\nEOF\n)', 1)[0]
assert 'CRITICAL_PATH_TIMES' not in marker_block

# LLVM's large executable links retain a separate Ninja pool. Native macOS
# also limits compilation and TableGen work independently to reduce paging.
# Native LLVM pool overrides must stay independent of the ABI cache marker.
assert 'LLVM_COMPILE_JOBS="${NATIVE_LLVM_COMPILE_JOBS-}"' in bootstrap
assert 'LLVM_TABLEGEN_JOBS="${NATIVE_LLVM_TABLEGEN_JOBS-}"' in bootstrap
assert '[[ -n "${NATIVE_LLVM_COMPILE_JOBS+x}" ]] || LLVM_COMPILE_JOBS=2' in bootstrap
assert '[[ -n "${NATIVE_LLVM_TABLEGEN_JOBS+x}" ]] || LLVM_TABLEGEN_JOBS=1' in bootstrap
assert '"-DLLVM_PARALLEL_COMPILE_JOBS=$LLVM_COMPILE_JOBS"' in bootstrap
assert '"-DLLVM_PARALLEL_TABLEGEN_JOBS=$LLVM_TABLEGEN_JOBS"' in bootstrap
assert 'if [[ "$pool_jobs" == 0 ]]; then' in bootstrap

# Exercise the extracted pool policy without launching a native LLVM build.
# This checks macOS defaults, non-macOS behavior, explicit unlimits, and errors.
pool_policy = bootstrap.split(
    '# Cap expensive LLVM compile and TableGen work independently of -j and links.\n', 1
)[1].split('host_id="$host_tag-$host_platform"', 1)[0]
pool_probe = (
    'set -euo pipefail\n'
    'host_os="${WHP_HOST_OS}"\n'
    'LLVM_LINK_JOBS=2\n'
    'LLVM_COMPILE_JOBS="${NATIVE_LLVM_COMPILE_JOBS-}"\n'
    'LLVM_TABLEGEN_JOBS="${NATIVE_LLVM_TABLEGEN_JOBS-}"\n'
    + pool_policy
    + 'printf "%s|%s\\n" "${LLVM_COMPILE_JOBS:-unlimited}" '
      '"${LLVM_TABLEGEN_JOBS:-unlimited}"\n'
)
def check_native_pool(host, overrides, expected_output=None):
    env = os.environ.copy()
    for name in ('NATIVE_LLVM_COMPILE_JOBS', 'NATIVE_LLVM_TABLEGEN_JOBS'):
        env.pop(name, None)
    env['WHP_HOST_OS'] = host
    env.update(overrides)
    outcome = subprocess.run(
        ['bash', '-c', pool_probe], env=env, capture_output=True, text=True
    )
    if expected_output is None:
        assert outcome.returncode != 0 and 'must be 0 or a positive integer' in outcome.stderr
    else:
        assert outcome.returncode == 0, outcome.stderr
        assert outcome.stdout.strip() == expected_output

check_native_pool('macos', {}, '2|1')
check_native_pool('linux', {}, 'unlimited|unlimited')
check_native_pool('macos', {'NATIVE_LLVM_COMPILE_JOBS': '0', 'NATIVE_LLVM_TABLEGEN_JOBS': '0'}, 'unlimited|unlimited')
check_native_pool('macos', {'NATIVE_LLVM_COMPILE_JOBS': '4', 'NATIVE_LLVM_TABLEGEN_JOBS': '2'}, '4|2')
check_native_pool('macos', {'NATIVE_LLVM_COMPILE_JOBS': 'invalid'})
link_job_policies = (
    (bootstrap, 'NATIVE_LLVM_LINK_JOBS'),
    (i386_bootstrap, 'I386_LLVM_LINK_JOBS'),
    (powerpc_bootstrap, 'POWERPC_LLVM_LINK_JOBS'),
)
for llvm_bootstrap, override in link_job_policies:
    assert f'LLVM_LINK_JOBS="${{{override}:-2}}"' in llvm_bootstrap
    assert 'LLVM_PARALLEL_LINK_JOBS=$LLVM_LINK_JOBS' in llvm_bootstrap
    assert f'{override} must be a positive integer' in llvm_bootstrap

# A C++26 failure should not throw away buildable work that can be reused by
# the next incremental invocation. All LLVM bootstrap lanes use Ninja, so ask
# it to exhaust independent build edges before returning a non-zero status.
# This is not continue-on-success: the failed distribution still stops before
# install-distribution.
for llvm_bootstrap in (bootstrap, i386_bootstrap, powerpc_bootstrap):
    assert (
        'cmake --build "$LLVM_BUILD_DIR" --target distribution '
        '"${cmake_parallel_args[@]}" -- -k 0'
    ) in llvm_bootstrap

# Windows manifest merging is an opt-in native-host utility, independent of
# QEMU's Meson version.rc resource compiler and Apple's arm64e Mach-O ABI.
# No libxml2 or llvm-mt edge is allowed into the default LLVM distribution.
assert 'LLVM_WINDOWS_MANIFEST="${NATIVE_LLVM_WINDOWS_MANIFEST:-0}"' in bootstrap
assert 'NATIVE_LLVM_WINDOWS_MANIFEST must be 0 or 1' in bootstrap
assert 'llvm_enable_libxml2=OFF' in bootstrap
assert 'llvm_enable_libxml2=FORCE_ON' in bootstrap
assert 'llvm_distribution_components="${llvm_distribution_components};llvm-mt"' in bootstrap
assert '"-DLLVM_ENABLE_LIBXML2=$llvm_enable_libxml2"' in bootstrap
assert 'windows_manifest_tool_usable()' in bootstrap
assert 'windows_manifest_tool_usable "$prefix" || {' in bootstrap
assert '"$prefix/bin/llvm-mt" -manifest "$probe_dir/input.manifest"' in bootstrap
assert 'grep -Fq \'WHP.LLVM\'' in bootstrap

print('native LLVM wiring tests: passed')

# A native LLVM graph must not silently reuse CMake/Ninja state after an LLVM
# source change, even if timestamps do not trigger the RERUN_CMAKE rule.
assert 'WHP_CMAKE_CONFIG_SCHEMA=2' in bootstrap
assert 'LLVM_GIT_COMMIT=%q' in bootstrap
assert 'LLVM_SOURCE_DIR=%q' in bootstrap
assert 'unset CMAKE_TOOLCHAIN_FILE CMAKE_GENERATOR CMAKE_GENERATOR_PLATFORM' in bootstrap
assert 'unset LIBRARY_PATH COMPILER_PATH GCC_EXEC_PREFIX LD_PRELOAD' in bootstrap
assert 'unset DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH DYLD_INSERT_LIBRARIES' in bootstrap
for stage in ('EXE', 'SHARED', 'MODULE', 'STATIC'):
    assert f'-DCMAKE_{stage}_LINKER_FLAGS_RELEASE=' in bootstrap
assert '-DCMAKE_STATIC_LINKER_FLAGS=' in bootstrap
assert 'unset CMAKE_PROJECT_TOP_LEVEL_INCLUDES CMAKE_PROJECT_INCLUDE' in bootstrap
for entry in (
    '-UCMAKE_TOOLCHAIN_FILE', '-UCMAKE_SYSROOT',
    '-UCMAKE_FIND_ROOT_PATH', '-UCMAKE_PROJECT_TOP_LEVEL_INCLUDES',
    '-UCMAKE_C_COMPILER_TARGET', '-UCMAKE_CXX_COMPILER_TARGET',
    '-UCMAKE_ASM_COMPILER_TARGET', '-UCMAKE_C_COMPILER_EXTERNAL_TOOLCHAIN',
    '-UCMAKE_CXX_COMPILER_EXTERNAL_TOOLCHAIN',
):
    assert entry in bootstrap[bootstrap.index('cmake_args=('):], entry
assert 'rm -rf "$LLVM_BUILD_DIR"' not in bootstrap

# Execute the actual native LLVM CMake cache marker, without a full LLVM build.
identity_body = bootstrap.split('cmake_config_identity="$(', 1)[1].split(
    '\n)"\n', 1
)[0]


def native_cmake_identity(revision: str, source_dir: str) -> str:
    script = (
        'set -euo pipefail\n'
        'llvm_revision="$1"\n'
        'LLVM_SOURCE_DIR="$2"\n'
        'bootstrap_cc_version=seed-cc\n'
        'bootstrap_cxx_version=seed-cxx\n'
        'cmake_args=(-S /test/llvm -B /test/build -G Ninja)\n'
        'cmake_config_identity="$(\n' + identity_body + '\n)"\n'
        'printf "%s\n" "$cmake_config_identity"\n'
    )
    return subprocess.run(
        ['bash', '-c', script, 'native-llvm-cmake-test', revision, source_dir],
        text=True, capture_output=True, check=True,
    ).stdout


baseline_identity = native_cmake_identity('a' * 40, '/checkout/llvm-project')
assert baseline_identity != native_cmake_identity(
    'b' * 40, '/checkout/llvm-project'
), 'LLVM gitlink drift reused the native CMake graph'
assert baseline_identity != native_cmake_identity(
    'a' * 40, '/different/llvm-project'
), 'LLVM source path drift reused the native CMake graph'

# Run the exact host CMake environment filter with adversarial toolchain and
# generator settings. Host library discovery prefixes must remain unchanged.
cmake_env_isolation = bootstrap.split(
    '# WHP_NATIVE_LLVM_CMAKE_ENV_BEGIN\n', 1
)[1].split('# WHP_NATIVE_LLVM_CMAKE_ENV_END', 1)[0]
poisoned_cmake_env = {
    **os.environ,
    'CMAKE_TOOLCHAIN_FILE': '/cross/target.cmake',
    'CMAKE_GENERATOR': 'Unix Makefiles',
    'CMAKE_GENERATOR_PLATFORM': 'arm64',
    'CMAKE_PROJECT_TOP_LEVEL_INCLUDES': '/cross/inject.cmake',
    'PKG_CONFIG_SYSROOT_DIR': '/cross/sysroot',
    'PKG_CONFIG_LIBDIR': '/cross/pkgconfig',
    'CMAKE_PREFIX_PATH': '/native/deps',
    'PKG_CONFIG_PATH': '/native/pkgconfig',
}
filtered = subprocess.run(
    [
        'bash', '-c', 'set -euo pipefail\n' + cmake_env_isolation +
        '\nprintf "%s|%s|%s|%s" "${CMAKE_TOOLCHAIN_FILE-unset}" '
        '"${CMAKE_GENERATOR-unset}" "${CMAKE_PREFIX_PATH-unset}" '
        '"${PKG_CONFIG_PATH-unset}"\n',
    ],
    env=poisoned_cmake_env, text=True, capture_output=True, check=True,
)
assert filtered.stdout == 'unset|unset|/native/deps|/native/pkgconfig'

# A matching marker must not hide an injected cross-toolchain cache entry.
cache_guard = bootstrap.split(
    '# WHP_NATIVE_LLVM_CMAKE_CACHE_GUARD_BEGIN\n', 1
)[1].split('# WHP_NATIVE_LLVM_CMAKE_CACHE_GUARD_END', 1)[0]
assert 'native_llvm_cmake_cache_clean; then' in bootstrap
with tempfile.TemporaryDirectory(prefix='whp-llvm-cmake-guard-') as td:
    cache = Path(td) / 'CMakeCache.txt'

    def cache_clean() -> bool:
        result = subprocess.run(
            ['bash', '-c',
             'set -euo pipefail\nLLVM_BUILD_DIR="$1"\n' +
             cache_guard + '\nnative_llvm_cmake_cache_clean',
             'whp-llvm-cmake-guard', td],
            text=True, capture_output=True, check=False,
        )
        return result.returncode == 0

    cache.write_text('CMAKE_GENERATOR:INTERNAL=Ninja\n', encoding='utf-8')
    assert cache_clean(), 'valid native Ninja graph was rejected'
    cache.write_text(
        'CMAKE_GENERATOR:INTERNAL=Ninja\n'
        'CMAKE_TOOLCHAIN_FILE:FILEPATH=/foreign/target.cmake\n',
        encoding='utf-8',
    )
    assert not cache_clean(), 'foreign toolchain cache entry was reused'
    cache.write_text(
        'CMAKE_GENERATOR:INTERNAL=Unix Makefiles\n', encoding='utf-8',
    )
    assert not cache_clean(), 'non-Ninja generator cache was reused'
    for stale in (
        'CMAKE_EXE_LINKER_FLAGS_RELEASE:STRING=-arch x86_64',
        'CMAKE_SHARED_LINKER_FLAGS_RELEASE:STRING=-Wl,-rpath,/cross/lib',
        'CMAKE_MODULE_LINKER_FLAGS_RELEASE:STRING=-fsanitize=address',
        'CMAKE_STATIC_LINKER_FLAGS_RELEASE:STRING=-arch x86_64',
        'CMAKE_EXE_LINKER_FLAGS:STRING=-Wl,-rpath,/target/lib',
        'CMAKE_SHARED_LINKER_FLAGS:STRING=-fuse-ld=lld',
        'CMAKE_STATIC_LINKER_FLAGS:STRING=--plugin=/foreign/lto.so',
        'CMAKE_C_COMPILER_TARGET:STRING=x86_64-unknown-linux-gnu',
        'CMAKE_CXX_COMPILER_EXTERNAL_TOOLCHAIN:PATH=/foreign/cross',
    ):
        cache.write_text(
            'CMAKE_GENERATOR:INTERNAL=Ninja\n' + stale + '\n',
            encoding='utf-8',
        )
        assert not cache_clean(), f'poisoned native LLVM cache reused: {stale}'
    cache.write_text(
        'CMAKE_GENERATOR:INTERNAL=Ninja\n'
        'CMAKE_EXE_LINKER_FLAGS:STRING=\n'
        'CMAKE_SHARED_LINKER_FLAGS:STRING=\n'
        'CMAKE_MODULE_LINKER_FLAGS:STRING=\n'
        'CMAKE_STATIC_LINKER_FLAGS:STRING=\n'
        'CMAKE_EXE_LINKER_FLAGS_RELEASE:STRING=\n',
        encoding='utf-8',
    )
    assert cache_clean(), 'a sanitized native linker cache was rejected'

# Prove shortcut precedence with the actual native seed-selection fragment.
# A prevalidated CC_FOR_BUILD is never re-probed; explicit LLVM overrides
# are admitted by cc.sh/cxx.sh *before* the default compiler is consulted.
native_seed_selection = bootstrap.split(
    '# WHP_NATIVE_LLVM_SEED_SELECTION_BEGIN\n', 1
)[1].split('# WHP_NATIVE_LLVM_SEED_SELECTION_END', 1)[0]
with tempfile.TemporaryDirectory(prefix='whp-llvm-seed-choice-') as td:
    root = Path(td)
    log = root / 'calls'
    for lang, adapter, override in (
        ('c', 'cc.sh', 'WHP_CC_SEED'),
        ('cxx', 'cxx.sh', 'WHP_CXX_SEED'),
    ):
        script = root / adapter
        command = '--print-cc' if lang == 'c' else '--print-cxx'
        script.write_text(
            '#!/bin/sh\n'
            'printf "%s\\n" "' + adapter + '" >> "$WHP_LLVM_TEST_SEED_CALLS"\n'
            '[ "$1" = "' + command + '" ] || exit 81\n'
            'case "$' + override + '" in\n'
            '  FAIL) exit 82 ;;\n'
            '  "") printf "/mock/default-' + lang + '\\n" ;;\n'
            '  *) printf "/mock/%s\\n" "$' + override + '" ;;\n'
            'esac\n', encoding='utf-8',
        )
        script.chmod(0o755)

    def selected(cc='', cxx='', override_cc='', override_cxx=''):
        log.unlink(missing_ok=True)
        env = dict(os.environ, SOURCE_DIR=str(root),
                   WHP_LLVM_TEST_SEED_CALLS=str(log),
                   CC_FOR_BUILD=cc, CXX_FOR_BUILD=cxx,
                   NATIVE_LLVM_BOOTSTRAP_CC=override_cc,
                   NATIVE_LLVM_BOOTSTRAP_CXX=override_cxx)
        result = subprocess.run(
            ['bash', '-c', 'set -euo pipefail\n' +
             native_seed_selection +
             '\nprintf "%s|%s\\n" "$bootstrap_cc" "$bootstrap_cxx"\n'],
            env=env, text=True, capture_output=True, check=False,
        )
        calls = log.read_text().splitlines() if log.exists() else []
        return result, calls

    chosen, calls = selected(cc='/known/cc', cxx='/known/cxx')
    assert chosen.returncode == 0, chosen.stderr
    assert chosen.stdout == '/known/cc|/known/cxx\n'
    assert not calls, 'LLVM re-ran the already admitted native C/C++ probes'
    chosen, calls = selected(cc='/known/cc')
    assert chosen.returncode == 0, chosen.stderr
    assert chosen.stdout == '/known/cc|/mock/default-cxx\n'
    assert calls == ['cxx.sh'], calls
    chosen, calls = selected()
    assert chosen.returncode == 0, chosen.stderr
    assert chosen.stdout == '/mock/default-c|/mock/default-cxx\n'
    assert calls == ['cc.sh', 'cxx.sh'], calls
    chosen, calls = selected(cc='/known/cc', cxx='/known/cxx',
                             override_cc='explicit-cc',
                             override_cxx='explicit-cxx')
    assert chosen.returncode == 0, chosen.stderr
    assert chosen.stdout == '/mock/explicit-cc|/mock/explicit-cxx\n'
    assert calls == ['cc.sh', 'cxx.sh'], calls
    chosen, calls = selected(cc='/known/cc', cxx='/known/cxx',
                             override_cc='FAIL')
    assert chosen.returncode != 0
    assert calls == ['cc.sh'], 'bad C override fell through to default'
    chosen, calls = selected(cc='/known/cc', cxx='/known/cxx',
                             override_cxx='FAIL')
    assert chosen.returncode != 0
    assert calls == ['cxx.sh'], 'bad C++ override fell through to default'

print('native LLVM compiler-role shortcut regressions: passed')
