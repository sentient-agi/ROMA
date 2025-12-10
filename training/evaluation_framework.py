"""
ACE Training Evaluation & Refinement Framework

This script helps identify weak patterns and gaps in the training data
by analyzing the results from all training sessions.
"""

import json
import glob
from pathlib import Path
from collections import defaultdict
import statistics

def load_all_training_results(results_dir="results"):
    """Load all training result files."""
    results_path = Path(results_dir)
    all_results = []

    for result_file in results_path.glob("training_results_*.json"):
        with open(result_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            all_results.append({
                'file': result_file.name,
                'data': data
            })

    return all_results

def analyze_pattern_coverage(all_results):
    """Analyze what patterns are covered and identify gaps."""

    patterns = defaultdict(list)

    for result_set in all_results:
        for result in result_set['data']['results']:
            scenario = result['scenario']
            name = scenario['name']
            goal = scenario['goal'].lower()

            # Categorize by detected patterns
            if 'notion' in goal:
                patterns['notion_integration'].append(name)
            if 'api' in goal or 'webhook' in goal:
                patterns['api_integration'].append(name)
            if 'sync' in goal or 'synchron' in goal:
                patterns['data_sync'].append(name)
            if 'auth' in goal or 'security' in goal or 'permission' in goal:
                patterns['authentication'].append(name)
            if 'analytics' in goal or 'dashboard' in goal or 'monitor' in goal:
                patterns['analytics'].append(name)
            if 'backup' in goal or 'export' in goal:
                patterns['data_management'].append(name)
            if 'automat' in goal or 'workflow' in goal:
                patterns['automation'].append(name)
            if 'mobile' in goal or 'widget' in goal or 'ios' in goal:
                patterns['mobile'].append(name)
            if 'ai' in goal or 'llm' in goal or 'ml' in goal:
                patterns['ai_ml'].append(name)
            if 'real-time' in goal or 'realtime' in goal or 'streaming' in goal:
                patterns['realtime'].append(name)
            if 'search' in goal or 'index' in goal:
                patterns['search'].append(name)
            if 'payment' in goal or 'invoice' in goal or 'billing' in goal:
                patterns['payments'].append(name)

    return patterns

def identify_weak_patterns(all_results):
    """Identify patterns with high complexity or low success."""

    weak_patterns = []

    for result_set in all_results:
        for result in result_set['data']['results']:
            if not result['success']:
                weak_patterns.append({
                    'scenario': result['scenario']['name'],
                    'error': result.get('error', 'Unknown'),
                    'category': result['scenario'].get('category', 'unknown')
                })
            elif result['metadata'].get('tokens_used', 0) > 4000:  # High complexity
                weak_patterns.append({
                    'scenario': result['scenario']['name'],
                    'reason': 'High complexity',
                    'tokens': result['metadata']['tokens_used'],
                    'cost': result['metadata']['cost_usd']
                })

    return weak_patterns

def suggest_gap_scenarios(patterns):
    """Suggest scenarios to fill identified gaps."""

    suggestions = []

    # Check for underrepresented patterns
    pattern_counts = {k: len(v) for k, v in patterns.items()}

    # Define minimum thresholds
    min_threshold = 5

    for pattern, count in pattern_counts.items():
        if count < min_threshold:
            suggestions.append({
                'pattern': pattern,
                'current_count': count,
                'recommended_additional': min_threshold - count,
                'priority': 'HIGH' if count < 3 else 'MEDIUM'
            })

    # Check for completely missing patterns
    expected_patterns = [
        'realtime', 'ai_ml', 'search', 'payments',
        'multi_tenant', 'rate_limiting', 'caching'
    ]

    for expected in expected_patterns:
        if expected not in pattern_counts or pattern_counts[expected] == 0:
            suggestions.append({
                'pattern': expected,
                'current_count': 0,
                'recommended_additional': 3,
                'priority': 'HIGH'
            })

    return suggestions

def generate_evaluation_report(output_file="EVALUATION_REPORT.md"):
    """Generate comprehensive evaluation report."""

    all_results = load_all_training_results()
    patterns = analyze_pattern_coverage(all_results)
    weak_patterns = identify_weak_patterns(all_results)
    gap_suggestions = suggest_gap_scenarios(patterns)

    # Calculate statistics
    total_scenarios = sum(r['data']['total_scenarios'] for r in all_results)
    total_successful = sum(r['data']['successful'] for r in all_results)
    total_cost = sum(r['data']['total_cost_usd'] for r in all_results)
    total_tokens = sum(r['data']['total_tokens'] for r in all_results)

    report = f"""# ACE Training Evaluation Report

## Overall Statistics

- **Total Training Sessions**: {len(all_results)}
- **Total Scenarios Trained**: {total_scenarios}
- **Success Rate**: {(total_successful/total_scenarios*100):.1f}%
- **Total Cost**: ${total_cost:.2f}
- **Total Tokens**: {total_tokens:,}
- **Avg Cost/Scenario**: ${total_cost/total_scenarios:.4f}

## Pattern Coverage Analysis

"""

    # Pattern coverage table
    report += "| Pattern | Count | Coverage |\n"
    report += "|---------|-------|----------|\n"

    for pattern, scenarios in sorted(patterns.items(), key=lambda x: len(x[1]), reverse=True):
        coverage = len(scenarios) / total_scenarios * 100
        report += f"| {pattern.replace('_', ' ').title()} | {len(scenarios)} | {coverage:.1f}% |\n"

    # Identified gaps
    report += "\n## Identified Gaps\n\n"

    if gap_suggestions:
        report += "The following patterns need more training scenarios:\n\n"
        for suggestion in sorted(gap_suggestions, key=lambda x: x['priority'], reverse=True):
            report += f"- **{suggestion['pattern'].replace('_', ' ').title()}**: "
            report += f"{suggestion['current_count']} scenarios "
            report += f"(recommend +{suggestion['recommended_additional']}) "
            report += f"[{suggestion['priority']} priority]\n"
    else:
        report += "No significant gaps identified. Coverage is well-distributed.\n"

    # Weak patterns
    if weak_patterns:
        report += "\n## Patterns Needing Refinement\n\n"

        failed = [p for p in weak_patterns if 'error' in p]
        complex = [p for p in weak_patterns if 'tokens' in p]

        if failed:
            report += f"### Failed Scenarios ({len(failed)})\n\n"
            for p in failed[:10]:  # Top 10
                report += f"- {p['scenario']}: {p['error']}\n"

        if complex:
            report += f"\n### High Complexity Scenarios ({len(complex)})\n\n"
            for p in sorted(complex, key=lambda x: x['tokens'], reverse=True)[:10]:
                report += f"- {p['scenario']}: {p['tokens']:,} tokens (${p['cost']:.4f})\n"

    # Recommendations
    report += "\n## Recommendations\n\n"
    report += "### Immediate Actions\n\n"

    high_priority_gaps = [g for g in gap_suggestions if g['priority'] == 'HIGH']
    if high_priority_gaps:
        report += f"1. **Add {sum(g['recommended_additional'] for g in high_priority_gaps)} targeted scenarios** "
        report += "to address high-priority gaps:\n"
        for gap in high_priority_gaps:
            report += f"   - {gap['recommended_additional']}x {gap['pattern'].replace('_', ' ')} scenarios\n"

    if weak_patterns:
        report += f"\n2. **Review and optimize {len(weak_patterns)} scenarios** "
        report += "with high complexity or failures\n"

    report += "\n### Next Steps\n\n"
    report += "1. Create targeted scenarios for identified gaps\n"
    report += "2. Simplify or break down high-complexity scenarios\n"
    report += "3. Re-train on gap-filling scenarios\n"
    report += "4. Validate improvements with real-world tasks\n"

    # Write report
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    return {
        'total_scenarios': total_scenarios,
        'patterns': patterns,
        'gaps': gap_suggestions,
        'weak_patterns': weak_patterns
    }

if __name__ == "__main__":
    print("Generating evaluation report...")
    results = generate_evaluation_report()
    print(f"\nReport generated: EVALUATION_REPORT.md")
    print(f"Total scenarios analyzed: {results['total_scenarios']}")
    print(f"Patterns identified: {len(results['patterns'])}")
    print(f"Gaps found: {len(results['gaps'])}")
    print(f"Weak patterns: {len(results['weak_patterns'])}")
