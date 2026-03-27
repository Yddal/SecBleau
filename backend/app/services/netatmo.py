"""
Netatmo public weather station client.

Uses the /getpublicdata endpoint to retrieve temperature + humidity from
community weather stations within the Fontainebleau bounding box.
These readings can supplement Open-Meteo with hyperlocal ground truth.

Requires a free developer account at https://dev.netatmo.com
Set NETATMO_CLIENT_ID and NETATMO_CLIENT_SECRET in .env to enable.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TOKEN_URL = "https://api.netatmo.com/oauth2/token"
PUBLIC_DATA_URL = "https://api.netatmo.com/api/getpublicdata"


class NetatmoClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    async def _ensure_token(self) -> None:
        now = datetime.now(timezone.utc)
        if self._access_token and self._token_expires_at and now < self._token_expires_at:
            return

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(TOKEN_URL, data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "read_station",
            })
            resp.raise_for_status()
            data = resp.json()

        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        from datetime import timedelta
        self._token_expires_at = now + timedelta(seconds=expires_in - 60)
        logger.info("Netatmo token refreshed, expires in %ds", expires_in)

    async def get_public_data(
        self,
        lat_ne: float, lon_ne: float,
        lat_sw: float, lon_sw: float,
    ) -> list[dict]:
        """
        Fetch all public Netatmo stations in the given bounding box.
        Returns a list of station dicts with location and latest measurements.
        """
        await self._ensure_token()

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                PUBLIC_DATA_URL,
                headers={"Authorization": f"Bearer {self._access_token}"},
                data={
                    "lat_ne": lat_ne,
                    "lon_ne": lon_ne,
                    "lat_sw": lat_sw,
                    "lon_sw": lon_sw,
                    "filter": "true",  # only stations with recent data
                },
            )
            resp.raise_for_status()
            body = resp.json()

        return body.get("body", [])

    def parse_stations(self, raw_stations: list[dict]) -> list[dict]:
        """
        Extract lat, lon, temperature, humidity from raw Netatmo station data.
        Returns list of simplified dicts.
        """
        stations = []
        for s in raw_stations:
            place = s.get("place", {})
            lat = place.get("location", [None, None])[1]
            lon = place.get("location", [None, None])[0]
            if lat is None or lon is None:
                continue

            measures = s.get("measures", {})
            temp = None
            humidity = None
            pressure = None

            for module_id, module_data in measures.items():
                res = module_data.get("res", {})
                for ts_str, values in res.items():
                    mtype = module_data.get("type", [])
                    for i, key in enumerate(mtype):
                        if key == "temperature" and i < len(values):
                            temp = values[i]
                        elif key == "humidity" and i < len(values):
                            humidity = values[i]
                        elif key == "pressure" and i < len(values):
                            pressure = values[i]

            if temp is not None or humidity is not None:
                stations.append({
                    "station_id": s.get("_id"),
                    "lat": lat,
                    "lon": lon,
                    "temperature_c": temp,
                    "humidity_pct": humidity,
                    "pressure_hpa": pressure,
                })

        return stations
