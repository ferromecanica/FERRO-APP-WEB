/**
 * Conexión de Ferro con Google Drive: reportes PDF y fotos de las OT.
 *
 * accion=reporte (o sin acción): Ferro manda el HTML del reporte; este script reemplaza
 *   __LOGO__, __FIRMA__ y __FOTO:archivo__ por las imágenes de Drive, lo convierte a PDF,
 *   lo guarda en la carpeta de reportes (reemplazando uno anterior con el mismo nombre)
 *   y devuelve el link.
 * accion=foto: guarda una foto (JPEG en base64) en la carpeta de fotos y devuelve su id.
 * accion=borrar_foto: manda una foto a la papelera.
 *
 * Instalación (una sola vez), en el MISMO proyecto "Ferro Backup":
 *  1. Archivo → "+" → Script → nombre "Reportes" → pegar este código. (Usa la constante
 *     SECRETO que ya está en el otro archivo del proyecto.)
 *  2. Implementar → Nueva implementación → tipo "Aplicación web":
 *       Ejecutar como: Yo    ·    Quién tiene acceso: Cualquier usuario
 *  3. Autorizar y copiar la URL de la aplicación web (termina en /exec).
 *
 * Para actualizar este código sin cambiar la URL:
 *  Implementar → Administrar implementaciones → lápiz → Versión: "Nueva versión" → Implementar.
 */
const FOLDER_REPORTES_ID = '1o1ZkDqFamPa13Vmgzq5Um2FFYla84GIq';
const FOLDER_LOGO_ID = '1hKdsArmHtOGlBSA_ZQ_LCeRv4UKKfyC3';
const NOMBRE_LOGO = 'SOBRIO FONDO BLANCO.jpeg';
const NOMBRE_FIRMA = 'FIRMA.jpg';
const FOLDER_FOTOS_ID = '1XbCu2_FdiR08_mzfzhPcsNifW2Cr1qjf';

function doPost(e) {
  try {
    const p = e.parameter;
    if (!p.secreto || p.secreto !== SECRETO) return json({ ok: false, error: 'secreto incorrecto' });
    const accion = p.accion || 'reporte';
    if (accion === 'reporte') return generarReporte(p);
    if (accion === 'foto') return guardarFoto(p);
    if (accion === 'borrar_foto') return borrarFoto(p);
    return json({ ok: false, error: 'acción desconocida: ' + accion });
  } catch (err) {
    return json({ ok: false, error: String(err.message || err) });
  }
}

function generarReporte(p) {
  if (!p.html || !p.nombre) return json({ ok: false, error: 'faltan datos' });
  let html = p.html
    .split('__LOGO__').join(imagenBase64(FOLDER_LOGO_ID, NOMBRE_LOGO) || '')
    .split('__FIRMA__').join(imagenBase64(FOLDER_LOGO_ID, NOMBRE_FIRMA) || '');
  html = html.replace(/__FOTO:(.+?)__/g, function (_, archivo) {
    return imagenBase64(FOLDER_FOTOS_ID, archivo) || '';
  });

  const carpeta = DriveApp.getFolderById(FOLDER_REPORTES_ID);
  const anteriores = carpeta.getFilesByName(p.nombre);
  while (anteriores.hasNext()) anteriores.next().setTrashed(true);

  const pdf = Utilities.newBlob(html, MimeType.HTML, 'temp.html').getAs(MimeType.PDF).setName(p.nombre);
  const archivo = carpeta.createFile(pdf);
  return json({ ok: true, url: archivo.getUrl() });
}

function guardarFoto(p) {
  if (!p.nombre || !p.contenido) return json({ ok: false, error: 'faltan datos' });
  const blob = Utilities.newBlob(Utilities.base64Decode(p.contenido), 'image/jpeg', p.nombre);
  const archivo = DriveApp.getFolderById(FOLDER_FOTOS_ID).createFile(blob);
  try {
    // Para poder ver la miniatura desde Ferro (el link no es público ni se puede adivinar)
    archivo.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  } catch (e) { /* si la cuenta no lo permite, la foto igual queda guardada */ }
  return json({ ok: true, id: archivo.getId(), nombre: archivo.getName() });
}

function borrarFoto(p) {
  if (!p.id) return json({ ok: false, error: 'falta el id' });
  DriveApp.getFileById(p.id).setTrashed(true);
  return json({ ok: true });
}

function imagenBase64(folderId, nombre) {
  try {
    const archivos = DriveApp.getFolderById(folderId).getFilesByName(nombre);
    if (!archivos.hasNext()) return null;
    const f = archivos.next();
    return 'data:' + f.getMimeType() + ';base64,' + Utilities.base64Encode(f.getBlob().getBytes());
  } catch (e) {
    return null;
  }
}

function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
