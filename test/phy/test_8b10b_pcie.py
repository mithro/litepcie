#!/usr/bin/env python3

"""
PCIe 8b/10b Encoder/Decoder Validation Tests

This test validates LiteX's existing 8b/10b encoder/decoder for PCIe usage.
Following the investigation in docs/phases/phase-9-8b10b-investigation.md, we use
LiteX's Encoder/Decoder classes directly (no wrapper needed).

Reference:
- LiteX: litex/soc/cores/code_8b10b.py
- liteiclink usage: liteiclink/serdes/gtx_7series.py (line 254-255)
- PCIe spec: K-characters for training sequences and framing
"""

import unittest
from migen import *
from litex.soc.cores.code_8b10b import Encoder, Decoder, K, D


# PCIe K-Character Constants (from PCIe Base Spec)
K28_5 = K(28, 5)  # 0xBC - COM (comma, for alignment)
K23_7 = K(23, 7)  # 0xF7 - PAD (TS1/TS2 identifier)
K27_7 = K(27, 7)  # 0xFB - STP (start of TLP)
K29_7 = K(29, 7)  # 0xFD - END (end of TLP)
K30_7 = K(30, 7)  # 0xFE - EDB (bad end)
K28_0 = K(28, 0)  # 0x1C - SKP (clock compensation)
K28_1 = K(28, 1)  # 0x3C - FTS (Fast Training Sequence)
K28_2 = K(28, 2)  # 0x5C - SDP (start of DLLP)
K28_3 = K(28, 3)  # 0x7C - IDL (electrical idle ordered set)


class Test8b10bPCIe(unittest.TestCase):
    """Test LiteX 8b/10b encoder/decoder with PCIe K-characters."""

    def test_k28_5_comma_encoding(self):
        """K28.5 (COM) encodes correctly with both disparities."""
        encoder = Encoder(nwords=1, lsb_first=True)

        def testbench():
            # Encode K28.5
            yield encoder.d[0].eq(K28_5)
            yield encoder.k[0].eq(1)
            yield  # Clock edge - encoder latches inputs
            yield  # Clock edge - encoder processes
            yield  # Clock edge - encoder output ready

            # Check output (one of two valid encodings based on disparity)
            output = yield encoder.output[0]
            # RD- : 0b0101111100 = 0x17C (LSB first)
            # RD+ : 0b1010000011 = 0x283 (LSB first)
            self.assertIn(output, [0x17C, 0x283],
                f"K28.5 encoding incorrect: got 0x{output:03x}")

        run_simulation(encoder, testbench())

    def test_ts1_sequence(self):
        """Test encoding PCIe TS1 ordered set: COM + PAD + Link_num + Lane_num."""
        encoder = Encoder(nwords=4, lsb_first=True)

        def testbench():
            # TS1 = COM + PAD + Link_num + Lane_num
            yield encoder.d[0].eq(K28_5)  # K28.5 - COM
            yield encoder.k[0].eq(1)
            yield encoder.d[1].eq(K23_7)  # K23.7 - PAD (TS1 identifier)
            yield encoder.k[1].eq(1)
            yield encoder.d[2].eq(0x00)   # D0.0 - Link number
            yield encoder.k[2].eq(0)
            yield encoder.d[3].eq(0x00)   # D0.0 - Lane number
            yield encoder.k[3].eq(0)
            yield  # Clock edge - encoder latches inputs
            yield  # Clock edge - encoder produces outputs

            # Verify all outputs are valid 10-bit codes
            for i in range(4):
                output = yield encoder.output[i]
                self.assertGreater(output, 0, f"Symbol {i} is zero")
                self.assertLess(output, 1024, f"Symbol {i} exceeds 10-bit max")

        run_simulation(encoder, testbench())

    def test_all_pcie_k_characters(self):
        """Test all PCIe K-characters encode without errors."""
        pcie_k_chars = [K28_5, K23_7, K27_7, K29_7, K30_7, K28_0, K28_1, K28_2, K28_3]
        encoder = Encoder(nwords=1, lsb_first=True)

        def testbench():
            for k_char in pcie_k_chars:
                yield encoder.d[0].eq(k_char)
                yield encoder.k[0].eq(1)
                yield  # Clock edge - encoder latches inputs
                yield  # Clock edge - encoder produces output

                output = yield encoder.output[0]
                self.assertGreater(output, 0, f"K-char 0x{k_char:02x} encoded as zero")
                self.assertLess(output, 1024, f"K-char 0x{k_char:02x} exceeds 10-bit")

        run_simulation(encoder, testbench())

    def test_decoder_invalid_code(self):
        """Decoder detects invalid 10-bit codes."""
        decoder = Decoder(lsb_first=True)

        def testbench():
            # Send invalid code (all zeros - not a valid 8b/10b code)
            yield decoder.input.eq(0x000)
            yield

            # Should flag as invalid
            invalid = yield decoder.invalid
            self.assertEqual(invalid, 1, "Decoder did not flag invalid code")

        run_simulation(decoder, testbench())

    def test_disparity_tracking(self):
        """Encoder maintains running disparity across symbols."""
        encoder = Encoder(nwords=2, lsb_first=True)

        def testbench():
            # Encode two K28.5 symbols (changes disparity)
            yield encoder.d[0].eq(K28_5)
            yield encoder.k[0].eq(1)
            yield encoder.d[1].eq(K28_5)
            yield encoder.k[1].eq(1)
            yield  # Clock edge - encoder latches inputs
            yield  # Clock edge - encoder processes
            yield  # Clock edge - encoder outputs and disparity ready

            # Check disparity flips (K28.5 alternates encoding based on disparity)
            disp0 = yield encoder.disparity[0]
            disp1 = yield encoder.disparity[1]
            out0 = yield encoder.output[0]
            out1 = yield encoder.output[1]

            # Disparity should change between symbols
            self.assertNotEqual(disp0, disp1, "Disparity did not change")
            # Outputs should be different (different disparity encodings)
            self.assertNotEqual(out0, out1, "Outputs should differ with different disparity")

        run_simulation(encoder, testbench())

    def test_roundtrip_data(self):
        """Data survives encode → decode roundtrip."""
        # Need to simulate encoder and decoder together
        dut = Module()
        dut.submodules.encoder = encoder = Encoder(nwords=1, lsb_first=True)
        dut.submodules.decoder = decoder = Decoder(lsb_first=True)

        def testbench():
            # Encode D0.0
            yield encoder.d[0].eq(0x00)
            yield encoder.k[0].eq(0)
            yield  # Clock edge - encoder latches inputs
            yield  # Clock edge - encoder produces output

            # Get encoded output
            encoded = yield encoder.output[0]
            self.assertGreater(encoded, 0, "Encoder produced zero output")

            # Decode it
            yield decoder.input.eq(encoded)
            yield  # Clock edge - decoder latches input
            yield  # Clock edge - decoder produces output

            # Check decoded matches original
            decoded_d = yield decoder.d
            decoded_k = yield decoder.k
            invalid = yield decoder.invalid

            self.assertEqual(decoded_d, 0x00, "Decoded data mismatch")
            self.assertEqual(decoded_k, 0, "Decoded K-char flag mismatch")
            self.assertEqual(invalid, 0, "Decoder flagged valid data as invalid")

        run_simulation(dut, testbench())

    def test_roundtrip_k_character(self):
        """K-character survives encode → decode roundtrip."""
        # Need to simulate encoder and decoder together
        dut = Module()
        dut.submodules.encoder = encoder = Encoder(nwords=1, lsb_first=True)
        dut.submodules.decoder = decoder = Decoder(lsb_first=True)

        def testbench():
            # Encode K28.5
            yield encoder.d[0].eq(K28_5)
            yield encoder.k[0].eq(1)
            yield  # Clock edge - encoder latches inputs
            yield  # Clock edge - encoder processes
            yield  # Clock edge - encoder output ready

            # Get encoded output
            encoded = yield encoder.output[0]
            self.assertGreater(encoded, 0, "Encoder produced zero output for K28.5")

            # Decode it
            yield decoder.input.eq(encoded)
            yield  # Clock edge - decoder latches input
            yield  # Clock edge - decoder produces output

            # Check decoded matches original
            decoded_d = yield decoder.d
            decoded_k = yield decoder.k
            invalid = yield decoder.invalid

            self.assertEqual(decoded_d, K28_5, f"Decoded K-char mismatch: got 0x{decoded_d:02x}")
            self.assertEqual(decoded_k, 1, "Decoded K-char flag should be 1")
            self.assertEqual(invalid, 0, "Decoder flagged valid K-char as invalid")

        run_simulation(dut, testbench())

    def test_multiword_encoder_like_liteiclink(self):
        """Test 2-word encoder like liteiclink uses for GTX."""
        # liteiclink uses Encoder(nwords=2, lsb_first=True)
        encoder = Encoder(nwords=2, lsb_first=True)

        def testbench():
            # Encode two bytes: K28.5 + D0.0
            yield encoder.d[0].eq(K28_5)
            yield encoder.k[0].eq(1)
            yield encoder.d[1].eq(0x00)
            yield encoder.k[1].eq(0)
            yield  # Clock edge - encoder latches inputs
            yield  # Clock edge - encoder produces outputs

            # Both should encode
            output0 = yield encoder.output[0]
            output1 = yield encoder.output[1]

            self.assertGreater(output0, 0, "First symbol zero")
            self.assertGreater(output1, 0, "Second symbol zero")
            self.assertLess(output0, 1024, "First symbol exceeds 10-bit")
            self.assertLess(output1, 1024, "Second symbol exceeds 10-bit")

        run_simulation(encoder, testbench())


if __name__ == "__main__":
    unittest.main()
