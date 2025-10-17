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


class TestLTSSML1(unittest.TestCase):
    """Test L1 power state."""

    def test_l1_entry_from_l0(self):
        """
        L1 can be entered from L0 via ASPM (Active State Power Management).

        L1 is deeper sleep than L0s, requires handshake for entry,
        longer recovery time but better power savings.

        Reference: PCIe Spec 4.0, Section 5.4.1: L1 Entry
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

            # Request L1 entry (longer idle period)
            yield dut.enter_l1.eq(1)
            yield
            yield
            yield
            yield

            # Should enter L1
            state = yield dut.current_state
            self.assertEqual(state, dut.L1)

            # TX should be in electrical idle
            tx_idle = yield dut.tx_elecidle
            self.assertEqual(tx_idle, 1)

        dut = LTSSM(gen=1, lanes=1, enable_l1=True)
        run_simulation(dut, testbench(dut))

    def test_l1_exit_to_recovery(self):
        """
        L1 exit goes through RECOVERY for retraining.

        Unlike L0s (fast exit via FTS), L1 requires full
        link retraining through RECOVERY state.

        Reference: PCIe Spec 4.0, Section 5.4.2: L1 Exit
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

            # Enter L1
            yield dut.enter_l1.eq(1)
            yield
            yield
            yield
            yield

            # In L1
            state = yield dut.current_state
            self.assertEqual(state, dut.L1)

            # Clear enter_l1
            yield dut.enter_l1.eq(0)
            yield

            # Request L1 exit (data to send)
            yield dut.exit_l1.eq(1)
            yield dut.rx_elecidle.eq(0)  # Partner exits too
            yield
            yield
            yield

            # Should enter RECOVERY for retraining
            state = yield dut.current_state
            self.assertEqual(state, dut.RECOVERY)

        dut = LTSSM(gen=1, lanes=1, enable_l1=True)
        run_simulation(dut, testbench(dut))


class TestLTSSML2(unittest.TestCase):
    """Test L2 power state."""

    def test_l2_entry_from_l1(self):
        """
        L2 can be entered from L1 for deepest power savings.

        L2 is the deepest sleep state, requires reset to exit.
        Used when system enters sleep/hibernate.

        Reference: PCIe Spec 4.0, Section 5.5: L2 State
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

            # Enter L1
            yield dut.enter_l1.eq(1)
            yield
            yield
            yield
            yield

            # In L1
            state = yield dut.current_state
            self.assertEqual(state, dut.L1)

            # Clear enter_l1
            yield dut.enter_l1.eq(0)
            yield

            # Request L2 entry (system sleep)
            yield dut.enter_l2.eq(1)
            yield
            yield
            yield

            # Should enter L2
            state = yield dut.current_state
            self.assertEqual(state, dut.L2)

        dut = LTSSM(gen=1, lanes=1, enable_l1=True, enable_l2=True)
        run_simulation(dut, testbench(dut))

    def test_l2_requires_detect_to_exit(self):
        """
        L2 exit requires returning to DETECT (link reset).

        L2 is non-recoverable - exiting requires full
        re-initialization from DETECT state.

        Reference: PCIe Spec 4.0, Section 5.5.2: L2 Exit
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

            # Enter L1 then L2
            yield dut.enter_l1.eq(1)
            yield
            yield
            yield
            yield

            yield dut.enter_l1.eq(0)
            yield dut.enter_l2.eq(1)
            yield
            yield
            yield
            yield

            # In L2
            state = yield dut.current_state
            self.assertEqual(state, dut.L2)

            # L2 exit requires full reset
            yield dut.exit_l2.eq(1)
            yield
            yield
            yield

            # Should return to DETECT
            state = yield dut.current_state
            self.assertEqual(state, dut.DETECT)

        dut = LTSSM(gen=1, lanes=1, enable_l1=True, enable_l2=True)
        run_simulation(dut, testbench(dut))


if __name__ == "__main__":
    unittest.main()
