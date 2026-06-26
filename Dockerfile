FROM python:3

WORKDIR /usr/src/app

RUN pip install flask flask-login psycopg2-binary

ADD  app.py    ./
ADD  db.py     ./
ADD  static    ./static/
ADD  templates ./templates/

