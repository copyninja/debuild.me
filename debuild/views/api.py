from debuild import app
from monomoy.core import db
from monomoy.utils import JSONEncoder
from debuild.utils import db_find
from chatham.builders import Builder

import json
import datetime as dt
from flask import request

API_BASE = '/api'


def serialize(obj, allok):
    obj['status'] = 'ok' if allok else 'nokay'
    return json.dumps(obj, cls=JSONEncoder)


def api_abort(code, text):
    return serialize({
        'code': code,
        'text': text
    }, False)


def get_things():
    req = request.values
    builder = Builder(req['node'])
    builder.ping()
    return (req, builder)


def api_validate(keys):
    req = request.values
    for key in ['node', 'signature']:
        if key not in req:
            return api_abort(
                'forgotten-core-key',
                'Ah man, it looks like you forgot the core key '
                '"%s" in the request.' % (key)
            )

    for key in keys:
        if key not in req:
            return api_abort(
                'forgotten-view-key',
                'Ah man, it looks like you forgot the view-local key '
                '"%s" in the request.' % (key)
            )

    node = req['node']
    builder = Builder(node)
    if builder.validate_request(req['signature']):
        return None

    return api_abort(
        'bad-signature',
        'stupid signature value'
    )


@app.route('%s/token' % (API_BASE), methods=['GET', 'POST'])
def token():
    req = request.values
    if 'node' not in req:  # no signature.
        return api_abort('nsp-node', 'No such param: node')

    (req, builder) = get_things()
    key = builder.new_token()

    return serialize({
        "token": key
    }, True)


@app.route("%s/ping" % (API_BASE), methods=['GET', 'POST'])
def ping():
    resp = api_validate([])
    if resp: return resp
    (req, builder) = get_things()

    builder.ping()

    return serialize({
        'ping': 'pung'
    }, True)


@app.route("%s/result" % (API_BASE), methods=['GET', 'POST'])
def result():
    resp = api_validate(['data'])
    if resp: return resp
    (req, builder) = get_things()

    data = json.loads(req['data'])
    job = data['job']
    jobj = db_find('jobs', job)
    data['job'] = jobj['_id']

    if jobj['builder'] is None:
        return api_abort('bad-builder', 'bad builder node')

    if jobj['builder'] != builder._obj['_id']:  # XXX: Fixme
        return api_abort('bad-builder', 'foo bad builder node')

    check_id = db.checks.insert(data)

    return serialize({
        'check': check_id
    }, True)


@app.route("%s/finish" % (API_BASE), methods=['GET', 'POST'])
def finished():
    resp = api_validate(['data'])
    if resp: return resp
    (req, builder) = get_things()

    job = req['job']
    jobj = db_find('jobs', job)

    if jobj['builder'] is None:
        return api_abort('bad-builder', 'bad builder node')

    if jobj['builder'] != builder._obj['_id']:  # XXX: Fixme
        return api_abort('bad-builder', 'foo bad builder node')

    if jobj['finished']:
        return api_abort('job-wtf', 'job is already closed, dummy')

    jobj['finished'] = True
    jobj['finished_at'] = dt.datetime.now()
    db.jobs.update({"_id": jobj['_id']},
                   jobj,
                   True,
                   safe=True)

    return serialize({
        'action': 'job closed'
    }, True)
