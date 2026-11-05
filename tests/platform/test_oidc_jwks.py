"""测试 OIDC JWKS 校验器。"""

import pytest

from agentforge.platform.infrastructure.auth.oidc_jwks import JWKSTokenValidator


def test_invalid_token_is_rejected():
    """验证格式错误令牌被拒绝。"""
    validator = JWKSTokenValidator("http://idp/jwks")
    with pytest.raises(ValueError):
        validator.validate("not-a-token")
