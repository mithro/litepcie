# test/dll/test_ltssm_power_states.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for LTSSM power management states.

PCIe supports multiple power states for energy efficiency:
- L0: Full power (normal operation)
- L0s: Low power standby (fast entry/exit)
- L1: Deeper sleep (slower entry/exit)
- L2: Deepest sleep (requires reset to exit)

References:
- PCIe Base Spec 4.0, Section 5.2: Link Power Management
- PCIe Base Spec 4.0, Section 4.2.5.3.6: L0s
"""

import unittest

from migen import *
from litex.gen import run_simulation

from litepcie.dll.ltssm import LTSSM


class TestLTSSML0s(unittest.TestCase):
    """Test L0s power state."""

    def test_l0s_entry_from_l0(self):
        """
        L0s can be entered from L0 when idle.

        L0s is a low-latency power state for short idle periods.
        Entry is fast (no handshake required), exit requires FTS.

        Reference: PCIe Spec 4.0, Section 4.2.5.3.6.1: L0s Entry
        """
        def testbench(dut):
            # Train to L0
            yield dut.rx_elecidle.eq(0)
            yield
            yield
            yield

            yield dut.ts1_detected.eq(1)
            yield
            yield
            yield

            yield dut.ts2_detected.eq(1)
            yield
            yield
            yield
            yield

            # In L0
            state = yield dut.current_state
            self.assertEqual(state, dut.L0)

            # Request L0s entry (idle for power savings)
            yield dut.enter_l0s.eq(1)
            yield
            yield
            yield
            yield

            # Should enter L0s
            state = yield dut.current_state
            self.assertEqual(state, dut.L0s_IDLE)

        dut = LTSSM(gen=1, lanes=1, enable_l0s=True)
        run_simulation(dut, testbench(dut))

    def test_l0s_exit_with_fts(self):
        """
        L0s exit requires FTS (Fast Training Sequence).

        To exit L0s:
        1. Transmitter sends N_FTS training sequences
        2. Receiver locks to signal
        3. Return to L0

        Reference: PCIe Spec 4.0, Section 4.2.5.3.6.2: L0s Exit
        """
        def testbench(dut):
            # Train to L0
            yield dut.rx_elecidle.eq(0)
            yield
            yield
            yield

            yield dut.ts1_detected.eq(1)
            yield
            yield
            yield

            yield dut.ts2_detected.eq(1)
            yield
            yield
            yield
            yield

            # Enter L0s
            yield dut.enter_l0s.eq(1)
            yield
            yield
            yield
            yield

            # In L0s
            state = yield dut.current_state
            self.assertEqual(state, dut.L0s_IDLE)

            # Clear enter_l0s
            yield dut.enter_l0s.eq(0)
            yield

            # Trigger L0s exit (data to send)
            yield dut.exit_l0s.eq(1)
            yield
            yield
            yield
            yield

            # Should enter L0s.FTS state
            state = yield dut.current_state
            self.assertEqual(state, dut.L0s_FTS)

            # Should be sending FTS sequences
            send_fts = yield dut.send_fts
            self.assertEqual(send_fts, 1)

            # After N_FTS sequences, return to L0
            for _ in range(130):
                yield

            state = yield dut.current_state
            self.assertEqual(state, dut.L0)

        dut = LTSSM(gen=1, lanes=1, enable_l0s=True)
        run_simulation(dut, testbench(dut))

    def test_l0s_not_available_when_disabled(self):
        """
        L0s should not be available when disabled.

        L0s is optional - can be disabled if not needed.
        """
        def testbench(dut):
            # Should not have L0s capability
            l0s_capable = yield dut.l0s_capable
            self.assertEqual(l0s_capable, 0)

        dut = LTSSM(gen=1, lanes=1, enable_l0s=False)
        run_simulation(dut, testbench(dut))


if __name__ == "__main__":
    unittest.main()
