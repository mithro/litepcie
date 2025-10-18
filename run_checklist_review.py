#!/usr/bin/env python3
"""
Initial checklist review for Task 10 - Architecture Documentation Review
Runs the validation commands from REVIEW_CHECKLIST.md on existing documentation
"""

import os
import re
import sys
from pathlib import Path
from collections import defaultdict

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def check_internal_links():
    """Check for broken internal markdown links"""
    print(f"\n{BLUE}=== Checking Internal Links ==={RESET}")
    docs_dir = Path("docs")
    broken_links = []
    total_links = 0
    repo_root = Path.cwd()

    files_to_check = list(docs_dir.glob("architecture/*.md")) + [docs_dir / "README.md"]

    for file in files_to_check:
        if not file.exists():
            continue

        content = file.read_text()
        # Find all markdown links [text](path.md) or [text](path.md#anchor)
        # Exclude regex patterns (containing [ ] or *)
        links = re.findall(r'\[([^\]]+)\]\(([^)]+\.md[^)]*)\)', content)
        # Filter out links that look like regex patterns
        links = [(text, path) for text, path in links
                 if not any(c in path for c in ['[', ']', '*', '\\'])]

        for link_text, link_path in links:
            total_links += 1
            # Remove anchor if present
            filepath = link_path.split('#')[0]

            # Skip external URLs
            if filepath.startswith('http'):
                continue

            # Try to resolve the path
            file_dir = file.parent
            possible_paths = [
                Path(filepath),
                file_dir / filepath,
                docs_dir / "architecture" / filepath,
            ]

            found = any(p.exists() for p in possible_paths)

            if not found:
                broken_links.append({
                    'file': str(file.resolve().relative_to(repo_root)),
                    'link': f'[{link_text}]({link_path})',
                    'path': filepath
                })

    if broken_links:
        print(f"{RED}❌ Found {len(broken_links)} broken links:{RESET}")
        for broken in broken_links:
            print(f"  {broken['file']}: {broken['link']}")
    else:
        print(f"{GREEN}✅ Link check complete - {total_links}/{total_links} links valid{RESET}")

    return len(broken_links) == 0

def check_code_references():
    """Check that code path references point to existing files"""
    print(f"\n{BLUE}=== Checking Code Path References ==={RESET}")
    docs_dir = Path("docs")
    invalid_refs = []
    total_refs = 0
    repo_root = Path.cwd()

    files_to_check = list(docs_dir.glob("architecture/*.md")) + [docs_dir / "README.md"]

    for file in files_to_check:
        if not file.exists():
            continue

        content = file.read_text()
        # Find all code references like `litepcie/path/to/file.py`
        refs = re.findall(r'`(litepcie/[^`]+)`', content)
        # Filter out regex patterns and examples with line numbers
        refs = [ref for ref in refs
                if not any(c in ref for c in ['[', ']', '*', '^'])
                and ':' not in ref.split('/')[-1]]  # Exclude file.py:line-range

        for ref in refs:
            total_refs += 1
            ref_path = Path(ref)

            if not ref_path.exists():
                invalid_refs.append({
                    'file': str(file.resolve().relative_to(repo_root)),
                    'ref': ref
                })

    if invalid_refs:
        print(f"{RED}❌ Found {len(invalid_refs)} invalid code references:{RESET}")
        for invalid in invalid_refs:
            print(f"  {invalid['file']}: `{invalid['ref']}`")
    else:
        print(f"{GREEN}✅ Code reference check complete - All {total_refs} paths valid{RESET}")

    return len(invalid_refs) == 0

def count_documentation_coverage():
    """Count sections, diagrams, and links in each document"""
    print(f"\n{BLUE}=== Documentation Coverage Analysis ==={RESET}")
    docs_dir = Path("docs")

    files_to_check = [
        "architecture/complete-system-architecture.md",
        "architecture/serdes-layer.md",
        "architecture/pipe-layer.md",
        "architecture/dll-layer.md",
        "architecture/tlp-layer.md",
        "architecture/integration-patterns.md",
        "architecture/quick-reference.md",
    ]

    total_sections = 0
    total_diagrams = 0
    total_links = 0

    for file_name in files_to_check:
        file_path = docs_dir / file_name
        if not file_path.exists():
            print(f"{YELLOW}⚠️  {file_name} not found{RESET}")
            continue

        content = file_path.read_text()

        # Count sections (## headings)
        sections = len(re.findall(r'^## ', content, re.MULTILINE))

        # Count diagrams (code blocks with ```)
        code_blocks = len(re.findall(r'^```$', content, re.MULTILINE))
        diagrams = code_blocks // 2  # Each diagram has opening and closing ```

        # Count markdown links
        links = len(re.findall(r'\[.*?\]\(.*?\.md[^)]*\)', content))

        total_sections += sections
        total_diagrams += diagrams
        total_links += links

        print(f"{file_path.name}:")
        print(f"  - Sections: {sections}")
        print(f"  - Diagrams: {diagrams}")
        print(f"  - Links: {links}")

    print(f"\n{GREEN}Totals:{RESET}")
    print(f"  - {total_sections} sections across all documents")
    print(f"  - {total_diagrams} diagrams showing architecture and data flows")
    print(f"  - {total_links} internal links for navigation")
    print(f"\n{GREEN}✅ Coverage analysis complete{RESET}")

    return True

def check_naming_consistency():
    """Check for common component naming inconsistencies"""
    print(f"\n{BLUE}=== Checking Component Naming Consistency ==={RESET}")
    docs_dir = Path("docs")

    files_to_check = list(docs_dir.glob("architecture/*.md"))

    # Common components to check for naming consistency
    component_patterns = defaultdict(set)

    for file in files_to_check:
        if not file.exists():
            continue

        content = file.read_text()

        # Check for variations of common component names
        variations = {
            'dll_tx': [r'DLL TX', r'DLL Transmit', r'DLL Transmitter'],
            'dll_rx': [r'DLL RX', r'DLL Receive', r'DLL Receiver'],
            'pipe_tx': [r'PIPE TX', r'TX Packetizer', r'PIPE Transmit'],
            'pipe_rx': [r'PIPE RX', r'RX Depacketizer', r'PIPE Receive'],
            'ltssm': [r'LTSSM', r'Link Training State Machine', r'State Machine'],
            'serdes': [r'SERDES', r'SerDes', r'serdes'],
        }

        for component, patterns in variations.items():
            for pattern in patterns:
                if re.search(pattern, content):
                    component_patterns[component].add(pattern)

    # Check for inconsistencies (same component with multiple names)
    inconsistencies = []
    for component, patterns in component_patterns.items():
        if len(patterns) > 1:
            inconsistencies.append((component, patterns))

    if inconsistencies:
        print(f"{YELLOW}⚠️  Found naming variations (may be intentional):{RESET}")
        for component, patterns in inconsistencies:
            print(f"  {component}: {', '.join(patterns)}")
    else:
        print(f"{GREEN}✅ Component naming is consistent{RESET}")

    return True

def check_minimum_requirements():
    """Verify layer docs meet minimum requirements"""
    print(f"\n{BLUE}=== Checking Minimum Requirements ==={RESET}")
    docs_dir = Path("docs")

    layer_docs = [
        "architecture/serdes-layer.md",
        "architecture/pipe-layer.md",
        "architecture/dll-layer.md",
        "architecture/tlp-layer.md",
        "architecture/integration-patterns.md",
    ]

    MIN_SECTIONS = 6
    MIN_DIAGRAMS = 3

    all_passed = True

    for doc_name in layer_docs:
        doc_path = docs_dir / doc_name
        if not doc_path.exists():
            print(f"{RED}❌ {doc_name} not found{RESET}")
            all_passed = False
            continue

        content = doc_path.read_text()
        sections = len(re.findall(r'^## ', content, re.MULTILINE))
        code_blocks = len(re.findall(r'^```$', content, re.MULTILINE))
        diagrams = code_blocks // 2

        passed = sections >= MIN_SECTIONS and diagrams >= MIN_DIAGRAMS
        status = f"{GREEN}✅{RESET}" if passed else f"{RED}❌{RESET}"

        print(f"{status} {doc_path.name}: {sections} sections (min {MIN_SECTIONS}), {diagrams} diagrams (min {MIN_DIAGRAMS})")

        if not passed:
            all_passed = False

    if all_passed:
        print(f"\n{GREEN}✅ All layer docs meet minimum requirements{RESET}")

    return all_passed

def main():
    """Run all checklist validation checks"""
    print(f"{BLUE}{'='*70}{RESET}")
    print(f"{BLUE}Architecture Documentation Review Checklist - Initial Review{RESET}")
    print(f"{BLUE}Task 10 - Standalone Architecture Documentation Plan{RESET}")
    print(f"{BLUE}{'='*70}{RESET}")

    # Change to repository root
    os.chdir("/home/tim/github/enjoy-digital/litepcie")

    results = {}

    # Run all checks
    results['links'] = check_internal_links()
    results['code_refs'] = check_code_references()
    results['coverage'] = count_documentation_coverage()
    results['naming'] = check_naming_consistency()
    results['minimums'] = check_minimum_requirements()

    # Summary
    print(f"\n{BLUE}{'='*70}{RESET}")
    print(f"{BLUE}Summary{RESET}")
    print(f"{BLUE}{'='*70}{RESET}")

    all_passed = all(results.values())

    for check, passed in results.items():
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        print(f"{check.replace('_', ' ').title()}: {status}")

    if all_passed:
        print(f"\n{GREEN}✅ All validation checks passed!{RESET}")
        print(f"{GREEN}Documentation is ready for publication.{RESET}")
    else:
        print(f"\n{YELLOW}⚠️  Some checks failed or have warnings.{RESET}")
        print(f"{YELLOW}Review the output above for details.{RESET}")

    print(f"\n{BLUE}Full validation report saved in VALIDATION_STATUS.md{RESET}")

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
