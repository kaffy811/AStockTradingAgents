import time
from unittest.mock import AsyncMock
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException, Response
from jose import jwt
from app.services import google_identity as identity
from app.routers import auth

@pytest.fixture
def issuer(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(identity.settings, 'google_client_id', 'test-client')
    monkeypatch.setattr(identity, '_keys', {'test': key.public_key()})
    monkeypatch.setattr(identity, '_expires', time.monotonic() + 300)
    claims = dict(sub='google-subject', email='person@gmail.com', email_verified=True,
                  iss='https://accounts.google.com', aud='test-client', nonce='browser-nonce',
                  iat=int(time.time()), exp=int(time.time()) + 300)
    def issue(**changes):
        omitted = changes.pop('_omit', ())
        payload = claims | changes
        for field in omitted:
            payload.pop(field, None)
        return jwt.encode(payload, key, algorithm='RS256', headers={'kid': 'test'})
    return issue

@pytest.mark.asyncio
async def test_valid_google_identity(issuer):
    assert (await identity.verify_google_token(issuer(), 'browser-nonce'))['sub'] == 'google-subject'

@pytest.mark.asyncio
@pytest.mark.parametrize('changes', [
    {'aud': 'attacker-client'}, {'iss': 'https://attacker.invalid'},
    {'nonce': 'other-browser'}, {'email_verified': False},
    {'exp': int(time.time()) - 300}, {'email': ''}, {'email': 'bad @example.com'}, {'sub': ''},
    {'azp': 'other-client'}, {'iat': int(time.time()) + 3600},
])
async def test_reject_invalid_claims(issuer, changes):
    with pytest.raises(HTTPException) as exc:
        await identity.verify_google_token(issuer(**changes), 'browser-nonce')
    assert exc.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize('credential', ['not-a-token', '', 'eyJhbGciOiJub25lIn0.e30.'])
async def test_malformed_credentials_are_safe(issuer, credential):
    with pytest.raises(HTTPException) as exc:
        await identity.verify_google_token(credential, 'browser-nonce')
    assert exc.value.status_code == 401
    assert credential not in str(exc.value.detail) or not credential


@pytest.mark.asyncio
async def test_wrong_signature_is_rejected(issuer):
    wrong = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = jwt.get_unverified_claims(issuer())
    token = jwt.encode(claims, wrong, algorithm='RS256', headers={'kid': 'test'})
    with pytest.raises(HTTPException) as exc:
        await identity.verify_google_token(token, 'browser-nonce')
    assert exc.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['aud', 'iss', 'sub', 'iat', 'exp', 'nonce', 'email_verified'])
async def test_required_identity_claim_cannot_be_omitted(issuer, field):
    with pytest.raises(HTTPException) as exc:
        await identity.verify_google_token(issuer(_omit=[field]), 'browser-nonce')
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_server_nonce_cannot_match_missing_claim(issuer):
    with pytest.raises(HTTPException) as exc:
        await identity.verify_google_token(issuer(_omit=['nonce']), None)
    assert exc.value.status_code == 401
