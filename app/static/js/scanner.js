(function () {
  var root = document.getElementById('scanner');
  if (!root) return;

  var csrf = root.dataset.csrf;
  var eventSel = document.getElementById('event');
  var box = document.getElementById('result');
  var historyEl = document.getElementById('history');
  var startBtn = document.getElementById('start-camera');
  var manualForm = document.getElementById('manual-form');
  var manualInput = document.getElementById('manual-code');
  var scanner = null, running = false, busy = false, lastCode = '', lastAt = 0;

  var LABELS = {
    admit: 'ADMITTED', already_used: 'ALREADY USED', wrong_event: 'WRONG EVENT',
    cancelled: 'TICKET CANCELLED', unknown_ticket: 'UNKNOWN TICKET', outside_checkin_time: 'OUTSIDE CHECK-IN TIME'
  };

  function show(ok, title, lines) {
    box.className = 'alert text-center ' + (ok ? 'alert-success' : 'alert-danger');
    box.replaceChildren();
    var h = document.createElement('div');
    h.className = 'h3 mb-1';
    h.textContent = title;
    box.appendChild(h);
    lines.forEach(function (text) {
      if (!text) return;
      var p = document.createElement('div');
      p.textContent = text;          // textContent, never innerHTML: ticket data is untrusted
      box.appendChild(p);
    });
    if (navigator.vibrate) navigator.vibrate(ok ? 80 : [120, 60, 120]);
  }

  function addHistory(ok, title, code) {
    var li = document.createElement('li');
    li.className = 'list-group-item d-flex justify-content-between small';
    var left = document.createElement('span');
    left.textContent = new Date().toLocaleTimeString() + '  ...' + code.slice(-6);
    var right = document.createElement('span');
    right.className = 'badge ' + (ok ? 'bg-success' : 'bg-danger');
    right.textContent = title;
    li.appendChild(left);
    li.appendChild(right);
    historyEl.insertBefore(li, historyEl.firstChild);
    while (historyEl.children.length > 10) historyEl.removeChild(historyEl.lastChild);
  }

  async function submit(raw, force) {
    var code = (raw || '').trim();
    if (!code || busy) return;
    var eventId = parseInt(eventSel.value, 10);
    if (!eventId) { show(false, 'CHOOSE AN EVENT', ['Select the event being scanned first.']); return; }
    // the camera reads the same QR many times a second: ignore repeats within 3 seconds
    if (!force && code === lastCode && Date.now() - lastAt < 3000) return;
    busy = true;
    lastCode = code;
    lastAt = Date.now();
    try {
      var res = await fetch('/api/scan', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
        body: JSON.stringify({code: code, event_id: eventId})
      });
      var data = await res.json();
      if (!res.ok) { show(false, 'ERROR', [data.detail || 'Request failed']); return; }
      var title = LABELS[data.decision] || (data.ok ? 'ADMITTED' : 'REJECTED');
      var lines = data.ok ? [data.holder + ' - ' + data.category, data.event_title] : [data.reason];
      if (data.suspicious) {
        lines.push('Suspicious: this code was scanned ' + data.scan_count + ' times (possible shared screenshot).');
      }
      show(data.ok, title, lines);
      addHistory(data.ok, title, code);
    } catch (err) {
      show(false, 'NETWORK ERROR', [String(err)]);
    } finally {
      busy = false;
    }
  }

  manualForm.addEventListener('submit', function (e) {
    e.preventDefault();
    submit(manualInput.value, true);
    manualInput.value = '';
    manualInput.focus();
  });

  startBtn.addEventListener('click', async function () {
    if (running) {
      try { await scanner.stop(); } catch (e) { /* already stopped */ }
      running = false;
      startBtn.textContent = 'Start camera';
      return;
    }
    if (!window.Html5Qrcode) {
      show(false, 'CAMERA LIBRARY NOT LOADED', ['Check the internet connection or use manual entry.']);
      return;
    }
    scanner = new Html5Qrcode('reader');
    try {
      await scanner.start({facingMode: 'environment'}, {fps: 10, qrbox: {width: 240, height: 240}},
        function (text) { submit(text, false); }, function () { /* no QR in this frame */ });
      running = true;
      startBtn.textContent = 'Stop camera';
    } catch (err) {
      show(false, 'CAMERA UNAVAILABLE', ['Could not open the camera (' + err + '). Use manual entry below.']);
    }
  });
})();
