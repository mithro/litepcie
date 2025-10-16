#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for sequence number management.

Tests behavioral aspects of sequence number allocation and tracking,
following TDD principles.

Reference: PCIe Base Spec 4.0, Section 3.3.5
"""

import unittest

from migen import *
from litex.gen import run_simulation

from litepcie.dll.common import DLL_SEQUENCE_NUM_MAX


class TestSequenceNumberManager(unittest.TestCase):
    """Test sequence number allocation and tracking."""

    def test_tx_sequence_starts_at_zero(self):
        """TX sequence should start at 0 on reset."""
        from litepcie.dll.sequence import SequenceNumberManager

        def testbench(dut):
            # After reset, first allocated sequence should be 0
            yield dut.tx_alloc.eq(1)
            yield
            seq = (yield dut.tx_seq_num)
            self.assertEqual(seq, 0, "First TX sequence should be 0")

        dut = SequenceNumberManager()
        run_simulation(dut, testbench(dut), vcd_name="test_seq_start_zero.vcd")

    def test_tx_sequence_increments(self):
        """TX sequence should increment on each allocation."""
        from litepcie.dll.sequence import SequenceNumberManager

        def testbench(dut):
            # Allocate first sequence (should be 0)
            yield dut.tx_alloc.eq(1)
            yield
            seq0 = (yield dut.tx_seq_num)

            # Allocate second sequence (should be 1)
            yield
            seq1 = (yield dut.tx_seq_num)

            # Allocate third sequence (should be 2)
            yield
            seq2 = (yield dut.tx_seq_num)

            yield dut.tx_alloc.eq(0)
            yield

            self.assertEqual(seq0, 0)
            self.assertEqual(seq1, 1)
            self.assertEqual(seq2, 2)

        dut = SequenceNumberManager()
        run_simulation(dut, testbench(dut), vcd_name="test_seq_increment.vcd")

    def test_tx_sequence_wraps_at_4096(self):
        """TX sequence should wrap from 4095 back to 0."""
        from litepcie.dll.sequence import SequenceNumberManager

        def testbench(dut):
            # Fast-forward: allocate all 4096 sequences (0-4095)
            # Counter starts at 0, after 4096 allocations reaches 4095, then wraps
            yield dut.tx_alloc.eq(1)

            # Allocate sequences: start at 0, allocate 4096 times
            for _ in range(4096):
                yield

            # Counter should now be at 4095
            seq_max = (yield dut.tx_seq_num)
            self.assertEqual(seq_max, 4095, "Should reach maximum sequence 4095")

            # One more allocation wraps to 0
            yield
            seq_wrapped = (yield dut.tx_seq_num)
            self.assertEqual(seq_wrapped, 0, "Should wrap to 0 after 4095")

            # Next allocation is sequence 1
            yield
            seq_after_wrap = (yield dut.tx_seq_num)
            self.assertEqual(seq_after_wrap, 1, "After wrap, next should be 1")

            yield dut.tx_alloc.eq(0)
            yield

        dut = SequenceNumberManager()
        run_simulation(dut, testbench(dut), vcd_name="test_seq_wrap.vcd")

    def test_tx_only_allocates_when_enabled(self):
        """TX sequence should only increment when tx_alloc is asserted."""
        from litepcie.dll.sequence import SequenceNumberManager

        def testbench(dut):
            # Read initial sequence (should be 0)
            seq0 = (yield dut.tx_seq_num)
            self.assertEqual(seq0, 0)

            # Allocate sequence 0 (counter increments after this cycle)
            yield dut.tx_alloc.eq(1)
            yield
            # Now counter is at 1

            # Disable allocation for 3 cycles
            yield dut.tx_alloc.eq(0)
            yield
            yield
            yield
            seq_after_pause = (yield dut.tx_seq_num)

            # Sequence should still be 1 (didn't increment without tx_alloc)
            self.assertEqual(seq_after_pause, 1,
                           "Sequence should not increment when tx_alloc=0")

            # Enable allocation again - counter should be 1 now, increment to 2
            yield dut.tx_alloc.eq(1)
            yield
            yield  # Wait for increment
            seq_next = (yield dut.tx_seq_num)
            self.assertEqual(seq_next, 2, "Next allocation should be sequence 2")

        dut = SequenceNumberManager()
        run_simulation(dut, testbench(dut), vcd_name="test_seq_enable.vcd")

    def test_rx_sequence_tracks_received_packets(self):
        """RX should track the next expected sequence number."""
        from litepcie.dll.sequence import SequenceNumberManager

        def testbench(dut):
            # Initially expecting sequence 0
            expected = (yield dut.rx_expected_seq)
            self.assertEqual(expected, 0, "Initially expecting sequence 0")

            # Receive packet with sequence 0
            yield dut.rx_seq_num.eq(0)
            yield dut.rx_valid.eq(1)
            yield
            yield dut.rx_valid.eq(0)  # Deassert valid immediately
            yield  # Wait for synchronous update

            # Should now expect sequence 1
            expected = (yield dut.rx_expected_seq)
            self.assertEqual(expected, 1, "After receiving seq 0, expect seq 1")

            # Receive sequence 1
            yield dut.rx_seq_num.eq(1)
            yield dut.rx_valid.eq(1)
            yield
            yield dut.rx_valid.eq(0)  # Deassert valid immediately
            yield  # Wait for synchronous update

            # Should now expect sequence 2
            expected = (yield dut.rx_expected_seq)
            self.assertEqual(expected, 2, "After receiving seq 1, expect seq 2")

            yield

        dut = SequenceNumberManager()
        run_simulation(dut, testbench(dut), vcd_name="test_rx_tracking.vcd")

    def test_rx_detects_out_of_order_packet(self):
        """RX should detect when received sequence doesn't match expected."""
        from litepcie.dll.sequence import SequenceNumberManager

        def testbench(dut):
            # Receive sequence 0 (correct)
            yield dut.rx_seq_num.eq(0)
            yield dut.rx_valid.eq(1)
            yield
            error = (yield dut.rx_seq_error)
            self.assertEqual(error, 0, "Sequence 0 should be correct")

            # Now expecting sequence 1, but receive sequence 3 (out of order)
            yield dut.rx_seq_num.eq(3)
            yield
            error = (yield dut.rx_seq_error)
            self.assertEqual(error, 1, "Should detect out-of-order packet")

            yield dut.rx_valid.eq(0)
            yield

        dut = SequenceNumberManager()
        run_simulation(dut, testbench(dut), vcd_name="test_rx_error.vcd")

    def test_ack_updates_acknowledged_sequence(self):
        """ACK reception should update last acknowledged sequence."""
        from litepcie.dll.sequence import SequenceNumberManager

        def testbench(dut):
            # Initially no sequences acknowledged
            acked = (yield dut.tx_acked_seq)
            self.assertEqual(acked, 0)

            # Receive ACK for sequence 5
            yield dut.ack_seq_num.eq(5)
            yield dut.ack_valid.eq(1)
            yield
            yield  # Wait one more cycle for synchronous update
            acked = (yield dut.tx_acked_seq)
            self.assertEqual(acked, 5, "Should track ACKed sequence 5")

            # Receive ACK for sequence 10
            yield dut.ack_seq_num.eq(10)
            yield
            yield  # Wait one more cycle for synchronous update
            acked = (yield dut.tx_acked_seq)
            self.assertEqual(acked, 10, "Should track ACKed sequence 10")

            yield dut.ack_valid.eq(0)
            yield

        dut = SequenceNumberManager()
        run_simulation(dut, testbench(dut), vcd_name="test_ack_tracking.vcd")


if __name__ == "__main__":
    unittest.main()
