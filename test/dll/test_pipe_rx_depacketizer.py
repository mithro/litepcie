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


class TestPIPERXDepacketizerData(unittest.TestCase):
    """Test PIPE RX depacketizer data accumulation."""

    def test_rx_accumulates_data_bytes(self):
        """
        RX should accumulate 8 data bytes into 64-bit word.

        Data accumulation:
        - Receives 8 sequential bytes after START symbol
        - Byte order: LSB-first (little-endian)
        - Byte 0 → bits [7:0], Byte 7 → bits [63:56]
        - Only accumulates data bytes (datak=0), not K-characters

        Note: This test verifies accumulation via debug signal.
        Task 4.8 will verify full packet output with END detection.

        Reference: PCIe Spec 4.0, Section 4.2.2: Symbol Encoding
        """

        def testbench(dut):
            # Send START symbol (STP for TLP)
            yield dut.pipe_rx_data.eq(0xFB)
            yield dut.pipe_rx_datak.eq(1)
            yield

            # Send 8 data bytes (LSB-first)
            # Expected buffer: 0x0123456789ABCDEF
            # Byte 0 (0xEF) → bits [7:0]
            # Byte 1 (0xCD) → bits [15:8]
            # ...
            # Byte 7 (0x01) → bits [63:56]
            data_bytes = [0xEF, 0xCD, 0xAB, 0x89, 0x67, 0x45, 0x23, 0x01]
            for byte_val in data_bytes:
                yield dut.pipe_rx_data.eq(byte_val)
                yield dut.pipe_rx_datak.eq(0)
                yield

            # Need one more cycle for the last byte to be written
            # NextValue schedules updates for next cycle
            yield

            # After 8 bytes, check accumulated data via debug signal
            buffer_value = yield dut.debug_data_buffer
            expected = 0x0123456789ABCDEF
            self.assertEqual(
                buffer_value,
                expected,
                f"Data buffer should be 0x{expected:016X}, got 0x{buffer_value:016X}",
            )

        # Enable debug mode for testing
        dut = PIPERXDepacketizer(debug=True)
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_rx_data.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


class TestPIPERXDepacketizerEnd(unittest.TestCase):
    """Test PIPE RX depacketizer END detection and packet output."""

    def test_rx_outputs_packet_on_end(self):
        """
        RX should output complete packet when END symbol is detected.

        Protocol flow:
        - Send START symbol (STP or SDP)
        - Send 8 data bytes
        - Send END symbol (0xFD, K=1)
        - Verify packet output on source endpoint
        - Check source.valid, source.first, source.last, source.dat

        Reference: PCIe Spec 4.0, Section 4.2.2.3: END Framing
        """

        def testbench(dut):
            # Send START symbol (STP for TLP)
            yield dut.pipe_rx_data.eq(0xFB)
            yield dut.pipe_rx_datak.eq(1)
            yield

            # Send 8 data bytes (LSB-first)
            # Expected buffer: 0x0123456789ABCDEF
            data_bytes = [0xEF, 0xCD, 0xAB, 0x89, 0x67, 0x45, 0x23, 0x01]
            for byte_val in data_bytes:
                yield dut.pipe_rx_data.eq(byte_val)
                yield dut.pipe_rx_datak.eq(0)
                yield

            # Send END symbol (0xFD, K=1)
            yield dut.pipe_rx_data.eq(0xFD)
            yield dut.pipe_rx_datak.eq(1)
            yield

            # Check packet output on source endpoint
            source_valid = yield dut.source.valid
            source_first = yield dut.source.first
            source_last = yield dut.source.last
            source_dat = yield dut.source.dat

            self.assertEqual(source_valid, 1, "source.valid should be set")
            self.assertEqual(source_first, 1, "source.first should be set")
            self.assertEqual(source_last, 1, "source.last should be set")
            self.assertEqual(
                source_dat, 0x0123456789ABCDEF, "source.dat should contain accumulated data"
            )

        dut = PIPERXDepacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_rx_end.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
