from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, WebSocket, status

from ..auth import SESSION_COOKIE, AuthService
from ..config import Config
from ..db import Database
from ..events import EventBus
from ..services.hub import Hub
from ..services.mqtt_link import MqttLinkService
from ..services.tuya_link import TuyaLinkService
from ..settings import SettingsStore


@dataclass
class Services:
    config: Config
    db: Database
    settings: SettingsStore
    bus: EventBus
    auth: AuthService
    hub: Hub
    tuya: TuyaLinkService
    mqtt: MqttLinkService


def services(request: Request) -> Services:
    return request.app.state.services


def current_user(request: Request) -> dict:
    svc: Services = request.app.state.services
    user = svc.auth.user_for_token(request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Faça login para continuar.")
    return user


def websocket_user(ws: WebSocket) -> dict | None:
    svc: Services = ws.app.state.services
    return svc.auth.user_for_token(ws.cookies.get(SESSION_COOKIE))
