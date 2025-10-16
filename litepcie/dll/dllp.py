#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
DLLP (Data Link Layer Packet) implementation.

This module implements DLLP generation and CRC-16 calculation for the
PCIe Data Link Layer.

DLLPs are 8-byte packets used for:
- ACK: Acknowledge successful TLP receipt
- NAK: Request TLP retransmission
- Flow control (not yet implemented)
- Power management (not yet implemented)

References
----------
- PCIe Base Spec 4.0, Section 3.4: Data Link Layer Packets
- PCIe Base Spec 4.0, Section 3.4.2: Ack and Nak DLLPs
- PCIe Base Spec 4.0, Section 3.4.3: DLLP CRC
"""

from litex.gen import *
from migen import *

from litepcie.dll.common import (
    DLLP_CRC16_INITIAL_VALUE,
    DLLP_CRC16_POLYNOMIAL,
    DLLP_TYPE_ACK,
    DLLP_TYPE_NAK,
)

# DLLP CRC-16 Generator ----------------------------------------------------------------------------


class DLLPCRC16Engine(Module):
    """
    CRC-16 Engine using parallel LFSR.

    Computes next CRC-16 value from previous CRC and data input using
    optimized asynchronous LFSR (similar to LiteEth/LiteSATA CRC engines).

    Parameters
    ----------
    data_width : int
        Width of data bus (8 bits for DLLP byte-wise processing)
    width : int
        Width of CRC (16 bits)
    polynom : int
        CRC polynomial (0x100B for DLLP CRC-16)

    Attributes
    ----------
    data : Signal(data_width), input
        Data input
    crc_prev : Signal(width), input
        Previous CRC value
    crc_next : Signal(width), output
        Next CRC value

    Notes
    -----
    This uses the same parallel LFSR approach as LiteEth's CRC-32 engine,
    adapted for CRC-16. The algorithm builds XOR equations for each output
    bit and optimizes them by removing duplicate terms.

    References
    ----------
    - PCIe Base Spec 4.0, Section 3.4.3: DLLP CRC
    - LiteEth MAC CRC Engine implementation
    - "Cyclic Redundancy Check" Wikipedia article
    """

    def __init__(self, data_width, width, polynom):
        self.data = Signal(data_width)
        self.crc_prev = Signal(width)
        self.crc_next = Signal(width)

        # # #

        # Determine bits affected by polynomial
        polynom_taps = [bit for bit in range(width) if (1 << bit) & polynom]

        # Build LFSR equations for parallel CRC calculation
        crc_bits = [[("state", i)] for i in range(width)]
        for n in range(data_width):
            feedback = crc_bits.pop(-1) + [("din", n)]
            for pos in range(width - 1):
                if (pos + 1) in polynom_taps:
                    crc_bits[pos] += feedback
                crc_bits[pos] = self._optimize_xors(crc_bits[pos])
            crc_bits.insert(0, feedback)

        # Generate combinatorial logic for each CRC bit
        for i in range(width):
            xors = []
            for t, n in crc_bits[i]:
                if t == "state":
                    xors += [self.crc_prev[n]]
                elif t == "din":
                    xors += [self.data[n]]
            self.comb += self.crc_next[i].eq(Reduce("XOR", xors))

    @staticmethod
    def _optimize_xors(bits):
        """
        Optimize XOR chains by removing duplicate terms.

        XOR properties: A ^ A = 0, so even occurrences cancel out.
        Only keep bits with odd occurrences.

        Parameters
        ----------
        bits : list
            List of (type, bit_index) tuples

        Returns
        -------
        list
            Optimized list with only odd-occurrence bits
        """
        from collections import Counter

        return [bit for bit, count in Counter(bits).items() if count % 2 == 1]


class DLLPCRC16(Module):
    """
    Hardware CRC-16 generator for DLLPs.

    Implements CRC-16 calculation using parallel LFSR engine, processing
    one byte per cycle.

    Attributes
    ----------
    data_in : Signal(8), input
        Input data byte
    data_valid : Signal(1), input
        Data valid strobe (process data_in on this cycle)
    reset : Signal(1), input
        Reset CRC to initial value
    crc_out : Signal(16), output
        Current CRC value

    Notes
    -----
    - CRC is calculated one byte per cycle when data_valid asserted
    - Reset signal returns CRC to DLLP_CRC16_INITIAL_VALUE (0xFFFF)
    - CRC polynomial: 0x100B
    - Initial value: 0xFFFF

    Examples
    --------
    >>> crc = DLLPCRC16()
    >>> # Feed 6 bytes of DLLP data
    >>> for byte_val in dllp_data:
    ...     yield crc.data_in.eq(byte_val)
    ...     yield crc.data_valid.eq(1)
    ...     yield
    >>> yield crc.data_valid.eq(0)
    >>> final_crc = (yield crc.crc_out)

    References
    ----------
    PCIe Base Spec 4.0, Section 3.4.3: DLLP CRC
    """

    def __init__(self):
        self.data_in = Signal(8)
        self.data_valid = Signal()
        self.reset = Signal()
        self.crc_out = Signal(16, reset=DLLP_CRC16_INITIAL_VALUE)

        # # #

        # CRC engine (parallel LFSR)
        self.submodules.engine = engine = DLLPCRC16Engine(
            data_width=8,
            width=16,
            polynom=DLLP_CRC16_POLYNOMIAL,
        )

        # CRC register
        crc = Signal(16, reset=DLLP_CRC16_INITIAL_VALUE)

        self.sync += [
            If(
                self.reset,
                crc.eq(DLLP_CRC16_INITIAL_VALUE),
            ).Elif(
                self.data_valid,
                crc.eq(engine.crc_next),
            ),
        ]

        self.comb += [
            engine.data.eq(self.data_in),
            engine.crc_prev.eq(crc),
            self.crc_out.eq(crc),
        ]


# DLLP ACK Generator -------------------------------------------------------------------------------


class DLLPAckGenerator(Module):
    """
    ACK DLLP generator.

    Generates ACK DLLPs with sequence number and CRC-16.

    Attributes
    ----------
    seq_num : Signal(12), input
        Sequence number to acknowledge
    generate : Signal(1), input
        Generate ACK DLLP (pulse)
    dllp_valid : Signal(1), output
        DLLP output is valid
    dllp_type : Signal(4), output
        DLLP type field (DLLP_TYPE_ACK)
    dllp_seq_num : Signal(12), output
        DLLP sequence number field
    dllp_crc : Signal(16), output
        DLLP CRC-16 field

    Notes
    -----
    ACK DLLP format (PCIe Spec 3.4.2):
    - Byte 0: Type (0x0) + Reserved
    - Bytes 1-2: Sequence number (12 bits) + Reserved
    - Bytes 3-5: Reserved
    - Bytes 6-7: CRC-16

    Examples
    --------
    >>> ack_gen = DLLPAckGenerator()
    >>> yield ack_gen.seq_num.eq(42)
    >>> yield ack_gen.generate.eq(1)
    >>> yield
    >>> yield ack_gen.generate.eq(0)
    >>> # Wait for dllp_valid
    >>> while not (yield ack_gen.dllp_valid):
    ...     yield

    References
    ----------
    PCIe Base Spec 4.0, Section 3.4.2: Ack DLLP
    """

    def __init__(self):
        self.seq_num = Signal(12)
        self.generate = Signal()

        self.dllp_valid = Signal()
        self.dllp_type = Signal(4)
        self.dllp_seq_num = Signal(12)
        self.dllp_crc = Signal(16)

        # # #

        # CRC generator
        self.submodules.crc = crc = DLLPCRC16()

        # DLLP generation state machine
        self.submodules.fsm = fsm = FSM(reset_state="IDLE")

        byte_count = Signal(3)
        seq_num_latched = Signal(12)

        fsm.act(
            "IDLE",
            self.dllp_valid.eq(0),
            If(
                self.generate,
                NextValue(seq_num_latched, self.seq_num),
                NextValue(byte_count, 0),
                NextState("GENERATE_CRC"),
            ),
        )

        fsm.act(
            "GENERATE_CRC",
            # Feed 6 bytes of DLLP data into CRC
            crc.data_valid.eq(1),
            # Generate appropriate byte based on byte_count
            Case(
                byte_count,
                {
                    0: crc.data_in.eq(DLLP_TYPE_ACK << 4),  # Byte 0: type + reserved
                    1: crc.data_in.eq(seq_num_latched[0:8]),  # Byte 1: seq low
                    2: crc.data_in.eq(seq_num_latched[8:12]),  # Byte 2: seq high + reserved
                    3: crc.data_in.eq(0x00),  # Byte 3: reserved
                    4: crc.data_in.eq(0x00),  # Byte 4: reserved
                    5: crc.data_in.eq(0x00),  # Byte 5: reserved
                },
            ),
            NextValue(byte_count, byte_count + 1),
            If(
                byte_count == 5,
                NextState("OUTPUT"),
            ),
        )

        fsm.act(
            "OUTPUT",
            self.dllp_valid.eq(1),
            self.dllp_type.eq(DLLP_TYPE_ACK),
            self.dllp_seq_num.eq(seq_num_latched),
            self.dllp_crc.eq(crc.crc_out),
            NextState("IDLE"),
        )


# DLLP NAK Generator -------------------------------------------------------------------------------


class DLLPNakGenerator(Module):
    """
    NAK DLLP generator.

    Generates NAK DLLPs with sequence number and CRC-16.

    Attributes
    ----------
    seq_num : Signal(12), input
        Sequence number of last correctly received TLP
    generate : Signal(1), input
        Generate NAK DLLP (pulse)
    dllp_valid : Signal(1), output
        DLLP output is valid
    dllp_type : Signal(4), output
        DLLP type field (DLLP_TYPE_NAK)
    dllp_seq_num : Signal(12), output
        DLLP sequence number field
    dllp_crc : Signal(16), output
        DLLP CRC-16 field

    Notes
    -----
    NAK DLLP format (PCIe Spec 3.4.2):
    - Byte 0: Type (0x1) + Reserved
    - Bytes 1-2: Sequence number (12 bits) + Reserved
    - Bytes 3-5: Reserved
    - Bytes 6-7: CRC-16

    The sequence number indicates the last correctly received TLP.
    Transmitter must replay all TLPs after this sequence.

    Examples
    --------
    >>> nak_gen = DLLPNakGenerator()
    >>> yield nak_gen.seq_num.eq(100)
    >>> yield nak_gen.generate.eq(1)
    >>> yield
    >>> yield nak_gen.generate.eq(0)
    >>> # Wait for dllp_valid
    >>> while not (yield nak_gen.dllp_valid):
    ...     yield

    References
    ----------
    PCIe Base Spec 4.0, Section 3.4.2: Nak DLLP
    """

    def __init__(self):
        self.seq_num = Signal(12)
        self.generate = Signal()

        self.dllp_valid = Signal()
        self.dllp_type = Signal(4)
        self.dllp_seq_num = Signal(12)
        self.dllp_crc = Signal(16)

        # # #

        # CRC generator
        self.submodules.crc = crc = DLLPCRC16()

        # DLLP generation state machine
        self.submodules.fsm = fsm = FSM(reset_state="IDLE")

        byte_count = Signal(3)
        seq_num_latched = Signal(12)

        fsm.act(
            "IDLE",
            self.dllp_valid.eq(0),
            If(
                self.generate,
                NextValue(seq_num_latched, self.seq_num),
                NextValue(byte_count, 0),
                NextState("GENERATE_CRC"),
            ),
        )

        fsm.act(
            "GENERATE_CRC",
            # Feed 6 bytes of DLLP data into CRC
            crc.data_valid.eq(1),
            # Generate appropriate byte based on byte_count
            Case(
                byte_count,
                {
                    0: crc.data_in.eq(DLLP_TYPE_NAK << 4),  # Byte 0: type + reserved
                    1: crc.data_in.eq(seq_num_latched[0:8]),  # Byte 1: seq low
                    2: crc.data_in.eq(seq_num_latched[8:12]),  # Byte 2: seq high + reserved
                    3: crc.data_in.eq(0x00),  # Byte 3: reserved
                    4: crc.data_in.eq(0x00),  # Byte 4: reserved
                    5: crc.data_in.eq(0x00),  # Byte 5: reserved
                },
            ),
            NextValue(byte_count, byte_count + 1),
            If(
                byte_count == 5,
                NextState("OUTPUT"),
            ),
        )

        fsm.act(
            "OUTPUT",
            self.dllp_valid.eq(1),
            self.dllp_type.eq(DLLP_TYPE_NAK),
            self.dllp_seq_num.eq(seq_num_latched),
            self.dllp_crc.eq(crc.crc_out),
            NextState("IDLE"),
        )
