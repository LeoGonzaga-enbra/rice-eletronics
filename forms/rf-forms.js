// Envio dos formulários nativos para o Worker (/api/form).
(function () {
  var cfgPromise = fetch('/api/form/config').then(function (r) { return r.json(); }).catch(function () { return {}; });

  function setStatus(form, text, cls) {
    var el = form.querySelector('.rf-status');
    el.textContent = text;
    el.className = 'rf-status' + (cls ? ' ' + cls : '');
  }

  function validate(form) {
    var ok = true;
    form.querySelectorAll('input,select,textarea').forEach(function (el) {
      el.classList.remove('rf-invalid');
      if (el.name === 'website' || el.type === 'hidden') return;
      var v = (el.value || '').trim();
      var bad = (el.required && !v) || (el.type === 'email' && v && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v));
      if (bad) { el.classList.add('rf-invalid'); ok = false; }
    });
    return ok;
  }

  document.querySelectorAll('form.rf-form').forEach(function (form) {
    cfgPromise.then(function (cfg) {
      if (!cfg.turnstileSiteKey) return;
      var box = document.createElement('div');
      box.className = 'cf-turnstile';
      box.setAttribute('data-sitekey', cfg.turnstileSiteKey);
      form.querySelector('.rf-actions').before(box);
      if (!document.getElementById('rf-turnstile')) {
        var s = document.createElement('script');
        s.id = 'rf-turnstile';
        s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js';
        document.head.appendChild(s);
      }
    });

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      if (!validate(form)) { setStatus(form, 'Please fill in the required fields.', 'rf-err'); return; }
      var btn = form.querySelector('.rf-submit');
      var data = {};
      new FormData(form).forEach(function (v, k) { data[k] = v; });
      data.page = location.pathname;
      btn.disabled = true;
      setStatus(form, 'Sending...');
      fetch('/api/form', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(data) })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok && j.ok, j: j }; }); })
        .then(function (res) {
          if (res.ok) {
            form.querySelector('.rf-grid').hidden = true;
            form.querySelector('.rf-actions').hidden = true;
            var ts = form.querySelector('.cf-turnstile'); if (ts) ts.hidden = true;
            setStatus(form, 'Thank you. Your message has been sent and our team will get back to you shortly.', 'rf-ok');
          } else {
            btn.disabled = false;
            setStatus(form, (res.j && res.j.error) || 'Something went wrong. Please call us or try again.', 'rf-err');
          }
        })
        .catch(function () {
          btn.disabled = false;
          setStatus(form, 'Something went wrong. Please call us or try again.', 'rf-err');
        });
    });
  });
})();
