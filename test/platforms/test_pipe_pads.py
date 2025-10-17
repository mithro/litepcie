#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for PIPE interface pad definitions.

PIPE pads connect FPGA to external PIPE PHY chip.

References:
- Intel PIPE 3.0 Specification
"""

import unittest

from litepcie.platforms.pipe_pads import get_pipe_pads


class TestPIPEPads(unittest.TestCase):
    """Test PIPE pad definitions."""

    def test_pipe_pads_structure(self):
        """
        PIPE pads should have all required signals.

        Required PIPE 3.0 signals:
        - TX: data, datak, elecidle
        - RX: data, datak, elecidle, status, valid
        - Control: powerdown, reset
        - Clock: pclk (from PHY)
        """
        pads = get_pipe_pads()

        # TX signals
        self.assertIn("tx_data", pads)
        self.assertIn("tx_datak", pads)
        self.assertIn("tx_elecidle", pads)

        # RX signals
        self.assertIn("rx_data", pads)
        self.assertIn("rx_datak", pads)
        self.assertIn("rx_elecidle", pads)
        self.assertIn("rx_status", pads)
        self.assertIn("rx_valid", pads)

        # Control signals
        self.assertIn("powerdown", pads)
        self.assertIn("reset", pads)

        # Clock
        self.assertIn("pclk", pads)


if __name__ == "__main__":
    unittest.main()
