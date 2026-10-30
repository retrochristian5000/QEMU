# The initrd stress workload is a Linux guest fixture requiring a fully
# static binary. Darwin has no static system iconv/GLib dependency and must
# not probe/link this Linux-only helper during native macOS configuration.
if host_os == 'linux'
  sysprof = dependency('sysprof-capture-4', method: 'pkg-config', required: false)
  glib_static = dependency('glib-2.0', version: glib_req_ver, required: false,
                           method: 'pkg-config', static: true)
  
  stress = executable(
    'stress',
    files('stress.c'),
    dependencies: [glib_static, sysprof],
    link_args: ['-static'],
    build_by_default: false,
  )
  
  custom_target(
    'initrd-stress.img',
    output: 'initrd-stress.img',
    input: stress,
    command: [find_program('initrd-stress.sh'), '@OUTPUT@', '@INPUT@']
  )
endif
