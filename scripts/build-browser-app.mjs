#!/usr/bin/env node
// Written by AI on 2026-10-24 by model GPT-6 Astra.
// Run after vinext build; direct-module source previews remain unchanged.
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';
import { build } from 'vite';

const projectDirectory = fileURLToPath(new URL('../', import.meta.url));
const sourceDirectory = path.join(projectDirectory, 'public');
const outputDirectory = path.resolve(projectDirectory, process.argv[2] || 'dist/client');
const htmlPath = path.join(outputDirectory, 'index.html');
const html = await readFile(htmlPath, 'utf8');
const entryScript = /<script type="module" src="\.\/(?:app\.js|assets\/app-[^"/]+\.js)"><\/script>/;
if (!entryScript.test(html)) throw new Error('Generated index.html has no recognised browser entry script');

const result = await build({
  configFile: false,
  root: sourceDirectory,
  publicDir: false,
  resolve: {
    alias: [
      { find: /^three\/addons\//, replacement: path.join(sourceDirectory, 'vendor/three/examples/jsm/') },
      { find: /^three$/, replacement: path.join(sourceDirectory, 'vendor/three/build/three.module.js') },
      { find: /^3d-tiles-renderer$/, replacement: path.join(sourceDirectory, 'vendor/3d-tiles-renderer/build/index.three.js') },
    ],
  },
  build: {
    outDir: outputDirectory,
    emptyOutDir: false,
    minify: true,
    rolldownOptions: {
      input: path.join(sourceDirectory, 'app.js'),
      output: {
        comments: { legal: true },
        banner: '/*! Vendored dependency licenses: /vendor/three/LICENSE and /vendor/3d-tiles-renderer/LICENSE. */',
      },
    },
  },
});

const outputs = (Array.isArray(result) ? result : [result]).flatMap(bundle => bundle.output);
const entry = outputs.find(output => output.type === 'chunk' && output.isEntry);
if (!entry) throw new Error('Vite did not produce a browser entry chunk');
await writeFile(htmlPath, html.replace(entryScript, `<script type="module" src="./${entry.fileName}"></script>`));

for (const output of outputs) {
  if (output.type !== 'chunk') continue;
  console.log(`${output.fileName}: ${Buffer.byteLength(output.code)} bytes, ${gzipSync(output.code).length} bytes gzip; ${output.imports.length} static imports, ${output.dynamicImports.length} lazy imports.`);
}
