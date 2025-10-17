#!/usr/bin/env python3

"""
Tests for Xilinx 7-Series GTX Transceiver

Tests the GTX wrapper structure, PLL configuration, and integration.
"""

import unittest
from migen import *
from litepcie.phy.xilinx.s7_gtx import (
    GTXChannelPLL,
    GTXResetSequencer,
    S7GTXTransceiver,
)


class TestGTXChannelPLL(unittest.TestCase):
    """Test GTX PLL configuration."""

    def test_gen1_100mhz_refclk(self):
        """Gen1 with 100 MHz refclk should find valid configuration."""
        pll = GTXChannelPLL(refclk_freq=100e6, linerate=2.5e9)

        # Should have computed a valid configuration
        self.assertIsNotNone(pll.config)
        self.assertIn('n1', pll.config)
        self.assertIn('n2', pll.config)
        self.assertIn('m', pll.config)
        self.assertIn('d', pll.config)
        self.assertIn('vco_freq', pll.config)

        # VCO frequency should be in valid range
        vco_freq = pll.config['vco_freq']
        self.assertGreaterEqual(vco_freq, 1.6e9)
        self.assertLessEqual(vco_freq, 3.3e9)

        # Linerate should match (within tolerance)
        self.assertAlmostEqual(pll.config['linerate'], 2.5e9, delta=1e6)

    def test_gen2_100mhz_refclk(self):
        """Gen2 with 100 MHz refclk should find valid configuration."""
        pll = GTXChannelPLL(refclk_freq=100e6, linerate=5.0e9)

        # Should have valid configuration
        self.assertIsNotNone(pll.config)

        # VCO frequency should be in valid range
        vco_freq = pll.config['vco_freq']
        self.assertGreaterEqual(vco_freq, 1.6e9)
        self.assertLessEqual(vco_freq, 3.3e9)

        # Linerate should match
        self.assertAlmostEqual(pll.config['linerate'], 5.0e9, delta=1e6)

    def test_invalid_configuration_raises(self):
        """Invalid refclk/linerate should raise ValueError."""
        with self.assertRaises(ValueError):
            # 10 MHz refclk is too low to generate 2.5 GT/s
            pll = GTXChannelPLL(refclk_freq=10e6, linerate=2.5e9)


class TestGTXResetSequencer(unittest.TestCase):
    """Test GTX reset sequencer."""

    def test_instantiation(self):
        """Reset sequencer should instantiate with FSM."""
        sequencer = GTXResetSequencer(sys_clk_freq=125e6)

        # Should have FSM
        self.assertTrue(hasattr(sequencer, 'fsm'))

        # Should have all required signals
        self.assertIsInstance(sequencer.tx_pll_locked, Signal)
        self.assertIsInstance(sequencer.tx_ready, Signal)
        self.assertIsInstance(sequencer.rx_ready, Signal)


class TestS7GTXTransceiver(unittest.TestCase):
    """Test S7GTXTransceiver wrapper (skeleton)."""

    def test_instantiation_basic(self):
        """GTX transceiver should instantiate with basic structure."""
        # Note: This is a basic test of the skeleton structure
        # Full GTX primitive instantiation testing requires more setup

        # Create mock pads
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

        platform = MockPlatform()
        pads = MockPads()
        refclk_pads = MockRefclkPads()

        # Create GTX transceiver (skeleton)
        gtx = S7GTXTransceiver(
            platform=platform,
            pads=pads,
            refclk_pads=refclk_pads,
            refclk_freq=100e6,
            sys_clk_freq=125e6,
            data_width=16,
            gen=1
        )

        # Should have PIPE interface signals (from base class)
        self.assertIsInstance(gtx.tx_data, Signal)
        self.assertIsInstance(gtx.rx_data, Signal)
        self.assertIsInstance(gtx.tx_datak, Signal)
        self.assertIsInstance(gtx.rx_datak, Signal)

        # Should have submodules
        self.assertTrue(hasattr(gtx, 'pll'))
        self.assertTrue(hasattr(gtx, 'encoder'))
        self.assertTrue(hasattr(gtx, 'decoder'))
        self.assertTrue(hasattr(gtx, 'tx_datapath'))
        self.assertTrue(hasattr(gtx, 'rx_datapath'))
        self.assertTrue(hasattr(gtx, 'reset_seq'))

    def test_data_width_validation(self):
        """Invalid data widths should be rejected."""
        class MockPads:
            def __init__(self):
                self.tx_p = Signal()
                self.tx_n = Signal()
                self.rx_p = Signal()
                self.rx_n = Signal()

        class MockPlatform:
            pass

        with self.assertRaises((AssertionError, TypeError)):
            # 7-bit data width is invalid (will raise TypeError from Signal width)
            gtx = S7GTXTransceiver(
                platform=MockPlatform(),
                pads=MockPads(),
                refclk_pads=Signal(),
                refclk_freq=100e6,
                sys_clk_freq=125e6,
                data_width=7,  # Invalid
                gen=1
            )

    def test_gen_validation(self):
        """Invalid gen values should be rejected."""
        class MockPads:
            def __init__(self):
                self.tx_p = Signal()
                self.tx_n = Signal()
                self.rx_p = Signal()
                self.rx_n = Signal()

        class MockPlatform:
            pass

        with self.assertRaises(AssertionError):
            # Gen3 not yet supported (needs 128b/130b encoding)
            gtx = S7GTXTransceiver(
                platform=MockPlatform(),
                pads=MockPads(),
                refclk_pads=Signal(),
                refclk_freq=100e6,
                sys_clk_freq=125e6,
                data_width=16,
                gen=3  # Invalid (Gen3 needs different encoding)
            )


if __name__ == "__main__":
    unittest.main()
