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


if __name__ == "__main__":
    unittest.main()
