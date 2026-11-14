from uuid import uuid4
from .broker import PolicyDenied,StaleReview
from .config import digest
from .store import now
from .ops import assess


def activate(service,rid,target="canary"):
    """Local canary manifest activation only. Never installs code or expands rights."""
    if target!="canary":raise PolicyDenied("ONLY_LOCAL_CANARY_SUPPORTED")
    with service.store.lock:
        candidate=service.store.get("manifest",rid)
        if not candidate:raise StaleReview("MANIFEST_NOT_FOUND")
        if digest(candidate)!=digest(service.manifest):raise StaleReview("RESTART_WITH_MATCHING_CODE_AND_CONFIG_REQUIRED")
        release,_,_=assess(service.store,service.config,service.telemetry,rid)
        if release['decision']!='READY_FOR_APPROVAL' or any(g['status']!='PASS' for g in release['gates']):raise StaleReview('RELEASE_GATES_NOT_ALL_PASS')
        previous=service.store.get('deployment',target)
        record={'id':target,'releaseId':rid,'manifestHash':digest(candidate),'previous':previous,'actor':'local-human','at':now(),'scope':'local-manifest-only'}
        audit_id='deploy-'+uuid4().hex
        with service.store.engine.begin() as connection:
            service.store.put('deployment',target,record,connection)
            service.store.put('deployment-audit',audit_id,record,connection)
            release.update(state='promoted');service.store.put('release',rid,release,connection)
        return {'id':rid,'target':target,'state':'promoted','scope':'local-manifest-only'}


def rollback(service,target="canary"):
    with service.store.lock:
        current=service.store.get('deployment',target)
        previous=(current or {}).get('previous')
        if not previous:raise StaleReview('NO_PREVIOUS_APPROVED_MANIFEST')
        manifest=service.store.get('manifest',previous['releaseId'])
        if not manifest or digest(manifest)!=previous['manifestHash']:raise StaleReview('ROLLBACK_MANIFEST_HASH_MISMATCH')
        if digest(manifest)!=digest(service.manifest):raise StaleReview('RESTART_WITH_PREVIOUS_CODE_AND_CONFIG_REQUIRED')
        record={**previous,'actor':'local-human','at':now(),'rollbackFrom':current['releaseId']}
        with service.store.engine.begin() as connection:
            service.store.put('deployment',target,record,connection)
            service.store.put('deployment-audit','rollback-'+uuid4().hex,record,connection)
        return {'id':previous['releaseId'],'target':target,'state':'rolled_back','scope':'local-manifest-only'}
