// Live countdown for waitlist seat holds: <span data-countdown="seconds_left">
document.querySelectorAll('[data-countdown]').forEach(function (el) {
  var left = parseInt(el.dataset.countdown, 10);
  function tick() {
    if (left <= 0) { el.textContent = 'expired - refresh the page'; return; }
    var m = Math.floor(left / 60), s = left % 60;
    el.textContent = m + ':' + String(s).padStart(2, '0');
    left -= 1;
    setTimeout(tick, 1000);
  }
  tick();
});
