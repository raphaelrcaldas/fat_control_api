"""Serviço genérico de imagens (validação + normalização para JPEG).

Funções puras/síncronas: a normalização é pesada (Pillow) e deve ser
chamada via `asyncio.to_thread` nos handlers. A regra de HTTP (levantar
`HTTPException`) fica no router — aqui só expomos predicados/transformações,
seguindo o mesmo desacoplamento de `services/storage.py`.
"""

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

# Magic bytes dos formatos aceitos no upload. O conteúdo é sempre
# recomprimido para JPEG por `normalizar_jpeg`, mas aceitamos PNG na entrada.
_JPEG_MAGIC = b'\xff\xd8\xff'
_PNG_MAGIC = b'\x89PNG\r\n\x1a\n'

# Cap de dimensão: evita guardar imagens absurdamente grandes. A proporção
# é preservada por `thumbnail` (só reduz, nunca amplia).
_MAX_DIM = (2000, 2000)

# Qualidade do JPEG de saída: compromisso entre nitidez do documento
# (passaporte/visto) e tamanho do arquivo.
_JPEG_QUALITY = 85

# Teto de pixels para barrar "decompression bomb": uma imagem de poucos MB
# pode decodificar para giga-pixels e estourar a memória do worker (DoS).
# ~50 MP cobre com folga fotos de documento.
_MAX_PIXELS = 50_000_000


class ImagemInvalidaError(Exception):
    """Conteúdo não decodificável como imagem segura (input inválido)."""


def is_imagem_valida(conteudo: bytes) -> bool:
    """Indica se `conteudo` começa com magic bytes de JPEG ou PNG."""
    return conteudo.startswith(_JPEG_MAGIC) or conteudo.startswith(_PNG_MAGIC)


def normalizar_jpeg(conteudo: bytes) -> bytes:
    """Recomprime a imagem para JPEG RGB com cap de dimensão.

    Aplica a orientação EXIF (foto de celular não sai girada) e
    `convert('RGB')` (evita o erro de salvar modos RGBA/P como JPEG).
    Síncrona de propósito (chamar via `asyncio.to_thread`).

    Levanta `ImagemInvalidaError` se o conteúdo não decodifica ou excede o
    teto de pixels (decompression bomb).
    """
    try:
        with Image.open(BytesIO(conteudo)) as img:
            if (img.width * img.height) > _MAX_PIXELS:
                raise ImagemInvalidaError(
                    'Imagem excede o limite de dimensões'
                )

            rgb = ImageOps.exif_transpose(img).convert('RGB')
            rgb.thumbnail(_MAX_DIM)

            buffer = BytesIO()
            rgb.save(
                buffer,
                format='JPEG',
                quality=_JPEG_QUALITY,
                optimize=True,
            )
            return buffer.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
    ) as e:
        raise ImagemInvalidaError('Imagem inválida ou corrompida') from e
