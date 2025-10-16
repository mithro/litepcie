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

from litepcie.dll.pipe import PIPETXPacketizer


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


if __name__ == "__main__":
    unittest.main()
