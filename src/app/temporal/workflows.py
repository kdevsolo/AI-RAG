from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# Workflow code is replayed deterministically from event history, so the
# sandbox forbids non-deterministic imports at module scope. The activity
# functions never execute inside this sandboxed process — they're dispatched
# to the worker's thread pool — so importing their definitions here is safe;
# this just tells the sandbox to trust that.
with workflow.unsafe.imports_passed_through():
    from app.temporal.activities import (
        ChunkAndStoreInput,
        EmbedChunksInput,
        chunk_and_store,
        embed_chunks,
        mark_failed,
        mark_ready,
        parse_document,
    )
    from app.temporal.shared import IngestDocumentInput, MarkFailedInput

# A corrupt/unsupported file will never parse on retry — retrying just burns
# time before reaching the same failure. UnsupportedFileTypeError subclasses
# ValueError (see app/rag/parsers.py), so listing ValueError here covers both.
_NON_RETRYABLE_ERROR_TYPES = ["ValueError", "UnsupportedFileTypeError"]


@workflow.defn
class IngestDocumentWorkflow:
    def __init__(self) -> None:
        self._status = "pending"

    @workflow.query
    def status(self) -> str:
        # Must not mutate state, must not block — a read-only snapshot for
        # callers to poll (e.g. a stuck-document diagnostic endpoint).
        return self._status

    @workflow.run
    async def run(self, inp: IngestDocumentInput) -> int:
        retry = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=30),
            maximum_attempts=5,
            non_retryable_error_types=_NON_RETRYABLE_ERROR_TYPES,
        )
        try:
            self._status = "parsing"
            text = await workflow.execute_activity(
                parse_document,
                inp,
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry,
            )

            self._status = "chunking"
            chunk_count = await workflow.execute_activity(
                chunk_and_store,
                ChunkAndStoreInput(document_id=inp.document_id, text=text),
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry,
            )

            self._status = "embedding"
            await workflow.execute_activity(
                embed_chunks,
                EmbedChunksInput(document_id=inp.document_id),
                start_to_close_timeout=timedelta(minutes=30),  # many OpenAI round-trips
                heartbeat_timeout=timedelta(seconds=60),  # detect a dead worker in 60s
                retry_policy=retry,
            )

            await workflow.execute_activity(
                mark_ready,
                inp.document_id,
                start_to_close_timeout=timedelta(seconds=30),
            )
            self._status = "ready"
            return chunk_count
        except Exception as exc:
            # Compensation: don't leave the row stuck in "embedding" forever.
            self._status = "failed"
            await workflow.execute_activity(
                mark_failed,
                MarkFailedInput(document_id=inp.document_id, error=str(exc)),
                start_to_close_timeout=timedelta(seconds=30),
            )
            raise
