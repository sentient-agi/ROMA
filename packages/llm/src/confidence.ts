/**
 * Confidence Scoring - Determines if LLM output needs clarification
 */

export interface ConfidenceScore {
  score: number; // 0.0 to 1.0
  confident: boolean; // true if score >= threshold
  reasons: string[]; // Why confidence is low
}

export interface ConfidenceOptions {
  threshold?: number; // Default 0.85
  strictMode?: boolean; // If true, apply additional checks
}

/**
 * Analyze LLM output confidence using simple heuristics
 */
export function scoreConfidence(
  output: string,
  options: ConfidenceOptions = {}
): ConfidenceScore {
  const threshold = options.threshold ?? 0.85;
  const strictMode = options.strictMode ?? false;

  const reasons: string[] = [];
  let deductions = 0;

  // Primary heuristic: Check for placeholder content
  const placeholderPatterns = [
    /\bTODO\b/gi,
    /\bFIXME\b/gi,
    /\bXXX\b/gi,
    /\.\.\./g, // Ellipsis as placeholder
    /\?\?\?/g, // Question marks
    /\bTBD\b/gi,
    /\bPLACEHOLDER\b/gi,
  ];

  placeholderPatterns.forEach((pattern) => {
    const matches = output.match(pattern);
    if (matches && matches.length > 0) {
      const patternName = pattern.source;
      reasons.push(`Found ${matches.length} placeholder(s): ${patternName}`);
      deductions += matches.length * 0.2; // Each placeholder: -0.2
    }
  });

  // Check for incomplete JSON (if output looks like JSON)
  if (output.trim().startsWith('{') || output.trim().startsWith('[')) {
    try {
      JSON.parse(output);
    } catch (error) {
      reasons.push('Output appears to be malformed JSON');
      deductions += 0.3;
    }
  }

  // Strict mode: Additional checks
  if (strictMode) {
    // Check for empty strings in common fields
    const emptyFieldPattern = /"(?:name|description|title|id)":\s*""/g;
    const emptyMatches = output.match(emptyFieldPattern);
    if (emptyMatches && emptyMatches.length > 0) {
      reasons.push(`Found ${emptyMatches.length} empty field(s)`);
      deductions += emptyMatches.length * 0.15;
    }

    // Check for suspiciously short output (<50 chars)
    if (output.trim().length < 50) {
      reasons.push('Output is suspiciously short');
      deductions += 0.2;
    }
  }

  // Calculate final score (start at 1.0, deduct based on issues)
  const score = Math.max(0, 1.0 - deductions);
  const confident = score >= threshold;

  return {
    score,
    confident,
    reasons: reasons.length > 0 ? reasons : ['No confidence issues detected'],
  };
}

/**
 * Quick check: Is output confident? (threshold 0.85)
 */
export function isConfident(output: string, threshold = 0.85): boolean {
  return scoreConfidence(output, { threshold }).confident;
}

/**
 * Strict confidence check with all heuristics enabled
 */
export function isStrictlyConfident(output: string): boolean {
  return scoreConfidence(output, { threshold: 0.9, strictMode: true }).confident;
}
