# test/dll/test_ltssm_substates.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for LTSSM detailed substates.

Full PCIe spec defines detailed substates for major states.
This improves compliance and debugging visibility.

References:
- PCIe Base Spec 4.0, Section 4.2.5.3.2: Polling
- PCIe Base Spec 4.0, Section 4.2.5.3.7: Recovery
"""

import unittest

from migen import *
from litex.gen import run_simulation

from litepcie.dll.ltssm import LTSSM


class TestLTSSMPollingSubstates(unittest.TestCase):
    """Test POLLING detailed substates."""

    def test_polling_active_sends_ts1(self):
        """
        POLLING.Active sends TS1 continuously.

        POLLING.Active is first substate where device sends
        TS1 and waits for partner TS1.

        Reference: PCIe Spec 4.0, Section 4.2.5.3.2.1
        """
        def testbench(dut):
            # Enter POLLING from DETECT
            yield dut.rx_elecidle.eq(0)
            yield
            yield
            yield

            # Should be in POLLING.Active
            state = yield dut.current_state
            self.assertEqual(state, dut.POLLING_ACTIVE)

            # Sending TS1
            send_ts1 = yield dut.send_ts1
            self.assertEqual(send_ts1, 1)

        dut = LTSSM(gen=1, lanes=1, detailed_substates=True)
        run_simulation(dut, testbench(dut))

    def test_polling_configuration_after_ts1_received(self):
        """
        POLLING.Configuration follows after receiving TS1.

        After receiving 8 consecutive TS1, transition to
        POLLING.Configuration and send TS2.

        Reference: PCIe Spec 4.0, Section 4.2.5.3.2.2
        """
        def testbench(dut):
            # Get to POLLING.Active
            yield dut.rx_elecidle.eq(0)
            yield
            yield
            yield

            # Receive TS1 from partner
            yield dut.ts1_detected.eq(1)

            # After detecting TS1, should eventually enter Configuration
            for _ in range(12):
                yield

            state = yield dut.current_state
            self.assertEqual(state, dut.POLLING_CONFIGURATION)

        dut = LTSSM(gen=1, lanes=1, detailed_substates=True)
        run_simulation(dut, testbench(dut))

    def test_polling_compliance_for_testing(self):
        """
        POLLING.Compliance is for electrical testing.

        If compliance bit set in TS1, enter Compliance
        mode for signal integrity testing.

        Reference: PCIe Spec 4.0, Section 4.2.5.3.2.3
        """
        def testbench(dut):
            # Get to POLLING
            yield dut.rx_elecidle.eq(0)
            yield
            yield
            yield

            # Receive TS1 with compliance request
            yield dut.rx_compliance_request.eq(1)
            yield
            yield
            yield

            # Should enter POLLING.Compliance
            state = yield dut.current_state
            self.assertEqual(state, dut.POLLING_COMPLIANCE)

        dut = LTSSM(gen=1, lanes=1, detailed_substates=True)
        run_simulation(dut, testbench(dut))


class TestLTSSMRecoverySubstates(unittest.TestCase):
    """Test RECOVERY detailed substates."""

    def test_recovery_rcvrlock_establishes_lock(self):
        """
        RECOVERY.RcvrLock establishes receiver bit/symbol lock.

        First RECOVERY substate sends TS1 to help partner
        re-establish symbol lock after error.

        Reference: PCIe Spec 4.0, Section 4.2.5.3.7.1
        """
        def testbench(dut):
            # Train to L0 first
            yield dut.rx_elecidle.eq(0)
            yield
            yield
            yield

            yield dut.ts1_detected.eq(1)
            for _ in range(12):
                yield

            yield dut.ts2_detected.eq(1)
            for _ in range(10):
                yield

            # In L0, trigger recovery via electrical idle
            yield dut.rx_elecidle.eq(1)
            yield
            yield
            yield

            # Should enter RECOVERY.RcvrLock
            state = yield dut.current_state
            self.assertEqual(state, dut.RECOVERY_RCVRLOCK)

            # Sending TS1
            send_ts1 = yield dut.send_ts1
            self.assertEqual(send_ts1, 1)

        dut = LTSSM(gen=1, lanes=1, detailed_substates=True)
        run_simulation(dut, testbench(dut))

    def test_recovery_rcvrcfg_after_lock(self):
        """
        RECOVERY.RcvrCfg exchanges configuration.

        After bit lock, exchange TS1 to verify configuration
        still matches between partners.

        Reference: PCIe Spec 4.0, Section 4.2.5.3.7.2
        """
        def testbench(dut):
            # Train to L0 first
            yield dut.rx_elecidle.eq(0)
            yield
            yield
            yield

            yield dut.ts1_detected.eq(1)
            for _ in range(12):
                yield

            yield dut.ts2_detected.eq(1)
            for _ in range(10):
                yield

            # In L0, trigger recovery
            yield dut.rx_elecidle.eq(1)
            yield
            yield
            yield

            # Should be in RcvrLock, now exit idle and detect TS1
            yield dut.rx_elecidle.eq(0)
            yield dut.ts1_detected.eq(1)
            yield
            yield
            yield

            # Should transition to RcvrCfg
            state = yield dut.current_state
            self.assertEqual(state, dut.RECOVERY_RCVRCFG)

        dut = LTSSM(gen=1, lanes=1, detailed_substates=True)
        run_simulation(dut, testbench(dut))

    def test_recovery_idle_before_l0(self):
        """
        RECOVERY.Idle is final check before returning to L0.

        Send configured TS2, verify partner also sends TS2,
        then return to L0.

        Reference: PCIe Spec 4.0, Section 4.2.5.3.7.3
        """
        def testbench(dut):
            # Train to L0 first
            yield dut.rx_elecidle.eq(0)
            yield
            yield
            yield

            yield dut.ts1_detected.eq(1)
            for _ in range(12):
                yield

            yield dut.ts2_detected.eq(1)
            for _ in range(10):
                yield

            # In L0, trigger recovery
            yield dut.ts2_detected.eq(0)  # Clear ts2 before recovery
            yield dut.rx_elecidle.eq(1)
            yield
            yield
            yield

            # Get through RcvrLock and RcvrCfg
            yield dut.rx_elecidle.eq(0)
            yield dut.ts1_detected.eq(1)
            for _ in range(5):
                yield

            # Should be in RECOVERY.Idle
            state = yield dut.current_state
            self.assertEqual(state, dut.RECOVERY_IDLE)

            # Sending TS2
            send_ts2 = yield dut.send_ts2
            self.assertEqual(send_ts2, 1)

        dut = LTSSM(gen=1, lanes=1, detailed_substates=True)
        run_simulation(dut, testbench(dut))


if __name__ == "__main__":
    unittest.main()
