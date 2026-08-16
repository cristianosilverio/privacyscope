# -*- coding: utf-8 -*-
"""Matriz de confusao diante de medida indeterminada.

O arcabouco nao devolve so booleano: `nao_aplicavel` marca precondicao nao
satisfeita e `nao_coletado` marca unidade que o instrumento nao obteve. A versao
anterior os deixava cair fora dos quatro ramos sem contar, de sorte que a unidade
saia do numerador e do denominador ao mesmo tempo — o mesmo defeito corrigido na
camada de resultados, uma camada acima.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "cgt", REPO / "scripts" / "compare_to_ground_truth.py")
cgt = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cgt
_spec.loader.exec_module(cgt)


def test_pares_booleanos_contam_como_antes():
    cm = cgt.confusion_matrix([(True, True), (False, False), (True, False),
                               (False, True)])
    assert (cm["tp"], cm["tn"], cm["fp"], cm["fn"]) == (1, 1, 1, 1)
    assert cm["n"] == 4
    assert cm["n_excluidos"] == 0


def test_indeterminado_sai_da_matriz_mas_e_contado():
    cm = cgt.confusion_matrix([(True, True), ("nao_coletado", True),
                               ("nao_aplicavel", False)])
    assert cm["n"] == 1, "medida indeterminada nao entra em matriz de confusao"
    assert cm["n_excluidos"] == 2, "mas nao pode sair sem deixar registro"
    assert cm["excluidos"] == {"nao_coletado": 1, "nao_aplicavel": 1}
    assert cm["n_confrontados"] == 3


def test_revocacao_declara_sobre_quantos_foi_calculada():
    """Sem a contagem, uma revocacao de 1,00 sobre um unico par pareceria
    identica a uma revocacao de 1,00 sobre cinquenta."""
    cm = cgt.confusion_matrix([(True, True)] + [("nao_coletado", True)] * 49)
    assert cgt.metrics(cm)["recall"] == 1.0
    assert cm["n"] == 1 and cm["n_excluidos"] == 49


def test_valor_inesperado_tambem_e_rotulado():
    cm = cgt.confusion_matrix([(None, True)])
    assert cm["n"] == 0
    assert list(cm["excluidos"]) == ["valor_NoneType"]
