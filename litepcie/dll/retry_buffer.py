#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Retry Buffer for PCIe DLL ACK/NAK Protocol.

The retry buffer stores transmitted TLPs until they are acknowledged by
the receiver. On NAK reception, all TLPs after the NAKed sequence number
are retransmitted.

References
----------
- PCIe Base Spec 4.0, Section 3.3.7: Retry Buffer
- "PCI Express System Architecture" Chapter 8: Data Link Layer
"""

from litex.gen import *
from migen import *

from litepcie.dll.common import DLL_SEQUENCE_NUM_WIDTH

# Retry Buffer ------------------------------------------------------------------------------------


class RetryBuffer(Module):
    """
    Circular buffer for TLP retry on NAK.

    Stores transmitted TLPs with their sequence numbers. When ACK received,
    releases entries. When NAK received, replays from NAK sequence + 1.

    Architecture
    ------------
    ::

        TX TLPs → [Write Port] → [Circular Buffer] → [Read Port] → Replay TLPs
                       ↓                                    ↑
                  [Sequence Tags]                     [NAK Trigger]
                       ↓
                  [ACK Release]

    The buffer is implemented as a circular FIFO with sequence number tagging.

    Attributes
    ----------
    write_data : Signal(data_width), input
        TLP data to store
    write_seq : Signal(12), input
        Sequence number of TLP
    write_valid : Signal(1), input
        Write enable
    write_ready : Signal(1), output
        Buffer can accept data

    ack_seq : Signal(12), input
        Sequence number from ACK DLLP
    ack_valid : Signal(1), input
        ACK received

    nak_seq : Signal(12), input
        Sequence number from NAK DLLP
    nak_valid : Signal(1), input
        NAK received (triggers replay)

    replay_data : Signal(data_width), output
        Replayed TLP data
    replay_seq : Signal(12), output
        Sequence number of replay
    replay_valid : Signal(1), output
        Replay data valid
    replay_ready : Signal(1), input
        Downstream ready for replay

    empty : Signal(1), output
        Buffer is empty (all TLPs ACKed)
    full : Signal(1), output
        Buffer is full (cannot accept more TLPs)
    count : Signal(log2_int(depth)), output
        Number of entries in buffer

    Parameters
    ----------
    depth : int
        Number of TLP slots (must be power of 2)
    data_width : int
        Width of TLP data in bits

    Notes
    -----
    The buffer depth should be sized based on:
    - Round-trip latency of the link
    - Desired throughput
    - Maximum outstanding TLPs

    Typical values: 64-256 entries for high-performance links.

    Examples
    --------
    >>> retry_buf = RetryBuffer(depth=64, data_width=128)
    >>> # Store TLP
    >>> yield retry_buf.write_data.eq(tlp_data)
    >>> yield retry_buf.write_seq.eq(seq_num)
    >>> yield retry_buf.write_valid.eq(1)
    >>> yield
    >>> # ACK TLP
    >>> yield retry_buf.ack_seq.eq(seq_num)
    >>> yield retry_buf.ack_valid.eq(1)
    >>> yield

    References
    ----------
    PCIe Base Spec 4.0, Section 3.3.7: Retry Buffer
    """

    def __init__(self, depth=64, data_width=64):
        assert depth & (depth - 1) == 0, "Depth must be power of 2"

        self.depth = depth
        self.data_width = data_width

        # Write interface
        self.write_data = Signal(data_width)
        self.write_seq = Signal(DLL_SEQUENCE_NUM_WIDTH)
        self.write_valid = Signal()
        self.write_ready = Signal()

        # ACK interface
        self.ack_seq = Signal(DLL_SEQUENCE_NUM_WIDTH)
        self.ack_valid = Signal()

        # NAK interface
        self.nak_seq = Signal(DLL_SEQUENCE_NUM_WIDTH)
        self.nak_valid = Signal()

        # Replay interface
        self.replay_data = Signal(data_width)
        self.replay_seq = Signal(DLL_SEQUENCE_NUM_WIDTH)
        self.replay_valid = Signal()
        self.replay_ready = Signal()

        # Status
        self.empty = Signal()
        self.full = Signal()
        self.count = Signal(max=depth)

        # # #

        # Storage: Dual-port RAM for data + sequence numbers
        self.specials.data_mem = Memory(data_width, depth)
        self.specials.seq_mem = Memory(DLL_SEQUENCE_NUM_WIDTH, depth)

        data_write_port = self.data_mem.get_port(write_capable=True)
        data_read_port = self.data_mem.get_port(async_read=True)
        seq_write_port = self.seq_mem.get_port(write_capable=True)
        seq_read_port = self.seq_mem.get_port(async_read=True)

        self.specials += data_write_port, data_read_port
        self.specials += seq_write_port, seq_read_port

        # Pointers
        write_ptr = Signal(max=depth)
        read_ptr = Signal(max=depth)
        ack_ptr = Signal(max=depth)  # Points to next entry to ACK

        # Write logic
        self.comb += [
            data_write_port.adr.eq(write_ptr),
            data_write_port.dat_w.eq(self.write_data),
            data_write_port.we.eq(self.write_valid & self.write_ready),
            seq_write_port.adr.eq(write_ptr),
            seq_write_port.dat_w.eq(self.write_seq),
            seq_write_port.we.eq(self.write_valid & self.write_ready),
        ]

        self.sync += [If(self.write_valid & self.write_ready, write_ptr.eq(write_ptr + 1))]

        # Read logic for replay
        self.comb += [
            data_read_port.adr.eq(read_ptr),
            self.replay_data.eq(data_read_port.dat_r),
            seq_read_port.adr.eq(read_ptr),
            self.replay_seq.eq(seq_read_port.dat_r),
        ]

        # Replay control
        replaying = Signal()
        self.comb += self.replay_valid.eq(replaying & (read_ptr != write_ptr))

        self.sync += [
            If(
                self.nak_valid,
                # NAK triggers replay mode
                read_ptr.eq(ack_ptr),
                replaying.eq(1),
            ).Elif(
                self.replay_valid & self.replay_ready,
                # Advance read pointer during replay
                read_ptr.eq(read_ptr + 1),
                # Stop replaying when caught up with write pointer
                If(
                    read_ptr + 1 == write_ptr,
                    replaying.eq(0),
                ),
            ),
        ]

        # ACK logic - advance ack_ptr
        self.sync += [
            If(
                self.ack_valid,
                # Advance ack pointer to release acknowledged entries
                ack_ptr.eq(ack_ptr + 1),
            )
        ]

        # Status signals
        # For full condition, need to handle wraparound properly
        # Create next_write_ptr with same bit width as ack_ptr
        next_write_ptr = Signal(max=depth)
        self.comb += [
            # Handle wraparound for next write pointer
            If(
                write_ptr == (depth - 1),
                next_write_ptr.eq(0),
            ).Else(
                next_write_ptr.eq(write_ptr + 1),
            ),
            self.empty.eq(write_ptr == ack_ptr),
            self.full.eq(next_write_ptr == ack_ptr),
            self.count.eq(write_ptr - ack_ptr),
            self.write_ready.eq(~self.full),
        ]
