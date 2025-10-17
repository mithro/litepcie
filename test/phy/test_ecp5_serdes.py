#!/usr/bin/env python3

"""
Tests for Lattice ECP5 SERDES Transceiver
"""

import unittest
from migen import *
from litepcie.phy.lattice.ecp5_serdes import (
    ECP5SCIInterface,
    ECP5SerDesPLL,
    ECP5ResetSequencer,
    ECP5SerDesTransceiver,
)


class TestECP5SCIInterface(unittest.TestCase):
    """Test ECP5 SCI interface."""

    def test_instantiation(self):
        """SCI interface should have all required signals."""
        sci = ECP5SCIInterface()

        # Check SCI signals
        self.assertIsInstance(sci.sci_wdata, Signal)
        self.assertEqual(len(sci.sci_wdata), 8)
        self.assertIsInstance(sci.sci_addr, Signal)
        self.assertEqual(len(sci.sci_addr), 6)
        self.assertIsInstance(sci.sci_rdata, Signal)
        self.assertIsInstance(sci.sci_rd, Signal)
        self.assertIsInstance(sci.sci_wrn, Signal)


class TestECP5SerDesPLL(unittest.TestCase):
    """Test ECP5 SERDES PLL."""

    def test_gen1_config(self):
        """Gen1 PLL should configure correctly."""
        pll = ECP5SerDesPLL(refclk_freq=100e6, linerate=2.5e9, speed_5GTps=False)

        config = pll.get_config()
        self.assertIsNotNone(config)
        self.assertEqual(config["D_TX_MAX_RATE"], "2.5")

    def test_gen2_config(self):
        """Gen2 PLL should configure for 5.0 GT/s."""
        pll = ECP5SerDesPLL(refclk_freq=100e6, linerate=5.0e9, speed_5GTps=True)

        config = pll.get_config()
        self.assertIsNotNone(config)
        self.assertEqual(config["D_TX_MAX_RATE"], "5.0")


class TestECP5ResetSequencer(unittest.TestCase):
    """Test ECP5 reset sequencer."""

    def test_instantiation(self):
        """Reset sequencer should have 8-state FSM."""
        sequencer = ECP5ResetSequencer(sys_clk_freq=125e6)

        # Should have FSM
        self.assertTrue(hasattr(sequencer, 'fsm'))

        # Should have all required signals
        self.assertIsInstance(sequencer.tx_pll_locked, Signal)
        self.assertIsInstance(sequencer.tx_ready, Signal)
        self.assertIsInstance(sequencer.rx_ready, Signal)


class TestECP5SerDesTransceiver(unittest.TestCase):
    """Test ECP5SerDesTransceiver wrapper."""

    def test_instantiation_basic(self):
        """ECP5 SERDES transceiver should instantiate with basic structure."""
        class MockPlatform:
            pass

        # Create ECP5 SERDES transceiver (skeleton)
        serdes = ECP5SerDesTransceiver(
            platform=MockPlatform(),
            dcu=0,
            channel=0,
            gearing=2,
            speed_5GTps=False,
            refclk_freq=100e6,
            sys_clk_freq=125e6,
            data_width=16,
            gen=1
        )

        # Should have PIPE interface signals
        self.assertIsInstance(serdes.tx_data, Signal)
        self.assertIsInstance(serdes.rx_data, Signal)
        self.assertIsInstance(serdes.tx_datak, Signal)
        self.assertIsInstance(serdes.rx_datak, Signal)

        # Should have submodules
        self.assertTrue(hasattr(serdes, 'encoder'))
        self.assertTrue(hasattr(serdes, 'decoder'))
        self.assertTrue(hasattr(serdes, 'sci'))
        self.assertTrue(hasattr(serdes, 'pll'))
        self.assertTrue(hasattr(serdes, 'tx_datapath'))
        self.assertTrue(hasattr(serdes, 'rx_datapath'))
        self.assertTrue(hasattr(serdes, 'reset_seq'))

    def test_gearing_validation(self):
        """Data width must match gearing."""
        class MockPlatform:
            pass

        with self.assertRaises(AssertionError):
            # Gearing 2 requires data_width 16, not 8
            serdes = ECP5SerDesTransceiver(
                platform=MockPlatform(),
                dcu=0,
                channel=0,
                gearing=2,
                refclk_freq=100e6,
                sys_clk_freq=125e6,
                data_width=8,  # Wrong for gearing=2
                gen=1
            )

    def test_dcu_channel_validation(self):
        """DCU and channel must be 0 or 1."""
        class MockPlatform:
            pass

        with self.assertRaises(AssertionError):
            # DCU 2 is invalid
            serdes = ECP5SerDesTransceiver(
                platform=MockPlatform(),
                dcu=2,  # Invalid
                channel=0,
                gearing=2,
                refclk_freq=100e6,
                sys_clk_freq=125e6,
                data_width=16,
                gen=1
            )


if __name__ == "__main__":
    unittest.main()
