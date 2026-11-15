"""Run Ax3l's private SnakeLab MCP server over stdio."""

from ax3l.app.snakelab.tools.server import mcp


if __name__ == "__main__":
    mcp.run()
