import * as THREE from 'three';

// RET's published SG3 side elevation supplies the three connected sections,
// tapered cabs, silver body and dark glazing. This is a family illustration;
// the position feed does not identify the reported train's rolling stock.
export function createMetroCarriageGeometry({ roof = false } = {}) {
  const vertices = [];
  const quad = (a,b,c,d) => { for (const point of [a,b,c,a,c,d]) vertices.push(...point); };
  const profile = roof
    ? [[-.49,-.5],[.49,-.5],[.49,.1],[.40,.5],[-.40,.5],[-.49,.1]]
    : [[-.43,-.5],[.43,-.5],[.5,-.35],[.5,.35],[.40,.5],[-.40,.5],[-.5,.35],[-.5,-.35]];
  for (let carriage=0;carriage<3;carriage++) {
    const start = -.5 + carriage / 3 + .004;
    const end = -.5 + (carriage + 1) / 3 - .004;
    const ring = (z, cab) => profile.map(([x,y]) => [x * (cab ? .89 : 1), y, z + (cab ? Math.sign(-z) * Math.max(0,y+.32)*.025 : 0)]);
    const rings = [ring(start,carriage===0), ring(start+.026,false), ring(end-.026,false),ring(end,carriage===2)];
    for(let station=0;station<rings.length-1;station++)for(let i=0;i<profile.length;i++) {
      const next=(i+1)%profile.length; quad(rings[station][i],rings[station][next],rings[station+1][next],rings[station+1][i]);
    }
    for(const [index,reverse]of [[0,true],[3,false]]) {
      const ringPoints = reverse ? [...rings[index]].reverse() : rings[index];
      for(let i=1;i<ringPoints.length-1;i++)vertices.push(...ringPoints[0],...ringPoints[i],...ringPoints[i+1]);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
  geometry.computeVertexNormals(); return geometry;
}
