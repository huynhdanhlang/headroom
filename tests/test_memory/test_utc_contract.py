"""Persistent timestamps stay naive UTC without Python's deprecated clock API."""
import warnings
from datetime import datetime, timezone

from headroom.memory.adapters.sqlite import SQLiteMemoryStore
from headroom.memory.models import Memory


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_memory_defaults_are_naive_utc_without_deprecation():
    before = utc_now()
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        memory = Memory(content="synthetic timestamp rule", user_id="alice")
    after = utc_now()
    assert memory.created_at.tzinfo is None and memory.valid_from.tzinfo is None
    assert before <= memory.created_at <= after
    assert before <= memory.valid_from <= after


async def test_record_access_persists_naive_utc_without_deprecation(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    historical = datetime(2020, 1, 1)
    memory = Memory(content="synthetic timestamp rule", user_id="alice",
                    created_at=historical, valid_from=historical)
    await store.save(memory)
    before = utc_now()
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        assert await store.record_access([memory.id]) == 1
    after = utc_now()
    current = await store.get(memory.id)
    assert current.last_accessed.tzinfo is None
    assert before <= current.last_accessed <= after
    assert current.access_count == 1
