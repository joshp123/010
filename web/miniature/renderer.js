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
import { citadisTram, car, cyclist } from './vehicles.js';

const TILE_METRES = 250;
const CAMERA_DISTANCE = 4000;
const STREET_HEIGHT = 3; // NAP metres; the point under the screen centre is at street level

export const defaultStyle = {
  elevationDegrees: 40,
  // Sun azimuth relative to the view: from behind the viewer and to one side,
  // so the walls facing the viewer read lit and their sides shaded at every bearing.
  sunAzimuthRelative: 225,
  sunElevationDegrees: 42,
  pixelArt: true,
  outlines: true,
  dither: 0.0,
  groundPhotoDetail: 0.0,
  facadeDetail: 0.6,
  facadeWindowRatio: 0.7,
  facadeRadius: 1.0,
  ambient: 1.05,
  saturation: 1.0,
  midtones: 1.0,
  sun: 4.3,
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
      .replace('#include <common>', `#include <common>\nvarying vec2 vTileUv;\nvarying vec3 vWorldNormalMini;\nuniform float dataOverlay;\nuniform float classOutput;\nuniform float night;\nuniform float nightHour;\nuniform sampler2D lampTexture;\nvec3 overlayCode = vec3(0.0);\nfloat classCode = 0.0;\nvec3 nightGlow = vec3(0.0);\n${fragmentPatch.declarations}`)
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

const overlayOutput = 'if (dataOverlay > 0.5) gl_FragColor = vec4(overlayCode, 1.0);\nif (classOutput > 0.5) gl_FragColor = vec4(classCode * 16.0 / 255.0, 0.0, 0.0, 1.0);';

const groundPatch = {
  key: 'mini-ground',
  overlay: overlayOutput,
  declarations: `
    uniform sampler2D classTexture;
    uniform sampler2D classColours;
    uniform sampler2D orthoTexture;
    uniform float groundPhotoDetail;
    uniform float texelsPerArtPixel;
    uniform sampler2D markingTexture;
    uniform vec3 trackBedColour;
    // Paint from the municipal marking register (tools/build-markings.py),
    // gathered over the art pixel like the line bits so thin lines survive.
    bool paintAround(vec2 uv) {
      float step = 1.0 / 2500.0;
      float reach = max(0.0, floor(texelsPerArtPixel * 0.5));
      for (float dy = -2.0; dy <= 2.0; dy += 1.0) {
        for (float dx = -2.0; dx <= 2.0; dx += 1.0) {
          if (abs(dx) > reach || abs(dy) > reach) continue;
          if (texture2D(markingTexture, uv + vec2(dx, dy) * step).r > 0.5) return true;
        }
      }
      return false;
    }
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
    vec3 groundPhoto = texture2D(orthoTexture, groundUv).rgb;
    float photoGreen = groundPhoto.g - max(groundPhoto.r, groundPhoto.b);
    // Track beds: grass track where the aerial shows grass, else the bed colour.
    if ((surfaceClass == 5.0 || surfaceClass == 14.0) && photoGreen > 0.02) {
      groundColour = texture2D(classColours, vec2(6.5 / 32.0, 0.5)).rgb * 0.95;
    } else if (surfaceClass == 5.0 && trackBedColour.r >= 0.0) {
      groundColour = trackBedColour; // the tile's tram bed as measured in the aerial
    }
    float deep = 1.0 - smoothstep(1.0, 2.0, texelsPerArtPixel); // 1 at 0.1 m per pixel and finer
    if (deep > 0.0) {
      // At deep zoom, surfaces that are not carriageway take a little texture
      // from the aerial photo (paving joints, worn grass, ballast); roads stay
      // clean because parked cars are in the photo.
      bool textured = surfaceClass == 3.0 || surfaceClass == 10.0 || surfaceClass == 6.0 || surfaceClass == 9.0
        || surfaceClass == 14.0 || surfaceClass == 16.0 || surfaceClass == 15.0;
      if (textured) {
        float shade = dot(groundPhoto, vec3(0.299, 0.587, 0.114)) / max(0.05, dot(groundColour, vec3(0.299, 0.587, 0.114)));
        groundColour *= mix(1.0, clamp(shade, 0.8, 1.2), 0.35 * deep);
      }
    }
    int lines = lineBitsAround(groundUv);
    if (paintAround(groundUv)) lines |= 4;
    // Markings and kerbs are narrower than an art pixel at coarse zoom; drawing
    // them there turns roads into speckle. Rails stay: they are the tram network.
    if (texelsPerArtPixel > 3.5) lines &= 3;
    if (texelsPerArtPixel < 1.6) lines &= ~3; // deep zoom: rails are geometry (railMesh)
    if ((lines & 8) != 0) {
      // Kerb: the stone on the pavement side, the gutter's shadow on the road side.
      bool roadSide = surfaceClass == 1.0 || surfaceClass == 2.0 || surfaceClass == 4.0;
      groundColour = roadSide ? groundColour * 0.72 : mix(groundColour, vec3(0.84, 0.83, 0.79), 0.75);
    }
    if ((lines & 4) != 0) groundColour = vec3(0.93, 0.92, 0.86);
    // Rails: dark lines read as track from afar; up close they are polished steel.
    if ((lines & 3) != 0) groundColour = mix(vec3(0.30, 0.29, 0.30), vec3(0.70, 0.71, 0.72), deep);
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
      groundColour = mix(groundColour, vec3(0.52, 0.62, 0.68), dash * 0.6);
    }
    diffuseColor.rgb = groundColour;
    // Class codes for measurement (tools/measure-classes.py).
    classCode = (surfaceClass == 1.0 || surfaceClass == 4.0) ? 1.0
      : (surfaceClass == 3.0 || surfaceClass == 10.0 || surfaceClass == 15.0) ? 2.0
      : (surfaceClass == 6.0 || surfaceClass == 7.0) ? 3.0 : surfaceClass == 8.0 ? 4.0 : surfaceClass == 2.0 ? 8.0 : 0.0;
    // Street lamps from the municipal register light pools on the ground.
    float lampLight = texture2D(lampTexture, groundUv).r;
    if (surfaceClass == 6.0 || surfaceClass == 7.0) lampLight *= 0.35; // grass and shrubs take little light
    nightGlow = groundColour * vec3(1.0, 0.80, 0.55) * lampLight * 1.3;
    if (surfaceClass == 8.0) nightGlow += vec3(1.0, 0.75, 0.45) * lampLight * 0.25;
    // At night water holds the dark blue sky, so it stays apart from the streets.
    if (surfaceClass == 8.0) diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.13, 0.20, 0.34), night * 0.75);`,
};

const buildingPatch = {
  key: 'mini-building',
  overlay: overlayOutput,
  vertexDeclarations: `
    attribute float _feature_id_0;
    uniform sampler2D featureTexture;
    uniform float featureCount;
    varying vec4 vFeature;
    varying vec4 vRoof;
    varying vec3 vWorldPosMini;`,
  vertexBody: `
    vFeature = texture2D(featureTexture, vec2((_feature_id_0 + 0.5) / max(1.0, featureCount), 0.25));
    vRoof = texture2D(featureTexture, vec2((_feature_id_0 + 0.5) / max(1.0, featureCount), 0.75));
    vWorldPosMini = miniWorld.xyz;`,
  declarations: `
    varying vec4 vFeature;
    varying vec4 vRoof;
    varying vec3 vWorldPosMini;
    // A roof drawn from its facts (tools/roof-facts.py): the colour measured
    // in the aerial and a material named from slope and colour, as courses,
    // joints, seams or gravel in world metres. Roofs without facts are plain
    // neutral grey: interpreted. Pattern contrast fades where a course would
    // be smaller than a pixel.
    vec3 roofSurface(vec4 facts, vec3 position, vec3 normal) {
      if (facts.w < 0.5) return vec3(0.42, 0.42, 0.40);
      vec3 base = facts.rgb;
      base = mix(vec3(dot(base, vec3(0.2126, 0.7152, 0.0722))), base, 1.25); // aerial haze
      vec2 down = length(normal.xz) > 0.05 ? normalize(normal.xz) : vec2(1.0, 0.0);
      float s = dot(position.xz, down) / max(normal.y, 0.35);
      float t = dot(position.xz, vec2(-down.y, down.x));
      float material = floor(facts.w + 0.5);
      float course = material == 1.0 ? 0.33 : material == 2.0 ? 0.22 : material == 3.0 ? 0.30 : 1.0;
      float detail = 1.0 - smoothstep(0.35, 0.8, fwidth(s) / course);
      float row = floor(s / course);
      float shade = 1.0;
      if (material <= 3.0) {
        float joint = material == 1.0 ? 0.21 : 0.30;
        float along = t / joint + (material == 1.0 ? 0.0 : 0.5 * mod(row, 2.0));
        float cell = fract(sin(dot(vec2(row, floor(along)), vec2(12.9898, 78.233))) * 43758.5453);
        shade = (fract(s / course) < 0.2 ? 0.80 : 1.0) * (material == 1.0 ? 0.93 + 0.09 * step(0.5, fract(along)) : (fract(along) < 0.08 ? 0.88 : 1.0)) * (0.95 + 0.1 * cell);
      } else if (material == 5.0 || material == 8.0) {
        float grain = fract(sin(dot(floor(position.xz / (material == 5.0 ? 0.12 : 0.3)), vec2(12.9898, 78.233))) * 43758.5453);
        shade = 0.88 + 0.24 * grain;
        detail = 1.0 - smoothstep(0.08, 0.2, fwidth(position.x));
      } else {
        float seam = material == 4.0 ? 1.0 : 2.0;
        shade = fract(t / seam) < 0.05 ? 1.07 : 1.0;
        detail = 1.0 - smoothstep(0.05, 0.12, fwidth(t));
      }
      return base * mix(1.0, shade, detail);
    }
    // Share of windows lit late in the evening, by BAG use: homes are lit
    // irregularly, offices mostly dark, shops show their ground floor.
    vec3 windowLight(bool isWindow, float pick, float heightAboveBase, float use) {
      if (!isWindow) return vec3(0.0);
      bool shopFloor = abs(use - 3.0) < 0.5 && heightAboveBase < 4.5;
      float share = shopFloor ? 0.7 : abs(use - 2.0) < 0.5 ? 0.08 : abs(use - 1.0) < 0.5 ? 0.24 : use < 0.5 ? 0.16 : 0.06;
      // Through the night fewer rooms are lit: homes from evening to small
      // hours, shops close at 21:00, offices empty.
      float evening = 1.0 - smoothstep(22.0, 26.0, nightHour < 12.0 ? nightHour + 24.0 : nightHour);
      share *= shopFloor ? step(nightHour < 12.0 ? 99.0 : nightHour, 21.0) * 0.9 + 0.1 : 0.25 + 0.75 * evening;
      if (pick > share) return vec3(0.0);
      vec3 warm = mix(vec3(1.0, 0.72, 0.38), vec3(1.0, 0.86, 0.60), fract(pick * 7.13));
      vec3 cool = vec3(0.80, 0.88, 1.0);
      return (abs(use - 2.0) < 0.5 || shopFloor ? cool * 0.85 : warm * 0.95);
    }
    uniform sampler2D orthoTexture;
    uniform float facadeDetail;
    uniform float facadeWindowRatio;
    uniform float facadeRadius;
    ${kuwaharaGlsl}`,
  body: `
    classCode = vWorldNormalMini.y > 0.55 ? 6.0 : 7.0;
    if (vWorldNormalMini.y > 0.55) {
      diffuseColor.rgb = roofSurface(vRoof, vWorldPosMini, vWorldNormalMini);
    } else {
    #ifdef ASSET_MATERIAL
    // Model-made walls keep their own colours. Windows are the asset's dark panes.
    if (night > 0.0 && vWorldNormalMini.y < 0.3) {
      vec3 luma = vec3(0.299, 0.587, 0.114);
      vec3 wallTone = texture2D(map, vMapUv, 4.0).rgb;
      float darker = dot(diffuseColor.rgb, luma) / max(0.03, dot(wallTone, luma));
      vec2 alongDir = normalize(vec2(-vWorldNormalMini.z, vWorldNormalMini.x) + 1e-5);
      float storeyH = (vFeature.z > 0.0 && vFeature.z < 1945.0) ? 3.3 : 3.0;
      vec2 room = vec2(floor(dot(vWorldPosMini.xz, alongDir) / 2.4), floor((vWorldPosMini.y - vFeature.x) / storeyH));
      float pick = fract(sin(dot(room + vFeature.xy * 0.37, vec2(12.9898, 78.233))) * 43758.5453);
      nightGlow = windowLight(darker < 0.6, pick, vWorldPosMini.y - vFeature.x, vFeature.w);
    }
    #else
    {
      vec3 luma = vec3(0.299, 0.587, 0.114);
      #ifdef USE_MAP
        vec3 bestMean = kuwahara(map, vMapUv, facadeRadius / vec2(textureSize(map, 0)));
        vec3 wall = 1.0 - pow(1.0 - bestMean, vec3(2.0));
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
        // Subtle: the rhythm is a fact (storeys), the exact windows are not.
        if (height > 0.0 && windowRow && windowColumn) wall = mix(wall, vec3(0.20, 0.24, 0.30), 0.22);
        diffuseColor.rgb = wall;
        if (night > 0.0 && vWorldNormalMini.y < 0.3) {
          float pick = fract(sin(dot(vec2(floor(along / pitch), floor(h / storey)) + vFeature.xy, vec2(12.9898, 78.233))) * 43758.5453);
          nightGlow = windowLight(height > 0.0 && windowRow && windowColumn, pick, h, use);
        }
      #endif
    }
    #endif
    }
`,
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
  uniform float midtones;
  uniform float rawOutput;
  uniform vec3 sunView;
  uniform float depthOutput;
  uniform vec3 background;
  uniform float transparentBackground;
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
    if (rawOutput > 0.5) { fragColour = vec4(linearColour, 1.0); return; } // codes, not colours
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
      fragColour = vec4(background, 1.0 - transparentBackground);
      return;
    }
    // At coarse scales neighbouring pixels are metres apart in depth; outline
    // only real object edges, and drop inner creases once they are sub-pixel.
    float edgeDepth = max(1.6, 4.0 * metresPerPixel);
    if (outlines > 0.5) {
      vec3 normal = texture(normalTexture, vUv).xyz * 2.0 - 1.0;
      float silhouette = 0.0, crease = 0.0;
      vec2 offsets[4] = vec2[4](vec2(1, 0), vec2(-1, 0), vec2(0, 1), vec2(0, -1));
      // Lines two pixels wide at deep zoom, so edges hold at 7.5 cm per pixel.
      float reach = metresPerPixel < 0.1 ? 2.0 : 1.0;
      for (int i = 0; i < 8; i++) {
        if (i >= 4 && reach < 1.5) break;
        vec2 uv = vUv + offsets[i - (i / 4) * 4] * texel * (i >= 4 ? 2.0 : 1.0);
        float neighbourDepth = depthAt(uv);
        // Outline belongs to the nearer surface, so objects keep their size.
        vec3 neighbourNormal = texture(normalTexture, uv).xyz * 2.0 - 1.0;
        // Two parallel surfaces a little apart (tile joins, kerbs, quay steps)
        // are not an object edge; anything taller than a storey is.
        bool parallelStep = dot(normal, neighbourNormal) > 0.98 && neighbourDepth - depth < edgeDepth + 1.0;
        if (neighbourDepth - depth > edgeDepth && !parallelStep) silhouette = 1.0;
        if (metresPerPixel < 1.0 && dot(normal, neighbourNormal) < 0.75 && abs(neighbourDepth - depth) < edgeDepth) {
          // A fold: the face turned towards the sun gets a highlight line,
          // the face turned away a shade line, as a pixel artist draws edges.
          crease = dot(normal, sunView) > dot(neighbourNormal, sunView) + 0.15 ? 2.0 : max(crease, 1.0);
        }
      }
      if (silhouette > 0.5) colour = mix(colour * 0.3, vec3(0.07, 0.07, 0.10), 0.6);
      else if (crease > 1.5) colour = min(colour * 1.28 + 0.04, vec3(1.0));
      else if (crease > 0.5) colour = colour * 0.62;
    }
    float grey = dot(colour, vec3(0.299, 0.587, 0.114));
    colour = clamp(mix(vec3(grey), colour, saturation), 0.0, 1.0);
    // Tone: darker midtones, highlights kept (measured against tiny.london).
    colour = pow(colour, vec3(midtones));
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
  constructor(canvas, { sceneBase, assetBase = null, manifest, area = 'core', style = {} }) {
    this.assetBase = assetBase;
    this.assetFile = style.assetFile ?? null; // e.g. buildings-provenance.glb
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
    this.renderer = new THREE.WebGLRenderer({ canvas, alpha: true, premultipliedAlpha: false, antialias: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
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
    this.classUniform = { value: 0 };
    this.nightUniform = { value: 0 };
    this.nightHourUniform = { value: 21 }; // local hour the night is drawn for
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
        saturation: { value: 1.0 },
        midtones: { value: 1.0 },
        rawOutput: { value: 0 },
        sunView: { value: new THREE.Vector3(0, 0, 1) },
        depthOutput: { value: 0 },
        background: { value: new THREE.Vector3(0xc9 / 255, 0xd3 / 255, 0xdd / 255) },
        transparentBackground: { value: 0 },
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
    // Retry a failed download twice before drawing the tile without that part;
    // a missing part is logged, never silent.
    const retrying = (start) => start().catch(() => new Promise((r) => setTimeout(r, 300)).then(start))
      .catch(() => new Promise((r) => setTimeout(r, 1000)).then(start));
    const optional = (promise) => promise.catch((error) => { console.warn(`tile ${tile.id}: ${error.message ?? error}`); return null; });
    const [ground, buildings, classTexture, orthoTexture, objects] = await Promise.all([
      optional(retrying(() => loader.loadAsync(`${base}/ground.glb`))),
      // A tile's building assets (made by the asset maker, pipeline/assets)
      // replace its raw buildings when they exist.
      (this.assetBase ? loader.loadAsync(`${this.assetBase}/tiles/${tile.id}/${this.assetFile ?? 'buildings.glb'}`).catch(() => null) : Promise.resolve(null))
        .then((assets) => assets ?? optional(retrying(() => loader.loadAsync(`${base}/buildings.glb`)))),
      optional(retrying(() => loadRawImageTexture(`${base}/classes.png`))),
      optional(retrying(() => loadPhotoTexture(`${base}/ortho.jpg`))),
      optional(retrying(() => fetch(`${base}/objects.json`).then((r) => { if (!r.ok) throw new Error(`objects.json ${r.status}`); return r.json(); }))),
    ]);
    const rails = await fetch(`${base}/rails.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    const roofFacts = await fetch(`${base}/roofs.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    const markings = await loadRawImageTexture(`${base}/markings.png`).catch(() => null);
    const shared = {
      orthoTexture: { value: orthoTexture },
      facadeDetail: { value: this.style.facadeDetail },
      facadeWindowRatio: { value: this.style.facadeWindowRatio },
      facadeRadius: { value: this.style.facadeRadius },
      groundPhotoDetail: { value: this.style.groundPhotoDetail },
      texelsPerArtPixel: { value: this.view.metresPerPixel / 0.1 },
      classTexture: { value: classTexture },
      classColours: { value: this.classColours },
      dataOverlay: this.overlayUniform,
      classOutput: this.classUniform,
      night: this.nightUniform,
      nightHour: this.nightHourUniform,
      lampTexture: { value: this.blankLamps },
      markingTexture: { value: markings ?? this.blankLamps },
      trackBedColour: { value: new THREE.Vector3(-1, -1, -1) },
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
      Object.assign(shared, this.featureTexture(buildings, roofFacts));
      buildings.scene.traverse((node) => {
        if (!node.isMesh) return;
        const source = node.material;
        const material = new THREE.MeshLambertMaterial({ color: source.map ? 0xffffff : 0xd9cfc0, map: source.map ?? null });
        if (material.map) material.map.colorSpace = THREE.SRGBColorSpace;
        if (source.userData?.asset) {
          // Asset textures are already clean and stylised: draw them as they are.
          material.map.minFilter = THREE.LinearMipmapLinearFilter;
          material.defines = { ASSET_MATERIAL: '' };
          node.material = orthoTexture ? withTilePosition(material, offset, shared, buildingPatch) : material;
        } else {
          node.material = orthoTexture ? withTilePosition(material, offset, shared, buildingPatch) : material;
        }
        node.castShadow = true;
        node.receiveShadow = true;
      });
      group.add(buildings.scene);
    }
    if (objects?.trees?.length) group.add(this.treeMesh(objects.trees, offset, rails?.tracks ?? []));
    const sampler = ground && classTexture ? this.groundSampler(offset, ground.scene, classTexture) : null;
    if (sampler && orthoTexture) {
      const bed = this.trackBedColour(sampler, orthoTexture);
      if (bed) shared.trackBedColour.value.set(...bed);
    }
    if (rails?.tracks?.length && sampler) group.add(this.railMesh(rails.tracks, sampler));
    if (sampler) group.add(await this.vehicleMesh(tile, sampler, rails?.tracks ?? []));
    group.updateMatrixWorld(true);
    this.scene.add(group);
    const record = { group, shared, lamps: objects?.lamps ?? [] };
    if (objects?.lamps?.length) group.add(this.lampHeads(objects.lamps, offset));
    this.tiles.set(tile.id, record);
    return record;
  }

  // Track as built: two steel rails at standard gauge on every BGT track
  // centreline, at the ground's height; on ballast beds also concrete
  // sleepers every 0.6 m. In-street (grooved) rail sits flush with no
  // sleepers; grass beds hide their sleepers. Drawn only at deep zoom, where a
  // rail is a pixel or more wide; coarser levels draw rails from the raster.
  // Ground class and height at any RD point of one tile, from its class
  // raster and its ground mesh. Rails and vehicles stand on this.
  groundSampler(offset, groundScene, classTexture) {
    const canvas = new OffscreenCanvas(classTexture.image.width, classTexture.image.height);
    const context = canvas.getContext('2d', { willReadFrequently: true });
    context.drawImage(classTexture.image, 0, 0);
    const classes = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const tileX = offset.x + this.origin.x, tileY = this.origin.y - offset.z; // tile south-west corner in RD
    const classAt = (x, y) => {
      const px = Math.floor((x - tileX) / TILE_METRES * canvas.width), py = Math.floor((tileY + TILE_METRES - y) / TILE_METRES * canvas.height);
      if (px < 0 || py < 0 || px >= canvas.width || py >= canvas.height) return 0;
      return classes[(py * canvas.width + px) * 4];
    };
    (groundScene.parent ?? groundScene).updateMatrixWorld(true); // ray in world coordinates
    const meshes = [];
    groundScene.traverse((n) => { if (n.isMesh) meshes.push(n); });
    const ray = new THREE.Raycaster();
    const down = new THREE.Vector3(0, -1, 0);
    const heightAt = (x, y) => {
      ray.set(new THREE.Vector3(x - this.origin.x, 200, -(y - this.origin.y)), down);
      const hit = ray.intersectObjects(meshes, false)[0];
      return hit ? hit.point.y : null;
    };
    return { tileX, tileY, classes, width: canvas.width, height: canvas.height, classAt, heightAt };
  }

  // The colour of a tile's tram bed in the 2026 aerial: the median of its
  // sunlit, not-green pixels (shadowed and grassed parts say nothing about
  // the paving). Linear RGB, or null when the tile has too little of it.
  trackBedColour(ground, orthoTexture) {
    const { classes, width, height } = ground;
    const canvas = new OffscreenCanvas(width, height);
    const context = canvas.getContext('2d', { willReadFrequently: true });
    context.drawImage(orthoTexture.image, 0, 0, width, height);
    const photo = context.getImageData(0, 0, width, height).data;
    const samples = [];
    for (let i = 0; i < width * height; i += 3) {
      if (classes[i * 4] !== 5) continue;
      const r = photo[i * 4], g = photo[i * 4 + 1], b = photo[i * 4 + 2];
      if (g - Math.max(r, b) > 5) continue;
      samples.push([r, g, b, 0.299 * r + 0.587 * g + 0.114 * b]);
    }
    if (samples.length < 500) return null;
    samples.sort((a, b) => a[3] - b[3]);
    const sunlit = samples.slice(Math.floor(samples.length * 0.6));
    const median = [0, 1, 2].map((c) => sunlit.map((p) => p[c]).sort((a, b) => a - b)[sunlit.length >> 1]);
    const colour = new THREE.Color().setRGB(median[0] / 255, median[1] / 255, median[2] / 255, THREE.SRGBColorSpace);
    return [colour.r, colour.g, colour.b];
  }

  railMesh(tracks, ground) {
    const { tileX, tileY, classAt, heightAt } = ground;
    const railParts = [], sleeperParts = [];
    let lastHeight = 3;
    for (const track of tracks) {
      const pts = track.points;
      for (let i = 1; i < pts.length; i++) {
        const [x0, y0] = pts[i - 1], [x1, y1] = pts[i];
        const dx = x1 - x0, dy = y1 - y0, length = Math.hypot(dx, dy);
        if (length < 0.05) continue;
        const ux = dx / length, uy = dy / length, nx = -uy, ny = ux;
        for (let s = 0; s < length; s += 1.0) {
          const step = Math.min(1.0, length - s), mx = x0 + ux * (s + step / 2), my = y0 + uy * (s + step / 2);
          const h = heightAt(mx, my) ?? lastHeight; lastHeight = h;
          const surface = classAt(mx, my);
          const street = surface === 1 || surface === 3 || surface === 10 || surface === 15;
          for (const side of [-0.7175, 0.7175]) {
            railParts.push({ x: mx + nx * side, y: my + ny * side, z: h, angle: Math.atan2(uy, ux), length: step, street });
          }
          const ballast = surface === 14 || surface === 16; // BGT says nothing about a tram bed's surface: no sleepers there
          if (ballast) {
            for (let k = 0.3; k < step; k += 0.6) {
              const sx = x0 + ux * (s + k), sy = y0 + uy * (s + k);
              sleeperParts.push({ x: sx, y: sy, z: h, angle: Math.atan2(uy, ux) });
            }
          }
        }
      }
    }
    const group = new THREE.Group();
    const unit = new THREE.BoxGeometry(1, 1, 1);
    const matrix = new THREE.Matrix4(), quaternion = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0);
    const place = (mesh, parts, size) => parts.forEach((part, i) => {
      quaternion.setFromAxisAngle(up, part.angle);
      const [w, hgt, d] = size(part);
      matrix.compose(new THREE.Vector3(part.x - tileX, part.z + hgt / 2, -(part.y - tileY)), quaternion, new THREE.Vector3(w, hgt, d));
      mesh.setMatrixAt(i, matrix);
    });
    const rails = new THREE.InstancedMesh(unit, new THREE.MeshLambertMaterial({ color: 0x6f7378 }), railParts.length);
    place(rails, railParts, (p) => [p.length + 0.02, p.street ? 0.03 : 0.16, p.street ? 0.09 : 0.07]);
    rails.castShadow = true; rails.receiveShadow = true;
    group.add(rails);
    if (sleeperParts.length) {
      const sleepers = new THREE.InstancedMesh(unit, new THREE.MeshLambertMaterial({ color: 0x8f8a82 }), sleeperParts.length);
      place(sleepers, sleeperParts, () => [0.24, 0.08, 2.4]);
      sleepers.receiveShadow = true;
      group.add(sleepers);
    }
    group.userData.deepOnly = true; // tile-local coordinates, like the tile's other parts
    return group;
  }

  // Vehicles standing in the tile. Parked cars fill the BGT parking bays
  // (which bays are taken is not known, so they are interpreted). With
  // style.traffic a moment of moving traffic is added for still pictures:
  // a Citadis on a tram track, cars on the OSM road graph, cyclists on the
  // cycle graph. The live map draws moving traffic itself.
  async vehicleMesh(tile, ground, tracks) {
    const { tileX, tileY, classAt, heightAt, classes, width, height } = ground;
    const hash = (a, b) => Math.abs(Math.sin(a * 12.9898 + b * 78.233) * 43758.5453) % 1;
    const placed = { car: [], cyclist: [], tram: [] };
    const put = (kind, x, y, heading, colour, lift = 0) => {
      const h = heightAt(x, y);
      if (h !== null) placed[kind].push({ x, y, z: h + lift, heading, colour });
    };
    // Dutch car colours, roughly by share of the fleet.
    const carColours = [[0.25, 0x6b6f75], [0.45, 0x1e2024], [0.6, 0xe8e8e6], [0.72, 0x2e4a7a], [0.84, 0xb9bcc0], [0.91, 0x9c2a2a], [0.94, 0x2f4a3a], [0.97, 0x7a6550], [1.01, 0xd08a2a]];
    const carColour = (r) => carColours.find(([share]) => r < share)[1];

    // Parked cars: each parking-bay area, walked along its long axis.
    const metres = TILE_METRES / width, label = new Int32Array(width * height);
    for (let start = 0, next = 1; start < width * height; start++) {
      if (label[start] || classes[start * 4] !== 4) continue;
      const pixels = [start];
      label[start] = next;
      for (let k = 0; k < pixels.length; k++) {
        const p = pixels[k], px = p % width, py = (p - px) / width;
        for (const q of [px > 0 ? p - 1 : -1, px < width - 1 ? p + 1 : -1, py > 0 ? p - width : -1, py < height - 1 ? p + width : -1]) {
          if (q >= 0 && !label[q] && classes[q * 4] === 4) { label[q] = next; pixels.push(q); }
        }
      }
      next++;
      if (pixels.length * metres * metres < 9) continue;
      let mx = 0, my = 0;
      for (const p of pixels) { mx += p % width; my += Math.floor(p / width); }
      mx /= pixels.length; my /= pixels.length;
      let sxx = 0, syy = 0, sxy = 0;
      for (const p of pixels) { const dx = p % width - mx, dy = Math.floor(p / width) - my; sxx += dx * dx; syy += dy * dy; sxy += dx * dy; }
      const angle = 0.5 * Math.atan2(2 * sxy, sxx - syy);
      // Long axis in RD (raster rows run south).
      const ux = Math.cos(angle), uy = -Math.sin(angle), vx = -uy, vy = ux;
      const bins = new Map();
      for (const p of pixels) {
        const x = tileX + (p % width + 0.5) * metres, y = tileY + TILE_METRES - (Math.floor(p / width) + 0.5) * metres;
        const u = x * ux + y * uy, v = x * vx + y * vy, key = Math.floor(u / 0.5);
        const bin = bins.get(key) ?? { v: 0, n: 0 };
        bin.v += v; bin.n += 1; bins.set(key, bin);
      }
      const keys = [...bins.keys()].sort((a, b) => a - b);
      const across = (key) => { const bin = bins.get(key); return bin ? bin.n * metres * metres / 0.5 : 0; };
      const centre = (key) => bins.get(key).v / bins.get(key).n;
      let key = keys[0];
      while (key <= keys[keys.length - 1]) {
        const w = across(key);
        const perpendicular = w >= 4.2, spacing = perpendicular ? 2.5 : 5.6;
        const mid = key + Math.round(spacing / 2 / 0.5);
        if (w < 1.6 || !bins.has(mid)) { key += 1; continue; }
        const u = mid * 0.5 + 0.25, v = centre(mid);
        const x = u * ux + v * vx, y = u * uy + v * vy;
        const heading = perpendicular ? Math.atan2(vy, vx) : Math.atan2(uy, ux);
        const fx = Math.cos(heading) * 2.0, fy = Math.sin(heading) * 2.0;
        if (classAt(x, y) === 4 && classAt(x + fx, y + fy) === 4 && classAt(x - fx, y - fy) === 4 && hash(x, y) < 0.85) {
          put('car', x, y, heading + (hash(y, x) < 0.5 ? Math.PI : 0), carColour(hash(x * 3.1, y * 1.7)));
        }
        key += Math.round(spacing / 0.5);
      }
    }

    const parkedCars = placed.car.length;
    if (this.style.traffic) {
      const networks = await this.trafficNetworks();
      const inside = (x, y) => x >= tileX && x < tileX + TILE_METRES && y >= tileY && y < tileY + TILE_METRES;
      const along = (graph, perMetre, keep, side, surfaces, kind, colourOf) => {
        graph.edges.forEach((edge, index) => {
          const [from, to, , , roadClass] = edge;
          const a = graph.nodes[from], b = graph.nodes[to];
          if (!inside((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) || !keep(roadClass) || graph.tunnel?.has(index)) return;
          const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
          const ux = (b[0] - a[0]) / length, uy = (b[1] - a[1]) / length;
          const way = graph.ways[graph.edge_ways[index]];
          const offset = way?.directions?.[0] && way?.directions?.[1] ? side : 0; // keep right on two-way ways
          const count = Math.floor(length * perMetre(roadClass) + hash(from, to));
          for (let k = 0; k < count; k++) {
            const s = (k + hash(index, k)) / count * length;
            const x = a[0] + ux * s + uy * offset, y = a[1] + uy * s - ux * offset;
            if (surfaces.includes(classAt(x, y))) put(kind, x, y, Math.atan2(uy, ux), colourOf(hash(x, y)));
          }
        });
      };
      const carDensity = { primary: 1 / 22, secondary: 1 / 22, tertiary: 1 / 35, residential: 1 / 70, unclassified: 1 / 70, living_street: 1 / 120 };
      if (networks.cars) along(networks.cars, (c) => carDensity[c] ?? 0, (c) => c in carDensity, 1.6, [1, 5, 12, 15], 'car', carColour);
      const clothes = [0x2b2f3a, 0x3a4a6b, 0x6b2f2f, 0x1e1e22, 0x56604a, 0x8a8f96, 0xb5763a];
      if (networks.bikes) along(networks.bikes, (c) => (c === 'cycleway' ? 1 / 35 : 1 / 140), () => true, 0.7, [1, 2, 10, 15], 'cyclist', (r) => clothes[Math.floor(r * clothes.length)]);
      // One tram on the longest tram track, running on the right: its other
      // track lies to its left.
      const trams = tracks.filter((t) => t.function === 'tram');
      const lengthOf = (t) => t.points.slice(1).reduce((sum, p, i) => sum + Math.hypot(p[0] - t.points[i][0], p[1] - t.points[i][1]), 0);
      // style.tramNear = [x, y] puts it on the track point nearest that place.
      const near = this.style.tramNear;
      const distanceTo = (t) => Math.min(...t.points.map((p) => Math.hypot(p[0] - near[0], p[1] - near[1])));
      const track = near ? trams.filter((t) => lengthOf(t) > 35 && distanceTo(t) < 40).sort((a, b) => distanceTo(a) - distanceTo(b))[0]
        : trams.sort((a, b) => lengthOf(b) - lengthOf(a))[0];
      if (track && lengthOf(track) > 35) {
        let target = lengthOf(track) * (0.3 + 0.4 * hash(track.points[0][0], track.points[0][1]));
        if (near) {
          let best = Infinity;
          for (let i = 1, walked = 0; i < track.points.length; i++) {
            const [x0, y0] = track.points[i - 1], [x1, y1] = track.points[i], segment = Math.hypot(x1 - x0, y1 - y0);
            const d = Math.hypot(x0 - near[0], y0 - near[1]);
            if (d < best) { best = d; target = walked; }
            walked += segment;
          }
          target = Math.min(Math.max(target, 16), lengthOf(track) - 16); // the whole tram on the track
        }
        let walked = 0;
        for (let i = 1; i < track.points.length; i++) {
          const [x0, y0] = track.points[i - 1], [x1, y1] = track.points[i];
          const segment = Math.hypot(x1 - x0, y1 - y0);
          if (walked + segment >= target) {
            const t = (target - walked) / segment, x = x0 + (x1 - x0) * t, y = y0 + (y1 - y0) * t;
            let ux = (x1 - x0) / segment, uy = (y1 - y0) / segment;
            const other = trams.filter((o) => o !== track).flatMap((o) => o.points)
              .map((p) => ({ p, d: Math.hypot(p[0] - x, p[1] - y) })).sort((a, b) => a.d - b.d)[0];
            if (other && other.d < 8 && (other.p[0] - x) * -uy + (other.p[1] - y) * ux < 0) { ux = -ux; uy = -uy; }
            if (inside(x, y)) put('tram', x, y, Math.atan2(uy, ux), 0, classAt(x, y) === 5 ? 0.16 : 0.03);
            break;
          }
          walked += segment;
        }
      }
    }

    console.log(`vehicles ${tile.id}: ${parkedCars} parked, ${placed.car.length - parkedCars} moving cars, ${placed.cyclist.length} cyclists, trams at ${placed.tram.map((t) => `${t.x.toFixed(0)},${t.y.toFixed(0)}`).join(" ")}`);
    const group = new THREE.Group();
    const models = { car: (c) => car(c), cyclist: (c) => cyclist(c), tram: () => citadisTram() };
    for (const [kind, items] of Object.entries(placed)) {
      if (!items.length) continue;
      // One instanced mesh per part of the model; paint takes each vehicle's colour.
      const model = models[kind](0xffffff);
      model.updateMatrixWorld(true);
      model.traverse((part) => {
        if (!part.isMesh) return;
        const paint = kind !== 'tram' && part.material.color?.getHex() === 0xffffff;
        const material = part.material.clone();
        if (this.style.provenance) material.color.lerp(new THREE.Color(0xff00ff), 0.45);
        const mesh = new THREE.InstancedMesh(part.geometry, material, items.length);
        const matrix = new THREE.Matrix4(), turn = new THREE.Matrix4(), colour = new THREE.Color();
        items.forEach((item, i) => {
          // Models run along +x; RD heading is anticlockwise from east, and the scene's z points south.
          turn.makeRotationY(item.heading).setPosition(item.x - tileX, item.z, -(item.y - tileY));
          matrix.multiplyMatrices(turn, part.matrixWorld);
          mesh.setMatrixAt(i, matrix);
          if (paint) mesh.setColorAt(i, colour.setHex(item.colour));
        });
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        group.add(mesh);
      });
    }
    group.userData.vehicles = true;
    return group;
  }

  // The OSM road and cycle graphs (scene/v1/networks), loaded once.
  trafficNetworks() {
    this.networksPromise ??= Promise.all(['cars', 'bikes'].map((kind) => fetch(`${this.sceneBase}/networks/${kind}.json`)
      .then((r) => r.json()).then((graph) => ({ ...graph, tunnel: new Set(graph.tunnel_edges ?? []) })).catch(() => null)))
      .then(([cars, bikes]) => ({ cars, bikes }));
    return this.networksPromise;
  }

  // Per-building facts for the shader: base height, height, construction
  // year and use, one texel per feature in the tile's feature table.
  // Row 1: base height, height, year, use. Row 2: the roof's measured colour
  // (linear) and material code from roofs.json; 0 = no facts (interpreted).
  featureTexture(buildings, roofFacts) {
    const features = buildings.parser.json.extras?.features ?? [];
    const count = Math.max(1, features.length);
    const data = new Float32Array(count * 8);
    const colour = new THREE.Color();
    for (let i = 0; i < count; i++) {
      const roof = roofFacts?.roofs?.[i];
      const code = roof?.material ? roofFacts.material_codes[roof.material] : 0;
      if (code) {
        colour.setRGB(roof.colour[0] / 255, roof.colour[1] / 255, roof.colour[2] / 255, THREE.SRGBColorSpace);
        data.set([colour.r, colour.g, colour.b, code], (count + i) * 4);
      } else if (this.style.provenance) {
        data.set([0.6, 0.1, 0.6, 6], (count + i) * 4); // interpreted roof, shown magenta
      }
    }
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
    const texture = new THREE.DataTexture(data, count, 2, THREE.RGBAFormat, THREE.FloatType);
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

  // Each tree is drawn from the register: its genus sets crown shape and leaf
  // colour (Rotterdam's street trees are mostly lime, maple, plane, ash,
  // cherry, willow and poplar), its height and crown width set the size. The
  // crown is a cluster of leaf clumps placed by a hash of the tree's position,
  // so a tree always looks the same; leaf texture appears only at deep zoom.
  static treeForm(genus) {
    // ratio: crown width / height when the register has no crown width.
    // autumn: the colour leaves turn; turn and bare: day of year the colour
    // starts and the last leaves fall (typical for the Randstad).
    const forms = {
      Tilia: { ratio: 0.75, colour: [0.24, 0.42, 0.18], autumn: [0.72, 0.62, 0.20], turn: 272, bare: 315 },
      Acer: { ratio: 0.8, colour: [0.26, 0.44, 0.17], autumn: [0.82, 0.48, 0.14], turn: 282, bare: 322 },
      Platanus: { ratio: 0.9, colour: [0.30, 0.45, 0.20], autumn: [0.62, 0.50, 0.24], turn: 295, bare: 340 },
      Fraxinus: { ratio: 0.8, colour: [0.29, 0.44, 0.20], autumn: [0.55, 0.56, 0.24], turn: 280, bare: 305, airy: true },
      Prunus: { ratio: 0.9, colour: [0.31, 0.38, 0.20], autumn: [0.74, 0.34, 0.16], turn: 262, bare: 305 },
      Malus: { ratio: 0.9, colour: [0.30, 0.42, 0.20], autumn: [0.66, 0.52, 0.20], turn: 275, bare: 315 },
      Pyrus: { ratio: 0.55, colour: [0.27, 0.43, 0.19], autumn: [0.70, 0.30, 0.16], turn: 290, bare: 330 },
      Salix: { ratio: 1.0, colour: [0.42, 0.52, 0.30], autumn: [0.66, 0.64, 0.30], turn: 295, bare: 335, airy: true },
      Populus: { ratio: 0.45, colour: [0.30, 0.47, 0.22], autumn: [0.78, 0.66, 0.22], turn: 280, bare: 315, columnar: true },
      Alnus: { ratio: 0.6, colour: [0.20, 0.36, 0.16], autumn: [0.36, 0.40, 0.18], turn: 300, bare: 330 },
      Betula: { ratio: 0.55, colour: [0.38, 0.50, 0.24], autumn: [0.80, 0.68, 0.24], turn: 272, bare: 312, airy: true },
      Quercus: { ratio: 0.95, colour: [0.23, 0.38, 0.15], autumn: [0.56, 0.40, 0.18], turn: 295, bare: 350 },
      Ulmus: { ratio: 0.85, colour: [0.25, 0.41, 0.17], autumn: [0.70, 0.60, 0.22], turn: 285, bare: 320 },
      Robinia: { ratio: 0.75, colour: [0.36, 0.48, 0.22], autumn: [0.72, 0.66, 0.26], turn: 280, bare: 312, airy: true },
      Aesculus: { ratio: 0.85, colour: [0.21, 0.38, 0.15], autumn: [0.62, 0.38, 0.16], turn: 255, bare: 300 },
      Carpinus: { ratio: 0.6, colour: [0.25, 0.43, 0.18], autumn: [0.74, 0.60, 0.22], turn: 288, bare: 325 },
      Liquidambar: { ratio: 0.55, colour: [0.25, 0.40, 0.17], autumn: [0.64, 0.18, 0.18], turn: 290, bare: 335 },
      Gleditsia: { ratio: 0.85, colour: [0.40, 0.52, 0.24], autumn: [0.82, 0.72, 0.22], turn: 272, bare: 300, airy: true },
      Styphnolobium: { ratio: 0.9, colour: [0.30, 0.45, 0.20], autumn: [0.70, 0.64, 0.24], turn: 290, bare: 325 },
      Pinus: { ratio: 0.6, colour: [0.15, 0.30, 0.18], conifer: true, evergreen: true },
      Chamaecyparis: { ratio: 0.35, colour: [0.14, 0.30, 0.20], conifer: true, columnar: true, evergreen: true },
      Taxus: { ratio: 0.8, colour: [0.12, 0.26, 0.15], evergreen: true },
      Ilex: { ratio: 0.6, colour: [0.13, 0.28, 0.14], evergreen: true },
    };
    return forms[genus] ?? { ratio: 0.8, colour: [0.25, 0.42, 0.18], autumn: [0.66, 0.56, 0.22], turn: 280, bare: 320 };
  }

  // Leaves on a deciduous tree on a day of the year: share still on the tree
  // (0 bare, 1 full) and how far the colour has turned (0 green, 1 autumn).
  static leafState(form, dayOfYear) {
    if (form.evergreen) return { leaves: 1, turned: 0 };
    const leafOut = 105, fullLeaf = 135; // mid-April to mid-May
    if (dayOfYear < leafOut || dayOfYear >= form.bare) return { leaves: 0, turned: 1 };
    if (dayOfYear < fullLeaf) return { leaves: (dayOfYear - leafOut) / (fullLeaf - leafOut), turned: 0 };
    if (dayOfYear < form.turn) return { leaves: 1, turned: 0 };
    const t = (dayOfYear - form.turn) / (form.bare - form.turn);
    return { leaves: Math.min(1, 1.6 * (1 - t)), turned: Math.min(1, t * 1.7) };
  }

  static distanceToTracks(x, y, tracks) {
    let best = Infinity;
    for (const track of tracks) {
      const pts = track.points;
      for (let i = 1; i < pts.length; i++) {
        const [x0, y0] = pts[i - 1], dx = pts[i][0] - x0, dy = pts[i][1] - y0, l2 = dx * dx + dy * dy || 1e-9;
        const t = Math.max(0, Math.min(1, ((x - x0) * dx + (y - y0) * dy) / l2));
        best = Math.min(best, Math.hypot(x - x0 - t * dx, y - y0 - t * dy));
      }
    }
    return best;
  }

  treeMesh(trees, offset, tracks = []) {
    const group = new THREE.Group();
    const clump = new THREE.IcosahedronGeometry(0.5, 1);
    // Leaf clumps get a leaf-sized texture; twig clumps (bare crowns) are a
    // stable screen of fine cells so the street shows through.
    const crownMaterial = (twigs) => {
      const material = new THREE.MeshLambertMaterial({ color: 0xffffff, flatShading: true });
      material.customProgramCacheKey = () => (twigs ? 'tree-twigs' : 'tree-leaves');
      material.onBeforeCompile = (shader) => {
        shader.uniforms.dataOverlay = this.overlayUniform;
        shader.uniforms.classOutput = this.classUniform;
        shader.vertexShader = shader.vertexShader
          .replace('#include <common>', '#include <common>\nvarying vec3 vLeafWorld;')
          .replace('#include <worldpos_vertex>', '#include <worldpos_vertex>\nvLeafWorld = (modelMatrix * instanceMatrix * vec4(transformed, 1.0)).xyz;');
        shader.fragmentShader = shader.fragmentShader
          .replace('#include <common>', '#include <common>\nuniform float dataOverlay;\nuniform float classOutput;\nvarying vec3 vLeafWorld;')
          .replace('#include <color_fragment>', `#include <color_fragment>
            vec3 cell = floor(vLeafWorld / ${twigs ? '0.14' : '0.35'});
            float leaf = fract(sin(dot(cell, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
            ${twigs ? 'if (leaf > 0.38) discard;' : ''}
            diffuseColor.rgb *= 0.86 + 0.28 * leaf;`)
          .replace('#include <opaque_fragment>', '#include <opaque_fragment>\nif (dataOverlay > 0.5) gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0);\nif (classOutput > 0.5) gl_FragColor = vec4(80.0 / 255.0, 0.0, 0.0, 1.0);');
      };
      return material;
    };
    const leaves = crownMaterial(false);
    // Season only when asked for (?date=YYYY-MM-DD); otherwise trees are in full leaf.
    const date = this.style.date ? new Date(this.style.date) : new Date(2026, 6, 1);
    const dayOfYear = Math.floor((date - new Date(date.getFullYear(), 0, 0)) / 86400000);
    const clumps = [], trunks = [], branches = [], twigs = [];
    for (const tree of trees) {
      const form = Miniature.treeForm(tree.genus);
      const height = Math.max(3, tree.height_m ?? 8);
      // The register leaves crown width at 0 for some trees; then use the genus's proportions.
      const crown = Math.max(2.0, tree.crown_m >= 1.5 ? tree.crown_m : height * form.ratio);
      const x = tree.x - this.origin.x - offset.x;
      const z = -(tree.y - this.origin.y) - offset.z;
      let crownHeight = form.columnar ? height * 0.85 : Math.min(height * 0.8, Math.max(crown * 1.05, height * 0.55));
      let width = form.columnar ? Math.min(crown, height * 0.3) : crown;
      let crownBase = tree.z + height - crownHeight;
      // Trees beside a track are pruned clear of trams, trains and their wires.
      const fromTrack = Miniature.distanceToTracks(tree.x, tree.y, tracks);
      if (fromTrack < 3.5) {
        crownBase = Math.max(crownBase, tree.z + 3.8);
        crownHeight = Math.max(1.6, tree.z + height - crownBase);
        width = Math.min(width, Math.max(1.2, 2 * (fromTrack + 0.6)));
      }
      let seed = Math.abs(Math.sin(tree.x * 12.9898 + tree.y * 78.233) * 43758.5453) % 1;
      const random = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
      const tone = random() - 0.5;
      // Trees of one kind do not turn on the same day: up to a week either way.
      const { leaves, turned } = Miniature.leafState(form, dayOfYear + Math.round((random() - 0.5) * 14));
      const turnedHere = Math.min(1, Math.max(0, turned + (random() - 0.5) * 0.4));
      const [r, g, b] = form.colour.map((c, i) => c + ((form.autumn ?? form.colour)[i] - c) * turnedHere);
      const colourAt = (v) => [r * (1 + 0.15 * tone) + 0.05 * v, g * (1 + 0.12 * tone) + 0.07 * v, b + 0.03 * v];
      // Position, genus, height and crown width are register facts; the crown's
      // exact shape is typical for the genus, so it is interpreted.
      const shown = this.style.provenance ? (v) => colourAt(v).map((c, i) => c + ([1, 0, 1][i] - c) * 0.45) : colourAt;
      if (form.conifer) {
        // Stacked clumps narrowing upward.
        for (let k = 0; k < 6; k++) {
          const t = k / 5;
          clumps.push({ position: [x, crownBase + crownHeight * (0.1 + 0.8 * t), z], size: width * (1 - 0.75 * t), colour: shown(0.2 * t) });
        }
      } else {
        if (leaves > 0.75) clumps.push({ position: [x, crownBase + crownHeight * 0.5, z], size: Math.min(width, crownHeight) * (form.airy ? 0.6 : 0.8), colour: shown(0) });
        const count = Math.max(6, Math.min(16, Math.round(width * crownHeight / 5)));
        for (let k = 0; k < count; k++) {
          const a = random() * Math.PI * 2, rr = Math.sqrt(random()) * 0.32, v = random();
          const size = Math.min(width, crownHeight) * (form.airy ? 0.38 : 0.5 - 0.15 * rr) * (0.85 + 0.3 * random());
          if (leaves < 0.9 && k % 2 === 0) twigs.push({ position: [x + Math.cos(a) * rr * width * 0.8, crownBase + crownHeight * (0.35 + 0.45 * v), z + Math.sin(a) * rr * width * 0.8], size: Math.min(width, crownHeight) * 0.62 });
          if (random() < leaves) clumps.push({ position: [x + Math.cos(a) * rr * width, crownBase + crownHeight * (0.25 + 0.55 * v), z + Math.sin(a) * rr * width], size: size * (0.6 + 0.4 * leaves), colour: shown(v) });
        }
        // Main limbs show as the leaves fall: from the top of the trunk up and
        // out to the edge of the crown.
        if (leaves < 0.9) {
          const limbs = 5 + Math.floor(random() * 3);
          for (let k = 0; k < limbs; k++) {
            const a = (k / limbs + random() * 0.15) * Math.PI * 2;
            const out = width * (0.3 + 0.15 * random()), up = crownHeight * (0.6 + 0.3 * random());
            branches.push({ from: [x, crownBase + crownHeight * 0.15, z], to: [x + Math.cos(a) * out, crownBase + crownHeight * 0.15 + up, z + Math.sin(a) * out], radius: Math.max(0.05, width * 0.015) });
          }
        }
      }
      trunks.push({ position: [x, tree.z, z], height: crownBase - tree.z + crownHeight * (leaves < 0.9 ? 0.75 : 0.3), radius: Math.max(0.15, width * 0.035) });
    }
    const leafMesh = new THREE.InstancedMesh(clump, leaves, clumps.length);
    const matrix = new THREE.Matrix4(), unit = new THREE.Quaternion(), colour = new THREE.Color();
    clumps.forEach((c, i) => {
      matrix.compose(new THREE.Vector3(...c.position), unit, new THREE.Vector3(c.size, c.size * 0.88, c.size));
      leafMesh.setMatrixAt(i, matrix);
      leafMesh.setColorAt(i, colour.setRGB(...c.colour, THREE.SRGBColorSpace));
    });
    leafMesh.castShadow = leafMesh.receiveShadow = true;
    leafMesh.userData.tree = true;
    const trunkMesh = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.7, 1, 1, 6).translate(0, 0.5, 0), new THREE.MeshLambertMaterial({ color: 0x5b4636 }), trunks.length);
    trunks.forEach((t, i) => {
      matrix.compose(new THREE.Vector3(...t.position), unit, new THREE.Vector3(t.radius * 2, t.height, t.radius * 2));
      trunkMesh.setMatrixAt(i, matrix);
    });
    trunkMesh.castShadow = true;
    trunkMesh.userData.tree = true;
    group.add(leafMesh, trunkMesh);
    if (branches.length) {
      const limbMesh = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.5, 1, 1, 4).translate(0, 0.5, 0), trunkMesh.material, branches.length);
      const up = new THREE.Vector3(0, 1, 0), along = new THREE.Vector3(), turn = new THREE.Quaternion();
      branches.forEach((limb, i) => {
        along.set(limb.to[0] - limb.from[0], limb.to[1] - limb.from[1], limb.to[2] - limb.from[2]);
        const length = along.length();
        turn.setFromUnitVectors(up, along.normalize());
        matrix.compose(new THREE.Vector3(...limb.from), turn, new THREE.Vector3(limb.radius * 2, length, limb.radius * 2));
        limbMesh.setMatrixAt(i, matrix);
      });
      limbMesh.castShadow = true;
      limbMesh.userData.tree = true;
      group.add(limbMesh);
    }
    if (twigs.length) {
      const twigMesh = new THREE.InstancedMesh(clump, crownMaterial(true), twigs.length);
      twigs.forEach((t, i) => {
        matrix.compose(new THREE.Vector3(...t.position), unit, new THREE.Vector3(t.size, t.size * 0.85, t.size));
        twigMesh.setMatrixAt(i, matrix);
        twigMesh.setColorAt(i, colour.setHex(this.style.provenance ? 0xbc4ab0 : 0x7a6d60));
      });
      twigMesh.userData.tree = true;
      group.add(twigMesh);
    }
    group.userData.tree = true;
    return group;
  }



  // Light from every lamp in the register, as a 1 m raster per tile, so a
  // lamp near a tile edge lights both tiles. Pools scale with mast height.
  lampLightFor(tile, lamps) {
    const size = 256, scale = size / TILE_METRES;
    const data = new Float32Array(size * size * 4);
    for (const lamp of lamps) {
      const radius = Math.min(4.5, Math.max(1.5, 0.35 * (lamp.height_m ?? 6))); // a short pool under the mast
      const cx = (lamp.x - tile.x_min) * scale, cy = (tile.y_min + TILE_METRES - lamp.y) * scale;
      const reach = radius * 2 * scale;
      if (cx < -reach || cy < -reach || cx > size + reach || cy > size + reach) continue;
      for (let y = Math.max(0, Math.floor(cy - reach)); y < Math.min(size, Math.ceil(cy + reach)); y++) {
        for (let x = Math.max(0, Math.floor(cx - reach)); x < Math.min(size, Math.ceil(cx + reach)); x++) {
          const d = Math.hypot(x + 0.5 - cx, y + 0.5 - cy) / scale / radius;
          data[(y * size + x) * 4] += Math.exp(-d * d * 3.0);
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
    this.view.bearing = bearing; // the sun follows the view
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
    const az = THREE.MathUtils.degToRad(this.view.bearing + this.style.sunAzimuthRelative);
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

  // A single object (a vehicle) drawn alone with the city's lighting and
  // pixel-art pass, on a transparent background, centred on its origin.
  // heading: compass direction of travel in radians (0 = north).
  renderSprite(object, bearing, metresPerPixel, heading, size) {
    const scene = new THREE.Scene();
    const holder = new THREE.Group();
    holder.add(object);
    holder.rotation.y = Math.PI / 2 - heading;
    scene.add(holder, this.hemisphere.clone(), this.sun.clone(), this.sun.target.clone());
    const sun = scene.children[2];
    sun.castShadow = false;
    const az = THREE.MathUtils.degToRad(bearing + this.style.sunAzimuthRelative), el = THREE.MathUtils.degToRad(this.style.sunElevationDegrees);
    sun.position.set(Math.sin(az) * Math.cos(el) * 100, Math.sin(el) * 100, -Math.cos(az) * Math.cos(el) * 100);
    sun.target = scene.children[3];
    sun.target.position.set(0, 0, 0);
    const { right, up, view } = screenAxes(bearing, this.style.elevationDegrees);
    const camera = new THREE.OrthographicCamera(-size / 2 * metresPerPixel, size / 2 * metresPerPixel, size / 2 * metresPerPixel, -size / 2 * metresPerPixel, 0, CAMERA_DISTANCE * 2);
    camera.position.copy(view).multiplyScalar(-CAMERA_DISTANCE);
    camera.up.copy(up);
    camera.lookAt(0, 0, 0);
    camera.updateMatrixWorld();
    this.resize(size, size);
    const u = this.postMaterial.uniforms;
    u.pixelArt.value = 1; u.outlines.value = 1; u.dither.value = 0; u.saturation.value = this.style.saturation;
    u.depthOutput.value = 0; u.metresPerPixel.value = metresPerPixel; u.transparentBackground.value = 1;
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.setRenderTarget(this.colourTarget);
    this.renderer.render(scene, camera);
    scene.overrideMaterial = this.normalMaterial;
    this.renderer.setRenderTarget(this.normalTarget);
    this.renderer.render(scene, camera);
    this.renderer.setRenderTarget(null);
    this.renderer.render(this.postScene, this.postCamera);
    u.transparentBackground.value = 0;
    return this.canvas.toDataURL('image/png');
  }

  render() {
    const u = this.postMaterial.uniforms;
    const overlay = Boolean(this.style.dataOverlay || this.style.classOutput);
    this.classUniform.value = this.style.classOutput ? 1 : 0;
    u.rawOutput.value = this.style.classOutput ? 1 : 0;
    const night = this.style.night ?? 0;
    this.nightUniform.value = night;
    this.nightHourUniform.value = this.style.nightHour ?? 21;
    this.sun.intensity = this.style.sun * (1 - night) + 0.7 * night;
    this.sun.color.setHex(night > 0.5 ? 0x9fb4ff : 0xfff0d8);
    this.hemisphere.intensity = this.style.ambient * (1 - night) + 1.4 * night;
    this.hemisphere.color.setHex(night > 0.5 ? 0x58627f : 0xdfe8ff);
    this.hemisphere.groundColor.setHex(night > 0.5 ? 0x2c3346 : 0x6f6450);
    // Depth tiles leave out tree crowns: a tram under street trees should
    // still show on the map.
    this.scene.traverse((node) => {
      if (node.userData.nightOnly) node.visible = night > 0.5;
      if (node.userData.tree) node.visible = !this.style.depthOutput;
      if (node.userData.deepOnly) node.visible = (this.screenWindow?.metresPerPixel ?? 1) < 0.16;
    });
    this.overlayUniform.value = this.style.dataOverlay ? 1 : 0;
    const backgroundHex = overlay ? 0x000000 : night > 0.5 ? 0x161c2c : 0xc9d3dd;
    this.scene.background.set(backgroundHex);
    u.background.value.set(((backgroundHex >> 16) & 255) / 255, ((backgroundHex >> 8) & 255) / 255, (backgroundHex & 255) / 255);
    u.pixelArt.value = this.style.pixelArt && !overlay ? 1 : 0;
    u.outlines.value = this.style.outlines && !overlay ? 1 : 0;
    u.dither.value = this.style.dither;
    u.saturation.value = this.style.saturation;
    u.midtones.value = this.style.midtones;
    // Sun direction in view space, for edge highlights (normals are view space).
    u.sunView.value.copy(this.sun.position).sub(this.sun.target.position).normalize().transformDirection(this.camera.matrixWorldInverse);
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
