#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for PIPE RX depacketizer.

Tests behavioral aspects of PIPE symbol reception and packet reconstruction.

Reference: Intel PIPE 3.0 Specification
"""

import os
import tempfile
import unittest

from litex.gen import run_simulation
from migen import *

from litepcie.dll.pipe import PIPERXDepacketizer
from litepcie.common import phy_layout


class TestPIPERXDepacketizerStructure(unittest.TestCase):
    """Test PIPE RX depacketizer structure."""

    def test_rx_depacketizer_has_required_interfaces(self):
        """RX depacketizer should have PIPE input and DLL output."""
        dut = PIPERXDepacketizer()

        # PIPE input (8-bit symbols from PHY)
        self.assertTrue(hasattr(dut, "pipe_rx_data"))
        self.assertEqual(len(dut.pipe_rx_data), 8)
        self.assertTrue(hasattr(dut, "pipe_rx_datak"))
        self.assertEqual(len(dut.pipe_rx_datak), 1)

        # DLL output (64-bit packets to DLL)
        self.assertTrue(hasattr(dut, "source"))
        self.assertEqual(len(dut.source.dat), 64)


if __name__ == "__main__":
    unittest.main()
