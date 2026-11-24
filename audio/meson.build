audio_ss = ss.source_set()
audio_ss.add(files(
  'audio.c',
  'audio-be.c',
  'audio-mixeng-be.c',
  'mixeng.c',
  'noaudio.c',
  'wavaudio.c',
))

# deprecated since v10.2, to be removed
system_ss.add(files('audio-hmp-cmds.c', 'wavcapture.c'))

# CoreAudio is the native Darwin backend. Keep its QOM registration in the
# system emulator even when optional backends are loadable modules. The
# Apple framework itself remains a dynamic system dependency.
if coreaudio.found()
  audio_ss.add(coreaudio, files('coreaudio.m'))
endif

audio_modules = {}
foreach m : [
  ['alsa', alsa, files('alsaaudio.c')],
  ['dsound', dsound, files('dsoundaudio.c', 'audio_win_int.c')],
  ['oss', oss, files('ossaudio.c')],
  ['pa', pulse, files('paaudio.c')],
  ['sdl', sdl_audio, files('sdlaudio.c')],
  ['jack', jack, files('jackaudio.c')],
  ['sndio', sndio, files('sndioaudio.c')],
  ['pipewire', pipewire, files('pwaudio.c')],
  ['spice', spice, files('spiceaudio.c')]
]
  if m[1].found()
    module_ss = ss.source_set()
    module_ss.add(m[1], m[2])
    audio_modules += {m[0] : module_ss}
  endif
endforeach

if dbus_display
    module_ss = ss.source_set()
    module_ss.add(when: [gio, pixman],
                  if_true: [dbus_display1_h, files('dbusaudio.c')])
    audio_modules += {'dbus': module_ss}
endif

modules += {'audio': audio_modules}
