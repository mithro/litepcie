#!/usr/bin/env python3

#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
PCIe PIPE Debug Example with LiteScope.

Example design showing how to integrate PIPEExternalPHY with LiteScope
for hardware debugging. Based on usb3_pipe's debugging approach.

Hardware Setup:
- FPGA board (e.g., KC705, Acorn)
- External PIPE PHY chip (e.g., TI TUSB1310A)
- Connection to PCIe root complex

Usage:
    python3 examples/pcie_pipe_debug.py --build  # Build bitstream
    python3 examples/pcie_pipe_debug.py --load   # Load to FPGA

Then use LiteScope to capture signals:
    litescope_cli --csv analyzer.csv

References:
- usb3_pipe/kc705.py: LiteScope integration pattern
- docs/pipe-interface-guide.md: PIPE interface usage
"""

import os
import argparse

from migen import *

from litex.soc.cores.clock import S7PLL
from litex.soc.integration.soc_core import SoCMini
from litex.soc.integration.builder import Builder

from litescope import LiteScopeAnalyzer

from litepcie.phy.pipe_external_phy import PIPEExternalPHY


# CRG (Clock Reset Generator) ----------------------------------------------------------------------

class _CRG(Module):
    """Clock Reset Generator for PCIe PIPE interface.

    Generates:
    - sys: System clock (125 MHz)
    - pcie: PCIe clock domain (driven by external PHY PCLK)
    """
    def __init__(self, platform, sys_clk_freq):
        self.clock_domains.cd_sys = ClockDomain()
        self.clock_domains.cd_pcie = ClockDomain()

        # # #

        # PLL for system clock
        self.submodules.pll = pll = S7PLL(speedgrade=-2)
        pll.register_clkin(platform.request("clk200"), 200e6)
        pll.create_clkout(self.cd_sys, sys_clk_freq)

        # PCIE clock domain is driven by external PHY PCLK
        # Platform must connect: platform.request("pcie_pipe").pclk → cd_pcie.clk


# PCIe PIPE Debug SoC ------------------------------------------------------------------------------

class PCIEPIPEDebugSoC(SoCMini):
    """
    PCIe PIPE debug design with LiteScope.

    Minimal SoC for debugging PIPEExternalPHY with hardware.
    Includes LiteScope for signal capture and Wishbone bridge for access.

    Parameters
    ----------
    platform : Platform
        LiteX platform
    with_analyzer : bool, optional
        Enable LiteScope analyzer (default: True)
    with_etherbone : bool, optional
        Enable Etherbone bridge (default: False, requires Ethernet)
    with_jtagbone : bool, optional
        Enable JTAGBone bridge (default: True)
    """

    def __init__(self, platform, with_analyzer=True, with_etherbone=False, with_jtagbone=True):
        sys_clk_freq = int(125e6)

        # SoCMini ----------------------------------------------------------------------------------
        SoCMini.__init__(self, platform, sys_clk_freq,
            ident="PCIEPIPEDebug",
            ident_version=True
        )

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = _CRG(platform, sys_clk_freq)

        # Wishbone Bridge --------------------------------------------------------------------------
        if with_jtagbone:
            self.add_jtagbone()

        if with_etherbone:
            # Note: Requires Ethernet on platform
            # from liteeth.phy import LiteEthPHY
            # self.submodules.eth_phy = LiteEthPHY(...)
            # self.add_etherbone(phy=self.eth_phy, ip_address="192.168.1.50")
            pass

        # External PIPE PHY ------------------------------------------------------------------------
        pcie_pads = platform.request("pcie_pipe")
        self.submodules.phy = PIPEExternalPHY(
            platform   = platform,
            pads       = pcie_pads,
            data_width = 64,
            cd         = "sys",
            bar0_size  = 0x10000,
        )

        # For now, loop back (no TLP layer yet)
        # In real design, connect to LitePCIeEndpoint
        self.comb += self.phy.source.connect(self.phy.sink)

        # Status LEDs ------------------------------------------------------------------------------
        if hasattr(platform, "request") and platform.lookup_request("user_led", loose=True):
            try:
                self.comb += platform.request("user_led", 0).eq(self.phy.pipe.link_up)
                self.comb += platform.request("user_led", 1).eq(~self.phy.pipe.ltssm.tx_elecidle)
            except:
                pass  # No LEDs on this platform

        # LiteScope Analyzer -----------------------------------------------------------------------
        if with_analyzer:
            analyzer_signals = [
                # LTSSM State Machine
                self.phy.pipe.ltssm.current_state,
                self.phy.pipe.link_up,
                self.phy.pipe.ltssm.send_ts1,
                self.phy.pipe.ltssm.send_ts2,
                self.phy.pipe.ltssm.ts1_detected,
                self.phy.pipe.ltssm.ts2_detected,
                self.phy.pipe.ltssm.rx_elecidle,
                self.phy.pipe.ltssm.tx_elecidle,

                # PIPE Interface Signals
                self.phy.pipe.pipe_tx_data,
                self.phy.pipe.pipe_tx_datak,
                self.phy.pipe.pipe_rx_data,
                self.phy.pipe.pipe_rx_datak,

                # DLL TX Path
                self.phy.dll_tx.tlp_sink.valid,
                self.phy.dll_tx.tlp_sink.ready,
                self.phy.dll_tx.phy_source.valid,
                self.phy.dll_tx.phy_source.ready,

                # DLL RX Path
                self.phy.dll_rx.phy_sink.valid,
                self.phy.dll_rx.phy_sink.ready,
                self.phy.dll_rx.tlp_source.valid,
                self.phy.dll_rx.tlp_source.ready,

                # TX/RX Datapaths
                self.phy.tx_datapath.source.valid,
                self.phy.rx_datapath.sink.valid,
            ]

            self.submodules.analyzer = LiteScopeAnalyzer(
                analyzer_signals,
                depth        = 4096,
                clock_domain = "pcie",
                csr_csv      = "analyzer.csv"
            )
            self.add_csr("analyzer")


# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="PCIe PIPE Debug Example with LiteScope",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--build",          action="store_true", help="Build bitstream")
    parser.add_argument("--load",           action="store_true", help="Load bitstream")
    parser.add_argument("--platform",       default="kc705",     help="Platform (kc705, acorn)")
    parser.add_argument("--with-etherbone", action="store_true", help="Enable Etherbone (needs Ethernet)")
    args = parser.parse_args()

    # Import platform
    if args.platform == "kc705":
        from litex_boards.platforms import xilinx_kc705
        platform = xilinx_kc705.Platform()
    elif args.platform == "acorn":
        from litex_boards.platforms import sqrl_acorn
        platform = sqrl_acorn.Platform()
    else:
        raise ValueError(f"Unknown platform: {args.platform}")

    # Add PIPE pad definitions to platform
    # TODO: User must add actual pin constraints for their board
    # See litepcie/platforms/pipe_pads.py for signal definitions
    print("\n" + "="*80)
    print("WARNING: You must add PIPE pad definitions to your platform!")
    print("See litepcie/platforms/pipe_pads.py for required signals.")
    print("="*80 + "\n")

    # Create SoC
    soc = PCIEPIPEDebugSoC(
        platform,
        with_analyzer  = True,
        with_etherbone = args.with_etherbone,
        with_jtagbone  = True,
    )

    # Build
    builder = Builder(soc, csr_csv="csr.csv", csr_json="csr.json")
    builder.build(run=args.build)

    # Load
    if args.load:
        prog = platform.create_programmer()
        prog.load_bitstream(os.path.join(builder.gateware_dir, soc.build_name + ".bit"))

    print("\n" + "="*80)
    print("To use LiteScope:")
    print("  1. Load bitstream: python3 examples/pcie_pipe_debug.py --load")
    print("  2. Run LiteScope: litescope_cli --csv analyzer.csv")
    print("  3. Trigger on LTSSM state changes or link_up signal")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
