#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for external PIPE PHY wrapper.

Tests that the external PHY wrapper provides required PHY interface
for drop-in replacement of vendor IP.

Reference: docs/integration-strategy.md
"""

import unittest

from migen import *

from litepcie.phy.pipe_external_phy import PIPEExternalPHY


class TestPIPEExternalPHYStructure(unittest.TestCase):
    """Test external PIPE PHY wrapper structure."""

    def test_external_phy_has_required_endpoints(self):
        """
        External PHY must provide same endpoints as vendor IP.

        Required endpoints for drop-in replacement:
        - sink: TX data from TLP layer
        - source: RX data to TLP layer
        - msi: MSI interrupt endpoint

        Reference: docs/integration-strategy.md
        """
        # Create mock platform (we'll use None for structure test)
        dut = PIPEExternalPHY(
            platform=None,
            pads=None,
            data_width=64,
            cd="sys",
            bar0_size=0x100000,
        )

        # Check required endpoints exist
        self.assertTrue(hasattr(dut, "sink"))
        self.assertTrue(hasattr(dut, "source"))
        self.assertTrue(hasattr(dut, "msi"))

    def test_external_phy_has_required_attributes(self):
        """External PHY must expose data_width and bar0_mask attributes."""
        dut = PIPEExternalPHY(
            platform=None,
            pads=None,
            data_width=128,
            cd="sys",
            bar0_size=0x200000,
        )

        self.assertTrue(hasattr(dut, "data_width"))
        self.assertEqual(dut.data_width, 128)
        self.assertTrue(hasattr(dut, "bar0_mask"))


class TestPIPEExternalPHYParameterValidation(unittest.TestCase):
    """Test external PIPE PHY parameter validation."""

    def test_invalid_data_width_raises_error(self):
        """
        External PHY should reject invalid data widths.

        Valid widths: 64, 128, 256, 512 bits
        These match standard PCIe TLP datapath widths.

        Reference: PCIe Base Spec 4.0, Section 2.2.7: TLP Data Width
        """
        # Test various invalid data widths
        invalid_widths = [8, 16, 32, 96, 192, 1024, 0, -64]

        for width in invalid_widths:
            with self.assertRaises(ValueError) as context:
                PIPEExternalPHY(
                    platform=None,
                    pads=None,
                    data_width=width,
                    cd="sys",
                    bar0_size=0x10000,
                )

            self.assertIn("Invalid data_width", str(context.exception))

    def test_valid_data_widths_accepted(self):
        """Valid data widths should be accepted."""
        valid_widths = [64, 128, 256, 512]

        for width in valid_widths:
            dut = PIPEExternalPHY(
                platform=None,
                pads=None,
                data_width=width,
                cd="sys",
                bar0_size=0x10000,
            )
            self.assertEqual(dut.data_width, width)


if __name__ == "__main__":
    unittest.main()
