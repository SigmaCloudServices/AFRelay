// AFRelay Portal — main.js

// Auto-dismiss alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.alert:not(.alert-permanent)').forEach(function (alert) {
    setTimeout(function () {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      if (bsAlert) bsAlert.close();
    }, 5000);
  });
});

// Clipboard copy helper (used in templates via onclick)
window.copyToClipboard = function (text, btn) {
  navigator.clipboard.writeText(text).then(function () {
    const original = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-check"></i>';
    setTimeout(function () { btn.innerHTML = original; }, 2000);
  });
};

// HTMX: show spinner on requests
document.addEventListener('htmx:beforeRequest', function (evt) {
  const el = evt.detail.elt;
  el.classList.add('htmx-loading');
});
document.addEventListener('htmx:afterRequest', function (evt) {
  const el = evt.detail.elt;
  el.classList.remove('htmx-loading');
});
