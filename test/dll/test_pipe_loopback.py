# test/dll/test_pipe_loopback.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for PIPE loopback (TX → RX).

Verifies complete data path through PIPE interface.

Reference: PCIe Base Spec 4.0, Section 4.2
"""

import os
import tempfile
import unittest

from litex.gen import run_simulation
from migen import *

from litepcie.dll.pipe import PIPEInterface


class TestPIPELoopback(unittest.TestCase):
    """Test PIPE loopback functionality."""

    def test_loopback_single_word(self):
        """
        Single 64-bit word should loop back correctly.

        TX: DLL packet → PIPE symbols
        Loopback: Connect TX → RX
        RX: PIPE symbols → DLL packet

        Verify output matches input.
        """

        def testbench(dut):
            # Test data
            test_data = 0x0123456789ABCDEF

            # Send packet to TX
            yield dut.dll_tx_sink.valid.eq(1)
            yield dut.dll_tx_sink.first.eq(1)
            yield dut.dll_tx_sink.last.eq(1)
            yield dut.dll_tx_sink.dat.eq(test_data)
            yield

            # Clear TX input
            yield dut.dll_tx_sink.valid.eq(0)

            # Wait for TX processing
            # After clearing TX input, monitoring starts at cycle 0
            # Cycle 0: First yield after clear
            # Cycle 1: START symbol (STP) sent
            # Cycles 2-9: 8 data bytes sent
            # Cycle 10: END symbol sent, RX output valid
            # We need to wait 10 cycles to reach the END symbol
            for _ in range(10):  # Wait 10 cycles to reach cycle 10
                yield

            # Check RX output (should be valid when END symbol is received)
            rx_valid = yield dut.dll_rx_source.valid
            rx_data = yield dut.dll_rx_source.dat
            rx_first = yield dut.dll_rx_source.first
            rx_last = yield dut.dll_rx_source.last

            self.assertEqual(rx_valid, 1, "RX should have valid output")
            self.assertEqual(
                rx_data,
                test_data,
                f"RX data mismatch: expected 0x{test_data:016X}, got 0x{rx_data:016X}",
            )
            self.assertEqual(rx_first, 1, "RX should assert first")
            self.assertEqual(rx_last, 1, "RX should assert last")

        # Create PIPE interface with loopback
        dut = PIPEInterface(data_width=8, gen=1)

        # Loopback TX → RX
        dut.comb += [
            dut.pipe_rx_data.eq(dut.pipe_tx_data),
            dut.pipe_rx_datak.eq(dut.pipe_tx_datak),
        ]

        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_loopback_single.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
