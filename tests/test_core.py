import os
import tempfile
import unittest
from rednexus.core import Nexus, Principal, Capability


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.n = Nexus()
        self.calls = []

        def handler(payload, previous):
            self.calls.append(payload)
            return {"ok": True}

        self.handler = handler
        self.n.register(Capability("test.read", "test", "1"), handler)
        self.n.register(Capability("test.propose", "test", "1", True), handler)
        self.p = Principal(
            "user",
            "a",
            frozenset(
                ["workflow:run", "tool:test.read", "tool:test.propose", "memory:shared:write", "memory:shared:read"]
            ),
        )
        self.r = Principal("reviewer", "a", frozenset(["approval:review"]))

    def tearDown(self):
        self.n.close()

    def submit(self, cap="test.read", key="1"):
        return self.n.submit(self.p, [{"capability": cap, "input": {"x": 1}}], key)

    def test_completed_run_is_not_executed_twice(self):
        run = self.submit()
        self.assertEqual(self.n.advance(self.p, run)["status"], "completed")
        self.n.advance(self.p, run)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.submit(), run)

    def test_key_conflict(self):
        self.submit()
        with self.assertRaises(ValueError):
            self.n.submit(self.p, [{"capability": "test.read", "input": {}}], "1")

    def test_approval_blocks_execution_and_repeated_wait_is_quiet(self):
        run = self.submit("test.propose")
        self.assertEqual(self.n.advance(self.p, run)["status"], "waiting_approval")
        self.n.advance(self.p, run)
        self.assertEqual(len(self.calls), 0)
        self.assertEqual(len(self.n.events(self.p, run)), 2)
        self.n.review(self.r, run, True)
        self.assertEqual(self.n.advance(self.p, run)["status"], "completed")
        with self.assertRaises(ValueError):
            self.n.review(self.r, run, True)

    def test_rejection(self):
        run = self.submit("test.propose")
        self.n.advance(self.p, run)
        self.n.review(self.r, run, False)
        self.assertEqual(self.n.advance(self.p, run)["status"], "rejected")
        self.assertFalse(self.calls)

    def test_self_review_and_cross_tenant_review_denied(self):
        run = self.submit("test.propose")
        self.n.advance(self.p, run)
        for reviewer in [Principal("user", "a", self.r.grants), Principal("reviewer", "b", self.r.grants)]:
            with self.assertRaises(PermissionError):
                self.n.review(reviewer, run, True)

    def test_cross_tenant_run_access_denied(self):
        run = self.submit()
        other = Principal("user", "b", self.p.grants)
        with self.assertRaises(PermissionError):
            self.n.advance(other, run)
        with self.assertRaises(PermissionError):
            self.n.events(other, run)

    def test_revoked_tool_permission_checked_again(self):
        run = self.submit()
        revoked = Principal("user", "a", frozenset(["workflow:run"]))
        with self.assertRaises(PermissionError):
            self.n.advance(revoked, run)
        self.assertFalse(self.calls)

    def test_memory_isolation_and_provenance(self):
        self.n.remember(self.p, "shared", "k", {"fact": 1}, "source:1")
        other = Principal("user", "b", self.p.grants)
        self.assertIsNone(self.n.recall(other, "shared", "k"))
        self.assertEqual(self.n.recall(self.p, "shared", "k")["source"], "source:1")
        with self.assertRaises(PermissionError):
            self.n.recall(Principal("x", "a", frozenset()), "shared", "k")

    def test_handler_failure_does_not_retry(self):
        def broken(*args):
            raise ValueError("sensitive error")

        self.n.register(Capability("broken", "test", "1"), broken)
        p = Principal("user", "a", self.p.grants | {"tool:broken"})
        run = self.n.submit(p, [{"capability": "broken", "input": {}}], "fail")
        self.assertEqual(self.n.advance(p, run)["status"], "failed")
        self.assertNotIn("sensitive error", str(self.n.events(p, run)))

    def test_cancelled_workflow_cannot_execute(self):
        run = self.submit()
        self.n.cancel(self.p, run)
        self.assertEqual(self.n.advance(self.p, run)["status"], "cancelled")
        self.assertFalse(self.calls)

    def test_contract_change_fails_closed(self):
        run = self.submit()
        self.n.registry["test.read"] = (Capability("test.read", "test", "2"), self.handler)
        with self.assertRaises(RuntimeError):
            self.n.advance(self.p, run)

    def test_restart_resumes_waiting_run(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "nexus.db")
            first = Nexus(path)
            first.register(Capability("test.propose", "test", "1", True), self.handler)
            run = first.submit(self.p, [{"capability": "test.propose", "input": {}}], "1")
            first.advance(self.p, run)
            first.close()
            second = Nexus(path)
            try:
                second.register(Capability("test.propose", "test", "1", True), self.handler)
                second.review(self.r, run, True)
                self.assertEqual(second.advance(self.p, run)["status"], "completed")
            finally:
                second.close()

    def test_uncertain_running_step_is_not_replayed(self):
        run = self.submit()
        with self.n.db:
            self.n.db.execute("UPDATE runs SET status='running' WHERE id=?", (run,))
        with self.assertRaises(RuntimeError):
            self.n.advance(self.p, run)
        self.assertFalse(self.calls)


if __name__ == "__main__":
    unittest.main()
