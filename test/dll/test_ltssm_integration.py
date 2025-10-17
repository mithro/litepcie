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
from litepcie.dll.ltssm import LTSSM


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


if __name__ == "__main__":
    unittest.main()
