#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
PCIe LTSSM (Link Training and Status State Machine).

Manages link initialization, training, speed negotiation, and status monitoring
according to the PCIe specification.

References
----------
- PCIe Base Spec 4.0, Section 4.2.5: LTSSM
- Intel PIPE 3.0 Specification
"""

from litex.gen import LiteXModule
from migen import *


class LTSSM(LiteXModule):
    """
    PCIe Link Training and Status State Machine.

    Implements the LTSSM states for Gen1 x1 operation:
    - DETECT: Receiver detection
    - POLLING: TS1/TS2 exchange for negotiation
    - CONFIGURATION: Configure link parameters
    - L0: Normal operation
    - RECOVERY: Error handling

    Parameters
    ----------
    gen : int, optional
        PCIe generation (1=Gen1 2.5GT/s, 2=Gen2 5.0GT/s), default: 1
    lanes : int, optional
        Number of lanes (1, 4, 8, 16), default: 1

    Attributes
    ----------
    link_up : Signal(1), output
        Link is trained and in L0 state
    current_state : Signal(3), output
        Current LTSSM state (for debug)
    link_speed : Signal(2), output
        Negotiated link speed (1=Gen1, 2=Gen2)
    link_width : Signal(5), output
        Negotiated link width (number of lanes)

    PIPE Control (outputs to PIPE interface):
    send_ts1 : Signal(1), output
        Assert to send TS1 ordered set
    send_ts2 : Signal(1), output
        Assert to send TS2 ordered set
    tx_elecidle : Signal(1), output
        TX electrical idle control
    powerdown : Signal(2), output
        PIPE powerdown state

    PIPE Status (inputs from PIPE interface):
    ts1_detected : Signal(1), input
        TS1 ordered set detected on RX
    ts2_detected : Signal(1), input
        TS2 ordered set detected on RX
    rx_elecidle : Signal(1), input
        RX electrical idle status

    References
    ----------
    PCIe Base Spec 4.0, Section 4.2.5: LTSSM State Descriptions
    """

    # LTSSM State Definitions (PCIe Spec Section 4.2.5.2)
    DETECT = 0
    POLLING = 1
    CONFIGURATION = 2
    L0 = 3
    RECOVERY = 4
    RECOVERY_SPEED = 5  # Speed change substate

    def __init__(self, gen=1, lanes=1):
        # Link status outputs
        self.link_up = Signal()
        self.current_state = Signal(3)
        self.link_speed = Signal(2, reset=1)  # Always start at Gen1
        self.link_width = Signal(5, reset=lanes)

        # PIPE control outputs (to PIPE TX)
        self.send_ts1 = Signal()
        self.send_ts2 = Signal()
        self.tx_elecidle = Signal(reset=1)  # Start in electrical idle
        self.powerdown = Signal(2)

        # PIPE status inputs (from PIPE RX)
        self.ts1_detected = Signal()
        self.ts2_detected = Signal()
        self.rx_elecidle = Signal()

        # Gen2 speed negotiation support
        self.gen2_capable = Signal(reset=1 if gen >= 2 else 0)
        self.ts_rate_id = Signal(5, reset=gen)  # Rate ID to advertise in TS1/TS2
        self.rx_rate_id = Signal(5)  # Rate ID received from partner
        self.speed_change_required = Signal()  # Need to change speed

        # Detect if partner supports same or higher speed
        self.comb += [
            self.speed_change_required.eq(
                self.gen2_capable &
                (self.rx_rate_id >= 2) &
                (self.link_speed == 1)  # Currently at Gen1
            ),
        ]

        # Multi-lane support
        self.num_lanes = lanes
        self.configured_lanes = Signal(5)  # Actual lanes configured
        self.rx_link_width = Signal(5)  # Width advertised by partner

        # Per-lane TS configuration
        self.ts_lane_number = Array([Signal(5) for _ in range(lanes)])
        for i in range(lanes):
            self.comb += self.ts_lane_number[i].eq(i)

        # Lane negotiation: use minimum of our lanes and partner's
        negotiated_width = Signal(5)
        self.comb += [
            negotiated_width.eq(
                Mux(self.rx_link_width < self.num_lanes,
                    self.rx_link_width,
                    self.num_lanes
                )
            ),
        ]

        # Lane reversal detection
        self.lane_reversal = Signal()
        self.rx_lane_numbers = Array([Signal(5) for _ in range(lanes)])
        self.logical_lane_map = Array([Signal(5) for _ in range(lanes)])

        # Detect lane reversal:
        # Normal: rx_lane_numbers = [0, 1, 2, 3]
        # Reversed: rx_lane_numbers = [3, 2, 1, 0]
        if lanes > 1:
            self.comb += [
                self.lane_reversal.eq(
                    self.rx_lane_numbers[0] == (lanes - 1)
                ),
            ]

            # Create logical lane mapping
            for i in range(lanes):
                self.comb += [
                    self.logical_lane_map[i].eq(
                        Mux(self.lane_reversal,
                            (lanes - 1 - i),  # Reversed
                            i                 # Normal
                        )
                    ),
                ]
        else:
            # Single lane cannot be reversed
            self.comb += [
                self.lane_reversal.eq(0),
                self.logical_lane_map[0].eq(0),
            ]

        # # #

        # LTSSM State Machine
        self.submodules.fsm = FSM(reset_state="DETECT")

        # DETECT State - Receiver Detection
        # Reference: PCIe Spec 4.0, Section 4.2.5.3.1
        self.fsm.act(
            "DETECT",
            # In DETECT, TX is in electrical idle
            NextValue(self.tx_elecidle, 1),
            NextValue(self.link_up, 0),
            NextValue(self.current_state, self.DETECT),
            # Transition to POLLING when receiver detected (rx_elecidle goes low)
            If(
                ~self.rx_elecidle,
                NextState("POLLING"),
            ),
        )

        # POLLING State - TS1/TS2 Exchange for Speed/Lane Negotiation
        # Reference: PCIe Spec 4.0, Section 4.2.5.3.2
        self.fsm.act(
            "POLLING",
            NextValue(self.current_state, self.POLLING),
            # Exit electrical idle and start sending TS1
            NextValue(self.tx_elecidle, 0),
            NextValue(self.send_ts1, 1),
            NextValue(self.send_ts2, 0),
            # Transition to CONFIGURATION when we receive TS1 from partner
            # (indicates both sides are sending TS1 successfully)
            If(
                self.ts1_detected,
                NextState("CONFIGURATION"),
            ),
        )

        # CONFIGURATION State - TS2 Exchange and Link Parameter Finalization
        # Reference: PCIe Spec 4.0, Section 4.2.5.3.4
        self.fsm.act(
            "CONFIGURATION",
            NextValue(self.current_state, self.CONFIGURATION),
            # Send TS2 ordered sets (stop sending TS1)
            NextValue(self.send_ts1, 0),
            NextValue(self.send_ts2, 1),
            NextValue(self.tx_elecidle, 0),
            # Lock in negotiated lane count
            NextValue(self.configured_lanes, negotiated_width),
            NextValue(self.link_width, negotiated_width),
            # Transition to L0 when we receive TS2 from partner
            # (indicates both sides have completed configuration)
            If(
                self.ts2_detected,
                NextState("L0"),
            ),
        )

        # L0 State - Normal Operation (Link Up)
        # Reference: PCIe Spec 4.0, Section 4.2.5.3.5
        self.fsm.act(
            "L0",
            NextValue(self.current_state, self.L0),
            # Link is up and operational
            NextValue(self.link_up, 1),
            # Stop sending training sequences
            NextValue(self.send_ts1, 0),
            NextValue(self.send_ts2, 0),
            NextValue(self.tx_elecidle, 0),
            # If speed change required, enter RECOVERY.Speed
            If(
                self.speed_change_required,
                NextState("RECOVERY_SPEED"),
            # Monitor for link errors
            # If rx goes to electrical idle unexpectedly, enter RECOVERY
            ).Elif(
                self.rx_elecidle,
                NextState("RECOVERY"),
            ),
        )

        # RECOVERY State - Error Recovery and Link Retraining
        # Reference: PCIe Spec 4.0, Section 4.2.5.3.7
        self.fsm.act(
            "RECOVERY",
            NextValue(self.current_state, self.RECOVERY),
            # Link is down during recovery
            NextValue(self.link_up, 0),
            # Send TS1 to attempt retraining
            NextValue(self.send_ts1, 1),
            NextValue(self.send_ts2, 0),
            NextValue(self.tx_elecidle, 0),
            # Wait for partner to exit electrical idle and respond with TS1
            # Simplified recovery: if we receive TS1, return to L0
            # (Full spec would go through POLLING/CONFIGURATION again)
            If(
                (~self.rx_elecidle) & self.ts1_detected,
                NextState("L0"),
            ),
        )

        # RECOVERY.Speed State - Speed Change
        # Reference: PCIe Spec 4.0, Section 4.2.6.2.1: Speed Change
        self.fsm.act(
            "RECOVERY_SPEED",
            NextValue(self.current_state, self.RECOVERY_SPEED),
            NextValue(self.link_up, 0),
            # Change link speed to Gen2
            NextValue(self.link_speed, 2),
            # Send TS1 at new speed
            NextValue(self.send_ts1, 1),
            NextValue(self.send_ts2, 0),
            NextValue(self.tx_elecidle, 0),
            # Wait for partner TS1 at new speed
            If(
                self.ts1_detected,
                # Speed change successful, return to L0
                NextState("L0"),
            ),
        )
