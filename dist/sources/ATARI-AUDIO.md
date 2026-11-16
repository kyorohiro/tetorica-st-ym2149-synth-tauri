# AtariAudio reference playback sources and rebuilding

SNDH and YM reference playback uses AtariAudio 1.31, pinned to
commit `1dd9fca810a4f00b4b5e6a5348872ac0a21d88fb` of
https://github.com/arnaud-carre/AtariAudio. Its MIT license, Karl Stenerud's
Musashi license, Hans Wessels' public-domain ICE notice and the LZH source
credits are retained in the source tree and in ../licenses/.

[ATARI-AUDIO.json](ATARI-AUDIO.json) records every native build input and both
shipped outputs with SHA-256 hashes. The browser transport and module Worker
remain readable in ../synth-ym2149-st/atari_engine.js and atari_worker.js.
The standalone WASM lives in ../generated/atari-audio-player/; it uses no
generated JavaScript factory. No music files from upstream are included.

The complete rebuild tree is [atari-audio-player/](atari-audio-player/). It keeps
the repository paths expected by the original build and verification scripts.
With Node.js and Emscripten installed, run from that directory:

```sh
sh scripts/build_atari_audio_player_wasm.sh /tmp/tetorica-atari-audio-player
cp /tmp/tetorica-atari-audio-player/atari-audio-player.wasm ../../generated/atari-audio-player/
cp /tmp/tetorica-atari-audio-player/atari-audio-player-build.json ../../generated/atari-audio-player/
```

The reference player is separate from the MAME-derived AY / YM instrument core.
SNDH replays its Atari 68000 program and can include STE DAC audio; the Live
view observes the three YM voices. Consult third_party/atari-audio/PATCHES.md
for local changes, limits, formats and retained upstream attributions.
