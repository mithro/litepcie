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

    # CRC-16 calculation (iterative bit-by-bit)
    crc = DLLP_CRC16_INITIAL_VALUE
    polynomial = DLLP_CRC16_POLYNOMIAL

    for byte in data:
        crc ^= (byte << 8)  # XOR byte into top 8 bits of CRC
        for _ in range(8):
            if crc & 0x8000:  # Check MSB
                crc = ((crc << 1) ^ polynomial) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF

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
