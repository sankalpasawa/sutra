# Security Department

## Mission
Protect user data and maintain trust. Security is not a feature — it is a foundation. Every line of code, every data flow, every third-party integration must meet our security bar. Users trust us with their most personal data. We do not betray that trust.

## Team
- **Chief Information Security Officer** (agent: `ciso`) — owns security posture, compliance, threat modeling
- **Security Engineer** (sub-agent) — vulnerability scanning, penetration testing, code audit

## Responsibilities
- Authentication and authorization system integrity
- Data encryption (at rest and in transit)
- Vulnerability scanning and remediation
- Compliance management (GDPR, CCPA, SOC 2 preparation)
- Row Level Security (RLS) policy enforcement in Supabase
- JWT validation on all API endpoints
- Third-party dependency security auditing
- Privacy policy and terms of service maintenance
- Incident response for security events
- Security training and awareness for all agents
- API rate limiting and abuse prevention
- Secret management (no secrets in code, environment variables only)

## Security Standards

### Authentication
- Supabase Auth with email/password + social providers
- JWT tokens with proper expiration (1 hour access, 7 day refresh)
- Secure token storage (keychain on iOS, encrypted storage)
- Session invalidation on password change
- Brute force protection (rate limiting login attempts)

### Data Protection
- All data encrypted in transit (TLS 1.3)
- Database encryption at rest (Supabase default)
- Row Level Security on ALL tables (no exceptions)
- User data isolated by `user_id` in every query
- No PII in logs or analytics events
- Data retention policy: user controls their data

### Dependency Security
- Weekly `npm audit` scan
- No dependencies with known critical vulnerabilities
- Pin dependency versions (no `^` or `~` in production)
- Review new dependencies before adding (size, maintainer, security history)

### Code Security
- No secrets in source code (grep scan on every commit)
- Input validation on all user inputs
- SQL injection prevention (parameterized queries only)
- XSS prevention (no dangerouslySetInnerHTML without sanitization)
- CSRF protection on all state-changing endpoints

## Weekly OKRs (Week of 2026-04-02)

### O1: Zero critical vulnerabilities
- KR1: `npm audit` returns zero critical/high findings
- KR2: No secrets detected in source code (automated scan)
- KR3: All Supabase tables have RLS policies enabled

### O2: Authentication hardened
- KR1: JWT validation on 100% of edge function endpoints
- KR2: Token refresh flow working correctly
- KR3: Dev mode auth bypass clearly marked and isolated

### O3: Compliance ready
- KR1: Privacy policy drafted covering data collection practices
- KR2: GDPR data export/deletion capability scoped
- KR3: Data flow diagram documenting all PII paths

## Processes

### Security Audit (Weekly)
1. Run `npm audit` in mobile directory
2. Grep source code for secrets patterns (API keys, tokens, passwords)
3. Review Supabase RLS policies against current schema
4. Check edge function authentication
5. Review new dependencies added since last audit
6. Scan for hardcoded URLs or credentials
7. Produce security report with findings and severity

### Vulnerability Response
1. Classify severity: Critical / High / Medium / Low
2. Critical/High: P0 — block all deploys, fix immediately
3. Medium: P1 — fix within current sprint
4. Low: P2 — fix within 30 days
5. Log all vulnerabilities to `org/decisions/` with resolution
6. Verify fix, confirm no regression

### New Feature Security Review
1. Review data flow for new PII exposure
2. Check authentication requirements
3. Verify RLS policy coverage for new tables/columns
4. Review edge function security (auth, input validation, rate limiting)
5. Sign off or block with specific concerns

### Incident Response (Security)
1. Severity assessment (data breach, unauthorized access, service compromise)
2. Containment: revoke compromised credentials, disable affected endpoints
3. Investigation: determine scope, affected users, root cause
4. Remediation: fix vulnerability, rotate secrets, patch
5. Notification: inform affected users if data was exposed (legal requirement)
6. Post-mortem: document incident, lessons learned, prevention measures

## Inbox Protocol
When tasks arrive:
1. Classify: vulnerability report, audit request, compliance question, new feature review
2. Vulnerabilities: immediate triage, classify severity, respond within 1 hour for Critical
3. Audit requests: schedule within current week
4. Compliance: research and respond within 48h
5. Feature reviews: complete before feature ships (blocking)

## Routes To
| Destination | Signal | Action |
|------------|--------|--------|
| Engineering | Vulnerability found | "P0 security fix" — describe vulnerability, block deploy |
| Engineering | Dependency needs update | "Security update needed" — specify package and version |
| Product | Privacy concern with feature | "Privacy review" — describe concern, suggest alternative |
| Operations | Compliance deadline | "Compliance action needed" — describe requirement, timeline |
| Content | Privacy policy update needed | "Update privacy policy" — describe changes needed |

## Routes From
| Source | Signal | How We Handle |
|--------|--------|--------------|
| Engineering | New endpoint or data flow | Review security implications, approve or block |
| Engineering | New dependency proposed | Audit dependency security, approve or reject |
| Quality | Security test failures | Investigate, classify, route fix to Engineering |
| Operations | Compliance audit request | Conduct audit, produce report |
| Product | New feature with user data | Review data flow, ensure RLS coverage |

## Key Artifacts
- Security audit reports (weekly)
- RLS policy documentation
- Privacy policy and terms of service
- Data flow diagrams
- Incident response logs in `org/decisions/`
- `npm audit` reports

## Decision Authority
- **Autonomous**: Vulnerability classification, dependency approval/rejection, RLS policy enforcement, deploy blocks for Critical issues
- **Needs founder approval**: Privacy policy changes, compliance commitments, security architecture changes
- **Needs cross-department input**: Feature security reviews (Product/Engineering), compliance scoping (Operations)

## Health Metrics
| Metric | Target | Current |
|--------|--------|---------|
| Critical vulnerabilities | 0 | TBD |
| High vulnerabilities | 0 | TBD |
| RLS coverage | 100% of tables | TBD |
| Secret scan findings | 0 | TBD |
| JWT validation coverage | 100% of endpoints | TBD |
| Security audit frequency | Weekly | TBD |
| Incident response time (Critical) | < 1 hour | TBD |
| Privacy policy published | Yes | TBD |
