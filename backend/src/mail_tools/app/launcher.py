import base64
import secrets
import threading
import webbrowser
from cryptography.fernet import Fernet
from mail_tools.secrets import get_secret, put_secret
from .config import config
from .service import Service
from .server import create_app


def stored_key(name,create):
    value=get_secret(name)
    if value is None:
        value=create();put_secret(name,value)
    return value


def local_service():
    settings=config()
    from mail_tools.settings import ROOT
    if not settings.database_dir.resolve().is_relative_to((ROOT/".local").resolve()):
        raise ValueError("Database directory must stay inside project .local")
    key=stored_key("artifact-encryption-key",lambda:Fernet.generate_key().decode()).encode()
    approval=stored_key("console-session-key",lambda:secrets.token_urlsafe(32)).encode()
    return Service(settings,key,approval)


def serve(open_browser=False,with_gateway=False):
    import uvicorn
    service=local_service()
    token=secrets.token_urlsafe(40)
    gateway_key=stored_key("hermes-command-key",lambda:secrets.token_urlsafe(32))
    application=create_app(service,token,gateway_key=gateway_key)
    gateway=None
    try:
        if with_gateway:
            from .gateway import HermesGateway
            gateway=HermesGateway(gateway_key);gateway.start()
        if open_browser:
            timer=threading.Timer(2,lambda:webbrowser.open("http://127.0.0.1:8000/#console="+token))
            timer.daemon=True;timer.start()
        print("Hermes local console: http://127.0.0.1:8000/ (loopback, development)")
        uvicorn.run(application,host="127.0.0.1",port=8000,access_log=False,log_level="warning")
    finally:
        if gateway: gateway.close()
        service.close()
