# --- IMPORTS ---
# region imports

from bson import ObjectId

from typing import Any, Generic, Optional, Type, TypeVar

from pydantic import BaseModel

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

# endregion imports


# declare placeholder model type
ModelType = TypeVar("ModelType", bound=BaseModel)


class BaseRepository(Generic[ModelType]):
    """
    Base repository class with generic ModelType parameter for subclasses to implement.
    """

    # --- CLASS ATTRIBUTES ---
    # region class attributes

    # collection name in MongoDB database to access
    collection_name: str

    # data model to interface with
    model: Type[ModelType]

    # endregion class attributes


    def __init__(self, database: AsyncDatabase) -> None:

        # get access to collection from database
        self.collection = database[self.collection_name]

    
    # --- HELPERS ---
    # region helpers

    def _to_document(self, obj: ModelType) -> dict[str, Any]:
        """
        Helper to convert model object to MongoDB document.
        """

        # generate dict representation of model
        document = obj.model_dump(by_alias=True, exclude_none=True);

        # remove existing _id if any to let MongoDB assign instead
        document.pop("_id", None);

        return document;
    

    def _to_model(self, document: Optional[dict[str, Any]]) -> Optional[ModelType]:
        """
        Helper to convert MongoDB document to model object.
        """

        return self.model.model_validate(document) if document else None;
    

    @staticmethod
    def _to_object_id(val: Any) -> ObjectId:
        """
        Helper to convert input value to ObjectId object.
        """

        return val if isinstance(val, ObjectId) else ObjectId(str(val));

    # endregion helpers

    
    # --- CRUD ---
    # region crud

    async def create(self, obj: ModelType) -> ModelType:
        """
        Create document in collection. Returns created document.
        """

        # convert data model to document
        document = self._to_document(obj);

        # insert document into collection
        result = await self.collection.insert_one(document);

        # get created document by id
        created = await self.get_by_id(result.inserted_id);

        # guard against document not found
        if created is None: raise RuntimeError("Failed to fetch document after insert.")
        
        return created;
    

    async def delete(self, document_id: Any) -> bool:
        """
        Delete first document from collection with matching id. Returns bool whether delete was
        successful.
        """

        # convert id to ObjectId object and delete from collection first document matching _id
        result = await self.collection.delete_one({"_id": self._to_object_id(document_id)});

        return result.deleted_count > 0;
    

    async def get_by_id(self, document_id: Any) -> Optional[ModelType]:
        """
        Get first document from collection with matching id and converts to data model. Returns None
        if no matches found.
        """

        # convert id to ObjectId object and query collection for first document matching _id
        document = await self.collection.find_one({"_id": self._to_object_id(document_id)});

        return self._to_model(document);
    

    async def update(self, document_id: Any, changes: dict[str, Any]) -> Optional[ModelType]:
        """
        Set changes to first document from collection with matching id. Returns updated document
        if any, else None.
        """

        # guard against overwriting MongoDB assigned id
        changes = changes.copy();
        changes.pop("_id", None);

        # guard against empty changes
        if not changes: return await self.get_by_id(document_id)

        # convert id to ObjectId object, filter collection for first document matching _id,
        # set changes, and return modified document
        document = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(document_id)},
            {"$set": changes},
            return_document=ReturnDocument.AFTER
        );

        return self._to_model(document);

    # endregion crud