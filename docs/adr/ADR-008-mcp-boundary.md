# ADR-008: MCP Boundary Rules

**STATUS**: Accepted
**CONTEXT**: We expose functionality to LLM agents via Model Context Protocol (MCP).
**DECISION**: The MCP Server MUST NOT bypass authorization or access the database directly. It MUST communicate with Application Services.
**CONSEQUENCES**: Ensures agent actions are governed by the same security and domain rules as HTTP users.
