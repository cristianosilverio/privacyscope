# -*- coding: utf-8 -*-
"""
Constrói o documento Resultados Preliminares V1 a partir do template oficial.
Preserva: cabeçalho USP/ESALQ, paginação, margens.
Reescreve: todo o corpo com o conteúdo do trabalho.
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
OUTPUT   = "/sessions/peaceful-lucid-edison/mnt/TCC/Resultados Preliminares - Cristiano Gouveia Silverio - V1.docx"
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
"aderência à ABNT NBR ISO/IEC 27037:2013. A amostragem combinou a Tranco List filtrada pelo TLD .br e a listagem oficial do Portal "
"Gov.br, em desenho estratificado. Foi definida bateria inicial de seis variáveis técnicas — quatro detectadas por regras "
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

subheading("Dataset: universo amostral e amostragem")

p("O universo amostral é constituído por domínios ativos sob o TLD .br, restritos a websites institucionais empresariais e "
"governamentais. A composição da amostra adota como fonte primária a Tranco List (LE POCHAT et al., 2019), uma listagem ranqueada e "
"reprodutível de domínios construída sobre múltiplas fontes (Cisco Umbrella, Cloudflare Radar, Majestic e Farsight), com "
"versionamento mensal e identificação por hash, amplamente utilizada em pesquisa de privacidade web por sua resistência a "
"manipulação e por seu uso em estudos revisados por pares. A versão de maio de 2026 foi filtrada para o TLD .br, gerando o quadro "
"amostral inicial. Para o estrato governamental, a Tranco List foi complementada pela listagem oficial de domínios .gov.br mantida "
"no Portal Gov.br, ampliando a cobertura para órgãos da administração pública federal de baixa popularidade global. A escolha por "
"essa estratégia decorre da indisponibilidade da fonte originalmente prevista no projeto — listagem institucional do NIC.br — cuja "
"solicitação formal não foi atendida. O desenho adotado preserva os requisitos de representatividade, neutralidade setorial e "
"reprodutibilidade metodológica.")

p("A amostragem é estratificada com alocação proporcional entre os dois estratos. O tamanho da amostra foi dimensionado pela fórmula "
"clássica de estimação de proporções para população infinita, considerando nível de confiança de 95%, margem de erro de 5% e "
"estimativa conservadora p̂ = 0,50, resultando em n ≈ 384 unidades. Para os Resultados Preliminares aqui reportados, uma amostra "
"piloto reduzida (n = 50, sendo 25 sites do estrato governamental e 25 do estrato empresarial) foi extraída por amostragem "
"aleatória simples dentro de cada estrato, com o propósito de validar o pipeline operacional e calibrar os parâmetros das regras "
"determinísticas. A expansão para n = 384 está prevista para a próxima etapa do trabalho, conforme cronograma.")

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
     "inventário estruturado dos cookies fixados em fases distintas (pré-consent e pós-consent), com nome, domínio, expiração e flags (Secure, HttpOnly, SameSite). O valor de cada cookie é armazenado em forma mascarada (truncamento aos 8 primeiros caracteres + comprimento original + hash SHA-256 truncado a 16 caracteres), preservando comparabilidade entre fases sem reter identificadores. Métricas derivadas (total, terceiros, persistentes, percentual com Secure) são calculadas em pós-processamento",
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

p("Os Resultados Preliminares consolidados até o fechamento desta versão referem-se à concepção e formalização da arquitetura do "
"framework, à especificação operacional das variáveis técnicas e à validação do desenho amostral, conforme apresentado na seção "
"anterior. A execução da coleta piloto sobre n = 50 sites, programada para 28 de maio de 2026, fornecerá as primeiras estatísticas "
"descritivas de frequências e distribuições das variáveis, bem como os primeiros valores de métricas de desempenho do pipeline "
"determinístico. A expansão da coleta para n = 384 sites e o treinamento dos classificadores supervisionados sobre o ground truth "
"manual estão previstos para o intervalo de 1º a 10 de junho de 2026, com incorporação completa das métricas e resultados "
"descritivos na versão revisada deste documento.")

p("Os artefatos consolidados nesta etapa compreendem: (i) a especificação arquitetural do framework PrivacyScope, formalizada em "
"interfaces abstratas e protocolo declarativo YAML; (ii) a definição operacional de seis variáveis técnicas com regras "
"computacionais e respaldo normativo e acadêmico, conforme Tabela 1; (iii) a estratégia amostral validada, com Tranco List filtrada "
"por TLD .br e complementada pela listagem oficial Gov.br, em desenho estratificado; (iv) o procedimento de cadeia de custódia das "
"evidências brutas, em conformidade com ABNT NBR ISO/IEC 27037:2013. O repositório público do framework, com o código-fonte "
"versionado e instruções de reprodução, será disponibilizado em endereço a ser informado no Apêndice da versão final do trabalho.")

# ---------------------- CONSIDERAÇÕES FINAIS ---------------------------
heading("Considerações Finais")

p("Os resultados parciais consolidados nesta etapa indicam compatibilidade estrutural entre o framework PrivacyScope e as "
"finalidades informacionais da etapa de Monitoramento prevista na Resolução CD/ANPD nº 1/2021. A arquitetura desacoplada e "
"parametrizável permite que os critérios e parâmetros sejam ajustados externamente por meio do protocolo declarativo, atendendo ao "
"requisito de adaptabilidade a diferentes ciclos de monitoramento e orientações regulatórias futuras. Os próximos passos "
"contemplam a execução completa do pipeline sobre a amostra dimensionada, o treinamento e a validação dos classificadores "
"supervisionados, a análise de robustez e de reprodutibilidade do framework, e a discussão conceitual-normativa da aderência da "
"ferramenta às finalidades institucionais da autoridade.")

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
# O template tem em word/header1.xml o texto:
#   " _________ (Nome do curso) – ____ (ano da defesa)"
# que precisa virar " MBA em Data Science e Analytics – 2026".
# python-docx não acessa esse parágrafo facilmente; manipula-se o XML do header
# direto via zipfile para garantir que cada regeneração do docx preserve o ajuste.
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
