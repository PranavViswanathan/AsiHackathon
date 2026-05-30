# Agents

AirFlow ships a set of Claude Code subagents, each scoped to one part of the
stack. They live in `.claude/agents/` as Markdown files and let work proceed in
parallel with focused context. This document covers installing, listing,
invoking, and sequencing them.

## Installing Agents

Project-level agents are just Markdown files in the project's `.claude/agents/`
directory. To install (or share) them, copy the agent definitions into place:

```
cp .claude/agents/*.md <other-project>/.claude/agents/
```

Within this repo they are already in `.claude/agents/` and are picked up
automatically when you run Claude Code from the project root. Each `*.md` file
has frontmatter (name, description, allowed tools) followed by the agent's
system prompt.

## Agent Roster

| Agent | Responsibility |
| --- | --- |
| **airspace-coder** | Core routing algorithm: space-time grid construction, congestion modeling, Dijkstra shortest-path routing, the iterative re-routing heuristic, and the optional QUBO optimization layer. Owns `src/algorithm/`. |
| **data-generator** | Synthetic and scenario flight data: generating realistic flight records, tuning grid parameters, seeding specific congestion scenarios, and exporting CSVs. Supports ingestion and test data. |
| **backend-engineer** | FastAPI backend: API routes, data models, request/response schemas, and serving routing results to the frontend. Owns `backend/`. |
| **frontend-engineer** | Next.js / React frontend: UI components, API integration, state management, and layout. Owns `frontend/` pages, components, and API hooks. |
| **viz-engineer** | Data visualization: heatmaps, flight-path animations, convergence charts, and the 3D scene polish — making the data look good and stay interactive. |
| **notebook-runner** | Jupyter notebooks: structuring analysis notebooks, adding markdown narrative, formatting plots, keeping `.ipynb` files clean and readable. |
| **demo-polisher** | Demo and presentation: UI copy, the pitch narrative, the README, and the before/after story — used in the final hours to make everything judge-ready. |
| **devops-agent** | Docker and deployment: Dockerfiles, docker-compose, environment variables, and getting the full stack up with one command. |

## Invoking Agents

Three ways, all equivalent in effect:

- **Natural language** — describe the work and let Claude Code route it to the
  right agent, e.g. "build the solve endpoint" naturally goes to
  `backend-engineer`.
- **@-mention** — name the agent directly in your message, e.g.
  `@airspace-coder add the weather penalty to the cost function`.
- **CLI flag** — start a session pinned to an agent:
  `claude --agent airspace-coder`.

## Recommended Hackathon-Day Sequence

Run the agents in phases so each builds on a working foundation laid by the
previous one. Phase 3 fans out in parallel once the API contract is stable.

```
Phase 0  data-generator                     # ingestion: parse flights, sectors, weather
Phase 1  airspace-coder                      # algorithm: grid + iterative Dijkstra solver
Phase 2  backend-engineer                    # API: expose solver over FastAPI
Phase 3  frontend-engineer + viz-engineer    # parallel: UI + 3D/charts on the live API
Phase 4  demo-polisher                       # final hour: copy, README, before/after story
```

`notebook-runner` and `devops-agent` slot in as needed — notebooks alongside
Phase 1 for analysis, and containerization once the stack runs end to end.
