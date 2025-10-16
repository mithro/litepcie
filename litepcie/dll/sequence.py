#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Sequence Number Management for PCIe Data Link Layer.

This module implements sequence number allocation and tracking for the
PCIe ACK/NAK protocol.

Sequence numbers are 12-bit values (0-4095) assigned to each TLP for
reliable delivery. The transmitter assigns sequence numbers, and the
receiver uses them to detect missing or duplicate packets.

References
----------
- PCIe Base Spec 4.0, Section 3.3.5: Sequence Numbers
- PCIe Base Spec 4.0, Section 3.3.6: ACK/NAK Protocol
"""

from migen import *
from litex.gen import *

from litepcie.dll.common import (
    DLL_SEQUENCE_NUM_WIDTH,
    DLL_SEQUENCE_NUM_MAX,
)


# Sequence Number Manager -----------------------------------------------------------------------

class SequenceNumberManager(Module):
    """
    Sequence number manager for PCIe DLL.

    Manages TX sequence number allocation and RX sequence number tracking
    for the ACK/NAK retry protocol.

    Attributes
    ----------
    tx_alloc : Signal(1), input
        Allocate next TX sequence number (assert for one cycle per TLP)
    tx_seq_num : Signal(12), output
        Current TX sequence number (valid when tx_alloc asserted)
    tx_acked_seq : Signal(12), output
        Last sequence number acknowledged by receiver

    rx_seq_num : Signal(12), input
        Received TLP sequence number
    rx_valid : Signal(1), input
        RX TLP valid (process sequence number)
    rx_expected_seq : Signal(12), output
        Next expected RX sequence number
    rx_seq_error : Signal(1), output
        RX sequence error (received != expected)

    ack_seq_num : Signal(12), input
        Sequence number from received ACK DLLP
    ack_valid : Signal(1), input
        ACK DLLP received (update tx_acked_seq)

    Notes
    -----
    Sequence numbers are 12 bits (0-4095) and wrap around.

    TX sequence allocation:
    - Starts at 0 on reset
    - Increments when tx_alloc asserted
    - Wraps from 4095 to 0

    RX sequence tracking:
    - Tracks next expected sequence number
    - Detects out-of-order packets
    - Updates on each valid RX TLP

    ACK tracking:
    - Records last sequence acknowledged by receiver
    - Used by retry buffer to release TLPs

    Examples
    --------
    >>> seq_mgr = SequenceNumberManager()
    >>> # Allocate TX sequence
    >>> yield seq_mgr.tx_alloc.eq(1)
    >>> yield
    >>> seq = (yield seq_mgr.tx_seq_num)  # Get assigned sequence
    >>>
    >>> # Check RX sequence
    >>> yield seq_mgr.rx_seq_num.eq(received_seq)
    >>> yield seq_mgr.rx_valid.eq(1)
    >>> yield
    >>> error = (yield seq_mgr.rx_seq_error)
    >>> if error:
    >>>     # Handle out-of-order packet

    References
    ----------
    PCIe Base Spec 4.0, Section 3.3.5: Sequence Numbers
    """
    def __init__(self):
        # TX interface
        self.tx_alloc = Signal()
        self.tx_seq_num = Signal(DLL_SEQUENCE_NUM_WIDTH)
        self.tx_acked_seq = Signal(DLL_SEQUENCE_NUM_WIDTH)

        # RX interface
        self.rx_seq_num = Signal(DLL_SEQUENCE_NUM_WIDTH)
        self.rx_valid = Signal()
        self.rx_expected_seq = Signal(DLL_SEQUENCE_NUM_WIDTH)
        self.rx_seq_error = Signal()

        # ACK interface
        self.ack_seq_num = Signal(DLL_SEQUENCE_NUM_WIDTH)
        self.ack_valid = Signal()

        # # #

        # TX sequence counter (wraps at 4096)
        tx_counter = Signal(DLL_SEQUENCE_NUM_WIDTH, reset=0)

        # Combinatorially assign current sequence number
        self.comb += self.tx_seq_num.eq(tx_counter)

        # Synchronously increment counter when allocating
        self.sync += [
            If(self.tx_alloc,
                # Wrap at 4096 (PCIe Spec 3.3.5)
                If(tx_counter == DLL_SEQUENCE_NUM_MAX,
                    tx_counter.eq(0),
                ).Else(
                    tx_counter.eq(tx_counter + 1),
                ),
            ),
        ]

        # RX sequence tracker
        rx_expected = Signal(DLL_SEQUENCE_NUM_WIDTH, reset=0)

        self.comb += [
            self.rx_expected_seq.eq(rx_expected),
            # Detect sequence error (received != expected)
            self.rx_seq_error.eq(self.rx_valid & (self.rx_seq_num != rx_expected)),
        ]

        self.sync += [
            If(self.rx_valid,
                # Update expected sequence for next packet
                If(rx_expected == DLL_SEQUENCE_NUM_MAX,
                    rx_expected.eq(0),
                ).Else(
                    rx_expected.eq(rx_expected + 1),
                ),
            ),
        ]

        # ACK sequence tracker
        self.sync += [
            If(self.ack_valid,
                self.tx_acked_seq.eq(self.ack_seq_num),
            ),
        ]
