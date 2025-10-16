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

from litex.gen import *
from migen import *

from litepcie.common import *

# PIPE Signal Layouts ------------------------------------------------------------------------------


def pipe_layout_8b(data_width=8):
    """
    PIPE 3.0 signal layout for 8-bit mode (Gen1/Gen2).

    This defines all PIPE signals for a single lane in 8-bit mode.

    Note: Currently defined for future multi-lane PIPE interfaces. Will be used
    when implementing x4/x8/x16 PCIe support.

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
        # TX Interface (MAC -> PHY)
        ("tx_data", data_width, DIR_M_TO_S),
        ("tx_datak", 1, DIR_M_TO_S),
        ("tx_elecidle", 1, DIR_M_TO_S),
        # RX Interface (PHY -> MAC)
        ("rx_data", data_width, DIR_S_TO_M),
        ("rx_datak", 1, DIR_S_TO_M),
        ("rx_valid", 1, DIR_S_TO_M),
        ("rx_status", 3, DIR_S_TO_M),
        ("rx_elecidle", 1, DIR_S_TO_M),
        # Control Interface
        ("powerdown", 2, DIR_M_TO_S),
        ("rate", 1, DIR_M_TO_S),
        ("rx_polarity", 1, DIR_M_TO_S),
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

# PIPE TX Packetizer -------------------------------------------------------------------------------


class PIPETXPacketizer(LiteXModule):
    """
    PIPE TX packetizer (DLL packets → PIPE symbols).

    Converts 64-bit DLL packets to 8-bit PIPE symbols with K-character framing.

    Parameters
    ----------
    None

    Attributes
    ----------
    sink : Endpoint(phy_layout(64)), input
        DLL packets to transmit
    pipe_tx_data : Signal(8), output
        PIPE TX data (8-bit symbol)
    pipe_tx_datak : Signal(1), output
        PIPE TX K-character indicator

    Protocol
    --------
    When sink.valid & sink.first:
        - Determine packet type from sink.dat[0:8]
        - Send STP (0xFB, K=1) for TLP
        - Send SDP (0x5C, K=1) for DLLP
    Then:
        - Send 8 data bytes (K=0) from sink.dat
    Finally:
        - Send END (0xFD, K=1) to mark packet completion
        - EDB (0xFE, K=1) for bad packets not yet implemented

    References
    ----------
    - PCIe Base Spec 4.0, Section 4.2.2: Symbol Encoding
    - PCIe Base Spec 4.0, Section 4.2.3: Framing
    """

    def __init__(self):
        # DLL-facing input (64-bit packets)
        self.sink = stream.Endpoint(phy_layout(64))

        # PIPE-facing output (8-bit symbols)
        self.pipe_tx_data = Signal(8)
        self.pipe_tx_datak = Signal()

        # # #

        # FSM for packetization
        self.submodules.fsm = FSM(reset_state="IDLE")

        # Detect packet type from first byte
        first_byte = Signal(8)
        is_dllp = Signal()
        self.comb += [
            first_byte.eq(self.sink.dat[0:8]),
            # DLLP types: 0x00 (ACK), 0x10 (NAK), 0x20 (PM), 0x30 (Vendor)
            is_dllp.eq((first_byte & 0xC0) == 0x00),
        ]

        # Byte counter for DATA state (0-7 for 8 bytes)
        byte_counter = Signal(3)

        # Array for byte selection (little-endian ordering)
        byte_array = Array(
            [
                self.sink.dat[0:8],  # Byte 0 (LSB)
                self.sink.dat[8:16],  # Byte 1
                self.sink.dat[16:24],  # Byte 2
                self.sink.dat[24:32],  # Byte 3
                self.sink.dat[32:40],  # Byte 4
                self.sink.dat[40:48],  # Byte 5
                self.sink.dat[48:56],  # Byte 6
                self.sink.dat[56:64],  # Byte 7 (MSB)
            ]
        )

        self.fsm.act(
            "IDLE",
            # When packet starts, transition to START and output START symbol
            If(
                self.sink.valid & self.sink.first,
                If(
                    is_dllp,
                    # DLLP: Send SDP (0x5C, K=1)
                    NextValue(self.pipe_tx_data, PIPE_K28_2_SDP),
                    NextValue(self.pipe_tx_datak, 1),
                ).Else(
                    # TLP: Send STP (0xFB, K=1)
                    NextValue(self.pipe_tx_data, PIPE_K27_7_STP),
                    NextValue(self.pipe_tx_datak, 1),
                ),
                NextValue(byte_counter, 0),
                NextState("DATA"),
            ).Else(
                # Default: output idle (data=0, K=0)
                NextValue(self.pipe_tx_data, 0x00),
                NextValue(self.pipe_tx_datak, 0),
            ),
        )

        self.fsm.act(
            "DATA",
            # Transmit data bytes from sink.dat
            # Output current byte (data, not K-character)
            NextValue(self.pipe_tx_data, byte_array[byte_counter]),
            NextValue(self.pipe_tx_datak, 0),
            # Increment byte counter
            NextValue(byte_counter, byte_counter + 1),
            # After 8 bytes (counter reaches 7), transition to END state
            If(byte_counter == 7, NextState("END")),
        )

        self.fsm.act(
            "END",
            # Send END symbol (0xFD, K=1) to mark packet completion
            NextValue(self.pipe_tx_data, PIPE_K29_7_END),
            NextValue(self.pipe_tx_datak, 1),
            NextState("IDLE"),
        )


# PIPE RX Depacketizer -------------------------------------------------------------------------------


class PIPERXDepacketizer(LiteXModule):
    """
    PIPE RX depacketizer (PIPE symbols → DLL packets).

    Converts 8-bit PIPE symbols to 64-bit DLL packets by detecting K-character
    framing and accumulating data bytes.

    Parameters
    ----------
    debug : bool, optional
        Enable debug signals for testing (default: False)

    Attributes
    ----------
    pipe_rx_data : Signal(8), input
        PIPE RX data (8-bit symbol)
    pipe_rx_datak : Signal(1), input
        PIPE RX K-character indicator
    source : Endpoint(phy_layout(64)), output
        DLL packets output
    debug_data_buffer : Signal(64), output (only when debug=True)
        Internal data buffer for test verification

    Protocol
    --------
    When pipe_rx_datak & (pipe_rx_data == STP or SDP):
        - Detect packet start and type
        - Begin accumulating data bytes
    While accumulating:
        - Collect 8 data bytes (K=0) into 64-bit word
    When pipe_rx_datak & (pipe_rx_data == END):
        - Output completed packet on source endpoint
        - Assert source.valid, source.first, source.last

    References
    ----------
    - PCIe Base Spec 4.0, Section 4.2.2: Symbol Encoding
    - PCIe Base Spec 4.0, Section 4.2.3: Framing
    """

    def __init__(self, debug=False):
        # PIPE-facing input (8-bit symbols)
        self.pipe_rx_data = Signal(8)
        self.pipe_rx_datak = Signal()

        # DLL-facing output (64-bit packets)
        self.source = stream.Endpoint(phy_layout(64))

        # # #

        # FSM for depacketization
        self.submodules.fsm = FSM(reset_state="IDLE")

        # Track packet type (TLP vs DLLP)
        is_tlp = Signal()  # 1 for TLP (STP), 0 for DLLP (SDP)

        # Byte counter and data buffer for accumulation
        byte_counter = Signal(3)  # 0-7 for 8 bytes
        data_buffer = Signal(64)  # Accumulate 8-bit symbols into 64-bit word

        # Debug signal (only when debug=True, for testing)
        if debug:
            self.debug_data_buffer = Signal(64)
            self.comb += self.debug_data_buffer.eq(data_buffer)

        self.fsm.act(
            "IDLE",
            # Wait for START symbol
            If(
                self.pipe_rx_datak,
                If(
                    self.pipe_rx_data == PIPE_K27_7_STP,
                    # STP: TLP start detected
                    NextValue(is_tlp, 1),
                    NextValue(byte_counter, 0),  # Reset counter
                    NextState("DATA"),
                ).Elif(
                    self.pipe_rx_data == PIPE_K28_2_SDP,
                    # SDP: DLLP start detected
                    NextValue(is_tlp, 0),
                    NextValue(byte_counter, 0),  # Reset counter
                    NextState("DATA"),
                ),
                # Ignore other K-characters (SKP, COM, etc.)
            ),
        )

        self.fsm.act(
            "DATA",
            # Accumulate data bytes (not K-characters)
            If(
                ~self.pipe_rx_datak,
                # Store byte in little-endian order
                Case(
                    byte_counter,
                    {
                        0: NextValue(data_buffer[0:8], self.pipe_rx_data),
                        1: NextValue(data_buffer[8:16], self.pipe_rx_data),
                        2: NextValue(data_buffer[16:24], self.pipe_rx_data),
                        3: NextValue(data_buffer[24:32], self.pipe_rx_data),
                        4: NextValue(data_buffer[32:40], self.pipe_rx_data),
                        5: NextValue(data_buffer[40:48], self.pipe_rx_data),
                        6: NextValue(data_buffer[48:56], self.pipe_rx_data),
                        7: NextValue(data_buffer[56:64], self.pipe_rx_data),
                    },
                ),
                NextValue(byte_counter, byte_counter + 1),
                # After 8 bytes, stay in DATA state waiting for END symbol
            ).Elif(
                self.pipe_rx_datak,
                # K-character detected - check for END symbol
                If(
                    self.pipe_rx_data == PIPE_K29_7_END,
                    # END symbol detected - output packet on source endpoint
                    self.source.valid.eq(1),
                    self.source.first.eq(1),
                    self.source.last.eq(1),
                    self.source.dat.eq(data_buffer),
                    NextState("IDLE"),
                ),
                # Ignore other K-characters (EDB handling is future work)
            ),
        )


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
        # TX Interface (MAC -> PHY)
        self.pipe_tx_data = Signal(data_width)
        self.pipe_tx_datak = Signal()
        self.pipe_tx_elecidle = Signal()

        # RX Interface (PHY -> MAC)
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
        self.submodules.tx_packetizer = tx_packetizer = PIPETXPacketizer()

        # Connect DLL TX sink to packetizer
        self.comb += self.dll_tx_sink.connect(tx_packetizer.sink)

        # Connect packetizer output to PIPE TX
        self.comb += [
            self.pipe_tx_data.eq(tx_packetizer.pipe_tx_data),
            self.pipe_tx_datak.eq(tx_packetizer.pipe_tx_datak),
        ]

        # When no data, send electrical idle
        self.comb += [
            If(
                ~tx_packetizer.sink.valid,
                self.pipe_tx_elecidle.eq(1),
            )
        ]

        # RX Path: PIPE symbols → DLL packets
        self.submodules.rx_depacketizer = rx_depacketizer = PIPERXDepacketizer()

        # Connect PIPE RX to depacketizer
        self.comb += [
            rx_depacketizer.pipe_rx_data.eq(self.pipe_rx_data),
            rx_depacketizer.pipe_rx_datak.eq(self.pipe_rx_datak),
        ]

        # Connect depacketizer output to DLL RX source
        self.comb += rx_depacketizer.source.connect(self.dll_rx_source)
