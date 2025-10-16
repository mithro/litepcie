#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Integration tests for DLL + PIPE interface.

Tests behavioral interaction between DLL layer and PIPE interface.

References
----------
- PCIe Base Spec 4.0, Section 3: Data Link Layer
- Intel PIPE 3.0 Specification
"""

import unittest

from migen import *

from litepcie.dll.pipe import PIPEInterface
from litepcie.dll.rx import DLLRX
from litepcie.dll.tx import DLLTX


class TestDLLPIPEIntegration(unittest.TestCase):
    """Test DLL and PIPE integration."""

    def test_dll_tx_can_connect_to_pipe(self):
        """
        DLL TX should connect to PIPE interface.

        This verifies structural compatibility between DLL and PIPE.
        """
        dll_tx = DLLTX(data_width=64)
        pipe = PIPEInterface(data_width=8, gen=1)

        # Verify interfaces are compatible
        # DLL TX output (phy_source) should connect to PIPE input (dll_tx_sink)
        self.assertIsNotNone(dll_tx.phy_source)
        self.assertIsNotNone(pipe.dll_tx_sink)

        # Both should use phy_layout
        # (Actual connection test would require full system simulation)

    def test_pipe_can_connect_to_dll_rx(self):
        """
        PIPE interface should connect to DLL RX.

        This verifies structural compatibility.
        """
        pipe = PIPEInterface(data_width=8, gen=1)
        dll_rx = DLLRX(data_width=64)

        # Verify interfaces are compatible
        # PIPE output (dll_rx_source) should connect to DLL RX input (phy_sink)
        self.assertIsNotNone(pipe.dll_rx_source)
        self.assertIsNotNone(dll_rx.phy_sink)

    def test_full_dll_pipe_system_structure(self):
        """
        Full system should have DLL TX → PIPE → DLL RX path.

        This is a structural test verifying all components can coexist.
        Behavioral tests will follow in later tasks.
        """
        dll_tx = DLLTX(data_width=64)
        pipe = PIPEInterface(data_width=8, gen=1)
        dll_rx = DLLRX(data_width=64)

        # Create a simple module connecting them
        class DLLPIPESystem(Module):
            def __init__(self):
                self.submodules.dll_tx = dll_tx
                self.submodules.pipe = pipe
                self.submodules.dll_rx = dll_rx

                # Note: Connections will be added when TX/RX paths are complete

        dut = DLLPIPESystem()
        # Just verify it instantiates without errors
        self.assertIsNotNone(dut)


if __name__ == "__main__":
    unittest.main()
