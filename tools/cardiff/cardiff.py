#!/usr/bin/env python
#
#  Copyright (C) 2013-2015 eNovance SAS <licensing@enovance.com>
#  Author: Erwan Velu  <erwan@enovance.com>
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

import os
import sys
import getopt
import check
import utils
import compare_sets
import shutil
import numpy
import glob


def print_help():
    print '''cardiff

-h --help                           : Print this help
-p <pattern> or --pattern <pattern> : A pattern in regexp to select input files
-o <dir>     or --output_dir <dir>  : Output directory if pattern is defined
                                      this directory will report the diff files
                                      if systems does not match
-l <level>   or --log-level <level> : Show only the log levels selected
                                    :   level is a comma separated list of the
                                      following levels
                                    :   INFO, ERROR, WARNING, SUMMARY, DETAIL
                                    :   SUMMARY is the default view
-g <group> or --group <group>       : Select the target group for DETAIL level
                                        (supports regexp)
-c <cat>   or --category <cat>      : Select the target category for DETAIL
                                         level (supports regexp)
-i <item>  or --item <item>         : Select the item for select group with
                                        DETAIL level (supports regexp)
-I <list>  or --ignore <list>       : Disable the grouping segregration on the
                                        coma separated list of components :
                                        cpu, hpa, disk, firmware, memory,
                                        network, system, megaraid, ahci, ipmi
-r <dir1>[,<dir2>,<dir3>, ...]      : Perform the rampup analysis on directory
                                        containing results from dahc.
                                        In such mode, no need to provide
                                        a pattern. Print the compared results
                                        if several dirs are separated by
                                        a comma

Examples:
$ cardiff.py -p 'sample/*.hw' -l DETAIL -g '1' -c 'loops_per_sec' \
    -i 'logical_1.*'
$ cardiff.py -p 'sample/*.hw' -l DETAIL -g '1' -c 'standalone_rand.*_4k_IOps' \
    -i 'sd.*'
$ cardiff.py -p 'sample/*.hw' -l DETAIL -g '0' -c '1G' -i '.*'
$ cardiff.py -p '*hw' -I disk,cpu -o plop
$ cardiff.py -r '/var/lib/edeploy/health/dahc/cpu_load/2014_09_15-12h17'
'''


def compare_disks(global_params, bench_values, unique_id, systems_groups):
    systems = utils.find_sub_element(bench_values, unique_id, 'pdisk')
    groups = check.physical_megaraid_disks(global_params, systems, unique_id)
    compare_sets.compute_similar_hosts_list(
        systems_groups,
        compare_sets.get_hosts_list_from_result(groups))
    systems = utils.find_sub_element(bench_values, unique_id, 'disk')
    groups = check.physical_hpa_disks(global_params, systems, unique_id)
    compare_sets.compute_similar_hosts_list(
        systems_groups,
        compare_sets.get_hosts_list_from_result(groups))
    groups = check.logical_disks(global_params, systems, unique_id)
    compare_sets.compute_similar_hosts_list(
        systems_groups,
        compare_sets.get_hosts_list_from_result(groups))


def compare_type(type_, check_func, global_params,
                 bench_values, unique_id, systems_groups):
    systems = utils.find_sub_element(bench_values, unique_id, type_)
    groups = check_func(global_params, systems, unique_id)
    compare_sets.compute_similar_hosts_list(
        systems_groups,
        compare_sets.get_hosts_list_from_result(groups))


def group_systems(global_params, bench_values, unique_id,
                  systems_groups, ignore_list):
    for name, func in (('hpa', check.hpa),
                       ('megaraid', check.megaraid),
                       ('ahci', check.ahci),
                       ('ipmi', check.ipmi),
                       ('system', check.systems),
                       ('firmware', check.firmware),
                       ('memory', check.memory_timing),
                       ('network', check.network_interfaces),
                       ('cpu', check.cpu)):
        if name not in ignore_list:
            compare_type(name, func, global_params, bench_values,
                         unique_id, systems_groups)


def compare_performance(bench_values, unique_id, systems_groups, detail,
                        rampup_value=0, current_dir=""):
    for group in systems_groups:
        systems = utils.find_sub_element(bench_values, unique_id,
                                         'disk', group)
        check.logical_disks_perf(systems, unique_id,
                                 systems_groups.index(group),
                                 detail, rampup_value, current_dir)

    for group in systems_groups:
        systems = utils.find_sub_element(bench_values, unique_id, 'cpu', group)
        check.cpu_perf(systems, unique_id, systems_groups.index(group), detail,
                       rampup_value, current_dir)

    for group in systems_groups:
        systems = utils.find_sub_element(bench_values, unique_id, 'cpu', group)
        check.memory_perf(systems, unique_id, systems_groups.index(group),
                          detail, rampup_value, current_dir)

    for group in systems_groups:
        systems = utils.find_sub_element(bench_values, unique_id, 'network',
                                         group)
        check.network_perf(systems, unique_id, systems_groups.index(group),
                           detail, rampup_value, current_dir)


def analyze_data(global_params, pattern, ignore_list, detail, rampup_value=0,
                 max_rampup_value=0, current_dir=""):
    if rampup_value > 0:
        pattern = pattern + "*.hw"

    # Extracting regex and path
    path = os.path.dirname(pattern)
    if not path:
        path = "."
    else:
        pattern = os.path.basename(pattern)

    if not os.path.isdir(path):
        print "Error: the path %s doesn't exists !" % path
        sys.exit(2)

    health_data_file = utils.find_file(path, pattern)
    if len(health_data_file) == 0:
        print "No log file found with pattern %s!" % pattern
        sys.exit(1)
    else:
        if rampup_value == 0:
            print "### %d files Selected with pattern '%s' ###" % \
                (len(health_data_file), pattern)
        else:
            print "########## Rampup: %d / %d hosts #########" % \
                (rampup_value, max_rampup_value)

    # Extract data from the hw files
    bench_values = []
    for health in health_data_file:
        bench_values.append(eval(open(health).read()))

    if rampup_value > 0:
        unique_id = 'uuid'
    else:
        unique_id = 'serial'

    # Extracting the host list from the data to get
    # the initial list of hosts. We have here a single group
    # with all the servers
    systems_groups = []
    systems_groups.append(utils.get_hosts_list(bench_values, unique_id))

    # Let's create groups of similar servers
    if rampup_value == 0:
        group_systems(global_params, bench_values, unique_id, systems_groups,
                      ignore_list)
        compare_sets.print_systems_groups(systems_groups)

    # It's time to compare performance in each group
    compare_performance(bench_values, unique_id, systems_groups, detail,
                        rampup_value, current_dir)
    print "##########################################"
    print
    return bench_values


def compute_deviance_percentage(metric):
    # If we have a single item
    # checking the variance is useless
    array = numpy.array(metric)
    if len(metric) == 1:
        return 0
    return numpy.std(array) / numpy.mean(array) * 100


def compute_metric(current_dir, rampup_value, metric, metric_name):
    array = numpy.array(metric)
    mean_group = numpy.mean(metric)
    deviance_percentage = compute_deviance_percentage(metric)
    deviance = numpy.std(array)
    utils.write_gnuplot_file(current_dir+"/%s-mean.plot" % metric_name,
                             rampup_value, mean_group)
    utils.write_gnuplot_file(
        current_dir + "/%s-deviance_percentage.plot" % metric_name,
        rampup_value, deviance_percentage)
    utils.write_gnuplot_file(
        current_dir + "/%s-deviance.plot" % metric_name,
        rampup_value, deviance)


def compute_metrics(current_dir, rampup_value, metrics):
    duration = []
    start_lag = []
    for value in metrics["duration"]:
        duration.append(metrics["duration"][value])
    for value in metrics["start_lag"]:
        start_lag.append(float(metrics["start_lag"][value]) * 1000)  # in ms

    compute_metric(current_dir, rampup_value, duration, "job_duration")
    compute_metric(current_dir, rampup_value, start_lag, "jitter")


def do_plot(current_dir, gpm_dir, main_title, subtitle, name, unit, titles,
            titles_order, expected_value=""):
    filename = current_dir+"/"+name+".gnuplot"
    with open(filename, "a") as f:
        shutil.copyfile("%s/graph2D.gpm" % gpm_dir,
                        "%s/graph2D.gpm" % current_dir)
        with open("%s/graph2D.gpm" % current_dir, "a") as myfile:
            column = 2
            for title in titles_order:
                if column == 2:
                    myfile.write(
                        "plot '$2' using %d:xtic(1) "
                        "with linespoints title '%s'" %
                        (column, titles[title]))
                else:
                    myfile.write(",\\\n'$2' using %d:xtic(1) "
                                 "with linespoints title '%s'" %
                                 (column, titles[title]))
                column = column + 1
            if expected_value:
                myfile.write(",\\\n %.2f w l ls 1 ti "
                             "'Expected value (%.2f)'" %
                             (expected_value, expected_value))
            myfile.write("\nset output '$4-smooth.png'\n")
            column = 2
            for title in titles_order:
                if column == 2:
                    myfile.write("plot '$2' using %d:xtic(1) "
                                 "smooth csplines title '%s'" %
                                 (column, titles[title]))
                else:
                    myfile.write(",\\\n'$2' using %d:xtic(1) "
                                 "smooth csplines title '%s'" %
                                 (column, titles[title]))
                column = column + 1
            if expected_value:
                myfile.write(",\\\n %.2f w l ls 1 ti "
                             "'Expected value (%.2f)'" %
                             (expected_value, expected_value))
            column = 2
            myfile.write("\nset output '$4-trend.png'\n")
            for title in titles_order:
                if column == 2:
                    myfile.write("plot '$2' using %d:xtic(1) "
                                 "smooth bezier title '%s'" %
                                 (column, titles[title]))
                else:
                    myfile.write(",\\\n'$2' using %d:xtic(1) "
                                 "smooth bezier title '%s'" %
                                 (column, titles[title]))
                column = column + 1
            if expected_value:
                myfile.write(",\\\n %.2f w l ls 1 ti "
                             "'Expected value (%.2f)'" %
                             (expected_value, expected_value))
            myfile.write("\n")

        f.write("call \'%s/graph2D.gpm\' \'%s' \'%s\' \'%s\' \'%s\' \'%s\' "
                "\'%s\'\n" % (current_dir, main_title, subtitle,
                              current_dir+"/"+name+".plot",
                              name, current_dir+name, unit))
    try:
        os.system("gnuplot %s" % filename)
    except:
        pass


def extract_hw_info(hw, level1, level2, level3):
    result = []
    temp_level2 = level2
    for entry in hw:
        if level2 == '*':
            temp_level2 = entry[1]
        if (level1 == entry[0] and temp_level2 == entry[1] and
                level3 == entry[2]):
            result.append(entry[3])
    return result


def is_virtualized(bench_values):
    if "hypervisor" in extract_hw_info(bench_values[0],
                                       'cpu', 'physical_0',
                                       'flags')[0]:
        return "virtualized"
    return ""


def plot_results(current_dir, rampup_values, job, metrics, bench_values,
                 titles, titles_order):
    gpm_dir = "./"
    context = ""
    bench_type = job
    unit = {}
    expected_value = {}
    expected_value["job_duration-mean"] = metrics["bench"]["runtime"]
    unit["job_duration-mean"] = "seconds (s)"
    unit["job_duration-deviance"] = unit["job_duration-mean"]
    unit["job_duration-deviance_percentage"] = "% of deviance (vs mean perf)"
    unit["jitter-mean"] = "milliseconds (ms)"
    unit["jitter-deviance"] = unit["jitter-mean"]
    unit["jitter-deviance_percentage"] = "% of deviance (vs mean perf)"
    if "cpu" in job:
        unit["deviance"] = "loops_per_sec"
        unit["deviance_percentage"] = "% of deviance (vs mean perf)"
        unit["mean"] = unit["deviance"]
        unit["sum"] = unit["deviance"]
        context = "%d cpu load per host" % metrics["bench"]["cores"]
        bench_type = "%s power" % job
    if "memory" in job:
        unit["deviance"] = "MB/sec"
        unit["deviance_percentage"] = "% of deviance (vs mean perf)"
        unit["mean"] = unit["deviance"]
        unit["sum"] = unit["deviance"]
        bench_type = "%s bandwidth" % job
        context = "%d %s threads per host, blocksize=%s" % \
                  (metrics["bench"]["cores"],
                   metrics["bench"]["mode"],
                   metrics["bench"]["block-size"])
    if "network" in job:
        if metrics["bench"]["mode"] == "bandwidth":
            unit["deviance"] = "Mbit/sec"
            bench_type = "%s %s bandwidth" % \
                         (job, metrics["bench"]["connection"])
        elif metrics["bench"]["mode"] == "latency":
            unit["deviance"] = "RRQ/sec"
            bench_type = "%s %s latency" % \
                         (job, metrics["bench"]["connection"])
        unit["deviance_percentage"] = "% of deviance (vs mean perf)"
        unit["mean"] = unit["deviance"]
        unit["sum"] = unit["deviance"]
        context = "%d %s threads per host, blocksize=%s" % \
                  (metrics["bench"]["cores"],
                   metrics["bench"]["mode"],
                   metrics["bench"]["block-size"])
    if "storage" in job:
        unit["deviance"] = "KB/sec"
        unit["deviance_percentage"] = "% of deviance (vs mean perf)"
        unit["mean"] = unit["deviance"]
        unit["sum"] = unit["deviance"]
        bench_type = "%s bandwidth" % job
        context = "%d %s threads per host, blocksize=%s, " \
                  "mode=%s, access=%s" % \
                  (metrics["bench"]["cores"],
                   metrics["bench"]["mode"],
                   metrics["bench"]["block-size"],
                   metrics["bench"]["mode"],
                   metrics["bench"]["access"])
    for kind in unit:
        title_appendix = ""
        if len(titles.keys()) > 1:
            for key in titles_order:
                if not title_appendix:
                    title_appendix = "\\n %s" % titles[key]
                else:
                    title_appendix = "%s vs %s" % (title_appendix, titles[key])
        else:
            title_appendix = metrics["bench"]["title"]
        title = "Study of %s %s from %d to %d hosts (step=%d) : %s" % \
                (bench_type, kind, min(rampup_values),
                 max(rampup_values), metrics["bench"]["step-hosts"],
                 title_appendix)
        total_disk_size = 0
        for disk_size in extract_hw_info(bench_values[0][0], 'disk', '*',
                                         'size'):
            total_disk_size = total_disk_size + int(disk_size)
        system = "HW per %s host: %s x %s CPUs, %d MB of RAM, %d "  \
                 "disks : %d GB total, %d NICs\\n OS : %s running " \
                 "kernel %s, cpu_arch=%s" % \
                 (is_virtualized(bench_values[0]),
                  extract_hw_info(bench_values[0][0], 'cpu',
                                  'physical', 'number')[0],
                  extract_hw_info(bench_values[0][0], 'cpu',
                                  'physical_0', 'product')[0],
                  int(extract_hw_info(bench_values[0][0], 'memory',
                                      'total', 'size')[0]) / 1024 / 1024,
                  int(extract_hw_info(bench_values[0][0], 'disk',
                                      'logical', 'count')[0]),
                  total_disk_size,
                  len(extract_hw_info(bench_values[0][0], 'network',
                                      '*', 'serial')),
                  extract_hw_info(bench_values[0][0], 'system',
                                  'os', 'version')[0],
                  extract_hw_info(bench_values[0][0], 'system',
                                  'kernel', 'version')[0],
                  extract_hw_info(bench_values[0][0], 'system',
                                  'kernel', 'arch')[0])

        subtitle = "\\nBenchmark setup : %s, runtime=%d seconds, %d "
        "hypervisors with %s scheduling\\n%s" % \
            (context, metrics["bench"]["runtime"],
             len(metrics["affinity"]), metrics["bench"]["affinity"],
             system)

        if kind in expected_value:
            do_plot(current_dir, gpm_dir, title, subtitle, kind, unit[kind],
                    titles, titles_order, expected_value[kind])
        else:
            do_plot(current_dir, gpm_dir, title, subtitle, kind, unit[kind],
                    titles, titles_order)


def main(argv):
    pattern = ''
    rampup = ""
    rampup_dirs = []
    rampup_values = ''
    ignore_list = ''
    detail = {'category': '', 'group': '', 'item': ''}
    global_params = {}
    try:
        opts, args = getopt.getopt(argv[1:], "hp:l:g:c:i:I:r:o:",
                                   ['pattern', 'log-level', 'group',
                                    'category', 'item', "ignore",
                                    "rampup", "output_dir"])
    except getopt.GetoptError:
        print "Error: One of the options passed " \
            "to the cmdline was not supported"
        print "Please fix your command line or read the help (-h option)"
        sys.exit(2)

    utils.print_level = int(utils.Levels.SUMMARY)

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            print_help()
            sys.exit(0)
        elif opt in ("-p", "--pattern"):
            pattern = arg
            pattern = pattern.replace('\\', '')
        elif opt in ("-r", "--rampup"):
            rampup = arg
            rampup = rampup.replace('\\', '')
        elif opt in ("-l", "--log-level"):
            if "list" in arg:
                print_help()
                sys.exit(2)
            utils.print_level = 0
            if utils.Levels.message[utils.Levels.INFO] in arg:
                utils.print_level |= int(utils.Levels.INFO)
            if utils.Levels.message[utils.Levels.WARNING] in arg:
                utils.print_level |= int(utils.Levels.WARNING)
            if utils.Levels.message[utils.Levels.ERROR] in arg:
                utils.print_level |= int(utils.Levels.ERROR)
            if utils.Levels.message[utils.Levels.SUMMARY] in arg:
                utils.print_level |= int(utils.Levels.SUMMARY)
            if utils.Levels.message[utils.Levels.DETAIL] in arg:
                utils.print_level |= int(utils.Levels.DETAIL)
            if utils.print_level == 0:
                print "Error: The log level specified is not " \
                    "part of the supported list !"
                print "Please check the usage of this tool and retry."
                sys.exit(2)
        elif opt in ("-g", "--group"):
            detail['group'] = arg
        elif opt in ("-c", "--category"):
            detail['category'] = arg
        elif opt in ("-i", "--item"):
            detail['item'] = arg
        elif opt in ("-I", "--ignore"):
            ignore_list = arg
        elif opt in ("-o", "--ouptut_dir"):
            if os.path.exists(arg):
                for filename in glob.glob("%s/*.diff" % arg):
                    os.remove(filename)
                for filename in glob.glob("%s/*.def" % arg):
                    os.remove(filename)
            else:
                os.mkdir(arg)
            global_params["output_dir"] = arg

    if (utils.print_level & utils.Levels.DETAIL) == utils.Levels.DETAIL:
        if (len(detail['group']) == 0 or len(detail['category']) == 0 or
                len(detail['item']) == 0):
            print "Error: The DETAIL output requires group, category & item " \
                "options to be set"
            sys.exit(2)

    if not pattern and not rampup:
        print "Error: Pattern option is mandatory"
        print_help()
        sys.exit(2)

    if rampup:
        for rampup_subdir in rampup.split(','):
            rampup_dir = rampup_subdir.strip()
            rampup_dirs.append(rampup_dir)

            if not os.path.isdir(rampup_dir):
                print "Rampup option shall point a directory"
                print "Error: the path %s doesn't exists !" % rampup_dir
                sys.exit(2)

            if not os.path.isfile(rampup_dir + "/hosts"):
                print "A valid rampup directory (%s) shall have a 'hosts'" \
                    " file in it" % rampup_dir
                print "Exiting"
                sys.exit(2)

            current_dir = "%s/results/" % (rampup_dir)
            try:
                if os.path.exists(current_dir):
                    shutil.rmtree(current_dir)
            except IOError as e:
                print "Unable to delete directory %s" % current_dir
                print e
                sys.exit(2)

            temp_rampup_values = [int(name) for name in os.listdir(rampup_dir)
                                  if os.path.isdir(rampup_dir+name)]
            if not rampup_values:
                rampup_values = temp_rampup_values
                if len(rampup_values) < 2:
                    print "A valid rampup directory (%s) shall have " \
                        "more than 1 output in it" % rampup_dir
                    print "Exiting"
                    sys.exit(2)

                print "Found %d rampup tests to analyse (from %d " \
                    "host up to %d)" % (len(rampup_values),
                                        min(rampup_values),
                                        max(rampup_values))
            else:
                if rampup_values != temp_rampup_values:
                    print "Directory %s doesn't have the same rampup values " \
                        "than the previous ones !" % (rampup_dir)
                    print "Exiting"
                    sys.exit(2)

    if rampup_values:
        bench_values = []
        for job in os.listdir("%s/%s" % (rampup_dir, rampup_values[0])):
            print "Processing Job '%s'" % job
            metrics = {}
            titles = {}
            for rampup_dir in rampup_dirs:
                result_dir = rampup_dir
                if len(rampup_dirs) > 1:
                    result_dir = "compared"
                current_dir = "%s/results/%s/" % (result_dir, job)
                try:
                    if not os.path.exists(current_dir):
                        os.makedirs(current_dir)
                except:
                    print "Unable to create directory %s" % current_dir
                    sys.exit(2)

                for rampup_value in sorted(rampup_values):
                    metrics = {}
                    metrics_file = (rampup_dir +
                                    "/%d/%s/metrics" % (rampup_value, job))
                    if not os.path.isfile(metrics_file):
                        print "Missing metric file for rampup=%d (%s)" % \
                            (rampup_value, metrics_file)
                        print "Skipping %d" % rampup_value
                        continue
                    metrics = eval(open(metrics_file).read())
                    titles[rampup_dir] = metrics["bench"]["title"]
                    compute_metrics(current_dir, rampup_value, metrics)

                    bench_values.append(
                        analyze_data(global_params, rampup_dir + '/' +
                                     str(rampup_value) + '/' + job + '/',
                                     ignore_list, detail,
                                     rampup_value, max(rampup_values),
                                     current_dir))

            plot_results(current_dir, rampup_values, metrics,
                         bench_values, titles, rampup_dirs, [])

        if len(titles.keys()) > 1:
            final_directory_name = ""
            for key in titles.keys():
                if not final_directory_name:
                    final_directory_name = "%s" % titles[key]
                else:
                    final_directory_name = "%s_vs_%s" % \
                                           (final_directory_name, titles[key])

            if os.path.exists(final_directory_name):
                shutil.rmtree(final_directory_name)
            os.rename(result_dir, final_directory_name)
            print "Output results can be found in directory '%s'" % \
                final_directory_name
    else:
        analyze_data(global_params, pattern, ignore_list, detail)


# Main
if __name__ == "__main__":
    sys.exit(main(sys.argv))
