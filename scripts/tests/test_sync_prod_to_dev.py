"""Regressões do shell com Podman simulado; nenhum banco é acessado.

Execute: python3 -m unittest discover -s scripts/tests -v
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'sync_prod_to_dev.sh'
PODMAN_STUB = """#!/bin/bash
echo "$*" >> "$SYNC_CALLS"
case "$*" in
    ps*) echo fcontrol_db ;;
    *pg_dump*)
        echo '-- fixture dump'
        if [ "$SYNC_FAILURE" = dump ]; then exit 1; fi
        ;;
    *psql*)
        if [[ "$*" != *" -c "* ]]; then
            cat >/dev/null
            if [ "$SYNC_FAILURE" = restore ]; then
                echo 'ERROR: fixture restore failure' >&2
                exit 3
            fi
        fi
        ;;
esac
"""


class SyncScriptTests(unittest.TestCase):
    def run_sync(self, failure):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        scripts = root / 'scripts'
        scripts.mkdir()
        shutil.copy2(SCRIPT, scripts / SCRIPT.name)
        (root / '.env').write_text(
            '# DATABASE_URL="postgresql+asyncpg://user:password@'
            'example.supabase.co:5432/postgres"\n'
        )
        stub = root / 'podman'
        stub.write_text(PODMAN_STUB)
        stub.chmod(0o700)
        calls = root / 'calls'
        result = subprocess.run(
            ['bash', str(scripts / SCRIPT.name)],
            env={
                **os.environ,
                'PATH': f'{root}:{os.environ["PATH"]}',
                'TMPDIR': str(root),
                'SYNC_CALLS': str(calls),
                'SYNC_FAILURE': failure,
            },
            capture_output=True,
            text=True,
            check=False,
        )
        return result, calls.read_text(), root

    def test_restore_failure_is_reported_and_dump_preserved(self):
        result, _, root = self.run_sync('restore')
        assert result.returncode != 0
        assert 'fixture restore failure' in result.stderr
        assert 'Sincronizacao concluida!' not in result.stdout
        assert list(root.rglob('backup.sql'))

    def test_dump_failure_preserves_existing_dev_database(self):
        result, calls, _ = self.run_sync('dump')
        assert result.returncode != 0
        assert 'DROP DATABASE' not in calls
        assert 'Sincronizacao concluida!' not in result.stdout

    def test_success_restores_with_error_checking_and_cleans_dump(self):
        result, calls, root = self.run_sync('none')
        assert result.returncode == 0, result.stderr
        assert 'Sincronizacao concluida!' in result.stdout
        assert 'ON_ERROR_STOP=1' in calls
        assert calls.index('pg_dump') < calls.index('DROP DATABASE')
        assert not list(root.rglob('backup.sql'))
