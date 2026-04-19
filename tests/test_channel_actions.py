"""channel_actions 유틸 테스트."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path


def test_pick_avatar_file_from_object_topic(tmp_path, monkeypatch):
    from worker import channel_actions

    root = tmp_path / "avatars"
    (root / "object" / "flower").mkdir(parents=True)
    for i in range(3):
        (root / "object" / "flower" / f"flower_{i:03d}.png").write_bytes(b"x")
    monkeypatch.setattr(channel_actions, "AVATARS_ROOT", root)

    persona = {"slot_id": 42, "age": 25, "gender": "male"}
    plan = {"avatar_plan": {"topic": "flower"}}
    path = channel_actions.pick_avatar_file(persona, plan)
    assert path is not None
    assert "flower" in path


def test_pick_avatar_file_face_uses_gender_age(tmp_path, monkeypatch):
    from worker import channel_actions

    root = tmp_path / "avatars"
    (root / "female" / "30s").mkdir(parents=True)
    (root / "female" / "30s" / "f30_007.png").write_bytes(b"x")
    monkeypatch.setattr(channel_actions, "AVATARS_ROOT", root)

    persona = {"slot_id": 1, "age": 34, "gender": "female"}
    plan = {"avatar_plan": {"topic": "face"}}
    path = channel_actions.pick_avatar_file(persona, plan)
    assert path is not None
    assert "female/30s/f30_007" in path


def test_pick_avatar_file_returns_none_when_no_plan():
    from worker.channel_actions import pick_avatar_file
    assert pick_avatar_file({"age": 25}, {}) is None
    assert pick_avatar_file({"age": 25}, {"avatar_plan": None}) is None
    assert pick_avatar_file({"age": 25}, {"avatar_plan": {"topic": None}}) is None


def test_pick_avatar_file_missing_folder_returns_none(tmp_path, monkeypatch):
    from worker import channel_actions
    monkeypatch.setattr(channel_actions, "AVATARS_ROOT", tmp_path / "nope")
    path = channel_actions.pick_avatar_file(
        {"age": 25, "gender": "male"}, {"avatar_plan": {"topic": "flower"}},
    )
    assert path is None
