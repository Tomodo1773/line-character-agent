# Copilot Instructions for line-character-agent

## Project Overview

This repository is a LINE-integrated AI character agent system built on Azure services. It features:
- Multi-channel support (LINE Messaging API, OpenAI-compatible API)
- Voice diary functionality with AI transcription
- LangGraph-based multi-agent orchestration
- Integration with Spotify (via MCP), Google Drive, and Cosmos DB

### Service Architecture

The project consists of three main Azure-deployed components:
1. **API Service** (`src/api/`) - FastAPI-based LINE webhook handler and chatbot agent
2. **Function Service** (`src/func/`) - Azure Functions for diary data upload to Cosmos DB
3. **MCP Service** (`src/mcp/`) - Model Context Protocol server for Spotify integration

## Technology Stack

- **Language**: Python 3.11
- **Web Framework**: FastAPI with uvicorn
- **AI/ML**: LangChain, LangGraph, OpenAI
- **Package Manager**: uv (not pip)
- **Testing**: pytest with pytest-asyncio
- **Linting/Formatting**: ruff
- **Infrastructure**: Azure (App Service, Functions, Cosmos DB, Key Vault)
- **IaC**: Bicep templates in `infra/`

## Development Commands

### API Service (`src/api/`)
```bash
cd src/api
uv sync                           # Install dependencies
uv add <package>                  # Add new package
uvicorn chatbot.main:app --reload # Run locally
uv run pytest                     # Run tests
uv run ruff check                 # Lint
uv run ruff format                # Format
```

### Function Service (`src/func/`)
```bash
cd src/func
uv sync                           # Install dependencies
uv add <package>                  # Add new package
# Use Azure Functions Core Tools for local execution
uv run pytest                     # Run tests
uv run ruff check                 # Lint
uv run ruff format                # Format
```

### MCP Service (`src/mcp/`)
```bash
cd src/mcp
uv sync                           # Install dependencies
uv add <package>                  # Add new package
uv run pytest                     # Run tests
uv run ruff check                 # Lint
uv run ruff format                # Format
```

## Coding Standards

### General Rules
- **Python version**: 3.11
- **Indentation**: 4 spaces
- **Line length**: 127 characters (ruff configured)
- **Naming conventions**:
  - Files/functions/variables: `snake_case`
  - Classes: `PascalCase`
- **Import order**: standard library → third-party → local
- **Import style**: Prefer absolute imports

### Code Quality
- Run `pre-commit run -a` before pushing
- All code must pass `ruff check` and `ruff format`
- Follow single responsibility principle
- Avoid global state; make dependencies explicit
- Keep functions pure when possible

## Testing Guidelines

- **Framework**: pytest with pytest-asyncio
- **Location**: `src/*/tests/` directories
- **Naming**: Files: `test_*.py`, Functions: `test_*`
- **Execution**: Run `uv run pytest` in each service directory
- **External dependencies**: Use `pytest.skip` if required env vars are missing
- Focus on small, independent unit tests

## Environment Variables

### Adding New Environment Variables
When adding a new environment variable, follow these 4 steps:
1. Define in the configuration module (e.g., `src/api/chatbot/utils/config.py`)
2. Add to `.env.sample` in the service directory
3. Add to `infra/main.bicep` in the appropriate service's `appSettings`
4. Document the purpose in the PR description

### Key Vault Secrets
- Register secrets in Azure Key Vault first
- Reference in `main.bicep` using `@Microsoft.KeyVault(SecretUri=...)`
- Never commit secrets to the repository
- Use `.env` files locally, Key Vault in Azure

### Important Notes
- DO NOT add scattered `os.environ.get()` calls throughout the code
- Centralize environment variable validation in config modules
- Missing `main.bicep` entries cause 503 errors in production
- Cosmos/Storage connection strings are auto-injected by service modules

## Architecture Notes

### Agent System (LangGraph)
The chatbot uses LangGraph for agent orchestration:
1. `router` node: Routes messages to appropriate agents
2. `spotify_agent` node: Handles music-related operations (via MCP)
3. `diary_search` node: RAG search over past diary entries
4. `chatbot` node: Main conversation handler (with web search capability)

### Data Flow
- LINE messages → FastAPI webhook → Agent processing → LINE API response
- Chat history stored in Cosmos DB (last 10 messages, 1-hour retention)
- Diary documents vectorized and stored in Cosmos DB for RAG

### Key Components
- **ChatbotAgent** (`src/api/chatbot/agent/`) - LangGraph-based agent implementation
- **Database layer** (`src/api/chatbot/database/`) - Cosmos DB repositories and models
- **LINE integration** (`src/api/chatbot/utils/line.py`) - LINE Messaging API wrapper
- **Authentication** (`src/api/chatbot/utils/auth.py`) - API key auth for OpenAI-compatible endpoint

## Commit and PR Guidelines

### Commit Messages
Use Conventional Commits format:
- `feat(api): add diary route`
- `fix(func): handle 404 errors`
- `refactor(mcp): simplify spotify client`
- `test(api): add agent integration tests`
- `docs: update README with new features`

### Pull Requests
- Clear, concise title
- Summary of changes
- Link related issues (e.g., `Closes #123`)
- Include test evidence (logs/commands)
- Update documentation if needed
- Ensure all checks pass (ruff, pytest, pre-commit)

## Security Best Practices

- Never commit secrets or credentials
- Use Azure Key Vault for production secrets
- Keep `.env` files local and add to `.gitignore`
- Validate and sanitize external inputs (LINE webhooks, API requests)
- Follow principle of least privilege for service accounts

## Design Philosophy

This repository prioritizes:
- **Best practices adherence**: Clear dependencies, single responsibility, loose coupling
- **Readability**: One file, one responsibility; no implicit global state
- **Changeability**: Add features without widespread modifications
- **Testability**: Push side effects to boundaries; focus on pure functions
- **Portability**: Explicit separation of credentials and external dependencies

### Change Strategy
Since this is a single-user project, we prioritize learning value and structural optimization over legacy compatibility. Don't hesitate to perform comprehensive refactoring (directory reorganization, interface overhaul, storage layer replacement) when needed. Avoid temporary hacks and compatibility bridges; move to a clean solution in one step.

## Module-Specific Guidance

### API Service
- Entry point: `src/api/chatbot/main.py`
- Configuration: `src/api/chatbot/utils/config.py`
- Database models: `src/api/chatbot/database/models.py`
- Repository pattern: `src/api/chatbot/database/repositories.py`

### Function Service
- Handles diary data upload to Cosmos DB
- Azure Functions runtime
- Async-ready with pytest

### MCP Service
- Model Context Protocol server for Spotify/OpenAI integration
- Called by API service agents
- Tests may skip if required env vars are missing

## Language and Communication

When performing a code review, respond in Japanese.