config_host_data.set('CONFIG_LIBSAMPLERATE', samplerate.found())
audio_drivers_selected = []
if have_system
  audio_drivers_available = {
    'alsa': alsa.found(),
    'coreaudio': coreaudio.found(),
    'dsound': dsound.found(),
    'jack': jack.found(),
    'oss': oss.found(),
    'pa': pulse.found(),
    'pipewire': pipewire.found(),
    'sdl': sdl_audio.found(),
    'sndio': sndio.found(),
  }
  foreach k, v: audio_drivers_available
    config_host_data.set('CONFIG_AUDIO_' + k.to_upper(), v)
  endforeach

  # Prefer native CoreAudio on macOS, then PulseAudio and SDL3.
  # JACK remains opt-in: startup must not depend on a running JACK server.
  # Preserve the other hosts' historical priority when changing macOS policy.
  if host_os == 'darwin'
    audio_drivers_priority = ['coreaudio', 'pa', 'sdl']
  else
    audio_drivers_priority = ['pa', 'coreaudio', 'dsound', 'sndio', 'oss']
    if host_os != 'linux'
      audio_drivers_priority += ['sdl']
    endif
  endif
  audio_drivers_default = []
  foreach k: audio_drivers_priority
    if audio_drivers_available[k]
      audio_drivers_default += k
    endif
  endforeach

  foreach k: get_option('audio_drv_list')
    if k == 'default'
      audio_drivers_selected += audio_drivers_default
    elif not audio_drivers_available[k]
      error('Audio driver "@0@" not available.'.format(k))
    else
      audio_drivers_selected += k
    endif
  endforeach
endif
config_host_data.set('CONFIG_AUDIO_DRIVERS',
                     '"' + '", "'.join(audio_drivers_selected) + '", ')
