// Written by AI on 2026-10-25 by model GPT-6.
// Build-only: source models remain intact. Every replacement decodes identically.
import { createHash } from 'node:crypto';
import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';

const outputDirectory = path.resolve(process.argv[2] || 'dist/client');
const modelDirectory = path.join(outputDirectory, 'data/illustrated-neighbourhood');
const textureDirectory = path.join(modelDirectory, 'shared-textures');
const sharedImages = new Map();
let embeddedBytes = 0, sharedBytes = 0, modelCount = 0, webpCount = 0;
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const alignFour = length => (length + 3) & ~3;

async function shareImage(bytes, mimeType) {
  const sourceHash = digest(bytes);
  if (sharedImages.has(sourceHash)) return sharedImages.get(sourceHash);
  let encoded = bytes, extension = mimeType === 'image/jpeg' ? 'jpg' : 'png';
  if (mimeType === 'image/png') {
    const candidate = await sharp(bytes).keepIccProfile().webp({ lossless: true, effort: 6 }).toBuffer();
    if (candidate.length < bytes.length) {
      const original = await sharp(bytes).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
      const decoded = await sharp(candidate).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
      if (original.info.width === decoded.info.width && original.info.height === decoded.info.height && original.data.equals(decoded.data)) {
        encoded = candidate;
        extension = 'webp';
        webpCount++;
      }
    }
  } else if (mimeType !== 'image/jpeg') {
    throw new Error(`Unsupported embedded image type: ${mimeType}`);
  }
  const filename = path.join(textureDirectory, `${digest(encoded)}.${extension}`);
  await writeFile(filename, encoded);
  const result = { filename, webp: extension === 'webp' };
  sharedImages.set(sourceHash, result);
  sharedBytes += encoded.length;
  return result;
}

function remapBufferViewReferences(value, indices) {
  if (!value || typeof value !== 'object') return;
  for (const [key, child] of Object.entries(value)) {
    if (key === 'bufferView') {
      if (!indices.has(child)) throw new Error(`Removed buffer view is still referenced: ${child}`);
      value[key] = indices.get(child);
    } else remapBufferViewReferences(child, indices);
  }
}

async function rewriteModel(filename) {
  const input = await readFile(filename);
  if (input.toString('ascii', 0, 4) !== 'glTF' || input.readUInt32LE(4) !== 2) throw new Error(`Invalid GLB: ${filename}`);
  const documentLength = input.readUInt32LE(12);
  const document = JSON.parse(input.toString('utf8', 20, 20 + documentLength).trim());
  if (!document.images?.some(image => image.bufferView !== undefined)) return;
  const binaryHeader = 20 + documentLength;
  const binary = input.subarray(binaryHeader + 8, binaryHeader + 8 + input.readUInt32LE(binaryHeader));
  const imageBufferViews = new Set();
  const webpImages = new Set();
  for (const [index, image] of document.images.entries()) {
    if (image.bufferView === undefined) continue;
    const view = document.bufferViews[image.bufferView];
    const imageBytes = binary.subarray(view.byteOffset || 0, (view.byteOffset || 0) + view.byteLength);
    embeddedBytes += imageBytes.length;
    const shared = await shareImage(imageBytes, image.mimeType);
    imageBufferViews.add(image.bufferView);
    image.uri = path.relative(path.dirname(filename), shared.filename).split(path.sep).join('/');
    delete image.bufferView;
    delete image.mimeType;
    if (shared.webp) webpImages.add(index);
  }
  for (const texture of document.textures || []) {
    if (!webpImages.has(texture.source)) continue;
    texture.extensions = { ...texture.extensions, EXT_texture_webp: { source: texture.source } };
    delete texture.source;
  }
  if (webpImages.size) {
    document.extensionsUsed = [...new Set([...(document.extensionsUsed || []), 'EXT_texture_webp'])];
    document.extensionsRequired = [...new Set([...(document.extensionsRequired || []), 'EXT_texture_webp'])];
  }
  // Retain any image view also used as geometry rather than assume exclusivity.
  const geometryReferences = new Set();
  function collectReferences(value) {
    if (!value || typeof value !== 'object') return;
    for (const [key, child] of Object.entries(value)) {
      if (key === 'bufferView') geometryReferences.add(child);
      else collectReferences(child);
    }
  }
  collectReferences({ ...document, bufferViews: undefined });
  const viewIndices = new Map(), views = [], chunks = [];
  let binaryLength = 0;
  for (const [index, view] of document.bufferViews.entries()) {
    if (imageBufferViews.has(index) && !geometryReferences.has(index)) continue;
    if ((view.buffer || 0) !== 0) throw new Error(`Multiple GLB buffers unsupported: ${filename}`);
    viewIndices.set(index, views.length);
    const bytes = binary.subarray(view.byteOffset || 0, (view.byteOffset || 0) + view.byteLength);
    views.push({ ...view, byteOffset: binaryLength });
    chunks.push(bytes, Buffer.alloc(alignFour(bytes.length) - bytes.length));
    binaryLength += alignFour(bytes.length);
  }
  document.bufferViews = views;
  remapBufferViewReferences(document, viewIndices);
  document.buffers[0].byteLength = binaryLength;
  const json = Buffer.from(JSON.stringify(document));
  const paddedJson = Buffer.concat([json, Buffer.alloc(alignFour(json.length) - json.length, 32)]);
  const header = Buffer.alloc(20), binaryChunkHeader = Buffer.alloc(8);
  header.write('glTF'); header.writeUInt32LE(2, 4);
  header.writeUInt32LE(28 + paddedJson.length + binaryLength, 8);
  header.writeUInt32LE(paddedJson.length, 12); header.write('JSON', 16);
  binaryChunkHeader.writeUInt32LE(binaryLength); binaryChunkHeader.writeUInt32LE(0x004e4942, 4);
  await writeFile(filename, Buffer.concat([header, paddedJson, binaryChunkHeader, ...chunks]));
  modelCount++;
}

async function visit(directory) {
  for (const entry of (await readdir(directory, { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name))) {
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory() && filename !== textureDirectory) await visit(filename);
    else if (entry.isFile() && entry.name.endsWith('.glb')) await rewriteModel(filename);
  }
}
await mkdir(textureDirectory, { recursive: true });
await visit(modelDirectory);
console.log(`Shared ${sharedImages.size} exact images across ${modelCount} models; ${webpCount} smaller pixel-identical WebPs. Embedded ${embeddedBytes} bytes → shared ${sharedBytes} bytes.`);
