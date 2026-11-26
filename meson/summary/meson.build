#########################
# Configuration summary #
#########################

# Build environment
summary_info = {}
summary_info += {'Build directory':   meson.project_build_root()}
summary_info += {'Source path':       meson.project_source_root()}
summary_info += {'Download dependencies': get_option('wrap_mode') != 'nodownload'}
summary(summary_info, bool_yn: true, section: 'Build environment')

# Directories
summary_info = {}
summary_info += {'Install prefix':    get_option('prefix')}
summary_info += {'BIOS directory':    qemu_datadir}
pathsep = host_os == 'windows' ? ';' : ':'
summary_info += {'firmware path':     pathsep.join(get_option('qemu_firmwarepath'))}
summary_info += {'binary directory':  get_option('prefix') / get_option('bindir')}
summary_info += {'library directory': get_option('prefix') / get_option('libdir')}
summary_info += {'module directory':  qemu_moddir}
summary_info += {'libexec directory': get_option('prefix') / get_option('libexecdir')}
summary_info += {'include directory': get_option('prefix') / get_option('includedir')}
summary_info += {'config directory':  get_option('prefix') / get_option('sysconfdir')}
if host_os != 'windows'
  summary_info += {'local state directory': get_option('prefix') / get_option('localstatedir')}
  summary_info += {'Manual directory':      get_option('prefix') / get_option('mandir')}
else
  summary_info += {'local state directory': 'queried at runtime'}
endif
summary_info += {'Doc directory':     get_option('prefix') / get_option('docdir')}
summary(summary_info, bool_yn: true, section: 'Directories')

# Host binaries
summary_info = {}
summary_info += {'python':            '@0@ (version: @1@)'.format(python.full_path(), python.language_version())}
summary_info += {'sphinx-build':      sphinx_build}

# FIXME: the [binaries] section of machine files, which can be probed
# with find_program(), would be great for passing gdb and genisoimage
# paths from configure to Meson.  However, there seems to be no way to
# hide a program (for example if gdb is too old).
if config_host.has_key('GDB')
  summary_info += {'gdb':             config_host['GDB']}
endif
summary_info += {'iasl':              iasl}
summary_info += {'genisoimage':       config_host['GENISOIMAGE']}
if host_os == 'windows' and have_ga
  summary_info += {'wixl':            wixl}
endif
if slirp.found() and have_system
  summary_info += {'smbd':            have_slirp_smbd ? smbd_path : false}
endif
summary(summary_info, bool_yn: true, section: 'Host binaries')

# Configurable features
summary_info = {}
summary_info += {'Documentation':     build_docs}
summary_info += {'system-mode emulation': have_system}
summary_info += {'user-mode emulation': have_user}
summary_info += {'block layer':       have_block}
summary_info += {'Install blobs':     get_option('install_blobs')}
summary_info += {'module support':    enable_modules}
if enable_modules
  summary_info += {'alternative module path': get_option('module_upgrades')}
endif
summary_info += {'fuzzing support':   get_option('fuzzing')}
if have_system
  summary_info += {'Audio drivers':     ' '.join(audio_drivers_selected)}
endif
summary_info += {'Trace backends':    ','.join(get_option('trace_backends'))}
if 'simple' in get_option('trace_backends')
  summary_info += {'Trace output file': get_option('trace_file') + '-<pid>'}
endif
summary_info += {'QOM debugging':     get_option('qom_cast_debug')}
summary_info += {'Relocatable install': get_option('relocatable')}
summary_info += {'vhost-kernel support': have_vhost_kernel}
summary_info += {'vhost-net support': have_vhost_net}
summary_info += {'vhost-user support': have_vhost_user}
summary_info += {'vhost-user-crypto support': have_vhost_user_crypto}
summary_info += {'vhost-user-blk server support': have_vhost_user_blk_server}
summary_info += {'vhost-vdpa support': have_vhost_vdpa}
summary_info += {'build guest agent': have_ga}
summary(summary_info, bool_yn: true, section: 'Configurable features')

# Compilation information
summary_info = {}
summary_info += {'host CPU':          cpu}
summary_info += {'host endianness':   build_machine.endian()}
summary_info += {'C compiler':        ' '.join(meson.get_compiler('c').cmd_array())}
summary_info += {'Host C compiler':   ' '.join(meson.get_compiler('c', native: true).cmd_array())}
if 'cpp' in all_languages
  summary_info += {'C++ compiler':    ' '.join(meson.get_compiler('cpp').cmd_array())}
else
  summary_info += {'C++ compiler':      false}
endif
if 'objc' in all_languages
  summary_info += {'Objective-C compiler': ' '.join(meson.get_compiler('objc').cmd_array())}
else
  summary_info += {'Objective-C compiler': false}
endif
summary_info += {'Rust support':      have_rust}
if have_rust
  summary_info += {'Rust target':     config_host['RUST_TARGET_TRIPLE']}
  summary_info += {'rustc':           ' '.join(rustc.cmd_array())}
  summary_info += {'rustc version':   rustc.version()}
  summary_info += {'rustdoc':         rustdoc}
  summary_info += {'bindgen':         bindgen.full_path()}
  summary_info += {'bindgen version': bindgen.version()}
endif
option_cflags = (get_option('debug') ? ['-g'] : [])
if get_option('optimization') != 'plain'
  option_cflags += ['-O' + get_option('optimization')]
endif
summary_info += {'CFLAGS':            ' '.join(get_option('c_args') + option_cflags)}
if 'cpp' in all_languages
  summary_info += {'CXXFLAGS':        ' '.join(get_option('cpp_args') + option_cflags)}
endif
if 'objc' in all_languages
  summary_info += {'OBJCFLAGS':       ' '.join(get_option('objc_args') + option_cflags)}
endif
link_args = get_option('c_link_args')
if link_args.length() > 0
  summary_info += {'LDFLAGS':         ' '.join(link_args)}
endif
summary_info += {'QEMU_CFLAGS':       ' '.join(qemu_common_flags + qemu_cflags)}
if 'cpp' in all_languages
  summary_info += {'QEMU_CXXFLAGS':     ' '.join(qemu_common_flags + qemu_cxxflags)}
endif
if 'objc' in all_languages
  summary_info += {'QEMU_OBJCFLAGS':    ' '.join(qemu_common_flags)}
endif
summary_info += {'QEMU_LDFLAGS':      ' '.join(qemu_ldflags)}
summary_info += {'link-time optimization (LTO)': get_option('b_lto')}
summary_info += {'PIE':               get_option('b_pie')}
summary_info += {'static build':      get_option('prefer_static')}
summary_info += {'shared QOM (experimental)': qom_shared}
summary_info += {'malloc trim support': has_malloc_trim}
summary_info += {'membarrier':        have_membarrier}
summary_info += {'debug graph lock':  get_option('debug_graph_lock')}
summary_info += {'debug stack usage': get_option('debug_stack_usage')}
summary_info += {'mutex debugging':   get_option('debug_mutex')}
summary_info += {'memory allocator':  get_option('malloc')}
summary_info += {'avx2 optimization': config_host_data.get('CONFIG_AVX2_OPT')}
summary_info += {'avx512bw optimization': config_host_data.get('CONFIG_AVX512BW_OPT')}
summary_info += {'gcov':              get_option('b_coverage')}
summary_info += {'thread sanitizer':  get_option('tsan')}
summary_info += {'CFI support':       get_option('cfi')}
if get_option('cfi')
  summary_info += {'CFI debug support': get_option('cfi_debug')}
endif
summary_info += {'strip binaries':    get_option('strip')}
summary_info += {'sparse':            sparse}
summary_info += {'mingw32 support':   host_os == 'windows'}
summary(summary_info, bool_yn: true, section: 'Compilation')

# snarf the cross-compilation information for tests
summary_info = {}
have_cross = false
foreach target: target_dirs
  tcg_mak = meson.project_build_root() / 'tests/tcg' / target / 'config-target.mak'
  if fs.exists(tcg_mak)
    config_cross_tcg = keyval.load(tcg_mak)
    if 'CC' in config_cross_tcg
      summary_info += {config_cross_tcg['TARGET_NAME']: config_cross_tcg['CC']}
      have_cross = true
    endif
  endif
endforeach
if have_cross
  summary(summary_info, bool_yn: true, section: 'Cross compilers')
endif

# Targets and accelerators
summary_info = {}
if have_system
  summary_info += {'KVM support':       config_all_accel.has_key('CONFIG_KVM')}
  summary_info += {'Nitro support':     config_all_accel.has_key('CONFIG_NITRO')}
  summary_info += {'HVF support':       config_all_accel.has_key('CONFIG_HVF')}
  summary_info += {'WHPX support':      config_all_accel.has_key('CONFIG_WHPX')}
  summary_info += {'NVMM support':      config_all_accel.has_key('CONFIG_NVMM')}
  summary_info += {'MSHV support':      config_all_accel.has_key('CONFIG_MSHV')}
  summary_info += {'Xen support':       xen.found()}
  if xen.found()
    summary_info += {'xen ctrl version':  xen.version()}
  endif
  summary_info += {'Xen emulation':     config_all_devices.has_key('CONFIG_XEN_EMU')}
endif
summary_info += {'TCG support':       config_all_accel.has_key('CONFIG_TCG')}
if config_all_accel.has_key('CONFIG_TCG')
  if get_option('tcg_interpreter')
    summary_info += {'TCG backend':   'TCI (TCG with bytecode interpreter, slow)'}
  else
    summary_info += {'TCG backend':   'native (@0@)'.format(cpu)}
  endif
  summary_info += {'TCG plugins':       get_option('plugins')}
  summary_info += {'TCG debug enabled': get_option('debug_tcg')}
  if have_linux_user or have_bsd_user
    summary_info += {'syscall buffer debugging support': get_option('debug_remap')}
  endif
endif
summary_info += {'target list':       ' '.join(target_dirs)}
if have_system
  summary_info += {'default devices':   get_option('default_devices')}
  summary_info += {'out of process emulation': multiprocess_allowed}
  summary_info += {'vfio-user server': vfio_user_server_allowed}
endif
summary(summary_info, bool_yn: true, section: 'Targets and accelerators')

# Block layer
summary_info = {}
summary_info += {'coroutine backend': coroutine_backend}
summary_info += {'coroutine pool':    have_coroutine_pool}
if have_block
  summary_info += {'Block whitelist (rw)': get_option('block_drv_rw_whitelist')}
  summary_info += {'Block whitelist (ro)': get_option('block_drv_ro_whitelist')}
  summary_info += {'Use block whitelist in tools': get_option('block_drv_whitelist_in_tools')}
  summary_info += {'VirtFS (9P) support':    have_virtfs}
  summary_info += {'replication support': config_host_data.get('CONFIG_REPLICATION')}
  summary_info += {'bochs support':     get_option('bochs').allowed()}
  summary_info += {'cloop support':     get_option('cloop').allowed()}
  summary_info += {'dmg support':       get_option('dmg').allowed()}
  summary_info += {'qcow v1 support':   get_option('qcow1').allowed()}
  summary_info += {'vdi support':       get_option('vdi').allowed()}
  summary_info += {'vhdx support':      get_option('vhdx').allowed()}
  summary_info += {'vmdk support':      get_option('vmdk').allowed()}
  summary_info += {'vpc support':       get_option('vpc').allowed()}
  summary_info += {'vvfat support':     get_option('vvfat').allowed()}
  summary_info += {'qed support':       get_option('qed').allowed()}
  summary_info += {'parallels support': get_option('parallels').allowed()}
  summary_info += {'FUSE exports':      fuse}
  summary_info += {'VDUSE block exports': have_vduse_blk_export}
endif
summary(summary_info, bool_yn: true, section: 'Block layer support')

# Crypto
summary_info = {}
summary_info += {'TLS priority':      get_option('tls_priority')}
summary_info += {'GNUTLS support':    gnutls}
if gnutls.found()
  summary_info += {'  GNUTLS crypto':   gnutls_crypto.found()}
  summary_info += {'  GNUTLS bug 1717 workaround': gnutls_bug1717_workaround }
endif
summary_info += {'libgcrypt':         gcrypt}
summary_info += {'nettle':            nettle}
summary_info += {'SM4 ALG support':   crypto_sm4}
summary_info += {'SM3 ALG support':   crypto_sm3}
summary_info += {'AF_ALG support':    have_afalg}
summary_info += {'rng-none':          get_option('rng_none')}
summary_info += {'Linux keyring':     have_keyring}
summary_info += {'Linux keyutils':    keyutils}
summary(summary_info, bool_yn: true, section: 'Crypto')

# UI
summary_info = {}
if host_os == 'darwin'
  summary_info += {'Cocoa support':           cocoa}
endif
summary_info += {'D-Bus display':     dbus_display}
summary_info += {'SDL support':       sdl}
summary_info += {'SDL3 audio support': sdl_audio}
summary_info += {'SDL image support': sdl_image}
summary_info += {'GTK support':       gtk}
summary_info += {'pixman':            pixman}
summary_info += {'VTE support':       vte}
summary_info += {'PNG support':       png}
summary_info += {'VNC support':       vnc}
if vnc.found()
  summary_info += {'VNC SASL support':  sasl}
  summary_info += {'VNC JPEG support':  jpeg}
endif
summary_info += {'VNC D-Bus server (qemu-vnc)': have_qemu_vnc}
summary_info += {'spice protocol support': spice_protocol}
if spice_protocol.found()
  summary_info += {'  spice server support': spice}
endif
summary_info += {'curses support':    curses}
summary_info += {'brlapi support':    brlapi}
summary(summary_info, bool_yn: true, section: 'User interface')

# Graphics backends
summary_info = {}
summary_info += {'VirGL support':     virgl}
summary_info += {'Rutabaga support':  rutabaga}
summary(summary_info, bool_yn: true, section: 'Graphics backends')

# Audio backends
summary_info = {}
if host_os not in ['darwin', 'haiku', 'windows']
  summary_info += {'OSS support':     oss}
  summary_info += {'sndio support':   sndio}
elif host_os == 'darwin'
  summary_info += {'CoreAudio support': coreaudio}
elif host_os == 'windows'
  summary_info += {'DirectSound support': dsound}
endif
if host_os == 'linux'
  summary_info += {'ALSA support':    alsa}
  summary_info += {'PulseAudio support': pulse}
endif
summary_info += {'PipeWire support':  pipewire}
summary_info += {'JACK support':      jack}
summary_info += {'libsamplerate playback': samplerate}
summary(summary_info, bool_yn: true, section: 'Audio backends')

# Network backends
summary_info = {}
if host_os == 'darwin'
  summary_info += {'vmnet.framework support': vmnet}
endif
summary_info += {'AF_XDP support':    libxdp}
summary_info += {'passt support':     enable_passt}
summary_info += {'slirp support':     slirp}
summary_info += {'vde support':       vde}
summary_info += {'netmap support':    have_netmap}
summary_info += {'l2tpv3 support':    have_l2tpv3}
summary(summary_info, bool_yn: true, section: 'Network backends')

# Libraries
summary_info = {}
summary_info += {'libtasn1':          tasn1}
summary_info += {'PAM':               pam}
summary_info += {'iconv support':     iconv}
summary_info += {'blkio support':     blkio}
summary_info += {'curl support':      curl}
summary_info += {'Multipath support': mpathpersist}
summary_info += {'Linux AIO support': libaio}
summary_info += {'Linux io_uring support': linux_io_uring}
summary_info += {'ATTR/XATTR support': libattr}
summary_info += {'RDMA support':      rdma}
summary_info += {'fdt support':       fdt_opt == 'internal' ? 'internal' : fdt}
summary_info += {'libcap-ng support': libcap_ng}
summary_info += {'bpf support':       libbpf}
summary_info += {'rbd support':       rbd}
summary_info += {'smartcard support': cacard}
summary_info += {'U2F support':       u2f}
summary_info += {'libusb':            libusb}
summary_info += {'usb net redir':     usbredir}
summary_info += {'OpenGL support (epoxy)': opengl}
summary_info += {'GBM':               gbm}
summary_info += {'libiscsi support':  libiscsi}
summary_info += {'libisofs support':  libisofs}
summary_info += {'libnfs support':    libnfs}
if host_os == 'windows'
  if have_ga
    summary_info += {'QGA VSS support':   have_qga_vss}
  endif
endif
summary_info += {'seccomp support':   seccomp}
summary_info += {'hv-balloon support': hv_balloon}
summary_info += {'TPM support':       have_tpm}
summary_info += {'IGVM support':      igvm}
summary_info += {'libssh support':    libssh}
summary_info += {'lzo support':       lzo}
summary_info += {'snappy support':    snappy}
summary_info += {'bzip2 support':     libbzip2}
summary_info += {'lzfse support':     liblzfse}
summary_info += {'zstd support':      zstd}
summary_info += {'Query Processing Library support': qpl}
summary_info += {'UADK Library support': uadk}
summary_info += {'qatzip support':    qatzip}
summary_info += {'NUMA host support': numa}
summary_info += {'capstone':          capstone}
summary_info += {'libpmem support':   libpmem}
summary_info += {'libdaxctl support': libdaxctl}
summary_info += {'libcbor support':   libcbor}
summary_info += {'libudev':           libudev}
# Dummy dependency, keep .found()
summary_info += {'FUSE lseek':        fuse_lseek.found()}
summary_info += {'selinux':           selinux}
summary_info += {'libdw':             libdw}
if host_os == 'freebsd'
  summary_info += {'libinotify-kqueue': inotify}
endif
if host_os == 'darwin'
  summary_info += {'ParavirtualizedGraphics support': pvg}
endif
summary_info += {'valgrind':          valgrind}
summary(summary_info, bool_yn: true, section: 'Dependencies')
