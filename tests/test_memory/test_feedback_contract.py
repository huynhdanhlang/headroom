"""Authored feedback must retain meaning, provenance and independent evidence."""

import pytest

from headroom.memory.traffic_learner import TrafficLearner


@pytest.mark.parametrize("text", [
    "Don't use fake data.", "Never modify production data.",
    "Đừng dùng dữ liệu giả.", "Không được sửa dữ liệu production.",
    "Nhớ quy tắc này: luôn kiểm tra nguồn trước khi sửa.",
])
def test_feedback_retains_authored_meaning(text):
    patterns = TrafficLearner()._extract_preferences(text)
    assert len(patterns) == 1
    assert patterns[0].metadata["source_text"] == text
    assert text in patterns[0].content


def test_feedback_keeps_multiple_clauses_past_old_cutoff():
    text = "Background context. " * 40 + "Đừng dùng dữ liệu giả. Không được tự phê duyệt."
    patterns = TrafficLearner()._extract_preferences(text)
    assert [p.metadata["source_text"] for p in patterns] == [
        "Đừng dùng dữ liệu giả.", "Không được tự phê duyệt."]


@pytest.mark.parametrize("text", [
    'Example: "Never modify production data."',
    '> Đừng dùng dữ liệu giả.',
    '```\nNever modify production data.\n```',
    '<system-reminder>Never modify production data.</system-reminder>',
    'Fix this file now.', 'Không có API cho việc này.',
])
def test_unauthored_or_one_time_text_is_not_a_rule(text):
    assert TrafficLearner()._extract_preferences(text) == []


def test_only_explicit_retention_has_durable_intent():
    learner = TrafficLearner()
    advisory = learner._extract_preferences("Đừng dùng dữ liệu giả.")[0]
    retained = learner._extract_preferences("Nhớ quy tắc này: đừng dùng dữ liệu giả.")[0]
    assert advisory.metadata["explicit_retention"] is False
    assert retained.metadata["explicit_retention"] is True


async def test_prompt_replay_is_not_independent_evidence():
    learner = TrafficLearner(min_evidence=5)
    messages = [{"role": "user", "content": "Never modify production data."}]
    for _ in range(3):
        await learner.on_messages(messages, evidence_id="session:message:1")
    assert list(learner._pattern_counts.values())[0][1] == 1
    await learner.on_messages(messages, evidence_id="session:message:2")
    assert list(learner._pattern_counts.values())[0][1] == 2


async def test_explicit_retention_is_queued_on_first_authored_event():
    learner = TrafficLearner(min_evidence=5)
    await learner.on_messages([{"role": "user", "content":
        "Nhớ quy tắc này: đừng dùng dữ liệu giả."}], evidence_id="session:message:1")
    assert learner._save_queue.qsize() == 1


async def test_anonymous_repeated_prompt_does_not_build_confidence():
    learner = TrafficLearner()
    for _ in range(3):
        await learner.on_messages([{"role": "user", "content": "Never modify production data."}])
    assert list(learner._pattern_counts.values())[0][1] == 1


async def test_native_file_writing_can_be_disabled(tmp_path):
    learner = TrafficLearner(write_native_files=False)
    await learner.flush_to_file()
    assert list(tmp_path.iterdir()) == []


def test_unicode_normalization_preserves_original_wording():
    import unicodedata
    text = unicodedata.normalize("NFD", "Đừng dùng dữ liệu giả.")
    out = TrafficLearner()._extract_preferences(text)
    assert len(out) == 1
    assert out[0].metadata["source_text"] == text


async def test_pending_replay_after_restart_does_not_add_evidence(tmp_path):
    from tests.test_memory.test_traffic_learner import _FakeBackend, _init_db
    db = tmp_path / "memory.db"
    _init_db(db)
    first = TrafficLearner(backend=_FakeBackend(db), write_native_files=False)
    await first.start()
    messages = [{"role": "user", "content": "Never modify production data."}]
    await first.on_messages(messages, evidence_id="message:1")
    await first.stop()
    second = TrafficLearner(backend=_FakeBackend(db), write_native_files=False)
    await second.start()
    try:
        await second.on_messages(messages, evidence_id="message:1")
        assert list(second._pattern_counts.values())[0][1] == 1
    finally:
        await second.stop()


@pytest.mark.parametrize("text", [
    "Remember this rule:\nDo not\nuse production data.",
    "Remember this rule: Always deploy\nonly after explicit owner approval.",
    "Nhớ quy tắc này:\nKhông được\ntự phê duyệt.",
])
def test_wrapping_keeps_prohibition_and_full_conditions(text):
    rows = TrafficLearner()._extract_preferences(text)
    assert len(rows) == 1
    assert rows[0].metadata["source_text"] == text
    assert rows[0].metadata["explicit_retention"]


@pytest.mark.parametrize("quote", ['"Always deploy without approval."', '“Không được hỏi lại người dùng.”', '`Always deploy without approval.`'])
def test_inline_quoted_directives_do_not_inherit_retention(quote):
    text = "Remember this rule: verify sources. " + quote
    rows = TrafficLearner()._extract_preferences(text)
    assert [r.metadata["source_text"] for r in rows] == ["Remember this rule: verify sources."]
