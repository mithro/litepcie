#!/usr/bin/env python3

"""
Tests for Transceiver Base Classes

Validates the common base abstraction for all transceiver wrappers.
"""

import unittest
from migen import *
from litepcie.phy.transceiver_base.transceiver import (
    PIPETransceiver,
    TransceiverTXDatapath,
    TransceiverRXDatapath,
    TransceiverResetSequencer,
)


class TestPIPETransceiver(unittest.TestCase):
    """Test PIPETransceiver base class."""

    def test_instantiation(self):
        """Base transceiver should instantiate with correct signals."""
        transceiver = PIPETransceiver(data_width=16, gen=1)

        # Check data width
        self.assertEqual(transceiver.data_width, 16)
        self.assertEqual(transceiver.gen, 1)

        # Check PIPE TX signals
        self.assertIsInstance(transceiver.tx_data, Signal)
        self.assertEqual(len(transceiver.tx_data), 16)
        self.assertIsInstance(transceiver.tx_datak, Signal)
        self.assertEqual(len(transceiver.tx_datak), 2)  # 16 bits / 8 = 2 bytes
        self.assertIsInstance(transceiver.tx_elecidle, Signal)

        # Check PIPE RX signals
        self.assertIsInstance(transceiver.rx_data, Signal)
        self.assertEqual(len(transceiver.rx_data), 16)
        self.assertIsInstance(transceiver.rx_datak, Signal)
        self.assertEqual(len(transceiver.rx_datak), 2)
        self.assertIsInstance(transceiver.rx_elecidle, Signal)
        self.assertIsInstance(transceiver.rx_valid, Signal)

        # Check clock signals
        self.assertIsInstance(transceiver.tx_clk, Signal)
        self.assertIsInstance(transceiver.rx_clk, Signal)

        # Check control signals
        self.assertIsInstance(transceiver.reset, Signal)
        self.assertIsInstance(transceiver.tx_ready, Signal)
        self.assertIsInstance(transceiver.rx_ready, Signal)

    def test_line_rate_gen1(self):
        """Gen1 should return 2.5 GT/s line rate."""
        transceiver = PIPETransceiver(data_width=16, gen=1)
        self.assertEqual(transceiver.get_line_rate(), 2.5e9)

    def test_line_rate_gen2(self):
        """Gen2 should return 5.0 GT/s line rate."""
        transceiver = PIPETransceiver(data_width=16, gen=2)
        self.assertEqual(transceiver.get_line_rate(), 5.0e9)

    def test_line_rate_gen3(self):
        """Gen3 should return 8.0 GT/s line rate."""
        transceiver = PIPETransceiver(data_width=16, gen=3)
        self.assertEqual(transceiver.get_line_rate(), 8.0e9)

    def test_word_clk_freq_gen1(self):
        """Gen1 word clock should be 250 MHz (2.5 GT/s / 10)."""
        transceiver = PIPETransceiver(data_width=16, gen=1)
        self.assertEqual(transceiver.get_word_clk_freq(), 250e6)

    def test_word_clk_freq_gen2(self):
        """Gen2 word clock should be 500 MHz (5.0 GT/s / 10)."""
        transceiver = PIPETransceiver(data_width=16, gen=2)
        self.assertEqual(transceiver.get_word_clk_freq(), 500e6)

    def test_data_width_8(self):
        """8-bit data width should have 1 K-char bit."""
        transceiver = PIPETransceiver(data_width=8, gen=1)
        self.assertEqual(len(transceiver.tx_datak), 1)
        self.assertEqual(len(transceiver.rx_datak), 1)

    def test_data_width_32(self):
        """32-bit data width should have 4 K-char bits."""
        transceiver = PIPETransceiver(data_width=32, gen=1)
        self.assertEqual(len(transceiver.tx_datak), 4)
        self.assertEqual(len(transceiver.rx_datak), 4)


class TestTransceiverTXDatapath(unittest.TestCase):
    """Test TX datapath module."""

    def test_instantiation(self):
        """TX datapath should instantiate with correct endpoints."""
        datapath = TransceiverTXDatapath(data_width=16)

        # Check sink (16-bit from sys_clk)
        self.assertIsNotNone(datapath.sink)
        self.assertTrue(hasattr(datapath.sink, 'data'))
        self.assertTrue(hasattr(datapath.sink, 'ctrl'))

        # Check source (16-bit to tx_clk)
        self.assertIsNotNone(datapath.source)
        self.assertTrue(hasattr(datapath.source, 'data'))
        self.assertTrue(hasattr(datapath.source, 'ctrl'))

        # Check has CDC submodule (no converter - 8b/10b handles width)
        self.assertTrue(hasattr(datapath, 'cdc'))


class TestTransceiverRXDatapath(unittest.TestCase):
    """Test RX datapath module."""

    def test_instantiation(self):
        """RX datapath should instantiate with correct endpoints."""
        datapath = TransceiverRXDatapath(data_width=16)

        # Check sink (16-bit from rx_clk)
        self.assertIsNotNone(datapath.sink)
        self.assertTrue(hasattr(datapath.sink, 'data'))
        self.assertTrue(hasattr(datapath.sink, 'ctrl'))

        # Check source (16-bit to sys_clk)
        self.assertIsNotNone(datapath.source)
        self.assertTrue(hasattr(datapath.source, 'data'))
        self.assertTrue(hasattr(datapath.source, 'ctrl'))

        # Check has CDC submodule (no converter - 8b/10b handles width)
        self.assertTrue(hasattr(datapath, 'cdc'))


class TestTransceiverResetSequencer(unittest.TestCase):
    """Test reset sequencer base class."""

    def test_instantiation(self):
        """Reset sequencer should have all required signals."""
        sequencer = TransceiverResetSequencer()

        # Status inputs
        self.assertIsInstance(sequencer.tx_pll_locked, Signal)
        self.assertIsInstance(sequencer.rx_has_signal, Signal)
        self.assertIsInstance(sequencer.rx_cdr_locked, Signal)

        # Reset outputs (should default to 1 = asserted)
        self.assertIsInstance(sequencer.tx_pll_reset, Signal)
        self.assertIsInstance(sequencer.tx_pcs_reset, Signal)
        self.assertIsInstance(sequencer.rx_cdr_reset, Signal)
        self.assertIsInstance(sequencer.rx_pcs_reset, Signal)

        # Status outputs
        self.assertIsInstance(sequencer.tx_ready, Signal)
        self.assertIsInstance(sequencer.rx_ready, Signal)


if __name__ == "__main__":
    unittest.main()
