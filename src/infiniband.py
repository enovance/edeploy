#
# Copyright (C) 2013 eNovance SAS <licensing@enovance.com>
#
# Author: Sebastien Badia <sebastien.badia@enovance.com>
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

from commands import getoutput as cmd
import re

def ib_card_drv():
  """Return an array of IB device (ex: ['mlx4_0'])."""
  return [cmd('ibstat -l')]

# {'node_guid': '0x0002c90300ea6840', 'sys_guid': '0x0002c90300ea6843',
# 'fw_ver': '2.11.500', 'device_type': 'MT4099', 'hw_ver': '0', 'nb_ports': '2'}
def ib_global_info(card_drv):
  """Return global info of a IB card in a python dict. (take in argument a card_drv (ex: mlx4_0))."""
  global_card_info = {}
  global_info = cmd('ibstat %s -s' %card_drv)
  for line in global_info.split('\n'):
    re_dev = re.search('CA type: (.*)', line)
    if re_dev is not None:
      global_card_info['device_type'] = re_dev.group(1)
    re_nb_ports = re.search('Number of ports: (.*)',line)
    if re_nb_ports is not None:
      global_card_info['nb_ports'] = re_nb_ports.group(1)
    re_fw_ver = re.search('Firmware version: (.*)',line)
    if re_fw_ver is not None:
      global_card_info['fw_ver'] = re_fw_ver.group(1)
    re_hw_ver = re.search('Hardware version: (.*)',line)
    if re_hw_ver is not None:
      global_card_info['hw_ver'] = re_hw_ver.group(1)
    re_node_guid = re.search('Node GUID: (.*)',line)
    if re_node_guid is not None:
      global_card_info['node_guid'] = re_node_guid.group(1)
    re_sys_guid = re.search('System image GUID: (.*)',line)
    if re_sys_guid is not None:
      global_card_info['sys_guid'] = re_sys_guid.group(1)
  return global_card_info

# {'base_lid': '0', 'port_guid': '0x0002c90300ea6841', 'rate': '40',
# 'physical_state': 'Down', 'sm_lid': '0', 'state': 'Down', 'lmc': '0'}
def ib_port_info(card_drv,port):
  """Return port infos of a IB card_drv in a python dict. (take in argument the card_drv name and the port number (ex: mlx4_0,1))"""
  port_infos = {}
  port_desc = cmd('ibstat %s %i' % (card_drv,port))
  for line in port_desc.split('\n'):
    re_state = re.search('State: (.*)', line)
    if re_state is not None:
      port_infos['state'] = re_state.group(1)
    re_phy_state = re.search('State: (.*)', line)
    if re_phy_state is not None:
      port_infos['physical_state'] = re_phy_state.group(1)
    re_rate = re.search('Rate: (.*)', line)
    if re_rate is not None:
      port_infos['rate'] = re_rate.group(1)
    re_blid = re.search('Base lid: (.*)', line)
    if re_blid is not None:
      port_infos['base_lid'] = re_blid.group(1)
    re_lmc = re.search('LMC: (.*)', line)
    if re_lmc is not None:
      port_infos['lmc'] = re_lmc.group(1)
    re_smlid = re.search('SM lid: (.*)', line)
    if re_smlid is not None:
      port_infos['sm_lid'] = re_smlid.group(1)
    re_pguid = re.search('Port GUID: (.*)', line)
    if re_pguid is not None:
      port_infos['port_guid'] = re_pguid.group(1)
  return port_infos

if __name__ == "__main__":
    _main()
