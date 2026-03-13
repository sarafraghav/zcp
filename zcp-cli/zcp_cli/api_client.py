import httpx


class ZCPClient:
    def __init__(self, api_url: str, token: str):
        self.api_url = api_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}

    def deploy(self, manifest: str, org_slug: str, source_zip: bytes) -> dict:
        resp = httpx.post(
            f"{self.api_url}/api/v1/deploy/",
            headers=self._headers,
            data={"manifest": manifest, "org_slug": org_slug},
            files={"source": ("source.zip", source_zip, "application/zip")},
            timeout=600.0,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Deploy failed ({resp.status_code}): {resp.text}")
        return resp.json()
