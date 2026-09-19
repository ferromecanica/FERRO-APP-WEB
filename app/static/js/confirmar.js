/* Ventanita de confirmación propia, en vez del cartel gris del navegador.
   Uso: <form data-confirmar="¿Eliminar la OT 10000?" data-confirmar-detalle="Los repuestos vuelven al stock."
              data-confirmar-boton="Eliminar" data-confirmar-tono="peligro"> */
(function () {
  var dialogo, titulo, detalle, aceptar, pendiente;

  function armar() {
    dialogo = document.createElement('dialog');
    dialogo.className = 'confirmar';
    dialogo.innerHTML =
      '<div class="confirmar-cuerpo"><div class="confirmar-icono"><i class="fa-solid fa-circle-question"></i></div>' +
      '<div><h3 class="confirmar-titulo"></h3><p class="confirmar-detalle muted small"></p></div></div>' +
      '<div class="confirmar-botones"><button type="button" class="btn" data-no>Cancelar</button>' +
      '<button type="button" class="btn btn-primary" data-si>Confirmar</button></div>';
    document.body.appendChild(dialogo);
    titulo = dialogo.querySelector('.confirmar-titulo');
    detalle = dialogo.querySelector('.confirmar-detalle');
    aceptar = dialogo.querySelector('[data-si]');
    dialogo.querySelector('[data-no]').addEventListener('click', function () { dialogo.close(); });
    dialogo.addEventListener('click', function (e) { if (e.target === dialogo) dialogo.close(); });
    aceptar.addEventListener('click', function () {
      dialogo.close();
      var form = pendiente;
      pendiente = null;
      if (form) { form.dataset.confirmado = '1'; form.requestSubmit ? form.requestSubmit() : form.submit(); }
    });
  }

  function preguntar(form) {
    if (!dialogo) armar();
    pendiente = form;
    titulo.textContent = form.dataset.confirmar;
    detalle.textContent = form.dataset.confirmarDetalle || '';
    detalle.hidden = !form.dataset.confirmarDetalle;
    aceptar.textContent = form.dataset.confirmarBoton || 'Confirmar';
    aceptar.classList.toggle('btn-peligro', form.dataset.confirmarTono === 'peligro');
    dialogo.querySelector('.confirmar-icono').className = 'confirmar-icono' +
      (form.dataset.confirmarTono === 'peligro' ? ' peligro' : '');
    dialogo.showModal();
    aceptar.focus();
  }

  document.addEventListener('submit', function (e) {
    var form = e.target.closest('form[data-confirmar]');
    if (!form || form.dataset.confirmado) return;
    e.preventDefault();
    preguntar(form);
  }, true);
})();
