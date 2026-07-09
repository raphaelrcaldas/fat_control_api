"""Brasão da organização: bucket e URL pública.

Centraliza o nome do bucket e a geração da URL do brasão para que tanto o
router de organizações (que gerencia o upload) quanto o de tenants (que
embute a organização) produzam a mesma `brasao_url` — sem duplicar a
constante do bucket nem a lógica de URL.

O brasão usa URL **pública** (não assinada): é conteúdo não sensível e o
path estável permite que o navegador cacheie a imagem entre navegações e
trocas de org, em vez de rebaixá-la a cada URL assinada nova (que expira).
Requer que o bucket `organizacoes` tenha leitura pública no storage.
"""

from fcontrol_api.services.storage import get_public_url

# Bucket do domínio de organizações (brasões). Nome constante de código
# (não é env/secret) — cada domínio tem o seu. Ver services/storage.py.
BUCKET_ORGANIZACOES = 'organizacoes'
BRASAO_PREFIX = 'brasoes'


def brasao_public_url(brasao_path: str | None) -> str | None:
    """URL pública do brasão, ou None quando a org não tem brasão."""
    if not brasao_path:
        return None
    return get_public_url(BUCKET_ORGANIZACOES, brasao_path)
