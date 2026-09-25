import shutil
import subprocess

import pytest

from fcontrol_api.services import pdf
from fcontrol_api.services.pdf import contar_paginas

tem_gs = shutil.which('gs') is not None


@pytest.mark.skipif(not tem_gs, reason='Ghostscript ausente')
def test_conta_paginas_de_pdf_real(tmp_path):
    saida = tmp_path / 'tres.pdf'
    subprocess.run(
        [
            'gs',
            '-q',
            '-sDEVICE=pdfwrite',
            '-o',
            str(saida),
            '-c',
            'showpage showpage showpage',
        ],
        check=True,
    )
    assert contar_paginas(saida.read_bytes()) == 3


@pytest.mark.skipif(not tem_gs, reason='Ghostscript ausente')
def test_bytes_invalidos_devolvem_none():
    assert contar_paginas(b'isto nao e um pdf') is None


def test_sem_ghostscript_devolve_none(monkeypatch):
    def sem_gs(*args, **kwargs):
        raise FileNotFoundError('gs')

    monkeypatch.setattr(pdf.subprocess, 'run', sem_gs)
    assert contar_paginas(b'%PDF-1.4') is None
