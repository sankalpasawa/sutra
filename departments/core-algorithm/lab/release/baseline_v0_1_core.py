"""Sutra Kernel Experiment 0.1.0 — stable, finite, declarative goal resolver.
NOT historical Sutra Core v0.2.2/v0.3.0 and NOT a real-world effect runtime.
Domain knowledge, methods, offers, grants and learning are versioned DATA packs.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import hashlib, json

TRUTH = {"TRUE", "FALSE", "UNKNOWN"}
RESOURCES = ("compute", "money", "attention")


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


@dataclass
class Context:
    tenant: str = "orgA"
    domain: str = "fulfillment"
    goals: list[str] = field(default_factory=list)
    facts: dict[str, dict] = field(default_factory=dict)
    rules: dict[str, dict] = field(default_factory=dict)
    unapproved_rules: set[str] = field(default_factory=set)
    methods: dict[str, list[dict]] = field(default_factory=dict)
    providers: dict[str, int] = field(default_factory=dict)
    grants: set[str] = field(default_factory=set)
    budget: dict[str, int] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0))
    preference: tuple[str, ...] = RESOURCES
    learn: bool = False
    growth: bool = False
    loaded: list[dict] = field(default_factory=list)
    event_log: list[dict] = field(default_factory=list)

    @classmethod
    def from_packs(cls, packs: list[dict]) -> "Context":
        c = cls()
        for pack in packs:
            c.apply(pack)
        return c

    def apply(self, pack: dict) -> None:
        if pack.get("schema") != "sutra-pack/1":
            raise ValueError("Unsupported pack schema")
        if "tenant" in pack:
            self.tenant = pack["tenant"]
        if "domain" in pack:
            self.domain = pack["domain"]
        if "goals" in pack:
            self.goals = list(pack["goals"])
        for row in pack.get("observations", []):
            if row["truth"] not in TRUTH:
                raise ValueError("Invalid truth")
            # Only current scope observations participate; other scopes may be retained but do not unify.
            key = self._key(row["predicate"], row.get("tenant", self.tenant), row.get("domain", self.domain))
            if row.get("verified", False):
                self.facts[key] = {"truth": row["truth"], "source": row.get("source", "unattributed"),
                                   "version": row.get("version", "1"), "verified": True}
        for row in pack.get("rules", []):
            if not row.get("approved", False):
                self.unapproved_rules.add(row["head"])
                continue
            if not row.get("alternatives") or any(not branch for branch in row["alternatives"]):
                raise ValueError("Each approved rule needs nonempty AND branches")
            if row["head"] in self.rules and row.get("replaces") != self.rules[row["head"]]["id"]:
                raise ValueError(f"Rule replacement requires exact previous rule ID for {row['head']}")
            self.rules[row["head"]] = row
        for row in pack.get("methods", []):
            if row.get("action") != "simulate_fact":
                raise ValueError("Only local simulated effects are allowed")
            if any(int(v) < 0 for v in row.get("cost", {}).values()):
                raise ValueError("Method costs cannot be negative")
            if any(row["id"] == m["id"] for vals in self.methods.values() for m in vals):
                raise ValueError("Method IDs must be globally unique")
            self.methods.setdefault(row["effect"], []).append(row)
        self.providers.update({k:int(v) for k,v in pack.get("providers", {}).items()})
        self.grants.update(pack.get("grants", []))
        self.grants.difference_update(pack.get("revoke_grants", []))
        if "budget" in pack:
            if any(int(v) < 0 for v in pack["budget"].values()):
                raise ValueError("Budget cannot be negative")
            self.budget.update({k:int(v) for k,v in pack["budget"].items()})
        if "preference" in pack:
            if set(pack["preference"]) != set(RESOURCES):
                raise ValueError("Preference must order all resource dimensions")
            self.preference = tuple(pack["preference"])
        self.learn = self.learn or bool(pack.get("learn", False))
        self.growth = self.growth or bool(pack.get("growth", False))
        self.loaded.append({"id":pack["id"], "sha256":digest(pack)})

    @staticmethod
    def _key(p: str, tenant: str, domain: str) -> str:
        return f"{tenant}|{domain}|{p}"

    def evidence(self, p: str) -> dict:
        return self.facts.get(self._key(p, self.tenant, self.domain), {"truth":"UNKNOWN", "verified":False})

    def record_observation(self, row: dict) -> None:
        if row.get("verified", False):
            self.facts[self._key(row["predicate"],row.get("tenant",self.tenant),row.get("domain",self.domain))] = {
                "truth":row["truth"], "source":row.get("source","event"),
                "version":row.get("version","event"), "verified":True
            }


class Kernel:
    """One operator: resolve goal against evidence, approved rules, and permitted method transitions."""
    def __init__(self, context: Context):
        self.c = context
        self.trace: list[dict] = []

    def _log(self, op: str, **fields: Any) -> None:
        self.trace.append({"seq":len(self.trace)+1,"operation":op, **fields})

    def resolve(self, goal: str, execute: bool = False) -> dict:
        self.trace = []
        self._log("GOAL", goal=goal, tenant=self.c.tenant, domain=self.c.domain)
        valid, blocks = self._expand(goal, (), 0)
        feasible = []
        for p in valid:
            blockers = self._check_admission(p)
            if blockers:
                blocks += blockers
            else:
                feasible.append(p)
        if feasible:
            frontier = [p for p in feasible if not any(self._dominates(q,p) for q in feasible)]
            chosen = min(frontier, key=lambda p: tuple(p["cost"][r] for r in self.c.preference)+(tuple(p["actions"]),))
            self._log("SELECT", plan=chosen["actions"], cost=chosen["cost"], pareto_options=len(frontier))
            status = "PLAN_READY" if chosen["actions"] else "SUPPORTED_BY_EVIDENCE"
            effect_receipts = []
            budget_before = dict(self.c.budget)
            if execute and chosen["actions"]:
                effect_receipts = self._simulate(chosen)
                status = "LOCAL_MODEL_EFFECTS_RECORDED"
            elif execute:
                status = "SUPPORTED_BY_EVIDENCE"  # no external proof of a parent business outcome
            learning = self._learn(goal, chosen, status)
            result = {"goal":goal,"status":status,"selected_branch":chosen["branch"],
                      "needs":chosen["needs"],"actions":chosen["actions"],"cost":chosen["cost"],
                      "proof":chosen["proof"],"pareto_options":len(frontier),
                      "observed_local_effects":effect_receipts,"learning":learning,"stop_reasons":[],
                      "budget_before":budget_before,"budget_after":dict(self.c.budget)}
        else:
            order = ["SEMANTICS_MISSING","SEMANTICS_UNAPPROVED","EVIDENCE_CONFLICT","QUERY_EVIDENCE",
                     "AUTHORITY_REQUIRED","PROVIDER_REQUIRED","RESOURCE_REQUIRED","METHOD_ABSENT","CYCLE_OR_LIMIT"]
            dominant = next((s for s in order if s in blocks), "METHOD_ABSENT")
            self._log("BLOCK", reason=dominant, seen=sorted(set(blocks)))
            learning = self._learn(goal, None, dominant)
            result = {"goal":goal,"status":dominant,"selected_branch":None,"needs":self._gaps(goal),
                      "actions":[],"cost":None,"proof":[],"pareto_options":0,"observed_local_effects":[],
                      "learning":learning,"stop_reasons":sorted(set(blocks)),
                      "budget_before":dict(self.c.budget),"budget_after":dict(self.c.budget)}
        result["trace"] = list(self.trace)
        result["scope"] = {"tenant":self.c.tenant,"domain":self.c.domain}
        result["kernel_claim"] = "local model/plan only, not an external outcome"
        self.c.event_log.append({"goal":goal,"status":result["status"],"trace_sha256":digest(result["trace"])})
        return result

    def _expand(self, p: str, trail: tuple, depth: int) -> tuple[list[dict],list[str]]:
        if p in trail or depth >= 18:
            self._log("CYCLE_OR_LIMIT", condition=p)
            return [], ["CYCLE_OR_LIMIT"]
        evidence = self.c.evidence(p)
        if evidence["truth"] == "TRUE" and evidence.get("verified", False):
            self._log("RETAIN", condition=p, source=evidence.get("source"))
            return [self._plan([], [], {r:0 for r in RESOURCES}, [f"{p}: observed TRUE from {evidence.get('source')}"])],[]
        path = trail+(p,)
        rule = self.c.rules.get(p)
        if rule:
            self._log("DERIVE", condition=p, rule=rule["id"], alternatives=len(rule["alternatives"]))
            all_plans, all_blocks = [], []
            for i,alternative in enumerate(rule["alternatives"]):
                partial = [self._plan([], [], {r:0 for r in RESOURCES}, [f"{rule['id']}: OR {i+1}"], branch=i+1)]
                for child in alternative:
                    candidates, blocks = self._expand(child,path,depth+1)
                    all_blocks += blocks
                    partial = [self._join(a,b) for a in partial for b in candidates]
                    if not partial:
                        break
                all_plans += partial
            # A presently FALSE goal can be repaired by a plan with actions.
            # A FALSE observation and a fully evidenced TRUE derivation conflict.
            if evidence["truth"] == "FALSE" and any(not plan["actions"] for plan in all_plans):
                self._log("EVIDENCE_CONFLICT", condition=p)
                return [], ["EVIDENCE_CONFLICT"]
            return all_plans, all_blocks
        if depth == 0:
            reason = "SEMANTICS_UNAPPROVED" if p in self.c.unapproved_rules else "SEMANTICS_MISSING"
            self._log(reason, condition=p)
            return [],[reason]
        if evidence["truth"] == "UNKNOWN":
            # Unknown truth must be investigated, not interpreted as FALSE.
            self._log("QUERY", condition=p)
            return [],["QUERY_EVIDENCE"]
        offers = self.c.methods.get(p, [])
        if not offers:
            self._log("METHOD_ABSENT", condition=p)
            return [],["METHOD_ABSENT"]
        plans, blocks = [], []
        for m in offers:
            self._log("MATCH", condition=p, method=m["id"])
            partial = [self._plan([],[p],{r:0 for r in RESOURCES},[f"{m['id']}: proposed {p}"])]
            for req in m.get("preconditions",[]):
                candidates, blockers=self._expand(req,path,depth+1)
                blocks += blockers
                partial=[self._join(a,b) for a in partial for b in candidates]
                if not partial:
                    break
            for plan in partial:
                if m["id"] not in plan["actions"]:
                    plan["actions"].append(m["id"])
                    for r in RESOURCES:
                        plan["cost"][r]+=int(m.get("cost",{}).get(r,0))
                plans.append(plan)
        return plans,blocks

    def _plan(self, actions:list,needs:list,cost:dict,proof:list,branch:int|None=None) -> dict:
        return {"actions":list(actions),"needs":list(needs),"cost":dict(cost),"proof":list(proof),"branch":branch}

    def _join(self,a:dict,b:dict)->dict:
        actions = list(dict.fromkeys(a["actions"]+b["actions"]))
        cost={r:0 for r in RESOURCES}
        for method_id in actions:
            m=self._method_by_id(method_id)
            for r in RESOURCES:
                cost[r]+=int(m.get("cost",{}).get(r,0))
        return self._plan(actions,list(dict.fromkeys(a["needs"]+b["needs"])),cost,a["proof"]+b["proof"],a["branch"] if a["branch"] is not None else b["branch"])

    def _method_by_id(self,method_id:str)->dict:
        all_m=[m for offers in self.c.methods.values() for m in offers if m["id"]==method_id]
        if len(all_m)!=1:
            raise ValueError(f"Method ID must be unique: {method_id}")
        return all_m[0]

    @staticmethod
    def _dominates(a:dict,b:dict)->bool:
        return all(a["cost"][r]<=b["cost"][r] for r in RESOURCES) and any(a["cost"][r]<b["cost"][r] for r in RESOURCES)

    def _check_admission(self,plan:dict)->list[str]:
        blocks=[]
        for r in RESOURCES:
            if plan["cost"][r]>self.c.budget[r]:blocks.append("RESOURCE_REQUIRED")
        usage={}
        for mid in plan["actions"]:
            m=self._method_by_id(mid)
            perm=m.get("permission","")
            prov=m.get("provider","")
            if perm and perm not in self.c.grants:blocks.append("AUTHORITY_REQUIRED")
            if prov:
                usage[prov]=usage.get(prov,0)+1
        for prov,n in usage.items():
            if self.c.providers.get(prov,0)<n:blocks.append("PROVIDER_REQUIRED")
        self._log("ADMIT", actions=plan["actions"], accepted=not blocks, blockers=sorted(set(blocks)))
        return blocks

    def _simulate(self,plan:dict)->list[dict]:
        receipts=[]
        # Execute ONLY a local model transition: no network, email, customer consent or external effects.
        for mid in plan["actions"]:
            m=self._method_by_id(mid)
            effect=m["effect"]
            # Recheck authorization/provider (the same gate used by planning).
            if self._check_admission(self._plan([mid],[],{r:int(m.get("cost",{}).get(r,0)) for r in RESOURCES},[])):
                raise RuntimeError("A simulated method lost eligibility")
            row={"predicate":effect,"truth":"TRUE","source":f"LOCAL_SIM:{mid}","verified":True}
            self.c.record_observation(row)
            for resource, amount in m.get("cost", {}).items():
                self.c.budget[resource] -= int(amount)
            if m.get("provider"):
                self.c.providers[m["provider"]] -= 1
            receipt={"method":mid,"effect":effect,"scope":f"{self.c.tenant}/{self.c.domain}",
                     "effect_scope":"LOCAL_MODEL_ONLY","receipt_sha256":digest(row)}
            self._log("SIMULATE_LOCAL_EFFECT",method=mid,effect=effect,receipt=receipt["receipt_sha256"])
            receipts.append(receipt)
        return receipts

    def _learn(self,goal:str,plan:dict|None,status:str)->list[dict]:
        if not self.c.learn and not self.c.growth:
            return []
        observations=[]
        if self.c.learn and plan and plan["actions"]:
            record={"status":"PROPOSED_ONLY","kind":"METHOD_COMPOSITION",
                    "signature":" -> ".join(plan["actions"]),"goal":goal,
                    "reason":"Observed local method composition; independent held-out evidence required before registration"}
            observations.append(record)
            self._log("LEARN_PROPOSED",kind=record["kind"],signature=record["signature"])
        if self.c.growth and status in ("METHOD_ABSENT","QUERY_EVIDENCE"):
            record={"status":"PROPOSED_ONLY","kind":"CAPABILITY_INVESTIGATION",
                    "goal":goal,"reason":"Candidate builder/research child goal, not constructed or authorized"}
            observations.append(record)
            self._log("GROWTH_PROPOSED",kind=record["kind"])
        return observations

    def _gaps(self,goal:str)->list[str]:
        out=[]
        def walk(p:str,seen:set[str]):
            if p in seen or len(seen)>20:return
            seen.add(p)
            if self.c.evidence(p)["truth"]=="TRUE":return
            r=self.c.rules.get(p)
            if r:
                for branch in r["alternatives"]:
                    for child in branch:walk(child,set(seen))
            else:out.append(p)
        walk(goal,set())
        return list(dict.fromkeys(out))

    def on_event(self,row:dict,execute:bool=False)->dict:
        predicate=row["predicate"]
        before=self.c.evidence(predicate)["truth"]
        self.c.record_observation(row)
        def touches(p:str,visited:set[str])->bool:
            if p==predicate:return True
            if p in visited:return False
            visited.add(p)
            rule=self.c.rules.get(p)
            if rule and any(touches(ch,set(visited)) for br in rule["alternatives"] for ch in br):return True
            return any(touches(pre,set(visited)) for m in self.c.methods.get(p,[]) for pre in m.get("preconditions",[]))
        affected=[g for g in self.c.goals if touches(g,set())]
        return {"observation":row,"previous":before,"affected":affected,
                "recomputed":[self.resolve(g,execute=execute) for g in affected]}

    def run_standing(self,execute:bool=False)->dict:
        return {"goals":list(self.c.goals),"outcomes":[self.resolve(g,execute=execute) for g in self.c.goals],
                "status":"NO_STANDING_GOAL" if not self.c.goals else "EVALUATED"}
