import { readdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { gzipSync } from 'node:zlib';

let models = 0, sourceBytes = 0, compressedBytes = 0;
async function compressDirectory(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const filename = join(directory, entry.name);
    if (entry.isDirectory()) await compressDirectory(filename);
    else if (entry.name.endsWith('.glb')) {
      const source = await readFile(filename), compressed = gzipSync(source);
      await writeFile(`${filename}.gz`, compressed);
      models++; sourceBytes += source.length; compressedBytes += compressed.length;
    }
  }
}
await compressDirectory(join(process.argv[2] || 'dist/client', 'data'));
console.log(`Prepared ${models} lossless model sidecars: ${sourceBytes} → ${compressedBytes} bytes.`);
