# Standalone program only: do not add this dependency to system_ss,
# common_ss, libqemuutil, or an emulator executable.
linphone_opt = get_option('liblinphone').require(
  have_system or have_tools,
  error_message: 'Liblinphone SDK helper requires a system emulator or tools build')
linphone_dep = not_found
if linphone_opt.allowed()
  linphone_dep = dependency('linphone', version: '>=5.3',
                            method: 'pkg-config',
                            required: linphone_opt)
  if linphone_dep.found() and not cc.links('''
    #include <linphone/linphonecore.h>
    int main(void)
    {
        return linphone_core_get_version() == 0;
    }
    ''', dependencies: linphone_dep, name: 'Liblinphone C SDK')
    if linphone_opt.enabled()
      error('Liblinphone SDK headers or C API cannot be linked')
    endif
    warning('Liblinphone SDK C API is unavailable; skipping standalone helper')
    linphone_dep = not_found
  endif
endif

summary('Standalone Liblinphone SDK helper', linphone_dep.found(),
        section: 'Telephone service')
if linphone_dep.found()
  sip_sdk_check = executable('qemu-sip-sdk-check', 'sdk-check.c',
                             dependencies: linphone_dep,
                             install: false)
  test('sip-sdk-version', sip_sdk_check, args: ['--version'],
       suite: ['sip'])
endif
