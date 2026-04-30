"""MCP server entry point for Hermes integration.

Run with:
    python -m trading_lab.mcp_server

Register in ~/.hermes/config.yaml:
    mcp_servers:
      trading-lab:
        command: "/path/to/.venv/bin/python"
        args: ["-m", "trading_lab.mcp_server"]
        env:
          PYTHONPATH: "/path/to/src"
        timeout: 60
"""
from trading_lab.mcp_server import main

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
