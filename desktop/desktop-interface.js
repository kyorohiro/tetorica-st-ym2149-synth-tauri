(() => {
  'use strict';
  const local = (location.protocol === 'tauri:' && location.hostname === 'localhost') ||
    (['http:', 'https:'].includes(location.protocol) && location.hostname === 'tauri.localhost');
  if (window.top !== window || !local || typeof window.__TAURI_INTERNALS__?.invoke !== 'function') return;
  const invoke = (command, args = {}) => window.__TAURI_INTERNALS__.invoke(command, args);
  const status = text => {const element = document.getElementById('audioStatus'); if (element) element.textContent = text;};
  const MAX_EXPORT_BYTES = 128 * 1024 * 1024, MAX_EXPORT_HEADER_BYTES = 4 * 1024;
  async function saveExport(blob, filename) {
    if (blob.size > MAX_EXPORT_BYTES) throw new Error('Export exceeds 128 MiB');
    const header = new TextEncoder().encode(JSON.stringify({filename}));
    if (!header.byteLength || header.byteLength > MAX_EXPORT_HEADER_BYTES) throw new Error('Export header exceeds 4096 bytes');
    const bytes = await blob.arrayBuffer();
    if (bytes.byteLength > MAX_EXPORT_BYTES) throw new Error('Export exceeds 128 MiB');
    const packet = new Uint8Array(4 + header.byteLength + bytes.byteLength);
    new DataView(packet.buffer).setUint32(0, header.byteLength, true);
    packet.set(header, 4);
    packet.set(new Uint8Array(bytes), 4 + header.byteLength);
    return invoke('save_export_binary', packet.buffer);
  }
  // Workspace replacement awaits this sink, so a cancelled native save keeps
  // the previous project and performance intact. Ordinary exports use the
  // anchor hook below. Both paths send the same original bytes.
  Object.defineProperty(window, 'tetoricaSynthSave', {
    value: async (bytes, filename, type = 'application/octet-stream') => {
      const blob = bytes instanceof Blob ? bytes : new Blob([bytes], {type});
      return (await saveExport(blob, filename)) !== null;
    },
  });
  const blobs = new Map();
  const create = URL.createObjectURL.bind(URL), revoke = URL.revokeObjectURL.bind(URL);
  URL.createObjectURL = blob => {const url = create(blob); blobs.set(url, blob); return url;};
  URL.revokeObjectURL = url => {blobs.delete(url); return revoke(url);};
  const click = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    const blob = blobs.get(this.href);
    if (!this.download || !blob) return click.call(this);
    // Hold the Blob before the Synth immediately revokes its temporary URL.
    const filename = this.download;
    void saveExport(blob, filename)
      .then(path => status(path ? `Saved ${path}` : 'Save cancelled.'))
      .catch(error => status(`Could not save: ${String(error)}`));
  };
  function confirmReload() {
    return new Promise(resolve => {
      const dialog = document.createElement('dialog');
      dialog.style.cssText = 'padding:24px;border:1px solid #9ca7b0;border-radius:12px;background:#e0e3e6;color:#30353c;font:16px system-ui';
      const message = document.createElement('p');
      message.textContent = 'Reload Synth? Playback and unsaved instrument changes will be cleared. Save a preset before reloading to keep the instrument.';
      const cancel = document.createElement('button'), confirm = document.createElement('button');
      cancel.textContent = 'Cancel'; confirm.textContent = 'Reload';
      cancel.addEventListener('click', () => dialog.close('cancel'));
      confirm.addEventListener('click', () => dialog.close('reload'));
      dialog.addEventListener('close', () => {const accepted = dialog.returnValue === 'reload'; dialog.remove(); resolve(accepted);}, {once:true});
      dialog.append(message, cancel, confirm); document.body.append(dialog); dialog.showModal(); cancel.focus();
    });
  }
  // The packaged browser assets stay unchanged. Add the same desktop toolbar
  // used by FM2612 / SPU, retaining the ST app's menu and palette.
  function ensureToolbarHost() {
    if (document.getElementById('synthDesktopTools')) return;
    const title = document.querySelector('.title-row, .title-bar');
    if (!title) return;
    const host = document.createElement('div'); host.id = 'synthDesktopTools';
    const pin = document.createElement('button');
    pin.id = 'synthPinButton'; pin.type = 'button'; pin.hidden = true;
    const audio = document.createElement('div'); audio.id = 'synthMenuAudio';
    const reload = document.createElement('button');
    reload.type = 'button'; reload.dataset.resetOfflineCache = ''; reload.textContent = 'Reload';
    host.append(audio, reload, pin); title.append(host);
  }
  function mountToolbar() {
    const host = document.getElementById('synthDesktopTools');
    if (!host || host.dataset.toolbarMounted) return;
    const identity = document.querySelector('.product-identity');
    const menu = document.getElementById('synthMenu');
    const pin = document.getElementById('synthPinButton');
    const audio = document.getElementById('synthMenuAudio');
    const reload = host.querySelector('[data-reset-offline-cache]');
    const panel = menu?.querySelector('.synth-menu-panel');
    if (!identity || !menu || !panel || !pin || !audio || !reload) return;
    host.dataset.toolbarMounted = 'true';
    document.title = 'Tetorica ST YM2149 Synth';
    const name = document.querySelector('#synthTitle .product-name');
    if (name) name.textContent = 'ST YM2149 Synth';
    const style = document.createElement('style');
    style.textContent = `
      .synth-title-group { display:flex; align-items:center; flex-wrap:wrap; gap:12px; flex:1; min-width:0; }
      .synth-title-group .product-identity { flex:1 1 260px; }
      #synthDesktopTools { display:flex; align-items:center; gap:6px; position:relative; flex-shrink:0; }
      #synthPinButton { display:inline-flex; align-items:center; justify-content:center; width:36px; height:36px; min-height:36px; padding:0; border:1px solid var(--line); border-radius:50%; background:var(--panel); color:var(--accent-dark); cursor:pointer; box-shadow:none; }
      #synthPinButton[hidden] { display:none; }
      #synthPinButton svg { width:19px; height:19px; }
      #synthPinButton:hover, #synthPinButton.is-selected { background:#dbeaf4; border-color:var(--accent); color:var(--accent); }
      #synthPinButton.is-selected .pin-head { fill:var(--accent); }
      #synthPinButton:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
    `;
    document.head.append(style);
    pin.classList.add('synth-icon-button');
    pin.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true"><path class="pin-head" d="M9 3h6v5l3 5v2H6v-2l3-5z"/><path d="M12 15v7"/></svg>';
    // The existing menu owns New Project, music, Files and Cassette actions.
    // Move that exact node instead of recreating its entries or listeners.
    audio.classList.add('synth-menu-section');
    const reloadSection = document.createElement('section');
    reloadSection.className = 'synth-menu-section synth-menu-actions';
    reload.classList.add('toolbar-button'); reload.dataset.closeSynthMenu = '';
    reloadSection.append(reload); panel.append(audio, reloadSection);
    host.replaceChildren(menu, pin);
    const group = document.createElement('div'); group.className = 'synth-title-group';
    identity.before(group); group.append(host, identity);
  }
  const mountedReloadButtons = new WeakSet(), mountedPinButtons = new WeakSet();
  function mountPin() {
    const button = document.getElementById('synthPinButton');
    if (!button || mountedPinButtons.has(button)) return;
    mountedPinButtons.add(button);
    let pinned = false, busy = true;
    const render = () => {
      button.disabled = busy;
      button.setAttribute('aria-pressed', String(pinned));
      button.classList.toggle('is-selected', pinned);
      button.title = pinned ? 'Unpin window' : 'Pin window on top';
      button.setAttribute('aria-label', button.title);
    };
    const readState = value => {
      if (typeof value !== 'boolean') throw new TypeError('Invalid native pin state');
      pinned = value;
    };
    // Keep the keyboard's performance target when clicking the toolbar.
    button.addEventListener('pointerdown', event => event.preventDefault());
    button.addEventListener('click', async () => {
      if (busy) return;
      busy = true; render();
      try {readState(await invoke('set_window_pin', {pinned: !pinned}));}
      catch (error) {status(`Could not pin window: ${String(error)}`);}
      finally {busy = false; render();}
    });
    render();
    void invoke('window_pin_state')
      .then(value => {readState(value); button.hidden = false;})
      .catch(error => status(`Could not read window pin state: ${String(error)}`))
      .finally(() => {busy = false; render();});
  }
  function mount() {
    ensureToolbarHost();
    mountToolbar();
    mountPin();
    const button = document.querySelector('[data-reset-offline-cache]');
    if (!button || mountedReloadButtons.has(button)) return;
    mountedReloadButtons.add(button);
    button.addEventListener('click', async event => {
      event.preventDefault(); event.stopImmediatePropagation();
      if (button.disabled) return;
      button.disabled = true;
      try {if (await confirmReload()) await invoke('reload_window');}
      catch (error) {status(`Could not reload: ${String(error)}`);}
      finally {button.disabled = false;}
    }, {capture: true});
  }
  window.addEventListener('tetorica-synth-ready', mount);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, {once: true});
  else mount();
})();
