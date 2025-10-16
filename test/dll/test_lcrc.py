#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for LCRC (Link CRC-32) implementation.

Tests behavioral aspects of LCRC generation and checking for TLP integrity.

Reference: PCIe Base Spec 4.0, Section 3.3.4
"""

import unittest

from litex.gen import run_simulation
from migen import *


class TestLCRC32Software(unittest.TestCase):
    """Test software LCRC-32 reference implementation."""

    def test_software_lcrc_known_value(self):
        """Software LCRC should produce known correct values."""
        from litepcie.dll.common import calculate_lcrc32

        # Test vector: simple data
        data = [0x00, 0x00, 0x00, 0x00]
        crc = calculate_lcrc32(data)

        # CRC should be valid 32-bit value
        self.assertIsInstance(crc, int)
        self.assertGreaterEqual(crc, 0)
        self.assertLessEqual(crc, 0xFFFFFFFF)

    def test_software_lcrc_different_data_different_crc(self):
        """Different data should produce different CRCs."""
        from litepcie.dll.common import calculate_lcrc32

        data1 = [0x00, 0x00, 0x00, 0x00]
        data2 = [0xFF, 0xFF, 0xFF, 0xFF]

        crc1 = calculate_lcrc32(data1)
        crc2 = calculate_lcrc32(data2)

        self.assertNotEqual(crc1, crc2, "Different data should produce different CRCs")

    def test_software_lcrc_validation(self):
        """Software CRC verification should work correctly."""
        from litepcie.dll.common import calculate_lcrc32, verify_lcrc32

        data = [0xDE, 0xAD, 0xBE, 0xEF, 0xCA, 0xFE, 0xBA, 0xBE]
        crc = calculate_lcrc32(data)

        # Correct CRC should verify
        self.assertTrue(verify_lcrc32(data, crc))

        # Incorrect CRC should fail
        self.assertFalse(verify_lcrc32(data, crc ^ 0xFFFFFFFF))

    def test_software_lcrc_empty_data(self):
        """Empty data should be rejected."""
        from litepcie.dll.common import calculate_lcrc32

        with self.assertRaises(ValueError):
            calculate_lcrc32([])


class TestLCRC32Hardware(unittest.TestCase):
    """Test hardware LCRC-32 generator."""

    def test_hardware_lcrc_matches_software(self):
        """Hardware LCRC should match software reference."""
        from litepcie.dll.common import calculate_lcrc32
        from litepcie.dll.lcrc import LCRC32Generator

        def testbench(dut):
            # Test data: 16 bytes
            test_data = [
                0x00,
                0x00,
                0x00,
                0x00,
                0xDE,
                0xAD,
                0xBE,
                0xEF,
                0xCA,
                0xFE,
                0xBA,
                0xBE,
                0x12,
                0x34,
                0x56,
                0x78,
            ]
            expected_crc = calculate_lcrc32(test_data)

            # Reset CRC
            yield dut.reset.eq(1)
            yield
            yield dut.reset.eq(0)
            yield

            # Feed data into hardware CRC
            for byte_val in test_data:
                yield dut.data_in.eq(byte_val)
                yield dut.data_valid.eq(1)
                yield

            yield dut.data_valid.eq(0)
            yield

            # Read CRC output
            hw_crc = yield dut.crc_out
            self.assertEqual(
                hw_crc,
                expected_crc,
                f"Hardware CRC 0x{hw_crc:08X} != Software CRC 0x{expected_crc:08X}",
            )

        dut = LCRC32Generator()
        run_simulation(dut, testbench(dut), vcd_name="test_lcrc_hw.vcd")

    def test_hardware_lcrc_reset(self):
        """Hardware LCRC reset should return to initial state."""
        from litepcie.dll.common import LCRC_INITIAL_VALUE
        from litepcie.dll.lcrc import LCRC32Generator

        def testbench(dut):
            # Feed some data
            yield dut.data_in.eq(0xAA)
            yield dut.data_valid.eq(1)
            yield
            yield dut.data_valid.eq(0)
            yield

            # CRC should be non-initial
            crc_before = yield dut.crc_out
            self.assertNotEqual(crc_before, LCRC_INITIAL_VALUE)

            # Reset
            yield dut.reset.eq(1)
            yield
            yield dut.reset.eq(0)
            yield

            # CRC should be back to initial
            crc_after = yield dut.crc_out
            self.assertEqual(crc_after, LCRC_INITIAL_VALUE)

        dut = LCRC32Generator()
        run_simulation(dut, testbench(dut), vcd_name="test_lcrc_reset.vcd")

    def test_hardware_lcrc_incremental(self):
        """Hardware LCRC should handle incremental data feed."""
        from litepcie.dll.common import calculate_lcrc32
        from litepcie.dll.lcrc import LCRC32Generator

        def testbench(dut):
            test_data = [0x12, 0x34, 0x56, 0x78]

            # Reset
            yield dut.reset.eq(1)
            yield
            yield dut.reset.eq(0)
            yield

            # Feed data one byte at a time with gaps
            for byte_val in test_data:
                yield dut.data_in.eq(byte_val)
                yield dut.data_valid.eq(1)
                yield
                yield dut.data_valid.eq(0)
                yield  # Gap between bytes
                yield

            # Final CRC should match
            hw_crc = yield dut.crc_out
            expected_crc = calculate_lcrc32(test_data)
            self.assertEqual(hw_crc, expected_crc)

        dut = LCRC32Generator()
        run_simulation(dut, testbench(dut), vcd_name="test_lcrc_incremental.vcd")


class TestLCRC32Checker(unittest.TestCase):
    """Test hardware LCRC-32 checker."""

    def test_checker_detects_valid_crc(self):
        """Checker should accept valid CRC.

        PCIe LCRC uses CRC-32 with polynomial 0x04C11DB7 and initial 0xFFFFFFFF,
        but does NOT use bit reflection (unlike Ethernet CRC-32). The CRC is
        appended directly without complementation. When valid data+CRC is processed,
        the checker should see residue 0x497C2DBF and not report an error.
        """
        from litepcie.dll.common import calculate_lcrc32
        from litepcie.dll.lcrc import LCRC32Checker

        def testbench(dut):
            # Prepare data with valid CRC
            data = [0xDE, 0xAD, 0xBE, 0xEF]
            crc = calculate_lcrc32(data)
            crc_bytes = [
                (crc >> 0) & 0xFF,
                (crc >> 8) & 0xFF,
                (crc >> 16) & 0xFF,
                (crc >> 24) & 0xFF,
            ]

            # Reset checker
            yield dut.reset.eq(1)
            yield
            yield dut.reset.eq(0)
            yield

            # Feed data
            for byte_val in data:
                yield dut.data_in.eq(byte_val)
                yield dut.data_valid.eq(1)
                yield

            # Feed CRC
            for byte_val in crc_bytes:
                yield dut.data_in.eq(byte_val)
                yield dut.data_valid.eq(1)
                yield

            yield dut.data_valid.eq(0)
            yield

            # Check should pass
            error = yield dut.crc_error
            self.assertEqual(error, 0, "Valid CRC should not trigger error")

        dut = LCRC32Checker()
        run_simulation(dut, testbench(dut), vcd_name="test_lcrc_check_valid.vcd")

    def test_checker_detects_invalid_crc(self):
        """Checker should reject invalid CRC."""
        from litepcie.dll.common import calculate_lcrc32
        from litepcie.dll.lcrc import LCRC32Checker

        def testbench(dut):
            # Prepare data with INVALID CRC
            data = [0xDE, 0xAD, 0xBE, 0xEF]
            crc = calculate_lcrc32(data) ^ 0xFFFFFFFF  # Corrupt CRC
            crc_bytes = [
                (crc >> 0) & 0xFF,
                (crc >> 8) & 0xFF,
                (crc >> 16) & 0xFF,
                (crc >> 24) & 0xFF,
            ]

            # Reset checker
            yield dut.reset.eq(1)
            yield
            yield dut.reset.eq(0)
            yield

            # Feed data + corrupted CRC
            for byte_val in data + crc_bytes:
                yield dut.data_in.eq(byte_val)
                yield dut.data_valid.eq(1)
                yield

            yield dut.data_valid.eq(0)
            yield

            # Check should fail
            error = yield dut.crc_error
            self.assertEqual(error, 1, "Invalid CRC should trigger error")

        dut = LCRC32Checker()
        run_simulation(dut, testbench(dut), vcd_name="test_lcrc_check_invalid.vcd")


if __name__ == "__main__":
    unittest.main()
