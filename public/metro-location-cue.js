import * as THREE from 'three';

// This annotation relates the underground inspector to the actual source track.
// It is deliberately screen-sized rather than a train parked on the road.
export function createMetroLocationCue() {
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(0, 1, 1, 0, -1, 1);
  const canvas = document.createElement('canvas');
  canvas.width = 192; canvas.height = 96;
  const context = canvas.getContext('2d');
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const badge = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false, depthWrite: false, toneMapped: false }));
  badge.scale.set(64, 32, 1); badge.renderOrder = 2; scene.add(badge);
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(64 * 6);
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const track = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ color: '#f4cd60', transparent: true, opacity: .8, depthTest: false, depthWrite: false, toneMapped: false }));
  track.frustumCulled = false; scene.add(track);
  let state = null, previousLabel = '';
  function update(section, cityCamera, width, height) {
    state = null;
    if (!section.enabled || !section.streetAnchor) return false;
    camera.right = width; camera.top = height; camera.updateProjectionMatrix();
    const projected = section.streetAnchor.clone().project(cityCamera);
    const actual = { x: (projected.x + 1) * width / 2, y: (1 - projected.y) * height / 2 };
    const x = THREE.MathUtils.clamp(actual.x, 40, width - 40);
    const y = THREE.MathUtils.clamp(actual.y, 112, height - section.viewportHeight - 34);
    const offscreen = Math.abs(x - actual.x) > 1 || Math.abs(y - actual.y) > 1;
    const directions = ['→', '↘', '↓', '↙', '←', '↖', '↑', '↗'];
    const arrow = offscreen ? directions[(Math.round(Math.atan2(actual.y - y, actual.x - x) / (Math.PI / 4)) + 8) % 8] : '↓';
    const label = `${section.report?.label || 'M'} ${arrow}`;
    if (label !== previousLabel) {
      previousLabel = label; context.clearRect(0, 0, 192, 96);
      context.fillStyle = '#203943'; context.strokeStyle = '#f4cd60'; context.lineWidth = 5;
      context.beginPath(); context.roundRect(5, 5, 182, 86, 24); context.fill(); context.stroke();
      context.fillStyle = '#fff8df'; context.font = 'bold 43px system-ui'; context.textAlign = 'center'; context.textBaseline = 'middle';
      context.fillText(label, 96, 49, 165); texture.needsUpdate = true;
    }
    badge.position.set(x, height - y, .1);
    let count = 0;
    for (const segment of section.sourceTrack || []) {
      if (count >= 64) break;
      for (const [index, endpoint] of [segment.start, segment.end].entries()) {
        const point = endpoint.clone().project(cityCamera), offset = count * 6 + index * 3;
        positions[offset] = (point.x + 1) * width / 2;
        positions[offset + 1] = (point.y + 1) * height / 2;
        positions[offset + 2] = 0;
      }
      count++;
    }
    geometry.setDrawRange(0, count * 2); geometry.attributes.position.needsUpdate = true;
    state = { x, y, offscreen, anchor: section.streetAnchor, report: section.report };
    return true;
  }
  return { scene, camera, update,
    hit(x, y) { return state && Math.abs(x - state.x) <= 34 && Math.abs(y - state.y) <= 22 ? state : null; },
    dispose() { geometry.dispose(); track.material.dispose(); badge.material.dispose(); texture.dispose(); },
  };
}
