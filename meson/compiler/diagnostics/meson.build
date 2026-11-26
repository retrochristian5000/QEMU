if get_option('cfi')
  cfi_flags=[]
  # Check for dependency on LTO
  if not get_option('b_lto')
    error('Selected Control-Flow Integrity but LTO is disabled')
  endif
  if enable_modules
    error('Selected Control-Flow Integrity is not compatible with modules')
  endif
  # Check for cfi flags. CFI requires LTO so we can't use
  # get_supported_arguments, but need a more complex "compiles" which allows
  # custom arguments
  if cc.compiles('int main () { return 0; }', name: '-fsanitize=cfi-icall',
                 args: ['-flto', '-fsanitize=cfi-icall'] )
    cfi_flags += '-fsanitize=cfi-icall'
  else
    error('-fsanitize=cfi-icall is not supported by the compiler')
  endif
  if cc.compiles('int main () { return 0; }',
                 name: '-fsanitize-cfi-icall-generalize-pointers',
                 args: ['-flto', '-fsanitize=cfi-icall',
                        '-fsanitize-cfi-icall-generalize-pointers'] )
    cfi_flags += '-fsanitize-cfi-icall-generalize-pointers'
  else
    error('-fsanitize-cfi-icall-generalize-pointers is not supported by the compiler')
  endif
  if get_option('cfi_debug')
    if get_option('safe_stack')
      error('cfi_debug is not compatible with safe_stack')
    endif
    if cc.compiles('int main () { return 0; }',
                   name: '-fno-sanitize-trap=cfi-icall',
                   args: ['-flto', '-fsanitize=cfi-icall',
                          '-fno-sanitize-trap=cfi-icall'] )
      cfi_flags += '-fno-sanitize-trap=cfi-icall'
    else
      error('-fno-sanitize-trap=cfi-icall is not supported by the compiler')
    endif
  endif
  add_global_arguments(cfi_flags, native: false, language: all_languages)
  add_global_link_arguments(cfi_flags, native: false, language: all_languages)
endif

# Check further flags that make QEMU more robust against malicious parties

hardening_flags = [
    # Initialize all stack variables to zero. This makes
    # it harder to take advantage of uninitialized stack
    # data to drive exploits
    '-ftrivial-auto-var-init=zero',
    # Ensure GCC zero-initializes padding bits and trailing fields in
    # unions. This avoids potentially leaking host data into the guest
    # when we init a struct and copy it into guest memory.  GCC prior
    # to GCC 15 and clang don't have this, but they zero the padding
    # and trailing portions of a union by default.
    '-fzero-init-padding-bits=all',
]

# Zero out registers used during a function call
# upon its return. This makes it harder to assemble
# ROP gadgets into something usable
#
# NB: Clang 17 is broken and SEGVs
# https://github.com/llvm/llvm-project/issues/75168
if cc.compiles('extern struct { void (*cb)(void); } s; void f(void) { s.cb(); }',
               name: '-fzero-call-used-regs=used-gpr',
               args: ['-O2', '-fzero-call-used-regs=used-gpr'])
    hardening_flags += '-fzero-call-used-regs=used-gpr'
endif

qemu_common_flags += hardening_flags

# Collect warning flags we want to set, sorted alphabetically
warn_flags = [
  # First enable interesting warnings
  '-Wempty-body',
  '-Wendif-labels',
  '-Wexpansion-to-defined',
  '-Wformat-overflow=2',
  '-Wformat-security',
  '-Wformat-y2k',
  '-Wignored-qualifiers',
  '-Wimplicit-fallthrough=2',
  '-Winit-self',
  '-Wmissing-format-attribute',
  '-Wmissing-prototypes',
  '-Wnested-externs',
  '-Wold-style-declaration',
  '-Wold-style-definition',
  '-Wredundant-decls',
  '-Wshadow=local',
  '-Wstrict-prototypes',
  '-Wtype-limits',
  '-Wundef',
  '-Wvla',
  '-Wwrite-strings',

  # Then disable some undesirable warnings
  '-Wno-gnu-variable-sized-type-not-at-end',
  '-Wno-initializer-overrides',
  '-Wno-missing-include-dirs',
  '-Wno-psabi',
  '-Wno-shift-negative-value',
  '-Wno-string-plus-int',
  '-Wno-tautological-type-limit-compare',
  '-Wno-typedef-redefinition',
]

if host_os != 'darwin'
  tsa_has_cleanup = cc.compiles('''
    struct __attribute__((capability("mutex"))) mutex {};
    void lock(struct mutex *m) __attribute__((acquire_capability(m)));
    void unlock(struct mutex *m) __attribute__((release_capability(m)));

    void test(void) {
      struct mutex __attribute__((cleanup(unlock))) m;
      lock(&m);
    }
  ''', args: ['-Wthread-safety', '-Werror'])
  if tsa_has_cleanup
    warn_flags += ['-Wthread-safety']
  endif
endif

# Set up C++ compiler flags
qemu_cxxflags = []
if 'cpp' in all_languages
  qemu_cxxflags = ['-D__STDC_LIMIT_MACROS', '-D__STDC_CONSTANT_MACROS', '-D__STDC_FORMAT_MACROS'] + qemu_cflags
endif

# Darwin's os/object.h requires compiler-specific policy for C-family sources.
# Do not propagate a GCC workaround into Objective-C or a Clang C++ compiler.
if host_os == 'darwin'
  if cc.get_id() == 'gcc'
    qemu_cflags += '-DOS_OBJECT_USE_OBJC=0'
  endif
  if 'cpp' in all_languages and cxx.get_id() == 'gcc'
    qemu_cxxflags += '-DOS_OBJECT_USE_OBJC=0'
  endif
endif

add_project_arguments(cc.get_supported_arguments(qemu_common_flags + qemu_cflags + warn_flags),
                      native: false, language: 'c')
add_global_link_arguments(qemu_ldflags, native: false, language: all_languages)
if have_rust
  add_global_link_arguments(qemu_ldflags, native: false, language: 'rust')
endif

if 'cpp' in all_languages
  add_project_arguments(cxx.get_supported_arguments(qemu_common_flags + qemu_cxxflags),
                        native: false, language: 'cpp')
  add_project_arguments(cxx.get_supported_arguments(warn_flags), native: false, language: 'cpp')
endif
if 'objc' in all_languages
  # macOS Cocoa sources must receive ASan instrumentation as well as C/C++.
  # Otherwise an ASan build silently leaves part of the host uninstrumented.
  objc_asan_flags = []
  if get_option('asan')
    if not objc.has_argument('-fsanitize=address') or not objc.links('''
      #ifndef __OBJC__
      #error Objective-C language mode is not active
      #endif
      int main(void) { return 0; }
    ''', args: '-fsanitize=address', name: 'Objective-C AddressSanitizer runtime')
      error('The Objective-C compiler cannot compile and link with AddressSanitizer')
    endif
    objc_asan_flags = ['-fsanitize=address', '-fno-omit-frame-pointer']
  endif
  qemu_objcflags = objc.get_supported_arguments(qemu_common_flags + objc_asan_flags + warn_flags)
  add_project_arguments(qemu_objcflags, native: false, language: 'objc')
endif
