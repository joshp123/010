#!/usr/bin/env node
// Prepare a candidate only. Actual visual review is a separate, explicit step.
import {execFileSync} from 'node:child_process';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {probeMedia,sha256,validateMedia} from './social-video.mjs';
const [input,commit,viewUrl,directory='work/social-video-candidate']=process.argv.slice(2);
if(!input || !/^[a-f0-9]{40}$/.test(commit||'') || !viewUrl?.startsWith('https://'))throw Error('Usage: node scripts/prepare-social-video.mjs INPUT SOURCE_COMMIT HTTPS_VIEW_URL [OUTPUT_DIRECTORY]');
await mkdir(directory,{recursive:true});
const video=path.join(directory,'preview.mp4'),poster=path.join(directory,'poster.jpg');
execFileSync('ffmpeg',['-hide_banner','-loglevel','error','-n','-i',input,'-t','15','-an','-vf',"scale='min(1280,iw)':-2,drawtext=text='@jjpcodes':fontsize=24:fontcolor=white:shadowcolor=black:shadowx=1:shadowy=1:x=w-tw-24:y=h-th-20",'-r','30','-c:v','libx264','-crf','21','-pix_fmt','yuv420p','-movflags','+faststart',video],{stdio:'inherit'});
execFileSync('ffmpeg',['-hide_banner','-loglevel','error','-n','-ss','1','-i',video,'-frames:v','1','-q:v','2',poster],{stdio:'inherit'});
const probe=probeMedia(video),stream=probe.streams.find(item=>item.codec_type==='video');
const manifest={source:{commit,viewUrl,recordingSha256:sha256(await readFile(input))},review:{status:'pending',reviewedAt:null,note:null},video:{file:'preview.mp4',sha256:sha256(await readFile(video)),width:stream.width,height:stream.height,durationSeconds:Number(probe.format.duration)},poster:{file:'poster.jpg',sha256:sha256(await readFile(poster)),width:stream.width,height:stream.height,alt:'Rotterdam in miniature. By @jjpcodes.'}};
await validateMedia(directory,manifest);
await writeFile(path.join(directory,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
console.log(`Validated candidate in ${directory}; NOT approved or referenced by public metadata. Watch it and review the source scene before acceptance.`);
