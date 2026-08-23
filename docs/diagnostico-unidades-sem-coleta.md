# Diagnóstico das unidades sem coleta — coleta ao vivo de 15/08/2026

**Apurado em:** 16 e 17/08/2026
**Conjunto:** as 20 unidades declaradas em `protocols/aovivo.yaml` que não produziram
resultado na execução `eff21c08`
**Reprodução:** `scripts/listar_sem_coleta.py`, `protocols/diagnostico_20.yaml`,
`scripts/resumir_diagnostico.py`, `scripts/sondar_rede.py`

---

## 1. Por que este documento existe

Vinte de cem unidades desapareceram da coleta ao vivo sem deixar registro além de
linhas de log. Some do numerador e do denominador ao mesmo tempo, e qualquer
proporção calculada passa a medir prevalência **entre os sítios alcançados**, e não
entre os amostrados.

O diagnóstico mostrou que "não coletado" reunia cinco fenômenos distintos, com
responsáveis distintos. Três deles o arcabouço passou a distinguir sozinho; dois só
a verificação humana identifica, e é esse o registro que este documento preserva.

---

## 2. Resultado consolidado

| estado | n | quem responde |
|---|---:|---|
| coletado (após as correções) | 7 | — |
| `unidade_inexistente` | 5 | quadro amostral |
| `nao_coletado`, defeito de quadro não detectável | 5 | quadro amostral |
| `nao_coletado`, falha real do sítio | 2 | o sítio |
| `nao_coletado`, `robots.txt` proíbe | 1 | decisão do controlador |

**Taxa de alcance: 0% → 46,7%** (7 de 15, excluídas do denominador as cinco unidades
inexistentes — endereço que não designa hospedeiro não é sítio não alcançado).

O quadro amostral responde por **10 das 20**. O arcabouço prova 5; as outras 5 são
indistinguíveis, para o instrumento, de indisponibilidade.

---

## 3. As sete recuperadas

Recuperadas por correções que só funcionam em conjunto: a queda para a variante
`www.` no coletor por requisição simples, e a **fusão de evidência** na cadeia, que
deixou de descartar coleta bem-sucedida quando o coletor seguinte falha. A fusão une
o que cada camada obteve, com a mais recente vencendo apenas nas colisões, e cada
artefato passa a registrar o coletor que o produziu.

| domínio | política | caminho |
|---|---|---|
| `anp.gov.br` | sim | `www.anp.gov.br` → 301 → `gov.br/anp` |
| `infraero.gov.br` | sim | `www.infraero.gov.br` → 302 → `www4` |
| `tjap.jus.br` | sim | `www.tjap.jus.br` → `/portal/politica-privacidade` |
| `kroton.com.br` | sim | ápex → 301 → `ri-cogna2025.mz-sites.com` |
| `novajus.com.br` | não | `www.novajus.com.br` |
| `wurthdobrasil.com.br` | não | `www.wurthdobrasil.com.br` |
| `uems.br` | sim | `www.uems.br`, com certificado registrado e coleta mantida |

**Seis das sete escalaram por `cookies_pre_consent_zero`**, e o sinal está correto: o
coletor por requisição simples só enxerga `Set-Cookie` de cabeçalho HTTP, de modo que
cookie posto por JavaScript — o caso de praticamente todo gerenciador de consentimento
— não aparece. Zero cookie ali não indica sítio que não rastreia; indica **camada não
observada**, que é exatamente o que o escalonamento serve para resolver.

Hipótese descartada: cheguei a ler o sinal como penalização do sítio conforme. Era
leitura errada — o sinal mede completude da coleta, e não o fenômeno. O defeito estava
apenas no descarte da evidência quando a camada seguinte falhava.

`kroton.com.br` foi coletado com marca de degradação numa execução e sem marca em
outra, 45 minutos depois. Instabilidade do instrumento, na mesma linha do caso
`unimeduberaba.com.br`.

---

## 4. Unidade inexistente — 5

O nome declarado não resolve, nem na variante `www.`. Confirmado em três redes
distintas: a máquina de coleta, resolvedor público 8.8.8.8 e infraestrutura externa.

| domínio | onde o sítio responde | por que nenhum coletor chega |
|---|---|---|
| `pdpj.jus.br` | `portaldeservicos.pdpj.jus.br` | subdomínio arbitrário |
| `lumeway.com.br` | `fenix.lumeway.com.br` | subdomínio arbitrário |
| `policia-civil.sp.gov.br` | `www.policiacivil.sp.gov.br` | outro nome registrável, sem hífen |
| `primelinelatam.com.br` | não localizado | provavelmente extinto |
| `ia.br` | ninguém | categoria de segundo nível, não é sítio |

---

## 5. Defeito de quadro que o instrumento não detecta — 5

O nome **resolve**. Para o coletor, é indistinguível de sítio fora do ar. Só a
verificação humana localizou o endereço real.

| domínio | sintoma no coletor | onde responde |
|---|---|---|
| `acessorh.com.br` | certificado de `api.people.unico.app`; a coleta falha depois, no destino do redirecionamento | `acesserh.com.br` — grafia distinta, certificado válido. **O achado do certificado é registrado mesmo com a unidade perdida** |
| `sgisistemas.com.br` | `ConnectTimeout` no ápex e no `www.` | `smart.sgisistemas.com.br` |
| `online.net.br` | `ConnectTimeout` no ápex e no `www.` | `velocidade.online.net.br` |
| `fulltrack.net.br` | ápex sem conexão; `www.` é NXDOMAIN | `fulltrack-tools.ftdata.com.br` — outro domínio |
| `franca.sp.gov.br` | `ConnectTimeout` no ápex e no `www.` | `www3.franca.sp.gov.br` — `www3` não sai de regra |

**Não há correção de código possível.** Adivinhar subdomínio a partir do nome seria
inventar dado. A única transformação determinística disponível é o prefixo `www.`, e
ela já está implementada.

---

## 6. Falha real do sítio — 2

| domínio | causa técnica | verificação |
|---|---|---|
| `bitcom.psi.br` | `www.bitcom.psi.br` encerra a conexão durante o *handshake*: `UNEXPECTED_EOF_WHILE_READING` | falha com e sem validação de certificado |
| `meucurriculoperfeito.com.br` | aceita TCP e não responde em HTTPS; `ERR_HTTP2_PROTOCOL_ERROR` no Chromium | mesmo comportamento no `www.` e em duas redes |

`uems.br` estava neste grupo e **saiu**: desde 17/08/2026 o coletor registra o
certificado defeituoso e prossegue, em vez de desistir. Sai com
`tls_estado=cadeia_ou_validade`, `*.uems.br`, GlobalSign — a cadeia de certificação é
incompleta, e isso é observação sobre o controlador, não motivo para perder a unidade.

Certificado inválido ultrapassa falha de coleta: transporte sem proteção adequada é
matéria do art. 46 da Lei 13.709/2018.

---

## 7. Comportamento correto — 1

`qualityautomacao.com.br` proíbe o agente por `robots.txt`. O sítio está no ar,
responde 200 e tem certificado válido. O arcabouço obedece e registra `robots_proibe`.
Não é falha: é decisão declarada do controlador, e o dado é o próprio achado.

---

## 8. Hipóteses descartadas no percurso

**A rede de coleta.** Levantei que parte da perda fosse do ambiente. A sondagem na
máquina de coleta bateu com a referência externa em todos os casos comparáveis, e os
cinco controles conectaram. Descartada.

**Hostilidade a rastreamento no estrato governamental.** O excesso medido —
46,2% contra 16,1%, razão de 2,87, Fisher bilateral *p* = 0,021 — é verdadeiro como
número, mas a causa não é bloqueio dirigido a coletor: dos seis governamentais, um é
host morto, um é erro de grafia, um foi recuperado pela variante `www.`, dois têm
conexão travada e um foi recuperado. Nenhum caso de anti-bot. Descartada.

**Certificado inválido em `acessorh.com.br` como propriedade do sítio.** É
consequência da mudança de domínio: o nome antigo aponta para servidor cujo
certificado responde por `acesserh.com.br`. Reclassificado como defeito de quadro.

---

## 9. Limitação metodológica da sondagem

`scripts/sondar_rede.py` **desativa a validação de certificado** para conseguir ler o
estado do servidor. Por isso reportou `HTTP/1.1 200 OK` para `www.uems.br` e
`acessorh.com.br`, que o coletor recusa — corretamente. Toda leitura da sondagem
precisa ser confrontada com o coletor antes de virar conclusão.

A reexecução mede a disponibilidade **do dia da reexecução**, e não reconstrói a
falha original de 15/08/2026: os motivos originais existiram apenas em terminal e não
foram transcritos.
