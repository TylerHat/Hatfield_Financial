from flask import Flask
from flask_cors import CORS

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

app = Flask(__name__)
CORS(app)

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

if __name__ == '__main__':
    app.run(port=5000, debug=True)
