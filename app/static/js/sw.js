/* Service worker de Ferro.

   Hace una sola cosa: guardar en el teléfono los archivos de /static (el CSS,
   los scripts, los íconos) para que la app abra rápido y no los baje de nuevo
   en cada pantalla.

   Las páginas NO se guardan nunca: una OT o un precio tienen que venir siempre
   del servidor, si no Iván vería datos viejos sin darse cuenta.

   Guardar el /static por su dirección completa es seguro porque la app les
   agrega ?v=<fecha> a esos archivos: cuando publicamos un cambio, la dirección
   cambia y el teléfono lo baja de nuevo solo. */
const CACHE = 'ferro-static-v1';

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (evento) => {
  evento.waitUntil((async () => {
    // Limpia versiones viejas de la caché por si alguna vez cambia el nombre
    const nombres = await caches.keys();
    await Promise.all(nombres.filter((n) => n !== CACHE).map((n) => caches.delete(n)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (evento) => {
  const pedido = evento.request;
  const url = new URL(pedido.url);
  const esEstatico = pedido.method === 'GET' &&
    url.origin === self.location.origin &&
    url.pathname.startsWith('/static/');
  if (!esEstatico) return;  // todo lo demás va derecho a la red, como siempre

  evento.respondWith((async () => {
    const guardado = await caches.match(pedido);
    if (guardado) return guardado;
    const respuesta = await fetch(pedido);
    if (respuesta.ok) {
      const cache = await caches.open(CACHE);
      await cache.put(pedido, respuesta.clone());
      // Saca las versiones anteriores del mismo archivo, para que el teléfono no
      // se llene de copias viejas del CSS cada vez que publicamos un cambio
      for (const vieja of await cache.keys()) {
        if (new URL(vieja.url).pathname === url.pathname && vieja.url !== pedido.url) {
          cache.delete(vieja);
        }
      }
    }
    return respuesta;
  })());
});
