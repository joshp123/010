import * as THREE from 'three';

const VEHICLE_STYLES = {
  bus: { color: '#c49558', width: 2.7, height: 3.1, length: 12 },
  tram: { color: '#b56a59', width: 2.6, height: 3.3, length: 28 },
  metro: { color: '#d1d7cc', width: 3, height: 3.5, length: 48 },
  train: { color: '#d1af58', width: 3.2, height: 3.8, length: 72 },
  ferry: { color: '#698a9a', width: 5, height: 3.5, length: 20 },
  'metro-position': { color: '#d19a45', width: 2.2, height: 2.2, length: 2.2 },
  unknown: { color: '#b3b6ac', width: 3, height: 3, length: 9 },
};
const TUNNEL_DEPTH = 12;
const CLASSIFICATION_DISTANCE = 18;
const CHAMBER_HALF_WIDTH = 3;
const TUNNEL_GROUND_CONTEXT = { source: 'metro-section', preferGround: true };

function pointOnSegment(point, start, end) {
  const dx = end.x - start.x, dz = end.z - start.z;
  const fraction = THREE.MathUtils.clamp(((point.x - start.x) * dx + (point.z - start.z) * dz) / (dx * dx + dz * dz || 1), 0, 1);
  return { distance: Math.hypot(point.x - start.x - fraction * dx, point.z - start.z - fraction * dz), fraction, heading: Math.atan2(dx, dz) };
}

// project returns the intended local ground surface plus offsetMetres. Shapes
// are symmetric symbols: dimensions and rail-axis orientation are illustrative.
export function createTransitView({ project, localPosition, requestRender = () => {} }) {
  const place = project || localPosition;
  const group = new THREE.Group();
  group.name = 'Observed public transport';
  const cutawayGroup = new THREE.Group();
  cutawayGroup.name = 'BRT tunnel plan · depth illustrated';
  cutawayGroup.visible = false;
  group.add(cutawayGroup);
  const box = new THREE.BoxGeometry(1, 1, 1);
  const reportMarker = new THREE.OctahedronGeometry(.65);
  const bodyMaterial = new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: 0.9, metalness: 0, flatShading: true });
  const roofMaterial = new THREE.MeshStandardMaterial({ color: '#e3e2ce', roughness: 0.95, metalness: 0 });
  const floorMaterial = new THREE.MeshStandardMaterial({ color: '#293333', roughness: 1, side: THREE.DoubleSide });
  const earthMaterial = new THREE.MeshStandardMaterial({ color: '#88745c', roughness: 1, side: THREE.DoubleSide });
  const tunnelMaterial = new THREE.MeshStandardMaterial({ color: '#89928b', roughness: 1, side: THREE.DoubleSide });
  const rimMaterial = new THREE.MeshStandardMaterial({color:'#b1a18a',roughness:1,side:THREE.DoubleSide});
  const metroBodyMaterial = bodyMaterial.clone(), metroRoofMaterial = roofMaterial.clone();
  for (const material of [metroBodyMaterial, metroRoofMaterial]) {
    const isBody = material === metroBodyMaterial;
    material.onBeforeCompile = shader => {
      shader.vertexShader = 'varying vec3 transitLocal;\n' + shader.vertexShader;
      shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\n transitLocal = position;');
      shader.fragmentShader = 'varying vec3 transitLocal;\n' + shader.fragmentShader;
      shader.fragmentShader = shader.fragmentShader.replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
        // Three illustrated articulated sections; no rolling-stock identity claim.
        float carriage = fract((transitLocal.z + 0.5) * 3.0);
        if (carriage < 0.013 || carriage > 0.987) discard;
        ${isBody ? `
        float side = step(0.49, abs(transitLocal.x));
        float window = step(-0.02, transitLocal.y) * step(transitLocal.y, 0.31);
        float pane = step(0.12, fract(carriage * 6.0)) * step(fract(carriage * 6.0), 0.86);
        float glazing = window * mix(step(0.49, abs(transitLocal.z)), pane, side);
        diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.025, 0.065, 0.075), glazing * 0.92);
        float stripe = side * step(-0.15, transitLocal.y) * step(transitLocal.y, -0.07);
        diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.16, 0.36, 0.32), stripe);
        totalEmissiveRadiance += vec3(0.18, 0.14, 0.07) * glazing;
        ` : ''}
      `);
    };
    material.customProgramCacheKey = () => `010-metro-articulation-${isBody ? 'body' : 'roof'}-v1`;
  }
  const trackMaterials = [
    new THREE.MeshStandardMaterial({ color: '#414a46', roughness: 1, side: THREE.DoubleSide }),
    new THREE.MeshStandardMaterial({ color: '#62665c', roughness: 1, side: THREE.DoubleSide }),
    new THREE.MeshStandardMaterial({ color: '#949e92', roughness: 0.8, side: THREE.DoubleSide }),
  ];
  const batches = new Map();
  const transform = new THREE.Object3D(), color = new THREE.Color();
  let snapshot = { vehicles: [] }, records = [], railSegments = [], cutaway = false, cutawayMask = null;
  let span = 1700, viewportHeight = 900, camera = null;
  const maskViewDirection = new THREE.Vector3();
  let physicalData = null, sectionAnchor = null, sectionSegments = [], sectionDiagnostics = null, selectedReportId = null;
  let tunnelSegments = [], maskRebuilds = 0, maskMilliseconds = 0, maskMetresPerPixel = Infinity;

  function batchFor(mode, count) {
    let batch = batches.get(mode);
    if (!batch || batch.capacity < count) {
      if (batch) { group.remove(batch.body, batch.roof); batch.body.dispose(); batch.roof.dispose(); }
      const capacity = Math.max(16, count);
      const body = new THREE.InstancedMesh(mode === 'metro-position' ? reportMarker : box, mode === 'metro' ? metroBodyMaterial : bodyMaterial, capacity);
      const roof = new THREE.InstancedMesh(box, mode === 'metro' ? metroRoofMaterial : roofMaterial, capacity);
      body.name = mode === 'metro-position' ? 'Reported metro position · track mismatch' : `Observed ${mode}`; roof.name = `${mode} roofs`;
      body.instanceMatrix.setUsage(THREE.DynamicDrawUsage); roof.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      body.castShadow = true; body.receiveShadow = true;
      group.add(body, roof);
      batch = { body, roof, capacity, records: [] };
      batches.set(mode, batch);
    }
    return batch;
  }

  function classify(position, routeHeading = null) {
    let nearest = null;
    for (const segment of railSegments) {
      const result = pointOnSegment(position, segment.start, segment.end);
      if (routeHeading !== null && Math.abs(Math.cos(routeHeading-result.heading)) < .94) continue;
      if (result.distance <= CLASSIFICATION_DISTANCE && (!nearest || result.distance < nearest.distance)) nearest = { ...result, id: segment.id, form: segment.form, relativeLevel: segment.relativeLevel, segment };
    }
    return nearest;
  }

  function routeAxis(report) {
    if (!report.routeShape) return null;
    const eastMetresPerDegree = 111320 * Math.cos(report.latitude * Math.PI / 180);
    let nearest = null;
    for (const line of report.routeShape) for (let index = 1; index < line.length; index++) {
      const [lonA, latA] = line[index - 1], [lonB, latB] = line[index];
      const start = { x: (lonA - report.longitude) * eastMetresPerDegree, z: (report.latitude - latA) * 111320 };
      const end = { x: (lonB - report.longitude) * eastMetresPerDegree, z: (report.latitude - latB) * 111320 };
      const result = pointOnSegment({ x: 0, z: 0 }, start, end);
      if (result.distance <= 40 && (!nearest || result.distance < nearest.distance)) nearest = result;
    }
    return nearest?.heading ?? null;
  }

  function rebuild(refreshReports = false) {
    if (refreshReports) {
      records = [];
      for (const report of snapshot.vehicles) {
        const mode = VEHICLE_STYLES[report.mode] ? report.mode : 'unknown';
        let ground = place(report.latitude, report.longitude, 0);
        const rail = mode === 'metro' ? classify(ground, routeAxis(report)) : null;
        const underground = rail?.form === 'tunnel';
        if (underground) ground = place(report.latitude, report.longitude, 0, TUNNEL_GROUND_CONTEXT);
        const routeShapeHeading = routeAxis(report);
        const routeAligned = rail && routeShapeHeading !== null && Math.abs(Math.cos(routeShapeHeading - rail.heading)) > .94;
        const mapMatched = underground && (rail.distance <= 5.5 || routeAligned);
        let representedGround = ground, representedPosition = null;
        if (mapMatched) {
          const longitude = THREE.MathUtils.lerp(rail.segment.startGeo[0], rail.segment.endGeo[0], rail.fraction);
          const latitude = THREE.MathUtils.lerp(rail.segment.startGeo[1], rail.segment.endGeo[1], rail.fraction);
          representedGround = place(latitude, longitude, 0, TUNNEL_GROUND_CONTEXT);
          representedPosition = {latitude, longitude, approximate:true, offsetMetres:rail.distance, method:routeAligned?'route-axis-compatible physical track':'nearest physical track within 5.5m'};
        }
        const routeHeading = mapMatched ? rail.heading : Number.isFinite(report.bearing) ? Math.PI - report.bearing * Math.PI / 180 : rail?.heading ?? routeAxis(report);
        const orientation = mapMatched ? 'source-track-axis' : Number.isFinite(report.bearing) ? 'reported-bearing' : rail ? 'source-track-axis' : routeHeading !== null ? 'source-route-axis' : 'camera-facing-symbol';
        const record = { report, ground, representedGround, representedPosition, rail, underground, mode, routeHeading, orientation, uncertainTrackPosition: underground && !mapMatched };
        records.push(record);
      }
    }
    const modes = new Map();
    for (const record of records) {
      if (record.underground && (!cutaway || selectedReportId !== record.report.id)) continue;
      const displayMode = record.uncertainTrackPosition ? 'metro-position' : record.mode;
      if (!modes.has(displayMode)) modes.set(displayMode, []);
      modes.get(displayMode).push(record);
    }
    for (const [mode, reports] of modes) {
      const batch = batchFor(mode, reports.length), style = VEHICLE_STYLES[mode];
      batch.records = reports;
      for (let index = 0; index < reports.length; index++) {
        const record = reports[index], report = record.report;
        const scale = record.underground ? 1 : THREE.MathUtils.clamp(4 * span / viewportHeight / style.length, 1, 8);
        const verticalOffset = record.underground && mode !== 'metro-position' ? -TUNNEL_DEPTH : 0;
        const base = record.underground ? record.representedGround.clone().add(new THREE.Vector3(0, verticalOffset, 0)) : place(report.latitude, report.longitude, verticalOffset);
        transform.position.copy(base); transform.position.y += style.height * scale / 2 + 0.4;
        // Compass bearings are clockwise from north; local +Z points south.
        transform.rotation.set(0, record.routeHeading ?? (camera ? Math.atan2(camera.position.x - base.x, camera.position.z - base.z) : 0), 0);
        transform.scale.set(style.width * scale, style.height * scale, style.length * scale);
        transform.updateMatrix(); batch.body.setMatrixAt(index, transform.matrix);
        color.set(style.color);
        if (report.freshness !== 'fresh' || !report.sourceConnected) color.set('#737d80');
        batch.body.setColorAt(index, color);
        transform.position.y += style.height * scale * 0.48;
        transform.scale.set(style.width * scale * 0.8, style.height * scale * 0.16, style.length * scale * (mode === 'metro' ? .97 : .76));
        transform.updateMatrix(); batch.roof.setMatrixAt(index, transform.matrix);
        batch.roof.setColorAt(index, new THREE.Color(report.freshness === 'fresh' && report.sourceConnected ? '#ffffff' : '#929b99'));
      }
      batch.body.count = reports.length; batch.roof.count = mode === 'metro-position' ? 0 : reports.length;
      batch.body.instanceMatrix.needsUpdate = batch.roof.instanceMatrix.needsUpdate = true;
      if (batch.body.instanceColor) batch.body.instanceColor.needsUpdate = true;
      if (batch.roof.instanceColor) batch.roof.instanceColor.needsUpdate = true;
      batch.body.computeBoundingSphere(); batch.roof.computeBoundingSphere();
    }
    for (const [mode, batch] of batches) if (!modes.has(mode)) { batch.body.count = batch.roof.count = 0; batch.records = []; }
    group.updateMatrixWorld(true);
    requestRender();
  }

  function projectRails() {
    railSegments = [];
    for (const segment of physicalData?.segments || []) {
      const points = segment.coordinates.map(([longitude, latitude]) => place(latitude, longitude, 0));
      for (let index = 1; index < points.length; index++) railSegments.push({ ...segment, coordinates: undefined, start: points[index - 1], end: points[index], startGeo: segment.coordinates[index - 1], endGeo: segment.coordinates[index] });
    }
    tunnelSegments = railSegments.filter(segment => segment.form === 'tunnel');
  }

  function setMetroData(data) {
    physicalData = data; projectRails();
    cutawayMask?.texture.dispose();
    const texture = new THREE.DataTexture(new Uint8Array([0]), 1, 1, THREE.RedFormat, THREE.UnsignedByteType);
    texture.minFilter = texture.magFilter = THREE.LinearFilter;
    texture.generateMipmaps = false; texture.needsUpdate = true;
    maskMetresPerPixel = Infinity;
    cutawayMask = { texture, bounds: new THREE.Vector4(0, 0, 1, 1), projection: new THREE.Vector2(), illustrativeDepthMetres: TUNNEL_DEPTH, source: data.source, classification: 'BRT explicitly in tunnel', sourceSegmentCount: data.segments.filter(segment => segment.form === 'tunnel').length };
    rebuild(true); updateCutawayMask(true); rebuild();
  }

  function inViewport(record) {
    if (!camera) return false;
    const position = record.ground.clone();
    position.y += record.underground ? -TUNNEL_DEPTH + 2 : 2;
    position.project(camera);
    return Math.abs(position.x) <= 1 && Math.abs(position.y) <= 1 && Math.abs(position.z) <= 1;
  }
  function fresh(record) { return record.report.freshness === 'fresh' && record.report.sourceConnected; }
  function clipToSection(segment, centre, radius) {
    const dx = segment.end.x - segment.start.x, dz = segment.end.z - segment.start.z;
    const x = segment.start.x - centre.x, z = segment.start.z - centre.z;
    const a = dx * dx + dz * dz;
    if (a < .001) return null;
    const b = 2 * (x * dx + z * dz), c = x * x + z * z - radius * radius;
    const discriminant = b * b - 4 * a * c;
    if (discriminant < 0) return null;
    const from = Math.max(0, (-b - Math.sqrt(discriminant)) / (2 * a));
    const to = Math.min(1, (-b + Math.sqrt(discriminant)) / (2 * a));
    if (to <= from) return null;
    const distance = Math.sqrt(a) * (to - from);
    const steps = Math.max(1, Math.ceil(distance / 8));
    const samples = [];
    for (let index = 0; index <= steps; index++) {
      const fraction = from + (to - from) * index / steps;
      const longitude = THREE.MathUtils.lerp(segment.startGeo[0], segment.endGeo[0], fraction);
      const latitude = THREE.MathUtils.lerp(segment.startGeo[1], segment.endGeo[1], fraction);
      // Source endpoint heights are not a ground profile. Re-query only the
      // actual local cut points, retaining their latitude/longitude evidence.
      const point = place(latitude, longitude, 0, TUNNEL_GROUND_CONTEXT);
      samples.push({ point, longitude, latitude, surfaceSource: point.userData?.surfaceSource || 'unspecified projection', measured: point.userData?.measured ?? null });
    }
    return samples.slice(1).map((sample,index)=>({ ...segment, start:samples[index].point, end:sample.point, startSample:samples[index], endSample:sample, capStart: index===0&&from>.001, capEnd:index===samples.length-2&&to<.999 }));
  }

  function drawSection(segments, halfWidth, viewDirection) {
    for (const child of [...cutawayGroup.children]) { cutawayGroup.remove(child); child.geometry.dispose(); }
    const surfaces = [[], [], [], [], [], [], []]; // floor, earth, concrete, bed, sleepers, rail, ground edge
    const addQuad = (a,b,c,d,out) => { for (const point of [a,b,c,a,c,d]) out.push(point.x,point.y,point.z); };
    for (const segment of segments) {
      const {start,end}=segment;
      const direction=end.clone().sub(start).setY(0).normalize();
      const side=new THREE.Vector3(-direction.z,0,direction.x);
      const corners=[start.clone().addScaledVector(side,halfWidth),start.clone().addScaledVector(side,-halfWidth),end.clone().addScaledVector(side,-halfWidth),end.clone().addScaledVector(side,halfWidth)];
      const floor=corners.map(point=>point.clone().add(new THREE.Vector3(0,-TUNNEL_DEPTH,0)));
      const lower=floor.map(point=>point.clone().add(new THREE.Vector3(0,4.2,0)));
      addQuad(...floor,surfaces[0]);
      // Retain the far earth face, remove only the near face to reveal depth.
      const edge=side.dot(viewDirection)>0 ? [0,3] : [1,2];
      // A restrained surface lip and lower maintenance ledge distinguish
      // ground, illustrated soil and the concrete chamber without inventing strata.
      const inward=side.clone().multiplyScalar(edge[0]===0?-.35:.35);
      addQuad(corners[edge[0]],corners[edge[1]],corners[edge[1]].clone().add(inward),corners[edge[0]].clone().add(inward),surfaces[6]);
      for(const sign of [-1,1]){
        const outer=side.clone().multiplyScalar(sign*(halfWidth-.12)),inner=side.clone().multiplyScalar(sign*(halfWidth-.65));
        const lift=new THREE.Vector3(0,-TUNNEL_DEPTH+.3,0);
        addQuad(start.clone().add(outer).add(lift),end.clone().add(outer).add(lift),end.clone().add(inner).add(lift),start.clone().add(inner).add(lift),surfaces[2]);
      }
      const farEnd = direction.dot(viewDirection) < 0 ? (segment.capStart ? [[0,1]] : []) : (segment.capEnd ? [[3,2]] : []);
      for (const [a,b] of [edge, ...farEnd]) {
        addQuad(corners[a],corners[b],lower[b],lower[a],surfaces[1]);
        addQuad(lower[a],lower[b],floor[b],floor[a],surfaces[2]);
      }
      const trackStart=start.clone().add(new THREE.Vector3(0,-TUNNEL_DEPTH,0));
      const trackEnd=end.clone().add(new THREE.Vector3(0,-TUNNEL_DEPTH,0));
      const strip=(from,to,hw,y,out)=>{
        const lift=new THREE.Vector3(0,y,0), lateral=side.clone().multiplyScalar(hw);
        addQuad(from.clone().add(lateral).add(lift),from.clone().sub(lateral).add(lift),to.clone().sub(lateral).add(lift),to.clone().add(lateral).add(lift),out);
      };
      strip(trackStart,trackEnd,1.8,.02,surfaces[3]);
      const length=start.distanceTo(end);
      for(let distance=.6;distance<length;distance+=1.2){const centre=trackStart.clone().lerp(trackEnd,distance/length);strip(centre.clone().addScaledVector(direction,-.14),centre.clone().addScaledVector(direction,.14),1.3,.08,surfaces[4]);}
      for(const offset of [-.75,.75])strip(trackStart.clone().addScaledVector(side,offset),trackEnd.clone().addScaledVector(side,offset),.075,.2,surfaces[5]);
    }
    const materialList=[floorMaterial,earthMaterial,tunnelMaterial,...trackMaterials,rimMaterial];
    const names=['Section floor','Cut earth face · depth illustrated','Concrete chamber','Illustrated track bed','Illustrated sleepers','Illustrated rails','Section ground edge'];
    for(let i=0;i<surfaces.length;i++){
      if(!surfaces[i].length)continue;
      const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(surfaces[i],3));geometry.computeVertexNormals();
      const mesh=new THREE.Mesh(geometry,materialList[i]);mesh.name=names[i];mesh.receiveShadow=true;cutawayGroup.add(mesh);
    }
  }

  function updateCutawayMask(force = false) {
    if (!cutawayMask || !camera || !cutaway && !force) return;
    const started=performance.now();
    const viewDirection=camera.getWorldDirection(new THREE.Vector3());
    const ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2(0,0),camera);
    const centre=ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0,1,0),0),new THREE.Vector3());
    if(!centre)return;
    const candidates=records.filter(record=>record.underground&&inViewport(record));
    candidates.sort((a,b)=>Number(fresh(b))-Number(fresh(a))||a.ground.distanceToSquared(centre)-b.ground.distanceToSquared(centre));
    const previousSelectedReportId=selectedReportId;
    selectedReportId=candidates[0]?.report.id??null;
    let selectedRail=candidates[0]?.rail?.segment||null;
    let anchor=candidates[0]?.representedGround.clone()||null;
    if(!anchor){
      let best=Infinity;
      for(const segment of tunnelSegments){const result=pointOnSegment(centre,segment.start,segment.end);if(result.distance<best){best=result.distance;selectedRail=segment;anchor=segment.start.clone().lerp(segment.end,result.fraction);}}
      if(best>span*.8)anchor=null;
    }
    const metresPerPixel=span/viewportHeight;
    if(!force&&previousSelectedReportId===selectedReportId&&sectionAnchor&&anchor&&sectionAnchor.distanceToSquared(anchor)<100&&maskViewDirection.distanceToSquared(viewDirection)<.000001&&metresPerPixel>=maskMetresPerPixel*.8&&metresPerPixel<=maskMetresPerPixel*1.25)return;
    sectionAnchor=anchor;
    sectionSegments=anchor&&selectedRail?tunnelSegments.filter(segment=>segment.id===selectedRail.id).flatMap(segment=>clipToSection(segment,anchor,38)||[]):[];
    // An offset report is uncertainty, not evidence for a wider tunnel.
    const halfWidth=CHAMBER_HALF_WIDTH;
    drawSection(sectionSegments,halfWidth,viewDirection);
    const samples=sectionSegments.flatMap(segment=>[segment.startSample,segment.endSample]);
    const heights=samples.map(sample=>sample.point.y);
    const nearestAtReport=candidates[0]&&sectionSegments.map(segment=>({segment,...pointOnSegment(candidates[0].ground,segment.start,segment.end)})).sort((a,b)=>a.distance-b.distance)[0];
    const atReport=nearestAtReport?THREE.MathUtils.lerp(nearestAtReport.segment.start.y,nearestAtReport.segment.end.y,nearestAtReport.fraction):null;
    const geometryBounds=new THREE.Box3().setFromObject(cutawayGroup);
    sectionDiagnostics={
      surfaceHeightRange:heights.length?[Math.min(...heights),Math.max(...heights)]:null,
      floorHeightRange:heights.length?[Math.min(...heights)-TUNNEL_DEPTH,Math.max(...heights)-TUNNEL_DEPTH]:null,
      geometryBounds:geometryBounds.isEmpty()?null:{min:geometryBounds.min.toArray(),max:geometryBounds.max.toArray()},
      widthMetres:halfWidth*2,
      groundSamples:samples.map(sample=>({latitude:sample.latitude,longitude:sample.longitude,height:sample.point.y,surfaceSource:sample.surfaceSource,measured:sample.measured})),
      report:candidates[0]?{id:candidates[0].report.id,latitude:candidates[0].report.latitude,longitude:candidates[0].report.longitude,groundHeight:candidates[0].ground.y,surfaceSource:candidates[0].ground.userData?.surfaceSource||'unspecified projection',measured:candidates[0].ground.userData?.measured??null,nearestSectionHeight:atReport,heightDifference:atReport===null?null:candidates[0].ground.y-atReport,sourceAxisDistanceMetres:candidates[0].rail.distance,representedPosition:candidates[0].representedPosition,renderedAs:candidates[0].uncertainTrackPosition?'position marker':'illustrated train',bodyBottomHeight:candidates[0].uncertainTrackPosition?null:candidates[0].representedGround.y-TUNNEL_DEPTH+.4,bodyTopHeight:candidates[0].uncertainTrackPosition?null:candidates[0].representedGround.y-TUNNEL_DEPTH+.4+VEHICLE_STYLES.metro.height}:null,
    };
    const projection=cutawayMask.projection.set(viewDirection.x/Math.min(-.1,viewDirection.y),viewDirection.z/Math.min(-.1,viewDirection.y));
    const projectToOpening=point=>new THREE.Vector3(point.x-point.y*projection.x,0,point.z-point.y*projection.y);
    const bounds=new THREE.Box3();
    // The aperture is exactly the projected physical section, never a dilated
    // centreline. Every removed city ray must have a floor/earth face behind it.
    const triangles=[];
    for (const mesh of cutawayGroup.children.slice(0,3)) {
      const position=mesh.geometry.getAttribute('position');
      for(let index=0;index<position.count;index+=3){
        const triangle=[];
        for(let vertex=0;vertex<3;vertex++){
          const point=projectToOpening(new THREE.Vector3().fromBufferAttribute(position,index+vertex));
          triangle.push(point); bounds.expandByPoint(point);
        }
        triangles.push(triangle);
      }
    }
    if(bounds.isEmpty()){bounds.min.set(-1,0,-1);bounds.max.set(1,0,1);}
    bounds.expandByScalar(1);
    const sx=bounds.max.x-bounds.min.x,sz=bounds.max.z-bounds.min.z;
    // A tighter geometric aperture needs enough precision to avoid jagged soil
    // edges at close phone scales. Coverage is still capped at1024 per axis.
    const resolution=Math.min(metresPerPixel,.15);
    const width=Math.min(1024,Math.max(64,Math.ceil(sx/resolution))),height=Math.min(1024,Math.max(64,Math.ceil(sz/resolution)));
    const cellX=sx/width,cellZ=sz/height;
    const pixels=new Uint8Array(width*height);
    const edge=(a,b,x,z)=>(x-a.x)*(b.z-a.z)-(z-a.z)*(b.x-a.x);
    for(const [a,b,c] of triangles){
      const left=Math.max(0,Math.floor((Math.min(a.x,b.x,c.x)-bounds.min.x)/cellX)),right=Math.min(width-1,Math.ceil((Math.max(a.x,b.x,c.x)-bounds.min.x)/cellX));
      const top=Math.max(0,Math.floor((Math.min(a.z,b.z,c.z)-bounds.min.z)/cellZ)),bottom=Math.min(height-1,Math.ceil((Math.max(a.z,b.z,c.z)-bounds.min.z)/cellZ));
      if(Math.abs(edge(a,b,c.x,c.z))<1e-8)continue;
      for(let y=top;y<=bottom;y++)for(let x=left;x<=right;x++){
        const px=bounds.min.x+(x+.5)*cellX,pz=bounds.min.z+(y+.5)*cellZ;
        const e0=edge(a,b,px,pz),e1=edge(b,c,px,pz),e2=edge(c,a,px,pz);
        if((e0>=0&&e1>=0&&e2>=0)||(e0<=0&&e1<=0&&e2<=0))pixels[y*width+x]=255;
      }
    }
    cutawayMask.texture.image={data:pixels,width,height};cutawayMask.texture.needsUpdate=true;
    cutawayMask.bounds.set(bounds.min.x,bounds.min.z,sx,sz);
    maskMetresPerPixel=metresPerPixel;maskViewDirection.copy(viewDirection);
    maskRebuilds++;maskMilliseconds=performance.now()-started;
  }

  async function loadMetro(url = './data/transit/metro-physical.json.gz') {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Metro physical geometry HTTP ${response.status}`);
    let bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes[0] === 31 && bytes[1] === 139) bytes = new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
    setMetroData(JSON.parse(new TextDecoder().decode(bytes)));
    return cutawayMask;
  }

  function presentReport(record) {
    if (!record) return null;
    return { ...record.report, presentation: { physicalForm: record.rail?.form || 'unclassified', sourceSegmentId: record.rail?.id || null, illustrativeDepthMetres: record.underground ? TUNNEL_DEPTH : null, orientation: record.orientation, representedPosition:record.representedPosition, dimensions: 'illustrative', sourceAxisDistanceMetres: record.rail?.distance ?? null, positionUncertainty: record.uncertainTrackPosition ? 'Reported point is outside the illustrated track chamber; position marker, not track-snapped train' : null } };
  }

  function pick(raycaster) {
    const hits = raycaster.intersectObjects([...batches.values()].flatMap(batch => [batch.body, batch.roof]), false);
    const hit = hits.find(hit => {
      const batch = [...batches.values()].find(batch => batch.body === hit.object || batch.roof === hit.object);
      return cutaway || !batch.records[hit.instanceId].underground;
    });
    if (!hit) return null;
    const batch = [...batches.values()].find(batch => batch.body === hit.object || batch.roof === hit.object);
    const record = batch.records[hit.instanceId];
    return presentReport(record);
  }

  function metroVisibility() {
    const metros = records.filter(record => record.mode === 'metro');
    const visible = metros.filter(inViewport);
    const underground = visible.filter(record => record.underground && (!cutaway || record.report.id===selectedReportId));
    const freshCount = underground.filter(fresh).length;
    const focusCandidates = metros.filter(record=>record.underground&&(fresh(record)||record.report.freshness==='stale'));
    focusCandidates.sort((a,b)=>Number(fresh(b))-Number(fresh(a))||(b.report.observedAt||0)-(a.report.observedAt||0));
    const focus=focusCandidates[0]?.report;
    return {
      metroObservations: metros.length,
      visibleMetroObservations: visible.length,
      visibleUndergroundObservations: underground.length,
      visibleFreshMetroObservations: visible.filter(fresh).length,
      visibleFreshUndergroundObservations: freshCount,
      metroFocusCandidates:focusCandidates.map(({report,uncertainTrackPosition})=>({inSection:report.id===selectedReportId,presentationState:uncertainTrackPosition?'marker':'train',id:report.id,latitude:report.latitude,longitude:report.longitude,label:report.label,observedAt:report.observedAt,freshness:report.freshness,sourceConnected:report.sourceConnected})),
      metroFocus: focus ? {id:focus.id,latitude:focus.latitude,longitude:focus.longitude,label:focus.label,observedAt:focus.observedAt,freshness:focus.freshness,sourceConnected:focus.sourceConnected} : null,
      cutawayShortMessage:!cutaway?null:underground.some(record=>record.uncertainTrackPosition)?'Report off mapped track':freshCount?'Fresh metro · approximate position':underground.length?'Older/unverified metro · not live':'No metro report',
      cutawayMessage: !cutaway ? null : underground.some(record=>record.uncertainTrackPosition)
        ? `${fresh(underground.find(record=>record.uncertainTrackPosition)) ? 'Fresh report' : 'Older/unverified report'} · ${Math.round(underground.find(record=>record.uncertainTrackPosition).rail.distance)} m from mapped track`
        : freshCount
        ? `Fresh metro · approximate track position`
        : underground.length ? `${underground.length} ${underground.every(record=>record.report.freshness==='stale')?'older':'unverified'} metro ${underground.length===1?'report':'reports'} · not live`
        : 'No metro report in this section',
      section: sectionAnchor ? {radiusMetres:38,selectedReportId,segmentCount:sectionSegments.length,illustrativeDepthMetres:TUNNEL_DEPTH,...sectionDiagnostics} : null,
    };
  }

  return {
    group,
    update(nextSnapshot) { snapshot = nextSnapshot; projectRails(); rebuild(true); updateCutawayMask(true); rebuild(); },
    setView(view) { camera = view.camera || camera; span = view.span ?? span; viewportHeight = view.viewportHeight ?? viewportHeight; updateCutawayMask(); rebuild(); },
    setCutaway(enabled) { cutaway = typeof enabled === 'object' ? enabled.enabled : enabled; cutawayGroup.visible = cutaway; updateCutawayMask(); rebuild(); return cutawayMask; },
    getCutaway() { return cutawayMask; },
    getSectionGeometry() { return {enabled:cutaway,segments:sectionSegments,halfWidth:CHAMBER_HALF_WIDTH,depth:TUNNEL_DEPTH,projection:cutawayMask?.projection||new THREE.Vector2()}; },
    setMetroData, loadMetro, pick,
    getReport(id) { return presentReport(records.find(record => record.report.id === id)); },
    statistics() { return { ...metroVisibility(), observations: records.length, underground: records.filter(record => record.underground).length, batches: batches.size, drawCalls: [...batches.values()].filter(batch => batch.body.count).length * 2 + (cutaway ? cutawayGroup.children.length : 0), railSegments: railSegments.length, mask: cutawayMask ? { width: cutawayMask.texture.image.width, height: cutawayMask.texture.image.height, metresPerTexel: [cutawayMask.bounds.z / cutawayMask.texture.image.width, cutawayMask.bounds.w / cutawayMask.texture.image.height], rebuilds: maskRebuilds, milliseconds: maskMilliseconds } : null }; },
    dispose() {
      for (const batch of batches.values()) { batch.body.dispose(); batch.roof.dispose(); }
      for (const child of cutawayGroup.children) child.geometry.dispose();
      cutawayMask?.texture.dispose(); box.dispose(); reportMarker.dispose(); bodyMaterial.dispose(); roofMaterial.dispose(); metroBodyMaterial.dispose(); metroRoofMaterial.dispose(); tunnelMaterial.dispose(); floorMaterial.dispose(); earthMaterial.dispose(); rimMaterial.dispose(); trackMaterials.forEach(material => material.dispose());
      group.removeFromParent(); group.clear(); batches.clear();
    },
  };
}
