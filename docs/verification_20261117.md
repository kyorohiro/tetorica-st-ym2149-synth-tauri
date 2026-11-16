# ST YM2149 desktop verification — 2026-11-17

Initial version **0.0.1**, product **Tetorica ST YM2149 Synth**, identifier
`net.tetorica.synth-st-ym2149`. This is an initial local implementation; no
commit, push, tag, publication or signing credentials were used.

## Imported source and modification workflow

The imported Web ZIP is `tetorica_ym2149_st_synth_tauri-20261117-r2_itch.zip`,
SHA-256 `cd07d0e20ec65dbdab7d8fd611ba78fad7a23cc820a278156be5996efb5156d9`.
All 202 files in `dist/` match its original bytes. The application JavaScript /
CSS remain readable modules; original browser inputs, AY SDK / native rebuild
sources, AtariAudio / Musashi / ICE / LZH sources and notices, Code-effect
sources and receipt files are included. The imported technical paths retain
`synth-ym2149-st`; the desktop display and repository use the new ST-first name.

`import_release.py` authenticates the readable-module inventory, dependency
closure, original-source ZIP and native source / WASM / license receipts before
replacing `dist/`. It retains atomic imports, independent `--version`, exact
cross-platform hashes and explicit local-edit recording. After direct edits,
`npm run record:edits` records the difference without replacing release hashes.

The wrapper injects its desktop adapters without rewriting imported assets.
The Web module exposes a local-origin, top-level-only final-Master audio bridge.
Output switching cancels Code reservations and reference playback, releases held
notes and resets Pitch. New keyboard / Code / reference starts are blocked while
the switch is in progress. The same WASM renderer serves Web Audio and CPAL.

The existing Menu node is retained, including Project, Files, music and Cassette
actions. The wrapper adds Pin, Reload and audio output. Native backup export is
awaitable: New Project's export-before-create waits for successful saving.
Cancellation or failure preserves the current project and performance. Binary
exports accept the Files layer's byte arrays as well as browser Blobs.

## Completed checks

- Parent `npm run test:ym2149-st-synth`: **170 passed** after the desktop bridge
  and awaited export hook. No shared runtime, DSP or mixer changes.
- Desktop `npm test`: **43 Python + 43 JavaScript passed**. The final typed-array
  export revision also passes all 15 desktop-interface tests. Coverage includes
  importer tampering / source archives / receipts, version rollback, local edits,
  Windows checkout bytes, saving / Pin / reload, PCM transport and error recovery.
- `cargo test --manifest-path src-tauri/Cargo.toml --locked --offline`:
  **24 passed, 2 device tests ignored**. The ignored tests open actual audio
  devices; no physical output device test was run.
- [Desktop browser report](desktop_browser_20261117.json): Chromium and WebKit
  pass with actual AY / AtariAudio WASM and Worklets, a mocked native host and
  muted speakers. It covers one Menu, Pin, Cassette bytes / cancellation,
  New Project backup cancellation preserving Files and running Code, keyboard
  PCM, the timed volume sample and its Stop, generated VGZ / YM3 / SNDH reference
  playback through the actual Worker, Pause / selected-channel audition, output
  switch source retirement / Pitch reset / input guards, native PCM packets and
  failure recovery. One AudioContext, no page errors / missing local assets,
  and no overflow at 390 px. External Monaco is intentionally blocked; the local
  text editor is used for these checks.
- [Transport model](audio_transport_20261117.json) passes its bounded-queue /
  resampling / IPC-delay checks. This is simulated stress evidence, not a
  real-device or long-running desktop test.
- Final local build:

  ```sh
  CARGO_NET_OFFLINE=true CI=true npm run build -- --bundles app --no-sign -- --locked
  ```

  produces `src-tauri/target/release/bundle/macos/Tetorica ST YM2149 Synth.app`.
  The native macOS window was opened: correct title, one Menu, visible Pin and
  cold silent initial state. No audio was enabled. The final save-adapter
  revision was subsequently rebuilt; its cancellation path is covered by the
  real-browser / mocked-native tests, not an actual native save-dialog test.

[Machine-readable evidence](verification_20261117.json) records the final app
binary, imported ZIP and relevant source hashes. This build has no Developer ID
signature or notarization. No claim of human listening or original Atari ST
CPU / MFP cycle accuracy is made.

## Remaining checks

See [the TODO](todo_20261117.md). Actual audio devices / listening, native save /
Pin interaction and long-duration behavior remain manual checks. macOS Intel,
Windows and Linux are configured in CI but have not run remotely. Signed /
notarized macOS app and DMG builds use the local `deploy_mac.sh`; no certificate
is uploaded to hosted Actions. Repository publication and releases remain with
the user.
