# test/dll/test_pipe_tx_packetizer.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for PIPE TX packetizer.

Tests conversion of DLL packets (64-bit) to PIPE symbols (8-bit) with K-character framing.

Reference: PCIe Base Spec 4.0, Section 4.2.2: Symbol Encoding
"""

import os
import tempfile
import unittest

from migen import *
from litex.gen import run_simulation

from litepcie.dll.pipe import PIPETXPacketizer
from litepcie.common import phy_layout


class TestPIPETXPacketizerStructure(unittest.TestCase):
    """Test TX packetizer structure."""

    def test_tx_packetizer_has_required_interfaces(self):
        """TX packetizer should have DLL input and PIPE output."""
        dut = PIPETXPacketizer()

        # DLL-facing input (64-bit)
        self.assertTrue(hasattr(dut, "sink"))
        self.assertEqual(len(dut.sink.dat), 64)

        # PIPE-facing output (8-bit symbols)
        self.assertTrue(hasattr(dut, "pipe_tx_data"))
        self.assertTrue(hasattr(dut, "pipe_tx_datak"))
        self.assertEqual(len(dut.pipe_tx_data), 8)
        self.assertEqual(len(dut.pipe_tx_datak), 1)


if __name__ == "__main__":
    unittest.main()
