# Rice Electronics (riceelectronics.com) em Cloudflare Workers

Réplica do site atual, servida como arquivos estáticos, com os formulários recriados no Worker.

- `public/` : site pronto (gerado, não editar na mão)
- `build.py` : gera `public/` a partir do espelho bruto do site antigo
- `src/index.js` : Worker (formulários em `/api/form` e redirect do domínio sem www)
- `forms/` : CSS e JS dos formulários
- `overrides/` : arquivos que substituem os originais (2 PDFs recomprimidos pra caber em 25 MiB)
- `relatorio-build.txt` : o que já estava quebrado no site antigo

## Rodar e publicar
    npm install
    npx wrangler dev      # teste local
    npx wrangler deploy   # publicar

## Configurar antes de ir pro ar
- `LEAD_TO` e `LEAD_FROM` em `wrangler.jsonc` (destino dos leads e remetente verificado no Resend)
- `npx wrangler secret put RESEND_API_KEY`
- opcional: `TURNSTILE_SITE_KEY` (vars) e `npx wrangler secret put TURNSTILE_SECRET`

Sem essas chaves os formulários respondem erro de propósito, pra nenhum lead se perder em silêncio.
