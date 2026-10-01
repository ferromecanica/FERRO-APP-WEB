/* Botones que tardan: avisan que están trabajando.

   Armar un PDF en Drive se lleva entre 10 y 20 segundos. Sin señal, el botón
   parece muerto: se vuelve a tocar, y el segundo click cancela el pedido que
   estaba en curso (el servidor lo registra como 499) y no se genera nada.

   Uso: <button data-ocupado="Generando la circular…"> */
(function () {
  document.addEventListener('submit', function (e) {
    var boton = e.submitter;
    if (!boton || !boton.dataset || !boton.dataset.ocupado) return;
    if (e.defaultPrevented) return;   // alguien frenó el envío (una confirmación): no se bloquea nada

    // Después de que el navegador ya tomó el envío: si se deshabilitara antes,
    // el name/value del botón no viajaría y el servidor no sabría qué se pidió
    setTimeout(function () {
      boton.disabled = true;
      boton.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> ' + boton.dataset.ocupado;
      boton.closest('form').querySelectorAll('button:not([disabled])').forEach(function (otro) {
        otro.disabled = true;          // tampoco se puede apretar otra cosa mientras tanto
      });
    });
  });
})();
