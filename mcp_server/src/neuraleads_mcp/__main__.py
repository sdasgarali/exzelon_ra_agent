"""CLI entry point: ``neuraleads-mcp [--transport stdio|http]``."""
from __future__ import annotations

import argparse
import logging
import sys

from neuraleads_mcp import __version__
from neuraleads_mcp.config import ConfigError, Settings


def _configure_logging(level: str) -> None:
    # stdout carries the MCP protocol in stdio mode, so logs must go to stderr.
    logging.basicConfig(stream=sys.stderr, level=getattr(logging, level, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)


def build_http_app(settings: Settings):
    """ASGI app for hosted mode: stateless Streamable HTTP at /mcp plus /healthz."""
    from mcp.server.transport_security import TransportSecuritySettings

    from neuraleads_mcp.server import build_server

    mcp, _rt = build_server(settings, hosted=True)
    return mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(settings.allowed_hosts),
            allowed_origins=[f"https://{h}" for h in settings.allowed_hosts if "*" not in h],
        ),
        host=settings.http_host,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="neuraleads-mcp", description="NeuraLeads MCP connector")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--env-file", default=None, help="Optional .env file to load")
    parser.add_argument("--version", action="version", version=f"neuraleads-mcp {__version__}")
    args = parser.parse_args(argv)

    try:
        settings = Settings.from_env(args.env_file)
    except ConfigError as exc:
        print(f"neuraleads-mcp: configuration error: {exc}", file=sys.stderr)
        return 2
    _configure_logging(settings.log_level)
    log = logging.getLogger("neuraleads_mcp")

    if args.transport == "stdio":
        if not settings.api_key:
            log.warning("NEURALEADS_API_KEY is not set; every tool call will fail until it is.")
        from neuraleads_mcp.server import build_server

        mcp, _rt = build_server(settings, hosted=False)
        log.info("NeuraLeads MCP %s (stdio) -> %s%s", __version__, settings.api_url,
                 " [read-only]" if settings.read_only else "")
        mcp.run("stdio")
        return 0

    import uvicorn

    log.info("NeuraLeads MCP %s (http) on %s:%s -> %s%s", __version__, settings.http_host,
             settings.http_port, settings.api_url, " [read-only]" if settings.read_only else "")
    uvicorn.run(build_http_app(settings), host=settings.http_host, port=settings.http_port,
                log_level=settings.log_level.lower(), proxy_headers=True, forwarded_allow_ips="127.0.0.1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
