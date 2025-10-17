# LitePCIe PIPE/DLL Documentation

This directory contains comprehensive documentation for the LitePCIe PIPE interface and Data Link Layer implementation.

## Quick Navigation

### 🏗️ Architecture Documentation
**Location:** `architecture/`

Core architecture and design documents explaining the overall system design:

- [PIPE Architecture](architecture/pipe-architecture.md) - PIPE interface architecture and component diagrams
- [Clock Domain Architecture](architecture/clock-domain-architecture.md) - Multi-domain clock strategy and CDC patterns
- [Integration Strategy](architecture/integration-strategy.md) - Overall integration approach and roadmap

### 📚 User Guides
**Location:** `guides/`

How-to guides and tutorials for using the PIPE interface:

- [PIPE Interface Guide](guides/pipe-interface-guide.md) - Complete user guide for PIPE interface usage
- [PIPE Integration Examples](guides/pipe-integration-examples.md) - Integration patterns and code examples
- [PIPE Testing Guide](guides/pipe-testing-guide.md) - Testing strategies and test development guide
- [Hardware Debugging](guides/hardware-debugging.md) - LiteScope integration and hardware debugging techniques

### 📖 Reference Documentation
**Location:** `reference/`

Technical specifications and reference material:

- [PIPE Interface Specification](reference/pipe-interface-spec.md) - Detailed PIPE signal specification
- [PIPE Performance](reference/pipe-performance.md) - Performance analysis and optimization guide

### 🔧 Development Documentation
**Location:** `development/`

Development status and quality metrics:

- [Implementation Status](development/implementation-status.md) - Current implementation status across all phases
- [Code Quality](development/code-quality.md) - Code quality standards and guidelines

### ✅ Phase Completion Summaries
**Location:** `phases/`

Summary documents for each completed implementation phase:

- [Phase 4 Completion](phases/phase-4-completion-summary.md) - PIPE TX/RX Datapath + Cleanup
- [Phase 5 Completion](phases/phase-5-completion-summary.md) - Ordered Sets & Link Training Foundation
- [Phase 6 Completion](phases/phase-6-completion-summary.md) - LTSSM (Link Training State Machine)
- [Phase 7 Completion](phases/phase-7-completion-summary.md) - Advanced LTSSM Features (Gen2, Multi-lane, Power States)
- [Phase 9 Completion](phases/phase-9-completion-summary.md) - Internal Transceiver Support

### 📋 Implementation Plans
**Location:** `plans/`

Detailed implementation plans for each phase (active plans only):

- [2025-10-16: Phase 3](plans/2025-10-16-phase-3-pipe-interface-external-phy.md) - PIPE Interface & External PHY
- [2025-10-17: Phase 5](plans/2025-10-17-phase-5-ordered-sets-link-training.md) - Ordered Sets & Link Training
- [2025-10-17: Phase 7](plans/2025-10-17-phase-7-advanced-ltssm-features.md) - Advanced LTSSM Features
- [2025-10-17: Phase 8](plans/2025-10-17-phase-8-hardware-validation.md) - Hardware Validation
- [2025-10-17: Phase 9 v2](plans/2025-10-17-phase-9-internal-transceiver-support-v2.md) - Internal Transceiver Support (latest)
- [2025-10-18: Reference Comparison](plans/2025-10-18-reference-comparison-and-improvements.md) - Reference implementation comparison

### 🔍 Investigations
**Location:** `investigations/`

Detailed technical investigations and analysis documents:

#### Phase 9 Investigation Documents
- [8b/10b Investigation](investigations/phase-9/8b10b-investigation.md) - Analysis of 8b/10b encoding approaches
- [8b/10b Validation](investigations/phase-9/8b10b-validation.md) - Architecture decision and validation
- [Dependencies](investigations/phase-9/dependencies.md) - liteiclink and dependency documentation
- [Plan Review](investigations/phase-9/plan-review.md) - Critical review of Phase 9 plan
- [Testing Strategy](investigations/phase-9/testing-strategy.md) - Tiered testing approach
- [Testing Summary](investigations/phase-9/testing-summary.md) - Test documentation and results

#### Documentation Strategy
- [Strategy Evaluation](investigations/documentation-strategy/evaluation.md) - Comprehensive documentation assessment
- [Strategy Summary](investigations/documentation-strategy/summary.md) - Executive summary of documentation needs
- [Checklist](investigations/documentation-strategy/checklist.md) - Documentation improvement checklist

### 📝 Session Notes
**Location:** `sessions/`

Detailed session work logs and summaries:

- [2025-10-17: Phase 5 Completion](sessions/2025-10-17-phase5-completion.md) - TS1/TS2 implementation session

### 🗄️ Archive
**Location:** `archive/`

Superseded plans and historical documents (kept for reference):

- Old phase plans (Phase 4, 6, 9 v1)
- Historical architectural reviews
- Superseded implementation plans

## Documentation Organization Principles

### Architecture vs. Guides vs. Reference

- **Architecture** (`architecture/`) - System design, high-level concepts, integration strategy
- **Guides** (`guides/`) - How-to documents, tutorials, practical usage
- **Reference** (`reference/`) - Specifications, technical details, API reference

### Plans vs. Completion Summaries

- **Plans** (`plans/`) - Forward-looking implementation plans (what we will do)
- **Phases** (`phases/`) - Backward-looking completion summaries (what we did)

### Active vs. Archive

- **Active** (all directories except `archive/`) - Current and relevant documentation
- **Archive** (`archive/`) - Superseded documents kept for historical reference

## Getting Started

### For New Users
1. Start with [PIPE Interface Guide](guides/pipe-interface-guide.md)
2. Review [PIPE Architecture](architecture/pipe-architecture.md)
3. Explore [Integration Examples](guides/pipe-integration-examples.md)
4. Check [Implementation Status](development/implementation-status.md) for current progress

### For Developers
1. Review [Integration Strategy](architecture/integration-strategy.md)
2. Check [Implementation Status](development/implementation-status.md) for current phase
3. Read relevant phase plan in `plans/`
4. Follow [Code Quality](development/code-quality.md) standards
5. Use [Testing Guide](guides/pipe-testing-guide.md) for test development

### For Hardware Engineers
1. Check [Hardware Debugging](guides/hardware-debugging.md) for LiteScope integration
2. Review [Clock Domain Architecture](architecture/clock-domain-architecture.md)
3. See phase completion summaries for implementation details

## Project Status

**Current Phase:** Phase 9 (Internal Transceiver Support) - Pre-Implementation Complete
**Latest Completion:** Phase 7 (Advanced LTSSM Features)
**Status Tracking:** See [Implementation Status](development/implementation-status.md)

## Contributing

When adding new documentation:

1. Place documents in the appropriate category directory
2. Update this README with links to new documents
3. Follow existing naming conventions
4. Update cross-references in related documents
5. Add entry to relevant phase completion summary

## External References

- **PCIe Base Specification 4.0:** [PCI-SIG](https://pcisig.com/)
- **Intel PIPE 3.0 Specification:** PHY Interface for PCI Express
- **LiteX:** [https://github.com/enjoy-digital/litex](https://github.com/enjoy-digital/litex)
- **liteiclink:** [https://github.com/enjoy-digital/liteiclink](https://github.com/enjoy-digital/liteiclink)

---

**Last Updated:** 2025-10-18
**Documentation Structure Version:** 2.0
