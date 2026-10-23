"""python-decouple configuration tests."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from decouple import Config, Csv, RepositoryEnv
from django.conf import settings
from django.test import SimpleTestCase

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent


def _run_settings(env_text, extra_env=None):
    """Import a copy of config/settings.py in a temp dir with the given .env. Returns CompletedProcess."""
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "config").mkdir()
        shutil.copy(BACKEND / "config" / "settings.py", tmp / "config" / "settings.py")
        (tmp / "config" / "__init__.py").write_text("")
        (tmp / ".env").write_text(env_text)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "AI_PROVIDER", "DEBUG", "WHATSAPP_"))}
        env.update(extra_env or {})
        code = "import config.settings as s; print('DEBUG', s.DEBUG); print('HOSTS', s.ALLOWED_HOSTS); print('PROVIDER', s.AI_PROVIDER)"
        return subprocess.run([sys.executable, "-c", code], cwd=tmp, env=env, capture_output=True, text=True, timeout=60)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class DecoupleConfigTests(SimpleTestCase):
    def test_settings_loaded_through_decouple(self):
        self.assertTrue(settings.SECRET_KEY)
        self.assertIn(settings.AI_PROVIDER, ("gemini", "deepseek", "groq"))
        self.assertIsInstance(settings.DEBUG, bool)
        self.assertIsInstance(settings.ALLOWED_HOSTS, list)

    def test_typed_values_are_cast(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / ".env").write_text("DEBUG=False\nFLAG=yes\nHOSTS=a.com, b.com\nTIMEOUT=42\n")
            cfg = Config(RepositoryEnv(str(tmp / ".env")))
            self.assertIs(cfg("DEBUG", cast=bool), False)
            self.assertIs(cfg("FLAG", cast=bool), True)
            self.assertEqual(cfg("HOSTS", cast=Csv()), ["a.com", "b.com"])
            self.assertEqual(cfg("TIMEOUT", cast=int), 42)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_valid_env_file_loads(self):
        r = _run_settings("DJANGO_SECRET_KEY=abc-very-secret-key-1234567890\nDEBUG=True\nALLOWED_HOSTS=x.test,y.test\nAI_PROVIDER=DeepSeek\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DEBUG True", r.stdout)
        self.assertIn("['x.test', 'y.test']", r.stdout)
        self.assertIn("PROVIDER deepseek", r.stdout)

    def test_missing_secret_key_fails_clearly(self):
        r = _run_settings("DEBUG=True\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", r.stderr)

    def test_invalid_ai_provider_rejected(self):
        r = _run_settings("DJANGO_SECRET_KEY=abc-very-secret-key-1234567890\nAI_PROVIDER=openai\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("AI_PROVIDER must be one of", r.stderr)

    def test_placeholder_secret_rejected_when_not_debug(self):
        r = _run_settings("DJANGO_SECRET_KEY=replace-me\nDEBUG=False\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY must be set", r.stderr)

    def test_unsigned_webhooks_refused_outside_debug(self):
        r = _run_settings("DJANGO_SECRET_KEY=abc-very-secret-key-1234567890\nDEBUG=False\nWHATSAPP_ALLOW_UNSIGNED_WEBHOOKS=True\n")
        self.assertNotEqual(r.returncode, 0)

    def test_env_example_has_no_real_credentials(self):
        text = (BACKEND / ".env.example").read_text()
        secret_markers = ("KEY", "TOKEN", "SECRET", "PASSWORD")
        for line in text.splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if any(m in key for m in secret_markers) and key not in ("WHATSAPP_ALLOW_UNSIGNED_WEBHOOKS",):
                self.assertIn(value.strip(), ("", "replace-me"), f"{key} must be empty in .env.example")

    def test_real_env_is_git_ignored(self):
        if shutil.which("git") is None or not (REPO / ".git").exists():
            self.skipTest("git not available")
        r = subprocess.run(["git", "check-ignore", "-q", "backend/.env"], cwd=REPO)
        self.assertEqual(r.returncode, 0, "backend/.env must be ignored by git")
        r2 = subprocess.run(["git", "check-ignore", "-q", "backend/.env.example"], cwd=REPO)
        self.assertNotEqual(r2.returncode, 0, ".env.example must NOT be ignored")


class RemovedProviderTests(SimpleTestCase):
    def test_grok_is_not_an_accepted_provider(self):
        r = _run_settings("DJANGO_SECRET_KEY=abc-very-secret-key-1234567890\nAI_PROVIDER=grok\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("AI_PROVIDER must be one of gemini, deepseek, groq", r.stderr)
