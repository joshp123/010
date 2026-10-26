// Written by AI on 2026-10-26 by model GPT-6.
import { createLiveFeed } from './live.js';
const live = createLiveFeed();
export default {
  fetch(request, env) {
    if (new URL(request.url).pathname === '/api/live') return live(request);
    return env.ASSETS.fetch(request);
  },
};
