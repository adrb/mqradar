#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# MQRadar by adrian.brzezinski (at) adrb.pl
#
# Requires:
#   python-yaml, python-mosquitto, python-jinja2
# 
import sys, os, time, argparse, traceback, pprint
import string, re
import yaml, json
import mosquitto, ssl

# See http://jinja.pocoo.org/docs/2.10/api/
import jinja2, base64

import Queue, threading
import commands

DEBUG=0
J2ENV=None
# Workers Queue
WQ=None
# Workers Queue lock
WQ_LOCK = threading.Lock()
STOPWORKERS=False

class Worker(threading.Thread):
  def __init__(self, workerID, name):
    threading.Thread.__init__(self)
    self.workerID = workerID
    self.name = name
    self.payload = None

  def mqtt_on_message(self, client, userdata, message):
    self.payload = message.payload.decode('UTF-8')

  def mqtt_process(self, client, j2dict, trigger_action):

    sub_topic = mqr_render_string( trigger_action['subscribe']['topic'], j2dict)
    pub_topic = mqr_render_string( trigger_action['publish']['topic'], j2dict)
    pub_msg = mqr_render_string( trigger_action['publish']['message'], j2dict)

    client.subscribe(sub_topic, qos=1)
    client.publish(pub_topic, pub_msg, qos=1)

    # Wait for reply
    self.payload = None
    reply_timeout = 10
    if 'timeout' in trigger_action:
      reply_timeout = trigger_action['timeout']

    start_time = time.time()
    while self.payload is None and (time.time() - start_time) < reply_timeout:
      time.sleep(0.1)
      client.loop(1)

    client.unsubscribe(sub_topic)

    # if something goes wrong, stop whole trigger processing
    if self.payload is None:
      raise ValueError('Variable "%s" is None' % trigger_action['subscribe']['varname']) 

    value = mqr_value(trigger_action['subscribe']['type'], self.payload)

    print('INFO: Worker "%s" published MQTT "%s %s", recived: "%s %s"' %
        (self.name, pub_topic, pub_msg, sub_topic, value))

    return ( trigger_action['subscribe']['varname'], value )

  def shell_process(self, j2dict, trigger_action):

    cmd = mqr_render_string(trigger_action['command'], j2dict)

    value = commands.getoutput(cmd)
    value = mqr_value(trigger_action['type'], value)

    print('INFO: Worker "%s" executed shell command: %s, output: %s' %
        (self.name, cmd, value))

    return ( trigger_action['varname'], value)

  def template_process(self, j2dict, trigger_action):

    src_file = mqr_render_string(trigger_action['src'], j2dict)
    template = mqr_render_file(src_file, j2dict)
    dest_file = mqr_render_string(trigger_action['dest'], j2dict)

    print('INFO: Worker "%s" saving file "%s" from template "%s")\nvariables= %s\n' %
        (self.name, dest_file, src_file, pprint.pformat(j2dict)))

    with open(dest_file, "w") as f:
      f.write(template)

    if DEBUG > 1:
      print('DEBUG: Worker "%s" saved template to file "%s":\n%s\n' %
        (self.name, dest_file, template))

  def process(self, config, j2dict, trigger):

    for trigger_action in trigger:
      if DEBUG > 1: print('DEBUG: Worker "%s" processing...\ntrigger action= %s\n' % (self.name, pprint.pformat(trigger_action)))

      value = None

      if 'mqtt' in trigger_action:
        # Make new connection, so we don't interrupt main thread
        mc = mqtt_init(config, "%s_%s" % (CONFIG['mqttbroker']['client_id'], self.name) );
        mc.on_message = self.mqtt_on_message
        mc.connect(config['mqttbroker']['host'], config['mqttbroker']['port'])

        varname, value = self.mqtt_process(mc, j2dict, trigger_action['mqtt'])

        mc.disconnect()

      if 'shell' in trigger_action:
        varname, value = self.shell_process(j2dict, trigger_action['shell'])

      if value is not None:
        if DEBUG > 2: print('DEBUG: Worker "%s" updating variable "%s" = "%s"' % (self.name, varname, value))
        j2dict.update( { varname: value } )

      if 'template' in trigger_action:
        self.template_process(j2dict, trigger_action['template'])

  def run(self):
    if DEBUG > 2: print('DEBUG: Worker "%s": starting' % self.name)

    while not STOPWORKERS:
      WQ_LOCK.acquire()

      if WQ.empty():
        WQ_LOCK.release()
      else:
        config, j2dict, trigger = WQ.get()
        WQ_LOCK.release()

        try:
          self.process(config, j2dict, trigger)
        except Exception as e:
          print('ERROR: Worker "%s": %s\nconfig= %s\nvariables= %s\ntrigger= %s\n'
            % (self.name, e, pprint.pformat(config), pprint.pformat(j2dict), pprint.pformat(trigger)))
          if DEBUG > 1: print('ERROR TRACE: %s' % traceback.format_exc())

      time.sleep(1)
    if DEBUG > 1: print('DEBUG: Finishing "%s"' % self.name)

#
# Main thread
#
def filter_remove_punctation( s ):
  return str(s).translate(None,string.punctuation)

def filter_pathescape( s ):
  return str(s).translate(string.maketrans('./\\','-__'))

def mqr_value(value_type, value):
  if value_type == 'json':
    return json.loads(value)
  return str(value)

def mqr_render_file(file_path, j2dict=None):
  return str(J2ENV.get_template(file_path).render(j2dict))

def mqr_render_string(template_string, j2dict=None):
  return str(J2ENV.from_string(template_string).render(j2dict))

def mqtt_on_log(client, userdata, level, buf):
  if DEBUG > 2: print("DEBUG: %s" % buf)

def mqtt_on_connect(client, userdata, rc):
  if rc != 0:
    print("ERROR: Can't connect to MQTT broker: %d" % rc )
    return

  if DEBUG and rc == 0:
    print("DEBUG: Connected to MQTT broker")

  for sub in userdata['mqttbroker']['subscribe']:
    client.subscribe(sub['topic'])
    if DEBUG: print('DEBUG: Subscribed to: %s' % sub['topic'])

def mqtt_on_message(client, userdata, message):
  if DEBUG > 1:
    print('DEBUG: Received message: %s %s' % (message.topic, str(message.payload)))

  for trigger in userdata['triggers']:
    tre = re.compile(trigger['topic_pattern'])

    if tre.match(message.topic):
      try:

        # Prepare variables for jinja2 template
        regroups = []
        regroups.append(message.topic)
        regroups += tre.match(message.topic).groups()

        j2dict = userdata['vars'].copy()
        j2dict.update( { 'trigger_topic': regroups } )
        j2dict['trigger_payload'] = mqr_value(trigger['payload_type'], message.payload.decode('UTF-8'))

        # Generate trigger config
        trigger_file = mqr_render_string(trigger['trigger'], j2dict)
        with open(trigger_file, 'r') as f:
          trigger_conf =  yaml.load(f)

        print('INFO: Trigger "%s" fired by message: %s %s' % (trigger_file, message.topic, message.payload.decode('UTF-8')))

        # put trigger on the queue to process
        WQ_LOCK.acquire()
        WQ.put((userdata.copy(), j2dict.copy(), trigger_conf))
        WQ_LOCK.release()

      except Exception as e:
        print('ERROR: Processing MQTT message: %s\ntopic= %s\npayload= %s\ntrigger= %s\n'
            % (e, str(message.topic), pprint.pformat(message.payload), pprint.pformat(trigger)))
        if DEBUG > 1: print('ERROR TRACE: %s' % traceback.format_exc())
        continue

# Initialize MQTT client
def mqtt_init(config, client_id):
  try:
    if 'credentials_file' in config['mqttbroker']:
      with open(config['mqttbroker']['credentials_file'], 'r') as f:
        credentials = yaml.load(f)
  except IOError as e:
     print("ERROR: %s (%s) - %s" % (e.strerror, e.errno, e.filename))
     sys.exit(1)

  mc = mosquitto.Mosquitto(client_id, clean_session=True, userdata=config)
  if 'credentials' in locals():
    mc.username_pw_set(credentials['user'], credentials['pwd'])

  if config['mqttbroker']['use_tls'] and strlen(config['mqttbroker']['ca_certs']) > 1:
    mc.tls_set(config['mqttbroker']['ca_certs'], tls_version=ssl.PROTOCOL_TLSv1_2)
    mc.tls_insecure_set(config['mqttbroker']['tls_insecure'])

  return mc

def parse_args():
  parser = argparse.ArgumentParser(description='MQtt Radar by adrian.brzezinski (at) adrb.pl')
  parser.add_argument('-c', '--config', help='Yaml config file', default='config.yaml')
  parser.add_argument('-d', '--debug', help='Set debugging level', action='count')

  return parser.parse_args()

if __name__ == '__main__':

  args = parse_args()
  DEBUG = args.debug

  # Initialize jinja2 templating
  J2ENV = jinja2.Environment(loader=jinja2.FileSystemLoader(os.getcwd()), trim_blocks=True)
  J2ENV.filters['b64decode'] = base64.b64decode
  J2ENV.filters['b64encode'] = base64.b64encode
  J2ENV.filters['remove_punctation'] = filter_remove_punctation
  J2ENV.filters['pathescape'] = filter_pathescape

  # Load config file
  try:
    with open(args.config, 'r') as f:
      CONFIG = yaml.load(f)

  except IOError as e:
    print("ERROR: %s (%s) - %s" % (e.strerror, e.errno, e.filename))
    sys.exit(1)

  # Initialize mqtt connection
  mc = mqtt_init(CONFIG, CONFIG['mqttbroker']['client_id']);
  mc.on_connect = mqtt_on_connect
  mc.on_message = mqtt_on_message
  mc.on_log = mqtt_on_log
  mc.connect(CONFIG['mqttbroker']['host'], CONFIG['mqttbroker']['port'])

  # Initialize workers queue
  workers = []
  WQ = Queue.Queue(CONFIG['workers_max_queue'])
  # Create new threads
  for workerID in xrange(CONFIG['worker_threads']):
    worker = Worker(workerID, "%d" % workerID)
    worker.daemon = True   # exit main thread without joining remaining threads
    worker.start()
    workers.append(worker)
    workerID += 1

  if DEBUG: print('DEBUG: MQRadar initialized...')
  mc.loop_forever()

#  STOPWORKERS=True
#  for worker in workers:
#    worker.join()

