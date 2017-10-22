import flask
import logging
import re
import splitit

logging.basicConfig(level=logging.DEBUG)

app = flask.Flask(__name__)

DEFAULT_QUERY_LIMIT = 25
DATE_RE = re.compile('^\d{4}-\d{2}-\d{2}$')

@app.route('/checks')
def describe_checks():
    data = flask.request.get_json()

    marker = data.get('marker')
    query_limit = data.get('limit', DEFAULT_QUERY_LIMIT)

    return flask.jsonify(splitit.get_checks(limit=query_limit, marker=marker))

@app.route('/check/<check_id>')
def describe_check(check_id):
    check = splitit.get_check(check_id)
    if not check:
        flask.abort(404)

    return flask.jsonify(check)

@app.route('/check', methods=['POST'])
def create_check():
    data = flask.request.get_json()

    if 'date' not in data:
        flask.abort(400)

    date = data['date']
    if not DATE_RE.match(date):
        flask.abort(400)

    if 'description' not in data:
        flask.abort(400)

    return flask.jsonify(splitit.put_check(date, data['description']))

def _validate_positive_int(data, key):
    if key in data and (type(data[key]) != int or data[key] < 0):
        log.warn('Invalid value for %s in %s', key, data)
        flask.abort(400)

def _validate_location(check, data):
    if not check:
        flask.abort(404)

    _validate_positive_int(data, 'tax_in_cents')
    _validate_positive_int(data, 'tip_in_cents')

def _validate_location_exists(check, location_id):
    found_location = False

    for location in check['locations']:
        if location['id'] == location_id:
            found_location = True
            break

    if not found_location:
        flask.abort(404)

@app.route('/check/<check_id>/location', methods=['POST'])
def create_location(check_id):
    data = flask.request.get_json()

    check = splitit.get_check(check_id)
    _validate_location(check, data)

    if 'name' not in data:
        flask.abort(400)

    for location in check['locations']:
        if location['name'] == data['name']:
            flask.abort(409)

    splitit.add_location(check, data['name'], data.get('tax_in_cents'), data.get('tip_in_cents'))

    return flask.jsonify(splitit.get_check(check_id))

@app.route('/check/<check_id>/location/<location_id>', methods=['PUT'])
def update_location(check_id, location_id):
    data = flask.request.get_json()

    check = splitit.get_check(check_id)
    _validate_location(check, data)

    _validate_location_exists(check, location_id)

    splitit.update_location(check, location_id, data.get('name'), data.get('tax_in_cents'), data.get('tip_in_cents'))

    return flask.jsonify(splitit.get_check(check_id))

@app.route('/check/<check_id>/location/<location_id>', methods=['DELETE'])
def remove_location(check_id, location_id):
    check = splitit.get_check(check_id)
    if not check:
        flask.abort(404)

    _validate_location_exists(check, location_id)

    splitit.delete_location(check, location_id)

    return flask.jsonify(splitit.get_check(check_id))
