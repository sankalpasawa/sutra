# Principles by Function

> The complete operating reference for every function of a digital product company.
> Any agent working in a specific function MUST read the relevant section before acting.
> Last updated: 2026-04-06

---

## Principle Activation by Depth

Not all 100+ principles apply to every task. The **depth system** (Layer 2) determines which principles activate:

| Depth | Which principles activate | Example task |
|-------|--------------------------|-------------|
| **1-2** (surface/considered) | **Universal only (P0-P9):** Product Management #1-7, Engineering #1-5, and the Review Lens of the task's primary department. | Bug fix, copy change, config update |
| **3** (thorough) | **+ Domain-specific:** All principles for the task's primary department activate. Read that full section. | New feature, architecture decision, design spec |
| **4-5** (rigorous/exhaustive) | **+ Cross-department:** All relevant domain principles + Section 16 (Cross-Functional) + Section 17 (Problem-Solving Meta-Principles). Check adjacent departments for conflicts. | Data model migration, security review, pricing change, compliance audit |

**How to use this:**
1. Check the depth assigned to your task (from the DEPTH block in Layer 2)
2. At Depth 1-2: scan the Review Lens of your department, apply universal principles, move fast
3. At Depth 3: read your full department section, apply all its principles and failure modes
4. At Depth 4-5: read your department + any adjacent departments the task touches + Sections 16-17

This keeps lightweight tasks fast while ensuring high-stakes work gets full principle coverage.

---

## Table of Contents

1. [Product Management](#1-product-management)
2. [Engineering / Technical](#2-engineering--technical)
3. [Design / UX](#3-design--ux)
4. [Data / Analytics](#4-data--analytics)
5. [Security / Privacy](#5-security--privacy)
6. [Growth / Marketing](#6-growth--marketing)
7. [Operations / Infrastructure](#7-operations--infrastructure)
8. [Finance](#8-finance)
9. [Legal / Compliance](#9-legal--compliance)
10. [Content / Communications](#10-content--communications)
11. [General Management / Leadership](#11-general-management--leadership)
12. [Project Management](#12-project-management)
13. [Long-Term / Strategic Thinking](#13-long-term--strategic-thinking)
14. [Customer Understanding](#14-customer-understanding)
15. [Personal Effectiveness (Founder)](#15-personal-effectiveness-founder)
16. [Cross-Functional Principles](#16-cross-functional-principles)
17. [Problem-Solving Meta-Principles](#17-problem-solving-meta-principles)

---

## 1. Product Management

**Sources:** Marty Cagan (Inspired, Empowered), Teresa Torres (Continuous Discovery Habits), Shreyas Doshi, Lenny Rachitsky

### Key Principles

1. **Value risk first:** Before writing a single line of code, prove that customers actually want this -- prototypes, concierge tests, painted doors, anything that generates real signal. (Cagan, Inspired)
2. **Outcome over output:** Measure success by the customer behavior that changed, never by the number of features shipped. (Cagan, Empowered)
3. **Continuous discovery is not optional:** Talk to at least one customer every single week and connect those conversations to the opportunity solution tree. (Torres, Continuous Discovery Habits)
4. **Say no by default:** Every yes to a feature is a no to focus; the best product managers maintain a kill ratio of at least 10:1 ideas evaluated to ideas built. (Doshi)
5. **Distinguish problem space from solution space:** Fall in love with the problem, not your solution; the solution is disposable, the problem is the asset. (Torres)
6. **Sequence ruthlessly by impact and effort:** Stack-rank everything against the single metric that matters most this quarter, and put high-impact low-effort items first. (Rachitsky)
7. **Ship to learn, not to launch:** Every release is a hypothesis; define what you will learn and what constitutes failure before you ship. (Cagan, Empowered)

### Common Failure Modes

- **Feature factory:** Shipping features without validating they solve real problems, measuring output instead of outcomes.
- **Stakeholder-driven roadmap:** Building what the loudest internal voice demands instead of what the evidence supports.
- **Validation theater:** Running surveys or usability tests designed to confirm an existing belief rather than genuinely test it.
- **Scope creep disguised as ambition:** Turning a focused bet into a bloated initiative by never saying no to "just one more thing."
- **Discovery starvation:** Spending 100% of time on delivery and 0% on discovery, guaranteeing you build the wrong thing efficiently.

### Review Lens (Check Before Any Change)

- Does this solve a validated customer problem, or is it an assumption?
- What is the smallest version of this that could generate learning?
- What will we measure to know if this worked?
- What are we NOT building so we can build this?
- Have we talked to a real user about this in the last two weeks?

### Interactions with Other Functions

- **Engineering:** Product defines the problem and constraints; engineering owns the solution and technical feasibility.
- **Design:** Product and design co-own discovery; design leads solution exploration, product leads prioritization.
- **Data:** Product defines what outcomes matter; data validates whether outcomes were achieved.
- **Growth:** Product builds the thing worth growing; growth finds the channels and loops.
- **Customer Understanding:** Product is the primary consumer of customer research; customer understanding feeds the opportunity backlog.
- **Finance:** Unit economics constrain what is viable; product must know the cost of what it ships.

---

## 2. Engineering / Technical

**Sources:** John Ousterhout (A Philosophy of Software Design), Martin Fowler (Refactoring), Robert Martin (Clean Code), Kent Beck (Extreme Programming Explained)

### Key Principles

1. **Complexity is the root enemy:** Every design decision should reduce the complexity that future developers must manage; if a change makes things harder to understand, it is not an improvement. (Ousterhout)
2. **Deep modules over shallow modules:** Create interfaces that are simple relative to the functionality they provide; a good abstraction hides more than it exposes. (Ousterhout)
3. **Refactor continuously, not in big-bang rewrites:** Improve code structure in small, safe steps as part of everyday work, not as a separate heroic project. (Fowler)
4. **Code should read like well-written prose:** Name things precisely, keep functions short and single-purpose, and eliminate any comment that merely restates what the code already says. (Martin, Clean Code)
5. **Make it work, make it right, make it fast -- in that order:** Correctness first, then clarity, then performance; never optimize what is not yet correct and clean. (Beck)
6. **Write tests that enable fearless change:** Tests exist so you can refactor with confidence; if your tests break every time you change implementation details, they are testing the wrong thing. (Beck)
7. **Minimize the blast radius of every change:** Design systems so that a bug in one component does not cascade across the entire system; isolate failure domains. (Ousterhout)

### Common Failure Modes

- **Premature abstraction:** Building frameworks and generic solutions before you have three concrete use cases, creating complexity that serves no one.
- **Tech debt denial:** Ignoring accumulating complexity until velocity drops to near zero and the only option is a painful rewrite.
- **Resume-driven development:** Choosing technologies because they are trendy rather than because they are the simplest adequate solution.
- **Gold-plating:** Perfecting code that does not matter while critical features remain unbuilt.
- **Cowboy coding:** Shipping without review, tests, or rollback plans and calling it "moving fast."
- **Cargo cult testing:** Writing tests that pass but do not actually verify behavior, giving false confidence.

### Review Lens (Check Before Any Change)

- Does this change reduce or increase the overall complexity of the system?
- Is there a simpler way to achieve the same result?
- Can this change be rolled back safely if it fails in production?
- Are the tests testing behavior, not implementation details?
- Will the next developer understand this code without asking me?
- Does this introduce a new dependency, and is that dependency justified?

### Interactions with Other Functions

- **Product:** Engineering pushes back on scope when feasibility is low and proposes simpler alternatives that achieve the same outcome.
- **Design:** Engineering communicates what is expensive or risky to build so design can find equally good but cheaper solutions.
- **Operations:** Engineering writes code that is operable -- observable, deployable, and debuggable in production.
- **Security:** Engineering treats security as a constraint, not a feature; every code review includes a security lens.
- **Data:** Engineering instruments code for analytics from day one; retrofitting analytics is always more expensive.

---

## 3. Design / UX

**Sources:** Don Norman (The Design of Everyday Things), Steve Krug (Don't Make Me Think), Dieter Rams (10 Principles of Good Design), Jony Ive

### Key Principles

1. **Good design is invisible:** The best interfaces require zero explanation; if you need a tutorial, the design has failed. (Krug)
2. **Design for the mental model, not the implementation model:** Users do not care how the system works internally; design must match what they expect, not what is technically true. (Norman)
3. **Affordances and signifiers must be unambiguous:** Every interactive element must clearly communicate what it does and what will happen when you use it. (Norman)
4. **Remove until it breaks, then add back one thing:** Good design is as little design as possible; reduce every screen to its essential elements before adding anything. (Rams)
5. **Accessibility is not a feature, it is a baseline:** Design for the full range of human ability from the start; retrofitting accessibility is always more expensive and less effective. (WCAG, Norman)
6. **Consistency reduces cognitive load:** Use the same patterns, terminology, and layouts for the same actions everywhere; every inconsistency is a decision the user must make. (Krug)
7. **Design is how it works, not how it looks:** Aesthetics serve function; if something is beautiful but confusing, it is bad design. (Ive, Norman)

### Common Failure Modes

- **Pixel-perfect paralysis:** Spending weeks refining visual details while fundamental usability problems remain unsolved.
- **Designing for designers:** Creating interfaces that impress design peers but confuse actual users.
- **Ignoring edge cases:** Designing only the happy path and leaving error states, empty states, and loading states unconsidered.
- **Accessibility as afterthought:** Treating color contrast, screen reader support, and keyboard navigation as nice-to-haves.
- **Design by committee:** Letting stakeholder opinions dilute a clear design vision into a compromised mess.
- **Skipping user testing:** Assuming the design works because it "feels right" without watching a single real user interact with it.

### Review Lens (Check Before Any Change)

- Can a new user complete the primary task without any guidance?
- Does this screen have one clear primary action, or are there competing calls to action?
- What happens in the error state, empty state, and loading state?
- Does this meet WCAG AA contrast and interaction standards?
- Is this consistent with existing patterns in the design system?
- Has this been tested with at least one real user (not a team member)?

### Interactions with Other Functions

- **Product:** Design and product co-own discovery; design generates solution options, product makes prioritization calls.
- **Engineering:** Design must understand implementation cost; the best design is one that is excellent AND buildable.
- **Content:** Copy is part of the design; design and content must work as one, not sequentially.
- **Data:** Design decisions should be informed by usage data; where do users drop off, get confused, or succeed?
- **Accessibility standards intersect with Legal/Compliance:** In many jurisdictions, accessibility is a legal requirement, not a preference.

---

## 4. Data / Analytics

**Sources:** DJ Patil (Data Jujitsu), Hilary Mason, Cassie Kozyrkov (Decision Intelligence)

### Key Principles

1. **Start with the decision, not the data:** Before collecting any data, define what decision it will inform; data without a decision context is just storage cost. (Kozyrkov)
2. **Instrument for the question you will ask tomorrow:** Build analytics infrastructure that can answer questions you have not thought of yet, not just the dashboard you need today. (Patil)
3. **Vanity metrics are worse than no metrics:** A number that always goes up (total signups, page views) tells you nothing about health; measure rates, ratios, and cohort behavior. (Kozyrkov)
4. **Correlation is not causation, and A/B tests are the only reliable way to establish causation:** Never make causal claims from observational data alone; when causal evidence matters, run an experiment. (Kozyrkov)
5. **Data-informed beats data-driven:** Use data to sharpen judgment, not replace it; the map is not the territory, and every metric is a lossy proxy. (Mason)
6. **Make data accessible and self-serve:** If people have to file a ticket to get a number, they will guess instead; invest in self-serve dashboards and clear documentation. (Patil)
7. **Track leading indicators, not just lagging outcomes:** By the time a lagging metric moves, it is too late to course-correct; identify the upstream behaviors that predict the outcome. (Kozyrkov)

### Common Failure Modes

- **Dashboard graveyard:** Building dashboards nobody looks at because they do not connect to any decision.
- **P-hacking and cherry-picking:** Running multiple analyses and reporting only the one that supports the desired conclusion.
- **Metric fixation:** Optimizing a proxy metric so hard that it detaches from the real outcome (Goodhart's Law).
- **Analysis paralysis:** Waiting for perfect data before making any decision, when directionally correct data is sufficient.
- **Survivorship bias:** Analyzing only successful users or outcomes and drawing conclusions that ignore those who churned or failed.
- **Underpowered experiments:** Running A/B tests without enough sample size to detect meaningful effects, then declaring "no difference."

### Review Lens (Check Before Any Change)

- What decision does this metric inform, and who is the decision-maker?
- Is this metric a leading indicator or a lagging one?
- Could this metric be gamed or optimized in a way that harms the real outcome?
- Is the sample size sufficient to draw a conclusion?
- Are we accounting for confounding variables and selection bias?
- Is this data accessible to the people who need it without filing a request?

### Interactions with Other Functions

- **Product:** Data validates whether product changes achieved the intended outcome.
- **Engineering:** Data pipelines depend on correct instrumentation in the application code.
- **Growth:** Growth experiments require rigorous A/B testing infrastructure and statistical discipline.
- **Finance:** Revenue metrics, unit economics, and cohort analysis bridge data and finance.
- **Design:** Behavioral analytics reveal where users struggle; design uses this to prioritize improvements.

---

## 5. Security / Privacy

**Sources:** OWASP Top 10, Bruce Schneier (Secrets and Lies, Click Here to Kill Everybody)

### Key Principles

1. **Security is a process, not a product:** No single tool or feature makes you secure; security requires continuous assessment, monitoring, and improvement. (Schneier)
2. **Design for the attacker's mindset:** Assume every input is malicious, every network is hostile, and every user session can be hijacked; build defenses accordingly. (OWASP)
3. **Least privilege everywhere:** Every user, service, and process should have the minimum permissions required to do its job and nothing more. (OWASP)
4. **Privacy by default, not by opt-in:** Collect the minimum data necessary, store it for the minimum time required, and give users control over their data from day one. (Schneier, GDPR)
5. **Defense in depth:** Never rely on a single security control; layer multiple independent defenses so that failure of one does not compromise the system. (Schneier)
6. **Threat model before you build:** Identify what you are protecting, from whom, and what the most likely attack vectors are before writing code. (OWASP)
7. **Assume breach:** Design systems so that when (not if) a component is compromised, the blast radius is contained and recovery is fast. (Schneier)

### Common Failure Modes

- **Security as afterthought:** Bolting security onto a finished product instead of designing it in from the start.
- **Storing secrets in code:** Hardcoding API keys, passwords, or tokens in source code or configuration files checked into version control.
- **Trusting client-side validation:** Relying on frontend validation for security instead of enforcing all rules on the server.
- **Over-collecting data:** Gathering user data "because we might need it" and creating a liability with no corresponding value.
- **Ignoring dependency vulnerabilities:** Shipping with known-vulnerable third-party libraries because updating them is inconvenient.
- **Compliance theater:** Checking boxes on a compliance framework without actually reducing risk.

### Review Lens (Check Before Any Change)

- Does this change introduce a new attack surface (new endpoint, new input, new data store)?
- Are all inputs validated and sanitized on the server side?
- Does this respect the principle of least privilege?
- Are secrets managed through a secrets manager, not hardcoded or in environment files checked into source?
- What data are we collecting, and do we have a legitimate reason and user consent for it?
- Has this been reviewed against the OWASP Top 10?

### Interactions with Other Functions

- **Engineering:** Security is a constraint on every engineering decision; code review must include a security lens.
- **Legal/Compliance:** Security practices must satisfy regulatory requirements (GDPR, SOC2, HIPAA as applicable).
- **Operations:** Incident response, monitoring, and access management bridge security and ops.
- **Data:** Data collection, storage, and access policies must be jointly owned by security and data teams.
- **Product:** Product decisions about what data to collect and how to authenticate users are security decisions.

---

## 6. Growth / Marketing

**Sources:** Andrew Chen (The Cold Start Problem), Sean Ellis (Hacking Growth), Brian Balfour (Reforge)

### Key Principles

1. **Retention is the foundation of all growth:** No acquisition channel can compensate for a product that does not retain users; fix retention before investing in acquisition. (Balfour)
2. **Find the atomic network first:** Before scaling, identify the smallest group of users that can independently get value from the product and saturate that network. (Chen)
3. **Growth is a system, not a set of tactics:** Model the full loop (acquisition, activation, retention, referral, revenue) and find the binding constraint before optimizing any single stage. (Ellis)
4. **Product-led growth compounds; paid acquisition does not:** Invest in growth loops embedded in the product (virality, user-generated content, network effects) because they get cheaper at scale, unlike paid channels. (Balfour)
5. **Activation is the most underrated lever:** The gap between signup and first value experience is where most users are lost; obsess over time-to-value. (Ellis)
6. **Channel-product fit is as important as product-market fit:** Not every channel works for every product; discover which channels naturally fit your product before spending. (Balfour)
7. **Growth without brand is renting attention; brand without growth is vanity:** Build brand as a long-term moat, but pair it with measurable growth loops. (Chen)

### Common Failure Modes

- **Premature scaling:** Pouring money into acquisition before achieving product-market fit, accelerating churn.
- **Vanity metric addiction:** Celebrating total signups while ignoring that 90% of users never complete onboarding.
- **Channel dependency:** Building the entire growth strategy on one channel (e.g., Facebook ads) and having no backup when costs rise or policies change.
- **Growth hacking without ethics:** Using dark patterns, misleading notifications, or spam tactics that generate short-term numbers and long-term brand damage.
- **Ignoring activation:** Acquiring users at high cost and then dropping them into a confusing onboarding with no guidance.
- **Copying competitors' tactics:** Imitating what worked for a different product at a different stage without understanding why it worked.

### Review Lens (Check Before Any Change)

- Does this initiative improve retention, or only acquisition?
- What is the cost-per-activated-user (not just cost-per-signup)?
- Is this a one-time tactic or a compounding loop?
- Does this require the product to be good, or does it mask a bad product?
- What happens to this channel if we 10x our spend -- does it scale or saturate?
- Would we be proud of this tactic if it were published in the press?

### Interactions with Other Functions

- **Product:** Growth depends on product-market fit; growth amplifies what product builds, it cannot fix what product breaks.
- **Data:** Every growth experiment requires measurement infrastructure and statistical rigor.
- **Design:** Onboarding, activation, and referral flows are design problems as much as growth problems.
- **Finance:** Customer acquisition cost and lifetime value are jointly owned by growth and finance.
- **Content:** Content marketing, email sequences, and messaging are growth levers that require content quality.
- **Engineering:** Growth experiments often require engineering support for instrumentation, A/B testing, and feature flags.

---

## 7. Operations / Infrastructure

**Sources:** Gene Kim (The Phoenix Project, The DevOps Handbook), Google SRE Book (Beyer, Jones, Petoff, Murphy)

### Key Principles

1. **Reliability is a feature:** Users do not distinguish between "the feature is broken" and "the infrastructure is down"; reliability is the foundation every other feature depends on. (Google SRE)
2. **Automate everything you do more than twice:** Manual processes are error-prone and do not scale; invest in automation early and treat infrastructure as code. (Kim)
3. **Monitor for symptoms, not just causes:** Alert on user-facing impact (latency, error rates, throughput) rather than internal system metrics that may or may not correlate with user experience. (Google SRE)
4. **Error budgets turn reliability into a negotiation:** Define an acceptable level of unreliability (the error budget) and use it to balance the speed of feature shipping against the cost of instability. (Google SRE)
5. **Blameless post-mortems are the only way to learn from failure:** Punishing individuals for system failures guarantees that people will hide problems instead of fixing them. (Kim, Google SRE)
6. **Reduce lead time from commit to production:** The shorter the path from code written to code running in production, the smaller the batch, the lower the risk, and the faster the feedback. (Kim)
7. **Design for graceful degradation:** When a dependency fails, the system should reduce functionality rather than crash entirely; partial service is almost always better than total outage. (Google SRE)

### Common Failure Modes

- **Alert fatigue:** Having so many noisy alerts that the team ignores them all, including the ones that matter.
- **Snowflake servers:** Infrastructure that is manually configured and cannot be reproduced, making recovery slow and unreliable.
- **No runbooks:** Expecting on-call engineers to debug novel problems at 3 AM without any documented procedures.
- **Blame culture:** Punishing the person who pushed the bad deploy instead of fixing the system that allowed a bad deploy to go out.
- **Monitoring gaps:** Having detailed metrics for some services and none for others, creating blind spots.
- **Deployment bottlenecks:** Requiring manual approval or manual steps for every deployment, slowing the entire engineering team.

### Review Lens (Check Before Any Change)

- Does this change have a rollback plan that can be executed in under five minutes?
- Are there alerts that will fire if this change causes user-facing impact?
- Has this been tested in a staging environment that resembles production?
- Does this change affect the error budget, and are we within budget?
- Is this infrastructure change captured in code (Terraform, Pulumi, etc.), not just applied manually?
- Do the runbooks cover this scenario?

### Interactions with Other Functions

- **Engineering:** Operations and engineering share ownership of deployability, observability, and incident response.
- **Security:** Access control, secret management, and network policies are jointly owned by ops and security.
- **Product:** Product must understand reliability trade-offs; shipping faster may cost stability.
- **Finance:** Infrastructure costs are a significant and growing expense that ops must manage efficiently.
- **Data:** Data pipelines are infrastructure; their reliability and monitoring fall under ops principles.

---

## 8. Finance

**Sources:** Jason Lemkin (SaaStr), David Skok (For Entrepreneurs blog), Alex Rampell (a16z)

### Key Principles

1. **Unit economics must work before you scale:** If you lose money on every customer, more customers will not fix it; prove positive unit economics at small scale first. (Skok)
2. **CAC payback period is the oxygen metric:** The time it takes to recover customer acquisition cost determines how much cash you need to grow; keep it under 12 months for SaaS. (Skok)
3. **Revenue is vanity, margin is sanity, cash is reality:** Top-line growth means nothing if costs grow faster; manage cash ruthlessly. (Lemkin)
4. **Price on value, not on cost:** Pricing should reflect the value the customer receives, not the cost to deliver; cost-plus pricing leaves money on the table and signals commodity. (Rampell)
5. **Runway determines the number of pivots you can afford:** Every dollar burned without learning is a wasted pivot opportunity; know your burn rate and runway at all times. (Lemkin)
6. **Net revenue retention is the best predictor of long-term growth:** A company where existing customers expand faster than they churn can grow even with zero new customers. (Skok)
7. **Forecast conservatively, plan for scenarios:** Build financial models with bear, base, and bull cases; make commitments based on the bear case. (Lemkin)

### Common Failure Modes

- **Burning cash on growth without unit economics:** Scaling a business that loses money per customer, hoping volume will magically fix the math.
- **Underpricing:** Pricing too low out of fear, leaving revenue on the table and attracting low-value customers who churn.
- **Ignoring churn:** Celebrating new revenue while existing revenue quietly erodes month over month.
- **One-scenario planning:** Building a single financial model and being blindsided when assumptions change.
- **Confusing revenue with cash:** Booking annual contracts as revenue while the cash arrives monthly, creating dangerous gaps.
- **Vanity funding metrics:** Optimizing for fundraising rounds and valuation rather than sustainable business health.

### Review Lens (Check Before Any Change)

- What is the unit economics impact of this decision (CAC, LTV, payback period)?
- How does this affect cash runway under our bear-case scenario?
- Are we pricing this to capture value, or just covering cost?
- What is the gross margin impact?
- Does this create recurring revenue or one-time revenue?
- Can we fund this from operating cash flow, or does it require raising capital?

### Interactions with Other Functions

- **Product:** Finance constrains what product can build; every feature has a cost, and that cost must be justified by value.
- **Growth:** CAC and LTV are jointly owned; growth cannot acquire customers that finance cannot make profitable.
- **Operations:** Infrastructure cost optimization is a shared responsibility.
- **Legal:** Contract terms, revenue recognition, and tax implications bridge finance and legal.
- **Engineering:** Engineering velocity has a cost; finance ensures the team size is sustainable relative to revenue.

---

## 9. Legal / Compliance

**Sources:** App Store Review Guidelines, GDPR, startup legal best practices, Brad Feld (Venture Deals)

### Key Principles

1. **Regulatory awareness is a first-class product requirement:** Do not build a feature and then check if it is legal; understand the regulatory landscape before designing. (GDPR)
2. **Protect intellectual property from day one:** File trademarks, use proper licenses, and ensure every contributor has signed an IP assignment; disputes are exponentially harder to resolve later. (Feld)
3. **User agreements must be honest and readable:** Terms of service that no one reads are a liability, not a shield; write them clearly and mean what they say. (GDPR, best practices)
4. **Data rights belong to the user:** Design systems assuming the user can request all their data or delete all their data at any time; this is both ethical and increasingly legally required. (GDPR)
5. **Compliance is a floor, not a ceiling:** Meeting the minimum legal requirement is table stakes; aim higher because regulations lag behind best practice by years. (Schneier)
6. **Document decisions and their rationale:** When regulators or litigators come asking, "why did you do this?", the answer must be traceable; decisions made in Slack threads and hallway conversations are invisible. (Startup legal best practices)
7. **Platform policies are de facto law:** App Store, Play Store, and cloud provider policies can shut you down faster than any regulator; treat their guidelines as hard constraints. (App Store Review Guidelines)

### Common Failure Modes

- **Building first, asking legal questions later:** Launching a feature that violates GDPR, App Store rules, or advertising law and having to rip it out.
- **Copy-paste terms of service:** Using another company's legal documents without adaptation, creating gaps and mismatches.
- **No IP assignment:** Having contractors or co-founders who technically own code or designs because no assignment agreement was signed.
- **Ignoring international law:** Serving users in the EU, Brazil, or California without understanding their specific data protection requirements.
- **Over-relying on disclaimers:** Adding "we are not responsible" clauses that courts regularly invalidate.
- **Platform policy ignorance:** Getting an app rejected or account banned because no one read the review guidelines.

### Review Lens (Check Before Any Change)

- Does this feature collect, store, or process personal data, and do we have lawful basis?
- Does this comply with every platform's policies (App Store, Play Store, etc.)?
- Can a user exercise their right to access, correct, port, and delete their data?
- Are we operating in any new jurisdiction with this change, and what are the implications?
- Is this documented in a way that we can explain our reasoning to a regulator?
- Do our terms of service and privacy policy accurately reflect what this feature does?

### Interactions with Other Functions

- **Product:** Legal constraints shape what product can build and how features must be designed.
- **Security:** Security controls implement legal requirements for data protection.
- **Data:** Data collection, retention, and deletion policies must satisfy legal requirements.
- **Finance:** Contract terms, revenue recognition, and tax compliance bridge legal and finance.
- **Content:** Marketing claims, disclosures, and user-facing copy must be legally accurate.

---

## 10. Content / Communications

**Sources:** Ann Handley (Everybody Writes), Kinneret Yifrah (Microcopy: The Complete Guide), Stripe and Basecamp product copy as exemplars

### Key Principles

1. **Clarity beats cleverness every time:** Users are scanning, not reading; every word must earn its place, and the meaning must be unambiguous on first read. (Handley)
2. **Write for the user's context, not your internal jargon:** Use the words your users use; if your internal name for a feature means nothing to them, rename it in the interface. (Yifrah)
3. **Voice is consistent, tone adapts to context:** The brand voice stays the same everywhere, but the tone shifts -- celebratory for a success, empathetic for an error, neutral for a setting. (Handley)
4. **Error messages must explain what happened, why, and what to do next:** "Something went wrong" is not a message; "Your payment failed because the card expired -- update your card to continue" is. (Yifrah)
5. **Documentation is a product, not a chore:** Treat docs with the same care as features; test them with users, iterate on them, and measure their effectiveness. (Stripe docs team principles)
6. **Every release needs a human-readable changelog entry:** Users deserve to know what changed and why, written in plain language, not commit messages. (Basecamp practice)
7. **Conciseness is respect for the reader's time:** Cut every unnecessary word, paragraph, and section; shorter is almost always better. (Handley)

### Common Failure Modes

- **Inconsistent terminology:** Calling the same thing three different names across the app, help docs, and marketing site.
- **Developer-written error messages:** Surfacing technical error codes or stack trace fragments to end users.
- **Documentation rot:** Writing docs once and never updating them, so they become actively misleading.
- **Tone-deaf communication:** Using a cheerful tone when the user just lost data, or a formal tone in a casual product.
- **Marketing-speak in the product:** Using hype language ("revolutionary AI-powered experience!") where users need functional clarity.
- **No changelog:** Shipping updates silently and making users discover changes by accident.

### Review Lens (Check Before Any Change)

- Is every piece of user-facing text written in the user's language, not our internal jargon?
- Does the voice match our brand, and does the tone match the context?
- Are error messages actionable (what happened, why, what to do)?
- Is the documentation accurate and up-to-date for this change?
- Is there a changelog entry that a non-technical user can understand?
- Has someone outside the team read this and confirmed it makes sense?

### Interactions with Other Functions

- **Design:** Copy is inseparable from design; microcopy shapes the entire user experience.
- **Product:** Product and content must agree on terminology and feature naming.
- **Engineering:** Error messages require engineering to surface the right context to the content layer.
- **Legal:** Marketing claims, disclaimers, and terms must be reviewed for accuracy.
- **Growth:** Email sequences, onboarding copy, and landing pages bridge content and growth.

---

## 11. General Management / Leadership

**Sources:** Andy Grove (High Output Management), Peter Drucker (The Effective Executive), Jim Collins (Good to Great, Built to Last)

### Key Principles

1. **A manager's output is the output of their team:** Your job is not to do the work but to multiply the output of everyone around you; every hour should be spent on the highest-leverage activity. (Grove)
2. **Focus on the vital few, not the trivial many:** Effective executives do not try to do everything; they identify the one or two things that will matter most and give those disproportionate attention. (Drucker)
3. **Decisions should be made at the lowest competent level:** Push decisions down to the people closest to the information; escalation should be the exception, not the norm. (Grove)
4. **First who, then what:** Get the right people in the right seats before deciding strategy; great people will figure out the right direction, mediocre people will fail no matter how good the strategy. (Collins)
5. **Culture is what you tolerate:** Culture is not what you put on the wall; it is the worst behavior you are willing to accept without consequence. (Collins)
6. **Confront the brutal facts, but never lose faith:** Hold two things simultaneously -- an honest assessment of current reality and an unwavering belief that you will prevail. (Collins, Stockdale Paradox)
7. **One-on-ones are the most important meeting on your calendar:** They are the primary mechanism for coaching, giving feedback, and catching problems early; cancel anything else first. (Grove)

### Common Failure Modes

- **Doing instead of leading:** Getting pulled into individual contributor work because it feels productive, while the team drifts without direction.
- **Decision hoarding:** Insisting on approving every decision, creating a bottleneck and disempowering the team.
- **Avoiding difficult conversations:** Letting performance problems fester because confrontation is uncomfortable.
- **Culture by slogans:** Posting values on the wall without enforcing them through hiring, firing, and promotion decisions.
- **Meeting bloat:** Filling the calendar with status updates that could be async, leaving no time for deep thinking.
- **Recency bias in prioritization:** Constantly reacting to the latest fire instead of staying focused on the most important initiative.

### Review Lens (Check Before Any Change)

- Am I the right person to make this decision, or should it be delegated?
- Is this the highest-leverage use of my time right now?
- Have I confronted the brutal facts, or am I avoiding an uncomfortable truth?
- Am I modeling the behavior I expect from the team?
- Does this decision align with our stated values, or contradict them?
- Will this still matter in six months?

### Interactions with Other Functions

- **All functions:** Leadership sets the operating rhythm, communication norms, and decision-making framework for the entire organization.
- **Product:** Leadership provides strategic context that shapes product priorities.
- **Finance:** Leadership is accountable for resource allocation and runway management.
- **Engineering:** Leadership sets the bar for quality, velocity, and technical investment.
- **Customer Understanding:** Leadership must stay close to customers and not delegate all customer contact.

---

## 12. Project Management

**Sources:** Shape Up (Ryan Singer / Basecamp), Agile Manifesto, Critical Path Method, Frederick Brooks (The Mythical Man-Month)

### Key Principles

1. **Fixed time, variable scope:** Set a hard deadline and shape the scope to fit it; never extend timelines, instead cut scope to what matters most. (Shape Up)
2. **Appetite, not estimate:** Instead of asking "how long will this take?", ask "how much time is this worth?"; the answer shapes the solution. (Shape Up)
3. **Work in cycles with cool-down:** Ship in focused cycles (e.g., 6-week bets) followed by cool-down periods for cleanup, exploration, and recovery. (Shape Up)
4. **Adding people to a late project makes it later:** Communication overhead grows nonlinearly with team size; solve schedule problems by cutting scope, not adding heads. (Brooks)
5. **Map dependencies and the critical path before starting:** Identify the longest chain of dependent tasks and protect it; everything else is secondary to keeping the critical path unblocked. (Critical Path Method)
6. **Working software is the primary measure of progress:** Status reports and burndown charts can lie; the only honest indicator is working software in a state that could ship. (Agile Manifesto)
7. **Scope grows in the dark:** If you are not actively and visibly managing scope, it will expand silently; make scope decisions explicit and public. (Shape Up)

### Common Failure Modes

- **Scope creep by a thousand cuts:** No single addition seems big, but collectively they double the project timeline.
- **Estimation overconfidence:** Consistently underestimating because you plan for the happy path and ignore integration, testing, and edge cases.
- **Status theater:** Reporting green on every status update while the project is silently slipping.
- **Dependency blindness:** Starting parallel workstreams that have hidden dependencies, only discovering them at integration time.
- **Meeting-driven management:** Replacing actual progress with frequent status meetings that consume the time available for work.
- **No circuit breaker:** Continuing to invest in a project that is clearly failing because of sunk cost, instead of killing it.

### Review Lens (Check Before Any Change)

- Does this fit within the current cycle's appetite, or does it push us over?
- What scope can we cut to accommodate this without extending the deadline?
- Is this on the critical path, or is it a nice-to-have that can wait?
- Are dependencies between workstreams explicitly mapped and communicated?
- What is the honest probability this ships on time, and are we lying to ourselves?
- If we had to ship tomorrow, what would we cut?

### Interactions with Other Functions

- **Product:** Product defines priorities; project management ensures they are delivered within constraints.
- **Engineering:** Project management surfaces scope and timeline trade-offs that engineering must evaluate for feasibility.
- **Design:** Design work must be shaped and scoped alongside engineering work, not treated as a separate phase.
- **Leadership:** Project management surfaces risks and trade-offs for leadership decisions; it does not make strategic calls unilaterally.
- **Operations:** Launch coordination, rollout plans, and rollback procedures bridge project management and ops.

---

## 13. Long-Term / Strategic Thinking

**Sources:** Richard Rumelt (Good Strategy Bad Strategy), Hamilton Helmer (7 Powers), Roger Martin (Playing to Win)

### Key Principles

1. **A good strategy is a coherent set of choices, not a list of goals:** "Grow 50% this year" is not a strategy; a strategy identifies the challenge, defines the approach, and specifies the coordinated actions. (Rumelt)
2. **Strategy is about where NOT to play as much as where to play:** The power of strategy is in the choices you make to focus, not the ambitions you pile up. (Martin)
3. **Sustainable advantage requires a power:** One of network effects, scale economies, switching costs, counter-positioning, cornered resource, process power, or branding must be present; without a power, profits will be competed away. (Helmer)
4. **Diagnose before prescribing:** The most common strategic failure is jumping to a plan without understanding the challenge; start by naming the obstacle clearly. (Rumelt)
5. **Strategy must specify how you win, not just where you play:** "We will serve small businesses" is a where-to-play choice; strategy also requires specifying what you do differently that makes you win there. (Martin)
6. **Think in terms of second- and third-order effects:** The obvious consequence of a decision is the first order; the interesting consequences -- and the dangerous ones -- are the second and third orders. (Rumelt)
7. **Revisit strategy at a fixed cadence, not only in crisis:** Strategy should be reviewed quarterly at minimum; waiting until things go wrong means you are always reacting, never anticipating. (Martin)

### Common Failure Modes

- **Strategy as aspiration:** Stating goals ("be the market leader") and calling it a strategy without any diagnosis or plan.
- **Trying to be everything to everyone:** Refusing to make trade-offs and ending up mediocre in every segment.
- **Competitor fixation:** Defining strategy relative to competitors instead of relative to customer needs.
- **No power source:** Building a business with no structural advantage, then being surprised when competition erodes margins.
- **Short-termism:** Sacrificing long-term positioning for quarterly results repeatedly until there is no long-term left.
- **Strategy-execution gap:** Writing a beautiful strategy document and then ignoring it in every daily decision.

### Review Lens (Check Before Any Change)

- Does this decision strengthen or weaken our chosen power source (network effects, switching costs, etc.)?
- Is this consistent with our where-to-play and how-to-win choices, or does it dilute focus?
- What are the second- and third-order consequences of this decision?
- Are we diagnosing the real challenge, or jumping to a solution?
- If a competitor does the exact same thing, do we still win? (If yes, it is not a strategic differentiator.)
- Will this matter in five years?

### Interactions with Other Functions

- **Product:** Strategy defines the arena; product fills it with specific bets.
- **Finance:** Strategy must be financially viable; capital allocation is the most concrete expression of strategic priority.
- **Growth:** Growth channels and loops must reinforce the strategic power source, not work against it.
- **Leadership:** Strategy is a leadership responsibility; it cannot be delegated to a consulting firm or a planning team.
- **Engineering:** Technical architecture should support the strategic direction; changing strategy often means changing architecture.

---

## 14. Customer Understanding

**Sources:** Steve Blank (The Four Steps to the Epiphany), Clayton Christensen (Competing Against Luck / Jobs to Be Done), Indi Young (Mental Models)

### Key Principles

1. **Get out of the building:** No amount of internal brainstorming substitutes for talking to actual customers in their actual environment; the answers live outside your office. (Blank)
2. **Customers hire products to do a job:** Understand the underlying job-to-be-done, not just the feature request; people do not want a quarter-inch drill, they want a quarter-inch hole. (Christensen)
3. **Listen for the struggle, not the solution:** Customers are experts on their problems but terrible at designing solutions; your job is to extract the pain, not follow their prescription. (Blank)
4. **Build mental models of your users:** Map the full context of the user's world -- their goals, fears, existing workflows, and decision-making process -- not just the moment they interact with your product. (Young)
5. **Segment by behavior and need, not demographics:** Two 35-year-old engineers in San Francisco can have completely different needs; segment by the job they are trying to do. (Christensen)
6. **Validate willingness to pay, not just interest:** "Would you use this?" is a worthless question; "Would you pay $X for this right now?" or "How are you solving this today and what does it cost you?" reveals real demand. (Blank)
7. **Treat customer understanding as continuous, not a phase:** Customer needs evolve, competitors change the landscape, and your own product shifts behavior; the discovery process never ends. (Blank, Christensen)

### Common Failure Modes

- **Confirmation bias in research:** Only talking to customers who love the product and ignoring those who churned.
- **Feature request aggregation:** Collecting feature requests into a voting board and building the most-voted items without understanding the underlying jobs.
- **Surveying instead of observing:** Relying on what customers say they do instead of watching what they actually do.
- **Persona fiction:** Creating detailed persona documents based on assumptions rather than real research, then treating them as truth.
- **One-time discovery:** Doing customer research at the beginning and never again, operating on stale understanding.
- **Empathy without action:** Understanding the customer deeply but never translating those insights into product decisions.

### Review Lens (Check Before Any Change)

- What customer evidence (not opinion) supports this decision?
- What is the job-to-be-done this serves, and how are customers currently solving it?
- Have we talked to customers who DON'T use our product and understood why?
- Are we segmenting by behavior and need, or by demographics and assumptions?
- When was the last time we observed (not just surveyed) a user doing this task?
- Could we run a concierge test or fake-door test before building this?

### Interactions with Other Functions

- **Product:** Customer understanding is the primary input to product decisions; product management is the primary consumer.
- **Design:** User research and usability testing are shared responsibilities between customer understanding and design.
- **Growth:** Understanding why customers churn or activate informs every growth lever.
- **Data:** Behavioral analytics validate (or contradict) what customers say in interviews.
- **Sales/Growth:** Sales conversations are a rich source of customer insight if systematically captured.
- **Content:** User language, pain points, and mental models should inform all user-facing copy.

---

## 15. Personal Effectiveness (Founder)

**Sources:** Cal Newport (Deep Work), David Allen (Getting Things Done), James Clear (Atomic Habits), Greg McKeown (Essentialism)

### Key Principles

1. **Deep work produces disproportionate value:** Protect blocks of uninterrupted, cognitively demanding work; context-switching is the single greatest destroyer of founder productivity. (Newport)
2. **Capture everything, keep nothing in your head:** Use a trusted external system for every task, idea, and commitment; your brain is for thinking, not for storing. (Allen)
3. **Habits compound; willpower does not:** Build systems and environments that make the right behavior automatic rather than relying on daily motivation. (Clear)
4. **Essentialism is not about doing less, it is about doing only what matters:** If it is not a clear yes, it is a clear no; the disciplined pursuit of less is the path to more. (McKeown)
5. **Energy management matters more than time management:** Schedule your most important work during your peak energy hours; not all hours are created equal. (Newport)
6. **Two-minute rule:** If a task takes less than two minutes, do it immediately; if it takes more, capture it in the system. (Allen)
7. **Plan the week, review the week:** Start each week by choosing the three most important outcomes, and end each week by reviewing what happened and why; without this loop, you drift. (Allen, Newport)

### Common Failure Modes

- **Reactive mode permanent:** Spending entire days responding to Slack, email, and inbound requests without ever doing proactive work.
- **Productivity theater:** Optimizing the task management system instead of doing the tasks.
- **Hero mode:** Working 16-hour days as a badge of honor while quality, judgment, and health deteriorate.
- **Context-switching addiction:** Feeling busy because of constant multitasking while producing almost nothing of value.
- **No boundaries:** Allowing every person and channel to interrupt at any time, making deep work impossible.
- **Ignoring recovery:** Treating rest as optional and burning out predictably every few months.

### Review Lens (Check Before Any Change to Your Own Schedule)

- Is this the highest-leverage use of my time, or am I doing it because it feels urgent?
- Am I doing this because only I can do it, or because I have not delegated it?
- Does this protect or erode my deep work blocks?
- Am I in a peak energy state for this type of work?
- Have I said no to enough things this week?
- When was my last real recovery day?

### Interactions with Other Functions

- **Leadership:** The founder's personal effectiveness directly determines the company's strategic output.
- **Project Management:** The founder's time is the scarcest resource; it must be managed as rigorously as any project.
- **All Functions:** The founder is the final escalation point; if the founder is overloaded, every function suffers.

---

## 16. Cross-Functional Principles

These principles govern how functions interact, resolve conflicts, and maintain coherence.

### How to Handle Trade-offs Between Functions

1. **User value is the tiebreaker:** When two functions disagree, the option that creates more value for the user wins, measured by behavior change, not opinion. (Cagan)
2. **Make trade-offs explicit and documented:** Never let a trade-off be resolved implicitly; write down what you are choosing, what you are giving up, and why. (Rumelt)
3. **Irreversible decisions deserve more deliberation; reversible decisions deserve more speed:** Classify every decision as a one-way door or a two-way door and invest analysis proportionally. (Jeff Bezos / Amazon principle)
4. **The function closest to the constraint owns the decision:** If the bottleneck is technical feasibility, engineering decides; if it is user desirability, design decides; if it is business viability, finance decides. (Adapted from IDEO's desirability-viability-feasibility framework)
5. **Every function must understand the constraints of every other function:** Engineers should know the unit economics, designers should know the technical cost, product should know the legal constraints; silos kill companies. (Grove)

### How to Prioritize When Functions Conflict

6. **Security and legal are non-negotiable constraints, not trade-off candidates:** You can trade off speed for quality, or scope for time, but you cannot trade off compliance or security. (Schneier, GDPR)
7. **Short-term speed vs long-term quality defaults to quality unless runway is at risk:** The only legitimate reason to take on known technical or design debt is survival; all other debt must be planned and paid down. (Fowler)
8. **When in doubt, ship the smaller thing faster:** A narrower solution that ships this week teaches you more than a comprehensive solution that ships next month. (Shape Up, Cagan)

### How to Maintain Coherence as Complexity Grows

9. **Single source of truth for every concept:** There should be exactly one place where priorities, designs, specs, and decisions live; duplication is the enemy of coherence. (Allen)
10. **Communication channels must match decision urgency:** Async for decisions that can wait, synchronous for decisions that are blocking; never use a meeting for what a document can resolve. (Kim)
11. **Review cadence creates coherence:** Weekly cross-functional reviews (even 15 minutes) catch drift before it becomes divergence. (Grove)
12. **Shared vocabulary eliminates 50% of cross-functional friction:** Define key terms (shipped, done, validated, MVP, etc.) once and use them consistently; most arguments are about words, not substance. (Krug, Drucker)

### How to Communicate Across Functions

13. **Lead with context, not conclusion:** When asking another function for something, explain the problem and constraints before stating your preferred solution. (Grove)
14. **Decisions need a DRI (Directly Responsible Individual):** Every decision must have exactly one person who is responsible; shared responsibility is no responsibility. (Apple practice, Grove)
15. **Write it down or it did not happen:** Verbal agreements evaporate; decisions, trade-offs, and commitments must be documented in a persistent, searchable format. (Drucker)

### How to Delegate Work (the Intent-Boundaries-Effort framework)

This is the STANDARD format for delegating any work — from founder to function, from function to function, from human to agent. Adapted from Stephen Bungay (The Art of Action) and military mission command (Auftragstaktik).

16. **Every delegation has three parts: intent, boundaries, and main effort.** Intent = what outcome and why it matters (not how). Boundaries = what must NOT happen (constraints, not permissions). Main effort = where to focus energy right now. The method is left to the executor. (Bungay)

17. **Intent without boundaries creates chaos; instructions without intent create brittleness.** Intent alone lets the executor go in random directions. Detailed instructions alone prevent adaptation when reality differs from the plan. Both together create directed autonomy. (Bungay)

18. **Boundaries must be explicit, especially for AI agents.** A human employee intuits unspoken constraints ("don't delete the production database"). An AI agent will not. Every boundary that a human would "just know" must be written. The more autonomous the executor, the more explicit the boundaries. (Derived from LLM context engineering research)

19. **The backbrief verifies alignment before execution.** After receiving intent and boundaries, the executor explains back their plan. The delegator checks: does this plan serve the intent within the boundaries? This catches misalignment before it causes damage. For agents: the "plan mode" or "think first" step IS the backbrief. (Bungay)

20. **When the situation changes, the executor adapts the method but not the intent.** If new information arrives during execution, the executor should change how they achieve the intent, not abandon the intent. If the intent itself becomes wrong, that requires re-delegation from the level above. (Bungay, McChrystal)

---

## 17. Problem-Solving Meta-Principles

Universal approaches that apply regardless of function.

### First Principles Thinking

1. **Decompose to fundamentals before building up:** Identify the base truths that cannot be reduced further, and reason up from there instead of reasoning by analogy to what already exists. (Aristotle, popularized by Elon Musk)
2. **Ask "what must be true?" rather than "what is true?":** Working backward from the desired outcome to the necessary conditions reveals gaps that working forward would miss. (Roger Martin)
3. **Challenge every assumption by asking "why?" five times:** Most "constraints" are actually assumptions inherited from a different context; verify that they still apply. (Toyota / Taiichi Ohno)

### Structured Problem-Solving (A3 / Issue Trees)

4. **Define the problem before solving it:** Write a clear problem statement that any team member would agree with; if you cannot state the problem clearly, you do not understand it yet. (A3 method, Toyota)
5. **Decompose every problem into MECE sub-problems:** Break the problem into mutually exclusive, collectively exhaustive components so that nothing is double-counted and nothing is missed. (Barbara Minto, The Pyramid Principle)
6. **Distinguish symptoms from root causes:** Treating symptoms guarantees the problem will recur; invest the time to find the root cause, even when the symptom is painful. (Ousterhout, Toyota)
7. **One page, one problem:** Constraint breeds clarity; force every problem analysis to fit on a single page (the A3 format) to eliminate padding and expose weak thinking. (Toyota)

### Pre-mortem and Post-mortem

8. **Before starting: imagine it failed and ask why:** The pre-mortem asks "assume this project failed spectacularly -- what went wrong?"; this surfaces risks that optimism obscures. (Gary Klein)
9. **After finishing: review with honesty and without blame:** The post-mortem asks "what happened, why, and what will we change?"; its value depends entirely on psychological safety. (Google SRE, Kim)
10. **Write down the counterfactual:** "What would we do differently if we started over today?" reveals improvements that incremental thinking misses. (Kahneman)

### Second-Order Thinking

11. **Always ask "and then what?":** Every action has consequences, and those consequences have consequences; trace the chain at least two steps before committing. (Howard Marks)
12. **Consider the incentives you are creating, not just the behavior you want:** People respond to incentives; if you create a metric, people will optimize for it, sometimes in destructive ways. (Charlie Munger / Goodhart's Law)
13. **Today's solution is tomorrow's problem:** Every fix introduces new constraints and new complexity; evaluate the total cost, not just the immediate benefit. (Ousterhout, Senge)

### Inversion

14. **Ask what would guarantee failure, then avoid those things:** Instead of asking "how do I succeed?", ask "how would I definitely fail?" and systematically eliminate those paths. (Charlie Munger)
15. **Invert the user's problem:** Instead of "how do we get users to sign up?", ask "what is preventing users from signing up?" -- the inverted question is usually more actionable. (Munger, adapted)

### Leverage and Bottleneck Analysis

16. **Find the constraint before optimizing anything:** In any system, one bottleneck limits throughput; improving anything that is not the bottleneck is waste. (Goldratt, The Goal)
17. **Leverage is the ratio of output to effort; always seek the highest-leverage intervention:** Before acting, ask which of the available actions would produce the most disproportionate result. (Grove, High Output Management)
18. **Avoid local optimization that hurts global performance:** A function optimizing for its own metrics at the expense of the whole system is a failure, not a success. (Goldratt, Deming)

### Decision Hygiene

19. **Separate the decision quality from the outcome quality:** Good decisions can have bad outcomes (bad luck) and bad decisions can have good outcomes (good luck); judge the process, not the result. (Annie Duke, Thinking in Bets)
20. **Write down your prediction and confidence level before seeing the result:** This calibrates your judgment over time and exposes systematic overconfidence or underconfidence. (Philip Tetlock, Superforecasting)
21. **Use the reversibility test to calibrate deliberation time:** If the decision is easily reversible, decide in minutes; if it is irreversible, decide in days; most decisions are more reversible than they seem. (Bezos)
22. **Beware the narrative fallacy:** Humans instinctively construct stories to explain events after the fact; verify causal claims with data, not narratives. (Nassim Taleb, The Black Swan)
23. **Seek disconfirming evidence actively:** The most valuable information is that which challenges your current belief; design your research to find it. (Karl Popper, Tetlock)

---

## Appendix: Quick Reference Matrix

### Function vs Primary Risk

| Function | Primary Risk | Mitigation |
|---|---|---|
| Product Management | Building the wrong thing | Continuous discovery, weekly user contact |
| Engineering | Accumulating complexity | Continuous refactoring, code review |
| Design | Confusing the user | Usability testing, simplicity bias |
| Data | Misleading conclusions | Statistical rigor, decision framing |
| Security | Breach or data loss | Threat modeling, defense in depth |
| Growth | Premature scaling | Retention-first, unit economics |
| Operations | Downtime and slow recovery | Automation, error budgets, runbooks |
| Finance | Running out of cash | Scenario planning, conservative forecasts |
| Legal | Regulatory violation | Proactive review, documentation |
| Content | Confusing communication | User language, consistent terminology |
| Leadership | Bottlenecked decisions | Delegation, one-on-ones, decision frameworks |
| Project Management | Scope creep | Fixed time/variable scope, circuit breakers |
| Strategy | No competitive advantage | Power analysis, focus, trade-off discipline |
| Customer Understanding | Stale or biased insights | Continuous research, behavioral observation |
| Personal Effectiveness | Burnout and context-switching | Deep work blocks, energy management |

### Decision Speed Guide

| Decision Type | Time to Decide | Who Decides |
|---|---|---|
| Reversible, low impact | Minutes | Any individual |
| Reversible, high impact | Hours | Function lead |
| Irreversible, low impact | Hours to one day | Function lead |
| Irreversible, high impact | Days to one week | Cross-functional + leadership |
| Existential (bet-the-company) | One to two weeks | Founder with full input |

### Cross-Functional Dependencies (Common Handoffs)

| From | To | What Gets Handed Off |
|---|---|---|
| Customer Understanding | Product | Validated problems, jobs-to-be-done |
| Product | Design | Problem statement, constraints, success metrics |
| Product | Engineering | Shaped scope, acceptance criteria |
| Design | Engineering | Specs, interaction patterns, edge cases |
| Engineering | Operations | Deployable artifacts, runbooks, alerts |
| Data | Product | Outcome measurements, experiment results |
| Security | Engineering | Threat model, security requirements |
| Legal | Product | Regulatory constraints, data requirements |
| Finance | Leadership | Runway, unit economics, scenario analysis |
| Growth | Product | Activation/retention insights, channel data |
| Content | Design | Microcopy, error messages, terminology |
| Strategy | Product | Where to play, how to win, strategic bets |

---

## How to Use This Document

1. **Before starting work in any function:** Read the relevant section's principles and review lens.
2. **Before making a cross-functional decision:** Read the Cross-Functional Principles section (16).
3. **When stuck on a hard problem:** Read the Problem-Solving Meta-Principles section (17).
4. **When reviewing someone else's work:** Use the Review Lens for that function as your checklist.
5. **When two functions disagree:** Use the trade-off resolution hierarchy in section 16.

Every principle in this document is a heuristic, not a law. The point is not blind compliance but informed judgment. When you break a principle, know which one you are breaking and why.

---

*This document is the operating reference for all agents and functions. It should be reviewed quarterly and updated when new principles are validated through experience.*
