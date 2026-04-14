import logging
import os
import threading
from time import time

from dotenv import load_dotenv, find_dotenv

# Load .env from repo root or Backend/ (walks upward from CWD).
# Must run before os.environ is read below.
load_dotenv(find_dotenv(usecwd=True))

from flask import Flask, jsonify, request, g
from werkzeug.security import generate_password_hash
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import event as sa_event, inspect as sa_inspect, text as sa_text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

from models import db, User
from routes.stock_data import stock_data_bp
from routes.stock_info import stock_info_bp
from routes.strategies.bollinger_bands import bb_bp
from routes.strategies.post_earnings_drift import ped_bp
from routes.strategies.relative_strength import rs_bp
from routes.strategies.mean_reversion import mr_bp
from routes.strategies.rsi import rsi_bp
from routes.strategies.macd_crossover import macd_bp
from routes.backtest import backtest_bp
from routes.strategies.volatility_squeeze import vs_bp
from routes.strategies.breakout_52week import bk_bp
from routes.strategies.ma_confluence import mac_bp
from routes.auth_routes import auth_bp
from routes.admin import admin_bp
from routes.user_data import user_data_bp
from routes.recommendations import recommendations_bp, prewarm_cache
from routes.analyst_data import analyst_data_bp

app = Flask(__name__)
_raw_origin = os.environ.get('ALLOWED_ORIGIN', 'http://localhost:3000')
_origins = list({o.strip() for o in _raw_origin.split(',') if o.strip()} | {'https://hatfield-financial.com'})
logger.info('CORS allowed origins: %s', _origins)
CORS(app, origins=_origins, supports_credentials=True,
     allow_headers=['Content-Type', 'Authorization'],
     methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-fallback-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///hatfield.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Optimize SQLite for EFS: WAL mode improves concurrent reads, busy_timeout
# prevents "database is locked" errors under load.
with app.app_context():
    if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
        @sa_event.listens_for(db.engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri='memory://')

@app.before_request
def _start_timer():
    g.start_time = time()

@app.after_request
def _log_request(response):
    duration_ms = round((time() - g.start_time) * 1000)
    logger.info('%s %s → %d (%dms)', request.method, request.path, response.status_code, duration_ms)
    return response

@app.errorhandler(500)
def internal_error(e):
    logger.error('Unhandled 500 on %s %s: %s', request.method, request.path, e, exc_info=True)
    return jsonify({'error': 'Internal server error'}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'error': 'Too many requests. Please try again later.'}), 429

app.register_blueprint(stock_data_bp)
app.register_blueprint(stock_info_bp)
app.register_blueprint(bb_bp)
app.register_blueprint(ped_bp)
app.register_blueprint(rs_bp)
app.register_blueprint(mr_bp)
app.register_blueprint(rsi_bp)
app.register_blueprint(macd_bp)
app.register_blueprint(backtest_bp)
app.register_blueprint(vs_bp)
app.register_blueprint(bk_bp)
app.register_blueprint(mac_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(user_data_bp)
app.register_blueprint(recommendations_bp)
app.register_blueprint(analyst_data_bp)

# Rate limits on auth endpoints
limiter.limit('5/minute')(app.view_functions['auth.login'])
limiter.limit('30/hour')(app.view_functions['auth.register'])
limiter.limit('10/minute')(app.view_functions['auth.update_me'])
limiter.limit('10/minute', methods=['GET'])(app.view_functions['user_data.get_watchlist_data'])
limiter.limit('10/minute')(app.view_functions['admin.delete_user'])
limiter.limit('10/minute')(app.view_functions['admin.update_user_role'])

with app.app_context():
    db.create_all()

    # Idempotent migration: add is_admin / last_login_at columns to existing
    # users tables. db.create_all() does not ALTER existing tables.
    inspector = sa_inspect(db.engine)
    if inspector.has_table('users'):
        existing_cols = {col['name'] for col in inspector.get_columns('users')}
        is_sqlite = 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']
        with db.engine.begin() as conn:
            if 'is_admin' not in existing_cols:
                default_clause = '0' if is_sqlite else 'FALSE'
                conn.execute(sa_text(
                    f'ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT {default_clause}'
                ))
                logger.info('Migration: added users.is_admin column')
            if 'last_login_at' not in existing_cols:
                conn.execute(sa_text(
                    'ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP NULL'
                ))
                logger.info('Migration: added users.last_login_at column')
            if 'email' not in existing_cols:
                conn.execute(sa_text(
                    'ALTER TABLE users ADD COLUMN email VARCHAR(254) NULL'
                ))
                logger.info('Migration: added users.email column')

        # Ensure unique index on users.email
        with db.engine.begin() as conn:
            conn.execute(sa_text(
                'CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users (email)'
            ))

    # Idempotent migration: widen ticker columns from VARCHAR(10) → VARCHAR(20)
    # so crypto pairs (e.g. "MATIC-USD") and longer ETF tickers fit.
    # No-op on SQLite (length is advisory, ALTER COLUMN TYPE not supported).
    # Runs on Postgres only — safe to keep across deploys.
    if not is_sqlite:
        with db.engine.begin() as conn:
            for table in ('watchlist_items', 'portfolio_holdings'):
                if inspector.has_table(table):
                    cols = {c['name']: c for c in inspector.get_columns(table)}
                    ticker_col = cols.get('ticker')
                    # Postgres reports type as e.g. VARCHAR(10); widen if < 20
                    needs_widen = False
                    if ticker_col is not None:
                        col_type = str(ticker_col.get('type', '')).upper()
                        if 'VARCHAR' in col_type:
                            try:
                                length = int(col_type.split('(')[1].rstrip(')'))
                                if length < 20:
                                    needs_widen = True
                            except (IndexError, ValueError):
                                pass
                    if needs_widen:
                        conn.execute(sa_text(
                            f'ALTER TABLE {table} ALTER COLUMN ticker TYPE VARCHAR(20)'
                        ))
                        logger.info('Migration: widened %s.ticker to VARCHAR(20)', table)

    # Seed admin from ADMIN_USERNAME env var, if set.
    admin_username = os.environ.get('ADMIN_USERNAME', '').strip()
    if admin_username:
        admin_user = User.query.filter_by(username=admin_username).first()
        if admin_user and not admin_user.is_admin:
            admin_user.is_admin = True
            db.session.commit()
            logger.info('Admin seeded: %s is now an admin', admin_username)
        elif admin_user:
            logger.info('Admin already flagged: %s', admin_username)
        else:
            logger.warning('ADMIN_USERNAME=%s not found in users table (register first)', admin_username)

    # Reset admin password from ADMIN_PASSWORD env var, if set.
    # Requires ADMIN_USERNAME to also be set so we know which user to update.
    # Remove ADMIN_PASSWORD from the task definition immediately after the reset.
    admin_password = os.environ.get('ADMIN_PASSWORD', '').strip()
    if admin_password and admin_username:
        admin_user = User.query.filter_by(username=admin_username).first()
        if admin_user:
            admin_user.password_hash = generate_password_hash(admin_password)
            db.session.commit()
            logger.info('Password reset for admin user: %s', admin_username)
        else:
            logger.warning('ADMIN_PASSWORD set but ADMIN_USERNAME=%s not found', admin_username)

# Pre-warm the recommendations cache in the background so the first user
# request doesn't block the server while fetching 500 tickers.
# gunicorn --preload loads this module once before forking workers,
# so this thread starts exactly once regardless of worker count.
threading.Thread(target=prewarm_cache, daemon=True).start()

if __name__ == '__main__':
    app.run(port=int(os.environ.get('PORT', 5000)), debug=False)
