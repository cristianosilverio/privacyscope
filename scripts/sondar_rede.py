# -*- coding: utf-8 -*-
"""Sonda resolucao de nome e alcance de rede, FORA do arcabouco.

POR QUE ISTO EXISTE
-------------------
A coleta ao vivo de 15/08/2026 perdeu 20 de 100 unidades. O diagnostico pelo proprio
arcabouco nao consegue separar tres coisas que se parecem no resultado: sitio fora do
ar, nome que nao designa hospedeiro, e rede de coleta que nao alcanca. As tres
produzem a mesma linha.

Este programa mede as tres SEM passar por coletor algum, e sem interpretar conteudo.
Nao coleta pagina, nao guarda evidencia, nao produz variavel. Cada medida e
elementar e verificavel a mao com `nslookup` e `Test-NetConnection`.

AS QUATRO MEDIDAS, E O QUE CADA UMA SEPARA
------------------------------------------
    resolucao do sistema  o resolvedor DESTA maquina conhece o nome?
    resolucao publica     um resolvedor publico conhece o nome?
                          divergencia entre as duas acusa o resolvedor local, e nao
                          o nome — e essa e a hipotese que motivou o programa
    conexao TCP 443       o hospedeiro aceita conexao desta rede?
    resposta HTTPS        ha servidor HTTP do outro lado, e com que status?

CONTROLES
---------
A lista inclui alvos que a propria coleta ao vivo obteve com sucesso. Se eles
falharem aqui, o problema e do momento ou da rede, e nenhuma conclusao sobre os
demais se sustenta. Sem controle, medida de rede nao vale nada.

REFERENCIA EXTERNA
------------------
As colunas `ref_dns` e `ref_tcp` trazem o que foi medido de OUTRA rede em 16/08/2026,
a partir de infraestrutura de centro de dados. Divergencia entre `sistema` e `ref`
indica propriedade da rede de coleta; coincidencia indica propriedade do alvo.

Uso:
    python scripts/sondar_rede.py
    python scripts/sondar_rede.py --lista protocols/diagnostico_20_lista.csv
    python scripts/sondar_rede.py --saida outputs/sondagem_rede.csv
"""
from __future__ import annotations

import argparse
import csv
import socket
import ssl
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Medido de rede externa em 16/08/2026. "-" quando nao foi medido.
REFERENCIA: dict[str, tuple[str, str]] = {
    "anp.gov.br": ("resolve", "conecta"),
    "www.anp.gov.br": ("resolve", "conecta"),
    "tjap.jus.br": ("resolve", "timeout"),
    "www.tjap.jus.br": ("resolve", "conecta"),
    "franca.sp.gov.br": ("resolve", "timeout"),
    "www.franca.sp.gov.br": ("resolve", "timeout"),
    "infraero.gov.br": ("NXDOMAIN", "-"),
    "www.infraero.gov.br": ("resolve", "conecta"),
    "pdpj.jus.br": ("NXDOMAIN", "-"),
    "www.pdpj.jus.br": ("NXDOMAIN", "-"),
    "policia-civil.sp.gov.br": ("NXDOMAIN", "-"),
    "www.policia-civil.sp.gov.br": ("NXDOMAIN", "-"),
    "uems.br": ("NXDOMAIN", "-"),
    "www.uems.br": ("resolve", "conecta"),
    "wurthdobrasil.com.br": ("NXDOMAIN", "-"),
    "www.wurthdobrasil.com.br": ("resolve", "conecta"),
    "ia.br": ("NXDOMAIN", "-"),
    "lumeway.com.br": ("NXDOMAIN", "-"),
    "www.lumeway.com.br": ("NXDOMAIN", "-"),
    "primelinelatam.com.br": ("NXDOMAIN", "-"),
    "www.primelinelatam.com.br": ("NXDOMAIN", "-"),
    "sgisistemas.com.br": ("resolve", "timeout"),
    "www.sgisistemas.com.br": ("resolve", "timeout"),
    "online.net.br": ("resolve", "timeout"),
    "www.online.net.br": ("resolve", "timeout"),
    "novajus.com.br": ("resolve", "timeout"),
    "www.novajus.com.br": ("resolve", "conecta"),
    "bitcom.psi.br": ("resolve", "timeout"),
    "www.bitcom.psi.br": ("resolve", "conecta"),
    "fulltrack.net.br": ("resolve", "timeout"),
    "www.fulltrack.net.br": ("NXDOMAIN", "-"),
    "acessorh.com.br": ("resolve", "conecta"),
    "www.acessorh.com.br": ("resolve", "timeout"),
    "kroton.com.br": ("resolve", "conecta"),
    "www.kroton.com.br": ("resolve", "conecta"),
    "meucurriculoperfeito.com.br": ("resolve", "conecta"),
    "www.meucurriculoperfeito.com.br": ("resolve", "conecta"),
    "qualityautomacao.com.br": ("-", "-"),
    "www.qualityautomacao.com.br": ("-", "-"),
}

# Alvos que a coleta ao vivo obteve com sucesso, mais nomes de referencia geral.
CONTROLES = ["ambev.com.br", "gigabicho.com.br", "anpd.gov.br", "gov.br", "google.com"]

RESOLVEDOR_PUBLICO = "8.8.8.8"


def resolve_sistema(host: str) -> tuple[str, str]:
    """(resultado, detalhe) pelo resolvedor desta maquina, separando IPv4 de IPv6."""
    v4 = v6 = ""
    for familia, rotulo in ((socket.AF_INET, "v4"), (socket.AF_INET6, "v6")):
        try:
            r = socket.getaddrinfo(host, 443, familia, socket.SOCK_STREAM)
            ip = r[0][4][0]
            if rotulo == "v4":
                v4 = ip
            else:
                v6 = ip
        except Exception:                                       # noqa: BLE001
            pass
    if not v4 and not v6:
        return "NXDOMAIN", ""
    return "resolve", v4 or f"[{v6}]"


def resolve_publico(host: str) -> str:
    """Segunda opiniao por resolvedor publico. Divergencia acusa o resolvedor local."""
    try:
        p = subprocess.run(["nslookup", host, RESOLVEDOR_PUBLICO],
                           capture_output=True, text=True, timeout=12)
    except Exception:                                           # noqa: BLE001
        return "?"
    saida = (p.stdout or "") + (p.stderr or "")
    baixo = saida.lower()
    if "can't find" in baixo or "não encontrado" in baixo or "nxdomain" in baixo:
        return "NXDOMAIN"
    # A primeira secao repete o proprio servidor consultado; interessa o que vem depois.
    corpo = saida.split("\n\n", 1)[-1]
    return "resolve" if ("address" in corpo.lower() or "endereço" in corpo.lower()) else "?"


def conecta(ip: str, porta: int = 443, limite: float = 8.0) -> str:
    if not ip:
        return "-"
    alvo = ip.strip("[]")
    familia = socket.AF_INET6 if ":" in alvo else socket.AF_INET
    s = socket.socket(familia, socket.SOCK_STREAM)
    s.settimeout(limite)
    try:
        s.connect((alvo, porta))
        return "conecta"
    except socket.timeout:
        return "timeout"
    except Exception as e:                                      # noqa: BLE001
        return type(e).__name__
    finally:
        s.close()


def https(host: str, limite: float = 10.0) -> str:
    """Status da resposta, ou a falha. Nao segue redirecionamento nem le corpo."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, 443), timeout=limite) as bruto:
            with ctx.wrap_socket(bruto, server_hostname=host) as tls:
                tls.settimeout(limite)
                tls.sendall(f"HEAD / HTTP/1.1\r\nHost: {host}\r\n"
                            f"User-Agent: PrivacyScope-sonda/1.0\r\n"
                            f"Connection: close\r\n\r\n".encode())
                dados = tls.recv(200).decode("latin-1", "replace")
        primeira = dados.split("\r\n", 1)[0].strip()
        return primeira[:40] or "sem resposta"
    except Exception as e:                                      # noqa: BLE001
        return type(e).__name__


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lista", default="protocols/diagnostico_20_lista.csv")
    ap.add_argument("--saida", default="outputs/sondagem_rede.csv")
    ap.add_argument("--sem-publico", action="store_true",
                    help="pula a consulta ao resolvedor publico")
    args = ap.parse_args()

    lista = REPO / args.lista
    alvos: list[tuple[str, str]] = []
    if lista.is_file():
        with lista.open(encoding="utf-8-sig", newline="") as fh:
            for l in csv.DictReader(fh, delimiter=";"):
                d = (l.get("dominio") or "").strip().lower()
                if d:
                    alvos.append((d, "alvo"))
                    if not d.startswith("www."):
                        alvos.append((f"www.{d}", "alvo"))
    alvos += [(c, "controle") for c in CONTROLES]

    print(f"sondando {len(alvos)} nomes; resolvedor publico: "
          f"{'nao' if args.sem_publico else RESOLVEDOR_PUBLICO}\n")
    cab = (f"{'nome':34s} {'tipo':9s} {'sistema':10s} {'publico':10s} "
           f"{'TCP443':12s} {'HTTPS':22s} {'ref_dns':10s} {'ref_tcp':9s}")
    print(cab)
    print("-" * len(cab))

    linhas = []
    for nome, tipo in alvos:
        sis, ip = resolve_sistema(nome)
        pub = "-" if args.sem_publico else resolve_publico(nome)
        tcp = conecta(ip) if sis == "resolve" else "-"
        web = https(nome) if tcp == "conecta" else "-"
        rd, rt = REFERENCIA.get(nome, ("-", "-"))
        print(f"{nome[:34]:34s} {tipo:9s} {sis:10s} {pub:10s} {tcp:12s} "
              f"{web[:22]:22s} {rd:10s} {rt:9s}")
        linhas.append({"nome": nome, "tipo": tipo, "sistema": sis, "ip": ip,
                       "publico": pub, "tcp443": tcp, "https": web,
                       "ref_dns": rd, "ref_tcp": rt})

    saida = REPO / args.saida
    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0]), delimiter=";")
        w.writeheader(); w.writerows(linhas)

    print()
    ctrl = [l for l in linhas if l["tipo"] == "controle"]
    ok_ctrl = sum(1 for l in ctrl if l["tcp443"] == "conecta")
    print(f"CONTROLES: {ok_ctrl} de {len(ctrl)} conectam.", end=" ")
    print("Rede utilizavel." if ok_ctrl == len(ctrl)
          else "ATENCAO: controle falhou; nenhuma conclusao sobre os alvos se sustenta.")

    divergem = [l for l in linhas if l["ref_dns"] not in ("-", "?")
                and l["sistema"] != l["ref_dns"]]
    if divergem:
        print(f"\nDIVERGEM da referencia externa em RESOLUCAO ({len(divergem)}) — "
              f"indicio de propriedade da rede de coleta, e nao do alvo:")
        for l in divergem:
            print(f"   {l['nome']:34s} aqui={l['sistema']:10s} externo={l['ref_dns']}")
    div_tcp = [l for l in linhas if l["ref_tcp"] == "conecta"
               and l["tcp443"] not in ("conecta", "-")]
    if div_tcp:
        print(f"\nRESOLVEM aqui e NAO CONECTAM, conectando de fora ({len(div_tcp)}):")
        for l in div_tcp:
            print(f"   {l['nome']:34s} aqui={l['tcp443']}")
    local = [l for l in linhas if l["sistema"] == "NXDOMAIN" and l["publico"] == "resolve"]
    if local:
        print(f"\nNAO RESOLVEM no sistema e RESOLVEM no publico ({len(local)}) — "
              f"aponta o resolvedor local:")
        for l in local:
            print(f"   {l['nome']}")
    print(f"\nplanilha: {saida.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
