import { readdir, readFile, writeFile, unlink } from 'node:fs/promises';
import { join } from 'node:path';
import { gzipSync } from 'node:zlib';
import { compressedModelDirectories } from '../public/compressed-models.js';

let models = 0, sourceBytes = 0, compressedBytes = 0;
async function compressDirectory(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const filename = join(directory, entry.name);
    if (entry.isDirectory()) await compressDirectory(filename);
    else if (entry.name.endsWith('.glb')) {
      const source = await readFile(filename), compressed = gzipSync(source);
      await writeFile(`${filename}.gz`, compressed);
      // All consumers use the compressed-model plugin; public source stays intact.
      await unlink(filename);
      models++; sourceBytes += source.length; compressedBytes += compressed.length;
    }
  }
}
for (const directory of compressedModelDirectories) await compressDirectory(join(process.argv[2] || 'dist/client', 'data', directory));
console.log(`Prepared ${models} lossless models without raw build duplicates: ${sourceBytes} → ${compressedBytes} bytes.`);
