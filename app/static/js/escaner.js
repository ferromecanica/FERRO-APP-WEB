/* Lector de códigos de barras.
   En cada <input data-escaner> agrega un botón 📷 que abre la cámara y completa el campo con lo que lee.
   - data-escaner="enviar": al leer, envía el formulario (ej.: agregar el repuesto a la OT).
   - Con un lector USB/Bluetooth (que "tipea" el código y un Enter) el Enter no manda el formulario:
     en el buscador dispara la búsqueda y en los demás campos solo pasa al siguiente.
   La librería (html5-qrcode) se carga recién la primera vez que se usa la cámara. */
(function () {
  var LIB = 'https://cdnjs.cloudflare.com/ajax/libs/html5-qrcode/2.3.8/html5-qrcode.min.js';
  var cargando = null, ventana = null, lector = null;

  function cargarLibreria() {
    if (window.Html5Qrcode) return Promise.resolve();
    if (!cargando) {
      cargando = new Promise(function (ok, mal) {
        var s = document.createElement('script');
        s.src = LIB; s.onload = ok; s.onerror = function () { cargando = null; mal(new Error('No se pudo cargar el lector')); };
        document.head.appendChild(s);
      });
    }
    return cargando;
  }

  function armarVentana() {
    ventana = document.createElement('div');
    ventana.className = 'escaner';
    ventana.hidden = true;
    ventana.innerHTML = '<div class="escaner-caja"><div class="escaner-top"><strong><i class="fa-solid fa-barcode"></i> Apuntá al código de barras</strong>' +
      '<button type="button" class="btn-icon escaner-cerrar" title="Cerrar"><i class="fa-solid fa-xmark"></i></button></div>' +
      '<div id="escaner-video"></div><div class="escaner-estado muted small">Iniciando cámara…</div></div>';
    document.body.appendChild(ventana);
    ventana.querySelector('.escaner-cerrar').addEventListener('click', cerrar);
    ventana.addEventListener('click', function (e) { if (e.target === ventana) cerrar(); });
  }

  function cerrar() {
    var l = lector;
    lector = null;
    if (ventana) ventana.hidden = true;
    if (!l) return;
    // stop() tira un error (no una promesa rechazada) si la cámara nunca llegó a arrancar
    try {
      Promise.resolve(l.stop()).catch(function () {}).then(function () { try { l.clear(); } catch (e) { /* nada */ } });
    } catch (e) {
      try { l.clear(); } catch (e2) { /* nada */ }
    }
  }

  function abrir(input) {
    if (!ventana) armarVentana();
    var estado = ventana.querySelector('.escaner-estado');
    estado.textContent = 'Iniciando cámara…';
    ventana.hidden = false;
    cargarLibreria().then(function () {
      var F = Html5QrcodeSupportedFormats;
      var este = lector = new Html5Qrcode('escaner-video', {
        formatsToSupport: [F.EAN_13, F.EAN_8, F.UPC_A, F.UPC_E, F.CODE_128, F.CODE_39, F.CODE_93, F.ITF, F.CODABAR, F.QR_CODE],
        useBarCodeDetectorIfSupported: true
      });
      return este.start({ facingMode: 'environment' }, { fps: 12, qrbox: function (w, h) { return { width: Math.min(w * 0.9, 380), height: Math.min(h * 0.5, 180) }; } },
        function (codigo) {
          if (navigator.vibrate) navigator.vibrate(80);
          input.value = codigo.trim();
          input.dispatchEvent(new Event('input', { bubbles: true }));
          input.dispatchEvent(new Event('change', { bubbles: true }));
          cerrar();
          if (input.dataset.escaner === 'enviar' && input.form) input.form.requestSubmit();
          else input.focus();
        }, function () { /* sin código en este cuadro: sigue buscando */ }).then(function () {
          // si cerraron la ventana mientras la cámara arrancaba, se apaga
          if (lector !== este) { lector = este; cerrar(); }
        });
    }).then(function () {
      estado.textContent = 'Poné el código dentro del recuadro. También podés usar un lector USB en el campo.';
    }).catch(function (e) {
      estado.textContent = (String(e).indexOf('NotAllowed') >= 0 || String(e).indexOf('Permission') >= 0)
        ? 'No hay permiso para usar la cámara. Habilitalo en el navegador y probá de nuevo.'
        : 'No se pudo usar la cámara: ' + (e.message || e);
    });
  }

  function preparar(input) {
    if (input.dataset.escanerListo) return;
    input.dataset.escanerListo = '1';
    var boton = document.createElement('button');
    boton.type = 'button';
    boton.className = 'btn btn-escaner';
    boton.title = 'Leer código de barras con la cámara';
    boton.innerHTML = '<i class="fa-solid fa-barcode"></i>';
    boton.addEventListener('click', function () { abrir(input); });
    var grupo = document.createElement('div');
    grupo.className = 'input-group';
    input.parentNode.insertBefore(grupo, input);
    grupo.appendChild(input);
    grupo.appendChild(boton);
    // Lector USB/Bluetooth: el Enter que manda al final no tiene que enviar el formulario
    input.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      if (input.type === 'search' || input.dataset.escaner === 'enviar') return;  // buscar / agregar: está bien
      e.preventDefault();
      var campos = Array.prototype.filter.call(input.form ? input.form.elements : [], function (c) {
        return c.tagName !== 'BUTTON' && c.type !== 'hidden' && !c.disabled;
      });
      var siguiente = campos[campos.indexOf(input) + 1];
      if (siguiente) siguiente.focus();
    });
  }

  function iniciar() { document.querySelectorAll('input[data-escaner]').forEach(preparar); }
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && ventana && !ventana.hidden) cerrar(); });
  iniciar();
  document.body.addEventListener('htmx:afterSwap', iniciar);
})();
