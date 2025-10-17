# test/dll/test_ltssm_equalization.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for LTSSM link equalization.

Link equalization adjusts transmitter and receiver settings
to optimize signal quality, especially important for Gen2+.

References:
- PCIe Base Spec 4.0, Section 4.2.5.3.7: Recovery
- PCIe Base Spec 4.0, Section 4.2.3: Link Equalization
"""

import unittest

from migen import *
from litex.gen import run_simulation

from litepcie.dll.ltssm import LTSSM


class TestLTSSMEqualization(unittest.TestCase):
    """Test link equalization."""

    def test_equalization_enabled_for_gen2(self):
        """
        Gen2 links should support equalization.

        Equalization is optional for Gen1 but recommended for
        Gen2 to improve signal integrity at higher speeds.
        """
        def testbench(dut):
            # Gen2 device should have equalization capability
            eq_capable = yield dut.eq_capable
            self.assertEqual(eq_capable, 1)

        dut = LTSSM(gen=2, lanes=1, enable_equalization=True)
        run_simulation(dut, testbench(dut))

    def test_recovery_equalization_phases(self):
        """
        RECOVERY.Equalization has 4 phases (Phase 0-3).

        Equalization phases:
        - Phase 0: Transmitter preset
        - Phase 1: Receiver coefficient request
        - Phase 2: Transmitter coefficient update
        - Phase 3: Link evaluation

        Reference: PCIe Spec 4.0, Section 4.2.3
        """
        def testbench(dut):
            # Train to L0 first
            yield dut.rx_elecidle.eq(0)
            yield
            yield
            yield

            # Should be in POLLING
            yield dut.ts1_detected.eq(1)
            yield
            yield
            yield

            # Should be in CONFIGURATION
            yield dut.ts2_detected.eq(1)
            yield
            yield
            yield

            # Should be in L0
            state = yield dut.current_state
            self.assertEqual(state, dut.L0)

            # Trigger link error to enter RECOVERY, then equalization
            yield dut.force_equalization.eq(1)
            yield dut.rx_elecidle.eq(1)  # Link error
            yield
            yield
            yield

            # Should be in RECOVERY
            state = yield dut.current_state
            self.assertEqual(state, dut.RECOVERY)

            # Exit electrical idle so RECOVERY can check for equalization
            yield dut.rx_elecidle.eq(0)
            yield
            yield

            # Should enter RECOVERY.Equalization.Phase0
            state = yield dut.current_state
            self.assertEqual(state, dut.RECOVERY_EQ_PHASE0)

            # Progress through all phases (need >100 cycles per phase)
            for _ in range(450):
                yield

            # Should complete and return to L0
            state = yield dut.current_state
            self.assertEqual(state, dut.L0)

        dut = LTSSM(gen=2, lanes=1, enable_equalization=True)
        run_simulation(dut, testbench(dut))

    def test_equalization_bypass_for_gen1(self):
        """
        Gen1 links should skip equalization.

        Equalization not needed at 2.5 GT/s, so Gen1 links
        should bypass equalization states.
        """
        def testbench(dut):
            # Gen1 should not have equalization
            eq_capable = yield dut.eq_capable
            self.assertEqual(eq_capable, 0)

        dut = LTSSM(gen=1, lanes=1, enable_equalization=False)
        run_simulation(dut, testbench(dut))


if __name__ == "__main__":
    unittest.main()
