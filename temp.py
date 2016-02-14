import asyncio
import json
import random

from slackclient import SlackClient

try:
    from local_settings import *
except ImportError:
    pass


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
    blamed = Column(String, default=0)

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
    session.close()


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

    question_dict = {
        'id': random_question.id,
        'text': random_question.text,
        'answer': random_question.answer,
    }
    random_question.times_asked += 1
    session.commit()

    # session.expunge(random_question)
    session.close()
    return question_dict


def initialize_round_number():
    Session = sessionmaker(bind=engine)
    session = Session()
    round_number = session.query(Question).order_by(
        Question.times_asked
    ).first().times_asked
    session.close()
    return round_number


@asyncio.coroutine
def ask_question(question):
    answer = question['answer']
    hints = list()
    hint = ["`Подсказка: "] + ['.']*len(answer) + ['`']
    hints.append("".join(hint))
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
        text="#" + str(question['id']) + ": " + question['text']
    )
    yield from asyncio.sleep(5)
    for i, hint in enumerate(hints):
        sc.api_call(
            "chat.postMessage",
            as_user="true:",
            channel=CHANNEL,
            text=hint
        )
        if i < len(hints) - 1:
            yield from asyncio.sleep(3.5)


def get_nickname(sc, user):
    user_info = sc.api_call(
        "users.info",
        user=user,
    )
    user_name = json.loads(
        user_info.decode('utf-8')
    )['user']['name']
    return user_name

def pm_user(user, message):
    sc = SlackClient(BOT_TOKEN)

    sc.api_call(
        "chat.postMessage",
        as_user="true:",
        channel=user,
        text=message
    )


def process_command(sc, command, from_user):
    Session = sessionmaker(bind=engine)
    session = Session()
    if command == 'top':
        tops = session.query(Player).order_by(Player.score.desc()).limit(5)
        for place, top in enumerate(tops):
            user_name = get_nickname(sc, top.slack_id)
            message = (
                "#" + str(place+1) + ' ' + user_name + ' ' + str(top.score))
            pm_user(from_user, message)
    elif command == 'myscore':
        player = session.query(Player).filter(
            Player.slack_id == from_user).first()
        if player:
            message = "Количество очков: " + str(player.score)
            pm_user(from_user, message)
    elif command.startswith('blame'):
        # don't blame too much they could think that you are weak
        times_blamed = session.query(func.count(Question.id)).filter(
            Question.blamed == from_user).scalar()
        if times_blamed == 5:
            message = 'Хватит жаловаться!'
            pm_user(from_user, message)
            return
        question_id = command[5:]
        try:
            question_id = int(question_id)
        except ValueError:
            session.close()
            return
        question = session.query(Question).get(question_id)
        if question and not question.blamed:
            question.blamed = from_user
            session.commit()
            message = 'Жалоба на вопрос %d принята' % (question_id, )
            pm_user(from_user, message)
        # elif question.blamed in ADMIN_USERS:
        #     message = 'Жалоба на вопрос %d закрыта' % (question_id, )
        #     pm_user(from_user, message)
        elif question:
            message = 'Жалоба на вопрос %d уже открыта' % (question_id, )
            pm_user(from_user, message)
        else:
            message = 'Набранный номер не существует'
            pm_user(from_user, message)

    session.close()


@asyncio.coroutine
def listen_to_the_channel(channel, event_loop):
    sc = SlackClient(BOT_TOKEN)
    rtm_connection = sc.api_call("rtm.start")

    if sc.rtm_connect():
        print('start rtm')
        asking_question = False
        current_answer = None
        ask_task = None
        trivia_on = False
        while True:
            try:
                new_event = sc.rtm_read()
                filtered_events = [
                    x for x in new_event
                    if (x.get('channel') == channel and
                        x.get('type') == 'message')
                ]
                if filtered_events:
                    try:
                        evs = [(x['text'], x['user']) for x in filtered_events]
                    except KeyError:
                        evs = ()

                    for text, user in evs:
                        if text.startswith('.trivia '):
                            if user in ADMIN_USERS and text == ".trivia start":
                                trivia_on = True
                            elif user in ADMIN_USERS and text == ".trivia stop":
                                trivia_on = False
                            process_command(sc, text[8:], user)
                        if current_answer and current_answer == text.lower():
                            print('User %s is krosavcheg' % (user, ))
                            ask_task.cancel()
                            asking_question = False
                            # TODO: create coroutine out of this
                            # Tell about the winner
                            Session = sessionmaker(bind=engine)
                            session = Session()
                            winner = session.query(Player).filter(
                                Player.slack_id == user).first()
                            if not winner:
                                new_player = Player(
                                    slack_id=user,
                                    score=1
                                )
                                session.add(new_player)
                            else:
                                winner.score += 1
                            session.commit()
                            session.close()
                            # user_info = sc.api_call(
                            #     "users.info",
                            #     user=user,
                            # )
                            # user_name = json.loads(
                            #     user_info.decode('utf-8')
                            # )['user']['name']
                            user_name = get_nickname(sc, user)
                            sc.api_call(
                                "chat.postMessage",
                                as_user="true:",
                                channel=CHANNEL,
                                text=user_name + " - молодчина! Плюс балл."
                            )

                            # pause

                if trivia_on and (
                    not asking_question or ask_task.done() or
                    ask_task.cancelled()
                ):
                    asking_question = True
                    rand_q = get_random_question()
                    current_answer = rand_q['answer'].lower()
                    yield from asyncio.sleep(5)
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


if __name__ == '__main__':
    round_number = initialize_round_number()

    loop = asyncio.get_event_loop()
    tasks = [
        listen_to_the_channel(CHANNEL, loop),
    ]
    loop.run_until_complete(
        asyncio.wait(tasks)
    )
    loop.close()
    print("Success!!")
