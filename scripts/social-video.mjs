import {readFile,mkdir,copyFile,readdir,rm} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import path from 'node:path';

const sha256=bytes=>createHash('sha256').update(bytes).digest('hex');
const marker=/\n?\s*<!-- validated social video -->[\s\S]*?<!-- end validated social video -->/g;
const escape=value=>String(value).replace(/[&"<>]/g,char=>({'&':'&amp;','"':'&quot;','<':'&lt;','>':'&gt;'}[char]));
export function probeMedia(filename) {
  return JSON.parse(execFileSync('ffprobe',['-v','error','-show_streams','-show_format','-of','json',filename],{encoding:'utf8',maxBuffer:1024*1024}));
}
export async function validateMedia(directory,manifest) {
  for(const name of ['video','poster']) {
    const item=manifest[name];
    if(!item || !/^[a-zA-Z0-9_-]+\.(mp4|jpg)$/.test(item.file))throw Error(`Invalid ${name} filename`);
    const file=path.join(directory,item.file),bytes=await readFile(file);
    if(sha256(bytes)!==item.sha256)throw Error(`${name} SHA256 mismatch`);
    if(bytes.length>24*1024*1024)throw Error(`${name} exceeds conservative 24 MiB asset budget`);
    const probe=probeMedia(file),stream=probe.streams.find(item=>item.codec_type==='video');
    if(!stream || stream.width!==item.width || stream.height!==item.height)throw Error(`${name} dimensions mismatch`);
    if(name==='video') {
      if(stream.codec_name!=='h264' || stream.pix_fmt!=='yuv420p' || !probe.format.format_name.includes('mp4'))throw Error('Video must be H.264/yuv420p MP4');
      if(probe.streams.some(item=>item.codec_type==='audio'))throw Error('Social clip must be silent');
      const duration=Number(probe.format.duration);
      if(!(duration>=2 && duration<=30) || !Number.isFinite(item.durationSeconds) || Math.abs(duration-item.durationSeconds)>.1)throw Error('Video duration must match manifest and be 2–30 seconds');
      // MP4 boxes, not substring matching: require fast-start moov before mdat.
      const boxes=[];
      for(let offset=0;offset+8<=bytes.length;) {
        let size=bytes.readUInt32BE(offset);const type=bytes.toString('ascii',offset+4,offset+8);
        if(size===1){if(offset+16>bytes.length)throw Error('Truncated MP4 box');size=Number(bytes.readBigUInt64BE(offset+8));}
        if(size===0)size=bytes.length-offset;
        if(size<8 || offset+size>bytes.length)throw Error('Invalid MP4 box');
        boxes.push(type);offset+=size;
      }
      if(boxes.indexOf('moov')<0 || boxes.indexOf('mdat')<0 || boxes.indexOf('moov')>boxes.indexOf('mdat'))throw Error('MP4 needs +faststart (moov before mdat)');
      execFileSync('ffmpeg',['-v','error','-xerror','-i',file,'-f','null','-'],{stdio:['ignore','ignore','pipe']});
    } else if(stream.codec_name!=='mjpeg')throw Error('Poster must be JPEG');
  }
  if(manifest.video.width!==manifest.poster.width || manifest.video.height!==manifest.poster.height)throw Error('Poster must match the clip dimensions');
}
export async function applySocialVideo({sourceDirectory,outputDirectory,html}) {
  if(html.includes('<!-- validated social video -->')) {
    // Restore the source poster when reprocessing a previously generated page.
    const baseline=await readFile(new URL('../public/index.html',import.meta.url),'utf8');
    for(const tag of baseline.match(/<meta property="og:image[^"]*" content="[^"]*">/g)||[]) {
      const property=tag.match(/property="([^"]+)"/)[1];
      html=html.replace(new RegExp(`<meta property="${property}" content="[^"]*">`),()=>tag);
    }
  }
  html=html.replace(marker,'');
  // A revoked/missing acceptance must not leave an old generated clip in dist.
  const generatedDirectory=path.join(outputDirectory,'social');
  for(const file of await readdir(generatedDirectory).catch(error=>{if(error.code==='ENOENT')return [];throw error;})) {
    if(/^preview-[a-f0-9]{16}\.(mp4|jpg)$/.test(file))await rm(path.join(generatedDirectory,file));
  }
  let manifest;
  try{manifest=JSON.parse(await readFile(path.join(sourceDirectory,'manifest.json'),'utf8'));}
  catch(error){if(error.code==='ENOENT')return {html,enabled:false,reason:'No reviewed clip'};throw error;}
  if(manifest.review?.status!=='accepted')return {html,enabled:false,reason:'Clip awaits visual acceptance'};
  if(!/^[a-f0-9]{40}$/.test(manifest.source?.commit||'') || !manifest.source?.viewUrl?.startsWith('https://') || !manifest.review?.reviewedAt || !manifest.review?.note)throw Error('Accepted clip needs source commit, HTTPS view and visual review record');
  await validateMedia(sourceDirectory,manifest);
  const assetDirectory=path.join(outputDirectory,'social');await mkdir(assetDirectory,{recursive:true});
  const videoName=`preview-${manifest.video.sha256.slice(0,16)}.mp4`,posterName=`preview-${manifest.poster.sha256.slice(0,16)}.jpg`;
  await copyFile(path.join(sourceDirectory,manifest.video.file),path.join(assetDirectory,videoName));
  await copyFile(path.join(sourceDirectory,manifest.poster.file),path.join(assetDirectory,posterName));
  const base='https://010.jjpcodes.com/social/',video=base+videoName,poster=base+posterName;
  const imageValues={'og:image':poster,'og:image:secure_url':poster,'og:image:type':'image/jpeg','og:image:width':manifest.poster.width,'og:image:height':manifest.poster.height,'og:image:alt':manifest.poster.alt||'Rotterdam in miniature. By @jjpcodes.'};
  for(const [property,value] of Object.entries(imageValues))html=html.replace(new RegExp(`(<meta property="${property}" content=")[^"]*(">)`),(_,before,after)=>before+escape(value)+after);
  const values={'og:video':video,'og:video:secure_url':video,'og:video:type':'video/mp4','og:video:width':manifest.video.width,'og:video:height':manifest.video.height};
  const tags=Object.entries(values).map(([property,value])=>`  <meta property="${property}" content="${escape(value)}">`).join('\n');
  html=html.replace('</head>',`  <!-- validated social video -->\n${tags}\n  <!-- end validated social video -->\n</head>`);
  return {html,enabled:true,video,poster};
}
export {sha256};
