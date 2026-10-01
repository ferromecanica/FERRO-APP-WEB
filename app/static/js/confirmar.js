/* Ventanita de confirmación propia, en vez del cartel gris del navegador.
   Uso: <form data-confirmar="¿Eliminar la OT 10000?" data-confirmar-detalle="Los repuestos vuelven al stock."
              data-confirmar-boton="Eliminar" data-confirmar-tono="peligro">

   Puede además pedir un dato antes de enviar, que viaja con el formulario:
       data-confirmar-campo="cantidad" data-confirmar-campo-label="¿Cuántos compraste?"
       data-confirmar-campo-valor="4"

   Los mismos atributos valen en el botón, para cuando un formulario tiene
   varios y solo uno necesita que se confirme (guardar no, cerrar el mes sí). */
(function () {
  var dialogo, titulo, detalle, aceptar, campo, campoCaja, campoLabel, pendiente, pendienteBoton;

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
      var form = pendiente, boton = pendienteBoton;
      pendiente = pendienteBoton = null;
      if (!form) return;
      // Lo que se contestó en la ventanita viaja con el formulario
      var pideCampo = (boton && boton.dataset.confirmarCampo) || form.dataset.confirmarCampo;
      if (pideCampo) {
        var oculto = form.querySelector('[name="' + pideCampo + '"]');
        if (!oculto) {
          oculto = document.createElement('input');
          oculto.type = 'hidden';
          oculto.name = pideCampo;
          form.appendChild(oculto);
        }
        oculto.value = campo.value;
      }
      form.dataset.confirmado = '1';
      // Se reenvía con el mismo botón: si no, se perderían su name, su value y
      // su formaction, y el servidor no sabría qué se pidió
      if (form.requestSubmit) form.requestSubmit(boton || undefined); else form.submit();
    });
  }

  /* De dónde salen los textos: del botón si los trae, si no del formulario. */
  function preguntar(form, boton) {
    if (!dialogo) armar();
    pendiente = form;
    pendienteBoton = boton;
    var d = (boton && boton.dataset.confirmar) ? boton.dataset : form.dataset;
    titulo.textContent = d.confirmar;
    detalle.textContent = d.confirmarDetalle || '';
    detalle.hidden = !d.confirmarDetalle;
    aceptar.textContent = d.confirmarBoton || 'Confirmar';
    aceptar.classList.toggle('btn-peligro', d.confirmarTono === 'peligro');
    dialogo.querySelector('.confirmar-icono').className = 'confirmar-icono' +
      (d.confirmarTono === 'peligro' ? ' peligro' : '');
    campoCaja.hidden = !d.confirmarCampo;
    if (d.confirmarCampo) {
      campoLabel.textContent = d.confirmarCampoLabel || '';
      campo.value = d.confirmarCampoValor || '';
    }
    dialogo.showModal();
    if (!campoCaja.hidden) { campo.focus(); campo.select(); } else { aceptar.focus(); }
  }

  document.addEventListener('submit', function (e) {
    var boton = e.submitter && e.submitter.dataset.confirmar ? e.submitter : null;
    var form = boton ? e.target : e.target.closest('form[data-confirmar]');
    if (!form || form.dataset.confirmado) return;
    e.preventDefault();
    preguntar(form, boton);
  }, true);
})();
