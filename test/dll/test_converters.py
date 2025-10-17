#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for layout converters between PHY, DLL, and PIPE interfaces.

These converters handle the different record layouts used by each layer:
- PHY layer: phy_layout (data, be)
- DLL layer: dll_layout (data)
- PIPE layer: phy_layout (dat, be)

References:
- litepcie/common.py: Layout definitions
"""

import unittest

from litex.gen import run_simulation
from migen import *

from litepcie.dll.converters import PHYToDLLConverter, DLLToPHYConverter


class TestPHYToDLLConverter(unittest.TestCase):
    """Test PHY to DLL layout conversion."""

    def test_phy_to_dll_converter_exists(self):
        """
        PHYToDLLConverter should convert phy_layout to dll_layout.

        phy_layout has (dat, be) fields
        dll_layout has (data) field

        Converter extracts data from phy_layout.
        """
        dut = PHYToDLLConverter(data_width=64)

        # Should have sink (phy_layout) and source (dll_layout)
        self.assertTrue(hasattr(dut, "sink"))
        self.assertTrue(hasattr(dut, "source"))

    def test_phy_to_dll_data_conversion(self):
        """
        PHY to DLL converter should pass data through correctly.
        """
        def testbench(dut):
            # Send PHY data
            yield dut.sink.valid.eq(1)
            yield dut.sink.dat.eq(0x1234567890ABCDEF)
            yield dut.source.ready.eq(1)
            yield

            # Check DLL data
            source_valid = yield dut.source.valid
            source_data = yield dut.source.data

            self.assertEqual(source_valid, 1)
            self.assertEqual(source_data, 0x1234567890ABCDEF)

        dut = PHYToDLLConverter(data_width=64)
        run_simulation(dut, testbench(dut))


class TestDLLToPHYConverter(unittest.TestCase):
    """Test DLL to PHY layout conversion."""

    def test_dll_to_phy_converter_exists(self):
        """
        DLLToPHYConverter should convert dll_layout to phy_layout.
        """
        dut = DLLToPHYConverter(data_width=64)

        # Should have sink (dll_layout) and source (phy_layout)
        self.assertTrue(hasattr(dut, "sink"))
        self.assertTrue(hasattr(dut, "source"))

    def test_dll_to_phy_data_conversion(self):
        """
        DLL to PHY converter should create phy_layout with proper be field.

        be (byte enable) should be all 1s for full data width.
        """
        def testbench(dut):
            # Send DLL data
            yield dut.sink.valid.eq(1)
            yield dut.sink.data.eq(0xFEDCBA9876543210)
            yield dut.source.ready.eq(1)
            yield

            # Check PHY data
            source_valid = yield dut.source.valid
            source_dat = yield dut.source.dat
            source_be = yield dut.source.be

            self.assertEqual(source_valid, 1)
            self.assertEqual(source_dat, 0xFEDCBA9876543210)
            self.assertEqual(source_be, 0xFF)  # All bytes enabled (64-bit = 8 bytes)

        dut = DLLToPHYConverter(data_width=64)
        run_simulation(dut, testbench(dut))


if __name__ == "__main__":
    unittest.main()
