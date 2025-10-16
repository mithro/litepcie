#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
PCIe Compliance Tests for Section 3.3 - Data Link Layer.

These tests verify compliance with specific requirements from the
PCI Express Base Specification, Section 3.3.

Each test maps to a "shall" statement in the specification.

Reference: PCIe Base Spec 4.0, Section 3.3
"""

import unittest

from migen import *
from litex.gen import run_simulation


class TestSpec3_3_5_SequenceNumbers(unittest.TestCase):
    """
    Compliance tests for Section 3.3.5: Sequence Numbers.

    Reference: PCIe Base Spec 4.0, Section 3.3.5
    """

    def test_spec_3_3_5_sequence_numbers_12bit(self):
        """
        Spec 3.3.5: Sequence numbers SHALL be 12 bits (0-4095).

        Verify that sequence numbers use exactly 12 bits and wrap at 4096.
        """
        from litepcie.dll.sequence import SequenceNumberManager
        from litepcie.dll.common import DLL_SEQUENCE_NUM_MAX

        def testbench(dut):
            # Verify max sequence number is 4095 (12 bits)
            self.assertEqual(DLL_SEQUENCE_NUM_MAX, 4095,
                           "Sequence number max must be 4095 (12-bit)")

            # Allocate sequences up to max
            for expected_seq in range(4096):
                yield dut.tx_alloc.eq(1)
                yield
                seq = (yield dut.tx_seq_num)
                self.assertEqual(seq, expected_seq,
                               f"Sequence {expected_seq} allocation failed")

            # Next allocation should wrap to 0
            yield dut.tx_alloc.eq(1)
            yield
            seq = (yield dut.tx_seq_num)
            self.assertEqual(seq, 0, "Sequence should wrap to 0 after 4095")

        dut = SequenceNumberManager()
        run_simulation(dut, testbench(dut), vcd_name="compliance_3_3_5.vcd")

    def test_spec_3_3_5_tx_sequence_increments(self):
        """
        Spec 3.3.5: Each transmitted TLP SHALL be assigned the next sequence number.

        Verify that sequence numbers increment by 1 for each TLP.
        """
        from litepcie.dll.sequence import SequenceNumberManager

        def testbench(dut):
            prev_seq = None
            for i in range(10):
                yield dut.tx_alloc.eq(1)
                yield
                seq = (yield dut.tx_seq_num)

                if prev_seq is not None:
                    expected = (prev_seq + 1) % 4096
                    self.assertEqual(seq, expected,
                                   f"Sequence should increment: got {seq}, expected {expected}")
                prev_seq = seq

            yield dut.tx_alloc.eq(0)

        dut = SequenceNumberManager()
        run_simulation(dut, testbench(dut), vcd_name="compliance_3_3_5_tx.vcd")


class TestSpec3_3_4_LCRC(unittest.TestCase):
    """
    Compliance tests for Section 3.3.4: LCRC.

    Reference: PCIe Base Spec 4.0, Section 3.3.4
    """

    def test_spec_3_3_4_lcrc_32bit(self):
        """
        Spec 3.3.4: LCRC SHALL be 32 bits.

        Verify LCRC width is exactly 32 bits.
        """
        from litepcie.dll.common import LCRC_WIDTH

        self.assertEqual(LCRC_WIDTH, 32, "LCRC must be 32 bits")

    def test_spec_3_3_4_lcrc_polynomial(self):
        """
        Spec 3.3.4: LCRC SHALL use polynomial 0x04C11DB7.

        Verify correct CRC-32 polynomial (Ethernet CRC-32).
        """
        from litepcie.dll.common import LCRC_POLYNOMIAL

        self.assertEqual(LCRC_POLYNOMIAL, 0x04C11DB7,
                        "LCRC polynomial must be 0x04C11DB7 (Ethernet CRC-32)")

    def test_spec_3_3_4_lcrc_initial_value(self):
        """
        Spec 3.3.4: LCRC calculation SHALL start with 0xFFFFFFFF.

        Verify LCRC initial value is all ones.
        """
        from litepcie.dll.common import LCRC_INITIAL_VALUE

        self.assertEqual(LCRC_INITIAL_VALUE, 0xFFFFFFFF,
                        "LCRC initial value must be 0xFFFFFFFF")

    def test_spec_3_3_4_lcrc_appended_to_tlp(self):
        """
        Spec 3.3.4: LCRC SHALL be appended to each TLP.

        Verify TX path calculates and stores LCRC.
        """
        from litepcie.dll.tx import DLLTX

        def testbench(dut):
            # Enable PHY ready
            yield dut.phy_source.ready.eq(1)

            # Send TLP
            yield dut.tlp_sink.valid.eq(1)
            yield dut.tlp_sink.data.eq(0xDEADBEEF)
            yield
            yield dut.tlp_sink.valid.eq(0)

            # Wait for processing
            for _ in range(10):
                yield

            # Verify LCRC was calculated (non-zero in debug signal)
            lcrc = (yield dut.debug_last_lcrc)
            self.assertNotEqual(lcrc, 0, "LCRC should be calculated for TLP")

        dut = DLLTX(data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="compliance_3_3_4_append.vcd")


class TestSpec3_3_6_AckNak(unittest.TestCase):
    """
    Compliance tests for Section 3.3.6: ACK/NAK Protocol.

    Reference: PCIe Base Spec 4.0, Section 3.3.6
    """

    def test_spec_3_3_6_ack_for_valid_tlp(self):
        """
        Spec 3.3.6: Receiver SHALL send ACK DLLP for correctly received TLP.

        Verify RX path generates ACK for valid TLP.
        """
        from litepcie.dll.rx import DLLRX

        def testbench(dut):
            # Enable ready signals
            yield dut.tlp_source.ready.eq(1)
            yield dut.ack_source.ready.eq(1)
            yield dut.nak_source.ready.eq(1)
            yield

            # Send valid TLP
            yield dut.phy_sink.valid.eq(1)
            yield dut.phy_sink.data.eq(0xDEADBEEF)
            yield dut.phy_sink.seq_num.eq(0)
            yield dut.phy_sink.lcrc.eq(0x12345678)
            yield
            yield dut.phy_sink.valid.eq(0)

            # Wait for ACK
            ack_found = False
            for _ in range(15):
                yield
                ack_valid = (yield dut.ack_source.valid)
                if ack_valid:
                    ack_found = True
                    break

            self.assertTrue(ack_found,
                          "Receiver must send ACK for valid TLP (Spec 3.3.6)")

        dut = DLLRX(data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="compliance_3_3_6_ack.vcd")

    def test_spec_3_3_6_nak_for_invalid_lcrc(self):
        """
        Spec 3.3.6: Receiver SHALL send NAK DLLP for TLP with bad LCRC.

        Verify RX path generates NAK for invalid LCRC.
        """
        from litepcie.dll.rx import DLLRX

        def testbench(dut):
            # Enable ready signals
            yield dut.tlp_source.ready.eq(1)
            yield dut.ack_source.ready.eq(1)
            yield dut.nak_source.ready.eq(1)
            yield

            # Send TLP with bad LCRC
            yield dut.phy_sink.valid.eq(1)
            yield dut.phy_sink.data.eq(0xDEADBEEF)
            yield dut.phy_sink.seq_num.eq(0)
            yield dut.phy_sink.lcrc.eq(0xBADBADBA)  # Invalid
            yield
            yield dut.phy_sink.valid.eq(0)

            # Wait for NAK
            nak_found = False
            for _ in range(15):
                yield
                nak_valid = (yield dut.nak_source.valid)
                if nak_valid:
                    nak_found = True
                    break

            self.assertTrue(nak_found,
                          "Receiver must send NAK for bad LCRC (Spec 3.3.6)")

        dut = DLLRX(data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="compliance_3_3_6_nak.vcd")

    def test_spec_3_3_6_retry_buffer_stores_tlps(self):
        """
        Spec 3.3.6: Transmitter SHALL store TLPs until acknowledged.

        Verify retry buffer stores TLPs before ACK.
        """
        from litepcie.dll.retry_buffer import RetryBuffer

        def testbench(dut):
            # Store TLP
            yield dut.write_data.eq(0xDEADBEEF)
            yield dut.write_seq.eq(0)
            yield dut.write_valid.eq(1)
            yield
            yield dut.write_valid.eq(0)
            yield

            # Verify stored (buffer not empty)
            empty = (yield dut.empty)
            self.assertFalse(empty,
                           "Retry buffer must store TLP until ACKed (Spec 3.3.6)")

            # ACK the TLP
            yield dut.ack_seq.eq(0)
            yield dut.ack_valid.eq(1)
            yield
            yield dut.ack_valid.eq(0)
            yield

            # Should be released
            empty = (yield dut.empty)
            self.assertTrue(empty, "ACK should release TLP from retry buffer")

        dut = RetryBuffer(depth=16, data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="compliance_3_3_6_retry.vcd")

    def test_spec_3_3_6_nak_triggers_retransmission(self):
        """
        Spec 3.3.6: Transmitter SHALL retransmit TLPs after NAK.

        Verify NAK triggers replay from retry buffer.
        """
        from litepcie.dll.retry_buffer import RetryBuffer

        def testbench(dut):
            # Store 2 TLPs
            for seq in range(2):
                yield dut.write_data.eq(0xAAAA0000 | seq)
                yield dut.write_seq.eq(seq)
                yield dut.write_valid.eq(1)
                yield
            yield dut.write_valid.eq(0)
            yield

            # ACK first TLP
            yield dut.ack_seq.eq(0)
            yield dut.ack_valid.eq(1)
            yield
            yield dut.ack_valid.eq(0)
            yield

            # NAK should trigger replay
            yield dut.nak_seq.eq(0)
            yield dut.nak_valid.eq(1)
            yield
            yield dut.nak_valid.eq(0)
            yield dut.replay_ready.eq(1)
            yield

            # Should replay sequence 1
            replay_valid = (yield dut.replay_valid)
            self.assertTrue(replay_valid,
                          "NAK must trigger retransmission (Spec 3.3.6)")

        dut = RetryBuffer(depth=16, data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="compliance_3_3_6_retx.vcd")


class TestSpec3_3_7_RetryBuffer(unittest.TestCase):
    """
    Compliance tests for Section 3.3.7: Retry Buffer.

    Reference: PCIe Base Spec 4.0, Section 3.3.7
    """

    def test_spec_3_3_7_buffer_depth_sufficient(self):
        """
        Spec 3.3.7: Retry buffer SHALL be large enough for link operation.

        Verify retry buffer has configurable depth and handles multiple TLPs.
        """
        from litepcie.dll.retry_buffer import RetryBuffer

        def testbench(dut):
            depth = dut.depth

            # Store multiple TLPs (up to depth-1)
            for i in range(min(10, depth - 1)):
                yield dut.write_data.eq(i)
                yield dut.write_seq.eq(i)
                yield dut.write_valid.eq(1)
                yield
            yield dut.write_valid.eq(0)
            yield

            # Buffer should not be full yet
            full = (yield dut.full)
            self.assertFalse(full,
                           "Buffer with adequate depth should handle multiple TLPs")

        # Test with standard depth
        dut = RetryBuffer(depth=64, data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="compliance_3_3_7_depth.vcd")

    def test_spec_3_3_7_fifo_ordering(self):
        """
        Spec 3.3.7: Retry buffer SHALL maintain TLP order.

        Verify TLPs are replayed in the same order they were stored.
        """
        from litepcie.dll.retry_buffer import RetryBuffer

        def testbench(dut):
            # Store 3 TLPs in order
            test_data = [0xAAAA, 0xBBBB, 0xCCCC]
            for seq, data in enumerate(test_data):
                yield dut.write_data.eq(data)
                yield dut.write_seq.eq(seq)
                yield dut.write_valid.eq(1)
                yield
            yield dut.write_valid.eq(0)
            yield

            # Trigger replay (NAK)
            yield dut.nak_seq.eq(0)
            yield dut.nak_valid.eq(1)
            yield
            yield dut.nak_valid.eq(0)
            yield dut.replay_ready.eq(1)
            yield

            # Verify order is maintained
            for expected_seq, expected_data in enumerate(test_data):
                replay_valid = (yield dut.replay_valid)
                if not replay_valid:
                    yield  # Wait one more cycle
                    replay_valid = (yield dut.replay_valid)

                self.assertTrue(replay_valid, f"Replay {expected_seq} should be valid")

                replay_seq = (yield dut.replay_seq)
                replay_data = (yield dut.replay_data)

                self.assertEqual(replay_seq, expected_seq,
                               f"Replay sequence order must match (got {replay_seq})")
                self.assertEqual(replay_data, expected_data,
                               f"Replay data order must match (got 0x{replay_data:X})")
                yield

        dut = RetryBuffer(depth=16, data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="compliance_3_3_7_order.vcd")


if __name__ == "__main__":
    unittest.main()
