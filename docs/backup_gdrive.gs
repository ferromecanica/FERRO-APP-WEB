/**
 * Backup diario de Ferro en Google Drive.
 *
 * Todos los días le pide a Ferro una copia de la base y la guarda en la
 * carpeta de Drive indicada en CARPETA_ID. Borra los backups de Ferro de más de
 * DIAS_A_GUARDAR días (no toca ningún otro archivo de la carpeta).
 *
 * Instalación (una sola vez):
 *  1. script.google.com → Nuevo proyecto → borrar lo que haya y pegar este código.
 *  2. Reemplazar SECRETO por el valor de BACKUP_SECRET del .env del servidor.
 *  3. Guardar. Arriba, elegir la función "instalar" → Ejecutar → autorizar con tu cuenta.
 *     Eso hace un primer backup y deja programado el diario.
 */
const SECRETO = 'PEGAR_ACA_EL_BACKUP_SECRET';
const URL_FERRO = 'https://lucioroncoroni.pythonanywhere.com/sistema/backup';
// Carpeta de Drive donde se guardan (el ID es lo que sigue a /folders/ en su dirección)
const CARPETA_ID = '1l0xUjQPm5LURPoBCUY4hYqJDWQ8G4dVt';
const DIAS_A_GUARDAR = 60;
const PREFIJO = 'ferro-backup-';
const HORA = 3; // 3 de la mañana (hora de la cuenta de Google)

function instalar() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('respaldarFerro').timeBased().everyDays(1).atHour(HORA).create();
  respaldarFerro();
  Logger.log('Listo: backup diario programado a las ' + HORA + ' hs.');
}

function respaldarFerro() {
  const r = UrlFetchApp.fetch(URL_FERRO, {
    method: 'post',
    payload: { secreto: SECRETO },
    muteHttpExceptions: true,
  });
  if (r.getResponseCode() !== 200) {
    throw new Error('Ferro respondió ' + r.getResponseCode() + ' (¿secreto incorrecto o sitio caído?)');
  }
  const carpeta = DriveApp.getFolderById(CARPETA_ID);
  const fecha = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd_HHmm');
  const archivo = carpeta.createFile(r.getBlob().setName(PREFIJO + fecha + '.sqlite.gz'));
  Logger.log('Guardado: ' + archivo.getName() + ' (' + Math.round(archivo.getSize() / 1024) + ' KB)');

  const limite = new Date(Date.now() - DIAS_A_GUARDAR * 24 * 3600 * 1000);
  const archivos = carpeta.getFiles();
  while (archivos.hasNext()) {
    const f = archivos.next();
    // Solo backups de Ferro: el resto de la carpeta no se toca
    if (f.getName().indexOf(PREFIJO) === 0 && f.getDateCreated() < limite) f.setTrashed(true);
  }
}
