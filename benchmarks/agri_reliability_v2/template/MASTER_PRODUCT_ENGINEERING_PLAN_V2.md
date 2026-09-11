# Protected Benchmark Contract — Agricultural Operations Reliability & Intelligence Platform v2

**Plan:** EVR-AGRI-RELIABILITY-002  
**North Star:** Make complex agricultural operations continue correctly when reality deviates from the plan.

This file is protected acceptance input. Coding agents must not edit, weaken, replace, or delete it.

## Product loop

Connect → Understand → Detect Exception → Determine Impact → Collaborate → Optimize → Check Policy → Approve → Execute → Verify → Learn → Quantify Value.

## Product boundary

This product is not another FMIS, AI Agronomist, or digital twin for its own sake. Existing Deere, CropX, ERP, IoT, weather, satellite, logistics and communication systems stay in place. Everstate provides canonical operational truth, exception handling, cross-system impact analysis, governed replanning, execution verification and outcome learning.

## Required core chain

Canonical Model → Connector SDK → World State → Exception Object → Dependency Graph → Supervisor + Agents → Optimization → Policy Engine → Approval → Action → Outcome.

## Required canonical entities

Organization, Farm, Field, CropCycle, Machine, Sensor, Worker, Task, Input, Inventory, Supplier, Contract, Shipment, Regulation, Event, Exception, Action, Outcome.

## Required invariants

- Canonical identity is provider-independent and tenant scoped.
- Entity aliases retain resolution confidence and evidence.
- Every actionable fact has provenance, observed/measured time, received time, freshness, quality and confidence.
- Freshness states are FRESH / AGING / STALE / UNKNOWN.
- Stale critical data cannot silently drive a high-risk action.
- Events and Exceptions are separate concepts; an Exception means the current plan is threatened or invalidated.
- Exception impact supports yield, revenue, cost, quality, compliance, contract, worker safety, water, machine utilization and time.
- Agent communication is structured and evidence-linked, not free-form operational chat.
- Initial agent workforce is Supervisor + Agronomy + Operations + Weather/Risk + Compliance.
- LLM = language/reasoning; ML/time-series = prediction; OR solver = optimization; deterministic policy = compliance/safety.
- Candidate plan selection runs feasibility → policy → optimization → risk → economics.
- Policy decisions support ALLOW, ALLOW_AND_LOG, REQUIRE_APPROVAL, REQUIRE_DUAL_APPROVAL and DENY.
- Every write is idempotent.
- Reversible actions declare compensation; irreversible actions are treated conservatively.
- No execution success is recorded before verification.
- Outcomes compare expected vs observed and feed a Decision → Action → Outcome dataset.
- ROI/value records are explicitly VERIFIED, ESTIMATED or ATTRIBUTED.
- Multi-tenant isolation, Data Vault access visibility/revocation, scoped Agent Identity and immutable audit are mandatory.

## Primary UX

The primary product surface is Attention/Exceptions, not a metric dashboard. Every Exception view answers: what happened, what is affected, why it matters, time remaining, evidence, available plans, cost/risk/compliance, approvals, execution and verification.

## Primary KPI

Exception Resolution Success Rate.

Supporting KPIs: Time-to-Detection, Time-to-Resolution, Plan Feasibility, Unauthorized Action Rate, False Exception Rate, Verified ROI, Human Override Rate, Recommendation-to-Outcome Calibration.

## Release blockers

Production is blocked by any cross-tenant leak, unauthorized action, compliance override, duplicate purchase/action, action on stale critical data, hallucinated machine state treated as fact, incorrect high-impact entity resolution, unrecoverable workflow, missing audit trail, or success claim before verification.

## MVP proof

The first end-to-end proof is weather-driven operations exceptions over fields/crop/workers/machines/inventory plus weather/satellite. A material forecast change must create the correct Exception, identify affected irrigation/spray/harvest work, build multiple feasible plans with cost/risk/compliance, obtain required approval, update tasks/notifications, verify outcome and record value.
