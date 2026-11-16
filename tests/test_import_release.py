import importlib.util
from pathlib import Path
import tempfile
import json
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('importer', Path(__file__).resolve().parents[1] / 'scripts/import_release.py')
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


def release_files(text=b'<html>test</html>'):
    # Self-contained original synthetic sources; no game/music assets or live ZIP.
    import io
    files = {name: ('source fixture ' + name).encode()
             for name in importer.REQUIRED | importer.NATIVE_INPUTS}
    files.update({
        'index.html': text, 'synth-ym2149-st/index.html': text,
        'synth-ym2149-st/synth.js': b'// readable app',
        'js/playground_ay8910_worklet.js': b'// readable processor',
        'synth-ym2149-st/synth.css': b'body {}',
        'js/ay8910audioengine.js': b'// readable wrapper',
        'generated/ay8910_wasm.js': b'// generated factory',
        'generated/ay8910_wasm.wasm': b'\x00asm\x01\x00\x00\x00',
        'generated/atari-audio-player/atari-audio-player.wasm': b'\x00asm\x01\x00\x00\x00',
    })
    def record(name):
        return {'path': name, 'bytes': len(files[name]), 'sha256': importer.digest(files[name])}
    files['js/native-fx-worklet.js'] = b'// readable Code effects processor'
    files['sources/code-effects/LICENSE'] = files['LICENSE']
    for name in ['LICENSE', 'README.md']:
        files['licenses/mame-ay8910/' + name] = files['sources/ay8910-sdk/vendor/mame-ay8910/' + name]
    manifest = {'schemaVersion': 1, 'files': {
        name.removeprefix('sources/ay8910-sdk/'): {
            'size': len(files[name]), 'sha256': importer.digest(files[name])}
        for name in sorted(importer.NATIVE_INPUTS)}}
    files['sources/ay8910-sdk/RELEASE-MANIFEST.json'] = json.dumps(manifest).encode()
    sdk = {'name': 'tetorica-soundchip-native', 'version': 'fixture',
           'manifestSha256': importer.digest(files['sources/ay8910-sdk/RELEASE-MANIFEST.json'])}
    files['sources/ay8910-sdk/soundchip-sdk.json'] = json.dumps(sdk).encode()
    build = {'id': 'ay8910', 'format': 'emscripten-es-module',
             'sourceFiles': [{'path': name.removeprefix('sources/ay8910-sdk/'),
                              'size': len(files[name]), 'sha256': importer.digest(files[name])}
                             for name in sorted(importer.NATIVE_INPUTS)],
             'outputs': [{'path': name, 'size': len(files['generated/' + name]),
                          'sha256': importer.digest(files['generated/' + name])}
                         for name in ['ay8910_wasm.js', 'ay8910_wasm.wasm']]}
    files['sources/AY8910.json'] = json.dumps({
        'component': 'ay8910', 'sdk': sdk, 'build': build,
        'inputs': [record(name) for name in sorted(importer.NATIVE_INPUTS)],
        'generated': {name: {key: value for key, value in record('generated/' + name).items() if key != 'path'}
                      for name in ['ay8910_wasm.js', 'ay8910_wasm.wasm']},
    }).encode()
    vendor = {'src/AtariAudio.h', 'src/AtariMachine.cpp', 'src/YmRenderer.cpp',
              'src/SndhRenderer.cpp', 'src/external/Musashi/m68k.cpp',
              'src/external/ice_24.cpp', 'src/external/lzh.cpp', 'LICENSE',
              'UPSTREAM_README.md', 'src/external/Musashi/readme.txt', 'src/external/Musashi/m68k.h'}
    atari_names = importer.ATARI_INPUTS | {'third_party/atari-audio/' + name for name in vendor}
    for name in atari_names:
        files[importer.ATARI_PREFIX + name] = (name + ' source').encode()
    files[importer.ATARI_PREFIX + 'LICENSE'] = files['LICENSE']
    upstream = {'repository': 'https://github.com/arnaud-carre/AtariAudio', 'revision': '1' * 40, 'version': 'fixture'}
    source_manifest = {**upstream, 'files': [
        {'path': name, 'sha256': importer.digest(files[importer.ATARI_PREFIX + 'third_party/atari-audio/' + name])}
        for name in sorted(vendor)]}
    files[importer.ATARI_PREFIX + 'third_party/atari-audio/upstream.json'] = json.dumps(source_manifest).encode()
    atari_build = {'component': importer.ATARI_COMPONENT, 'upstream': upstream,
                   'inputs': {name: {key: value for key, value in record(importer.ATARI_PREFIX + name).items() if key != 'path'}
                              for name in sorted(atari_names)},
                   'output': {key: value for key, value in record('generated/atari-audio-player/atari-audio-player.wasm').items() if key != 'path'}}
    files['generated/atari-audio-player/atari-audio-player-build.json'] = json.dumps(atari_build).encode()
    files['sources/ATARI-AUDIO.json'] = json.dumps({
        'component': importer.ATARI_COMPONENT, 'upstream': upstream, 'build': atari_build,
        'inputs': [{**record(importer.ATARI_PREFIX + name), 'sourcePath': name} for name in sorted(atari_names)],
        'generated': [record(name) for name in sorted(importer.ATARI_OUTPUTS)],
    }).encode()
    for name, source in importer.ATARI_NOTICES.items():
        files[name] = files[importer.ATARI_PREFIX + source]
    entries = sorted(importer.BROWSER_ENTRIES)
    modules = [{**record(name), 'sourcePath': 'docs/' + name, 'localImports':
                ['../generated/ay8910_wasm.js', './ay8910audioengine.js'] if name.endswith('/playground_ay8910_worklet.js') else []}
               for name in [*entries, 'js/ay8910audioengine.js']]
    originals = {item['sourcePath']: files[item['path']] for item in modules}
    originals.update({source: files[target] for source, target in importer.FX_INPUTS.items()})
    originals.update({name: files[importer.ATARI_PREFIX + name] for name in atari_names})
    originals.update({'docs/' + name: files[name] for name in importer.ATARI_OUTPUTS})
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as output:
        for name, data in originals.items(): output.writestr(name, data)
    files['sources/ym2149-st-synth-browser-inputs.zip'] = archive.getvalue()
    files['sources/ym2149-st-synth-browser.json'] = json.dumps({
        'productId': 'tetorica-ym2149-st-synth', 'builder': {'name': 'source-copy', 'minify': False, 'bundle': False},
        'bundles': [record(name) for name in entries], 'modules': modules,
        'originalInputs': [{'path': name, 'bytes': len(data), 'sha256': importer.digest(data)} for name, data in originals.items()],
        'sourceArchive': record('sources/ym2149-st-synth-browser-inputs.zip'),
        'referenceArtifacts': [record(name) for name in sorted(importer.ATARI_OUTPUTS)],
    }).encode()
    return files

def write_archive(path, files):
    with zipfile.ZipFile(path, 'w') as output:
        for name, data in files.items():
            output.writestr(name, data)



def refresh_source_archive(files, receipt):
    import io
    name = receipt['sourceArchive']['path']
    with zipfile.ZipFile(io.BytesIO(files[name])) as old:
        original = {entry: old.read(entry) for entry in old.namelist()}
    for item in receipt['modules']:
        original[item['sourcePath']] = files[item['path']]
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as output:
        for entry, body in original.items(): output.writestr(entry, body)
    files[name] = data.getvalue()
    receipt['sourceArchive'] = {'path': name, 'bytes': len(files[name]), 'sha256': importer.digest(files[name])}

def extra_runtime_release_files():
    files = release_files()
    receipt = json.loads(files['sources/ym2149-st-synth-browser.json'])
    name = 'js/extra_fx_worklet.js'
    files[name] = b'// Additional effect worklet'
    module = {'path': name, 'sourcePath': 'docs/' + name,
              'bytes': len(files[name]), 'sha256': importer.digest(files[name]),
              'localImports': ['../generated/extra_fx_wasm.js?v=1']}
    receipt['bundles'].append(module.copy())
    receipt['modules'].append(module.copy())
    receipt['originalInputs'].append({**module, 'path': module['sourcePath']})
    receipt['runtimeArtifacts'] = []
    for name, data in [('generated/extra_fx_wasm.js', b'// Additional effect factory'),
                       ('generated/extra_fx_wasm.wasm', b'\x00asm\x01\x00\x00\x00')]:
        files[name] = data
        receipt['runtimeArtifacts'].append({'path': name, 'bytes': len(data), 'sha256': importer.digest(data)})
    refresh_source_archive(files, receipt)
    files['sources/ym2149-st-synth-browser.json'] = json.dumps(receipt).encode()
    return files


class ImportTests(unittest.TestCase):
    def test_additional_worklet_entries_and_recorded_runtime_are_accepted(self):
        files = extra_runtime_release_files()
        self.assertEqual(self.unpack(files), {name: importer.digest(data) for name, data in files.items()})

    def test_additional_entries_and_runtime_remain_fully_verified(self):
        for name in ['js/extra_fx_worklet.js', 'generated/extra_fx_wasm.js', 'generated/extra_fx_wasm.wasm']:
            for change in ['modify', 'delete']:
                files = extra_runtime_release_files()
                if change == 'modify':
                    files[name] = b'tampered'
                else:
                    del files[name]
                with self.subTest(name=name, change=change), self.assertRaises(ValueError):
                    self.unpack(files)
        for field, omitted in [('bundles', 'synth-ym2149-st/synth.js'),
                               ('modules', 'js/extra_fx_worklet.js'),
                               ('runtimeArtifacts', 'generated/extra_fx_wasm.js'),
                               ('runtimeArtifacts', 'generated/extra_fx_wasm.wasm')]:
            files = extra_runtime_release_files()
            receipt = json.loads(files['sources/ym2149-st-synth-browser.json'])
            receipt[field] = [item for item in receipt[field] if item['path'] != omitted]
            files['sources/ym2149-st-synth-browser.json'] = json.dumps(receipt).encode()
            with self.subTest(field=field, omitted=omitted), self.assertRaises(ValueError):
                self.unpack(files)

    def test_new_zip_updates_without_version_and_preserves_label_for_same_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'any-name.zip'
            write_archive(archive, release_files(b'first'))
            first = importer.import_release(root, archive)
            first['version'] = 'named-release'
            (root / 'release.lock.json').write_text(json.dumps(first))
            self.assertEqual(importer.import_release(root, archive)['version'], 'named-release')
            write_archive(archive, release_files(b'second'))
            changed = importer.import_release(root, archive)
            self.assertNotEqual(changed['sha256'], first['sha256'])
            self.assertEqual(changed['version'], 'sha256-' + changed['sha256'][:12])
            self.assertEqual((root / 'dist/index.html').read_text(), 'second')
            self.assertEqual(importer.check(root), changed)

    def test_invalid_replacement_preserves_dist_and_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'release.zip'
            write_archive(archive, release_files(b'valid'))
            first = importer.import_release(root, archive)
            write_archive(archive, {'index.html': b'wrong app'})
            with self.assertRaises(ValueError):
                importer.import_release(root, archive)
            self.assertEqual(importer.check(root), first)
            self.assertEqual((root / 'dist/index.html').read_text(), 'valid')

    def unpack(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'release.zip'
            write_archive(archive, files)
            return importer.unpack(archive, root / 'out')

    def test_preserves_all_original_bytes(self):
        files = release_files()
        self.assertEqual(self.unpack(files), {name: importer.digest(data) for name, data in files.items()})

    def test_bundled_or_minified_browser_receipts_are_rejected(self):
        for change in [{'name': 'bundle'}, {'minify': True}, {'bundle': True}]:
            files = release_files()
            receipt = json.loads(files['sources/ym2149-st-synth-browser.json'])
            receipt['builder'].update(change)
            files['sources/ym2149-st-synth-browser.json'] = json.dumps(receipt).encode()
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'readable unbundled'):
                self.unpack(files)

    def test_code_effects_wasm_sources_and_licenses_match_original_receipts(self):
        for name in importer.FX_INPUTS.values():
            files = release_files()
            files[name] = b'changed effect input'
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'receipt mismatch'):
                self.unpack(files)
        files = release_files()
        receipt = json.loads(files['sources/ym2149-st-synth-browser.json'])
        receipt['originalInputs'] = [item for item in receipt['originalInputs']
                                     if item['path'] != 'tetorica_src/runtime/generated/effects/gain.wasm']
        files['sources/ym2149-st-synth-browser.json'] = json.dumps(receipt).encode()
        with self.assertRaisesRegex(ValueError, 'Code effects original source receipt'):
            self.unpack(files)

    def test_native_sdk_and_build_inventories_cannot_disagree_with_source_receipts(self):
        for target in ['sources/ay8910-sdk/RELEASE-MANIFEST.json',
                       'sources/ay8910-sdk/soundchip-sdk.json']:
            files = release_files()
            files[target] = b'{}'
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'SDK manifest'):
                self.unpack(files)
        for field in ['sourceFiles', 'outputs']:
            files = release_files()
            receipt = json.loads(files['sources/AY8910.json'])
            receipt['build'][field][0]['sha256'] = '0' * 64
            files['sources/AY8910.json'] = json.dumps(receipt).encode()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'build (source|output) mismatch'):
                self.unpack(files)
        files = release_files()
        receipt = json.loads(files['sources/AY8910.json'])
        receipt['build']['sourceFiles'] = [item for item in receipt['build']['sourceFiles']
                                          if item['path'] != 'wasm/ay8910_wasm.cpp']
        files['sources/AY8910.json'] = json.dumps(receipt).encode()
        with self.assertRaisesRegex(ValueError, 'complete AY8910 WASM build inputs'):
            self.unpack(files)

    def test_check_detects_modified_or_extra_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'dist').mkdir()
            target = root / 'dist/index.html'
            target.write_bytes(b'original')
            (root / 'release.lock.json').write_text(json.dumps({'version': 'test', 'files': {'index.html': importer.digest(b'original')}}))
            self.assertEqual(importer.check(root)['version'], 'test')
            target.write_bytes(b'changed')
            with self.assertRaises(ValueError): importer.check(root)
            target.write_bytes(b'original')
            (root / 'dist/extra.js').write_bytes(b'extra')
            with self.assertRaises(ValueError): importer.check(root)

    def test_rejects_traversal(self):
        for name in ['../escape', '/absolute', 'a/../../escape', 'a\\escape', 'C:/escape']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.unpack({name: b'bad'})

    def test_rejects_wrong_release_or_missing_wasm_and_sources(self):
        with self.assertRaises(ValueError): self.unpack({'index.html': b'wrong app'})
        for name in ['generated/ay8910_wasm.js', 'generated/ay8910_wasm.wasm',
                     'sources/AY8910.json', 'sources/ym2149-st-synth-browser-inputs.zip']:
            files = release_files(); del files[name]
            with self.subTest(name=name), self.assertRaises(ValueError): self.unpack(files)

    def test_rejects_mismatched_receipts_and_changed_native_or_browser_bytes(self):
        for name in ['generated/ay8910_wasm.wasm', 'synth-ym2149-st/synth.js',
                     'js/ay8910audioengine.js', 'sources/ay8910-sdk/vendor/mame-ay8910/ay8910.cpp',
                     'sources/ym2149-st-synth-browser-inputs.zip']:
            files = release_files(); files[name] = b'changed'
            with self.subTest(name=name), self.assertRaises(ValueError): self.unpack(files)
        files = release_files()
        receipt = json.loads(files['sources/ym2149-st-synth-browser.json'])
        receipt['productId'] = 'tetorica-spu-synth'
        files['sources/ym2149-st-synth-browser.json'] = json.dumps(receipt).encode()
        with self.assertRaises(ValueError): self.unpack(files)

    def test_every_readable_module_matches_its_live_bytes_and_original_input_record(self):
        files = release_files()
        receipt = json.loads(files['sources/ym2149-st-synth-browser.json'])
        receipt['modules'][-1]['sha256'] = '0' * 64
        files['sources/ym2149-st-synth-browser.json'] = json.dumps(receipt).encode()
        with self.assertRaisesRegex(ValueError, 'receipt mismatch'): self.unpack(files)
        files = release_files()
        receipt = json.loads(files['sources/ym2149-st-synth-browser.json'])
        next(item for item in receipt['originalInputs'] if item['path'] == receipt['modules'][0]['sourcePath'])['sha256'] = '0' * 64
        files['sources/ym2149-st-synth-browser.json'] = json.dumps(receipt).encode()
        with self.assertRaisesRegex(ValueError, 'original source'): self.unpack(files)

    def test_readable_module_graph_cannot_omit_a_dependency_or_an_entry(self):
        for omitted in ['js/ay8910audioengine.js', 'synth-ym2149-st/synth.js']:
            files = release_files()
            receipt = json.loads(files['sources/ym2149-st-synth-browser.json'])
            receipt['modules'] = [item for item in receipt['modules'] if item['path'] != omitted]
            files['sources/ym2149-st-synth-browser.json'] = json.dumps(receipt).encode()
            with self.subTest(omitted=omitted), self.assertRaises(ValueError): self.unpack(files)
        files = release_files()
        del files['js/ay8910audioengine.js']
        with self.assertRaisesRegex(ValueError, 'Missing recorded'): self.unpack(files)

    def test_ym2149_requires_licenses_and_complete_native_sdk_sources(self):
        for name in ['licenses/mame-ay8910/LICENSE', 'licenses/mame-ay8910/README.md',
                     'sources/ay8910-sdk/vendor/mame-ay8910/LICENSE',
                     'sources/ay8910-sdk/scripts/build-wasm.sh',
                     'sources/ay8910-sdk/vendor/mame-ay8910/upstream/ay8910.cpp']:
            files = release_files(); del files[name]
            with self.subTest(name=name), self.assertRaises(ValueError): self.unpack(files)
        files = release_files()
        receipt = json.loads(files['sources/AY8910.json'])
        receipt['inputs'] = [item for item in receipt['inputs'] if not item['path'].endswith('ay8910.h')]
        files['sources/AY8910.json'] = json.dumps(receipt).encode()
        with self.assertRaisesRegex(ValueError, 'core, wrapper'): self.unpack(files)
        files = release_files()
        receipt = json.loads(files['sources/AY8910.json']); receipt['component'] = 'gameboy_apu'
        files['sources/AY8910.json'] = json.dumps(receipt).encode()
        with self.assertRaisesRegex(ValueError, 'ST YM2149'): self.unpack(files)

    def test_malformed_or_unsafe_module_records_are_rejected(self):
        for replacement in [[], [None], [{'path': '../escape'}]]:
            files = release_files()
            receipt = json.loads(files['sources/ym2149-st-synth-browser.json']); receipt['modules'] = replacement
            files['sources/ym2149-st-synth-browser.json'] = json.dumps(receipt).encode()
            with self.subTest(replacement=replacement), self.assertRaises(ValueError): self.unpack(files)
        files = release_files()
        receipt = json.loads(files['sources/ym2149-st-synth-browser.json'])
        receipt['modules'][0]['localImports'] = ['../../escape.js']
        files['sources/ym2149-st-synth-browser.json'] = json.dumps(receipt).encode()
        with self.assertRaisesRegex(ValueError, 'Unsafe'): self.unpack(files)

    def test_rejects_duplicate_names_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); archive = root / 'release.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('index.html', b'a')
                with self.assertWarns(UserWarning): output.writestr('index.html', b'b')
            with self.assertRaisesRegex(ValueError, 'Duplicate'): importer.unpack(archive, root / 'out')
            with zipfile.ZipFile(archive, 'w') as output:
                info = zipfile.ZipInfo('link'); info.create_system = 3
                info.external_attr = 0o120777 << 16
                output.writestr(info, '../../escape')
            with self.assertRaisesRegex(ValueError, 'Unsafe'): importer.unpack(archive, root / 'out2')


class AtariAudioImportTests(unittest.TestCase):
    unpack = ImportTests.unpack
    def test_atari_reference_wasm_sources_and_notices_are_required_and_authenticated(self):
        names = [*importer.ATARI_OUTPUTS, *importer.ATARI_NOTICES,
                 importer.ATARI_PREFIX + 'third_party/atari-audio/src/SndhRenderer.cpp',
                 importer.ATARI_PREFIX + 'scripts/build_atari_audio_player_wasm.sh']
        for name in names:
            for mode in ['missing', 'changed']:
                files = release_files()
                if mode == 'missing': del files[name]
                else: files[name] = b'tampered native reference input/output'
                with self.subTest(name=name, mode=mode), self.assertRaises(ValueError):
                    self.unpack(files)

    def test_atari_receipt_cannot_omit_sources_or_reference_outputs(self):
        for name, field in [('sources/ATARI-AUDIO.json', 'inputs'),
                            ('sources/ATARI-AUDIO.json', 'generated'),
                            ('sources/ym2149-st-synth-browser.json', 'referenceArtifacts')]:
            files = release_files()
            receipt = json.loads(files[name]); receipt[field] = receipt[field][1:]
            files[name] = json.dumps(receipt).encode()
            with self.subTest(field=field), self.assertRaises(ValueError): self.unpack(files)
        files = release_files()
        native = json.loads(files['sources/ATARI-AUDIO.json'])
        native['build']['inputs'].pop('scripts/build_atari_audio_player_wasm.sh')
        files['sources/ATARI-AUDIO.json'] = json.dumps(native).encode()
        with self.assertRaisesRegex(ValueError, 'build identity'): self.unpack(files)

    def test_nested_browser_source_archive_is_checked_beyond_outer_hash(self):
        import io
        for mode in ['tamper', 'missing', 'extra', 'traversal', 'duplicate']:
            files = release_files()
            name = 'sources/ym2149-st-synth-browser-inputs.zip'
            with zipfile.ZipFile(io.BytesIO(files[name])) as source:
                originals = {entry: source.read(entry) for entry in source.namelist()}
            first = next(iter(originals))
            if mode == 'tamper': originals[first] = b'changed original input'
            if mode == 'missing': originals.pop(first)
            if mode == 'extra': originals['extra.js'] = b'extra'
            if mode == 'traversal': originals['../escape'] = b'escape'
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as archive:
                for entry, data in originals.items(): archive.writestr(entry, data)
                if mode == 'duplicate':
                    with self.assertWarns(UserWarning): archive.writestr(first, b'duplicate')
            files[name] = buffer.getvalue()
            receipt = json.loads(files['sources/ym2149-st-synth-browser.json'])
            receipt['sourceArchive'] = {'path': name, 'bytes': len(files[name]), 'sha256': importer.digest(files[name])}
            files['sources/ym2149-st-synth-browser.json'] = json.dumps(receipt).encode()
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.unpack(files)


if __name__ == '__main__':
    unittest.main()
