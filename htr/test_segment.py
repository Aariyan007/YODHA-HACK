"""Run: cd htr && ./venv/bin/python test_segment.py   (no model needed)"""
import unittest

import numpy as np

from app import segment


class Segment(unittest.TestCase):
    def page(self, bands, h=400, w=600):
        a = np.full((h, w), 235.0, dtype=np.float32)
        for y0, y1 in bands:
            a[y0:y1, 40:560:3] = 20.0  # dashed "ink" so rows have many dark pixels
        return a

    def test_finds_each_line(self):
        self.assertEqual(segment(self.page([(40, 70), (120, 150), (220, 250)])), [(40, 70), (120, 150), (220, 250)])

    def test_blank_page_has_no_lines(self):
        self.assertEqual(segment(self.page([])), [])

    def test_specks_are_not_lines(self):
        self.assertEqual(segment(self.page([(50, 54)])), [])


if __name__ == "__main__":
    unittest.main()
