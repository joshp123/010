// Written by AI on 2026-10-26 by model Claude Opus 5.5.
// The living layer over the pyramid: real public transport from /api/live,
// and simulated cars and cyclists on the real road and cycle networks.
// Everything is placed in RD/NAP and projected into the same art-pixel grid
// as the pyramid; the pyramid's depth tiles hide what a building should hide.

const CAMERA_DISTANCE = 4000; // web/miniature/renderer.js
const STREET_HEIGHT = 3;

// Liveries: RET (Rotterdam's trams, metros and buses) is white with red;
// NS trains are yellow with blue. Window bands mark the sides.
const modeStyle = {
  tram: { length: 30, width: 2.4, height: 3.4, top: '#ecebe6', side: '#d4d1c8', band: '#2b3442', stripe: '#d4302b' },
  metro: { length: 42, width: 2.7, height: 3.6, top: '#e6e6e2', side: '#c9c8c2', band: '#2b3442', stripe: '#d4302b' },
  bus: { length: 12, width: 2.5, height: 3.1, top: '#efefec', side: '#d6d6d1', band: '#2b3442', stripe: '#d4302b' },
  train: { length: 80, width: 2.9, height: 4.0, top: '#f4cf1d', side: '#e5bd12', band: '#1f3c88', stripe: '#1f3c88' },
  ferry: { length: 20, width: 5, height: 3, top: '#f0f0ea', side: '#3a6b8f', band: '#1d2a38' },
  car: { length: 4.5, width: 1.8, height: 1.5, band: '#1d2430' },
  bike: { length: 1.8, width: 0.6, height: 1.6, top: '#2b2f3a', side: '#1d2029' },
};
const carColours = [['#d8d8d4', '#9a9a96'], ['#2f3440', '#1c2028'], ['#8a1f22', '#5c1416'], ['#3b5c8c', '#26405f'], ['#c9ccd0', '#8b8f95'], ['#151719', '#0b0c0d']];

function axes(bearingDegrees, elevationDegrees) {
  const b = bearingDegrees * Math.PI / 180, e = elevationDegrees * Math.PI / 180;
  const forward = [Math.sin(b), 0, -Math.cos(b)];
  return {
    right: [Math.cos(b), 0, Math.sin(b)],
    up: [forward[0] * Math.sin(e), Math.cos(e), forward[2] * Math.sin(e)],
    view: [forward[0] * Math.cos(e), -Math.sin(e), forward[2] * Math.cos(e)],
  };
}

export class LiveLayer {
  constructor(container, { depthBase }) {
    this.canvas = document.createElement('canvas');
    this.canvas.style.cssText = 'position:fixed;inset:0;width:100vw;height:100vh;height:100dvh;pointer-events:none;image-rendering:pixelated;';
    container.after(this.canvas);
    this.context = this.canvas.getContext('2d');
    this.depthBase = depthBase;
    this.depthTiles = new Map();
    this.transit = new Map();
    this.agents = [];
    this.networks = {};
    this.night = false;
  }

  setView(view) { this.view = view; }

  // --- data -----------------------------------------------------------------

  async pollTransit() {
    try {
      const response = await fetch('./api/live', { cache: 'no-store' });
      if (response.ok) {
        const feed = await response.json();
        const now = Date.now();
        for (const [id, lineIndex, , x, y, bearing, observedAt] of feed.vehicles ?? []) {
          const [mode, line] = feed.lines[lineIndex] ?? [];
          if (!mode || !observedAt) continue;
          const observed = observedAt * 1000;
          if (now - observed > 120000) continue; // stale reports are not shown as live
          const vehicle = { id, mode, line, x, y };
          if (Number.isFinite(bearing)) vehicle.heading = bearing * Math.PI / 180;
          const known = this.transit.get(vehicle.id) ?? { track: [] };
          if (vehicle.heading !== undefined && known.heading === undefined) known.heading = vehicle.heading;
          const last = known.track.at(-1);
          if (!last || last.t !== observed) known.track.push({ x: vehicle.x, y: vehicle.y, t: observed });
          while (known.track.length > 4) known.track.shift();
          Object.assign(known, { mode: vehicle.mode, line: vehicle.line, seen: now });
          this.transit.set(vehicle.id, known);
        }
        for (const [id, vehicle] of this.transit) if (now - vehicle.seen > 120000) this.transit.delete(id);
      }
    } catch { /* offline or no live data: the map stays quiet */ }
    setTimeout(() => this.pollTransit(), 10000);
  }

  async loadNetworks(base) {
    for (const kind of ['cars', 'bikes']) {
      try {
        const graph = await fetch(`${base}/${kind}.json`).then((r) => r.json());
        const outgoing = graph.nodes.map(() => []);
        graph.edges.forEach((edge, index) => outgoing[edge[0]].push(index));
        this.networks[kind] = { ...graph, outgoing };
      } catch { /* network not built for this area yet */ }
    }
  }

  // Route geometry per (mode, line), with heights and tunnel flags, so a
  // reported position can be placed on its real track.
  async loadTransitShapes(url) {
    try {
      const data = await fetch(url).then((r) => r.json());
      this.shapes = new Map();
      for (const entry of data.lines) {
        const paths = entry.paths.map((points) => {
          const along = [0];
          for (let i = 1; i < points.length; i++) along.push(along[i - 1] + Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]));
          return { points, along };
        });
        this.shapes.set(`${entry.mode}:${entry.line}`, paths);
      }
    } catch { /* no shapes: vehicles move in straight lines between reports */ }
  }

  // Nearest point on the line's track, as (path, distance along it).
  snap(mode, line, x, y) {
    const paths = this.shapes?.get(`${mode}:${line}`);
    if (!paths) return null;
    let best = null;
    paths.forEach((path, p) => {
      const pts = path.points;
      for (let i = 1; i < pts.length; i++) {
        const ax = pts[i - 1][0], ay = pts[i - 1][1], dx = pts[i][0] - ax, dy = pts[i][1] - ay;
        const len2 = dx * dx + dy * dy || 1;
        const k = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / len2));
        const d = Math.hypot(ax + dx * k - x, ay + dy * k - y);
        if (!best || d < best.d) best = { d, path: p, s: path.along[i - 1] + Math.sqrt(len2) * k };
      }
    });
    return best && best.d < 60 ? best : null;
  }

  pointAt(mode, line, path, s) {
    const shape = this.shapes.get(`${mode}:${line}`)[path];
    const { points, along } = shape;
    let i = 1;
    while (i < points.length - 1 && along[i] < s) i++;
    const a = points[i - 1], b = points[i];
    const k = Math.max(0, Math.min(1, (s - along[i - 1]) / Math.max(0.01, along[i] - along[i - 1])));
    return { x: a[0] + (b[0] - a[0]) * k, y: a[1] + (b[1] - a[1]) * k, z: a[2] + (b[2] - a[2]) * k,
      tunnel: (k < 0.5 ? a[3] : b[3]) === 1, heading: Math.atan2(b[0] - a[0], b[1] - a[1]) };
  }

  // --- simulation -------------------------------------------------------------

  // Traffic over a day in Rotterdam: share of peak traffic by hour.
  static dayProfile(hour) {
    const profile = [0.08, 0.05, 0.04, 0.04, 0.06, 0.15, 0.45, 0.9, 1.0, 0.75, 0.6, 0.62,
      0.68, 0.65, 0.66, 0.75, 0.92, 1.0, 0.85, 0.6, 0.45, 0.35, 0.25, 0.14];
    return profile[Math.floor(hour) % 24];
  }

  // How much traffic an edge carries relative to a residential street.
  static edgeWeight(kind, edge) {
    const cls = edge[4] ?? edge.class;
    if (kind === 'bikes') return cls === 'cycleway' ? 2.5 : 1;
    return { motorway: 6, trunk: 6, primary: 5, secondary: 4, tertiary: 2.5, unclassified: 1, residential: 0.7, living_street: 0.25, service: 0.2 }[cls] ?? 1;
  }

  // Agents near the view, spawned in proportion to road importance and the
  // time of day; each picks an onward edge at junctions (weighted by road
  // importance), keeps a gap to the one ahead, and sometimes stops at
  // junctions as at lights or priority.
  simulate(dt) {
    if (!this.view) return;
    const hour = new Date().toLocaleString('en-GB', { timeZone: 'Europe/Amsterdam', hour: 'numeric', hour12: false });
    const busy = LiveLayer.dayProfile(Number(hour));
    const areaKm2 = Math.PI * (this.view.halfWidthMetres * 1.6) ** 2 / 1e6;
    const want = { cars: Math.min(400, Math.round(260 * busy * areaKm2)), bikes: Math.min(400, Math.round(320 * Math.max(0.15, busy) * areaKm2)) };
    for (const kind of ['cars', 'bikes']) {
      const graph = this.networks[kind];
      if (!graph) continue;
      graph.weights ??= graph.edges.map((edge) => LiveLayer.edgeWeight(kind, edge));
      let count = this.agents.filter((a) => a.kind === kind).length;
      for (let attempts = 0; count < want[kind] && attempts < 600; attempts++) {
        const edge = Math.floor(Math.random() * graph.edges.length);
        if (Math.random() * 6 > graph.weights[edge]) continue;
        const node = graph.nodes[graph.edges[edge][0]];
        if (!this.nearView(node[0], node[1], 1.6)) continue;
        this.agents.push({ kind, edge, along: Math.random(), wait: 0, colour: carColours[Math.floor(Math.random() * carColours.length)], pace: 0.85 + Math.random() * 0.3 });
        count++;
      }
      while (count > want[kind] * 1.2) {
        const i = this.agents.findIndex((a) => a.kind === kind);
        this.agents.splice(i, 1); count--;
      }
    }
    // Gap keeping: order agents along each edge.
    const byEdge = new Map();
    for (const agent of this.agents) {
      const key = `${agent.kind}:${agent.edge}`;
      if (!byEdge.has(key)) byEdge.set(key, []);
      byEdge.get(key).push(agent);
    }
    for (const list of byEdge.values()) list.sort((a, b) => b.along - a.along);
    this.agents = this.agents.filter((agent) => {
      const graph = this.networks[agent.kind];
      let [from, to, speed] = graph.edges[agent.edge];
      const a = graph.nodes[from], b = graph.nodes[to];
      const length = Math.max(0.5, Math.hypot(b[0] - a[0], b[1] - a[1]));
      if (agent.wait > 0) { agent.wait -= dt; return true; }
      const limit = graph.edges[agent.edge][5] ?? speed ?? 30;
      let metresPerSecond = (agent.kind === 'bikes' ? 4.6 : Math.min(limit, 70) / 3.6 * 0.75) * agent.pace;
      const list = byEdge.get(`${agent.kind}:${agent.edge}`);
      const ahead = list[list.indexOf(agent) - 1];
      if (ahead) {
        const gap = (ahead.along - agent.along) * length;
        const keep = agent.kind === 'cars' ? 7 : 2.5;
        if (gap < keep) metresPerSecond = 0;
        else if (gap < keep * 3) metresPerSecond *= (gap - keep) / (keep * 2);
      }
      agent.along += metresPerSecond * dt / length;
      while (agent.along >= 1) {
        agent.along -= 1;
        const options = graph.outgoing[to].filter((e) => graph.edges[e][1] !== from);
        const next = options.length ? options : graph.outgoing[to];
        if (!next.length) return false;
        if (next.length >= 2 && Math.random() < (agent.kind === 'cars' ? 0.3 : 0.15)) agent.wait = 2 + Math.random() * 10;
        let total = 0;
        for (const e of next) total += graph.weights[e];
        let pick = Math.random() * total;
        agent.edge = next.find((e) => (pick -= graph.weights[e]) <= 0) ?? next[0];
        [from, to] = graph.edges[agent.edge];
      }
      const p = this.agentPosition(agent);
      return this.nearView(p.x, p.y, 2.2);
    });
  }

  agentPosition(agent) {
    const graph = this.networks[agent.kind];
    const [from, to] = graph.edges[agent.edge];
    const a = graph.nodes[from], b = graph.nodes[to];
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const length = Math.hypot(dx, dy) || 1;
    // Drive on the right: offset from the centre line.
    const offset = agent.kind === 'cars' ? 1.6 : 0.8;
    return {
      x: a[0] + dx * agent.along + (dy / length) * offset,
      y: a[1] + dy * agent.along - (dx / length) * offset,
      z: a[2] + (b[2] - a[2]) * agent.along,
      heading: Math.atan2(dx, dy),
    };
  }

  nearView(x, y, factor) {
    if (!this.view) return false;
    const { centre, halfWidthMetres } = this.view;
    return Math.hypot(x - centre.x, y - centre.y) < halfWidthMetres * factor;
  }

  // --- drawing ---------------------------------------------------------------

  project(x, y, z) {
    const { m, axes: ax, levelInfo, viewLeft, viewTop } = this.view;
    const p = [x - m.origin_rd[0], z, -(y - m.origin_rd[1])];
    const dot = (v) => v[0] * p[0] + v[1] * p[1] + v[2] * p[2];
    const sx = dot(ax.right) / levelInfo.metres_per_pixel, sy = dot(ax.up) / levelInfo.metres_per_pixel;
    return { px: sx - viewLeft, py: viewTop - sy, sx, sy, depth: dot(ax.view) + CAMERA_DISTANCE };
  }

  depthTile(column, row) {
    const key = `${this.view.bearing}/${column}_${row}`;
    let tile = this.depthTiles.get(key);
    if (tile) return tile.data;
    tile = { data: null };
    this.depthTiles.set(key, tile);
    const image = new Image();
    image.onload = () => {
      const canvas = new OffscreenCanvas(image.width, image.height);
      const context = canvas.getContext('2d', { willReadFrequently: true });
      context.drawImage(image, 0, 0);
      tile.data = context.getImageData(0, 0, image.width, image.height).data;
    };
    image.src = `${this.depthBase}/b${this.view.bearing}/dd/${column}_${row}.png`;
    return null;
  }

  // Hidden if the pyramid shows something nearer the camera at that pixel.
  // Depth is packed at level-0 scale: one file per 1024 x 1024 level-0
  // pixels, one sample per 4 x 4 pixels (tools/pack-depth.py).
  hidden(point) {
    const { m, levelInfo } = this.view;
    const level0 = m.levels[0];
    const scale = levelInfo.metres_per_pixel / level0.metres_per_pixel;
    if (scale > 2) return false;
    const fx = point.sx * scale - level0.left, fy = level0.top - point.sy * scale;
    const column = Math.floor(fx / 1024), row = Math.floor(fy / 1024);
    if (column < 0 || row < 0 || column * 2 >= level0.columns || row * 2 >= level0.rows) return false;
    const data = this.depthTile(column, row);
    if (!data) return false;
    const x = Math.floor((fx - column * 1024) / 4), y = Math.floor((fy - row * 1024) / 4);
    if (x < 0 || y < 0 || x >= 256 || y >= 256) return false;
    const i = (y * 256 + x) * 4;
    const units = data[i] * 256 + data[i + 1];
    if (units === 0) return false;
    return units / 10 + 1000 < point.depth - 1.5;
  }

  // A vehicle as a small box: roof and the two sides facing the camera.
  drawBox(x, y, z, heading, style, top, side, xray = false) {
    const { length, width, height } = style;
    const c = Math.cos(heading), s = Math.sin(heading);
    const corner = (u, v, h) => this.project(x + s * u + c * v, y + c * u - s * v, z + h);
    const base = [corner(length / 2, width / 2, 0), corner(length / 2, -width / 2, 0), corner(-length / 2, -width / 2, 0), corner(-length / 2, width / 2, 0)];
    const roof = [corner(length / 2, width / 2, height), corner(length / 2, -width / 2, height), corner(-length / 2, -width / 2, height), corner(-length / 2, width / 2, height)];
    const centre = this.project(x, y, z + height / 2);
    if (!xray && this.hidden(centre)) return;
    const g = this.context;
    g.fillStyle = side;
    for (let i = 0; i < 4; i++) {
      const j = (i + 1) % 4;
      g.beginPath();
      g.moveTo(Math.round(base[i].px), Math.round(base[i].py));
      g.lineTo(Math.round(base[j].px), Math.round(base[j].py));
      g.lineTo(Math.round(roof[j].px), Math.round(roof[j].py));
      g.lineTo(Math.round(roof[i].px), Math.round(roof[i].py));
      g.fill();
    }
    // Window band and livery stripe along the sides that face the camera.
    const band = (low, high, colour) => {
      if (!colour) return;
      const a = [corner(length / 2, width / 2, low), corner(length / 2, -width / 2, low), corner(-length / 2, -width / 2, low), corner(-length / 2, width / 2, low)];
      const b = [corner(length / 2, width / 2, high), corner(length / 2, -width / 2, high), corner(-length / 2, -width / 2, high), corner(-length / 2, width / 2, high)];
      g.fillStyle = colour;
      for (let i = 0; i < 4; i++) {
        const j = (i + 1) % 4;
        g.beginPath();
        g.moveTo(Math.round(a[i].px), Math.round(a[i].py));
        g.lineTo(Math.round(a[j].px), Math.round(a[j].py));
        g.lineTo(Math.round(b[j].px), Math.round(b[j].py));
        g.lineTo(Math.round(b[i].px), Math.round(b[i].py));
        g.fill();
      }
    };
    band(height * 0.45, height * 0.8, style.band);
    band(height * 0.18, height * 0.3, style.stripe);
    g.fillStyle = top;
    g.beginPath();
    roof.forEach((p, i) => (i ? g.lineTo(Math.round(p.px), Math.round(p.py)) : g.moveTo(Math.round(p.px), Math.round(p.py))));
    g.fill();
    if (this.night && style !== modeStyle.bike) {
      const front = this.project(x + s * length / 2, y + c * length / 2, z + 0.7);
      g.fillStyle = '#fff3c4';
      g.fillRect(Math.round(front.px) - 1, Math.round(front.py) - 1, 2, 2);
    }
  }

  // Cutaway: the metro tunnels drawn as dark corridors through the ground.
  drawTunnels() {
    if (!this.shapes) return;
    const g = this.context;
    g.lineCap = 'round';
    for (const [key, paths] of this.shapes) {
      if (!key.startsWith('metro:') && !key.startsWith('train:')) continue;
      for (const { points } of paths) {
        g.beginPath();
        let open = false;
        for (const point of points) {
          if (point[3] !== 1) { open = false; continue; }
          const p = this.project(point[0], point[1], point[2]);
          if (!open) { g.moveTo(p.px, p.py); open = true; } else g.lineTo(p.px, p.py);
        }
        g.strokeStyle = 'rgba(20, 22, 32, 0.78)';
        g.lineWidth = Math.max(3, 9 / this.view.levelInfo.metres_per_pixel);
        g.stroke();
      }
    }
  }

  transitPosition(vehicle, now) {
    // Shown 15 s behind real time, moving smoothly between observations,
    // along the real track when both reports snap to the same path.
    const t = now - 15000;
    const track = vehicle.track;
    // Snap reports to the track once the route geometry has loaded.
    if (this.shapes) for (const point of track) if (point.on === undefined) point.on = this.snap(vehicle.mode, vehicle.line, point.x, point.y);
    for (let i = track.length - 1; i >= 0; i--) {
      const a = track[i - 1] ?? track[i], b = track[i];
      if (i > 0 && t < a.t) continue;
      if (a.on && b.on && a.on.path === b.on.path && Math.abs(b.on.s - a.on.s) < 2500) {
        const k = b.t > a.t ? Math.max(0, Math.min(1, (t - a.t) / (b.t - a.t))) : 1;
        const p = this.pointAt(vehicle.mode, vehicle.line, a.on.path, a.on.s + (b.on.s - a.on.s) * k);
        if (b.on.s < a.on.s) p.heading += Math.PI;
        return p;
      }
      if (b.on && i === track.length - 1 && t >= b.t) return this.pointAt(vehicle.mode, vehicle.line, b.on.path, b.on.s);
      break;
    }
    if (track.length === 1 || t <= track[0].t) return { ...track[0], heading: vehicle.heading ?? 0 };
    for (let i = 1; i < track.length; i++) {
      const a = track[i - 1], b = track[i];
      if (t <= b.t) {
        const k = (t - a.t) / Math.max(1, b.t - a.t);
        if (Math.hypot(b.x - a.x, b.y - a.y) > 1) vehicle.heading = Math.atan2(b.x - a.x, b.y - a.y);
        return { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k, heading: vehicle.heading ?? 0 };
      }
    }
    return { ...track.at(-1), heading: vehicle.heading ?? 0 };
  }

  draw(now) {
    if (!this.view) return;
    const { width, height } = this.view;
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width; this.canvas.height = height;
    }
    this.canvas.style.width = `${width * this.view.scale}px`;
    this.canvas.style.height = `${height * this.view.scale}px`;
    const g = this.context;
    g.imageSmoothingEnabled = false;
    g.clearRect(0, 0, width, height);
    const items = [];
    for (const agent of this.agents) {
      const p = this.agentPosition(agent);
      const style = agent.kind === 'cars' ? modeStyle.car : modeStyle.bike;
      items.push({ ...p, style, top: agent.kind === 'cars' ? agent.colour[0] : style.top, side: agent.kind === 'cars' ? agent.colour[1] : style.side });
    }
    for (const vehicle of this.transit.values()) {
      const style = modeStyle[vehicle.mode] ?? modeStyle.bus;
      const p = this.transitPosition(vehicle, now);
      if (p.tunnel && !this.cutaway) continue; // underground, out of sight
      items.push({ ...p, z: p.z ?? STREET_HEIGHT, style, top: style.top, side: style.side, xray: p.tunnel });
    }
    // Only what is on screen, far to near, so nearer vehicles cover farther ones.
    for (let i = items.length - 1; i >= 0; i--) {
      const p = this.project(items[i].x, items[i].y, items[i].z ?? STREET_HEIGHT);
      if (p.px < -120 || p.py < -120 || p.px > width + 120 || p.py > height + 120) items.splice(i, 1);
      else items[i].depth = p.depth;
    }
    items.sort((a, b) => b.depth - a.depth);
    this.drawn = items.length;
    if (this.cutaway) this.drawTunnels();
    for (const item of items) this.drawBox(item.x, item.y, item.z ?? STREET_HEIGHT, item.heading, item.style, item.top, item.side, item.xray);
  }

  // Current weather over Rotterdam (Open-Meteo, free, CC BY 4.0). Rain is
  // drawn as streaks slanted by the real wind; heavy cloud dims the light.
  async pollWeather() {
    try {
      const url = 'https://api.open-meteo.com/v1/forecast?latitude=51.92&longitude=4.48&current=precipitation,cloud_cover,wind_speed_10m,wind_direction_10m,weather_code';
      this.weather = (await fetch(url).then((r) => r.json())).current;
    } catch { /* keep the last weather */ }
    setTimeout(() => this.pollWeather(), 10 * 60000);
  }

  drawWeather(now) {
    const weather = this.weather;
    if (!weather) return;
    const g = this.context, { width, height } = this.view;
    const overcast = Math.max(0, (weather.cloud_cover - 60) / 40);
    if (overcast > 0) {
      g.fillStyle = `rgba(70, 80, 100, ${0.10 * overcast})`;
      g.fillRect(0, 0, width, height);
    }
    const rain = weather.precipitation ?? 0;
    const snow = [71, 73, 75, 77, 85, 86].includes(weather.weather_code);
    if (rain <= 0.05) return;
    const drops = Math.min(900, Math.round(width * height / 900 * Math.min(4, rain)));
    // Wind blows from wind_direction; on screen, slant follows its east-west part.
    const slant = Math.sin((weather.wind_direction_10m + 180) * Math.PI / 180 - this.view.axes.right[0]) * Math.min(1, weather.wind_speed_10m / 40);
    g.fillStyle = snow ? 'rgba(255,255,255,0.85)' : 'rgba(200,215,235,0.55)';
    for (let i = 0; i < drops; i++) {
      const seed = (i * 9301 + 49297) % 233280 / 233280;
      const speed = snow ? 0.03 : 0.5;
      const x = ((seed * 7919 + now * speed * slant * 0.3) % width + width) % width;
      const y = ((seed * 104729 % 1) * height + now * speed) % height;
      if (snow) g.fillRect(Math.round(x), Math.round(y), 1, 1);
      else for (let k = 0; k < 3; k++) g.fillRect(Math.round(x + slant * k), Math.round(y + k), 1, 1);
    }
  }

  start() {
    let last = performance.now();
    const frame = (time) => {
      const dt = Math.min(0.1, (time - last) / 1000);
      last = time;
      this.simulate(dt);
      this.draw(Date.now());
      this.drawWeather(Date.now());
      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
    this.pollTransit();
    this.pollWeather();
  }
}

export { axes as liveAxes };
