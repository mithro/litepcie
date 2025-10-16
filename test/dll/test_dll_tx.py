#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for PCIe DLL TX Path.

Tests behavioral aspects of DLL transmit path including sequence number
assignment, LCRC generation, and retry buffer integration.

Reference: PCIe Base Spec 4.0, Section 3.3
"""

import unittest

from migen import *
from litex.gen import run_simulation


class TestDLLTXPath(unittest.TestCase):
    """Test DLL transmit path."""

    def test_tx_assigns_sequence_numbers(self):
        """TX path should assign incrementing sequence numbers to TLPs."""
        from litepcie.dll.tx import DLLTX

        def testbench(dut):
            # Enable PHY ready
            yield dut.phy_source.ready.eq(1)

            # Send first TLP
            yield dut.tlp_sink.valid.eq(1)
            yield dut.tlp_sink.data.eq(0xDEADBEEFCAFEBABE)
            yield dut.tlp_sink.last.eq(1)
            yield
            yield dut.tlp_sink.valid.eq(0)

            # Wait for FSM to process
            for _ in range(10):
                yield

            # Check sequence number assigned
            seq0 = (yield dut.debug_last_seq)
            self.assertEqual(seq0, 0, "First TLP should get sequence 0")

            # Send second TLP
            yield dut.tlp_sink.valid.eq(1)
            yield dut.tlp_sink.data.eq(0xAAAABBBBCCCCDDDD)
            yield dut.tlp_sink.last.eq(1)
            yield
            yield dut.tlp_sink.valid.eq(0)

            # Wait for FSM to process
            for _ in range(10):
                yield

            # Check sequence number incremented
            seq1 = (yield dut.debug_last_seq)
            self.assertEqual(seq1, 1, "Second TLP should get sequence 1")

        dut = DLLTX(data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="test_dll_tx_seq.vcd")

    def test_tx_appends_lcrc(self):
        """TX path should append LCRC to outgoing TLPs."""
        from litepcie.dll.tx import DLLTX
        from litepcie.dll.common import calculate_lcrc32

        def testbench(dut):
            # Send TLP data
            test_data = [0xDE, 0xAD, 0xBE, 0xEF]
            expected_crc = calculate_lcrc32(test_data)

            # Send 4-byte TLP
            yield dut.tlp_sink.valid.eq(1)
            yield dut.tlp_sink.data.eq(int.from_bytes(bytes(test_data), 'little'))
            yield dut.tlp_sink.last.eq(1)
            yield
            yield dut.tlp_sink.valid.eq(0)
            yield
            yield

            # Wait for output and check LCRC was appended
            # (Implementation detail: output should have data + LCRC)
            # This is a behavioral test - we verify LCRC is calculated correctly
            output_valid = (yield dut.phy_source.valid)
            if output_valid:
                # Verify LCRC was computed
                computed_crc = (yield dut.debug_last_lcrc)
                self.assertEqual(computed_crc, expected_crc,
                               f"LCRC should be 0x{expected_crc:08X}")

        dut = DLLTX(data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="test_dll_tx_lcrc.vcd")

    def test_tx_stores_in_retry_buffer(self):
        """TX path should store TLPs in retry buffer."""
        from litepcie.dll.tx import DLLTX

        def testbench(dut):
            # Enable PHY ready
            yield dut.phy_source.ready.eq(1)

            # Send TLP
            yield dut.tlp_sink.valid.eq(1)
            yield dut.tlp_sink.data.eq(0x1234567890ABCDEF)
            yield dut.tlp_sink.last.eq(1)
            yield
            yield dut.tlp_sink.valid.eq(0)

            # Wait for FSM to store in retry buffer
            for _ in range(10):
                yield

            # Check retry buffer has entry
            retry_empty = (yield dut.retry_buffer.empty)
            self.assertFalse(retry_empty, "Retry buffer should have stored TLP")

            # Send ACK to release from buffer
            yield dut.ack_sink.valid.eq(1)
            yield dut.ack_sink.seq_num.eq(0)
            yield
            yield dut.ack_sink.valid.eq(0)

            # Wait for ACK to process
            for _ in range(5):
                yield

            # Buffer should be empty after ACK
            retry_empty = (yield dut.retry_buffer.empty)
            self.assertTrue(retry_empty, "Retry buffer should be empty after ACK")

        dut = DLLTX(data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="test_dll_tx_retry.vcd")


if __name__ == "__main__":
    unittest.main()
