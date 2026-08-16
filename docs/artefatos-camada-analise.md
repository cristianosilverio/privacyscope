# Artefatos da camada de análise — determinação

Documento de contrato. Fixa o que precisa existir para que as quatro variáveis
modeladas por classificação supervisionada — canal do titular, finalidade
especificada, direitos do titular explicados e transferência internacional
divulgada — sejam executáveis pelo arcabouço, e não apenas pelos programas de
análise.

Estado em 11/08/2026: **nenhuma delas tem caminho de inferência.** O registro de
plugins tem três testes, todos por regra, e o `canal_titular` registrado é o
detector determinístico que os resultados reportam como linha de base, não o
classificador. Os modelos existem como programas em `scripts/` e como CSV de
coeficientes; não há modelo serializado no repositório.

---

## 1. Princípio que governa esta camada

A arquitetura declara que o conhecimento de domínio sujeito a refinamento
empírico — vocabulários, limiares e listas de exclusão — reside em configuração
apartada do código, o que viabiliza **ajuste auditável sem alterar a lógica**.

**Esse princípio não se transfere ao artefato de modelo.** Um vocabulário de
TF-IDF é um vocabulário e um limiar é um limiar, mas nenhum dos dois é ajustável
à mão: editar o vocabulário sem reajustar os coeficientes rompe o pareamento
entre eles e produz predição plausível e errada, que nenhuma verificação a
jusante acusa.

O artefato de modelo é, portanto, classe distinta de objeto externalizado:

| propriedade | configuração de regra | artefato de modelo |
|---|---|---|
| externalizado | sim | sim |
| versionado | sim | sim |
| editável por humano | **sim**, é o propósito | **não**, substituído como unidade |
| granularidade da troca | parâmetro | arquivo inteiro |
| identidade | conteúdo do YAML | resumo criptográfico próprio |

## 2. Estado que o plugin carrega

O plugin **não carrega o conjunto de treino**, e carrega estado fechado: o
vocabulário, os pesos documentais e os coeficientes, todos derivados dele.

A distinção não é entre com e sem estado, e sim entre estado **fechado** —
aprendido uma vez, imutável na inferência — e estado **aberto**, que consultaria
o conjunto a cada execução. Apenas o segundo se tornou dispensável, com a
substituição do filtro de repetição por deduplicação intra-sítio: era o contador
entre sítios que exigia conjunto de referência.

Não carregar o corpo elimina uma classe inteira de dependência oculta, em que o
resultado de um sítio varia conforme os demais sítios da execução — defeito que
o contador entre sítios de fato produzia, e que foi medido.

**O artefato carrega, em lugar do corpo:**

- o **resumo criptográfico do conjunto de treino** e a **versão do preparo de
  texto** que o produziram, de sorte que a proveniência sobreviva sem a fonte
- **estatísticas de cobertura de vocabulário**, para que a extrapolação seja
  detectável: documento cujos termos estejam muito abaixo da cobertura típica
  recebe marca no `audit_trail`, porque a predição ali é extrapolação e não
  interpolação

## 3. Contrato de saída

Fixado após exame das alternativas. A classificação é e permanece **em nível de
sentença**; o que segue é o contrato da camada de saída, a jusante dela.

```
value          bool     ao menos uma sentença sinalizada
confidence     float    maior probabilidade entre as sentenças sinalizadas
audit_trail    n_sentencas_sinalizadas   contagem
               n_segmentos_avaliados     denominador, sem o qual não há normalização
               limiar                    valor empregado
               sentencas[:N]             texto, escore e posição, N declarado
               modelo_sha256             identidade do artefato
               preparo_versao            versão do pipeline de texto
               cobertura_vocabulario     fração de termos vistos no treino
```

Quatro razões fixaram esse desenho, e a primeira reverteu a proposta inicial de
pôr a contagem em `value`:

**Tipo declarado.** As variáveis são binárias no protocolo, e a leitura binária
é a agregação trivial da contagem — ao menos uma sentença sinalizada. Pôr a
contagem em `value` contrariaria a declaração sem acrescentar informação, uma vez
que ela permanece disponível no `audit_trail`.

**Confiança definível.** Com saída binária, a confiança é a maior probabilidade
entre as sinalizadas. Com contagem, seria preciso inventar regra para caber no
campo.

**Comparabilidade.** Contagem bruta não é comparável entre sítios: política de
três mil segmentos e outra de cem, ambas com cinco sentenças sinalizadas, não
dizem a mesma coisa. O denominador vai no `audit_trail` para que a normalização
seja possível a jusante.

**Tamanho.** Sessenta sentenças por variável, três variáveis, texto integral e
tudo sob resumo criptográfico inviabilizariam o armazenamento. O teto N é
declarado e a contagem total registrada à parte.

O arcabouço não arbitra o que cinco sentenças significam em lugar de uma. Ele
relata, e a decisão fica com quem consome — o que preserva a separação entre
evidência técnica observável e juízo de conformidade.

## 4. Formato de serialização

**NPZ com metadados em JSON, e nunca `pickle` ou `joblib`.**

A serialização por `pickle` amarra o artefato à versão da biblioteca que o
gravou, executa código arbitrário na leitura e não é inspecionável. Nenhuma das
três propriedades é aceitável em artefato que precisa ser conferido por terceiro
e sobreviver a atualização de dependência. O `.gitignore` já recusa `*.pkl` e
`*.joblib` em `outputs/`, e esta determinação estende a recusa ao artefato de
modelo.

Conteúdo, em arquivo único:

- coeficientes e intercepto, como vetores numéricos
- vocabulário e pesos documentais do TF-IDF
- limiar de decisão
- versão do preparo de texto e parâmetros congelados que o governam
- resumo criptográfico do conjunto de treino
- estatísticas de cobertura de vocabulário
- data de ajuste e identificação do programa que o produziu

O resumo criptográfico do artefato é calculado sobre os bytes canônicos do
arquivo e registrado no `audit_trail` de todo resultado que ele produzir.

## 5. Artefatos a construir, em ordem de dependência

| # | artefato | depende de | observação |
|---|---|---|---|
| 1 | `privacyscope/text/segmentacao.py` | — | **CONCLUÍDO em 11/08/2026.** As seis etapas migradas de programa para biblioteca; equivalência provada por resumo criptográfico idêntico antes e depois, em dois ambientes |
| 2 | `privacyscope/models/artefato.py` | 1 | gravação, leitura e conferência do artefato |
| 3 | `scripts/exportar_modelo_textuais.py` | 2 | produz o artefato a partir do ajuste |
| 4 | `privacyscope/tests/ml_texto.py` | 1, 2 | uma classe parametrizada, três variáveis |
| 5 | `scripts/exportar_modelo_canal.py` | 2 | artefato do estimador de Firth |
| 6 | `privacyscope/tests/canal_titular_ml.py` | 2 | **acrescenta**, não substitui o detector por regra |
| 7 | `privacyscope/tests/bertimbau.py` | 1, 2 | teto comparativo, não habilitado por omissão |
| 8 | `config/protocol.yaml` | 4, 6, 7 | declaração das variáveis e dos artefatos |

O item 1 é pré-requisito de tudo e é o de maior esforço. Hoje a segmentação vive
em `scripts/segmentar_politicas.py`, com leitura de argumentos, de planilha de
rotulagem e de pacotes congelados — nada disso pertence a um caminho de
inferência. **A migração inverte a dependência:** a biblioteca passa a conter o
procedimento, e o programa de segmentação passa a importá-la. Sem essa inversão,
treino e produção executam código distinto para a mesma finalidade, que é
exatamente a divergência que o contrato do preparo de texto proíbe.

O item 6 acrescenta um plugin e preserva o existente. Os resultados reportam os
dois regimes para a mesma variável, e o arcabouço tem de poder executar ambos,
sob declaração no protocolo.

## 6. Pendências de protocolo — resolvidas

Esta seção registrava três pendências. Todas foram fechadas; ficam aqui com o
desfecho, porque a decisão importa mais que a pendência.

**Variáveis declaradas sem plugin registrado.** `config/protocol.yaml` declarava
`cookies_set`, `categoria_cookies` e `menciona_lgpd`, nenhuma delas registrada, e
a execução interrompia com erro de resolução. `menciona_lgpd` era resíduo de
desenho anterior e saiu. `cookies_set` e `categoria_cookies` foram para **trabalho
futuro** (decidido em 11/08/2026): não integram a bateria de seis variáveis
técnicas nem figuram nos resultados, e são extensões que a arquitetura comporta
pelo mesmo mecanismo de plugin, sem refatoração das camadas. O protocolo em vigor
é `protocols/padrao.yaml`, que declara as seis variáveis efetivamente registradas.

`config/protocol.yaml` permanece no repositório, marcado no cabeçalho como esquema
obsoleto e não executável — registro da migração, e não configuração ativa.
`scripts/verificar_item.py` afere a presença desse aviso.

**Nomenclatura anunciada e nunca escrita.** O docstring de `VariableTest` e a
seção 4.4 de `docs/arquitetura.md` anunciavam `StructuralTest`, `LexiconTest`,
`MLClassifierTest` e `CookieAnalyzer`, nenhuma das quatro existente. Os nomes
foram substituídos pelas classes registradas, e um teste
(`tests_unit/test_protocolos.py`) passou a recusar que o documento cite classe
ausente do registro — de sorte que a divergência não se reinstale em silêncio.
