import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from app.core.config import config
from app.temporal.activities import (
    chunk_and_store,
    embed_chunks,
    mark_failed,
    mark_ready,
    parse_document,
)
from app.temporal.workflows import IngestDocumentWorkflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    client = await Client.connect(config.temporal_host, namespace=config.temporal_namespace)
    logger.info(
        "Connected to Temporal at %s (namespace=%s), polling task queue %r",
        config.temporal_host,
        config.temporal_namespace,
        config.temporal_task_queue,
    )
    # The five activities are all sync `def`s (see activities.py) — they run
    # in this thread pool, off the worker's asyncio event loop, which is why
    # your existing synchronous SQLAlchemy code works unchanged here.
    with ThreadPoolExecutor(max_workers=8) as executor:
        worker = Worker(
            client,
            task_queue=config.temporal_task_queue,
            workflows=[IngestDocumentWorkflow],
            activities=[
                parse_document,
                chunk_and_store,
                embed_chunks,
                mark_ready,
                mark_failed,
            ],
            activity_executor=executor,
        )
        await worker.run()  # blocks forever, polling for work


if __name__ == "__main__":
    asyncio.run(main())
