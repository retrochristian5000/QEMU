cc = meson.get_compiler('c', native: false)
all_languages = ['c']
enable_cpp = host_os == 'windows' or get_option('plugins')
if enable_cpp and add_languages('cpp', required: false, native: false)
  all_languages += ['cpp']
  cxx = meson.get_compiler('cpp')
endif
if host_os == 'darwin' and \
   add_languages('objc', required: true, native: false)
  all_languages += ['objc']
  objc = meson.get_compiler('objc', native: false)
  if not cc.compiles('''
    #ifdef __OBJC__
    #error C compiler is using Objective-C mode
    #endif
    int main(void) { return 0; }
  ''', name: 'Darwin C language mode')
    error('The Darwin C compiler must compile C sources in C mode')
  endif
  if not objc.compiles('''
    #ifndef __OBJC__
    #error Objective-C language mode is not active
    #endif
    @class NSObject;
    int main(void) { return 0; }
  ''', name: 'Darwin Objective-C language mode')
    error('The Darwin Objective-C compiler must compile Objective-C sources in Objective-C mode')
  endif
  if cc.sizeof('void *') != objc.sizeof('void *')
    error('The Darwin C and Objective-C compilers disagree on pointer size')
  endif
endif

have_rust = add_languages('rust', native: false,
    required: get_option('rust').disable_auto_if(not have_system))
have_rust = have_rust and add_languages('rust', native: true,
    required: get_option('rust').disable_auto_if(not have_system))
if have_rust
  rustc = meson.get_compiler('rust')
  if rustc.version().version_compare('<1.83.0')
    if get_option('rust').enabled()
      error('rustc version ' + rustc.version() + ' is unsupported. Please upgrade to at least 1.83.0')
    else
      warning('rustc version ' + rustc.version() + ' is unsupported, disabling Rust compilation.')
      message('Please upgrade to at least 1.83.0 to use Rust.')
      have_rust = false
    endif
  endif
endif

if have_rust
  rustdoc = find_program('rustdoc', required: get_option('rust'))
  bindgen = find_program('bindgen', required: get_option('rust'))
  if not bindgen.found() or bindgen.version().version_compare('<0.60.0')
    if get_option('rust').enabled()
      error('bindgen version ' + bindgen.version() + ' is unsupported. You can install a new version with "cargo install --locked bindgen-cli"')
    else
      if bindgen.found()
        warning('bindgen version ' + bindgen.version() + ' is unsupported, disabling Rust compilation.')
      else
        warning('bindgen not found, disabling Rust compilation.')
      endif
      message('To use Rust you can install a new version with "cargo install bindgen-cli"')
      have_rust = false
    endif
  endif
endif

if have_rust
  rustc_args = [find_program(meson.project_source_root() / 'scripts/rust/rustc_args.py'),
    '--rustc-version', rustc.version(),
    '--workspace', meson.project_source_root() / 'rust']
  rustfmt = find_program('rustfmt', required: false)

  rustc_lint_args = run_command(rustc_args, '--lints',
     capture: true, check: true).stdout().strip().splitlines()
  if get_option('strict_rust_lints')
    rustc_lint_args += ['-Dwarnings', '-Funknown_lints']
  endif

  add_project_arguments(rustc_lint_args + ['--cfg', 'MESON'],
      native: false, language: 'rust')
  add_project_arguments(rustc_lint_args + ['--cfg', 'MESON'],
      native: true, language: 'rust')
endif
