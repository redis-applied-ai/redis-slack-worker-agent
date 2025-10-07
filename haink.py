#!/usr/bin/env python3
"""
haink - CLI for the applied AI agent application

Controls starting the REST API, worker, and running the data pipeline.
"""

import os
import subprocess
import sys

import click


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """haink - Applied AI Agent CLI

    Controls starting the REST API, worker, and running the data pipeline.
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.option("--host", default="localhost", help="Host to bind the server to")
@click.option("--port", default=3000, help="Port to bind the server to")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def api(host, port, reload):
    """Start the FastAPI server"""
    click.echo(f"Starting FastAPI server on {host}:{port}")

    cmd = ["uv", "run", "fastapi", "dev" if reload else "run", "app.api.main:app"]
    if not reload:
        cmd.extend(["--host", host, "--port", str(port)])

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        click.echo("\nShutting down API server...")
    except subprocess.CalledProcessError as e:
        click.echo(f"Error starting API server: {e}", err=True)
        sys.exit(1)


@cli.command()
def worker():
    """Start the Docket worker"""
    click.echo("Starting Docket worker...")

    try:
        subprocess.run(["uv", "run", "python", "-m", "app.worker"], check=True)
    except KeyboardInterrupt:
        click.echo("\nShutting down worker...")
    except subprocess.CalledProcessError as e:
        click.echo(f"Error starting worker: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--ingestion-only", is_flag=True, help="Run only the ingestion pipeline")
@click.option(
    "--processing-only", is_flag=True, help="Run only the processing pipeline"
)
@click.option("--force-reclone", is_flag=True, help="Force re-clone repositories")
@click.option(
    "--force-redownload", is_flag=True, help="Force re-download recipe notebooks"
)
def pipeline(ingestion_only, processing_only, force_reclone, force_redownload):
    """Run the data pipeline (DEPRECATED - pipelines module removed)"""
    click.echo("❌ Pipeline functionality has been removed.")
    click.echo("💡 Use the API endpoints instead:")
    click.echo("   - POST /api/content/ingest - for content ingestion")
    click.echo("   - POST /api/content/vectorize - for content vectorization")
    click.echo("   - Use the Haink web interface or API directly")
    return


@cli.command()
def dev():
    """Start development environment (API + Worker in parallel)"""
    click.echo("Starting development environment...")
    click.echo("This will start both the API server and worker in parallel.")
    click.echo("Press Ctrl+C to stop both services.")

    import threading
    import time

    def run_api():
        subprocess.run(["uv", "run", "fastapi", "dev", "app.api.main:app"])

    def run_worker():
        # Give API a moment to start first
        time.sleep(2)
        subprocess.run(["uv", "run", "python", "-m", "app.worker"])

    api_thread = threading.Thread(target=run_api, daemon=True)
    worker_thread = threading.Thread(target=run_worker, daemon=True)

    try:
        api_thread.start()
        worker_thread.start()

        # Keep main thread alive
        while api_thread.is_alive() or worker_thread.is_alive():
            time.sleep(0.1)

    except KeyboardInterrupt:
        click.echo("\nShutting down development environment...")


@cli.command()
def health():
    """Check health of all services"""
    click.echo("Checking service health...")

    # Check if Redis is running
    try:
        import redis

        r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        r.ping()
        click.echo("✓ Redis: Connected")
    except Exception as e:
        click.echo(f"✗ Redis: Failed to connect ({e})")

    # Check if API is running (basic check)
    try:
        import httpx

        response = httpx.get("http://localhost:3000/health", timeout=5)
        if response.status_code == 200:
            click.echo("✓ API: Running")
        else:
            click.echo(f"✗ API: HTTP {response.status_code}")
    except Exception:
        click.echo("✗ API: Not responding")


if __name__ == "__main__":
    cli()
