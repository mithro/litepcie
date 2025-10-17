# test/dll/test_ltssm.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for PCIe LTSSM (Link Training and Status State Machine).

The LTSSM manages link initialization, training, and status through
defined states according to the PCIe specification.

References:
- PCIe Base Spec 4.0, Section 4.2.5: LTSSM
"""

import unittest

from litex.gen import run_simulation
from migen import *

from litepcie.dll.ltssm import LTSSM


class TestLTSSMStructure(unittest.TestCase):
    """Test LTSSM state machine structure."""

    def test_ltssm_has_required_states(self):
        """
        LTSSM should define standard PCIe training states.

        Required states for Gen1 operation:
        - DETECT: Receiver detection
        - POLLING: TS1/TS2 exchange for speed/lane negotiation
        - CONFIGURATION: Configure link parameters
        - L0: Normal operation (data transfer)
        - RECOVERY: Error handling and re-training

        Reference: PCIe Spec 4.0, Section 4.2.5.2
        """
        dut = LTSSM()

        # Should have state constants defined
        self.assertTrue(hasattr(dut, "DETECT"))
        self.assertTrue(hasattr(dut, "POLLING"))
        self.assertTrue(hasattr(dut, "CONFIGURATION"))
        self.assertTrue(hasattr(dut, "L0"))
        self.assertTrue(hasattr(dut, "RECOVERY"))

    def test_ltssm_has_status_outputs(self):
        """
        LTSSM should provide link status signals.
        """
        dut = LTSSM()

        # Status outputs
        self.assertTrue(hasattr(dut, "link_up"))
        self.assertTrue(hasattr(dut, "current_state"))
        self.assertTrue(hasattr(dut, "link_speed"))
        self.assertTrue(hasattr(dut, "link_width"))

    def test_ltssm_has_pipe_control_outputs(self):
        """
        LTSSM should control PIPE interface signals.
        """
        dut = LTSSM()

        # PIPE control outputs
        self.assertTrue(hasattr(dut, "send_ts1"))
        self.assertTrue(hasattr(dut, "send_ts2"))
        self.assertTrue(hasattr(dut, "tx_elecidle"))
        self.assertTrue(hasattr(dut, "powerdown"))

    def test_ltssm_has_pipe_status_inputs(self):
        """
        LTSSM should monitor PIPE interface status.
        """
        dut = LTSSM()

        # PIPE status inputs
        self.assertTrue(hasattr(dut, "ts1_detected"))
        self.assertTrue(hasattr(dut, "ts2_detected"))
        self.assertTrue(hasattr(dut, "rx_elecidle"))


class TestLTSSMDetect(unittest.TestCase):
    """Test LTSSM DETECT state."""

    def test_ltssm_starts_in_detect(self):
        """
        LTSSM should start in DETECT state after reset.

        DETECT state responsibilities:
        - Check for receiver on the link
        - Determine if link partner is present
        - Transition to POLLING when receiver detected

        Reference: PCIe Spec 4.0, Section 4.2.5.3.1: Detect
        """

        def testbench(dut):
            # After reset, should be in DETECT
            state = yield dut.current_state
            self.assertEqual(state, dut.DETECT)

            # Link should not be up
            link_up = yield dut.link_up
            self.assertEqual(link_up, 0)

            # TX should be in electrical idle
            tx_elecidle = yield dut.tx_elecidle
            self.assertEqual(tx_elecidle, 1)

        dut = LTSSM()
        run_simulation(dut, testbench(dut))

    def test_detect_transitions_to_polling_when_receiver_detected(self):
        """
        DETECT should transition to POLLING when receiver exits electrical idle.

        In real hardware, receiver detection is done by PHY. For this implementation,
        we use rx_elecidle signal: when it goes low, receiver is detected.
        """

        def testbench(dut):
            # Start in DETECT
            state = yield dut.current_state
            self.assertEqual(state, dut.DETECT)

            # Simulate receiver detection (rx_elecidle goes low)
            yield dut.rx_elecidle.eq(0)
            yield
            yield  # Give state machine time to transition

            # Should transition to POLLING
            state = yield dut.current_state
            self.assertEqual(state, dut.POLLING)

        dut = LTSSM()
        run_simulation(dut, testbench(dut))


class TestLTSSMPolling(unittest.TestCase):
    """Test LTSSM POLLING state."""

    def test_polling_sends_ts1_ordered_sets(self):
        """
        POLLING.Active should send TS1 ordered sets continuously.

        POLLING state has substates:
        - POLLING.Active: Send TS1 ordered sets
        - POLLING.Configuration: Send TS2 after receiving TS1 from partner
        - POLLING.Compliance: Compliance pattern (not implemented in Gen1)

        Reference: PCIe Spec 4.0, Section 4.2.5.3.2: Polling
        """

        def testbench(dut):
            # Start in DETECT, simulate receiver detection
            yield dut.rx_elecidle.eq(0)
            yield
            yield  # Transition to POLLING

            # Should be in POLLING state
            state = yield dut.current_state
            self.assertEqual(state, dut.POLLING)

            # Should be sending TS1 ordered sets
            send_ts1 = yield dut.send_ts1
            self.assertEqual(send_ts1, 1)

            # TX should exit electrical idle
            tx_elecidle = yield dut.tx_elecidle
            self.assertEqual(tx_elecidle, 0)

        dut = LTSSM()
        run_simulation(dut, testbench(dut))


class TestLTSSMConfiguration(unittest.TestCase):
    """Test LTSSM CONFIGURATION state."""

    def test_configuration_sends_ts2_ordered_sets(self):
        """
        CONFIGURATION should send TS2 ordered sets.

        After POLLING (TS1 exchange), devices move to CONFIGURATION
        and exchange TS2 ordered sets to finalize link parameters.

        Reference: PCIe Spec 4.0, Section 4.2.5.3.4: Configuration
        """

        def testbench(dut):
            # Simulate path: DETECT → POLLING → CONFIGURATION
            yield dut.rx_elecidle.eq(0)
            yield
            yield  # Now in POLLING

            # Simulate receiving TS1 from partner
            yield dut.ts1_detected.eq(1)
            yield
            yield
            yield  # Transition to CONFIGURATION (need extra cycle for state transition)
            yield dut.ts1_detected.eq(0)  # Clear detection flag

            # Should be in CONFIGURATION state
            state = yield dut.current_state
            self.assertEqual(state, dut.CONFIGURATION)

            # Should be sending TS2 ordered sets
            send_ts2 = yield dut.send_ts2
            self.assertEqual(send_ts2, 1)

            # Should NOT be sending TS1 anymore
            send_ts1 = yield dut.send_ts1
            self.assertEqual(send_ts1, 0)

        dut = LTSSM()
        run_simulation(dut, testbench(dut))

    def test_configuration_transitions_to_l0_when_ts2_received(self):
        """
        CONFIGURATION should transition to L0 when TS2 received from partner.

        Receiving TS2 confirms partner has also received TS1 and moved
        to CONFIGURATION. After exchanging TS2, link is ready for L0.
        """

        def testbench(dut):
            # Get to CONFIGURATION state
            yield dut.rx_elecidle.eq(0)
            yield
            yield  # POLLING
            yield dut.ts1_detected.eq(1)
            yield
            yield
            yield  # CONFIGURATION (need extra cycle for state transition)
            yield dut.ts1_detected.eq(0)

            # Simulate receiving TS2 from partner
            yield dut.ts2_detected.eq(1)
            yield
            yield
            yield  # Should transition to L0 (need extra cycle for state transition)

            # Should be in L0 state
            state = yield dut.current_state
            self.assertEqual(state, dut.L0)

        dut = LTSSM()
        run_simulation(dut, testbench(dut))


class TestLTSSML0(unittest.TestCase):
    """Test LTSSM L0 state (normal operation)."""

    def test_l0_sets_link_up(self):
        """
        L0 state should assert link_up signal.

        L0 is the normal operational state where:
        - Link is trained and ready for data transfer
        - link_up signal is asserted
        - No training sequences sent (except SKP for clock compensation)

        Reference: PCIe Spec 4.0, Section 4.2.5.3.5: L0
        """

        def testbench(dut):
            # Simulate full training sequence to reach L0
            # DETECT → POLLING → CONFIGURATION → L0

            # DETECT → POLLING
            yield dut.rx_elecidle.eq(0)
            yield
            yield

            # POLLING → CONFIGURATION
            yield dut.ts1_detected.eq(1)
            yield
            yield
            yield dut.ts1_detected.eq(0)

            # CONFIGURATION → L0
            yield dut.ts2_detected.eq(1)
            yield
            yield
            yield  # Need extra cycle for state transition

            # Should be in L0
            state = yield dut.current_state
            self.assertEqual(state, dut.L0)

            # Link should be up
            link_up = yield dut.link_up
            self.assertEqual(link_up, 1)

            # Should not be sending TS1 or TS2
            send_ts1 = yield dut.send_ts1
            send_ts2 = yield dut.send_ts2
            self.assertEqual(send_ts1, 0)
            self.assertEqual(send_ts2, 0)

        dut = LTSSM()
        run_simulation(dut, testbench(dut))

    def test_l0_transitions_to_recovery_on_electrical_idle(self):
        """
        L0 should transition to RECOVERY if link goes to electrical idle.

        Unexpected electrical idle indicates link error or partner initiated
        link retrain. RECOVERY state will attempt to restore the link.
        """

        def testbench(dut):
            # Get to L0 state (same sequence as above)
            yield dut.rx_elecidle.eq(0)
            yield
            yield
            yield dut.ts1_detected.eq(1)
            yield
            yield
            yield dut.ts1_detected.eq(0)
            yield dut.ts2_detected.eq(1)
            yield
            yield
            yield  # Need extra cycle for state transition

            # In L0 now
            state = yield dut.current_state
            self.assertEqual(state, dut.L0)

            # Simulate link going to electrical idle (error condition)
            yield dut.rx_elecidle.eq(1)
            yield
            yield
            yield  # Need extra cycle for state transition

            # Should transition to RECOVERY
            state = yield dut.current_state
            self.assertEqual(state, dut.RECOVERY)

        dut = LTSSM()
        run_simulation(dut, testbench(dut))


class TestLTSSMRecovery(unittest.TestCase):
    """Test LTSSM RECOVERY state."""

    def test_recovery_sends_ts1_for_retraining(self):
        """
        RECOVERY state should send TS1 ordered sets to retrain link.

        RECOVERY is entered when link errors occur in L0. It attempts
        to restore the link by re-exchanging training sequences.

        Reference: PCIe Spec 4.0, Section 4.2.5.3.7: Recovery
        """

        def testbench(dut):
            # Get to L0, then trigger recovery
            yield dut.rx_elecidle.eq(0)
            yield
            yield
            yield dut.ts1_detected.eq(1)
            yield
            yield
            yield dut.ts1_detected.eq(0)
            yield dut.ts2_detected.eq(1)
            yield
            yield
            yield  # Now in L0

            # Trigger recovery (electrical idle)
            yield dut.rx_elecidle.eq(1)
            yield
            yield
            yield

            # Should be in RECOVERY
            state = yield dut.current_state
            self.assertEqual(state, dut.RECOVERY)

            # Should be sending TS1 to retrain
            send_ts1 = yield dut.send_ts1
            self.assertEqual(send_ts1, 1)

            # Link should no longer be up
            link_up = yield dut.link_up
            self.assertEqual(link_up, 0)

        dut = LTSSM()
        run_simulation(dut, testbench(dut))

    def test_recovery_returns_to_l0_after_successful_retrain(self):
        """
        RECOVERY should return to L0 after successful retraining.

        When partner responds with TS1 (exits electrical idle), recovery
        can transition back to L0 (simplified - full spec uses TS2 exchange).
        """

        def testbench(dut):
            # Get to RECOVERY state
            yield dut.rx_elecidle.eq(0)
            yield
            yield
            yield dut.ts1_detected.eq(1)
            yield
            yield
            yield dut.ts1_detected.eq(0)
            yield dut.ts2_detected.eq(1)
            yield
            yield
            yield  # L0
            yield dut.rx_elecidle.eq(1)
            yield
            yield
            yield  # RECOVERY

            # Simulate partner exiting electrical idle and sending TS1
            yield dut.rx_elecidle.eq(0)
            yield
            yield
            yield dut.ts1_detected.eq(1)
            yield
            yield
            yield

            # Should return to L0 (simplified recovery)
            state = yield dut.current_state
            self.assertEqual(state, dut.L0)

        dut = LTSSM()
        run_simulation(dut, testbench(dut))


if __name__ == "__main__":
    unittest.main()
