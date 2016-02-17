"""Utility module

"""
import os

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from models import Question


engine = create_engine('sqlite:///trivia.sqlite3')


def fill_db_with_questions_from_txt():
    """
    Fills Database with question from file questions/Total.txt
    lines in that file should be of the format below:
        <question>*<answer>
    :return: None
    """
    Session = sessionmaker(bind=engine)
    session = Session()
    c = 0
    skipper = 35000
    with open(os.path.join('questions', 'Total.txt')) as f:
        for line in f.readlines():
            c += 1
            if c < skipper:
                continue
            question_text = line[:line.find('*')]
            question_answer = line[line.find('*')+1:-1]
            new_q = Question(
                text=question_text,
                answer=question_answer,
            )
            session.add(new_q)
            try:
                session.commit()
            except IntegrityError:
                print('IntegrityError with: %s' % (question_text, ))
                session.rollback()
            if c % 1000 == 0:
                print('Added %d k question' % (c / 1000))
    session.commit()
    session.close()
