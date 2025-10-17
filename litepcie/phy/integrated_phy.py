#!/usr/bin/env python3

#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2025 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Integrated PCIe PHY Examples

Shows how to integrate transceivers with PIPE, DLL, and LTSSM layers.

Architecture:
    User Logic (TLPs) → DLL → PIPE → Transceiver → Physical Link

This module provides example integrated PHY classes that combine:
- Transceiver wrapper (GTX/GTY/ECP5)
- PIPE interface (Phase 3)
- DLL layer (Phase 4)
- LTSSM (Phase 6)

These serve as reference implementations for full PCIe PHY integration.
"""

from migen import *
from litex.gen import LiteXModule


# Example: 7-Series GTX Integrated PHY -----------------------------------------------------

class S7PCIePHY(LiteXModule):
    """
    Example integrated PCIe PHY using Xilinx 7-Series GTX.

    Combines:
    - S7GTXTransceiver (software 8b/10b)
    - PIPE interface
    - DLL layer
    - LTSSM

    This is a reference implementation showing integration patterns.

    Parameters
    ----------
    platform : Platform
        LiteX platform
    pads : Record
        PCIe pads (tx_p, tx_n, rx_p, rx_n)
    refclk_pads : Record
        Reference clock pads
    sys_clk_freq : float
        System clock frequency

    Example
    -------
    # In your SoC:
    phy = S7PCIePHY(
        platform=platform,
        pads=platform.request("pcie_x1"),
        refclk_pads=platform.request("pcie_refclk"),
        sys_clk_freq=125e6
    )

    # Connect to endpoint
    endpoint = LitePCIeEndpoint(phy)
    """

    def __init__(self, platform, pads, refclk_pads, sys_clk_freq):
        # Import here to avoid circular dependencies
        from litepcie.phy.xilinx.s7_gtx import S7GTXTransceiver

        # Transceiver
        # -----------
        self.submodules.gtx = S7GTXTransceiver(
            platform=platform,
            pads=pads,
            refclk_pads=refclk_pads,
            refclk_freq=100e6,
            sys_clk_freq=sys_clk_freq,
            data_width=16,  # 2 bytes per cycle
            gen=1           # Start with Gen1, LTSSM can negotiate Gen2
        )

        # PIPE Interface (would be from Phase 3)
        # ---------------------------------------
        # from litepcie.phy.pipe import PIPEInterface
        # self.submodules.pipe = PIPEInterface(data_width=16)

        # Connect GTX to PIPE
        # self.comb += [
        #     self.pipe.tx_data.eq(self.gtx.tx_data),
        #     self.gtx.rx_data.eq(self.pipe.rx_data),
        #     # ... more PIPE connections
        # ]

        # DLL Layer (would be from Phase 4)
        # ----------------------------------
        # from litepcie.core.dll import DLL
        # self.submodules.dll = DLL()

        # LTSSM (would be from Phase 6)
        # ------------------------------
        # from litepcie.core.ltssm import LTSSM
        # self.submodules.ltssm = LTSSM()

        # LTSSM ↔ Transceiver Integration
        # --------------------------------
        # Key connections for LTSSM integration:

        # 1. Speed control (LTSSM negotiates speed)
        # self.comb += self.gtx.speed.eq(self.ltssm.link_speed)

        # 2. Electrical idle control
        # self.comb += [
        #     self.gtx.tx_elecidle.eq(self.ltssm.tx_elecidle),
        #     self.ltssm.rx_elecidle.eq(self.gtx.rx_elecidle),
        # ]

        # 3. Link status
        # self.comb += [
        #     self.ltssm.phy_ready.eq(self.gtx.tx_ready & self.gtx.rx_ready),
        # ]

        # 4. Reset coordination
        # self.comb += self.gtx.reset.eq(self.ltssm.phy_reset)

        # Export TLP interface (for user logic)
        # --------------------------------------
        # self.sink = self.dll.sink     # TX TLPs
        # self.source = self.dll.source # RX TLPs


# Example: UltraScale+ GTY Integrated PHY --------------------------------------------------

class USPPCIePHY(LiteXModule):
    """
    Example integrated PCIe PHY using Xilinx UltraScale+ GTY.

    Similar to S7PCIePHY but with GTY transceiver.

    Parameters
    ----------
    platform : Platform
        LiteX platform
    pads : Record
        PCIe pads
    refclk_pads : Record
        Reference clock pads
    sys_clk_freq : float
        System clock frequency
    """

    def __init__(self, platform, pads, refclk_pads, sys_clk_freq):
        from litepcie.phy.xilinx.usp_gty import USPGTYTransceiver

        # Transceiver
        self.submodules.gty = USPGTYTransceiver(
            platform=platform,
            pads=pads,
            refclk_pads=refclk_pads,
            refclk_freq=100e6,
            sys_clk_freq=sys_clk_freq,
            data_width=16,
            gen=1
        )

        # Integration pattern same as S7PCIePHY
        # (PIPE, DLL, LTSSM connections)


# Example: ECP5 SERDES Integrated PHY ------------------------------------------------------

class ECP5PCIePHY(LiteXModule):
    """
    Example integrated PCIe PHY using Lattice ECP5 SERDES.

    Open-source toolchain friendly implementation.

    Parameters
    ----------
    platform : Platform
        LiteX platform
    dcu : int
        DCU number (0 or 1)
    channel : int
        Channel number (0 or 1)
    sys_clk_freq : float
        System clock frequency
    """

    def __init__(self, platform, dcu=0, channel=0, sys_clk_freq=125e6):
        from litepcie.phy.lattice.ecp5_serdes import ECP5SerDesTransceiver

        # Transceiver
        self.submodules.serdes = ECP5SerDesTransceiver(
            platform=platform,
            dcu=dcu,
            channel=channel,
            gearing=2,          # 16-bit interface
            speed_5GTps=False,  # Gen1 initially
            refclk_freq=100e6,
            sys_clk_freq=sys_clk_freq,
            data_width=16,
            gen=1
        )

        # Integration pattern same as S7PCIePHY
        # (PIPE, DLL, LTSSM connections)


# LTSSM Integration Helpers ----------------------------------------------------------------

def connect_ltssm_to_transceiver(ltssm, transceiver):
    """
    Helper function to connect LTSSM to transceiver.

    This encapsulates the common connection pattern.

    Parameters
    ----------
    ltssm : LTSSM
        Link Training and Status State Machine (from Phase 6)
    transceiver : PIPETransceiver
        Transceiver wrapper (GTX/GTY/ECP5)

    Returns
    -------
    list
        List of Migen statements for connections
    """
    return [
        # Speed control
        transceiver.speed.eq(ltssm.link_speed),

        # Electrical idle
        transceiver.tx_elecidle.eq(ltssm.tx_elecidle),
        ltssm.rx_elecidle.eq(transceiver.rx_elecidle),

        # Link status
        ltssm.phy_ready.eq(transceiver.tx_ready & transceiver.rx_ready),

        # Reset coordination
        transceiver.reset.eq(ltssm.phy_reset),
    ]
