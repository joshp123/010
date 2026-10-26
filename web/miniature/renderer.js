// Written by AI on 2026-10-25 by model Claude Opus 5.5.
// Renders the city scene (pipeline/README.md) as pixel art.
//
// The camera is orthographic and every art pixel sits on one global grid per
// bearing, so a live view (T1) and an offline pyramid tile (T2) of the same
// place produce the same pixels.

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { buildPalette, surfaceClassColours } from './palette.js';

const TILE_METRES = 250;
const CAMERA_DISTANCE = 4000;
const STREET_HEIGHT = 3; // NAP metres; the point under the screen centre is at street level

export const defaultStyle = {
  elevationDegrees: 40,
  sunAzimuthDegrees: 215,
  sunElevationDegrees: 42,
  pixelArt: true,
  outlines: true,
  dither: 0.0,
  orthoRoofs: true,
  groundPhotoDetail: 0.0,
  facadeDetail: 0.6,
  facadeWindowRatio: 0.7,
  facadeRadius: 1.0,
  roofRadius: 1.0,
  ambient: 1.25,
  saturation: 1.2,
  sun: 4.2,
};

// Screen axes for a bearing (degrees clockwise from north at the top of the
// screen) and a camera elevation. World axes: x east, y up, z south.
export function screenAxes(bearingDegrees, elevationDegrees) {
  const b = THREE.MathUtils.degToRad(bearingDegrees);
  const e = THREE.MathUtils.degToRad(elevationDegrees);
  const forward = new THREE.Vector3(Math.sin(b), 0, -Math.cos(b));
  const right = new THREE.Vector3(Math.cos(b), 0, Math.sin(b));
  const up = forward.clone().multiplyScalar(Math.sin(e)).add(new THREE.Vector3(0, Math.cos(e), 0));
  const view = forward.clone().multiplyScalar(Math.cos(e)).add(new THREE.Vector3(0, -Math.sin(e), 0));
  return { right, up, view };
}

function loadRawImageTexture(url) {
  return fetch(url)
    .then((response) => {
      if (!response.ok) throw new Error(`${url}: ${response.status}`);
      return response.blob();
    })
    .then((blob) => createImageBitmap(blob, { colorSpaceConversion: 'none', premultiplyAlpha: 'none' }))
    .then((bitmap) => {
      const texture = new THREE.Texture(bitmap);
      texture.flipY = false;
      texture.magFilter = THREE.NearestFilter;
      texture.minFilter = THREE.NearestFilter;
      texture.generateMipmaps = false;
      texture.colorSpace = THREE.NoColorSpace;
      texture.needsUpdate = true;
      return texture;
    });
}

function loadPhotoTexture(url) {
  return loadRawImageTexture(url).then((texture) => {
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.magFilter = THREE.LinearFilter;
    texture.minFilter = THREE.LinearFilter;
    return texture;
  });
}

function classColourTexture() {
  const data = new Uint8Array(32 * 4);
  for (const [index, rgb] of Object.entries(surfaceClassColours)) {
    data.set([...rgb.map((v) => Math.round(v * 255)), 255], Number(index) * 4);
  }
  const texture = new THREE.DataTexture(data, 32, 1);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

function paletteTexture() {
  const colours = buildPalette();
  const data = new Uint8Array(colours.length * 4);
  colours.forEach((rgb, i) => data.set([...rgb.map((v) => Math.round(v * 255)), 255], i * 4));
  const texture = new THREE.DataTexture(data, colours.length, 1);
  texture.needsUpdate = true;
  return { texture, size: colours.length };
}

// Injects "where am I in the tile" into a Lambert material so the fragment
// shader can read the tile's rasters at the fragment's ground position.
function withTilePosition(material, tileOffset, extraUniforms, fragmentPatch) {
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, extraUniforms, { tileOffset: { value: tileOffset } });
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', `#include <common>\nuniform vec3 tileOffset;\nvarying vec2 vTileUv;\nvarying vec3 vWorldNormalMini;\n${fragmentPatch.vertexDeclarations ?? ''}`)
      .replace('#include <worldpos_vertex>', `#include <worldpos_vertex>
        vec4 miniWorld = modelMatrix * vec4(transformed, 1.0);
        #ifdef USE_INSTANCING
          miniWorld = modelMatrix * instanceMatrix * vec4(transformed, 1.0);
        #endif
        vec3 tileLocal = miniWorld.xyz - tileOffset;
        vTileUv = vec2(tileLocal.x / ${TILE_METRES.toFixed(1)}, 1.0 + tileLocal.z / ${TILE_METRES.toFixed(1)});
        vWorldNormalMini = normalize(mat3(modelMatrix) * objectNormal);
        ${fragmentPatch.vertexBody ?? ''}`);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>\nvarying vec2 vTileUv;\nvarying vec3 vWorldNormalMini;\nuniform float dataOverlay;\nuniform float night;\nuniform sampler2D lampTexture;\nvec3 overlayCode = vec3(0.0);\nvec3 nightGlow = vec3(0.0);\n${fragmentPatch.declarations}`)
      .replace('#include <map_fragment>', `#include <map_fragment>\n${fragmentPatch.body}`)
      .replace('#include <emissivemap_fragment>', '#include <emissivemap_fragment>\ntotalEmissiveRadiance += nightGlow * night;')
      .replace('#include <opaque_fragment>', `#include <opaque_fragment>\n${fragmentPatch.overlay ?? ''}`);
  };
  material.customProgramCacheKey = () => fragmentPatch.key;
  return material;
}


const kuwaharaGlsl = `
    // Edge-preserving flattening (Kuwahara): of the four quadrants around the
    // sample, return the mean of the calmest one. Noise flattens into clean
    // patches; real edges stay sharp. Every colour still comes from the photo.
    vec3 kuwahara(sampler2D image, vec2 uv, vec2 step) {
      vec3 bestMean = vec3(0.0);
      float bestVariance = 1e9;
      for (int q = 0; q < 4; q++) {
        vec2 dir = vec2(q == 1 || q == 3 ? 1.0 : -1.0, q >= 2 ? 1.0 : -1.0);
        vec3 sum = vec3(0.0), sumSq = vec3(0.0);
        for (int j = 0; j <= 2; j++) {
          for (int i = 0; i <= 2; i++) {
            vec3 c = texture2D(image, uv + dir * vec2(float(i), float(j)) * step).rgb;
            sum += c; sumSq += c * c;
          }
        }
        vec3 mean = sum / 9.0;
        float variance = dot(sumSq / 9.0 - mean * mean, vec3(1.0));
        if (variance < bestVariance) { bestVariance = variance; bestMean = mean; }
      }
      return bestMean;
    }`;

const overlayOutput = 'if (dataOverlay > 0.5) gl_FragColor = vec4(overlayCode, 1.0);';

const groundPatch = {
  key: 'mini-ground',
  overlay: overlayOutput,
  declarations: `
    uniform sampler2D classTexture;
    uniform sampler2D classColours;
    uniform sampler2D orthoTexture;
    uniform float groundPhotoDetail;
    uniform float texelsPerArtPixel;
    int lineBitsAround(vec2 uv) {
      float step = 1.0 / 2500.0;
      float reach = max(0.0, floor(texelsPerArtPixel * 0.5));
      int bits = 0;
      for (float dy = -2.0; dy <= 2.0; dy += 1.0) {
        for (float dx = -2.0; dx <= 2.0; dx += 1.0) {
          if (abs(dx) > reach || abs(dy) > reach) continue;
          bits |= int(texture2D(classTexture, uv + vec2(dx, dy) * step).g * 255.0 + 0.5);
        }
      }
      return bits;
    }`,
  body: `
    vec2 groundUv = clamp(vTileUv, vec2(0.0002), vec2(0.9998));
    vec4 surface = texture2D(classTexture, groundUv);
    float surfaceClass = floor(surface.r * 255.0 + 0.5);
    vec3 groundColour = texture2D(classColours, vec2((surfaceClass + 0.5) / 32.0, 0.5)).rgb;
    // BGT records most private gardens as yards. Where the 2026 aerial shows
    // vegetation on a yard, unpaved or unknown surface, draw it as planted.
    if (surfaceClass == 10.0 || surfaceClass == 9.0 || surfaceClass == 0.0) {
      vec3 photo = texture2D(orthoTexture, groundUv).rgb;
      float greenness = photo.g - max(photo.r, photo.b);
      if (greenness > 0.025) {
        groundColour = texture2D(classColours, vec2((greenness > 0.07 ? 7.5 : 6.5) / 32.0, 0.5)).rgb;
      }
    }
    if (groundPhotoDetail > 0.0) {
      vec3 photo = texture2D(orthoTexture, groundUv).rgb;
      float shade = dot(photo, vec3(0.299, 0.587, 0.114)) / max(0.05, dot(groundColour, vec3(0.299, 0.587, 0.114)));
      groundColour *= mix(1.0, clamp(shade, 0.6, 1.4), groundPhotoDetail);
    }
    int lines = lineBitsAround(groundUv);
    // Markings and kerbs are narrower than an art pixel at coarse zoom; drawing
    // them there turns roads into speckle. Rails stay: they are the tram network.
    if (texelsPerArtPixel > 3.5) lines &= 3;
    if ((lines & 8) != 0) groundColour = mix(groundColour, vec3(0.80, 0.78, 0.72), 0.7);
    if ((lines & 4) != 0) groundColour = vec3(0.93, 0.92, 0.86);
    if ((lines & 3) != 0) groundColour = vec3(0.30, 0.29, 0.30);
    // Data overlay: which line features are at this pixel, as pure colours,
    // for compositing data back over a painted image.
    if ((lines & 8) != 0) overlayCode = vec3(0.0, 0.0, 1.0);
    if ((lines & 4) != 0) overlayCode = vec3(0.0, 1.0, 0.0);
    if ((lines & 3) != 0) overlayCode = vec3(1.0, 0.0, 0.0);
    if (surfaceClass == 8.0) {
      // Water: lighter towards quays, with drawn ripples on a 5 m grid.
      vec2 metres = vTileUv * ${TILE_METRES.toFixed(1)};
      vec2 cell = floor(metres / vec2(2.5, 1.25));
      float pick = fract(sin(dot(cell, vec2(12.9898, 78.233))) * 43758.5453);
      float dash = step(0.86, pick) * step(fract(metres.x / 2.5), 0.6) * step(fract(metres.y / 1.25), 0.3);
      groundColour = mix(groundColour, vec3(0.55, 0.72, 0.80), dash * 0.6);
    }
    diffuseColor.rgb = groundColour;
    // Street lamps from the municipal register light pools on the ground.
    float lampLight = texture2D(lampTexture, groundUv).r;
    nightGlow = groundColour * vec3(1.0, 0.80, 0.55) * lampLight * 1.9;
    if (surfaceClass == 8.0) nightGlow += vec3(1.0, 0.75, 0.45) * lampLight * 0.25;`,
};

const buildingPatch = {
  key: 'mini-building',
  overlay: overlayOutput,
  vertexDeclarations: `
    attribute float _feature_id_0;
    uniform sampler2D featureTexture;
    uniform float featureCount;
    varying vec4 vFeature;
    varying vec3 vWorldPosMini;`,
  vertexBody: `
    vFeature = texture2D(featureTexture, vec2((_feature_id_0 + 0.5) / max(1.0, featureCount), 0.5));
    vWorldPosMini = miniWorld.xyz;`,
  declarations: `
    varying vec4 vFeature;
    varying vec3 vWorldPosMini;
    // Share of windows lit late in the evening, by BAG use: homes are lit
    // irregularly, offices mostly dark, shops show their ground floor.
    vec3 windowLight(bool isWindow, float pick, float heightAboveBase, float use) {
      if (!isWindow) return vec3(0.0);
      bool shopFloor = abs(use - 3.0) < 0.5 && heightAboveBase < 4.5;
      float share = shopFloor ? 0.7 : abs(use - 2.0) < 0.5 ? 0.08 : abs(use - 1.0) < 0.5 ? 0.24 : use < 0.5 ? 0.16 : 0.06;
      if (pick > share) return vec3(0.0);
      vec3 warm = mix(vec3(1.0, 0.72, 0.38), vec3(1.0, 0.86, 0.60), fract(pick * 7.13));
      vec3 cool = vec3(0.80, 0.88, 1.0);
      return (abs(use - 2.0) < 0.5 || shopFloor ? cool * 0.85 : warm * 0.95);
    }
    uniform sampler2D orthoTexture;
    uniform float orthoRoofs;
    uniform float facadeDetail;
    uniform float facadeWindowRatio;
    uniform float facadeRadius;
    uniform float roofRadius;
    ${kuwaharaGlsl}`,
  body: `
    if (orthoRoofs > 0.5 && vWorldNormalMini.y > 0.55) {
      vec2 roofUv = clamp(vTileUv, vec2(0.0002), vec2(0.9998));
      diffuseColor.rgb = kuwahara(orthoTexture, roofUv, roofRadius / vec2(textureSize(orthoTexture, 0)));
    } else {
      vec3 luma = vec3(0.299, 0.587, 0.114);
      #ifdef USE_MAP
        vec3 bestMean = kuwahara(map, vMapUv, facadeRadius / vec2(textureSize(map, 0)));
        vec3 wall = 1.0 - pow(1.0 - bestMean, vec3(1.5));
        diffuseColor.rgb = mix(vec3(dot(wall, luma)), wall, 1.3);
        // At night only real windows can light: places where the photo is
        // clearly darker than its own wall. Which ones are lit depends on the
        // building's use, and varies window by window.
        if (night > 0.0 && vWorldNormalMini.y < 0.3) {
          vec3 wallTone = texture2D(map, vMapUv, 5.0).rgb;
          float darker = dot(bestMean, luma) / max(0.03, dot(wallTone, luma));
          // Rooms, not pixels: one choice per 2.4 m of wall per storey.
          vec2 alongDir = normalize(vec2(-vWorldNormalMini.z, vWorldNormalMini.x) + 1e-5);
          float storeyH = (vFeature.z > 0.0 && vFeature.z < 1945.0) ? 3.3 : 3.0;
          vec2 room = vec2(floor(dot(vWorldPosMini.xz, alongDir) / 2.4), floor((vWorldPosMini.y - vFeature.x) / storeyH));
          float pick = fract(sin(dot(room + vFeature.xy * 0.37, vec2(12.9898, 78.233))) * 43758.5453);
          nightGlow = windowLight(darker < 0.62, pick, vWorldPosMini.y - vFeature.x, vFeature.w);
        }
      #else
        // No photo: a facade from facts only, deliberately plainer than a
        // photographed one. Construction year sets the storey height and the
        // material family; use sets the window rhythm. Nothing else is drawn.
        float base = vFeature.x, height = vFeature.y, year = vFeature.z, use = vFeature.w;
        // Year only hints at material, so the tones stay close to neutral:
        // a wrong guess must read as plain, never as a confident colour.
        vec3 wall = year <= 0.0 ? vec3(0.74, 0.71, 0.66)
          : year < 1945.0 ? vec3(0.66, 0.58, 0.53)
          : year < 1975.0 ? vec3(0.74, 0.72, 0.67)
          : vec3(0.70, 0.67, 0.62);
        float storey = (year > 0.0 && year < 1945.0) ? 3.3 : 2.9;
        float h = vWorldPosMini.y - base;
        vec2 along2 = normalize(vec2(-vWorldNormalMini.z, vWorldNormalMini.x));
        float along = dot(vWorldPosMini.xz, along2);
        float inStorey = mod(h, storey);
        bool office = abs(use - 2.0) < 0.5;
        float pitch = office ? 1.8 : 2.7, width = office ? 1.5 : 1.1;
        bool windowRow = h > 0.6 && height - h > 0.9 && inStorey > 0.9 && inStorey < 2.2;
        bool windowColumn = mod(along, pitch) < width;
        if (height > 0.0 && windowRow && windowColumn) wall = mix(wall, vec3(0.20, 0.24, 0.30), 0.5);
        diffuseColor.rgb = wall;
        if (night > 0.0 && vWorldNormalMini.y < 0.3) {
          float pick = fract(sin(dot(vec2(floor(along / pitch), floor(h / storey)) + vFeature.xy, vec2(12.9898, 78.233))) * 43758.5453);
          nightGlow = windowLight(height > 0.0 && windowRow && windowColumn, pick, h, use);
        }
      #endif
    }
    if (vWorldNormalMini.y > 0.55) diffuseColor.rgb = mix(diffuseColor.rgb, diffuseColor.rgb * 1.15, 0.5);`,
};

const postFragment = `
  precision highp float;
  uniform sampler2D colourTexture;
  uniform sampler2D depthTexture;
  uniform sampler2D normalTexture;
  uniform sampler2D palette;
  uniform float paletteSize;
  uniform vec2 resolution;
  uniform float pixelArt;
  uniform float outlines;
  uniform float dither;
  uniform float depthScale;
  uniform float metresPerPixel;
  uniform float saturation;
  uniform float depthOutput;
  uniform vec3 background;
  in vec2 vUv;
  out vec4 fragColour;

  vec3 toLinear(vec3 c) { return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c)); }
  vec3 toOklab(vec3 srgb) {
    vec3 c = toLinear(srgb);
    float l = 0.4122214708 * c.r + 0.5363325363 * c.g + 0.0514459929 * c.b;
    float m = 0.2119034982 * c.r + 0.6806995451 * c.g + 0.1073969566 * c.b;
    float s = 0.0883024619 * c.r + 0.2817188376 * c.g + 0.6299787005 * c.b;
    l = pow(l, 1.0 / 3.0); m = pow(m, 1.0 / 3.0); s = pow(s, 1.0 / 3.0);
    return vec3(0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
                1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
                0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s);
  }
  float bayer4(vec2 p) {
    int x = int(mod(p.x, 4.0)), y = int(mod(p.y, 4.0));
    int index = x + y * 4;
    int m[16] = int[16](0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5);
    return float(m[index]) / 16.0 - 0.5;
  }
  float depthAt(vec2 uv) { return texture(depthTexture, uv).r * depthScale; }

  void main() {
    vec2 texel = 1.0 / resolution;
    // The scene renders into a linear buffer; everything below works in sRGB.
    vec3 linearColour = texture(colourTexture, vUv).rgb;
    vec3 colour = mix(linearColour * 12.92, 1.055 * pow(linearColour, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, linearColour));
    float depth = depthAt(vUv);
    if (depthOutput > 0.5) {
      // Depth tiles for live layers: distance from the camera in 10 cm units
      // above 1000 m, as 16 bits in red (high) and green (low). 0 = nothing.
      if (depth >= depthScale * 0.999) { fragColour = vec4(0.0, 0.0, 0.0, 1.0); return; }
      float units = clamp((depth - 1000.0) * 10.0, 1.0, 65535.0);
      fragColour = vec4(floor(units / 256.0) / 255.0, mod(units, 256.0) / 255.0, 0.0, 1.0);
      return;
    }
    if (depth >= depthScale * 0.999) {
      // Background stays exactly the page colour, so tile edges never show.
      fragColour = vec4(background, 1.0);
      return;
    }
    // At coarse scales neighbouring pixels are metres apart in depth; outline
    // only real object edges, and drop inner creases once they are sub-pixel.
    float edgeDepth = max(1.6, 4.0 * metresPerPixel);
    if (outlines > 0.5) {
      vec3 normal = texture(normalTexture, vUv).xyz * 2.0 - 1.0;
      float silhouette = 0.0, crease = 0.0;
      vec2 offsets[4] = vec2[4](vec2(1, 0), vec2(-1, 0), vec2(0, 1), vec2(0, -1));
      for (int i = 0; i < 4; i++) {
        vec2 uv = vUv + offsets[i] * texel;
        float neighbourDepth = depthAt(uv);
        // Outline belongs to the nearer surface, so objects keep their size.
        vec3 neighbourNormal = texture(normalTexture, uv).xyz * 2.0 - 1.0;
        // Two parallel surfaces a little apart (tile joins, kerbs, quay steps)
        // are not an object edge; anything taller than a storey is.
        bool parallelStep = dot(normal, neighbourNormal) > 0.98 && neighbourDepth - depth < edgeDepth + 1.0;
        if (neighbourDepth - depth > edgeDepth && !parallelStep) silhouette = 1.0;
        if (metresPerPixel < 1.0 && dot(normal, neighbourNormal) < 0.75 && abs(neighbourDepth - depth) < edgeDepth) crease = 1.0;
      }
      if (silhouette > 0.5) colour = colour * vec3(0.36, 0.36, 0.44);
      else if (crease > 0.5) colour = colour * 0.80;
    }
    float grey = dot(colour, vec3(0.299, 0.587, 0.114));
    colour = clamp(mix(vec3(grey), colour, saturation), 0.0, 1.0);
    if (pixelArt > 0.5) {
      vec3 target = toOklab(clamp(colour + dither * 0.06 * bayer4(gl_FragCoord.xy), 0.0, 1.0));
      float best = 1e9;
      vec3 chosen = colour;
      for (float i = 0.0; i < 256.0; i += 1.0) {
        if (i >= paletteSize) break;
        vec3 candidate = texture(palette, vec2((i + 0.5) / paletteSize, 0.5)).rgb;
        vec3 d = toOklab(candidate) - target;
        float distance = dot(d, d * vec3(1.0, 1.3, 1.3));
        if (distance < best) { best = distance; chosen = candidate; }
      }
      colour = chosen;
    }
    fragColour = vec4(colour, 1.0);
  }`;

export class Miniature {
  constructor(canvas, { sceneBase, manifest, area = 'core', style = {} }) {
    this.canvas = canvas;
    this.sceneBase = sceneBase;
    this.manifest = manifest;
    this.style = { ...defaultStyle, ...style };
    this.tileList = Object.keys(manifest.tiles).map((id) => {
      const [, x, y] = id.match(/^x(\d+)_y(\d+)$/);
      return { id, x_min: Number(x), y_min: Number(y) };
    });
    const bounds = manifest.area?.[area]?.bounds_rd;
    if (bounds) {
      this.tileList = this.tileList.filter((t) => t.x_min >= bounds[0] && t.y_min >= bounds[1] && t.x_min < bounds[2] && t.y_min < bounds[3]);
    }
    // A fixed origin keeps every coordinate small; it does not move when the area grows.
    this.origin = { x: 89750, y: 435250 };
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(1);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0xc9d3dd);
    this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, CAMERA_DISTANCE * 2);
    this.hemisphere = new THREE.HemisphereLight(0xdfe8ff, 0x6f6450, this.style.ambient);
    this.sun = new THREE.DirectionalLight(0xfff0d8, this.style.sun);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(4096, 4096);
    this.sun.shadow.bias = -0.0004;
    this.sun.shadow.normalBias = 0.25;
    this.scene.add(this.hemisphere, this.sun, this.sun.target);
    this.classColours = classColourTexture();
    this.palette = paletteTexture();
    this.normalMaterial = new THREE.MeshNormalMaterial();
    this.tiles = new Map();
    this.overlayUniform = { value: 0 };
    this.nightUniform = { value: 0 };
    this.blankLamps = new THREE.DataTexture(new Float32Array(4), 1, 1, THREE.RGBAFormat, THREE.FloatType);
    this.blankLamps.needsUpdate = true;
    this.view = { x: 0, y: 0, bearing: 0, metresPerPixel: 0.3, width: 256, height: 256 };
    this.setupPost();
  }

  setupPost() {
    const target = () => new THREE.WebGLRenderTarget(1, 1, { minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, type: THREE.HalfFloatType });
    this.colourTarget = target();
    this.colourTarget.depthTexture = new THREE.DepthTexture(1, 1);
    this.colourTarget.depthTexture.type = THREE.FloatType;
    this.normalTarget = target();
    this.postMaterial = new THREE.ShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: 'out vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }',
      fragmentShader: postFragment,
      uniforms: {
        colourTexture: { value: this.colourTarget.texture },
        depthTexture: { value: this.colourTarget.depthTexture },
        normalTexture: { value: this.normalTarget.texture },
        palette: { value: this.palette.texture },
        paletteSize: { value: this.palette.size },
        resolution: { value: new THREE.Vector2(1, 1) },
        pixelArt: { value: 1 },
        outlines: { value: 1 },
        dither: { value: 0.35 },
        depthScale: { value: CAMERA_DISTANCE * 2 },
        metresPerPixel: { value: 0.3 },
        saturation: { value: 1.2 },
        depthOutput: { value: 0 },
        background: { value: new THREE.Vector3(0xc9 / 255, 0xd3 / 255, 0xdd / 255) },
      },
    });
    this.postScene = new THREE.Scene();
    this.postScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.postMaterial));
    this.postCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  }

  tileOffset(tile) {
    return new THREE.Vector3(tile.x_min - this.origin.x, 0, -(tile.y_min - this.origin.y));
  }

  async loadTile(tile) {
    if (this.tiles.has(tile.id)) return this.tiles.get(tile.id);
    const base = `${this.sceneBase}/tiles/${tile.id}`;
    const offset = this.tileOffset(tile);
    const group = new THREE.Group();
    group.position.copy(offset);
    const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
    const optional = (promise) => promise.catch((error) => { console.warn(error.message ?? error); return null; });
    const [ground, buildings, classTexture, orthoTexture, objects] = await Promise.all([
      optional(loader.loadAsync(`${base}/ground.glb`)),
      optional(loader.loadAsync(`${base}/buildings.glb`)),
      optional(loadRawImageTexture(`${base}/classes.png`)),
      optional(loadPhotoTexture(`${base}/ortho.jpg`)),
      optional(fetch(`${base}/objects.json`).then((r) => (r.ok ? r.json() : null))),
    ]);
    const shared = {
      orthoTexture: { value: orthoTexture },
      orthoRoofs: { value: this.style.orthoRoofs ? 1 : 0 },
      facadeDetail: { value: this.style.facadeDetail },
      facadeWindowRatio: { value: this.style.facadeWindowRatio },
      facadeRadius: { value: this.style.facadeRadius },
      roofRadius: { value: this.style.roofRadius },
      groundPhotoDetail: { value: this.style.groundPhotoDetail },
      texelsPerArtPixel: { value: this.view.metresPerPixel / 0.1 },
      classTexture: { value: classTexture },
      classColours: { value: this.classColours },
      dataOverlay: this.overlayUniform,
      night: this.nightUniform,
      lampTexture: { value: this.blankLamps },
    };
    if (classTexture) {
      const groundMaterial = withTilePosition(new THREE.MeshLambertMaterial({ color: 0xffffff }), offset, shared, groundPatch);
      const heights = [];
      if (ground) {
        ground.scene.traverse((node) => {
          if (!node.isMesh) return;
          node.material = groundMaterial;
          node.receiveShadow = true;
          const positions = node.geometry.attributes.position;
          for (let i = 0; i < positions.count; i += 7) heights.push(positions.getY(i));
        });
        group.add(ground.scene);
      }
      // Where the source ground has holes, a flat underlay still shows the BGT
      // surface classes. It sits just below the lowest real surface (the water
      // or the lowest street), so it never pokes up through real ground at a
      // tile join; holes read as slightly sunken rather than as raised slabs.
      heights.sort((a, b) => a - b);
      const lampHeights = (objects?.lamps ?? []).map((lamp) => lamp.z).sort((a, b) => a - b);
      const lowest = heights.length ? heights[Math.floor(heights.length * 0.02)] : lampHeights[0] ?? 0;
      const streetHeight = Math.min(lowest, lampHeights.length ? lampHeights[0] : lowest);
      const underlay = new THREE.Mesh(new THREE.PlaneGeometry(TILE_METRES, TILE_METRES).rotateX(-Math.PI / 2), groundMaterial);
      underlay.position.set(TILE_METRES / 2, streetHeight - 0.25, -TILE_METRES / 2);
      underlay.receiveShadow = true;
      group.add(underlay);
    }
    if (buildings) {
      Object.assign(shared, this.featureTexture(buildings));
      buildings.scene.traverse((node) => {
        if (!node.isMesh) return;
        const source = node.material;
        const material = new THREE.MeshLambertMaterial({ color: source.map ? 0xffffff : 0xd9cfc0, map: source.map ?? null });
        if (material.map) material.map.colorSpace = THREE.SRGBColorSpace;
        node.material = orthoTexture ? withTilePosition(material, offset, shared, buildingPatch) : material;
        node.castShadow = true;
        node.receiveShadow = true;
      });
      group.add(buildings.scene);
    }
    if (objects?.trees?.length) group.add(this.treeMesh(objects.trees, offset));
    group.updateMatrixWorld(true);
    this.scene.add(group);
    const record = { group, shared, lamps: objects?.lamps ?? [] };
    if (objects?.lamps?.length) group.add(this.lampHeads(objects.lamps, offset));
    this.tiles.set(tile.id, record);
    return record;
  }

  // Each tree is a few overlapping leaf clumps placed by a hash of its
  // position, so the same tree always looks the same. Size comes from data.
  // Per-building facts for the shader: base height, height, construction
  // year and use, one texel per feature in the tile's feature table.
  featureTexture(buildings) {
    const features = buildings.parser.json.extras?.features ?? [];
    const count = Math.max(1, features.length);
    const data = new Float32Array(count * 4);
    const useCodes = { woonfunctie: 1, kantoorfunctie: 2, winkelfunctie: 3, industriefunctie: 4 };
    features.forEach((feature, i) => {
      const uses = Array.isArray(feature.use) ? feature.use : feature.use ? [feature.use] : [];
      const use = uses.map((u) => useCodes[u] ?? 5).sort()[0] ?? 0;
      data.set([1e9, feature.height_m ?? 0, feature.year ?? 0, use], i * 4);
    });
    buildings.scene.updateMatrixWorld(true);
    const point = new THREE.Vector3();
    buildings.scene.traverse((node) => {
      const ids = node.geometry?.attributes?._feature_id_0;
      if (!node.isMesh || !ids) return;
      const positions = node.geometry.attributes.position;
      for (let v = 0; v < positions.count; v++) {
        const id = Math.round(ids.getX(v));
        point.fromBufferAttribute(positions, v).applyMatrix4(node.matrixWorld);
        if (id < count && point.y < data[id * 4]) data[id * 4] = point.y;
      }
    });
    for (let i = 0; i < count; i++) if (data[i * 4] > 1e8) data[i * 4] = 0;
    const texture = new THREE.DataTexture(data, count, 1, THREE.RGBAFormat, THREE.FloatType);
    texture.needsUpdate = true;
    return { featureTexture: { value: texture }, featureCount: { value: count } };
  }

  // The lamp heads themselves, visible only at night.
  lampHeads(lamps, offset) {
    const mesh = new THREE.InstancedMesh(new THREE.BoxGeometry(0.7, 0.35, 0.7), new THREE.MeshBasicMaterial({ color: 0xffe2a8 }), lamps.length);
    const matrix = new THREE.Matrix4();
    lamps.forEach((lamp, i) => {
      matrix.makeTranslation(lamp.x - this.origin.x - offset.x, lamp.z + (lamp.height_m ?? 5), -(lamp.y - this.origin.y) - offset.z);
      mesh.setMatrixAt(i, matrix);
    });
    mesh.userData.nightOnly = true;
    mesh.visible = false;
    return mesh;
  }

  treeMesh(trees, offset) {
    const clump = new THREE.IcosahedronGeometry(0.5, 1);
    const material = new THREE.MeshLambertMaterial({ color: 0xffffff, flatShading: true });
    material.onBeforeCompile = (shader) => {
      shader.uniforms.dataOverlay = this.overlayUniform;
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', '#include <common>\nuniform float dataOverlay;')
        .replace('#include <opaque_fragment>', '#include <opaque_fragment>\nif (dataOverlay > 0.5) gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0);');
    };
    const clumpsPerTree = 5;
    const mesh = new THREE.InstancedMesh(clump, material, trees.length * clumpsPerTree);
    const matrix = new THREE.Matrix4();
    const colour = new THREE.Color();
    const unit = new THREE.Quaternion();
    let index = 0;
    trees.forEach((tree) => {
      const crown = Math.max(2.5, tree.crown_m ?? (tree.height_m ?? 8) * 0.6);
      const height = Math.max(3, tree.height_m ?? 8);
      const x = tree.x - this.origin.x - offset.x;
      const z = -(tree.y - this.origin.y) - offset.z;
      const centreY = tree.z + height - crown * 0.5;
      let seed = Math.abs(Math.sin(tree.x * 12.9898 + tree.y * 78.233) * 43758.5453);
      const random = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
      const tone = random();
      for (let k = 0; k < clumpsPerTree; k++) {
        const angle = k * 2.4 + random();
        const spread = k === 0 ? 0 : crown * 0.26;
        const size = crown * (k === 0 ? 0.78 : 0.5 + 0.12 * random());
        matrix.compose(
          new THREE.Vector3(x + Math.cos(angle) * spread, centreY + (k === 0 ? 0 : (random() - 0.35) * crown * 0.35), z + Math.sin(angle) * spread),
          unit,
          new THREE.Vector3(size, size * 0.9, size),
        );
        mesh.setMatrixAt(index, matrix);
        colour.setRGB(0.26 + 0.07 * tone, 0.48 + 0.08 * tone + 0.03 * k, 0.18 + 0.04 * tone, THREE.SRGBColorSpace);
        mesh.setColorAt(index, colour);
        index++;
      }
    });
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.userData.tree = true;
    return mesh;
  }

  // Light from every lamp in the register, as a 1 m raster per tile, so a
  // lamp near a tile edge lights both tiles. Pools scale with mast height.
  lampLightFor(tile, lamps) {
    const size = 256, scale = size / TILE_METRES;
    const data = new Float32Array(size * size * 4);
    for (const lamp of lamps) {
      const radius = Math.min(10, Math.max(3.5, 0.7 * (lamp.height_m ?? 6)));
      const cx = (lamp.x - tile.x_min) * scale, cy = (tile.y_min + TILE_METRES - lamp.y) * scale;
      const reach = radius * 2 * scale;
      if (cx < -reach || cy < -reach || cx > size + reach || cy > size + reach) continue;
      for (let y = Math.max(0, Math.floor(cy - reach)); y < Math.min(size, Math.ceil(cy + reach)); y++) {
        for (let x = Math.max(0, Math.floor(cx - reach)); x < Math.min(size, Math.ceil(cx + reach)); x++) {
          const d = Math.hypot(x + 0.5 - cx, y + 0.5 - cy) / scale / radius;
          data[(y * size + x) * 4] += Math.exp(-d * d * 2.2);
        }
      }
    }
    for (let i = 0; i < data.length; i += 4) data[i] = 1 - Math.exp(-data[i] * 1.1);
    const texture = new THREE.DataTexture(data, size, size, THREE.RGBAFormat, THREE.FloatType);
    texture.flipY = false;
    texture.magFilter = THREE.LinearFilter;
    texture.needsUpdate = true;
    return texture;
  }

  buildLampLight() {
    const lamps = this.allLamps ?? [...this.tiles.values()].flatMap((record) => record.lamps ?? []);
    for (const [id, record] of this.tiles) {
      record.shared.lampTexture.value = this.lampLightFor(this.tileList.find((t) => t.id === id), lamps);
    }
  }

  // For offline rendering of large areas: every lamp up front (small), so any
  // tile's light can be built when it is loaded.
  async loadAllLamps() {
    const lists = await Promise.all(this.tileList.map((tile) => fetch(`${this.sceneBase}/tiles/${tile.id}/objects.json`)
      .then((r) => (r.ok ? r.json() : null)).then((o) => o?.lamps ?? []).catch(() => [])));
    this.allLamps = lists.flat();
  }

  // Ground-plane RD footprint of a screen window, for choosing which tiles to load.
  windowFootprint(left, top, width, height, bearing, metresPerPixel) {
    const { right, up, view } = screenAxes(bearing, this.style.elevationDegrees);
    const xs = [], ys = [];
    for (const [sx, sy] of [[left, top], [left + width, top], [left, top - height], [left + width, top - height]]) {
      for (const z of [-8, 80]) {
        const p = right.clone().multiplyScalar(sx * metresPerPixel).add(up.clone().multiplyScalar(sy * metresPerPixel));
        p.add(view.clone().multiplyScalar((z - p.y) / view.y));
        xs.push(p.x + this.origin.x); ys.push(this.origin.y - p.z);
      }
    }
    return { xMin: Math.min(...xs), xMax: Math.max(...xs), yMin: Math.min(...ys), yMax: Math.max(...ys) };
  }

  // Load the tiles a window needs (plus a margin for shadows and tall
  // buildings) and drop the ones far from it, so memory stays bounded.
  async ensureWindow(left, top, width, height, bearing, metresPerPixel, margin = 120) {
    const f = this.windowFootprint(left, top, width, height, bearing, metresPerPixel);
    const needed = this.tileList.filter((t) => t.x_min + TILE_METRES > f.xMin - margin && t.x_min < f.xMax + margin
      && t.y_min + TILE_METRES > f.yMin - margin && t.y_min < f.yMax + margin);
    const neededIds = new Set(needed.map((t) => t.id));
    for (const [id, record] of this.tiles) {
      if (neededIds.has(id) || this.tiles.size <= 40) continue;
      this.scene.remove(record.group);
      record.group.traverse((node) => {
        node.geometry?.dispose();
        for (const m of [node.material].flat()) { if (!m) continue; m.map?.dispose(); m.dispose(); }
      });
      for (const key of ['orthoTexture', 'classTexture', 'lampTexture', 'featureTexture']) record.shared[key]?.value?.dispose?.();
      this.tiles.delete(id);
    }
    await Promise.all(needed.map((tile) => this.loadTile(tile)));
    for (const tile of needed) {
      const record = this.tiles.get(tile.id);
      if (!record.lampReady) { record.shared.lampTexture.value = this.lampLightFor(tile, this.allLamps ?? record.lamps); record.lampReady = true; }
    }
  }

  // Nearest tiles first, a few at a time, so the view under the user arrives
  // before bandwidth is spent on tiles off screen.
  async loadAll(onTile = () => {}, near = { x: this.view.x, y: this.view.y }, concurrency = 3) {
    const distance = (t) => Math.hypot(t.x_min + TILE_METRES / 2 - near.x, t.y_min + TILE_METRES / 2 - near.y);
    const queue = [...this.tileList].sort((a, b) => distance(a) - distance(b));
    const worker = async () => {
      while (queue.length) {
        const tile = queue.shift();
        await this.loadTile(tile);
        onTile(tile);
      }
    };
    await Promise.all(Array.from({ length: concurrency }, worker));
    this.buildLampLight();
  }

  tileAt(x, y) {
    return this.tileList.find((t) => x >= t.x_min && x < t.x_min + TILE_METRES && y >= t.y_min && y < t.y_min + TILE_METRES);
  }

  // World position (scene units) of an RD point at NAP 0.
  worldFromRd(x, y, z = 0) {
    return new THREE.Vector3(x - this.origin.x, z, -(y - this.origin.y));
  }

  // Sets the view so the canvas shows width x height art pixels centred on an
  // RD point, snapped to the global art-pixel grid for this bearing.
  setView({ x, y, bearing = this.view.bearing, metresPerPixel = this.view.metresPerPixel, width, height }) {
    Object.assign(this.view, { x, y, bearing, metresPerPixel, width, height });
    const { right, up, view } = screenAxes(bearing, this.style.elevationDegrees);
    const centre = this.worldFromRd(x, y, STREET_HEIGHT);
    const centreSx = Math.round(centre.dot(right) / metresPerPixel);
    const centreSy = Math.round(centre.dot(up) / metresPerPixel);
    this.setScreenWindow(centreSx - Math.floor(width / 2), centreSy + Math.floor(height / 2), width, height, bearing, metresPerPixel);
  }

  // Exact screen window: left column and top row in art pixels on the global grid.
  setScreenWindow(left, top, width, height, bearing, metresPerPixel) {
    const { right, up, view } = screenAxes(bearing, this.style.elevationDegrees);
    this.camera.position.copy(view).multiplyScalar(-CAMERA_DISTANCE);
    this.camera.up.copy(up);
    this.camera.lookAt(0, 0, 0);
    this.camera.left = left * metresPerPixel;
    this.camera.right = (left + width) * metresPerPixel;
    this.camera.top = top * metresPerPixel;
    this.camera.bottom = (top - height) * metresPerPixel;
    this.camera.updateProjectionMatrix();
    this.camera.updateMatrixWorld();
    this.screenWindow = { left, top, width, height, bearing, metresPerPixel };
    this.resize(width, height);
    this.placeSun(right, up, left, top, width, height, metresPerPixel);
    for (const { shared } of this.tiles.values()) shared.texelsPerArtPixel.value = metresPerPixel / 0.1;
  }

  placeSun(right, up, left, top, width, height, metresPerPixel) {
    // Centre of the view on the ground, then the shadow box around it.
    const sx = (left + width / 2) * metresPerPixel, sy = (top - height / 2) * metresPerPixel;
    const { view } = screenAxes(this.view.bearing, this.style.elevationDegrees);
    const centre = right.clone().multiplyScalar(sx).add(up.clone().multiplyScalar(sy));
    // Move along the view ray down to the ground plane.
    const t = -centre.y / view.y;
    centre.add(view.clone().multiplyScalar(t));
    const az = THREE.MathUtils.degToRad(this.style.sunAzimuthDegrees);
    const el = THREE.MathUtils.degToRad(this.style.sunElevationDegrees);
    const toSun = new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), -Math.cos(az) * Math.cos(el));
    const reach = Math.ceil((Math.max(width, height) * metresPerPixel * 0.85 + 40) / 16) * 16;
    // Snap the shadow box to its own texel grid so neighbouring pyramid tiles
    // get identical shadow edges.
    const texel = (2 * reach) / this.sun.shadow.mapSize.x;
    const lightRight = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 1, 0), toSun).normalize();
    const lightUp = new THREE.Vector3().crossVectors(toSun, lightRight).normalize();
    const a = Math.round(centre.dot(lightRight) / texel) * texel - centre.dot(lightRight);
    const b = Math.round(centre.dot(lightUp) / texel) * texel - centre.dot(lightUp);
    centre.add(lightRight.multiplyScalar(a)).add(lightUp.multiplyScalar(b));
    this.sun.target.position.copy(centre);
    this.sun.position.copy(centre).add(toSun.clone().multiplyScalar(800));
    Object.assign(this.sun.shadow.camera, { left: -reach, right: reach, top: reach, bottom: -reach, near: 1, far: 2000 });
    this.sun.shadow.camera.updateProjectionMatrix();
    this.sun.target.updateMatrixWorld();
  }

  // Art-pixel bounds of all loaded tiles for a bearing, including 60 m of height.
  screenBounds(bearing, metresPerPixel) {
    const { right, up } = screenAxes(bearing, this.style.elevationDegrees);
    let left = Infinity, rightEdge = -Infinity, top = -Infinity, bottom = Infinity;
    for (const tile of this.tileList) {
      for (const [dx, dy] of [[0, 0], [TILE_METRES, 0], [0, TILE_METRES], [TILE_METRES, TILE_METRES]]) {
        for (const z of [-5, 60]) {
          const p = this.worldFromRd(tile.x_min + dx, tile.y_min + dy, z);
          const sx = p.dot(right) / metresPerPixel, sy = p.dot(up) / metresPerPixel;
          left = Math.min(left, sx); rightEdge = Math.max(rightEdge, sx);
          top = Math.max(top, sy); bottom = Math.min(bottom, sy);
        }
      }
    }
    return { left: Math.floor(left), right: Math.ceil(rightEdge), top: Math.ceil(top), bottom: Math.floor(bottom) };
  }

  resize(width, height) {
    if (this.canvas.width !== width || this.canvas.height !== height) this.renderer.setSize(width, height, false);
    this.colourTarget.setSize(width, height);
    this.normalTarget.setSize(width, height);
    this.postMaterial.uniforms.resolution.value.set(width, height);
    if (this.screenWindow) this.postMaterial.uniforms.metresPerPixel.value = this.screenWindow.metresPerPixel;
  }

  render() {
    const u = this.postMaterial.uniforms;
    const overlay = Boolean(this.style.dataOverlay);
    const night = this.style.night ?? 0;
    this.nightUniform.value = night;
    this.sun.intensity = this.style.sun * (1 - night) + 0.35 * night;
    this.sun.color.setHex(night > 0.5 ? 0x9fb4ff : 0xfff0d8);
    this.hemisphere.intensity = this.style.ambient * (1 - night) + 0.85 * night;
    this.hemisphere.color.setHex(night > 0.5 ? 0x3b4a78 : 0xdfe8ff);
    this.hemisphere.groundColor.setHex(night > 0.5 ? 0x1a1d28 : 0x6f6450);
    // Depth tiles leave out tree crowns: a tram under street trees should
    // still show on the map.
    this.scene.traverse((node) => {
      if (node.userData.nightOnly) node.visible = night > 0.5;
      if (node.userData.tree) node.visible = !this.style.depthOutput;
    });
    this.overlayUniform.value = overlay ? 1 : 0;
    const backgroundHex = overlay ? 0x000000 : night > 0.5 ? 0x161c2c : 0xc9d3dd;
    this.scene.background.set(backgroundHex);
    u.background.value.set(((backgroundHex >> 16) & 255) / 255, ((backgroundHex >> 8) & 255) / 255, (backgroundHex & 255) / 255);
    u.pixelArt.value = this.style.pixelArt && !overlay ? 1 : 0;
    u.outlines.value = this.style.outlines && !overlay ? 1 : 0;
    u.dither.value = this.style.dither;
    u.saturation.value = this.style.saturation;
    u.depthOutput.value = this.style.depthOutput ? 1 : 0;
    this.renderer.setRenderTarget(this.colourTarget);
    this.renderer.render(this.scene, this.camera);
    this.scene.overrideMaterial = this.normalMaterial;
    const shadows = this.renderer.shadowMap.autoUpdate;
    this.renderer.shadowMap.autoUpdate = false;
    this.renderer.setRenderTarget(this.normalTarget);
    this.renderer.render(this.scene, this.camera);
    this.renderer.shadowMap.autoUpdate = shadows;
    this.scene.overrideMaterial = null;
    this.renderer.setRenderTarget(null);
    this.renderer.render(this.postScene, this.postCamera);
  }
}
