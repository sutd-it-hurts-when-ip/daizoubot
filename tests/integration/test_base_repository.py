# --- IMPORTS ---
# region imports

from bson import ObjectId

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

import pytest

from typing import Annotated, Optional


from repositories.base_repository import BaseRepository

# endregion imports


# define type alias to coerce value to str for pydantic validator
PyObjectId = Annotated[str, BeforeValidator(str)]


class _TestModel(BaseModel):
    """
    Test domain model with trivial implementation.
    """

    # --- CLASS ATTRIBUTES ---
    # region class attributes

    # accept both field name and alias (for id and _id fields)
    model_config = ConfigDict(validate_by_name=True)

    # endregion class attributes


    # --- MODEL FIELDS ---
    # region model fields

    # make tid field optional and alias to _id
    tid: Optional[PyObjectId] = Field(alias="_id", default=None)

    # trivial field
    amount: int = 62353535

    # endregion model fields


class _TestRepository(BaseRepository[_TestModel]):
    """
    Test data repository with trivial implementation.
    """

    # --- CLASS ATTRIBUTES ---
    # region class attributes

    collection_name = "test_base_repository"
    model = _TestModel

    # endregion class attributes


@pytest.fixture
def repo(database) -> _TestRepository:
    """
    Instantiate TestRepository as parameter for test functions.
    """

    return _TestRepository(database)


@pytest.mark.asyncio
async def test_create_round_trip(repo):

    # --- SETUP ---
    # region setup

    # initialise test model field values
    test_amount = 67

    # endregion setup


    # --- ACT ---
    # region act

    # instantiate _TestModel object and create document
    result = await repo.create(_TestModel(amount=test_amount))

    # endregion act


    # --- ASSERT ---
    # region assert

    # check document id exists
    assert ObjectId.is_valid(result.tid)

    # check document amount matches input object amount
    assert result.amount == test_amount

    # endregion assert


    # --- TEARDOWN ---
    # already handled by conftest.py


@pytest.mark.asyncio
async def test_delete_existing_document_returns_true(repo):

    # --- SETUP ---
    # region setup

    # create document to be deleted
    document = await repo.create(_TestModel())

    # endregion setup


    # --- ACT ---
    # region act

    # delete existing document
    result = await repo.delete(document.tid)

    # endregion act


    # --- ASSERT ---
    # region assert

    # check delete reported successful
    assert result is True

    # verify document no longer exists
    assert await repo.get_by_id(document.tid) is None

    # endregion assert


    # --- TEARDOWN ---
    # already handled by conftest.py


@pytest.mark.asyncio
async def test_delete_missing_document_returns_false(repo):

    # --- SETUP ---
    # region setup

    # create document to be preserved
    document = await repo.create(_TestModel())

    # endregion setup


    # --- ACT ---
    # region act

    # delete missing document
    result = await repo.delete(ObjectId())

    # endregion act


    # --- ASSERT ---
    # region assert

    # check delete reported unsuccessful
    assert result is False

    # check existing document preserved
    assert await repo.get_by_id(document.tid) is not None

    # endregion assert


    # --- TEARDOWN ---
    # already handled by conftest.py


@pytest.mark.asyncio
async def test_get_by_id_existing_document_returns_document(repo):

    # --- SETUP ---
    # region setup

    # initialise test model field values
    test_amount = 67

    # create document to be returned
    document = await repo.create(_TestModel(amount=test_amount))

    # create document to not be returned
    await repo.create(_TestModel(amount=(test_amount + 1)))

    # endregion setup


    # --- ACT ---
    # region act

    # get document by id
    result = await repo.get_by_id(document.tid)

    # endregion act


    # --- ASSERT ---
    # region assert

    # check result exists
    assert result is not None

    # check result is target document
    assert result.amount == test_amount

    # endregion assert


    # --- TEARDOWN ---
    # already handled by conftest.py


@pytest.mark.asyncio
async def test_get_by_id_missing_document_returns_none(repo):

    # --- SETUP ---
    # region setup

    # create document to not be returned
    await repo.create(_TestModel())

    # endregion setup


    # --- ACT ---
    # region act

    # get document by id
    result = await repo.get_by_id(ObjectId())

    # endregion act


    # --- ASSERT ---
    # region assert

    # check result does not exist
    assert result is None

    # endregion assert


    # --- TEARDOWN ---
    # already handled by conftest.py


@pytest.mark.asyncio
async def test_update_existing_document_returns_updated_document(repo):

    # --- SETUP ---
    # region setup

    # initialise test model field values
    test_amount = 67
    decoy_amount = test_amount + 1
    updated_amount = test_amount + 2

    # create document to not be updated
    decoy = await repo.create(_TestModel(amount=decoy_amount))

    # create document to be updated
    document = await repo.create(_TestModel(amount=test_amount))

    # endregion setup


    # --- ACT ---
    # region act

    # update existing document amount
    result = await repo.update(document.tid, { "amount": updated_amount })

    # endregion act


    # --- ASSERT ---
    # region assert

    # check result exists
    assert result is not None

    # check returned document for updated amount
    assert result.tid == document.tid
    assert result.amount == updated_amount

    # check decoy document for unchanged amount
    assert (await repo.get_by_id(decoy.tid)).amount == decoy_amount

    # endregion assert


    # --- TEARDOWN ---
    # already handled by conftest.py


@pytest.mark.asyncio
async def test_update_missing_document_returns_none(repo):

    # --- SETUP ---
    # region setup

    # initialise test model field values
    test_amount = 67
    fake_amount = test_amount + 2

    # create document to not be updated
    decoy = await repo.create(_TestModel(amount=test_amount))

    # endregion setup


    # --- ACT ---
    # region act

    # update missing document amount
    result = await repo.update(ObjectId(), {"amount": fake_amount})

    # endregion act


    # --- ASSERT ---
    # region assert

    # check result does not exist
    assert result is None

    # check decoy document for unchanged amount
    assert (await repo.get_by_id(decoy.tid)).amount == test_amount

    # endregion assert


    # --- TEARDOWN ---
    # already handled by conftest.py


@pytest.mark.asyncio
async def test_update_ignores_id_changes(repo):

    # --- SETUP ---
    # region setup

    # initialise test model field values
    fake_id = ObjectId()
    test_amount = 67
    updated_amount = test_amount + 2

    # create document to be updated
    document = await repo.create(_TestModel(amount=test_amount))

    # endregion setup


    # --- ACT ---
    # region act

    # update existing document
    result = await repo.update(document.tid, { "_id": fake_id, "amount": updated_amount })

    # endregion act


    # --- ASSERT ---
    # region assert

    # check result exists
    assert result is not None

    # check document id unchanged
    assert result.tid == document.tid

    # check fake id not in collection
    assert (await repo.get_by_id(fake_id)) is None

    # check document amount updated
    assert (await repo.get_by_id(document.tid)).amount == updated_amount

    # endregion assert


    # --- TEARDOWN ---
    # already handled by conftest.py


@pytest.mark.asyncio
async def test_update_empty_changes_returns_document(repo):

    # --- SETUP ---
    # region setup

    # initialise test model field values
    test_amount = 67

    # create document
    document = await repo.create(_TestModel(amount=test_amount))

    # endregion setup


    # --- ACT ---
    # region act

    # update existing document with empty changes
    result = await repo.update(document.tid, {})

    # endregion act


    # --- ASSERT ---
    # region assert

    # check result exists
    assert result is not None

    # check result is document
    assert result.tid == document.tid

    # check for amount unchanged
    assert result.amount == test_amount

    # endregion assert


    # --- TEARDOWN ---
    # already handled by conftest.py
