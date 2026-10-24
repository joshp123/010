import { createTransitProxy } from "../source-tools/transit-worker.js";

const transit = createTransitProxy();
export default {
  async fetch(request: Request) {
    return await transit(request) ?? new Response("Not found", { status: 404 });
  },
};
