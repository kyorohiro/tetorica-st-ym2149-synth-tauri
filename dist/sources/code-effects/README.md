# Code software effects

This original Tetorica C effect rack is BSD-3-Clause; see LICENSE. It runs after
the YM2149 chip as host software, separately from its hardware sound controls.
The readable browser host is js/native_fx_rack.js; its binary is
js/native_audio_effect.wasm. With Emscripten installed, run here:

```sh
sh scripts/build_native_audio_effect.sh /tmp/tetorica-ym2149-st-code-effects
cp /tmp/tetorica-ym2149-st-code-effects/gain.wasm ../../js/native_audio_effect.wasm
```

An explicit output directory keeps this rebuild independent of artifact-sync tools.
