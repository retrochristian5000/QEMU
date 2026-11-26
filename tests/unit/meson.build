
testblock = declare_dependency(dependencies: [block], sources: 'iothread.c')

tests = {
  'check-block-qdict': [],
  'check-qdict': [],
  'check-qnum': [],
  'check-qstring': [],
  'check-qlist': [],
  'check-qnull': [],
  'check-qobject': [],
  'check-qjson': [],
  'check-json-parser': [],
  'check-qlit': [],
  'test-error-report': [],
  'test-qobject-output-visitor': [testqapi],
  'test-clone-visitor': [testqapi],
  'test-qobject-input-visitor': [testqapi],
  'test-forward-visitor': [testqapi],
  'test-string-input-visitor': [testqapi],
  'test-string-output-visitor': [testqapi],
  'test-visitor-serialization': [testqapi],
  'test-bitmap': [],
  'test-resv-mem': [],
  # all code tested by test-x86-topo is inside topology.h
  'test-x86-topo': [],
  'test-cutils': [],
  'test-div128': [],
  'test-shift128': [],
  'test-mul64': [],
  # all code tested by test-int128 is inside int128.h
  'test-int128': [],
  'rcutorture': [],
  'test-rcu-list': [],
  'test-rcu-simpleq': [],
  'test-rcu-tailq': [],
  'test-rcu-slist': [],
  'test-qdist': [],
  'test-qht': [],
  'test-qtree': [],
  'test-bitops': [],
  'test-bitcnt': [],
  'test-qgraph': ['../qtest/libqos/qgraph.c'],
  'check-qom-interface': [qom],
  'check-qom-proplist': [qom],
  'test-qemu-opts': [],
  'test-keyval': [testqapi],
  'test-logging': [],
  'test-qapi-util': [],
  'test-interval-tree': [],
  'test-fifo': [],
  'test-envlist': [],
}

if host_os == 'darwin'
  tests += {'test-qemu-thread-signal-mask': []}
endif

if have_system or have_tools
  tests += {
    'test-qmp-event': [testqapi],
  }

  if seccomp.found()
    tests += {'test-seccomp': ['../../system/qemu-seccomp.c', seccomp]}
  endif
endif

if have_block
  tests += {
    'test-coroutine': [testblock],
    'test-aio': [testblock],
    'test-aio-multithread': [testblock],
    'test-throttle': [testblock],
    'test-thread-pool': [testblock],
    'test-hbitmap': [testblock],
    'test-bdrv-drain': [testblock],
    'test-bdrv-graph-mod': [testblock],
    'test-blockjob': [testblock],
    'test-blockjob-txn': [testblock],
    'test-block-backend': [testblock],
    'test-block-iothread': [testblock],
    'test-write-threshold': [testblock],
    'test-crypto-hash': [crypto],
    'test-crypto-hmac': [crypto],
    'test-crypto-cipher': [crypto],
    'test-crypto-akcipher': [crypto],
    'test-crypto-secret': [crypto, keyutils],
    'test-crypto-der': [crypto],
    'test-authz-simple': [authz],
    'test-authz-list': [authz],
    'test-authz-listfile': [authz],
    'test-io-task': [testblock],
    'test-io-channel-socket': ['socket-helpers.c', 'io-channel-helpers.c', io],
    'test-io-channel-file': ['io-channel-helpers.c', io],
    'test-io-channel-command': ['io-channel-helpers.c', io],
    'test-io-channel-buffer': ['io-channel-helpers.c', io],
    'test-io-channel-null': [io],
    'test-crypto-ivgen': [io],
    'test-crypto-afsplit': [io],
    'test-crypto-block': [io],
    'test-timed-average': [],
    'test-uuid': [],
  }
  if gnutls.found() and \
     tasn1.found() and \
     host_os != 'windows'
    tests += {
      'test-crypto-tlscredsx509': ['crypto-tls-x509-helpers.c',
                                   tasn1, crypto, gnutls],
      'test-crypto-tlssession': ['crypto-tls-x509-helpers.c', 'crypto-tls-psk-helpers.c',
                                 tasn1, crypto, gnutls],
      'test-io-channel-tls': ['io-channel-helpers.c', 'crypto-tls-x509-helpers.c',
                              tasn1, io, crypto, gnutls]}
  endif
  if pam.found()
    tests += {'test-authz-pam': [authz]}
  endif
  if host_os != 'windows'
    tests += {
      'test-image-locking': [testblock],
      'test-nested-aio-poll': [],
    }
  endif
  if config_host_data.get('CONFIG_REPLICATION')
    tests += {'test-replication': [testblock]}
  endif
  tests += {'test-crypto-pbkdf': [io]}
endif

if have_system
  tests += {
    'ptimer-test': ['ptimer-test-stubs.c', meson.project_source_root() / 'hw/core/ptimer.c'],
    'test-iov': [],
    'test-intel-8741': [
      meson.project_source_root() / 'hw/input/intel-8741-core.c',
      meson.project_source_root() / 'hw/input/intel-8741-program.c',
      meson.project_source_root() / 'hw/input/att-kbd302-core.c',
    ],
    'test-att-kbd302': [
      meson.project_source_root() / 'hw/input/att-kbd302-core.c',
      meson.project_source_root() / 'hw/input/att-kbd302-map.c',
    ],
    'test-core99-flash': [meson.project_source_root() / 'hw/nvram/core99_flash.c'],
    'test-core99-bank': [meson.project_source_root() / 'hw/nvram/core99_bank.c'],
    'test-ncr5380': [meson.project_source_root() / 'hw/scsi/ncr5380.c'],
    'test-opts-visitor': [testqapi],
    'test-xs-node': [qom],
    'test-virtio-dmabuf': [meson.project_source_root() / 'hw/display/virtio-dmabuf.c'],
    'test-qmp-cmds': [testqapi],
    'test-xbzrle': [migration],
    'test-util-sockets': ['socket-helpers.c'],
    'test-base64': [],
    'test-bufferiszero': [],
    'test-smp-parse': [qom, meson.project_source_root() / 'hw/core/machine-smp.c'],
    'test-analog-video': [meson.project_source_root() / 'hw/display/analog-video.c'],
    'test-vga-scanout': [],
    'test-vga-palette': [],
    'test-edid-input': [meson.project_source_root() / 'hw/display/edid-generate.c'],
    'test-dvdrom': [meson.project_source_root() / 'hw/block/dvdrom.c'],
    'test-cdrom-sector': [],
    'test-mmc-rom': [],
    'test-eltorito': [],
    'test-apic-bitmap': [],
    'test-ced': [meson.project_source_root() / 'hw/block/ced.c'],
    'test-ced-sft100': [
      meson.project_source_root() / 'hw/block/ced.c',
      meson.project_source_root() / 'hw/block/ced-sft100-control.c',
    ],
    'test-ced-sft100-audio': [
      meson.project_source_root() / 'hw/block/ced.c',
      meson.project_source_root() / 'hw/block/ced-sft100-control.c',
      meson.project_source_root() / 'hw/block/ced-sft100-audio.c',
    ],
    'test-f8-isa': [meson.project_source_root() / 'target/f8/isa.c'],
    'test-f8-regs': [meson.project_source_root() / 'target/f8/regs.c'],
    'test-vmstate': [migration, io],
    'test-yank': ['socket-helpers.c', qom, io, chardev],
    'test-ram-discard-manager': [
      'test-ram-discard-manager.c',
      'test-ram-discard-manager-stubs.c',
      meson.project_source_root() / 'system/ram-discard-manager.c',
      genh, qemuutil, qom
    ],
  }
  if config_host_data.get('CONFIG_INOTIFY1')
    tests += {'test-util-filemonitor': []}
  endif

  # Some tests: test-char, test-qdev-global-props, and test-qga,
  # are not runnable under TSan due to a known issue.
  # https://github.com/google/sanitizers/issues/1116
  if not get_option('tsan')
    if host_os != 'windows'
        tests += {
          'test-char': [
            'socket-helpers.c',
            meson.project_source_root() / 'chardev/modem.c',
            qom,
            io,
            chardev,
          ],
          'test-modem-voice': [
            meson.project_source_root() / 'chardev/modem.c',
            qom,
            io,
            chardev,
          ],
        }
    endif

    tests += {
      'test-qdev-global-props': [qom, hwcore]
    }
  endif
  tests += {'test-qdev': [qom, hwcore]}
endif

if have_ga and host_os == 'linux'
  tests += {'test-qga': ['../qtest/libqmp.c', '../qtest/libqtest.c']}
  test_deps += {'test-qga': qga}
endif

# Exercise the actual libatomic ABI on private host objects only.  Do not
# add this dependency to qemuutil or the emulator's guest-memory atomics.
if host_arch == 'aarch64' and host_os == 'linux' and config_host_data.get('CONFIG_INT128_TYPE')
  aarch64_libatomic = cc.find_library('atomic', required: false)
  aarch64_libatomic_test = files('test-aarch64-libatomic.c')
  if aarch64_libatomic.found() and cc.links(aarch64_libatomic_test,
      dependencies: aarch64_libatomic, name: 'AArch64 libatomic 128-bit ABI')
    aarch64_libatomic_exe = executable('test-aarch64-libatomic',
                                      aarch64_libatomic_test,
                                      dependencies: aarch64_libatomic)
    test('test-aarch64-libatomic', aarch64_libatomic_exe, suite: ['unit'])
  endif
endif

if samplerate.found()
  tests += {'test-audio-samplerate': [
    meson.project_source_root() / 'audio/resample-samplerate.c',
    samplerate,
  ]}
endif

test_env = environment()
test_env.set('G_TEST_SRCDIR', meson.current_source_dir())
test_env.set('G_TEST_BUILDDIR', meson.current_build_dir())

slow_tests = {
  'test-aio-multithread' : 120,
  'test-bufferiszero': 60,
  'test-crypto-block' : 300,
  'test-crypto-tlscredsx509': 90,
  'test-crypto-tlssession': 90,
  'test-replication': 60,
}

foreach test_name, extra: tests
  src = [test_name + '.c']
  deps = [qemuutil]
  if extra.length() > 0
    # use a sourceset to quickly separate sources and deps
    test_ss = ss.source_set()
    test_ss.add(extra)
    src += test_ss.all_sources()
    deps += test_ss.all_dependencies()
  endif
  exe = executable(test_name, src, genh, dependencies: deps)

  test(test_name, exe,
       depends: test_deps.get(test_name, []),
       env: test_env,
       args: ['--tap', '-k'],
       protocol: 'tap',
       timeout: slow_tests.get(test_name, 30),
       priority: slow_tests.get(test_name, 30),
       suite: ['unit'])
endforeach