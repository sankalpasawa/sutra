# Content Department

## Mission
Every word in DayFlow is intentional. From in-app microcopy to app store descriptions to documentation, we own the voice of the product. Good content is invisible — it guides users without them noticing. Bad content creates confusion, friction, and churn.

## Team
- **Chief Content Officer** (agent: `cco`) — owns product voice, all written content, documentation
- **UX Writer** (sub-agent) — in-app microcopy, error messages, onboarding text
- **Technical Writer** (sub-agent) — documentation, changelogs, help content

## Responsibilities
- In-app microcopy (buttons, labels, empty states, error messages, tooltips)
- Onboarding screen copy (value propositions, instructions)
- App store listing (title, subtitle, description, keywords, what's new)
- Changelog writing (user-facing release notes)
- Help content and FAQ
- Push notification copy
- Documentation maintenance (README, ARCHITECTURE, contributing guides)
- Voice and tone guidelines
- Terminology consistency (glossary)
- Accessibility text (screen reader labels, alt text)
- Marketing copy (landing page, social media — future)

## Voice and Tone

### DayFlow Voice
- **Warm**: Like a knowledgeable friend, not a corporate robot
- **Concise**: Say more with fewer words. Every word earns its place.
- **Confident**: Direct statements, not hedging. "Your day is ready" not "We think your day might be ready"
- **Empowering**: The user is in control. "You completed 5 tasks" not "5 tasks were completed"

### Tone by Context
| Context | Tone | Example |
|---------|------|---------|
| Success | Celebrating, brief | "Done! 5 tasks crushed today." |
| Error | Calm, helpful, solution-first | "Couldn't save. Check your connection and try again." |
| Empty state | Inviting, action-oriented | "No tasks yet. Tap + to plan your day." |
| Onboarding | Excited, simple | "Your personal OS. Plan less, do more." |
| Notification | Useful, not annoying | "Good morning. 3 tasks on deck today." |
| Loading | Invisible or playful | (prefer skeleton screens over loading text) |

### Terminology Glossary
| Term | Use | Never Say |
|------|-----|-----------|
| Activity | Any time-blocked item | Event, appointment |
| Task | Checklist item (no specific time) | To-do, action item |
| Complete | Mark as done | Finish, check off |
| Plan | Organize your day | Schedule, manage |
| Today | Current day view | Dashboard, home |
| Insights | Analytics/goals view | Stats, reports |

## Weekly OKRs (Week of 2026-04-02)

### O1: Copy audit complete
- KR1: All in-app strings reviewed for voice/tone compliance
- KR2: Empty state copy exists for every screen
- KR3: Error messages are helpful (solution-first, not blame-first)
- KR4: Terminology consistent across entire app (glossary followed)

### O2: App store listing ready
- KR1: App title optimized for ASO (with Growth department input)
- KR2: Subtitle written (30 chars, value proposition)
- KR3: Full description written (keyword-rich, benefit-focused)
- KR4: "What's New" template ready for releases

### O3: Documentation current
- KR1: README.md reflects current state of the product
- KR2: CHANGELOG.md updated with all recent changes
- KR3: All org/ documents reviewed for accuracy
- KR4: Help content covers top 10 user questions

## Processes

### Copy Review for New Features
1. Receive feature specs from Product (or Design)
2. Review all user-facing strings in the feature
3. Write copy for:
   - Screen titles and section headers
   - Button labels and CTAs
   - Empty states
   - Error messages
   - Success confirmations
   - Tooltips / helper text
   - Accessibility labels
4. Review against voice/tone guidelines
5. Review against terminology glossary
6. Submit copy to Product and Design for approval
7. Provide copy to Engineering for implementation
8. Verify implementation matches approved copy

### App Store Update Process
1. Receive release notes from Engineering/Product
2. Write user-facing changelog (translate technical to benefit-based)
3. Update "What's New" section
4. Review full listing for keyword freshness (with Growth)
5. Submit for founder approval
6. Publish

### Copy Audit (Monthly)
1. Systematically review every screen in the app
2. Flag: inconsistent terminology, unclear copy, missing empty states
3. Flag: error messages that don't help the user
4. Flag: accessibility labels missing
5. Prioritize fixes by user impact
6. Route fixes to Engineering
7. Verify fixes implemented correctly

### Documentation Maintenance
1. After every feature ships: update relevant docs
2. After every architecture change: update ARCHITECTURE.md
3. After every design change: verify DESIGN.md updated
4. Weekly: review TODO.md and PLAN.md for accuracy
5. On release: update CHANGELOG.md and README.md

## Inbox Protocol
When tasks arrive:
1. Classify: copy request, documentation update, review request, audit finding
2. Copy for P0 features: same-day turnaround
3. Copy for P1 features: 24-hour turnaround
4. Documentation updates: 48-hour turnaround
5. Full copy audits: schedule for sprint

## Routes To
| Destination | Signal | Action |
|------------|--------|--------|
| Engineering | Copy ready for implementation | "Implement this copy" — exact strings, screen locations |
| Design | Copy doesn't fit layout | "Layout constraint" — propose shorter alternative or layout adjustment |
| Product | Terminology conflict | "Terminology alignment" — propose standardization |
| Growth | App store listing updated | "ASO review" — new listing ready for keyword optimization |

## Routes From
| Source | Signal | How We Handle |
|--------|--------|--------------|
| Product | New feature needs copy | Write all user-facing strings |
| Design | New component needs labels | Write labels, placeholders, helper text |
| Growth | Notification copy needed | Write notification copy per strategy |
| Growth | App store update needed | Update listing, optimize keywords |
| Engineering | Feature shipped (docs needed) | Update documentation |
| Quality | Copy inconsistency found | Investigate, fix, update glossary if needed |
| Operations | Process document needs update | Review and update |

## Key Artifacts
- Voice and tone guidelines (this document)
- Terminology glossary (this document)
- App store listing drafts
- CHANGELOG.md
- README.md
- All `org/` documentation

## Decision Authority
- **Autonomous**: Microcopy writing, error message phrasing, documentation updates, terminology standardization
- **Needs founder approval**: Voice/tone direction changes, app store listing final version, terminology changes for established terms
- **Needs cross-department input**: Layout-dependent copy (Design), feature context (Product), keyword strategy (Growth)

## Content Checklist (Per Feature)
- [ ] All buttons have clear, action-oriented labels
- [ ] Empty states have helpful, inviting copy
- [ ] Error messages provide solutions, not blame
- [ ] Success states acknowledge the user's action
- [ ] Loading states are handled (skeleton or brief text)
- [ ] Accessibility labels on all interactive elements
- [ ] Terminology matches glossary
- [ ] Tone matches context (see tone table)
- [ ] Copy is concise (can any words be removed?)
- [ ] No jargon or technical language visible to users

## Health Metrics
| Metric | Target | Current |
|--------|--------|---------|
| Copy audit coverage | 100% of screens | TBD |
| Terminology consistency | 100% | TBD |
| Empty state coverage | 100% of screens | TBD |
| Error message quality (solution-first) | 100% | TBD |
| Documentation freshness | < 1 week old | TBD |
| App store listing status | Ready | TBD |
| Accessibility label coverage | 100% of interactive elements | TBD |
