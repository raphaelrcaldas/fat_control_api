from types import ModuleType
from unittest.mock import patch

import pytest

from fcontrol_api.cleanup.runner import ALLOWED_TASKS, run_all_tasks

pytestmark = pytest.mark.anyio

EXPECTED_TASK_NAMES = {
    'cleanup_old_unavailability',
    'cleanup_old_login_logs',
}


async def test_runner_discovers_and_runs_all_tasks(session, users):
    results = await run_all_tasks(session)

    assert len(results) == len(ALLOWED_TASKS)

    task_names = {r.task_name for r in results}
    assert task_names == EXPECTED_TASK_NAMES


async def test_runner_returns_results_for_each_task(session, users):
    results = await run_all_tasks(session)

    for result in results:
        assert result.task_name
        assert result.status in {'success', 'skipped', 'error'}
        assert result.duration_seconds >= 0


async def test_runner_skips_module_without_run_function(
    session, users
):
    fake_module = ModuleType('fake_task')

    with patch(
        'fcontrol_api.cleanup.runner.ALLOWED_TASKS',
        ALLOWED_TASKS | {'fake_task'},
    ), patch(
        'fcontrol_api.cleanup.runner.importlib.import_module',
        side_effect=lambda name: (
            fake_module
            if name.endswith('fake_task')
            else __import__(
                name, fromlist=[name.rsplit('.', 1)[-1]]
            )
        ),
    ):
        results = await run_all_tasks(session)

    task_names = {r.task_name for r in results}
    assert 'fake_task' not in task_names
    assert len(results) == len(ALLOWED_TASKS)
