"""
Entrypoint para execucao de todas as cleanup tasks.

Uso local:
    cd /path/to/api
    python -m scripts.run_cleanup

Fly.io Machine (schedule weekly):
    flyctl machine run registry.fly.io/fcontrol-api \
      --app fcontrol-api \
      --region gru \
      --vm-memory 256 \
      --schedule weekly \
      --restart no \
      --name cleanup-runner \
      --entrypoint "python -m scripts.run_cleanup"
"""

import asyncio
import logging

from fcontrol_api.cleanup.runner import log_report, run_all_tasks
from fcontrol_api.database import get_session

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


async def main():
    logger.info('Iniciando cleanup runner...')

    async for session in get_session():
        results = await run_all_tasks(session)
        log_report(results)

        logger.info('Cleanup runner finalizado.')
        break


if __name__ == '__main__':
    asyncio.run(main())
