from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    watchlists = db.relationship('Watchlist', backref='user', lazy=True, cascade='all, delete-orphan')
    holdings = db.relationship('PortfolioHolding', backref='user', lazy=True, cascade='all, delete-orphan')
    settings = db.relationship('UserSettings', backref='user', uselist=False, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Watchlist(db.Model):
    __tablename__ = 'watchlists'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False, default='Default')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    items = db.relationship('WatchlistItem', backref='watchlist', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'items': [item.to_dict() for item in self.items],
        }


class WatchlistItem(db.Model):
    __tablename__ = 'watchlist_items'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    watchlist_id = db.Column(db.Integer, db.ForeignKey('watchlists.id'), nullable=False)
    ticker = db.Column(db.String(10), nullable=False)
    added_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint('watchlist_id', 'ticker', name='uq_watchlist_ticker'),)

    def to_dict(self):
        return {
            'id': self.id,
            'ticker': self.ticker,
            'added_at': self.added_at.isoformat() if self.added_at else None,
        }


class PortfolioHolding(db.Model):
    __tablename__ = 'portfolio_holdings'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ticker = db.Column(db.String(10), nullable=False)
    shares = db.Column(db.Float, nullable=False)
    cost_basis = db.Column(db.Float, nullable=False)
    acquired_at = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'ticker': self.ticker,
            'shares': self.shares,
            'cost_basis': self.cost_basis,
            'acquired_at': self.acquired_at.isoformat() if self.acquired_at else None,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class UserSettings(db.Model):
    __tablename__ = 'user_settings'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    default_strategy = db.Column(db.String(50), default='none')
    default_date_range_months = db.Column(db.Integer, default=6)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'default_strategy': self.default_strategy,
            'default_date_range_months': self.default_date_range_months,
        }
