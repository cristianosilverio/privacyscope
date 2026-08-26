# Pendências técnicas

**Status:** aberto — nada foi alterado no código.
**Origem:** revisão do texto do TCC (agosto/2026). Ao conferir afirmações do
documento contra a implementação, apareceram divergências entre o que o código
faz e o que se afirma dele, em docstring, em documentação ou em teste. Registradas
aqui para tratamento posterior.

O arquivo nasceu como fila de pendências de docstring e passou a reunir também
código morto, dependência de ordem não declarada e comportamento que contraria
doutrina do próprio projeto. O nome acompanhou o escopo.

**Prioridade atual: finalizar o documento do TCC.** Não alterar código enquanto
essa meta não for concluída. Este arquivo é a fila de trabalho para depois.

## Como usar este arquivo

Cada item traz: arquivo e símbolo, o que se afirma hoje, o que o código faz de
fato, e o que precisa mudar. Ao corrigir um item, marque `[x]` e registre a data.
Ao descobrir um novo item durante a revisão do TCC, acrescente na mesma estrutura,
sem alterar o código no momento da descoberta.

**Declare a direção do conserto.** Nem todo item se resolve corrigindo o texto: há
casos em que o docstring está certo e o código é que erra. Quando for esse o caso,
diga-o na primeira linha do item, sob pena de alguém pacificar a divergência no
sentido errado e enterrar o defeito com aparência de resolvido.

Regra que motivou este arquivo: **conclusões sobre o comportamento do framework
devem ser tiradas do código, não do docstring.** Os docstrings deste projeto são
extensos e didáticos, o que os torna úteis e, ao mesmo tempo, propensos a
divergir da implementação quando esta muda.

---

## [ ] 1. `fetchers/_exceptions.py` — `RobotsDisallowedError`

**Docstring atual (item 3 do guia no cabeçalho do módulo e a própria classe):**

> "site explicitamente proibiu coleta via robots.txt. O FallbackChain NÃO deve
> escalonar — outro fetcher também deve respeitar."

**O que o código faz.** `HttpFetcher._load_robots` trata o status conforme a
RFC 9309, e a exceção nasce de **dois caminhos semanticamente distintos**:

| Status do `/robots.txt` | Tratamento | Levanta `RobotsDisallowedError`? |
|---|---|---|
| 200 | Parseia as regras | Só se houver `Disallow` aplicável ao nosso UA |
| 4xx (401/403/404 incl.) | `allow-all` (RFC 9309 §2.3.1.4) | Não |
| **5xx** | **Sintetiza `User-agent: * / Disallow: /`** | **Sim** |
| Laço de redirecionamento (>5 saltos) | `allow-all` | Não |

No caminho 5xx não há proibição: o servidor não conseguiu servir o arquivo. A
justificativa "outro fetcher também deve respeitar" não se aplica — outro
coletor, com caminho de rede e temporização distintos, poderia obter 200.
Abortar ali é decisão de política conservadora, não decorrência lógica.

O código registra que a semântica de 4xx mudou (comentário datado de
**2026-05-20**: 401/403 deixaram de ser tratados como `Disallow:/` porque
"tipicamente decorrem de proteção anti-bot genérica, e.g., Akamai retornando 403
ao robots.txt, não de diretiva de exclusão dirigida a crawlers"). Essa revisão
não chegou ao `_exceptions.py`.

**O que fazer:**

1. Distinguir os dois caminhos de origem na descrição da classe.
2. Registrar o tratamento por faixa de status, com a data da revisão de 4xx.
3. Substituir "a proibição aplica-se a qualquer agente de coleta" por
   formulação que cubra o caso 5xx (é política conservadora, não proibição).
4. Documentar o acoplamento de ordem descrito no item 2 abaixo.

## [ ] 2. `fetchers/fallback_chain.py` — dependência de ordem entre `abort_on` e `escalate_if`

**Não documentado em lugar nenhum.**

`_eval_condition_on_exception` casa por MRO, e `RobotsDisallowedError` herda de
`FetchError`, que está em `escalate_if` em todos os protocolos. O
comportamento correto depende de `_should_abort` ser avaliado **antes** de
`_should_escalate` no laço principal. Invertida a ordem, todo bloqueio de
robots passaria a escalar para o Playwright, silenciosamente.

**O que fazer:** documentar a dependência no docstring da classe `FallbackChain`
(ou no do laço) e considerar um teste de regressão que fixe a ordem.

## [ ] 3. `fetchers/_signals.py` — `is_cookies_pre_consent_zero`

**O docstring está correto**, mas omite a consequência sistêmica.

Ele afirma que o `HttpFetcher` "popula `cookies_by_phase['single']`, NUNCA
`'pre_consent'`. Logo este sinal SEMPRE dispara". Confere: `http_fetcher.py`
escreve exclusivamente a chave `"single"`; `"pre_consent"` só existe no
`playwright_fetcher.py`.

Como `escalate_if` é *any-of*, disso decorre que **o escalonamento HTTP →
Playwright é incondicional** em todos os protocolos vigentes. Os outros três
sinais (`html_root_smaller_than_bytes`, `subpage_selection_empty`,
`has_js_shell_markers`) nunca chegam a decidir nada; no máximo aparecem no
motivo registrado na trilha. O papel efetivo do componente HTTP não é atender
sítios simples sem custo de navegador, e sim **acumular evidência** que depois é
fundida por `_funde`.

**O que fazer:** acrescentar nota explicitando que, com este sinal em
`escalate_if`, a cadeia escala sempre e o componente HTTP opera como coletor
complementar. Vale a mesma nota no docstring do módulo `fallback_chain`.

## [ ] 4. `fetchers/_signals.py` — `are_consent_actions_all_failed` (sinal órfão)

**Não é erro de docstring, é código morto.** O sinal está implementado e
registrado em `SIGNAL_REGISTRY` como `consent_actions_all_failed`, mas:

- não é referenciado por nenhum protocolo em `protocols/` nem por `config/`;
- não poderia disparar na etapa HTTP → Playwright, porque `consent_actions` é
  populado exclusivamente pelo `playwright_fetcher.py` e a função abre com
  `if not actions: return False`.

**O que fazer:** decidir entre (a) removê-lo, (b) mantê-lo com nota explícita de
que só faz sentido em cadeias com dois fetchers capazes de interagir com banner.
Não deixar como está sem nota, porque induz leitor a crer que a interação com
banner participa da decisão de escalonamento — foi exatamente o erro que entrou
no texto do TCC e precisou ser corrigido.

---

## [ ] 5. `tests/ml_texto.py` — ramo sem segmentos devolve `False` onde a doutrina manda estado indeterminado

**ATENÇÃO: o comentário está CORRETO e o código está errado.** Não resolver este
item alinhando o comentário ao código.

**O que o comentário afirma**, imediatamente acima da linha: "Ausencia de conteudo
avaliavel NAO e ausencia de divulgacao."

**O que o código faz.** `return self._resultado(evidence, False, 0.0, ...)`.
Devolve ausência de divulgação, para os dois motivos possíveis do ramo,
`sem_texto_avaliavel` e `politica_outro_idioma`.

**O que o `orchestrator.py` declara**, no docstring da resolução de dependências:
o resultado sai "com valor `nao_aplicavel` — nunca `false`, que confundiria 'não
divulgou' com 'não foi medido' e enviesaria o indicador na direção que mais
importa". O ramo sem segmentos não passa pelo orquestrador e escapa da regra.

**O comportamento está fixado por teste.** `test_documento_sem_texto_nao_e_ausencia_de_divulgacao`
afirma no nome o contrário do que assere no corpo, onde exige `r.value is False`;
`test_politica_so_em_outro_idioma_recebe_motivo_proprio` afere motivo, e não
estado. Corrigir o código quebra os dois, e os nomes precisam ser reescritos junto.
Foi a leitura apressada do segundo nome que produziu, no texto do TCC, a afirmação
de que o sítio recebia estado próprio, corrigida em 23/08/2026.

**O que precisa mudar.** Separar os dois motivos, que hoje compartilham o mesmo
retorno:

- `sem_texto_avaliavel` para `nao_coletado`: o instrumento não obteve o objeto da
  medição, ainda que o detector de política tenha encontrado a política. É
  coerente com `tem_politica_privacidade = true` no mesmo sítio, porque achar a
  política e extrair texto dela são coisas distintas.
- `politica_outro_idioma` para `nao_aplicavel`: o documento existe, foi obtido e é
  legível; o que não se verifica é a precondição de ser declaração endereçada ao
  titular em português.

Avaliar antes o efeito sobre `outputs/renderizadores.py::_prioridade`, que manda o
não coletado para o fim da fila de triagem. Sob `nao_coletado`, os sítios afetados
saem da fila de inspeção e entram na de recoleta, o que parece o destino certo,
mas é mudança de comportamento na saída e não apenas de rótulo.

**Magnitude.** Coleta definitiva, execução `0d425930`: `politica_outro_idioma` não
ocorre nenhuma vez; `sem_texto_avaliavel` alcança dois sítios, o que dá seis
medições entre as três variáveis textuais. Nenhum resultado reportado no TCC
depende disso, porque as variáveis textuais não são reportadas por sítio.

---

## Sinais e exceções conferidos e sem pendência

Verificados contra a implementação durante a mesma revisão, sem divergência:

- `is_html_root_smaller_than_bytes` — default 1000; protocolos usam 5000.
- `is_subpage_selection_empty`
- `has_js_shell_markers`
- `JsRequiredError`
- `NavigationFailedError`
