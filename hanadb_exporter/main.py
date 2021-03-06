"""
SAP HANA database prometheus data exporter app

:author: xarbulu
:organization: SUSE Linux GmbH
:contact: xarbulu@suse.de

:since: 2019-05-09
"""

import sys
import os
import traceback
import logging
from logging.config import fileConfig
import time
import json
import argparse

from prometheus_client.core import REGISTRY
from prometheus_client import start_http_server

from hanadb_exporter import prometheus_exporter
from hanadb_exporter import db_manager

LOGGER = logging.getLogger(__name__)
CONFIG_FOLDER = '/etc/hanadb_exporter'
METRICS_FILES = [
    '/etc/hanadb_exporter/metrics.json',
    '/usr/etc/hanadb_exporter/metrics.json'
]

def parse_config(config_file):
    """
    Parse config file
    """
    with open(config_file, 'r') as f_ptr:
        json_data = json.load(f_ptr)
    return json_data


def parse_arguments():
    """
    Parse command line arguments
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c", "--config", help="Path to hanadb_exporter configuration file")
    parser.add_argument(
        "-m", "--metrics", help="Path to hanadb_exporter metrics file")
    parser.add_argument(
        "--identifier", help="Identifier of the configuration file from /etc/hanadb_exporter")
    parser.add_argument(
        "-v", "--verbosity",
        help="Python logging level. Options: DEBUG, INFO, WARN, ERROR (INFO by default)")
    args = parser.parse_args()
    return args


def setup_logging(config):
    """
    Setup logging system
    """
    hana_config = config.get('hana')
    sufix = 'hanadb_exporter_{}_{}'.format(hana_config.get('host'), hana_config.get('port', 30015))
    log_file = config.get('logging').get('log_file', '/var/log/{}'.format(sufix))

    fileConfig(config.get('logging').get('config_file'), defaults={'logfilename': log_file})

    # The next method is used to recatch and raise all
    # exceptions to redirect them to the logging system
    def handle_exception(*exc_info): # pragma: no cover
        """
        Catch exceptions to log them
        """
        text = ''.join(traceback.format_exception(*exc_info))
        logging.getLogger('hanadb_exporter').error(text)

    sys.excepthook = handle_exception


def find_metrics_file():
    """
    Find metrics predefined files in default locations
    """
    for metric_file in METRICS_FILES:
        if os.path.isfile(metric_file):
            return metric_file
    raise ValueError(
        'metrics file does not exist in {}'.format(",".join(METRICS_FILES)))


# Start up the server to expose the metrics.
def run():
    """
    Main execution
    """
    args = parse_arguments()
    if args.config is not None:
        config = parse_config(args.config)
    elif args.identifier is not None:
        config = parse_config('{}/{}.json'.format(CONFIG_FOLDER, args.identifier))
    else:
        raise ValueError('configuration file or identifier must be used')

    if config.get('logging', None):
        setup_logging(config)
    else:
        logging.basicConfig(level=args.verbosity or logging.INFO)

    if args.metrics:
        metrics = args.metrics
    else:
        metrics = find_metrics_file()

    try:
        hana_config = config['hana']
        dbs = db_manager.DatabaseManager()
        dbs.start(
            hana_config['host'], hana_config.get('port', 30013),
            user=hana_config.get('user', ''),
            password=hana_config.get('password', ''),
            userkey=hana_config.get('userkey', None),
            multi_tenant=config.get('multi_tenant', True),
            timeout=config.get('timeout', 600))
    except KeyError as err:
        raise KeyError('Configuration file {} is malformed: {} not found'.format(args.config, err))

    connectors = dbs.get_connectors()
    collector = prometheus_exporter.SapHanaCollectors(connectors=connectors, metrics_file=metrics)
    REGISTRY.register(collector)
    LOGGER.info('exporter sucessfully registered')

    LOGGER.info('starting to serve metrics')
    start_http_server(config.get('exposition_port', 9668), '0.0.0.0')
    while True:
        time.sleep(1)

if __name__ == "__main__": # pragma: no cover
    run()
