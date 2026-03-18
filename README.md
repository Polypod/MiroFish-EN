<div align="center">

<img src="./static/image/MiroFish_logo_compressed.jpeg" alt="MiroFish Logo" width="60%"/>

# MiroFish — 3GPP Standardization Simulation Fork

This repository is a fork of [666ghj/MiroFish](https://github.com/666ghj/MiroFish) (original, Chinese) via the English translation at [666ghj/MiroFish-EN](https://github.com/666ghj/MiroFish-EN).
This fork by [Polypod](https://github.com/Polypod) extends MiroFish with 3GPP telecom standardization simulation capabilities.

</div>

## ⚡ What is MiroFish?

**MiroFish** is a multi-agent social simulation engine. Upload seed documents, describe a prediction requirement in natural language, and MiroFish builds a population of AI agents with independent personalities, long-term memory, and behavioral logic — then runs them in a simulated social environment.

For a full description, demos, and background see the upstream project: [666ghj/MiroFish-EN](https://github.com/666ghj/MiroFish-EN).

The simulation engine is powered by **[OASIS (Open Agent Social Interaction Simulations)](https://github.com/camel-ai/oasis)** by the CAMEL-AI team.

## 🔄 Workflow

1. **Graph Building** — Upload documents, extract entities, build a Graphiti knowledge graph (backed by Neo4j)
2. **Simulation Prep** — Generate agent personas, add synthetic delegates, produce agent config
3. **Simulation** — Run dual-platform (Reddit/Twitter mode) multi-agent simulation via OASIS
4. **Report** — Interact with a ReportAgent and individual simulation agents post-run

## 🔬 Polypod Extensions — 3GPP Standardization Simulation

This fork adds support for simulating **3GPP telecom standardization meetings**, where fictive but realistic conference delegates from different companies debate and negotiate technical proposals.

### Synthetic 3GPP Delegate Generation

The standard MiroFish pipeline creates agents from entities extracted from uploaded documents. This fork adds a parallel path that generates **synthetic delegates** — fictive persons with realistic company affiliation, working group membership, technical expertise, seniority, role, and stance — to supplement or replace graph-extracted entities.

**How it works:**

1. During simulation preparation, an LLM analyzes uploaded documents and infers which 3GPP companies are most relevant to the debate, allocating a configurable number of delegates across them.
2. A second LLM call batch-generates full delegate personas grounded in the topic context. Each delegate gets a name, bio, detailed persona, MBTI, country, expertise areas, and stance.
3. Synthetic delegates are merged with any real graph entities and passed into OASIS.

**Preset company library** (`backend/app/data/3gpp_companies.json`) — 25 major 3GPP participants:

| Region | Companies |
| ------ | --------- |
| EU | Ericsson, Nokia, Deutsche Telekom, Orange, Vodafone |
| US | Qualcomm, Intel, Apple, Google, AT&T, T-Mobile, InterDigital |
| CN | Huawei, ZTE, OPPO, vivo, China Mobile, CATT |
| APAC | Samsung, MediaTek, KDDI, NTT DOCOMO, Sharp, Panasonic, LG Electronics |

Working groups: RAN1, RAN2, RAN3, SA1, SA2, SA3, CT1, CT4

**API** — new optional fields in `POST /api/simulation/prepare`:

```json
{
  "enable_synthetic_delegates": true,
  "synthetic_delegate_count": 30,
  "synthetic_delegate_config": null
}
```

`synthetic_delegate_config` accepts a manual company list to bypass LLM distribution inference. A toggle and count input are available in the simulation prep UI.

### Other Changes

- **Any OpenAI-compatible LLM provider** — works with OpenRouter, LM Studio, Mistral, or any provider. Set `LLM_JSON_MODE=false` for local models that don't support JSON response format.
- **`.env.local` support** — loaded before `.env` for local credential overrides.
- **CORS preflight fix** — `OPTIONS` requests are exempt from API key auth, fixing frontend 401 errors.
- **Delegate conference hours** — synthetic delegates use 08:00–17:00 working hours instead of the default evening-peak schedule.

## 🚀 Quick Start

### Prerequisites

| Tool | Version | Check |
| ---- | ------- | ----- |
| Node.js | 18+ | `node -v` |
| Python | 3.11–3.12 | `python --version` |
| uv | latest | `uv --version` |

### 1. Configure environment variables

```bash
cp .env.example .env
# Edit .env — or create .env.local for local overrides
```

Minimum required:

```env
LLM_API_KEY=your_key
LLM_BASE_URL=https://openrouter.ai/api/v1   # or any OpenAI-compatible endpoint
LLM_MODEL_NAME=openai/gpt-4o-mini
LLM_JSON_MODE=true                           # set false for local models

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-neo4j-password

GRAPHITI_EMBED_BASE_URL=http://localhost:1234/v1   # LM Studio or compatible
GRAPHITI_EMBED_MODEL=mlx-community/Qwen3-Embedding-4B-mxfp8
GRAPHITI_EMBED_API_KEY=lm-studio

# Optional: switch to Zep Cloud instead of Graphiti
# MEMORY_BACKEND=zep
# ZEP_API_KEY=your_zep_api_key

API_KEY=your_api_key
VITE_API_KEY=your_api_key
SECRET_KEY=your_secret_key
```

### 2. Install dependencies

```bash
npm run setup:all
```

### 3. Start

```bash
npm run dev
```

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:5001`

### Docker

```bash
cp .env.example .env  # fill in values
docker compose up -d
```

## 📄 Acknowledgments

Built on [MiroFish](https://github.com/666ghj/MiroFish) by 666ghj / Shanda Group, and [OASIS](https://github.com/camel-ai/oasis) by the CAMEL-AI team.
