from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import UniqueConstraint

Base = declarative_base()


class Player(Base):
    __tablename__ = 'player'
    id = Column(Integer, primary_key=True, autoincrement=True)
    slack_id = Column(String, unique=True)
    score = Column(Integer)

    def __repr__(self):
        return '<Player(slack_id=%s, score=%s)>' % (self.slack_id, self.score)


class Question(Base):
    __tablename__ = 'question'

    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(String)
    answer = Column(String)
    times_asked = Column(Integer, default=0)
    blamed = Column(String, default=0)

    __table_args__ = (
        UniqueConstraint('text', 'answer', name='_text_answer_uc'),
    )
