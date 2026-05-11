"""AWS Lambda handler — fires daily at 9:30 AM ET MON-FRI via EventBridge
Scheduler and triggers a force-rebalance for every Custom ETF strategy.

Uses urllib (stdlib) so the Lambda zip needs no third-party dependencies.

Environment variables:
  BACKEND_URL          e.g. https://api.hatfield-financial.com
  INTERNAL_API_SECRET  shared secret matching the backend env var
"""

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    backend_url = os.environ['BACKEND_URL'].rstrip('/')
    secret = os.environ['INTERNAL_API_SECRET']
    url = f'{backend_url}/api/custom-etf/auto-rebalance-all'

    req = urllib.request.Request(
        url,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-Internal-Secret': secret,
        },
        data=b'{}',
    )

    logger.info('Triggering auto-rebalance at %s', url)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode('utf-8')
            logger.info('Backend responded %d: %s', resp.status, body[:500])
            return {'statusCode': resp.status, 'body': body}
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        logger.error('Backend returned %d: %s', e.code, body[:500])
        return {'statusCode': e.code, 'body': body}
    except Exception as e:
        logger.error('Rebalance trigger failed: %s', e, exc_info=True)
        raise
