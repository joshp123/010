export const compressedModelDirectories = new Set(['industrial-structures', 'industrial-terrain', 'lamps', 'supplementary-lamps', 'streets', 'bridge-surfaces']);

async function fetchPreparedModel(url, options) {
  const compressedURL = new URL(url);
  compressedURL.pathname += '.gz';
  const response = await fetch(compressedURL, options);
  // The source preview has raw models; sidecars are generated only by the build.
  if (response.status === 404) return fetch(url, options);
  if (!response.ok) return response;
  return new Response(response.body.pipeThrough(new DecompressionStream('gzip')));
}

export function createCompressedModelsPlugin() {
  return {
    name: 'Lossless prepared model transfers',
    fetchData(uri, options) {
      if (typeof DecompressionStream === 'undefined') return null;
      const url = new URL(uri, location.href);
      if (url.origin !== location.origin || !url.pathname.startsWith('/data/') || !url.pathname.endsWith('.glb')) return null;
      if (!compressedModelDirectories.has(url.pathname.split('/')[2])) return null;
      return fetchPreparedModel(url, options);
    },
  };
}
