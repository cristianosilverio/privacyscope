# outputs/

Artefatos gerados por script. Nenhum arquivo deste diretorio e editado manualmente.

Criterio: artefatos reproduziveis a partir de um script residem aqui; fontes da
verdade produzidas manualmente residem fora.

| arquivo | script | conteudo |
|---|---|---|
| `features_canal_N200.csv` | `extrair_features_canal.py --janela 200` | matriz de 8 atributos por sitio, com o rotulo `y` |
| `features_canal_N100.csv` / `N400` | idem, `--janela 100` / `400` | verificacao de robustez da janela de proximidade |
| `verificacao_evidencias.csv` | `verificar_evidencias.py` | ancoragem das citacoes de evidencia na rotulagem |
| `revisao_formas_canal.csv` | `revisar_formas_canal.py` | fatos observaveis por sitio, para revisao das formas |
| `kappa_subset_b9.xlsx` | instrumento cego | subconjunto de 70 sitios para concordancia inter-avaliadores |
| `kappa_subset_membership.csv` | idem | site_id e semente do sorteio, para cruzamento posterior |

## Fontes da verdade (fora deste diretorio)

`rotulagem_b9.csv` e `rotulagem_b9.xlsx` contem a rotulagem manual e constituem
entrada dos scripts. O arquivo XLSX e a fonte primaria; o CSV e sua exportacao.

## Reproducao

    python scripts/extrair_features_canal.py --janela 200
    python scripts/auditar_features_canal.py
    python scripts/linhas_base_canal.py

A janela de proximidade e fixada em 200 caracteres previamente a avaliacao. As
execucoes com 100 e 400 destinam-se a verificacao de robustez; a selecao da
janela pelo desempenho equivaleria a ajuste de hiperparametro sobre a amostra
inteira e nao e adotada.
