#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import sys
import time
import signal
import argparse
import os
import os.path
import subprocess
from urlparse import urlparse

try:
    from zapv2 import ZAPv2, ZapError
except ImportError:
    print('You need to install zapv2 python module - pip install python-owasp-zap-v2.4')
    sys.exit(1)


__author__ = 'ale'
__package__ = 'zapy'
__doc__ = """
Zapy is a python script that used the ZAP python API to interact with a headless Zed Attack Proxy.
Mainly useful to automate runs.
"""


def signal_handler(signal, frame):
    print('\n')
    sys.exit(0)


def run_spider(zap, target, api_key, cid=None, uid=None):
    """
    spider the target

    only spiders the target, it will not automatically kick off a active scan
    """
    print('Spidering target {0}'.format(target))
    zap.spider.set_option_scope_string(target, apikey=api_key)
    zap.spider.set_option_max_depth(10, apikey=api_key)
    zap.spider.set_option_thread_count(3)

    if cid and uid:
        try:
            z = zap.spider.scan_as_user(url=target, contextid=cid, userid=uid, maxchildren=0, apikey=api_key)
            print (z)
        except Exception as e:
            print('Exception: {0}'.format(e))
    else:
        try:
            z = zap.spider.scan(target, apikey=api_key)
        except Exception as e:
            print('Exception: {0}'.format(e))

    # Give the Spider a chance to start
    time.sleep(3)
    while (int(zap.spider.status()) < 100):
        print('Spider progress %: ' + zap.spider.status())
        time.sleep(2)

    print('Spider completed')


def run_active_scan(zap, target, api_key):
    """
    run a active scan against target using the initialized zap object

    a active scan will run through all available plugins like SQLi, Path Traversal, etc. just like when you would
    use the UI and start an attack against TARGET
    """
    print('Scanning target {0}'.format(target))
    zap.ascan.scan(target, True, apikey=api_key)
    time.sleep(3)
    while (int(zap.ascan.status()) < 100):
        print('Scan progress %: ' + zap.ascan.status())
        time.sleep(5)
    print('Scan completed')


def gen_report(zap, api_key, alerts, reporttype, report_file, force=False):
    '''
    generates a report in `reporttype`
    :param reporttype: html or xml
    '''

    # zap.core.htmlreport seems to be broken so we're using json2html for a very basic report in html
    # report = zap.core.htmlreport()

    if os.path.isfile(report_file) and force:
        try:
            os.remove(report_file)
        except IOError as e:
            print('Unable to remove {0}'.format(report_file))
    elif os.path.isfile(report_file):
        print('File {0} exists and --force was not used. '
              'Please remove file and re-run your scan. Exiting.'.format(report_file))
        sys.exit(1)
    try:
        with open(report_file, 'a') as f:
            print ('Creating {0} report..'.format(reporttype.upper()))
            if reporttype == 'html':
                html = zap.core.htmlreport(apikey=api_key)
                f.write(html)
            elif reporttype == 'xml':
                xml = zap.core.xmlreport(apikey=api_key)
                f.write(xml)
        print('Success: {1} report saved to {0}'.format(report_file, reporttype.upper()))
    except Exception as e:
        print('Error: Unable to save {1} report: {0}'.format(e, reporttype.upper()))


def auth(zap, target, api_key, authuser=None, authpass=None):
    """
    Setting authentication
    """
    # Set the context. Probably useful to have it outside?

    p = urlparse(target)
    cname = p.hostname
    cid = zap.context.new_context(cname)

    # Set the session management info to HTTP based
    ret = zap.sessionManagement.set_session_management_method(cid, "httpAuthSessionManagement", apikey=api_key)

    p = urlparse(target)
    ret = zap.authentication.set_authentication_method(cid, 'httpAuthentication', 'hostname={0}&port={1}&realm='.format(p.hostname, p.port), apikey=api_key)
    ret = zap.authentication.set_logged_out_indicator(cid, '401', api_key)

    # Add the user "profile"
    uid = zap.users.new_user(cid, "admin", apikey=api_key)
    ret = zap.forcedUser.set_forced_user(cid, uid, api_key)

    ret = zap.forcedUser.set_forced_user_mode_enabled(True, api_key)

    # Setting auth credentials. Parameters must be x-www-urlencoded.
    ret = zap.users.set_authentication_credentials(cid,
                                                   uid,
                                                   'username={authuser}&password={authpass}'.format(
                                                       authuser=authuser, authpass=authpass
                                                   ),
                                                   apikey=api_key)

    ret = zap.users.set_user_enabled(cid, uid, True, apikey=api_key)
    ret = zap.context.include_in_context(cname, '\Q{0}\E.*'.format(target), apikey=api_key)

    return zap


def start_zap(zapsh='/zap/weekly/zap.sh', apikey='zap'):
    """
    starts zap
    """
    print('Starting ZAP ...')
    subprocess.Popen([zapsh, '-config', 'api.key=' + apikey, '-daemon'], stdout=open(os.devnull, 'w'))
    print('Waiting for ZAP to load, 10 seconds ...')
    print('Use api-key {0} to interact with my API ...'.format(apikey))
    time.sleep(10)


def stop_zap(zap):
    """
    stops zap
    """
    zap.core.shutdown()


def main(args=None):
    """
    main function
    """
    if args is not None:
        start = args.start
        stop = args.stop
        useauth = args.auth
        authuser = args.authuser
        authpass = args.authpass
        zapsh = args.zapsh
        target = args.target
        api_key = args.api_key
        spider = args.spider
        active_scan = args.active_scan
        html_report = args.html_report
        xml_report = args.xml_report
        force = args.force
    else:
        print('No arguments supplied. Exiting')
        sys.exit(1)

    if useauth:
        if not authuser:
            print ("Missing --authuser parameter")
            print("Exiting.")
            sys.exit(1)
        if not authpass:
            print ("Missing --authpass parameter")
            print ("Exiting.")
            sys.exit(1)

    if start:
        start_zap(zapsh, api_key)

    zap = ZAPv2()

    zap.core.delete_all_alerts(apikey=api_key)
    zap.core.new_session(target, True, apikey=api_key)

    cid = None
    uid = None

    if useauth:
        zap = auth(zap, target, api_key, authuser, authpass)

    # Use the line below if ZAP is not listening on 8090
    # zap = ZAPv2(proxies={'http': 'http://127.0.0.1:8090', 'https': 'http://127.0.0.1:8090'})

    zap.urlopen(target)
    time.sleep(2)

    if spider:
        if cid and uid:
            run_spider(zap, target, api_key, cid, uid)
        else:
            run_spider(zap, target, api_key)
        time.sleep(5)

    if active_scan:
        run_active_scan(zap, target, api_key)
        time.sleep(5)

    print('Hosts: ' + ', '.join(zap.core.hosts))

    alerts = zap.core.alerts()

    if html_report is not None or xml_report is not None:
        reporttype = None
        report_file = None
        if html_report is not None:
            reporttype = 'html'
            report_file = html_report
        elif xml_report is not None:
            reporttype = 'xml'
            report_file = xml_report
        gen_report(zap, api_key, alerts, reporttype, report_file, force)

    if stop:
        stop_zap(zap)


if __name__ == '__main__':

    signal.signal(signal.SIGINT, signal_handler)

    parser = argparse.ArgumentParser()

    parser.add_argument('--start',
                        help="Start ZAP locally",
                        action='store_true',
                        required=False)

    parser.add_argument('--stop',
                        help="Stop ZAP locally when scan completed",
                        action='store_true',
                        required=False)

    parser.add_argument('--auth',
                        help="Use authentication (basic auth for now only)",
                        action='store_true',
                        required=False)

    parser.add_argument('--authuser',
                        help="Use this user for authentication (required: when --auth is used)",
                        required=False)

    parser.add_argument('--authpass',
                        help="Use this password for specified user (required: when --auth is used)",
                        required=False)

    parser.add_argument('--zapsh',
                        default="/zap/weekly/zap.sh",
                        help="Specify where ZAP's zap.sh is located (default: /zap/weekly/zap.sh)",
                        required=False)

    parser.add_argument('-t', '--target', '-u', '--url',
                        help="The target / url to scan (https://scanme.domain.com)",
                        required=True)

    parser.add_argument('-k', '--api-key',
                        help="The api key to connect to ZAP",
                        required=False)

    parser.add_argument('-s', '--spider', action='store_true',
                        help="Run spider against TARGET",
                        required=False)

    parser.add_argument('-a', '--active-scan', action='store_true',
                        help="Run a active-scan against TARGET",
                        required=False)

    parser.add_argument('--html-report',
                        help="Create a html report in /path/to/report.html",
                        required=False)

    parser.add_argument('--xml-report',
                        help="Create a xml report in /path/to/report.xml",
                        required=False)

    parser.add_argument('--force', action='store_true',
                        help="Overwrite /data/report.html if it exists",
                        required=False)

    args = parser.parse_args()
    main(args)
