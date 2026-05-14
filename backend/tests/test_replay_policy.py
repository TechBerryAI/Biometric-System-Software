"""Replay safety and write-policy regression tests."""

from __future__ import annotations

from dataclasses import dataclass
import unittest

from app.core.config import Settings
from app.services.device_command_service import _enforce_safe_write_policy, _execution_hash


@dataclass
class _DummyCommand:
    device_id: str
    command_type: str
    payload: dict


def _settings(**overrides):
    data = Settings().model_dump()
    data.update(overrides)
    return Settings(**data)


class ReplayPolicyTests(unittest.TestCase):
    def test_execution_hash_is_stable_for_same_attempt(self) -> None:
        command = _DummyCommand(
            device_id="device-1",
            command_type="UPSERT_USER",
            payload={"user_id": "E001", "name": "Alice"},
        )
        one = _execution_hash(command, 1)
        two = _execution_hash(command, 1)
        self.assertEqual(one, two)

    def test_execution_hash_changes_across_attempts(self) -> None:
        command = _DummyCommand(
            device_id="device-1",
            command_type="UPSERT_USER",
            payload={"user_id": "E001", "name": "Alice"},
        )
        self.assertNotEqual(_execution_hash(command, 1), _execution_hash(command, 2))

    def test_uid_rewrite_is_blocked_without_override(self) -> None:
        ok, message = _enforce_safe_write_policy(
            settings=_settings(allow_device_uid_rewrite=False, allow_device_admin_override=False),
            payload={"user_id": "E001", "uid": 1002},
            current_on_device={"uid": 1001},
            firmware_profile=None,
        )
        self.assertFalse(ok)
        self.assertIsNotNone(message)
        self.assertIn("uid rewrite blocked", str(message))


if __name__ == "__main__":
    unittest.main()
