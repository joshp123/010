import { createJunctionArbitrator } from './traffic-motion.js';

// Cars and bicycles retain their own sourced networks. Shared NWB road/node
// identities let them follow and yield to each other where those routes meet.
export function createTrafficCoordinator() {
  const fleets = new Set();
  const junctions = createJunctionArbitrator();
  let frameTime = null, frame = null;
  return {
    register(vehicles) { fleets.add(vehicles); return () => fleets.delete(vehicles); },
    occupied(roadId, distance, clearance) {
      return [...fleets].some(read => read().some(vehicle => vehicle.road.id === roadId && Math.abs(vehicle.distance - distance) < clearance));
    },
    clear() { frameTime = null; junctions.clear(); },
    frame(time, delta) {
      if (frameTime === time) return frame;
      const vehicles = [...fleets].flatMap(read => read());
      const occupants = new Map();
      for (const vehicle of vehicles) {
        const roadId = vehicle.road.id;
        if (!occupants.has(roadId)) occupants.set(roadId, []);
        occupants.get(roadId).push({ vehicle, direction: vehicle.direction, distance: vehicle.distance });
      }
      frameTime = time;
      frame = { occupants, junctionReservations: junctions.update(vehicles, occupants, delta) };
      return frame;
    },
  };
}
