// Minimal GTFS-Realtime VehiclePosition subset, using the official field IDs.
// Unknown fields/extensions are skipped; missing observations stay missing.
const textDecoder = new TextDecoder();

class ProtobufReader {
  constructor(input) {
    this.bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
    this.view = new DataView(this.bytes.buffer, this.bytes.byteOffset, this.bytes.byteLength);
    this.offset = 0;
  }
  integer() {
    let value = 0, multiplier = 1;
    for (let byteIndex = 0; byteIndex < 10; byteIndex++) {
      if (this.offset >= this.bytes.length) throw new Error('Truncated protobuf varint');
      const byte = this.bytes[this.offset++];
      value += (byte & 127) * multiplier;
      if (!(byte & 128)) return value;
      multiplier *= 128;
    }
    throw new Error('Invalid protobuf varint');
  }
  block() {
    const length = this.integer(), start = this.offset;
    this.offset += length;
    if (this.offset > this.bytes.length) throw new Error('Truncated protobuf message');
    return this.bytes.subarray(start, this.offset);
  }
  fields(consume) {
    while (this.offset < this.bytes.length) {
      const tag = this.integer(), field = Math.floor(tag / 8), wire = tag & 7;
      if (!field) throw new Error('Invalid protobuf field');
      let value;
      if (wire === 0) value = this.integer();
      else if (wire === 2) value = this.block();
      else if (wire === 5) { if (this.offset + 4 > this.bytes.length) throw new Error('Truncated protobuf float'); value = this.view.getFloat32(this.offset, true); this.offset += 4; }
      else if (wire === 1) { if (this.offset + 8 > this.bytes.length) throw new Error('Truncated protobuf double'); value = this.view.getFloat64(this.offset, true); this.offset += 8; }
      else throw new Error(`Unsupported protobuf wire type ${wire}`);
      consume(field, value, wire);
    }
  }
}

function readMessage(bytes, fields) {
  const result = {};
  new ProtobufReader(bytes).fields((field, value, wire) => {
    const definition = fields[field];
    if (!definition) return;
    const [name, type] = definition;
    result[name] = type === 'text' ? textDecoder.decode(value) : typeof type === 'function' ? type(value) : value;
  });
  return result;
}
const readTrip = bytes => readMessage(bytes, { 1: ['id', 'text'], 2: ['startTime', 'text'], 3: ['startDate', 'text'], 4: ['scheduleRelationship'], 5: ['routeId', 'text'], 6: ['directionId'] });
const readPosition = bytes => readMessage(bytes, { 1: ['latitude'], 2: ['longitude'], 3: ['bearing'], 4: ['odometer'], 5: ['speed'] });
const readVehicle = bytes => readMessage(bytes, { 1: ['trip', readTrip], 2: ['position', readPosition], 3: ['stopSequence'], 4: ['stopStatus'], 5: ['timestamp'], 7: ['stopId', 'text'], 8: ['vehicle', value => readMessage(value, { 1: ['id', 'text'], 2: ['label', 'text'] })] });

export function decodeVehiclePositions(input) {
  const result = { header: {}, entities: [] };
  new ProtobufReader(input).fields((field, bytes) => {
    if (field === 1) result.header = readMessage(bytes, { 1: ['version', 'text'], 2: ['incrementality'], 3: ['timestamp'], 4: ['feedVersion', 'text'] });
    if (field === 2) result.entities.push(readMessage(bytes, { 1: ['id', 'text'], 2: ['deleted'], 4: ['vehicle', readVehicle] }));
  });
  return result;
}

function decodeCoordinates(bytes) {
  const reader = new ProtobufReader(bytes), coordinates = [], previous = [0, 0];
  while (reader.offset < reader.bytes.length) {
    const coordinate = [];
    for (let axis = 0; axis < 2; axis++) {
      const encoded = reader.integer();
      previous[axis] += encoded % 2 ? -(encoded + 1) / 2 : encoded / 2;
      coordinate.push(previous[axis] / 1e7);
    }
    coordinates.push(coordinate);
  }
  return coordinates;
}

function decodeLine(bytes) {
  let coordinates = [];
  new ProtobufReader(bytes).fields((field, value) => { if (field === 1) coordinates = decodeCoordinates(value); });
  return coordinates;
}

// Input is decompressed map.pb. The .proto beside the source provenance defines
// the complete, small schema; GTFS route types remain their original integers.
export function decodeTransitMap(input) {
  const result = { routes: [], shapes: [], trips: new Map(), municipality: [] };
  new ProtobufReader(input).fields((field, bytes) => {
    if (field === 1) result.routes.push(readMessage(bytes, { 1: ['id', 'text'], 2: ['shortName', 'text'], 3: ['longName', 'text'], 4: ['type'], 5: ['agencyId', 'text'], 6: ['agencyName', 'text'] }));
    if (field === 2) {
      const shape = { lines: [] };
      new ProtobufReader(bytes).fields((key, value) => { if (key === 1) shape.id = textDecoder.decode(value); if (key === 2) shape.lines.push(decodeLine(value)); });
      result.shapes.push(shape);
    }
    if (field === 3) {
      const trip = readMessage(bytes, { 1: ['id', 'text'], 2: ['routeIndex'], 3: ['shapeIndex'] });
      result.trips.set(trip.id, trip);
    }
    if (field === 4) {
      const rings = [];
      new ProtobufReader(bytes).fields((key, value) => { if (key === 1) rings.push(decodeLine(value)); });
      result.municipality.push(rings);
    }
    if (field === 5) result.version = bytes;
  });
  if (result.version !== 1) throw new Error('Unsupported Rotterdam transit map format');
  return result;
}

function insideRing(longitude, latitude, ring) {
  let inside = false;
  for (let index = 0, previous = ring.length - 1; index < ring.length; previous = index++) {
    const [x, y] = ring[index], [previousX, previousY] = ring[previous];
    if ((y > latitude) !== (previousY > latitude) && longitude < (previousX - x) * (latitude - y) / (previousY - y) + x) inside = !inside;
  }
  return inside;
}

export function withinTransitMunicipality(longitude, latitude, polygons) {
  return polygons.some(rings => insideRing(longitude, latitude, rings[0]) && !rings.slice(1).some(ring => insideRing(longitude, latitude, ring)));
}

// These are upstream-reported coordinates, not a claim of independent GPS.
// In particular, upstream metro fixes can originate from operational stop data.
// Stale/missing timestamps remain visible to the caller; no time is substituted.
export function municipalVehicleReports(feed, map) {
  const routeById = new Map(map.routes.map(route => [route.id, route]));
  const reports = [];
  for (const entity of feed.entities) {
    const vehicle = entity.vehicle, position = vehicle?.position;
    if (entity.deleted || !position || !Number.isFinite(position.latitude) || !Number.isFinite(position.longitude) || !withinTransitMunicipality(position.longitude, position.latitude, map.municipality)) continue;
    const trip = map.trips.get(vehicle.trip?.id);
    const route = trip ? map.routes[trip.routeIndex] : routeById.get(vehicle.trip?.routeId);
    reports.push({ entityId: entity.id, ...vehicle, route: route || null, shape: trip ? map.shapes[trip.shapeIndex] : null, positionSource: 'upstream-report', feedTimestamp: feed.header.timestamp ?? null, observationTimestamp: vehicle.timestamp ?? null });
  }
  return reports;
}
