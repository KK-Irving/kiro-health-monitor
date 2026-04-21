"""Entry point for Kiro Health Monitor MCP Server."""

from src.tools.mcp_server import create_server


def main() -> None:
    """Start the Kiro Health Monitor MCP Server."""
    mcp = create_server()
    mcp.run()


if __name__ == "__main__":
    main()
