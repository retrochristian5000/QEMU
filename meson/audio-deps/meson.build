oss = not_found
if get_option('oss').allowed() and have_system
  if not cc.has_header('sys/soundcard.h')
    # not found
  elif host_os == 'netbsd'
    oss = cc.find_library('ossaudio', required: get_option('oss'))
  else
    oss = declare_dependency()
  endif

  if not oss.found()
    if get_option('oss').enabled()
      error('OSS not found')
    endif
  endif
endif
dsound = not_found
if not get_option('dsound').auto() or (host_os == 'windows' and have_system)
  if cc.has_header('dsound.h')
    dsound = declare_dependency(link_args: ['-lole32', '-ldxguid'])
  endif

  if not dsound.found()
    if get_option('dsound').enabled()
      error('DirectSound not found')
    endif
  endif
endif

samplerate = not_found
if have_system and not get_option('libsamplerate').disabled()
  samplerate = dependency('samplerate', version: '>=0.2.2',
                          required: get_option('libsamplerate'),
                          method: 'pkg-config')
  if samplerate.found() and not cc.links('''
    #include <samplerate.h>
    int main(void) {
      int err;
      SRC_STATE *s = src_new(SRC_SINC_FASTEST, 2, &err);
      SRC_DATA d = {0};
      if (s) {
        src_process(s, &d);
        src_reset(s);
        src_delete(s);
      }
      return !src_is_valid_ratio(1.0);
    }
  ''', dependencies: samplerate, name: 'libsamplerate streaming ABI')
    if get_option('libsamplerate').enabled()
      error('libsamplerate headers and library failed the streaming ABI link check')
    endif
    samplerate = not_found
  endif
elif get_option('libsamplerate').enabled()
  error('libsamplerate playback requires a system emulator build')
endif

coreaudio = not_found
if not get_option('coreaudio').auto() or (host_os == 'darwin' and have_system)
  coreaudio = dependency('appleframeworks', modules: 'CoreAudio',
                         required: get_option('coreaudio'))
endif
