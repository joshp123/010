import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm,readdir} from 'node:fs/promises';
import os from 'node:os';import path from 'node:path';import {execFileSync} from 'node:child_process';
import {applySocialVideo,probeMedia,sha256} from '../scripts/social-video.mjs';
const root=await mkdtemp(path.join(os.tmpdir(),'010-media-test-')),sourceDirectory=path.join(root,'source'),outputDirectory=path.join(root,'output');
try {
 await mkdir(sourceDirectory);await mkdir(outputDirectory);
 const html=await readFile(new URL('../public/index.html',import.meta.url),'utf8');
 assert.equal((await applySocialVideo({sourceDirectory,outputDirectory,html})).enabled,false,'Absent real media never gets video tags');
 // Synthetic bytes are test fixtures only, never copied to repository/public output.
 const video=path.join(sourceDirectory,'preview.mp4'),poster=path.join(sourceDirectory,'poster.jpg');
 execFileSync('ffmpeg',['-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=12','-t','2','-an','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',video]);
 execFileSync('ffmpeg',['-v','error','-i',video,'-frames:v','1',poster]);
 const manifest={source:{commit:'a'.repeat(40),viewUrl:'https://010.jjpcodes.com/?span=90'},review:{status:'pending'},video:{file:'preview.mp4',sha256:sha256(await readFile(video)),width:320,height:180,durationSeconds:Number(probeMedia(video).format.duration)},poster:{file:'poster.jpg',sha256:sha256(await readFile(poster)),width:320,height:180,alt:'Synthetic test only'}};
 const save=()=>writeFile(path.join(sourceDirectory,'manifest.json'),JSON.stringify(manifest));await save();
 assert.equal((await applySocialVideo({sourceDirectory,outputDirectory,html})).enabled,false,'Unreviewed media stays unadvertised');
 manifest.review={status:'accepted',reviewedAt:'2026-10-24',note:'Synthetic fixture acceptance for tests only'};await save();
 const result=await applySocialVideo({sourceDirectory,outputDirectory,html});assert.equal(result.enabled,true);
 for(const tag of ['og:video','og:video:secure_url','og:video:type','og:video:width','og:video:height'])assert.ok(result.html.includes(`property="${tag}"`));
 assert.match(result.html,/content="video\/mp4"/);assert.match(result.html,/https:\/\/010\.jjpcodes\.com\/social\/preview-[a-f0-9]+\.mp4/);
 assert.match(result.html,/name="twitter:card" content="summary_large_image"/,'Static fallback retained');
 manifest.video.width=640;await save();await assert.rejects(()=>applySocialVideo({sourceDirectory,outputDirectory,html}),/dimensions mismatch/);
 manifest.video.width=320;manifest.video.sha256='0'.repeat(64);await save();await assert.rejects(()=>applySocialVideo({sourceDirectory,outputDirectory,html}),/SHA256 mismatch/);
 manifest.review.status='pending';await save();const revoked=await applySocialVideo({sourceDirectory,outputDirectory,html:result.html});assert.equal(revoked.enabled,false);assert.match(revoked.html,/property="og:image" content="https:\/\/010\.jjpcodes\.com\/social-preview\.jpg"/,'Revocation restores static poster');assert.ok(!revoked.html.includes('property="og:video"'));assert.equal((await readdir(path.join(outputDirectory,'social'))).length,0,'Revocation removes generated public clips');
 console.log('Social video gate: absent/pending/accepted, MP4 decode, metadata, corrupt dimensions/hash and revocation pass');
} finally {await rm(root,{recursive:true,force:true});}
