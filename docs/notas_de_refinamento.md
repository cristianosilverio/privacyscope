# Notas de Refinamento — pendências validadas em execução

Itens detectados durante execução e que dependem de amostra mais representativa
para serem refinados com base empírica. Não bloqueiam B3.

---

## 1. Defaults de `DEFAULT_SUBPAGE_CATEGORIES` são permissivos demais

**Origem:** smoke test do `HttpFetcher` em 17/05/2026 contra `gov.br/anpd`,
`serpro.gov.br` e `uol.com.br`.

**Evidência de imprecisão observada:**

| Site | Link capturado | Categoria atribuída | Avaliação humana |
|---|---|---|---|
| gov.br/anpd | "Denúncia de descumprimento da LGPD" | `politica_privacidade` | **Falso positivo** — é página de denúncia, não política |
| serpro.gov.br | "3ª Semana Serpro de Privacidade e Proteção de Dados" | `politica_privacidade` | **Falso positivo** — é evento, não documento normativo |
| uol.com.br | "Termos de Uso" → `https://noticias.uol.com.br/regras/termos-de-uso/` | `termos_uso` | Correto (mas o GET retornou HTTP 403 — bloqueio anti-bot por User-Agent) |

**Hipóteses sobre causa:**

- `\blgpd\b` sozinho é gatilho fraco — qualquer link que mencione "LGPD" passa,
  inclusive denúncia, FAQ, blog.
- `prote\w*[\s_\-]*de[\s_\-]*dados` casa qualquer menção solta a "proteção de
  dados" (eventos, notícias, glossários).
- A ausência de qualificadores como "política", "aviso", "termo" no token-âncora
  causa baixa precisão.

**Ações propostas para refinamento (após coleta real n=50):**

1. Coletar amostra n=50 com os defaults atuais.
2. Rotular manualmente cada match (verdadeiro positivo / falso positivo).
3. Recalcular regexes priorizando precisão sobre recall:
   - Exigir token de "nominalização" (`polit\w+`, `aviso`, `termo`) no padrão,
     em vez de aceitar `\blgpd\b` ou `prote\w+\s+de\s+dados` isolados.
   - Considerar âncoras de palavra (`^`, `$`) quando casamento for contra `href`
     para reduzir matches em paths longos contendo a palavra-chave.
   - Penalizar matches em contextos óbvios de notícia (`/noticias/`, `/blog/`,
     `/eventos/`) — possivelmente via lista de path-blockers configurável.
4. Documentar precisão/recall por categoria nos Resultados Preliminares.

**Decisão atual:** manter os defaults permissivos até a piloto rodar, para que
o framework não filtre cedo demais e perca matches úteis. A baixa precisão é
**observável** via `subpage_selection.matched_pattern` em cada `RawEvidence` —
exatamente o motivo pelo qual essa auditoria foi adicionada à camada de tipos.

---

## 2. HttpFetcher captura zero cookies em todos os 3 alvos do smoke

**Observação:** `Cookies fixados via Set-Cookie: 0` em gov.br/anpd, serpro.gov.br
e uol.com.br.

**Não é bug** — é a limitação documentada do HttpFetcher: cookies setados via
JavaScript (`document.cookie` após consent banner, analytics tags, etc.) não
aparecem em coleta HTTP simples. UOL é o caso clássico: a página depende de
banner de consent JS, que só dispara `Set-Cookie` após interação.

**Conclusão para o TCC:** este resultado é evidência empírica da **necessidade
do FallbackChain** com PlaywrightFetcher para coleta de cookies em sites
comerciais brasileiros. Vai virar argumento de defesa em banca para justificar
a complexidade arquitetural.

---

## 3. Incorporação de ARIA e title na detecção de subpáginas (HttpFetcher)

**Origem:** sugestão do autor com base em experiência prática da LGPD2U.

**Mudança:** `_extract_subpage_candidates` passou a inspecionar, além de `text` e `href`, os atributos `aria-label` e `title` de cada `<a>`. A ordem de prioridade é:

1. `text` — o que o usuário vê
2. `aria-label` — o que tecnologias assistivas "veem" (WCAG / eMAG / LBI)
3. `title` — tooltip
4. `href` — URL/path

O campo `subpage_selection[*].matched_against` agora pode assumir os quatro valores acima.

**Justificativa regulatória/técnica:**

- Decreto 5.296/2004 e Lei Brasileira de Inclusão (Lei 13.146/2015) tornam acessibilidade praticamente obrigatória em sites `.gov.br` — ARIA está amplamente disponível neste estrato
- Grandes empresas adotam ARIA por compliance ESG / acessibilidade
- Sites bem-feitos frequentemente têm ícones ou links genéricos ("Saiba Mais") cujo único sinal explícito está em `aria-label`
- Padrão amplamente recomendado pela eMAG (Modelo de Acessibilidade em Governo Eletrônico)

**Limitação reconhecida:**

- `aria-labelledby` (referência indireta a outro elemento) **não** é resolvido nesta versão — exigiria 2 passes pelo DOM, ganho marginal
- ARIA dinâmica (setada via JS após carga) só será capturada pelo PlaywrightFetcher, não pelo HttpFetcher

**Validação esperada:**

- Re-rodar smoke test em sites institucionais com ícones-link (frequente em `.gov.br`)
- Estatística agregada: % de matches por `matched_against` quando piloto rodar — informa se ARIA está sendo de fato útil ou se text/href já capturariam

---

## 4. Subpágina UOL retornou HTTP 403 (anti-bot)

**Site:** `https://noticias.uol.com.br/regras/termos-de-uso/`
**Status:** `403 Forbidden`

**Hipóteses:**

- UOL bloqueia User-Agents não-browsers no subdomínio de notícias
- Pode ser bloqueio por TLS fingerprint (httpx tem TLS fingerprint diferente de Chrome)

**Decisão atual:** não circumvent. Manter User-Agent identificável de pesquisa
é decisão consciente. Sites que bloqueiam coleta acadêmica documentada **ficam
fora da amostra efetiva** — registrado em `errors`. Isso preserva ética e é
auditável.

**Possível evolução futura (não para este TCC):** plugin `CurlCffiFetcher`
que simula TLS fingerprint de Chrome real, para casos em que coleta é
juridicamente lícita mas tecnicamente bloqueada por proteção excessiva.
