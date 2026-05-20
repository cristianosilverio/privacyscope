"""
Amostragem estratificada do piloto B4 (n=50: 40 empresariais + 10 governamentais).

Lê a Tranco top-1M filtrada por .br (via TrancoSource), separa em estratos por
sufixo .gov.br, aplica heurística de exclusão, e amostra com semente fixa
mantendo a proporção 40/10 num buffer de 60 (48 empresariais + 12 governamentais).

A alocação NÃO é proporcional ao peso populacional dos estratos — é uma
sobre-representação deliberada do estrato governamental para garantir cobertura
analítica mínima, dado seu interesse central para a finalidade do trabalho
(apoio à etapa de Monitoramento da ANPD). Cf. seção de amostragem do documento.

Saída: protocols/b4_sample.csv (60 candidatos) para REVISÃO MANUAL antes de
gerar o protocolo de coleta. NÃO gera o b4.yaml automaticamente.

Uso::

    python scripts/sample_b4.py --list-id <ID_TRANCO> \\
        --out protocols/b4_sample.csv

O <ID_TRANCO> é o identificador de uma lista gerada em https://tranco-list.eu
(garante reprodutibilidade — a lista fica congelada e versionada por hash).
"""

from __future__ import annotations

import argparse
import csv
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import tldextract


# Semente fixa de amostragem (data da decisão) — reprodutibilidade.
DEFAULT_SEED = 20260520

# Buffer mantendo proporção 40/10 (folga para falhas de coleta).
DEFAULT_N_CORP = 48
DEFAULT_N_GOV = 12

# Heurística de exclusão (lista mínima — usuário complementa na revisão manual).
# Substrings de domínio típicas de encurtadores, CDNs e assets — não são
# websites institucionais analisáveis.
DEFAULT_EXCLUDED_SUBSTRINGS = [
    "bit.ly", "t.co", "goo.gl", "ow.ly", "tinyurl",
    "cloudfront", "akamai", "fastly", "edgekey", "edgesuite",
    "mlstatic", "gstatic", "googleusercontent",
]


@dataclass
class SampleReport:
    """Resultado da amostragem, com diagnóstico para auditoria."""
    corp: list = field(default_factory=list)   # list[Domain] amostrados
    gov: list = field(default_factory=list)
    total_br: int = 0
    total_gov_available: int = 0
    total_corp_available: int = 0
    excluded_count: int = 0
    deduped_count: int = 0
    gov_shortfall: bool = False  # True se não havia gov suficiente


def _registered_domain(domain_str: str, extract: "tldextract.TLDExtract") -> str:
    """Retorna o domínio registrável (ex.: www.uol.com.br -> uol.com.br)."""
    ext = extract(domain_str)
    if ext.registered_domain:
        return ext.registered_domain.lower()
    return domain_str.lower()


def _is_excluded(domain_str: str, excluded_substrings: list[str]) -> bool:
    d = domain_str.lower()
    return any(sub in d for sub in excluded_substrings)


# Prefixos de PRIMEIRO LABEL que indicam subdomínio de infraestrutura (não
# site institucional navegável). Detectado no pré-piloto B4: ns4.to.gov.br
# (name server) entrou na amostra. Cobre name servers, mail, hosting, etc.
_INFRA_LABEL_RE = re.compile(
    r"^(ns\d*|dns\d*|mx\d*|smtp\d*|pop\d*|imap\d*|mail\d*|webmail|ftp\d*|sftp|"
    r"cpanel|webdisk|autodiscover|autoconfig|vpn|gateway|proxy|relay)$",
    re.IGNORECASE,
)


def _is_infrastructure_subdomain(host: str) -> bool:
    """True se o primeiro label do host for prefixo de infraestrutura.

    Ex.: ns4.to.gov.br -> primeiro label 'ns4' -> True (name server, não site).
    """
    first_label = host.split(".", 1)[0]
    return bool(_INFRA_LABEL_RE.match(first_label))


def stratify_and_sample(
    domains: list,
    *,
    n_corp: int = DEFAULT_N_CORP,
    n_gov: int = DEFAULT_N_GOV,
    seed: int = DEFAULT_SEED,
    excluded_substrings: list[str] | None = None,
    extract: "tldextract.TLDExtract | None" = None,
) -> SampleReport:
    """Separa em estratos, deduplica, exclui e amostra. Função pura testável.

    Args:
        domains: lista de Domain (na ordem do ranque Tranco).
        n_corp, n_gov: tamanhos-alvo do buffer por estrato.
        seed: semente do gerador aleatório.
        excluded_substrings: substrings de domínio a excluir.
        extract: instância TLDExtract (injetável para teste offline).

    Returns:
        SampleReport com os amostrados e diagnóstico.
    """
    if excluded_substrings is None:
        excluded_substrings = DEFAULT_EXCLUDED_SUBSTRINGS
    if extract is None:
        extract = tldextract.TLDExtract()

    report = SampleReport()
    seen_registered: set[str] = set()
    gov_pool: list = []
    corp_pool: list = []

    for dom in domains:
        host = dom.url.replace("https://", "").replace("http://", "").rstrip("/").lower()
        report.total_br += 1

        if _is_excluded(host, excluded_substrings) or _is_infrastructure_subdomain(host):
            report.excluded_count += 1
            continue

        reg = _registered_domain(host, extract)
        if reg in seen_registered:
            report.deduped_count += 1
            continue
        seen_registered.add(reg)

        if host.endswith(".gov.br"):
            gov_pool.append(dom)
        else:
            corp_pool.append(dom)

    report.total_gov_available = len(gov_pool)
    report.total_corp_available = len(corp_pool)

    rng = random.Random(seed)
    # Amostragem aleatória simples dentro de cada estrato.
    report.corp = rng.sample(corp_pool, min(n_corp, len(corp_pool)))
    if len(gov_pool) >= n_gov:
        report.gov = rng.sample(gov_pool, n_gov)
    else:
        # Plano B: usa todos os governamentais disponíveis (já está percorrendo
        # o top-1M inteiro — não há mais de onde tirar nesta fonte).
        report.gov = list(gov_pool)
        report.gov_shortfall = True

    return report


def write_csv(report: SampleReport, out_path: Path) -> None:
    """Escreve o CSV de candidatos para revisão manual."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ordem", "estrato", "rank_tranco", "dominio", "url", "aprovado"])
        ordem = 0
        for stratum, items in (("governamental", report.gov), ("empresarial", report.corp)):
            for dom in items:
                ordem += 1
                host = dom.url.replace("https://", "").rstrip("/")
                rank = getattr(dom, "rank", "") or ""
                # coluna 'aprovado' em branco para o revisor marcar
                w.writerow([ordem, stratum, rank, host, dom.url, ""])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--list-id", required=True, help="ID da lista Tranco (tranco-list.eu)")
    p.add_argument("--out", type=Path, default=Path("protocols/b4_sample.csv"))
    p.add_argument("--n-corp", type=int, default=DEFAULT_N_CORP)
    p.add_argument("--n-gov", type=int, default=DEFAULT_N_GOV)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--top-n", type=int, default=1_000_000)
    args = p.parse_args()

    # Import tardio para não exigir o pacote em testes da função pura.
    from privacyscope.sources.tranco import TrancoSource

    src = TrancoSource()
    print(f"Carregando Tranco list_id={args.list_id} top_n={args.top_n} filtro=.br ...")
    domains = list(src.list_domains({
        "list_id": args.list_id,
        "top_n": args.top_n,
        "tld_filters": [".br"],
    }))
    print(f"  domínios .br carregados: {len(domains)}")

    report = stratify_and_sample(
        domains, n_corp=args.n_corp, n_gov=args.n_gov, seed=args.seed,
    )

    print(f"\n=== Diagnóstico ===")
    print(f"  total .br processados:        {report.total_br}")
    print(f"  excluídos (heurística):       {report.excluded_count}")
    print(f"  deduplicados (mesmo domínio): {report.deduped_count}")
    print(f"  governamentais disponíveis:   {report.total_gov_available}")
    print(f"  empresariais disponíveis:     {report.total_corp_available}")
    print(f"\n  amostrados governamentais:    {len(report.gov)} (alvo {args.n_gov})")
    print(f"  amostrados empresariais:      {len(report.corp)} (alvo {args.n_corp})")
    if report.gov_shortfall:
        print(f"\n  AVISO: governamentais disponíveis ({report.total_gov_available}) < alvo "
              f"({args.n_gov}). Usando todos os disponíveis. Decida plano B "
              f"(complementar fonte ou reduzir estrato).")

    write_csv(report, args.out)
    print(f"\nOK: {len(report.gov) + len(report.corp)} candidatos -> {args.out}")
    print("Próximo: revise o CSV manualmente (coluna 'aprovado'), remova o que")
    print("não for institucional, e me avise para gerar o protocols/b4.yaml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
