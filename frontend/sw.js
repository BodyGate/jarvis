// Service worker minimo (RNF-008: offline parziale, RF-014: installabile).
// Mette in cache solo l'app shell statica — mai le risposte API, che
// devono sempre riflettere lo stato reale (sessione, conversazioni).
//
// Strategia network-first (non cache-first): l'app è ancora in sviluppo
// attivo, un cache-first avrebbe continuato a servire HTML/JS vecchi dopo
// ogni deploy finché la cache non scadeva esplicitamente. Con network-first
// l'utente online vede sempre l'ultima versione; solo se la rete non
// risponde si usa la copia in cache (offline reale, non "poco aggiornato").
const CACHE_NAME = "jarvis-shell-v3";
const SHELL_ASSETS = [
  "/",
  "/css/styles.css",
  "/js/app.js",
  "/js/scene.js",
  "/js/vendor/socket.io.min.js",
  "/js/vendor/three.module.js",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  // Mai intercettare API o Socket.IO: devono sempre andare in rete.
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/socket.io/") || url.pathname.startsWith("/auth/")) {
    return;
  }

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok && url.origin === self.location.origin) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      })
      .catch(() => caches.match(request))
  );
});
