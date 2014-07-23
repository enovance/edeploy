#!/usr/bin/env python2
#
# Copyright (C) 2014 eNovance SAS <licensing@enovance.com>
#
# Author: Erwan Velu <erwan.velu@enovance.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from socket import socket, AF_INET, SOCK_STREAM
from health_messages import Health_Message as HM
from health_bench import Health_CPU as HCPU
import atexit
import health_protocol as HP
import logging
import sys

s = socket(AF_INET, SOCK_STREAM)
connected = False


def invalid_message(msg):
    HP.logger.error("%s is not a valid message for a client" %
                    msg.get_message_type())


def none(socket, msg):
    invalid_message(msg)


def start(socket, msg):
    HP.logger.info("Recevied START")


def stop(socket, msg):
    return


def completed(socket, msg):
    return


def connect(socket, msg):
    invalid_message(msg)


def disconnect(socket, msg):
    HP.logger.info("Disconnecting based on server request")
    sys.exit(0)


def ack(socket, msg):
    return


def nack(socket, msg):
    return


def cpu(socket, msg):
    HP.logger.info("Module CPU (%d sec)" % msg.running_time)
    action(socket, msg, HCPU(msg, socket, HP.logger))
    return


def storage(socket, msg):
    return


def memory(socket, msg):
    return


def network(socket, msg):
    return


def action(socket, msg, hb):
    handlers = {HM.NONE: hb.none,
                HM.STOP: hb.stop,
                HM.START: hb.start,
                HM.COMPLETED: hb.completed,
                HM.NOTCOMPLETED: hb.notcompleted,
                }

    HP.logger.info("Received action %s (%d)" %
                   (msg.get_action_type(), msg.action))
    handlers[msg.action]()


def module(socket, msg):
    handlers = {HM.NONE: none,
                HM.CPU: cpu,
                HM.STORAGE: storage,
                HM.MEMORY: memory,
                HM.NETWORK: network,
                }

    HP.logger.info("Received module %s (%d)" %
                   (msg.get_module_type(), msg.module))
    handlers[msg.module](socket, msg)


def connect_to_server(hostname):
    global s
    global connected
    try:
        s.connect((hostname, 20000))
    except:
        HP.logger.error("Server %s is not available, exiting" % hostname)
        sys.exit(1)

    connected = True
    HP.send_hm_message(s, HM(HM.CONNECT), True)
    while True:
        try:
            msg = HP.recv_hm_message(s)
        except:
            HP.logger.error("Broken socket, exiting !")
            break

        if not msg:
            continue

        if msg.message == HM.INVALID:
            HP.logger.error("Ignoring invalid message")
            continue

        if msg.message == HM.DISCONNECTED:
            connected = False
            HP.logger.error("Got disconnected from server, exiting")
            break

        msg.hw = eval(open(sys.argv[1]).read(-1))

        handlers = {HM.NONE: none,
                    HM.CONNECT: connect,
                    HM.DISCONNECT: disconnect,
                    HM.ACK: ack,
                    HM.NACK: nack,
                    HM.MODULE: module,
                    }

        HP.logger.info("Received %d" % msg.message)
        HP.logger.info(handlers)
        handlers[msg.message](s, msg)


def cleanup():
    global s
    global connected
    if connected is True:
        HP.send_hm_message(s, HM(HM.DISCONNECT), False)
        s.shutdown(1)
        s.close()

if __name__ == '__main__':
    HP.start_log('/var/log/health-client.log', logging.DEBUG)
    atexit.register(cleanup)
    if len(sys.argv) < 3:
        HP.logger.error("You must provide an hardware file and a host to "
                        "connect as argument")
        sys.exit(1)
    connect_to_server(sys.argv[2])
