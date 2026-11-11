// Worker do site da Rice Electronics.
// Os arquivos estáticos (./public) são servidos direto pela plataforma;
// este código só roda em /api/* e no redirect do domínio sem www.

const FORMS = {
  contact: 'Contact Us',
  quote: 'Request A Quote',
  consultation: 'Free Consultation',
  safetech: 'Safetech',
  ecosystem: 'Ecosystem CTA',
  newsletter: 'Newsletter',
};

const FIELDS = [
  ['first_name', 'First Name'], ['last_name', 'Last Name'], ['company', 'Company Name'],
  ['phone', 'Phone'], ['email', 'Email'], ['address', 'Street Address'], ['city', 'City'],
  ['state', 'State'], ['zip', 'Zip Code'], ['comments', 'Comments or Questions'],
  ['source', 'How Did You Find Us?'],
];

const REQUIRED = {
  contact: ['first_name', 'last_name', 'company', 'phone', 'email', 'address', 'city', 'state', 'zip', 'source'],
  quote: ['first_name', 'last_name', 'company', 'phone', 'email', 'address', 'city', 'state', 'zip', 'source'],
  consultation: ['first_name', 'last_name', 'company', 'phone', 'email', 'address', 'city', 'state', 'zip', 'source'],
  safetech: ['first_name', 'last_name', 'phone', 'email'],
  ecosystem: ['first_name', 'last_name', 'phone', 'email'],
  newsletter: ['first_name', 'last_name', 'company', 'email'],
};

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' } });

const clean = (v, max = 4000) => String(v ?? '').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, '').trim().slice(0, max);
const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function verifyTurnstile(env, token, ip) {
  if (!env.TURNSTILE_SECRET) return true;
  const body = new URLSearchParams({ secret: env.TURNSTILE_SECRET, response: token || '' });
  if (ip) body.set('remoteip', ip);
  const r = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', { method: 'POST', body });
  const out = await r.json().catch(() => ({}));
  return out.success === true;
}

async function handleForm(request, env) {
  if (request.method !== 'POST') return json({ ok: false, error: 'Method not allowed.' }, 405);
  const origin = request.headers.get('origin');
  if (origin && new URL(origin).host !== new URL(request.url).host) return json({ ok: false, error: 'Invalid origin.' }, 403);

  let data;
  try { data = await request.json(); } catch { return json({ ok: false, error: 'Invalid request.' }, 400); }

  // honeypot: robô preenche, gente não vê. Responde ok sem enviar nada.
  if (clean(data.website)) return json({ ok: true });

  const form = clean(data.form, 40);
  if (!FORMS[form]) return json({ ok: false, error: 'Unknown form.' }, 400);

  const values = {};
  for (const [key] of FIELDS) values[key] = clean(data[key], key === 'comments' ? 4000 : 200);
  for (const key of REQUIRED[form]) if (!values[key]) return json({ ok: false, error: 'Please fill in the required fields.' }, 400);
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email)) return json({ ok: false, error: 'Please enter a valid email address.' }, 400);

  const ip = request.headers.get('cf-connecting-ip') || '';
  if (!(await verifyTurnstile(env, data['cf-turnstile-response'], ip)))
    return json({ ok: false, error: 'Verification failed. Please try again.' }, 400);

  // Sem destino configurado o formulário falha de propósito, pra ninguém achar que o lead foi entregue.
  if (!env.RESEND_API_KEY || !env.LEAD_TO || !env.LEAD_FROM) {
    console.error('Formulário recebido mas email não configurado (RESEND_API_KEY / LEAD_TO / LEAD_FROM).');
    return json({ ok: false, error: 'This form is not available right now. Please call us at 713-991-0999.' }, 503);
  }

  const rows = FIELDS.filter(([key]) => values[key]).map(([key, label]) => [label, values[key]]);
  rows.push(['Page', clean(data.page, 300)]);
  const text = rows.map(([l, v]) => `${l}: ${v}`).join('\n');
  const html = `<table cellpadding="6" style="font-family:Arial,sans-serif;font-size:15px;border-collapse:collapse">${rows
    .map(([l, v]) => `<tr><td style="font-weight:bold;vertical-align:top;border-bottom:1px solid #ddd">${esc(l)}</td><td style="border-bottom:1px solid #ddd">${esc(v).replace(/\n/g, '<br>')}</td></tr>`)
    .join('')}</table>`;

  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { authorization: `Bearer ${env.RESEND_API_KEY}`, 'content-type': 'application/json' },
    body: JSON.stringify({
      from: env.LEAD_FROM,
      to: env.LEAD_TO.split(',').map((s) => s.trim()).filter(Boolean),
      reply_to: values.email,
      subject: `[Rice Electronics] ${FORMS[form]}: ${values.first_name} ${values.last_name}`.trim(),
      text,
      html,
    }),
  });
  if (!res.ok) {
    console.error('Resend falhou', res.status, await res.text());
    return json({ ok: false, error: 'We could not send your message. Please call us at 713-991-0999.' }, 502);
  }
  return json({ ok: true });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // domínio sem www sempre vai pro www (hoje os dois respondem 200 com o mesmo conteúdo)
    if (env.CANONICAL_HOST && url.hostname === env.CANONICAL_HOST.replace(/^www\./, '')) {
      url.hostname = env.CANONICAL_HOST;
      url.protocol = 'https:';
      return Response.redirect(url.toString(), 301);
    }

    if (url.pathname === '/api/form/config') return json({ turnstileSiteKey: env.TURNSTILE_SITE_KEY || '' });
    if (url.pathname === '/api/form') return handleForm(request, env);
    if (url.pathname.startsWith('/api/')) return json({ ok: false, error: 'Not found.' }, 404);

    return env.ASSETS.fetch(request);
  },
};
