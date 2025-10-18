#!/usr/bin/env python3
"""
Comprehensive documentation validation script for LitePCIe architecture docs.
Validates all documentation created in Tasks 1-8 of the standalone architecture plan.
"""

import os
import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple

# ANSI color codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

class DocValidator:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.docs_dir = self.base_dir / "docs"
        self.arch_dir = self.docs_dir / "architecture"

        # Files created in Tasks 1-8
        self.task_files = [
            "complete-system-architecture.md",  # Task 1
            "serdes-layer.md",                   # Task 2
            "pipe-layer.md",                     # Task 3
            "dll-layer.md",                      # Task 4
            "tlp-layer.md",                      # Task 5
            "integration-patterns.md",           # Task 6
            "../README.md",                      # Task 7 (modified)
            "quick-reference.md",                # Task 8
        ]

        # Validation results
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

        # Component name tracking for consistency
        self.component_names: Dict[str, Set[str]] = defaultdict(set)

        # Statistics
        self.stats = {
            'total_files': 0,
            'total_sections': 0,
            'total_diagrams': 0,
            'total_links': 0,
            'broken_links': 0,
            'invalid_paths': 0,
            'inconsistent_names': 0,
        }

    def print_header(self, text: str):
        """Print section header."""
        print(f"\n{BOLD}{BLUE}{'='*80}{RESET}")
        print(f"{BOLD}{BLUE}{text}{RESET}")
        print(f"{BOLD}{BLUE}{'='*80}{RESET}\n")

    def print_status(self, status: str, message: str):
        """Print status message."""
        if status == "PASS":
            print(f"  {GREEN}✓{RESET} {message}")
        elif status == "WARN":
            print(f"  {YELLOW}⚠{RESET} {message}")
        elif status == "FAIL":
            print(f"  {RED}✗{RESET} {message}")
        else:
            print(f"  {BLUE}ℹ{RESET} {message}")

    def validate_file_exists(self, filepath: str) -> bool:
        """Check if a file exists."""
        full_path = self.arch_dir / filepath
        return full_path.exists()

    def step1_validate_links(self):
        """Step 1: Validate all internal links."""
        self.print_header("Step 1: Validating Internal Links")

        # Pattern to match markdown links: [text](path) or [text](path#anchor)
        link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

        for filename in self.task_files:
            filepath = self.arch_dir / filename
            if not filepath.exists():
                self.errors.append(f"File not found: {filename}")
                self.print_status("FAIL", f"Missing file: {filename}")
                continue

            self.stats['total_files'] += 1

            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                line_num = 0
                for line in content.split('\n'):
                    line_num += 1
                    matches = link_pattern.findall(line)

                    for text, path in matches:
                        self.stats['total_links'] += 1

                        # Skip external links (http/https)
                        if path.startswith('http://') or path.startswith('https://'):
                            continue

                        # Skip anchor-only links
                        if path.startswith('#'):
                            continue

                        # Extract path without anchor
                        link_path = path.split('#')[0]
                        if not link_path:
                            continue

                        # Resolve relative paths
                        if link_path.startswith('..'):
                            # Parent directory reference
                            link_file = filepath.parent.parent / link_path.lstrip('../')
                        elif '/' in link_path:
                            # Subdirectory reference
                            link_file = self.docs_dir / link_path
                        else:
                            # Same directory
                            link_file = filepath.parent / link_path

                        if not link_file.exists():
                            self.errors.append(
                                f"{filename}:{line_num}: Broken link to '{path}' (resolved to {link_file})"
                            )
                            self.stats['broken_links'] += 1
                            self.print_status("FAIL", f"{filename}:{line_num}: Broken link → {path}")

        # Summary
        if self.stats['broken_links'] == 0:
            self.print_status("PASS", f"All {self.stats['total_links']} links are valid")
        else:
            self.print_status("FAIL", f"Found {self.stats['broken_links']} broken links")

    def step2_verify_diagrams(self):
        """Step 2: Verify diagram consistency (component naming)."""
        self.print_header("Step 2: Verifying Diagram Consistency")

        # Common component name patterns to check
        component_patterns = {
            'TLP': ['TLP', 'Transaction Layer', 'tlp'],
            'DLL': ['DLL', 'Data Link Layer', 'dll'],
            'PIPE': ['PIPE', 'PHY Interface', 'pipe'],
            'SERDES': ['SERDES', 'Transceiver', 'serdes'],
            'LTSSM': ['LTSSM', 'Link Training State Machine'],
            'LCRC': ['LCRC'],
            'ACK/NAK': ['ACK', 'NAK', 'ACK/NAK'],
        }

        for filename in self.task_files:
            filepath = self.arch_dir / filename
            if not filepath.exists():
                continue

            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

                # Count code blocks (diagrams are typically in code blocks)
                diagram_count = content.count('```') // 2
                self.stats['total_diagrams'] += diagram_count

                # Extract component names from diagrams
                # Look for lines in box-drawing diagrams
                in_diagram = False
                for line in content.split('\n'):
                    if line.strip() == '```':
                        in_diagram = not in_diagram
                    elif in_diagram:
                        # Extract text from box drawing (between │ or within boxes)
                        if '│' in line:
                            # Extract text between box characters
                            parts = line.split('│')
                            for part in parts:
                                stripped = part.strip()
                                if stripped and len(stripped) > 2:
                                    # Store component reference
                                    for category, variants in component_patterns.items():
                                        for variant in variants:
                                            if variant in stripped:
                                                self.component_names[category].add(stripped)

        # Check for consistency
        inconsistencies = []
        for category, references in self.component_names.items():
            if len(references) > 5:  # More than 5 unique references might indicate inconsistency
                inconsistencies.append(f"{category}: {len(references)} variations found")
                self.stats['inconsistent_names'] += 1

        if inconsistencies:
            self.print_status("WARN", f"Potential naming inconsistencies detected:")
            for inc in inconsistencies:
                self.warnings.append(f"Component naming: {inc}")
                print(f"    - {inc}")
        else:
            self.print_status("PASS", "Component naming appears consistent")

        self.print_status("INFO", f"Total diagrams found: {self.stats['total_diagrams']}")

    def step3_verify_code_references(self):
        """Step 3: Verify code path references."""
        self.print_header("Step 3: Verifying Code Path References")

        # Pattern to match code paths like `litepcie/dll/pipe.py`
        code_path_pattern = re.compile(r'`(litepcie/[^`]+)`')

        for filename in self.task_files:
            filepath = self.arch_dir / filename
            if not filepath.exists():
                continue

            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                line_num = 0
                for line in content.split('\n'):
                    line_num += 1
                    matches = code_path_pattern.findall(line)

                    for path in matches:
                        # Check if path exists
                        full_path = self.base_dir / path
                        if not full_path.exists():
                            # Could be a directory
                            if not full_path.parent.exists():
                                self.errors.append(
                                    f"{filename}:{line_num}: Invalid code reference '{path}'"
                                )
                                self.stats['invalid_paths'] += 1
                                self.print_status("FAIL", f"{filename}:{line_num}: Invalid path → {path}")
                            elif path.endswith('/'):
                                # Directory reference - check parent
                                if full_path.parent.exists():
                                    self.print_status("PASS", f"{filename}:{line_num}: Valid dir → {path}")
                                else:
                                    self.warnings.append(
                                        f"{filename}:{line_num}: Directory reference may be invalid '{path}'"
                                    )
                                    self.print_status("WARN", f"{filename}:{line_num}: Unverified dir → {path}")

        if self.stats['invalid_paths'] == 0:
            self.print_status("PASS", "All code path references are valid")
        else:
            self.print_status("FAIL", f"Found {self.stats['invalid_paths']} invalid code paths")

    def step4_check_cross_references(self):
        """Step 4: Check cross-references between docs."""
        self.print_header("Step 4: Checking Cross-References")

        # Each layer doc should reference the master architecture doc
        layer_docs = [
            "serdes-layer.md",
            "pipe-layer.md",
            "dll-layer.md",
            "tlp-layer.md",
            "integration-patterns.md",
        ]

        master_doc = "complete-system-architecture.md"

        missing_refs = []
        for layer_doc in layer_docs:
            filepath = self.arch_dir / layer_doc
            if not filepath.exists():
                continue

            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                if master_doc not in content:
                    missing_refs.append(layer_doc)
                    self.warnings.append(
                        f"{layer_doc} doesn't reference master doc ({master_doc})"
                    )
                    self.print_status("WARN", f"{layer_doc} missing reference to {master_doc}")
                else:
                    self.print_status("PASS", f"{layer_doc} references master doc")

        # Check bidirectional references
        # Master doc should reference all layer docs
        master_path = self.arch_dir / master_doc
        if master_path.exists():
            with open(master_path, 'r', encoding='utf-8') as f:
                master_content = f.read()
                for layer_doc in layer_docs:
                    if layer_doc not in master_content:
                        self.warnings.append(
                            f"Master doc doesn't reference {layer_doc}"
                        )
                        self.print_status("WARN", f"Master doc missing reference to {layer_doc}")
                    else:
                        self.print_status("PASS", f"Master doc references {layer_doc}")

    def step5_generate_coverage_report(self):
        """Step 5: Generate documentation coverage report."""
        self.print_header("Step 5: Documentation Coverage Report")

        print(f"\n{BOLD}File Coverage:{RESET}")
        print(f"{'File':<45} {'Sections':<10} {'Diagrams':<10} {'Links':<10}")
        print("-" * 75)

        total_sections = 0
        total_diagrams = 0
        total_links = 0

        link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

        for filename in self.task_files:
            filepath = self.arch_dir / filename
            if not filepath.exists():
                print(f"{filename:<45} {'MISSING':<10} {'-':<10} {'-':<10}")
                continue

            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

                # Count sections (## headers)
                sections = content.count('\n## ')

                # Count diagrams (code blocks)
                diagrams = content.count('```') // 2

                # Count links
                links = len(link_pattern.findall(content))

                total_sections += sections
                total_diagrams += diagrams
                total_links += links

                print(f"{filename:<45} {sections:<10} {diagrams:<10} {links:<10}")

        print("-" * 75)
        print(f"{'TOTAL':<45} {total_sections:<10} {total_diagrams:<10} {total_links:<10}")

        self.stats['total_sections'] = total_sections

        # Check minimum requirements (from Task 9)
        print(f"\n{BOLD}Quality Metrics:{RESET}")

        # Each layer doc should have at least 6 sections and 3 diagrams
        layer_docs = [
            "serdes-layer.md",
            "pipe-layer.md",
            "dll-layer.md",
            "tlp-layer.md",
        ]

        for layer_doc in layer_docs:
            filepath = self.arch_dir / layer_doc
            if not filepath.exists():
                continue

            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                sections = content.count('\n## ')
                diagrams = content.count('```') // 2

                if sections >= 6:
                    self.print_status("PASS", f"{layer_doc}: {sections} sections (≥6 required)")
                else:
                    self.print_status("WARN", f"{layer_doc}: {sections} sections (<6 required)")
                    self.warnings.append(f"{layer_doc} has fewer than 6 sections")

                if diagrams >= 3:
                    self.print_status("PASS", f"{layer_doc}: {diagrams} diagrams (≥3 required)")
                else:
                    self.print_status("WARN", f"{layer_doc}: {diagrams} diagrams (<3 required)")
                    self.warnings.append(f"{layer_doc} has fewer than 3 diagrams")

    def step6_final_summary(self):
        """Step 6: Final validation summary."""
        self.print_header("Step 6: Validation Summary")

        print(f"{BOLD}Statistics:{RESET}")
        print(f"  Total files checked: {self.stats['total_files']}")
        print(f"  Total sections: {self.stats['total_sections']}")
        print(f"  Total diagrams: {self.stats['total_diagrams']}")
        print(f"  Total links: {self.stats['total_links']}")
        print()

        print(f"{BOLD}Issues Found:{RESET}")
        print(f"  {RED}Errors: {len(self.errors)}{RESET}")
        print(f"  {YELLOW}Warnings: {len(self.warnings)}{RESET}")
        print(f"  {BLUE}Info: {len(self.info)}{RESET}")
        print()

        if self.errors:
            print(f"{BOLD}{RED}ERRORS:{RESET}")
            for error in self.errors:
                print(f"  {RED}✗{RESET} {error}")
            print()

        if self.warnings:
            print(f"{BOLD}{YELLOW}WARNINGS:{RESET}")
            for warning in self.warnings:
                print(f"  {YELLOW}⚠{RESET} {warning}")
            print()

        # Final verdict
        print(f"\n{BOLD}{'='*80}{RESET}")
        if len(self.errors) == 0:
            if len(self.warnings) == 0:
                print(f"{BOLD}{GREEN}✓ VALIDATION PASSED - All checks successful!{RESET}")
                return 0
            else:
                print(f"{BOLD}{YELLOW}⚠ VALIDATION PASSED WITH WARNINGS{RESET}")
                return 0
        else:
            print(f"{BOLD}{RED}✗ VALIDATION FAILED - {len(self.errors)} error(s) found{RESET}")
            return 1

    def run_validation(self) -> int:
        """Run all validation steps."""
        print(f"{BOLD}{BLUE}")
        print("╔════════════════════════════════════════════════════════════════════════════╗")
        print("║           LitePCIe Architecture Documentation Validator                   ║")
        print("║                          Task 9 Validation                                 ║")
        print("╚════════════════════════════════════════════════════════════════════════════╝")
        print(f"{RESET}")

        # Run all validation steps
        self.step1_validate_links()
        self.step2_verify_diagrams()
        self.step3_verify_code_references()
        self.step4_check_cross_references()
        self.step5_generate_coverage_report()

        # Final summary
        return self.step6_final_summary()


def main():
    """Main entry point."""
    # Get repository root
    script_dir = Path(__file__).parent

    # Create validator
    validator = DocValidator(script_dir)

    # Run validation
    exit_code = validator.run_validation()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
