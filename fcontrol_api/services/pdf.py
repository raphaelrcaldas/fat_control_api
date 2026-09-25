import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def comprimir_pdf(conteudo: bytes) -> bytes:
    """Comprime PDF via Ghostscript (ebook/150dpi).

    Retorna os bytes comprimidos. Se a compressão falhar
    ou resultar em arquivo maior, retorna o original.
    """
    with tempfile.TemporaryDirectory() as tmp:
        entrada = Path(tmp) / 'input.pdf'
        saida = Path(tmp) / 'output.pdf'
        entrada.write_bytes(conteudo)

        try:
            subprocess.run(
                [
                    'gs',
                    '-sDEVICE=pdfwrite',
                    '-dCompatibilityLevel=1.4',
                    '-dPDFSETTINGS=/ebook',
                    '-dNOPAUSE',
                    '-dBATCH',
                    '-dQUIET',
                    '-sOutputFile=' + str(saida),
                    str(entrada),
                ],
                check=True,
                timeout=30,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning('Ghostscript indisponível, usando PDF original')
            return conteudo
        except subprocess.TimeoutExpired:
            logger.warning('Compressão PDF timeout')
            return conteudo

        if not saida.exists():
            return conteudo

        comprimido = saida.read_bytes()

        if len(comprimido) >= len(conteudo):
            return conteudo

        return comprimido


def contar_paginas(conteudo: bytes) -> int | None:
    """Conta as páginas de um PDF com o Ghostscript.

    Devolve `None` quando o `gs` não existe, falha ou não imprime um número
    positivo: a contagem é informativa e nunca deve impedir um upload. Roda em
    modo `-dSAFER`, com leitura liberada só para o arquivo temporário.
    """
    with tempfile.TemporaryDirectory() as tmp:
        arquivo = Path(tmp) / 'entrada.pdf'
        arquivo.write_bytes(conteudo)
        try:
            resultado = subprocess.run(
                [
                    'gs',
                    '-q',
                    '-dNODISPLAY',
                    '-dSAFER',
                    f'--permit-file-read={arquivo}',
                    '-c',
                    f'({arquivo}) (r) file runpdfbegin pdfpagecount = quit',
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=15,
            )
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            FileNotFoundError,
        ):
            logger.warning('Não foi possível contar as páginas do PDF')
            return None

    linhas = resultado.stdout.strip().splitlines()
    try:
        paginas = int(linhas[-1])
        if paginas < 1:
            logger.warning('Não foi possível contar as páginas do PDF')
            return None
        return paginas
    except (ValueError, IndexError):
        return None
