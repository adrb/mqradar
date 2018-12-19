
## Introduction

MQRadar is a MQTT protocol client, designed to discover and auto configure
MQTT devices. In conjunction with linux Zeroconf capabilities (Avahi and mDNS)
it allows ad-hoc configuration of IoT devices.

The principle of operation is rather simple, it connects to MQTT broker
and then listen to configured MQTT topics. If received topic match given regexp
pattern, trigger is launched. Triggers can execute one of three actions:

- Publish messages and store possible reply with defined variable
- Execute shell command, it's return value also can be stored as cutom variable
- Generate file from Jinja2 template

For more information please read enclosed configuration examples.

Please also note, that so far it have been tested only on Debian like
distributions.

## Integration with home automation systems

Enclosed configuration examples shows integration for devices with Tasmota [1]
firmware, managed by OpenHab2. But please note, that MQRadar can support
home automotion system or MQTT device of any kind.

For refrence about Tasmota firmware configuration please visit:
https://github.com/arendst/Sonoff-Tasmota/wiki/Commands

Also note that OpenHab2 needs "MQTT Binding" add-on installed and configured
connection to MQTT broker.

For other automation systems please refer to documentation and then
write your own MQRadar triggers and templates.
Patches with examples are welcome :)

## Using REST apis

Currently you can query REST apis via triggers curl commands.

## Example Mosquitto MQTT broker setup

Basically if you aim at effortless IoT devices configuration, your MQTT server
should allow connections without prompting for user name and passwords.
Thus "allow_anonymous" should be set to "true". But of course you pay the price
of lower security.

Your main configuration might look like:
```
listener 1883
listener 8883
cafile /etc/ssl/certs/ca_cert.pem
certfile /etc/ssl/certs/localhost_cert.pem
keyfile /etc/ssl/private/localhost_key.pem

allow_anonymous true
password_file /etc/mosquitto/password_file
acl_file /etc/mosquitto/acl_file
```

Despite enabled "allow_anonymous" option, you should also create at least
one administrative account with full rights.
Users and password can be set using command:

```
mosquitto_passwd /etc/mosquitto/password_file <put_your_username>
```

Tasmota devices with default configuration trying to log into MQTT broker
as "DVES_USER" with "DVES_PASS". So beside adding "admin" user, you may also
consider setting "DVES_USER".

Now the key part is proper setup in "acl_file". In the following example,
we allowed Read/Write access for Tasmota devices only to topics needed for
various status reports [2]. User admin is allowed to read or write any topic:

```
# read for anonymous users
pattern read cmnd/#
# r/w for anonymous users
topic stat/#
pattern tele/#

# R/W to all topics for admin
user admin
topic #
```

MQRadar should access MQTT broker as a "admin" user.
Please note that MQTT passwords are sent in cleartext, so for admin user
you should use encrypted connections, unless your are going to connect
from localhost.

## MQTT broker autodiscovery with Avahi mDNS responder

For automatic MQTT server discovery you should configure mDNS server.
Main diffrence between regular DNS and mDNS is that, mDNS uses multicast
IP (224.0.0.251 with 5353 port), instead of unicast IP with port 53.
That traffic should pass through firewall as well.

Lets install avahi daemon:
```
# apt-get install avahi-daemon libnss-mdns avahi-utils
```

If MQTT broker is on some other machine than "avahi-daemon", put it's
IP address and name to /etc/avahi/hosts file.

Avahi service configuration for MQTT in /etc/avahi/services/mqtt.service file:
```
<service-group>
  <name>MQTT broker</name>
  <service>
    <type>_mqtt._tcp</type>
    <port>1883</port>
    <host-name>your mqtt broker hostname</host-name>
  </service>
  <service>
    <type>_mqtts._tcp</type>
    <port>8883</port>
    <host-name>your mqtt broker hostname</host-name>
  </service>
</service-group>
```

Testing mDNS configuration:
```
# avahi-browse -tv _mqtt._tcp
# avahi-resolve -vn <your mqtt broker hostname>
```

On top of that you also need automatic IP address configuration.
You can consider one of two options:
- DHCP server, since every home router comes with preconfigured DHCP server,
it's recommended solution
- avahi-autoipd daemon for automatic IP address configuration from the
link-local 169.254.0.0/16 range

## MQRadar installation

MQradar has few dependencies which need to be installed:
```
# apt-get update && apt-get install python-yaml python-mosquitto python-jinja2
```

Now it's time to deploy. In this example MQRadar daemon is going to be run as "openhab" user:
```
# ./install.sh --user openhab --group openhab
# systemctl enable mqradar
# systemctl start mqradar
```

## Tasmota devices setup

When uploading Tasmota firmware to device, pay attention to the fact
that 'MQTT_HOST_DISCOVERY' flag, which enables mDNS autodiscovery,
is disabled for "minimal" and "basic" firmware flavours. Please see Tasmota
RELEASENOTES.md file for reference.

After initializing your device with Tasmota firmware, restart it
(or press button 4 times) to start an Access Point with IP address 192.168.4.1,
and a web server allowing WiFi configuration.
Basically it's all you need to do when adding new device with MQRadar daemon
enabled and configured Zeroconf discovery. However you should further customize
your device and at least change MQTT topic to avoid name conflicts [2].


## License

This software is distributed under CreativeCommons BY-SA 4.0 license.
Full license text you can read on :

 - https://creativecommons.org/licenses/by-sa/4.0/legalcode

## Authors:
Adrian Brzezinski <adrian.brzezinski at adrb.pl>

-- 
[1] https://github.com/arendst/Sonoff-Tasmota/

[2] https://github.com/arendst/Sonoff-Tasmota/wiki/MQTT-Overview

