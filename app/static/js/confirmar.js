/* Ventanita de confirmación propia, en vez del cartel gris del navegador.
   Uso: <form data-confirmar="¿Eliminar la OT 10000?" data-confirmar-detalle="Los repuestos vuelven al stock."
              data-confirmar-boton="Eliminar" data-confirmar-tono="peligro">

   Puede además pedir un dato antes de enviar, que viaja con el formulario:
       data-confirmar-campo="cantidad" data-confirmar-campo-label="¿Cuántos compraste?"
       data-confirmar-campo-valor="4"  */
(function () {
  var dialogo, titulo, detalle, aceptar, campo, campoCaja, campoLabel, pendiente;

  function armar() {
    dialogo = document.createElement('dialog');
    dialogo.className = 'confirmar';
    dialogo.innerHTML =
      '<div class="confirmar-cuerpo"><div class="confirmar-icono"><i class="fa-solid fa-circle-question"></i></div>' +
      '<div><h3 class="confirmar-titulo"></h3><p class="confirmar-detalle muted small"></p>' +
      '<label class="confirmar-campo" hidden><span></span>' +
      '<input inputmode="decimal" autocomplete="off"></label></div></div>' +
      '<div class="confirmar-botones"><button type="button" class="btn" data-no>Cancelar</button>' +
      '<button type="button" class="btn btn-primary" data-si>Confirmar</button></div>';
    document.body.appendChild(dialogo);
    titulo = dialogo.querySelector('.confirmar-titulo');
    detalle = dialogo.querySelector('.confirmar-detalle');
    aceptar = dialogo.querySelector('[data-si]');
    campoCaja = dialogo.querySelector('.confirmar-campo');
    campoLabel = campoCaja.querySelector('span');
    campo = campoCaja.querySelector('input');
    campo.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); aceptar.click(); } });
    dialogo.querySelector('[data-no]').addEventListener('click', function () { dialogo.close(); });
    dialogo.addEventListener('click', function (e) { if (e.target === dialogo) dialogo.close(); });
    aceptar.addEventListener('click', function () {
      dialogo.close();
      var form = pendiente;
      pendiente = null;
      if (!form) return;
      // Lo que se contestó en la ventanita viaja con el formulario
      if (form.dataset.confirmarCampo) {
        var oculto = form.querySelector('[name="' + form.dataset.confirmarCampo + '"]');
        if (!oculto) {
          oculto = document.createElement('input');
          oculto.type = 'hidden';
          oculto.name = form.dataset.confirmarCampo;
          form.appendChild(oculto);
        }
        oculto.value = campo.value;
      }
      form.dataset.confirmado = '1';
      form.requestSubmit ? form.requestSubmit() : form.submit();
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
    campoCaja.hidden = !form.dataset.confirmarCampo;
    if (form.dataset.confirmarCampo) {
      campoLabel.textContent = form.dataset.confirmarCampoLabel || '';
      campo.value = form.dataset.confirmarCampoValor || '';
    }
    dialogo.showModal();
    if (!campoCaja.hidden) { campo.focus(); campo.select(); } else { aceptar.focus(); }
  }

  document.addEventListener('submit', function (e) {
    var form = e.target.closest('form[data-confirmar]');
    if (!form || form.dataset.confirmado) return;
    e.preventDefault();
    preguntar(form);
  }, true);
})();
