"""Fail closed on missing Google-only production authentication configuration.

Legacy email verification/invite settings remain readable for rollback and
historical tools, but are not prerequisites for Google-only admission.
"""
import logging

log = logging.getLogger(__name__)
_PRODUCTION_ENVS = frozenset({'staging', 'production', 'prod'})


def validate_startup_config(settings) -> None:
    if getattr(settings, 'app_env', 'development').lower() not in _PRODUCTION_ENVS:
        return
    errors = []
    client = getattr(settings, 'google_client_id', '')
    if not client or not client.endswith('.apps.googleusercontent.com'):
        errors.append('GOOGLE_CLIENT_ID must be a configured Google Web application client ID.')
    if errors:
        # Only configuration names/rules, never supplied values.
        raise ValueError('[startup_validation] ' + ' '.join(errors))
    log.info('Google-only production authentication configuration checked')
