from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-mcp-server",
    version="1.0.0",
    description="FastMCP server that auto-discovers CLI-Anything harnesses and exposes them as MCP tools",
    packages=find_namespace_packages(include=("cli_anything.*",)),
    python_requires=">=3.10",
    install_requires=[
        "mcp>=1.0",
        "click>=8.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-asyncio>=0.21",
        ],
    },
    entry_points={
        "console_scripts": [
            "cli-anything-mcp-server=cli_anything.mcp_server.server:main",
        ],
    },
)
