"""CsvSource — fonte amostral a partir de lista fornecida por quem executa.

POR QUE ESTA FONTE EXISTE
-------------------------
A fonte por ranque de popularidade serve ao desenho amostral da pesquisa. Nao serve
a quem executa o arcabouco contra a PROPRIA lista — um recorte setorial, um conjunto
de orgaos, os sitios de um processo de fiscalizacao ja instaurado. Sem ela, a unica
via era enumerar dominios em `override_domains` dentro do protocolo, o que para
duzentas linhas e transcricao manual, e transcricao manual e onde erro entra.

REPRODUTIBILIDADE DA ENTRADA
----------------------------
O quadro amostral integra a cadeia de custodia como qualquer outro insumo. O
protocolo pode declarar `sha256`, e o arquivo e conferido na leitura: divergencia
INTERROMPE, em lugar de executar sobre lista que nao e a declarada.

A conferencia e opcional porque a lista e de quem executa, e nem todo uso e de
pesquisa. Quando ausente, o resumo apurado vai para o registro, de sorte que se possa
declara-lo depois — mas ai a garantia e de rastreio, e nao de identidade.

O QUE ELA NAO FAZ
-----------------
Nao amostra. Devolve a lista inteira, na ordem do arquivo. Amostragem e desenho, nao
leitura de arquivo, e embuti-la aqui esconderia a decisao dentro de um plugin de
entrada — os programas de amostragem do repositorio existem para isso e produzem
registro proprio.

Uso no protocolo:

    sources:
      - name: csv
        params:
          path: listas/orgaos_estaduais.csv
          coluna_dominio: dominio      # opcional; tenta dominio, url, host, site
          coluna_estrato: estrato      # opcional
          sha256: 3f9a...              # opcional, mas conferido quando declarado
"""
from __future__ import annotations

import csv
import hashlib
import logging
from pathlib import Path
from typing import Any, ClassVar, Iterator

from privacyscope.core.interfaces import SampleSource
from privacyscope.core.types import Domain

logger = logging.getLogger(__name__)

CANDIDATAS_DOMINIO = ("dominio", "domínio", "url", "host", "site", "domain")
CANDIDATAS_ESTRATO = ("estrato", "stratum", "grupo", "setor")
CANDIDATAS_RANK = ("rank", "rank_tranco", "posicao", "ordem")


class ListaInvalidaError(ValueError):
    """Lista ausente, ilegivel, sem coluna de dominio ou de identidade divergente."""


def resumo_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def normaliza_host(bruto: str) -> str:
    """Aceita dominio nu ou endereco completo; devolve o host em minusculas."""
    s = (bruto or "").strip().strip('"').strip()
    for prefixo in ("https://", "http://"):
        if s.lower().startswith(prefixo):
            s = s[len(prefixo):]
    return s.split("/")[0].strip().lower()


def sufixo(host: str) -> str:
    """Sufixo efetivo, por tldextract quando disponivel; senao, heuristica.

    A heuristica cobre o caso brasileiro — dois rotulos finais em `.br` — e existe
    para que a fonte funcione sem a dependencia opcional. Ela e declarada porque
    devolve resultado distinto do extrator em dominios de sufixo composto fora do
    padrao previsto.
    """
    try:
        import tldextract
        s = tldextract.TLDExtract()(host).suffix
        if s:
            return "." + s
    except Exception:                                          # noqa: BLE001
        pass
    partes = host.split(".")
    if len(partes) >= 3 and partes[-1] == "br":
        return "." + ".".join(partes[-2:])
    return "." + partes[-1] if len(partes) > 1 else ".unknown"


class CsvSource(SampleSource):
    """Lista de dominios fornecida por quem executa."""

    name: ClassVar[str] = "csv"
    version: ClassVar[str] = "1.0.0"

    def list_domains(self, params: dict[str, Any]) -> Iterator[Domain]:
        caminho = params.get("path")
        if not caminho:
            raise ListaInvalidaError(
                "CsvSource exige params['path'] com o caminho da lista.")
        p = Path(caminho)
        if not p.is_absolute():
            p = Path(__file__).resolve().parents[3] / caminho
        if not p.is_file():
            raise ListaInvalidaError(f"lista nao encontrada: {p}")

        sha = resumo_arquivo(p)
        esperado = params.get("sha256")
        if esperado and sha != esperado:
            raise ListaInvalidaError(
                f"a lista {p.name} nao corresponde a declarada.\n"
                f"  declarado no protocolo: {esperado}\n"
                f"  encontrado no arquivo : {sha}\n"
                f"O quadro amostral integra a cadeia de custodia: executar sobre "
                f"lista distinta da declarada produziria resultado atribuido a um "
                f"universo que nao foi o empregado.")
        if not esperado:
            logger.warning("CsvSource: `sha256` nao declarado para %s; resumo "
                           "apurado: %s", p.name, sha)
        else:
            logger.info("CsvSource: lista %s conferida (%s)", p.name, sha[:16])

        delim = params.get("delimitador")
        with p.open(encoding=params.get("encoding", "utf-8-sig"), newline="") as fh:
            amostra = fh.read(8192)
            fh.seek(0)
            if not delim:
                # Vírgula e ponto e vírgula convivem em planilhas brasileiras; deixar
                # a deteccao ao Sniffer evita exigir do analista uma configuracao que
                # ele nao tem por que conhecer.
                try:
                    delim = csv.Sniffer().sniff(amostra, delimiters=";,\t").delimiter
                except csv.Error:
                    delim = ";" if amostra.count(";") > amostra.count(",") else ","
            leitor = csv.DictReader(fh, delimiter=delim)
            campos = [c.strip() for c in (leitor.fieldnames or [])]
            col = params.get("coluna_dominio") or _primeira(campos, CANDIDATAS_DOMINIO)
            if not col:
                raise ListaInvalidaError(
                    f"nao identifiquei a coluna de dominio em {p.name}. "
                    f"Colunas encontradas: {campos}. "
                    f"Declare `coluna_dominio` no protocolo.")
            col_estrato = params.get("coluna_estrato") or _primeira(campos, CANDIDATAS_ESTRATO)
            col_rank = params.get("coluna_rank") or _primeira(campos, CANDIDATAS_RANK)

            vistos: set[str] = set()
            emitidos = repetidos = vazios = 0
            for linha in leitor:
                host = normaliza_host((linha.get(col) or ""))
                if not host or "." not in host:
                    vazios += 1
                    continue
                if host in vistos:
                    repetidos += 1
                    continue
                vistos.add(host)
                rank = None
                if col_rank:
                    try:
                        rank = int(str(linha.get(col_rank) or "").strip())
                    except (TypeError, ValueError):
                        rank = None
                emitidos += 1
                yield Domain(
                    url=f"https://{host}",
                    tld=sufixo(host),
                    source_name=self.name,
                    rank=rank if (rank or 0) >= 1 else None,
                    stratum=(linha.get(col_estrato) or None) if col_estrato else None,
                )
        logger.info("CsvSource: %d dominios de %s (coluna %r); %d repetidos, "
                    "%d sem dominio valido", emitidos, p.name, col, repetidos, vazios)


def _primeira(campos: list[str], candidatas: tuple[str, ...]) -> str | None:
    baixo = {c.lower(): c for c in campos}
    for c in candidatas:
        if c in baixo:
            return baixo[c]
    return None
