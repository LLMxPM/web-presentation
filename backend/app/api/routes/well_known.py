"""文件功能：暴露 .well-known 相关的公开服务路由。"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.token_service import TokenService

router = APIRouter()


@router.get("/.well-known/jwks.json", summary="提供应用的 JWKS 配置")
async def get_jwks() -> JSONResponse:
    """返回用于验证 Runtime Preview JWS 和其他 JWT 的公钥集。"""
    
    jwks = TokenService.get_jwks()
    return JSONResponse(jwks)
