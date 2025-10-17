# test/dll/test_ltssm_gen2.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for LTSSM Gen2 speed negotiation.

Gen2 speed negotiation uses TS1/TS2 rate_id field to communicate
supported speeds between link partners.

References:
- PCIe Base Spec 4.0, Section 4.2.6.2.1: Speed Change
- PCIe Base Spec 4.0, Section 8.4.1: Link Speed Changes
"""

import unittest

from migen import *
from litex.gen import run_simulation

from litepcie.dll.ltssm import LTSSM
from litepcie.dll.pipe import TS1OrderedSet, TS2OrderedSet


class TestLTSSMGen2Negotiation(unittest.TestCase):
    """Test Gen2 speed negotiation."""

    def test_ltssm_gen1_initialization(self):
        """
        LTSSM initialized with gen=1 should start at Gen1 speed.

        Initial link training always starts at Gen1 (2.5 GT/s),
        then may negotiate up to Gen2 if both partners support it.

        Reference: PCIe Spec 4.0, Section 4.2.5.3.2: Polling
        """
        def testbench(dut):
            # Should initialize with Gen1 speed
            link_speed = yield dut.link_speed
            self.assertEqual(link_speed, 1)  # Gen1

            # Should report Gen1 in TS1 rate_id
            rate_id = yield dut.ts_rate_id
            self.assertEqual(rate_id, 1)  # Gen1

        dut = LTSSM(gen=1, lanes=1)
        run_simulation(dut, testbench(dut))

    def test_ltssm_gen2_capability_advertisement(self):
        """
        LTSSM initialized with gen=2 should advertise Gen2 capability.

        When LTSSM is configured for Gen2 support, it should:
        1. Start training at Gen1 (spec requirement)
        2. Advertise Gen2 capability via rate_id=2 in TS1/TS2
        3. Negotiate to Gen2 if partner also advertises Gen2

        Reference: PCIe Spec 4.0, Section 4.2.6.2.1
        """
        def testbench(dut):
            # Should start at Gen1 speed for initial training
            link_speed = yield dut.link_speed
            self.assertEqual(link_speed, 1)  # Gen1 initially

            # Should advertise Gen2 capability in TS rate_id
            rate_id = yield dut.ts_rate_id
            self.assertEqual(rate_id, 2)  # Advertise Gen2 support

            # Should have Gen2 capability flag
            has_gen2 = yield dut.gen2_capable
            self.assertEqual(has_gen2, 1)

        dut = LTSSM(gen=2, lanes=1)
        run_simulation(dut, testbench(dut))

    def test_gen2_negotiation_successful(self):
        """
        Both partners advertising Gen2 should negotiate to Gen2 speed.

        Speed negotiation flow:
        1. Both start at Gen1, exchange TS1 with rate_id=2
        2. Both detect partner Gen2 support
        3. After reaching L0 at Gen1, enter RECOVERY.Speed
        4. Change speed to Gen2, retrain at higher speed
        5. Return to L0 at Gen2
        """
        def testbench(dut):
            # Simulate receiver detection
            yield dut.rx_elecidle.eq(0)
            yield
            yield

            # Now in POLLING, sending TS1 with rate_id=2
            state = yield dut.current_state
            self.assertEqual(state, dut.POLLING)

            # Simulate receiving TS1 from Gen2-capable partner
            yield dut.ts1_detected.eq(1)
            yield dut.rx_rate_id.eq(2)  # Partner advertises Gen2
            yield
            yield
            yield

            # Should detect Gen2 capability match
            gen2_match = yield dut.speed_change_required
            self.assertEqual(gen2_match, 1)

            # Should be in CONFIGURATION now
            state = yield dut.current_state
            self.assertEqual(state, dut.CONFIGURATION)

            # Continue to L0 at Gen1 first (spec requirement)
            yield dut.ts2_detected.eq(1)
            yield
            yield
            yield

            # In L0 at Gen1
            state = yield dut.current_state
            self.assertEqual(state, dut.L0)
            link_speed = yield dut.link_speed
            self.assertEqual(link_speed, 1)  # Still Gen1

            # LTSSM should automatically enter RECOVERY.Speed
            # to change to Gen2
            for _ in range(10):
                yield
                state = yield dut.current_state
                if state == dut.RECOVERY_SPEED:
                    break

            self.assertEqual(state, dut.RECOVERY_SPEED)

            # After speed change, should retrain and reach L0 at Gen2
            # (Simplified - actual implementation needs full retrain)

        dut = LTSSM(gen=2, lanes=1)
        run_simulation(dut, testbench(dut))


class TestLTSSMMultiLane(unittest.TestCase):
    """Test multi-lane link configuration."""

    def test_ltssm_x4_initialization(self):
        """
        LTSSM initialized with lanes=4 should configure x4 link.

        Multi-lane links require:
        1. Each lane sends TS1/TS2 with unique lane_number
        2. Lane numbers must be consecutive (0-3 for x4)
        3. All lanes must complete training

        Reference: PCIe Spec 4.0, Section 4.2.6.2: Lane Numbers
        """
        def testbench(dut):
            # Should initialize with x4 width
            link_width = yield dut.link_width
            self.assertEqual(link_width, 4)

            # Should have configured_lanes output
            configured_lanes = yield dut.configured_lanes
            self.assertEqual(configured_lanes, 0)  # Not configured yet

        dut = LTSSM(gen=1, lanes=4)
        run_simulation(dut, testbench(dut))

    def test_multi_lane_negotiation(self):
        """
        Multi-lane links should negotiate common width.

        Both partners advertise maximum width, then negotiate
        to minimum of both. For example:
        - Device A: supports x8
        - Device B: supports x4
        - Result: link trains as x4
        """
        def testbench(dut):
            # Simulate x4 device receiving TS from x8 partner
            yield dut.rx_elecidle.eq(0)
            yield
            yield
            yield

            # In POLLING
            yield dut.ts1_detected.eq(1)
            yield dut.rx_link_width.eq(8)  # Partner wants x8
            yield
            yield
            yield

            # Should be in CONFIGURATION now
            state = yield dut.current_state
            self.assertEqual(state, dut.CONFIGURATION)

            # Should negotiate to x4 (our limit)
            negotiated_width = yield dut.configured_lanes
            self.assertEqual(negotiated_width, 4)

            # Also check link_width was updated
            link_width = yield dut.link_width
            self.assertEqual(link_width, 4)

        dut = LTSSM(gen=1, lanes=4)
        run_simulation(dut, testbench(dut))

    def test_lane_numbers_in_ts1(self):
        """
        Each lane must send TS1/TS2 with correct lane number.

        For x4 link, lanes 0-3 each send TS with their lane_number.
        Receiver validates all expected lanes are present.
        """
        def testbench(dut):
            # Check that TS contains lane number field
            # (This is a per-lane TX configuration)
            for lane_num in range(4):
                lane_id = yield dut.ts_lane_number[lane_num]
                self.assertEqual(lane_id, lane_num)

        dut = LTSSM(gen=1, lanes=4)
        run_simulation(dut, testbench(dut))


if __name__ == "__main__":
    unittest.main()
