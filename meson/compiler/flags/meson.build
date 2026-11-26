if (cc.sizeof('void *') < 8) and (have_system or have_user)
  error('QEMU emulator requires a 64-bit CPU host architecture. Only tools may be built for 32-bit.')
endif

foreach lang : all_languages
  language_compiler = meson.get_compiler(lang, native: false)
  if language_compiler.get_id() == 'gcc' and language_compiler.version().version_compare('>=10.4')
    # ok
  elif language_compiler.get_id() == 'clang' and language_compiler.compiles('''
      #ifdef __apple_build_version__
      # if __clang_major__ < 15 || (__clang_major__ == 15 && __clang_minor__ < 0)
      #  error You need at least XCode Clang v15.0 to compile QEMU
      # endif
      #else
      # if __clang_major__ < 10 || (__clang_major__ == 10 && __clang_minor__ < 0)
      #  error You need at least Clang v10.0 to compile QEMU
      # endif
      #endif''')
    # ok
  elif language_compiler.get_id() == 'emscripten'
    # ok
  else
    error('Unsupported @0@ compiler @1@ @2@: QEMU requires GCC 10.4, Clang 10.0, or Apple Clang 15.0 or newer'.format(lang, language_compiler.get_id(), language_compiler.version()))
  endif
  # Windows plugins require lld when using Clang. Check each enabled language.
  if host_os == 'windows' and language_compiler.get_id() == 'clang' and language_compiler.get_linker_id() != 'ld.lld'
    error('The Windows @0@ Clang compiler requires lld; use the MSYS2 clang64 or clangarm64 environment'.format(lang))
  endif
endforeach

# default flags for all hosts
# We use -fwrapv to tell the compiler that we require a C dialect where
# left shift of signed integers is well defined and has the expected
# 2s-complement style results. (Both clang and gcc agree that it
# provides these semantics.)

qemu_common_flags = [
  '-D_GNU_SOURCE', '-D_FILE_OFFSET_BITS=64', '-D_LARGEFILE_SOURCE',
  '-fno-strict-aliasing', '-fno-common', '-fwrapv' ]
qemu_cflags = []
qemu_ldflags = []

if host_os == 'sunos'
  # needed for CMSG_ macros in sys/socket.h
  qemu_common_flags += '-D_XOPEN_SOURCE=600'
  # needed for TIOCWIN* defines in termios.h
  qemu_common_flags += '-D__EXTENSIONS__'
elif host_os == 'haiku'
  qemu_common_flags += ['-DB_USE_POSITIVE_POSIX_ERRORS', '-D_BSD_SOURCE', '-fPIC']
endif

# Choose instruction set (currently x86-only)

qemu_isa_flags = []

# Pick x86-64 baseline version
if host_arch == 'x86_64'
  if get_option('x86_version') == '0'
    error('x86_64-v1 required for x86-64 hosts')
  endif

  # add flags for individual instruction set extensions
  if get_option('x86_version') >= '1'
    # present on basically all processors but technically not part of
    # x86-64-v1, so only include -mneeded for x86-64 version 2 and above
    qemu_isa_flags += ['-mcx16']
  endif
  if get_option('x86_version') >= '2'
    qemu_isa_flags += ['-mpopcnt']
    qemu_isa_flags += cc.get_supported_arguments('-mneeded')
  endif
  if get_option('x86_version') >= '3'
    # GCC's -mabm enables LZCNT and POPCNT, but Clang uses explicit flags.
    # POPCNT is already required by x86-64-v2; enable LZCNT here.
    qemu_isa_flags += ['-mmovbe', '-mlzcnt', '-mbmi', '-mbmi2', '-mfma', '-mf16c']
  endif

  # add required vector instruction set (each level implies those below)
  if get_option('x86_version') == '1'
    qemu_isa_flags += ['-msse2']
  elif get_option('x86_version') == '2'
    qemu_isa_flags += ['-msse4.2']
  elif get_option('x86_version') == '3'
    qemu_isa_flags += ['-mavx2']
  elif get_option('x86_version') == '4'
    qemu_isa_flags += ['-mavx512f', '-mavx512bw', '-mavx512cd', '-mavx512dq', '-mavx512vl']
  endif
endif

# GCC >= 16 automatically tries to link libatomic for all programs.
#
# QEMU explicitly does NOT want to use libatomic for int128 types.
#
# Later checks assume we won't get atomic ops for int128 without
# explicitly asking for -latomic, so we must disable GCC's new
# automatic linking with the new -fno-link-libatomic flag.
#
# When not building the emulators, but qemu helper tools only
# (e.g. on 32-bit hosts), libatomic is sometimes required and
# thus acceptable.
if (have_system or have_user)
  # Keep feature probes and final executable links under the same policy.
  qemu_isa_flags += cc.get_supported_arguments('-fno-link-libatomic')
  qemu_ldflags += cc.get_supported_link_arguments('-fno-link-libatomic')
else
  qemu_ldflags += cc.get_supported_link_arguments('-latomic')
endif

qemu_common_flags = qemu_isa_flags + qemu_common_flags

if get_option('prefer_static')
  qemu_ldflags += get_option('b_pie') ? '-static-pie' : '-static'
endif

# Meson currently only handles pie as a boolean for now, so if the user
# has explicitly disabled PIE we need to extend our cflags.
#
# -no-pie is supposedly a linker flag that has no effect on the compiler
# command line, but some distros, that didn't quite know what they were
# doing, made local changes to gcc's specs file that turned it into
# a compiler command-line flag.
#
# What about linker flags?  For a static build, no PIE is implied by -static
# which we added above (and if it's not because of the same specs patching,
# there's nothing we can do: compilation will fail, report a bug to your
# distro and do not use --disable-pie in the meanwhile).  For dynamic linking,
# instead, we can't add -no-pie because it overrides -shared: the linker then
# tries to build an executable instead of a shared library and fails.  So
# don't add -no-pie anywhere and cross fingers. :(
#
# Emscripten doesn't support -no-pie but meson can't catch the compiler
# warning. So explicitly omit the flag for Emscripten.
if not get_option('b_pie') and host_os != 'emscripten'
  qemu_common_flags += cc.get_supported_arguments('-fno-pie', '-no-pie')
endif

if not get_option('stack_protector').disabled()
  stack_protector_probe = '''
    int main(int argc, char *argv[])
    {
      char arr[64], *p = arr, *c = argv[argc - 1];
      while (*c) {
          *p++ = *c++;
      }
      return 0;
    }'''
  have_stack_protector = false
  foreach arg : ['-fstack-protector-strong', '-fstack-protector-all']
    # We need to check both a compile and a link, since some compiler
    # setups fail only on a .c->.o compile and some only at link time
    if cc.compiles(stack_protector_probe, args: ['-Werror', arg]) and \
       cc.links(stack_protector_probe, args: ['-Werror', arg])
      have_stack_protector = true
      qemu_cflags += arg
      qemu_ldflags += arg
      break
    endif
  endforeach
  get_option('stack_protector') \
    .require(have_stack_protector, error_message: 'Stack protector not supported')
endif

coroutine_backend = get_option('coroutine_backend')
ucontext_probe = '''
  #include <ucontext.h>
  #ifdef __stub_makecontext
  #error Ignoring glibc stub makecontext which will always fail
  #endif
  int main(void) { makecontext(0, 0, 0); return 0; }'''

# On Windows the only valid backend is the Windows specific one.
# For POSIX prefer ucontext, but it's not always possible. The fallback
# is sigcontext.
supported_backends = []
if host_os == 'windows'
  supported_backends += ['windows']
elif host_os == 'emscripten'
  supported_backends += ['wasm']
else
  if host_os != 'darwin' and cc.links(ucontext_probe)
    supported_backends += ['ucontext']
  endif
  supported_backends += ['sigaltstack']
endif

if coroutine_backend == 'auto'
  coroutine_backend = supported_backends[0]
elif coroutine_backend not in supported_backends
  error('"@0@" backend requested but not available.  Available backends: @1@' \
        .format(coroutine_backend, ', '.join(supported_backends)))
endif

# Compiles if SafeStack *not* enabled
safe_stack_probe = '''
  int main(void)
  {
  #if defined(__has_feature)
  #if __has_feature(safe_stack)
  #error SafeStack Enabled
  #endif
  #endif
      return 0;
  }'''
if get_option('safe_stack') != not cc.compiles(safe_stack_probe)
  safe_stack_arg = get_option('safe_stack') ? '-fsanitize=safe-stack' : '-fno-sanitize=safe-stack'
  if get_option('safe_stack') != not cc.compiles(safe_stack_probe, args: safe_stack_arg)
    error(get_option('safe_stack') \
          ? 'SafeStack not supported by your compiler' \
          : 'Cannot disable SafeStack')
  endif
  qemu_cflags += safe_stack_arg
  qemu_ldflags += safe_stack_arg
endif
if get_option('safe_stack') and coroutine_backend != 'ucontext'
  error('SafeStack is only supported with the ucontext coroutine backend')
endif

if get_option('asan')
  if cc.has_argument('-fsanitize=address')
    qemu_cflags = ['-fsanitize=address'] + qemu_cflags
    qemu_ldflags = ['-fsanitize=address'] + qemu_ldflags
    # Ensure complete stack traces for LSan suppressions to match correctly.
    qemu_cflags += ['-fno-omit-frame-pointer']
  else
    error('Your compiler does not support -fsanitize=address')
  endif
endif

if get_option('ubsan')
  # Detect static linking issue with ubsan:
  # https://gcc.gnu.org/bugzilla/show_bug.cgi?id=84285
  if cc.links('int main(int argc, char **argv) { return argc + 1; }',
              args: [qemu_ldflags, '-fsanitize=undefined'])
    qemu_cflags += ['-fsanitize=undefined']
    qemu_ldflags += ['-fsanitize=undefined']

    # Suppress undefined behaviour from function call to mismatched type.
    # In addition, tcg prologue does not emit function type prefix
    # required by function call sanitizer.
    if cc.has_argument('-fno-sanitize=function')
      qemu_cflags += ['-fno-sanitize=function']
    endif
  else
    error('Your compiler does not support -fsanitize=undefined')
  endif
endif

# Thread sanitizer is, for now, much noisier than the other sanitizers;
# keep it separate until that is not the case.
if get_option('tsan')
  if get_option('asan') or get_option('ubsan')
    error('TSAN is not supported with other sanitizers')
  endif
  if not cc.has_function('__tsan_create_fiber',
                         args: '-fsanitize=thread',
                         prefix: '#include <sanitizer/tsan_interface.h>')
    error('Cannot enable TSAN due to missing fiber annotation interface')
  endif
  tsan_warn_suppress = []
  # gcc (>=11) will report constructions not supported by tsan:
  # "error: ‘atomic_thread_fence’ is not supported with ‘-fsanitize=thread’"
  # https://gcc.gnu.org/gcc-11/changes.html
  # However, clang does not support this warning and this triggers an error.
  if cc.has_argument('-Wno-tsan')
    tsan_warn_suppress = ['-Wno-tsan']
  endif
  qemu_cflags = ['-fsanitize=thread'] + tsan_warn_suppress + qemu_cflags
  qemu_ldflags = ['-fsanitize=thread'] + qemu_ldflags
endif

# Detect support for PT_GNU_RELRO + DT_BIND_NOW.
# The combination is known as "full relro", because .got.plt is read-only too.
qemu_ldflags += cc.get_supported_link_arguments('-Wl,-z,relro', '-Wl,-z,now')

if host_os == 'windows'
  qemu_ldflags += cc.get_supported_link_arguments('-Wl,--no-seh', '-Wl,--nxcompat')
  qemu_ldflags += cc.get_supported_link_arguments('-Wl,--dynamicbase', '-Wl,--high-entropy-va')
endif
