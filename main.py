from flask import Flask, request, abort, jsonify
import requests
from defusedxml.ElementTree import fromstring as parse_xml
import os  # for environ
import sys  # for stderr
import json

app = Flask("slack-nextbus")

VERIFICATION_TOKEN = os.environ.get('SLACK_NEXTBUS_TOKEN', None)
if not VERIFICATION_TOKEN:
    print("WARNING: Env variable 'VERIFICATION_TOKEN' not set. Less secure against requests not sent by Slack.", file=sys.stderr)

def validate_token(token):
    if VERIFICATION_TOKEN and not token == VERIFICATION_TOKEN:
        app.logger.debug("Rejecting request based on verification token")
        abort(406)

@app.route("/", methods=['POST'])
def root():
    validate_token(request.form.get('token', None))

    args = request.form.get('text', '').split(' ')
    subcmd = args[0] if len(args) > 0 else None
    app.logger.debug(request.form)
    # app.logger.debug("subcmd: " + str(subcmd));

    if subcmd == 'add':
        return build_add(None)
#        agencies = nextbus_get_agencies()
#        return jsonify({
#            "text": "Adding a new routeset.",
#            "attachments": [
#                {
#                    "text": "First, select a transportation agency.",
#                    "fallback": "agency list",
#                    "callback_id": "add_agency_selected",
#                    "actions": [
#                        {
#                            "name": "agency_list",
#                            "text": "Bus agency...",
#                            "type": "select",
#                            "options": [ {"text": a[1] + " (" + a[2] + ")" , "value": json.dumps({'a': a[0], 'name': a[1]})} for a in agencies ]
#                        }
#                    ]
#                }
#            ]
#        })
    else:
        # TODO show help here
        return jsonify({
            "text": "Unknown command '" + subcmd + "'."
        })

# user_routes = {}

def dictmerge(base, add):
    return {**base, **add}

def build_add(payload):
    if payload and payload.get('actions', None):
        data = json.loads(payload['actions'][0]['selected_options'][0]['value'])
        callback_id = payload.get('callback_id', None)
    else:
        callback_id = None
        data = {}

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
        "text": "Adding a new routeset.",
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
                        "options": [ {"text": a[1] + " (" + a[2] + ")", "value": json.dumps({'a': a[0], 'aname': a[1]})} for a in agencies ],
                        "selected_options": [ {"text": agency_name, "value": json.dumps({'a': agency_tag, 'aname': agency_name})} ] if agency_tag else None
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
                    "options": [ {"text": r[1], "value": json.dumps({'a': agency_tag, 'aname': agency_name, 'r': r[0], 'rname': r[1]}) } for r in routes ],
                    "selected_options": [ {"text": route_name, "value": json.dumps({'a': agency_tag, 'aname': agency_name, 'r': route_tag, 'rname': route_name})} ] if route_name else None
                }
            ]
        })

    if agency_tag and route_tag:
        option_groups = [ {"text": d[1], "options": [ {"text": stops[stag][0], "value": json.dumps(dictmerge(data, { 'dir': d[0], 'dirname': d[1], 's': stag, 'sname': stops[stag] }))} for stag in d[2] ] } for d in directions ]
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
        app.logger.debug("finished: " + agency_tag + ", " + route_tag + ", " + dir_tag + ", " + stop_tag)

    return jsonify(response)


@app.route("/action", methods=['POST'])
def action():
    payload = json.loads(request.form.get('payload', "{}"))
    validate_token(payload.get('token', None))
    callback_id = payload.get('callback_id', None)
    if callback_id == None:
        app.logger.info("No callback_id specified")
        app.logger.info(payload)
        abort(400)
    elif callback_id.startswith('add_'):
        return build_add(payload)
    else:
        app.logger.info("Unknown callback_id '" + callback_id + "'.")
        app.logger.info(payload)
        abort(400)


NEXTBUS_ENDPOINT = "http://webservices.nextbus.com/service/publicXMLFeed"

# TODO cache
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

