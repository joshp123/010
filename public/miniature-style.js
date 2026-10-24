import * as THREE from 'three';
import { featureAppearance } from './data/appearance.js';

const observedColors = new Map(featureAppearance.map(record => [`${record.layer}:${record.sourceName}`, new THREE.Color(record.color)]));

const BUILDING_COLORS = ['#d5c9ad', '#bda58a', '#a77d62', '#c5c4b5', '#aebfc1', '#e0d4bb', '#a68c7b', '#8d9ea3'].map(color => new THREE.Color(color));
const GROUND_COLORS = Object.fromEntries(Object.entries({
  water: '#367b86', green: '#73936d', road: '#8d9694', cycleway: '#b78770',
  footway: '#c9c4b2', transit: '#a5a999', paving: '#b5b5a7', quay: '#9ca99e',
  building: '#b4ad98', sand: '#d7c8a4', other: '#b3b5a1',
}).map(([kind, color]) => [kind, new THREE.Color(color)]));

function hashNumber(value) { let hash = 2166136261; for (const char of String(value)) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619); return (hash >>> 0); }
function classOfGround(attributes) {
  const type = String(attributes.KLASSE_IMG || '').toLowerCase();
  const classification = String(attributes.KLASSE || '').toLowerCase();
  const purpose = String(attributes.FUNCTIE || classification).toLowerCase();
  const surface = String(attributes.FYSIEKVK || '').toLowerCase();
  if (type.includes('water')) return 'water';
  if (type.startsWith('begroeid') || /gras|groen|struik|bos|tuin/.test(surface)) return 'green';
  if (type.includes('pand')) return 'building';
  if (/fiets|rijwiel/.test(purpose)) return 'cycleway';
  if (/voet|trap/.test(purpose)) return 'footway';
  if (/ov.baan|spoor/.test(purpose)) return 'transit';
  if (/rijbaan/.test(purpose)) return 'road';
  if (/kade|muur/.test(classification)) return 'quay';
  if (/zand/.test(surface)) return 'sand';
  if (/verharding/.test(surface) || type.includes('wegdeel')) return 'paving';
  return 'other';
}

export function featureColor(kind, attributes, fallbackIdentifier) {
  const observedColor = observedColors.get(`${kind}:${attributes['gml:name']}`);
  if (observedColor) return observedColor;
  if (kind === 'ground') return GROUND_COLORS[classOfGround(attributes)];
  if (kind === 'trees') return new THREE.Color('#638168');
  if (kind === 'bridges') return new THREE.Color('#d1d7cb');
  if (kind === 'tanks') return new THREE.Color('#d9d9cb');
  if (kind === 'lights') return new THREE.Color('#586564');
  const identifier = attributes.GEBOUWNUMMER || attributes['gml:id'] || fallbackIdentifier;
  return BUILDING_COLORS[hashNumber(identifier) % BUILDING_COLORS.length];
}

export function streetColor(kind) {
  return kind === 'rail' ? new THREE.Color('#777e73') : GROUND_COLORS[kind] || GROUND_COLORS.road;
}

export function yardColor(kind) {
  return new THREE.Color({ 'open-paving': '#b5b5a7', 'closed-paving': '#929b98', yard: '#b4b29b', 'crane-rail': '#687770' }[kind] || '#b4b29b');
}

export function createCityMaterial(kind, uniforms) {
  const material = new THREE.MeshStandardMaterial({ color: 0xffffff, vertexColors: true, roughness: 0.94, metalness: 0, flatShading: true, side: THREE.DoubleSide });
  material.onBeforeCompile = shader => {
    shader.uniforms.cityNight = uniforms.night;
    shader.uniforms.citySnow = uniforms.snow;
    shader.uniforms.cityReflection = uniforms.reflection;
    shader.uniforms.cityReflectionMatrix = uniforms.reflectionMatrix;
    shader.uniforms.cityReflectionTexel = uniforms.reflectionTexel;
    shader.vertexShader = `varying vec3 cityWorldPosition; varying vec3 cityWorldNormal;\n` + shader.vertexShader;
    shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>', `#include <begin_vertex>\n vec4 cityVertex = vec4(transformed, 1.0);\n #ifdef USE_INSTANCING\n cityVertex = instanceMatrix * cityVertex;\n #endif\n cityWorldPosition = (modelMatrix * cityVertex).xyz; cityWorldNormal = normalize(mat3(modelMatrix) * objectNormal);`);
    shader.fragmentShader = `uniform float cityNight; uniform float citySnow; uniform sampler2D cityReflection; uniform mat4 cityReflectionMatrix; uniform vec2 cityReflectionTexel; varying vec3 cityWorldPosition; varying vec3 cityWorldNormal;\n float cityHash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123); }\n` + shader.fragmentShader;
    let surface = '';
    if (kind === 'buildings') {
      surface = `
        vec3 cityNormal = normalize(cityWorldNormal);
        float cityHeightAboveEllipsoid = cityWorldPosition.y + dot(cityWorldPosition.xz, cityWorldPosition.xz) / (2.0 * 6371000.0);
        float cityWall = 1.0 - smoothstep(0.15, 0.55, abs(cityNormal.y));
        vec2 cityTangent = normalize(vec2(cityNormal.z + 0.00001, -cityNormal.x));
        float cityHorizontal = dot(cityWorldPosition.xz, cityTangent);
        vec2 cityWindowCell = vec2(cityHorizontal / 3.1, (cityHeightAboveEllipsoid - 1.1) / 3.25);
        vec2 cityWindowUV = fract(cityWindowCell);
        vec2 cityWindowAA = min(fwidth(cityWindowCell) * 0.5, vec2(0.24));
        float cityWindow = smoothstep(0.19-cityWindowAA.x, 0.19+cityWindowAA.x, cityWindowUV.x) * (1.0-smoothstep(0.66-cityWindowAA.x, 0.66+cityWindowAA.x, cityWindowUV.x)) * smoothstep(0.18-cityWindowAA.y, 0.18+cityWindowAA.y, cityWindowUV.y) * (1.0-smoothstep(0.73-cityWindowAA.y, 0.73+cityWindowAA.y, cityWindowUV.y)) * cityWall;
        cityWindow *= 1.0-smoothstep(0.8, 2.2, max(fwidth(cityWindowCell.x),fwidth(cityWindowCell.y)));
        cityWindow *= smoothstep(3.2, 5.5, cityHeightAboveEllipsoid);
        float cityWindowSeed = cityHash(floor(cityWindowCell) + floor(vColor.rg * 91.0));
        float cityLit = step(0.66, cityWindowSeed);
        vec3 cityWindowLight = mix(vec3(1.0, 0.29, 0.055), vec3(1.0, 0.61, 0.22), step(0.77, cityWindowSeed));
        diffuseColor.rgb *= mix(1.0, 0.68, 1.0 - cityWall);
        diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.12, 0.23, 0.27), cityWindow * 0.62);
        diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.86, 0.90, 0.91), citySnow * smoothstep(0.4, 0.9, cityNormal.y));
        // Generic fallback openings are schematic, so their night emission stays
        // subordinate to the separately prepared, source-supported glazing.
        // This term is exactly zero in day mode; no facade/day colour changes.
        totalEmissiveRadiance += cityWindowLight * cityWindow * cityLit * cityNight * 0.25;
      `;
    } else if (kind === 'ground') {
      surface = `
        float cityWater = step(vColor.r * 1.7, vColor.g) * step(vColor.r * 1.9, vColor.b);
        if (cityWater > 0.5 && cityNight > 0.1) {
        vec4 cityReflectedPosition = cityReflectionMatrix * vec4(cityWorldPosition, 1.0);
        vec2 cityReflectionUV = cityReflectedPosition.xy / cityReflectedPosition.w * 0.5 + 0.5;
        float cityWave = sin(cityWorldPosition.z * 0.72 + sin(cityWorldPosition.x * 0.15) * 2.0);
        cityReflectionUV += vec2(cityWave * 0.005, sin(cityWorldPosition.x * 0.31 + cityWorldPosition.z * 1.4) * 0.001);
        vec2 cityReflectionBlur = cityReflectionTexel * vec2(5.0, 2.0);
        vec3 cityReflectionLight = texture2D(cityReflection, cityReflectionUV).rgb * 0.28;
        cityReflectionLight += texture2D(cityReflection, cityReflectionUV + vec2(cityReflectionBlur.x, 0.0)).rgb * 0.18;
        cityReflectionLight += texture2D(cityReflection, cityReflectionUV - vec2(cityReflectionBlur.x, 0.0)).rgb * 0.18;
        cityReflectionLight += texture2D(cityReflection, cityReflectionUV + cityReflectionBlur).rgb * 0.09;
        cityReflectionLight += texture2D(cityReflection, cityReflectionUV - cityReflectionBlur).rgb * 0.09;
        cityReflectionLight += texture2D(cityReflection, cityReflectionUV + vec2(-cityReflectionBlur.x, cityReflectionBlur.y)).rgb * 0.09;
        cityReflectionLight += texture2D(cityReflection, cityReflectionUV + vec2(cityReflectionBlur.x, -cityReflectionBlur.y)).rgb * 0.09;
        cityReflectionLight /= vec3(1.0) + cityReflectionLight * 2.0;
        float cityRipple = 0.12 + 0.60 * pow(max(0.0, cityWave), 4.0);
        float cityReflectionInside = step(0.0, cityReflectionUV.x) * step(cityReflectionUV.x, 1.0) * step(0.0, cityReflectionUV.y) * step(cityReflectionUV.y, 1.0);
        totalEmissiveRadiance += cityReflectionLight * cityWater * cityNight * cityRipple * cityReflectionInside * 0.22;
        }
      `;
    } else if (kind === 'bridges') {
      surface = `
        float cityEdgeLight = pow(1.0 - abs(normalize(cityWorldNormal).y), 3.0);
        totalEmissiveRadiance += vColor.rgb * vec3(0.8, 0.9, 1.0) * cityEdgeLight * cityNight * 0.32;
      `;
    }
    shader.fragmentShader = shader.fragmentShader.replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>\n${surface}`);
  };
  material.customProgramCacheKey = () => `010-miniature-${kind}-v4`;
  return material;
}


export function createLampPoolMaterial(night, pixelsPerMetre, surfaceStrength = { value: 0 }) {
  const material = new THREE.ShaderMaterial({
    uniforms: { night, pixelsPerMetre, surfaceStrength }, transparent: true, depthWrite: false,
    blending: THREE.AdditiveBlending, toneMapped: false,
    vertexShader: `uniform float pixelsPerMetre; attribute float _pool_radius;
      void main() {
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        gl_Position.z -= 0.000002 * gl_Position.w;
        gl_PointSize = max(1.0, 2.0 * _pool_radius * pixelsPerMetre);
      }`,
    fragmentShader: `uniform float night; uniform float surfaceStrength;
      void main() {
        vec2 distanceFromLamp = (gl_PointCoord - 0.5) * vec2(2.0, 3.4641016);
        float radius = length(distanceFromLamp);
        if (radius > 1.0) discard;
        float falloff = exp(-radius * radius * 4.0) * (1.0 - smoothstep(0.65, 1.0, radius));
        gl_FragColor = vec4(vec3(1.0, 0.58, 0.22), falloff * night * (1.0 - surfaceStrength) * 0.16);
      }`,
  });
  material.defaultAttributeValues._pool_radius = [9];
  return material;
}


// Shared world-space corridor clipping for city meshes, point lamps and shafts.
export function applyMetroCutaway(material, uniforms) {
  material.defaultAttributeValues = {...material.defaultAttributeValues, _metroExcised:[0]};
  const compile = material.onBeforeCompile;
  const cacheKey = material.customProgramCacheKey.bind(material);
  const originalKey = cacheKey();
  material.onBeforeCompile = function(shader, renderer) {
    compile.call(this, shader, renderer);
    Object.assign(shader.uniforms, {
      metroCutawayEnabled: uniforms.enabled,
      metroCutawayMask: uniforms.mask,
      metroCutawayBounds: uniforms.bounds,
      metroCutawayProjection: uniforms.projection,
    });
    shader.vertexShader = 'attribute float _metroExcised; varying float metroExcised; varying vec3 metroWorldPosition;\n' + shader.vertexShader;
    const worldPosition = `metroExcised = _metroExcised; vec4 metroVertex = vec4(position, 1.0);
      #ifdef USE_INSTANCING
      metroVertex = instanceMatrix * metroVertex;
      #endif
      metroWorldPosition = (modelMatrix * metroVertex).xyz;`;
    shader.vertexShader = shader.vertexShader.replace(/void main\s*\(\s*\)\s*{/, 'void main() {\n' + worldPosition);
    shader.fragmentShader = `uniform float metroCutawayEnabled; uniform sampler2D metroCutawayMask; uniform vec4 metroCutawayBounds; uniform vec2 metroCutawayProjection; varying vec3 metroWorldPosition; varying float metroExcised;\n` + shader.fragmentShader;
    shader.fragmentShader = shader.fragmentShader.replace(/void main\s*\(\s*\)\s*{/, `void main() {
      if (metroCutawayEnabled > 0.5) {
        if (metroExcised > 0.5) discard;
        vec2 metroProjectedXZ = metroWorldPosition.xz - metroWorldPosition.y * metroCutawayProjection;
        vec2 metroUV = (metroProjectedXZ - metroCutawayBounds.xy) / metroCutawayBounds.zw;
        if (all(greaterThanEqual(metroUV, vec2(0.0))) && all(lessThanEqual(metroUV, vec2(1.0))) && texture2D(metroCutawayMask, metroUV).r > 0.5) discard;
      }`);
  };
  material.customProgramCacheKey = () => originalKey + '-metro-cutaway-v2';
  return material;
}
