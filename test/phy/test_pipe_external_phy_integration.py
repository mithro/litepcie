#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for PIPEExternalPHY DLL-PIPE integration.

Validates that DLL TX/RX properly connects to PIPE interface
through layout converters.

References:
- docs/integration-strategy.md: PHY integration requirements
"""

import unittest

from migen import *

from litepcie.phy.pipe_external_phy import PIPEExternalPHY


class TestPIPEExternalPHYIntegration(unittest.TestCase):
    """Test DLL-PIPE integration in external PHY wrapper."""

    def test_phy_has_dll_components(self):
        """
        PIPEExternalPHY should have DLL TX/RX components.
        """
        dut = PIPEExternalPHY(platform=None, pads=None, data_width=64)

        # Should have DLL components
        self.assertTrue(hasattr(dut, "dll_tx"))
        self.assertTrue(hasattr(dut, "dll_rx"))

    def test_phy_has_pipe_interface(self):
        """
        PIPEExternalPHY should have PIPE interface.
        """
        dut = PIPEExternalPHY(platform=None, pads=None, data_width=64)

        # Should have PIPE interface
        self.assertTrue(hasattr(dut, "pipe"))

    def test_phy_has_layout_converters(self):
        """
        PIPEExternalPHY should have layout converters for DLL-PIPE.
        """
        dut = PIPEExternalPHY(platform=None, pads=None, data_width=64)

        # Should have converters
        self.assertTrue(hasattr(dut, "tx_phy_to_dll_conv"))
        self.assertTrue(hasattr(dut, "tx_dll_to_phy_conv"))
        self.assertTrue(hasattr(dut, "rx_phy_to_dll_conv"))
        self.assertTrue(hasattr(dut, "rx_dll_to_phy_conv"))


if __name__ == "__main__":
    unittest.main()
