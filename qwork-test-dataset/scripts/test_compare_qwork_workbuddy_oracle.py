#!/usr/bin/env python3

from __future__ import annotations

import unittest

from PIL import Image

from compare_qwork_workbuddy_oracle import pixel_diff_stats


class PixelDiffStatsTest(unittest.TestCase):
    def test_ignores_subthreshold_antialiasing_but_retains_exact_ratio(self) -> None:
        reference = Image.new("RGBA", (2, 1), (240, 240, 240, 255))
        candidate = Image.new("RGBA", (2, 1), (240, 240, 240, 255))
        candidate.putpixel((0, 0), (247, 240, 240, 255))

        stats = pixel_diff_stats(candidate, reference, channel_threshold=8)

        self.assertEqual(stats["exact_diff_ratio"], 0.5)
        self.assertEqual(stats["significant_diff_ratio"], 0.0)

    def test_counts_a_pixel_when_any_channel_exceeds_the_threshold(self) -> None:
        reference = Image.new("RGBA", (2, 1), (240, 240, 240, 255))
        candidate = Image.new("RGBA", (2, 1), (240, 240, 240, 255))
        candidate.putpixel((1, 0), (249, 240, 240, 255))

        stats = pixel_diff_stats(candidate, reference, channel_threshold=8)

        self.assertEqual(stats["exact_diff_ratio"], 0.5)
        self.assertEqual(stats["significant_diff_ratio"], 0.5)


if __name__ == "__main__":
    unittest.main()
