import asyncio
import io
import json
import unittest
from unittest.mock import AsyncMock, patch

from flow_errors import error_fields, with_next_step


class ErrorFieldsTest(unittest.TestCase):
    def test_own_message_is_returned(self):
        try:
            raise ValueError("Modelo inválido; use omni-flash.")
        except ValueError as exc:
            self.assertEqual(error_fields(exc), {"error_type": "ValueError",
                                                 "error": "Modelo inválido; use omni-flash."})

    def test_unexpected_internal_error_points_to_location(self):
        try:
            [][1]
        except IndexError as exc:
            fields = error_fields(exc)
        self.assertIn("formato inesperado", fields["error"])
        self.assertTrue(fields["error_location"].startswith("test_errors.py:"))

    def test_full_disk_is_explained(self):
        import errno

        try:
            raise OSError(errno.ENOSPC, "No space left on device")
        except OSError as exc:
            self.assertIn("Disco cheio", error_fields(exc)["error"])

    def test_library_message_is_hidden(self):
        try:
            json.loads("segredo=abc")
        except ValueError as exc:
            fields = error_fields(exc, "recovery_")
        self.assertEqual(fields["recovery_error_type"], "JSONDecodeError")
        self.assertNotIn("segredo", fields["recovery_error"])

    def test_browser_errors_keep_first_line_without_urls(self):
        from playwright._impl._errors import TimeoutError as BrowserTimeout

        code = compile("raise BrowserTimeout(text)", "/site-packages/playwright/_impl/x.py", "exec")
        text = ('locator.click: Timeout 5000ms exceeded. at https://storage.googleapis.com/a?Signature=SEGREDO\n'
                'Call log: waiting for get_by_role("button", name="Nova cena")')
        try:
            exec(code, {"BrowserTimeout": BrowserTimeout, "text": text})
        except BrowserTimeout as exc:
            fields = error_fields(exc)
        self.assertIn("Timeout 5000ms", fields["error"])
        self.assertNotIn("SEGREDO", fields["error"])
        self.assertNotIn("Call log", fields["error"])

    def test_gflow_input_validation_is_returned(self):
        from gflow_cli.api.video import Aspect

        try:
            Aspect.from_cli("2:1")
        except ValueError as exc:
            self.assertIn("2:1", error_fields(exc).get("error", ""))

    def test_model_names_accept_common_variants_and_list_options(self):
        from flow_video import IMAGE_MODELS, VIDEO_MODELS, normalize_model

        self.assertEqual(normalize_model("omni_flash", VIDEO_MODELS), "omni-flash")
        self.assertEqual(normalize_model("Nano Banana Pro", IMAGE_MODELS), "nano-pro")
        with self.assertRaises(ValueError) as ctx:
            normalize_model("sora", VIDEO_MODELS)
        self.assertIn("veo-lite", str(ctx.exception))

    def test_parsers_survive_new_sections_added_by_flow(self):
        from flow_assets import parse_assets
        from flow_character import parse_characters
        from flow_collections import parse_collections
        from flow_projects import parse_projects
        from flow_scene import parse_scenes

        project = "4020285f-df1c-4e7c-8629-922df02f2a11"
        grown = [None] * 9  # projeto vazio com uma seção nova no fim
        for parse in (parse_assets, parse_characters, parse_collections, parse_scenes):
            self.assertEqual(parse(grown, project), [])
        self.assertEqual(parse_projects([None, "cursor", "campo novo"])["projects"], [])

    def test_every_status_is_success_or_has_next_step(self):
        import re
        from pathlib import Path
        from flow_errors import NEXT_STEPS

        success = {"ok", "authenticated", "completed", "created", "updated", "deleted", "archived", "cancelled", "downloaded",
                   "uploaded", "exported", "quoted", "recovered", "unchanged", "catalog_only",
                   "waiting_for_extension", "image_set", "image_removed"}
        emitted = set()
        for path in Path(__file__).parent.glob("flow_*.py"):
            text = path.read_text(encoding="utf-8")
            emitted |= set(re.findall(r"""["']status["']\s*:\s*["']([a-z_]+)["']""", text))
            emitted |= set(re.findall(r"""\bstatus\s*=\s*["']([a-z_]+)["']""", text))
        # Status novo sem orientação ao agente: acrescente em NEXT_STEPS (ou em success).
        self.assertEqual(sorted(emitted - success - set(NEXT_STEPS)), [])

    def test_next_step_only_for_known_status(self):
        self.assertIn("NÃO repita", with_next_step({"status": "submission_unknown"})["next_step"])
        self.assertNotIn("next_step", with_next_step({"status": "ok"}))
        self.assertEqual(with_next_step({"status": "timeout", "next_step": "x"})["next_step"], "x")


class WorkerErrorTest(unittest.IsolatedAsyncioTestCase):
    async def test_worker_returns_own_validation_message(self):
        import flow_http

        class Dummy:
            def __init__(self, *args, **kwargs):
                self.account_id = "conta-a"

            async def close(self):
                pass

        request = json.dumps({"action": "generate", "payload": {"prompt": "x", "max_credits": 1,
                                                                 "model": "sora"}}) + "\n"
        out = io.StringIO()
        with patch.object(flow_http, "FlowHTTP", Dummy):
            await flow_http.worker("conta-a", io.StringIO(request), out)
        result = json.loads(out.getvalue())
        self.assertEqual(result["status"], "http_error")
        self.assertEqual(result["action"], "generate")
        self.assertIn("omni-flash", result["error"])

    async def test_unreadable_first_request_does_not_kill_worker(self):
        import flow_http

        class Dummy:
            def __init__(self, *args, **kwargs):
                self.account_id = "conta-a"

            async def close(self):
                pass

        out = io.StringIO()
        with patch.object(flow_http, "FlowHTTP", Dummy), patch.object(
                flow_http, "http_operation", AsyncMock(return_value={"status": "ok"})):
            await flow_http.worker("conta-a", io.StringIO('{quebrado\n{"action":"credits"}\n'), out)
        first, second = (json.loads(line) for line in out.getvalue().splitlines())
        self.assertEqual((first["status"], first["action"]), ("http_error", None))
        self.assertIn("ilegível", first["error"])
        self.assertEqual(second["status"], "ok")

    async def test_worker_pipe_accepts_responses_over_64_kib(self):
        import sys
        import flow_http

        real_exec = asyncio.create_subprocess_exec
        script = "import json,sys; sys.stdin.readline(); print(json.dumps({'status':'ok','x':'a'*200000}), flush=True)"

        async def fake_exec(*args, **kwargs):
            return await real_exec(sys.executable, "-c", script, **kwargs)

        with patch("asyncio.create_subprocess_exec", fake_exec):
            try:
                result = await flow_http.run_worker_operation("conta-big", "assets", {}, None, None)
            finally:
                await flow_http.close_workers()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["x"]), 200000)

    async def test_stale_worker_response_of_cancelled_call_is_discarded(self):
        import sys
        import flow_http

        real_exec = asyncio.create_subprocess_exec
        script = ("import json,sys; r=json.loads(sys.stdin.readline()); "
                  "print(json.dumps({'status':'stale','request_id':'antigo'})); "
                  "print(json.dumps({'status':'ok','request_id':r['id']}), flush=True)")

        async def fake_exec(*args, **kwargs):
            return await real_exec(sys.executable, "-c", script, **kwargs)

        with patch("asyncio.create_subprocess_exec", fake_exec):
            try:
                result = await flow_http.run_worker_operation("conta-defasada", "credits", {}, None, None)
            finally:
                await flow_http.close_workers()
        self.assertEqual(result, {"status": "ok"})

    async def test_busy_account_answers_instead_of_hanging(self):
        import flow_http

        lock = flow_http._locks.setdefault("conta-ocupada", asyncio.Lock())
        await lock.acquire()
        flow_http._running["conta-ocupada"] = ("generate", asyncio.get_running_loop().time())
        try:
            with patch.object(flow_http, "BUSY_GRACE_SECONDS", 0.05):
                result = await flow_http.run_worker_operation("conta-ocupada", "credits", {}, None, None)
        finally:
            lock.release()
            flow_http._running.pop("conta-ocupada", None)
        self.assertEqual(result["status"], "account_busy")
        self.assertEqual(result["running_action"], "generate")
        self.assertIn("nada foi enviado", result["message"])

    def test_worker_timeout_scales_with_batches(self):
        from flow_http import worker_timeout

        self.assertEqual(worker_timeout("credits", {}), 240)
        self.assertEqual(worker_timeout("generate", {}), 1260)
        self.assertEqual(worker_timeout("edit_images", {"media_ids": ["a", "b"]}), 2520)
        self.assertEqual(worker_timeout("refine_video", {"refinements": ["a"] * 5}), 3780)
        self.assertEqual(worker_timeout("manage_character", {"description": "x"}), 1260)


class SessionRefreshTest(unittest.IsolatedAsyncioTestCase):
    def client(self, codes):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from flow_http import FlowHTTP

        client = FlowHTTP("conta-a")
        client.templates["UpteDb"] = {"url": "https://flow.google.com/_/Ui/data/batchexecute?rpcids=UpteDb",
                                      "call": ["UpteDb", "[]", None, "generic"], "form": {}, "headers": {}}
        client.templates["Zzl0ze"] = dict(client.templates["UpteDb"])
        replies = iter(SimpleNamespace(status_code=code, text="frames") for code in codes)
        client.client = SimpleNamespace(post=AsyncMock(side_effect=lambda *a, **k: next(replies)))
        client.refresh_session = AsyncMock()
        return client

    async def test_read_rpc_refreshes_cookies_once_and_retries(self):
        client = self.client([401, 200])
        with patch("gflow_cli.api.transports.batchexecute.parse_frames", return_value=[("Zzl0ze", [1])]):
            self.assertEqual(await client.rpc("Zzl0ze"), [1])
        client.refresh_session.assert_awaited_once()

    async def test_mutation_is_never_retried(self):
        client = self.client([401, 200])
        with self.assertRaises(ValueError) as ctx:
            await client.rpc("jHPbke", params=["projects/*"])
        self.assertIn("401", str(ctx.exception))
        client.refresh_session.assert_not_awaited()
        self.assertEqual(client.client.post.await_count, 1)

    async def test_persistent_failure_explains_login(self):
        client = self.client([401, 401])
        with self.assertRaises(ValueError) as ctx:
            await client.rpc("Zzl0ze")
        self.assertIn("login", str(ctx.exception))
        client.refresh_session.assert_awaited_once()

    def test_login_redirect_is_reported(self):
        from types import SimpleNamespace
        from flow_http import require_flow_page

        require_flow_page(SimpleNamespace(url="https://flow.google.com/project/x"))
        for url in ("https://accounts.google.com/signin", "https://flow.google.com/about"):
            with self.assertRaises(ValueError):
                require_flow_page(SimpleNamespace(url=url))

    async def test_idle_worker_releases_chrome_and_keeps_serving(self):
        import flow_http

        clients = []

        class Client:
            def __init__(self, *args, **kwargs):
                self.account_id, self.pending_upload = "conta-a", None
                self.browser = type("Browser", (), {"context": object()})()
                self.closed = False
                clients.append(self)

            async def close(self):
                self.closed = True

        class SlowInput:
            lines = iter(['{"action":"credits","payload":{}}\n', ""])

            def readline(self, limit):
                import time
                time.sleep(0.3)
                return next(self.lines)

        out = io.StringIO()
        with patch.object(flow_http, "FlowHTTP", Client), patch.object(flow_http, "WORKER_IDLE_SECONDS", 0.1), \
                patch.object(flow_http, "http_operation", AsyncMock(return_value={"status": "ok"})):
            await flow_http.worker("conta-a", SlowInput(), out)
        self.assertEqual(json.loads(out.getvalue())["status"], "ok")
        self.assertTrue(clients[0].closed)  # Chrome ocioso fechado antes do pedido
        self.assertTrue(clients[-1].closed)  # e o último ao encerrar o worker


if __name__ == "__main__":
    unittest.main()
