#!/usr/bin/env python3
"""One-shot transactional patcher for the selective QEMU tools change."""

from pathlib import Path
import re


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


tool_names = [
    "qemu-img", "qemu-io", "qemu-nbd", "qemu-storage-daemon",
    "qemu-keymap", "qemu-edid", "elf2dmp",
    "vhost-user-blk", "vhost-user-bridge", "vhost-user-gpu",
    "vhost-user-input", "vhost-user-scsi",
    "qemu-bridge-helper", "qemu-pr-helper", "qemu-vmsr-helper",
    "ivshmem-client", "ivshmem-server", "qemu-vnc",
]

choices = ", ".join(repr(x) for x in tool_names)
replace_once(
    "meson_options.txt",
    "option('gdb', type: 'string', value: '',\n"
    "       description: 'Path to GDB')\n\n"
    "# Everything else can be set via --enable/--disable-* option",
    "option('gdb', type: 'string', value: '',\n"
    "       description: 'Path to GDB')\n"
    "option('tool_list', type : 'array', value : [],\n"
    f"       choices : [{choices}],\n"
    "       description: 'support utilities to build when tools are enabled (empty means all)')\n\n"
    "# Everything else can be set via --enable/--disable-* option",
)

replace_once(
    "scripts/meson-buildoptions.py",
    '    "default_devices",\n    "fuzzing_engine",\n}',
    '    "default_devices",\n    "fuzzing_engine",\n    "tool_list",\n}',
)

replace_once(
    "configure",
    "  --without-default-features) # processed above\n  ;;",
    '''  --enable-tools=*)
      test -n "$optarg" || error_exit "--enable-tools= requires a comma-separated tool list"
      meson_option_parse --enable-tools ""
      selected_tools=$(printf "%s" "$optarg" | tr ',' ':')
      meson_option_add "-Dtool_list=$(meson_option_build_array "$selected_tools")"
  ;;
  --without-default-features) # processed above
  ;;''',
)
replace_once(
    "configure",
    "EOF\n  meson_options_help\n",
    'EOF\n  printf "%s\\n" "  --enable-tools=LIST        build only comma-separated support utilities"\n  meson_options_help\n',
)

p = Path("meson.build")
text = p.read_text(encoding="utf-8")
old = """have_tools = get_option('tools') \\
  .disable_auto_if(not have_system) \\
  .allowed()
have_ga = get_option('guest_agent') \\
"""
names_literal = ", ".join(repr(x) for x in tool_names)
new = """have_tools = get_option('tools') \\
  .disable_auto_if(not have_system) \\
  .allowed()
tool_list = get_option('tool_list')
if not have_tools and tool_list.length() > 0
  error('tool_list requires tools support')
endif
tool_enabled = {}
foreach tool : [""" + names_literal + """]
  tool_enabled += {tool: have_tools and (tool_list.length() == 0 or tool in tool_list)}
endforeach
have_ga = get_option('guest_agent') \\
"""
if text.count(old) != 1:
    raise SystemExit("meson.build: have_tools insertion point changed")
text = text.replace(old, new, 1)

replacement = r'''# qemu-keymap also feeds the explicit update-keymaps target, so keep the
# executable defined when xkbcommon is available but only build/install it by
# default when the user selected it.
if xkbcommon.found()
  qemu_keymap = executable('qemu-keymap', files('qemu-keymap.c', 'ui/input-keymap.c') + genh,
                           dependencies: [qemuutil, xkbcommon],
                           build_by_default: tool_enabled['qemu-keymap'],
                           install: tool_enabled['qemu-keymap'])
endif

if have_tools
  tools_link_args = enable_modules ? ['@block.syms'] : []
endif

if tool_enabled['qemu-img']
  qemu_img = executable('qemu-img', [files('qemu-img.c'), hxdep],
             link_args: tools_link_args, link_depends: block_syms,
             dependencies: [authz, block, crypto, io, qom, qemuutil], install: true)
  traceable += [{'exe': 'qemu-img', 'probe-prefix': 'qemu.img'}]
endif

if tool_enabled['qemu-io']
  qemu_io = executable('qemu-io', files('qemu-io.c'),
             link_args: tools_link_args, link_depends: block_syms,
             dependencies: [block, qemuutil], install: true)
  traceable += [{'exe': 'qemu-io', 'probe-prefix': 'qemu.io'}]
endif

if tool_enabled['qemu-nbd']
  qemu_nbd = executable('qemu-nbd', files('qemu-nbd.c'),
               link_args: tools_link_args, link_depends: block_syms,
               dependencies: [blockdev, qemuutil, selinux],
               install: true)
  traceable += [{'exe': 'qemu-nbd', 'probe-prefix': 'qemu.nbd'}]
endif

if tool_enabled['qemu-storage-daemon']
  subdir('storage-daemon')
  traceable += [{'exe': 'qemu-storage-daemon', 'probe-prefix': 'qemu.storage_daemon'}]
endif

if tool_enabled['elf2dmp']
  subdir('contrib/elf2dmp')
endif

if tool_enabled['qemu-edid']
  executable('qemu-edid', files('qemu-edid.c', 'hw/display/edid-generate.c'),
             dependencies: [qemuutil, rt],
             install: true)
endif

if have_vhost_user
  if tool_enabled['vhost-user-blk']
    subdir('contrib/vhost-user-blk')
  endif
  if tool_enabled['vhost-user-bridge']
    subdir('contrib/vhost-user-bridge')
  endif
  if tool_enabled['vhost-user-gpu']
    subdir('contrib/vhost-user-gpu')
  endif
  if tool_enabled['vhost-user-input']
    subdir('contrib/vhost-user-input')
  endif
  if tool_enabled['vhost-user-scsi']
    subdir('contrib/vhost-user-scsi')
  endif
endif

if host_os == 'linux'
  if tool_enabled['qemu-bridge-helper']
    executable('qemu-bridge-helper', files('qemu-bridge-helper.c'),
               dependencies: [qemuutil, libcap_ng],
               install: true,
               install_dir: get_option('libexecdir'))
  endif

  if tool_enabled['qemu-pr-helper']
    executable('qemu-pr-helper', files('scsi/qemu-pr-helper.c', 'scsi/utils.c'),
               dependencies: [authz, crypto, io, qom, qemuutil,
                              libcap_ng, mpathpersist],
               install: true)
  endif

  if cpu == 'x86_64' and tool_enabled['qemu-vmsr-helper']
    executable('qemu-vmsr-helper', files('tools/i386/qemu-vmsr-helper.c'),
               dependencies: [authz, crypto, io, qom, qemuutil,
                              libcap_ng, mpathpersist],
               install: true)
  endif
endif

if have_ivshmem and tool_enabled['ivshmem-client']
  subdir('contrib/ivshmem-client')
endif
if have_ivshmem and tool_enabled['ivshmem-server']
  subdir('contrib/ivshmem-server')
endif

if have_qemu_vnc and tool_enabled['qemu-vnc']
  subdir('tools/qemu-vnc')
endif

if stap.found()'''
pattern = re.compile(r"# Don't build qemu-keymap.*?\nendif\n\nif stap\.found\(\)", re.S)
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit(f"meson.build: tool block matches={count}")
p.write_text(text, encoding="utf-8")

replace_once(
    "tests/functional/meson.build",
    "    if have_tools\n"
    "      test_env.set('QEMU_TEST_QEMU_IMG', meson.global_build_root() / 'qemu-img')\n"
    "      test_deps += [qemu_img]\n"
    "    endif",
    "    if tool_enabled['qemu-img']\n"
    "      test_env.set('QEMU_TEST_QEMU_IMG', meson.global_build_root() / 'qemu-img')\n"
    "      test_deps += [qemu_img]\n"
    "    endif",
)

replace_once(
    "tests/qemu-iotests/meson.build",
    "if not have_tools or host_os == 'windows'\n  subdir_done()\nendif",
    "if host_os == 'windows' or not (tool_enabled['qemu-img'] and \\\n"
    "    tool_enabled['qemu-io'] and tool_enabled['qemu-nbd'] and \\\n"
    "    tool_enabled['qemu-storage-daemon'])\n"
    "  subdir_done()\nendif",
)

replace_once(
    "pc-bios/keymaps/meson.build",
    "                                    build_by_default: true,",
    "                                    build_by_default: have_system,",
)

p = Path("docs/meson.build")
text = p.read_text(encoding="utf-8")
replacements = {
    "'qemu-storage-daemon-qmp-ref.7': (have_tools ? 'man7' : '')":
        "'qemu-storage-daemon-qmp-ref.7': (tool_enabled['qemu-storage-daemon'] ? 'man7' : '')",
    "'qemu-img.1': (have_tools ? 'man1' : '')":
        "'qemu-img.1': (tool_enabled['qemu-img'] ? 'man1' : '')",
    "'qemu-nbd.8': (have_tools ? 'man8' : '')":
        "'qemu-nbd.8': (tool_enabled['qemu-nbd'] ? 'man8' : '')",
    "'qemu-pr-helper.8': (have_tools ? 'man8' : '')":
        "'qemu-pr-helper.8': (tool_enabled['qemu-pr-helper'] ? 'man8' : '')",
    "'qemu-storage-daemon.1': (have_tools ? 'man1' : '')":
        "'qemu-storage-daemon.1': (tool_enabled['qemu-storage-daemon'] ? 'man1' : '')",
    "'qemu-vnc.1': (have_qemu_vnc ? 'man1' : '')":
        "'qemu-vnc.1': (have_qemu_vnc and tool_enabled['qemu-vnc'] ? 'man1' : '')",
}
for old, new in replacements.items():
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"docs/meson.build: expected one match for {old!r}, found {count}")
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")
