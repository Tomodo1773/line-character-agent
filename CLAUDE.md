# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a LINE AI chatbot built with Azure services that creates a character-based conversational AI agent. The bot uses LangGraph for agent orchestration and can perform web searches when needed. It consists of three main components deployed as Azure services:

1. **API Service** (`src/api/`) - FastAPI-based LINE webhook handler and chatbot agent
2. **Function Service** (`src/func/`) - Azure Function for automated diary uploading to AI Search
3. **MCP Service** (`src/mcp/`) - Model Context Protocol server for Spotify integration

## Development Commands

### API Service (src/api/)
- **Install dependencies**: `cd src/api && uv install`
- **Run locally**: `cd src/api && uvicorn chatbot.main:app --reload`
- **Run tests**: `cd src/api && pytest`
- **Lint code**: `cd src/api && ruff check`
- **Format code**: `cd src/api && ruff format`

### Function Service (src/func/)
- **Install dependencies**: `cd src/func && uv install`
- **Run locally**: Use Azure Functions Core Tools

### MCP Service (src/mcp/)
- **Install dependencies**: `cd src/mcp && uv install`

### Deployment
- **Deploy all services**: `azd up`
- **Deploy specific service**: `azd deploy <service-name>`

## Architecture Notes

### Agent System
The chatbot uses LangGraph to create an AI agent with the following flow:
1. Messages are processed by the `chatbot` node
2. If web search is needed, the `tools` node (Tavily) is called
3. The agent can iterate between chatbot and tools until a final response is generated

### Data Flow
- LINE messages → FastAPI webhook → Agent processing → Response via LINE API
- Chat history is stored in Azure Cosmos DB (last 10 messages, 1 hour retention)
- Diary documents are automatically uploaded to Azure AI Search for RAG

### Key Components
- **ChatbotAgent** (`src/api/chatbot/agent/`) - LangGraph-based agent implementation
- **Database layer** (`src/api/chatbot/database/`) - Cosmos DB repositories and models
- **LINE integration** (`src/api/chatbot/utils/line.py`) - LINE Messaging API wrapper
- **Authentication** (`src/api/chatbot/utils/auth.py`) - API key verification for OpenAI-compatible endpoints

### Environment Configuration
- All services use uv for dependency management
- API service uses `.env` files for local development
- Azure deployment uses bicep templates in `infra/` directory

### Testing
- API service has pytest configuration with async support
- Tests are located in `src/api/tests/`
- Use `pytest` command in the API directory to run tests