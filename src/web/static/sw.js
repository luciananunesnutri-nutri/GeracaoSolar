/* ─────────────────────────────────────────────────────────────────────────
   Service Worker — Monitoramento Solar
   Estratégia:
     • Static assets  → Cache-first (fontes, CSS, JS de CDN, ícones)
     • Páginas HTML   → Network-first com fallback de cache
     • APIs /api/*    → Network-only (dados sempre frescos)
   ───────────────────────────────────────────────────────────────────────── */

const CACHE_NAME  = 'solar-v1';
const CACHE_SHELL = [
  '/',
  '/insights',
  '/static/favicon.svg',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/apple-touch-icon.png',
];

// ── Install: pré-cacheia o shell da aplicação ─────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(CACHE_SHELL))
  );
  self.skipWaiting();
});

// ── Activate: remove caches antigos ──────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// ── Fetch ─────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // APIs: sempre rede (sem cache)
  if (url.pathname.startsWith('/api/')) return;

  // Recursos externos (CDN): cache-first
  if (url.origin !== location.origin) {
    event.respondWith(
      caches.match(request).then(cached =>
        cached || fetch(request).then(resp => {
          if (resp.ok) {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then(c => c.put(request, clone));
          }
          return resp;
        })
      )
    );
    return;
  }

  // Páginas HTML: network-first, fallback para cache
  if (request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(request)
        .then(resp => {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then(c => c.put(request, clone));
          return resp;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Static assets: cache-first
  event.respondWith(
    caches.match(request).then(cached =>
      cached || fetch(request).then(resp => {
        if (resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then(c => c.put(request, clone));
        }
        return resp;
      })
    )
  );
});
