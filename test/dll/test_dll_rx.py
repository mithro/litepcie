#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Incremental Tests for PCIe DLL RX Path.

Breaking down RX tests into small, incremental steps.
Each test validates one specific behavior.

Reference: PCIe Base Spec 4.0, Section 3.3
"""

import unittest

from migen import *
from litex.gen import run_simulation


class TestDLLRXIncremental(unittest.TestCase):
    """Incremental tests for DLL RX path."""

    def test_step1_fsm_accepts_tlp(self):
        """Step 1: FSM should accept TLP from PHY."""
        from litepcie.dll.rx import DLLRX

        def testbench(dut):
            # Enable all ready signals
            yield dut.tlp_source.ready.eq(1)
            yield dut.ack_source.ready.eq(1)
            yield dut.nak_source.ready.eq(1)
            yield

            # Verify FSM starts in IDLE
            fsm_state = (yield dut.fsm.state)
            print(f"Initial FSM state: {fsm_state}")

            # Send minimal TLP
            yield dut.phy_sink.valid.eq(1)
            yield dut.phy_sink.data.eq(0xDEADBEEF)
            yield dut.phy_sink.seq_num.eq(0)
            yield dut.phy_sink.lcrc.eq(0x12345678)  # Valid-looking CRC
            yield

            # Check phy_sink was accepted (ready should be high in IDLE)
            phy_ready = (yield dut.phy_sink.ready)
            self.assertTrue(phy_ready, "PHY sink should be ready in IDLE state")

            # FSM should have moved from IDLE
            yield dut.phy_sink.valid.eq(0)
            yield
            fsm_state = (yield dut.fsm.state)
            print(f"FSM state after TLP: {fsm_state}")
            # Should not be in IDLE (state 0) anymore
            self.assertNotEqual(fsm_state, 0, "FSM should have left IDLE state")

        dut = DLLRX(data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="test_rx_step1.vcd")

    def test_step2_fsm_progresses_through_states(self):
        """Step 2: FSM should progress through CHECK_LCRC -> COMPARE_CRC -> CHECK_SEQ."""
        from litepcie.dll.rx import DLLRX

        def testbench(dut):
            # Enable all ready signals
            yield dut.tlp_source.ready.eq(1)
            yield dut.ack_source.ready.eq(1)
            yield dut.nak_source.ready.eq(1)
            yield

            # Send TLP
            yield dut.phy_sink.valid.eq(1)
            yield dut.phy_sink.data.eq(0xDEADBEEF)
            yield dut.phy_sink.seq_num.eq(0)
            yield dut.phy_sink.lcrc.eq(0x12345678)
            yield
            yield dut.phy_sink.valid.eq(0)

            # Track FSM state progression
            states = []
            for i in range(10):
                yield
                state = (yield dut.fsm.state)
                states.append(state)
                print(f"Cycle {i}: FSM state = {state}")

            # Verify FSM moved through multiple states
            unique_states = set(states)
            self.assertGreater(len(unique_states), 1,
                             f"FSM should visit multiple states, got: {states}")

        dut = DLLRX(data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="test_rx_step2.vcd")

    def test_step3_lcrc_validation_accepts_good_crc(self):
        """Step 3: LCRC validation should accept non-bad CRC patterns."""
        from litepcie.dll.rx import DLLRX

        def testbench(dut):
            # Enable ready signals
            yield dut.tlp_source.ready.eq(1)
            yield dut.ack_source.ready.eq(1)
            yield dut.nak_source.ready.eq(1)
            yield

            # Send TLP with valid-looking CRC
            yield dut.phy_sink.valid.eq(1)
            yield dut.phy_sink.data.eq(0xDEADBEEF)
            yield dut.phy_sink.seq_num.eq(0)
            yield dut.phy_sink.lcrc.eq(0x12345678)  # Not a bad pattern
            yield
            yield dut.phy_sink.valid.eq(0)

            # Wait for processing
            for _ in range(10):
                yield

            # Check debug signal for LCRC validation result
            lcrc_valid = (yield dut.debug_lcrc_valid)
            print(f"LCRC valid: {lcrc_valid}")
            self.assertTrue(lcrc_valid, "Valid CRC should pass validation")

        dut = DLLRX(data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="test_rx_step3_good.vcd")

    def test_step4_lcrc_validation_rejects_bad_crc(self):
        """Step 4: LCRC validation should reject known bad CRC patterns."""
        from litepcie.dll.rx import DLLRX

        def testbench(dut):
            # Enable ready signals
            yield dut.tlp_source.ready.eq(1)
            yield dut.ack_source.ready.eq(1)
            yield dut.nak_source.ready.eq(1)
            yield

            # Send TLP with BAD CRC pattern
            yield dut.phy_sink.valid.eq(1)
            yield dut.phy_sink.data.eq(0xDEADBEEF)
            yield dut.phy_sink.seq_num.eq(0)
            yield dut.phy_sink.lcrc.eq(0xBADBADBA)  # Known bad pattern
            yield
            yield dut.phy_sink.valid.eq(0)

            # Wait for processing
            for _ in range(10):
                yield

            # Check debug signal for LCRC validation result
            lcrc_valid = (yield dut.debug_lcrc_valid)
            print(f"LCRC valid: {lcrc_valid}")
            self.assertFalse(lcrc_valid, "Bad CRC pattern should fail validation")

        dut = DLLRX(data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="test_rx_step4_bad.vcd")

    def test_step5_sequence_validation_accepts_expected_seq(self):
        """Step 5: Sequence validation should accept expected sequence number."""
        from litepcie.dll.rx import DLLRX

        def testbench(dut):
            # Enable ready signals
            yield dut.tlp_source.ready.eq(1)
            yield dut.ack_source.ready.eq(1)
            yield dut.nak_source.ready.eq(1)
            yield

            # Send TLP with sequence 0 (expected on startup)
            yield dut.phy_sink.valid.eq(1)
            yield dut.phy_sink.data.eq(0xDEADBEEF)
            yield dut.phy_sink.seq_num.eq(0)  # Expected first sequence
            yield dut.phy_sink.lcrc.eq(0x12345678)
            yield
            yield dut.phy_sink.valid.eq(0)

            # Wait for processing
            for _ in range(10):
                yield

            # Check debug signal for sequence validation
            seq_valid = (yield dut.debug_seq_valid)
            print(f"Seq valid: {seq_valid}")
            self.assertTrue(seq_valid, "Expected sequence should be valid")

        dut = DLLRX(data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="test_rx_step5.vcd")

    def test_step6_ack_generation(self):
        """Step 6: FSM should generate ACK for valid TLP."""
        from litepcie.dll.rx import DLLRX

        def testbench(dut):
            # Enable ready signals
            yield dut.tlp_source.ready.eq(1)
            yield dut.ack_source.ready.eq(1)
            yield dut.nak_source.ready.eq(1)
            yield

            # Send valid TLP
            yield dut.phy_sink.valid.eq(1)
            yield dut.phy_sink.data.eq(0xDEADBEEF)
            yield dut.phy_sink.seq_num.eq(0)
            yield dut.phy_sink.lcrc.eq(0x12345678)
            yield
            yield dut.phy_sink.valid.eq(0)

            # Wait and look for ACK
            ack_found = False
            for i in range(15):
                yield
                ack_valid = (yield dut.ack_source.valid)
                if ack_valid:
                    ack_seq = (yield dut.ack_source.seq_num)
                    print(f"Cycle {i}: ACK generated with seq={ack_seq}")
                    ack_found = True
                    self.assertEqual(ack_seq, 0, "ACK should have sequence 0")
                    break

            self.assertTrue(ack_found, "ACK should be generated for valid TLP")

        dut = DLLRX(data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="test_rx_step6.vcd")

    def test_step7_nak_generation(self):
        """Step 7: FSM should generate NAK for invalid LCRC."""
        from litepcie.dll.rx import DLLRX

        def testbench(dut):
            # Enable ready signals
            yield dut.tlp_source.ready.eq(1)
            yield dut.ack_source.ready.eq(1)
            yield dut.nak_source.ready.eq(1)
            yield

            # Send TLP with bad CRC
            yield dut.phy_sink.valid.eq(1)
            yield dut.phy_sink.data.eq(0xDEADBEEF)
            yield dut.phy_sink.seq_num.eq(0)
            yield dut.phy_sink.lcrc.eq(0xBADBADBA)  # Bad CRC
            yield
            yield dut.phy_sink.valid.eq(0)

            # Wait and look for NAK
            nak_found = False
            for i in range(15):
                yield
                nak_valid = (yield dut.nak_source.valid)
                if nak_valid:
                    nak_seq = (yield dut.nak_source.seq_num)
                    print(f"Cycle {i}: NAK generated with seq={nak_seq}")
                    nak_found = True
                    break

            self.assertTrue(nak_found, "NAK should be generated for bad LCRC")

        dut = DLLRX(data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="test_rx_step7.vcd")

    def test_step8_tlp_forwarding(self):
        """Step 8: Valid TLP should be forwarded to Transaction Layer."""
        from litepcie.dll.rx import DLLRX

        def testbench(dut):
            # Enable ready signals
            yield dut.tlp_source.ready.eq(1)
            yield dut.ack_source.ready.eq(1)
            yield dut.nak_source.ready.eq(1)
            yield

            # Send valid TLP
            test_data = 0xDEADBEEFCAFEBABE
            yield dut.phy_sink.valid.eq(1)
            yield dut.phy_sink.data.eq(test_data)
            yield dut.phy_sink.seq_num.eq(0)
            yield dut.phy_sink.lcrc.eq(0x12345678)
            yield
            yield dut.phy_sink.valid.eq(0)

            # Wait and look for forwarded TLP
            tlp_found = False
            for i in range(15):
                yield
                tlp_valid = (yield dut.tlp_source.valid)
                if tlp_valid:
                    tlp_data = (yield dut.tlp_source.data)
                    print(f"Cycle {i}: TLP forwarded with data=0x{tlp_data:016X}")
                    tlp_found = True
                    self.assertEqual(tlp_data, test_data, "Forwarded data should match input")
                    break

            self.assertTrue(tlp_found, "Valid TLP should be forwarded")

        dut = DLLRX(data_width=64)
        run_simulation(dut, testbench(dut), vcd_name="test_rx_step8.vcd")


if __name__ == "__main__":
    unittest.main()
