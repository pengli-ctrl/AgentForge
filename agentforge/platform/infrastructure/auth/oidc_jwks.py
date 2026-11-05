"""提供 OIDC JWKS 令牌校验。"""
import base64, json, time
import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

def _b64(value):
    """解码 地址安全编码。

    Args:
        value: 编码文本。

    Returns:
        原始字节。
    """
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

class JWKSTokenValidator:
    """校验 RS256 JWT。"""
    def __init__(self, jwks_url, *, issuer="", audience="agentforge", client=None):
        """初始化校验器。

        Args:
            jwks_url: JWKS 地址。
            issuer: 签发者。
            audience: 受众。
            client: HTTP 客户端。
        """
        self.url=jwks_url; self.issuer=issuer; self.audience=audience; self.client=client or httpx.Client(timeout=3); self.keys={}
    def _load(self, force=False):
        """加载 JWKS。

        Args:
            force: 是否强制刷新。

        Returns:
            密钥字典。
        """
        if self.keys and not force: return self.keys
        response=self.client.get(self.url); response.raise_for_status(); self.keys={k["kid"]:k for k in response.json().get("keys",[]) if k.get("kid")}; return self.keys
    def validate(self, token):
        """校验令牌。

        Args:
            token: JWT 文本。

        Returns:
            令牌声明。

        Raises:
            ValueError: 令牌无效时抛出。
        """
        h,p,s=token.split("."); header=json.loads(_b64(h)); payload=json.loads(_b64(p)); kid=str(header.get("kid") or "")
        if header.get("alg")!="RS256" or not kid: raise ValueError("unsupported JWT")
        key=self._load().get(kid) or self._load(True).get(kid)
        if key is None: raise ValueError("unknown JWT kid")
        pub=rsa.RSAPublicNumbers(int.from_bytes(_b64(key["e"]),"big"), int.from_bytes(_b64(key["n"]),"big")).public_key()
        pub.verify(_b64(s), f"{h}.{p}".encode(), padding.PKCS1v15(), hashes.SHA256())
        now=int(time.time())
        if payload.get("exp", now+1) < now: raise ValueError("JWT expired")
        if payload.get("nbf", now-1) > now: raise ValueError("JWT not yet valid")
        if self.issuer and payload.get("iss") != self.issuer: raise ValueError("issuer mismatch")
        if self.audience and payload.get("aud") not in (self.audience,[self.audience]): raise ValueError("audience mismatch")
        return payload
