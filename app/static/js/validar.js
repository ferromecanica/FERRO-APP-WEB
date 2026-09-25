/* Ningún formulario se queda mudo.

   Cuando falta algo, el navegador no dispara "submit": cancela y muestra un
   globito sobre el campo. Si ese campo está oculto —adentro de un bloque que
   no corresponde, o de una sección cerrada— no puede mostrar nada y el botón
   parece roto: se aprieta y no pasa nada, sin error ni explicación.

   Acá escuchamos "invalid" (que salta en cada campo que falla) y avisamos
   nosotros, arriba del formulario, diciendo qué falta y por qué. */
(function () {
  var pendientes = new Map();

  /* El nombre que ve la persona, no el del campo en el código. */
  function etiqueta(campo) {
    // En un grupo de opciones cada una tiene su label ("Servicio", "Otro"): lo
    // que hay que nombrar es el título del grupo ("Tipo de trabajo")
    if (campo.type === 'radio' || campo.type === 'checkbox') {
      var arriba = campo.closest('div, fieldset');
      for (var i = 0; arriba && i < 3; i++, arriba = arriba.parentElement) {
        var titulo = buscarLabel(arriba, campo);
        if (titulo) return titulo;
      }
    }
    var propia = campo.labels && campo.labels[0];
    if (propia && propia.textContent.trim()) return limpiar(propia.textContent);
    return buscarLabel(campo.closest('div, td, fieldset'), campo) ||
      limpiar(campo.getAttribute('placeholder') || campo.name || 'un dato');
  }

  /* Un label de esa caja que sea el título, no el de la opción en sí. */
  function buscarLabel(caja, campo) {
    if (!caja) return null;
    var labels = Array.prototype.slice.call(caja.querySelectorAll('label'));
    for (var i = 0; i < labels.length; i++) {
      // El título es el que solo tiene texto; los que envuelven un control son
      // las opciones ("Servicio", "Otro"), que no nombran al grupo
      if (!labels[i].querySelector('input, select, textarea') && labels[i].textContent.trim()) {
        return limpiar(labels[i].textContent);
      }
    }
    return null;
  }

  function limpiar(texto) {
    return texto.replace(/\s+/g, ' ').replace(/\s*\*\s*$/, '').trim();
  }

  function motivo(campo) {
    if (campo.validity.valueMissing) return null;           // "falta completar" ya se entiende
    return campo.validationMessage || null;                 // el resto lo explica el navegador
  }

  function avisar(form, campos) {
    var viejo = form.querySelector('[data-falta]');
    if (viejo) viejo.remove();

    var partes = campos.map(function (c) {
      var razon = motivo(c);
      return etiqueta(c) + (razon ? ' (' + razon.toLowerCase() + ')' : '');
    });
    var caja = document.createElement('div');
    caja.className = 'flash flash-error';
    caja.setAttribute('data-falta', '');
    caja.innerHTML = '<i class="fa-solid fa-circle-exclamation"></i> Falta completar: <strong>' +
      partes.join('</strong>, <strong>') + '</strong>.';

    // Si lo que falta no se ve, la persona no tiene forma de arreglarlo sola
    if (campos.some(function (c) { return !c.offsetParent; })) {
      caja.innerHTML += ' <span class="muted">Ese campo no está a la vista: avisá que pasó esto.</span>';
    }
    form.insertBefore(caja, form.firstChild);
    caja.scrollIntoView({ block: 'nearest', behavior: 'smooth' });

    var primero = campos.find(function (c) { return c.offsetParent; });
    if (primero) primero.focus({ preventScroll: true });
  }

  document.addEventListener('invalid', function (e) {
    var campo = e.target, form = campo.form;
    if (!form) return;
    e.preventDefault();   // el globito del navegador no sirve si el campo está oculto

    // "invalid" salta una vez por campo (y una por cada opción de un grupo):
    // se juntan todos y se avisa una sola vez, cuando terminaron de saltar
    var lista = pendientes.get(form);
    if (!lista) {
      lista = [];
      pendientes.set(form, lista);
      setTimeout(function () {
        avisar(form, pendientes.get(form) || []);
        pendientes.delete(form);
      });
    }
    // De un grupo de opciones alcanza con nombrarlo una vez
    var repetido = campo.name && lista.some(function (c) { return c.name === campo.name; });
    if (!repetido) lista.push(campo);
  }, true);

  /* Al corregir, el aviso sobra. Se mira campo por campo y no con
     checkValidity(), que volvería a disparar los "invalid" y lo repintaría. */
  function todoCompleto(form) {
    return Array.prototype.every.call(form.elements, function (c) {
      return !c.validity || c.validity.valid;
    });
  }

  function revisar(e) {
    var form = e.target.form;
    var aviso = form && form.querySelector('[data-falta]');
    if (aviso && todoCompleto(form)) aviso.remove();
  }
  document.addEventListener('input', revisar, true);
  document.addEventListener('change', revisar, true);
})();
