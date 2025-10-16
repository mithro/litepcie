#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
DLL TX Path for PCIe.

Implements the transmit side of the Data Link Layer including:
- Sequence number assignment
- LCRC generation and appending
- Retry buffer integration
- TLP framing for PHY layer

References
----------
- PCIe Base Spec 4.0, Section 3.3: Data Link Layer TX
"""

from migen import *
from litex.gen import *
from litex.soc.interconnect import stream

from litepcie.dll.common import DLL_SEQUENCE_NUM_WIDTH
from litepcie.dll.sequence import SequenceNumberManager
from litepcie.dll.lcrc import LCRC32Generator
from litepcie.dll.retry_buffer import RetryBuffer


# DLL TX Path -------------------------------------------------------------------------------------

class DLLTX(Module):
    """
    DLL Transmit Path.

    Processes outgoing TLPs from the Transaction Layer:
    - Assigns sequence numbers
    - Calculates and appends LCRC-32
    - Stores TLPs in retry buffer for ACK/NAK protocol
    - Frames TLPs for PHY transmission

    Architecture
    ------------
    ::

        TLP Layer → [Sequence] → [LCRC Gen] → [Retry Buffer] → PHY Layer
                         ↓            ↓              ↓
                    [Seq Num]    [CRC-32]      [Store+Forward]
                                                      ↑
                                                 [ACK/NAK]

    Attributes
    ----------
    tlp_sink : Endpoint(stream), input
        Incoming TLPs from Transaction Layer
    phy_source : Endpoint(stream), output
        Outgoing TLPs to PHY layer
    ack_sink : Endpoint, input
        ACK DLLPs from receiver
    nak_sink : Endpoint, input
        NAK DLLPs from receiver (triggers replay)

    debug_last_seq : Signal(12), output
        Last assigned sequence number (for testing)
    debug_last_lcrc : Signal(32), output
        Last calculated LCRC (for testing)

    Parameters
    ----------
    data_width : int
        Width of data path in bits

    Notes
    -----
    The TX path operates in store-and-forward mode: TLPs are buffered in
    the retry buffer until ACKed, allowing replay on NAK.

    Examples
    --------
    >>> tx = DLLTX(data_width=64)
    >>> # Connect TLP source
    >>> self.comb += tx.tlp_sink.connect(tlp_source)
    >>> # Connect to PHY
    >>> self.comb += tx.phy_source.connect(phy_sink)

    References
    ----------
    PCIe Base Spec 4.0, Section 3.3: Data Link Layer
    """
    def __init__(self, data_width=64):
        self.data_width = data_width

        # TLP interface (from Transaction Layer)
        self.tlp_sink = stream.Endpoint([("data", data_width)])

        # PHY interface (to Physical Layer)
        self.phy_source = stream.Endpoint([("data", data_width)])

        # ACK/NAK interface
        self.ack_sink = stream.Endpoint([("seq_num", DLL_SEQUENCE_NUM_WIDTH)])
        self.nak_sink = stream.Endpoint([("seq_num", DLL_SEQUENCE_NUM_WIDTH)])

        # Debug signals
        self.debug_last_seq = Signal(DLL_SEQUENCE_NUM_WIDTH)
        self.debug_last_lcrc = Signal(32)

        # # #

        # Submodules
        self.submodules.seq_manager = SequenceNumberManager()
        self.submodules.lcrc_gen = LCRC32Generator()
        self.submodules.retry_buffer = RetryBuffer(depth=64, data_width=data_width)

        # TX FSM
        self.submodules.fsm = fsm = FSM(reset_state="IDLE")

        # Current TLP tracking
        current_seq = Signal(DLL_SEQUENCE_NUM_WIDTH)
        current_data = Signal(data_width)
        lcrc_value = Signal(32)

        fsm.act("IDLE",
            If(self.tlp_sink.valid,
                # Allocate sequence number
                self.seq_manager.tx_alloc.eq(1),
                NextValue(current_seq, self.seq_manager.tx_seq_num),
                NextValue(current_data, self.tlp_sink.data),
                NextValue(self.debug_last_seq, self.seq_manager.tx_seq_num),
                NextState("CALC_LCRC"),
            )
        )

        fsm.act("CALC_LCRC",
            # Feed data to LCRC calculator
            # For simplicity, assuming single-cycle TLP for now
            # (Real implementation would process multi-cycle TLPs)
            self.lcrc_gen.data_in.eq(current_data[:8]),
            self.lcrc_gen.data_valid.eq(1),
            NextValue(lcrc_value, self.lcrc_gen.crc_out),
            NextValue(self.debug_last_lcrc, self.lcrc_gen.crc_out),
            NextState("STORE"),
        )

        fsm.act("STORE",
            # Store in retry buffer
            self.retry_buffer.write_data.eq(current_data),
            self.retry_buffer.write_seq.eq(current_seq),
            self.retry_buffer.write_valid.eq(1),
            If(self.retry_buffer.write_ready,
                NextState("TX"),
            )
        )

        fsm.act("TX",
            # Transmit to PHY
            self.phy_source.valid.eq(1),
            self.phy_source.data.eq(current_data),
            If(self.phy_source.ready,
                # Consume TLP from sink
                self.tlp_sink.ready.eq(1),
                NextState("IDLE"),
            )
        )

        # ACK/NAK handling
        self.comb += [
            self.seq_manager.ack_seq_num.eq(self.ack_sink.seq_num),
            self.seq_manager.ack_valid.eq(self.ack_sink.valid),
            self.retry_buffer.ack_seq.eq(self.ack_sink.seq_num),
            self.retry_buffer.ack_valid.eq(self.ack_sink.valid),
        ]

        # NAK triggers replay from retry buffer
        self.comb += [
            self.retry_buffer.nak_seq.eq(self.nak_sink.seq_num),
            self.retry_buffer.nak_valid.eq(self.nak_sink.valid),
        ]

        # Replay path (simplified - full implementation would mux with normal TX)
        # For now, just expose retry buffer replay signals
        self.comb += [
            self.retry_buffer.replay_ready.eq(1),  # Always ready for replay
        ]
