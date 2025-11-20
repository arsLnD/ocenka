from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import config

Base = declarative_base()


class WelcomePost(Base):
    __tablename__ = 'welcome_posts'

    id = Column(Integer, primary_key=True)
    text = Column(Text)
    photo = Column(String, nullable=True)
    video = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class Review(Base):
    __tablename__ = 'reviews'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    rating = Column(Integer)
    text = Column(Text)
    photo = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# Инициализация базы данных
engine = create_engine(config.DATABASE_URL)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


def get_session():
    return Session()