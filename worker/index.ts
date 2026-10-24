import { createTransitProxy } from "../source-tools/transit-worker.js";

import { createMunicipalBuildingsProxy } from "../source-tools/municipal-buildings-worker.js";

const transit = createTransitProxy();
const municipalBuildings = createMunicipalBuildingsProxy();
export default {
  async fetch(request: Request) {
    return await municipalBuildings(request) ?? await transit(request) ?? new Response("Not found", { status: 404 });
  },
};
