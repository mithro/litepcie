#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
PIPE Interface Abstraction for PCIe.

This module implements the MAC side of PIPE (PHY Interface for PCI Express),
providing an abstraction layer between the DLL and PHY hardware.

The PIPE interface supports:
- External PIPE PHY chips (handles 8b/10b, ordered sets, physical layer)
- Internal transceivers wrapped with PIPE protocol (future)

References
----------
- Intel PIPE 3.0 Specification
- PCIe Base Spec 4.0, Section 4: Physical Layer
- docs/pipe-interface-spec.md
"""

from migen import *
from litex.gen import *
from litepcie.common import *

# PIPE Signal Layouts ------------------------------------------------------------------------------

def pipe_layout_8b(data_width=8):
    """
    PIPE 3.0 signal layout for 8-bit mode (Gen1/Gen2).

    This defines all PIPE signals for a single lane in 8-bit mode.

    Parameters
    ----------
    data_width : int
        PIPE data width (8 for basic PIPE 3.0)

    Returns
    -------
    list
        PIPE signal layout

    Notes
    -----
    For Gen1 (2.5 GT/s), PCLK = 125 MHz
    For Gen2 (5.0 GT/s), PCLK = 250 MHz

    References
    ----------
    Intel PIPE 3.0 Specification, Section 3: Signal Descriptions
    docs/pipe-interface-spec.md
    """
    return [
        # TX Interface (MAC � PHY)
        ("tx_data",     data_width, DIR_M_TO_S),
        ("tx_datak",    1,          DIR_M_TO_S),
        ("tx_elecidle", 1,          DIR_M_TO_S),

        # RX Interface (PHY � MAC)
        ("rx_data",     data_width, DIR_S_TO_M),
        ("rx_datak",    1,          DIR_S_TO_M),
        ("rx_valid",    1,          DIR_S_TO_M),
        ("rx_status",   3,          DIR_S_TO_M),
        ("rx_elecidle", 1,          DIR_S_TO_M),

        # Control Interface
        ("powerdown",   2,          DIR_M_TO_S),
        ("rate",        1,          DIR_M_TO_S),
        ("rx_polarity", 1,          DIR_M_TO_S),
    ]

# PIPE Constants -----------------------------------------------------------------------------------

# RxStatus codes (Intel PIPE 3.0 Specification, Section 3.3.3)
PIPE_RXSTATUS_NORMAL = 0b000
PIPE_RXSTATUS_DISPARITY_ERROR = 0b011
PIPE_RXSTATUS_DECODE_ERROR = 0b100
PIPE_RXSTATUS_ELASTIC_OVERFLOW = 0b101
PIPE_RXSTATUS_ELASTIC_UNDERFLOW = 0b110

# PowerDown states
PIPE_POWERDOWN_P0 = 0b00  # Full power
PIPE_POWERDOWN_P0S = 0b01  # Power savings
PIPE_POWERDOWN_P1 = 0b10  # Low power
PIPE_POWERDOWN_P2 = 0b11  # Lowest power

# Rate (speed) selection
PIPE_RATE_GEN1 = 0  # 2.5 GT/s
PIPE_RATE_GEN2 = 1  # 5.0 GT/s

# K-characters (8b/10b special codes)
# PCIe uses these for ordered sets
PIPE_K28_5_COM = 0xBC  # Comma (alignment)
PIPE_K28_0_SKP = 0x1C  # Skip (clock compensation)
PIPE_K23_7_PAD = 0xF7  # Pad
PIPE_K27_7_STP = 0xFB  # Start TLP
PIPE_K28_2_SDP = 0x5C  # Start DLLP
PIPE_K29_7_END = 0xFD  # End packet
PIPE_K30_7_EDB = 0xFE  # End bad packet

# PIPE Interface -----------------------------------------------------------------------------------

class PIPEInterface(LiteXModule):
    """
    PIPE interface abstraction (MAC side).

    Provides abstraction between DLL packet-based interface and PIPE raw signals.
    Handles:
    - TX: Converting DLL packets to PIPE symbols
    - RX: Converting PIPE symbols to DLL packets
    - Control: Power management, rate control
    - Status: Error detection and reporting

    Parameters
    ----------
    data_width : int
        PIPE data width (8 for PIPE 3.0 8-bit mode)
    gen : int
        PCIe generation (1 for Gen1/2.5GT/s, 2 for Gen2/5.0GT/s)

    Attributes
    ----------
    dll_tx_sink : Endpoint(phy_layout), input
        TX packets from DLL layer
    dll_rx_source : Endpoint(phy_layout), output
        RX packets to DLL layer

    pipe_tx_data : Signal(data_width), output
        PIPE TX data
    pipe_tx_datak : Signal(1), output
        PIPE TX K-character indicator
    pipe_tx_elecidle : Signal(1), output
        PIPE TX electrical idle request

    pipe_rx_data : Signal(data_width), input
        PIPE RX data
    pipe_rx_datak : Signal(1), input
        PIPE RX K-character indicator
    pipe_rx_valid : Signal(1), input
        PIPE RX data valid
    pipe_rx_status : Signal(3), input
        PIPE RX status
    pipe_rx_elecidle : Signal(1), input
        PIPE RX electrical idle detected

    pipe_powerdown : Signal(2), output
        PIPE power state control
    pipe_rate : Signal(1), output
        PIPE rate/speed control
    pipe_rx_polarity : Signal(1), output
        PIPE RX polarity inversion

    Examples
    --------
    >>> pipe = PIPEInterface(data_width=8, gen=1)
    >>> # Connect DLL layer
    >>> self.comb += dll.tx_source.connect(pipe.dll_tx_sink)
    >>> self.comb += pipe.dll_rx_source.connect(dll.rx_sink)
    >>> # Connect to external PIPE PHY chip
    >>> self.comb += [
    ...     phy_pads.tx_data.eq(pipe.pipe_tx_data),
    ...     phy_pads.tx_datak.eq(pipe.pipe_tx_datak),
    ...     pipe.pipe_rx_data.eq(phy_pads.rx_data),
    ...     pipe.pipe_rx_datak.eq(phy_pads.rx_datak),
    ... ]

    References
    ----------
    - Intel PIPE 3.0 Specification
    - PCIe Base Spec 4.0, Section 4: Physical Layer
    - docs/pipe-interface-spec.md
    """
    def __init__(self, data_width=8, gen=1):
        if data_width != 8:
            raise ValueError("Only 8-bit PIPE mode supported currently")
        if gen not in [1, 2]:
            raise ValueError("Only Gen1/Gen2 supported currently")

        # DLL-facing interface (packet-based)
        self.dll_tx_sink = stream.Endpoint(phy_layout(data_width * 8))  # 64-bit TLP data
        self.dll_rx_source = stream.Endpoint(phy_layout(data_width * 8))

        # PIPE-facing interface (raw signals)
        # TX Interface (MAC � PHY)
        self.pipe_tx_data = Signal(data_width)
        self.pipe_tx_datak = Signal()
        self.pipe_tx_elecidle = Signal()

        # RX Interface (PHY � MAC)
        self.pipe_rx_data = Signal(data_width)
        self.pipe_rx_datak = Signal()
        self.pipe_rx_valid = Signal()
        self.pipe_rx_status = Signal(3)
        self.pipe_rx_elecidle = Signal()

        # Control Interface
        self.pipe_powerdown = Signal(2, reset=PIPE_POWERDOWN_P0)  # Start in P0
        self.pipe_rate = Signal(reset=PIPE_RATE_GEN1 if gen == 1 else PIPE_RATE_GEN2)
        self.pipe_rx_polarity = Signal()

        # # #

        # TX Path: DLL packets → PIPE symbols
        # When no data from DLL, send electrical idle
        self.comb += [
            self.pipe_tx_elecidle.eq(~self.dll_tx_sink.valid),
        ]

        # TODO: Implement actual TX data path
        # TODO: Implement RX path (PIPE symbols → DLL packets)
