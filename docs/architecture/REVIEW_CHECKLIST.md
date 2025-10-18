# Architecture Documentation Review Checklist

**Version:** 1.0
**Date:** 2025-10-18
**Purpose:** Comprehensive review criteria for LitePCIe architecture documentation

Use this checklist to verify documentation completeness, quality, and consistency. This checklist can be used for:
- Reviewing new documentation before publication
- Periodic quality audits of existing documentation
- Ensuring consistency across documentation updates
- Pre-publication verification before releases

## How to Use This Checklist

1. **Initial Review**: Go through each section sequentially for comprehensive review
2. **Quick Validation**: Run the automated validation commands in the [Validation](#validation) section
3. **Quality Audit**: Focus on the [Quality](#quality) section for periodic reviews
4. **Sign-off**: Complete all sections before marking documentation ready for publication

---

## 1. Completeness

### 1.1 Complete System Architecture (`complete-system-architecture.md`)

**Required Sections:**
- [ ] Overview section explaining LitePCIe's unique characteristics
- [ ] Full 5-layer stack diagram (Application → TLP → DLL → PIPE → SERDES)
- [ ] Reading guide for different audiences (new users, implementers, debuggers)
- [ ] Layer overview with component summaries
- [ ] Cross-references to all layer-specific documents
- [ ] Data flow examples showing packet traversal

**Content Requirements:**
- [ ] Explains vendor-IP-free approach and benefits
- [ ] Documents all supported FPGA families (7-Series, UltraScale+, ECP5)
- [ ] Includes high-level comparison to vendor hard IP solutions
- [ ] Provides clear navigation paths for different user types

### 1.2 SERDES Layer (`serdes-layer.md`)

**Required Sections:**
- [ ] Layer overview with purpose and location
- [ ] PIPETransceiver base class architecture
- [ ] Vendor-specific implementations (GTX, GTY, ECP5)
- [ ] TX datapath architecture and CDC
- [ ] RX datapath architecture and CDC
- [ ] Reset sequencing documentation
- [ ] Clocking architecture (CPLL, QPLL, CDR)
- [ ] 8b/10b encoding/decoding explanation

**Content Requirements:**
- [ ] Explains software 8b/10b decision rationale
- [ ] Documents clock domain crossings (sys_clk ↔ tx_clk/rx_clk)
- [ ] Shows timing diagrams for data flow
- [ ] Includes transceiver primitive integration details
- [ ] Documents reset FSM states and transitions
- [ ] Explains electrical idle handling
- [ ] Covers speed switching (Gen1/Gen2/Gen3)

**Diagrams Required:**
- [ ] TransceiverBase class hierarchy diagram
- [ ] TX datapath architecture (AsyncFIFO, encoder, serializer)
- [ ] RX datapath architecture (deserializer, decoder, AsyncFIFO)
- [ ] Reset sequencer state machine
- [ ] Clock domain diagram showing all clocks
- [ ] At least one vendor-specific transceiver diagram

### 1.3 PIPE Layer (`pipe-layer.md`)

**Required Sections:**
- [ ] Layer overview with MAC/PHY boundary explanation
- [ ] PIPE interface specification (based on Intel PIPE 3.0)
- [ ] TX Packetizer architecture
- [ ] RX Depacketizer architecture
- [ ] K-character framing (STP, SDP, END, EDB, PAD)
- [ ] Ordered set generation (SKP, TS1, TS2, COM)
- [ ] Ordered set detection and handling
- [ ] Symbol encoding tables
- [ ] Timing diagrams with cycle-accurate examples

**Content Requirements:**
- [ ] Documents all PIPE control signals (tx_elecidle, rx_elecidle, etc.)
- [ ] Explains 64-bit to 8-bit conversion process
- [ ] Shows framing FSM states and transitions
- [ ] Documents SKP insertion timing (every 1180 symbols)
- [ ] Explains TS1/TS2 ordered set structure
- [ ] Covers electrical idle detection and handling

**Diagrams Required:**
- [ ] PIPE interface signal diagram
- [ ] TX Packetizer FSM state machine
- [ ] RX Depacketizer FSM state machine
- [ ] K-character encoding table
- [ ] Ordered set format diagrams (SKP, TS1, TS2)
- [ ] Complete TX→RX data flow with timing

### 1.4 DLL Layer (`dll-layer.md`)

**Required Sections:**
- [ ] Layer overview with reliability mechanisms
- [ ] DLL TX path architecture
- [ ] DLL RX path architecture
- [ ] LCRC generation and checking
- [ ] Sequence number management
- [ ] ACK/NAK protocol
- [ ] Retry buffer architecture (4KB circular buffer)
- [ ] DLLP processing (ACK, NAK, UpdateFC, PM)
- [ ] LTSSM state machine
- [ ] Link training sequences (TS1/TS2 exchange)
- [ ] Error recovery procedures

**Content Requirements:**
- [ ] Explains LCRC calculation algorithm
- [ ] Documents sequence number wraparound handling
- [ ] Shows ACK timing requirements
- [ ] Explains NAK conditions and replay mechanism
- [ ] Documents retry buffer management
- [ ] Covers all LTSSM states (DETECT → POLLING → CONFIG → L0 → RECOVERY)
- [ ] Explains speed and lane negotiation
- [ ] Documents power state transitions

**Diagrams Required:**
- [ ] Complete DLL architecture (TX, RX, retry buffer, LTSSM)
- [ ] LTSSM state machine with all transitions
- [ ] ACK/NAK protocol sequence diagram
- [ ] Retry buffer structure and management
- [ ] DLLP format diagrams (ACK, NAK, UpdateFC)
- [ ] Link training sequence diagram (TS1/TS2 exchange)
- [ ] Error recovery flow diagram

### 1.5 TLP Layer (`tlp-layer.md`)

**Required Sections:**
- [ ] Layer overview with transaction types
- [ ] TLP Packetizer architecture
- [ ] TLP Depacketizer architecture
- [ ] TLP header formats (3DW and 4DW)
- [ ] Flow control architecture
- [ ] Credit management (Posted, Non-Posted, Completion)
- [ ] Routing mechanisms (address-based, ID-based)
- [ ] Completion tracking
- [ ] TLP types documentation (Memory, I/O, Config, Completion, Messages)

**Content Requirements:**
- [ ] Documents all TLP header fields
- [ ] Explains ECRC calculation (optional)
- [ ] Shows credit pool initialization
- [ ] Documents credit return mechanisms
- [ ] Explains throttling based on credits
- [ ] Covers completion timeout handling
- [ ] Documents poisoned TLP handling
- [ ] Explains unsupported request handling

**Diagrams Required:**
- [ ] TLP layer architecture diagram
- [ ] TLP header format diagrams (all types)
- [ ] Flow control credit flow diagram
- [ ] Memory read transaction sequence
- [ ] Memory write transaction sequence
- [ ] Configuration transaction sequence
- [ ] Completion matching flow

### 1.6 Integration Patterns (`integration-patterns.md`)

**Required Sections:**
- [ ] Layer integration overview
- [ ] Interface contracts between layers
- [ ] End-to-end data flow (application to wire)
- [ ] Clock domain architecture
- [ ] CDC (Clock Domain Crossing) points
- [ ] Vendor PHY integration patterns
- [ ] Custom PIPE implementation integration
- [ ] Example integration code
- [ ] Common integration pitfalls

**Content Requirements:**
- [ ] Shows complete packet flow through all layers
- [ ] Documents all clock domains (sys_clk, tx_clk, rx_clk, pcie_clk)
- [ ] Explains CDC safety mechanisms (AsyncFIFO, etc.)
- [ ] Compares vendor IP vs. custom PIPE integration
- [ ] Provides integration checklist
- [ ] Documents platform-specific considerations

**Diagrams Required:**
- [ ] End-to-end data flow diagram
- [ ] Clock domain architecture diagram
- [ ] CDC points diagram
- [ ] Vendor IP integration diagram
- [ ] Custom PIPE integration diagram
- [ ] Complete system integration example

### 1.7 Quick Reference (`quick-reference.md`)

**Required Content:**
- [ ] One-page stack overview diagram
- [ ] Layer interface summary table
- [ ] Key parameters table (widths, speeds, buffer sizes)
- [ ] Common signal reference
- [ ] Links to detailed documentation

### 1.8 Main Documentation Index (`docs/README.md`)

**Required Links:**
- [ ] Links to all architecture documents
- [ ] Links to user guides
- [ ] Links to reference documentation
- [ ] Getting started guide with reading order
- [ ] Quick navigation section
- [ ] Project status information

---

## 2. Quality

### 2.1 Diagram Quality

**ASCII Diagram Standards:**
- [ ] All diagrams use consistent box-drawing characters
- [ ] Columns are properly aligned (no jagged edges)
- [ ] Signal names match code exactly (e.g., `tx_data` not `txdata`)
- [ ] Arrows clearly show data flow direction (→, ↓, ↑, ←)
- [ ] Diagrams fit in 80-column terminal (for console viewing)
- [ ] Multi-part diagrams are separated with blank lines
- [ ] Box borders use consistent characters (─, │, ┌, └, ┐, ┘, ├, ┤, ┬, ┴, ┼)

**Diagram Content:**
- [ ] All major components are labeled
- [ ] Data widths are shown (e.g., "64-bit packets")
- [ ] Clock domains are indicated where relevant
- [ ] Control signals are distinguished from data signals
- [ ] FSM states are clearly labeled
- [ ] State transitions show conditions

**Consistency Across Diagrams:**
- [ ] Component names are consistent (e.g., always "DLL TX" not varying names)
- [ ] Signal naming is consistent across all diagrams
- [ ] Clock domain naming is consistent (sys_clk, tx_clk, rx_clk)
- [ ] Layer names are consistent with established terminology
- [ ] Abstraction levels are appropriate for each document

### 2.2 Cross-References

**Internal Links:**
- [ ] All internal markdown links work (no 404s)
- [ ] Each layer doc references the master doc (`complete-system-architecture.md`)
- [ ] Related concepts are cross-linked (e.g., LTSSM in DLL links to TS1/TS2 in PIPE)
- [ ] Master doc links to all layer docs
- [ ] Integration patterns doc links to relevant layer sections
- [ ] Circular references are avoided (no infinite loops)

**Code References:**
- [ ] All file paths are accurate and resolve to actual files
- [ ] Module names match implementation
- [ ] Class names match code
- [ ] Signal names match code definitions
- [ ] Configuration parameter names match code

**External References:**
- [ ] PCIe specification references include section numbers
- [ ] PIPE specification references are accurate
- [ ] External URLs are valid (when applicable)
- [ ] Vendor documentation references are current

### 2.3 Code Examples and References

**Path Accuracy:**
- [ ] All `litepcie/` paths resolve to actual files or directories
- [ ] File references include correct directory structure
- [ ] Module imports are valid
- [ ] Class hierarchies are accurate

**Code Snippets:**
- [ ] All code snippets are syntactically correct
- [ ] Signal names match implementation
- [ ] Register names are accurate
- [ ] Configuration examples are valid
- [ ] Comments explain non-obvious details
- [ ] Code style follows LiteX conventions

**Technical Accuracy:**
- [ ] Register addresses are correct
- [ ] Bit field definitions match implementation
- [ ] Timing values are accurate
- [ ] Buffer sizes are correct (e.g., 4KB retry buffer)
- [ ] Clock frequencies are accurate

### 2.4 Readability and Accessibility

**Structure:**
- [ ] Suitable for readers with no prior LitePCIe experience
- [ ] Logical flow from overview to details
- [ ] Progressive disclosure (simple concepts before complex)
- [ ] Clear section headings
- [ ] Table of contents provided for long documents

**Language:**
- [ ] Technical terms defined on first use
- [ ] Acronyms expanded on first use
- [ ] Complex concepts have examples
- [ ] Active voice used where appropriate
- [ ] Consistent terminology throughout

**Formatting:**
- [ ] Consistent markdown formatting
- [ ] Code blocks have language hints (```python, ```verilog, etc.)
- [ ] Lists are properly formatted
- [ ] Tables are well-aligned
- [ ] Emphasis (bold, italic) used appropriately

**Examples:**
- [ ] Each complex concept has at least one example
- [ ] Examples build on each other logically
- [ ] Edge cases are covered
- [ ] Common mistakes are addressed
- [ ] Real-world usage scenarios included

---

## 3. Validation

### 3.1 Automated Validation Commands

Run these commands from the repository root to verify documentation quality:

#### Check for Broken Internal Links
```bash
cd /home/tim/github/enjoy-digital/litepcie/docs
for file in architecture/*.md README.md; do
  echo "=== Checking $file ==="
  grep -o '\[.*\](.*\.md[^)]*)' "$file" | while IFS= read -r link; do
    # Extract path (everything between ( and ))
    path=$(echo "$link" | sed 's/.*](\([^)]*\)).*/\1/')
    # Remove anchor if present
    filepath=$(echo "$path" | cut -d'#' -f1)
    # Skip empty paths and external URLs
    if [ -n "$filepath" ] && [[ "$filepath" != http* ]]; then
      # Try relative to current file's directory
      dir=$(dirname "$file")
      if [ ! -f "$filepath" ] && [ ! -f "$dir/$filepath" ] && [ ! -f "architecture/$filepath" ]; then
        echo "  ❌ BROKEN: $link"
      fi
    fi
  done
done
echo "✅ Link check complete"
```

#### Verify Code Path References
```bash
cd /home/tim/github/enjoy-digital/litepcie
echo "=== Checking code path references ==="
grep -rho '`litepcie/[^`]*`' docs/architecture/*.md docs/README.md | sort -u | while read ref; do
  file=$(echo "$ref" | tr -d '`')
  # Check if it's a file or directory
  if [ ! -e "$file" ]; then
    echo "  ❌ Invalid reference: $ref"
  fi
done
echo "✅ Code reference check complete"
```

#### Count Documentation Coverage
```bash
cd /home/tim/github/enjoy-digital/litepcie/docs
echo "=== Documentation Coverage ==="
for file in architecture/{serdes,pipe,dll,tlp,integration}-*.md architecture/complete-system-architecture.md; do
  if [ -f "$file" ]; then
    sections=$(grep -c '^## ' "$file" || echo 0)
    # Count code blocks (diagrams)
    diagrams=$(grep -c '^```$' "$file" || echo 0)
    diagrams=$((diagrams / 2))  # Each diagram has opening and closing ```
    links=$(grep -o '\[.*\](.*\.md)' "$file" | wc -l)
    echo "$(basename $file):"
    echo "  - Sections: $sections"
    echo "  - Diagrams: $diagrams"
    echo "  - Links: $links"
  fi
done
echo "✅ Coverage analysis complete"
```

#### Check Diagram Consistency
```bash
cd /home/tim/github/enjoy-digital/litepcie/docs
echo "=== Checking component naming consistency ==="
# Extract component names from diagrams (lines with │...│ pattern)
grep -h '│.*│' architecture/*.md | \
  grep -v '^│ *│' | \
  grep -v '^│─' | \
  sed 's/│//g' | \
  sed 's/^[[:space:]]*//' | \
  sed 's/[[:space:]]*$//' | \
  grep -v '^$' | \
  sort | uniq -c | sort -rn | head -30
echo "✅ Review above list for naming inconsistencies"
```

#### Full Validation Suite (Python)
If the validation scripts from Task 9 exist:
```bash
cd /home/tim/github/enjoy-digital/litepcie
if [ -f validate_docs.py ]; then
  echo "=== Running full validation suite ==="
  python3 validate_docs.py
else
  echo "⚠️  validate_docs.py not found (Task 9 validation script)"
fi
```

### 3.2 Manual Validation Checklist

**Document Structure:**
- [ ] All layer docs have consistent structure
- [ ] Section numbering is consistent
- [ ] Heading hierarchy is correct (# > ## > ###)
- [ ] No orphaned sections (sections without parent context)

**Link Validation:**
- [ ] All internal links tested by clicking
- [ ] Anchors in links are valid (section exists)
- [ ] Cross-references are bidirectional where appropriate
- [ ] No circular reference loops

**Code Reference Validation:**
- [ ] File paths verified by opening actual files
- [ ] Signal names verified against code
- [ ] Class names verified in implementation
- [ ] Module paths verified in repository

**Example Validation:**
- [ ] Code examples tested (if executable)
- [ ] Configuration examples verified against code
- [ ] Timing diagrams checked against implementation
- [ ] Data flow examples traced through code

---

## 4. Consistency

### 4.1 Terminology Consistency

**Standard Terms** (use consistently):
- "SERDES" (not "SerDes" or "serdes")
- "PIPE interface" (not "PIPE layer" when referring to the protocol)
- "Data Link Layer" or "DLL" (not "Link Layer")
- "Transaction Layer" or "TLP layer" (not "Transport Layer")
- "ordered set" (not "ordered-set" or "OrderedSet")
- "K-character" (not "K-char" or "special character")
- "sys_clk" domain (not "system clock domain")
- "AsyncFIFO" (not "async FIFO" or "asynchronous FIFO")

**Component Names:**
- [ ] Consistent across all documents
- [ ] Match code class/module names
- [ ] Use established PCIe terminology

**Signal Names:**
- [ ] Match code exactly (case-sensitive)
- [ ] Consistent bit width notation ([15:0] or [7:0])
- [ ] Consistent suffix usage (_valid, _ready, _data)

### 4.2 Formatting Consistency

**Code Formatting:**
- [ ] File paths in backticks: `litepcie/dll/pipe.py`
- [ ] Signal names in backticks: `tx_data[15:0]`
- [ ] Class names in backticks: `PIPETransceiver`
- [ ] Constants in code style: `0xFB` or `K28.5`

**Lists:**
- [ ] Consistent bullet style (- for unordered, 1. for ordered)
- [ ] Consistent capitalization in list items
- [ ] Consistent punctuation (period or no period, but consistent)

**Tables:**
- [ ] Headers properly formatted
- [ ] Columns aligned
- [ ] Consistent cell content formatting

**Sections:**
- [ ] Consistent heading style (sentence case or title case)
- [ ] Consistent use of introductory paragraphs
- [ ] Consistent "See also" references at section ends

### 4.3 Diagram Style Consistency

**Box Drawing:**
- [ ] Consistent characters: ─│┌└┐┘├┤┬┴┼
- [ ] Consistent spacing inside boxes
- [ ] Consistent label alignment

**Arrows:**
- [ ] Consistent arrow style (→ ↓ ↑ ← or ASCII ->)
- [ ] Consistent data flow annotation
- [ ] Consistent label placement relative to arrows

**Layout:**
- [ ] Consistent diagram width (typically 65-75 chars)
- [ ] Consistent spacing between components
- [ ] Consistent nesting indentation

---

## 5. Technical Accuracy

### 5.1 Architecture Accuracy

**Layer Boundaries:**
- [ ] Interface definitions match implementation
- [ ] Data widths are correct
- [ ] Control signals are complete
- [ ] Clock domains are accurate

**Component Descriptions:**
- [ ] Component responsibilities are accurate
- [ ] Component interactions are correct
- [ ] State machines match implementation
- [ ] Timing requirements are accurate

**Data Flows:**
- [ ] Packet flows are traced correctly
- [ ] Transformations are accurate (64→8 bit, etc.)
- [ ] Buffer sizes are correct
- [ ] Latencies are realistic

### 5.2 Protocol Accuracy

**PCIe Compliance:**
- [ ] PIPE specification references are correct
- [ ] PCIe specification sections cited correctly
- [ ] Protocol requirements are accurate
- [ ] Timing requirements match spec

**Implementation Details:**
- [ ] Reset sequences match implementation
- [ ] State machines match code
- [ ] Error handling is correct
- [ ] Edge cases are handled

### 5.3 Performance Characteristics

**Timing:**
- [ ] Clock frequencies are accurate
- [ ] Latencies are realistic
- [ ] Throughput calculations are correct
- [ ] Buffer depths are appropriate

**Resources:**
- [ ] Buffer sizes are correct (e.g., 4KB retry buffer)
- [ ] FIFO depths are accurate
- [ ] Resource usage estimates are reasonable

---

## 6. Sign-off

### 6.1 Pre-Publication Checklist

**Completeness:**
- [ ] All required documents exist
- [ ] All required sections present in each document
- [ ] All diagrams included
- [ ] All cross-references complete

**Quality:**
- [ ] All automated validation commands pass
- [ ] All manual validation items checked
- [ ] Peer review completed
- [ ] Technical review completed

**Consistency:**
- [ ] Terminology consistent across all documents
- [ ] Formatting consistent
- [ ] Diagram style consistent
- [ ] Code references consistent

**Accuracy:**
- [ ] Technical content verified against code
- [ ] Protocol compliance verified
- [ ] Performance characteristics validated
- [ ] Examples tested

### 6.2 Final Sign-off

**Reviewers:**
- [ ] Technical review completed by: _________________ Date: _______
- [ ] Documentation review completed by: _____________ Date: _______
- [ ] Quality assurance completed by: _______________ Date: _______

**Publication:**
- [ ] All checklist items complete
- [ ] All validation commands pass with zero errors
- [ ] Ready for publication
- [ ] Version number assigned: _______
- [ ] Publication date: _______

---

## 7. Maintenance

### 7.1 Periodic Review Schedule

**Quarterly Review:**
- [ ] Run all automated validation commands
- [ ] Check for broken links
- [ ] Verify code references are still valid
- [ ] Update version numbers and dates

**After Major Changes:**
- [ ] Review affected documents
- [ ] Update diagrams if architecture changed
- [ ] Update cross-references
- [ ] Re-run full validation

### 7.2 Documentation Updates

**When to Update:**
- New features added to implementation
- Architecture changes
- Bug fixes that affect documented behavior
- New FPGA support added
- Performance optimizations

**Update Process:**
1. Identify affected documents
2. Update content and diagrams
3. Run validation checklist
4. Update cross-references
5. Commit with descriptive message

---

## 8. Validation Results Reference

### 8.1 Expected Validation Output

When all checks pass, expect:

```
✅ Link check complete - 113/113 links valid
✅ Code reference check complete - All paths valid
✅ Coverage analysis complete:
   - complete-system-architecture.md: 14 sections, 5 diagrams, 20 links
   - serdes-layer.md: 14 sections, 16 diagrams, 4 links
   - pipe-layer.md: 10 sections, 20 diagrams, 7 links
   - dll-layer.md: 13 sections, 36 diagrams, 4 links
   - tlp-layer.md: 16 sections, 39 diagrams, 2 links
   - integration-patterns.md: 9 sections, 38 diagrams, 14 links
✅ Component naming consistency - No inconsistencies found
```

### 8.2 Common Issues and Fixes

**Broken Links:**
- **Issue:** Relative paths don't resolve
- **Fix:** Use correct relative path from document location
- **Example:** `../guides/pipe-interface-guide.md` from architecture/ directory

**Code References:**
- **Issue:** File path doesn't exist
- **Fix:** Verify actual file location in repository
- **Example:** Use `litepcie/phy/common.py` (correct) instead of a non-existent path

**Diagram Formatting:**
- **Issue:** Columns not aligned in ASCII diagrams
- **Fix:** Use fixed-width font editor, align with spaces not tabs
- **Tool:** Use `column` command or careful manual alignment

**Naming Inconsistencies:**
- **Issue:** Component called different names in different docs
- **Fix:** Choose canonical name, update all occurrences
- **Example:** Use "DLL TX" consistently, not "DLL Transmitter" or "TX Path"

---

## Appendix A: Minimum Requirements

### Per-Document Minimums

All layer-specific documents (serdes, pipe, dll, tlp, integration) must meet:

- **Minimum 6 sections** (## level headings)
- **Minimum 3 diagrams** (code blocks with ASCII art)
- **At least 2 cross-references** to other documents
- **Code path references** to implementation files
- **At least 1 complete example** or data flow

### Quality Gates

Documentation cannot be published unless:

- ✅ Zero broken internal links
- ✅ Zero invalid code path references
- ✅ All automated validation commands pass
- ✅ Peer review approved
- ✅ Technical review approved

---

## Appendix B: Review Shortcuts

### Quick Review (15 minutes)

For rapid quality check:

1. Run all automated validation commands (5 min)
2. Spot-check 3 random diagrams for formatting (3 min)
3. Verify 5 random code references by opening files (3 min)
4. Check main README links work (2 min)
5. Scan for obvious typos/formatting issues (2 min)

### Full Review (2 hours)

For comprehensive quality assurance:

1. Run all automated validation commands (10 min)
2. Read through each document for readability (45 min)
3. Verify all diagrams are accurate (30 min)
4. Check all code references against implementation (20 min)
5. Test all examples if executable (15 min)

### Pre-Release Review (4 hours)

Before major release or publication:

1. Full review process above (2 hours)
2. Technical accuracy verification against code (1 hour)
3. Protocol compliance verification (30 min)
4. Cross-document consistency check (30 min)

---

**Checklist Version:** 1.0
**Last Updated:** 2025-10-18
**Maintainer:** LitePCIe Documentation Team
**Related:** [VALIDATION_STATUS.md](VALIDATION_STATUS.md) for latest validation results
