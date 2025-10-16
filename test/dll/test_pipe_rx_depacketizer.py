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


class TestPIPERXDepacketizerStart(unittest.TestCase):
    """Test PIPE RX depacketizer START detection."""

    def test_rx_detects_stp(self):
        """
        RX should detect STP (0xFB, K=1) and transition to DATA state.

        Reference: PCIe Spec 4.0, Section 4.2.2.1: START Framing
        """
        def testbench(dut):
            # Send STP symbol
            yield dut.pipe_rx_data.eq(0xFB)
            yield dut.pipe_rx_datak.eq(1)
            yield

            # Check FSM transitioned to DATA state
            # Since FSM state is internal, we can check behavior:
            # After STP, FSM should be in DATA state (not outputting yet)
            yield dut.pipe_rx_datak.eq(0)
            yield

            # FSM should be back in IDLE now (DATA state returns to IDLE)
            # This is a basic smoke test; full verification in Task 4.7

        dut = PIPERXDepacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_rx_stp.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)

    def test_rx_detects_sdp(self):
        """
        RX should detect SDP (0x5C, K=1) for DLLP packets.

        Reference: PCIe Spec 4.0, Section 3.3.1: DLLP Format
        """
        def testbench(dut):
            # Send SDP symbol
            yield dut.pipe_rx_data.eq(0x5C)
            yield dut.pipe_rx_datak.eq(1)
            yield

            # Basic smoke test
            yield dut.pipe_rx_datak.eq(0)
            yield

        dut = PIPERXDepacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_rx_sdp.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
