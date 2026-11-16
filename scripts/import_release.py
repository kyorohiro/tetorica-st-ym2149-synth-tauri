"""Import an unmodified Synth release; pin archive and extracted file hashes."""
import argparse
import importlib.util
import hashlib
import json
import posixpath
import re
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    'index.html', 'synth-ym2149-st/index.html', 'synth-ym2149-st/synth.js',
    'synth-ym2149-st/atari_worker.js', 'synth-ym2149-st/synth.css',
    'generated/ay8910_wasm.js', 'generated/ay8910_wasm.wasm',
    'sources/AY8910.json', 'sources/AY8910.md',
    'sources/ym2149-st-synth-browser.json', 'sources/ym2149-st-synth-browser-inputs.zip',
    'tetorica_ym2149_st_synth.webp', 'LICENSE',
    'licenses/mame-ay8910/LICENSE', 'licenses/mame-ay8910/README.md',
    'sources/ay8910-sdk/RELEASE-MANIFEST.json', 'sources/ay8910-sdk/soundchip-sdk.json',
    'js/native_audio_effect.wasm', 'sources/code-effects/LICENSE',
    'sources/code-effects/README.md',
    'sources/ATARI-AUDIO.json', 'sources/ATARI-AUDIO.md',
    'generated/atari-audio-player/atari-audio-player.wasm',
    'generated/atari-audio-player/atari-audio-player-build.json',
    'licenses/atari-audio/LICENSE', 'licenses/atari-audio/UPSTREAM_README.md',
    'licenses/musashi/readme.txt', 'licenses/musashi/m68k.h',
    'licenses/ice/ice_24.cpp', 'licenses/lzh/lzh.cpp',
}
NATIVE_INPUTS = {
    'sources/ay8910-sdk/LICENSE', 'sources/ay8910-sdk/sdk.json',
    'sources/ay8910-sdk/scripts/build-wasm.sh',
    'sources/ay8910-sdk/scripts/build_ay8910_wasm.sh',
    'sources/ay8910-sdk/scripts/record_wasm_build.mjs',
    'sources/ay8910-sdk/vendor/mame-ay8910/LICENSE',
    'sources/ay8910-sdk/vendor/mame-ay8910/README.md',
    'sources/ay8910-sdk/vendor/mame-ay8910/ay8910.cpp',
    'sources/ay8910-sdk/vendor/mame-ay8910/ay8910.h',
    'sources/ay8910-sdk/vendor/mame-ay8910/upstream/ay8910.cpp',
    'sources/ay8910-sdk/vendor/mame-ay8910/upstream/ay8910.h',
    'sources/ay8910-sdk/wasm/ay8910_wasm.cpp',
}
BUILD_INPUTS = {
    'scripts/build-wasm.sh', 'scripts/build_ay8910_wasm.sh',
    'scripts/record_wasm_build.mjs',
    'vendor/mame-ay8910/ay8910.cpp', 'vendor/mame-ay8910/ay8910.h',
    'vendor/mame-ay8910/upstream/ay8910.cpp',
    'vendor/mame-ay8910/upstream/ay8910.h', 'wasm/ay8910_wasm.cpp',
}
BROWSER_ENTRIES = {'synth-ym2149-st/synth.js', 'synth-ym2149-st/atari_worker.js',
                   'synth-ym2149-st/synth.css', 'js/playground_ay8910_worklet.js',
                   'js/native-fx-worklet.js'}
# These copies are recorded as original browser inputs rather than generated
# AY8910 outputs. Verify the Code effect engine and its rebuild sources too.
FX_INPUTS = {
    'tetorica_src/runtime/generated/effects/gain.wasm': 'js/native_audio_effect.wasm',
    'scripts/build_native_audio_effect.sh': 'sources/code-effects/scripts/build_native_audio_effect.sh',
    'LICENSE': 'sources/code-effects/LICENSE',
}
for _name in ['compressor.c', 'compressor.h', 'eq.c', 'extra_fx.c', 'extra_fx.h',
              'gain.c', 'graph.c', 'noise.c', 'noise_gate.c', 'noise_gate.h',
              'reverb.c', 'reverb.h', 'sample.c']:
    FX_INPUTS['tetorica_src/native/audio_effect/' + _name] = (
        'sources/code-effects/tetorica_src/native/audio_effect/' + _name)
REQUIRED.update(FX_INPUTS.values())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_release(destination, hashes):
    missing = REQUIRED - hashes.keys()
    if missing:
        raise ValueError('Expected ST YM2149 Synth ZIP; missing: ' + ', '.join(sorted(missing)))

    def verify(record, name):
        if not isinstance(record, dict):
            raise ValueError('Expected a source receipt record')
        safe_name(name)
        if name not in hashes:
            raise ValueError(f'Missing recorded release file: {name}')
        data = (destination / name).read_bytes()
        if record.get('bytes') != len(data) or record.get('sha256') != hashes[name]:
            raise ValueError(f'Release source receipt mismatch: {name}')

    def records(value, label):
        if not isinstance(value, list) or not value:
            raise ValueError(f'Expected {label} source records')
        result = {}
        for record in value:
            if not isinstance(record, dict):
                raise ValueError(f'Expected a {label} source record')
            name = safe_name(record.get('path'))
            if name in result:
                raise ValueError(f'Duplicate {label} source record: {name}')
            result[name] = record
        return result

    browser = json.loads((destination / 'sources/ym2149-st-synth-browser.json').read_text())
    native = json.loads((destination / 'sources/AY8910.json').read_text())
    if (not isinstance(browser, dict) or not isinstance(native, dict)
            or browser.get('productId') != 'tetorica-ym2149-st-synth' or native.get('component') != 'ay8910'):
        raise ValueError('Expected ST YM2149 Synth / AY8910 source receipts')
    builder = browser.get('builder')
    if (not isinstance(builder, dict) or builder.get('name') != 'source-copy'
            or builder.get('minify') is not False or builder.get('bundle') is not False):
        raise ValueError('Expected readable unbundled ST YM2149 browser modules')
    entries = records(browser.get('bundles'), 'browser entry')
    if not BROWSER_ENTRIES <= entries.keys():
        raise ValueError('Expected complete ST YM2149 Synth entry receipts')
    modules = records(browser.get('modules'), 'readable browser module')
    if not entries.keys() <= modules.keys():
        raise ValueError('Expected all browser entries in the readable module receipts')
    # Extra recorded runtime artifacts remain checked, while native FX is
    # authenticated against its original-input receipt below.
    runtime = records(browser['runtimeArtifacts'], 'browser runtime artifact') if 'runtimeArtifacts' in browser else {}
    for name, record in runtime.items():
        verify(record, name)
    original = records(browser.get('originalInputs'), 'original browser input')
    for source, target in FX_INPUTS.items():
        record = original.get(source)
        if record is None:
            raise ValueError(f'Missing Code effects original source receipt: {source}')
        verify(record, target)
    verify(original['LICENSE'], 'LICENSE')
    for name, record in modules.items():
        verify(record, name)
        source = original.get(safe_name(record.get('sourcePath')))
        if not source or any(record.get(key) != source.get(key) for key in ['bytes', 'sha256']):
            raise ValueError(f'Browser module differs from its original source receipt: {name}')
        imports = record.get('localImports', [])
        if not isinstance(imports, list):
            raise ValueError(f'Expected local module imports: {name}')
        for dependency in imports:
            if not isinstance(dependency, str) or not dependency.startswith(('./', '../')):
                raise ValueError(f'Expected a relative local module import: {name}')
            target = safe_name(posixpath.normpath(posixpath.join(posixpath.dirname(name), re.split(r'[?#]', dependency, maxsplit=1)[0])))
            if target not in modules and target != 'generated/ay8910_wasm.js':
                if target in runtime:
                    if target.startswith('generated/') and target.endswith('_wasm.js'):
                        wasm = target[:-3] + '.wasm'
                        if wasm not in runtime:
                            raise ValueError(f'Missing recorded browser runtime WASM: {wasm}')
                    continue
                raise ValueError(f'Missing recorded browser module dependency: {name} -> {target}')
    for name, record in entries.items():
        verify(record, name)
        if any(record.get(key) != modules[name].get(key) for key in ['bytes', 'sha256']):
            raise ValueError(f'Browser entry differs from its module receipt: {name}')
    source = browser.get('sourceArchive', {})
    if not isinstance(source, dict) or source.get('path') != 'sources/ym2149-st-synth-browser-inputs.zip':
        raise ValueError('Expected browser source archive receipt')
    verify(source, source['path'])
    verify_source_archive(destination / source['path'], original)
    generated = native.get('generated')
    if not isinstance(generated, dict):
        raise ValueError('Expected generated ST YM2149 source records')
    for name in ['ay8910_wasm.js', 'ay8910_wasm.wasm']:
        verify(generated.get(name), 'generated/' + name)
    inputs = records(native.get('inputs'), 'AY8910 native input')
    if not NATIVE_INPUTS <= inputs.keys():
        raise ValueError('Expected ST YM2149 core, wrapper and build recipe source inputs')
    for name, record in inputs.items():
        verify(record, name)
    sdk = native.get('sdk')
    sdk_copy = json.loads((destination / 'sources/ay8910-sdk/soundchip-sdk.json').read_text())
    manifest = json.loads((destination / 'sources/ay8910-sdk/RELEASE-MANIFEST.json').read_text())
    if (not isinstance(sdk, dict) or sdk != sdk_copy
            or sdk.get('name') != 'tetorica-soundchip-native'
            or sdk.get('manifestSha256') != hashes['sources/ay8910-sdk/RELEASE-MANIFEST.json']
            or not isinstance(manifest, dict) or not isinstance(manifest.get('files'), dict)):
        raise ValueError('AY8910 SDK manifest / release identity mismatch')
    prefix = 'sources/ay8910-sdk/'
    for name, record in inputs.items():
        source = manifest['files'].get(name.removeprefix(prefix))
        if (not name.startswith(prefix) or not isinstance(source, dict)
                or source.get('size') != record.get('bytes')
                or source.get('sha256') != record.get('sha256')):
            raise ValueError(f'AY8910 SDK source inventory mismatch: {name}')
    build = native.get('build')
    if (not isinstance(build, dict) or build.get('id') != 'ay8910'
            or build.get('format') != 'emscripten-es-module'):
        raise ValueError('Expected AY8910 WASM build identity')
    sources = records(build.get('sourceFiles'), 'AY8910 build input')
    outputs = records(build.get('outputs'), 'AY8910 build output')
    if not BUILD_INPUTS <= sources.keys():
        raise ValueError('Expected complete AY8910 WASM build inputs')
    if set(outputs) != {'ay8910_wasm.js', 'ay8910_wasm.wasm'}:
        raise ValueError('Expected complete AY8910 WASM build outputs')
    for name, source in sources.items():
        recorded = inputs.get(prefix + name)
        if (not recorded or source.get('size') != recorded.get('bytes')
                or source.get('sha256') != recorded.get('sha256')):
            raise ValueError(f'AY8910 build source mismatch: {name}')
    for name, output in outputs.items():
        if (output.get('size') != generated[name].get('bytes')
                or output.get('sha256') != generated[name].get('sha256')):
            raise ValueError(f'AY8910 build output mismatch: {name}')
    for copied, recorded in [
            ('licenses/mame-ay8910/LICENSE', 'sources/ay8910-sdk/vendor/mame-ay8910/LICENSE'),
            ('licenses/mame-ay8910/README.md', 'sources/ay8910-sdk/vendor/mame-ay8910/README.md')]:
        verify(inputs[recorded], copied)

    validate_atari_audio(destination, hashes, original, browser, verify, records)


def verify_source_archive(archive, originals):
    with zipfile.ZipFile(archive) as source:
        members = {}
        for entry in source.infolist():
            if entry.is_dir():
                continue
            name = safe_name(entry.filename)
            if name in members or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError(f'Unsafe or duplicate browser input: {name}')
            members[name] = entry
        if set(members) != set(originals):
            raise ValueError('Browser source archive inventory differs from original inputs')
        for name, record in originals.items():
            data = source.read(members[name])
            if record.get('bytes') != len(data) or record.get('sha256') != digest(data):
                raise ValueError(f'Browser source archive receipt mismatch: {name}')


ATARI_COMPONENT = 'ym2149-atari-audio-reference-player'
ATARI_PREFIX = 'sources/atari-audio-player/'
ATARI_INPUTS = {
    'LICENSE', 'third_party/atari-audio/upstream.json',
    'third_party/atari-audio/LICENSE', 'third_party/atari-audio/UPSTREAM_README.md',
    'third_party/atari-audio/PATCHES.md', 'third_party/atari-audio/local.patch',
    'tetorica_src/wasm/atari_audio_player_wasm.cpp',
    'scripts/build_atari_audio_player_wasm.sh', 'scripts/atari_audio_player_artifacts.mjs',
}
ATARI_NOTICES = {
    'licenses/atari-audio/LICENSE': 'third_party/atari-audio/LICENSE',
    'licenses/atari-audio/UPSTREAM_README.md': 'third_party/atari-audio/UPSTREAM_README.md',
    'licenses/musashi/readme.txt': 'third_party/atari-audio/src/external/Musashi/readme.txt',
    'licenses/musashi/m68k.h': 'third_party/atari-audio/src/external/Musashi/m68k.h',
    'licenses/ice/ice_24.cpp': 'third_party/atari-audio/src/external/ice_24.cpp',
    'licenses/lzh/lzh.cpp': 'third_party/atari-audio/src/external/lzh.cpp',
}
ATARI_OUTPUTS = {
    'generated/atari-audio-player/atari-audio-player.wasm',
    'generated/atari-audio-player/atari-audio-player-build.json',
}


def validate_atari_audio(destination, hashes, original, browser, verify, records):
    native = json.loads((destination / 'sources/ATARI-AUDIO.json').read_text())
    build = json.loads((destination / 'generated/atari-audio-player/atari-audio-player-build.json').read_text())
    if (not isinstance(native, dict) or not isinstance(build, dict)
            or native.get('component') != ATARI_COMPONENT or build.get('component') != ATARI_COMPONENT
            or native.get('build') != build or native.get('upstream') != build.get('upstream')):
        raise ValueError('Expected consistent AtariAudio reference build identity')
    upstream = build.get('upstream')
    if (not isinstance(upstream, dict)
            or upstream.get('repository') != 'https://github.com/arnaud-carre/AtariAudio'
            or not isinstance(upstream.get('revision'), str)
            or re.fullmatch(r'[0-9a-f]{40}', upstream['revision']) is None):
        raise ValueError('Expected AtariAudio upstream repository and revision')
    inputs = records(native.get('inputs'), 'AtariAudio input')
    generated = records(native.get('generated'), 'AtariAudio generated')
    reference = records(browser.get('referenceArtifacts'), 'reference artifact')
    if set(generated) != ATARI_OUTPUTS or not ATARI_OUTPUTS <= reference.keys():
        raise ValueError('Expected both AtariAudio reference outputs')
    for name, record in reference.items():
        verify(record, name)
    for name, record in generated.items():
        verify(record, name)
        verify(reference[name], name)
        original_name = 'docs/' + name
        if original_name not in original:
            raise ValueError(f'Missing AtariAudio original output: {name}')
        verify(original[original_name], name)
    build_inputs = build.get('inputs')
    if not isinstance(build_inputs, dict) or not ATARI_INPUTS <= build_inputs.keys():
        raise ValueError('Expected complete AtariAudio core and rebuild inputs')
    manifest_name = ATARI_PREFIX + 'third_party/atari-audio/upstream.json'
    manifest = json.loads((destination / manifest_name).read_text())
    if (not isinstance(manifest, dict) or manifest.get('revision') != upstream['revision']
            or manifest.get('repository') != upstream['repository']):
        raise ValueError('AtariAudio vendored source revision mismatch')
    vendored = records(manifest.get('files'), 'AtariAudio vendored input')
    if not {'src/AtariAudio.h', 'src/AtariMachine.cpp', 'src/YmRenderer.cpp',
            'src/SndhRenderer.cpp', 'src/external/Musashi/m68k.cpp',
            'src/external/ice_24.cpp', 'src/external/lzh.cpp'} <= vendored.keys():
        raise ValueError('Expected complete AtariAudio source inventory')
    if not (ATARI_INPUTS | {'third_party/atari-audio/' + name for name in vendored}) <= build_inputs.keys():
        raise ValueError('AtariAudio build omits vendored source inputs')
    expected_paths = {ATARI_PREFIX + name for name in build_inputs}
    if set(inputs) != expected_paths:
        raise ValueError('AtariAudio input / build inventory mismatch')
    for name, record in inputs.items():
        source = safe_name(record.get('sourcePath'))
        if name != ATARI_PREFIX + source:
            raise ValueError('AtariAudio input path differs from its original source')
        verify(record, name)
        verify(build_inputs[source], name)
        if source not in original:
            raise ValueError(f'Missing original AtariAudio input: {source}')
        verify(original[source], name)
    for name, record in vendored.items():
        source = 'third_party/atari-audio/' + name
        if record.get('sha256') != build_inputs[source].get('sha256'):
            raise ValueError(f'AtariAudio vendored input mismatch: {name}')
    for target, source in ATARI_NOTICES.items():
        verify(build_inputs[source], target)
    verify(build.get('output'), 'generated/atari-audio-player/atari-audio-player.wasm')


def unpack(archive, destination):
    hashes = {}
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in entry.filename
                    or ':' in entry.filename or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError(f'Unsafe ZIP entry: {entry.filename}')
        for entry in entries:
            if entry.is_dir():
                continue
            name = str(PurePosixPath(entry.filename))
            if name in hashes:
                raise ValueError(f'Duplicate ZIP entry: {name}')
            data = source.read(entry)
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            hashes[name] = digest(data)
    validate_release(destination, hashes)
    return hashes


LOCAL_REQUIRED = {'index.html', 'synth-ym2149-st/synth.js'}
LOCAL_MANIFEST = 'local-changes.json'


def safe_name(name):
    if not isinstance(name, str) or not name or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError('Expected a safe relative release file path')
    path = PurePosixPath(name)
    if (path.is_absolute() or name != path.as_posix() or '..' in path.parts
            or name == '.' or '\\' in name or ':' in name):
        raise ValueError(f'Unsafe local change path: {name}')
    return name


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def snapshot_dist(root):
    directory = root / 'dist'
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Expected a real dist directory')
    hashes = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Symlinks are not release files: {path.relative_to(directory)}')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f'Expected a regular release file: {path.relative_to(directory)}')
        name = safe_name(path.relative_to(directory).as_posix())
        hashes[name] = digest(path.read_bytes())
    return hashes


def baseline_files(lock):
    files = lock.get('files') if isinstance(lock, dict) else None
    if not isinstance(files, dict) or not valid_hash(lock.get('sha256')):
        raise ValueError('Expected a pinned release SHA-256 and file hashes')
    for name, sha in files.items():
        safe_name(name)
        if not valid_hash(sha):
            raise ValueError(f'Invalid imported file SHA-256: {name}')
    return files


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate local manifest property: {key}')
        result[key] = value
    return result


def local_changes(root, lock):
    path = root / LOCAL_MANIFEST
    if path.is_symlink():
        raise ValueError('Local change manifest must not be a symlink')
    if not path.exists():
        return None
    baseline = baseline_files(lock)
    manifest = json.loads(path.read_text(), object_pairs_hook=unique_object)
    if (not isinstance(manifest, dict) or set(manifest) != {'schemaVersion', 'baseSha256', 'files'}
            or type(manifest['schemaVersion']) is not int or manifest['schemaVersion'] != 1
            or not isinstance(manifest['files'], dict)):
        raise ValueError('Invalid local change manifest schema')
    if manifest['baseSha256'] != lock['sha256']:
        raise ValueError('Local changes belong to a different imported release; import and reapply edits')
    for name, sha in manifest['files'].items():
        safe_name(name)
        if sha is None:
            if name not in baseline:
                raise ValueError(f'Cannot delete an unknown imported file: {name}')
        elif not valid_hash(sha):
            raise ValueError(f'Invalid local file SHA-256: {name}')
    return manifest


def require_entries(files):
    missing = LOCAL_REQUIRED - files.keys()
    if missing:
        raise ValueError('Local edits must keep application entry files: ' + ', '.join(sorted(missing)))


def record_local_changes(root):
    lock = json.loads((root / 'release.lock.json').read_text())
    baseline = baseline_files(lock)
    local_changes(root, lock)  # Reject stale or malformed records before replacing them.
    actual = snapshot_dist(root)
    require_entries(actual)
    changes = {name: actual.get(name) for name in sorted(baseline.keys() | actual.keys())
               if actual.get(name) != baseline.get(name)}
    manifest = {'schemaVersion': 1, 'baseSha256': lock['sha256'], 'files': changes}
    destination = root / LOCAL_MANIFEST
    if changes:
        with tempfile.TemporaryDirectory(prefix='.local-edits-', dir=root) as temporary:
            staging = Path(temporary) / LOCAL_MANIFEST
            staging.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
            staging.replace(destination)
        print(f"Recorded {len(changes)} local changes over Synth {lock['version']}; imported release hashes kept")
    else:
        destination.unlink(missing_ok=True)
        print(f"Restored imported Synth {lock['version']}; no local changes")
    return manifest


def check(root):
    lock = json.loads((root / 'release.lock.json').read_text())
    actual = snapshot_dist(root)
    manifest = local_changes(root, lock)
    expected = dict(lock['files'])
    if manifest is not None:
        for name, sha in manifest['files'].items():
            if sha is None:
                expected.pop(name)
            else:
                expected[name] = sha
        require_entries(actual)
    if actual != expected:
        raise ValueError('dist has unrecorded changes; run npm run record:edits or import the pinned ZIP again')
    return lock


def prepare_app_version(root, version):
    # Keep each checkout self-contained and support tests loading this module
    # directly by filename, without relying on the caller's Python path.
    spec = importlib.util.spec_from_file_location('app_version', Path(__file__).with_name('app_version.py'))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper.prepare_version_update(root, version)


def import_release(root, archive, version=None):
    version_update = prepare_app_version(root, version) if version is not None else None
    if not archive.is_file():
        raise FileNotFoundError(f'Synth release ZIP not found: {archive}')
    sha = digest(archive.read_bytes())
    previous = root / 'release.lock.json'
    old_receipt = previous.read_bytes() if previous.exists() else None
    old_lock = json.loads(old_receipt) if old_receipt is not None else {}
    release_version = old_lock.get('version') if old_lock.get('sha256') == sha else f'sha256-{sha[:12]}'
    local_manifest = root / LOCAL_MANIFEST
    old_local = local_manifest.read_bytes() if local_manifest.exists() else None
    with tempfile.TemporaryDirectory(prefix='.import-', dir=root) as temporary:
        staging = Path(temporary) / 'dist'
        staging.mkdir()
        hashes = unpack(archive, staging)
        lock = {'version': release_version, 'archive': archive.name, 'sha256': sha, 'files': hashes}
        destination = root / 'dist'
        backup = Path(temporary) / 'previous-dist'
        if destination.exists():
            destination.rename(backup)
        try:
            staging.rename(destination)
            previous.write_text(json.dumps(lock, indent=2, sort_keys=True) + '\n')
            local_manifest.unlink(missing_ok=True)
            if version_update is not None:
                version_update.apply()
        except BaseException:
            if destination.exists():
                shutil.rmtree(destination)
            if backup.exists():
                backup.rename(destination)
            if old_receipt is None:
                previous.unlink(missing_ok=True)
            else:
                previous.write_bytes(old_receipt)
            if old_local is not None:
                local_manifest.write_bytes(old_local)
            raise
    print(f'Imported {release_version}: {len(hashes)} files, SHA256 {sha}')
    if version_update is not None:
        print(f'App version set to {version_update.version}; dependency versions preserved')
    return lock

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip', nargs='?', type=Path, help='Path to the Synth release ZIP')
    parser.add_argument('--version', help='Set the desktop app version (X.Y.Z), independently of the ZIP name')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--check', action='store_true')
    actions.add_argument('--record-local-changes', action='store_true')
    args = parser.parse_args()
    if (args.check or args.record_local_changes) and (args.zip is not None or args.version is not None):
        parser.error('choose a ZIP import with optional --version, --check, or --record-local-changes')
    if not args.check and not args.record_local_changes and args.zip is None:
        parser.error('provide the ZIP path: npm run import:release -- ./xxx.zip')
    try:
        if args.check:
            lock = check(ROOT)
            manifest = local_changes(ROOT, lock)
            if manifest is None:
                print(f"Verified Synth {lock['version']}: {len(lock['files'])} files")
            else:
                print(f"Verified locally edited Synth {lock['version']}: {len(manifest['files'])} recorded local changes over SHA256 {lock['sha256']}")
        elif args.record_local_changes:
            record_local_changes(ROOT)
        else:
            import_release(ROOT, args.zip, version=args.version)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
