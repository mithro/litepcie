#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for PIPE interface abstraction.

Tests behavioral aspects of PIPE signal generation and processing.

Reference: Intel PIPE 3.0 Specification
"""

import os
import tempfile
import unittest

from litex.gen import run_simulation
from migen import *

from litepcie.dll.pipe import PIPEInterface


class TestPIPEInterfaceStructure(unittest.TestCase):
    """Test PIPE interface module structure."""

    def test_pipe_interface_has_required_signals(self):
        """PIPE interface should expose all required PIPE signals."""
        dut = PIPEInterface(data_width=8, gen=1)

        # TX PIPE signals (MAC → PHY)
        self.assertTrue(hasattr(dut, "pipe_tx_data"))
        self.assertTrue(hasattr(dut, "pipe_tx_datak"))
        self.assertTrue(hasattr(dut, "pipe_tx_elecidle"))

        # RX PIPE signals (PHY → MAC)
        self.assertTrue(hasattr(dut, "pipe_rx_data"))
        self.assertTrue(hasattr(dut, "pipe_rx_datak"))
        self.assertTrue(hasattr(dut, "pipe_rx_valid"))
        self.assertTrue(hasattr(dut, "pipe_rx_status"))
        self.assertTrue(hasattr(dut, "pipe_rx_elecidle"))

        # Control signals
        self.assertTrue(hasattr(dut, "pipe_powerdown"))
        self.assertTrue(hasattr(dut, "pipe_rate"))
        self.assertTrue(hasattr(dut, "pipe_rx_polarity"))

    def test_pipe_interface_has_dll_endpoints(self):
        """PIPE interface should have DLL-facing stream endpoints."""
        dut = PIPEInterface(data_width=8, gen=1)

        # DLL endpoints (packet-based)
        self.assertTrue(hasattr(dut, "dll_tx_sink"))
        self.assertTrue(hasattr(dut, "dll_rx_source"))


class TestPIPETXBehavior(unittest.TestCase):
    """Test PIPE TX behavior."""

    def test_pipe_tx_sends_idle_when_no_data(self):
        """
        PIPE TX should send electrical idle when no DLL data present.

        Reference: PCIe Spec 4.0, Section 4.2.6.2.4: Electrical Idle
        """

        def testbench(dut):
            # No DLL data provided
            yield dut.dll_tx_sink.valid.eq(0)
            yield

            # PIPE should request electrical idle
            elecidle = yield dut.pipe_tx_elecidle
            self.assertEqual(elecidle, 1, "Should request electrical idle when no data")

            # Wait a few cycles
            for _ in range(5):
                yield
                elecidle = yield dut.pipe_tx_elecidle
                self.assertEqual(elecidle, 1, "Should maintain electrical idle")

        dut = PIPEInterface(data_width=8, gen=1)
        # Use temporary directory in project for VCD files to ensure cleanup
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_pipe_tx_idle.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


class TestPIPEInterfaceTXRX(unittest.TestCase):
    """Test TX/RX integration."""

    def test_pipe_interface_has_tx_rx(self):
        """PIPE interface should have TX and RX components."""
        dut = PIPEInterface(data_width=8, gen=1)

        # Should have TX packetizer
        self.assertTrue(hasattr(dut, "tx_packetizer"))

        # Should have RX depacketizer
        self.assertTrue(hasattr(dut, "rx_depacketizer"))


if __name__ == "__main__":
    unittest.main()
