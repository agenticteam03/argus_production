"""Static safety and behavior contract for the disposable RB-002 practice lab."""

from pathlib import Path
import unittest


LAB_DIR = Path(__file__).resolve().parent


class LabContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose = (LAB_DIR / "compose.yaml").read_text(encoding="utf-8")
        cls.dockerfile = (LAB_DIR / "Dockerfile").read_text(encoding="utf-8")
        cls.app = (LAB_DIR / "app.py").read_text(encoding="utf-8")

    def test_lab_uses_only_disposable_named_objects(self) -> None:
        self.assertIn("argus-lab-rb002", self.compose)
        self.assertIn("argus-rb002-net", self.compose)
        self.assertNotIn("volumes:", self.compose)

    def test_lab_is_bounded_and_unprivileged(self) -> None:
        for expected in (
            "127.0.0.1:18082:8080",
            "read_only: true",
            "no-new-privileges:true",
            "cap_drop:",
            "mem_limit: 64m",
            "pids_limit: 64",
            'restart: "no"',
        ):
            self.assertIn(expected, self.compose)
        self.assertIn("USER 65532:65532", self.dockerfile)

    def test_health_check_matches_runbook_lab_timing(self) -> None:
        self.assertIn("interval: 15s", self.compose)
        self.assertIn("timeout: 3s", self.compose)
        self.assertIn("retries: 3", self.compose)

    def test_fixture_creates_a_running_service_health_contradiction(self) -> None:
        self.assertIn("PORT = 8080", self.app)
        self.assertIn("/health", self.app)
        self.assertIn("127.0.0.1:8081/health", self.compose)


if __name__ == "__main__":
    unittest.main()
