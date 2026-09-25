import unittest

from app.services.url_safety import validate_monitor_url


class UrlValidationTests(unittest.TestCase):
    def test_accepts_public_https_url(self):
        self.assertEqual(
            validate_monitor_url("https://example.com/health"),
            "https://example.com/health",
        )

    def test_rejects_localhost(self):
        with self.assertRaises(ValueError):
            validate_monitor_url("http://localhost:8000")

    def test_rejects_private_ip(self):
        with self.assertRaises(ValueError):
            validate_monitor_url("http://192.168.1.10/status")

    def test_rejects_unsupported_scheme(self):
        with self.assertRaises(ValueError):
            validate_monitor_url("ftp://example.com/file")


if __name__ == "__main__":
    unittest.main()
