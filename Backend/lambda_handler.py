"""
AWS Lambda handler — pre-computes S&P 500 recommendations and writes
the result to S3 so the Fargate backend can serve it without doing
any heavy pandas / yfinance work.

Triggered every 20 minutes by EventBridge.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import boto3

from routes.recommendations import _fetch_all_data

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client('s3')


def handler(event, context):
    bucket = os.environ['S3_BUCKET']
    key = os.environ.get('S3_KEY', 'recommendations/latest.json')

    t0 = time.time()
    logger.info('Starting recommendations pre-compute')

    stocks, failed, total = _fetch_all_data()

    result = {
        'stocks': stocks,
        'lastUpdated': datetime.now(timezone.utc).isoformat(),
        'count': len(stocks),
        'failedCount': failed,
        'totalTickers': total,
    }

    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(result),
        ContentType='application/json',
    )

    elapsed = time.time() - t0
    logger.info('Wrote %d stocks to s3://%s/%s in %.1fs (%d failed)',
                len(stocks), bucket, key, elapsed, failed)

    return {'statusCode': 200, 'stocks': len(stocks), 'failed': failed}
