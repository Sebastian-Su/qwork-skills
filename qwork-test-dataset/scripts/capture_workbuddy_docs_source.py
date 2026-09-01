#!/usr/bin/env python3
"""Freeze the public WorkBuddy desktop documentation as a versioned text source.

The snapshot intentionally stores normalized article text and image metadata rather
than copying site chrome or image bytes into Git. Every fetched byte stream is
hashed so later runs can detect source drift.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html.parser
import json
import os
import pathlib
import re
import shutil
import struct
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any


USER_AGENT = "QWork-Test-Dataset/1.0 (+official-docs-read-only-capture)"
MAX_RESPONSE_BYTES = 64 * 1024 * 1024


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


@dataclass(frozen=True)
class Fetched:
    requested_url: str
    effective_url: str
    content_type: str
    body: bytes


def fetch(url: str) -> Fetched:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=30) as response:
        declared_length = response.headers.get("Content-Length")
        if declared_length and int(declared_length) > MAX_RESPONSE_BYTES:
            raise ValueError(f"response exceeds {MAX_RESPONSE_BYTES} bytes: {url}")
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError(f"response exceeds {MAX_RESPONSE_BYTES} bytes: {url}")
        return Fetched(
            requested_url=url,
            effective_url=response.geturl(),
            content_type=response.headers.get_content_type(),
            body=body,
        )


class ArticleParser(html.parser.HTMLParser):
    BLOCK_TAGS = {"p", "div", "section", "article", "aside", "blockquote", "pre", "tr"}
    SKIP_TAGS = {"script", "style", "svg", "noscript", "template"}

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.article_depth = 0
        self.skip_depth = 0
        self.title_depth = 0
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.headings: list[dict[str, Any]] = []
        self.heading_level: int | None = None
        self.heading_parts: list[str] = []
        self.links: list[dict[str, str]] = []
        self.link_stack: list[dict[str, Any]] = []
        self.images: list[dict[str, str]] = []
        self.table_cell_index = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}
        if tag == "title":
            self.title_depth += 1
        classes = set(attributes.get("class", "").split())
        if self.article_depth == 0 and "vp-doc" in classes:
            self.article_depth = 1
        elif self.article_depth:
            self.article_depth += 1
        if not self.article_depth:
            return
        if self.skip_depth or tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if re.fullmatch(r"h[1-6]", tag):
            self._newline()
            self.heading_level = int(tag[1])
            self.heading_parts = []
        elif tag == "li":
            self._newline()
            self.text_parts.append("- ")
        elif tag == "br":
            self._newline()
        elif tag == "tr":
            self._newline()
            self.table_cell_index = 0
        elif tag in {"th", "td"}:
            if self.table_cell_index:
                self.text_parts.append(" | ")
            self.table_cell_index += 1
        elif tag in self.BLOCK_TAGS:
            self._newline()
        if tag == "a" and attributes.get("href"):
            self.link_stack.append({"url": normalize_url(self.base_url, attributes["href"]), "parts": []})
        if tag == "img" and attributes.get("src"):
            self.images.append(
                {
                    "url": normalize_url(self.base_url, attributes["src"]),
                    "alt": normalize_text(attributes.get("alt", "")),
                    "title": normalize_text(attributes.get("title", "")),
                }
            )

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self.title_depth:
            self.title_depth -= 1
        if not self.article_depth:
            return
        if self.skip_depth:
            self.skip_depth -= 1
        else:
            if re.fullmatch(r"h[1-6]", tag) and self.heading_level is not None:
                text = normalize_text("".join(self.heading_parts).replace("​", ""))
                if text:
                    self.headings.append({"level": self.heading_level, "text": text})
                self.heading_level = None
                self.heading_parts = []
                self._newline()
            elif tag == "a" and self.link_stack:
                link = self.link_stack.pop()
                self.links.append({"url": link["url"], "text": normalize_text("".join(link["parts"]))})
            elif tag in self.BLOCK_TAGS or tag in {"li", "tr"}:
                self._newline()
        self.article_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.title_depth:
            self.title_parts.append(data)
        if not self.article_depth or self.skip_depth:
            return
        text = normalize_text(data.replace("​", ""))
        if not text:
            return
        if self.text_parts and not self.text_parts[-1].endswith(("\n", " ", "- ", " | ")):
            self.text_parts.append(" ")
        self.text_parts.append(text)
        if self.heading_level is not None:
            self.heading_parts.append(text)
        for link in self.link_stack:
            link["parts"].append(text)

    def _newline(self) -> None:
        if self.text_parts and not self.text_parts[-1].endswith("\n"):
            self.text_parts.append("\n")

    def result(self) -> dict[str, Any]:
        if not self.headings:
            raise ValueError(f"article .vp-doc was not found or contained no headings: {self.base_url}")
        text = "".join(self.text_parts)
        text = re.sub(r"[ \t]+([.,;:!?，。；：！？])", r"\1", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return {
            "title": normalize_text("".join(self.title_parts).replace("​", "")),
            "headings": self.headings,
            "text": text,
            "links": unique_dicts(self.links, ("url", "text")),
            "images": unique_dicts(self.images, ("url", "alt", "title")),
        }


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_url(base_url: str, value: str) -> str:
    absolute = urllib.parse.urljoin(base_url, value)
    parsed = urllib.parse.urlsplit(absolute)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def unique_dicts(values: list[dict[str, str]], keys: tuple[str, ...]) -> list[dict[str, str]]:
    seen: set[tuple[str, ...]] = set()
    result: list[dict[str, str]] = []
    for value in values:
        identity = tuple(value[key] for key in keys)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(value)
    return result


def parse_sitemap(body: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(body)
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    pages = []
    for url in root.findall("sm:url", namespace):
        locator = normalize_text(url.findtext("sm:loc", default="", namespaces=namespace))
        lastmod = normalize_text(url.findtext("sm:lastmod", default="", namespaces=namespace))
        if locator:
            pages.append({"url": locator, "lastmod": lastmod})
    if not pages:
        raise ValueError("sitemap contains no URL entries")
    return pages


def image_dimensions(body: bytes, content_type: str) -> tuple[int | None, int | None]:
    if body.startswith(b"\x89PNG\r\n\x1a\n") and len(body) >= 24:
        return struct.unpack(">II", body[16:24])
    if body.startswith((b"GIF87a", b"GIF89a")) and len(body) >= 10:
        return struct.unpack("<HH", body[6:10])
    if body.startswith(b"RIFF") and body[8:16] == b"WEBPVP8X" and len(body) >= 30:
        width = int.from_bytes(body[24:27], "little") + 1
        height = int.from_bytes(body[27:30], "little") + 1
        return width, height
    if body.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(body):
            if body[index] != 0xFF:
                index += 1
                continue
            marker = body[index + 1]
            index += 2
            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > len(body):
                break
            length = int.from_bytes(body[index:index + 2], "big")
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF} and index + 7 < len(body):
                return int.from_bytes(body[index + 5:index + 7], "big"), int.from_bytes(body[index + 3:index + 5], "big")
            index += max(length, 2)
    if content_type == "image/svg+xml":
        text = body.decode("utf-8", errors="replace")[:4096]
        width = re.search(r"\bwidth=['\"]([0-9.]+)", text)
        height = re.search(r"\bheight=['\"]([0-9.]+)", text)
        return (int(float(width.group(1))) if width else None, int(float(height.group(1))) if height else None)
    return None, None


def capture_source(
    *,
    sitemap_url: str,
    output: pathlib.Path,
    expected_prefix: str,
    captured_at: str | None = None,
) -> dict[str, Any]:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite immutable snapshot: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = pathlib.Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        sitemap = fetch(sitemap_url)
        sitemap_entries = parse_sitemap(sitemap.body)
        for entry in sitemap_entries:
            if not entry["url"].startswith(expected_prefix):
                raise ValueError(f"sitemap URL is outside expected prefix {expected_prefix}: {entry['url']}")

        pages_root = temporary / "pages"
        pages_root.mkdir()
        image_cache: dict[str, dict[str, Any]] = {}
        page_inventory: list[dict[str, Any]] = []
        for entry in sitemap_entries:
            fetched = fetch(entry["url"])
            parser = ArticleParser(entry["url"])
            parser.feed(fetched.body.decode("utf-8", errors="replace"))
            try:
                article = parser.result()
                article_status = "present"
            except ValueError:
                article = {
                    "title": normalize_text("".join(parser.title_parts).replace("​", "")),
                    "headings": [],
                    "text": "",
                    "links": [],
                    "images": [],
                }
                article_status = "not-present"
            for image in article["images"]:
                url = image["url"]
                if url.startswith("data:"):
                    metadata = {"url": url, "fetch_status": "embedded-data-url"}
                elif url not in image_cache:
                    image_response = fetch(url)
                    width, height = image_dimensions(image_response.body, image_response.content_type)
                    metadata = {
                        "url": url,
                        "effective_url": image_response.effective_url,
                        "content_type": image_response.content_type,
                        "bytes": len(image_response.body),
                        "sha256": sha256_bytes(image_response.body),
                        "width": width,
                        "height": height,
                        "fetch_status": "captured-hash-only",
                    }
                    image_cache[url] = metadata
                else:
                    metadata = image_cache[url]
                image.update(metadata)

            page = {
                "schema_version": 1,
                "source_kind": "official-web-documentation-page",
                "authority_kind": "normative",
                "url": entry["url"],
                "effective_url": fetched.effective_url,
                "lastmod": entry["lastmod"],
                "captured_at": captured_at or dt.datetime.now(dt.timezone.utc).isoformat(),
                "raw_html_sha256": sha256_bytes(fetched.body),
                "content_type": fetched.content_type,
                "article_status": article_status,
                **article,
            }
            page["text_sha256"] = sha256_bytes(page["text"].encode("utf-8"))
            page_bytes = canonical_json(page)
            relative_file = f"pages/{sha256_bytes(entry['url'].encode('utf-8'))[:16]}.json"
            (temporary / relative_file).write_bytes(page_bytes)
            page_inventory.append(
                {
                    "url": entry["url"],
                    "lastmod": entry["lastmod"],
                    "file": relative_file,
                    "sha256": sha256_bytes(page_bytes),
                    "raw_html_sha256": page["raw_html_sha256"],
                    "text_sha256": page["text_sha256"],
                    "article_status": article_status,
                    "heading_count": len(page["headings"]),
                    "image_count": len(page["images"]),
                }
            )

        inventory = {
            "schema_version": 1,
            "source_kind": "official-web-documentation-inventory",
            "pages": page_inventory,
            "images": sorted(image_cache.values(), key=lambda value: value["url"]),
        }
        inventory_bytes = canonical_json(inventory)
        (temporary / "inventory.json").write_bytes(inventory_bytes)
        lastmods = [entry["lastmod"] for entry in sitemap_entries if entry["lastmod"]]
        article_page_count = sum(page["article_status"] == "present" for page in page_inventory)
        timestamp = captured_at or dt.datetime.now(dt.timezone.utc).isoformat()
        manifest = {
            "schema_version": 1,
            "source_kind": "official-web-documentation",
            "authority_kind": "normative",
            "authority_domains": ["product", "behavior", "interaction", "ui", "support"],
            "product": "WorkBuddy",
            "scope": "desktop-documentation",
            "sitemap_url": sitemap_url,
            "sitemap_effective_url": sitemap.effective_url,
            "sitemap_sha256": sha256_bytes(sitemap.body),
            "sitemap_lastmod_max": max(lastmods) if lastmods else None,
            "captured_at": timestamp,
            "expected_url_prefix": expected_prefix,
            "page_count": len(page_inventory),
            "article_page_count": article_page_count,
            "non_article_page_count": len(page_inventory) - article_page_count,
            "image_count": len(image_cache),
            "inventory": "inventory.json",
            "inventory_sha256": sha256_bytes(inventory_bytes),
            "image_storage_policy": "hash-and-physical-metadata-only; image bytes are not copied into the snapshot",
            "version_policy": "page atoms require explicit runtime applicability before UI or behavior PASS",
            "brand_policy": "QWork approved brand names and assets are excluded from parity requirements",
        }
        (temporary / "manifest.json").write_bytes(canonical_json(manifest))
        validate_snapshot(temporary)
        os.replace(temporary, output)
        return {"status": "ok", "output": str(output), "page_count": len(page_inventory), "image_count": len(image_cache)}
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def validate_snapshot(root: pathlib.Path) -> None:
    root = root.resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    inventory_path = root / manifest["inventory"]
    inventory_bytes = inventory_path.read_bytes()
    if sha256_bytes(inventory_bytes) != manifest["inventory_sha256"]:
        raise ValueError("official docs inventory hash drifted")
    inventory = json.loads(inventory_bytes)
    navigation = manifest.get("browser_navigation_observation")
    if navigation:
        navigation_path = (root / navigation["file"]).resolve()
        if not navigation_path.is_relative_to(root) or sha256_bytes(navigation_path.read_bytes()) != navigation["sha256"]:
            raise ValueError("official docs browser navigation observation drifted")
    if manifest["page_count"] != len(inventory["pages"]):
        raise ValueError("official docs page count drifted")
    article_page_count = sum(page["article_status"] == "present" for page in inventory["pages"])
    if manifest["article_page_count"] != article_page_count or manifest["non_article_page_count"] != len(inventory["pages"]) - article_page_count:
        raise ValueError("official docs article disposition count drifted")
    if manifest["image_count"] != len(inventory["images"]):
        raise ValueError("official docs image count drifted")
    seen_urls: set[str] = set()
    for page_record in inventory["pages"]:
        if page_record["url"] in seen_urls:
            raise ValueError(f"duplicate official docs page: {page_record['url']}")
        seen_urls.add(page_record["url"])
        page_path = (root / page_record["file"]).resolve()
        if not page_path.is_relative_to(root):
            raise ValueError(f"official docs page escapes snapshot: {page_record['file']}")
        page_bytes = page_path.read_bytes()
        if sha256_bytes(page_bytes) != page_record["sha256"]:
            raise ValueError(f"official docs page hash drifted: {page_record['url']}")
        page = json.loads(page_bytes)
        if page["url"] != page_record["url"] or page["text_sha256"] != page_record["text_sha256"]:
            raise ValueError(f"official docs page identity drifted: {page_record['url']}")
        if sha256_bytes(page["text"].encode("utf-8")) != page["text_sha256"]:
            raise ValueError(f"official docs page text drifted: {page_record['url']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sitemap-url", required=True)
    parser.add_argument("--expected-prefix", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--captured-at")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        validate_snapshot(args.output)
        result = {"status": "ok", "output": str(args.output.resolve()), "validation": "passed"}
    else:
        result = capture_source(
            sitemap_url=args.sitemap_url,
            output=args.output,
            expected_prefix=args.expected_prefix,
            captured_at=args.captured_at,
        )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
