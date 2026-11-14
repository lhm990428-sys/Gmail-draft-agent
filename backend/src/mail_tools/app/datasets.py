import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from .config import digest


class Case(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    subject:str=Field(min_length=1,max_length=500)
    body:str=Field(min_length=1,max_length=16000)
    reference:Literal['REPLY_REQUIRED','NO_REPLY','REVIEW_REQUIRED']
    requests:str=Field(min_length=1,max_length=2000)
    risk:bool=False


class Corpus(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    split:Literal['dev','holdout']='dev'
    source:Literal['synthetic']
    cases:list[Case]=Field(min_length=1,max_length=500)


def import_dataset(store,path:Path):
    if path.stat().st_size>12_000_000:raise ValueError('DATASET_FILE_TOO_LARGE')
    corpus=Corpus.model_validate_json(path.read_text(encoding='utf-8-sig'))
    cases=[c.model_dump() for c in corpus.cases]
    if len({c['id'] for c in cases})!=len(cases):raise ValueError('DUPLICATE_CASE_ID')
    identifier=corpus.name+'@'+digest(corpus.model_dump())[:20]
    value={'id':identifier,'digest':digest(cases),'cases':cases,'source':'synthetic','split':corpus.split,'purpose':'locked_evaluation','locked':True}
    old=store.get('dataset',identifier)
    if old and old!=value:raise ValueError('LOCKED_DATASET_CANNOT_CHANGE')
    store.put('dataset',identifier,value)
    return {'id':identifier,'count':len(cases),'split':corpus.split,'locked':True}
