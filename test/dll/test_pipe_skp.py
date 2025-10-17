# test/dll/test_pipe_skp.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for PIPE SKP ordered set handling.

SKP (Skip) ordered sets are used for clock compensation between
link partners with slightly different clock frequencies.

Reference: PCIe Base Spec 4.0, Section 4.2.7: Clock Compensation
"""

import os
import tempfile
import unittest

from litex.gen import run_simulation
from migen import *

from litepcie.dll.pipe import PIPERXDepacketizer, PIPETXPacketizer


class TestPIPETXSKPGeneration(unittest.TestCase):
    """Test SKP ordered set generation in TX path."""

    def test_tx_has_skp_generation_capability(self):
        """
        TX packetizer should have SKP generation capability.

        SKP Ordered Set Format (Gen1/Gen2):
        - Symbol 0: COM (K28.5, 0xBC) with K=1
        - Symbol 1: SKP (K28.0, 0x1C) with K=1
        - Symbol 2: SKP (K28.0, 0x1C) with K=1
        - Symbol 3: SKP (K28.0, 0x1C) with K=1

        Reference: PCIe Spec 4.0, Section 4.2.7.1
        """
        dut = PIPETXPacketizer(enable_skp=True)

        # Should have SKP generation control
        self.assertTrue(hasattr(dut, "skp_counter"))
        self.assertTrue(hasattr(dut, "skp_interval"))


class TestPIPETXSKPInsertion(unittest.TestCase):
    """Test SKP insertion behavior."""

    def test_tx_inserts_skp_at_interval(self):
        """
        TX should insert SKP ordered set every N symbols.

        SKP Ordered Set (4 symbols):
        1. COM (0xBC, K=1)
        2. SKP (0x1C, K=1)
        3. SKP (0x1C, K=1)
        4. SKP (0x1C, K=1)

        Test with small interval (16 symbols) for quick verification.
        """

        def testbench(dut):
            # Scan for SKP ordered set (COM followed by 3x SKP)
            found_skp = False

            for cycle in range(30):  # Scan first 30 cycles
                yield
                tx_data = yield dut.pipe_tx_data
                tx_datak = yield dut.pipe_tx_datak

                # Look for COM symbol (start of SKP ordered set)
                if tx_data == 0xBC and tx_datak == 1:
                    # Found COM, verify next 3 symbols are SKP
                    yield
                    skp1_data = yield dut.pipe_tx_data
                    skp1_datak = yield dut.pipe_tx_datak

                    yield
                    skp2_data = yield dut.pipe_tx_data
                    skp2_datak = yield dut.pipe_tx_datak

                    yield
                    skp3_data = yield dut.pipe_tx_data
                    skp3_datak = yield dut.pipe_tx_datak

                    # Verify all 3 are SKP (0x1C, K=1)
                    if (
                        skp1_data == 0x1C
                        and skp1_datak == 1
                        and skp2_data == 0x1C
                        and skp2_datak == 1
                        and skp3_data == 0x1C
                        and skp3_datak == 1
                    ):
                        found_skp = True
                        break

            self.assertTrue(found_skp, "Should find SKP ordered set within 30 cycles")

        # Use small interval for testing
        dut = PIPETXPacketizer(enable_skp=True, skp_interval=16)
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_skp_insertion.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


class TestPIPERXSKPDetection(unittest.TestCase):
    """Test SKP detection and handling in RX path."""

    def test_rx_detects_and_skips_skp_ordered_set(self):
        """
        RX should detect SKP ordered set and skip it (not output to DLL).

        SKP is transparent to upper layers - inserted/removed by Physical Layer.

        Reference: PCIe Spec 4.0, Section 4.2.7.2
        """

        def testbench(dut):
            # Send SKP ordered set: COM + 3xSKP
            yield dut.pipe_rx_data.eq(0xBC)  # COM (K28.5)
            yield dut.pipe_rx_datak.eq(1)
            yield

            # Send 3x SKP
            for _ in range(3):
                yield dut.pipe_rx_data.eq(0x1C)  # SKP (K28.0)
                yield dut.pipe_rx_datak.eq(1)
                yield

            # After SKP, send a TLP packet
            # START symbol (STP)
            yield dut.pipe_rx_data.eq(0xFB)  # STP (K27.7)
            yield dut.pipe_rx_datak.eq(1)
            yield

            # Send 8 data bytes
            data_bytes = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x11, 0x22]
            for byte_val in data_bytes:
                yield dut.pipe_rx_data.eq(byte_val)
                yield dut.pipe_rx_datak.eq(0)
                yield

            # END symbol
            yield dut.pipe_rx_data.eq(0xFD)  # END (K29.7)
            yield dut.pipe_rx_datak.eq(1)
            yield

            # Check packet output
            source_valid = yield dut.source.valid
            self.assertEqual(source_valid, 1, "Should have packet output after SKP")

        dut = PIPERXDepacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_rx_skp.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
