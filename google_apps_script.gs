/**
 * Aunty Queen Hotline: Google Sheet backend.
 *
 * Setup (once):
 * 1. Create a Google Sheet (share it ONLY with counselors).
 * 2. Extensions > Apps Script, paste this file, save.
 * 3. Project Settings > Script properties > add SHEET_SECRET = (a long random string).
 *    Put the same value in Render as SHEET_SECRET.
 * 4. Deploy > New deployment > Web app: Execute as "Me", Who has access "Anyone".
 *    Copy the /exec URL into Render as GOOGLE_SHEET_WEBHOOK_URL.
 *
 * Tabs created automatically:
 *   Intakes  - one row per intake, updated after every answer (download via File > Download)
 *   Sessions - bot memory so conversations survive restarts (do not edit by hand)
 */

function doPost(e) {
  var body = JSON.parse(e.postData.contents || '{}');
  var secret = PropertiesService.getScriptProperties().getProperty('SHEET_SECRET') || '';
  if (secret && body.secret !== secret) {
    return json({ ok: false, error: 'unauthorized' });
  }

  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    if (body.action === 'upsert_intake') {
      upsertRow('Intakes', 'intake_id', body.row);
      return json({ ok: true });
    }
    if (body.action === 'save_session') {
      upsertRow('Sessions', 'phone', {
        phone: String(body.phone),
        updated_at: body.session.updated_at,
        mode: body.session.mode,
        step: body.session.step,
        session_json: JSON.stringify(body.session)
      });
      return json({ ok: true });
    }
    if (body.action === 'get_session') {
      var row = findRow('Sessions', 'phone', String(body.phone));
      return json({ ok: true, session: row ? JSON.parse(row.session_json) : null });
    }
    // Old bot format (no action): append as a row so nothing is lost.
    if (!body.action) {
      body.intake_id = body.intake_id || Utilities.getUuid().slice(0, 10);
      upsertRow('Intakes', 'intake_id', body);
      return json({ ok: true });
    }
    return json({ ok: false, error: 'unknown action' });
  } finally {
    lock.releaseLock();
  }
}

function doGet() {
  return json({ ok: true, service: 'Aunty Queen sheet backend' });
}

function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function getSheet(name, keyField) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    sheet.appendRow([keyField]);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function headersOf(sheet) {
  return sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), 1)).getValues()[0];
}

function findRow(name, keyField, keyValue) {
  var sheet = getSheet(name, keyField);
  var values = sheet.getDataRange().getValues();
  var headers = values[0];
  var keyCol = headers.indexOf(keyField);
  for (var r = 1; r < values.length; r++) {
    if (String(values[r][keyCol]) === String(keyValue)) {
      var obj = {};
      headers.forEach(function (h, i) { obj[h] = values[r][i]; });
      return obj;
    }
  }
  return null;
}

function upsertRow(name, keyField, row) {
  var sheet = getSheet(name, keyField);
  var headers = headersOf(sheet);

  // Add any new columns.
  Object.keys(row).forEach(function (k) {
    if (headers.indexOf(k) === -1) {
      headers.push(k);
      sheet.getRange(1, headers.length).setValue(k);
    }
  });

  var keyCol = headers.indexOf(keyField) + 1;
  var rowIndex = -1;
  var lastRow = sheet.getLastRow();
  if (lastRow > 1) {
    var keys = sheet.getRange(2, keyCol, lastRow - 1, 1).getValues();
    for (var i = 0; i < keys.length; i++) {
      if (String(keys[i][0]) === String(row[keyField])) { rowIndex = i + 2; break; }
    }
  }
  if (rowIndex === -1) rowIndex = lastRow + 1;

  var existing = rowIndex <= lastRow
    ? sheet.getRange(rowIndex, 1, 1, headers.length).getValues()[0]
    : headers.map(function () { return ''; });
  var out = headers.map(function (h, i) {
    if (!(h in row)) return existing[i];
    var v = row[h];
    // Keep phone numbers and dates as plain text so Sheets does not reformat them.
    return (h === 'phone' || h === 'lmp') ? "'" + v : v;
  });
  sheet.getRange(rowIndex, 1, 1, headers.length).setValues([out]);
}
