# -*- coding: utf-8 -*-
"""
Constrói o documento Resultados Preliminares V2 a partir do template oficial.

V2 (19/05/2026): pós-implementação do MVP (B3 concluído).
Mudanças relativas ao V1:
  - Verbos no passado em Implementação
  - URL do GitHub publico no texto
  - Subseção "Composicao de plugins via registry"
  - Tabela 1 atualizada (cookies_set agora reflete cookies_by_phase)
  - Resultados: subsecao "Validacao empirica" + Tabela 2 com smoke C3
  - Cronograma atualizado nas Consideracoes Finais

Preserva: cabecalho USP/ESALQ, paginacao, margens, header fix automatico.
"""
import shutil
from copy import deepcopy
from docx import Document
from docx.shared import Pt, Cm, Mm, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

TEMPLATE = "/sessions/peaceful-lucid-edison/mnt/TCC/Estrutura do TCC/Template Resultados Preliminares_PT (251, 252).docx"
OUTPUT   = "/sessions/peaceful-lucid-edison/mnt/TCC/Resultados Preliminares - Cristiano Gouveia Silverio - V2.docx"
FIG1     = "/sessions/peaceful-lucid-edison/mnt/TCC/PrivacyScope/docs/figuras/figura1_arquitetura.png"

shutil.copy(TEMPLATE, OUTPUT)
doc = Document(OUTPUT)

# --- Limpa o corpo, preserva sectPr (margens, cabeçalho, paginação) ---
body = doc.element.body
sectPr = None
for el in list(body):
    if el.tag == qn("w:sectPr"):
        sectPr = el
        continue
    body.remove(el)

# Helpers --------------------------------------------------------------
def _set_run(r, *, bold=False, italic=False, size=11, font="Arial", color=None):
    r.font.name = font
    r.font.size = Pt(size)
    r.bold = bold
    r.italic = italic
    if color:
        r.font.color.rgb = RGBColor(*color)
    # Garante fallback em runs com caracteres não-latin
    rPr = r._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rFonts.set(qn(attr), font)

def p(text, *, bold=False, italic=False, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
      indent_first=True, line_spacing=1.5, space_after=0, size=11,
      space_before=0, keep_with_next=False):
    para = doc.add_paragraph()
    pf = para.paragraph_format
    para.alignment = align
    pf.line_spacing = line_spacing
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    if indent_first:
        pf.first_line_indent = Cm(1.25)
    if keep_with_next:
        pf.keep_with_next = True
    if text:
        r = para.add_run(text)
        _set_run(r, bold=bold, italic=italic, size=size)
    return para

def heading(text):
    """Seção: Arial 11, negrito, alinhado à esquerda, sem indent, espaço antes/depois."""
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf = para.paragraph_format
    pf.line_spacing = 1.5
    pf.space_before = Pt(12)
    pf.space_after  = Pt(6)
    pf.keep_with_next = True
    r = para.add_run(text)
    _set_run(r, bold=True, size=11)
    return para

def subheading(text):
    """Subseção: Arial 11, negrito, recuo de 1,25 cm na primeira linha."""
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf = para.paragraph_format
    pf.line_spacing = 1.5
    pf.space_before = Pt(8)
    pf.space_after  = Pt(2)
    pf.first_line_indent = Cm(1.25)
    pf.keep_with_next = True
    r = para.add_run(text)
    _set_run(r, bold=True, size=11)
    return para

def blank_line(size=11):
    para = doc.add_paragraph()
    para.paragraph_format.line_spacing = 1.0
    para.paragraph_format.space_after = Pt(0)
    r = para.add_run("")
    _set_run(r, size=size)

def caption(text, *, before=4, after=4):
    para = doc.add_paragraph()
    pf = para.paragraph_format
    para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf.line_spacing = 1.0
    pf.space_before = Pt(before)
    pf.space_after  = Pt(after)
    r = para.add_run(text)
    _set_run(r, size=11)
    return para

# ---------------------- FOLHA DE ROSTO --------------------------------
# Título (negrito, centralizado, fonte 11, sem indent)
para = doc.add_paragraph()
para.alignment = WD_ALIGN_PARAGRAPH.CENTER
para.paragraph_format.line_spacing = 1.0
para.paragraph_format.space_before = Pt(6)
para.paragraph_format.space_after  = Pt(0)
r = para.add_run("Apoio à Etapa de Monitoramento no Processo Fiscalizatório da ANPD: abordagem baseada em webscraping e machine learning")
_set_run(r, bold=True, size=11)

# Dois espaços de caractere → linhas em branco
blank_line()
blank_line()

# Autores
para = doc.add_paragraph()
para.alignment = WD_ALIGN_PARAGRAPH.CENTER
para.paragraph_format.line_spacing = 1.0
para.paragraph_format.space_after  = Pt(0)
r1 = para.add_run("Cristiano Gouveia Silverio")
_set_run(r1, size=11)
r2 = para.add_run("¹*")
_set_run(r2, size=11)
r3 = para.add_run("; Prof. Me. Denis Bruno Viríssimo")
_set_run(r3, size=11)
r4 = para.add_run("²")
_set_run(r4, size=11)

blank_line()

# Endereços (Arial 9, justificado à esquerda)
def addr(text):
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf = para.paragraph_format
    pf.line_spacing = 1.0
    pf.space_after = Pt(0)
    r = para.add_run(text)
    _set_run(r, size=9)
    return para

addr("¹* Especializando em MBA em Data Science e Analytics. LGPD2U. E-mail autor correspondente: cristiano.silverio@lgpd2u.com.br")
addr("² Mestre em Engenharia de Computação. Instituto de Pesquisas Tecnológicas do Estado de São Paulo. E-mail: dbvirissimo@ipt.br")

# Salto de página para começar conteúdo
para = doc.add_paragraph()
r = para.add_run()
br = OxmlElement("w:br")
br.set(qn("w:type"), "page")
r._element.append(br)

# ---------------------- TÍTULO + RESUMO -------------------------------
para = doc.add_paragraph()
para.alignment = WD_ALIGN_PARAGRAPH.CENTER
para.paragraph_format.space_after = Pt(6)
para.paragraph_format.line_spacing = 1.0
r = para.add_run("Apoio à Etapa de Monitoramento no Processo Fiscalizatório da ANPD: abordagem baseada em webscraping e machine learning")
_set_run(r, bold=True, size=11)

# Resumo (heading)
para = doc.add_paragraph()
para.alignment = WD_ALIGN_PARAGRAPH.LEFT
para.paragraph_format.space_before = Pt(8)
para.paragraph_format.space_after  = Pt(4)
para.paragraph_format.line_spacing = 1.0
r = para.add_run("Resumo")
_set_run(r, bold=True, size=11)

# Texto do resumo: parágrafo único, espaçamento simples, justificado, sem recuo, max 250 palavras
resumo = ("A consolidação de marcos legais de proteção de dados pessoais, como a Lei nº 13.709/2018 e a Lei nº 15.352/2026, "
"ampliou as atribuições fiscalizatórias da Autoridade Nacional de Proteção de Dados (ANPD), entre as quais se destaca a etapa "
"de Monitoramento prevista na Resolução CD/ANPD nº 1/2021. Essa etapa requer a coleta sistemática de evidências observáveis em "
"larga escala, atividade incompatível com inspeção manual exaustiva. O presente trabalho propôs o desenvolvimento de um framework "
"computacional parametrizável, denominado PrivacyScope, baseado em técnicas de webscraping e aprendizado de máquina, destinado a "
"operacionalizar parâmetros observáveis de transparência em websites institucionais brasileiros. A pesquisa caracterizou-se como "
"aplicada, descritiva, com abordagem mista e delineamento de Implementação de Algoritmo de Machine Learning. A arquitetura foi "
"estruturada em seis camadas desacopladas (Ingestão, Coleta, Evidência Bruta, Análise, Resultados Estruturados e Saída), governadas "
"por protocolo declarativo versionado, com cadeia de custódia das evidências brutas via empacotamento e hash criptográfico, em "
"aderência à ABNT NBR ISO/IEC 27037:2013. A amostragem adotou a Tranco List filtrada pelo TLD .br como fonte única, em desenho "
"estratificado por sufixo de domínio. Foi definida bateria inicial de seis variáveis técnicas — quatro detectadas por regras "
"determinísticas e duas por classificação supervisionada. Os resultados parciais consolidaram a arquitetura, a especificação "
"operacional das variáveis e o pipeline em fase de validação. O framework mostrou-se compatível, em concepção, com as finalidades "
"informacionais da etapa de Monitoramento, preservando a distinção entre evidência técnica observável e juízo jurídico de conformidade.")
para = doc.add_paragraph()
para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
para.paragraph_format.line_spacing = 1.0
para.paragraph_format.space_after = Pt(8)
para.paragraph_format.first_line_indent = Cm(0)
r = para.add_run(resumo)
_set_run(r, size=11)

# Palavras-chave
para = doc.add_paragraph()
para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
para.paragraph_format.line_spacing = 1.0
para.paragraph_format.space_after = Pt(12)
r1 = para.add_run("Palavras-chave: ")
_set_run(r1, bold=True, size=11)
r2 = para.add_run("monitoramento regulatório; proteção de dados pessoais; coleta automatizada de dados; transparência digital; evidências observáveis.")
_set_run(r2, size=11)

# ---------------------- CONSIDERAÇÕES INICIAIS ------------------------
heading("Considerações Iniciais")

p("A intensificação da digitalização das atividades econômicas e sociais ampliou a coleta, o processamento e a circulação de dados "
"pessoais, tornando a proteção desses dados tema central das agendas regulatórias contemporâneas. No Brasil, a Lei nº 13.709/2018 "
"(Lei Geral de Proteção de Dados Pessoais — LGPD) estabeleceu princípios, direitos e deveres voltados à garantia da privacidade dos "
"dados pessoais e instituiu a Autoridade Nacional de Proteção de Dados (ANPD) como órgão competente para regular, fiscalizar e "
"aplicar sanções administrativas (BRASIL, 2018). Posteriormente, a Lei nº 15.352/2026 transformou a ANPD em autarquia especial "
"vinculada ao Ministério da Justiça e Segurança Pública, dotada de autonomia técnica, decisória, administrativa e financeira "
"(BRASIL, 2026). Em escala global, mais de 160 países instituíram legislações próprias de proteção de dados, frequentemente "
"fundamentadas em diretrizes internacionais como as recomendações da OECD (OECD, 2013; JAVED; SAJID, 2024).")

p("No exercício de suas atribuições, a ANPD aprovou, por meio da Resolução CD/ANPD nº 1/2021, o Regulamento do Processo de "
"Fiscalização, que organiza as atividades fiscalizatórias em diferentes instrumentos e etapas operacionais (BRASIL, 2021). Entre "
"essas etapas, destaca-se a fase de Monitoramento, destinada à coleta sistemática de informações, análise de evidências e "
"identificação de indícios relacionados ao tratamento de dados pessoais. A etapa possui caráter informacional e exploratório, "
"orientada à produção de conhecimento sobre práticas de tratamento, identificação de padrões de comportamento regulatório e "
"levantamento de evidências que possam subsidiar decisões futuras da autoridade. Diferentemente das etapas sancionatórias, o "
"monitoramento não tem por finalidade a aplicação de penalidades ou a caracterização formal de infrações, mas sim o apoio à "
"formulação de estratégias regulatórias e ao planejamento das ações de fiscalização (AGÊNCIA NACIONAL DE PROTEÇÃO DE DADOS, 2026).")

p("Observa-se crescente interesse acadêmico e institucional no uso de tecnologias computacionais para apoiar atividades de "
"supervisão regulatória baseadas em dados, frequentemente associadas à abordagem de regulação baseada em evidências, diante da "
"necessidade de fortalecimento das capacidades analíticas do Estado para lidar com problemas complexos de governança (LODGE; "
"WEGRICH, 2014). Métodos de coleta automatizada de informações na web (webscraping e web crawling), combinados a técnicas de "
"análise textual e estrutural, têm sido explorados para produção de evidências empíricas sobre comportamento organizacional em "
"ambientes digitais. Pesquisas recentes investigam classificação automatizada de políticas de privacidade (JAVED; SAJID, 2024; "
"MORI et al., 2023; VORSTER; DA VEIGA, 2023), análise de mecanismos técnicos como cookies e rastreadores (HORMOZI, 2006; "
"DABROWSKI et al., 2019; RASAII et al., 2023; VU; HOANG; LE, 2023) e priorização de fatores críticos de conformidade (KOLEY; "
"BHARATHI, 2021), demonstrando o potencial dessas abordagens para examinar padrões de transparência informacional em larga escala.")

p("Apesar dos avanços técnicos, são escassos os estudos que investigam a aplicação sistemática dessas técnicas no contexto específico "
"da supervisão regulatória em proteção de dados pessoais, particularmente em relação ao apoio à etapa de Monitoramento prevista nos "
"processos fiscalizatórios brasileiros. Identifica-se, assim, a oportunidade de investigar como abordagens computacionais baseadas "
"em coleta automatizada e análise de conteúdo digital podem contribuir para a produção estruturada de informações observáveis em "
"ambientes digitais públicos, sem substituir o julgamento jurídico ou a análise regulatória realizada pelas autoridades competentes. "
"A delimitação adotada concentra-se exclusivamente no desenvolvimento de ferramental técnico potencialmente aplicável à fase "
"informacional do processo, não abrangendo classificação de infrações, dosimetria de sanções ou avaliação de impacto decisório "
"(BRASIL, 2023).")

p("Diante desse contexto, o objetivo deste trabalho é desenvolver e avaliar um framework computacional parametrizável, denominado "
"PrivacyScope, baseado em técnicas de webscraping e métodos de aprendizado de máquina, capaz de operacionalizar parâmetros "
"observáveis de transparência em websites institucionais brasileiros, produzindo indicadores descritivos auditáveis e reprodutíveis "
"que possam subsidiar a etapa de Monitoramento prevista na Resolução CD/ANPD nº 1/2021. A finalidade técnica do algoritmo "
"enquadra-se nas categorias supervised (modelos de classificação textual sobre políticas de privacidade e categorização de cookies) "
"e web crawlers development (coleta estruturada de evidências digitais), com ênfase em auditabilidade, reprodutibilidade e "
"extensibilidade. As limitações estruturais do método — natureza estritamente técnico-descritiva e impossibilidade de inferir "
"práticas internas de tratamento de dados não observáveis publicamente — são tratadas nas seções subsequentes.")

# ---------------------- IMPLEMENTAÇÃO DE ALGORITMO ---------------------
heading("Implementação de Algoritmo(s) de Machine Learning")

p("Esta pesquisa caracteriza-se, quanto aos objetivos, como aplicada e descritiva, com abordagem metodológica mista, combinando "
"análise quantitativa (proporções, distribuições e métricas de desempenho) com análise qualitativa (interpretação de divergências "
"entre detecção automatizada e avaliação manual de referência). O delineamento adotado é Implementação de Algoritmo(s) de Machine "
"Learning, modalidade prevista no Manual de Instruções e Normas dos cursos de MBA em Data Science e Analytics e Engenharia de "
"Software da USP/Esalq, e a técnica de obtenção de dados é o Levantamento de Dados Secundários, executado sobre conteúdos "
"publicamente disponíveis em websites institucionais brasileiros. Não há interação direta com pessoas naturais nem coleta de dados "
"pessoais privados, o que enquadra o estudo nas hipóteses de dispensa de análise pelo Comitê de Ética em Pesquisa previstas na "
"Resolução CNS nº 510/2016, incisos II e III do parágrafo único do artigo 1º.")

subheading("Arquitetura do framework PrivacyScope")

p("A arquitetura do framework PrivacyScope foi concebida em camadas desacopladas, comunicando-se exclusivamente por interfaces "
"abstratas, em aderência aos princípios de inversão de dependência e aberto-fechado descritos por Martin (2000), e ao desenho de "
"sistemas de aprendizado de máquina com configuração externalizada e separação rígida entre coleta, processamento e modelagem "
"proposto por Sculley et al. (2015). A estrutura é apresentada na Figura 1.")

# Inserir Figura 1
para = doc.add_paragraph()
para.alignment = WD_ALIGN_PARAGRAPH.CENTER
para.paragraph_format.space_before = Pt(6)
para.paragraph_format.space_after  = Pt(2)
para.paragraph_format.line_spacing = 1.0
r = para.add_run()
r.add_picture(FIG1, width=Cm(15.5))

# Legenda da figura (Arial 11, espaçamento 1, sem indent)
caption("Figura 1. Arquitetura em camadas do framework PrivacyScope", before=2, after=0)
caption("Fonte: Elaborada pelo autor", before=0, after=8)

p("A Figura 1 apresenta o desenho em seis camadas funcionais, governadas por um protocolo declarativo em formato YAML, versionado e "
"auditável por hash criptográfico. As camadas são: (1) Ingestão, responsável por gerar a lista de domínios a partir de fontes "
"amostrais plugáveis; (2) Coleta, que executa o webscraping/webcrawling e produz evidências brutas (HTML, cookies, headers e "
"capturas de tela); (3) Evidência Bruta, repositório imutável (append-only) que empacota e assina criptograficamente cada conjunto "
"de evidências; (4) Análise, que aplica testes parametrizáveis às evidências e gera resultados estruturados; (5) Resultados "
"Estruturados, persistência tabular em formato longo (long-format); e (6) Saída, que renderiza os resultados em formatos "
"consumíveis. O orquestrador resolve plugins, paraleliza execuções e registra trilha de auditoria. Cada caixa do diagrama "
"representa uma interface formal — plugins específicos podem ser substituídos ou adicionados sem alteração das demais camadas, "
"atendendo ao requisito de extensibilidade definido no projeto. A formalização desses contratos em classes abstratas (Abstract "
"Base Classes em Python) e a externalização das configurações em arquivo YAML versionado seguem boas práticas de reprodutibilidade "
"computacional consolidadas por Wilson et al. (2017).")

p("A implementação do framework foi concluída na primeira fase do cronograma e disponibilizada em repositório público no GitHub, "
"no endereço https://github.com/cristianosilverio/privacyscope, em conformidade com os princípios FAIR (Findable, Accessible, "
"Interoperable, Reusable) propostos por Wilson et al. (2017). A versão de referência deste documento corresponde aos commits "
"sequenciais que materializam as camadas da arquitetura, incluindo a refatoração para representação dinâmica de fases de coleta "
"de cookies, conforme detalhado na Tabela 1. A execução completa do pipeline é invocada por interface de linha de comando "
"(``privacyscope run protocol.yaml``), recebendo como único parâmetro o caminho do protocolo declarativo em formato YAML, cujo "
"hash criptográfico SHA-256 é registrado na trilha de auditoria de cada evidência produzida — garantindo rastreabilidade entre "
"parâmetros de execução e resultados.")

subheading("Composição de plugins via registry")

p("A resolução de plugins é centralizada em um registry declarativo (``core/plugin_registry.py``), que mapeia o nome textual "
"referenciado no protocolo YAML à classe concreta que implementa a interface correspondente. O registry separa explicitamente "
"plugins por camada (fontes amostrais, fetchers, repositórios, result stores, testes de variáveis e renderizadores de saída), "
"impedindo que um plugin destinado a uma camada seja inadvertidamente resolvido como pertencente a outra. A adição de uma "
"nova variável técnica, fonte amostral ou estratégia de coleta exige duas ações apenas: (i) a criação do arquivo Python que "
"implementa a interface abstrata da camada apropriada, e (ii) o registro do nome desse plugin no dicionário correspondente. "
"Nenhuma alteração nas demais camadas, no orquestrador ou na linha de comando é necessária, em estrita aderência ao princípio "
"aberto-fechado (Martin, 2000). Essa propriedade é central para a defensibilidade do desenho frente a refinamentos pós-piloto, "
"nos quais variáveis adicionais ou critérios mais restritos podem ser incorporados sem refatoração do núcleo do sistema.")

p("A cadeia de coleta é particularizada por um plugin específico — ``FallbackChain`` — que implementa o padrão Chain of Responsibility, "
"orquestrando uma sequência ordenada de fetchers e definindo declarativamente as condições de escalonamento entre eles, expressas no "
"protocolo YAML como sinais qualitativos sobre a evidência produzida. Esse desenho permite que um fetcher mais leve (HttpFetcher, "
"baseado em ``httpx`` e ``BeautifulSoup``) seja experimentado primeiro, escalando para um fetcher mais oneroso (PlaywrightFetcher, "
"com renderização JavaScript completa via Chromium em modo headless) somente quando o resultado do anterior apresenta sinais de "
"insuficiência. Cinco sinais foram operacionalizados: ``html_root_smaller_than_bytes`` (página suspeitamente pequena, típica de "
"shell SPA), ``subpage_selection_empty`` (nenhuma subpágina relevante detectada), ``cookies_pre_consent_zero`` (fetcher não captou "
"cookies em fase pré-consent), ``consent_actions_all_failed`` (todas as tentativas de interação com banner falharam) e "
"``has_js_shell_markers`` (HTML contém marcadores típicos de página dependente de JavaScript). Cada decisão de escalonamento é "
"registrada cronologicamente na trilha de auditoria da evidência, permitindo reconstrução completa do histórico de tentativas.")

subheading("Dataset: universo amostral e amostragem")

p("O universo amostral é constituído por domínios ativos sob o TLD .br, restritos a websites institucionais empresariais e "
"governamentais. A composição da amostra adota como fonte primária a Tranco List (LE POCHAT et al., 2019), uma listagem ranqueada e "
"reprodutível de domínios construída sobre múltiplas fontes (Cisco Umbrella, Cloudflare Radar, Majestic e Farsight), com "
"versionamento mensal e identificação por hash, amplamente utilizada em pesquisa de privacidade web por sua resistência a "
"manipulação e por seu uso em estudos revisados por pares. A versão de maio de 2026 foi filtrada para o TLD .br, gerando o quadro "
"amostral. Adotou-se a Tranco List como fonte única: o estrato governamental é obtido pelo subconjunto de domínios com sufixo "
"``.gov.br`` presente na própria lista, percorrendo-se o ranqueamento em profundidade até alcançar o número de unidades "
"governamentais necessário. Optou-se por não complementar com listagens externas a fim de preservar a homogeneidade da fonte e "
"evitar viés de amostragem diferencial entre os estratos — ambos derivam do mesmo critério de popularidade ranqueada e auditável. "
"A escolha pela Tranco decorre da indisponibilidade da fonte originalmente prevista no projeto — listagem institucional do "
"NIC.br — cuja solicitação formal não foi atendida. O desenho adotado preserva os requisitos de neutralidade setorial e "
"reprodutibilidade metodológica.")

p("A amostragem é estratificada em dois estratos definidos pelo sufixo do domínio: governamental (``.gov.br``) e empresarial "
"(demais domínios sob o TLD .br). O tamanho-alvo da amostra final foi dimensionado pela fórmula clássica de estimação de "
"proporções para população infinita, considerando nível de confiança de 95%, margem de erro de 5% e estimativa conservadora "
"p̂ = 0,50, resultando em n ≈ 384 unidades. Para a coleta piloto reportada nesta etapa adotou-se n = 50, com alocação de 40 "
"unidades ao estrato empresarial e 10 ao estrato governamental, extraídas por amostragem aleatória simples dentro de cada "
"estrato a partir de semente fixa (para reprodutibilidade).")

p("Cumpre registrar, por transparência metodológica, que esta alocação não é proporcional ao peso populacional dos estratos. "
"O estrato governamental representa fração ínfima do universo de domínios .br, de modo que a alocação estritamente proporcional "
"resultaria em pouquíssimas unidades governamentais. Optou-se deliberadamente por sobre-representar o estrato governamental "
"relativamente ao seu peso populacional, com o objetivo de garantir cobertura analítica mínima desse estrato, dado seu interesse "
"central para a finalidade institucional do trabalho — o apoio à etapa de Monitoramento da Autoridade Nacional de Proteção de "
"Dados. Reconhece-se que estimativas globais ponderadas para o universo .br exigiriam reponderação das observações pelos pesos "
"reais de cada estrato. Reconhece-se igualmente que, com n = 10, o estrato governamental fornece cobertura exploratória, e não "
"estimativa pontual de precisão elevada para esse estrato isoladamente. A expansão para n ≈ 384 com reavaliação da alocação está "
"prevista para a etapa subsequente, conforme cronograma.")

subheading("Variáveis técnicas operacionalizadas")

p("As variáveis técnicas representam requisitos observáveis de transparência operacionalizados como regras computacionais formais. "
"A Tabela 1 apresenta a especificação inicial das seis variáveis configuradas no protocolo desta execução. Cada variável é "
"acompanhada de definição conceitual, regra computacional de detecção, critério de classificação e fundamentação normativa ou "
"acadêmica, em aderência ao requisito de auditabilidade da fase de Monitoramento.")

# Tabela 1
caption("Tabela 1. Variáveis técnicas operacionalizadas no protocolo v1.0.0 do framework PrivacyScope", before=4, after=2)

table = doc.add_table(rows=1, cols=5)
table.style = "Table Grid"
hdr = table.rows[0].cells
for i, txt in enumerate(["Variável", "Tipo", "Definição operacional", "Detecção", "Respaldo"]):
    hdr[i].text = ""
    par = hdr[i].paragraphs[0]
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.line_spacing = 1.0
    r = par.add_run(txt)
    _set_run(r, bold=True, size=10)

rows = [
    ("tem_banner_cookies", "binária",
     "presença de banner informativo sobre uso de cookies na página inicial",
     "seletor CSS + léxico (cookieconsent, OneTrust, gdpr-banner, OptanonAlert, etc.)",
     "LGPD art. 8º; Dabrowski et al. (2019); Rasaii et al. (2023)"),
    ("tem_politica_privacidade", "binária",
     "presença de link ou seção rotulado como política/aviso/termo de privacidade",
     "regex (política|aviso|termo).{0,20}(privacidade|dados) no DOM e atributo href",
     "LGPD art. 9º; Javed; Sajid (2024); Vorster; Da Veiga (2023)"),
    ("tem_canal_titular", "binária",
     "presença de canal de atendimento ao titular (e-mail, formulário ou link específico)",
     "regex de e-mail DPO/encarregado, padrão /encarregado, link \"fale conosco\" + termos de titular",
     "LGPD art. 41; Res. CD/ANPD 1/2021"),
    ("cookies_set", "composta",
     "inventário estruturado dos cookies fixados em fases distintas, representado por dicionário dinâmico ``cookies_by_phase: dict[str, list]`` com chaves de fase livres (\"single\" para fetchers single-shot; \"pre_consent\", \"post_consent\", \"post_revocation\" para o PlaywrightFetcher; outras chaves permitidas para futuros fetchers sem alteração do schema). Cada cookie é registrado com nome, domínio, expiração e flags (Secure, HttpOnly, SameSite). O valor de cada cookie é armazenado em forma mascarada (truncamento aos 8 primeiros caracteres + comprimento original + hash SHA-256 truncado a 16 caracteres), preservando comparabilidade entre fases sem reter identificadores. Métricas derivadas (total, terceiros, persistentes, percentual com Secure) são calculadas em pós-processamento",
     "inspeção de document.cookie e cabeçalhos Set-Cookie via navegador headless, em fases pré/pós-consent",
     "Hormozi (2006); Dabrowski et al. (2019); Rasaii et al. (2023)"),
    ("categoria_cookies", "categórica",
     "classificação por duração (sessão/persistente) e escopo (primária/terceiros)",
     "regras determinísticas sobre nome/atributos + classificador supervisionado para casos ambíguos",
     "Vu; Hoang; Le (2023); Pantelic et al. (2022)"),
    ("menciona_lgpd", "binária",
     "menção explícita à LGPD ou à Lei nº 13.709/2018 no texto da política de privacidade",
     "TF-IDF + Regressão Logística treinada em ground truth manual",
     "Mori et al. (2023); Javed; Sajid (2024)"),
]
for row in rows:
    cells = table.add_row().cells
    for i, txt in enumerate(row):
        cells[i].text = ""
        par = cells[i].paragraphs[0]
        par.alignment = WD_ALIGN_PARAGRAPH.LEFT if i != 1 else WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.line_spacing = 1.0
        r = par.add_run(txt)
        _set_run(r, size=10)

caption("Fonte: Elaborada pelo autor", before=2, after=10)

subheading("Cadeia de custódia das evidências")

p("A integridade das evidências coletadas é garantida por procedimento de cadeia de custódia inspirado na ABNT NBR ISO/IEC "
"27037:2013, que estabelece diretrizes para identificação, coleta, aquisição e preservação de evidência digital (ASSOCIAÇÃO "
"BRASILEIRA DE NORMAS TÉCNICAS, 2013; CASEY, 2011). Para cada site analisado, o conjunto bruto de evidências — HTML da página "
"principal e de páginas internas relevantes (política, termos, encarregado), cookies fixados, cabeçalhos HTTP de cada requisição, "
"captura de tela completa e metadados de execução — é serializado e empacotado em arquivo tar.gz. Um hash criptográfico SHA-256 do "
"pacote é calculado e registrado em manifest.jsonl assinado, cujo próprio hash é gravado no log de auditoria. Qualquer adulteração "
"posterior é detectável pela recomputação dos hashes em cascata. O repositório de evidências brutas opera em modo append-only, o "
"que assegura imutabilidade e permite que múltiplas execuções analíticas sob protocolos diferentes sejam aplicadas sobre o mesmo "
"conjunto preservado, atendendo aos requisitos de consistência e reprodutibilidade do projeto.")

subheading("Pipeline de coleta")

p("O pipeline de coleta é implementado em Python (versão 3.11), com paralelismo assíncrono (asyncio) e cadeia de fallback. A "
"primeira tentativa de coleta é realizada por meio do componente HttpFetcher, baseado nas bibliotecas httpx e BeautifulSoup, "
"adequado para páginas com conteúdo estático servido via HTML. Páginas que dependem de renderização por JavaScript ou que somente "
"fixam cookies após interação são processadas pelo PlaywrightFetcher, que opera uma instância de navegador Chromium em modo "
"headless, com processo isolado por coleta para garantir ausência de vazamento de estado entre sites. Em todas as coletas, "
"são respeitadas as boas práticas técnicas: controle de frequência de requisições, identificação adequada do agente de coleta no "
"cabeçalho User-Agent, observância às restrições explicitamente sinalizadas pelo robots.txt do domínio e limitação estrita a "
"conteúdos publicamente disponibilizados (BRASIL, 2018, art. 7º, §4º; OWASP, n.d.). Falhas operacionais (timeouts, certificados "
"inválidos, redirecionamentos abusivos) são registradas no log de execução e analisadas qualitativamente.")

p("O tratamento do arquivo robots.txt segue o Robots Exclusion Protocol formalizado na RFC 9309 (KOSTER et al., 2022). Quando o "
"robots.txt é servido com status HTTP 200, suas diretivas são integralmente respeitadas, e domínios que proíbam a coleta para o "
"agente de pesquisa são excluídos da amostra efetiva, com o evento registrado na trilha de auditoria. Para respostas de erro, "
"adota-se a recomendação da seção 2.3.1.4 da RFC: erros da classe 5xx (servidor incapaz de servir as regras) são interpretados "
"conservadoramente como proibição total de coleta, ao passo que erros da classe 4xx — incluindo 401 e 403 — são interpretados "
"como ausência de restrições aplicáveis. Esta última decisão, revista após observação empírica no pré-piloto, decorre de que "
"respostas 403 ao robots.txt frequentemente originam-se de proteções anti-bot genéricas a montante (firewalls de aplicação web) "
"e não de diretivas de exclusão dirigidas a coletores, de modo que o tratamento estritamente conservador excluiria indevidamente "
"sites cujo conteúdo é público e cuja página inicial responde normalmente.")

p("A camada FallbackChain orquestra o encadeamento dos fetchers com escalonamento baseado em sinais auditáveis. Para cada fetcher "
"na cadeia, o protocolo declara explicitamente as condições que disparam escalonamento ao próximo — tanto por classes de exceção "
"(``NavigationFailedError``, ``JsRequiredError``) quanto por sinais qualitativos sobre a evidência produzida. Cinco sinais foram "
"operacionalizados nesta versão: ``html_root_smaller_than_bytes`` (página suspeitamente pequena, típica de shell SPA), "
"``subpage_selection_empty`` (nenhuma subpágina relevante detectada), ``cookies_pre_consent_zero`` (fetcher não captou cookies em "
"fase pré-consent), ``consent_actions_all_failed`` (todas as tentativas de interação com banner falharam) e ``has_js_shell_markers`` "
"(HTML contém marcadores típicos de página dependente de JavaScript). Cada decisão de escalonamento é registrada cronologicamente "
"em ``RawEvidence.errors`` com prefixo ``chain.``, permitindo reconstrução completa do histórico de tentativas para qualquer "
"resultado. Condições do tipo abort_on (e.g., ``RobotsDisallowedError``) interrompem a cadeia sem escalonar, preservando ética da "
"coleta. Backoff exponencial entre tentativas e retries por fetcher são igualmente configuráveis no protocolo.")

p("Especificamente, o PlaywrightFetcher opera em fases distintas — captura de cookies antes da interação com qualquer banner de "
"consent e, em seguida, após aceitação automatizada do banner — em alinhamento à metodologia consolidada por Dabrowski et al. (2019) "
"e Rasaii et al. (2023). Essa diferenciação permite distinguir cookies estritamente necessários, ativados antes da manifestação do "
"titular, daqueles ativados condicionalmente após o consentimento, dimensão relevante para análise de aderência aos artigos 7º e 8º "
"da Lei nº 13.709/2018 e às orientações da ANPD sobre tratamento de dados via cookies. A detecção do banner de consent emprega "
"heurísticas configuráveis no protocolo, incluindo padrões léxicos, seletores CSS e, com prioridade, atributos de acessibilidade "
"ARIA (``aria-label``, ``role``, ``aria-modal``). A inclusão de ARIA como sinal primário decorre da exigibilidade de acessibilidade "
"digital em sites institucionais brasileiros, estabelecida pelo Decreto nº 5.296/2004, pela Lei nº 13.146/2015 (Lei Brasileira de "
"Inclusão) e operacionalizada pelo Modelo de Acessibilidade em Governo Eletrônico (BRASIL, 2004; BRASIL, 2015; eMAG, 2014). Em "
"sites tecnicamente acessíveis, atributos ARIA frequentemente carregam informação semântica mais explícita do que o texto visível "
"do elemento, aumentando a precisão da detecção automatizada de banners e elementos de navegação institucional.")

subheading("Pipeline de análise: regras formais e classificadores supervisionados")

p("O pipeline de análise opera em dois regimes complementares. O regime determinístico aplica regras formais — seletores CSS, "
"expressões regulares e padrões léxico-semânticos — para as variáveis de baixa ambiguidade (banner de cookies, política de "
"privacidade, canal do titular e inventário de cookies). O regime probabilístico, acionado seletivamente, aplica classificadores "
"supervisionados às variáveis textualmente complexas (categoria de cookies e menção à LGPD). O classificador-base é uma Regressão "
"Logística sobre representação TF-IDF do texto da política de privacidade ou dos atributos do cookie, treinada sobre subamostra "
"rotulada manualmente (ground truth). Para fins de comparação e análise de robustez, está prevista avaliação adicional com "
"embeddings contextuais do modelo BERTimbau, permitindo verificar ganhos marginais frente ao baseline TF-IDF. Cada execução de um "
"teste produz um VariableResult contendo o valor, um nível de confiança, um excerto evidencial e a versão do plugin acionado, "
"viabilizando a auditoria caso a caso.")

subheading("Métricas de validação")

p("A validação do desempenho do framework adota subamostragem probabilística da amostra principal, com tamanho dimensionado pela "
"mesma fórmula clássica de estimação de proporções (n = 50, IC 95%, margem de erro de 10%, p̂ = 0,5). Sobre essa subamostra, um "
"conjunto de referência (ground truth) é constituído por rotulagem manual seguindo os mesmos critérios formais definidos no "
"protocolo. As métricas de desempenho calculadas para cada variável incluem precisão, revocação, acurácia global e medida F1, "
"complementadas pelo coeficiente kappa de Cohen para avaliação de concordância entre detecção automatizada e avaliação manual. "
"Divergências são analisadas qualitativamente, separando ambiguidade textual genuína, limitação estrutural das regras de detecção "
"e necessidade de refinamento de parâmetros. A consistência interna do framework é avaliada por execução repetida sob protocolo "
"idêntico (esperando-se hash idêntico do conjunto de evidências brutas) e por análise de estabilidade frente à variação controlada "
"de parâmetros configuráveis.")

# ---------------------- RESULTADOS PRELIMINARES ------------------------
heading("Resultados Preliminares")

p("Os Resultados Preliminares consolidados até o fechamento desta versão compreendem três conjuntos de artefatos com graus distintos "
"de maturidade. O primeiro conjunto, de natureza estrutural, abrange a formalização arquitetural completa do framework PrivacyScope, "
"incluindo as interfaces abstratas das seis camadas, o protocolo declarativo YAML, o registry de plugins e a documentação técnica "
"versionada no repositório público (https://github.com/cristianosilverio/privacyscope). O segundo conjunto, de natureza operacional, "
"compreende a implementação concluída do MVP funcional do pipeline em linguagem Python, disponibilizado como pacote instalável e "
"acessível por interface de linha de comando, com testes de fumaça (smoke tests) executados em ambiente real e cadeia de custódia "
"das evidências validada por hash criptográfico em cascata. O terceiro conjunto, de natureza empírica preliminar, apresenta os "
"primeiros resultados quantitativos da aplicação do pipeline sobre sites institucionais brasileiros, ainda em escala reduzida.")

subheading("Validação empírica do pipeline (smoke C3, n = 5)")

p("Para validar a operação ponta-a-ponta do pipeline antes da execução da coleta piloto formal, foi conduzido um teste de fumaça em "
"cinco sites institucionais brasileiros, selecionados por diversidade vertical: dois portais governamentais de regulação e "
"administração geral (gov.br/anpd e gov.br), um portal governamental de tecnologia (serpro.gov.br), um portal comercial de mídia "
"(uol.com.br) e um portal comercial de comércio eletrônico (mercadolivre.com.br). A execução completa do pipeline, governada pelo "
"protocolo declarativo, produziu cinco pacotes de evidências brutas com hash SHA-256 registrado em manifest auditado em cascata, "
"e quinze observações estruturadas (cinco sites × três variáveis técnicas determinísticas), persistidas em banco SQLite no formato "
"longo. A Tabela 2 apresenta os resultados obtidos.")

caption("Tabela 2. Resultados do teste de fumaça do pipeline (n = 5 sites, três variáveis determinísticas)", before=4, after=2)

table2 = doc.add_table(rows=1, cols=5)
table2.style = "Table Grid"
hdr2 = table2.rows[0].cells
for i, txt in enumerate(["Site", "Banner de cookies", "Política de privacidade", "Canal do titular", "Sinal predominante (banner)"]):
    hdr2[i].text = ""
    par = hdr2[i].paragraphs[0]
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.line_spacing = 1.0
    r = par.add_run(txt)
    _set_run(r, bold=True, size=10)

smoke_rows = [
    ("gov.br/anpd",       "Sim (conf. 0,65)", "Sim (conf. 0,95)", "Sim (conf. 0,95)", "estrutural + léxico"),
    ("gov.br (raiz)",     "Sim (conf. 0,95)", "Sim (conf. 0,95)", "Não (conf. 0,95)", "estrutural + léxico"),
    ("serpro.gov.br",     "Sim (conf. 0,95)", "Sim (conf. 0,95)", "Não (conf. 0,95)", "estrutural + léxico"),
    ("uol.com.br",        "Sim (conf. 0,95)", "Não (conf. 0,95)", "Não (conf. 0,95)", "vendor (OneTrust)"),
    ("mercadolivre.com.br","Sim (conf. 0,95)","Não (conf. 0,95)", "Não (conf. 0,95)", "estrutural + léxico"),
]
for row in smoke_rows:
    cells = table2.add_row().cells
    for i, txt in enumerate(row):
        cells[i].text = ""
        par = cells[i].paragraphs[0]
        par.alignment = WD_ALIGN_PARAGRAPH.LEFT if i in (0, 4) else WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.line_spacing = 1.0
        r = par.add_run(txt)
        _set_run(r, size=10)

caption("Fonte: Elaborada pelo autor a partir da execução do PrivacyScope em 19 de maio de 2026", before=2, after=10)

p("Os resultados da Tabela 2 fornecem evidências qualitativas relevantes para a defensibilidade do pipeline. A detecção de banner "
"de cookies identificou corretamente a presença do mecanismo nos cinco sites, com nível de confiança máximo (0,95) em quatro deles, "
"e nível intermediário (0,65) no portal da ANPD em decorrência de falha operacional na tentativa automatizada de interação com o "
"banner — um caso explicitamente capturado pelo desenho do framework, que distingue \"banner detectado e interagível\" de \"banner "
"detectado e não interagível\" por meio da gradação do nível de confiança. A detecção do canal do titular foi positiva apenas no "
"portal da ANPD, único caso da amostra em que o endereço eletrônico institucional do encarregado de proteção de dados (\"encarregado@\") "
"foi identificado conjuntamente com uma subpágina dedicada ao exercício de direitos, configurando o critério de confiança máxima. "
"A detecção de política de privacidade resultou positiva nos três portais governamentais e negativa em uol.com.br e "
"mercadolivre.com.br — observação relevante que indica limitação da heurística atual de categorização de subpáginas, motivando "
"refinamento documentado nas notas técnicas do repositório.")

p("Um achado de particular interesse para a discussão metodológica refere-se à identificação positiva, em uol.com.br, do uso da "
"plataforma OneTrust como Consent Management Platform (CMP) — um dos vendors comerciais com signatures DOM identificáveis "
"explicitamente cobertos pelo módulo de detecção. Esse achado oferece evidência empírica de que sites brasileiros de grande tráfego "
"adotam plataformas estabelecidas de gestão de consentimento, em linha com as observações de Pantelic et al. (2022) e Rasaii et al. "
"(2023) sobre o mercado global de CMPs. Outro achado operacionalmente relevante refere-se ao mercadolivre.com.br, que foi processado "
"integralmente pela primeira etapa da cadeia de coleta (HttpFetcher, baseado em ``httpx``) em aproximadamente sete segundos, sem "
"necessidade de escalonamento para o fetcher de renderização JavaScript completa — indicando que o site mantém conteúdo crítico "
"acessível em HTML estático, comportamento favorável tanto à coleta automatizada quanto à indexação por mecanismos de busca.")

subheading("Próximas etapas e validação manual prévia (n = 10)")

p("Em complemento ao teste de fumaça reportado acima, foi conduzida etapa intermediária de validação por confronto manual, com "
"amostra dimensionada para n = 10 sites e abrangendo cinco portais governamentais (gov.br/anpd, serpro.gov.br, gov.br raiz, portal "
"da Receita Federal e Tribunal de Contas da União) e cinco portais comerciais (uol.com.br, globo.com, mercadolivre.com.br, "
"magazineluiza.com.br e nubank.com.br). Para cada um dos sites, a rotulagem manual das três variáveis determinísticas foi realizada "
"em navegador limpo (sem cookies de sessão), aplicando os mesmos critérios formais especificados no protocolo. A comparação "
"resultante entre detecção automatizada e rotulagem manual produziu matriz de confusão 2×2 por variável, com métricas de precisão, "
"revocação, medida F1 e coeficiente kappa de Cohen — registradas no apêndice técnico do repositório. Ressalva-se que, com n = 10, "
"os intervalos de confiança dessas métricas são deliberadamente amplos: o propósito desta etapa não é fornecer estimativas "
"estatisticamente robustas, mas identificar classes de erro recorrentes no framework antes da execução da coleta piloto formal, "
"evitando ajustes excessivos a partir de amostras de baixa potência estatística. As estimativas estatisticamente defensáveis "
"derivarão da subamostra de validação prevista no delineamento metodológico, com n = 50, nível de confiança de 95% e margem de "
"erro de 10%.")

p("A execução da coleta piloto formal sobre n = 50 sites, prevista para 28 de maio de 2026, fornecerá as primeiras estatísticas "
"descritivas de frequência e distribuição das três variáveis determinísticas ao longo dos estratos governamental e empresarial. "
"A expansão posterior da coleta para n = 384 sites e o treinamento dos classificadores supervisionados (variáveis ``categoria_cookies`` "
"e ``menciona_lgpd``) sobre o ground truth manual estão programados para o intervalo de 1º a 12 de junho de 2026. As métricas de "
"desempenho completas e os resultados descritivos consolidados serão incorporados à versão revisada deste documento, prevista "
"para submissão à plataforma MBX em 16 de junho de 2026.")

# ---------------------- CONSIDERAÇÕES FINAIS ---------------------------
heading("Considerações Finais")

p("Os resultados parciais consolidados nesta etapa indicam compatibilidade estrutural entre o framework PrivacyScope e as "
"finalidades informacionais da etapa de Monitoramento prevista na Resolução CD/ANPD nº 1/2021. A arquitetura desacoplada e "
"parametrizável, formalizada em interfaces abstratas e governada por protocolo declarativo versionado, permite que critérios "
"e parâmetros sejam ajustados externamente sem alteração do núcleo do sistema — propriedade verificada empiricamente no teste "
"de fumaça reportado na Tabela 2 e na execução repetida de variações do protocolo sobre o mesmo conjunto de evidências brutas. "
"A composição modular de plugins, materializada no registry declarativo, sustenta o requisito de extensibilidade frente a "
"refinamentos futuros, incluindo a incorporação de variáveis técnicas adicionais, fontes amostrais alternativas e classificadores "
"de aprendizado supervisionado, sem necessidade de refatoração das camadas estruturais.")

p("Os próximos passos do trabalho contemplam quatro frentes interdependentes. A primeira, de natureza empírica, abrange a execução "
"da coleta piloto sobre n = 50 sites em 28 de maio de 2026, com produção das primeiras estatísticas descritivas de frequência e "
"distribuição das três variáveis determinísticas. A segunda, de natureza estatística, abrange o cálculo das métricas de desempenho "
"do pipeline determinístico (precisão, revocação, medida F1, acurácia global e coeficiente kappa de Cohen) sobre subamostra de "
"validação manual com n = 50, no intervalo de 1º a 12 de junho de 2026. A terceira, de natureza modelística, abrange o treinamento "
"dos classificadores supervisionados para as variáveis ``categoria_cookies`` e ``menciona_lgpd``, incluindo comparação entre "
"representação clássica (TF-IDF com regressão logística) e representação contextual (embeddings do modelo BERTimbau). A quarta, de "
"natureza analítica, abrange a discussão conceitual-normativa da aderência do framework às finalidades institucionais da etapa de "
"Monitoramento, com particular atenção aos limites legítimos da inferência computacional sobre evidências observáveis e à "
"preservação da distinção entre evidência técnica e juízo jurídico de conformidade. A versão consolidada do documento, contendo "
"esses quatro conjuntos de resultados, está prevista para entrega ao orientador em 31 de maio de 2026 e submissão à plataforma "
"MBX em 16 de junho de 2026.")

# ---------------------- REFERÊNCIAS -----------------------------------
heading("Referências")

def ref(text):
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf = para.paragraph_format
    pf.line_spacing = 1.0
    pf.space_after = Pt(6)
    pf.first_line_indent = Cm(0)
    r = para.add_run(text)
    _set_run(r, size=11)
    return para

ref("AGÊNCIA NACIONAL DE PROTEÇÃO DE DADOS. Saiba como fiscalizamos. Brasília, DF, 2026. Disponível em: https://www.gov.br/anpd/pt-br/assuntos/fiscalizacao-2/saibacomo_fiscalizamos. Acesso em: 17 maio 2026.")

ref("ASSOCIAÇÃO BRASILEIRA DE NORMAS TÉCNICAS. ABNT NBR ISO/IEC 27037:2013 — Tecnologia da informação: técnicas de segurança: diretrizes para identificação, coleta, aquisição e preservação de evidência digital. Rio de Janeiro: ABNT, 2013.")

ref("BRASIL. Lei nº 13.709, de 14 de agosto de 2018. Lei Geral de Proteção de Dados Pessoais (LGPD). Diário Oficial da União: seção 1, Brasília, DF, 15 ago. 2018.")

ref("BRASIL. Autoridade Nacional de Proteção de Dados. Resolução CD/ANPD nº 1, de 28 de outubro de 2021. Aprova o Regulamento do Processo de Fiscalização e do Processo Administrativo Sancionador no âmbito da ANPD. Diário Oficial da União: seção 1, Brasília, DF, 29 out. 2021.")

ref("BRASIL. Autoridade Nacional de Proteção de Dados. Resolução CD/ANPD nº 4, de 24 de fevereiro de 2023. Aprova o Regulamento de Dosimetria e Aplicação de Sanções Administrativas. Diário Oficial da União: seção 1, Brasília, DF, 27 fev. 2023.")

ref("BRASIL. Lei nº 15.352, de 25 de fevereiro de 2026. Transforma a Autoridade Nacional de Proteção de Dados em Agência Nacional de Proteção de Dados. Diário Oficial da União: edição extra, Brasília, DF, 25 fev. 2026.")

ref("BRASIL. Decreto nº 5.296, de 2 de dezembro de 2004. Regulamenta as Leis nº 10.048/2000 e nº 10.098/2000, estabelecendo normas gerais e critérios básicos para a promoção da acessibilidade. Diário Oficial da União: Brasília, DF, 3 dez. 2004.")

ref("BRASIL. Lei nº 13.146, de 6 de julho de 2015. Institui a Lei Brasileira de Inclusão da Pessoa com Deficiência (Estatuto da Pessoa com Deficiência). Diário Oficial da União: Brasília, DF, 7 jul. 2015.")

ref("eMAG. 2014. Modelo de Acessibilidade em Governo Eletrônico — versão 3.1. Departamento de Governo Eletrônico, Ministério do Planejamento, Orçamento e Gestão. Brasília, DF.")

ref("CASEY, E. 2011. Digital Evidence and Computer Crime: Forensic science, computers and the internet. 3ed. Academic Press, Waltham, MA, USA.")

ref("DABROWSKI, A.; MERZDOVNIK, G.; ULLRICH, J.; SENDERA, G.; WEIPPL, E. 2019. Measuring cookies and web privacy in a post-GDPR world. In: Privacy Technologies and Policy. Springer, Cham, Switzerland.")

ref("HORMOZI, A. M. 2006. Cookies and privacy. Information Systems Security 13(6): 51-59.")

ref("JAVED, Y.; SAJID, A. 2024. A systematic review of privacy policy literature. ACM Computing Surveys 57(4): 1-43. DOI: 10.1145/3698393.")

ref("KOLEY, S.; BHARATHI, S. V. 2021. Prioritizing and ranking the taxonomy of factors critical to GDPR compliance. Journal of Physics: Conference Series 1964 042074. DOI: 10.1088/1742-6596/1964/4/042074.")

ref("KOSTER, M.; ILLYES, G.; ZELLER, H.; SASSMAN, L. 2022. RFC 9309: Robots Exclusion Protocol. Internet Engineering Task Force (IETF). DOI: 10.17487/RFC9309. Disponível em: https://www.rfc-editor.org/rfc/rfc9309. Acesso em: 20 maio 2026.")

ref("LE POCHAT, V.; VAN GOETHEM, T.; TAJALIZADEHKHOOB, S.; KORCZYŃSKI, M.; JOOSEN, W. 2019. Tranco: a research-oriented top sites ranking hardened against manipulation. In: Proceedings of the 26th Network and Distributed System Security Symposium (NDSS 2019), San Diego, CA, USA.")

ref("LODGE, M.; WEGRICH, K. (eds.). 2014. The Problem-solving Capacity of the Modern State: Governance challenges and administrative capacities. Oxford University Press, Oxford, UK.")

ref("MARTIN, R. C. 2000. Design Principles and Design Patterns. Object Mentor.")

ref("MORI, K.; NAGAI, T.; TAKATA, Y.; KAMIZONO, M.; MORI, T. 2023. Analysis of privacy compliance by classifying policies before and after the Japanese law revision. Journal of Information Processing 31: 829-841. DOI: 10.2197/ipsjjip.31.829.")

ref("OECD. 2013. Recommendation of the Council concerning Guidelines Governing the Protection of Privacy and Transborder Flows of Personal Data. OECD/LEGAL/0188. OECD, Paris, France.")

ref("OWASP. n.d. OWASP Top 10 Privacy Risks Countermeasures v2.0. OWASP Foundation.")

ref("PANTELIC, O.; JOVIC, K.; KRSTOVIC, S. 2022. Cookies implementation analysis and the impact on user privacy regarding GDPR and CCPA regulations. Sustainability 14(9): 5015. DOI: 10.3390/su14095015.")

ref("RASAII, A.; SINGH, S.; GOSAIN, D.; GASSER, O. 2023. Exploring the Cookieverse: a multi-perspective analysis of web cookies. In: Passive and Active Measurement (PAM). Springer, Cham, Switzerland.")

ref("SCULLEY, D.; HOLT, G.; GOLOVIN, D.; DAVYDOV, E.; PHILLIPS, T.; EBNER, D.; CHAUDHARY, V.; YOUNG, M.; CRESPO, J.-F.; DENNISON, D. 2015. Hidden technical debt in machine learning systems. In: Advances in Neural Information Processing Systems 28 (NeurIPS), Montreal, Canada, p. 2503-2511.")

ref("VORSTER, A.; DA VEIGA, A. 2023. Proposed guidelines for website data privacy policies and an application thereof. In: Human Aspects of Information Security and Assurance (HAISA). Springer, Cham, Switzerland.")

ref("VU, T.-H.-G.; HOANG, H.-N.; LE, T.-Q. 2023. A user privacy risk-driven approach to web cookie classification. In: Proceedings of the International Conference on Security and Privacy. Springer, Singapore.")

ref("WILSON, G.; BRYAN, J.; CRANSTON, K.; KITZES, J.; NEDERBRAGT, L.; TEAL, T. K. 2017. Good enough practices in scientific computing. PLOS Computational Biology 13(6): e1005510. DOI: 10.1371/journal.pcbi.1005510.")

# --- Re-append sectPr to ensure margins/header/page-numbers preserved ---
if sectPr is not None:
    body.append(sectPr)

doc.save(OUTPUT)

# --- Corrige cabeçalho: substitui placeholders pelo curso e ano corretos ---
import zipfile, shutil as _shutil, os

_HEADER_PATH = "word/header1.xml"
_PLACEHOLDER = " _________ (Nome do curso) – ____ (ano da defesa)"
_REPLACEMENT = " MBA em Data Science e Analytics – 2026"

_tmp = OUTPUT + ".tmp.zip"
with zipfile.ZipFile(OUTPUT, "r") as zin, zipfile.ZipFile(_tmp, "w", zipfile.ZIP_DEFLATED) as zout:
    found = False
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename == _HEADER_PATH:
            txt = data.decode("utf-8")
            if _PLACEHOLDER in txt:
                txt = txt.replace(_PLACEHOLDER, _REPLACEMENT)
                found = True
            data = txt.encode("utf-8")
        zout.writestr(item, data)
_shutil.move(_tmp, OUTPUT)
if not found:
    print("AVISO: placeholder do cabeçalho não encontrado — verificar manualmente.")
else:
    print("Cabeçalho corrigido: 'MBA em Data Science e Analytics – 2026'")

print("OK:", OUTPUT)
print("Tamanho:", os.path.getsize(OUTPUT), "bytes")
