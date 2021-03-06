from debuild import monomoy
from debuild.utils import db_find

from chatham.builders import (Builder, ChathamSanityException,
                              ChathamBuilderNotFound)
from chatham.queue import ChathamQueue

from monomoy.core import db
from monomoy.utils import JSONEncoder
from monomoy.archive import MonomoyArchive

import json
import datetime as dt
from flask import Blueprint, render_template, abort, request
from jinja2 import TemplateNotFound

api = Blueprint(
    'simple_page',
    __name__,
    template_folder='templates'
)

CHATHAM_QUEUE = ChathamQueue()

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
    try:
        builder = Builder(req['node'])
    except ChathamBuilderNotFound:
        abort(404)

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


@api.route("/package/<package_id>", methods=['GET', 'POST'])
def api_package(package_id):
    package = db_find('packages', package_id)
    if package is None:
        return api_abort('no-such-package',
                         'no such package: %s exists' % (package_id))

    archive = MonomoyArchive(monomoy['root'])
    path = archive.get_package_root(package['_id'])
    root = monomoy['archive']
    path = "%s/%s" % (root, path)

    dscs = filter(lambda x: x['name'].endswith('.dsc'),
                  package['changes']['Files'])
    files = ["%s/%s" % (path, x['name']) for x in dscs]

    return serialize({
        "files": files,
        "package": package['_id'],
        "package_obj": package
    }, True)


@api.route('/token', methods=['GET', 'POST'])
def token():
    req = request.values
    if 'node' not in req:  # no signature.
        return api_abort('nsp-node', 'No such param: node')

    (req, builder) = get_things()
    key = builder.new_token()

    return serialize({
        "token": key
    }, True)


@api.route("/ping", methods=['GET', 'POST'])
def ping():
    resp = api_validate([])
    if resp: return resp
    (req, builder) = get_things()

    builder.ping()

    return serialize({
        'ping': 'pung'
    }, True)


@api.route("/result", methods=['GET', 'POST'])
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


@api.route("/finish", methods=['GET', 'POST'])
def finished():
    resp = api_validate(['job'])
    if resp: return resp
    (req, builder) = get_things()

    job = req['job']
    jobj = db_find('jobs', job)

    builder.finish(jobj)

    return serialize({
        'action': 'job closed'
    }, True)


@api.route("/aquire", methods=['GET', 'POST'])
def aquire():
    resp = api_validate([])
    if resp: return resp
    (req, builder) = get_things()

    def _ret_job(job):
        return serialize({
            "job": job
        }, True)

    try:
        job = CHATHAM_QUEUE.next_job(builder)
    except ChathamSanityException as e:
        return api_abort(e.code, e.description)

    if job is None:
        return api_abort('no-jobs', 'no more jobs')

    return _ret_job(job)
