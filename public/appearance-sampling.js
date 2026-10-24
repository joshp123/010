import * as THREE from 'three';

// Review-only controlled sampler changes. No images, UVs, materials or lighting
// are replaced. Caller owns view locking, render requests and screenshot review.
export function setAppearanceSampling(models, { renderer, preset = 'baseline' } = {}) {
  if (!['baseline', 'linear', 'anisotropic'].includes(preset)) throw new Error(`Unknown appearance sampling preset: ${preset}`);
  const reported = Number(renderer?.capabilities?.getMaxAnisotropy?.() ?? 1);
  const supported = Number.isFinite(reported) ? Math.max(1, Math.floor(reported)) : 1;
  const anisotropy = preset === 'anisotropic' ? Math.min(8, supported) : 1;
  const magFilter = preset === 'baseline' ? THREE.NearestFilter : THREE.LinearFilter;
  const seen = new Set(); let changed = 0;
  for (const model of models) model?.traverse(mesh => {
    if (!mesh.isMesh) return;
    for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      const texture = material.map;
      if (!texture || seen.has(texture)) continue;
      seen.add(texture);
      // Vendored Three disables anisotropy with NearestFilter magnification.
      // The linear control isolates that change from anisotropy itself.
      if (texture.magFilter !== magFilter || texture.minFilter !== THREE.LinearMipmapLinearFilter || texture.anisotropy !== anisotropy) {
        texture.magFilter = magFilter;
        texture.minFilter = THREE.LinearMipmapLinearFilter;
        texture.anisotropy = anisotropy;
        texture.needsUpdate = true;
        changed++;
      }
    }
  });
  return { preset, textures: seen.size, changed, supportedAnisotropy: supported, appliedAnisotropy: anisotropy, magFilter: preset === 'baseline' ? 'nearest' : 'linear', minFilter: 'linear-mipmap-linear', mipmapsPreserved: true };
}
