// Written by AI on 2026-10-26 by model Claude Opus 5.5.
// The living layer over the pyramid: real public transport from /api/live,
// and simulated cars and cyclists on the real road and cycle networks.
// Everything is placed in RD/NAP and projected into the same art-pixel grid
// as the pyramid; the pyramid's depth tiles hide what a building should hide.

const CAMERA_DISTANCE = 4000; // web/miniature/renderer.js
const STREET_HEIGHT = 3;

const modeStyle = {
  tram: { length: 30, width: 2.4, height: 3.4, top: '#f2c230', side: '#b8861c' },
  metro: { length: 42, width: 2.7, height: 3.6, top: '#e8453c', side: '#a42a24' },
  bus: { length: 12, width: 2.5, height: 3.1, top: '#d9dde3', side: '#8f97a3' },
  train: { length: 80, width: 2.9, height: 4.0, top: '#f5d31f', side: '#2c4fa0' },
  ferry: { length: 20, width: 5, height: 3, top: '#f0f0ea', side: '#3a6b8f' },
  car: { length: 4.5, width: 1.8, height: 1.5 },
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
        for (const vehicle of feed.vehicles ?? []) {
          const known = this.transit.get(vehicle.id) ?? { track: [] };
          const observed = (vehicle.observed ?? feed.timestamp ?? now / 1000) * 1000;
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

  // --- simulation -------------------------------------------------------------

  // Keep a fixed number of agents near the view: cars on the car network,
  // cyclists on the cycle network, each choosing a random onward edge at every
  // junction and never turning back unless the street ends.
  simulate(dt) {
    const want = { cars: 160, bikes: 140 };
    for (const kind of ['cars', 'bikes']) {
      const graph = this.networks[kind];
      if (!graph) continue;
      let count = this.agents.filter((a) => a.kind === kind).length;
      for (let attempts = 0; count < want[kind] && attempts < 400; attempts++) {
        const edge = Math.floor(Math.random() * graph.edges.length);
        const [from] = graph.edges[edge];
        const node = graph.nodes[from];
        if (!this.nearView(node[0], node[1], 1.6)) continue;
        this.agents.push({ kind, edge, along: Math.random(), colour: carColours[Math.floor(Math.random() * carColours.length)], pace: 0.8 + Math.random() * 0.4 });
        count++;
      }
    }
    this.agents = this.agents.filter((agent) => {
      const graph = this.networks[agent.kind];
      let [from, to, speed] = graph.edges[agent.edge];
      const a = graph.nodes[from], b = graph.nodes[to];
      const length = Math.max(0.5, Math.hypot(b[0] - a[0], b[1] - a[1]));
      const metresPerSecond = (agent.kind === 'bikes' ? 4.5 : Math.min(speed ?? 30, 50) / 3.6 * 0.7) * agent.pace;
      agent.along += metresPerSecond * dt / length;
      while (agent.along >= 1) {
        agent.along -= 1;
        const options = graph.outgoing[to].filter((e) => graph.edges[e][1] !== from);
        const next = options.length ? options : graph.outgoing[to];
        if (!next.length) return false;
        agent.edge = next[Math.floor(Math.random() * next.length)];
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

  depthTile(level, column, row) {
    const key = `${this.view.bearing}/${level}/${column}_${row}`;
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
    image.src = `${this.depthBase}/b${this.view.bearing}/d${level}/${column}_${row}.png`;
    return null;
  }

  // Hidden if the pyramid shows something nearer the camera at that pixel.
  hidden(point) {
    const { level, levelInfo } = this.view;
    if (level > 1) return false;
    const fx = point.sx - levelInfo.left, fy = levelInfo.top - point.sy;
    const column = Math.floor(fx / 512), row = Math.floor(fy / 512);
    const data = this.depthTile(level, column, row);
    if (!data) return false;
    const x = Math.floor((fx - column * 512) / 2), y = Math.floor((fy - row * 512) / 2);
    if (x < 0 || y < 0 || x >= 256 || y >= 256) return false;
    const i = (y * 256 + x) * 4;
    const units = data[i] * 256 + data[i + 1];
    if (units === 0) return false;
    return units / 10 + 1000 < point.depth - 1.2;
  }

  // A vehicle as a small box: roof and the two sides facing the camera.
  drawBox(x, y, z, heading, style, top, side) {
    const { length, width, height } = style;
    const c = Math.cos(heading), s = Math.sin(heading);
    const corner = (u, v, h) => this.project(x + s * u + c * v, y + c * u - s * v, z + h);
    const base = [corner(length / 2, width / 2, 0), corner(length / 2, -width / 2, 0), corner(-length / 2, -width / 2, 0), corner(-length / 2, width / 2, 0)];
    const roof = [corner(length / 2, width / 2, height), corner(length / 2, -width / 2, height), corner(-length / 2, -width / 2, height), corner(-length / 2, width / 2, height)];
    const centre = this.project(x, y, z + height / 2);
    if (this.hidden(centre)) return;
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

  transitPosition(vehicle, now) {
    // Shown 15 s behind real time, moving smoothly between observations.
    const t = now - 15000;
    const track = vehicle.track;
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
      items.push({ ...p, z: STREET_HEIGHT, style, top: style.top, side: style.side });
    }
    // Far to near, so nearer vehicles cover farther ones.
    for (const item of items) item.depth = this.project(item.x, item.y, item.z ?? STREET_HEIGHT).depth;
    items.sort((a, b) => b.depth - a.depth);
    for (const item of items) this.drawBox(item.x, item.y, item.z ?? STREET_HEIGHT, item.heading, item.style, item.top, item.side);
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
