// Written by AI on 2026-10-26 by model GPT-6.
import { build } from 'esbuild';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const out = path.resolve(process.argv[2]);
const dist = path.join(out, 'dist');
await mkdir(path.join(dist, 'server'), { recursive: true });
await mkdir(path.join(dist, '.openai'), { recursive: true });
const hosting = JSON.parse(await readFile(new URL('../.openai/hosting.json', import.meta.url)));
delete hosting.static;
for (const directory of [out, dist]) {
  await mkdir(path.join(directory, '.openai'), { recursive: true });
  await writeFile(path.join(directory, '.openai/hosting.json'), JSON.stringify(hosting, null, 2) + '\n');
}
await build({ entryPoints: [fileURLToPath(new URL('./index.js', import.meta.url))],
  outfile: path.join(dist, 'server/index.js'), bundle: true, minify: true,
  format: 'esm', target: 'es2022', platform: 'browser',
  define: { 'globalThis.SITE_BUILD': JSON.stringify(process.env.SITE_BUILD ?? new Date().toISOString()) } });
await writeFile(path.join(dist, 'server/wrangler.json'), JSON.stringify({
  name: 'rotterdam-010', main: 'index.js', compatibility_date: '2026-05-22',
  assets: { directory: '../client', binding: 'ASSETS', html_handling: 'auto-trailing-slash',
    not_found_handling: 'none', run_worker_first: ['/api/*', '/pyramids/*'] },
}, null, 2) + '\n');
console.log(`Worker: ${dist}/server/index.js; static assets: ${dist}/client`);
