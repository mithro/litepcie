#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for PCIe DLL Retry Buffer.

Tests behavioral aspects of retry buffer for ACK/NAK protocol,
following TDD principles.

Reference: PCIe Base Spec 4.0, Section 3.3.7
"""

import unittest

from migen import *
from litex.gen import run_simulation


class TestRetryBuffer(unittest.TestCase):
    """Test retry buffer for ACK/NAK protocol."""

    def test_store_and_ack(self):
        """Test storing TLP and acknowledging."""
        from litepcie.dll.retry_buffer import RetryBuffer

        def testbench(dut):
            # Store TLP with sequence 0
            tlp_data = 0xDEADBEEFCAFEBABE
            yield dut.write_data.eq(tlp_data)
            yield dut.write_seq.eq(0)
            yield dut.write_valid.eq(1)
            yield
            yield dut.write_valid.eq(0)
            yield  # Wait for synchronous write_ptr update

            # Verify not empty
            empty = (yield dut.empty)
            self.assertFalse(empty, "Buffer should not be empty after write")

            # ACK sequence 0
            yield dut.ack_seq.eq(0)
            yield dut.ack_valid.eq(1)
            yield
            yield dut.ack_valid.eq(0)

            # Should be empty now
            yield
            empty = (yield dut.empty)
            self.assertTrue(empty, "Buffer should be empty after ACK")

        dut = RetryBuffer(depth=16, data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="test_retry_store_ack.vcd")

    def test_nak_triggers_replay(self):
        """Test NAK triggers replay from correct sequence."""
        from litepcie.dll.retry_buffer import RetryBuffer

        def testbench(dut):
            # Store 3 TLPs
            tlps = [
                (0, 0xAAAAAAAAAAAAAAAA),
                (1, 0xBBBBBBBBBBBBBBBB),
                (2, 0xCCCCCCCCCCCCCCCC),
            ]

            for seq, data in tlps:
                yield dut.write_seq.eq(seq)
                yield dut.write_data.eq(data)
                yield dut.write_valid.eq(1)
                yield

            yield dut.write_valid.eq(0)
            yield

            # ACK sequence 0
            yield dut.ack_seq.eq(0)
            yield dut.ack_valid.eq(1)
            yield
            yield dut.ack_valid.eq(0)
            yield

            # NAK sequence 0 (last good was 0, replay from 1)
            yield dut.nak_seq.eq(0)
            yield dut.nak_valid.eq(1)
            yield
            yield dut.nak_valid.eq(0)
            yield

            # Enable replay
            yield dut.replay_ready.eq(1)
            yield

            # Should replay sequence 1
            replay_valid = (yield dut.replay_valid)
            replay_seq = (yield dut.replay_seq)
            replay_data = (yield dut.replay_data)

            self.assertTrue(replay_valid, "Replay should be valid")
            self.assertEqual(replay_seq, 1, "Should replay sequence 1")
            self.assertEqual(replay_data, 0xBBBBBBBBBBBBBBBB, "Should replay correct data")
            yield

            # Should replay sequence 2
            replay_seq = (yield dut.replay_seq)
            replay_data = (yield dut.replay_data)
            self.assertEqual(replay_seq, 2, "Should replay sequence 2")
            self.assertEqual(replay_data, 0xCCCCCCCCCCCCCCCC, "Should replay correct data")

        dut = RetryBuffer(depth=16, data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="test_retry_nak_replay.vcd")

    def test_buffer_full(self):
        """Test buffer full condition prevents writes."""
        from litepcie.dll.retry_buffer import RetryBuffer

        def testbench(dut):
            # Fill buffer to capacity (depth-1 items in a circular buffer)
            depth = dut.depth

            # Write depth-1 items (e.g., 15 items for depth=16)
            for i in range(depth - 1):
                yield dut.write_seq.eq(i)
                yield dut.write_data.eq(i)
                yield dut.write_valid.eq(1)
                yield
                yield dut.write_valid.eq(0)  # Deassert immediately
                yield  # Wait for sync update

                # Check full status - should be full only on last iteration
                full = (yield dut.full)
                if i < depth - 2:
                    self.assertFalse(full, f"Buffer should not be full at entry {i}")
                else:
                    self.assertTrue(full, f"Buffer should be full after entry {i}")

            # Verify buffer is full
            full = (yield dut.full)
            write_ready = (yield dut.write_ready)
            self.assertTrue(full, "Buffer should be full")
            self.assertFalse(write_ready, "Write should not be ready when full")

            # ACK one entry to make space
            yield dut.ack_seq.eq(0)
            yield dut.ack_valid.eq(1)
            yield
            yield dut.ack_valid.eq(0)
            yield

            # Should no longer be full
            full = (yield dut.full)
            self.assertFalse(full, "Buffer should not be full after ACK")

        dut = RetryBuffer(depth=16, data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="test_retry_buffer_full.vcd")


if __name__ == "__main__":
    unittest.main()
