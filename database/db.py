"""In-memory database implementation."""
import os
import json
from uuid import uuid4
from threading import Lock
from typing import Dict, Any, Optional, List

from config import Config
from utils.logger import get_logger

logger = get_logger("database")


class InMemoryMongo:
    """A tiny thread-safe in-memory DB with Mongo-like semantics for simple apps.

    - Collections: arbitrary string keys (e.g. 'users', 'assets')
    - Each collection is a dict of id -> document
    - Documents are plain dicts and must contain an 'id' field if inserted via insert_one
    - find supports simple equality matching across top-level keys
    - owner scoping is supported by passing owner_id to queries (it filters by owner_id)
    """

    def __init__(self):
        self._lock = Lock()
        self._collections: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def _ensure_collection(self, name: str):
        with self._lock:
            if name not in self._collections:
                self._collections[name] = {}

    def insert_one(self, collection: str, document: Dict[str, Any]):
        """Insert a document into a collection."""
        try:
            self._ensure_collection(collection)
            with self._lock:
                doc = dict(document)
                if "id" not in doc:
                    doc["id"] = str(uuid4())
                self._collections[collection][doc["id"]] = doc
                return doc
        except Exception as e:
            logger.error(f"Error inserting document into {collection}: {e}")
            raise RuntimeError(f"Failed to insert document: {e}")

    def find(self, collection: str, filter: Optional[Dict[str, Any]] = None, owner_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Find documents matching the filter."""
        try:
            self._ensure_collection(collection)
            results = []
            with self._lock:
                for doc in self._collections[collection].values():
                    if owner_id is not None and doc.get("owner_id") != owner_id:
                        continue
                    if not filter:
                        results.append(dict(doc))
                        continue
                    match = True
                    for k, v in filter.items():
                        if doc.get(k) != v:
                            match = False
                            break
                    if match:
                        results.append(dict(doc))
            return results
        except Exception as e:
            logger.error(f"Error finding documents in {collection}: {e}")
            raise RuntimeError(f"Failed to find documents: {e}")

    def find_one(self, collection: str, filter: Dict[str, Any], owner_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Find a single document matching the filter."""
        try:
            res = self.find(collection, filter, owner_id)
            return res[0] if res else None
        except Exception as e:
            logger.error(f"Error finding document in {collection}: {e}")
            raise RuntimeError(f"Failed to find document: {e}")

    def update_one(self, collection: str, filter: Dict[str, Any], patch: Dict[str, Any], owner_id: Optional[str] = None) -> Dict[str, Any]:
        """Update a single document matching the filter."""
        try:
            self._ensure_collection(collection)
            with self._lock:
                for id_, doc in self._collections[collection].items():
                    if owner_id is not None and doc.get("owner_id") != owner_id:
                        continue
                    match = True
                    for k, v in filter.items():
                        if doc.get(k) != v:
                            match = False
                            break
                    if match:
                        doc.update(patch)
                        self._collections[collection][id_] = doc
                        return dict(doc)
            raise KeyError("document not found")
        except KeyError:
            raise
        except Exception as e:
            logger.error(f"Error updating document in {collection}: {e}")
            raise RuntimeError(f"Failed to update document: {e}")

    def delete_one(self, collection: str, filter: Dict[str, Any], owner_id: Optional[str] = None) -> Dict[str, Any]:
        """Delete a single document matching the filter."""
        try:
            self._ensure_collection(collection)
            with self._lock:
                for id_, doc in list(self._collections[collection].items()):
                    if owner_id is not None and doc.get("owner_id") != owner_id:
                        continue
                    match = True
                    for k, v in filter.items():
                        if doc.get(k) != v:
                            match = False
                            break
                    if match:
                        removed = self._collections[collection].pop(id_)
                        return dict(removed)
            raise KeyError("document not found")
        except KeyError:
            raise
        except Exception as e:
            logger.error(f"Error deleting document from {collection}: {e}")
            raise RuntimeError(f"Failed to delete document: {e}")

    def dump_to_files(self):
        """Dump every collection to a JSON file under assets/db/<collection>.json for easy inspection."""
        if not Config.PERSIST:
            return
        
        try:
            # ensure folder
            db_folder = os.path.join("assets", "db")
            os.makedirs(db_folder, exist_ok=True)
        except Exception as e:
            logger.warning(f"Failed to create database directory: {e}")
            return

        try:
            with self._lock:
                # shallow copy of collections
                collections_copy = {k: list(v.values()) for k, v in self._collections.items()}
        except Exception as e:
            logger.warning(f"Failed to copy collections for persistence: {e}")
            return

        for coll_name, docs in collections_copy.items():
            path = os.path.join(db_folder, f"{coll_name}.json")
            try:
                with open(path, "w") as f:
                    json.dump({coll_name: docs}, f, indent=2, default=str)
                logger.debug(f"Persisted {len(docs)} documents to {coll_name}.json")
            except (IOError, OSError) as e:
                # File I/O errors - log warning but don't fail
                logger.warning(f"Failed to write collection {coll_name} to {path}: {e}")
            except (TypeError, ValueError) as e:
                # JSON serialization errors - log warning but don't fail
                logger.warning(f"Failed to serialize collection {coll_name}: {e}")
            except Exception as e:
                # Catch-all for unexpected errors
                logger.warning(f"Unexpected error writing collection {coll_name}: {e}")

    def load_from_files(self):
        """
        Load collections from assets/db/<collection>.json if present.
        Useful at startup to populate in-memory DB with previously persisted data.
        """
        if not Config.PERSIST:
            return
        
        try:
            db_folder = os.path.join("assets", "db")
            os.makedirs(db_folder, exist_ok=True)
        except Exception as e:
            logger.warning(f"Failed to create database directory: {e}")
            return

        try:
            file_list = os.listdir(db_folder)
        except Exception as e:
            logger.warning(f"Failed to list database directory: {e}")
            return

        # look for any json file in the folder and attempt to load it
        for fname in file_list:
            if not fname.endswith(".json"):
                continue
            full = os.path.join(db_folder, fname)
            try:
                with open(full, "r") as f:
                    payload = json.load(f)
                
                # payload expected shape: { "<collection>": [ ...docs... ] }
                if isinstance(payload, dict):
                    for coll_name, docs in payload.items():
                        if isinstance(docs, list):
                            loaded_count = 0
                            for d in docs:
                                # Insert but avoid duplicate IDs if already in memory
                                if isinstance(d, dict):
                                    existing = None
                                    if "id" in d:
                                        # ensure collection exists
                                        self._ensure_collection(coll_name)
                                        with self._lock:
                                            existing = self._collections.get(coll_name, {}).get(d["id"])
                                    if existing:
                                        # skip duplicate
                                        continue
                                    # insert a shallow copy so in-memory has its own dict
                                    try:
                                        self.insert_one(coll_name, dict(d))
                                        loaded_count += 1
                                    except Exception as insert_error:
                                        logger.warning(f"Failed to insert document from {fname}: {insert_error}")
                            logger.info(f"Loaded {loaded_count} documents from {fname}")
                        else:
                            logger.warning(f"Invalid data format in {fname}: expected list of documents")
                else:
                    logger.warning(f"Invalid JSON structure in {fname}: expected dictionary")
            except (IOError, OSError) as e:
                # File I/O errors - log warning but continue loading other files
                logger.warning(f"Failed to read file {full}: {e}")
            except json.JSONDecodeError as e:
                # JSON parsing errors - log warning but continue
                logger.warning(f"Failed to parse JSON from {full}: {e}")
            except Exception as e:
                # Catch-all for unexpected errors
                logger.warning(f"Unexpected error loading {full}: {e}")


# instantiate DB and load existing files (if desired)
db = InMemoryMongo()
if Config.PERSIST:
    db.load_from_files()

