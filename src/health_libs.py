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

from health_messages import Health_Message as HM
import health_protocol as HP
import ipaddr
import psutil
import sys
import subprocess
from hardware import matcher
import re
from commands import getstatusoutput as cmd
import threading
from sets import Set
import os


def is_in_network(left, right):
    'Helper for match_spec.'
    return ipaddr.IPv4Address(left) in ipaddr.IPv4Network(right)


def get_multiple_values(hw, level1, level2, level3):
    result = []
    temp_level2 = level2
    for entry in hw:
        if level2 == '*':
            temp_level2 = entry[1]
        if (level1 == entry[0] and temp_level2 == entry[1] and level3 == entry[2]):
            result.append(entry[3])
    return result


def get_value(hw_, level1, level2, level3):
    for entry in hw_:
        if (level1 == entry[0] and level2 == entry[1] and level3 == entry[2]):
            return entry[3]
    return None


def fatal_error(error):
    '''Report a shell script with the error message and log
       the message on stderr.'''
    HP.logger.error('%s\n' % error)
    sys.exit(1)


def run_sysbench_cpu(hw_, max_time, cpu_count, processor_num=-1):
    'Running sysbench cpu stress of a give amount of logical cpu'
    taskset = ''
    if (processor_num < 0):
        sys.stderr.write('Benchmarking all CPUs for '
                         '%d seconds (%d threads)\n' % (max_time, cpu_count))
    else:
        sys.stderr.write('Benchmarking CPU %d for %d seconds (%d threads)\n' %
                         (processor_num, max_time, cpu_count))
        taskset = 'taskset %s' % hex(1 << processor_num)

    cmds = '%s sysbench --max-time=%d --max-requests=10000000' \
           ' --num-threads=%d --test=cpu --cpu-max-prime=15000 run' \
           % (taskset, max_time, cpu_count)
    sysbench_cmd = subprocess.Popen(cmds, shell=True, stdout=subprocess.PIPE)

    for line in sysbench_cmd.stdout:
        if "total number of events" in line.decode():
            title, perf = line.decode().rstrip('\n').replace(' ', '').split(':')
            if processor_num == -1:
                hw_.append(('cpu', 'logical', 'loops_per_sec',
                            str(int(perf) / max_time)))
            else:
                hw_.append(('cpu', 'logical_%d' % processor_num,
                            'loops_per_sec', str(int(perf) / max_time)))


def get_available_memory():
    try:
        return psutil.virtual_memory().total
    except Exception:
        return psutil.avail_phymem()


def check_mem_size(block_size, cpu_count):
    dsplit = re.compile(r'\d+')
    ssplit = re.compile(r'[A-Z]+')
    unit = ssplit.findall(block_size)
    unit_in_bytes = 1
    if unit[0] == 'K':
        unit_in_bytes = 1024
    elif unit[0] == 'M':
        unit_in_bytes = 1024 * 1024
    elif unit[0] == 'G':
        unit_in_bytes = 1024 * 1024 * 1024

    size_in_bytes = unit_in_bytes * \
        int(dsplit.findall(block_size)[0]) * cpu_count
    if (size_in_bytes > get_available_memory()):
        return False

    return True


def stop_netservers(message):
    sys.stderr.write('Stopping netservers\n')
    status, output = cmd('pkill -9 netserver')


def start_bench_server(message, port_number):
    sys.stderr.write('Spawning netserver : (%s:%d)\n' % (message.my_peer_name, port_number))
    status, output = cmd('netserver -p %d' % port_number)


def get_my_ip_port(message):
    return get_ip_port(message, message.my_peer_name)


def get_ip_port(message, ip):
    port_number = 0
    for host in message.peer_servers:
        if host[1] == ip:
            port_number = message.ports_list[host[0]]
            break
    return port_number


def start_netservers(message):
    threads = {}
    sys.stderr.write('Starting %d netservers\n' % (len(message.peer_servers) - 1))
    for server in message.peer_servers:
        if message.my_peer_name != server[1]:
            port_number = get_ip_port(message, server[1])
            sys.stderr.write("-> %s : opening port %d for %s\n" % (message.my_peer_name, port_number, server[1]))
            threads[port_number] = threading.Thread(target=start_bench_server, args=tuple([message, port_number]))
            threads[port_number].start()


def add_netperf_suboption(sub_options, value):
    if len(sub_options) == 0:
        sub_options = "--"

    return "%s %s" % (sub_options, value)


def start_bench_client(ip, port, message):
    netperf_mode = "TCP_STREAM"
    unit = ""
    sub_options = ""

    if message.network_test == HM.BANDWIDTH:
        netperf_mode = "TCP_STREAM"
        unit = "-f m"
        if message.block_size != "0":
            sub_options = add_netperf_suboption(sub_options, "-m %s -M %s" % (message.block_size, message.block_size))
        if message.network_connection == HM.UDP:
            netperf_mode = "UDP_STREAM"
    elif message.network_test == HM.LATENCY:
            netperf_mode = "TCP_RR"
            if message.network_connection == HM.UDP:
                netperf_mode = "UDP_RR"

    sys.stderr.write("Starting bench client (%s) from %s to %s:%s\n" % (netperf_mode, message.my_peer_name, ip, port))
    cmd_netperf = subprocess.Popen(
        'netperf -l %d -H %s -p %s -t %s %s %s ' % (message.running_time, ip, port, netperf_mode, unit, sub_options),
        shell=True, stdout=subprocess.PIPE)

    return_code = cmd_netperf.wait()
    if return_code == 0:
        for line in cmd_netperf.stdout:
            stop = Set(['bytes', 'AF_INET', 'Local', 'Socket', 'Send', 'Throughput'])
            current = Set(line.split())
            if current.intersection(stop):
                continue
            elif (len(line.split()) < 4):
                continue
            else:
                if message.network_test == HM.BANDWIDTH:
                    message.hw.append(('network', 'bandwidth', '%s/%s' % (ip, port), str(line.split()[4])))
                elif message.network_test == HM.LATENCY:
                    message.hw.append(('network', 'requests_per_sec', '%s/%s' % (ip, port), str(line.split()[5])))
    else:
        sys.stderr.write("Netperf failed (err:%d) with the following errors:\n" % cmd_netperf.returncode)
        for line in cmd_netperf.stdout:
            sys.stderr.write(line)


def run_network_bench(message):
    run_netperf(message)


def run_netperf(message):
    threads = {}
    nb = 0
    sys.stderr.write('Benchmarking %s @%s for %d seconds\n' % (message.network_test, message.block_size, message.running_time))
    for server in message.peer_servers:
        if message.my_peer_name == server[1]:
            continue
        threads[nb] = threading.Thread(target=start_bench_client, args=[server[1], get_my_ip_port(message), message])
        threads[nb].start()
        nb += 1

    sys.stderr.write('Waiting %d bench clients to finish\n' % nb)
    for i in range(nb):
        threads[i].join()


def run_sysbench_memory(message):
    if message.mode == HM.FORKED:
        run_sysbench_memory_forked(message.hw, message.running_time, message.block_size, message.cpu_instances)
    else:
        run_sysbench_memory_threaded(message.hw, message.running_time, message.block_size, message.cpu_instances)


def run_sysbench_memory_threaded(hw_, max_time, block_size, cpu_count, processor_num=-1):
    'Running memtest on a processor'
    check_mem = check_mem_size(block_size, cpu_count)
    taskset = ''
    if (processor_num < 0):
        if check_mem is False:
            msg = ("Avoid Benchmarking memory @%s "
                   "from all CPUs, not enough memory\n")
            sys.stderr.write(msg % block_size)
            return
        sys.stderr.write('Benchmarking memory @%s from all CPUs '
                         'for %d seconds (%d threads)\n'
                         % (block_size, max_time, cpu_count))
    else:
        if check_mem is False:
            msg = ("Avoid Benchmarking memory @%s "
                   "from CPU %d, not enough memory\n")
            sys.stderr.write(msg % (block_size, processor_num))
            return

        sys.stderr.write('Benchmarking memory @%s from CPU %d'
                         ' for %d seconds (%d threads)\n'
                         % (block_size, processor_num, max_time, cpu_count))
        taskset = 'taskset %s' % hex(1 << processor_num)

    _cmd = '%s sysbench --max-time=%d --max-requests=100000000 ' \
           '--num-threads=%d --test=memory --memory-block-size=%s run'
    sysbench_cmd = subprocess.Popen(_cmd % (taskset, max_time,
                                            cpu_count, block_size),
                                    shell=True, stdout=subprocess.PIPE)

    for line in sysbench_cmd.stdout:
        if "transferred" in line:
            title, right = line.rstrip('\n').replace(' ', '').split('(')
            perf, useless = right.split('.')
            if processor_num == -1:
                hw_.append(('cpu', 'logical', 'threaded_bandwidth_%s'
                            % block_size, perf))
            else:
                hw_.append(('cpu', 'logical_%d' % processor_num, 'bandwidth_%s'
                            % block_size, perf))


def run_sysbench_memory_forked(hw_, max_time, block_size, cpu_count):
    'Running forked memtest on a processor'
    if check_mem_size(block_size, cpu_count) is False:
        cmd = 'Avoid benchmarking memory @%s from all' \
              ' CPUs (%d forked processes), not enough memory\n'
        sys.stderr.write(cmd % (block_size, cpu_count))
        return
    sys.stderr.write('Benchmarking memory @%s from all CPUs'
                     ' for %d seconds (%d forked processes)\n'
                     % (block_size, max_time, cpu_count))
    sysbench_cmd = '('
    for cpu in range(cpu_count):
        _cmd = 'sysbench --max-time=%d --max-requests=100000000 ' \
               '--num-threads=1 --test=memory --memory-block-size=%s run &'
        sysbench_cmd += _cmd % (max_time, block_size)

    sysbench_cmd.rstrip('&')
    sysbench_cmd += ')'

    global_perf = 0
    process = subprocess.Popen(
        sysbench_cmd, shell=True, stdout=subprocess.PIPE)
    for line in process.stdout:
        if "transferred" in line:
            title, right = line.rstrip('\n').replace(' ', '').split('(')
            perf, useless = right.split('.')
            global_perf += int(perf)

    hw_.append(('cpu', 'logical', 'forked_bandwidth_%s' %
               (block_size), str(global_perf)))


def generate_filename_and_macs(items):
    '''Generate a file name for a hardware using DMI information
    (product name and version) then if the DMI serial number is
    available we use it unless we lookup the first mac address.
    As a result, we do have a filename like :

    <dmi_product_name>-<dmi_product_version>-{dmi_serial_num|mac_address}'''

    # Duplicate items as it will be modified by match_* functions
    hw_items = list(items)
    sysvars = {}
    sysvars['sysname'] = ''

    matcher.match_spec(('system', 'product', 'name', '$sysprodname'),
                       hw_items, sysvars)
    if 'sysprodname' in sysvars:
        sysvars['sysname'] = re.sub(r'\W+', '', sysvars['sysprodname']) + '-'

    matcher.match_spec(('system', 'product', 'vendor', '$sysprodvendor'),
                       hw_items, sysvars)
    if 'sysprodvendor' in sysvars:
        sysvars['sysname'] += re.sub(r'\W+', '', sysvars['sysprodvendor']) + \
            '-'

    matcher.match_spec(('system', 'product', 'serial', '$sysserial'),
                       hw_items, sysvars)
    # Let's use any existing DMI serial number or take the first mac address
    if 'sysserial' in sysvars:
        sysvars['sysname'] += re.sub(r'\W+', '', sysvars['sysserial']) + '-'

    # we always need to have the mac addresses for pxemngr
    if matcher.match_multiple(hw_items,
                              ('network', '$eth', 'serial', '$serial'),
                              sysvars):
        sysvars['sysname'] += sysvars['serial'][0].replace(':', '-')
    else:
        HP.logger.error('unable to detect network macs')

    return sysvars


def check_mce_status(hw_):
    if os.path.isfile('/mcelog') and os.stat('/mcelog').st_size > 0:
        hw_.append(('system', 'platform', 'mce', 'True'))
    else:
        hw_.append(('system', 'platform', 'mce', 'False'))


def run_fio_job(message):
    mode = message.access
    if message.mode == HM.RANDOM:
        mode = "rand%s" % mode

    run_fio(message.hw, message.device.split(), mode, message.block_size, message.running_time - message.rampup_time, message.rampup_time)


def run_fio(hw_, disks_list, mode, io_size, time, rampup_time):
    filelist = [f for f in os.listdir(".") if f.endswith(".fio")]
    for myfile in filelist:
        os.remove(myfile)
    fio = "fio --ioengine=libaio --invalidate=1 --ramp_time=%d --iodepth=32 " \
          "--runtime=%d --time_based --direct=1 " \
          "--bs=%s --rw=%s" % (rampup_time, time, io_size, mode)

    global_disk_list = ''
    for disk in disks_list:
        if '/dev/' not in disk:
            disk = '/dev/%s' % disk
        # Flusing Disk's cache prior benchmark
        os.system("hdparm -f %s >/dev/null 2>&1" % disk)
        short_disk = disk.replace('/dev/', '')
        fio = "%s --name=MYJOB-%s --filename='%s'" % (fio, short_disk, disk)
        global_disk_list += '%s,' % short_disk
    global_disk_list = global_disk_list.rstrip(',')
    sys.stderr.write(
        'Benchmarking storage %s for %s seconds in '
        '%s mode with blocksize=%s\n' %
        (global_disk_list, time, mode, io_size))
    fio_cmd = subprocess.Popen(fio,
                               shell=True, stdout=subprocess.PIPE)
    current_disk = ''
    for line in fio_cmd.stdout:
        if ('MYJOB-' in line) and ('pid=' in line):
            # MYJOB-sda: (groupid=0, jobs=1): err= 0: pid=23652: Mon Sep  9
            # 16:21:42 2013
            current_disk = re.search('MYJOB-(.*): \(groupid', line).group(1)
            continue
        if ("read : io=" in line) or ("write: io=" in line):
            # read : io=169756KB, bw=16947KB/s, iops=4230, runt= 10017msec
            if (len(disks_list) > 1):
                mode_str = "simultaneous_%s_%s" % (mode, io_size)
            else:
                mode_str = "standalone_%s_%s" % (mode, io_size)

            try:
                perf = re.search('bw=(.*?B/s),', line).group(1)
            except Exception:
                sys.stderr.write('Failed at detecting '
                                 'bwps pattern with %s\n' % line)
            else:
                multiply = 1
                divide = 1
                if "MB/s" in perf:
                    multiply = 1024
                elif "KB/s" in perf:
                    multiply = 1
                elif "B/s" in perf:
                    divide = 1024
                try:
                    iperf = perf.replace(
                        'KB/s', '').replace('MB/s', '').replace('B/s', '')
                except Exception:
                    True
                hw_.append(('disk', current_disk, mode_str + '_KBps',
                            str(int(float(float(iperf) * multiply / divide)))))

            try:
                hw_.append(('disk', current_disk, mode_str + '_IOps',
                            re.search('iops=(.*),', line).group(1).strip(' ')))
            except Exception:
                sys.stderr.write('Failed at detecting iops '
                                 'pattern with %s\n' % line)
