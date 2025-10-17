#!/usr/bin/env python3

"""
Tests for Xilinx UltraScale+ GTY Transceiver
"""

import unittest
from migen import *
from litepcie.phy.xilinx.usp_gty import (
    GTYChannelPLL,
    GTYResetSequencer,
    USPGTYTransceiver,
)


class TestGTYChannelPLL(unittest.TestCase):
    """Test GTY QPLL configuration."""

    def test_gen1_100mhz_refclk(self):
        """Gen1 with 100 MHz refclk should find valid QPLL configuration."""
        pll = GTYChannelPLL(refclk_freq=100e6, linerate=2.5e9)

        # Should have computed a valid configuration
        self.assertIsNotNone(pll.config)
        self.assertIn('n', pll.config)
        self.assertIn('m', pll.config)
        self.assertIn('d', pll.config)
        self.assertIn('qpll_type', pll.config)
        self.assertIn('vco_freq', pll.config)

        # VCO frequency should be in valid range (either QPLL0 or QPLL1)
        vco_freq = pll.config['vco_freq']
        qpll_type = pll.config['qpll_type']

        if qpll_type == "QPLL0":
            self.assertGreaterEqual(vco_freq, 9.8e9)
            self.assertLessEqual(vco_freq, 16.375e9)
        else:  # QPLL1
            self.assertGreaterEqual(vco_freq, 8.0e9)
            self.assertLessEqual(vco_freq, 13.0e9)

        # Linerate should match
        self.assertAlmostEqual(pll.config['linerate'], 2.5e9, delta=1e6)

    def test_gen2_100mhz_refclk(self):
        """Gen2 with 100 MHz refclk should find valid QPLL configuration."""
        pll = GTYChannelPLL(refclk_freq=100e6, linerate=5.0e9)

        # Should have valid configuration
        self.assertIsNotNone(pll.config)

        # VCO frequency should be in valid range
        vco_freq = pll.config['vco_freq']
        qpll_type = pll.config['qpll_type']

        if qpll_type == "QPLL0":
            self.assertGreaterEqual(vco_freq, 9.8e9)
            self.assertLessEqual(vco_freq, 16.375e9)
        else:
            self.assertGreaterEqual(vco_freq, 8.0e9)
            self.assertLessEqual(vco_freq, 13.0e9)

        # Linerate should match
        self.assertAlmostEqual(pll.config['linerate'], 5.0e9, delta=1e6)


class TestGTYResetSequencer(unittest.TestCase):
    """Test GTY reset sequencer."""

    def test_instantiation(self):
        """Reset sequencer should instantiate with FSM."""
        sequencer = GTYResetSequencer(sys_clk_freq=125e6)

        # Should have FSM
        self.assertTrue(hasattr(sequencer, 'fsm'))

        # Should have all required signals
        self.assertIsInstance(sequencer.tx_pll_locked, Signal)
        self.assertIsInstance(sequencer.tx_ready, Signal)
        self.assertIsInstance(sequencer.rx_ready, Signal)


class TestUSPGTYTransceiver(unittest.TestCase):
    """Test USPGTYTransceiver wrapper."""

    def test_instantiation_basic(self):
        """GTY transceiver should instantiate with basic structure."""
        class MockPads:
            def __init__(self):
                self.tx_p = Signal()
                self.tx_n = Signal()
                self.rx_p = Signal()
                self.rx_n = Signal()

        class MockRefclkPads:
            def __init__(self):
                self.p = Signal()
                self.n = Signal()

        class MockPlatform:
            pass

        # Create GTY transceiver (skeleton)
        gty = USPGTYTransceiver(
            platform=MockPlatform(),
            pads=MockPads(),
            refclk_pads=MockRefclkPads(),
            refclk_freq=100e6,
            sys_clk_freq=125e6,
            data_width=16,
            gen=1
        )

        # Should have PIPE interface signals
        self.assertIsInstance(gty.tx_data, Signal)
        self.assertIsInstance(gty.rx_data, Signal)
        self.assertIsInstance(gty.tx_datak, Signal)
        self.assertIsInstance(gty.rx_datak, Signal)

        # Should have submodules
        self.assertTrue(hasattr(gty, 'pll'))
        self.assertTrue(hasattr(gty, 'encoder'))
        self.assertTrue(hasattr(gty, 'decoder'))
        self.assertTrue(hasattr(gty, 'tx_datapath'))
        self.assertTrue(hasattr(gty, 'rx_datapath'))
        self.assertTrue(hasattr(gty, 'reset_seq'))


if __name__ == "__main__":
    unittest.main()
