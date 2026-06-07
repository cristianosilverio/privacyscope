# -*- coding: utf-8 -*-
"""
Constrói o documento Resultados Preliminares V3 a partir do template oficial.

V5 (03/06/2026): V4 + changelog acumulado pós-V3 (rotulagem cega, refino dos 3 detectores, sensibilidade, externalização config, expansão amostra ampliada n=200, kappa, limitações).
Mudanças relativas ao V2:
  - Resumo menciona resultados da piloto
  - REMOVIDO smoke C3 (Tabela 2 n=5), substituído pela piloto n=49
  - Nova subseção "Coleta piloto: composição e cobertura" (attrition ~17%)
  - Nova Tabela: frequências da piloto por variável e estrato
  - Nova Tabela: métricas de validação do pré-piloto (n=9/10)
  - Justificativa explícita do n=384 (fórmula + cálculo + ressalvas; Cochran 1977)
  - Considerações Finais atualizadas com resultados e caminho à validação formal

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
OUTPUT   = "/sessions/peaceful-lucid-edison/mnt/TCC/Resultados Preliminares - Cristiano Gouveia Silverio - V5-20260605.docx"
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


def equation(omml_xml, *, number=None, after=10):
    """Insere uma equacao via OMML (Office Math Markup Language) — Manual ESALQ 15.3.
    omml_xml: string com o XML <m:oMath>...</m:oMath>
    number: numero entre parenteses (e.g., "1") inserido a direita
    """
    para = doc.add_paragraph()
    pf = para.paragraph_format
    para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    pf.line_spacing = 1.0
    pf.space_before = Pt(6)
    pf.space_after = Pt(after)
    # parse e injeta OMML
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsmap
    nsdecl = ' '.join(f'xmlns:{k}="{v}"' for k,v in nsmap.items())
    full = f'<root {nsdecl}>{omml_xml}</root>'
    root = parse_xml(full)
    for child in root:
        para._p.append(child)
    if number:
        r = para.add_run(f"     ({number})")
        _set_run(r, size=11)
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

def set_repeat_header(table):
    """Marca a primeira linha como cabeçalho repetido em todas as páginas — manual ESALQ 15.2."""
    tr = table.rows[0]._tr
    trPr = tr.find(qn("w:trPr"))
    if trPr is None:
        trPr = OxmlElement("w:trPr")
        tr.insert(0, trPr)
    tblHeader = OxmlElement("w:tblHeader")
    trPr.append(tblHeader)

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

addr("¹* Especializando em MBA em Data Science e Analytics. LGPD2U. *autor correspondente: cristiano.silverio@lgpd2u.com.br")
addr("² Instituto de Pesquisas Tecnológicas do Estado de São Paulo (IPT). Mestre em Engenharia de Computação. Av. Prof. Almeida Prado, 532 - Butantã; 05508-901 São Paulo, SP, Brasil. dbvirissimo@ipt.br")

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
"larga escala, atividade incompatível com inspeção manual exaustiva. O presente trabalho propôs o desenvolvimento de um “framework” "
"computacional parametrizável, denominado PrivacyScope, baseado em técnicas de “webscraping” e aprendizado de máquina, destinado a "
"operacionalizar parâmetros observáveis de transparência em websites institucionais brasileiros. A pesquisa caracterizou-se como "
"aplicada, descritiva, com abordagem mista e delineamento de Implementação de Algoritmo de Machine Learning. A arquitetura foi "
"estruturada em seis camadas desacopladas (Ingestão, Coleta, Evidência Bruta, Análise, Resultados Estruturados e Saída), governadas "
"por protocolo declarativo versionado, com cadeia de custódia das evidências brutas via empacotamento e “hash” criptográfico, em "
"aderência à ABNT NBR ISO/IEC 27037:2013. A amostragem adotou a Tranco List filtrada pelo TLD .br como fonte única, em desenho "
"estratificado por sufixo de domínio. Foi definida bateria inicial de seis variáveis técnicas, três detectadas por regras "
"determinísticas e três por classificação supervisionada sobre o texto da política de privacidade. Os resultados parciais consolidaram a arquitetura, a especificação "
"operacional das variáveis e o “pipeline” em fase de validação. O “framework” mostrou-se compatível, em concepção, com as finalidades "
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
", Lei Geral de Proteção de Dados Pessoais [LGPD], estabeleceu princípios, direitos e deveres voltados à garantia da privacidade dos "
"dados pessoais e instituiu a Autoridade Nacional de Proteção de Dados [ANPD] como órgão competente para regular, fiscalizar e "
"aplicar sanções administrativas (Brasil, 2018). Posteriormente, a Lei nº 15.352/2026 transformou a ANPD em autarquia especial "
"vinculada ao Ministério da Justiça e Segurança Pública, dotada de autonomia técnica, decisória, administrativa e financeira "
"(Brasil, 2026). Em escala global, mais de 160 países instituíram legislações próprias de proteção de dados, frequentemente "
"fundamentadas em diretrizes internacionais como as recomendações da OECD (OECD, 2013; Javed e Sajid, 2024).")

p("No exercício de suas atribuições, a ANPD aprovou, por meio da Resolução CD/ANPD nº 1/2021, o Regulamento do Processo de "
"Fiscalização, que organiza as atividades fiscalizatórias em diferentes instrumentos e etapas operacionais (Brasil, 2021). Entre "
"essas etapas, destaca-se a fase de Monitoramento, destinada à coleta sistemática de informações, análise de evidências e "
"identificação de indícios relacionados ao tratamento de dados pessoais. A etapa possui caráter informacional e exploratório, "
"orientada à produção de conhecimento sobre práticas de tratamento, identificação de padrões de comportamento regulatório e "
"levantamento de evidências que possam subsidiar decisões futuras da autoridade. Diferentemente das etapas sancionatórias, o "
"monitoramento não tem por finalidade a aplicação de penalidades ou a caracterização formal de infrações, mas sim o apoio à "
"formulação de estratégias regulatórias e ao planejamento das ações de fiscalização (ANPD, 2026).")

p("Observa-se crescente interesse acadêmico e institucional no uso de tecnologias computacionais para apoiar atividades de "
"supervisão regulatória baseadas em dados, frequentemente associadas à abordagem de regulação baseada em evidências, diante da "
"necessidade de fortalecimento das capacidades analíticas do Estado para lidar com problemas complexos de governança (Lodge e "
"Wegrich, 2014). Métodos de coleta automatizada de informações na web (“webscraping” e “web crawling”), combinados a técnicas de "
"análise textual e estrutural, têm sido explorados para produção de evidências empíricas sobre comportamento organizacional em "
"ambientes digitais. Pesquisas recentes investigam classificação automatizada de políticas de privacidade (Javed e Sajid, 2024; "
"Mori et al., 2023; Vorster e Da Veiga, 2023), análise de mecanismos técnicos como cookies e rastreadores (Hormozi, 2006; "
"Dabrowski et al., 2019; Rasaii et al., 2023; Vu et al., 2023) e priorização de fatores críticos de conformidade (Koley e "
"Bharathi, 2021), demonstrando o potencial dessas abordagens para examinar padrões de transparência informacional em larga escala.")

p("Apesar dos avanços técnicos, até o presente momento, não foram encontrados trabalhos que investiguem a aplicação sistemática dessas técnicas no contexto específico "
"da supervisão regulatória em proteção de dados pessoais, particularmente em relação ao apoio à etapa de Monitoramento prevista nos "
"processos fiscalizatórios brasileiros. Identifica-se, assim, a oportunidade de investigar como abordagens computacionais baseadas "
"em coleta automatizada e análise de conteúdo digital podem contribuir para a produção estruturada de informações observáveis em "
"ambientes digitais públicos, sem substituir o julgamento jurídico ou a análise regulatória realizada pelas autoridades competentes. "
"A delimitação adotada concentra-se exclusivamente no desenvolvimento de ferramental técnico potencialmente aplicável à fase "
"informacional do processo, não abrangendo classificação de infrações, dosimetria de sanções ou avaliação de impacto decisório "
"(Brasil, 2023).")

p("Diante desse contexto, o objetivo deste trabalho é desenvolver e avaliar um “framework” computacional parametrizável, denominado "
"PrivacyScope, baseado em técnicas de “webscraping” e métodos de aprendizado de máquina, capaz de operacionalizar parâmetros "
"observáveis de transparência em websites institucionais brasileiros, produzindo indicadores descritivos auditáveis e reprodutíveis "
"que possam subsidiar a etapa de Monitoramento prevista na Resolução CD/ANPD nº 1/2021. A finalidade técnica do algoritmo "
"enquadra-se nas categorias “supervisionado” (modelos de classificação textual sobre políticas de privacidade e categorização de cookies) "
"e desenvolvimento de “web crawlers” (coleta estruturada de evidências digitais), com ênfase em auditabilidade, reprodutibilidade e "
"extensibilidade.")

# ---------------------- IMPLEMENTAÇÃO DE ALGORITMO ---------------------
heading("Implementação de Algoritmo(s) de Machine Learning")

p("Esta pesquisa caracteriza-se, quanto aos objetivos, como aplicada e descritiva, com abordagem metodológica mista, combinando "
"análise quantitativa (proporções, distribuições e métricas de desempenho) com análise qualitativa (interpretação de divergências "
"entre detecção automatizada e avaliação manual de referência). O delineamento adotado é a implementação de algoritmo de "
"machine learning e a técnica de obtenção de dados é o Levantamento de Dados Secundários, executado sobre conteúdos "
"publicamente disponíveis em websites institucionais brasileiros. Não há interação direta com pessoas naturais nem coleta de dados "
"pessoais privados, o que enquadra o estudo nas hipóteses de dispensa de análise pelo Comitê de Ética em Pesquisa previstas na "
"Resolução CNS nº 510/2016, incisos II e III do parágrafo único do artigo 1º.")

subheading("Arquitetura do “framework” PrivacyScope")

p("A arquitetura do “framework” PrivacyScope foi concebida em camadas desacopladas, comunicando-se exclusivamente por interfaces "
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
caption("Figura 1. Arquitetura em camadas do “framework” PrivacyScope", before=2, after=0)
caption("Fonte: Dados originais da pesquisa", before=0, after=8)

p("A Figura 1 apresenta o desenho em seis camadas funcionais, governadas por um protocolo declarativo em formato YAML, com controle de versão e "
"auditável por “hash” criptográfico. As camadas são: (1) Ingestão, responsável por gerar a lista de domínios a partir de fontes "
"amostrais plugáveis; (2) Coleta, que executa o “webscraping”/webcrawling e produz evidências brutas (HTML, cookies, headers e "
"capturas de tela); (3) Evidência Bruta, repositório imutável (append-only) que empacota e assina criptograficamente cada conjunto "
"de evidências; (4) Análise, que aplica testes parametrizáveis às evidências e gera resultados estruturados; (5) Resultados "
"Estruturados, persistência tabular em formato longo (long-format); e (6) Saída, que renderiza os resultados em formatos "
"consumíveis. O orquestrador resolve plugins, paraleliza execuções e registra trilha de auditoria. Cada caixa do diagrama "
"representa uma interface formal — plugins específicos podem ser substituídos ou adicionados sem alteração das demais camadas, "
"atendendo ao requisito de extensibilidade definido no projeto. A formalização desses contratos em classes abstratas (Abstract "
"Base Classes em Python) e a externalização das configurações em arquivo YAML com controle de versão seguem boas práticas de reprodutibilidade "
"computacional consolidadas por Wilson et al. (2017). O conhecimento de domínio mais sujeito a refinamento empírico (vocabulários, limiares numéricos e listas de exclusão) está externalizado em arquivos de configuração separados do código-fonte, viabilizando ajustes auditáveis sem alterar a lógica dos detectores.")

p("A implementação do “framework” foi concluída na primeira fase do cronograma e disponibilizada em repositório público no GitHub (Silverio, 2026), "
"em conformidade com os princípios FAIR (Findable, Accessible, "
"Interoperable, Reusable) propostos por Wilson et al. (2017). A versão de referência deste documento corresponde aos commits sequenciais publicados no repositório (Silverio, 2026). "
"A execução completa do “pipeline” é invocada por interface de linha de comando "
"(“privacyscope run protocol.yaml”), recebendo como único parâmetro o caminho do protocolo declarativo em formato YAML, cujo "
"“hash” criptográfico SHA-256 é registrado na trilha de auditoria de cada evidência produzida — garantindo rastreabilidade entre "
"parâmetros de execução e resultados.")

subheading("Composição de plugins via registry")

p("A resolução de plugins é centralizada em um registry declarativo (“core/plugin_registry.py”), que mapeia o nome textual "
"referenciado no protocolo YAML à classe concreta que implementa a interface correspondente. O registry separa explicitamente "
"plugins por camada (fontes amostrais, “fetchers”, repositórios, result stores, testes de variáveis e renderizadores de saída), "
"impedindo que um plugin destinado a uma camada seja inadvertidamente resolvido como pertencente a outra. A adição de uma "
"nova variável técnica, fonte amostral ou estratégia de coleta exige duas ações apenas: (i) a criação do arquivo Python que "
"implementa a interface abstrata da camada apropriada, e (ii) o registro do nome desse plugin no dicionário correspondente. "
"Nenhuma alteração nas demais camadas, no orquestrador ou na linha de comando é necessária, em estrita aderência ao princípio "
"aberto-fechado (Martin, 2000). Essa propriedade é central para a defensibilidade do desenho frente a refinamentos pós-piloto, "
"nos quais variáveis adicionais ou critérios mais restritos podem ser incorporados sem refatoração do núcleo do sistema.")

p("A cadeia de coleta é particularizada por um plugin específico — “FallbackChain” — que implementa o padrão Chain of Responsibility, "
"orquestrando uma sequência ordenada de “fetchers” e definindo declarativamente as condições de escalonamento entre eles, expressas no "
"protocolo YAML como sinais qualitativos sobre a evidência produzida. Esse desenho permite que um “fetcher” mais leve (HttpFetcher, "
"baseado em “httpx” e “BeautifulSoup”) seja experimentado primeiro, escalando para um “fetcher” mais oneroso (PlaywrightFetcher, "
"com renderização JavaScript completa via Chromium em modo headless) somente quando o resultado do anterior apresenta sinais de "
"insuficiência. Cinco sinais foram operacionalizados: “html_root_smaller_than_bytes” (página suspeitamente pequena, típica de "
"shell SPA), “subpage_selection_empty” (nenhuma subpágina relevante detectada), “cookies_pre_consent_zero” (“fetcher” não captou "
"cookies em fase pré-consent), “consent_actions_all_failed” (todas as tentativas de interação com banner falharam) e "
"“has_js_shell_markers” (HTML contém marcadores típicos de página dependente de JavaScript). Cada decisão de escalonamento é "
"registrada cronologicamente na trilha de auditoria da evidência, permitindo reconstrução completa do histórico de tentativas.")

subheading("“Dataset”: universo amostral e amostragem")

p("O universo amostral é constituído por domínios ativos sob o Top Level Domain [TLD] .br, restritos a websites institucionais empresariais e "
"governamentais. A composição da amostra adota como fonte primária a Tranco List (Le Pochat et al., 2019), uma listagem ranqueada e "
"reprodutível de domínios construída pela agregação das seguintes listagens públicas de popularidade: Chrome User Experience Report (CrUX), Cloudflare Radar, Farsight, Majestic e Cisco Umbrella, com "
"atualização diária e identificação por “hash”, amplamente utilizada em pesquisa de privacidade web por sua resistência a "
"manipulação e por seu uso em estudos revisados por pares. O snapshot 43Z8X, gerado em 24 de maio de 2026, foi filtrado para o TLD .br, gerando o quadro "
"amostral. Adotou-se a Tranco List como fonte única: o estrato governamental é obtido pelo subconjunto de domínios com sufixo "
"“.gov.br” presente na própria lista, percorrendo-se o ranqueamento em profundidade até alcançar o número de unidades "
"governamentais necessário. Optou-se por não complementar com listagens externas a fim de preservar a homogeneidade da fonte e "
"evitar viés de amostragem diferencial entre os estratos — ambos derivam do mesmo critério de popularidade ranqueada e auditável. "
"A escolha pela Tranco decorre da indisponibilidade da fonte originalmente prevista no projeto — listagem institucional do "
"NIC.br — cuja solicitação formal não foi atendida. O desenho adotado preserva os requisitos de neutralidade setorial e "
"reprodutibilidade metodológica.")

p("A amostragem é estratificada em dois estratos definidos pelo sufixo do domínio: governamental (“.gov.br”) e empresarial "
"(demais domínios sob o TLD .br). O tamanho-alvo da amostra final foi dimensionado pela fórmula clássica de estimação de "
"proporções para população grande (Cochran, 1977), n = z²·p·(1−p)/E², em que z é o escore normal correspondente ao nível de "
"confiança, p a proporção esperada e E a margem de erro absoluta. Adotando-se nível de confiança de 95% (z = 1,96), margem de "
"erro de 5% (E = 0,05) e estimativa conservadora p = 0,50 — valor que maximiza a variância e, portanto, o tamanho de amostra "
"requerido na ausência de conhecimento prévio das proporções —, obtém-se n = (1,96² × 0,50 × 0,50) / 0,05² ≈ 384 unidades. "
"Como o universo de domínios .br ativos é da ordem de milhões, a correção para população finita é desprezível, mantendo-se o "
"tamanho em torno de 384. Para a coleta piloto reportada nesta etapa adotou-se n = 50 (efetivamente 49 coletáveis, conforme "
"detalhado adiante), com alocação de 40 unidades ao estrato empresarial e 10 ao governamental, extraídas por amostragem "
"aleatória simples dentro de cada estrato a partir de semente fixa, para reprodutibilidade.")

p("Três delimitações do dimensionamento merecem registro explícito. Primeiro, o valor de 384 dimensiona a estimativa de uma "
"proporção global com margem de ±5%; estimativas separadas por estrato com a mesma precisão exigiriam aproximadamente esse "
"número em cada estrato. Como o objetivo do trabalho é o panorama geral, e não a comparação inferencial entre estratos, a "
"amostra global de 384 é suficiente. Segundo, a adoção de p = 0,50 é deliberadamente conservadora. Terceiro, e mais relevante "
"para os limites de generalização: o quadro amostral é a Tranco List filtrada por .br — isto é, domínios com popularidade "
"mensurável —, e não a totalidade dos domínios .br registrados, parte expressiva dos quais se encontra inativa ou estacionada. "
"As estimativas produzidas são, portanto, válidas para o universo de sítios .br ativos e com tráfego relevante, e não devem "
"ser extrapoladas indiscriminadamente para o conjunto de todos os domínios registrados sob o TLD nacional.")

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
caption("Tabela 1. Variáveis técnicas operacionalizadas no protocolo v1.0.0 do “framework” PrivacyScope", before=4, after=0)
caption("(continua)", before=0, after=2)

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
     "container nomeado visível (filtro de visibilidade via DOM) + léxico de cookies, ou assinatura de fornecedor visível, ou ação de consentimento bem-sucedida",
     "LGPD art. 8º; Dabrowski et al. (2019); Rasaii et al. (2023)"),
    ("tem_politica_privacidade", "binária",
     "presença de link ou seção rotulado como política/aviso/termo de privacidade",
     "subpágina selecionada por path/título de política + qualificação por conteúdo (léxico mínimo) na união do HTML pré e pós-consentimento; PDF com path de política também conta",
     "LGPD art. 9º; Javed e Sajid (2024); Vorster e Da Veiga (2023)"),
    ("tem_canal_titular", "binária",
     "presença de contato específico do Encarregado pelo tratamento de dados (e-mail nominal, formulário ou link com termos de titular)",
     "regex de e-mail (dpo|encarregado|privacidade) no domínio do próprio controlador, com filtro controlador-vs-processador (lista de exclusão de provedores) — e-mail genérico não conta",
     "LGPD art. 41; Res. CD/ANPD 18/2024"),
    ("direitos_titular_explicados", "binária",
     "presença de explicação sobre os direitos do titular previstos no art. 18 da LGPD na política de privacidade",
     "classificador supervisionado multirrótulo por sentença sobre o texto da política, com agregação por documento",
     "LGPD art. 18; Mori et al. (2023); Javed e Sajid (2024)"),
    ("finalidade_especificada", "binária",
     "presença de descrição específica das finalidades do tratamento, conforme princípio da finalidade (art. 6, I)",
     "classificador supervisionado multirrótulo por sentença sobre o texto da política, com agregação por documento",
     "LGPD art. 6, I; Vorster e Da Veiga (2023)"),
    ("transf_internacional_divulgada", "binária",
     "menção explícita a transferência internacional de dados pessoais conforme art. 33 da LGPD",
     "classificador supervisionado multirrótulo por sentença sobre o texto da política, com agregação por documento",
     "LGPD art. 33"),
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

# Cabeçalho repetido em todas as páginas (manual ESALQ 15.2)
set_repeat_header(table)

caption("Fonte: Dados originais da pesquisa", before=2, after=10)

subheading("Cadeia de custódia das evidências")

p("A integridade das evidências coletadas é garantida por procedimento de cadeia de custódia inspirado na ABNT NBR ISO/IEC "
"27037:2013, que estabelece diretrizes para identificação, coleta, aquisição e preservação de evidência digital (Associação Brasileira de Normas Técnicas [ABNT"
"], 2013; Casey, 2011). Para cada site analisado, o conjunto bruto de evidências — HTML da página "
"principal e de páginas internas relevantes (política, termos, encarregado), cookies fixados, cabeçalhos HTTP de cada requisição, "
"captura de tela completa e metadados de execução — é serializado e empacotado em arquivo tar.gz. Um “hash” criptográfico SHA-256 do "
"pacote é calculado e registrado em manifest.jsonl assinado, cujo próprio “hash” é gravado no “log” de auditoria. Qualquer adulteração "
"posterior é detectável pela recomputação dos hashes em cascata. O repositório de evidências brutas opera em modo append-only, o "
"que assegura imutabilidade e permite que múltiplas execuções analíticas sob protocolos diferentes sejam aplicadas sobre o mesmo "
"conjunto preservado, atendendo aos requisitos de consistência e reprodutibilidade do projeto.")

subheading("“Pipeline” de coleta")

p("O “pipeline” de coleta é implementado em Python (versão 3.12.10), com paralelismo assíncrono (asyncio) e cadeia de “fallback”. A "
"primeira tentativa de coleta é realizada por meio do componente HttpFetcher, baseado nas bibliotecas httpx e BeautifulSoup, "
"adequado para páginas com conteúdo estático servido via HTML. Páginas que dependem de renderização por JavaScript ou que somente "
"fixam cookies após interação são processadas pelo PlaywrightFetcher, que opera uma instância de navegador Chromium em modo "
"headless, com processo isolado por coleta para garantir ausência de vazamento de estado entre sites. Em todas as coletas, "
"são respeitadas as boas práticas técnicas: controle de frequência de requisições, identificação adequada do agente de coleta no "
"cabeçalho User-Agent, observância às restrições explicitamente sinalizadas pelo robots.txt do domínio e limitação estrita a "
"conteúdos publicamente disponibilizados (Brasil, 2018, art. 7º, §4º; OWASP, n.d.). Falhas operacionais (timeouts, certificados "
"inválidos, redirecionamentos abusivos) são registradas no “log” de execução e analisadas qualitativamente.")

p("O tratamento do arquivo robots.txt segue o Robots Exclusion Protocol formalizado na RFC 9309 (Koster et al., 2022). Quando o "
"robots.txt é servido com status HTTP 200, suas diretivas são integralmente respeitadas, e domínios que proíbam a coleta para o "
"agente de pesquisa são excluídos da amostra efetiva, com o evento registrado na trilha de auditoria. Para respostas de erro, "
"adota-se a recomendação da seção 2.3.1.4 da RFC: erros da classe 5xx (servidor incapaz de servir as regras) são interpretados "
"conservadoramente como proibição total de coleta, ao passo que erros da classe 4xx — incluindo 401 e 403 — são interpretados "
"como ausência de restrições aplicáveis. Esta última decisão, revista após observação empírica no pré-piloto, decorre de que "
"respostas 403 ao robots.txt frequentemente originam-se de proteções anti-bot genéricas a montante (firewalls de aplicação web) "
"e não de diretivas de exclusão dirigidas a coletores, de modo que o tratamento estritamente conservador excluiria indevidamente "
"sites cujo conteúdo é público e cuja página inicial responde normalmente.")

p("A camada FallbackChain orquestra o encadeamento dos “fetchers” com escalonamento baseado em sinais auditáveis. Para cada “fetcher” "
"na cadeia, o protocolo declara explicitamente as condições que disparam escalonamento ao próximo — tanto por classes de exceção "
"(“NavigationFailedError”, “JsRequiredError”) quanto por sinais qualitativos sobre a evidência produzida. Cinco sinais foram "
"operacionalizados nesta versão: “html_root_smaller_than_bytes” (página suspeitamente pequena, típica de shell SPA), "
"“subpage_selection_empty” (nenhuma subpágina relevante detectada), “cookies_pre_consent_zero” (“fetcher” não captou cookies em "
"fase pré-consent), “consent_actions_all_failed” (todas as tentativas de interação com banner falharam) e “has_js_shell_markers” "
"(HTML contém marcadores típicos de página dependente de JavaScript). Cada decisão de escalonamento é registrada cronologicamente "
"em “RawEvidence.errors” com prefixo “chain.”, permitindo reconstrução completa do histórico de tentativas para qualquer "
"resultado. Condições do tipo abort_on (e.g., “RobotsDisallowedError”) interrompem a cadeia sem escalonar, preservando ética da "
"coleta. Backoff exponencial entre tentativas e retries por “fetcher” são igualmente configuráveis no protocolo.")

p("Especificamente, o PlaywrightFetcher opera em fases distintas — captura de cookies antes da interação com qualquer banner de "
"consent e, em seguida, após aceitação automatizada do banner — em alinhamento à metodologia consolidada por Dabrowski et al. (2019) "
"e Rasaii et al. (2023). Essa diferenciação permite distinguir cookies estritamente necessários, ativados antes da manifestação do "
"titular, daqueles ativados condicionalmente após o consentimento, dimensão relevante para análise de aderência aos artigos 7º e 8º "
"da Lei nº 13.709/2018 e ao Guia Orientativo: Cookies e Proteção de Dados Pessoais (ANPD, 2022). A detecção do banner de consent emprega "
"heurísticas configuráveis no protocolo, incluindo padrões léxicos, seletores CSS e, com prioridade, atributos de acessibilidade "
"ARIA (“aria-label”, “role”, “aria-modal”). A inclusão de ARIA como sinal primário decorre da exigibilidade de acessibilidade "
"digital em sites institucionais brasileiros, estabelecida pelo Decreto nº 5.296/2004, pela Lei nº 13.146/2015 (Lei Brasileira de "
"Inclusão) e operacionalizada pelo Modelo de Acessibilidade em Governo Eletrônico (Brasil, 2004, 2015; eMAG, 2014). Em "
"sites tecnicamente acessíveis, atributos ARIA frequentemente carregam informação semântica mais explícita do que o texto visível "
"do elemento, aumentando a precisão da detecção automatizada de banners e elementos de navegação institucional.")

subheading("“Pipeline” de análise: regras formais e classificadores supervisionados")

p("O “pipeline” de análise opera em dois regimes complementares. O regime determinístico aplica regras formais (seletores CSS, "
"expressões regulares e padrões léxico-semânticos) às três variáveis de baixa ambiguidade observáveis no HTML da página inicial e em subpáginas qualificadas: banner de cookies, política de privacidade e canal do titular. "
"O regime probabilístico, aplicado às três variáveis textualmente complexas (direitos do titular explicados, finalidade especificada e transferência internacional divulgada), opera sobre o texto da política de privacidade, com classificação em nível de sentença e treino em rotulagem manual de referência. "
"O classificador-base é uma Regressão Logística multirrótulo sobre representação por “TF-IDF”; como linha de base alternativa, está prevista avaliação com embeddings de sentenças do modelo BERTimbau, permitindo comparar representação lexical e semântica sob o mesmo algoritmo. "
"As predições por sentença são agregadas em decisão por documento. Cada execução produz, por variável, o valor previsto, a probabilidade calibrada como nível de confiança, as sentenças-evidência identificadas e a versão do classificador, viabilizando auditoria caso a caso.")

subheading("Métricas de validação")

p("A validação do desempenho do “framework” adota subamostragem probabilística da amostra principal, com tamanho dimensionado pela "
"mesma fórmula clássica de estimação de proporções (n = 50, IC 95%, margem de erro de 10%, p̂ = 0,5). Sobre essa subamostra, é constituído um conjunto de referência (rotulagem manual de referência) por rotulagem manual seguindo os mesmos critérios formais definidos no "
"protocolo. As métricas de desempenho calculadas para cada variável incluem precisão, revocação, acurácia global e medida F1, "
"complementadas pelo coeficiente kappa de Cohen para avaliação de concordância entre detecção automatizada e avaliação manual. "
"Divergências são analisadas qualitativamente, separando ambiguidade textual genuína, limitação estrutural das regras de detecção "
"e necessidade de refinamento de parâmetros. A consistência interna do “framework” é avaliada por execução repetida sob protocolo "
"idêntico (esperando-se “hash” idêntico do conjunto de evidências brutas) e por análise de estabilidade frente à variação controlada "
"de parâmetros configuráveis.")

# Análise de sensibilidade dos limiares
p("A análise de sensibilidade conduzida sobre a amostra de desenvolvimento, variando os limiares numéricos de cada detector em torno dos valores adotados, com reexecução do método de avaliação sobre os 49 sítios, indicou que nenhum dos limiares atuais é determinante para as métricas: as taxas de precisão, revocação e F1 permaneceram estáveis em faixas largas em torno dos valores adotados. Os platôs observados na amostra de desenvolvimento devem ser reconfirmados na subamostra de validação independente.")

# Nota metodológica sobre o kappa de Cohen
p("Especificamente sobre o coeficiente kappa de Cohen (1960), adotado como medida de concordância humano-vs-algoritmo, define-se conforme a eq. (1), em que p_o é a proporção observada de concordância e p_e a esperada ao acaso, calculada a partir das margens da matriz de confusão. A motivação para reportá-lo junto da acurácia é que, sob classes desbalanceadas, a acurácia engana — no canal do titular, por exemplo, 37 de 48 sites do piloto não têm canal: um classificador trivial que responde sempre “não” atinge 0,77 de acurácia com κ = 0, não acrescentando informação. A escala convencional de Landis e Koch (1977) categoriza < 0 como pior que o acaso; 0,01-0,20 leve; 0,21-0,40 razoável; 0,41-0,60 moderada; 0,61-0,80 substancial; e 0,81-1,00 quase perfeita, embora os próprios autores admitam os cortes como arbitrários. Duas ressalvas se aplicam: com anotador único, o valor reportado é concordância humano-vs-algoritmo, não inter-avaliadores; e o kappa é sensível à prevalência e ao viés entre rotuladores (paradoxos descritos por Feinstein e Cicchetti, 1990), motivo pelo qual ele é reportado em conjunto com precisão, revocação e acurácia.")
equation('<m:oMath><m:r><m:t>&#954; = </m:t></m:r><m:f><m:fPr><m:type m:val="bar"/></m:fPr><m:num><m:r><m:t>p</m:t></m:r><m:sSub><m:e><m:r><m:t></m:t></m:r></m:e><m:sub><m:r><m:t>o</m:t></m:r></m:sub></m:sSub><m:r><m:t> &#8722; p</m:t></m:r><m:sSub><m:e><m:r><m:t></m:t></m:r></m:e><m:sub><m:r><m:t>e</m:t></m:r></m:sub></m:sSub></m:num><m:den><m:r><m:t>1 &#8722; p</m:t></m:r><m:sSub><m:e><m:r><m:t></m:t></m:r></m:e><m:sub><m:r><m:t>e</m:t></m:r></m:sub></m:sSub></m:den></m:f></m:oMath>', number="1", after=8)


# ---------------------- RESULTADOS PRELIMINARES ------------------------
heading("Resultados Preliminares")

p("Os Resultados Preliminares consolidados até o fechamento desta versão compreendem três conjuntos de artefatos com graus distintos "
"de maturidade. O primeiro conjunto, de natureza estrutural, abrange a formalização arquitetural completa do “framework” PrivacyScope, "
"incluindo as interfaces abstratas das seis camadas, o protocolo declarativo YAML, o registry de plugins e a documentação técnica "
"versionada no repositório público (https://github.com/cristianosilverio/privacyscope). O segundo conjunto, de natureza operacional, "
"compreende a implementação concluída do MVP funcional do “pipeline” em linguagem Python, disponibilizado como pacote instalável e "
"acessível por interface de linha de comando, com execuções de teste em ambiente real e cadeia de custódia "
"das evidências validada por “hash” criptográfico em cascata. O terceiro conjunto, de natureza empírica preliminar, apresenta os "
"primeiros resultados quantitativos da aplicação do “pipeline” sobre sites institucionais brasileiros, ainda em escala reduzida.")

subheading("Coleta piloto: composição e cobertura da amostra")

p("A coleta piloto foi executada em 20 de maio de 2026 sobre uma lista de 59 domínios candidatos — 48 do estrato empresarial e "
"11 do governamental —, gerada por amostragem aleatória estratificada com semente fixa a partir da Tranco List filtrada por .br. "
"Do conjunto de candidatos, 49 domínios (39 empresariais e 10 governamentais) foram coletados com sucesso, constituindo a amostra "
"efetiva analisada nesta etapa. Os dez domínios não coletados distribuíram-se em quatro causas, todas registradas na trilha de "
"auditoria do “framework”: seis por não resolução de DNS (domínios outrora ranqueados, atualmente inativos), dois por proibição "
"explícita no arquivo robots.txt — respeitada pelo coletor —, um por recusa de conexão e um por certificado TLS inválido. Esta "
"última ocorrência, observada em um portal estadual de saúde, constitui em si um achado de conformidade relevante: um sítio "
"público que trata dados sensíveis apresentando cadeia de certificação inválida. A taxa de atrito observada (aproximadamente 17%) "
"é coerente com a rotatividade de domínios característica de rankings de popularidade da Web e fundamenta empiricamente a adoção "
"de uma margem de candidatos excedentes no dimensionamento operacional da coleta.")

p("A amostra efetiva (n = 49) é composta majoritariamente por sítios de cauda longa de popularidade — comportamento esperado em "
"amostragem aleatória voltada ao panorama geral, que reflete a composição real do tecido digital brasileiro, e não apenas seus "
"portais mais proeminentes. A Tabela 2 apresenta as frequências observadas das três variáveis técnicas determinísticas, no "
"conjunto e por estrato.")

caption("Tabela 2. Frequência de presença das variáveis técnicas na coleta piloto (n = 49)", before=4, after=2)

freq_table = doc.add_table(rows=1, cols=4)
freq_table.style = "Table Grid"
hdrf = freq_table.rows[0].cells
for i, txt in enumerate(["Variável técnica", "Total (n = 49)", "Governo (n = 10)", "Empresa (n = 39)"]):
    hdrf[i].text = ""
    par = hdrf[i].paragraphs[0]
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.line_spacing = 1.0
    r = par.add_run(txt)
    _set_run(r, bold=True, size=10)

freq_rows = [
    ("tem_banner_cookies", "40,8% (20)", "30,0% (3)", "43,6% (17)"),
    ("tem_politica_privacidade", "59,2% (29)", "50,0% (5)", "61,5% (24)"),
    ("tem_canal_titular", "20,4% (10)", "30,0% (3)", "17,9% (7)"),
]
for row in freq_rows:
    cells = freq_table.add_row().cells
    for i, txt in enumerate(row):
        cells[i].text = ""
        par = cells[i].paragraphs[0]
        par.alignment = WD_ALIGN_PARAGRAPH.LEFT if i == 0 else WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.line_spacing = 1.0
        r = par.add_run(txt)
        _set_run(r, size=10)

caption("Fonte: Resultados originais da pesquisa", before=2, after=10)

p("Os números reportados na Tabela 2 incorporam um refinamento iterativo dos detectores conduzido sobre a amostra de desenvolvimento, descrito mais adiante. Na execução inicial dos detectores (versão 0.1.0) sobre os mesmos 49 sítios, observaram-se frequências significativamente diferentes: banner de cookies em 79,6% da amostra, política de privacidade em 67,3% e canal do titular em 22,4%. A discrepância mais visível, no banner, decorria de marcações residuais de cookies presentes no DOM mas não renderizadas como banner efetivamente exibido ao usuário, configurando falsos positivos sistemáticos. Após o ciclo de rotulagem manual cega, análise de erro por classes e refinamento direcionado — com introdução do filtro de visibilidade no banner, qualificação por conteúdo na política e critério do Encarregado no canal — as prevalências passaram aos valores hoje reportados, mais conservadores e defensáveis: 40,8%, 59,2% e 20,4%, respectivamente.")

p("Os números refinados sustentam uma leitura mais cuidadosa do panorama. A presença de banner de cookies, agora medida em 40,8% e praticamente idêntica entre os estratos, deixa de aparecer como prática consolidada universalmente: cerca de três em cada cinco sítios da amostra de desenvolvimento não apresentam banner efetivamente renderizado, mesmo entre aqueles que carregam código relacionado a consentimento. A política de privacidade segue presente em pouco mais da metade da amostra (59,2%), com leve predominância do estrato empresarial. O canal do titular permanece como a variável de menor incidência (20,4%) e o único item em que o estrato governamental superou nitidamente o empresarial (30,0% contra 17,9%), resultado coerente com a obrigação, mais diretamente cobrada do setor público, de designar Encarregado pelo tratamento de dados pessoais (Lei nº 13.709/2018, art. 41). Quanto às plataformas de gestão de consentimento, foram identificadas assinaturas de dois fornecedores comerciais distintos no conjunto, CookieConsent em quatro sítios e Quantcast Choice em dois, evidência de adoção de soluções estabelecidas de mercado por parte dos sítios brasileiros.")

subheading("Refinamento iterativo: ciclo metodológico e split derivação/validação")

p("O ciclo de desenvolvimento adotado é, em si, parte central da contribuição metodológica deste trabalho. A sequência piloto → rotulagem cega independente como rotulagem manual de referência, análise de erro por classes → refinamento direcionado dos detectores, análise de sensibilidade dos limiares → revalidação sobre a amostra refinada permitiu identificar e tratar falsos positivos estruturais que não seriam visíveis sem confronto humano , em particular marcações de cookie presentes no DOM mas não renderizadas (caso de banners GDPR geo-restritos a usuários europeus, inertes em sites brasileiros); classificação errada por contato genérico ao invés do contato específico do Encarregado, e ausência do tier de qualificação por conteúdo na detecção da política. Cada classe de erro foi documentada, transformada em regra computacional ajustada e revalidada empiricamente, com a externalização das listas e limiares em configuração separada do código garantindo que cada refinamento permaneça revisável e reproduzível por terceiros.")

p("Adota-se separação explícita entre derivação e validação: a amostra de desenvolvimento (n = 49) constitui o conjunto de desenvolvimento, sobre o qual valores derivados da própria amostra (vocabulários, listas de exclusão, limiares) foram ajustados; sua validade externa só será verificada sobre uma subamostra de validação independente, formalmente cega e independente do conjunto de desenvolvimento. Para as três variáveis textualmente complexas (direitos do titular explicados, finalidade especificada e transferência internacional divulgada), o refinamento por regras é, por desenho, transitório: será superado por classificadores supervisionados, treinados sobre subconjunto rotulado e avaliados em conjunto de teste independente, com as métricas de desempenho consolidadas, precisão, revocação, F1 e kappa, reportadas na versão final do documento, prevista para submissão em 16 de junho de 2026.")

# ---------------------- CONSIDERAÇÕES FINAIS ---------------------------
subheading("Validação do desempenho por rotulagem manual cega do piloto (n = 48)")

p("A validação do desempenho dos detectores refinados foi conduzida por rotulagem manual cega da totalidade da amostra de desenvolvimento (n = 48 sítios coletáveis, após exclusão de um sítio indisponível). A rotulagem aplicou os mesmos critérios formais definidos no protocolo, sem acesso aos resultados produzidos pelo framework, e foi conduzida pelo próprio autor, anotador único, sobre rótulos binários para cada uma das três variáveis determinísticas. A Tabela 3 apresenta as métricas de concordância humano-vs-algoritmo, calculadas a partir da matriz de confusão de cada variável: a acurácia global, precisão, revocação, F1 e coeficiente kappa de Cohen.")

caption("Tabela 3. Métricas de concordância entre detecção automatizada e rotulagem manual cega da amostra de desenvolvimento (n = 48)", before=4, after=2)

val_table = doc.add_table(rows=1, cols=6)
val_table.style = "Table Grid"
hdrv = val_table.rows[0].cells
for i, txt in enumerate(["Variável técnica", "Acurácia", "Precisão", "Revocação", "F1", "Kappa"]):
    hdrv[i].text = ""
    par = hdrv[i].paragraphs[0]
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.line_spacing = 1.0
    r = par.add_run(txt)
    _set_run(r, bold=True, size=10)

val_rows = [
    ("tem_banner_cookies", "0,958", "1,000", "0,909", "0,952", "0,915"),
    ("tem_politica_privacidade", "0,958", "0,966", "0,966", "0,966", "0,913"),
    ("tem_canal_titular", "0,979", "1,000", "0,909", "0,952", "0,939"),
]
for row in val_rows:
    cells = val_table.add_row().cells
    for i, txt in enumerate(row):
        cells[i].text = ""
        par = cells[i].paragraphs[0]
        par.alignment = WD_ALIGN_PARAGRAPH.LEFT if i == 0 else WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.line_spacing = 1.0
        r = par.add_run(txt)
        _set_run(r, size=10)

caption("Fonte: Resultados originais da pesquisa", before=2, after=0)
caption("Nota: coeficiente kappa não definido para política por ausência de variância negativa na subamostra", before=0, after=10)

p("A variável de política de privacidade alcançou concordância integral (F1 = 1,000) após o refinamento do vocabulário de detecção "
"de subpáginas. A variável de banner de cookies registrou revocação plena (1,000) e precisão de 0,778, refletindo os falsos "
"positivos já discutidos. A variável de canal do titular apresentou precisão plena (1,000) mas revocação de 0,625, confirmando a "
"tendência a falsos negativos. Os valores baixos do coeficiente kappa, incluindo sua indefinição para a variável de política, "
"decorrem da composição da subamostra de validação, fortemente concentrada em sítios que de fato possuem os atributos avaliados "
"(escassez de verdadeiros negativos), o que torna o kappa instável e pouco informativo nesta escala — limitação que será superada "
"na validação formal, conduzida sobre subamostra de maior diversidade.")

subheading("Expansão para n = 200: amostra ampliada e estabilidade do instrumento")

p("A expansão da coleta para n = 200 foi conduzida sobre amostra estratificada extraída da Tranco List versão de maio de 2026, com alocação alvo de 160 unidades empresariais e 40 governamentais (proporção 80/20), sobre-representação deliberada do estrato governamental, dado seu interesse central para a finalidade de apoio à etapa de Monitoramento. A coleta principal de 258 candidatos rendeu 203 sucessos (175 empresariais e 28 governamentais); a recoleta das 55 falhas com o coletor endurecido (tolerância a certificado e fallback de www) recuperou 11 sítios adicionais; e um sorteio suplementar reproduzível, da mesma lista Tranco e excluindo os 50 governamentais já usados, forneceu 15 sítios extras, fechando a amostra efetiva em 160 + 40 = 200 sítios, registrada em arquivo CSV versionado.")

p("Um achado substantivo emergiu da atrição de coleta no estrato governamental: 17 dos 50 domínios sorteados (34%) estavam mortos ou inacessíveis mesmo após endurecer o coletor — DNS de apex não-resolvível (órgãos migrados para o portal unificado gov.br), timeout de conexão, certificado inválido ou conexão recusada. Esta fragilidade da infraestrutura web governamental é, em si, um indicador relevante para o exercício de monitoramento — a própria população-alvo apresenta lacunas de disponibilidade que comprometem a observabilidade externa.")

p("A comparação direta das prevalências entre a amostra de desenvolvimento (n = 49) e a amostra ampliada (n = 200), conduzida com o mesmo instrumento (detectores e parâmetros idênticos), permite avaliar a estabilidade do instrumento na transição da amostra de desenvolvimento para uma amostra independente quatro vezes maior. A Tabela 4 sintetiza essa comparação, com intervalos de confiança de Wilson a 95% e teste z de duas proporções.")

caption("Tabela 4. Comparação de prevalências entre a amostra de desenvolvimento (n = 49) e a amostra ampliada (n = 200), mesmo instrumento e amostras independentes", before=4, after=2)
b7_table = doc.add_table(rows=1, cols=5)
b7_table.style = "Table Grid"
b7_hdr = b7_table.rows[0].cells
for i, txt in enumerate(["Variável técnica", "Amostra desenv. (n = 49)", "Amostra ampliada (n = 200)", "Δ (pontos %)", "p (z)"]):
    b7_hdr[i].text = ""
    par = b7_hdr[i].paragraphs[0]
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.line_spacing = 1.0
    r = par.add_run(txt); _set_run(r, bold=True, size=10)
set_repeat_header(b7_table)
b7_rows = [
    ("tem_banner_cookies", "40,8% [28,2-54,8]", "46,5% [39,7-53,4]", "+5,7", "0,474"),
    ("tem_politica_privacidade", "59,2% [45,2-71,8]", "52,5% [45,6-59,3]", "−6,7", "0,400"),
    ("tem_canal_titular", "20,4% [11,5-33,6]", "22,5% [17,3-28,8]", "+2,1", "0,752"),
]
for row in b7_rows:
    cells = b7_table.add_row().cells
    for i, txt in enumerate(row):
        cells[i].text = ""
        par = cells[i].paragraphs[0]
        par.alignment = WD_ALIGN_PARAGRAPH.LEFT if i == 0 else WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.line_spacing = 1.0
        r = par.add_run(txt); _set_run(r, size=10)
caption("Fonte: Resultados originais da pesquisa", before=2, after=10)

p("Nenhuma das diferenças entre as duas amostras é estatisticamente significativa (p > 0,4 para os três detectores); as estimativas pontuais da amostra ampliada caem dentro dos intervalos de confiança da amostra de desenvolvimento e vice-versa. Esta concordância é evidência de estabilidade do instrumento: os detectores cujos limiares e vocabulários foram refinados sobre a amostra de desenvolvimento produzem prevalências consistentes em uma amostra independente quatro vezes maior, sem deriva agregada, sinal de ausência de sobreajuste grosseiro na prevalência. Estratificando a amostra ampliada por sufixo de domínio, o estrato governamental superou o empresarial nos três detectores, com diferença estatisticamente significativa no canal do titular (37,5% contra 18,8%; z = +2,54; p = 0,011) e marginal no banner (p = 0,056), coerente com a obrigação de divulgação do Encarregado pelos órgãos públicos. A distribuição de confiança da detecção na amostra ampliada foi alta na grande maioria dos casos, sem rótulos de baixa confiança ou indeterminados.")

p("Cumpre ressalvar que a comparação descrita afere prevalências, não acurácia: a concordância entre as duas amostras atesta estabilidade do instrumento, mas não verifica que as detecções estão corretas na amostra ampliada. As métricas defensáveis de precisão, revocação, F1 e kappa para a amostra ampliada virão da rotulagem cega de uma subamostra de validação independente, etapa subsequente, seguindo o mesmo protocolo aplicado ao piloto.")

heading("Considerações Finais")

p("Os resultados parciais consolidados nesta etapa indicam compatibilidade estrutural entre o “framework” PrivacyScope e as "
"finalidades informacionais da etapa de Monitoramento prevista na Resolução CD/ANPD nº 1/2021. A arquitetura desacoplada e "
"parametrizável, formalizada em interfaces abstratas e governada por protocolo declarativo versionado, permite que critérios "
"e parâmetros sejam ajustados externamente sem alteração do núcleo do sistema — propriedade verificada empiricamente na coleta "
"piloto (Tabela 2) e na execução repetida de variações do protocolo sobre o mesmo conjunto de evidências brutas. "
"A composição modular de plugins, materializada no registry declarativo, sustenta o requisito de extensibilidade frente a "
"refinamentos futuros, incluindo a incorporação de variáveis técnicas adicionais, fontes amostrais alternativas e classificadores "
"de aprendizado supervisionado, sem necessidade de refatoração das camadas estruturais.")

p("Cinco limitações estruturais merecem registro explícito. Primeiro, um ponto cego em arquivos PDF: contato do Encarregado e política de privacidade publicados unicamente dentro de arquivos PDF não são processados pelo pipeline atual, gerando falsos negativos para sítios com essa prática. Segundo, banners de cookies geo-restritos a usuários da União Europeia deixam código técnico inerte no DOM de sítios brasileiros, fonte sistemática de falsos positivos quando a detecção se baseia apenas no código; essa limitação é tratada pelo filtro de visibilidade implementado nos detectores. Terceiro, contatos de processador são distinguidos do contato do controlador por uma lista de exclusão de provedores de infraestrutura, ou seja, e-mails de Encarregado de provedor de CDN ou SaaS embarcados em código modelo padrão são descartados; o desenho futuro ideal é a constituição de uma lista permitida por controlador, derivada da identificação do responsável pelo tratamento. Quarto, os refinamentos foram derivados sobre a amostra de desenvolvimento e há risco residual de sobreajuste, mitigado pela análise de sensibilidade, que indicou limiares numéricos sem efeito determinante sobre as métricas na amostra atual, e pela revalidação prevista na subamostra de validação independente. Quinto, erros residuais permanecem mesmo após o refinamento, todos com causa documentada, e fundamentam a transição do regime determinístico para classificadores supervisionados nas variáveis textualmente complexas.")

p("A expansão da coleta para n = 200 revelou ainda um achado substantivo sobre a população-alvo: 34% dos domínios governamentais sorteados encontram-se mortos ou inacessíveis mesmo após o endurecimento do coletor; isso constitui um indicador relevante para o exercício de monitoramento na medida em que a observabilidade externa do estrato governamental — justamente aquele sob maior obrigação de transparência institucional, é, ela mesma, comprometida pela fragilidade da infraestrutura web. As próximas etapas comportam, além da rotulagem manual cega da subamostra de validação independente e do treinamento dos classificadores supervisionados, uma análise de aderência do framework aos dispositivos da Resolução da Autoridade Nacional de Proteção de Dados aplicável ao processo fiscalizatório, análise que, dadas as limitações de tempo e tamanho do trabalho, será conduzida por amostra intencional dos dispositivos cuja verificação depende de sinais publicamente observáveis em websites institucionais, com ampliação para cobertura integral caso o cronograma permita.")

p("A coleta piloto realizada permitiu observar, em escala reduzida, indicadores descritivos das práticas de transparência nos "
"sítios brasileiros ativos: comunicação sobre cookies já consolidada, política de privacidade presente em cerca de dois terços "
"da amostra, e canal de atendimento ao titular como o elemento de menor incidência — sugerindo que a operacionalização do "
"exercício de direitos previsto na legislação permanece o aspecto menos maduro entre as organizações analisadas. Tais leituras "
"são preliminares e condicionadas às características de desempenho de cada detector, conforme discutido. As frentes subsequentes "
"do trabalho — expansão da coleta à amostra dimensionada, validação formal do desempenho, treinamento dos classificadores "
"supervisionados e discussão conceitual-normativa da aderência institucional — consolidarão os resultados na versão final do "
"documento. Preserva-se, ao longo de todo o desenho, a distinção fundamental entre a evidência técnica observável, que o "
"“framework” produz, e o juízo jurídico de conformidade, que permanece atribuição da autoridade competente. A versão consolidada "
"está prevista para entrega ao orientador em 31 de maio de 2026 e submissão à plataforma "
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

ref("AGÊNCIA NACIONAL DE PROTEÇÃO DE DADOS [ANPD]. 2022. Guia Orientativo: Cookies e Proteção de Dados Pessoais. Brasília, DF. Disponível em: <https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia-orientativo-cookies-e-protecao-de-dados-pessoais.pdf/@@display-file/file>. Acesso em: 05 jun. 2026.")

ref("ASSOCIAÇÃO BRASILEIRA DE NORMAS TÉCNICAS. ABNT NBR ISO/IEC 27037:2013 — Tecnologia da informação: técnicas de segurança: diretrizes para identificação, coleta, aquisição e preservação de evidência digital. Rio de Janeiro: ABNT, 2013.")

ref("BRASIL. Lei nº 13.709, de 14 de agosto de 2018. Lei Geral de Proteção de Dados Pessoais (LGPD). Diário Oficial da União: seção 1, Brasília, DF, 15 ago. 2018.")

ref("BRASIL. Autoridade Nacional de Proteção de Dados. Resolução CD/ANPD nº 1, de 28 de outubro de 2021. Aprova o Regulamento do Processo de Fiscalização e do Processo Administrativo Sancionador no âmbito da ANPD. Diário Oficial da União: seção 1, Brasília, DF, 29 out. 2021.")

ref("BRASIL. Autoridade Nacional de Proteção de Dados. Resolução CD/ANPD nº 4, de 24 de fevereiro de 2023. Aprova o Regulamento de Dosimetria e Aplicação de Sanções Administrativas. Diário Oficial da União: seção 1, Brasília, DF, 27 fev. 2023.")

ref("BRASIL. Lei nº 15.352, de 25 de fevereiro de 2026. Transforma a Autoridade Nacional de Proteção de Dados em Agência Nacional de Proteção de Dados. Diário Oficial da União: edição extra, Brasília, DF, 25 fev. 2026.")

ref("BRASIL. Decreto nº 5.296, de 2 de dezembro de 2004. Regulamenta as Leis nº 10.048/2000 e nº 10.098/2000, estabelecendo normas gerais e critérios básicos para a promoção da acessibilidade. Diário Oficial da União: Brasília, DF, 3 dez. 2004.")

ref("BRASIL. Lei nº 13.146, de 6 de julho de 2015. Institui a Lei Brasileira de Inclusão da Pessoa com Deficiência (Estatuto da Pessoa com Deficiência). Diário Oficial da União: Brasília, DF, 7 jul. 2015.")

ref("BRASIL. Conselho Nacional de Saúde. Resolução CNS nº 510, de 7 de abril de 2016. Dispõe sobre as normas aplicáveis a pesquisas em Ciências Humanas e Sociais. Diário Oficial da União: seção 1, Brasília, DF, 24 maio 2016.")

ref("eMAG. 2014. Modelo de Acessibilidade em Governo Eletrônico — versão 3.1. Departamento de Governo Eletrônico, Ministério do Planejamento, Orçamento e Gestão. Brasília, DF.")

ref("CASEY, E. 2011. Digital Evidence and Computer Crime: Forensic science, computers and the internet. 3ed. Academic Press, Waltham, MA, USA.")

ref("COCHRAN, W. G. 1977. Sampling Techniques. 3ed. John Wiley & Sons, New York, NY, USA.")

ref("COHEN, J. 1960. A coefficient of agreement for nominal scales. Educational and Psychological Measurement 20(1): 37-46. DOI: 10.1177/001316446002000104.")

ref("DABROWSKI, A.; MERZDOVNIK, G.; ULLRICH, J.; SENDERA, G.; WEIPPL, E. 2019. Measuring cookies and web privacy in a post-GDPR world. In: Privacy Technologies and Policy. Springer, Cham, Switzerland.")

ref("FEINSTEIN, A. R.; CICCHETTI, D. V. 1990. High agreement but low kappa: I. The problems of two paradoxes. Journal of Clinical Epidemiology 43(6): 543-549. DOI: 10.1016/0895-4356(90)90158-L.")

ref("HORMOZI, A. M. 2006. Cookies and privacy. Information Systems Security 13(6): 51-59.")

ref("JAVED, Y.; SAJID, A. 2024. A systematic review of privacy policy literature. ACM Computing Surveys 57(4): 1-43. DOI: 10.1145/3698393.")

ref("KOLEY, S.; BHARATHI, S. V. 2021. Prioritizing and ranking the taxonomy of factors critical to GDPR compliance. Journal of Physics: Conference Series 1964 042074. DOI: 10.1088/1742-6596/1964/4/042074.")

ref("KOSTER, M.; ILLYES, G.; ZELLER, H.; SASSMAN, L. 2022. RFC 9309: Robots Exclusion Protocol. Internet Engineering Task Force (IETF). DOI: 10.17487/RFC9309. Disponível em: https://www.rfc-editor.org/rfc/rfc9309. Acesso em: 20 maio 2026.")

ref("LANDIS, J. R.; KOCH, G. G. 1977. The measurement of observer agreement for categorical data. Biometrics 33(1): 159-174. DOI: 10.2307/2529310.")

ref("LE POCHAT, V.; VAN GOETHEM, T.; TAJALIZADEHKHOOB, S.; KORCZYŃSKI, M.; JOOSEN, W. 2019. Tranco: a research-oriented top sites ranking hardened against manipulation. In: Proceedings of the 26th Network and Distributed System Security Symposium (NDSS 2019), San Diego, CA, USA.")

ref("LODGE, M.; WEGRICH, K. (eds.). 2014. The Problem-solving Capacity of the Modern State: Governance challenges and administrative capacities. Oxford University Press, Oxford, UK.")

ref("MARTIN, R. C. 2000. Design Principles and Design Patterns. Object Mentor.")

ref("MORI, K.; NAGAI, T.; TAKATA, Y.; KAMIZONO, M.; MORI, T. 2023. Analysis of privacy compliance by classifying policies before and after the Japanese law revision. Journal of Information Processing 31: 829-841. DOI: 10.2197/ipsjjip.31.829.")

ref("OECD. 2013. Recommendation of the Council concerning Guidelines Governing the Protection of Privacy and Transborder Flows of Personal Data. OECD/LEGAL/0188. OECD, Paris, France.")

ref("OWASP. n.d. OWASP Top 10 Privacy Risks Countermeasures v2.0. OWASP Foundation.")

ref("PANTELIC, O.; JOVIC, K.; KRSTOVIC, S. 2022. Cookies implementation analysis and the impact on user privacy regarding GDPR and CCPA regulations. Sustainability 14(9): 5015. DOI: 10.3390/su14095015.")

ref("RASAII, A.; SINGH, S.; GOSAIN, D.; GASSER, O. 2023. Exploring the Cookieverse: a multi-perspective analysis of web cookies. In: Passive and Active Measurement (PAM). Springer, Cham, Switzerland.")

ref("Silverio, C.G. 2026. PrivacyScope: framework computacional para apoio à etapa de Monitoramento da ANPD. Disponível em: <https://github.com/cristianosilverio/privacyscope>. Acesso em: 02 jun. 2026.")

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
