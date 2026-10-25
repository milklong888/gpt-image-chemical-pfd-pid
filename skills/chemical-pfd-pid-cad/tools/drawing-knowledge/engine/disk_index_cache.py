"""LlamaIndex IngestionCache with an unbounded durable per-collection Index.

No embedding/model or retrieval algorithm is implemented here. Existing exact
model+indexed-text digest keys and official node JSON values remain unchanged.
"""
from pathlib import Path
import hashlib
import json
import re
import ijson
from diskcache import Index
from llama_index.core.storage.kvstore.types import MutableMappingKVStore
from llama_index.core.ingestion import IngestionCache


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


class DiskIndexKVStore(MutableMappingKVStore):
    def __init__(self, directory):
        super().__init__(mapping_factory=dict)
        self.directory=Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)

    def _get_collection_mapping(self, collection):
        if collection not in self._collections_mappings:
            # The full digest prevents collection collisions/path traversal.
            child=self.directory/('collection-'+hashlib.sha256(collection.encode('utf8')).hexdigest())
            self._collections_mappings[collection]=Index(str(child))
            if self._collections_mappings[collection].cache.eviction_policy != 'none':
                raise ValueError('DISK_INDEX_UNEXPECTED_EVICTION_POLICY')
        return self._collections_mappings[collection]

    def close(self):
        for mapping in self._collections_mappings.values():
            mapping.cache.close()
        self._collections_mappings.clear()

    def counts(self):
        return {name:len(mapping) for name,mapping in self._collections_mappings.items()}


def migrate_simple_cache(seed_json, store):
    """Stream old SimpleKVStore collections and every value without whole-file load.

    Idempotent after interruption: existing same keys must have identical JSON
    values. SQLite writes are durable; completion marker is committed last.
    """
    seed_json=Path(seed_json)
    marker=store.directory/'seed-migration.json'
    seed_sha=sha(seed_json)
    if marker.exists():
        previous=json.loads(marker.read_text('utf8'))
        if previous['seed_sha256'] != seed_sha:
            raise ValueError('DISK_CACHE_SEED_CHANGED_AFTER_MIGRATION')
        for name,count in previous['collection_counts'].items():
            if len(store._get_collection_mapping(name)) < count:
                raise ValueError('DISK_CACHE_SEED_ENTRIES_MISSING')
        return previous
    collections=[]
    with seed_json.open('rb') as f:
        for prefix,event,value in ijson.parse(f,use_float=True):
            if prefix=='' and event=='map_key':
                if not re.fullmatch(r'[A-Za-z0-9_-]+',value):
                    raise ValueError('UNSUPPORTED_CACHE_COLLECTION_NAME')
                collections.append(value)
    counts={}
    for name in collections:
        mapping=store._get_collection_mapping(name)
        count=0
        with seed_json.open('rb') as f:
            for key,value in ijson.kvitems(f,name,use_float=True):
                if key in mapping:
                    if mapping[key] != value:
                        raise ValueError('DISK_CACHE_EXISTING_KEY_VALUE_MISMATCH: '+name+':'+key)
                else:
                    mapping[key]=value
                count+=1
        counts[name]=count
    if sha(seed_json) != seed_sha:
        raise ValueError('DISK_CACHE_SEED_CHANGED_DURING_MIGRATION')
    receipt={'seed_path':str(seed_json.resolve()),'seed_sha256':seed_sha,
             'collection_counts':counts,'complete':True,'values_truncated':False,
             'backend':'LlamaIndex MutableMappingKVStore + diskcache.Index; eviction_policy=none'}
    tmp=marker.with_name(marker.name+'.tmp')
    tmp.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),'utf8');tmp.replace(marker)
    return receipt


def open_ingestion_cache(directory,seed_json=None):
    store=DiskIndexKVStore(directory)
    try:
        receipt=migrate_simple_cache(seed_json,store) if seed_json and Path(seed_json).exists() else None
        return IngestionCache(cache=store),store,receipt
    except BaseException:
        store.close()
        raise
