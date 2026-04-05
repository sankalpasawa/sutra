# Operations Department — AI Agent

## Mission
Keep the agent running, deployed, and within budget. Infrastructure, deployment, API key management, and rate limiting.

## Team
- **Head of Operations** (agent: `ops_lead`) — owns deployment, infrastructure, uptime

## Responsibilities
- Deployment pipeline (git push to production)
- API key management and rotation schedule
- Rate limiting configuration (per-user, per-IP, global)
- Uptime monitoring and alerting
- Cost budget enforcement (hard stop at monthly ceiling)
- LLM provider status monitoring (external dependency)
- Backup and disaster recovery for interaction logs

## Decision Authority
- **Autonomous**: Deployment, key rotation, rate limit tuning, monitoring config
- **Needs founder approval**: Infrastructure cost changes, new provider accounts, downtime decisions
- **Needs cross-department input**: Rate limits (Product), budget thresholds (Finance)

## Health Metrics
| Metric | Target | Current |
|--------|--------|---------|
| Uptime | > 99.5% | TBD |
| Deploy frequency | Multiple per week | TBD |
| API key age | < 90 days | TBD |
