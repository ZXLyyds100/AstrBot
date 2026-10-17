"""Measure the T2I return contract using real rendering and production file routes.

The renderer failure is actual loopback HTTP. File downloads use the production
ASGI router and services in-process; this is not a full deployed dashboard/IM test.
"""

import argparse
import asyncio
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
from aiohttp import web
from fastapi import FastAPI
from PIL import Image


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ["ASTRBOT_ROOT"] = str(output / "disposable-runtime")
    os.environ["ASTRBOT_DASHBOARD_INITIAL_PASSWORD"] = "Fixture-Only-Do-Not-Deploy-10388!"
    sys.path.insert(0, str(source))

    import astrbot.core.star.base as star_base
    from astrbot.core import file_token_service
    from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
    from astrbot.core.utils.t2i.renderer import HtmlRenderer
    from astrbot.dashboard.api.files import legacy_router
    from astrbot.dashboard.services.file_service import FileService

    assert Path(star_base.__file__).resolve().is_relative_to(source)
    Path(get_astrbot_temp_path()).mkdir(parents=True, exist_ok=True)
    state = {"remote_success": False}
    probes = []
    remote_image = io.BytesIO()
    Image.new("RGB", (32, 32), "#185bba").save(remote_image, format="PNG")

    async def renderer_request(request):
        payload = await request.json()
        probes.append({"json": payload["json"], "success": state["remote_success"]})
        if state["remote_success"]:
            return web.json_response({"data": {"id": "remote.png"}})
        if not payload["json"]:
            request.transport.close()
        return web.Response(status=503, text="Synthetic loopback renderer failure")

    async def renderer_image(_request):
        return web.Response(body=remote_image.getvalue(), content_type="image/png")

    renderer_app = web.Application(client_max_size=16 * 1024 * 1024)
    renderer_app.router.add_post("/text2img/generate", renderer_request)
    renderer_app.router.add_get("/text2img/remote.png", renderer_image)
    runner = web.AppRunner(renderer_app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    endpoint = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
    renderer = HtmlRenderer(endpoint)
    config = {"t2i_endpoint": endpoint, "callback_api_base": "http://fixture.test"}
    context = SimpleNamespace(get_config=lambda _umo: config, html_renderer=renderer)
    star = star_base.Star(context)
    file_app = FastAPI()
    file_app.state.services = SimpleNamespace(files=FileService())
    file_app.include_router(legacy_router)
    results = {}
    text = "# Synthetic T2I contract fixture\n\nRendered locally after a real HTTP failure."
    try:
        result = await star.text_to_image(text, return_url=True, umo="fixture:group:10388")
        is_url = urlsplit(result).scheme in {"http", "https"}
        results["url_requested_with_callback"] = {
            "actual_kind": "http_url" if is_url else "filesystem_path",
            "value": result if is_url else Path(result).name,
            "filesystem_path_redacted": not is_url,
        }
        if is_url:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=file_app), base_url="http://fixture.test"
            ) as client:
                first = await client.get(result)
                second = await client.get(result)
                token = result.rsplit("/", 1)[-1]
                local_path, _, single_use = file_token_service.staged_files[token]
                file_token_service.staged_files[token] = (local_path, 0, single_use)
                expired = await client.get(result)
                (output / "rendered-fallback.jpg").write_bytes(first.content)
                results["file_route"] = {
                    "first_status": first.status_code,
                    "second_status": second.status_code,
                    "expired_status": expired.status_code,
                    "expiry_method": "Stored expiry moved into the past; not a five-minute wall-clock wait",
                    "same_bytes": first.content == second.content == Path(local_path).read_bytes(),
                    "content_type": first.headers.get("content-type"),
                    "single_use": single_use,
                }
        else:
            shutil.copyfile(result, output / "rendered-fallback.jpg")
            results["file_route"] = {"not_attempted": "The helper returned a path, not a URL"}

        config.pop("callback_api_base")
        try:
            result = await star.text_to_image(text, return_url=True)
            results["url_requested_without_callback"] = {
                "actual_kind": "filesystem_path",
                "value": Path(result).name,
                "filesystem_path_redacted": True,
            }
        except RuntimeError as error:
            results["url_requested_without_callback"] = {
                "actual_kind": "actionable_error",
                "exception": type(error).__name__,
                "message": str(error),
            }
        invalid_bases = []
        for suffix in ("?", "#", "?#", "/proxy/?", "/proxy/#", "/proxy/?#"):
            config["callback_api_base"] = f"http://fixture.test{suffix}"
            tokens_before = len(file_token_service.staged_files)
            try:
                invalid_result = await star.text_to_image(text, return_url=True)
                observation = {
                    "actual_kind": "http_url"
                    if urlsplit(invalid_result).scheme in {"http", "https"}
                    else "filesystem_path",
                }
            except RuntimeError as error:
                observation = {
                    "actual_kind": "actionable_error",
                    "exception": type(error).__name__,
                    "message": str(error),
                }
            invalid_bases.append({
                "synthetic_base": config["callback_api_base"],
                **observation,
                "extra_tokens": len(file_token_service.staged_files) - tokens_before,
            })
        config.pop("callback_api_base")
        results["invalid_callback_delimiters"] = invalid_bases
        result = await star.text_to_image(text, return_url=False)
        with Image.open(result) as image:
            results["path_requested"] = {
                "actual_kind": "filesystem_path", "exists": Path(result).is_file(),
                "format": image.format, "size": list(image.size),
            }
        result = await renderer.render_t2i(text, return_url=True, endpoint=endpoint)
        results["lower_level_renderer"] = {
            "actual_kind": "filesystem_path", "exists": Path(result).is_file(),
            "registered_tokens": len(file_token_service.staged_files),
        }
        state["remote_success"] = True
        count_before = len(file_token_service.staged_files)
        result = await star.text_to_image(text, return_url=True)
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(result)
        results["remote_success"] = {
            "actual_kind": "http_url", "get_status": response.status_code,
            "content_matches": response.content == remote_image.getvalue(),
            "extra_tokens": len(file_token_service.staged_files) - count_before,
        }
    finally:
        await runner.cleanup()

    with Image.open(output / "rendered-fallback.jpg") as image:
        rendered = {"format": image.format, "size": list(image.size)}
    checks = {
        "local_url_request_returns_url": results["url_requested_with_callback"]["actual_kind"] == "http_url",
        "local_url_without_base_fails_clearly": results["url_requested_without_callback"]["actual_kind"] == "actionable_error",
        "empty_query_or_fragment_rejected_without_tokens": all(
            case["actual_kind"] == "actionable_error" and case["extra_tokens"] == 0
            for case in results["invalid_callback_delimiters"]
        ),
        "explicit_path_still_works": results["path_requested"]["exists"],
        "lower_level_path_semantics_unchanged": results["lower_level_renderer"]["exists"],
        "remote_url_success_unchanged": results["remote_success"]["content_matches"] and results["remote_success"]["extra_tokens"] == 0,
        "repeated_download_and_expiry": results["file_route"].get("first_status") == 200
        and results["file_route"].get("second_status") == 200
        and results["file_route"].get("expired_status") == 404
        and results["file_route"].get("same_bytes") is True,
    }
    proof = {
        "boundary": "Real loopback renderer HTTP; real local Pillow render; production ASGI file router/services; not full dashboard/IM",
        "source_commit": subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip(),
        "source_file_sha256": hashlib.sha256(Path(star_base.__file__).read_bytes()).hexdigest(),
        "results": results, "renderer_probes": probes, "rendered_image": rendered,
        "checks": checks, "all_checks_passed": all(checks.values()),
    }
    (output / "proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps(proof, indent=2))


asyncio.run(main())
