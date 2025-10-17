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
    RECOVERY_EQ_PHASE0 = 6  # Equalization phase 0
    RECOVERY_EQ_PHASE1 = 7  # Equalization phase 1
    RECOVERY_EQ_PHASE2 = 8  # Equalization phase 2
    RECOVERY_EQ_PHASE3 = 9  # Equalization phase 3
    L0s_IDLE = 10  # L0s low power state
    L0s_FTS = 11  # L0s exit via FTS
    L1 = 12  # L1 deeper sleep state
    L2 = 13  # L2 deepest sleep state
    # Detailed POLLING substates (optional)
    POLLING_ACTIVE = 16  # POLLING.Active - Send TS1, wait for partner
    POLLING_CONFIGURATION = 17  # POLLING.Configuration - Send TS2
    POLLING_COMPLIANCE = 18  # POLLING.Compliance - Electrical testing
    # Detailed RECOVERY substates (optional)
    RECOVERY_RCVRLOCK = 19  # RECOVERY.RcvrLock - Establish bit lock
    RECOVERY_RCVRCFG = 20  # RECOVERY.RcvrCfg - Verify configuration
    RECOVERY_IDLE = 21  # RECOVERY.Idle - Final check before L0

    def __init__(self, gen=1, lanes=1, enable_equalization=False, enable_l0s=False, enable_l1=False, enable_l2=False, detailed_substates=False):
        # Link status outputs
        self.link_up = Signal()
        self.current_state = Signal(5)  # 5 bits for states 0-21
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

        # Equalization support
        self.enable_eq = enable_equalization
        self.eq_capable = Signal(reset=1 if (gen >= 2 and enable_equalization) else 0)
        self.force_equalization = Signal()  # Trigger equalization
        self.eq_phase = Signal(2)  # Current equalization phase (0-3)

        # Equalization phase counter
        eq_phase_timer = Signal(16)

        # L0s power state support
        self.enable_l0s = enable_l0s
        self.l0s_capable = Signal(reset=1 if enable_l0s else 0)
        self.enter_l0s = Signal()  # Request L0s entry
        self.exit_l0s = Signal()   # Request L0s exit
        self.send_fts = Signal()   # Send FTS (Fast Training Sequence)

        # FTS counter (n_fts field from TS1/TS2)
        fts_counter = Signal(8)

        # L1 and L2 power states support
        self.enable_l1 = enable_l1
        self.enable_l2 = enable_l2
        self.l1_capable = Signal(reset=1 if enable_l1 else 0)
        self.l2_capable = Signal(reset=1 if enable_l2 else 0)
        self.enter_l1 = Signal()  # Request L1 entry
        self.exit_l1 = Signal()   # Request L1 exit
        self.enter_l2 = Signal()  # Request L2 entry
        self.exit_l2 = Signal()   # Request L2 exit

        # Detailed substates support
        self.detailed_substates = detailed_substates
        self.rx_compliance_request = Signal()  # Compliance request from partner

        # TS1 receive counter for POLLING.Active → POLLING.Configuration
        ts1_rx_count = Signal(4)

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
                # Use detailed substates if enabled, otherwise simple POLLING
                NextState("POLLING_ACTIVE" if detailed_substates else "POLLING"),
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

        # Detailed POLLING Substates (optional)
        if detailed_substates:
            # POLLING.Active - Send TS1 and wait for partner TS1
            # Reference: PCIe Spec 4.0, Section 4.2.5.3.2.1
            self.fsm.act(
                "POLLING_ACTIVE",
                NextValue(self.current_state, self.POLLING_ACTIVE),
                NextValue(self.tx_elecidle, 0),
                NextValue(self.send_ts1, 1),
                NextValue(self.send_ts2, 0),
                # Count received TS1
                If(
                    self.ts1_detected,
                    NextValue(ts1_rx_count, ts1_rx_count + 1),
                ),
                # Compliance takes priority
                If(
                    self.rx_compliance_request,
                    NextState("POLLING_COMPLIANCE"),
                    NextValue(ts1_rx_count, 0),
                # After 8 consecutive TS1, move to Configuration
                ).Elif(
                    ts1_rx_count >= 8,
                    NextState("POLLING_CONFIGURATION"),
                    NextValue(ts1_rx_count, 0),
                ),
            )

            # POLLING.Configuration - Send TS2 after TS1 exchange
            # Reference: PCIe Spec 4.0, Section 4.2.5.3.2.2
            self.fsm.act(
                "POLLING_CONFIGURATION",
                NextValue(self.current_state, self.POLLING_CONFIGURATION),
                NextValue(self.send_ts1, 0),
                NextValue(self.send_ts2, 1),
                # Transition to CONFIGURATION state when TS2 detected
                If(
                    self.ts2_detected,
                    NextState("CONFIGURATION"),
                ),
            )

            # POLLING.Compliance - Electrical testing mode
            # Reference: PCIe Spec 4.0, Section 4.2.5.3.2.3
            self.fsm.act(
                "POLLING_COMPLIANCE",
                NextValue(self.current_state, self.POLLING_COMPLIANCE),
                # Send compliance pattern (simplified: send TS1)
                NextValue(self.send_ts1, 1),
                # Stay in compliance until reset/timeout
                # (Real HW would send specific compliance patterns)
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
            # Enter L1 if requested and capable
            If(
                self.l1_capable & self.enter_l1,
                NextState("L1"),
            # Enter L0s if requested and capable
            ).Elif(
                self.l0s_capable & self.enter_l0s,
                NextState("L0s_IDLE"),
            # If speed change required, enter RECOVERY.Speed
            ).Elif(
                self.speed_change_required,
                NextState("RECOVERY_SPEED"),
            # Monitor for link errors
            # If rx goes to electrical idle unexpectedly, enter RECOVERY
            ).Elif(
                self.rx_elecidle,
                NextState("RECOVERY_RCVRLOCK" if detailed_substates else "RECOVERY"),
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
            # If equalization requested and capable, enter equalization
            If(
                self.eq_capable & self.force_equalization,
                NextState("RECOVERY_EQ_PHASE0"),
                NextValue(eq_phase_timer, 0),
            # Wait for partner to exit electrical idle and respond with TS1
            # Simplified recovery: if we receive TS1, return to L0
            # (Full spec would go through POLLING/CONFIGURATION again)
            ).Elif(
                (~self.rx_elecidle) & self.ts1_detected,
                NextState("L0"),
            ),
        )

        # Detailed RECOVERY Substates (optional)
        if detailed_substates:
            # RECOVERY.RcvrLock - Establish receiver bit/symbol lock
            # Reference: PCIe Spec 4.0, Section 4.2.5.3.7.1
            self.fsm.act(
                "RECOVERY_RCVRLOCK",
                NextValue(self.current_state, self.RECOVERY_RCVRLOCK),
                NextValue(self.link_up, 0),
                NextValue(self.send_ts1, 1),
                NextValue(self.send_ts2, 0),
                NextValue(self.tx_elecidle, 0),
                # Wait for partner to exit electrical idle and send TS1
                If(
                    (~self.rx_elecidle) & self.ts1_detected,
                    NextState("RECOVERY_RCVRCFG"),
                ),
            )

            # RECOVERY.RcvrCfg - Verify configuration
            # Reference: PCIe Spec 4.0, Section 4.2.5.3.7.2
            self.fsm.act(
                "RECOVERY_RCVRCFG",
                NextValue(self.current_state, self.RECOVERY_RCVRCFG),
                NextValue(self.send_ts1, 1),
                # After configuration verified, move to Idle
                # (Simplified - real implementation checks config fields)
                If(
                    self.ts1_detected,
                    NextState("RECOVERY_IDLE"),
                ),
            )

            # RECOVERY.Idle - Final check before L0
            # Reference: PCIe Spec 4.0, Section 4.2.5.3.7.3
            self.fsm.act(
                "RECOVERY_IDLE",
                NextValue(self.current_state, self.RECOVERY_IDLE),
                NextValue(self.send_ts1, 0),
                NextValue(self.send_ts2, 1),
                # After TS2 exchange, return to L0
                If(
                    self.ts2_detected,
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

        # RECOVERY.Equalization Phase 0 - Transmitter Preset
        # Reference: PCIe Spec 4.0, Section 4.2.3: Link Equalization
        self.fsm.act(
            "RECOVERY_EQ_PHASE0",
            NextValue(self.current_state, self.RECOVERY_EQ_PHASE0),
            NextValue(self.eq_phase, 0),
            NextValue(eq_phase_timer, eq_phase_timer + 1),
            # Send TS1 with equalization request
            NextValue(self.send_ts1, 1),
            # Phase 0: Transmitter preset (simplified - time-based)
            If(
                eq_phase_timer > 100,
                NextState("RECOVERY_EQ_PHASE1"),
                NextValue(eq_phase_timer, 0),
            ),
        )

        # RECOVERY.Equalization Phase 1 - Receiver Coefficient Request
        self.fsm.act(
            "RECOVERY_EQ_PHASE1",
            NextValue(self.current_state, self.RECOVERY_EQ_PHASE1),
            NextValue(self.eq_phase, 1),
            NextValue(eq_phase_timer, eq_phase_timer + 1),
            # Phase 1: Receiver coefficient request
            If(
                eq_phase_timer > 100,
                NextState("RECOVERY_EQ_PHASE2"),
                NextValue(eq_phase_timer, 0),
            ),
        )

        # RECOVERY.Equalization Phase 2 - Transmitter Coefficient Update
        self.fsm.act(
            "RECOVERY_EQ_PHASE2",
            NextValue(self.current_state, self.RECOVERY_EQ_PHASE2),
            NextValue(self.eq_phase, 2),
            NextValue(eq_phase_timer, eq_phase_timer + 1),
            # Phase 2: Transmitter coefficient update
            If(
                eq_phase_timer > 100,
                NextState("RECOVERY_EQ_PHASE3"),
                NextValue(eq_phase_timer, 0),
            ),
        )

        # RECOVERY.Equalization Phase 3 - Link Evaluation
        self.fsm.act(
            "RECOVERY_EQ_PHASE3",
            NextValue(self.current_state, self.RECOVERY_EQ_PHASE3),
            NextValue(self.eq_phase, 3),
            NextValue(eq_phase_timer, eq_phase_timer + 1),
            # Phase 3: Link evaluation
            If(
                eq_phase_timer > 100,
                # Equalization complete, return to L0
                NextState("L0"),
                NextValue(self.force_equalization, 0),
            ),
        )

        # L0s.Idle State - Low Power Standby
        # Reference: PCIe Spec 4.0, Section 4.2.5.3.6: L0s State
        self.fsm.act(
            "L0s_IDLE",
            NextValue(self.current_state, self.L0s_IDLE),
            # Link still up, but in low power
            NextValue(self.link_up, 1),
            # TX in electrical idle (power savings)
            NextValue(self.tx_elecidle, 1),
            # Exit L0s when data needs to be sent
            If(
                self.exit_l0s,
                NextState("L0s_FTS"),
                NextValue(fts_counter, 0),
            ),
        )

        # L0s.FTS State - Exit via Fast Training Sequence
        self.fsm.act(
            "L0s_FTS",
            NextValue(self.current_state, self.L0s_FTS),
            # Exit electrical idle
            NextValue(self.tx_elecidle, 0),
            # Send FTS sequences for receiver lock
            NextValue(self.send_fts, 1),
            NextValue(fts_counter, fts_counter + 1),
            # After N_FTS sequences, return to L0
            # (Using n_fts value - typically 128 for Gen1)
            If(
                fts_counter >= 128,
                NextState("L0"),
                NextValue(self.send_fts, 0),
                NextValue(self.exit_l0s, 0),
            ),
        )

        # L1 State - Deeper Sleep State
        # Reference: PCIe Spec 4.0, Section 5.4: L1 State
        self.fsm.act(
            "L1",
            NextValue(self.current_state, self.L1),
            # Link down during L1
            NextValue(self.link_up, 0),
            # TX in electrical idle (power savings)
            NextValue(self.tx_elecidle, 1),
            # Enter L2 if requested and capable
            If(
                self.l2_capable & self.enter_l2,
                NextState("L2"),
            # Exit L1 to RECOVERY for retraining
            ).Elif(
                self.exit_l1,
                NextState("RECOVERY_RCVRLOCK" if detailed_substates else "RECOVERY"),
                NextValue(self.exit_l1, 0),
            ),
        )

        # L2 State - Deepest Sleep State
        # Reference: PCIe Spec 4.0, Section 5.5: L2 State
        self.fsm.act(
            "L2",
            NextValue(self.current_state, self.L2),
            # Link down during L2
            NextValue(self.link_up, 0),
            # TX in electrical idle (deepest power savings)
            NextValue(self.tx_elecidle, 1),
            # L2 exit requires full reset to DETECT
            If(
                self.exit_l2,
                NextState("DETECT"),
                NextValue(self.exit_l2, 0),
            ),
        )
