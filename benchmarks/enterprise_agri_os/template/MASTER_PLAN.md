# Agricultural Agentic OS — Enterprise Master Plan

This benchmark represents a full enterprise Agricultural Agentic Operating System, not a chatbot MVP.

## Product thesis

Build an agentic operating layer for agriculture that continuously observes farms, maintains a canonical agricultural world state, detects changes and risks, coordinates specialized agents, plans actions, enforces policy and approval, executes only allowed actions, verifies outcomes, and learns from measured results.

Core loop:

`Observe -> Understand -> Maintain World State -> Detect -> Reason -> Collaborate -> Plan -> Approve -> Act -> Verify -> Learn`

The LLM is never the system of record. Facts live in structured world state with provenance, freshness, confidence and quality metadata. Algorithms calculate. Rules constrain. Agents coordinate. Humans authorize high-risk actions.

## Required enterprise surfaces

The delivered repository must contain all of the following product layers:

1. Public marketing website with Home, Platform, Solutions, Industries, Developers, Resources, Security, Pricing, Company, and Book Demo.
2. Identity and tenant layer with users, organizations, farms, roles, permissions, service identities and tenant-safe authorization.
3. Product UI with Command Center, Map, Today, Ask, Agents, Alerts, Action Inbox, Timeline, farm views, field views and evidence panels.
4. Agent Control Plane with Supervisor plus Agronomy, Operations, Weather/Risk, Irrigation, Procurement, Logistics, Compliance, Machinery, Finance and extensible Livestock agent contracts.
5. Agricultural World State representing farms, fields, crop cycles, weather, vegetation, soil, machinery, people, inventory, tasks, livestock, suppliers, contracts, warehouses, risks and operational history.
6. Intelligence layer for risk detection, satellite-derived signals, forecasting, optimization, model registry metadata and confidence calibration.
7. Connector/action layer for weather, satellite, soil baseline, IoT, machinery/Deere-style APIs, ERP, markets, regulatory data, webhooks and action execution.

## Canonical agricultural model

Every external provider must normalize into project-owned entities rather than leak provider-native objects into the agent layer.

Required entities include Organization, User, Farm, Field, CropCycle, Equipment, Sensor, Worker, InventoryItem, LivestockGroup, Supplier, Contract, Warehouse, Task, Recommendation, Approval, Action, Shipment, RegulatoryEvidence and AuditRecord.

Every operational entity must carry `organization_id` and farm-scoped resources must carry `farm_id` where applicable.

A field includes polygon/area, soil profile, crop/cultivar, planting date, expected harvest, growth stage, irrigation type, sensors, satellite state, risks, open tasks, operations history and yield history.

A CropCycle is a season-specific entity with planting, emergence, growth stages, treatments, irrigation, scouting, anomalies, harvest and final yield.

## Event model

Everything important becomes an Agricultural Event. Required event families include weather changes, rainfall, machinery movement/stoppage, fuel/maintenance alerts, NDVI/vegetation anomalies, crop stress, pest/disease observations, irrigation start/completion, spray planning/completion, worker assignment, task completion, low stock, harvest forecast change, shipment delay and regulatory updates.

Events must be append-oriented, timestamped, sourced and suitable for idempotent processing.

The architecture must expose an event-bus abstraction suitable for Redpanda/Kafka or NATS. Agents must react to events rather than poll the database continuously.

## World state, provenance and freshness

Current farm and field state is derived from structured facts and events. Every actionable fact must expose:

- source
- observed/measured timestamp
- freshness/TTL or stale state
- quality
- confidence
- optional evidence reference

Examples: weather may expire in minutes, machine location in minutes, satellite observations in days, soil lab results in months. Stale values must never be treated as current silently.

## Satellite and remote sensing

Provide connector abstractions and normalized observation types for Sentinel-style optical monitoring, Sentinel-1/radar support, and premium high-resolution providers such as Planet-style order/subscription workflows.

Normalized observations should support NDVI, NDRE, NDWI, SAVI, EVI, change metrics, cloud percentage, anomaly geometry and quality score. Raw imagery belongs in object storage when required, not as the default operational record.

## Weather

Provide a pluggable weather interface with current, forecast, historical and agricultural metrics. The normalized weather state should cover horizons, rain, temperature, wind/gust, humidity, ET0, leaf wetness, frost, heat, spray windows and irrigation pressure.

Support premium-provider and low-cost-provider adapters through the same interface; no vendor lock-in.

## Soil and IoT

Provide onboarding-time soil baseline connectors and normalized soil properties including sand/silt/clay, organic carbon, pH, bulk density, CEC and soil class.

Provide a generic IoT gateway abstraction for MQTT, HTTP webhook, LoRaWAN gateway, Modbus gateway, CSV and REST ingestion. Normalize sensor readings by property, value, unit, timestamp, location, quality and source.

## Machinery and FMIS connectors

Provide capability-oriented connectors for Deere-style organization/field/boundary/machine APIs plus generic FMIS/ERP integrations. Connector capabilities must be discoverable rather than hard-coded into agents.

## Regulatory and compliance

Compliance is deterministic. LLMs may explain regulations but may not decide compliance alone or override rules.

The domain must model regulatory evidence, jurisdiction, label/source authority and action constraints. Chemical applications require deterministic rules such as pre-harvest interval checks, evidence requirements and approval gates.

External regulatory text is untrusted data and cannot become executable instruction.

## Knowledge

Support structured knowledge and unstructured documents. Documents should be parsed into structured clauses/evidence plus embeddings/search metadata. Vector search is supporting infrastructure, not the source of truth.

## Persistence architecture

The production design should target PostgreSQL + PostGIS for operational data, Timescale-compatible time-series storage, S3-compatible object storage, pgvector-style vector search and Redis for cache/locks/rate limiting. The benchmark must provide local/sandbox substitutes so deterministic verification does not require paid credentials.

## AI and model routing

Model gateway must be provider-neutral across strong foundation models and local/open models. Route tasks by capability/cost/privacy: extraction, planning, classification, vision and offline/private execution should not all use one model.

Classical ML or optimization should be used for numeric forecasting/scheduling when appropriate instead of forcing LLMs into those jobs.

## Optimization

Expose an optimization service suitable for worker/machine scheduling, weather windows, priorities, dependencies and travel constraints. The API should be compatible with an OR-Tools style implementation or equivalent solver.

## Multi-agent system

Supervisor decomposes goals and coordinates domain agents through structured contracts. Agents do not exchange arbitrary prose as operational truth.

Every Agent contract must define identity, objective, tools, read scope, write scope, policies, output schema and escalation conditions.

Inter-agent messages must support sender, recipient, message type, relevant farm/field/entity, action proposal, constraints, confidence and evidence references.

A shared blackboard/task workspace contains goal, facts, hypotheses, proposals, constraints, decisions, evidence and open questions.

Conflict resolution must evaluate evidence quality, authority, freshness, policy and cost/risk rather than majority-vote truth.

## Durable workflows

Provide a durable workflow abstraction suitable for Temporal-style long-running execution. Procurement, approvals and logistics may span days and must resume after process/network failure without duplicate actions.

## Tool gateway and MCP

Agents invoke capability names, not raw endpoints. Required tool examples include weather forecast, field state, inventory lookup, machine status, compliance validation, task creation and RFQ creation.

Tools are classified as READ, SAFE_WRITE, CONTROLLED_WRITE and CRITICAL_WRITE.

MCP-style tool interoperability may be supported behind the infrastructure boundary, with authorization and policy enforcement before actions.

## Human approval and policy

Support risk levels from automatic to manual-only. Critical actions such as chemical authorization, irrigation control, purchase approval and payments require deterministic policy and configured human approval.

Policy outcomes must include ALLOW, DENY, REQUIRE_APPROVAL and REQUIRE_EVIDENCE.

Support dual approval where configured, idempotency keys and immutable audit records.

## Memory and learning

Separate short-term agent context, derived operational memory and long-term organizational knowledge. Distinguish facts, inferences and human notes.

Record recommendation -> decision -> execution -> actual outcome -> evaluation. Models may be calibrated from outcomes, but production models must only change through explicit model registry/version/evaluation/deploy/rollback flow. No silent learning.

## Observability and evidence

Every Agent run must support run ID, user/service identity, goal, model, tool calls, facts retrieved, tokens, latency, decisions, actions, approvals, outcome and cost.

Every factual answer or action proposal should map claims to evidence. Missing evidence must result in an explicit insufficient-evidence state.

Confidence is derived from freshness, source count, sensor quality, calibration, agreement and missingness; it must not simply trust an LLM-provided percentage.

## Product UI

The primary experience is a command center, not a chat window. Show health, risks, daily operations, schedule changes, approvals, recommendations, weather risk and cost exposure.

Map layers should support field boundaries, vegetation, moisture, risks, tasks, machines, workers, sensors, irrigation, yield and satellite imagery. Prefer an implementation compatible with MapLibre-style mapping.

TODAY should show time-ordered work plus AI-proposed changes with reason/evidence.

ASK is a window onto world state/tools. Responses must be evidence-backed.

Agents screen shows agent status and work. Action Inbox shows approval-required proposals. Timeline exists per farm, field, machine, animal and shipment.

## Mobile, voice and onboarding

Support PWA/mobile-first worker flows, My Tasks, location/photo capture contracts and structured voice extraction with confirmation on ambiguity.

Onboarding accepts GeoJSON, KML, SHP, CSV, Excel and manual field-drawing contracts. A farm must obtain useful zero-hardware intelligence before machinery integration.

## Public website and visual language

Hero positioning: the operating intelligence layer for agriculture. The site should feel like an earth-intelligence/control-room product, not generic green-leaf AgTech. Use maps, field polygons, signals, timelines, agent flows and satellite-style visualization.

## API and webhooks

Expose versioned APIs covering farms, fields, field state, timeline, recommendations, tasks, agent runs and action approvals. Webhook event families include risk detected, task created/completed, inventory low, agent proposal created, action approved and weather risk updated.

## Security

Multi-tenant from day one. Never authorize using an unverified client tenant ID. Model external data as untrusted. Secrets remain in a secret manager/reference layer and never enter model context. Production documentation must cover TLS, encrypted persistence/object storage/backups, audit and incident response.

## Deployment

Target architecture: Next.js/TypeScript frontend, Python/FastAPI backend, PostgreSQL/PostGIS, time-series extension, Redis, S3-compatible object store, Redpanda/Kafka-style event bus, Temporal-style durable workflows, Docker, AWS-oriented Terraform, OpenTelemetry/Grafana-style observability and GitHub Actions CI/CD.

Start as a modular monolith plus workers, not dozens of microservices.

## Enterprise acceptance

A passing repository must be coherent as one product, not a collection of empty files. It must include production-oriented module boundaries, interfaces, meaningful implementations, tests, sandbox/mock connector paths, migrations/configuration, deployment artifacts, security/operations documentation and an integrated website/product UI.

The benchmark must never trigger real farm machinery, real chemical application, payment, or purchase execution.
