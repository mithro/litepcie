#!/usr/bin/env python3

#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2025 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Xilinx UltraScale+ GTY Transceiver for PCIe

Wraps GTYE4_CHANNEL primitive with PIPE interface, using software 8b/10b
encoding for consistency across platforms.

Reference:
- Xilinx UG578: UltraScale Architecture GTY Transceivers User Guide
- Similar to s7_gtx.py but with UltraScale+ specifics

Architecture:
    PIPE Interface (16-bit) → CDC → 8b/10b Encoder → GTY Primitive

Key Differences from 7-Series GTX:
- GTHE4_COMMON for shared QPLL0/QPLL1
- BUFG_GT for clock buffering (instead of BUFG)
- More advanced equalization options
- Gen3 capable architecture (though Gen3 needs 128b/130b encoding)
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


# GTY PLL Configuration --------------------------------------------------------------------

class GTYChannelPLL(LiteXModule):
    """
    GTY Channel PLL configuration (QPLL0/QPLL1).

    UltraScale+ uses QPLL instead of CPLL for better jitter performance.

    Parameters
    ----------
    refclk_freq : float
        Reference clock frequency in Hz
    linerate : float
        Target line rate in bits per second

    Reference
    ---------
    Xilinx UG578: UltraScale Architecture GTY Transceivers
    """

    def __init__(self, refclk_freq, linerate):
        self.refclk_freq = refclk_freq
        self.linerate = linerate
        self.config = self.compute_config(refclk_freq, linerate)

        # Outputs
        self.lock = Signal()

    @staticmethod
    def compute_config(refclk_freq, linerate):
        """
        Compute QPLL configuration for target line rate.

        QPLL VCO Range: 9.8 GHz to 16.375 GHz (QPLL0) or 8.0 GHz to 13.0 GHz (QPLL1)

        Returns
        -------
        dict
            Configuration with keys: n, m, d, vco_freq, linerate, qpll_type
        """
        # Try QPLL0 first (higher frequency range)
        for n in [16, 20, 32, 40, 60, 64, 66, 75, 80, 84, 90, 96, 100, 112, 120, 125, 150, 160]:
            for m in [1, 2, 3, 4]:
                vco_freq = refclk_freq * n / m

                # Check QPLL0 range
                if 9.8e9 <= vco_freq <= 16.375e9:
                    for d in [1, 2, 4, 8, 16]:
                        current_linerate = vco_freq * 2 / d
                        if abs(current_linerate - linerate) < 1e6:
                            return {
                                "qpll_type": "QPLL0",
                                "n": n,
                                "m": m,
                                "d": d,
                                "vco_freq": vco_freq,
                                "linerate": current_linerate,
                                "refclk_freq": refclk_freq,
                            }

        # Try QPLL1 (lower frequency range)
        for n in [16, 20, 32, 40, 60, 64, 66, 75, 80, 84, 90, 96, 100]:
            for m in [1, 2, 3, 4]:
                vco_freq = refclk_freq * n / m

                # Check QPLL1 range
                if 8.0e9 <= vco_freq <= 13.0e9:
                    for d in [1, 2, 4, 8, 16]:
                        current_linerate = vco_freq * 2 / d
                        if abs(current_linerate - linerate) < 1e6:
                            return {
                                "qpll_type": "QPLL1",
                                "n": n,
                                "m": m,
                                "d": d,
                                "vco_freq": vco_freq,
                                "linerate": current_linerate,
                                "refclk_freq": refclk_freq,
                            }

        raise ValueError(
            f"No valid QPLL configuration found for "
            f"refclk={refclk_freq/1e6:.1f} MHz, linerate={linerate/1e9:.1f} GT/s"
        )


# GTY Reset Sequencer ----------------------------------------------------------------------

class GTYResetSequencer(TransceiverResetSequencer):
    """
    GTY-specific reset sequencer.

    Similar to GTX but with UltraScale+ timing requirements.

    Parameters
    ----------
    sys_clk_freq : float
        System clock frequency in Hz
    """

    def __init__(self, sys_clk_freq):
        TransceiverResetSequencer.__init__(self)
        self.sys_clk_freq = sys_clk_freq

        # Calculate cycle counts for timing (similar to GTX)
        defer_cycles = int(50e-3 * sys_clk_freq)  # 50ms defer
        pll_lock_timeout = int(1e-3 * sys_clk_freq)  # 1ms timeout

        # # #

        # Defer counter
        defer_timer = Signal(max=defer_cycles)

        # PLL lock timeout
        pll_timer = Signal(max=pll_lock_timeout)

        # FSM (same pattern as GTX)
        self.submodules.fsm = FSM(reset_state="DEFER")
        self.fsm.act("DEFER",
            self.tx_pll_reset.eq(1),
            self.tx_pcs_reset.eq(1),
            self.rx_cdr_reset.eq(1),
            self.rx_pcs_reset.eq(1),
            NextValue(defer_timer, defer_timer + 1),
            If(defer_timer == (defer_cycles - 1),
                NextState("INIT_RESET")
            )
        )
        self.fsm.act("INIT_RESET",
            self.tx_pll_reset.eq(1),
            self.tx_pcs_reset.eq(1),
            self.rx_cdr_reset.eq(1),
            self.rx_pcs_reset.eq(1),
            NextValue(pll_timer, 0),
            NextState("WAIT_PLL_LOCK")
        )
        self.fsm.act("WAIT_PLL_LOCK",
            self.tx_pll_reset.eq(0),
            self.tx_pcs_reset.eq(1),
            self.rx_cdr_reset.eq(1),
            self.rx_pcs_reset.eq(1),
            NextValue(pll_timer, pll_timer + 1),
            If(self.tx_pll_locked,
                NextState("RELEASE_TX")
            ).Elif(pll_timer == (pll_lock_timeout - 1),
                NextState("INIT_RESET")
            )
        )
        self.fsm.act("RELEASE_TX",
            self.tx_pll_reset.eq(0),
            self.tx_pcs_reset.eq(0),
            self.rx_cdr_reset.eq(1),
            self.rx_pcs_reset.eq(1),
            self.tx_ready.eq(1),
            NextState("RELEASE_RX")
        )
        self.fsm.act("RELEASE_RX",
            self.tx_pll_reset.eq(0),
            self.tx_pcs_reset.eq(0),
            self.rx_cdr_reset.eq(0),
            self.rx_pcs_reset.eq(0),
            self.tx_ready.eq(1),
            self.rx_ready.eq(1),
            NextState("READY")
        )
        self.fsm.act("READY",
            self.tx_pll_reset.eq(0),
            self.tx_pcs_reset.eq(0),
            self.rx_cdr_reset.eq(0),
            self.rx_pcs_reset.eq(0),
            self.tx_ready.eq(1),
            self.rx_ready.eq(1),
        )


# UltraScale+ GTY Transceiver --------------------------------------------------------------

class USPGTYTransceiver(PIPETransceiver):
    """
    Xilinx UltraScale+ GTY transceiver for PCIe.

    Wraps GTYE4_CHANNEL primitive with PIPE interface, using software 8b/10b.

    Parameters
    ----------
    platform : Platform
        LiteX platform for constraints
    pads : Record
        Differential TX/RX pads
    refclk_pads : Record or Signal
        Reference clock input
    refclk_freq : float
        Reference clock frequency in Hz
    sys_clk_freq : float
        System clock frequency in Hz
    data_width : int
        PIPE data width (8, 16, or 32 bits)
    gen : int
        PCIe generation (1=Gen1, 2=Gen2)

    Reference
    ---------
    - Xilinx UG578: UltraScale Architecture GTY Transceivers
    - Phase 9 Plan: Task 9.4
    """

    def __init__(self, platform, pads, refclk_pads, refclk_freq,
                 sys_clk_freq, data_width=16, gen=1):
        PIPETransceiver.__init__(self, data_width, gen)

        self.platform = platform
        self.pads = pads
        self.sys_clk_freq = sys_clk_freq

        assert data_width in [8, 16, 32], "data_width must be 8, 16, or 32"
        assert gen in [1, 2], "Only Gen1 and Gen2 supported (Gen3 needs 128b/130b)"

        # Calculate parameters
        linerate = self.get_line_rate()
        nwords = data_width // 8

        # # #

        # Reference Clock
        # ---------------
        if isinstance(refclk_pads, (Signal, ClockSignal)):
            refclk = refclk_pads
        else:
            refclk = Signal()
            self.specials += Instance("IBUFDS_GTE4",
                i_CEB = 0,
                i_I   = refclk_pads.p,
                i_IB  = refclk_pads.n,
                o_O   = refclk
            )

        # PLL
        # ---
        pll = GTYChannelPLL(refclk_freq, linerate)
        self.submodules.pll = pll

        # 8b/10b Encoder/Decoder (Software)
        # ----------------------------------
        self.submodules.encoder = ClockDomainsRenamer("tx")(
            Encoder(nwords=nwords, lsb_first=True)
        )
        self.submodules.decoder = ClockDomainsRenamer("rx")(
            Decoder(lsb_first=True)
        )

        # TX/RX Datapaths
        # ---------------
        self.submodules.tx_datapath = TransceiverTXDatapath(data_width=data_width)
        self.submodules.rx_datapath = TransceiverRXDatapath(data_width=data_width)

        # Reset Sequencer
        # ---------------
        self.submodules.reset_seq = GTYResetSequencer(sys_clk_freq)

        # GTY Primitive Instantiation
        # ----------------------------
        # TODO: Add full GTYE4_CHANNEL instantiation
        # Note: GTY has different parameters than GTX (GTHE4_COMMON, BUFG_GT, etc.)

        # Clock Domains
        # -------------
        self.clock_domains.cd_tx = ClockDomain("tx")
        self.clock_domains.cd_rx = ClockDomain("rx")

        # Platform Constraints
        # --------------------
        word_clk_freq = self.get_word_clk_freq()
        # platform.add_period_constraint(self.tx_clk, 1e9/word_clk_freq)
        # platform.add_period_constraint(self.rx_clk, 1e9/word_clk_freq)

        # NOTE: Skeleton implementation - full GTYE4_CHANNEL instantiation pending
