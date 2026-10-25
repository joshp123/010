// Written by AI on 2026-10-25 by model GPT-6.
// Decode baked custom attributes using the browser's actual MeshoptDecoder.
import fs from 'node:fs';
import { MeshoptDecoder } from '../../web/vendor/three/examples/jsm/libs/meshopt_decoder.module.js';
await MeshoptDecoder.ready;
const file = fs.readFileSync(process.argv[2]);
const jsonLength = file.readUInt32LE(12);
const document = JSON.parse(file.subarray(20, 20 + jsonLength));
const binary = file.subarray(28 + jsonLength);
const values = new Set();
for (const mesh of document.meshes) {
  for (const primitive of mesh.primitives) {
    const accessor = document.accessors[primitive.attributes[process.argv[3]]];
    const view = document.bufferViews[accessor.bufferView];
    const compression = view.extensions.EXT_meshopt_compression;
    const decoded = new Uint8Array(compression.count * compression.byteStride);
    MeshoptDecoder.decodeGltfBuffer(decoded, compression.count, compression.byteStride,
      binary.subarray(compression.byteOffset, compression.byteOffset + compression.byteLength),
      compression.mode, compression.filter);
    const data = new DataView(decoded.buffer);
    for (let index = 0; index < accessor.count; index++) {
      const value = data.getFloat32((accessor.byteOffset ?? 0) + index * view.byteStride, true);
      if (!Number.isInteger(value)) throw new Error('Custom attribute lost integer precision');
      values.add(value);
    }
  }
}
console.log(JSON.stringify([...values].sort((a, b) => a - b)));
