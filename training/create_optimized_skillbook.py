#!/usr/bin/env python3
"""
Create Optimized Skillbook

This script generates an optimized skillbook by:
1. Removing redundant scenarios (keeping best 2 from each pattern)
2. Adding consolidated patterns for over-represented areas
3. Simplifying high-complexity scenarios
"""

import json
import yaml
from pathlib import Path
from collections import defaultdict

def load_training_results():
    """Load all training results to identify best scenarios."""
    results_dir = Path("results")
    all_results = []

    for result_file in results_dir.glob("training_results_*.json"):
        with open(result_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            all_results.extend(data['results'])

    return all_results

def categorize_scenarios(results):
    """Categorize scenarios by pattern."""
    patterns = defaultdict(list)

    for result in results:
        if not result['success']:
            continue

        scenario = result['scenario']
        name = scenario['name']
        goal = scenario['goal'].lower()
        tokens = result['metadata'].get('tokens_used', 0)
        cost = result['metadata'].get('cost_usd', 0)

        # Create scenario entry
        entry = {
            'name': name,
            'goal': scenario['goal'],
            'requirements': scenario.get('requirements', []),
            'tokens': tokens,
            'cost': cost,
            'category': scenario.get('category', 'micro_saas')
        }

        # Categorize by patterns
        if 'notion' in goal:
            patterns['notion'].append(entry)
        if 'ai' in goal or 'ml' in goal or 'llm' in goal:
            patterns['ai_ml'].append(entry)
        if 'mobile' in goal or 'widget' in goal or 'ios' in goal:
            patterns['mobile'].append(entry)
        if 'analytics' in goal or 'dashboard' in goal or 'monitor' in goal:
            patterns['analytics'].append(entry)
        if 'automat' in goal or 'workflow' in goal:
            patterns['automation'].append(entry)
        if 'auth' in goal or 'security' in goal:
            patterns['auth'].append(entry)
        if 'api' in goal or 'webhook' in goal:
            patterns['api'].append(entry)
        if 'sync' in goal:
            patterns['sync'].append(entry)
        if 'payment' in goal or 'invoice' in goal:
            patterns['payments'].append(entry)
        if 'search' in goal:
            patterns['search'].append(entry)
        if 'cache' in goal or 'caching' in goal:
            patterns['caching'].append(entry)
        if 'rate' in goal and 'limit' in goal:
            patterns['rate_limiting'].append(entry)
        if 'tenant' in goal or 'multi-tenant' in goal:
            patterns['multi_tenant'].append(entry)

    return patterns

def select_best_scenarios(patterns, max_per_pattern=2):
    """Select best scenarios from each pattern based on optimal complexity."""
    selected = []

    for pattern_name, scenarios in patterns.items():
        if not scenarios:
            continue

        # Sort by optimal complexity (1500-3500 tokens ideal) and cost
        def score_scenario(s):
            tokens = s['tokens']
            cost = s['cost']

            # Optimal token range score
            if 1500 <= tokens <= 3500:
                token_score = 10
            elif 1000 <= tokens <= 5000:
                token_score = 5
            else:
                token_score = 1

            # Cost efficiency score
            if cost < 0.008:
                cost_score = 5
            elif cost < 0.012:
                cost_score = 3
            else:
                cost_score = 1

            return token_score + cost_score

        # Sort by score descending
        sorted_scenarios = sorted(scenarios, key=score_scenario, reverse=True)

        # Take best max_per_pattern scenarios
        selected.extend(sorted_scenarios[:max_per_pattern])

    return selected

def create_consolidated_scenarios():
    """Create comprehensive consolidated scenarios for over-represented patterns."""
    consolidated = [
        {
            'name': 'Notion Integration Framework',
            'goal': 'Build a comprehensive Notion integration framework with sync, webhooks, and automation',
            'requirements': [
                'Connect to Notion API with OAuth authentication',
                'Sync bidirectional data between Notion and external systems',
                'Handle webhooks for real-time updates',
                'Support cross-database operations and relations',
                'Implement rate limiting and error handling',
                'Provide template system for common workflows'
            ],
            'task_type': 'CODE_INTERPRET',
            'category': 'micro_saas'
        },
        {
            'name': 'Notion Automation Suite',
            'goal': 'Create a automation suite for Notion power-users with advanced workflows',
            'requirements': [
                'Formula builder with AI assistance',
                'Bulk operations across databases',
                'Custom permission management',
                'Backup and export functionality',
                'Template library with versioning',
                'Analytics dashboard for workspace insights'
            ],
            'task_type': 'CODE_INTERPRET',
            'category': 'micro_saas'
        },
        {
            'name': 'Mobile App Development Kit',
            'goal': 'Build a comprehensive mobile development kit with widgets and offline support',
            'requirements': [
                'iOS and Android native widget support',
                'Offline-first data synchronization',
                'Push notification system',
                'Biometric authentication',
                'Deep linking and app shortcuts',
                'Analytics and crash reporting'
            ],
            'task_type': 'CODE_INTERPRET',
            'category': 'mobile'
        },
        {
            'name': 'Mobile Widget Studio',
            'goal': 'Create a widget studio for rapid mobile widget development and deployment',
            'requirements': [
                'Widget template system',
                'Real-time preview and testing',
                'Dynamic data sources and API integration',
                'Customizable themes and layouts',
                'Widget analytics and usage tracking',
                'One-click deployment to app stores'
            ],
            'task_type': 'CODE_INTERPRET',
            'category': 'mobile'
        },
        {
            'name': 'Analytics & Monitoring Platform',
            'goal': 'Build a comprehensive analytics and monitoring platform for SaaS applications',
            'requirements': [
                'Real-time metrics collection and aggregation',
                'Customizable dashboards with drill-down',
                'Alerting and notification system',
                'Anomaly detection with ML',
                'Multi-tenant data isolation',
                'Export and reporting functionality'
            ],
            'task_type': 'CODE_INTERPRET',
            'category': 'analytics'
        },
        {
            'name': 'Business Intelligence Dashboard',
            'goal': 'Create a BI dashboard for business metrics visualization and insights',
            'requirements': [
                'Connect multiple data sources (SQL, APIs, files)',
                'Interactive charts and visualizations',
                'Custom metric calculations',
                'Scheduled reports and email delivery',
                'Collaborative annotations and sharing',
                'Mobile-responsive design'
            ],
            'task_type': 'CODE_INTERPRET',
            'category': 'analytics'
        }
    ]

    return consolidated

def simplify_high_complexity_scenarios():
    """Create simplified versions of high-complexity scenarios."""
    simplified = [
        {
            'name': 'SEO Health Checker',
            'goal': 'Build a SEO health checker that analyzes website performance',
            'requirements': [
                'Crawl website pages and extract metadata',
                'Check for common SEO issues (meta tags, headers, alt text)',
                'Analyze page load performance',
                'Generate actionable recommendations',
                'Export report in PDF/HTML format'
            ],
            'task_type': 'CODE_INTERPRET',
            'category': 'micro_saas'
        },
        {
            'name': 'Sponsorship Manager',
            'goal': 'Create a sponsorship tracking and management system',
            'requirements': [
                'Track sponsor agreements and contracts',
                'Manage sponsor tiers and benefits',
                'Generate invoices and track payments',
                'Dashboard for sponsor engagement metrics',
                'Automated reminder system for renewals'
            ],
            'task_type': 'CODE_INTERPRET',
            'category': 'micro_saas'
        },
        {
            'name': 'Invoice Automation',
            'goal': 'Build an invoice automation system with payment tracking',
            'requirements': [
                'Generate invoices from templates',
                'Track invoice status (sent, paid, overdue)',
                'Send automated payment reminders',
                'Integration with payment gateways',
                'Financial reporting dashboard'
            ],
            'task_type': 'CODE_INTERPRET',
            'category': 'micro_saas'
        },
        {
            'name': 'Bulk Data Exporter',
            'goal': 'Create a bulk data export tool for multiple formats',
            'requirements': [
                'Support multiple data sources (API, database, files)',
                'Export to various formats (CSV, JSON, Excel, PDF)',
                'Scheduled export jobs',
                'Data transformation and filtering',
                'Progress tracking and error handling'
            ],
            'task_type': 'CODE_INTERPRET',
            'category': 'automation'
        },
        {
            'name': 'Template Launcher',
            'goal': 'Build a template launcher for rapid project setup',
            'requirements': [
                'Template library with categories',
                'Customizable template variables',
                'One-click project initialization',
                'Version control integration',
                'Template sharing and marketplace'
            ],
            'task_type': 'CODE_INTERPRET',
            'category': 'automation'
        }
    ]

    return simplified

def generate_optimized_skillbook():
    """Generate the optimized skillbook."""
    print("Loading training results...")
    results = load_training_results()

    print(f"Analyzing {len(results)} scenarios...")
    patterns = categorize_scenarios(results)

    print("\nPattern distribution:")
    for pattern, scenarios in sorted(patterns.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {pattern}: {len(scenarios)} scenarios")

    print("\nSelecting best scenarios from each pattern...")
    selected = select_best_scenarios(patterns, max_per_pattern=2)

    print("\nAdding consolidated scenarios...")
    consolidated = create_consolidated_scenarios()

    print("\nAdding simplified high-complexity scenarios...")
    simplified = simplify_high_complexity_scenarios()

    # Combine all scenarios
    all_scenarios = []

    # Add gap-filling scenarios first (critical infrastructure)
    gap_file = Path("scenarios_gap_filling.yaml")
    if gap_file.exists():
        with open(gap_file, 'r', encoding='utf-8') as f:
            gap_data = yaml.safe_load(f)
            all_scenarios.extend(gap_data['scenarios'])

    # Add consolidated scenarios
    all_scenarios.extend(consolidated)

    # Add simplified scenarios
    all_scenarios.extend(simplified)

    # Add best selected scenarios
    for s in selected:
        all_scenarios.append({
            'name': s['name'],
            'goal': s['goal'],
            'requirements': s['requirements'],
            'task_type': 'CODE_INTERPRET',
            'category': s['category']
        })

    # Remove duplicates by name
    seen_names = set()
    unique_scenarios = []
    for s in all_scenarios:
        if s['name'] not in seen_names:
            seen_names.add(s['name'])
            unique_scenarios.append(s)

    # Create optimized skillbook
    optimized = {
        'scenarios': unique_scenarios
    }

    # Save to file
    output_file = Path("scenarios_optimized.yaml")
    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.dump(optimized, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"\n✅ Optimized skillbook created: {output_file}")
    print(f"   Total scenarios: {len(unique_scenarios)}")
    print(f"   Breakdown:")
    print(f"     - Gap-filling (infrastructure): 10")
    print(f"     - Consolidated patterns: 6")
    print(f"     - Simplified high-complexity: 5")
    print(f"     - Best selected from patterns: {len(selected)}")
    print(f"\n   Reduction: {len(results)} → {len(unique_scenarios)} scenarios")
    print(f"   Estimated savings: ~${(len(results) - len(unique_scenarios)) * 0.007:.2f} per training run")

    return unique_scenarios

if __name__ == "__main__":
    scenarios = generate_optimized_skillbook()
