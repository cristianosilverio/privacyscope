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

## 4. Primeiro datapoint regulatório real (PlaywrightFetcher smoke 18/05/2026)

**Achado central:** UOL.com.br carrega **115 cookies antes** de qualquer interação com banner de consent. Delta para 118 após accept (apenas +3). Inversão do comportamento esperado pela LGPD: a maioria dos cookies entra **sem** consentimento prévio do titular.

**Comparativo nos 3 alvos** (cookies_pre_consent → cookies_post_consent):
- gov.br/anpd: 2 → 2 (delta 0; sem banner detectado — site não parece ter)
- serpro.gov.br: 0 → 13 (delta +13; aderência aparente ao opt-in)
- uol.com.br: **115 → 118** (delta +3; massiva exposição pré-consent)

**Validações que esta execução produziu:**
- ARIA como sinal primário funcionou: em serpro, o primeiro selector que casou foi `[aria-label*='aceitar' i]`, button text "Aceitar"
- Cookies_set como variável composta (não apenas contagem) já mostra valor: nos cookies novos do serpro estão `_ga`, `_gid`, `_gat` (Google Analytics) e `li_sugr` (LinkedIn) — sinal claro de tracking de terceiros pós-consent
- O framework distingue corretamente sites conformes (serpro) de não-conformes (uol) na metodologia pre/post-consent

**Para o TCC:** os números acima vão para tabela da seção Resultados (após piloto rodar com n=50, mas o sinal qualitativo já é demonstrável).

---

## 5. Banner não detectado em gov.br/anpd (false negative aceitável)

**Observação:** o site `https://www.gov.br/anpd/pt-br` não disparou nenhum dos seletores nem padrões de texto do banner. Resultado: `consent_actions[0].success = False` em 57ms.

**Diagnóstico provável:** o site da ANPD aparentemente não usa banner de cookies pop-up — ou é um site bem-comportado (carrega apenas cookies necessários) ou tem implementação atípica.

**Decisão:** não é bug; é dado. O framework registra `success=False` honestamente. Site permanece na amostra com `cookies_pre_consent == cookies_post_consent` (delta zero registrado explicitamente). Validar pós-piloto se a falha de detecção é generalizada em `.gov.br`.

---

## 6. Tempo por fetch acima do estimado

**Observação:** smoke contra os 3 sites levou 42s + 38s + 29s = 109s total. Estimativa original era 5-15s por site.

**Causa:** `_ensure_full_render` está custando ~10-15s por execução (networkidle 5s + 5 iterações de scroll 500ms cada + novo networkidle 5s, repetido para cada fase). Para 3 fases sem revoke: ~30-45s só de rendering.

**Decisão para a piloto:** aceitar como está; total estimado para n=384 é ~3-4h em modo serial. Paralelizar com asyncio (8 workers) reduz para ~30-45min. Tolerável.

**Refinamento opcional pós-piloto:** reduzir `scroll_max_iterations` de 5 para 3 (média observada de iterações reais é 1-2 antes de altura estabilizar). Pode cortar 5-10s por fase.

---

## 7. Screenshots por fase ocupam muito espaço em sites grandes

**Observação:** screenshots full-page do UOL chegaram a 4MB cada (PNG). Para n=384 sites × 2 fases (pre, post) = ~3GB de screenshots em coleta sem revoke. Com revoke, +1.5GB.

**Decisão:** aceitável no MVP; cada execução completa de protocolo é ~5GB com revoke. Disco local trivial.

**Refinamento opcional pós-piloto:** parâmetro `screenshot_format: "png" | "jpeg"` e `screenshot_quality: 0-100` para JPEG. JPEG 75% reduz screenshots a ~500KB sem perda significativa de auditabilidade visual. Não é prioridade agora.

---

## 8. FallbackChain validado end-to-end com escalada por sinal (19/05/2026)

**Cenário:** chain `[HttpFetcher → PlaywrightFetcher]` com `escalate_if` contendo 6 condições, contra os 3 sites baseline (gov.br/anpd, serpro.gov.br, uol.com.br).

**Resultado:** todos os 3 sites escalaram via `cookies_pre_consent_zero` — comportamento esperado porque o HttpFetcher é estruturalmente cego a cookies setados via JS. Audit log de 7 eventos por site, totalmente rastreável.

**Comparativo de tempos (sem screenshot por fase no chain, vs com no PlaywrightFetcher isolado):**

| Site | Chain (s) | Playwright isolado (s) | Economia |
|---|---|---|---|
| gov.br/anpd | 19.6 | 42.5 | 22.9s |
| serpro.gov.br | 37.8 | 37.9 | 0.1s |
| uol.com.br | 26.7 | 28.6 | 1.9s |

A economia em sites pesados de imagem (anpd com muitas tags) vem de `phase_screenshots=False`. Para a piloto real, **avaliar trade-off**: screenshots são evidência visual auditável, mas oneram disco (até 4 MB por fase em UOL).

**Recomendação para piloto:** ativar `phase_screenshots=True` apenas em fase `post_consent` (não em `pre_consent` nem `post_revocation`). Reduz disco em ~50% sem perder a evidência principal.

**Flutuação de cookies em UOL:**
- Smoke 18/05: 115 pré-consent
- Smoke 19/05: 130 pré-consent

Subiu 13% em 24 horas — provavelmente flutuação normal de redes de ads que rotacionam ou cookies temporários. **Decisão para a piloto:** coletar cada site 2-3 vezes em dias diferentes e tomar mediana. Variabilidade é dado, não bug.

---

## 9. Subpágina UOL retornou HTTP 403 (anti-bot)

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

---

## 10. Refatoração de cookies por fase para extensibilidade total (19/05/2026)

**Motivação:** durante o desenho do `FileSystemRepository`, ficou claro que
manter campos nominais `cookies`, `cookies_pre_consent`, `cookies_post_consent`,
`cookies_post_revocation` na `RawEvidence` produzia um layout interno do
`tar.gz` acoplado aos fetchers atuais. Adicionar um fetcher futuro com nova
fase (ex.: `post_geo_consent`) ou um fetcher single-shot diferente do
`HttpFetcher` exigiria mudar o tipo E o repositório — quebra de Open-Closed.

**Decisão:** unificar em um único campo dinâmico `cookies_by_phase:
dict[str, list[dict]]` na `RawEvidence`. Convenção de chaves:

- `"single"` para fetchers single-shot (HttpFetcher; futuros CurlCffi etc.).
- `"pre_consent"`, `"post_consent"`, `"post_revocation"` para o PlaywrightFetcher.
- Outros fetchers escolhem nomes próprios livremente.

**Impacto:**

- `core/types.py`: 4 campos → 1 (`cookies` + os 3 nominais consolidados).
- `playwright_fetcher.py`: popula `cookies_by_phase` montando dict por fase ativa.
- `http_fetcher.py`: popula `cookies_by_phase={"single": [...]}` quando há cookies.
- `_signals.py`: sinal `cookies_pre_consent_zero` lê `cookies_by_phase.get("pre_consent", [])`. Comportamento preservado: HttpFetcher (chave `"single"`, sem `"pre_consent"`) sempre dispara o sinal → escala para Playwright.
- Smoke scripts: ajustados para iterar `cookies_by_phase.items()`.
- `filesystem_repo.py`: layout `phases/<name>/cookies.json` é agnóstico ao fetcher — qualquer chave nova vira diretório novo automaticamente.

**Validação:** 3 cenários sintéticos validados (Playwright 3-fases, HTTP single-shot, evidência sem cookies). Round-trip put/get/verify do `FileSystemRepository` confirma serialização e desserialização preservam bytes idênticos.

**Para o TCC:** o desenho permite que a banca pergunte "como você lida com sites em jurisdições diferentes que têm fluxos adicionais de consent (banner geográfico do GDPR antes do brasileiro, p.ex.)?" — resposta concreta: chave nova no `cookies_by_phase`, zero mudança no tipo ou no repositório.

---

## 11. Smoke C2 — observações empíricas dos 3 VariableTests (19/05/2026)

**Resultados sintetizados nos 3 sites baseline** (n=9 VariableResults):

| Site | banner | política | canal_titular |
|---|---|---|---|
| gov.br/anpd | True 0.65 (struct+lex) | True 0.95 (qualificada, 10+ keywords) | True 0.95 (email LGPD + subpage encarregado) |
| serpro.gov.br | True 0.95 (struct+lex) | True 0.95 (qualificada) | False 0.95 (no_signal) |
| uol.com.br | True 0.95 (**OneTrust** vendor) | **False 0.95** (no_match) | False 0.95 (no_signal) |

**Observações com valor regulatório/argumentativo:**

1. **UOL com `tem_politica_privacidade=False`** é dado regulatório, não bug. O `subpage_selection` capturou apenas `termos_uso` no UOL — o link de política de privacidade ou está injetado via JS após `networkidle` (não capturado pelo Playwright atual), ou está em domínio diferente (e.g. social.api.uol.com.br), ou usa vocabulário não previsto. Para a banca: o framework é **honesto** sobre o que vê — não inventa positivo onde a página inicial não evidencia.

2. **`canal_titular` (categoria nova) com 0 acionamentos nos 3 baseline.** "Portal do Titular", "Seus Direitos", "Exercício de Direitos" são vocabulário ainda raro em sites brasileiros. A categoria foi criada porque é semanticamente correta (art. 18 LGPD) — esperar-se-á ver mais acionamentos em e-commerces e portais com programa LGPD maduro, fora deste baseline minimalista.

3. **`tem_canal_titular=True` no anpd** veio por dois sinais convergentes: e-mail com prefixo whitelist E subpágina encarregado qualificada (Encarregado de Dados na ANPD). Múltiplos sinais convergindo aumentam defensibilidade do achado.

4. **Banner com confidence 0.65 vs 0.95**: o anpd hoje (banner accept falhou) saiu medium; serpro (struct+lex sem accept) também saiu medium em smokes anteriores mas agora saiu high — variação real do alvo (banners brasileiros variam entre execuções). Esse comportamento foi pensado: `confidence_level` graduado capta a diferença entre "banner detectado + interagível" e "banner detectado + não-clicável".

**Para o TCC:** estes 9 datapoints já permitem ilustrar a Tabela de resultados descritivos. Após piloto B4 (n=50), as proporções globais serão calculadas e comparadas entre estratos (governamental vs empresarial).

---

## 12. Resultado isolado interessante — UOL detectou OneTrust

**Achado:** UOL retornou `banner_cookies` com `matched_via=vendor` e `vendor=OneTrust`. Primeiro caso real de detecção de CMP comercial pelo framework.

**Para o TCC:** evidência direta de que sites comerciais brasileiros de grande tráfego (UOL é top-10 do mercado nacional) usam ConsentManager Platforms estabelecidos. Suporta argumento de que o framework precisa reconhecer signatures de CMPs (não apenas léxico genérico) para evitar falso negativo em sites que não exibem texto léxico no HTML estático (CMPs renderizam texto via i18n após carga JS).

---

## 13. Smoke C3 — 15 resultados em 5 sites baseline (19/05/2026)

**Distribuição:**

| Variável | True | False |
|---|---|---|
| `tem_banner_cookies` | 5/5 | 0/5 |
| `tem_politica_privacidade` | 3/5 | 2/5 (uol, mercadolivre) |
| `tem_canal_titular` | 1/5 (só anpd) | 4/5 |

**Achado 1 — mercadolivre.com.br com política=False apesar de URL `/privacidade` acessada.**

O log do HttpFetcher mostra GET HTTP/1.1 200 em `https://www.mercadolivre.com.br/privacidade#tech-and-cookies`. Mas a variável `tem_politica_privacidade` deu False. Hipótese: o link foi capturado pelo `_subpage.py` mas categorizado como `termos_uso` (não `politica_privacidade`) devido ao `break`-no-primeiro-match do loop interno. O padrão `condi\w*[\s_\-]*de[\s_\-]*uso` ou similar pode ter casado o texto âncora antes do padrão de política.

**Ação proposta para B7 (pós-piloto):** alterar `extract_subpage_candidates` para casar contra TODAS as categorias e gerar entries em todas (vs. atual one-shot). Custo: ~10 linhas no `_subpage.py`. Benefício: link que casa "política E termos" entra em ambas, e o VariableTest decide qualificação por conteúdo.

**Achado 2 — `canal_titular` detectado em 1/5 (só anpd).**

Coerente com observação anterior (item 11): o vocabulário "Portal do Titular", "Seus Direitos", "Exercício de Direitos" ainda é raro fora de sites com programa LGPD maduro. ANPD detectou via subpágina `encarregado` + e-mail prefixo whitelist (`encarregado@anpd.gov.br` capturado no HTML).

**Ação proposta:** rodar piloto B4 (n=50) e revisar taxa de positivos. Se < 20%, considerar suplementar com classificador ML supervisionado em B9.

**Achado 3 — `mercadolivre.com.br` coletado em ~7s pelo HttpFetcher sem escalar para Playwright.**

Caso interessante: e-commerce expõe `/privacidade` via path estático no HTML inicial. Mesmo um banner OneTrust detectável (`tem_banner_cookies=True confidence=0.95`) foi detectado via HTML estático — não exigiu renderização JavaScript. **Argumento para banca:** sites bem-projetados em SEO mantêm conteúdo crítico no HTML inicial (acessibilidade + indexação), o que beneficia coleta automatizada.

**Achado 4 — `confidence=0.65` somente em anpd `tem_banner_cookies`.**

Único caso de medium hoje. Reflete variação real do site (banner accept falhou em runs anteriores e nesta também). Confidence graduado captura essa nuance — sem mascarar a observação como "banner detectado plenamente".

---

## 14. Pré-piloto n=10 com validação manual + refinamentos A/B (19/05/2026)

**Métricas do pré-piloto (antes dos refinamentos), n=9 coletados (1 falha):**

| Variável | Acurácia | Precisão | Recall | F1 | Discordâncias |
|---|---|---|---|---|---|
| tem_banner_cookies | 0,778 | 0,778 | 1,000 | 0,875 | 2 FP (nubank, serpro) |
| tem_politica_privacidade | 0,667 | 0,857 | 0,750 | 0,800 | 1 FP + 2 FN |
| tem_canal_titular | 0,667 | 1,000 | 0,625 | 0,769 | 3 FN |

Ressalva: TN=0 em banner/política e kappa instável (até negativo) — viés de composição (amostra toda institucional grande, poucos negativos verdadeiros). Métricas absolutas pouco informativas neste n; foco nas classes de erro.

**Correções de ground truth identificadas durante análise:**
- Nubank `tem_politica_privacidade`: rotulagem manual estava errada. Nubank TEM política em `/transparencia/politicas-de-privacidade-e-seguranca/politica-de-privacidade` e e-mail DPO. O "FP" do framework era acerto parcial (pegou a sub-página de segurança vizinha). Corrigido para True no ground_truth.
- Nubank e serpro `tem_banner_cookies`: confirmado sem banner. Os 2 FP são reais.

**Classes de erro e refinamentos aplicados:**

- **Refinamento A (aplicado):** link rotulado apenas "Privacidade"/"Privacy" (sem "política de") não casava nenhum padrão. Causou FN em uol e mercadolivre. Adicionados padrões `\bprivacidade\b` e `\bprivacy\b` em `politica_privacidade`. Precisão isolada baixa, mas o VariableTest qualifica por conteúdo (>=3 keywords, >=500 bytes), filtrando FP na 2a etapa.

- **Refinamento B (aplicado):** `extract_subpage_candidates` fazia `break` no primeiro match de categoria, jogando `/privacidade` em uma só categoria. Alterado para casar TODAS as categorias (dedup por categoria; `total` conta URLs únicas para respeitar `max_total`). Agora `/privacidade` pode alimentar `politica_privacidade` E `canal_titular` simultaneamente — corrige por tabela cruzada os FN de canal em gov.br e mercadolivre.

**Adiado para B7 (não refinar com n≤10 — risco de overfit):**
- Banner FP (markup de cookie presente sem banner ativo): exige detecção de visibilidade via rendering (CSS display/position/z-index), não só markup. Trabalho grande.
- FP de path-match (href contém "privacidade" mas página é outra, ex.: política de segurança): exigir mais keywords quando match foi via href, não texto.
- Canal do globo: 6 e-mails genéricos, nenhum LGPD. Possível e-mail `privacidade@g.globo` não capturado por TLD atípico, ou em subpágina não coletada.

**Pendência operacional:** magazineluiza.com.br falhou na coleta (errors_count=1, capturado pelo D12). Causa a investigar antes do B4 — re-rodar com -v.

**Correção colateral:** `compare_to_ground_truth.py` ganhou leitura robusta de encoding (utf-8-sig → cp1252 → latin-1) e detecção de delimitador (`;` do Excel BR vs `,`), pois o CSV salvo pelo Excel brasileiro vinha em cp1252 com separador ponto-e-vírgula.

---

## 15. Fechamento do pré-piloto B3.5 — refinamentos C/D/E/F (20/05/2026)

**Resultado final (comparison_v3, n=9 coletados):**

| Variável | F1 inicial → final | Decisão |
|---|---|---|
| tem_politica_privacidade | 0,800 → **1,000** | Fechada. Refinamentos A+B validados em produção. |
| tem_banner_cookies | 0,875 → 0,857 | 2 FP reais (nubank, serpro) → B7 (detecção de visibilidade). |
| tem_canal_titular | 0,769 → 0,769 | 3 FN heterogêneos → B7 (varrer subpáginas de política por âncora/email). |

**Refinamentos aplicados e validados nesta rodada:**

- **C** (`filesystem_repo.py`): nome de subpágina indexado `sub_NNN.html` + `_index.json`. Corrige crash MAX_PATH do Windows (globo.com tinha slug de notícia >100 chars). globo recuperado: n subiu de 8 para 9.
- **D** (`_subpage.py`): path-blockers (`/noticia/`, `/blog/`, `.ghtml`, etc.) descartam conteúdo editorial que casava "privacidade" por acaso no slug. Resolve a causa-raiz do FP+crash do globo.
- **E** (`http_fetcher.py`): robots.txt 4xx→allow-all, 5xx→disallow, conforme RFC 9309 §2.3.1.4 (KOSTER et al., 2022). PDF da RFC arquivado em Artigos/. magazineluiza deixou de abortar por robots.
- **F1** (protocolos): `escalate_if` do http_simples ganhou `exception: FetchError`. Sites com anti-bot que retornam 403 no GET (Akamai bloqueando httpx por TLS fingerprint) agora escalam ao PlaywrightFetcher (Chromium real) em vez de falhar. RobotsDisallowedError continua abortando — validado que abort_on tem precedência sobre escalate_if.

**Diagnóstico do magazineluiza:** após E, deixou de abortar por robots, mas o GET da home retorna 403 (Akamai anti-bot, X-SEC-TRIGGERED). No v3 o chain ainda não escalava (faltava F1). Com F1, passará a tentar o Playwright. Confiança média de que o Playwright passe (Akamai avançado detecta headless); se falhar, o site vai para o buffer do B4 — comportamento esperado e documentado (cf. nota 9).

**Veredito:** o pré-piloto cumpriu o objetivo de filtro de qualidade — pegou 3 bugs reais (crash MAX_PATH, robots conservador demais, ausência de escalonamento por anti-bot) que teriam causado perda silenciosa de sites no B4 (n=384). política saltou para F1=1,0. banner e canal têm refinamentos identificados e priorizados para B7, sem overfit a n=10.

**Parâmetros confirmados para o B4 (piloto n=50):**
- Estratificação **40 corporativos + 10 governamentais** (sobre-representação do estrato governamental; objetivo = panorama geral, não comparação de estratos).
- Fonte única: Tranco List top-1M filtrada por `.br`; estratos por sufixo `.gov.br`. Descer no ranking até obter governamentais suficientes.
- Buffer 60 mantendo proporção 40/10 (48 corp + 12 gov).
- Seleção das 50 efetivas **por estrato** (40 corp + 10 gov que coletarem primeiro), pós-processada do SQLite.
- Seed de amostragem: 20260520.
