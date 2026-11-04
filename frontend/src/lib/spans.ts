export interface Located {
  ruleKey: string
  section: string
  start: number
  end: number
}

export interface Segment {
  text: string
  ruleKey: string | null
}

interface LocatableRule {
  rule_key: string
  source_span: string
  policy_ref: string | null
}

const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** Whitespace- and case-insensitive search that returns offsets in the original text. */
export function findSpan(text: string, span: string): { start: number; end: number } | null {
  const words = span.trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return null
  const match = new RegExp(words.map(escapeRegExp).join('\\s+'), 'i').exec(text)
  return match ? { start: match.index, end: match.index + match[0].length } : null
}

/** Section "requirement" is tried first, then the policy the rule cites. */
export function locateRules(
  rules: LocatableRule[],
  requirementText: string,
  policyText: Record<string, string>,
): Located[] {
  const found: Located[] = []
  for (const rule of rules) {
    const inRequirement = findSpan(requirementText, rule.source_span)
    if (inRequirement) {
      found.push({ ruleKey: rule.rule_key, section: 'requirement', ...inRequirement })
      continue
    }
    const cited = rule.policy_ref ? policyText[rule.policy_ref] : undefined
    const inPolicy = cited ? findSpan(cited, rule.source_span) : null
    if (rule.policy_ref && inPolicy) {
      found.push({ ruleKey: rule.rule_key, section: rule.policy_ref, ...inPolicy })
    }
  }
  return found
}

export function buildSegments(
  text: string,
  marks: { start: number; end: number; ruleKey: string }[],
): Segment[] {
  const sorted = [...marks].sort((a, b) => a.start - b.start)
  const segments: Segment[] = []
  let position = 0
  for (const mark of sorted) {
    if (mark.start < position) continue
    if (mark.start > position) segments.push({ text: text.slice(position, mark.start), ruleKey: null })
    segments.push({ text: text.slice(mark.start, mark.end), ruleKey: mark.ruleKey })
    position = mark.end
  }
  if (position < text.length) segments.push({ text: text.slice(position), ruleKey: null })
  return segments
}
