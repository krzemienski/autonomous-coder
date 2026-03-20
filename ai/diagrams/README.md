# TUI Agent Orchestration System — Diagrams

Unified Impact Diagrams following Diagram Driven Development (DDD) methodology.
Every diagram connects Front-Stage (user experience) to Back-Stage (technical implementation).

## Architecture

| Diagram | Purpose | Last Updated |
|---------|---------|--------------|
| [arch-system-overview](architecture/arch-system-overview.md) | Four-layer architecture: TUI → Orchestration → SDK → Persistence | 2026-03-19 |

## Features

| Diagram | Purpose | Last Updated |
|---------|---------|--------------|
| [feature-security-pipeline](features/feature-security-pipeline.md) | `can_use_tool` defense-in-depth with pre-execution blocking | 2026-03-19 |
| [feature-cost-tracking](features/feature-cost-tracking.md) | Manual budget enforcement via `ResultMessage.total_cost_usd` | 2026-03-19 |

## Journeys

| Diagram | Purpose | Last Updated |
|---------|---------|--------------|
| [sequence-agent-pipeline](journeys/sequence-agent-pipeline.md) | Full R→E→P→C pipeline user journey with cost tracking | 2026-03-19 |

## Refactoring

_No refactoring diagrams yet._
