# Pipeline de preparação do texto para os classificadores textuais

Documento de contrato. Descreve, em ordem de execução, o processamento aplicado ao
material coletado para produzir as unidades sobre as quais os classificadores de
finalidade, direitos do titular e transferência internacional operam.

O mesmo processamento tem de ser aplicado ao material de teste e, adiante, a qualquer
sítio submetido ao framework em operação. Divergência entre o preparo do treino e o do
uso produz degradação silenciosa: o modelo recebe unidades de natureza distinta
daquelas com que aprendeu, e o erro não se manifesta como falha, e sim como queda de
desempenho sem causa aparente.

Implementação em `scripts/segmentar_politicas.py`.

---

## Etapa 1 — Extração do material

**HTML.** Percorre-se a marcação recolhendo o texto visível. Descarta-se o conteúdo de
`script`, `style`, `noscript`, `head`, `svg` e `path`. Os elementos que o navegador
renderiza como bloco encerram o trecho corrente: `p`, `div`, `li`, `br`, `tr`, `td`,
`th`, `section`, `article`, `ul`, `ol`, `table`, `blockquote`, `dt`, `dd`, `form`,
`header`, `footer`, `nav`, `main`, `aside`, `figure`, `figcaption`, `hr` e `h1` a `h6`.

Os blocos são acumulados em estrutura própria, **jamais delimitados por marcador
inserido no texto**: qualquer caractere escolhido como marcador pode ocorrer no
conteúdo capturado — ao menos uma página da amostra traz byte nulo no texto.

**PDF.** Aproveita-se o texto já extraído no pacote de evidência, cuja obtenção
combina camada de texto e reconhecimento óptico conforme a disponibilidade.

O pacote é localizado pela pasta do TCC, informada por `--tcc` ou pela variável de
ambiente `PRIVACYSCOPE_TCC`. **Executar sem essa referência suprime, em silêncio, a
totalidade do texto publicado em PDF** — inclusive a política inteira dos sítios que só
publicam nesse formato. Por isso a ausência interrompe a execução, e segmentar sem os
PDF exige `--sem-pdf` explícito.

**Limpeza.** Removem-se caracteres de controle e colapsam-se sequências de espaço. A
remoção de caracteres de controle é pré-requisito das etapas seguintes e da gravação
em formato separado por delimitador, que não os admite.

### Independência da versão do interpretador

O analisador de hipertexto da biblioteca padrão decide por si quais elementos têm
conteúdo de **texto puro**, e essa decisão variou entre versões do CPython: as
antigas comprehendem apenas `script` e `style`; as recentes acrescentam `xmp`,
`iframe`, `noembed` e `noframes`.

A diferença é observável no material coletado. Onde `iframe` é tratado como texto
puro, sua marcação interna vira segmento — encontrou-se
`<span class="fr-mk" style="display: none;">&nbsp;</span>` em dois sítios; onde não
é, a marcação é analisada como marcação e apenas o texto interno comparece.

O extrator **declara o conjunto clássico**, `("script", "style")`, em vez de herdar
o do interpretador. A escolha é por compatibilidade com o corpo de rotulagem, que
foi construído e marcado sob esse comportamento, e não por mérito. Descartar todo o
conteúdo de `iframe` seria um terceiro comportamento, distinto dos dois que os
interpretadores exibem, e suprimiria texto legítimo.

Sem essa declaração, o mesmo material produz corpos distintos conforme o ambiente,
e o resumo criptográfico do conjunto de treino deixa de identificar coisa alguma.
A propriedade é verificada em `tests_unit/test_segmentacao.py`.

## Etapa 2 — Filtro de idioma, por subpágina

O classificador opera sobre política em português: o modelo de linguagem adotado é
pré-treinado nesse idioma, e o vocabulário da representação esparsa se fragmentaria
entre línguas. Subpágina redigida em outro idioma é **removida**.

Remover difere de rotular como negativo. Num esquema em que a ausência de marca
significa ausência do requisito, deixar tais segmentos sem marcação afirmaria que
passagens que de fato declaram finalidade não a declaram — falso negativo introduzido
por artefato de idioma.

A detecção compara a frequência de vocábulos funcionais de cada língua e opera **por
subpágina**, nunca por segmento: o segmento tem extensão mediana de algumas dezenas de
caracteres, insuficiente para identificação confiável, ao passo que a subpágina reúne
milhares e a separação observada é inequívoca.

| parâmetro | valor | função |
|---|---|---|
| `MIN_IDIOMA` | 400 | abaixo disso preserva-se, por insuficiência de evidência |
| `RAZAO_IDIOMA` | 1,4 | predominância exigida para declarar outro idioma |

Documento cujas subpáginas sejam todas estrangeiras resulta vazio. A situação recebe
status próprio, `politica_outro_idioma`, e é reportada: trata-se de sítio cuja política
não se endereça ao titular em português, o que não é ausência de política nem omissão
do requisito.

## Etapa 3 — Reconstrução do texto extraído de PDF

A extração de PDF devolve as linhas de **diagramação**, não períodos: a quebra ocorre
onde a margem da página termina, e a oração se reparte ao meio. Sem esta etapa, apenas
12% das unidades encerram em pontuação.

Três operações, **nesta ordem**:

1. **Remoção de linha recorrente.** Cabeçalho e rodapé repetem-se a cada folha.
   Suprimem-se as linhas que ocorram três vezes ou mais no mesmo documento, desde que
   não excedam 150 caracteres. A operação **precede** a junção: aplicada depois, o
   cabeçalho já teria aderido ao conteúdo, tornando única cada ocorrência e escapando
   à detecção.

2. **Junção das linhas**, encerrando a unidade apenas diante de `.`, `!`, `?` ou `;`.
   O ponto e vírgula é incluído porque a enumeração de direitos e de finalidades o
   emprega como separador de item; desconsiderá-lo fundiria a lista inteira em unidade
   única. Linha terminada em hífen indica vocábulo partido, e a junção se faz sem
   espaço.

3. **Marcador de item sempre inicia unidade.** Reconhecem-se numeração decimal, letra
   e algarismo romano, com ou sem parênteses. Sem esta regra, o título de seção, que
   não encerra em pontuação, absorve o número do item seguinte.

| parâmetro | valor |
|---|---|
| `REPET_PAGINA` | 3 |
| `MAX_RECORRENTE` | 150 caracteres |

## Etapa 4 — Divisão por sentença

A unidade é a **sentença**. Quando o bloco não contém fronteira de sentença — item de
lista, título, célula de tabela —, o próprio bloco constitui a unidade. A regra é única
e dispensa limiar de comprimento.

A fronteira é o sinal de pontuação final seguido de espaço e maiúscula, mais os
marcadores de item numerado e entre parênteses. Protegem-se previamente os pontos que
não encerram período: abreviaturas correntes em texto jurídico e em política de
privacidade — `art.`, `arts.`, `inc.`, `n.`, `nº`, `Ltda.`, `Sr.`, `Sra.`, `Dr.`,
`Dra.`, `Av.`, `etc.`, `Prof.`, `Cia.` e outras —, iniciais isoladas e separadores
decimais.

Blocos que resistam à divisão — enumeração sem pontuação, lista de países em campo de
formulário — permanecem extensos. Reparti-los por contagem de caracteres seria corte
arbitrário no interior de oração.

## Etapa 5 — Deduplicação por sítio

Cabeçalho, rodapé e menu não integram o objeto de análise, mas **não podem ser
excluídos pela marca semântica** que os envolve: 10,5% das passagens que fundamentam
os rótulos residem dentro de `header`, `footer`, `nav` ou `aside`, porque parte
expressiva dos sítios emprega esses elementos de forma incorreta.

Adota-se **deduplicação**: de cada texto idêntico dentro do mesmo sítio preserva-se
uma ocorrência, a primeira, e descartam-se as demais. Não há remoção por repetição, e
**não há parâmetro de corte**.

### Por que a formulação anterior foi abandonada

A versão anterior descartava toda ocorrência de texto que comparecesse cinco vezes ou
mais no mesmo sítio, ou em cinco sítios distintos. Três medições a inviabilizaram:

1. **O problema é duplicação, não presença.** A mesma frase contada dezenas de vezes
   distorce a proporção de classes, a ponderação pelo inverso da frequência documental
   e — sobretudo — as próprias métricas: como as cópias residem no mesmo documento e a
   partição é por documento, a decisão do modelo sobre uma única sentença comparece
   várias vezes no conjunto reunido. Preservar uma cópia resolve a duplicação sem
   suprimir texto algum.

2. **O critério entre sítios removia declaração.** Sete segmentos portadores de
   evidência foram descartados exclusivamente por ele. Política copiada de modelo
   continua sendo declaração do controlador que a publicou, e o título "Transferência
   internacional de dados" sobreviveu apenas por comparecer em quatro sítios, a um
   passo do corte.

3. **O critério entre sítios acoplava cada sítio à composição da execução.** O mesmo
   documento produzia conjuntos distintos conforme quem mais estivesse na rodada.

### Consequência declarada

Material de navegação passa a integrar o conjunto, uma vez por sítio. Isso é
deliberado: a etapa 6 suprime o cromo mais curto, e o que resta é exatamente o que o
arcabouço encontrará em operação — de modo que o classificador aprende a rejeitá-lo no
treino, em vez de encontrá-lo pela primeira vez em campo.

### Rótulo da sobrevivente

Quando ocorrências do mesmo texto divergem quanto ao rótulo derivado do casamento
posicional, a sobrevivente recebe o rótulo **positivo**. A divergência decorre de o
intervalo da transcrição cobrir uma ocorrência e não as outras; descartar a positiva
suprimiria evidência por acidente de posição.

## Etapa 6 — Descarte de fragmento curto

Descartam-se as unidades com menos de 20 caracteres, remanescentes de navegação que as
etapas anteriores não alcançaram.

O descarte ocorre **apenas na saída**. O documento contíguo empregado para localizar as
passagens transcritas é montado com a totalidade das unidades: filtrar antes abriria
lacunas e impediria a correspondência de trechos que as atravessam.

---

## Aplicação a material novo

**Todas as etapas dependem apenas do documento e se aplicam sem alteração.**

Essa propriedade não existia na formulação anterior: o critério de repetição entre
sítios exigia conjunto de referência, indisponível quando se avalia um sítio isolado, e
obrigava a declarar uma entre duas condutas divergentes. A deduplicação é estritamente
intra-sítio e é computável sobre um único documento, de sorte que **o preparo do treino
e o preparo do uso passam a coincidir por construção**, e não por convenção.

## Parâmetros congelados

| parâmetro | valor | origem |
|---|---|---|
| `MIN_SEG` | 20 | inspeção |
| `MIN_IDIOMA` | 400 | inspeção |
| `RAZAO_IDIOMA` | 1,4 | inspeção |
| `REPET_PAGINA` | 3 | inspeção |
| `MAX_RECORRENTE` | 150 | inspeção |

Os cinco foram fixados por inspeção e **não foram validados**; constituem limitação
declarada. O corte de repetição, sexto parâmetro da formulação anterior e único
derivado do conjunto rotulado — e por isso não recalculável em produção —, **deixou de
existir** com a adoção da deduplicação.

## Verificações embutidas

**Identidade de conteúdo.** Confronta-se o texto reextraído contra o pacote de
evidência congelado, vocábulo a vocábulo, exigindo-se coincidência de 98%. A
verificação emprega o conjunto **integral**, anterior ao filtro de idioma, porque afere
a fidelidade da extração e não as exclusões deliberadas que a sucedem.

**Preservação da evidência.** Após o filtro de navegação, verifica-se que nenhum
documento rotulado ficou sem segmento positivo. Violação interrompe o processamento.

**Localização das transcrições.** Reporta-se quantas passagens transcritas foram
localizadas no documento reconstituído. Queda nesse número entre execuções indica que
alguma etapa passou a suprimir material que antes preservava.
