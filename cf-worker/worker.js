// Cloudflare Worker 反代 — jigou-neican API
// 部署：https://dash.cloudflare.com → Workers → Create
// 绑定自定义域：jgnc.jeeseek.top（或新域）

const RENDER_URL = 'https://jigou-neican-api.onrender.com';  // Render service URL
const ALLOWED_ORIGINS = [
  'https://jeeseek.top',
  'https://jgnc.jeeseek.top',
  'http://localhost:3000',
];

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': ALLOWED_ORIGINS.includes(request.headers.get('Origin')) ? request.headers.get('Origin') : '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization',
          'Access-Control-Max-Age': '86400',
        },
      });
    }

    // Cache key
    const cacheKey = new Request(url.toString(), request);
    const cache = caches.default;
    if (request.method === 'GET') {
      const cached = await cache.match(cacheKey);
      if (cached) {
        const resp = new Response(cached.body, cached);
        resp.headers.set('X-Cache', 'HIT');
        return resp;
      }
    }

    // Proxy to Render
    const targetUrl = RENDER_URL + url.pathname + url.search;
    const resp = await fetch(targetUrl, {
      method: request.method,
      headers: request.headers,
      body: request.body,
    });

    // Cache GET for 5 min
    const out = new Response(resp.body, resp);
    if (request.method === 'GET' && resp.ok) {
      out.headers.set('Cache-Control', 'public, max-age=300');
      ctx.waitUntil(cache.put(cacheKey, out.clone()));
    }
    out.headers.set('Access-Control-Allow-Origin', '*');
    return out;
  },
};
