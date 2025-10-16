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

from litex.gen import run_simulation
from migen import *

from litepcie.dll.pipe import PIPETXPacketizer


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
            tx_data = yield dut.pipe_tx_data
            tx_datak = yield dut.pipe_tx_datak
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
            tx_data = yield dut.pipe_tx_data
            tx_datak = yield dut.pipe_tx_datak
            self.assertEqual(tx_data, 0x5C, "Should send SDP (0x5C)")
            self.assertEqual(tx_datak, 1, "SDP should be K-character")

        dut = PIPETXPacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_tx_sdp.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


class TestPIPETXPacketizerData(unittest.TestCase):
    """Test DATA transmission."""

    def test_tx_transmits_data_bytes(self):
        """
        TX should transmit 8 data bytes after START symbol.

        Data transmission:
        - Converts 64-bit word to 8 sequential bytes
        - Byte order: LSB-first (little-endian)
        - Data bytes have datak=0 (not K-characters)

        Timing:
        - Cycle 0: IDLE detects packet start (valid & first)
        - Cycle 1: START symbol appears, transition to DATA
        - Cycles 2-9: 8 data bytes appear (byte 0-7)
        - Cycle 10: Return to IDLE

        Reference: PCIe Spec 4.0, Section 4.2.2: Symbol Encoding
        """

        def testbench(dut):
            # Send 64-bit data packet
            # Data: 0x0123456789ABCDEF
            # Expected bytes (LSB-first): 0xEF, 0xCD, 0xAB, 0x89, 0x67, 0x45, 0x23, 0x01
            tlp_data = 0x0123456789ABCDEF
            yield dut.sink.valid.eq(1)
            yield dut.sink.first.eq(1)
            yield dut.sink.last.eq(0)
            yield dut.sink.dat.eq(tlp_data)
            yield

            # Clear first flag
            yield dut.sink.first.eq(0)

            # Cycle 1: START symbol (STP) appears
            yield
            tx_data = yield dut.pipe_tx_data
            tx_datak = yield dut.pipe_tx_datak
            self.assertEqual(tx_data, 0xFB, "Should send STP")
            self.assertEqual(tx_datak, 1, "STP should be K-character")

            # Cycles 2-9: Check 8 data bytes (LSB-first)
            expected_bytes = [0xEF, 0xCD, 0xAB, 0x89, 0x67, 0x45, 0x23, 0x01]
            for i, expected in enumerate(expected_bytes):
                yield
                tx_data = yield dut.pipe_tx_data
                tx_datak = yield dut.pipe_tx_datak
                self.assertEqual(tx_data, expected, f"Byte {i} should be 0x{expected:02X}")
                self.assertEqual(tx_datak, 0, f"Byte {i} should not be K-char")

        dut = PIPETXPacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_tx_data.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


class TestPIPETXPacketizerEnd(unittest.TestCase):
    """Test END symbol generation."""

    def test_tx_sends_end_after_data(self):
        """
        TX should send END (0xFD, K=1) after data transmission.

        Packet framing:
        - Cycle 0: IDLE detects packet (valid & first)
        - Cycle 1: Transition to DATA, START symbol scheduled
        - Cycle 2: START symbol (STP/SDP) appears
        - Cycles 3-10: 8 data bytes transmitted
        - Cycle 11: END symbol (0xFD, K=1) appears
        - Cycle 12: Return to IDLE

        Note: NextValue in FSM schedules outputs for next cycle,
        so outputs lag state transitions by one cycle.

        Reference: PCIe Spec 4.0, Section 4.2.2.2: END Framing
        """

        def testbench(dut):
            # Send 64-bit data packet with last=1
            tlp_data = 0x0123456789ABCDEF
            yield dut.sink.valid.eq(1)
            yield dut.sink.first.eq(1)
            yield dut.sink.last.eq(1)
            yield dut.sink.dat.eq(tlp_data)
            yield

            # Clear first flag
            yield dut.sink.first.eq(0)
            yield dut.sink.valid.eq(0)

            # Skip START symbol and 8 data bytes (10 cycles total)
            # Cycle 1: Processing input
            # Cycle 2: START symbol (STP)
            # Cycles 3-10: 8 data bytes
            for _ in range(10):
                yield

            # Cycle 11: Check END symbol
            tx_data = yield dut.pipe_tx_data
            tx_datak = yield dut.pipe_tx_datak
            self.assertEqual(tx_data, 0xFD, "Should send END (0xFD)")
            self.assertEqual(tx_datak, 1, "END should be K-character")

        dut = PIPETXPacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_tx_end.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
