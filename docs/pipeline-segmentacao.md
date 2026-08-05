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

**Limpeza.** Removem-se caracteres de controle e colapsam-se sequências de espaço. A
remoção de caracteres de controle é pré-requisito das etapas seguintes e da gravação
em formato separado por delimitador, que não os admite.

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

## Etapa 5 — Remoção de material de navegação

Cabeçalho, rodapé e menu não integram o objeto de análise, mas **não podem ser
excluídos pela marca semântica** que os envolve: 10,5% das passagens que fundamentam
os rótulos residem dentro de `header`, `footer`, `nav` ou `aside`, porque parte
expressiva dos sítios emprega esses elementos de forma incorreta.

Adota-se critério de **repetição**. Material de navegação reaparece em cada subpágina
do mesmo sítio; material de modelo de plataforma reaparece em sítios distintos. Texto
que se repete nessa escala não constitui declaração do controlador sobre o tratamento.

O corte é o menor valor em que **nenhum documento rotulado perde a totalidade de sua
evidência**. A formulação ao nível do documento, e não do segmento, decorre de
observação: o casamento posicional ocasionalmente varre para dentro da passagem um
título contíguo que se repete em todas as subpáginas, e exigir que nenhum segmento
positivo seja atingido faria um único sítio elevar o corte de cinco para vinte e uma
ocorrências.

**Sob o material coletado, o corte apurado é 5.**

## Etapa 6 — Descarte de fragmento curto

Descartam-se as unidades com menos de 20 caracteres, remanescentes de navegação que as
etapas anteriores não alcançaram.

O descarte ocorre **apenas na saída**. O documento contíguo empregado para localizar as
passagens transcritas é montado com a totalidade das unidades: filtrar antes abriria
lacunas e impediria a correspondência de trechos que as atravessam.

---

## Aplicação a material novo

As etapas 1 a 4 e 6 dependem apenas do documento e se aplicam sem alteração.

A **etapa 5 exige atenção**. O critério de repetição no mesmo sítio é computável sobre
um único documento. O critério de repetição entre sítios distintos exige conjunto de
referência, indisponível quando se avalia um sítio isolado. Duas condutas são
admissíveis, e a escolha deve ser declarada:

- aplicar somente o critério intra-sítio, aceitando que material de modelo de
  plataforma não seja removido; ou
- conservar o conjunto de treino como referência e confrontar cada segmento novo
  contra ele.

O **corte de 5 é parâmetro congelado**. Ele foi derivado com as passagens positivas à
vista, e não pode ser recalculado sobre material não rotulado — não há evidência a
preservar. Recalculá-lo em produção descaracterizaria o procedimento.

## Parâmetros congelados

| parâmetro | valor | origem |
|---|---|---|
| `MIN_SEG` | 20 | inspeção |
| `MIN_IDIOMA` | 400 | inspeção |
| `RAZAO_IDIOMA` | 1,4 | inspeção |
| `REPET_PAGINA` | 3 | inspeção |
| `MAX_RECORRENTE` | 150 | inspeção |
| corte de repetição | 5 | derivado do conjunto rotulado |

Os cinco primeiros foram fixados por inspeção e **não foram validados**; constituem
limitação declarada. O sexto obedece a regra reproduzível e verificável.

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
