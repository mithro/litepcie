#!/usr/bin/env python3

#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2025 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
PCIe PIPE Transceiver Base Classes

Common abstraction for FPGA internal transceivers (GTX, GTH, GTY, ECP5 SERDES).
Provides standard PIPE interface to DLL/LTSSM layers.

Based on patterns from:
- usb3_pipe (TX/RX datapath, CDC)
- ECP5-PCIe (reset sequencing)
- LUNA (PIPE compliance, PLL configuration)
"""

from migen import *
from litex.gen import LiteXModule
from litex.soc.interconnect import stream


# PIPETransceiver Base Class --------------------------------------------------------------

class PIPETransceiver(LiteXModule):
    """
    Base class for PCIe PIPE transceivers.

    Provides common interface for GTX, GTH, GTY, ECP5 SERDES.
    Subclasses implement vendor-specific primitives.

    PIPE Interface (matching Phase 3 implementation)
    ------------------------------------------------
    TX Signals:
        tx_data     : Signal(data_width)     - Transmit data from DLL
        tx_datak    : Signal(data_width//8)  - TX K-character flags (1 bit per byte)
        tx_elecidle : Signal()               - TX electrical idle request

    RX Signals:
        rx_data     : Signal(data_width)     - Received data to DLL
        rx_datak    : Signal(data_width//8)  - RX K-character flags (1 bit per byte)
        rx_elecidle : Signal()               - RX electrical idle status
        rx_valid    : Signal()               - RX data valid (no 8b/10b errors)

    Clock Interface
    ---------------
        tx_clk : Signal() - TX word clock (125 MHz Gen1, 250 MHz Gen2)
        rx_clk : Signal() - RX recovered clock

    Control Interface
    -----------------
        reset    : Signal() - Transceiver reset
        tx_ready : Signal() - TX path ready
        rx_ready : Signal() - RX path ready

    Parameters
    ----------
    data_width : int
        PIPE data width in bits (8, 16, or 32)
        8  = 1 byte per cycle
        16 = 2 bytes per cycle (typical for Gen1/Gen2)
        32 = 4 bytes per cycle (Gen3+)

    gen : int
        PCIe generation (1=Gen1 2.5GT/s, 2=Gen2 5.0GT/s, 3=Gen3 8.0GT/s)

    Example
    -------
    # Create GTX transceiver (see xilinx/s7_gtx.py)
    gtx = S7GTXTransceiver(
        platform, pads,
        refclk_pads=platform.request("clk100"),
        refclk_freq=100e6,
        data_width=16,  # 2 bytes per cycle
        gen=1           # Gen1 (2.5 GT/s)
    )

    # Connect to PIPE interface
    self.comb += [
        pipe.tx_data.eq(gtx.tx_data),
        gtx.rx_data.eq(pipe.rx_data),
        # ... more connections
    ]
    """

    def __init__(self, data_width=16, gen=1):
        self.data_width = data_width
        self.gen = gen

        # PIPE TX Interface
        self.tx_data     = Signal(data_width)
        self.tx_datak    = Signal(data_width//8)
        self.tx_elecidle = Signal()

        # PIPE RX Interface
        self.rx_data     = Signal(data_width)
        self.rx_datak    = Signal(data_width//8)
        self.rx_elecidle = Signal()
        self.rx_valid    = Signal()

        # Clock Interface
        self.tx_clk = Signal()
        self.rx_clk = Signal()

        # Control Interface
        self.reset    = Signal()
        self.tx_ready = Signal()
        self.rx_ready = Signal()

        # Speed Control (for Gen1/Gen2 switching)
        # Value: 1=Gen1 (2.5GT/s), 2=Gen2 (5.0GT/s), 3=Gen3 (8.0GT/s)
        self.speed = Signal(2, reset=gen)  # 2 bits to support Gen1/2/3

    def get_line_rate(self):
        """Get line rate in bits per second."""
        return {
            1: 2.5e9,  # Gen1: 2.5 GT/s
            2: 5.0e9,  # Gen2: 5.0 GT/s
            3: 8.0e9,  # Gen3: 8.0 GT/s
        }[self.gen]

    def get_word_clk_freq(self):
        """
        Get word clock frequency in Hz.

        For 8b/10b encoding (Gen1/Gen2):
            word_clk = line_rate / 10
            Gen1: 2.5 GT/s / 10 = 250 MHz
            Gen2: 5.0 GT/s / 10 = 500 MHz

        For 128b/130b encoding (Gen3):
            word_clk = line_rate / 130 * 128
        """
        line_rate = self.get_line_rate()
        if self.gen in [1, 2]:
            # 8b/10b encoding
            return line_rate / 10
        else:
            # 128b/130b encoding (Gen3)
            return line_rate / 130 * 128


# TX/RX Datapath Modules ------------------------------------------------------------------

class TransceiverTXDatapath(Module):
    """
    Common TX datapath pattern - Clock Domain Crossing only.

    Transfers data from sys_clk domain → tx_clk domain. Width conversion
    is NOT needed because the 8b/10b encoder handles the 8→10 bit conversion.

    Architecture:
        sys_clk domain → AsyncFIFO → tx_clk domain

    Parameters
    ----------
    data_width : int
        PIPE data width (8, 16, or 32 bits) - matches PIPETransceiver

    Example
    -------
    # In GTX wrapper:
    self.submodules.tx_datapath = TransceiverTXDatapath(data_width=16)

    # Connect from PIPE interface (sys_clk domain)
    self.comb += [
        self.tx_datapath.sink.data.eq(self.tx_data),
        self.tx_datapath.sink.ctrl.eq(self.tx_datak),
    ]

    # Connect to 8b/10b encoder (tx_clk domain)
    # (read from tx_datapath.source in tx_clk domain)
    """

    def __init__(self, data_width=16):
        ctrl_width = data_width // 8
        self.sink   = stream.Endpoint([("data", data_width), ("ctrl", ctrl_width)])
        self.source = stream.Endpoint([("data", data_width), ("ctrl", ctrl_width)])

        # # #

        # Clock domain crossing: sys → tx
        cdc = stream.AsyncFIFO(
            [("data", data_width), ("ctrl", ctrl_width)],
            depth=8,
            buffered=True
        )
        cdc = ClockDomainsRenamer({"write": "sys", "read": "tx"})(cdc)
        self.submodules.cdc = cdc

        # Connect
        self.comb += [
            self.sink.connect(cdc.sink),
            cdc.source.connect(self.source),
        ]


class TransceiverRXDatapath(Module):
    """
    Common RX datapath pattern - Clock Domain Crossing only.

    Transfers data from rx_clk domain → sys_clk domain. Width conversion
    is NOT needed because the 8b/10b decoder handles the 10→8 bit conversion.

    Architecture:
        rx_clk domain → AsyncFIFO → sys_clk domain

    Parameters
    ----------
    data_width : int
        PIPE data width (8, 16, or 32 bits) - matches PIPETransceiver

    Example
    -------
    # In GTX wrapper:
    self.submodules.rx_datapath = TransceiverRXDatapath(data_width=16)

    # Connect from 8b/10b decoder (rx_clk domain)
    # (write to rx_datapath.sink in rx_clk domain)

    # Connect to PIPE interface (sys_clk domain)
    self.comb += [
        self.rx_data.eq(self.rx_datapath.source.data),
        self.rx_datak.eq(self.rx_datapath.source.ctrl),
    ]
    """

    def __init__(self, data_width=16):
        ctrl_width = data_width // 8
        self.sink   = stream.Endpoint([("data", data_width), ("ctrl", ctrl_width)])
        self.source = stream.Endpoint([("data", data_width), ("ctrl", ctrl_width)])

        # # #

        # Clock domain crossing: rx → sys
        cdc = stream.AsyncFIFO(
            [("data", data_width), ("ctrl", ctrl_width)],
            depth=8,
            buffered=True
        )
        cdc = ClockDomainsRenamer({"write": "rx", "read": "sys"})(cdc)
        self.submodules.cdc = cdc

        # Connect
        self.comb += [
            self.sink.connect(cdc.sink),
            cdc.source.connect(self.source),
        ]


# Reset Sequencer Base Class --------------------------------------------------------------

class TransceiverResetSequencer(Module):
    """
    Base reset sequencer pattern.

    All transceivers require complex reset sequencing:
    1. Initial reset (all blocks in reset)
    2. Release PLL reset, wait for lock
    3. Release TX PCS reset
    4. Wait for RX signal presence
    5. Release RX CDR reset
    6. Wait for CDR lock
    7. Release RX PCS reset
    8. Monitor for errors, restart if needed

    Subclasses implement vendor-specific timing and FSM states.

    Status Inputs
    -------------
        tx_pll_locked : Signal() - TX PLL has locked
        rx_has_signal : Signal() - RX has detected signal
        rx_cdr_locked : Signal() - RX CDR has locked to data

    Reset Outputs
    -------------
        tx_pll_reset : Signal() - TX PLL reset
        tx_pcs_reset : Signal() - TX PCS reset
        rx_cdr_reset : Signal() - RX CDR reset
        rx_pcs_reset : Signal() - RX PCS reset

    Status Outputs
    --------------
        tx_ready : Signal() - TX path ready for operation
        rx_ready : Signal() - RX path ready for operation

    Example
    -------
    # In GTX wrapper:
    self.submodules.reset_seq = GTXResetSequencer(sys_clk_freq)

    # Connect to GTX primitive
    self.comb += [
        self.reset_seq.tx_pll_locked.eq(gtx.pll_lock),
        gtx.tx_pll_reset.eq(self.reset_seq.tx_pll_reset),
        # ... more connections
    ]
    """

    def __init__(self):
        # Status inputs
        self.tx_pll_locked = Signal()
        self.rx_has_signal = Signal()
        self.rx_cdr_locked = Signal()

        # Reset outputs
        self.tx_pll_reset = Signal(reset=1)
        self.tx_pcs_reset = Signal(reset=1)
        self.rx_cdr_reset = Signal(reset=1)
        self.rx_pcs_reset = Signal(reset=1)

        # Status outputs
        self.tx_ready = Signal()
        self.rx_ready = Signal()
