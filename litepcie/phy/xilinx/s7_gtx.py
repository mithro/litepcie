#!/usr/bin/env python3

#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2025 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Xilinx 7-Series GTX Transceiver for PCIe

Wraps GTXE2_CHANNEL primitive with PIPE interface, using software 8b/10b
encoding for consistency across platforms.

Reference:
- Xilinx UG476: 7 Series FPGAs GTX/GTH Transceivers User Guide
- usb3_pipe K7USB3SerDes implementation
- LUNA XC7GTXSerDesPIPE

Architecture:
    PIPE Interface (16-bit) → CDC → 8b/10b Encoder → GTX Primitive

For PCIe Gen1/Gen2, we use software 8b/10b encoding (like liteiclink does)
rather than the GTX's built-in hardware 8b/10b. This provides:
- Consistency with ECP5 (which has no hardware 8b/10b)
- Better visibility for debugging
- Same timing characteristics across platforms
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


# GTX PLL Configuration --------------------------------------------------------------------

class GTXChannelPLL(LiteXModule):
    """
    GTX Channel PLL configuration.

    Computes PLL parameters for target line rate from reference clock.

    Parameters
    ----------
    refclk_freq : float
        Reference clock frequency in Hz (typically 100 MHz for PCIe)
    linerate : float
        Target line rate in bits per second
        Gen1: 2.5e9 (2.5 GT/s)
        Gen2: 5.0e9 (5.0 GT/s)

    Reference
    ---------
    Xilinx UG476 Table 3-3: CPLL Configuration

    Example
    -------
    pll = GTXChannelPLL(refclk_freq=100e6, linerate=2.5e9)
    print(f"PLL config: n1={pll.config['n1']}, n2={pll.config['n2']}")
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
        Compute PLL configuration for target line rate.

        For PCIe:
        - Gen1: 2.5 GT/s line rate → 250 MHz word clock (divide by 10 for 8b/10b)
        - Gen2: 5.0 GT/s line rate → 500 MHz word clock

        CPLL VCO Frequency Range: 1.6 GHz to 3.3 GHz

        PLL Equation:
            VCO_freq = refclk_freq * (N1 * N2) / M
            linerate = VCO_freq * 2 / D

        Where:
            N1 ∈ {4, 5}
            N2 ∈ {1, 2, 3, 4, 5}
            M ∈ {1, 2}
            D ∈ {1, 2, 4, 8, 16}

        Returns
        -------
        dict
            Configuration with keys: n1, n2, m, d, vco_freq, linerate

        Raises
        ------
        ValueError
            If no valid configuration found for the given parameters
        """
        for m in [1, 2]:
            for n1 in [4, 5]:
                for n2 in [1, 2, 3, 4, 5]:
                    vco_freq = refclk_freq * (n1 * n2) / m

                    # Check VCO frequency is in valid range
                    if not (1.6e9 <= vco_freq <= 3.3e9):
                        continue

                    for d in [1, 2, 4, 8, 16]:
                        current_linerate = vco_freq * 2 / d

                        if abs(current_linerate - linerate) < 1e6:  # Within 1 MHz tolerance
                            return {
                                "n1": n1,
                                "n2": n2,
                                "m": m,
                                "d": d,
                                "vco_freq": vco_freq,
                                "linerate": current_linerate,
                                "refclk_freq": refclk_freq,
                            }

        raise ValueError(
            f"No valid PLL configuration found for "
            f"refclk={refclk_freq/1e6:.1f} MHz, linerate={linerate/1e9:.1f} GT/s"
        )


# GTX Reset Sequencer ----------------------------------------------------------------------

class GTXResetSequencer(TransceiverResetSequencer):
    """
    GTX-specific reset sequencer.

    Implements Xilinx AR43482 reset sequence:
    1. Wait 50ms after FPGA configuration before any GTX reset
    2. Assert all resets
    3. Release PLL reset, wait for lock
    4. Release TX reset
    5. Release RX reset
    6. Monitor for errors

    Parameters
    ----------
    sys_clk_freq : float
        System clock frequency in Hz (used for timing)

    Reference
    ---------
    Xilinx AR43482: 7 Series FPGAs GTX/GTH Transceivers Reset Sequence
    """

    def __init__(self, sys_clk_freq):
        TransceiverResetSequencer.__init__(self)
        self.sys_clk_freq = sys_clk_freq

        # Calculate cycle counts for timing
        defer_cycles = int(50e-3 * sys_clk_freq)  # 50ms defer (AR43482)
        pll_lock_timeout = int(1e-3 * sys_clk_freq)  # 1ms timeout

        # # #

        # Defer counter (AR43482 requirement)
        defer_timer = Signal(max=defer_cycles)
        defer_done = Signal()

        # PLL lock timeout
        pll_timer = Signal(max=pll_lock_timeout)

        # FSM
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
            self.tx_pll_reset.eq(0),  # Release PLL reset
            self.tx_pcs_reset.eq(1),
            self.rx_cdr_reset.eq(1),
            self.rx_pcs_reset.eq(1),
            NextValue(pll_timer, pll_timer + 1),
            If(self.tx_pll_locked,
                NextState("RELEASE_TX")
            ).Elif(pll_timer == (pll_lock_timeout - 1),
                NextState("INIT_RESET")  # Retry if timeout
            )
        )
        self.fsm.act("RELEASE_TX",
            self.tx_pll_reset.eq(0),
            self.tx_pcs_reset.eq(0),  # Release TX reset
            self.rx_cdr_reset.eq(1),
            self.rx_pcs_reset.eq(1),
            self.tx_ready.eq(1),
            NextState("RELEASE_RX")
        )
        self.fsm.act("RELEASE_RX",
            self.tx_pll_reset.eq(0),
            self.tx_pcs_reset.eq(0),
            self.rx_cdr_reset.eq(0),
            self.rx_pcs_reset.eq(0),  # Release RX reset
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
            # Stay in READY state (could add error monitoring here)
        )


# 7-Series GTX Transceiver -----------------------------------------------------------------

class S7GTXTransceiver(PIPETransceiver):
    """
    Xilinx 7-Series GTX transceiver for PCIe.

    Wraps GTXE2_CHANNEL primitive with PIPE interface, using software 8b/10b
    encoding for consistency across platforms.

    Parameters
    ----------
    platform : Platform
        LiteX platform for constraints and pad requests
    pads : Record
        Differential TX/RX pads (tx_p, tx_n, rx_p, rx_n)
    refclk_pads : Record or Signal
        Reference clock input (100 MHz typical for PCIe)
    refclk_freq : float
        Reference clock frequency in Hz
    sys_clk_freq : float
        System clock frequency in Hz (for reset sequencing)
    data_width : int
        PIPE data width (8, 16, or 32 bits)
        Typical: 16 (2 bytes per cycle for Gen1/Gen2)
    gen : int
        PCIe generation (1=Gen1 2.5GT/s, 2=Gen2 5.0GT/s)

    Example
    -------
    # In your SoC:
    gtx = S7GTXTransceiver(
        platform=platform,
        pads=platform.request("pcie_x1"),
        refclk_pads=platform.request("pcie_refclk"),
        refclk_freq=100e6,
        sys_clk_freq=125e6,
        data_width=16,
        gen=1
    )

    # Connect to PIPE interface
    self.comb += [
        pipe.tx_data.eq(gtx.tx_data),
        gtx.rx_data.eq(pipe.rx_data),
        # ...
    ]

    Reference
    ---------
    - Xilinx UG476: 7 Series FPGAs GTX/GTH Transceivers
    - usb3_pipe: K7USB3SerDes implementation
    - Phase 9 Plan: Task 9.3
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
        nwords = data_width // 8  # Number of bytes

        # # #

        # Reference Clock
        # ---------------
        if isinstance(refclk_pads, (Signal, ClockSignal)):
            refclk = refclk_pads
        else:
            refclk = Signal()
            self.specials += Instance("IBUFDS_GTE2",
                i_CEB = 0,
                i_I   = refclk_pads.p,
                i_IB  = refclk_pads.n,
                o_O   = refclk
            )

        # PLL
        # ---
        pll = GTXChannelPLL(refclk_freq, linerate)
        self.submodules.pll = pll

        # 8b/10b Encoder/Decoder (Software - for ALL platforms)
        # -------------------------------------------------------
        # We use software 8b/10b for consistency (like liteiclink does)
        self.submodules.encoder = ClockDomainsRenamer("tx")(
            Encoder(nwords=nwords, lsb_first=True)
        )
        self.submodules.decoder = ClockDomainsRenamer("rx")(
            Decoder(lsb_first=True)
        )

        # TX/RX Datapaths (Clock Domain Crossing)
        # ----------------------------------------
        self.submodules.tx_datapath = TransceiverTXDatapath(data_width=data_width)
        self.submodules.rx_datapath = TransceiverRXDatapath(data_width=data_width)

        # Reset Sequencer
        # ---------------
        self.submodules.reset_seq = GTXResetSequencer(sys_clk_freq)

        # GTX Primitive Instantiation
        # ----------------------------
        # (Will be completed in next step - this is a stub for now)
        # TODO: Add full GTXE2_CHANNEL instantiation with ~100 parameters

        # Clock Domains
        # -------------
        self.clock_domains.cd_tx = ClockDomain("tx")
        self.clock_domains.cd_rx = ClockDomain("rx")

        # For now, use stub clocks (will connect to GTX TXOUTCLK/RXOUTCLK)
        # self.comb += [
        #     ClockSignal("tx").eq(self.tx_clk),
        #     ClockSignal("rx").eq(self.rx_clk),
        # ]

        # Platform Constraints
        # --------------------
        word_clk_freq = self.get_word_clk_freq()
        # platform.add_period_constraint(self.tx_clk, 1e9/word_clk_freq)
        # platform.add_period_constraint(self.rx_clk, 1e9/word_clk_freq)

        # Connections (to be implemented)
        # --------------------------------
        # TODO: Connect PIPE interface → tx_datapath → encoder → GTX
        # TODO: Connect GTX → decoder → rx_datapath → PIPE interface
        # TODO: Connect reset sequencer to GTX resets

        # NOTE: This is a skeleton implementation. Full GTX primitive
        # instantiation requires ~100 parameters and careful configuration.
        # See Phase 9 Plan Task 9.3 Steps 3-5 for complete implementation.
