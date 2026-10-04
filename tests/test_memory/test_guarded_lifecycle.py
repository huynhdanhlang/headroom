"""Exact ownership/current-version guards on the retained SQLite owner."""
import asyncio
import hashlib
import sqlite3

import pytest

from headroom.memory.adapters.sqlite import SQLiteMemoryStore
from headroom.memory.models import Memory
from headroom.memory.ports import TextFilter


@pytest.fixture
def system(tmp_path):
    from headroom.memory.adapters.fts5 import FTS5TextIndex
    from headroom.memory.adapters.sqlite_vector import SQLiteVectorIndex
    from headroom.memory.core import HierarchicalMemory
    class NoPaidEmbedder:
        async def embed(self, text):
            raise AssertionError("foreign writes must be rejected before embedding")
    return HierarchicalMemory(
        SQLiteMemoryStore(tmp_path / "memory.db"),
        SQLiteVectorIndex(dimension=2, db_path=tmp_path / "vectors.db"),
        FTS5TextIndex(tmp_path / "text.db"), NoPaidEmbedder(),
    )


def digest(text):
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


async def seed(store, content, owner="alice"):
    memory = Memory(content=content, user_id=owner)
    await store.save(memory)
    return memory


def test_content_hash_is_exact_utf8_not_a_summary():
    memory = Memory(content="Đừng dùng dữ liệu giả.")
    assert memory.content_hash == digest("Đừng dùng dữ liệu giả.")
    memory.content += " "
    assert memory.content_hash == digest("Đừng dùng dữ liệu giả. ")


@pytest.mark.parametrize("owner,version,identifier", [
    ("bob", None, None), ("alice", "sha256:stale", None),
    ("alice", None, "nonexistent"),
])
async def test_guarded_supersession_rejects_foreign_stale_or_missing(tmp_path, owner, version, identifier):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    old = await seed(store, "Never use fake data.")
    successor = Memory(content="Only synthetic test data.", user_id=owner)
    with pytest.raises(ValueError) as error:
        await store.supersede(identifier or old.id, successor,
                             expected_user_id=owner, expected_content_hash=version or digest(old.content))
    assert type(error.value).__name__ == "MemoryConflictError"
    assert (await store.get(old.id)).is_current
    assert await store.get(successor.id) is None
    assert successor.supersedes is None


async def test_competing_successors_have_one_winner_and_history(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    old = await seed(store, "Never use fake data.")
    successors = [Memory(content=text, user_id="alice") for text in ("Use fixtures.", "Use live data.")]
    results = await asyncio.gather(*[
        store.supersede(old.id, candidate, expected_user_id="alice",
                        expected_content_hash=digest(old.content)) for candidate in successors
    ], return_exceptions=True)
    winners = [r for r in results if isinstance(r, Memory)]
    assert len(winners) == 1
    losers = [r for r in results if isinstance(r, Exception)]
    assert len(losers) == 1 and type(losers[0]).__name__ == "MemoryConflictError"
    current = await store.get(old.id)
    assert current.content == old.content and current.superseded_by == winners[0].id
    assert len(await store.get_history(winners[0].id)) == 2
    assert successors[1].supersedes is None


async def test_failed_successor_insert_rolls_back_old_row_and_input(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    old = await seed(store, "Old rule")
    with store._get_conn() as conn:
        conn.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON memories BEGIN SELECT RAISE(ABORT, 'interrupted'); END")
    candidate = Memory(content="New rule", user_id="alice")
    with pytest.raises(sqlite3.IntegrityError, match="interrupted"):
        await store.supersede(old.id, candidate, expected_user_id="alice",
                             expected_content_hash=digest(old.content))
    assert (await store.get(old.id)).is_current
    assert await store.get(candidate.id) is None
    assert candidate.supersedes is None


async def test_guarded_successor_cannot_replace_an_unrelated_id(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    old = await seed(store, "Old rule")
    unrelated = await seed(store, "Unrelated evidence")
    with pytest.raises(ValueError):
        await store.supersede(old.id, Memory(id=unrelated.id, content="Replacement", user_id="alice"),
                             expected_user_id="alice", expected_content_hash=digest(old.content))
    assert (await store.get(unrelated.id)).content == "Unrelated evidence"
    assert (await store.get(old.id)).is_current


async def test_forget_is_guarded_and_retains_audit_history(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    old = await seed(store, "Never use fake data.")
    for owner, version in [("bob", digest(old.content)), ("alice", "stale")]:
        with pytest.raises(ValueError):
            await store.forget(old.id, user_id=owner, expected_content_hash=version, reason="owner request")
        assert (await store.get(old.id)).is_current
    assert await store.forget(old.id, user_id="alice", expected_content_hash=digest(old.content), reason="owner request")
    forgotten = await store.get(old.id)
    assert not forgotten.is_current
    assert forgotten.content == old.content
    assert forgotten.metadata["forget_reason"] == "owner request"
    assert forgotten.metadata["forgotten_at"]
    with pytest.raises(ValueError):
        await store.supersede(old.id, Memory(content="New rule", user_id="alice"),
                             expected_user_id="alice", expected_content_hash=digest(old.content))


async def test_core_rejects_foreign_owner_before_embedding(system):
    old = await system.add("Alice private rule", "alice", auto_embed=False)
    with pytest.raises(ValueError) as error:
        await system.supersede(old.id, "Bob replacement", expected_user_id="bob",
                               expected_content_hash=digest(old.content))
    assert type(error.value).__name__ == "MemoryConflictError"
    assert (await system.get(old.id)).content == "Alice private rule"


async def test_core_update_and_forget_remove_active_text_recall(system):
    old = await system.add("obsolete rule xyzzy", "alice", auto_embed=False)
    new = await system.supersede(old.id, "current rule xyzzy", auto_embed=False,
                                expected_user_id="alice", expected_content_hash=digest(old.content),
                                metadata_updates={"update_reason": "owner correction"})
    results = system._text_index.search("xyzzy", filter=TextFilter(query="xyzzy", user_id="alice"))
    assert [r.memory_id for r in results] == [new.id]
    assert new.metadata["update_reason"] == "owner correction"
    assert len(await system.get_history(new.id)) == 2
    await system.forget(new.id, user_id="alice", expected_content_hash=digest(new.content), reason="owner forget")
    assert system._text_index.search("xyzzy", filter=TextFilter(query="xyzzy", user_id="alice")) == []


async def test_local_backend_forwards_owner_hash_and_audit_reason(system):
    from headroom.memory.backends.local import LocalBackend
    backend = LocalBackend()
    backend._hierarchical_memory = system
    backend._initialized = True
    old = await system.add("Private rule", "alice", auto_embed=False)
    with pytest.raises(ValueError):
        await backend.update_memory(old.id, "Hijack", reason="test", user_id="bob",
                                    expected_content_hash=digest(old.content))
    # Deterministic embedding is a test-only substitute for paid/network I/O.
    import numpy as np
    class FixtureEmbedder:
        async def embed(self, text):
            return np.array([1.0, 0.0], dtype=np.float32)
    system._embedder = FixtureEmbedder()
    new = await backend.update_memory(old.id, "Correct rule", reason="owner correction", user_id="alice",
                                      expected_content_hash=digest(old.content))
    assert new.metadata["update_reason"] == "owner correction"
    assert await backend.delete_memory_guarded(new.id, "alice", digest(new.content), "owner forget")
    assert not (await system.get(new.id)).is_current


async def test_evidence_replay_and_independent_similar_facts(system):
    kwargs = {"content": "Remember this rule", "user_id": "alice", "auto_embed": False,
              "evidence_key": "session:message:clause1", "metadata": {"source_text": "Remember this rule"}}
    results = await asyncio.gather(system.add(**kwargs), system.add(**kwargs))
    assert results[0].id == results[1].id
    assert results[0].replayed is False and results[1].replayed is True
    with pytest.raises(ValueError):
        await system.add(**{**kwargs, "content": "A changed rule"})
    other = await system.add(**{**kwargs, "evidence_key": "session:message:clause2"})
    foreign = await system.add(**{**kwargs, "user_id": "bob"})
    assert len({results[0].id, other.id, foreign.id}) == 3


async def test_index_failure_retry_repairs_only_active_durable_row(system, monkeypatch):
    original = system._text_index.index_memory
    async def interrupted(memory):
        raise RuntimeError("index interrupted")
    monkeypatch.setattr(system._text_index, "index_memory", interrupted)
    kwargs = {"content": "xyzzy remembered rule", "user_id": "alice", "auto_embed": False,
              "evidence_key": "session:message:1"}
    with pytest.raises(RuntimeError, match="interrupted"):
        await system.add(**kwargs)
    monkeypatch.setattr(system._text_index, "index_memory", original)
    memory = await system.add(**kwargs)
    assert memory.replayed is True
    assert len(system._text_index.search("xyzzy")) == 1
    new = await system.supersede(memory.id, "corrected rule xyzzy", auto_embed=False,
                                expected_user_id="alice", expected_content_hash=digest(memory.content))
    replay = await system.add(**kwargs)
    assert replay.replayed and not replay.is_current
    assert [r.memory_id for r in system._text_index.search("xyzzy")] == [new.id]


async def test_forgotten_evidence_never_revives_on_restart(system):
    kwargs = {"content": "xyzzy remembered rule", "user_id": "alice", "auto_embed": False,
              "evidence_key": "session:message:1"}
    memory = await system.add(**kwargs)
    await system.forget(memory.id, user_id="alice", expected_content_hash=digest(memory.content), reason="forget")
    # Fresh primary-store connection and empty process cache model a backend restart.
    system._store = SQLiteMemoryStore(system._store.db_path)
    replay = await system.add(**kwargs)
    assert not replay.is_current and replay.metadata["forgotten_at"]
    assert system._text_index.search("xyzzy") == []


async def test_local_fact_clauses_have_distinct_replay_keys(system):
    from headroom.memory.backends.local import LocalBackend
    from headroom.memory.ports import MemoryFilter
    from types import SimpleNamespace
    import numpy as np
    class FixtureEmbedder:
        async def embed(self, text):
            return np.array([1.0, 0.0], dtype=np.float32)
    system._embedder = FixtureEmbedder()
    backend = LocalBackend()
    backend._initialized = True
    backend._hierarchical_memory = system
    backend._graph = SimpleNamespace()
    for _ in range(2):
        await backend.save_memory("Two facts", "alice", facts=["Rule one", "Rule two"],
                                  evidence_key="session:message")
    rows = await system._store.query(MemoryFilter(user_id="alice"))
    assert len(rows) == 2
    assert {r.content for r in rows} == {"Rule one", "Rule two"}


async def test_local_list_uses_primary_recency_not_an_empty_embedding_query(system):
    from headroom.memory.backends.local import LocalBackend
    backend = LocalBackend()
    backend._hierarchical_memory = system
    backend._initialized = True
    old = await system.add("Original rule", "alice", auto_embed=False)
    new = await system.supersede(old.id, "Current rule", auto_embed=False)
    await system.add("Foreign rule", "bob", auto_embed=False)
    rows = await backend.list_memories("alice", limit=10)
    assert [m.id for m in rows] == [new.id]


@pytest.mark.parametrize("changed", [
    {"content": "changed", "facts": ["Rule A", "Rule B"]},
    {"content": "original", "facts": ["Rule A", "Rule B"]},
    {"content": "original", "facts": None},
])
async def test_fact_event_identity_rejects_any_changed_original_payload(system, changed):
    from headroom.memory.backends.local import LocalBackend
    from headroom.memory.ports import MemoryFilter
    from types import SimpleNamespace
    import numpy as np
    class FixtureEmbedder:
        async def embed(self, text):
            return np.array([1.0, 0.0], dtype=np.float32)
    system._embedder = FixtureEmbedder()
    backend = LocalBackend()
    backend._initialized = True
    backend._hierarchical_memory = system
    backend._graph = SimpleNamespace()
    await backend.save_memory("original", "alice", facts=["Rule A"], evidence_key="event")
    with pytest.raises(ValueError):
        await backend.save_memory(user_id="alice", evidence_key="event", **changed)
    assert len(await system._store.query(MemoryFilter(user_id="alice"))) == 1


@pytest.mark.parametrize("failed_step", ["remove", "index"])
async def test_committed_update_recovers_after_restart_from_primary_pending_evidence(system, monkeypatch, failed_step):
    from headroom.memory.backends.local import LocalBackend
    old = await system.add("Old xyzzy rule", "alice", auto_embed=False)
    original = getattr(system.vector_index, failed_step)
    async def interrupted(*args):
        raise RuntimeError("index interrupted")
    monkeypatch.setattr(system.vector_index, failed_step, interrupted)
    if failed_step == "index":
        import numpy as np
        class FixtureEmbedder:
            async def embed(self, text):
                return np.array([1.0, 0.0], dtype=np.float32)
        system._embedder = FixtureEmbedder()
    with pytest.raises(RuntimeError):
        await system.supersede(old.id, "Corrected xyzzy rule", expected_user_id="alice",
                               expected_content_hash=digest(old.content), auto_embed=failed_step == "index")
    successor_id = (await system._store.get(old.id)).superseded_by
    monkeypatch.setattr(system.vector_index, failed_step, original)
    # Fresh store/empty process caches; initialization/search must repair the
    # committed current row before recalling or declaring it absent.
    system._store = SQLiteMemoryStore(system._store.db_path)
    backend = LocalBackend()
    backend._initialized = True
    backend._hierarchical_memory = system
    rows = await backend.list_memories("alice")
    assert [r.id for r in rows] == [successor_id]
    assert [r.memory_id for r in system.text_index.search("xyzzy")] == [successor_id]
    assert not (await system._store.get(successor_id)).metadata.get("index_pending")
