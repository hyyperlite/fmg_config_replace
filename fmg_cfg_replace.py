import sys
import argparse
from fmg_api_cfg import *
import logging

urllib3.disable_warnings()

parser = argparse.ArgumentParser()
parser.add_argument('--fmg', type=str, help="IP or FQDN of FortiManager")
parser.add_argument('--user', type=str, default='admin', help='login user with FMG API privileges')
parser.add_argument('--passwd', type=str, help='login password for user with FMG API privileges')
parser.add_argument('--fg', type=str, help='Device name on FortiManager to target for config replacement')
parser.add_argument('--file', type=str, help='Path to file in which to use for replacing target device configuration')
parser.add_argument('--debug', type=bool, default=False, help='Show additional logging including http/json')
parser.add_argument('--tasktimeout', type=int,  default=300, help='Number of seconds to wait for fmg task to complete')
parser.add_argument('--do_cfg_replace', type=bool,  default=True, help='Execute the config replace api call to FMG')
parser.add_argument('--do_install', type=bool,  default=True, help='Execute the config diff install to real device')
args = parser.parse_args()

fmg = args.fmg
fmg_user = args.user                    # Login for fmg api user
fmg_pass = args.passwd                  # Password for fmg api user
fg_device = args.fg                     # Target fg device to have config replace executed
cfg_file = args.file                    # 'new' config file to push to target fg
task_timeout = args.tasktimeout         # Time period to wait for fmg task completion before giving up
# do_cfg_replace = args.do_cfg_replace    # Execute the config replacement api call to fgm or not
# do_install = args.do_install            # Execute install config from fmg to target device or not

# temp actions to override cmdline
do_cfg_replace = True
do_preview = False
do_install = True
args.debug = False

if args.debug is True:
    logging.basicConfig(format='%(asctime)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S',
                        level=logging.DEBUG, stream=sys.stdout)
else:
    logging.basicConfig(format='%(asctime)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S',
                        level=logging.INFO, stream=sys.stdout)

# <-------- Start --------->
logging.info(f'Updating config for target device: {fg_device}')
logging.info(f'New Config File: {cfg_file}')
logging.info(f'FortiManager: {fmg}')


# Open target config file and read to fg_cfg str
with open(cfg_file, 'r') as file:
    fg_cfg = file.read()

# Loging to FMG via API to retrieve session key
fmg_session = fmg_api_login(fmg, fmg_user, fmg_pass)

if do_cfg_replace is True:
    my_descr = '/deployment/import/config'
    # API call to fmg to update config on device db for target device
    # If successful returns a task id to monitor status of in fmg_task_result
    # fmg_task_status, fmg_task_result = fmg_cfg_replace(fmg, fmg_session, fg_device, fg_cfg)
    fmg_response = fmg_cfg_replace(fmg, fmg_session, fg_device, fg_cfg)

    # Check if result was success/fail, output messages for either and continue if warranted
    if api_success(fmg_response, my_descr):
        # Monitor task id for completion and result
        fmg_task_status, fmg_response = \
            monitor_task(fmg, fmg_session, get_task_id(fmg_response), my_descr, f_timeout=task_timeout)

        # Check/process results from monitor_task, log and continue or not based on results
        if process_task_results(fmg_task_status, fmg_response, my_descr) is not True:
            log_and_exit()
    else:
        log_and_exit()

if do_preview is True:
    my_descr = 'security/console/install/preview'
    fmg_response = do_dev_preview(fmg, fmg_session, fg_device)
    if api_success(fmg_response, my_descr):

        # Monitor task id for completion and result
        fmg_task_status, fmg_response = \
            monitor_task(fmg, fmg_session, get_task_id(fmg_response), my_descr, f_timeout=task_timeout)

        # Check/process results from monitor_task, log and continue or not based on results
        if process_task_results(fmg_task_status, fmg_response, my_descr) is not True:
            log_and_exit()
    else:
        log_and_exit()

    get_preview_result(fmg, fmg_session, fg_device)

if do_install is True:
    my_descr = '/securityconsole/install/device'
    # exec function to make API call to install target device's device db configuration
    fmg_response = install_dev_config(fmg, fmg_session, fg_device)
    if api_success(fmg_response, my_descr):

        # Monitor task id for completion and result
        fmg_task_status, fmg_response = \
            monitor_task(fmg, fmg_session, get_task_id(fmg_response), my_descr, f_timeout=task_timeout)

        # Check/process results from monitor_task, log and continue or not based on results
        process_task_results(fmg_task_status, fmg_response, my_descr)
    else:
        log_and_exit()

# Logout of API
fmg_api_logout(fmg, fmg_session)
# Any final logging info
logging.info(f'### Tasks for Fortigate {fg_device} complete: SUCCESS')
