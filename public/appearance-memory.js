import { TextureUtils } from 'three';

// Same upload key as the vendored WebGLTextures. UV transforms are uniforms:
// GLTFLoader's KHR_texture_transform clones keep the same Texture.Source.
export function appearanceTextureUploadKey(texture) {
  return [texture.wrapS, texture.wrapT, texture.wrapR || 0,
    texture.magFilter, texture.minFilter, texture.anisotropy, texture.internalFormat,
    texture.format, texture.type, texture.generateMipmaps, texture.premultiplyAlpha,
    texture.flipY, texture.unpackAlignment, texture.colorSpace].join();
}

export function estimateAppearanceBytes(model) {
  const attributes = new Set(), uploads = new Map();
  let bytes = 0;
  function attribute(value) {
    if (!value) return;
    const buffer = value.isInterleavedBufferAttribute ? value.data : value;
    if (attributes.has(buffer)) return;
    attributes.add(buffer);
    bytes += buffer.array?.byteLength || 0;
  }
  model.traverse(object => {
    const geometry = object.geometry;
    if (geometry) {
      attribute(geometry.index);
      for (const value of Object.values(geometry.attributes)) attribute(value);
      for (const values of Object.values(geometry.morphAttributes)) values.forEach(attribute);
    }
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      if (!material) continue;
      for (const texture of Object.values(material)) {
        if (!texture?.isTexture) continue;
        const source = texture.source, key = appearanceTextureUploadKey(texture);
        if (!uploads.has(source)) uploads.set(source, new Set());
        if (uploads.get(source).has(key)) continue;
        uploads.get(source).add(key);
        if (texture.isCompressedTexture) {
          for (const mip of texture.mipmaps) bytes += mip.data.byteLength;
          continue;
        }
        const image = texture.image;
        if (!image?.width || !image?.height) continue;
        let width = image.width, height = image.height;
        while (true) {
          bytes += TextureUtils.getByteLength(width, height, texture.format, texture.type);
          if (!texture.generateMipmaps || (width === 1 && height === 1)) break;
          width = Math.max(1, Math.floor(width / 2));
          height = Math.max(1, Math.floor(height / 2));
        }
      }
    }
  });
  return bytes;
}
