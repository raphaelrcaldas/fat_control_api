import importlib
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from fcontrol_api.cleanup.models.cleanup_result import CleanupTaskResult
from fcontrol_api.cleanup.runner import ALLOWED_TASKS, run_all_tasks
from fcontrol_api.database import get_session
from fcontrol_api.routers.admin_cleanup import router
from fcontrol_api.security import require_system_admin

pytestmark = pytest.mark.anyio


@pytest.fixture
def task_runs(monkeypatch):
    runs = {}
    for name in ALLOWED_TASKS:
        module = importlib.import_module(f'fcontrol_api.cleanup.tasks.{name}')
        runs[name] = AsyncMock(
            return_value=CleanupTaskResult(
                task_name=module.TASK_NAME,
                status='success',
                rows_affected=2,
            )
        )
        monkeypatch.setattr(module, 'run', runs[name])
    return runs


@pytest.fixture
def cleanup_app():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: None
    app.dependency_overrides[require_system_admin] = lambda: None
    return app


@pytest.mark.parametrize('task_name', sorted(ALLOWED_TASKS))
async def test_selected_task_does_not_run_other_tasks(
    cleanup_app, task_runs, task_name
):
    async with AsyncClient(
        transport=ASGITransport(app=cleanup_app), base_url='http://test'
    ) as client:
        response = await client.post(
            '/admin/cleanup/run', params={'task_name': task_name}
        )

    assert response.status_code == 200
    data = response.json()['data']
    assert data['total_deleted'] == 2
    assert [task['task_name'] for task in data['tasks']] == [
        f'cleanup_{task_name}'
    ]
    for name, run in task_runs.items():
        assert run.await_count == (1 if name == task_name else 0)


async def test_without_selection_still_runs_all_tasks(cleanup_app, task_runs):
    async with AsyncClient(
        transport=ASGITransport(app=cleanup_app), base_url='http://test'
    ) as client:
        response = await client.post('/admin/cleanup/run')

    assert response.status_code == 200
    data = response.json()['data']
    assert data['total_deleted'] == 2 * len(ALLOWED_TASKS)
    assert len(data['tasks']) == len(ALLOWED_TASKS)
    for run in task_runs.values():
        run.assert_awaited_once()


@pytest.mark.parametrize(
    'task_name', ['', 'unknown', 'cleanup_old_login_logs']
)
async def test_invalid_selection_never_runs_cleanup(
    cleanup_app, task_runs, task_name
):
    async with AsyncClient(
        transport=ASGITransport(app=cleanup_app), base_url='http://test'
    ) as client:
        response = await client.post(
            '/admin/cleanup/run', params={'task_name': task_name}
        )

    assert response.status_code == 422
    with pytest.raises(ValueError, match='Tarefa de limpeza inválida'):
        await run_all_tasks(object(), task_name=task_name)
    for run in task_runs.values():
        run.assert_not_awaited()


async def test_selected_task_requires_system_admin(cleanup_app, task_runs):
    def deny_access():
        raise HTTPException(status_code=403, detail='SCOPE_FORBIDDEN')

    cleanup_app.dependency_overrides[require_system_admin] = deny_access
    async with AsyncClient(
        transport=ASGITransport(app=cleanup_app), base_url='http://test'
    ) as client:
        response = await client.post(
            '/admin/cleanup/run', params={'task_name': 'old_login_logs'}
        )

    assert response.status_code == 403
    for run in task_runs.values():
        run.assert_not_awaited()
