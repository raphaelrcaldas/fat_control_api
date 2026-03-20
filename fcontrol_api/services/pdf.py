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
