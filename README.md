
## Introduction

MQRadar is a MQTT protocol client, designed to discover and configure MQTT devices. The principle of operation is very simple, it connects
to MQTT server and then listen to configured MQTT topics.
If received topic match configured pattern, trigger is launched.
Triggers can execute one of three actions:

- Publish messages and store possible reply with defined variable
- Execute shell command, it's return value also can be stored as cutom variable
- Generate file from Jinja2 template

Please read example configuration for more examples.

## Installation

Please note, that so far it have been tested only on Debian like distributions.

Basically MQradar has few dependencies:
```
# apt-get update && apt-get install python-yaml, python-mosquitto, python-jinja2
```

Now it's time to deploy:
```
# ./install.sh --user openhab --group openhab
# systemctl enable mqradar
# systemctl start mqradar
```

## License

This software is distributed under CreativeCommons BY-SA 4.0 license.
Full license text you can read on :

 - https://creativecommons.org/licenses/by-sa/4.0/legalcode

## Authors:
Adrian Brzezinski <adrian.brzezinski at adrb.pl>

