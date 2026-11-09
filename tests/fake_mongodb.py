"""
In-Memory Async MongoDB Fake for Deterministic Unit & Integration Testing.

Implements the subset of PyMongo AsyncMongoClient / AsyncDatabase / AsyncCollection
used by EdgeMind, providing:
- True async coroutine interfaces.
- In-memory document storage with deep copying.
- Unique index constraint enforcement (DuplicateKeyError).
- Filtering, sorting (ASCENDING / DESCENDING), skip, limit, and to_list.
- update_one with $set, $setOnInsert, and upsert=True.
- Connection ping and simulated offline states.
"""

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError


class InsertOneResult:
    def __init__(self, inserted_id: ObjectId):
        self.inserted_id = inserted_id


class UpdateResult:
    def __init__(self, matched_count: int, modified_count: int, upserted_id: Optional[ObjectId] = None):
        self.matched_count = matched_count
        self.modified_count = modified_count
        self.upserted_id = upserted_id


class DeleteResult:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count


class FakeAsyncCursor:
    """Async cursor simulating PyMongo find() results with sort, skip, limit, and to_list."""

    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = list(docs)
        self._skip = 0
        self._limit: Optional[int] = None
        self._sort_key: Optional[str] = None
        self._sort_dir: int = ASCENDING

    def sort(self, key: str, direction: int = ASCENDING) -> "FakeAsyncCursor":
        self._sort_key = key
        self._sort_dir = direction
        return self

    def skip(self, count: int) -> "FakeAsyncCursor":
        self._skip = max(0, int(count))
        return self

    def limit(self, count: int) -> "FakeAsyncCursor":
        self._limit = max(0, int(count))
        return self

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        docs = list(self._docs)
        if self._sort_key:
            rev = (self._sort_dir == DESCENDING)
            docs.sort(key=lambda d: d.get(self._sort_key) or "", reverse=rev)

        if self._skip:
            docs = docs[self._skip:]

        lim = self._limit
        if length is not None:
            lim = min(lim, length) if lim is not None else length

        if lim is not None:
            docs = docs[:lim]

        return [deepcopy(d) for d in docs]


class FakeAsyncCollection:
    """Async collection simulating PyMongo document operations with unique index support."""

    def __init__(self, name: str):
        self.name = name
        self._docs: Dict[str, Dict[str, Any]] = {}  # keyed by str(_id)
        self._unique_fields: List[str] = ["analysis_session_id"]

    def _matches_filter(self, doc: Dict[str, Any], filter_dict: Optional[Dict[str, Any]]) -> bool:
        if not filter_dict:
            return True
        for k, v in filter_dict.items():
            if doc.get(k) != v:
                return False
        return True

    async def create_indexes(self, index_models: List[Any]) -> List[str]:
        names = []
        for model in index_models:
            name = getattr(model, "name", "idx")
            names.append(name)
            if getattr(model, "unique", False):
                keys = getattr(model, "document", {}).get("key", [])
                for field_spec in keys:
                    field_name = field_spec[0] if isinstance(field_spec, (list, tuple)) else str(field_spec)
                    if field_name not in self._unique_fields:
                        self._unique_fields.append(field_name)
        return names

    async def insert_one(self, doc: Dict[str, Any]) -> InsertOneResult:
        new_doc = deepcopy(doc)
        if "_id" not in new_doc:
            new_doc["_id"] = ObjectId()

        # Check unique constraint
        for field in self._unique_fields:
            if field in new_doc:
                for existing in self._docs.values():
                    if existing.get(field) == new_doc[field]:
                        raise DuplicateKeyError(f"Duplicate key on unique field '{field}': {new_doc[field]}")

        doc_id = str(new_doc["_id"])
        self._docs[doc_id] = new_doc
        return InsertOneResult(new_doc["_id"])

    async def find_one(self, filter_dict: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        for doc in self._docs.values():
            if self._matches_filter(doc, filter_dict):
                return deepcopy(doc)
        return None

    def find(self, filter_dict: Optional[Dict[str, Any]] = None) -> FakeAsyncCursor:
        matched = [deepcopy(d) for d in self._docs.values() if self._matches_filter(d, filter_dict)]
        return FakeAsyncCursor(matched)

    async def count_documents(self, filter_dict: Optional[Dict[str, Any]] = None) -> int:
        return sum(1 for d in self._docs.values() if self._matches_filter(d, filter_dict))

    async def update_one(
        self,
        filter_dict: Dict[str, Any],
        update_doc: Dict[str, Any],
        upsert: bool = False,
    ) -> UpdateResult:
        for doc_id, doc in self._docs.items():
            if self._matches_filter(doc, filter_dict):
                # Apply $set
                set_fields = update_doc.get("$set", {})
                for k, v in set_fields.items():
                    doc[k] = deepcopy(v)
                return UpdateResult(matched_count=1, modified_count=1)

        if upsert:
            new_doc: Dict[str, Any] = {"_id": ObjectId()}
            for k, v in filter_dict.items():
                new_doc[k] = deepcopy(v)
            for k, v in update_doc.get("$setOnInsert", {}).items():
                new_doc[k] = deepcopy(v)
            for k, v in update_doc.get("$set", {}).items():
                new_doc[k] = deepcopy(v)

            # Check unique constraints on upsert insert
            for field in self._unique_fields:
                if field in new_doc:
                    for existing in self._docs.values():
                        if existing.get(field) == new_doc[field]:
                            raise DuplicateKeyError(f"Duplicate key on unique field '{field}' during upsert: {new_doc[field]}")

            doc_id = str(new_doc["_id"])
            self._docs[doc_id] = new_doc
            return UpdateResult(matched_count=0, modified_count=0, upserted_id=new_doc["_id"])

        return UpdateResult(matched_count=0, modified_count=0)

    async def delete_one(self, filter_dict: Dict[str, Any]) -> DeleteResult:
        for doc_id, doc in list(self._docs.items()):
            if self._matches_filter(doc, filter_dict):
                del self._docs[doc_id]
                return DeleteResult(deleted_count=1)
        return DeleteResult(deleted_count=0)


class FakeAdmin:
    """Simulates admin database with ping support."""

    def __init__(self, is_online: bool = True):
        self.is_online = is_online

    async def command(self, cmd: str, **kwargs) -> Dict[str, Any]:
        if not self.is_online:
            from pymongo.errors import ConnectionFailure
            raise ConnectionFailure("Simulated MongoDB instance unreachable.")
        if cmd == "ping":
            return {"ok": 1.0}
        return {"ok": 1.0}


class FakeAsyncDatabase:
    """Simulates PyMongo AsyncDatabase."""

    def __init__(self, name: str = "edgemind", client: Optional["FakeAsyncMongoClient"] = None):
        self.name = name
        self.client = client
        self._collections: Dict[str, FakeAsyncCollection] = {}

    def __getitem__(self, name: str) -> FakeAsyncCollection:
        if name not in self._collections:
            self._collections[name] = FakeAsyncCollection(name)
        return self._collections[name]


class FakeAsyncMongoClient:
    """Simulates PyMongo AsyncMongoClient."""

    def __init__(self, uri: str = "mongodb://127.0.0.1:27017", is_online: bool = True):
        self.uri = uri
        self.is_online = is_online
        self.admin = FakeAdmin(is_online=is_online)
        self._databases: Dict[str, FakeAsyncDatabase] = {}

    def __getitem__(self, name: str) -> FakeAsyncDatabase:
        if name not in self._databases:
            self._databases[name] = FakeAsyncDatabase(name, client=self)
        return self._databases[name]

    async def close(self) -> None:
        self.is_online = False
