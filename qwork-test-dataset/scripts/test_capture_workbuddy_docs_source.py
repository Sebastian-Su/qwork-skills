#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import http.server
import json
import pathlib
import socketserver
import tempfile
import threading
import unittest

import capture_workbuddy_docs_source as capture


PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360606060000000050001a5f645400000000049454e44"
    "ae426082"
)


class FixtureHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        payloads = {
            "/sitemap.xml": (
                "application/xml",
                b"<?xml version='1.0' encoding='UTF-8'?>"
                b"<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                b"<url><loc>HTTP_ORIGIN/docs/workbuddy/</loc><lastmod>2026-08-31</lastmod></url>"
                b"<url><loc>HTTP_ORIGIN/docs/workbuddy/Quickstart</loc><lastmod>2026-08-31</lastmod></url>"
                b"<url><loc>HTTP_ORIGIN/docs/workbuddy/Feature</loc><lastmod>2026-08-30</lastmod></url>"
                b"</urlset>",
            ),
            "/docs/workbuddy/": (
                "text/html; charset=utf-8",
                b"<html><head><title>Missing root</title></head><body><p>Not found.</p></body></html>",
            ),
            "/docs/workbuddy/Quickstart": (
                "text/html; charset=utf-8",
                b"<html><head><title>Quickstart</title></head><body>"
                b"<aside>navigation must not be captured</aside>"
                b"<article class='vp-doc'><h1>Quickstart</h1><p>Hello <strong>WorkBuddy</strong>.</p>"
                b"<h2>Result</h2><table><tr><th>Area</th><th>Effect</th></tr>"
                b"<tr><td>Panel</td><td>Preview</td></tr></table>"
                b"<img alt='screen' src='/static/screen.png'>"
                b"<a href='/docs/workbuddy/Feature'>Feature</a></article></body></html>",
            ),
            "/docs/workbuddy/Feature": (
                "text/html; charset=utf-8",
                b"<html><head><title>Feature</title></head><body>"
                b"<main><div class='vp-doc'><h1>Feature</h1><ul><li>First</li><li>Second</li></ul>"
                b"</div></main></body></html>",
            ),
            "/static/screen.png": ("image/png", PNG_1X1),
        }
        content_type, body = payloads.get(self.path, ("text/plain", b"missing"))
        if self.path == "/sitemap.xml":
            body = body.replace(b"HTTP_ORIGIN", self.server.origin.encode("ascii"))
        status = 200 if self.path in payloads else 404
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


class CaptureWorkBuddyDocsSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingServer(("127.0.0.1", 0), FixtureHandler)
        self.server.origin = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_capture_freezes_pages_and_image_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / "snapshot"
            result = capture.capture_source(
                sitemap_url=f"{self.server.origin}/sitemap.xml",
                output=output,
                expected_prefix=f"{self.server.origin}/docs/workbuddy/",
                captured_at="2026-08-31T00:00:00+00:00",
            )

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            inventory = json.loads((output / "inventory.json").read_text(encoding="utf-8"))

            self.assertEqual(result["page_count"], 3)
            self.assertEqual(manifest["source_kind"], "official-web-documentation")
            self.assertEqual(manifest["authority_kind"], "normative")
            self.assertEqual(manifest["page_count"], 3)
            self.assertEqual(manifest["article_page_count"], 2)
            self.assertEqual(manifest["non_article_page_count"], 1)
            self.assertEqual(manifest["image_count"], 1)
            self.assertEqual(manifest["sitemap_lastmod_max"], "2026-08-31")
            self.assertEqual(len(inventory["pages"]), 3)

            root = next(page for page in inventory["pages"] if page["url"].endswith("/workbuddy/"))
            self.assertEqual(root["article_status"], "not-present")

            quickstart = next(page for page in inventory["pages"] if page["url"].endswith("/Quickstart"))
            page = json.loads((output / quickstart["file"]).read_text(encoding="utf-8"))
            self.assertEqual(page["headings"][0]["text"], "Quickstart")
            self.assertIn("Hello WorkBuddy.", page["text"])
            self.assertIn("Area | Effect", page["text"])
            self.assertNotIn("navigation must not be captured", page["text"])
            self.assertEqual(page["images"][0]["width"], 1)
            self.assertEqual(page["images"][0]["height"], 1)
            self.assertEqual(page["images"][0]["sha256"], hashlib.sha256(PNG_1X1).hexdigest())
            self.assertEqual(page["links"][0]["url"], f"{self.server.origin}/docs/workbuddy/Feature")

            capture.validate_snapshot(output)

    def test_rejects_urls_outside_the_desktop_docs_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "outside expected prefix"):
                capture.capture_source(
                    sitemap_url=f"{self.server.origin}/sitemap.xml",
                    output=pathlib.Path(temporary) / "snapshot",
                    expected_prefix=f"{self.server.origin}/docs/workbuddy/Quickstart",
                    captured_at="2026-08-31T00:00:00+00:00",
                )

    def test_refuses_to_overwrite_an_immutable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / "snapshot"
            output.mkdir()
            with self.assertRaises(FileExistsError):
                capture.capture_source(
                    sitemap_url=f"{self.server.origin}/sitemap.xml",
                    output=output,
                    expected_prefix=f"{self.server.origin}/docs/workbuddy/",
                    captured_at="2026-08-31T00:00:00+00:00",
                )

    def test_reads_webp_vp8x_canvas_dimensions_even_when_the_url_ends_in_png(self) -> None:
        body = b"RIFF" + (22).to_bytes(4, "little") + b"WEBPVP8X" + (10).to_bytes(4, "little")
        body += b"\x00\x00\x00\x00" + (1745).to_bytes(3, "little") + (495).to_bytes(3, "little")
        self.assertEqual(capture.image_dimensions(body, "image/png"), (1746, 496))


if __name__ == "__main__":
    unittest.main()
