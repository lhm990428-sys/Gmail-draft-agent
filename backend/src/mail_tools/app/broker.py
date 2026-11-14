from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
import base64
import hashlib
import hmac
import json
import time
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
import httplib2
from mail_tools.secrets import get_secret, put_secret
from .config import digest

READ = "https://www.googleapis.com/auth/gmail.readonly"
COMPOSE = "https://www.googleapis.com/auth/gmail.compose"


class PolicyDenied(Exception): pass
class StaleReview(Exception): pass
class UncertainWrite(Exception): pass


def approval_signature(key: bytes, approval: dict) -> str:
    return hmac.new(key, json.dumps(approval, sort_keys=True).encode(), hashlib.sha256).hexdigest()


def verify_approval(key: bytes, approval: dict, signature: str, mail: dict):
    if not hmac.compare_digest(approval_signature(key, approval), signature): raise PolicyDenied("APPROVAL_SIGNATURE_INVALID")
    if approval["expires"] < time.time() or approval["actor"] != "local-human": raise PolicyDenied("APPROVAL_EXPIRED_OR_ACTOR")
    expected = {"mail_id": mail["id"], "revision": mail["revision"], "draft_hash": digest(mail["draftBody"]), "recipient_hash": digest(mail["address"]), "message_id": mail["latestMessageId"]}
    if any(approval.get(k) != v for k,v in expected.items()): raise StaleReview("APPROVAL_SNAPSHOT_CHANGED")


class GmailBroker:
    def __init__(self, config, approval_key: bytes): self.config, self.approval_key = config, approval_key
    def _service(self, write=False):
        token = get_secret("gmail-oauth-token")
        if not token: raise PolicyDenied("GMAIL_AUTH_REQUIRED")
        info = json.loads(token)
        scopes = set(info.get("scopes", []))
        if info.get("token_uri") != "https://oauth2.googleapis.com/token" or not scopes <= {READ,COMPOSE} or READ not in scopes:
            raise PolicyDenied("UNAPPROVED_OAUTH_SCOPE")
        if write and (not self.config.allow_gmail_draft_write or COMPOSE not in scopes): raise PolicyDenied("COMPOSE_CONSENT_AND_WRITE_POLICY_REQUIRED")
        creds = Credentials.from_authorized_user_info(info, list(scopes))
        if not creds.valid:
            from functools import partial
            creds.refresh(partial(Request(), timeout=15))
            put_secret("gmail-oauth-token", creds.to_json())
        return build("gmail", "v1", http=AuthorizedHttp(creds, http=httplib2.Http(timeout=15)), cache_discovery=False)

    def read_test_thread(self):
        if not self.config.allow_real_mail_export: raise PolicyDenied("REAL_MAIL_EXPORT_NOT_APPROVED")
        service = self._service()
        try:
            found = service.users().threads().list(userId="me", q="label:"+self.config.label, maxResults=1).execute(num_retries=0).get("threads", [])
            if not found: raise PolicyDenied("NO_MAIL_IN_APPROVED_TEST_LABEL")
            thread = service.users().threads().get(userId="me", id=found[0]["id"], format="full").execute(num_retries=0)
            messages = thread.get("messages", [])
            if not messages: raise PolicyDenied("EMPTY_GMAIL_THREAD")
            last = messages[-1]
            headers = {x["name"].lower():x["value"] for x in last.get("payload",{}).get("headers",[])}
            sender, address = parseaddr(headers.get("reply-to",headers.get("from","")))
            def body(part):
                if part.get("mimeType")=="text/plain" and part.get("body",{}).get("data"):
                    return base64.urlsafe_b64decode(part["body"]["data"]+"==").decode("utf-8", errors="replace")
                return "\n".join(filter(None,(body(child) for child in part.get("parts",[]))))
            text = "\n\n".join(body(x.get("payload",{})) for x in messages)
            if not text.strip() or len(text)>16000: raise PolicyDenied("PLAIN_TEXT_OR_SIZE_POLICY")
            if not address or "\n" in address or "\r" in address: raise PolicyDenied("INVALID_REPLY_RECIPIENT")
            return {"source":"gmail","threadId":thread["id"],"latestMessageId":last["id"],"rfcMessageId":headers.get("message-id",""),"references":headers.get("references",""), "sender":sender or address,"address":address,"subject":headers.get("subject","(제목 없음)"),"originalBody":text,"receivedAt":datetime.fromtimestamp(int(last["internalDate"])/1000,timezone.utc).isoformat()}
        finally: service.close()

    def recent_page(self,since,until,page_token=None):
        if not self.config.allow_real_mail_export:raise PolicyDenied("REAL_MAIL_EXPORT_NOT_APPROVED")
        service=self._service()
        try:
            response=service.users().messages().list(userId="me",q=f"in:inbox after:{int(since)-1} before:{int(until)+1}",labelIds=["INBOX"],maxResults=20,pageToken=page_token,includeSpamTrash=False).execute(num_retries=0)
            items=[]
            for message in response.get("messages",[]):
                if getattr(self,"stop_event",None) is not None and self.stop_event.is_set():raise PolicyDenied("COLLECTOR_STOPPING")
                item=service.users().messages().get(userId="me",id=message["id"],format="metadata",metadataHeaders=["From","Reply-To","Subject","List-Unsubscribe","Precedence","Auto-Submitted"]).execute(num_retries=0)
                received=int(item.get("internalDate",0))/1000
                if not since<=received<=until or "INBOX" not in item.get("labelIds",[]):continue
                headers={x["name"].lower():x["value"] for x in item.get("payload",{}).get("headers",[])}
                sender,address=parseaddr(headers.get("from",""))
                excluded="CATEGORY_PROMOTIONS" in item.get("labelIds",[]) and (bool(headers.get("list-unsubscribe")) or headers.get("precedence","").lower() in ("bulk","list"))
                items.append({"messageId":item["id"],"threadId":item["threadId"],"sender":sender or address,"address":address,"subject":headers.get("subject","(제목 없음)"),"receivedAt":datetime.fromtimestamp(received,timezone.utc).isoformat(),"reason":"프로모션 라벨 + 대량발송 헤더" if excluded else None})
            return items,response.get("nextPageToken")
        finally:service.close()

    def read_message(self,message_id,since):
        if not self.config.allow_real_mail_export:raise PolicyDenied("REAL_MAIL_EXPORT_NOT_APPROVED")
        service=self._service()
        try:
            item=service.users().messages().get(userId="me",id=message_id,format="full").execute(num_retries=0)
            if "INBOX" not in item.get("labelIds",[]) or int(item.get("internalDate",0))/1000<since:raise PolicyDenied("MESSAGE_OUTSIDE_RECENT_INBOX")
            headers={x["name"].lower():x["value"] for x in item.get("payload",{}).get("headers",[])}
            thread=service.users().threads().get(userId="me",id=item["threadId"],format="metadata",metadataHeaders=["From"]).execute(num_retries=0)
            later=[m for m in thread.get("messages",[]) if int(m.get("internalDate",0))>int(item["internalDate"])]
            newest=max(later,key=lambda m:int(m.get("internalDate",0)),default=None)
            already_replied=bool(newest and "SENT" in newest.get("labelIds",[]) and "INBOX" not in newest.get("labelIds",[]))
            superseded=any("INBOX" in m.get("labelIds",[]) for m in later)
            sender,address=parseaddr(headers.get("reply-to",headers.get("from","")))
            def extract(part,mime):
                if part.get("mimeType")==mime and part.get("body",{}).get("data"):
                    return base64.urlsafe_b64decode(part["body"]["data"]+"==").decode("utf-8",errors="replace")
                return "\n".join(filter(None,(extract(child,mime) for child in part.get("parts",[]))))
            text=extract(item.get("payload",{}),"text/plain")
            if not text.strip():
                from html.parser import HTMLParser
                class Plain(HTMLParser):
                    def __init__(self):super().__init__();self.values=[];self.skip=0
                    def handle_starttag(self,tag,attrs):
                        if tag in ("style","script"):self.skip+=1
                        elif tag in ("br","p","div","tr"):self.values.append("\n")
                    def handle_endtag(self,tag):
                        if tag in ("style","script"):self.skip=max(0,self.skip-1)
                    def handle_data(self,data):
                        if not self.skip:self.values.append(data)
                parser=Plain();parser.feed(extract(item.get("payload",{}),"text/html"));text="".join(parser.values)
            if not address or "\r" in address or "\n" in address:raise PolicyDenied("INVALID_REPLY_RECIPIENT")
            # Do not silently classify incomplete/oversized content.
            limited=not text.strip() or len(text.encode("utf-8"))>12000
            return {"source":"gmail","threadId":item["threadId"],"latestMessageId":item["id"],"rfcMessageId":headers.get("message-id",""),"references":headers.get("references",""),"sender":sender or address,"address":address,"subject":headers.get("subject","(제목 없음)"),"originalBody":text[:12000],"receivedAt":datetime.fromtimestamp(int(item["internalDate"])/1000,timezone.utc).isoformat(),"contentLimited":limited,"alreadyReplied":already_replied,"superseded":superseded}
        finally:service.close()

    def latest(self, mail):
        service = self._service()
        try:
            thread = service.users().threads().get(userId="me", id=mail["threadId"], format="minimal", fields="messages(id)").execute(num_retries=0)
            return thread["messages"][-1]["id"]
        finally: service.close()

    def preflight(self, mail):
        service = self._service(write=True)
        service.close()
        if self.latest(mail) != mail["latestMessageId"]: raise StaleReview("THREAD_CHANGED_REVIEW_REQUIRED")

    def create_draft(self, mail, approval, signature, intent_id):
        verify_approval(self.approval_key, approval, signature, mail)
        # Recheck immediately before writing; approval cannot authorize a newer reply.
        if self.latest(mail) != mail["latestMessageId"]:
            raise StaleReview("THREAD_CHANGED_REVIEW_REQUIRED")
        service = self._service(write=True)
        message = EmailMessage()
        message["To"] = mail["address"]
        message["Subject"] = mail["subject"] if mail["subject"].lower().startswith("re:") else "Re: "+mail["subject"]
        if mail.get("rfcMessageId"):
            message["In-Reply-To"] = mail["rfcMessageId"]
            message["References"] = (mail.get("references","")+" "+mail["rfcMessageId"]).strip()
        message["X-Hermes-Intent"] = intent_id
        message.set_content(mail["draftBody"])
        try:
            # This is the only external write exposed. No send/delete/modify method.
            return service.users().drafts().create(userId="me", body={"message":{"threadId":mail["threadId"],"raw":base64.urlsafe_b64encode(message.as_bytes()).decode()}}).execute(num_retries=0)["id"]
        except Exception:
            raise UncertainWrite("DRAFT_RESULT_UNKNOWN_RECONCILE_REQUIRED") from None
        finally: service.close()

    def reconcile(self, mail, intent_id):
        service = self._service()
        try:
            page, matches = None, []
            for _ in range(10):
                result = service.users().drafts().list(userId="me", maxResults=100, pageToken=page).execute(num_retries=0)
                for entry in result.get("drafts",[]):
                    if entry.get("message",{}).get("threadId") != mail["threadId"]: continue
                    item = service.users().drafts().get(userId="me", id=entry["id"], format="metadata").execute(num_retries=0)
                    headers = item.get("message",{}).get("payload",{}).get("headers",[])
                    if any(h["name"].lower()=="x-hermes-intent" and h["value"]==intent_id for h in headers): matches.append(entry["id"])
                page = result.get("nextPageToken")
                if not page: break
            if len(matches)==1: return matches[0]
            raise UncertainWrite("NO_UNIQUE_DRAFT_MATCH_DO_NOT_RETRY_CREATE")
        finally: service.close()


class FixtureBroker:
    def __init__(self, store, approval_key): self.store,self.approval_key = store,approval_key
    def latest(self, mail): return mail["latestMessageId"]
    def preflight(self, mail): pass
    def create_draft(self, mail, approval, signature, intent_id):
        verify_approval(self.approval_key, approval, signature, mail)
        identifier = "local-draft-"+intent_id
        self.store.put("local-draft",identifier,{"id":identifier,"body":mail["draftBody"],"intent":intent_id})
        return identifier
    def reconcile(self, mail, intent_id):
        identifier = "local-draft-"+intent_id
        if self.store.get("local-draft",identifier): return identifier
        raise UncertainWrite("LOCAL_DRAFT_NOT_CONFIRMED")


def fixture_mail(kind="reply"):
    return {"source":"fixture","threadId":"fixture-thread","latestMessageId":"fixture-message-1","sender":"스터디 테스트","address":"study@example.test","subject":"Newsletter" if kind=="newsletter" else "스터디 자료 수신 확인 요청","originalBody":"이번 주 소식을 공유합니다. 자동 발송 뉴스레터입니다." if kind=="newsletter" else "안녕하세요. 스터디 자료를 공유드립니다. 메일 수신 여부를 알려주시고, 다음 주 참석 가능 여부도 확인 후 회신 부탁드립니다. 첨부 자료의 내용은 아직 확인되지 않았습니다.","receivedAt":datetime.now(timezone.utc).isoformat()}
