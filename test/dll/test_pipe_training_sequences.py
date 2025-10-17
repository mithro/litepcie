# test/dll/test_pipe_training_sequences.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for PIPE Training Sequence (TS1/TS2) ordered sets.

Training Sequences are used during link training for speed negotiation,
lane configuration, and link equalization.

Reference: PCIe Base Spec 4.0, Section 4.2.6: Ordered Sets
"""

import unittest

from litepcie.dll.pipe import (
    TS1OrderedSet,
    TS2OrderedSet,
    PIPE_K28_5_COM,
)


class TestTS1OrderedSet(unittest.TestCase):
    """Test TS1 ordered set structure."""

    def test_ts1_has_correct_structure(self):
        """
        TS1 ordered set has 16 symbols (Gen1/Gen2).

        Symbol 0: COM (K28.5)
        Symbols 1-15: Configuration data (link/lane numbers, etc.)

        Reference: PCIe Spec 4.0, Section 4.2.6.2
        """
        ts1 = TS1OrderedSet(
            link_number=0,
            lane_number=0,
            n_fts=128,  # Fast Training Sequence count
            rate_id=1,  # Gen1
        )

        self.assertEqual(len(ts1.symbols), 16, "TS1 should have 16 symbols")
        self.assertEqual(ts1.symbols[0], PIPE_K28_5_COM, "Symbol 0 should be COM")


class TestTS2OrderedSet(unittest.TestCase):
    """Test TS2 ordered set structure."""

    def test_ts2_has_correct_structure(self):
        """
        TS2 ordered set has 16 symbols (Gen1/Gen2).

        Same structure as TS1, but signifies later training stage.

        Reference: PCIe Spec 4.0, Section 4.2.6.3
        """
        ts2 = TS2OrderedSet(
            link_number=0,
            lane_number=0,
            n_fts=128,
            rate_id=1,
        )

        self.assertEqual(len(ts2.symbols), 16, "TS2 should have 16 symbols")
        self.assertEqual(ts2.symbols[0], PIPE_K28_5_COM, "Symbol 0 should be COM")


if __name__ == "__main__":
    unittest.main()
