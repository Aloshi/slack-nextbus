from flask import Flask, request, abort, jsonify
import requests
from defusedxml.ElementTree import fromstring as parse_xml
import os  # for environ
import sys  # for stderr
import json
from collections import defaultdict
import datetime
import math

app = Flask("slack-nextbus")

VERIFICATION_TOKEN = os.environ.get('SLACK_NEXTBUS_TOKEN', None)
if not VERIFICATION_TOKEN:
    print("WARNING: Env variable 'VERIFICATION_TOKEN' not set. Less secure against requests not sent by Slack.", file=sys.stderr)

def validate_token(token):
    if VERIFICATION_TOKEN and not token == VERIFICATION_TOKEN:
        app.logger.debug("Rejecting request based on verification token")
        abort(406)


user_routes = defaultdict(list)

def add_user_route(user_id, name, agency_tag, agency_name, route_tag, route_name, stop_tag, stop_name, dir_tag, dir_name):
    del_user_route(user_id, name)
    user_routes[user_id].append((name, agency_tag, agency_name, route_tag, route_name, stop_tag, stop_name, dir_tag, dir_name))

def is_user_route(user_id, name):
    for data in user_routes[user_id]:
        if data[0] == name:
            return True
    return False

def iter_user_routes(user_id):
    return iter(user_routes[user_id])

def get_user_route(user_id, name):
    for data in user_routes[user_id]:
        if data[0] == name:
            return data
    raise KeyError()

def del_user_route(user_id, name):
    user_routes[user_id] = [data for data in user_routes[user_id] if data[0] != name]

@app.route("/", methods=['POST'])
def root():
    validate_token(request.form.get('token', None))

    user_id = request.form['user_id']

    args = request.form.get('text', '').split(' ')
    subcmd = args[0] if len(args) > 0 else None
    # app.logger.debug(request.form)
    # app.logger.debug("subcmd: " + str(subcmd));

    if subcmd == 'add':
        reserved = ['add', 'routes', 'remove', 'help']
        if len(args) != 2 or args[1] in reserved:
            return "Invalid route name. Usage: /nextbus add routename, where routename is a single word with no special characters or spaces."

        return handle_add(user_id, {'name': args[1]})
    elif subcmd == 'routes':
        return handle_routes(user_id)
    elif subcmd == 'remove':
        return handle_remove(user_id, args[0])
    elif is_user_route(user_id, args[0]):
        return handle_predictions(user_id, args[0])
    else:
        # TODO show help here
        text = ""
        if subcmd and subcmd != 'help':
            text += "Unknown command '" + subcmd + "'.\n\n"
        text += "Usage:\n"
        text += '  add _name_    - save a new route as _name_\n'
        text += '  remove _name_ - remove a saved route\n'
        text += '  routes        - list your saved routes\n'
        text += '  _name_        - view predictions for the next bus for a saved route\n'
        text += '\nMade with :heart: by Alec "Aloshi" Lofquist. Feedback welcome at <mailto:alces14@gmail.com|/dev/null>.'
        text += '\nNote: route data is currently not saved to disk. For now, your saved routes may be cleared as updates happen. Sorry!'
        
        return jsonify({
            "text": text
        })


def dictmerge(base, add):
    return {**base, **add}

def handle_add(user_id, payload):
    assert payload
    if payload.get('actions', None):
        data = json.loads(payload['actions'][0]['selected_options'][0]['value'])
        callback_id = payload.get('callback_id', None)
    else:
        data = payload  # this is a hack so the / handler can call this function with name

    name = data['name']
    agency_tag = data.get('a', None)
    agency_name = data.get('aname', None)
    route_tag = data.get('r', None)
    route_name = data.get('rname', None)
    stop_tag = data.get('s', None)
    stop_name = data.get('sname', None)
    dir_tag = data.get('dir', None)
    dir_name = data.get('dirname', None)

    agencies = nextbus_get_agencies()
    routes = nextbus_get_routes(agency_tag) if agency_tag else None
    stops, directions = nextbus_get_route_info(agency_tag, route_tag) if route_tag and agency_tag else (None, None)

    response = {
        "text": "Adding a new saved route named " + name + ".",
        "attachments": [
            {
                "text": "First, select a transportation agency.",
                "fallback": "agency list",
                "callback_id": "add_agency_selected",
                "actions": [
                    {
                        "name": "agency_list",
                        "text": "Bus agency...",
                        "type": "select",
                        "options": [ {"text": a[1] + " (" + a[2] + ")", "value": json.dumps({'name': name, 'a': a[0], 'aname': a[1]})} for a in agencies ],
                        "selected_options": [ {"text": agency_name, "value": json.dumps({'name': name, 'a': agency_tag, 'aname': agency_name})} ] if agency_tag else None
                    }
                ]
            }
        ]
    }

    if agency_tag:
        response['attachments'].append({
            "text": "Okay, let's pick a route from " + agency_name + ".",
            "fallback": "route list",
            "callback_id": "add_route_selected",
            "actions": [
                {
                    "name": "route_list",
                    "text": "Bus route...",
                    "type": "select",
                    "options": [ {"text": r[1], "value": json.dumps({'name': name, 'a': agency_tag, 'aname': agency_name, 'r': r[0], 'rname': r[1]}) } for r in routes ],
                    "selected_options": [ {"text": route_name, "value": json.dumps({'name': name, 'a': agency_tag, 'aname': agency_name, 'r': route_tag, 'rname': route_name})} ] if route_name else None
                }
            ]
        })

    if agency_tag and route_tag:
        option_groups = [ {"text": d[1], "options": [ {"text": stops[stag][0], "value": json.dumps(dictmerge(data, { 'dir': d[0], 'dirname': d[1], 's': stag, 'sname': stops[stag][0] }))} for stag in d[2] ] } for d in directions ]
        response['attachments'].append({
            "text": "Almost done! Finally, pick a direction and stop.",
            "fallback": "route info",
            "callback_id": "add_direction_selected",
            "actions": [
                {
                    "name": "route_info",
                    "text": "Bus stop...",
                    "type": "select",
                    "option_groups": option_groups
                }
            ]
        })

    if agency_tag and route_tag and dir_tag and stop_tag:
        # app.logger.debug("finished: " + agency_tag + ", " + route_tag + ", " + dir_tag + ", " + stop_tag)
        add_user_route(user_id, name, agency_tag, agency_name, route_tag, route_name, stop_tag, stop_name, dir_tag, dir_name)
        print(get_user_route(user_id, name))
        response = {
            "text": "All done! Registered " + agency_name + "'s " + route_name + " route, stop " + stop_name + ", as " + name + ".\nTry typing */nextbus " + name + "* to check the next bus!"
        }

    return jsonify(response)


def handle_routes(user_id):
    attachments = []
    for name, agency_tag, agency_name, route_tag, route_name, stop_tag, stop_name, direction_tag, direction_name in iter_user_routes(user_id):
        attachments.append({
            "fallback": name + " - " + agency_name + " - " + route_name + " - " + stop_name + " - " + direction_name,
            "title": name,
            "text": agency_name + "'s " + route_name + ", boarding at " + stop_name + ", headed towards " + direction_name + "."
        })

    if len(attachments) == 0:
        return jsonify({
            "text": "It looks like you don't have any saved routes. Type */nextbus add _routename_* to get started."
        })
    else:
        return jsonify({
            "text": "Here's a list of your currently saved routes.",
            "attachments": attachments
        })

def handle_remove(user_id, entered_name):
    if not is_user_route(entered_name):
        return "'" + entered_name + "' is not a saved route name."

    del_user_route(user_id, entered_name)
    return "Route '" + entered_name + "' removed successfully."

def time_left(prediction):
    epochTime = float(prediction[0]) / 1000.0
    arriveTime = datetime.datetime.fromtimestamp(epochTime)
    delta = arriveTime - datetime.datetime.utcnow()
    seconds = delta.total_seconds()
    if seconds < 10:
        return "A few seconds"
    elif seconds < 60:
        return "Less than a minute"
    elif seconds < 60*60:
        mins = math.floor(seconds / 60)
        return str(mins) + " minute" + ("s" if mins != 1 else "")
    else:
        hrs = math.floor(seconds / 60 / 60)
        mins = math.floor((seconds - hrs * 60 * 60) / 60)
        return str(hrs) + " hour" + ("s" if hrs != 1 else "") + ", " + str(mins) + " minute" + ("s" if mins != 1 else "")

def handle_predictions(user_id, entered_name):
    name, agency_tag, agency_name, route_tag, route_name, stop_tag, stop_name, dir_tag, dir_name = get_user_route(user_id, entered_name)
    predictions = nextbus_get_predictions(agency_tag, route_tag, stop_tag, dir_tag)

    if len(predictions) == 0:
        return "It doesn't seem like any buses are coming for " + entered_name + "! Oh dear. I hope you can walk."

    # TODO point out "last bus"

    attachments = []
    for prediction in predictions:
        attachments.append({
            "text": time_left(prediction),
            "text": "*" + time_left(prediction) + "* for " + route_name + " at " + stop_name,
        })

    return jsonify({
        "attachments": attachments
    })

@app.route("/action", methods=['POST'])
def action():
    payload = json.loads(request.form.get('payload', "{}"))
    validate_token(payload.get('token', None))

    callback_id = payload.get('callback_id', None)
    user_id = payload['user']['id']
    if callback_id.startswith('add_'):
        return handle_add(user_id, payload)
    elif callback_id == None:
        app.logger.info("No callback_id specified")
    else:
        app.logger.info("Unknown callback_id '" + callback_id + "'.")

    # unhandled
    app.logger.info(payload)
    abort(400)


NEXTBUS_ENDPOINT = "http://webservices.nextbus.com/service/publicXMLFeed"

# cache API calls with memoization, since everything except predictions rarely changes
memo_store = {}
from memoize import Memoizer
memo = Memoizer(memo_store)

@memo(max_age=60*60*8)  # 8 hours
def nextbus_get_agencies():
    """
    returns a list of (agencyTag, agencyTitle, regionTitle) tuples
    """
    response = requests.get(NEXTBUS_ENDPOINT, params={'command': 'agencyList'})
    response = parse_xml(response.text)

    agencies = []
    for agency in response.findall("agency"):
        agencies.append((agency.attrib['tag'], agency.attrib['title'], agency.attrib.get('regionTitle', None)))
    return agencies

@memo(max_age=60*60*2)  # 2 hours
def nextbus_get_routes(agency):
    """
    returns a list of (routeTag, routeTitle) tuples
    """
    response = requests.get(NEXTBUS_ENDPOINT, params={'command': 'routeList', 'a': agency})
    response = parse_xml(response.text)

    routes = []
    for route in response.findall("route"):
        routes.append((route.attrib['tag'], route.attrib['title']))
    return routes

@memo(max_age=60*60*2)  # 2 hours
def nextbus_get_route_info(agency, route):
    """
    returns (stops, directions), where:
        stops: {'stopTag': ('stopTitle', ), ...}
        directions: [ (directionTag, directionTitle, [stopTag1, stopTag2, ...]), ... ]
    """
    response = requests.get(NEXTBUS_ENDPOINT, params={'command': 'routeConfig', 'a': agency, 'r': route})
    response = parse_xml(response.text)

    route = response.find("route")
    stops = {}
    for stop in route.findall("stop"):
        stops[stop.attrib['tag']] = (stop.attrib['title'], )

    directions = []
    for direction in route.findall("direction"):
        dir_tag = direction.attrib['tag']
        dir_title = direction.attrib['title']
        dir_stops = []
        for stop in direction:
            dir_stops.append(stop.attrib['tag'])
        directions.append((dir_tag, dir_title, dir_stops))

    return stops, directions

@memo(max_age=2)  # 2 seconds
def nextbus_get_predictions(agency, route, stop, filterDirection):
    """
    returns a list of (epochTime, routeTitle, stopTitle) tuples
    """
    response = requests.get(NEXTBUS_ENDPOINT, params={'command': 'predictions', 'a': agency, 'r': route, 's': stop})
    response = parse_xml(response.text)

    predictions = []
    for predictionSet in response.findall("predictions"):
        for direction in predictionSet.findall("direction"):
            for prediction in direction.findall("prediction"):
                if prediction.attrib['dirTag'] != filterDirection:
                    continue
                epochTime = prediction.attrib['epochTime']
                routeTitle = predictionSet.attrib['routeTitle']
                stopTitle = predictionSet.attrib['stopTitle']
                predictions.append((epochTime, routeTitle, stopTitle))

    return predictions

