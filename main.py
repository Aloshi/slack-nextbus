from flask import Flask, request, abort, jsonify
import requests
from defusedxml.ElementTree import fromstring as parse_xml
import os  # for environ
import sys  # for stderr

app = Flask("slack-nextbus")

VERIFICATION_TOKEN = os.environ.get('SLACK_NEXTBUS_TOKEN', None)
if not VERIFICATION_TOKEN:
    print("WARNING: Env variable 'VERIFICATION_TOKEN' not set. Less secure against requests not sent by Slack.", file=sys.stderr)

def validate_token(token):
    if VERIFICATION_TOKEN and not token == VERIFICATION_TOKEN:
       abort(406)

@app.route("/", methods=['POST'])
def root():
    validate_token(request.form['token'])

    args = response.form.get('text', '').split(' ')
    subcmd = args[0] if len(args) > 0 else None

    if subcmd == 'add':
        return add()
    else:
        # TODO show help here
        return jsonify({
            "text": "Unknown command '" + subcmd + "'."
        })

user_routes = {}

# @app.route("/add", methods=['POST'])
def add():
    callback_id = request.form.get('callback_id', None)
    response = None
    if not callback_id:
        response = {"text": "echoing: " + request.form['text']}
    elif callback_id == 'agency_select':
        pass
    elif callback_id == 'route_select':
        pass
    elif callback_id == 'alias_select':
        pass
    else:
        abort(406)

    return jsonify(response)

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
    returns { "stops": [ (stopTag, stopTitle), ... ], "directions": [ (directionTag, directionTitle, [ stopTag1, stopTag2, ... ]) ] }
    """
    response = requests.get(NEXTBUS_ENDPOINT, params={'command': 'routeConfig', 'a': agency, 'r': route})
    response = parse_xml(response.text)

    route = response.find("route")
    stops = []
    for stop in route.findall("stop"):
        stops.append((stop.attrib['tag'], stop.attrib['title']))

    directions = []
    for direction in route.findall("direction"):
        dir_tag = direction.attrib['tag']
        dir_title = direction.attrib['title']
        dir_stops = []
        for stop in direction:
            dir_stops.append(stop.attrib['tag'])
        directions.append((dir_tag, dir_title, dir_stops))

    return { 'stops': stops, 'directions': directions }

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

