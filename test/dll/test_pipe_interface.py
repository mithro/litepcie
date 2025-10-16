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


class TestPIPEInterfaceParameterValidation(unittest.TestCase):
    """Test PIPE interface parameter validation."""

    def test_invalid_data_width_raises_error(self):
        """
        PIPE interface should reject invalid data widths.

        Only 8-bit mode is currently supported (PIPE 3.0 standard).
        Unsupported widths (16, 32, etc.) should raise ValueError.

        Reference: Intel PIPE 3.0 Specification, Section 2.1
        """
        # Test various invalid data widths
        invalid_widths = [16, 32, 64, 128, 4, 0, -8]

        for width in invalid_widths:
            with self.assertRaises(ValueError) as context:
                PIPEInterface(data_width=width, gen=1)

            self.assertIn("8-bit", str(context.exception))

    def test_invalid_gen_raises_error(self):
        """
        PIPE interface should reject invalid PCIe generations.

        Only Gen1 (2.5 GT/s) and Gen2 (5.0 GT/s) are currently supported.
        Gen3/Gen4/Gen5 require different PIPE modes not yet implemented.

        Reference: PCIe Base Spec 4.0, Section 8.0: Physical Layer
        """
        # Test various invalid generations
        invalid_gens = [0, 3, 4, 5, -1, 10]

        for gen in invalid_gens:
            with self.assertRaises(ValueError) as context:
                PIPEInterface(data_width=8, gen=gen)

            self.assertIn("Gen1/Gen2", str(context.exception))

    def test_valid_parameters_accepted(self):
        """Valid parameter combinations should work."""
        # Gen1 with 8-bit - should create successfully
        dut1 = PIPEInterface(data_width=8, gen=1)
        self.assertTrue(hasattr(dut1, "pipe_rate"))
        self.assertTrue(hasattr(dut1, "pipe_tx_data"))

        # Gen2 with 8-bit - should create successfully
        dut2 = PIPEInterface(data_width=8, gen=2)
        self.assertTrue(hasattr(dut2, "pipe_rate"))
        self.assertTrue(hasattr(dut2, "pipe_tx_data"))


if __name__ == "__main__":
    unittest.main()
