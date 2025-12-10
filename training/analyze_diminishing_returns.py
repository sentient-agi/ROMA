import json
import statistics

with open('results/training_results_20251210_022549.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

    # Analyze cost/token trends across the 100 scenarios
    costs = [r['metadata']['cost_usd'] for r in data['results']]
    tokens = [r['metadata']['tokens_used'] for r in data['results']]

    # Break into quartiles to see if complexity is changing
    q1_costs = costs[0:25]
    q2_costs = costs[25:50]
    q3_costs = costs[50:75]
    q4_costs = costs[75:100]

    q1_tokens = tokens[0:25]
    q2_tokens = tokens[25:50]
    q3_tokens = tokens[50:75]
    q4_tokens = tokens[75:100]

    print('SCENARIO COMPLEXITY ANALYSIS')
    print('=' * 60)
    print('Quartile | Avg Cost | Avg Tokens | Complexity Trend')
    print('-' * 60)
    print(f'Q1 (1-25)   | ${statistics.mean(q1_costs):.4f} | {int(statistics.mean(q1_tokens)):,} | Baseline')

    q2_change = (statistics.mean(q2_costs)/statistics.mean(q1_costs)-1)*100
    print(f'Q2 (26-50)  | ${statistics.mean(q2_costs):.4f} | {int(statistics.mean(q2_tokens)):,} | {"UP" if q2_change > 0 else "DOWN"} {abs(q2_change):.1f}%')

    q3_change = (statistics.mean(q3_costs)/statistics.mean(q2_costs)-1)*100
    print(f'Q3 (51-75)  | ${statistics.mean(q3_costs):.4f} | {int(statistics.mean(q3_tokens)):,} | {"UP" if q3_change > 0 else "DOWN"} {abs(q3_change):.1f}%')

    q4_change = (statistics.mean(q4_costs)/statistics.mean(q3_costs)-1)*100
    print(f'Q4 (76-100) | ${statistics.mean(q4_costs):.4f} | {int(statistics.mean(q4_tokens)):,} | {"UP" if q4_change > 0 else "DOWN"} {abs(q4_change):.1f}%')

    print()
    print('VARIANCE ANALYSIS')
    print('=' * 60)
    print(f'Cost Std Dev:   ${statistics.stdev(costs):.4f}')
    print(f'Token Std Dev:  {int(statistics.stdev(tokens)):,}')
    print(f'Min Cost:       ${min(costs):.4f}')
    print(f'Max Cost:       ${max(costs):.4f}')
    print(f'Cost Range:     {(max(costs)/min(costs)):.2f}x variation')
    print()

    # Analyze unique patterns
    print('PATTERN DIVERSITY INDICATORS')
    print('=' * 60)

    # Look at scenario names to identify patterns
    names = [r['scenario']['name'] for r in data['results']]

    # Count unique word stems to estimate pattern diversity
    words = set()
    for name in names:
        words.update(name.lower().split())

    print(f'Unique scenario names:  {len(set(names))}')
    print(f'Unique word stems:      {len(words)}')
    print(f'Avg words per name:     {sum(len(n.split()) for n in names) / len(names):.1f}')
