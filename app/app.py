import calendar
import json
import os
from datetime import date, timedelta
from functools import wraps

import requests
import yaml
from flask import Flask, Response, make_response, render_template, request
from sassutils.wsgi import SassMiddleware
from waitress import serve

from lib.git_parse import GitHub

from .charts import n_authors_by_location, n_posts_histogram, lifecycles
from .models import (Author, Event, GithubQueryLog, Month, Repo,
                     db, update_db_from_github)

app = Flask(__name__)
scss_manifest = {app.name: ('static/_scss', 'static/css')}
# Middleware
app.wsgi_app = SassMiddleware(app.wsgi_app, scss_manifest)

servers = {"production": os.environ.get('PROD'),
           "staging": os.environ.get('STAGING')}


# htpasswd configuration c/o http://flask.pocoo.org/snippets/8/
def check_auth(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    return username == os.environ['HTUSER'] and password == os.environ[
        'HTAUTH']


def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response('Could not verify your access level for that URL.\n'
                    'You have to login with proper credentials', 401,
                    {'WWW-Authenticate': 'Basic realm="Login Required"'})


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)

    return decorated


@app.context_processor
def load_data():
    update_db_from_github(refresh_timedelta=app.config['REFRESH_TIMEDELTA'])
    data = {
        'months': Month.query.filter(Month.authors),
        'current': Author.query.filter(Author.posts).all(),
        'formatted': date.today().strftime('%Y-%-m-%d'),
        'authorship_by_team': Author.authorship_histogram_by_team(),
        'authorship_by_loc': Author.authorship_histogram_by_loc(),
        'headcount': Author.query.count(),
    }
    (data['lifecycle_script'], data['lifecycle_div']) = ('', '')

    repo = Repo.get_fresh('18f', 'blog-drafts', refresh_threshhold_seconds=app.config['REFRESH_TIMEDELTA'].total_seconds())
    data['lifecycle'] = lifecycles(repo.json_summary_flattened())
    (data['authors_by_location_script'], data['authors_by_location_div']) = n_authors_by_location()
    (data['authorship_histogram_script'], data['authorship_histogram_div']) = n_posts_histogram()
    return dict(data=data)


@app.route("/")
@requires_auth
def index():
    return render_template("index.html")


@app.route("/manage/")
@requires_auth
def manage():
    error = None
    if request.args.get('rebuild'):
        server = request.args.get('rebuild')
        url = servers[server]
        headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
        payload = {"ref": "refs/heads/%s" % server}
        requests.post(url, data=json.dumps(payload), headers=headers)
    else:
        error = "No server to rebuild"
    return render_template("manage.html", error=error)
