import asyncio
import time
import random
import time

from slackclient import SlackClient

try:
    from local_settings import *
except ImportError:
    pass


# sc = SlackClient(BOT_TOKEN)
# chan = CHANNEL
# greeting = "Hello!\nNice to meet you there =)"
# print(sc.api_call("chat.postMessage", as_user="true:", channel=chan, text=greeting))


# sc = SlackClient(BOT_TOKEN)
# print(sc.api_call("api.test"))
# rtm_connection = sc.api_call("rtm.start")
# rtm_url = json.loads(rtm_connection.decode('utf-8'))['url']
# print(rtm_url)
#
# sc = SlackClient(BOT_TOKEN)
# if sc.rtm_connect():
#     print('start rtm')
#     while True:
#         new_event = sc.rtm_read()
#         filtered_events = [x for x in new_event if x.get('channel') == 'CHANNEL' and x.get('type') == 'message']
#         if filtered_events:
#             print([x['text'] for x in filtered_events])
#         # time.sleep(1)
# else:
#     print("Connection Failed, invalid token?")



import os
from sqlalchemy import create_engine
from sqlalchemy import desc
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.sql.expression import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import sessionmaker, relationship

round_number = -1

engine = create_engine('sqlite:///trivia.sqlite3')

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
    blamed = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint('text', 'answer', name='_text_answer_uc'),
    )


def fill_db_with_questions_from_txt():
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


def increment_round_number():
    global round_number
    print('incrementing...')
    round_number += 1


def get_random_question():
    Session = sessionmaker(bind=engine)
    session = Session()
    random_question = session.query(Question).filter(
        Question.times_asked == round_number
    ).order_by(func.random()).first()
    if not random_question:
        print(random_question)
        increment_round_number()
        random_question = session.query(Question).filter(
            Question.times_asked == round_number
        ).order_by(func.random()).first()
    session.close()
    return random_question


def initialize_round_number():
    Session = sessionmaker(bind=engine)
    session = Session()
    return session.query(Question).order_by(
        Question.times_asked
    ).first().times_asked


@asyncio.coroutine
def ask_question(question):
    print('start asking')
    answer = question.answer
    hints = list()
    hint = ["`Подсказка: "] + ['.']*len(answer) + ['`']
    hints.append("".join(hint))
    print(hint)
    offset = 1
    rand_indexes = list(range(len(answer)))
    random.shuffle(rand_indexes)
    for i in rand_indexes:
        hint[offset+i] = answer[i]
        hints.append("".join(hint))
    sc = SlackClient(BOT_TOKEN)

    sc.api_call(
        "chat.postMessage",
        as_user="true:",
        channel=CHANNEL,
        text=question.text
    )
    # time.sleep(5)
    yield from asyncio.sleep(5)
    for hint in hints:
        print(hint)
        sc.api_call(
            "chat.postMessage",
            as_user="true:",
            channel=CHANNEL,
            text=hint
        )
        yield from asyncio.sleep(3.5)
        # time.sleep(3.5)


@asyncio.coroutine
def listen_to_the_channel(channel, event_loop):
    sc = SlackClient(BOT_TOKEN)
    rtm_connection = sc.api_call("rtm.start")

    if sc.rtm_connect():
        print('start rtm')
        asking_question = False
        current_answer = None
        ask_task = None
        while True:
            try:
                new_event = sc.rtm_read()
                filtered_events = [
                    x for x in new_event
                    if (x.get('channel') == channel and
                        x.get('type') == 'message')
                ]
                if current_answer and filtered_events:
                    evs = [(x['text'], x['user']) for x in filtered_events]
                    for text, user in evs:
                        if current_answer == text:
                            print('User %s is krosavcheg' % (user, ))
                            ask_task.cancel()
                            asking_question = False

                if not asking_question:
                    asking_question = True
                    rand_q = get_random_question()
                    current_answer = rand_q.answer
                    ask_task = asyncio.Task(
                        ask_question(rand_q), loop=event_loop
                    )
                yield from asyncio.sleep(0)
            except KeyboardInterrupt:
                if ask_task:
                    ask_task.cancel()
                break
    else:
        print("Connection Failed, invalid token?")

@asyncio.coroutine
def ask_question_coroutine(seconds_to_sleep=1):
    print('Asking for a question')
    rand_q = get_random_question()
    ask_question(rand_q)
    yield from asyncio.sleep(seconds_to_sleep)


@asyncio.coroutine
def read_answers_coroutine(seconds_to_sleep=1):
    sc = SlackClient(BOT_TOKEN)
    if sc.rtm_connect():
        while True:
            new_event = sc.rtm_read()
            filtered_events = [
                x for x in new_event if (
                    x.get('channel') == CHANNEL and x.get('type') == 'message'
                )
            ]
            if filtered_events:
                print([x['text'] for x in filtered_events])
            # time.sleep(1)
    else:
        print("Connection Failed, invalid token?")
    yield from asyncio.sleep(seconds_to_sleep)


if __name__ == '__main__':
    round_number = initialize_round_number()
    # rand_q = get_random_question()
    # ask_question(rand_q)
    loop = asyncio.get_event_loop()
    tasks = [
        ask_question_coroutine(1),
        read_answers_coroutine(),
    ]
    loop.run_until_complete(asyncio.wait(tasks))

    print('Success!!')
