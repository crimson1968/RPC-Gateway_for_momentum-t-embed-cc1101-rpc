"""Bounded SD-card access through the existing firmware WebFS routes."""
import asyncio
import json
from urllib.parse import quote
import httpx
from mcp.server.fastmcp.exceptions import ToolError

MAX_FILE = 2 * 1024 * 1024

def sd_path(value):
    if not isinstance(value,str) or not (value == '/ext' or value.startswith('/ext/')) or '..' in value or '\\' in value or any(ord(c)<32 for c in value):
        raise ToolError('invalid_path: only /ext paths without traversal are allowed')
    if len(value.encode()) > 255 or len(quote(value, safe='')) > 280:
        raise ToolError('invalid_path: path is too long for firmware WebFS')
    return value

class WebFiles:
    def __init__(self,device): self.device=device
    async def call(self,method,route,params,content=None):
        try:
            async with asyncio.timeout(30):
                async with httpx.AsyncClient(base_url=self.device.base_url,transport=self.device.transport,timeout=10,trust_env=False,follow_redirects=False) as client:
                    async with client.stream(method,'/api/'+route,params=params,content=content) as r:
                        if r.status_code!=200: raise ToolError('webfs_error: HTTP '+str(r.status_code))
                        data=bytearray()
                        async for chunk in r.aiter_bytes():
                            data.extend(chunk)
                            if len(data)>MAX_FILE: raise ToolError('webfs_limit: response exceeds 2 MiB')
                        return bytes(data)
        except (httpx.RequestError,TimeoutError) as exc:
            raise ToolError('webfs_timeout: operation may be incomplete; inspect files before retrying') from exc
    async def list(self,path='/ext'):
        path=sd_path(path)
        raw=await self.call('GET','list',{'path':path})
        try:
            data=json.loads(raw)
            if not isinstance(data,dict) or data.get('path')!=path or not isinstance(data.get('entries'),list): raise ValueError()
            for e in data['entries']:
                if not isinstance(e,dict) or not isinstance(e.get('name'),str) or '/' in e['name'] or '\\' in e['name'] or type(e.get('dir')) is not bool or type(e.get('size')) is not int: raise ValueError()
            return data
        except (ValueError,TypeError) as exc: raise ToolError('invalid_response: malformed WebFS listing') from exc
    async def download(self,path): return await self.call('GET','download',{'path':sd_path(path)})
    async def mutate(self,operation,path,new_path=None,content=None):
        path=sd_path(path)
        if path=='/ext': raise ToolError('invalid_path: cannot modify SD root')
        if operation not in ('upload','rename','mkdir','delete'): raise ToolError('invalid_operation')
        if content is not None and len(content)>MAX_FILE: raise ToolError('webfs_limit: maximum upload 2 MiB')
        params={'path':path}
        if operation=='rename':
            target=sd_path(new_path)
            if target=='/ext': raise ToolError('invalid_path: cannot replace SD root')
            params={'old':path,'new':target}
        result=await self.call('POST',operation,params,content)
        if result.strip()!=b'ok': raise ToolError('invalid_response: WebFS did not acknowledge operation')
        return {'ok':True}
