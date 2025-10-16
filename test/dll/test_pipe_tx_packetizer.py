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


class TestPIPETXPacketizerStart(unittest.TestCase):
    """Test START symbol generation."""

    def test_tx_sends_stp_for_tlp(self):
        """
        TX should send STP (0xFB, K=1) at start of TLP.

        TLP identification: First byte is not DLLP type (0x00, 0x10, 0x20, 0x30)

        Reference: PCIe Spec 4.0, Section 4.2.2.1: START Framing
        """
        def testbench(dut):
            # Prepare TLP data (first byte = 0xEF in little-endian, indicating TLP)
            tlp_data = 0x0123456789ABCDEF  # 64-bit TLP data
            yield dut.sink.valid.eq(1)
            yield dut.sink.first.eq(1)
            yield dut.sink.last.eq(0)
            yield dut.sink.dat.eq(tlp_data)
            yield

            # FSM processes inputs and schedules transition
            # Need one more cycle for START symbol to appear
            yield dut.sink.first.eq(0)
            yield

            # Check START symbol (STP)
            tx_data = (yield dut.pipe_tx_data)
            tx_datak = (yield dut.pipe_tx_datak)
            self.assertEqual(tx_data, 0xFB, "Should send STP (0xFB)")
            self.assertEqual(tx_datak, 1, "STP should be K-character")

        dut = PIPETXPacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_tx_stp.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)

    def test_tx_sends_sdp_for_dllp(self):
        """
        TX should send SDP (0x5C, K=1) at start of DLLP.

        DLLP identification: First byte is DLLP type (0x00=ACK, 0x10=NAK, etc.)

        Reference: PCIe Spec 4.0, Section 3.3.1: DLLP Format
        """
        def testbench(dut):
            # Prepare DLLP data (first byte = 0x34 in little-endian, type check uses bits [7:6])
            dllp_data = 0x00000000ABCD1234  # 64-bit DLLP data
            yield dut.sink.valid.eq(1)
            yield dut.sink.first.eq(1)
            yield dut.sink.last.eq(0)
            yield dut.sink.dat.eq(dllp_data)
            yield

            # FSM processes inputs and schedules transition
            # Need one more cycle for START symbol to appear
            yield dut.sink.first.eq(0)
            yield

            # Check START symbol (SDP)
            tx_data = (yield dut.pipe_tx_data)
            tx_datak = (yield dut.pipe_tx_datak)
            self.assertEqual(tx_data, 0x5C, "Should send SDP (0x5C)")
            self.assertEqual(tx_datak, 1, "SDP should be K-character")

        dut = PIPETXPacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_tx_sdp.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
