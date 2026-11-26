# SPDX-License-Identifier: GPL-2.0-or-later

tests_i386_system_quick = [
  'migration',
]

if host_os == 'darwin' and have_tcg
  tests_i386_system_quick += ['tcg_host_qos']
endif

tests_i386_system_thorough = [
  'replay',
  'tuxrun',
]
