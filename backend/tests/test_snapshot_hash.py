"""Snapshot hashing determinism tests."""

from __future__ import annotations

import unittest

from app.services.device_command_service import _snapshot_hash


class SnapshotHashTests(unittest.TestCase):
    def test_snapshot_hash_is_deterministic(self) -> None:
        payload = {"users": [{"user_id": "E001", "name": "A"}, {"user_id": "E002", "name": "B"}]}
        self.assertEqual(_snapshot_hash(payload), _snapshot_hash(payload))

    def test_snapshot_hash_changes_on_mutation(self) -> None:
        left = {"users": [{"user_id": "E001", "name": "A"}]}
        right = {"users": [{"user_id": "E001", "name": "B"}]}
        self.assertNotEqual(_snapshot_hash(left), _snapshot_hash(right))


if __name__ == "__main__":
    unittest.main()
