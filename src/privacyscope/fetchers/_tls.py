"""Inspecao do certificado apresentado pelo hospedeiro.

POR QUE ISTO EXISTE
-------------------
O arcabouco tratava certificado invalido de duas maneiras contraditorias: o coletor
por requisicao simples validava e desistia; o PlaywrightFetcher ignorava erros de TLS
por padrao e coletava sem registrar nada. Coletar ou nao dependia de qual coletor
vencia, e o registro nao dizia coisa alguma.

Nao cabe ao instrumento decidir se um certificado defeituoso invalida a observacao.
Cabe registrar o que foi apresentado, com precisao suficiente para que quem examina
decida. Recusar a coleta nao protegia atribuicao alguma — apagava o achado.

O QUE A DISTINCAO ENTRE OS ESTADOS SERVE
----------------------------------------
Medido em 17/08/2026 sobre 789 coletas e 219 unidades sem coleta de b7, b9 e da
coleta ao vivo, os defeitos encontrados nao sao do mesmo tipo:

    cadeia_ou_validade       o certificado COBRE o nome pedido; falta a cadeia
                             intermediaria ou a validade expirou. Defeito de
                             configuracao. Ex.: www.uems.br, com certificado
                             *.uems.br emitido por autoridade publica.
    escopo_do_certificado    mesmo dominio registravel, cobertura errada — curinga
                             que nao cobre o apex, ou certificado de `www` usado no
                             apex. Ex.: cbtu.gov.br com certificado *.cbtu.gov.br.
    certificado_de_terceiro  nome de outra organizacao. Ex.: pge.rn.gov.br
                             apresentando certificado de arsep.rn.gov.br;
                             jbcred.com.br com o certificado padrao do Azure;
                             gruppy.com.br com "Kubernetes Ingress Controller Fake
                             Certificate".

Sao tres achados distintos para quem monitora, e reduzi-los a "TLS invalido" perderia
a distincao entre descuido de configuracao e sitio servido por infraestrutura alheia.
"""
from __future__ import annotations

import socket
import ssl
from typing import Any

ESTADOS = ("valido", "cadeia_ou_validade", "escopo_do_certificado",
           "certificado_de_terceiro", "nao_inspecionado", "indeterminado")


def _casa(nome: str, host: str) -> bool:
    """Casamento de nome conforme RFC 6125: curinga cobre UM rotulo, e nao o apex."""
    nome = (nome or "").lower().rstrip(".")
    host = (host or "").lower().rstrip(".")
    if nome.startswith("*."):
        return host.count(".") == nome.count(".") and host.endswith(nome[1:])
    return host == nome


_EXTRATOR = None


def _registravel(nome: str) -> str:
    """Dominio registravel, pela lista de sufixos publicos.

    Contar rotulos nao serve: `pge.rn.gov.br` e `arsep.rn.gov.br` compartilham
    `rn.gov.br`, que e sufixo publico, e sao ORGAOS DIFERENTES. Classifica-los como
    mesmo dominio transformaria certificado de terceiro em descuido de escopo, que e
    justamente a distincao que interessa a quem monitora.

    A lista custa carga, mas esta funcao so roda quando um certificado ja falhou a
    validacao — nao esta no caminho quente da coleta. Usa-se o instantaneo embutido,
    sem consulta de rede, para que a classificacao seja reproduzivel.
    """
    global _EXTRATOR
    nome = (nome or "").lower().lstrip("*.").rstrip(".")
    if not nome:
        return ""
    if _EXTRATOR is None:
        try:
            import tldextract
            _EXTRATOR = tldextract.TLDExtract(suffix_list_urls=())
        except Exception:                                       # noqa: BLE001
            _EXTRATOR = False
    if _EXTRATOR is False:
        # Sem a lista, o conservador e recusar a equivalencia: preferimos rotular
        # como terceiro o que talvez fosse escopo, e nunca o contrario.
        return nome
    r = _EXTRATOR(nome)
    return f"{r.domain}.{r.suffix}" if r.suffix and r.domain else nome


def _mesmo_registravel(host: str, nome: str) -> bool:
    a, b = _registravel(host), _registravel(nome)
    return bool(a) and a == b


def inspeciona(host: str, *, porta: int = 443, timeout: float = 8.0) -> dict[str, Any]:
    """Devolve o estado do certificado e o que ele declara. Nunca levanta."""
    fora: dict[str, Any] = {"estado": "indeterminado", "host": host, "cn": "",
                            "sans": [], "emissor": "", "valido_ate": "", "detalhe": ""}
    try:
        with socket.create_connection((host, porta), timeout=timeout) as s:
            with ssl.create_default_context().wrap_socket(s, server_hostname=host):
                fora["estado"] = "valido"
                return fora
    except ssl.SSLCertVerificationError as e:
        fora["detalhe"] = str(e)[:200]
    except Exception as e:                                      # noqa: BLE001
        fora["detalhe"] = f"{type(e).__name__}: {str(e)[:150]}"
        return fora

    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
    except Exception:                                           # noqa: BLE001
        # Sem a biblioteca, sabe-se que o certificado nao valida e nao se sabe de
        # quem ele e. Dizer isso e melhor que devolver `indeterminado` mudo, que se
        # confunde com hospedeiro inalcancavel.
        fora["detalhe"] = ("biblioteca `cryptography` ausente: nao foi possivel ler "
                           "o certificado apresentado; " + fora["detalhe"])[:250]
        fora["estado"] = "nao_inspecionado"
        return fora

    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((host, porta), timeout=timeout) as s:
            with ctx.wrap_socket(s, server_hostname=host) as t:
                cert = x509.load_der_x509_certificate(
                    t.getpeercert(binary_form=True), default_backend())
    except Exception as e:                                      # noqa: BLE001
        fora["detalhe"] = f"{type(e).__name__}: {str(e)[:150]}"
        return fora

    try:
        sans = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    except Exception:                                           # noqa: BLE001
        sans = []
    cn = next((a.value for a in cert.subject if a.oid._name == "commonName"), "")
    emissor = next((a.value for a in cert.issuer
                    if a.oid._name in ("commonName", "organizationName")), "")
    nomes = [n for n in ([cn] + list(sans)) if n]
    try:
        ate = cert.not_valid_after_utc.date().isoformat()
    except Exception:                                           # noqa: BLE001
        ate = ""

    fora.update({"cn": cn, "sans": list(sans)[:8], "emissor": emissor, "valido_ate": ate})
    if any(_casa(n, host) for n in nomes):
        fora["estado"] = "cadeia_ou_validade"
    elif any(_mesmo_registravel(host, n) for n in nomes):
        fora["estado"] = "escopo_do_certificado"
    else:
        fora["estado"] = "certificado_de_terceiro"
    return fora


def marca(info: dict[str, Any]) -> str:
    """Linha de auditoria com o que foi apresentado. Viaja com a evidencia."""
    return (f"tls.defeito estado={info.get('estado')} host={info.get('host')} "
            f"cn={info.get('cn')!r} sans={','.join(info.get('sans') or [])[:120]} "
            f"emissor={info.get('emissor')!r} valido_ate={info.get('valido_ate')} "
            f"detalhe={(info.get('detalhe') or '')[:120]}")
