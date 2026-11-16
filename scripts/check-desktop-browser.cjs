// SPDX-License-Identifier: BSD-3-Clause
// Actual packaged YM2149 / AtariAudio WASM and Worklets, mocked Tauri IPC.
// Every physical speaker route passes through zero gain; no CPAL device opens.
const {chromium, webkit} = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const {gzipSync} = require('node:zlib');
const http = require('node:http');
const root = path.resolve(__dirname, '..');
const options = {out:path.join(root,'docs/desktop_browser_20261117.json'), screenshots:null};
for(let index=2;index<process.argv.length;index++) {
  const name=process.argv[index].replace(/^--/,'');
  assert(Object.hasOwn(options,name),`Unknown option: ${name}`);
  assert(process.argv[index+1],`Missing value: ${name}`);
  options[name]=path.resolve(process.argv[++index]);
}
const mime = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.wasm':'application/wasm',
  '.json':'application/json','.webp':'image/webp','.png':'image/png','.svg':'image/svg+xml'};
function vgm() {
  const data=[0xa0,0,0xc4,0xa0,1,1,0xa0,7,0x3e,0xa0,8,12];
  for(let n=0;n<20;n++)data.push(0x61,0xff,0xff);
  data.push(0x66);
  const bytes=Buffer.alloc(256+data.length);
  bytes.write('Vgm ');bytes.writeUInt32LE(bytes.length-4,4);bytes.writeUInt32LE(0x171,8);
  bytes.writeUInt32LE(256-0x34,0x34);bytes.writeUInt32LE(2_000_000,0x74);
  bytes[0x78]=0x10;bytes[0x79]=1;bytes.set(data,256);return bytes;
}
function ym3() {
  const ticks=1500,registers=[0xc4,1,0,0,0,0,1,0x3e,15,0,0,64,0,0xff];
  const bytes=Buffer.alloc(4+ticks*14);bytes.write('YM3!');
  registers.forEach((value,reg)=>bytes.fill(value,4+reg*ticks,4+(reg+1)*ticks));return bytes;
}
function sndh() {
  const word=n=>[(n>>>8)&255,n&255],long=n=>[...word(n>>>16),...word(n)],ascii=s=>[...Buffer.from(s)];
  const immediate=(value,address)=>[0x13,0xfc,0,value,...long(address)];
  const write=(reg,value)=>[...immediate(reg,0xff8800),...immediate(value,0xff8802)];
  const bytes=Buffer.alloc(288);
  bytes.set([0x60,0,0,126,0x4e,0x75,0x4e,0x71,0x60,0,0,246]);
  bytes.set([...ascii('SNDHTITLDesktop generated tone\0COMMCodex test\0YEAR2026\0##02#!02\0!V50\0FRMS'),
    ...long(1500),...long(1501),...ascii('HDNS')],12);
  bytes.set([...write(0,0xc4),...write(1,1),...write(7,0x3e),...write(8,15),0x4e,0x75],128);
  bytes.set([...write(0,0x90),0x4e,0x75],256);return bytes;
}
async function run(name, engine, backend) {
  const browser=await engine.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1280,height:1000},acceptDownloads:true});
  page.setDefaultTimeout(15000);
  const errors=[], missing=[], consoleErrors=[], blockedMonaco=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error')consoleErrors.push(message.text());});
  const desktop=await fs.readFile(path.join(root,'desktop/desktop-interface.js'),'utf8');
  const audio=await fs.readFile(path.join(root,'desktop/audio-interface.js'),'utf8');
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(['blob:','data:'].includes(url.protocol)) return route.continue();
    if(url.hostname!=='tauri.localhost') {if(url.hostname==='cdnjs.cloudflare.com'&&url.pathname.includes('/monaco-editor/'))blockedMonaco.push(url.href);else missing.push(url.href);return route.abort();}
    try {
      const file=url.pathname==='/desktop-audio-worklet.js' ? path.join(root,'desktop/audio-worklet.js')
        :path.resolve(root,'dist','.'+decodeURIComponent(url.pathname==='/'?'/index.html':url.pathname));
      assert(file.startsWith(path.join(root,'dist')+path.sep)||file===path.join(root,'desktop/audio-worklet.js'));
      let body=await fs.readFile(file);
      if(url.pathname==='/synth-ym2149-st/synth.js') body=Buffer.concat([body,Buffer.from('\n;\n'+audio)]);
      return route.fulfill({status:200,body,contentType:mime[path.extname(file)]||'application/octet-stream',
        headers:{'access-control-allow-origin':'*'}});
    } catch(error) {missing.push(`${url.pathname}: ${error.message}`);return route.fulfill({status:404,body:'Missing asset'});}
  });
  await page.addInitScript(({backend})=>{
    const audit=window.desktopAudit={calls:[],saves:[],contexts:[],worklets:[],speakerEdges:new Map(),
      pinned:false,nextRead:0,packets:0,returned:0,nativePeak:0,nativeFinite:true,nativeSession:0,failWrites:false,holdStart:false,cancelSave:false};
    const Context=window.AudioContext??window.webkitAudioContext, Node=window.AudioWorkletNode;
    const connect=AudioNode.prototype.connect,disconnect=AudioNode.prototype.disconnect;
    window.AudioContext=class extends Context {constructor(...args){
      super(...args);audit.contexts.push(this);
      // Playwright page routes do not see AudioWorklet module fetches. Serve
      // those exact bytes through a real CORS-enabled loopback test server.
      const add=this.audioWorklet.addModule.bind(this.audioWorklet);
      this.audioWorklet.addModule=(url,...options)=>{
        const value=new URL(url,location.href);
        return add(value.hostname==='tauri.localhost'?new URL(value.pathname+value.search,backend).href:url,...options);
      };
    }};
    if(window.webkitAudioContext) window.webkitAudioContext=window.AudioContext;
    window.AudioWorkletNode=class extends Node {constructor(...args){super(...args);audit.worklets.push({node:this,name:args[1]});}};
    AudioNode.prototype.connect=function(destination,...args){
      if(destination!==this.context.destination) return connect.call(this,destination,...args);
      const analyser=this.context.createAnalyser();analyser.fftSize=4096;
      const mute=this.context.createGain();mute.gain.value=0;
      connect.call(this,analyser);connect.call(analyser,mute);connect.call(mute,destination);
      audit.speakerEdges.set(this,{analyser,mute});return destination;
    };
    AudioNode.prototype.disconnect=function(destination,...args){
      const edge=audit.speakerEdges.get(this);
      if(edge&&(arguments.length===0||destination===this.context.destination)) {
        disconnect.call(this,edge.analyser);disconnect.call(edge.analyser);disconnect.call(edge.mute);audit.speakerEdges.delete(this);
        if(arguments.length) return;
      }
      return arguments.length?disconnect.call(this,destination,...args):disconnect.call(this);
    };
    audit.read=()=>new Promise((resolve,reject)=>{
      const node=audit.worklets.find(entry=>entry.name==='tetorica-ay8910')?.node;
      if(!node) return reject(Error('No synth worklet'));
      const id=--audit.nextRead,timer=setTimeout(()=>{node.port.removeEventListener('message',receive);reject(Error('Read timed out'));},5000);
      function receive({data}) {if(data.id!==id)return;clearTimeout(timer);node.port.removeEventListener('message',receive);data.error?reject(Error(data.error)):resolve(data.value);}
      node.port.addEventListener('message',receive);node.port.start();node.port.postMessage({id,method:'ayTimed',args:[{action:'capture'}]});
    });
    audit.webPeak=async()=>{
      const {output}=await window.tetoricaSynthAudio.ensureReady(),edge=audit.speakerEdges.get(output);
      if(!edge)return 0;const samples=new Float32Array(edge.analyser.fftSize);edge.analyser.getFloatTimeDomainData(samples);
      return samples.reduce((peak,value)=>Math.max(peak,Math.abs(value)),0);
    };
    window.__TAURI_INTERNALS__={invoke:async(command,args={},options)=>{
      audit.calls.push({command,session:args?.session,bytes:args instanceof ArrayBuffer?args.byteLength:null});
      if(command==='window_pin_state')return audit.pinned;
      if(command==='set_window_pin')return audit.pinned=args.pinned;
      if(command==='save_export_binary') {
        const length=new DataView(args).getUint32(0,true),header=JSON.parse(new TextDecoder().decode(new Uint8Array(args,4,length)));
        const bytes=new Uint8Array(args,4+length),text=new TextDecoder().decode(bytes);
        audit.saves.push({header,text,bytes:[...bytes]});return audit.cancelSave?null:'/tmp/'+header.filename;
      }
      if(command==='audio_devices')return [{id:'offline-test',name:'Offline test device',isDefault:true}];
      if(command==='audio_start') {
        if(audit.holdStart)await new Promise(resolve=>{audit.releaseStart=()=>{audit.holdStart=false;resolve();};});
        return {session:`offline-${++audit.nativeSession}`,frames:512,credits:8,sampleRate:args.sampleRate};
      }
      if(command==='audio_stop')return null;
      if(command==='audio_write') {
        if(audit.failWrites)throw Error('Injected offline device failure');
        const samples=new Float32Array(args);audit.packets+=args.byteLength/(512*8);
        for(const value of samples){audit.nativeFinite&&=Number.isFinite(value);audit.nativePeak=Math.max(audit.nativePeak,Math.abs(value));}
        return {rustMicros:100,serviceMicros:200};
      }
      if(command==='audio_poll') {
        await new Promise(resolve=>setTimeout(resolve,20));const credits=Math.min(8,audit.packets-audit.returned);audit.returned+=credits;
        return {credits,queuedFrames:1024,underruns:0};
      }
      if(command==='reload_window')return null;
      throw Error(`Unexpected native command: ${command}`);
    }};
  },{backend});
  await page.addInitScript({content:desktop});
  const state=()=>page.evaluate(()=>window.tetoricaYm2149StSynth.getState());
  const code=()=>page.evaluate(()=>window.tetoricaYm2149StSynth.getCodeState());
  const song=()=>page.evaluate(()=>window.tetoricaYm2149StSynth.getSongState());
  const poll=async(read,predicate,label='State did not settle')=>{
    let value;for(let index=0;index<160;index++){value=await read();if(predicate(value))return value;await page.waitForTimeout(25);}
    throw Error(label+': '+JSON.stringify(value));
  };
  const wait=predicate=>poll(state,predicate);
  const menu=async()=>{if(!await page.locator('#synthMenu').evaluate(node=>node.open))await page.click('#synthMenuButton');};
  const blur=()=>page.evaluate(()=>document.activeElement?.blur());
  const audition=async()=>{
    await blur();await page.keyboard.down('z');await wait(value=>value.activeChannels.length===1);
    const peak=await poll(()=>page.evaluate(()=>desktopAudit.webPeak()),value=>value>.0001,'No pre-mute PCM');
    await page.keyboard.up('z');await wait(value=>value.activeChannels.length===0);return peak;
  };
  const importMusic=async(filename,bytes)=>{
    await menu();const chooser=page.waitForEvent('filechooser');await page.click('#ymLoadMusic');
    await(await chooser).setFiles({name:filename,mimeType:'application/octet-stream',buffer:bytes});
    return poll(song,value=>value.loaded&&!value.busy&&value.name===filename,'Reference did not load');
  };
  try {
    console.log(`CHECK ${name}: ST toolbar / preserved menu / Pin / lazy audio`);
    await page.goto(backend+'/index.html');
    await page.waitForFunction(()=>window.tetoricaSynthAudio&&window.tetoricaYm2149StSynth&&
      document.querySelector('#synthPinButton')?.hidden===false&&document.querySelector('#desktop-audio-native'));
    await page.waitForFunction(()=>document.querySelector('#ymFileNewButton')?.disabled===false);
    assert.equal(await page.title(),'Tetorica ST YM2149 Synth');
    assert.equal(await page.locator('#synthTitle .product-name').textContent(),'ST YM2149 Synth');
    for(const id of ['synthMenu','synthMenuButton','synthMenuPanel','synthPinButton','synthDesktopTools',
      'ymMenuProjectNew','ymLoadMusic','ymMenuProjectImport','ymMenuFilesImport','ymMenuProjectExport','ymMenuFileExport'])
      assert.equal(await page.locator('#'+id).count(),1,`${id} remains unique`);
    assert.equal(await page.locator('#loadPreset').count(),0,'no duplicate desktop preset importer');
    assert.equal(await page.evaluate(()=>desktopAudit.contexts.length),0);
    await page.click('#synthPinButton');await page.waitForFunction(()=>document.querySelector('#synthPinButton').getAttribute('aria-pressed')==='true');
    await page.click('#synthPinButton');await page.waitForFunction(()=>document.querySelector('#synthPinButton').getAttribute('aria-pressed')==='false');
    await menu();assert(await page.locator('#ymProjectNewButton').isVisible());
    await page.click('[data-reset-offline-cache]');
    await page.getByRole('dialog').waitFor();await page.getByRole('button',{name:'Cancel',exact:true}).click();
    assert.equal(await page.evaluate(()=>desktopAudit.calls.filter(c=>c.command==='reload_window').length),0);
    await menu();await page.click('#ymProjectExportButton');
    await page.waitForFunction(()=>desktopAudit.saves.length===1);
    const exported=await page.evaluate(()=>desktopAudit.saves[0]);
    assert.match(exported.header.filename,/\.cassette\.zip$/);assert.deepEqual(exported.bytes.slice(0,2),[80,75]);
    assert.equal(await page.evaluate(()=>desktopAudit.contexts.length),0,'native file saving does not start audio');
    await page.evaluate(()=>{desktopAudit.cancelSave=true;});await menu();await page.click('#ymProjectExportButton');
    await page.waitForFunction(()=>document.querySelector('#audioStatus').textContent==='Save cancelled.');
    await page.evaluate(()=>{desktopAudit.cancelSave=false;});

    console.log(`CHECK ${name}: real YM2149 PCM / same chip / timed example`);
    await page.click('#enableAudio');await page.waitForFunction(()=>document.querySelector('#enableAudio').textContent==='Audio ready');
    const keyboardPeak=await audition();
    assert.equal(await page.evaluate(()=>desktopAudit.contexts.length),1);
    assert.equal(await page.evaluate(()=>desktopAudit.worklets.filter(w=>w.name==='tetorica-ay8910').length),1);
    await page.click('#savePreset');await page.waitForFunction(()=>document.querySelector('#ymPresetSelect').options.length>1);
    if(await page.locator('#ymFilesPanel').isHidden())await page.click('#ymFilesToggle');
    await page.click('[data-file-path="/examples/volume-sample.js"]');await page.click('#synthInputCodeTab');
    await page.click('#synthCodeRunButton');await poll(code,value=>value.running);
    const samplePeak=await poll(()=>page.evaluate(()=>desktopAudit.webPeak()),value=>value>.0001,'Sample has no pre-mute PCM');
    await page.click('#synthInputKeyboardTab');assert((await code()).running,'changing input view keeps Code running');
    const beforeCancelledBackup=await page.locator('#ymFilesTree [data-file-path]').evaluateAll(nodes=>nodes.map(n=>n.dataset.filePath).sort());
    const savesBeforeBackup=await page.evaluate(()=>desktopAudit.saves.length);
    await page.evaluate(()=>{desktopAudit.cancelSave=true;});await menu();await page.click('#ymProjectNewButton');
    await page.getByRole('dialog').waitFor();await page.getByRole('button',{name:'Export current & create',exact:true}).click();
    await page.waitForFunction(count=>desktopAudit.saves.length===count+1,savesBeforeBackup);
    await page.waitForFunction(()=>!document.querySelector('#ymFileNewButton').disabled);
    assert((await code()).running,'cancelling native backup keeps Code running');
    assert.deepEqual(await page.locator('#ymFilesTree [data-file-path]').evaluateAll(nodes=>nodes.map(n=>n.dataset.filePath).sort()),beforeCancelledBackup,
      'cancelling native backup preserves Files');
    if(await page.locator('#ymNewProjectDialog').isVisible())await page.click('#ymNewProjectCancel');
    await page.evaluate(()=>{desktopAudit.cancelSave=false;});
    await page.click('#synthInputCodeTab');await page.click('#synthCodeStopButton');await poll(code,value=>!value.running);
    await poll(()=>page.evaluate(()=>desktopAudit.read()),value=>value.registers[8]===0,'Timed Stop leaves R8 on');
    await page.click('#synthInputKeyboardTab');await page.click('#stopSound');

    console.log(`CHECK ${name}: VGM / YM / SNDH actual reference renderers`);
    const references=[];
    for(const [filename,bytes,expected] of [['generated-st.vgz',gzipSync(vgm()),'vgm'],
      ['generated-st.ym',ym3(),'ym'],['generated-st.sndh',sndh(),'sndh']]) {
      const loaded=await importMusic(filename,bytes);
      assert(loaded.format.toLowerCase().includes(expected));
      await page.click('#ymSongPlay');await poll(song,value=>value.playing&&value.positionFrames>0);
      const peak=await poll(()=>page.evaluate(()=>desktopAudit.webPeak()),value=>value>.0001,'Reference has no PCM');
      await page.click('#ymSongPause');const paused=await poll(song,value=>value.paused);
      await page.click('#ymChannel1Tab');await blur();
      await page.keyboard.down('z');await wait(value=>value.activeChannels.length===1);
      await page.evaluate(async()=>{tetoricaSynthAudio.setSwitching(true);await tetoricaSynthAudio.stopPlayback();});
      await wait(value=>value.activeChannels.length===0&&value.pitch===0);
      assert.equal((await song()).playing,false);assert.equal((await song()).paused,false);
      await page.keyboard.up('z');await page.evaluate(()=>tetoricaSynthAudio.setSwitching(false));
      references.push({filename,format:loaded.format,peak,pausedFrame:paused.positionFrames,pausedAudition:true});
    }
    await page.click('#ymChannelAutoTab');
    const savedPreset=await page.locator('#ymPresetSelect option').evaluateAll(items=>items.map(item=>item.value).find(Boolean));
    assert(savedPreset);await page.locator('#ymPresetSelect').selectOption(savedPreset);
    await wait(value=>value.preset.voices.every(voice=>voice.tone&&voice.volume>0));
    await page.click('[data-file-path="/index.js"]');
    let preserved=structuredClone((await state()).preset);
    await page.locator('#pitchBend').evaluate(node=>{node.value='.5';node.dispatchEvent(new Event('input',{bubbles:true}));});
    await wait(value=>value.pitch===.5);
    await page.evaluate(async()=>{tetoricaSynthAudio.setSwitching(true);await tetoricaSynthAudio.stopPlayback();});
    await page.keyboard.down('z');assert.equal((await state()).activeChannels.length,0);await page.keyboard.up('z');
    await page.click('#synthInputCodeTab');await page.click('#synthCodeRunButton');await page.waitForTimeout(100);
    assert.equal((await code()).running,false,'Code cannot start while output switches');
    await page.evaluate(()=>tetoricaSynthAudio.setSwitching(false));await page.click('#synthInputKeyboardTab');

    console.log(`CHECK ${name}: native capture / switching / failure restores Web Audio`);
    await menu();if(!await page.locator('#desktop-audio-output').evaluate(node=>node.open))await page.locator('#desktop-audio-output > summary').click();
    await blur();await page.keyboard.down('z');await wait(value=>value.activeChannels.length===1);
    preserved=structuredClone((await state()).preset);
    await page.click('#desktop-audio-native');await page.waitForFunction(()=>document.querySelector('#desktop-audio-status').textContent.startsWith('Native →'));
    await wait(value=>value.activeChannels.length===0&&value.pitch===0);await page.keyboard.up('z');
    assert.deepEqual((await state()).preset,preserved);
    await blur();await page.keyboard.down('z');await wait(value=>value.activeChannels.length===1);
    await page.waitForFunction(()=>desktopAudit.nativePeak>.001&&desktopAudit.packets>0);
    preserved=structuredClone((await state()).preset);
    await page.click('#desktop-audio-web');await page.waitForFunction(()=>document.querySelector('#desktop-audio-status').textContent==='Web Audio output');
    await wait(value=>value.activeChannels.length===0);await page.keyboard.up('z');
    assert.deepEqual((await state()).preset,preserved);await audition();
    preserved=structuredClone((await state()).preset);
    await page.click('#desktop-audio-native');await page.waitForFunction(()=>document.querySelector('#desktop-audio-status').textContent.startsWith('Native →'));
    await page.evaluate(()=>{desktopAudit.failWrites=true;});
    await page.waitForFunction(()=>document.querySelector('#desktop-audio-status').textContent.includes('Injected offline device failure'));
    await wait(value=>value.activeChannels.length===0);
    assert.deepEqual((await state()).preset,preserved);await audition();
    assert.equal(await page.evaluate(()=>desktopAudit.contexts.length),1);
    const measurements=await page.evaluate(()=>({nativePackets:desktopAudit.packets,nativePeak:desktopAudit.nativePeak,
      nativeFinite:desktopAudit.nativeFinite,physicalOutputMuted:[...desktopAudit.speakerEdges.values()].every(v=>v.mute.gain.value===0)}));
    assert(measurements.nativeFinite&&measurements.physicalOutputMuted);
    if(options.screenshots)await page.screenshot({path:path.join(options.screenshots,`desktop-${name}.png`),fullPage:true});
    await page.setViewportSize({width:390,height:900});await page.waitForTimeout(120);
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);assert(overflow<=1,`Narrow overflow ${overflow}`);
    if(options.screenshots)await page.screenshot({path:path.join(options.screenshots,`desktop-${name}-narrow.png`),fullPage:true});
    assert.deepEqual(errors,[]);assert.deepEqual(missing,[]);
    return {engine:name,passed:true,toolbarUnique:true,pin:true,originalMenuPreserved:true,nativeCassetteSave:true,
      saveCancel:true,newProjectBackupCancelPreservesFilesAndCode:true,reloadCancel:true,keyboardPeak,samplePeak,timedExample:true,referenceRenderers:references,
      outputSwitchStopsSources:true,outputSwitchResetsPitch:true,outputSwitchBlocksKeysAndCode:true,
      nativeCapturePcm:true,nativeFailureFallback:true,oneAudioContext:true,mobileOverflow:overflow,...measurements,
      nativeHost:'mocked Tauri IPC; no CPAL device',pageErrors:errors,missingAssets:missing,expectedBlockedMonaco:blockedMonaco};
  } catch(error) {
    console.error(JSON.stringify({engine:name,audioStatus:await page.locator('#audioStatus').textContent().catch(()=>null),
      songStatus:await page.locator('#ymSongStatus').textContent().catch(()=>null),errors,missing,consoleErrors}));
    if(options.screenshots)await page.screenshot({path:path.join(options.screenshots,`desktop-${name}-failure.png`),fullPage:true}).catch(()=>{});
    throw error;
  } finally {await browser.close();}
}
(async()=>{
  if(options.screenshots)await fs.mkdir(options.screenshots,{recursive:true});
  const server=http.createServer(async(request,response)=>{
    try {
      let name=decodeURIComponent(new URL(request.url,'http://localhost').pathname);if(name.endsWith('/'))name+='index.html';
      const file=name==='/desktop-audio-worklet.js'?path.join(root,'desktop/audio-worklet.js'):path.resolve(root,'dist','.'+name);
      assert(file.startsWith(path.join(root,'dist')+path.sep)||file===path.join(root,'desktop/audio-worklet.js'));
      const bytes=await fs.readFile(file);response.writeHead(200,{'content-type':mime[path.extname(file)]||'application/octet-stream','access-control-allow-origin':'*'});response.end(bytes);
    } catch(error){response.writeHead(404,{'access-control-allow-origin':'*'});response.end('Missing test asset');}
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  try {
    const backend=`http://tauri.localhost:${server.address().port}`;
    const rows=[];for(const [name,engine] of [['chromium',chromium],['webkit',webkit]])rows.push(await run(name,engine,backend));
    await fs.mkdir(path.dirname(options.out),{recursive:true});await fs.writeFile(options.out,JSON.stringify({passed:true,rows},null,2)+'\n');
    console.log(`Desktop browser check passed: ${options.out}`);
  } finally {await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
