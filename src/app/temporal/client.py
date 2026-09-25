from temporalio.client import Client

from app.core.config import config

# Populated once by main.py's lifespan on startup. Client.connect() is async
# and relatively expensive, so it happens exactly once per process — never
# per request.
_client: Client | None = None


async def connect() -> Client | None:
    """Connect to Temporal, or return None if it's unreachable.

    Deliberately non-fatal: the API and Temporal are separate deployables,
    and a developer running `make dev` without `make temporal-up` (or a
    test run, or Temporal being briefly down) shouldn't take the whole app
    down with it. Uploads simply fail with a clear error (get_client raises)
    until Temporal comes back — the same posture as /health vs /health/db.
    """
    global _client
    try:
        _client = await Client.connect(config.temporal_host, namespace=config.temporal_namespace)
    except RuntimeError:
        _client = None
    return _client


def get_client() -> Client:
    if _client is None:
        raise RuntimeError(
            "Temporal client not connected. Did the app startup lifespan run "
            "(app.temporal.client.connect)?"
        )
    return _client
