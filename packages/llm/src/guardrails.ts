/**
 * Safety Guardrails - Domain filtering for SaaS generation
 */

export interface GuardrailResult {
  allowed: boolean;
  reason?: string;
  flaggedKeywords?: string[];
  domain?: string;
}

/**
 * Blacklisted domains - will NOT generate SaaS for these
 */
const BLACKLIST_KEYWORDS = [
  // Healthcare
  'healthcare',
  'medical',
  'health',
  'hospital',
  'doctor',
  'patient',
  'diagnosis',
  'prescription',
  'pharmacy',
  'clinic',
  'telemedicine',

  // Legal
  'legal',
  'lawyer',
  'attorney',
  'law firm',
  'litigation',
  'court',
  'legal advice',
  'contract review',

  // Finance/Banking
  'finance',
  'financial',
  'banking',
  'bank',
  'loan',
  'mortgage',
  'credit card',
  'payment processing',
  'trading',
  'investment',
  'stocks',
  'forex',

  // Crypto/Blockchain
  'crypto',
  'cryptocurrency',
  'bitcoin',
  'ethereum',
  'blockchain',
  'nft',
  'defi',
  'wallet',
  'token',

  // Gambling
  'gambling',
  'casino',
  'betting',
  'lottery',
  'poker',
  'slots',
  'wagering',

  // Kids (<13)
  'kids',
  'children',
  'child',
  'minors',
  'parental',
  'youth',
  'elementary',
  'kindergarten',

  // Government-regulated
  'government',
  'regulatory',
  'compliance tracking',
  'tax filing',
  'insurance',
];

/**
 * Green-listed domains - safe to generate
 */
const GREENLIST_KEYWORDS = [
  'productivity',
  'dev-tools',
  'developer',
  'entertainment',
  'education',
  'e-commerce',
  'ecommerce',
  'social',
  'iot',
  'internet of things',
  'collaboration',
  'project management',
  'cms',
  'content management',
  'blogging',
  'portfolio',
  'marketing',
  'analytics',
  'dashboard',
  'saas',
  'api',
];

/**
 * Check if a prompt describes a blacklisted domain
 */
export function checkGuardrails(prompt: string): GuardrailResult {
  const lowerPrompt = prompt.toLowerCase();
  const flaggedKeywords: string[] = [];

  // Check blacklist first
  for (const keyword of BLACKLIST_KEYWORDS) {
    // Use word boundaries to avoid false positives
    const regex = new RegExp(`\\b${keyword}\\b`, 'i');
    if (regex.test(lowerPrompt)) {
      flaggedKeywords.push(keyword);
    }
  }

  if (flaggedKeywords.length > 0) {
    return {
      allowed: false,
      reason: `Request contains blacklisted domain keywords: ${flaggedKeywords.join(', ')}`,
      flaggedKeywords,
      domain: inferDomain(flaggedKeywords),
    };
  }

  // Check if greenlist match exists (optional - for logging)
  const greenlistMatch = GREENLIST_KEYWORDS.find((keyword) => {
    const regex = new RegExp(`\\b${keyword}\\b`, 'i');
    return regex.test(lowerPrompt);
  });

  return {
    allowed: true,
    domain: greenlistMatch || 'general',
  };
}

/**
 * Infer the blacklisted domain category
 */
function inferDomain(keywords: string[]): string {
  const domainMap: Record<string, string[]> = {
    healthcare: ['healthcare', 'medical', 'health', 'hospital', 'doctor', 'patient'],
    legal: ['legal', 'lawyer', 'attorney', 'law firm', 'litigation'],
    finance: ['finance', 'banking', 'loan', 'mortgage', 'trading', 'investment'],
    crypto: ['crypto', 'bitcoin', 'ethereum', 'blockchain', 'nft', 'defi'],
    gambling: ['gambling', 'casino', 'betting', 'lottery', 'poker'],
    'kids-content': ['kids', 'children', 'child', 'minors'],
    'government-regulated': ['government', 'regulatory', 'compliance', 'tax', 'insurance'],
  };

  for (const [domain, domainKeywords] of Object.entries(domainMap)) {
    if (keywords.some((kw) => domainKeywords.includes(kw))) {
      return domain;
    }
  }

  return 'unknown-blacklisted';
}

/**
 * Format a user-friendly error message for blacklisted domains
 */
export function formatGuardrailError(result: GuardrailResult): string {
  if (result.allowed) {
    return '';
  }

  const domainNames: Record<string, string> = {
    healthcare: 'Healthcare/Medical',
    legal: 'Legal Services',
    finance: 'Financial Services',
    crypto: 'Cryptocurrency/Blockchain',
    gambling: 'Gambling/Betting',
    'kids-content': 'Children (<13)',
    'government-regulated': 'Government-Regulated Services',
  };

  const domainDisplay = domainNames[result.domain || ''] || 'Restricted Domain';

  return `❌ Cannot generate SaaS for ${domainDisplay}.

Reason: ROMA does not support code generation for regulated domains including:
- Healthcare/Medical services
- Legal services
- Financial services & banking
- Cryptocurrency/Blockchain
- Gambling/Betting platforms
- Children's content (<13)
- Government-regulated services

Supported domains include:
✅ Productivity tools
✅ Developer tools
✅ Entertainment
✅ Education (non-children)
✅ E-commerce
✅ Social platforms
✅ IoT/Smart home
✅ Content management
✅ Marketing/Analytics

Flagged keywords: ${result.flaggedKeywords?.join(', ')}`;
}
