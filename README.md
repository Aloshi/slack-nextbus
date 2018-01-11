# NextBus integration for Slack

This is a simple Python script that integrates NextBus time listings into Slack.
Users can register a list of routes they are interested in and query the bus predictions API with one command.

# Setup

Install from requirements.txt with pip, then run `flash main.py --port 8080`. Then set up an HTTPS reverse proxy (between port 443 and port 8080), since Slack will only talk to servers with a valid SSL certificate.

Finally, create a new Slack App using the Slack website and point it at your server. You'll need to set up a slash command pointed to `/` and enable "interactive components" and point it at `/action`.

# TODO

* Persist saved route data to disk somehow
* Show colors for routes (already supplied by the nextbus API)
* Support adding multiple routes under one name (i.e. student services + Beyer hall)



Alec "Aloshi" Lofquist

https://aloshi.com
