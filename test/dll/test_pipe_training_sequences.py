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

import os
import tempfile
import unittest

from litex.gen import run_simulation
from migen import *

from litepcie.dll.pipe import (
    TS1OrderedSet,
    TS2OrderedSet,
    PIPE_K28_5_COM,
    PIPETXPacketizer,
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


class TestTS1Generation(unittest.TestCase):
    """Test TS1 generation in TX path."""

    def test_tx_can_generate_ts1(self):
        """
        TX should be able to generate TS1 ordered set on command.

        TS1 is 16 symbols starting with COM.
        """
        def testbench(dut):
            # Trigger TS1 generation
            yield dut.send_ts1.eq(1)
            yield
            yield dut.send_ts1.eq(0)
            yield  # Extra cycle for FSM transition

            # Check for COM symbol (TS1 start)
            yield
            tx_data = yield dut.pipe_tx_data
            tx_datak = yield dut.pipe_tx_datak
            self.assertEqual(tx_data, 0xBC, "Symbol 0 should be COM")
            self.assertEqual(tx_datak, 1, "Symbol 0 should be K-character")

            # Check next 15 symbols (don't validate specific values yet)
            for i in range(15):
                yield
                tx_datak = yield dut.pipe_tx_datak
                self.assertEqual(tx_datak, 0, f"Symbol {i+1} should be data (K=0)")

        dut = PIPETXPacketizer(enable_training_sequences=True)
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_ts1_gen.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
