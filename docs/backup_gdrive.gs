/**
 * Receptor de backups de Ferro en Google Drive.
 *
 * Instalación (una sola vez):
 *  1. script.google.com → Nuevo proyecto → pegar este código.
 *  2. Reemplazar SECRETO por el valor de BACKUP_SECRET del .env del servidor.
 *  3. Implementar → Nueva implementación → tipo "Aplicación web":
 *       Ejecutar como: Yo    ·    Quién tiene acceso: Cualquier usuario
 *  4. Autorizar y copiar la URL de la aplicación web (termina en /exec).
 *
 * Guarda cada copia en la carpeta "Ferro - Backups" de tu Drive y borra las
 * que tengan más de DIAS_A_GUARDAR días.
 */
const SECRETO = 'PEGAR_ACA_EL_BACKUP_SECRET';
const CARPETA = 'Ferro - Backups';
const DIAS_A_GUARDAR = 60;

function doPost(e) {
  const p = e.parameter;
  if (!p.secreto || p.secreto !== SECRETO) return respuesta({ ok: false, error: 'secreto incorrecto' });
  if (!p.nombre || !p.contenido) return respuesta({ ok: false, error: 'faltan datos' });

  const carpeta = obtenerCarpeta();
  const bytes = Utilities.base64Decode(p.contenido);
  const archivo = carpeta.createFile(Utilities.newBlob(bytes, 'application/gzip', p.nombre));

  const limite = new Date(Date.now() - DIAS_A_GUARDAR * 24 * 3600 * 1000);
  const viejos = carpeta.getFiles();
  while (viejos.hasNext()) {
    const f = viejos.next();
    if (f.getDateCreated() < limite) f.setTrashed(true);
  }
  return respuesta({ ok: true, archivo: archivo.getName() });
}

function obtenerCarpeta() {
  const existentes = DriveApp.getFoldersByName(CARPETA);
  return existentes.hasNext() ? existentes.next() : DriveApp.createFolder(CARPETA);
}

function respuesta(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
