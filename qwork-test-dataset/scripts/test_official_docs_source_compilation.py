#!/usr/bin/env python3

from __future__ import annotations

import pathlib
import unittest

import build_product_baseline as builder


class OfficialDocsSourceCompilationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill_root = pathlib.Path(__file__).resolve().parents[1]
        cls.snapshot = (
            cls.skill_root
            / "data/sources/workbuddy-official-docs/sitemap-20260831-sha256-2f505afc04288b1f"
        )

    def test_snapshot_compiles_every_article_and_disposes_the_root_shell(self) -> None:
        manifest, inventory = builder.load_official_docs_snapshot(self.snapshot)
        atoms, dispositions = builder.official_docs_atoms(
            "WORKBUDDY-OFFICIAL-DOCS-20260831",
            self.snapshot,
            inventory,
            runtime_version="5.3.14",
        )

        self.assertEqual(manifest["page_count"], 85)
        self.assertEqual(manifest["article_page_count"], 84)
        self.assertEqual(len(dispositions), 1)
        self.assertEqual(dispositions[0]["disposition"], "not_applicable-no-article")
        self.assertTrue(dispositions[0]["url"].endswith("/docs/workbuddy/"))
        self.assertGreater(len(atoms), manifest["article_page_count"])

        parallel = next(
            atom
            for atom in atoms
            if "多任务并行" in atom["label"]
            and "url:https://www.workbuddy.cn/docs/workbuddy/Quickstart" in atom["locator"]
        )
        self.assertEqual(parallel["runtime_applicability"]["documented_version"], "5.3.14")
        self.assertIn("url:https://www.workbuddy.cn/docs/workbuddy/Quickstart", parallel["locator"])
        self.assertIn("heading:2. 核心优势", parallel["locator"])

        positioning = next(atom for atom in atoms if "腾讯推出的全场景职场 AI" in atom["label"])
        self.assertIn("WorkBuddy", positioning["brand_tokens"])
        self.assertIn("腾讯", positioning["brand_tokens"])
        self.assertEqual(positioning["brand_substitution_policy"], "name-and-asset-differences-exempt-only")

        pricing_formulas = [
            atom for atom in atoms if atom.get("page_url", "").endswith("/Plan")
        ]
        self.assertTrue(any("140 X 2 = 280元" in atom["label"] for atom in pricing_formulas))
        self.assertTrue(all(atom["facet"] != "ui-geometry" for atom in pricing_formulas))

    def test_newer_documentation_is_context_only_for_the_approved_538_runtime(self) -> None:
        policy = builder.official_docs_source_policy(
            documented_version="5.3.14",
            approved_runtime_version="5.3.8",
        )

        self.assertEqual(policy["authority_kind"], "context-only")
        self.assertFalse(policy["version_match"])
        self.assertEqual(policy["requirement_status"], "not_applicable")
        self.assertIn("5.3.14", policy["status_reason"])
        self.assertIn("5.3.8", policy["status_reason"])

    def test_matching_documentation_can_be_normative_for_the_approved_runtime(self) -> None:
        policy = builder.official_docs_source_policy(
            documented_version="5.3.8",
            approved_runtime_version="5.3.8",
        )

        self.assertEqual(policy["authority_kind"], "normative")
        self.assertTrue(policy["version_match"])
        self.assertEqual(policy["requirement_status"], "covered")

    def test_document_images_are_hash_bound_but_not_promoted_to_pixel_or_geometry_pass(self) -> None:
        _manifest, inventory = builder.load_official_docs_snapshot(self.snapshot)
        atoms, _dispositions = builder.official_docs_atoms(
            "WORKBUDDY-OFFICIAL-DOCS-20260831",
            self.snapshot,
            inventory,
            runtime_version="5.3.14",
        )

        images = [atom for atom in atoms if atom.get("source_media")]
        self.assertEqual(len(images), 457)
        self.assertTrue(all(atom["facet"] == "ui-visual" for atom in images))
        self.assertTrue(all(atom["evidence_only"] is True for atom in images))
        self.assertTrue(all(atom["source_media"]["calibration_status"] == "missing" for atom in images))
        self.assertTrue(all(atom["source_media"]["width"] and atom["source_media"]["height"] for atom in images))


if __name__ == "__main__":
    unittest.main()
