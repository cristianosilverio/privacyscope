"""
Exceções compartilhadas entre fetchers do PrivacyScope.

Vive em ``fetchers/_exceptions`` (underscore prefix = privado da camada por
convenção). Centralizar evita que cada fetcher (HttpFetcher, PlaywrightFetcher,
e qualquer fetcher futuro) defina exceções duplicadas — o FallbackChain
consegue capturar todas com um único ``except FetchError`` em vez de tuplas
múltiplas.

================================================================================
Guia para autores de novos fetchers
================================================================================

Ao criar um novo plugin de Coleta (qualquer subclasse de ``PageFetcher``):

1. **Importe daqui em vez de definir exceções locais**. Mantém polimorfismo
   no FallbackChain e em qualquer consumidor que faça ``except FetchError``.

2. **Se seu fetcher precisar de uma exceção específica nova**, derive de
   ``FetchError`` (ou de subclasse mais específica). Adicione aqui em
   ``_exceptions.py`` e exporte no ``__all__`` — não defina no seu próprio
   módulo de fetcher.

3. **Semântica de cada classe**:
   - ``FetchError`` (base): "falha fatal de coleta — sem evidência possível".
     O FallbackChain captura essa classe-base para decidir escalonar para
     o próximo fetcher na cadeia.
   - ``RobotsDisallowedError``: site explicitamente proibiu coleta via
     robots.txt. O FallbackChain NÃO deve escalonar — outro fetcher também
     deve respeitar.
   - ``ResponseTooLargeError``: resposta excedeu limite configurado.
   - ``NavigationFailedError``: navegação para a URL falhou (timeout, DNS,
     TLS, conexão recusada). Candidato natural a escalonamento.
   - ``JsRequiredError``: página exige JavaScript para renderizar conteúdo
     útil. Sinal específico para o FallbackChain escalar para fetcher com
     browser real (PlaywrightFetcher).
   - ``AmbienteIncompletoError``: dependência do ambiente ausente — navegador
     do Playwright não instalado, por exemplo. NÃO é falha do sítio, e por isso
     NÃO escalona nem é registrada como atrito de coleta: ela ABORTA a execução.
     Degradar em silêncio produziria amostra enviesada para os sítios que
     dispensam escalonamento, que são justamente os mais simples.

4. **Não capture e re-lance silenciosamente**. Erros não-fatais (timeout em
   subpágina, robots.txt ignora um link específico, etc.) devem ir para
   ``RawEvidence.errors`` como string descritiva, não como exceção.
"""

from __future__ import annotations


class FetchError(Exception):
    """Erro fatal durante coleta — sem evidência possível.

    Classe-base. Subclassed por exceções específicas. FallbackChain captura
    essa classe-base para decidir escalonamento.
    """



class AmbienteIncompletoError(FetchError):
    """Dependencia do ambiente ausente, e nao falha do sitio.

    Derivada de FetchError apenas para conveniencia de tipagem; o FallbackChain a
    trata a parte, abortando a execucao em vez de escalonar. A distincao importa:
    falha de sitio e atrito de coleta, registrado e reportado; ambiente incompleto
    afeta TODOS os sitios igualmente, e prosseguir produziria amostra enviesada para
    os que dispensam escalonamento — os mais simples, e portanto os menos
    informativos.

    Descoberta que motivou a classe: coleta ao vivo iniciada com o navegador do
    Playwright ausente do ambiente. A cadeia escalava, o lancamento falhava, e cada
    sitio saia sem evidencia; nao houvesse quem lesse o registro, a amostra chegaria
    ao fim com atrito inexplicado e sem causa visivel.
    """

class NomeNaoResolveError(FetchError):
    """O nome declarado nao resolve, nem na variante com `www.`.

    Distinta das demais falhas de coleta porque nao e falha de coleta: o endereco
    nao designa hospedeiro algum. Nenhum tempo limite maior, nenhum coletor melhor e
    nenhuma nova tentativa a resolvem — o defeito esta no quadro amostral, que
    registrou um nome que nao e ponto de entrada de sitio.

    Levanta-se so depois de esgotada a unica transformacao deterministica disponivel,
    o prefixo `www.`. Fora dela, adivinhar subdominio seria inventar dado.
    """


class RobotsDisallowedError(FetchError):
    """robots.txt do site proíbe coleta pelo nosso User-Agent.

    O FallbackChain NÃO deve escalonar para outro fetcher — a proibição
    aplica-se a qualquer agente de coleta.
    """


class ResponseTooLargeError(FetchError):
    """Resposta excedeu ``max_response_bytes`` configurado.

    Indica conteúdo anômalo (potencialmente malicioso) ou má configuração
    do limite. FallbackChain pode escalonar se outro fetcher tiver limite
    maior, mas geralmente é falha definitiva.
    """


class NavigationFailedError(FetchError):
    """Navegação para a URL falhou — timeout, DNS, TLS, conexão recusada.

    Candidato natural a escalonamento pelo FallbackChain — outro fetcher
    pode ter parametrização diferente de timeout ou capacidades distintas.
    """


class JsRequiredError(FetchError):
    """Página requer renderização JavaScript que o fetcher atual não pode fazer.

    Sinal explícito para o FallbackChain escalar para um fetcher com browser
    real (e.g., PlaywrightFetcher). Levantada tipicamente pelo HttpFetcher
    ao detectar shell SPA vazio.
    """


__all__ = [
    "FetchError",
    "RobotsDisallowedError",
    "ResponseTooLargeError",
    "NavigationFailedError",
    "JsRequiredError",
]
