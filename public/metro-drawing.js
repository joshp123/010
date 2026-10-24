import * as THREE from 'three';

// Drawn from RET's SG3/HSG3 elevations retained in source-data/metro-artwork.
// This illustrates the family, not a rolling-stock identification from the feed.
export function createMetroCarriageGeometry({ roof = false } = {}) {
  const vertices = [], colours = [], glazing = [], materialGroups = [];
  let paintingOverlay = false;
  const palette = { silver:'#bfc4bd', light:'#d7dbd0', lower:'#808d89', roof:'#66736f', dark:'#283c40', glass:'#88a7a4', reflection:'#b4c7bc', teal:'#007f80', red:'#c73536', rubber:'#25312f' };
  const face = (points, tone) => {
    const colour = new THREE.Color(palette[tone] || tone);
    const start = vertices.length / 3;
    for (let i=1;i<points.length-1;i++) for(const p of [points[0],points[i],points[i+1]]) { vertices.push(...p); colours.push(colour.r,colour.g,colour.b); glazing.push(Number(tone === 'glass' || tone === 'reflection')); }
    const count = vertices.length / 3 - start, materialIndex = Number(paintingOverlay);
    const previous = materialGroups.at(-1);
    if (previous?.materialIndex === materialIndex) previous.count += count;
    else materialGroups.push({ start, count, materialIndex });
  };
  const quad = (a,b,c,d,tone) => face([a,b,c,d],tone);
  const block = (x0,x1,y0,y1,z0,z1,tone) => {
    quad([x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],tone);
    quad([x1,y0,z1],[x0,y0,z1],[x0,y1,z1],[x1,y1,z1],tone);
    quad([x0,y0,z1],[x0,y0,z0],[x0,y1,z0],[x0,y1,z1],tone);
    quad([x1,y0,z0],[x1,y0,z1],[x1,y1,z1],[x1,y1,z0],tone);
    quad([x0,y1,z0],[x1,y1,z0],[x1,y1,z1],[x0,y1,z1],tone);
  };
  const along = pixel => (pixel-43)/1962-.5;
  const sections = [[-.5,along(752)],[along(766),along(1279)],[along(1293),.5]];
  if (roof) {
    for (const [start,end] of sections) {
      block(-.49,.49,-.3,.04,start+.006,end-.006,'roof');
      block(-.38,.38,.04,.35,(start+end)/2-.035,(start+end)/2+.035,'lower');
      block(-.34,.34,.35,.42,(start+end)/2-.03,(start+end)/2+.03,'silver');
      for (const offset of [-.018,-.009,0,.009,.018]) block(-.32,.32,.42,.45,(start+end)/2+offset-.001,(start+end)/2+offset+.001,'roof');
    }
  } else {
    const profile=[[-.40,-.38],[.40,-.38],[.49,-.28],[.50,.24],[.43,.43],[-.43,.43],[-.50,.24],[-.49,-.28]];
    for (let section=0;section<sections.length;section++) {
      const [start,end]=sections[section];
      const ring=(z,cab)=>profile.map(([x,y])=>[x*(cab?.84:1),y,z+(cab?Math.sign(-z)*(y+.38)*.026:0)]);
      const rings=[ring(start,section===0),ring(start+.028,false),ring(end-.028,false),ring(end,section===2)];
      for(let r=0;r<3;r++)for(let i=0;i<profile.length;i++)quad(rings[r][i],rings[r][(i+1)%8],rings[r+1][(i+1)%8],rings[r+1][i],i===0?'lower':i===4?'roof':'silver');
      face([...rings[0]].reverse(),'silver');face(rings[3],'silver');
      block(-.4,.4,-.46,-.38,start+.02,end-.02,'rubber');
    }
    for(const gap of [along(759),along(1286)]) {
      block(-.43,.43,-.34,.37,gap-.005,gap+.005,'rubber');
      for(const fold of [-.003,0,.003])block(-.445,.445,-.31,.34,gap+fold-.0006,gap+fold+.0006,'lower');
    }
    paintingOverlay = true;
    const sidePanels = [];
    const sidePanel = (sign,z0,z1,y0,y1,tone) => sidePanels.push({sign,z0,z1,y0,y1,tone});
    for(const sign of [-1,1]) {
      for(const [first,last] of [[220,370],[460,625],[812,974],[1059,1230],[1410,1580],[1667,1823]]) {
        const a=along(first),b=along(last);
        sidePanel(sign,a,b,-.015,.285,'dark');
        sidePanel(sign,a+.004,b-.004,.002,.248,'glass');
        sidePanel(sign,a+.004,b-.004,.205,.248,'reflection');
        sidePanel(sign,(a+b)/2-.0015,(a+b)/2+.0015,-.015,.285,'dark');
      }
      for(const [first,last]of [[136,210],[383,457],[630,704],[983,1057],[1340,1414],[1585,1659],[1836,1910]]) {
        const a=along(first),b=along(last),mid=(a+b)/2;
        sidePanel(sign,a,b,-.36,.31,'lower');
        for(const [left,right]of [[a+.002,mid-.0015],[mid+.0015,b-.002]]) {
          sidePanel(sign,left,right,-.34,.295,'light');
          sidePanel(sign,left+.0015,right-.0015,-.005,.24,'dark');
          sidePanel(sign,left+.003,right-.003,.018,.22,'glass');
        }
      }
      for(const [first,last]of [[505,583],[1721,1799]]) {
        const a=along(first),b=along(last);
        quad([sign*.508,-.34,a-.005],[sign*.508,-.34,b-.005],[sign*.508,-.035,b+.008],[sign*.508,-.035,a+.008],'teal');
        quad([sign*.506,-.34,b-.003],[sign*.506,-.34,b+.005],[sign*.506,.31,b+.018],[sign*.506,.31,b+.010],'red');
        sidePanel(sign,a+.008,b-.006,.015,.245,'glass');
      }
      for(const wheelZ of [-.43,-.385,-.16,-.115,.115,.16,.385,.43]) {
        const points=[];for(let i=0;i<12;i++){const angle=i/12*Math.PI*2;points.push([sign*.405,-.47+Math.sin(angle)*.095,wheelZ+Math.cos(angle)*.0078]);}face(points,'rubber');
        const hub=[];for(let i=0;i<10;i++){const angle=i/10*Math.PI*2;hub.push([sign*.41,-.47+Math.sin(angle)*.043,wheelZ+Math.cos(angle)*.0035]);}face(hub,'lower');
      }
    }
    // One surface partition keeps frames, panes and mullions disjoint in depth.
    for (const sign of [-1,1]) {
      const panels = sidePanels.filter(panel => panel.sign === sign);
      const zCuts = [...new Set(panels.flatMap(panel => [panel.z0,panel.z1]))].sort((a,b)=>a-b);
      const yCuts = [...new Set(panels.flatMap(panel => [panel.y0,panel.y1]))].sort((a,b)=>a-b);
      for (let zi=1;zi<zCuts.length;zi++) for (let yi=1;yi<yCuts.length;yi++) {
        const z0=zCuts[zi-1],z1=zCuts[zi],y0=yCuts[yi-1],y1=yCuts[yi];
        const z=(z0+z1)/2,y=(y0+y1)/2;
        const panel=panels.findLast(panel=>z>panel.z0&&z<panel.z1&&y>panel.y0&&y<panel.y1);
        if (panel) quad([sign*.514,y0,z0],[sign*.514,y0,z1],[sign*.514,y1,z1],[sign*.514,y1,z0],panel.tone);
      }
    }
    const framedGlass = outer => {
      const inset=(u,v)=>outer[0].map((_,axis)=>(1-v)*((1-u)*outer[0][axis]+u*outer[1][axis])+v*((1-u)*outer[3][axis]+u*outer[2][axis]));
      const inner=[inset(.1,.1),inset(.9,.1),inset(.9,.9),inset(.1,.9)];
      for(let edge=0;edge<4;edge++)quad(outer[edge],outer[(edge+1)%4],inner[(edge+1)%4],inner[edge],'dark');
      face(inner,'glass');
    };
    for(const sign of [-1,1]) {
      for(const side of [-1,1]) {
        framedGlass([[side*.452,-.035,sign*.492],[side*.497,-.035,sign*.471],[side*.447,.30,sign*.471],[side*.383,.30,sign*.482]]);
      }
      const end=sign*.5;
      framedGlass([[ -.34,-.04,end-sign*.007],[.34,-.04,end-sign*.007],[.32,.34,end-sign*.017],[-.32,.34,end-sign*.017]]);
      block(-.22,.22,-.39,-.33,end-sign*.006,end+sign*.004,'rubber');
      for(const x of [-.29,.29])block(x-.035,x+.035,-.25,-.225,end-sign*.005,end+sign*.001,'light');
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
  geometry.setAttribute('color',new THREE.Float32BufferAttribute(colours,3));
  geometry.setAttribute('metroGlazing',new THREE.Float32BufferAttribute(glazing,1));
  for (const group of materialGroups) geometry.addGroup(group.start, group.count, group.materialIndex);
  geometry.computeVertexNormals();return geometry;
}
