# Agricultural Operations Reliability & Intelligence Platform

## Master Product & Engineering Plan v2

**Plan ID:** EVR-AGRI-RELIABILITY-002  
**North Star:** *Make complex agricultural operations continue correctly when reality deviates from the plan.*

## Product thesis

Everstate must not become another Farm Management System, another AI Agronomist, or a Digital Twin built for its own sake. The product is the operational reliability and intelligence layer between the systems a commercial agricultural business already uses.

The product loop is:

**Connect → Understand → Detect Exception → Determine Impact → Collaborate → Optimize → Check Policy → Approve → Execute → Verify → Learn → Quantify Value**

The system does not merely answer “what is the state of Field 27?” It must answer: “what changed, which operations/contracts/resources are affected, what are the feasible response plans, what is their cost/risk/compliance status, which plan is approved, what was executed, did it work, and what value was created or protected?”

## Core architecture

The product is organized around an **Exception Control Plane** over a persistent **Agricultural World State**.

```text
Users: Web / Mobile / Voice / WhatsApp
                    |
                    v
             Command Center
                    |
                    v
        Exception Control Plane
                    |
                Supervisor
        ____________|____________
       |            |            |
    Agronomy    Operations     Finance
    Weather     Machinery      Procurement
    Compliance  Logistics      Inventory
       \____________|____________/
                    |
              Optimization
                    |
               Policy Engine
                    |
              Human Approval
                    |
                 Execution
                    |
    Deere / ERP / Tasks / Messaging / Controllers
                    |
                Verification
                    |
                ROI / Learning

All layers operate over Agricultural World State.
```

## Non-negotiable product principles

1. Keep customer systems. Connect them; do not demand replacement.
2. Canonical operational truth belongs to Everstate, not to chat history, vector memory, or a single external vendor.
3. External systems are capability providers, never business-critical single points of failure.
4. LLMs reason over verified facts; they are never the compliance engine, numeric optimizer, or system of record.
5. High-risk actions are deterministic-policy gated and human-authorized according to risk class.
6. No agent may claim execution success before observed verification.
7. Every actionable fact has provenance, timestamps, quality, confidence, and freshness state.
8. Every write is idempotent. Every reversible action declares compensation. Irreversible actions are treated more conservatively under uncertainty.
9. Multi-tenant isolation, scoped agent identities, auditability, and credential separation are platform requirements from day one.
10. The primary KPI is **Exception Resolution Success Rate**, not “LLM accuracy.”

## 1. Agricultural Canonical Model

Create one internal operational language across vendors. Core entities:

- Organization
- Farm
- Field
- CropCycle
- Machine
- Sensor
- Worker
- Task
- Input
- Inventory
- Supplier
- Contract
- Shipment
- Regulation
- Event
- Exception
- Action
- Outcome

Use ADAPT-compatible semantics where useful for equipment, spatial and field-operation concepts, then extend for ERP, logistics, agents, exceptions, outcomes and finance. Provider objects are translated at connector boundaries and never leak as the internal domain model.

## 2. Agricultural Identity Graph

Entity resolution is a first-class subsystem, not ETL glue. It must reconcile aliases across Deere, CropX, SAP, Excel, xFarm and other sources into canonical IDs.

Signals include geometry overlap, organization, names, GPS, area, historical operations and explicit human confirmation. Every mapping carries confidence and evidence. Low-confidence mappings affecting critical actions require human confirmation.

## 3. Connector Control Plane

Every connector declares authentication, capabilities, mappings, reads, writes, webhooks, polling policy, rate limits, retries, health, version and permissions.

Capability-first provider independence is mandatory. Example capability sources:

- Field geometry: Deere / OneSoil / CropX / GeoJSON / manual
- Weather: Meteomatics / station / fallback provider
- Satellite: Sentinel Hub / future providers
- Machinery: Deere first, then CNH / CLAAS / Trimble / Ag Leader / other OEMs
- Enterprise: SAP / Dynamics Dataverse / Odoo
- IoT: MQTT / HTTP / LoRaWAN
- Execution: internal work orders / messaging / ERP requests / selected controllers

Initial integration gates:

- **G0:** CSV / Excel / GeoJSON, Sentinel Hub, Weather, Internal Task System
- **G1:** Generic MQTT, John Deere, Odoo
- **G2:** OneSoil, CropX, WhatsApp
- **G3:** SAP, Dynamics, irrigation/logistics
- **G4:** additional OEMs

## 4. Provenance, freshness and uncertainty

Every fact records source, provider, measured/observed time, received time, quality and confidence. AI-derived facts also record model/version, evidence and explanation.

Freshness classes:

- FRESH
- AGING
- STALE
- UNKNOWN

Freshness policy is capability-specific: machine position may expire in minutes, weather in hours, satellite in days, lab soil data in months, boundaries on change.

High-risk decisions using STALE critical data are blocked or require refresh.

Recommendations must separate:

- What we know
- What we infer
- What we do not know

Confidence is computed from source quality, freshness, agreement, calibration and missing information. LLMs do not invent confidence scores.

## 5. Agricultural World State

World State is a persistent time-indexed projection of canonical entities, facts and operational status. It supports historical state reconstruction and deterministic transitions.

It must represent agronomic, weather, water, operational, inventory, machine, labor, contract and logistics state together so downstream exception logic can reason across domains.

## 6. Event Engine

Important changes become typed events such as:

- FORECAST_CHANGED
- MACHINE_FAILED
- SENSOR_OFFLINE
- INVENTORY_SHORTAGE
- HARVEST_FORECAST_CHANGED
- WORKER_ABSENT
- SHIPMENT_DELAYED
- NDVI_ANOMALY
- REGULATION_CHANGED

Use an event-bus abstraction. Production target is Redpanda/Kafka when throughput and operational needs justify it.

## 7. Exception Engine — product center

An event becomes an Exception only when it invalidates or materially threatens the current plan.

An Exception records type, severity, time-to-impact, affected entities, affected value, dependencies, evidence, status and resolution lifecycle.

Example: a forecast shifts from 4 mm to 27 mm; three irrigation tasks, two sprays and one harvest are affected; the system creates a WeatherPlanConflict with exposure and time-to-impact.

## 8. Dependency Graph and Impact Engine

Model operational dependencies across field → crop cycle → tasks → workers/machines → storage → shipment → contract → customer.

Start with PostgreSQL relational/recursive graph patterns. Introduce a dedicated graph database only when scale/complexity proves the need.

Impact dimensions:

- Yield
- Revenue
- Cost
- Quality
- Compliance
- Contract
- Worker safety
- Water
- Machine utilization
- Time

Every candidate response should expose expected cost, residual risk and protected/exposed value.

## 9. Multi-agent control plane

Start with Supervisor plus four focused agents:

- Agronomy
- Operations
- Weather/Risk
- Compliance

Later add Machinery, Procurement, Inventory, Logistics, Finance and Livestock.

The Supervisor decomposes the problem, selects agents, defines dependencies, requests missing evidence, detects disagreements and constructs candidate plans. It does not redefine canonical truth.

Agent-to-agent communication is structured, not free-form chat. Messages are typed findings such as CONSTRAINT, ACTION_REQUIRED, RESOURCE_CONFLICT and ALTERNATIVE with entity, confidence and evidence references.

## 10. Shared Blackboard

Every exception owns a scoped Problem Workspace containing:

- Exception
- Goal
- Verified Facts
- Unknown Facts
- Constraints
- Candidate Actions
- Agent Findings
- Conflicts
- Plans
- Evidence
- Decision
- Outcome

Agents read only the scopes allowed by their agent identity.

## 11. Intelligence and Model Gateway

Use the right engine for the right work:

- Foundation LLM: language/reasoning/decomposition
- ML/time-series: numeric prediction
- OR solver: optimization
- Deterministic rules/OPA: safety and compliance

ModelGateway exposes `reason()`, `extract()`, `vision()`, `embed()`, and `classify()` with provider routing based on quality, cost, latency, privacy and task.

Do not train a foundation model initially. Build proprietary models gradually for vegetation anomaly, yield/harvest forecast, machine failure risk, inventory consumption, operation duration, supplier delay and exception severity.

The long-term proprietary model is the **Action → Outcome Model**: given state Y, what historically happened after action X?

## 12. Optimization Engine

Optimization is first-class. It receives tasks, machines, workers, weather windows, contract deadlines, inventory constraints and travel times and returns feasible alternatives such as:

- Plan A: maximum risk reduction
- Plan B: minimum cost
- Plan C: balanced

Conflict resolution is deterministic pipeline first: feasibility → policy → optimization → risk score → economic score. Do not ask an LLM to decide which conflicting agent is “right.”

## 13. Policy-before-action

Use OPA or an equivalent deterministic policy engine separated from enforcement.

Decision classes:

- ALLOW
- ALLOW_AND_LOG
- REQUIRE_APPROVAL
- REQUIRE_DUAL_APPROVAL
- DENY

Every spray, purchase, irrigation, shipment or other controlled write is evaluated before execution. Critical physical/chemical/payment actions remain human-authorized unless a later autonomy gate explicitly proves a safe closed loop.

## 14. Durable execution

Long-running workflows use Temporal-style durable semantics: wait for supplier responses, approvals, delivery, machine recovery or changing weather without keeping an in-memory agent process alive.

All writes have idempotency keys. Reversible actions declare compensation; irreversible actions declare `reversible=false` and receive stricter uncertainty/policy treatment.

## 15. Outcome Engine and ROI Ledger

Every Action has an expected outcome and later an observed outcome. Record prediction error, operational success, financial effect and agronomic effect.

This creates the proprietary **Decision → Action → Outcome Dataset**.

ROI entries distinguish:

- VERIFIED
- ESTIMATED
- ATTRIBUTED

Examples: water avoided, labor hours avoided, exposure reduction, duplicate purchase prevented.

## 16. Product UX

The primary page is **Attention**, not a dashboard wall.

It answers:

- What changed?
- What is affected?
- Why does it matter?
- How much time remains?
- What evidence supports this?
- What plans are available?
- What is cost/risk/compliance for each plan?
- What approval is required?
- What was executed and verified?

The map is exception-contextual: affected entities, dependencies and alternatives only.

Ask/chat is an additional interface for operational questions (“why did the plan change?”, “what if Field 7 is delayed?”, “give me the cheapest plan with risk < 8%”), not the product’s system of record.

Mobile Worker focuses on assigned task, location, instructions, material, machine and deadline, with Start / Problem / Complete plus photo, voice and GPS capture.

WhatsApp is a channel, never a database. Messages become structured events only after extraction and confirmation where ambiguity exists.

## 17. Data and software architecture

Initial stack:

- PostgreSQL + PostGIS: canonical operational truth
- Timescale-compatible time-series: telemetry
- S3-compatible storage: imagery/documents/files
- Redis: cache/coordination
- pgvector: document/search embeddings
- Redpanda/Kafka abstraction: events
- Temporal: durable workflows
- FastAPI/Python backend and workers
- Next.js/TypeScript frontend
- Docker, Terraform, GitHub Actions
- OpenTelemetry + Grafana

Prefer modular monolith + separate workers. Do not introduce Kubernetes or many microservices until scale requires them.

## 18. Security and Data Vault

All objects are tenant/organization scoped. Enforce RBAC, row-level isolation, OAuth connector authorization, credential vaulting, encryption and immutable audit.

Data Vault exposes exactly who/what can access each source/capability and supports revocation.

Each Agent Identity declares read scopes, tool scopes, write scopes, financial ceiling, allowed farms and jurisdictions. Agronomy cannot purchase; Procurement cannot pay.

## 19. Edge readiness

Architecture must allow a future Farm Edge Runtime holding recent state, tasks, critical rules, sensor streams, last weather, machine events and queued actions. Offline mode may continue local alerts/task execution/sensor ingestion/critical policy checks and sync later.

## 20. MVP / first proof

Do not build the entire master plan before proving the wedge.

Demo scenario:

1. Customer adds fields, crop, workers, machines and inventory.
2. Platform adds satellite and weather.
3. Forecast changes materially.
4. Exception Engine detects affected irrigation, spraying and harvest operations.
5. Supervisor + agents produce Plan A/B/C with cost/risk.
6. Manager approves a plan.
7. System updates tasks and notifies workers.
8. Execution is observed and outcome verified.
9. ROI/value is recorded.

If this works end-to-end, the core product is proven.

## 21. Development gates

| Gate | Required result | Exit condition |
|---|---|---|
| G0 — Model | Canonical model + identity + tenancy | Complete farm represented without vendor dependency |
| G1 — Observe | Weather + satellite + manual data + provenance/freshness | Coherent World State from multiple sources |
| G2 — Detect | Event + Exception + dependency/impact | Correct conflicts detected with affected graph |
| G3 — Explain | Read-only AI + evidence/uncertainty | No hallucinated operational facts |
| G4 — Resolve | Supervisor + Agronomy/Operations/Weather/Compliance | Multi-source candidate response plans |
| G5 — Optimize | Constraints + OR solver | Feasible plan beats baseline by explicit objective |
| G6 — Govern | OPA-style policy + approvals + audit | Agent cannot bypass policy |
| G7 — Execute | Tasks/messages + durable workflow + verification | Approved action completes end-to-end and outcome is observed |
| G8 — Integrate | Deere + ERP + IoT capability adapters | Same exception scenario works on real/sandbox external data |
| G9 — Learn | Outcome engine + ROI ledger | Decision→Outcome dataset produced |
| G10 — Commercial Pilot | High-value real workflow | Measurable ROI with human oversight |
| G11 — Enterprise | HA/security/SSO/connectors/operations | Production contract readiness |
| G12 — Autonomy | Selected closed loops only | Demonstrated safe autonomous execution under policy |

## 22. Benchmark program

Before commercial pilot, maintain ~100 deterministic scenarios including rain change, machine failure, worker absence, inventory shortage, stale sensors, conflicting sensors, provider outage, supplier delay, harvest forecast change, prohibited chemical, duplicate task, wrong field mapping, ERP/warehouse mismatch and internet outage.

Each scenario has expected system behavior, not merely expected text.

## 23. Release blockers

No production release if any of these can occur:

- cross-tenant data leak
- action without permission
- compliance override
- duplicate purchase/action
- action on stale critical data
- hallucinated machine state treated as fact
- incorrect high-impact entity resolution
- unrecoverable durable workflow after crash
- missing audit trail
- agent claims success before verification

## 24. Product KPIs

Primary: **Exception Resolution Success Rate**

Supporting:

- Time-to-Detection
- Time-to-Resolution
- Plan Feasibility
- Unauthorized Action Rate
- False Exception Rate
- Verified ROI
- Human Override Rate
- Recommendation-to-Outcome Calibration

## 25. Pilot strategy

Target a complex commercial grower: multiple fields, 50+ workers, several machines, irrigation, export/processor contracts, one ERP and at least one external farm system, preferably high-value crops.

Do not ask the pilot to replace systems. Start with one workflow:

1. Weather-driven Operations Exceptions
2. Machine/Operations disruption
3. Inventory + agronomy + procurement
4. Pre-action compliance

## 26. Commercial model

Do not price by number of agents. Price by operational footprint: farms/hectares, connected systems, automation level, exception volume and enterprise features. Enterprise connectors, compliance and execution may be add-ons.

## 27. Long-term moat

The defensible assets are:

- Agricultural Identity Graph
- Canonical Operational Model
- Cross-system Connector Network
- Dependency Graph
- Exception Dataset
- Decision → Action → Outcome Dataset
- Farm-specific Operational Memory
- Policy Library
- Integration Mapping Library
- Optimization Models

The maturity path is:

**Descriptive → Diagnostic → Predictive → Prescriptive → Agentic → Adaptive**

The strategic center is not “AI manages the farm.” It is:

**AI makes existing systems, people, machines and decisions work as one operational system when reality changes on the ground.**

## 28. Engineering sequence after EVR-AGRI-ENTERPRISE-001

The first official continuation milestone is deliberately backend/core-first:

**Canonical Model → Connector SDK → World State → Exception Object → Dependency Graph → Supervisor + Agents → Optimization → Policy Engine → Approval → Action → Outcome**

Website, maps, WhatsApp and additional vendor integrations are extensions over this chain, not substitutes for it.
