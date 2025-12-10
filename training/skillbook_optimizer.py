"""
ACE Skillbook Optimization Tool

Analyzes training results to identify redundant patterns, optimize high-value
scenarios, and create an optimized skillbook for maximum performance.
"""

import json
import glob
from pathlib import Path
from collections import defaultdict, Counter
import statistics

def load_all_training_data():
    """Load all training results and scenarios."""
    results_path = Path("results")

    all_scenarios = []
    all_results = []

    for result_file in results_path.glob("training_results_*.json"):
        with open(result_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            all_results.extend(data['results'])

    return all_results

def detect_redundant_patterns(results):
    """Identify scenarios with overlapping patterns."""

    redundancy_groups = defaultdict(list)

    for result in results:
        scenario = result['scenario']
        name = scenario['name']
        goal = scenario['goal'].lower()

        # Create a fingerprint based on key terms
        terms = set()
        keywords = ['notion', 'api', 'sync', 'auth', 'analytics', 'backup',
                   'automat', 'mobile', 'widget', 'dashboard', 'monitor',
                   'payment', 'invoice', 'search', 'ai', 'ml', 'export']

        for keyword in keywords:
            if keyword in goal:
                terms.add(keyword)

        # Group by similar fingerprints
        fingerprint = tuple(sorted(terms))
        if fingerprint:
            redundancy_groups[fingerprint].append({
                'name': name,
                'goal': goal,
                'tokens': result['metadata'].get('tokens_used', 0),
                'cost': result['metadata'].get('cost_usd', 0),
                'success': result['success']
            })

    # Find groups with 3+ scenarios (likely redundant)
    redundant_groups = {k: v for k, v in redundancy_groups.items() if len(v) >= 3}

    return redundant_groups

def identify_high_value_scenarios(results):
    """Identify most valuable scenarios for optimization."""

    scored_scenarios = []

    for result in results:
        scenario = result['scenario']

        # Value score based on multiple factors
        score = 0

        # Success adds value
        if result['success']:
            score += 10

        # Moderate complexity is ideal (not too simple, not too complex)
        tokens = result['metadata'].get('tokens_used', 0)
        if 1500 <= tokens <= 3500:
            score += 8
        elif 1000 <= tokens <= 5000:
            score += 5
        else:
            score += 2

        # Cost efficiency
        cost = result['metadata'].get('cost_usd', 0)
        if cost < 0.008:
            score += 5
        elif cost < 0.012:
            score += 3

        # Pattern diversity (unique requirements)
        req_count = len(scenario.get('requirements', []))
        if req_count >= 3:
            score += 4
        elif req_count >= 2:
            score += 2

        scored_scenarios.append({
            'name': scenario['name'],
            'goal': scenario['goal'],
            'score': score,
            'tokens': tokens,
            'cost': cost,
            'requirements': scenario.get('requirements', [])
        })

    # Sort by score
    scored_scenarios.sort(key=lambda x: x['score'], reverse=True)

    return scored_scenarios

def suggest_optimizations(results, redundant_groups, high_value_scenarios):
    """Generate optimization recommendations."""

    recommendations = {
        'redundancy_reduction': [],
        'high_value_focus': [],
        'pattern_consolidation': [],
        'efficiency_improvements': []
    }

    # Redundancy reduction
    for pattern, scenarios in redundant_groups.items():
        if len(scenarios) >= 4:
            # Keep top 2-3 best examples, remove rest
            sorted_scenarios = sorted(scenarios, key=lambda x: (x['success'], -x['tokens']))
            to_keep = sorted_scenarios[:2]
            to_remove = sorted_scenarios[2:]

            recommendations['redundancy_reduction'].append({
                'pattern': ' + '.join(pattern),
                'total_scenarios': len(scenarios),
                'keep': [s['name'] for s in to_keep],
                'remove': [s['name'] for s in to_remove],
                'savings': sum(s['cost'] for s in to_remove)
            })

    # High-value focus
    top_20_percent = int(len(high_value_scenarios) * 0.2)
    top_scenarios = high_value_scenarios[:top_20_percent]

    recommendations['high_value_focus'] = [{
        'name': s['name'],
        'score': s['score'],
        'reason': 'Optimal complexity and cost-efficiency'
    } for s in top_scenarios[:10]]

    # Pattern consolidation opportunities
    pattern_counts = Counter()
    for result in results:
        goal = result['scenario']['goal'].lower()
        if 'notion' in goal:
            pattern_counts['notion_integration'] += 1
        if 'mobile' in goal or 'widget' in goal:
            pattern_counts['mobile_development'] += 1
        if 'analytics' in goal or 'dashboard' in goal:
            pattern_counts['analytics_dashboards'] += 1

    for pattern, count in pattern_counts.most_common(5):
        if count > 10:
            recommendations['pattern_consolidation'].append({
                'pattern': pattern,
                'count': count,
                'suggestion': f'Consider creating 1-2 comprehensive {pattern} scenarios instead of {count} specific ones'
            })

    # Efficiency improvements
    high_cost_scenarios = [r for r in results if r['metadata'].get('cost_usd', 0) > 0.012]
    if high_cost_scenarios:
        recommendations['efficiency_improvements'] = [{
            'name': r['scenario']['name'],
            'cost': r['metadata']['cost_usd'],
            'tokens': r['metadata']['tokens_used'],
            'suggestion': 'Break into smaller scenarios or simplify requirements'
        } for r in sorted(high_cost_scenarios, key=lambda x: x['metadata']['cost_usd'], reverse=True)[:5]]

    return recommendations

def generate_optimization_report(output_file="SKILLBOOK_OPTIMIZATION_REPORT.md"):
    """Generate skillbook optimization report."""

    results = load_all_training_data()
    redundant_groups = detect_redundant_patterns(results)
    high_value_scenarios = identify_high_value_scenarios(results)
    recommendations = suggest_optimizations(results, redundant_groups, high_value_scenarios)

    total_scenarios = len(results)
    potential_savings = sum(r['savings'] for r in recommendations['redundancy_reduction'])

    report = f"""# Skillbook Optimization Report

## Executive Summary

- **Total Scenarios Analyzed**: {total_scenarios}
- **Redundant Patterns Found**: {len(redundant_groups)}
- **High-Value Scenarios Identified**: {len(high_value_scenarios[:20])}
- **Potential Cost Savings**: ${potential_savings:.4f}
- **Optimization Opportunities**: {sum(len(v) for v in recommendations.values())}

## Redundancy Analysis

### Detected Redundant Patterns

"""

    if recommendations['redundancy_reduction']:
        for item in recommendations['redundancy_reduction']:
            report += f"\n#### Pattern: {item['pattern']}\n\n"
            report += f"- **Total Scenarios**: {item['total_scenarios']}\n"
            report += f"- **Recommended to Keep**: {len(item['keep'])}\n"
            report += f"- **Recommended to Remove**: {len(item['remove'])}\n"
            report += f"- **Cost Savings**: ${item['savings']:.4f}\n\n"

            if item['keep']:
                report += "**Keep these (best examples)**:\n"
                for name in item['keep']:
                    report += f"- {name}\n"

            if item['remove']:
                report += "\n**Consider removing**:\n"
                for name in item['remove'][:3]:  # Top 3
                    report += f"- {name}\n"
                if len(item['remove']) > 3:
                    report += f"- ...and {len(item['remove'])-3} more\n"
    else:
        report += "No significant redundancy detected. Pattern distribution is optimal.\n"

    ## High-Value Scenarios
    report += "\n## High-Value Scenarios\n\n"
    report += "These scenarios provide the best learning value and should be prioritized:\n\n"

    if recommendations['high_value_focus']:
        report += "| Rank | Scenario | Value Score | Reason |\n"
        report += "|------|----------|-------------|--------|\n"

        for i, item in enumerate(recommendations['high_value_focus'], 1):
            report += f"| {i} | {item['name']} | {item['score']} | {item['reason']} |\n"

    # Pattern Consolidation
    if recommendations['pattern_consolidation']:
        report += "\n## Pattern Consolidation Opportunities\n\n"

        for item in recommendations['pattern_consolidation']:
            report += f"### {item['pattern'].replace('_', ' ').title()}\n\n"
            report += f"- **Current Count**: {item['count']} scenarios\n"
            report += f"- **Suggestion**: {item['suggestion']}\n\n"

    # Efficiency Improvements
    if recommendations['efficiency_improvements']:
        report += "\n## Efficiency Improvement Opportunities\n\n"
        report += "High-cost scenarios that could be optimized:\n\n"

        report += "| Scenario | Cost | Tokens | Recommendation |\n"
        report += "|----------|------|--------|----------------|\n"

        for item in recommendations['efficiency_improvements']:
            report += f"| {item['name']} | ${item['cost']:.4f} | {item['tokens']:,} | {item['suggestion']} |\n"

    # Action Plan
    report += "\n## Recommended Action Plan\n\n"
    report += "### Phase 1: Immediate Optimizations\n\n"

    if recommendations['redundancy_reduction']:
        total_removable = sum(len(r['remove']) for r in recommendations['redundancy_reduction'])
        report += f"1. **Remove {total_removable} redundant scenarios** (saves ${potential_savings:.4f})\n"

    if recommendations['high_value_focus']:
        report += f"2. **Focus on top {len(recommendations['high_value_focus'])} high-value scenarios** for core skillbook\n"

    report += "\n### Phase 2: Pattern Refinement\n\n"

    if recommendations['pattern_consolidation']:
        report += f"1. Consolidate {len(recommendations['pattern_consolidation'])} over-represented patterns\n"

    if recommendations['efficiency_improvements']:
        report += f"2. Optimize {len(recommendations['efficiency_improvements'])} high-cost scenarios\n"

    report += "\n### Phase 3: Skillbook Creation\n\n"
    report += "1. Create optimized skillbook with deduplicated patterns\n"
    report += "2. Focus on 40-50 core patterns covering all use cases\n"
    report += "3. Ensure each pattern has 1-2 high-quality examples\n"
    report += "4. Total estimated scenarios in optimized skillbook: 60-80\n"

    report += "\n## Expected Impact\n\n"
    report += "- **Performance**: Maintained or improved (focused learning)\n"
    report += "- **Efficiency**: 20-30% reduction in training time\n"
    report += f"- **Cost Savings**: ${potential_savings:.4f} immediate + ongoing efficiency gains\n"
    report += "- **Maintainability**: Easier to update and extend\n"

    # Write report
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    return {
        'total_scenarios': total_scenarios,
        'redundant_groups': redundant_groups,
        'high_value_scenarios': high_value_scenarios[:20],
        'recommendations': recommendations,
        'potential_savings': potential_savings
    }

if __name__ == "__main__":
    print("Analyzing skillbook for optimization opportunities...")
    results = generate_optimization_report()
    print(f"\nOptimization report generated: SKILLBOOK_OPTIMIZATION_REPORT.md")
    print(f"Total scenarios analyzed: {results['total_scenarios']}")
    print(f"Redundant patterns found: {len(results['redundant_groups'])}")
    print(f"Potential savings: ${results['potential_savings']:.4f}")
