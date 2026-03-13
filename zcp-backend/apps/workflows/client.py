from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from django.conf import settings


async def get_temporal_client() -> Client:
    return await Client.connect(
        target_host=settings.TEMPORAL_HOST,
        namespace=settings.TEMPORAL_NAMESPACE,
        api_key=settings.TEMPORAL_API_KEY,
        tls=True,
        data_converter=pydantic_data_converter,
    )
