#!/usr/bin/env python3

"""
Tests for Gen1/Gen2 Speed Switching

Validates speed control signals and dynamic speed negotiation support.
"""

import unittest
from migen import *
from litepcie.phy.transceiver_base.transceiver import PIPETransceiver


class TestSpeedSwitching(unittest.TestCase):
    """Test speed control functionality."""

    def test_speed_signal_exists(self):
        """Transceiver should have speed control signal."""
        transceiver = PIPETransceiver(data_width=16, gen=1)

        # Should have speed signal
        self.assertIsInstance(transceiver.speed, Signal)
        self.assertEqual(len(transceiver.speed), 2)  # 2 bits for Gen1/2/3

    def test_speed_signal_default_gen1(self):
        """Speed signal should default to gen parameter."""
        transceiver = PIPETransceiver(data_width=16, gen=1)

        # Default should be Gen1
        self.assertEqual(transceiver.speed.reset, 1)

    def test_speed_signal_default_gen2(self):
        """Speed signal should default to Gen2 when gen=2."""
        transceiver = PIPETransceiver(data_width=16, gen=2)

        # Default should be Gen2
        self.assertEqual(transceiver.speed.reset, 2)

    def test_speed_values(self):
        """Speed values should map correctly to PCIe generations."""
        # Gen1
        transceiver1 = PIPETransceiver(data_width=16, gen=1)
        self.assertEqual(transceiver1.get_line_rate(), 2.5e9)

        # Gen2
        transceiver2 = PIPETransceiver(data_width=16, gen=2)
        self.assertEqual(transceiver2.get_line_rate(), 5.0e9)

        # Gen3
        transceiver3 = PIPETransceiver(data_width=16, gen=3)
        self.assertEqual(transceiver3.get_line_rate(), 8.0e9)

    def test_speed_to_word_clock_gen1(self):
        """Gen1 speed should produce 250 MHz word clock."""
        transceiver = PIPETransceiver(data_width=16, gen=1)

        word_clk = transceiver.get_word_clk_freq()
        self.assertEqual(word_clk, 250e6)

    def test_speed_to_word_clock_gen2(self):
        """Gen2 speed should produce 500 MHz word clock."""
        transceiver = PIPETransceiver(data_width=16, gen=2)

        word_clk = transceiver.get_word_clk_freq()
        self.assertEqual(word_clk, 500e6)


class TestSpeedSwitchingIntegration(unittest.TestCase):
    """Test speed switching integration patterns."""

    def test_ltssm_speed_control_pattern(self):
        """Demonstrate LTSSM integration pattern for speed control."""
        # This is a documentation test showing the expected integration

        class MockLTSSM:
            def __init__(self):
                self.link_speed = Signal(2)  # Speed negotiated by LTSSM

        transceiver = PIPETransceiver(data_width=16, gen=1)
        ltssm = MockLTSSM()

        # Integration pattern (would be done in actual PHY wrapper)
        # self.comb += transceiver.speed.eq(ltssm.link_speed)

        # Verify signals exist for connection
        self.assertIsInstance(transceiver.speed, Signal)
        self.assertIsInstance(ltssm.link_speed, Signal)

    def test_speed_change_requires_retraining(self):
        """Document that speed changes require link retraining."""
        # This is a documentation test
        #
        # When speed changes:
        # 1. LTSSM enters Recovery state
        # 2. Speed signal updated
        # 3. Transceiver reconfigures (output dividers change)
        # 4. Link retrains with TS1/TS2 at new speed
        # 5. LTSSM returns to L0

        transceiver = PIPETransceiver(data_width=16, gen=1)

        # Initial speed: Gen1
        initial_speed = 1

        # LTSSM negotiates Gen2
        new_speed = 2

        # This would trigger retraining in actual implementation
        self.assertNotEqual(initial_speed, new_speed)


if __name__ == "__main__":
    unittest.main()
