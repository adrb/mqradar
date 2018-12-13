#!/bin/bash
#
# by Adrian Brzezinski <adrian.brzezinski at adrb.pl>
#

set -e

NAME=mqradar

PREFIXDIR="/usr/local"
CONFDIR="/etc/${NAME}"
RUNASUSER="root"
RUNASGROUP="root"

function usage() {
  cat << _EOF_

MQRadar install script

Usage: $0 [options]

  --prefix PREFIXDIR
    Set installation prefix directory
    Default: /usr/local

  --conf-path CONFDIR
    Configuration directory, relative to PREFIXDIR
    Default: /etc/${NAME}

  --user RUNASUSER
    Set username to run as. It's recommended to use non-privileged one
    Default: root

  --group RUNASGROUP
    Set the group to run as
    Default: root

_EOF_

  exit 1
}

function parse_args() {

  while [ -n "$1" ]; do
    case "$1" in
    --prefix)
      shift
      PREFIXDIR="$1"
      shift
      ;;
    --conf-path)
      shift
      CONFDIR="$1"
      shift
      ;;
    --user)
      shift
      RUNASUSER="$1"
      shift
      ;;
    --group)
      shift
      RUNASGROUP="$1"
      shift
      ;;
    *)
      echo "Unrecognized option: $1"
      usage
    ;;
    esac
  done
}

parse_args "$@"

CONFDIR="${PREFIXDIR}${CONFDIR}"

#
# Install
mkdir -p "${CONFDIR}"
cp -r config/* "${CONFDIR}/"
chown -R "${RUNASUSER}":"${RUNASGROUP}" "${CONFDIR}/"
chmod 0400 "${CONFDIR}/mqtt_creds.yaml" 

BINNAME="${PREFIXDIR}/sbin/${NAME}"
cp -a ${NAME}.py "${BINNAME}"

#
# Generate systemd startup script
SYSTEMDLIBDIR="${PREFIXDIR}/lib/systemd/system"
mkdir -p "${SYSTEMDLIBDIR}"
cat << _EOF_ > "${SYSTEMDLIBDIR}/${NAME}.service"
[Unit]
Description=MQTT provisioner service
After=network.target

[Service]
Type=simple
User=${RUNASUSER}
Group=${RUNASGROUP}
WorkingDirectory=${CONFDIR}
ExecStart=${BINNAME}
Restart=on-failure

[Install]
WantedBy=multi-user.target
_EOF_

ln -f -s "${SYSTEMDLIBDIR}/${NAME}.service" /etc/systemd/system/${NAME}.service
systemctl daemon-reload

