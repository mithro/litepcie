#!/usr/bin/env python3

#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2025 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Lattice ECP5 SERDES Transceiver for PCIe

Wraps ECP5 DCUA primitive with PIPE interface, using software 8b/10b encoding.

Reference:
- Lattice TN1261: ECP5/ECP5-5G SERDES/PCS Usage Guide
- Lattice FPGA-TN-02032: ECP5 and ECP5-5G SERDES Design Guide
- ECP5-PCIe project (excellent reference implementation)

Architecture:
    PIPE Interface (16-bit) → CDC → 8b/10b Encoder → DCUA Primitive

Key ECP5 Differences:
- No built-in 8b/10b encoder/decoder (must use software)
- DCUA (Dual Channel Unit) primitive
- SCI (SerDes Client Interface) for runtime configuration
- Complex 8-state reset sequencing required
- Primarily Gen1 (2.5 GT/s), Gen2 experimental
- Open-source toolchain support (nextpnr)
"""

from migen import *
from litex.gen import LiteXModule
from litex.soc.cores.code_8b10b import Encoder, Decoder

from litepcie.phy.transceiver_base.transceiver import (
    PIPETransceiver,
    TransceiverTXDatapath,
    TransceiverRXDatapath,
    TransceiverResetSequencer,
)


# SCI (SerDes Client Interface) -----------------------------------------------------------

class ECP5SCIInterface(Module):
    """
    ECP5 SerDes Client Interface for runtime configuration.

    Used for:
    - RX/TX polarity inversion
    - Termination settings
    - Loopback modes

    Reference
    ---------
    Lattice TN1261 pages 52-55
    """

    def __init__(self):
        # SCI signals to DCUA
        self.sci_wdata = Signal(8)
        self.sci_addr = Signal(6)
        self.sci_rdata = Signal(8)
        self.sci_rd = Signal()
        self.sci_wrn = Signal()
        self.dual_sel = Signal()
        self.chan_sel = Signal()


# ECP5 PLL Configuration -------------------------------------------------------------------

class ECP5SerDesPLL(LiteXModule):
    """
    ECP5 SERDES PLL configuration.

    Reference
    ---------
    Lattice TN1261: ECP5/ECP5-5G SERDES/PCS Usage Guide
    """

    def __init__(self, refclk_freq, linerate, speed_5GTps=False):
        self.refclk_freq = refclk_freq
        self.linerate = linerate
        self.speed_5GTps = speed_5GTps

        # Outputs
        self.lock = Signal()

    def get_config(self):
        """
        Get DCU configuration parameters.

        Returns
        -------
        dict
            DCU configuration parameters
        """
        return {
            "D_MACROPDB": "0b1",
            "D_TXPLL_PWDNB": "0b1",
            "D_REFCK_MODE": "0b100" if self.refclk_freq == 100e6 else "0b000",  # 25x ref_clk or 20x
            "D_TX_MAX_RATE": "5.0" if self.speed_5GTps else "2.5",
            "D_TX_VCO_CK_DIV": "0b000",  # DIV/1
            # More parameters would be added in full implementation
        }


# ECP5 Reset Sequencer ---------------------------------------------------------------------

class ECP5ResetSequencer(TransceiverResetSequencer):
    """
    ECP5-specific reset sequencer.

    ECP5 requires complex 8-state FSM for proper reset sequencing:
    1. INITIAL_RESET - Assert all resets
    2. WAIT_FOR_TXPLL_LOCK - Wait for TX PLL to lock
    3. APPLY_TXPCS_RESET - Reset TX PCS
    4. RELEASE_TXPCS_RESET - Release TX PCS reset
    5. WAIT_FOR_RXDATA - Wait for RX data presence
    6. APPLY_RXPCS_RESET - Reset RX PCS
    7. RELEASE_RXPCS_RESET - Release RX PCS reset
    8. IDLE - Normal operation

    Reference
    ---------
    ECP5-PCIe project: ecp5_serdes.py lines 217-264
    LUNA: ecp5.py lines 505-659
    """

    def __init__(self, sys_clk_freq):
        TransceiverResetSequencer.__init__(self)
        self.sys_clk_freq = sys_clk_freq

        # Calculate cycle counts
        timeout_cycles = int(1e-3 * sys_clk_freq)  # 1ms timeout

        # # #

        # Timeout counter
        timeout_timer = Signal(max=timeout_cycles)

        # Synchronized status signals
        tx_lol_sync = Signal()  # TX Loss of Lock
        rx_lol_sync = Signal()  # RX Loss of Lock

        # FSM
        self.submodules.fsm = FSM(reset_state="INITIAL_RESET")

        self.fsm.act("INITIAL_RESET",
            self.tx_pll_reset.eq(1),
            self.tx_pcs_reset.eq(1),
            self.rx_cdr_reset.eq(1),
            self.rx_pcs_reset.eq(1),
            NextValue(timeout_timer, 0),
            NextState("WAIT_FOR_TXPLL_LOCK")
        )

        self.fsm.act("WAIT_FOR_TXPLL_LOCK",
            self.tx_pll_reset.eq(0),  # Release TX PLL reset
            self.tx_pcs_reset.eq(1),
            self.rx_cdr_reset.eq(1),
            self.rx_pcs_reset.eq(1),
            NextValue(timeout_timer, timeout_timer + 1),
            If(self.tx_pll_locked | (timeout_timer == (timeout_cycles - 1)),
                NextState("APPLY_TXPCS_RESET")
            )
        )

        self.fsm.act("APPLY_TXPCS_RESET",
            self.tx_pll_reset.eq(0),
            self.tx_pcs_reset.eq(1),
            self.rx_cdr_reset.eq(1),
            self.rx_pcs_reset.eq(1),
            NextState("RELEASE_TXPCS_RESET")
        )

        self.fsm.act("RELEASE_TXPCS_RESET",
            self.tx_pll_reset.eq(0),
            self.tx_pcs_reset.eq(0),  # Release TX PCS reset
            self.rx_cdr_reset.eq(1),
            self.rx_pcs_reset.eq(1),
            self.tx_ready.eq(1),
            NextValue(timeout_timer, 0),
            NextState("WAIT_FOR_RXDATA")
        )

        self.fsm.act("WAIT_FOR_RXDATA",
            self.tx_pll_reset.eq(0),
            self.tx_pcs_reset.eq(0),
            self.rx_cdr_reset.eq(0),  # Release RX CDR reset
            self.rx_pcs_reset.eq(1),
            self.tx_ready.eq(1),
            NextValue(timeout_timer, timeout_timer + 1),
            If(self.rx_has_signal | (timeout_timer == (timeout_cycles - 1)),
                NextState("APPLY_RXPCS_RESET")
            )
        )

        self.fsm.act("APPLY_RXPCS_RESET",
            self.tx_pll_reset.eq(0),
            self.tx_pcs_reset.eq(0),
            self.rx_cdr_reset.eq(0),
            self.rx_pcs_reset.eq(1),
            self.tx_ready.eq(1),
            NextState("RELEASE_RXPCS_RESET")
        )

        self.fsm.act("RELEASE_RXPCS_RESET",
            self.tx_pll_reset.eq(0),
            self.tx_pcs_reset.eq(0),
            self.rx_cdr_reset.eq(0),
            self.rx_pcs_reset.eq(0),  # Release RX PCS reset
            self.tx_ready.eq(1),
            self.rx_ready.eq(1),
            NextState("IDLE")
        )

        self.fsm.act("IDLE",
            self.tx_pll_reset.eq(0),
            self.tx_pcs_reset.eq(0),
            self.rx_cdr_reset.eq(0),
            self.rx_pcs_reset.eq(0),
            self.tx_ready.eq(1),
            self.rx_ready.eq(1),
            # Could add error monitoring and restart logic here
        )


# ECP5 SERDES Transceiver ------------------------------------------------------------------

class ECP5SerDesTransceiver(PIPETransceiver):
    """
    Lattice ECP5 SERDES transceiver for PCIe.

    Wraps DCUA primitive with PIPE interface, using software 8b/10b encoding.

    Key differences from Xilinx:
    - No built-in 8b/10b (use gateware encoder/decoder)
    - Uses DCUA (Dual Channel Unit) primitive
    - SCI interface for runtime configuration
    - Complex reset sequencing required
    - Gen1 primary target (Gen2 experimental)

    Parameters
    ----------
    platform : Platform
        LiteX platform
    dcu : int
        DCU number (0 or 1)
    channel : int
        Channel within DCU (0 or 1)
    gearing : int
        Gearbox ratio (1 or 2)
        1 = 8-bit interface (1 byte per cycle)
        2 = 16-bit interface (2 bytes per cycle, typical)
    speed_5GTps : bool
        Enable 5 GT/s support (Gen2)
    refclk_freq : float
        Reference clock frequency (100e6 or 200e6)
    sys_clk_freq : float
        System clock frequency
    data_width : int
        PIPE data width (must match gearing: gearing*8)
    gen : int
        PCIe generation (1 or 2)

    Reference
    ---------
    - ECP5-PCIe project
    - Lattice TN1261: ECP5/ECP5-5G SERDES/PCS Usage Guide
    - Phase 9 Plan: Task 9.5
    """

    def __init__(self, platform, dcu=0, channel=0, gearing=2,
                 speed_5GTps=False, refclk_freq=100e6, sys_clk_freq=125e6,
                 data_width=16, gen=1):

        assert dcu in [0, 1], "DCU must be 0 or 1"
        assert channel in [0, 1], "Channel must be 0 or 1"
        assert gearing in [1, 2], "Gearing must be 1 or 2"
        assert refclk_freq in [100e6, 200e6], "RefClk must be 100 or 200 MHz"
        assert data_width == gearing * 8, "data_width must match gearing"

        PIPETransceiver.__init__(self, data_width, gen)

        self.platform = platform
        self.dcu = dcu
        self.channel = channel
        self.gearing = gearing
        self.speed_5GTps = speed_5GTps

        nwords = data_width // 8

        # # #

        # 8b/10b Encoder/Decoder (Software - ECP5 has no hardware 8b/10b)
        # -----------------------------------------------------------------
        self.submodules.encoder = ClockDomainsRenamer("tx")(
            Encoder(nwords=nwords, lsb_first=True)
        )
        self.submodules.decoder = ClockDomainsRenamer("rx")(
            Decoder(lsb_first=True)
        )

        # SCI Interface
        # -------------
        self.submodules.sci = ECP5SCIInterface()

        # PLL
        # ---
        linerate = self.get_line_rate()
        pll = ECP5SerDesPLL(refclk_freq, linerate, speed_5GTps)
        self.submodules.pll = pll

        # TX/RX Datapaths
        # ---------------
        self.submodules.tx_datapath = TransceiverTXDatapath(data_width=data_width)
        self.submodules.rx_datapath = TransceiverRXDatapath(data_width=data_width)

        # Reset Sequencer
        # ---------------
        self.submodules.reset_seq = ECP5ResetSequencer(sys_clk_freq)

        # DCUA Primitive Instantiation
        # -----------------------------
        # TODO: Add full DCUA instantiation with DCU and channel configuration
        # Note: ECP5 requires careful parameter setup (60+ parameters per channel)
        # See Phase 9 Plan Task 9.5 for complete implementation

        # Clock Domains
        # -------------
        self.clock_domains.cd_tx = ClockDomain("tx")
        self.clock_domains.cd_rx = ClockDomain("rx")

        # Platform Constraints
        # --------------------
        word_clk_freq = self.get_word_clk_freq()
        # platform.add_period_constraint(self.tx_clk, 1e9/word_clk_freq)
        # platform.add_period_constraint(self.rx_clk, 1e9/word_clk_freq)

        # NOTE: Skeleton implementation - full DCUA instantiation pending
        # Full implementation requires:
        # - DCU-level configuration (D_MACROPDB, D_TXPLL_PWDNB, etc.)
        # - Channel-level configuration (CHx_PROTOCOL, CHx_PCIE_MODE, etc.)
        # - SCI interface wiring
        # - Reference clock setup (EXTREFB)
