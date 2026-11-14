"""Hermes slash command adapter. Fixed endpoint, narrow commands, no shell."""
import json
import os
from http.client import HTTPConnection
from uuid import uuid4


def command(raw_args: str):
    arguments=raw_args.strip().split()
    if not arguments or arguments[0] not in ("run","status"):
        return "Usage: /mail-runtime run | /mail-runtime status [run-id]. Synthetic input only; approval stays in local console."
    if len(arguments)>2 or arguments[0]=="run" and len(arguments)!=1:
        return "Unsupported command arguments."
    if len(arguments)==2 and (not arguments[1].startswith("run-") or len(arguments[1])>80 or not all(c.isalnum() or c=='-' for c in arguments[1])):
        return "Invalid run identifier."
    key=os.environ.get("HERMES_MAIL_COMMAND_KEY","")
    if not key: return "Local runtime bridge is not configured."
    payload={"command":arguments[0],"run_id":arguments[1] if len(arguments)==2 else None,"request_id":str(uuid4())}
    connection=HTTPConnection("127.0.0.1",8000,timeout=10)
    try:
        connection.request("POST","/api/v1/gateway/command",body=json.dumps(payload).encode(),headers={"Content-Type":"application/json","Authorization":"Bearer "+key})
        response=connection.getresponse()
        if response.status!=200:return json.dumps({"status":"unavailable","http_status":response.status})
        result=json.loads(response.read(20000))
        return json.dumps(result,ensure_ascii=False)
    except Exception as error:
        return json.dumps({"status":"unavailable","category":type(error).__name__})
    finally: connection.close()


def register(ctx):
    ctx.register_command("mail-runtime",handler=command,description="Start/inspect the constrained local LangGraph workflow. Human approval remains in the console.")
    def wire(application,adapter):
        import asyncio
        import hmac
        from aiohttp import web
        async def ingress(request):
            key=os.environ.get("API_SERVER_KEY","")
            token=request.headers.get("Authorization","").removeprefix("Bearer ")
            if not key or not hmac.compare_digest(token,key):return web.json_response({"error":"unauthorized"},status=403)
            if request.content_length is None or request.content_length>1024:return web.json_response({"error":"body_size"},status=400)
            payload=await request.json()
            text=payload.get("command","")
            if not isinstance(text,str) or len(text)>120:return web.json_response({"error":"invalid_command"},status=400)
            value=await asyncio.to_thread(command,text.removeprefix("/mail-runtime").strip())
            try:result=json.loads(value)
            except ValueError:result={"help":value}
            return web.json_response(result)
        application.router.add_post("/hermes-mail-runtime/command",ingress)
    ctx.register_platform_handler("api_server",wire)
