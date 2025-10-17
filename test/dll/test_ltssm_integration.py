# test/dll/test_ltssm_integration.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for LTSSM integration with PIPE interface.

Validates that LTSSM properly controls PIPE TX/RX for automatic
link training without manual intervention.

References:
- PCIe Base Spec 4.0, Section 4.2.5: LTSSM
"""

import unittest

from litex.gen import run_simulation
from migen import *

from litepcie.dll.pipe import PIPEInterface


class TestLTSSMPIPEIntegration(unittest.TestCase):
    """Test LTSSM integration with PIPE interface."""

    def test_pipe_interface_can_use_ltssm(self):
        """
        PIPEInterface should support LTSSM integration.

        When enable_ltssm=True, PIPE interface should:
        - Instantiate LTSSM controller
        - Connect LTSSM control signals to TX packetizer
        - Connect PIPE RX status to LTSSM inputs
        - Provide link_up output
        """
        dut = PIPEInterface(data_width=8, gen=1, enable_ltssm=True)

        # Should have LTSSM instance
        self.assertTrue(hasattr(dut, "ltssm"))

        # Should expose link_up signal
        self.assertTrue(hasattr(dut, "link_up"))

    def test_ltssm_controls_ts_generation(self):
        """
        LTSSM should control TS1/TS2 generation automatically.
        """

        def testbench(dut):
            # Initially in DETECT, no TS generation
            send_ts1 = yield dut.ltssm.send_ts1
            send_ts2 = yield dut.ltssm.send_ts2
            self.assertEqual(send_ts1, 0)
            self.assertEqual(send_ts2, 0)

            # Simulate receiver detection
            yield dut.ltssm.rx_elecidle.eq(0)
            yield
            yield

            # Should now be sending TS1 (POLLING state)
            send_ts1 = yield dut.ltssm.send_ts1
            self.assertEqual(send_ts1, 1)

        dut = PIPEInterface(data_width=8, gen=1, enable_ltssm=True, enable_training_sequences=True)
        run_simulation(dut, testbench(dut))


class TestLTSSMAutoLinkTraining(unittest.TestCase):
    """Test automatic link training with LTSSM."""

    def test_ltssm_automatic_link_training_loopback(self):
        """
        LTSSM should automatically train link in loopback configuration.

        Test sequence:
        1. Both sides start in DETECT
        2. Loopback simulates receiver detection (rx_elecidle low)
        3. Both sides enter POLLING, send TS1
        4. Both detect partner TS1, enter CONFIGURATION
        5. Both send TS2
        6. Both detect partner TS2, enter L0
        7. link_up asserted

        This validates the full LTSSM training sequence.
        """

        def testbench(dut):
            # Initially in DETECT, link down
            link_up = yield dut.link_up
            self.assertEqual(link_up, 0)

            # Simulate receiver detection (in real HW, PHY would do this)
            # In loopback, we manually trigger it
            yield dut.ltssm.rx_elecidle.eq(0)
            yield
            yield

            # Should transition through states automatically via loopback:
            # TX sends TS1 → loopback to RX → RX detects TS1 → CONFIGURATION
            # TX sends TS2 → loopback to RX → RX detects TS2 → L0

            # Give it time to complete training (several cycles for TS exchange)
            # Need ~60 cycles: TS1 detection takes ~20 cycles, then TS2 takes ~35 more
            for _ in range(100):
                yield

                # Check if link came up
                link_up = yield dut.link_up
                state = yield dut.ltssm.current_state

                if link_up == 1:
                    # Success! Link trained to L0
                    self.assertEqual(state, dut.ltssm.L0)
                    break
            else:
                # Loop completed without link_up
                state = yield dut.ltssm.current_state
                self.fail(f"Link training failed. Final state: {state}, expected: {dut.ltssm.L0}")

        # Create PIPE interface with full loopback
        dut = PIPEInterface(
            data_width=8,
            gen=1,
            enable_skp=False,  # Disable SKP to simplify test
            enable_training_sequences=True,
            enable_ltssm=True,
        )

        # Loopback connections (TX → RX)
        dut.comb += [
            dut.pipe_rx_data.eq(dut.pipe_tx_data),
            dut.pipe_rx_datak.eq(dut.pipe_tx_datak),
        ]

        run_simulation(dut, testbench(dut), vcd_name="ltssm_loopback.vcd")


if __name__ == "__main__":
    unittest.main()
