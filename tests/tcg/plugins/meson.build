test_plugins = [
'bb.c',
'discons.c',
'empty.c',
'inline.c',
'insn.c',
'mem.c',
'patch.c',
'registers.c',
'reset.c',
'setpc.c',
'syscall.c',
]

t = []
if get_option('plugins')
  foreach i : test_plugins
    t += shared_module(fs.stem(i), files(i),
                       dependencies: plugins_deps)
  endforeach
  # Explicitly invoked diagnostic; keep it out of the automatic plugin rotation.
  t += shared_module('xed-capture', files('../../xed/xed-capture.c'),
                     dependencies: plugins_deps)
endif
if t.length() > 0
  alias_target('test-plugins', t)
else
  run_target('test-plugins', command: [python, '-c', ''])
endif

plugin_modules += t
