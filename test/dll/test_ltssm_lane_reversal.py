# test/dll/test_ltssm_lane_reversal.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for LTSSM lane reversal detection.

Lane reversal allows PCIe links to work when TX/RX lanes are
physically reversed on the board, simplifying PCB routing.

References:
- PCIe Base Spec 4.0, Section 4.2.4.1.4: Lane Reversal
"""

import unittest

from migen import *
from litex.gen import run_simulation

from litepcie.dll.ltssm import LTSSM


class TestLTSSMLaneReversal(unittest.TestCase):
    """Test lane reversal detection."""

    def test_normal_lane_ordering_x4(self):
        """
        Normal lane ordering: Lane 0-3 in correct order.

        In normal configuration, received lane numbers match
        expected sequence (0, 1, 2, 3 for x4).
        """
        def testbench(dut):
            # Simulate normal lane order
            yield dut.rx_elecidle.eq(0)
            yield
            yield

            # In POLLING, receive TS1 with normal lane numbers
            yield dut.ts1_detected.eq(1)

            # Lanes received in order: 0, 1, 2, 3
            yield dut.rx_lane_numbers[0].eq(0)
            yield dut.rx_lane_numbers[1].eq(1)
            yield dut.rx_lane_numbers[2].eq(2)
            yield dut.rx_lane_numbers[3].eq(3)
            yield
            yield

            # Should detect normal ordering
            lane_reversed = yield dut.lane_reversal
            self.assertEqual(lane_reversed, 0)

        dut = LTSSM(gen=1, lanes=4)
        run_simulation(dut, testbench(dut))

    def test_reversed_lane_ordering_x4(self):
        """
        Reversed lane ordering: Lane 3-0 (physically reversed).

        When lanes are reversed, received lane numbers are
        inverted: (3, 2, 1, 0) instead of (0, 1, 2, 3).

        LTSSM should detect this and set lane_reversal flag.
        """
        def testbench(dut):
            yield dut.rx_elecidle.eq(0)
            yield
            yield

            # In POLLING, receive TS1 with reversed lane numbers
            yield dut.ts1_detected.eq(1)

            # Lanes received reversed: 3, 2, 1, 0
            yield dut.rx_lane_numbers[0].eq(3)
            yield dut.rx_lane_numbers[1].eq(2)
            yield dut.rx_lane_numbers[2].eq(1)
            yield dut.rx_lane_numbers[3].eq(0)
            yield
            yield

            # Should detect lane reversal
            lane_reversed = yield dut.lane_reversal
            self.assertEqual(lane_reversed, 1)

        dut = LTSSM(gen=1, lanes=4)
        run_simulation(dut, testbench(dut))

    def test_lane_reversal_compensation(self):
        """
        Lane reversal should be transparent to upper layers.

        When reversal detected, LTSSM should compensate by
        remapping lane numbers so data flows correctly.
        """
        def testbench(dut):
            # Simulate reversed lanes
            yield dut.rx_elecidle.eq(0)
            yield
            yield

            yield dut.ts1_detected.eq(1)
            yield dut.rx_lane_numbers[0].eq(3)
            yield dut.rx_lane_numbers[1].eq(2)
            yield dut.rx_lane_numbers[2].eq(1)
            yield dut.rx_lane_numbers[3].eq(0)
            yield
            yield

            # Physical lane 0 receives logical lane 3
            # Remapping should compensate
            logical_lane = yield dut.logical_lane_map[0]
            self.assertEqual(logical_lane, 3)

            logical_lane = yield dut.logical_lane_map[1]
            self.assertEqual(logical_lane, 2)

            logical_lane = yield dut.logical_lane_map[2]
            self.assertEqual(logical_lane, 1)

            logical_lane = yield dut.logical_lane_map[3]
            self.assertEqual(logical_lane, 0)

        dut = LTSSM(gen=1, lanes=4)
        run_simulation(dut, testbench(dut))


if __name__ == "__main__":
    unittest.main()
