import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from models import db
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
from routes.user_data import user_data_bp
from routes.recommendations import recommendations_bp

app = Flask(__name__)
CORS(app, origins=['http://localhost:3000'])

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-fallback-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hatfield.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri='memory://')

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
app.register_blueprint(user_data_bp)
app.register_blueprint(recommendations_bp)

# Rate limits on auth endpoints
limiter.limit('5/minute')(app.view_functions['auth.login'])
limiter.limit('3/hour')(app.view_functions['auth.register'])

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(port=5000, debug=True)
