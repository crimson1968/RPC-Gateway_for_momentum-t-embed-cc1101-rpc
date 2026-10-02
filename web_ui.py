"""Small browser UI sharing the Device instance and RX lock with MCP."""
import asyncio
import base64
from web_files import WebFiles, MAX_FILE
from usb_remote import UsbRemote
import json
from pathlib import Path
from functools import wraps

from mcp.server.fastmcp.exceptions import ToolError
from starlette.responses import HTMLResponse, JSONResponse, Response


def register_ui(server, device, hosts):
    files = WebFiles(device)
    usb = server.tembed_usb
    allowed = set(hosts)
    page = Path(__file__).with_name('web.html').read_text(encoding='utf-8')

    def guarded(fn):
        @wraps(fn)
        async def wrapper(request):
            host = request.headers.get('host', '')
            origin = request.headers.get('origin')
            if host not in allowed or (origin and origin not in {f'http://{host}', f'https://{host}'}):
                return JSONResponse({'error': 'Host or origin is not allowed.'}, status_code=403)
            if request.method == 'POST' and (
                request.headers.get('x-tembed-ui') != '1' or
                request.headers.get('content-type', '').split(';')[0] != 'application/json'
            ):
                return JSONResponse({'error': 'JSON and the UI header are required.'}, status_code=403)
            try:
                response = await fn(request)
            except ToolError as exc:
                message = str(exc)
                code = 409 if message.startswith('busy:') else 404 if message.startswith('not_found:') else 400 if message.startswith(('invalid_frequency:', 'invalid_duration:', 'invalid_job_id:')) else 502
                response = JSONResponse({'error': message}, status_code=code)
            except (ValueError, TypeError, TimeoutError):
                response = JSONResponse({'error': 'The request is invalid or too large.'}, status_code=400)
            response.headers['Cache-Control'] = 'no-store'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['Content-Security-Policy'] = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
            return response
        return wrapper

    @server.custom_route('/', methods=['GET'])
    @guarded
    async def index(request):
        return HTMLResponse(page)

    @server.custom_route('/ui/api/status', methods=['GET'])
    @guarded
    async def status(request):
        return JSONResponse((await device.status()).model_dump())

    @server.custom_route('/ui/api/capabilities', methods=['GET'])
    @guarded
    async def capabilities(request):
        return JSONResponse((await device.capabilities()).model_dump())

    @server.custom_route('/ui/api/settings', methods=['GET'])
    @guarded
    async def settings(request):
        return JSONResponse((await device.settings()).model_dump())

    @server.custom_route('/ui/api/diagnostics', methods=['GET'])
    @guarded
    async def diagnostics(request):
        return JSONResponse((await device.diagnostics()).model_dump())

    @server.custom_route('/ui/api/jobs', methods=['GET'])
    @guarded
    async def jobs(request):
        return JSONResponse((await device.jobs()).model_dump())

    @server.custom_route('/ui/api/jobs/{job_id:int}', methods=['GET'])
    @guarded
    async def job(request):
        return JSONResponse((await device.job(request.path_params['job_id'])).model_dump())

    @server.custom_route('/ui/api/jobs/{job_id:int}/cancel', methods=['POST'])
    @guarded
    async def job_cancel(request):
        return JSONResponse(
            (await device.cancel_job(request.path_params['job_id'])).model_dump(),
            status_code=202,
        )

    @server.custom_route('/ui/api/rx', methods=['POST'])
    @guarded
    async def rx(request):
        body = bytearray()
        async with asyncio.timeout(5):
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 1024:
                    raise ValueError('body too large')
        data = json.loads(body)
        if not isinstance(data, dict) or set(data) != {'frequency_hz', 'duration_ms'}:
            raise ValueError('invalid fields')
        return JSONResponse((await device.start_rx(data['frequency_hz'], data['duration_ms'])).model_dump(), status_code=202)

    @server.custom_route('/ui/api/files', methods=['GET'])
    @guarded
    async def files_list(request):
        return JSONResponse(await files.list(request.query_params.get('path','/ext')))

    @server.custom_route('/ui/api/file', methods=['GET'])
    @guarded
    async def files_download(request):
        data = await files.download(request.query_params.get('path',''))
        return Response(data, media_type='application/octet-stream', headers={'Content-Disposition':'attachment; filename="tembed-file.bin"'})

    @server.custom_route('/ui/api/files', methods=['POST'])
    @guarded
    async def files_modify(request):
        body = bytearray()
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_FILE * 2: raise ValueError('body too large')
        data = json.loads(body)
        if not isinstance(data,dict) or set(data)-{'operation','path','new_path','content_base64'}: raise ValueError('invalid fields')
        operation = data.get('operation')
        content = None
        if operation == 'upload':
            encoded = data.get('content_base64')
            if not isinstance(encoded,str): raise ValueError('content missing')
            content = base64.b64decode(encoded,validate=True)
        return JSONResponse(await files.mutate(operation,data.get('path'),data.get('new_path'),content))

    @server.custom_route('/ui/api/usb', methods=['GET'])
    @guarded
    async def usb_status(request):
        return JSONResponse(usb.snapshot())

    @server.custom_route('/ui/api/usb', methods=['POST'])
    @guarded
    async def usb_action(request):
        body = bytearray()
        async with asyncio.timeout(5):
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>1024: raise ValueError('body too large')
        data=json.loads(body)
        if not isinstance(data,dict): raise ValueError('invalid action')
        action=data.get('action')
        if action=='connect' and set(data)=={'action'}:
            return JSONResponse(await asyncio.to_thread(usb.connect))
        if action=='disconnect' and set(data)=={'action'}:
            return JSONResponse(await asyncio.to_thread(usb.close))
        if action=='key' and set(data)<= {'action','key','long'}:
            return JSONResponse(await asyncio.to_thread(usb.key,data.get('key'),data.get('long',False)))
        raise ValueError('invalid action')
