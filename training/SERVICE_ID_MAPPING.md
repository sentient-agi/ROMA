# Service ID Mapping Between Scenario Files

## Overview
The 158 services from the SaaS catalog are distributed across two YAML files:

## scenarios_100_services.yaml (100 scenarios)
Contains services with the following IDs:
- **1-48**: First 48 consecutive services (Notion tools, productivity apps)
- **Plus distributed services from 49-158**: Selected to reach 100 total

### Services included (by name):
1. Cross-DB Automator
2. Share Guard
3. Theme Tuner
4. Template Enforcer
5. Chart Builder
6. Notion Backup Vault
7. Encryption Guard
8. Search Accelerator
9. Pocket Notion
10. Onboarding Assistant
11. File Hub
12. Security Auditor
13-48. [Various Notion and productivity tools]
Plus 52 additional services distributed from IDs 49-158

## scenarios_remaining_58.yaml (58 scenarios)
Contains the services NOT included in the first 100:

### Service ID Ranges:
- **49-60**: Mobile/Widget Tools (12 services)
  - SmartClipper, Notion MultiActions, WidgetHabitTrails, etc.

- **113-134**: Notion Ecosystem Extensions (22 services)
  - DMSmartReply, WriteStreakMobile, NotionOfflineSync, etc.

- **135-146**: Creator & Widget Tools (12 services)
  - CreatorPulse, HabitPact, QuickNotion, ContentSparks, etc.

- **147-158**: Business Automation Tools (12 services)
  - WorkflowWatch, SponsorStack, QuoteGuard, APISchemaGuard, etc.

## Complete Service ID List (Remaining 58)

| ID Range | Count | Category | Examples |
|----------|-------|----------|----------|
| 49-60 | 12 | Mobile/Widget | SmartClipper, WidgetHabitTrails, MobileTimerBuddy |
| 113-134 | 22 | Notion Ecosystem | NotionOfflineSync, IntegraNotionHub, NotionFormFlow |
| 135-146 | 12 | Creator Tools | ContentSparks, TipWidget, FocusTogether |
| 147-158 | 12 | Business Tools | WorkflowWatch, InventorySync, BubbleComponentMarket |

## Gap Analysis
Services 61-112 (52 services) are included in scenarios_100_services.yaml
This distribution ensures:
- First 100 scenarios cover a representative mix of all service types
- Remaining 58 scenarios cover the unused services
- Total = 158 scenarios covering all catalog services

## Verification
```bash
# Count scenarios in first file
grep -c "^  - name:" scenarios_100_services.yaml
# Output: 100

# Count scenarios in second file
grep -c "^  - name:" scenarios_remaining_58.yaml
# Output: 58

# Total
# 100 + 58 = 158 ✓
```

## Usage
When training ROMA:
1. Use scenarios_100_services.yaml for initial training (100 scenarios)
2. Use scenarios_remaining_58.yaml for extended training (58 scenarios)
3. Or combine both files for complete 158-scenario training

---
Generated: 2025-12-10
Total Services: 158
Coverage: 100%
