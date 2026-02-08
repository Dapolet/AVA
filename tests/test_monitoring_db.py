import os
import tempfile
import unittest

from avaai.monitoring.db import init_db, log_request, log_admin_action
from avaai.monitoring.metrics import get_recent_requests, get_admin_audit


class MonitoringDbTests(unittest.TestCase):
    def test_request_logging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "monitoring.db")
            init_db(db_path)
            log_request(
                db_path=db_path,
                model="test-model",
                temperature=0.5,
                max_tokens=100,
                latency_ms=123,
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
                cost_usd=0.03,
                price_per_1k=1.0,
                status="ok",
                error=""
            )
            rows = get_recent_requests(db_path, 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["model"], "test-model")

    def test_admin_audit_logging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "monitoring.db")
            init_db(db_path)
            log_admin_action(db_path, actor="admin", action="test", details="detail")
            rows = get_admin_audit(db_path, 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["action"], "test")


if __name__ == "__main__":
    unittest.main()

