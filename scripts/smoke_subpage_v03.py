"""Smoke test do _subpage.py v0.3 (trampolim Acesso à Informação).

Roda DOIS testes em três sítios alvo (saogoncalo.rn.gov.br, cgu.gov.br,
predize.com.br):

    Teste A — extract_subpage_candidates na home:
        Verifica se a nova categoria ``acesso_informacao_gov`` é descoberta
        em sítios .gov.br (e NÃO disparada em sítios corp).

    Teste B — extract_trampoline_lgpd_candidates no HTML da página-trampolim:
        Verifica se, a partir do HTML de /acessoainformacao.php (ou
        equivalente), o trampolim descobre páginas LGPD em profundidade 2
        (lgpd.php, privacidade-e-protecao-de-dados, etc.).

Não toca em fetchers, orquestrador, sqlite — apenas testa a primitiva.
Uso de httpx síncrono para simplicidade (não é parte do pipeline).

Saída esperada (sucesso):
    saogoncalo.rn.gov.br: TESTE A=PASS (acesso_informacao_gov descoberto)
                          TESTE B=PASS (lgpd descoberto via trampolim)
    cgu.gov.br:           TESTE A=PASS
                          TESTE B=PASS
    predize.com.br:       TESTE A=PASS (acesso_informacao_gov NAO disparou)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Garante import direto do source, ignorando qualquer instalação editable.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

import httpx  # noqa: E402

from privacyscope.fetchers._subpage import (  # noqa: E402
    DEFAULT_SUBPAGE_CATEGORIES,
    SUBPAGE_VERSION,
    TRAMPOLINE_CATEGORIES,
    extract_subpage_candidates,
    extract_trampoline_lgpd_candidates,
)

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def fetch_with_final_url(url: str) -> tuple[bytes, str]:
    """Devolve (content, final_url pós-redirect). Necessário para que o
    same-host enforcement do extract_subpage_candidates compare contra o
    netloc correto, não o pré-redirect."""
    with httpx.Client(
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"},
    ) as client:
        resp = client.get(url)
        return resp.content, str(resp.url)

TARGETS = [
    {
        "name": "saogoncalo.rn.gov.br",
        "home": "https://saogoncalo.rn.gov.br/",
        "expected_trampoline_descovered": True,
        # Página esperada como TRAMPOLIM descoberto na home.
        "expected_trampoline_url_contains": "acessoainformacao",
        # Página LGPD esperada como descoberta DEPOIS do trampolim.
        "expected_lgpd_url_contains": "lgpd",
    },
    {
        "name": "cgu.gov.br",
        "home": "https://www.cgu.gov.br/",
        "expected_trampoline_descovered": True,
        "expected_trampoline_url_contains": "acesso-a-informacao",
        "expected_lgpd_url_contains": "privacidade",
    },
    {
        "name": "predize.com.br",
        "home": "https://predize.com.br/",
        "expected_trampoline_descovered": False,
        "expected_trampoline_url_contains": None,
        "expected_lgpd_url_contains": None,
    },
]


def run_test_a(target: dict) -> tuple[bool, str]:
    """Testa extract_subpage_candidates em sítios institucionais BR.

    Usa URL pós-redirect como base_url e passa TRAMPOLINE_CATEGORIES como
    same_host_categories — mesma configuração que os fetchers reais usam
    em v0.3.0.
    """
    home_html, final_url = fetch_with_final_url(target["home"])
    sel = extract_subpage_candidates(
        html=home_html,
        base_url=final_url,
        categories=DEFAULT_SUBPAGE_CATEGORIES,
        max_per_category=2,  # permite ver mais de 1 candidato p/ debug
        max_total=15,
        same_host_categories=TRAMPOLINE_CATEGORIES,
    )
    tramp_items = sel.get("acesso_informacao_gov", [])
    tramp_urls = [i["url"] for i in tramp_items]

    if target["expected_trampoline_descovered"]:
        if not tramp_items:
            return False, f"esperava acesso_informacao_gov; achou {list(sel.keys())}"
        if target["expected_trampoline_url_contains"]:
            urls_match = [
                u for u in tramp_urls
                if target["expected_trampoline_url_contains"] in u.lower()
            ]
            if not urls_match:
                return False, (
                    f"trampolim descoberto mas URL nao contem "
                    f"'{target['expected_trampoline_url_contains']}': {tramp_urls}"
                )
        return True, (
            f"acesso_informacao_gov ok ({len(tramp_items)}): {tramp_urls[:3]}"
        )
    else:
        # corp esperado a NAO disparar trampolim
        if tramp_items:
            return False, (
                f"NAO esperava trampolim em sitio corp; achou: {tramp_urls}"
            )
        return True, "trampolim corretamente NAO disparou em sitio corp"


def run_test_b(target: dict) -> tuple[bool, str]:
    """Testa extract_trampoline_lgpd_candidates no HTML da pagina-trampolim."""
    if not target["expected_trampoline_descovered"]:
        return True, "N/A (sitio corp; trampolim nao se aplica)"

    # Re-roda Teste A so para pegar a URL real do trampolim descoberto.
    home_html, final_url = fetch_with_final_url(target["home"])
    sel = extract_subpage_candidates(
        html=home_html,
        base_url=final_url,
        categories=DEFAULT_SUBPAGE_CATEGORIES,
        max_per_category=2,
        max_total=15,
        same_host_categories=TRAMPOLINE_CATEGORIES,
    )
    tramp_items = sel.get("acesso_informacao_gov", [])
    if not tramp_items:
        return False, "Teste A falhou; sem URL trampolim para testar Teste B"

    # Pega o primeiro item que casa com o que esperamos.
    target_url = None
    for i in tramp_items:
        if target["expected_trampoline_url_contains"] in i["url"].lower():
            target_url = i["url"]
            break
    if not target_url:
        target_url = tramp_items[0]["url"]

    tramp_html, tramp_final_url = fetch_with_final_url(target_url)
    depth2 = extract_trampoline_lgpd_candidates(
        html=tramp_html,
        base_url=tramp_final_url,
        categories=DEFAULT_SUBPAGE_CATEGORIES,
        source_category="acesso_informacao_gov",
        max_per_category=2,
        max_total=5,
    )

    if not depth2:
        return False, (
            f"trampolim {target_url} NAO descobriu LGPD em profundidade 2"
        )

    # Verifica que pelo menos um item descoberto tem o esperado
    expected = target["expected_lgpd_url_contains"]
    all_urls = []
    for cat, items in depth2.items():
        for i in items:
            all_urls.append((cat, i["url"], i.get("discovered_via", "?")))
    matching = [
        (cat, u, dv) for cat, u, dv in all_urls if expected in u.lower()
    ]
    if not matching:
        return False, (
            f"trampolim achou {len(all_urls)} candidatos LGPD mas nenhum "
            f"contem '{expected}': {all_urls}"
        )

    # Confere discovered_via
    sample = matching[0]
    if not sample[2].startswith("trampoline:"):
        return False, f"discovered_via mal anotado: {sample[2]}"

    return True, (
        f"trampolim descobriu {len(all_urls)} candidatos LGPD; "
        f"matching '{expected}': {matching[:2]}"
    )


def main() -> int:
    print(f"=== smoke test _subpage v{SUBPAGE_VERSION} ===")
    print(f"TRAMPOLINE_CATEGORIES = {set(TRAMPOLINE_CATEGORIES)}")
    print(f"categorias = {list(DEFAULT_SUBPAGE_CATEGORIES.keys())}")
    print()

    all_pass = True
    for target in TARGETS:
        print(f"### {target['name']}")
        try:
            ok_a, msg_a = run_test_a(target)
        except Exception as e:
            ok_a, msg_a = False, f"EXCEPT: {type(e).__name__}: {e}"
        print(f"  TESTE A (subpage_candidates):  {'PASS' if ok_a else 'FAIL'}")
        print(f"    {msg_a}")
        all_pass &= ok_a

        try:
            ok_b, msg_b = run_test_b(target)
        except Exception as e:
            ok_b, msg_b = False, f"EXCEPT: {type(e).__name__}: {e}"
        print(f"  TESTE B (trampoline_lgpd):     {'PASS' if ok_b else 'FAIL'}")
        print(f"    {msg_b}")
        all_pass &= ok_b
        print()

    print(f"=== overall: {'PASS' if all_pass else 'FAIL'} ===")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
