from datastore.datastore import DataStore
import os

async def get_datastore() -> DataStore:
    from datastore.providers.pinecone_datastore import PineconeDataStore
    return PineconeDataStore()