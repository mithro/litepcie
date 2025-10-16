#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Common definitions for PCIe Data Link Layer.

This module defines constants, layouts, and helper functions used throughout
the DLL implementation.

References
----------
- PCIe Base Spec 4.0, Section 3.3: Data Link Layer
- PCIe Base Spec 4.0, Section 3.4: DLLPs
"""

from migen import *
from litex.gen import *
from litepcie.common import *

# Constants ----------------------------------------------------------------------------------------

# Sequence Numbers (PCIe Spec 3.3.5)
DLL_SEQUENCE_NUM_WIDTH = 12  # Sequence numbers are 12 bits
DLL_SEQUENCE_NUM_MAX = 4095  # Maximum sequence number (2^12 - 1)

# DLLP Types (PCIe Spec 3.4.1)
# These are the 4-bit type field values in DLLP headers
DLLP_TYPE_ACK = 0b0000  # Ack DLLP
DLLP_TYPE_NAK = 0b0001  # Nak DLLP

# DLLP Lengths
DLLP_LENGTH_BYTES = 8  # DLLPs are always 8 bytes (6 bytes data + 2 bytes CRC-16)
DLLP_DATA_LENGTH_BYTES = 6  # DLLP data (excluding CRC-16)

# LCRC (PCIe Spec 3.3.4)
LCRC_WIDTH = 32  # LCRC is 32-bit CRC
LCRC_POLYNOMIAL = 0x04C11DB7  # CRC-32 polynomial (Ethernet polynomial)
LCRC_INITIAL_VALUE = 0xFFFFFFFF  # LCRC initial value
LCRC_RESIDUE_VALUE = 0x2144DF1C  # Expected residue after processing data+CRC (CRC-32 magic number)

# CRC-16 for DLLPs (PCIe Spec 3.4.3)
DLLP_CRC16_WIDTH = 16  # DLLP CRC is 16 bits
DLLP_CRC16_POLYNOMIAL = 0x100B  # CRC-16 polynomial for DLLPs
DLLP_CRC16_INITIAL_VALUE = 0xFFFF  # CRC-16 initial value

# Layouts ------------------------------------------------------------------------------------------

def dllp_layout():
    """
    DLLP (Data Link Layer Packet) layout.

    DLLPs are control packets used for ACK/NAK, flow control, and power management.
    All DLLPs are 8 bytes: 6 bytes data + 2 bytes CRC-16.

    Returns
    -------
    EndpointDescription
        DLLP layout with type, data, and CRC fields

    Notes
    -----
    DLLP structure (PCIe Spec 3.4.1):
    - Byte 0: Type (4 bits) + Reserved (4 bits)
    - Bytes 1-5: Type-specific data
    - Bytes 6-7: CRC-16

    Examples
    --------
    >>> layout = dllp_layout()
    >>> dllp_endpoint = stream.Endpoint(layout)

    References
    ----------
    PCIe Base Spec 4.0, Section 3.4: Data Link Layer Packets
    """
    layout = [
        ("type", 4),  # DLLP type (ACK, NAK, etc.)
        ("data", 40),  # Type-specific data (5 bytes = 40 bits)
        ("crc16", 16),  # CRC-16 over type and data
    ]
    return EndpointDescription(layout)


def ack_dllp_layout():
    """
    ACK DLLP layout (PCIe Spec 3.4.2).

    ACK DLLPs acknowledge successful receipt of TLPs.

    Returns
    -------
    EndpointDescription
        ACK DLLP layout with sequence number field

    Notes
    -----
    ACK DLLP structure:
    - Byte 0: Type=0x0, Reserved
    - Bytes 1-2: AckNak_Seq_Num (12 bits) + Reserved (4 bits)
    - Bytes 3-5: Reserved
    - Bytes 6-7: CRC-16

    The AckNak_Seq_Num indicates the sequence number of the last
    correctly received TLP.

    Examples
    --------
    >>> ack = stream.Endpoint(ack_dllp_layout())
    >>> yield ack.seq_num.eq(42)  # ACK up to sequence 42

    References
    ----------
    PCIe Base Spec 4.0, Section 3.4.2: Ack DLLP
    """
    layout = [
        ("type", 4),  # DLLP type = DLLP_TYPE_ACK (0x0)
        ("seq_num", 12),  # Sequence number being acknowledged
        ("reserved", 24),  # Reserved bits
        ("crc16", 16),  # CRC-16
    ]
    return EndpointDescription(layout)


def nak_dllp_layout():
    """
    NAK DLLP layout (PCIe Spec 3.4.2).

    NAK DLLPs request retransmission of TLPs.

    Returns
    -------
    EndpointDescription
        NAK DLLP layout with sequence number field

    Notes
    -----
    NAK DLLP structure:
    - Byte 0: Type=0x1, Reserved
    - Bytes 1-2: AckNak_Seq_Num (12 bits) + Reserved (4 bits)
    - Bytes 3-5: Reserved
    - Bytes 6-7: CRC-16

    The AckNak_Seq_Num indicates the sequence number of the last
    correctly received TLP. All TLPs after this sequence must be
    retransmitted.

    Examples
    --------
    >>> nak = stream.Endpoint(nak_dllp_layout())
    >>> yield nak.seq_num.eq(42)  # Request replay from sequence 43

    References
    ----------
    PCIe Base Spec 4.0, Section 3.4.2: Nak DLLP
    """
    layout = [
        ("type", 4),  # DLLP type = DLLP_TYPE_NAK (0x1)
        ("seq_num", 12),  # Sequence number of last good TLP
        ("reserved", 24),  # Reserved bits
        ("crc16", 16),  # CRC-16
    ]
    return EndpointDescription(layout)


# Helper Functions ---------------------------------------------------------------------------------

def calculate_dllp_crc16(data):
    """
    Calculate CRC-16 for DLLP.

    This is a software implementation for testing. Hardware implementation
    will be in litepcie/dll/crc.py.

    Parameters
    ----------
    data : list[int]
        DLLP data bytes (must be exactly 6 bytes)

    Returns
    -------
    int
        CRC-16 value (16 bits)

    Raises
    ------
    ValueError
        If data length is not 6 bytes
        If any byte is out of range 0-255

    Notes
    -----
    CRC-16 polynomial: 0x100B
    Initial value: 0xFFFF
    Bit ordering: LSB-first (matches LiteX parallel LFSR convention)

    This implementation processes bits LSB-first (bit 0, then bit 1, etc.)
    to match the hardware parallel LFSR used in LiteX ecosystem. Both
    transmitter and receiver use the same convention for consistency.

    Examples
    --------
    >>> data = [0x00, 0x2A, 0x00, 0x00, 0x00, 0x00]  # ACK DLLP with seq=42
    >>> crc = calculate_dllp_crc16(data)
    >>> print(f"CRC-16: 0x{crc:04X}")

    References
    ----------
    PCIe Base Spec 4.0, Section 3.4.3: DLLP CRC
    """
    if len(data) != DLLP_DATA_LENGTH_BYTES:
        raise ValueError(
            f"DLLP data must be {DLLP_DATA_LENGTH_BYTES} bytes, got {len(data)}"
        )
    if any(b < 0 or b > 255 for b in data):
        raise ValueError("All bytes must be in range 0-255")

    # CRC-16 calculation (LSB-first to match hardware parallel LFSR)
    # This matches the LiteX parallel LFSR convention used in hardware
    crc = DLLP_CRC16_INITIAL_VALUE
    polynomial = DLLP_CRC16_POLYNOMIAL

    # Extract polynomial tap positions
    polynom_taps = [bit for bit in range(16) if (1 << bit) & polynomial]

    # Convert CRC to bit array (LSB first)
    state = [(crc >> i) & 1 for i in range(16)]

    for byte in data:
        # Process each bit LSB-first (bit 0, then bit 1, ... bit 7)
        for bit_idx in range(8):
            din_bit = (byte >> bit_idx) & 1

            # Compute feedback (MSB of state XOR with input bit)
            feedback = state[-1] ^ din_bit

            # Shift state and apply polynomial
            new_state = [feedback]  # New LSB is feedback
            for pos in range(15):  # Positions 0 to 14
                if (pos + 1) in polynom_taps:
                    new_state.append(state[pos] ^ feedback)
                else:
                    new_state.append(state[pos])

            state = new_state

    # Convert bit array back to integer
    crc = 0
    for i, bit in enumerate(state):
        if bit:
            crc |= (1 << i)

    return crc


def verify_dllp_crc16(data, crc):
    """
    Verify CRC-16 for DLLP.

    Parameters
    ----------
    data : list[int]
        DLLP data bytes (6 bytes)
    crc : int
        Received CRC-16 value

    Returns
    -------
    bool
        True if CRC is correct, False otherwise

    Examples
    --------
    >>> data = [0x00, 0x2A, 0x00, 0x00, 0x00, 0x00]
    >>> crc = calculate_dllp_crc16(data)
    >>> verify_dllp_crc16(data, crc)
    True
    >>> verify_dllp_crc16(data, crc + 1)
    False
    """
    expected_crc = calculate_dllp_crc16(data)
    return crc == expected_crc


def calculate_lcrc32(data):
    """
    Calculate LCRC-32 for TLP.

    This is a software implementation for testing. Hardware implementation
    is in litepcie/dll/lcrc.py.

    Parameters
    ----------
    data : list[int]
        TLP data bytes (variable length)

    Returns
    -------
    int
        LCRC-32 value (32 bits)

    Raises
    ------
    ValueError
        If data is empty
        If any byte is out of range 0-255

    Notes
    -----
    LCRC-32 polynomial: 0x04C11DB7 (Ethernet CRC-32)
    Initial value: 0xFFFFFFFF
    Bit ordering: LSB-first (matches LiteX parallel LFSR convention)

    This implementation processes bits LSB-first (bit 0, then bit 1, etc.)
    to match the hardware parallel LFSR used in LiteX ecosystem.

    Examples
    --------
    >>> data = [0xDE, 0xAD, 0xBE, 0xEF]
    >>> crc = calculate_lcrc32(data)
    >>> print(f"LCRC-32: 0x{crc:08X}")

    References
    ----------
    PCIe Base Spec 4.0, Section 3.3.4: LCRC
    """
    if len(data) == 0:
        raise ValueError("LCRC data cannot be empty")
    if any(b < 0 or b > 255 for b in data):
        raise ValueError("All bytes must be in range 0-255")

    # LCRC-32 calculation (LSB-first to match hardware parallel LFSR)
    crc = LCRC_INITIAL_VALUE
    polynomial = LCRC_POLYNOMIAL

    # Extract polynomial tap positions
    polynom_taps = [bit for bit in range(32) if (1 << bit) & polynomial]

    # Convert CRC to bit array (LSB first)
    state = [(crc >> i) & 1 for i in range(32)]

    for byte in data:
        # Process each bit LSB-first (bit 0, then bit 1, ... bit 7)
        for bit_idx in range(8):
            din_bit = (byte >> bit_idx) & 1

            # Compute feedback (MSB of state XOR with input bit)
            feedback = state[-1] ^ din_bit

            # Shift state and apply polynomial
            new_state = [feedback]  # New LSB is feedback
            for pos in range(31):  # Positions 0 to 30
                if (pos + 1) in polynom_taps:
                    new_state.append(state[pos] ^ feedback)
                else:
                    new_state.append(state[pos])

            state = new_state

    # Convert bit array back to integer
    crc = 0
    for i, bit in enumerate(state):
        if bit:
            crc |= (1 << i)

    return crc


def verify_lcrc32(data, crc):
    """
    Verify LCRC-32 for TLP.

    Parameters
    ----------
    data : list[int]
        TLP data bytes
    crc : int
        Received LCRC-32 value

    Returns
    -------
    bool
        True if CRC is correct, False otherwise

    Examples
    --------
    >>> data = [0xDE, 0xAD, 0xBE, 0xEF]
    >>> crc = calculate_lcrc32(data)
    >>> verify_lcrc32(data, crc)
    True
    >>> verify_lcrc32(data, crc + 1)
    False

    References
    ----------
    PCIe Base Spec 4.0, Section 3.3.4: LCRC
    """
    expected_crc = calculate_lcrc32(data)
    return crc == expected_crc
