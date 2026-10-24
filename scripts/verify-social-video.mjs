#!/usr/bin/env node
// Read-only verification against the actual candidate/published asset server.
import assert from 'node:assert/strict';
const origin=new URL(process.argv[2]||'https://010.jjpcodes.com');
const page=await fetch(origin);assert.equal(page.status,200,'HTML must be public HTTP200');
const html=await page.text(),tags=Object.fromEntries([...html.matchAll(/<meta property="([^"]+)" content="([^"]*)"/g)].map(match=>[match[1],match[2]]));
const hosted=value=>new URL(new URL(value).pathname,origin);
assert.ok(tags['og:image']?.startsWith('https://'),'HTTPS poster fallback missing');
const poster=await fetch(hosted(tags['og:image']),{method:'HEAD'});assert.equal(poster.status,200);assert.match(poster.headers.get('content-type')||'',/^image\/jpeg/);
if(!tags['og:video']){console.log('Static poster verified; no social video is referenced. Final clip verification remains pending.');process.exitCode=2;}
else {
  assert.ok(tags['og:video'].startsWith('https://'));
  assert.equal(tags['og:video:secure_url'],tags['og:video']);assert.equal(tags['og:video:type'],'video/mp4');
  assert.ok(Number(tags['og:video:width'])>0&&Number(tags['og:video:height'])>0);
  const url=hosted(tags['og:video']),head=await fetch(url,{method:'HEAD'});assert.equal(head.status,200);assert.match(head.headers.get('content-type')||'',/^video\/mp4/);
  const size=Number(head.headers.get('content-length'));assert.ok(size>1024,'Video Content-Length missing/too small');
  const range=await fetch(url,{headers:{Range:'bytes=0-1023'}});assert.equal(range.status,206,'Server must actually support byte ranges');
  assert.equal(range.headers.get('content-range'),`bytes 0-1023/${size}`);
  const bytes=new Uint8Array(await range.arrayBuffer());assert.equal(bytes.length,1024);
  assert.equal(new TextDecoder().decode(bytes.slice(4,8)),'ftyp','Range must contain MP4 bytes, not HTML/auth redirect');
  console.log(JSON.stringify({origin:origin.origin,video:url.href,poster:hosted(tags['og:image']).href,bytes:size,width:Number(tags['og:video:width']),height:Number(tags['og:video:height']),rangeStatus:range.status},null,2));
}
