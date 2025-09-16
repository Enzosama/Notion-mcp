from setuptools import setup, find_packages

setup(
    name="notion-mcp-server",
    version="1.0.0",
    description="A Model Context Protocol server for Notion integration",
    author="Your Name",
    packages=find_packages(),
    install_requires=[
        "notion-client>=2.2.1",
        "mcp>=0.5.0",
        "asyncio-compat>=0.1.2",
    ],
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "notion-mcp-server=mcp_server:main",
            "notion-mcp-client=main:main",
        ]
    },
)