import { createTransitProxy } from "../source-tools/transit-worker.js";
import { createMunicipalDeliveryProxy } from "../source-tools/municipal-delivery-worker.js";
import municipalManifest from "../public/data/municipal-delivery/manifest.json";

const transit = createTransitProxy();
export default {
  async fetch(request: Request, _env: unknown, context: ExecutionContext) {
    if (new URL(request.url).pathname.startsWith("/api/municipal-delivery/")) {
      const municipal = createMunicipalDeliveryProxy({
        manifest: municipalManifest,
        cache: caches.default,
        waitUntil: context.waitUntil.bind(context),
      });
      return await municipal(request);
    }
    return await transit(request) ?? new Response("Not found", { status: 404 });
  },
};
