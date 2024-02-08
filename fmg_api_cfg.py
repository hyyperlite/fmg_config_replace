import requests
import urllib3
import time
import logging
import sys

urllib3.disable_warnings()


class FmgApiError(Exception):
    pass


def fmg_api_login(f_ip, f_user, f_pass):
    # API password login to FortiManager
    data = {
        "method": "exec",
        "params": [
            {
                "data": {
                    "user": f_user,
                    "passwd": f_pass,
                },
                "url": "/sys/login/user"
            }
        ]
    }
    # Exec function to execute API Call
    response_json = fmg_exec_api(f_ip, data)
    logging.debug(response_json)

    # Check if the response includes session param, if so assume was successful and return session id
    if 'session' in response_json:
        logging.debug(f'API Session: {response_json.get("session")}')
        return response_json.get('session')
    else:
        logging.error('Failed to login to FMG API and get session key')
        raise Exception('Failed to get session key')


def log_and_exit(message="### Tasks for Fortigate Config Replace did not complete: FAIL", exitcode=1):
    logging.info(message)
    sys.exit(exitcode)


def fmg_api_logout(f_ip, f_session):
    # Logout this API session from FMG
    data = {
        "method": "exec",
        "params": [
            {
                "url": "/sys/logout"
            }
        ],
        "session": f_session
    }
    response_json = fmg_exec_api(f_ip, data)
    logging.debug(response_json)


def fmg_exec_api(f_ip, f_data):
    # Exec API Call to FMG, requires the formatted json 'data' and fmg ip addr
    try:
        response = requests.post(f'https://{f_ip}/jsonrpc', json=f_data, verify=False)
    except requests.exceptions.Timeout as err:
        raise FmgApiError(f'Timeout Attempting to Reach Fortimanager:\n {err}')
    except requests.exceptions.ConnectionError as err:
        raise FmgApiError(f'Experienced Network Issue Connecting to Fortimanager\n {err}')
    except requests.exceptions.RequestException as err:
        raise FmgApiError(f'Request to FortiManager Failed - '
                          f'FMG API permissions, Network Connectivity, etc:\n {err}')
    return response.json()


def get_task_id(f_task_result):
    # Get task id from json response and return it
    return f_task_result['result'][0]['data']['task']


def get_task(f_ip, f_session, f_task):
    # Check task on FMG continually until complete or timeout and return result
    data = {
        "method": "get",
        "params": [
            {
                "url": f"/task/task/{f_task}"
            }
        ],
        "session": f_session
    }
    return fmg_exec_api(f_ip, data)


def monitor_task(f_ip, f_session, f_task, f_name='', f_timeout=300):
    logging.info(f'Start Monitoring Task: {f_task} ({f_name})')
    # Monitor a task until completed or exceed the provided timeout value
    # Calls the get_task function repeatedly
    timer = 0
    timewait = 5
    i = 1
    while True:
        timer = timer + timewait
        response_json = get_task(f_ip, f_session, f_task)
        task_result = response_json['result'][0]['data']
        logging.info(f'  Task Check{i}: {task_result}')

        if task_result.get('percent') == 100:
            if task_result.get('num_err') == 0 and task_result.get('num_warn') == 0:
                return True, f_task
            else:
                return False, task_result
        if timer >= f_timeout:
            return None, "Timeout waiting for task to complete"
        time.sleep(timewait)
        i += 1


def api_success(f_task_result, f_name):
    if f_task_result['result'][0]['status']['message'] == 'OK':
        logging.info(f'API Request to {f_name}: Success')
        return True
    else:
        logging.info(f'API Request to {f_name}: Failed')
        return False


def process_task_results(f_task_status, f_task_result, f_name):
    # If task failed, then provide details of task jobs and errors
    if f_task_status is False and f_task_result == 'Invalid Parameter':
        logging.info(f'Result for Previous Task ({f_name}): '
                     f'ERROR: Invalid Parameter (Invalid device name?)')
        return False

    if f_task_status is False:
        logging.info(f'Result for Task: {f_task_result["id"]} ({f_name}): '
                     f'ERROR -> Failed (Check task history for reason)')
        for line in f_task_result['line'][0]['history']:
            logging.info(f'  {line.get("detail").split(":", 3)[3]}')  # get last element of split on ':'
        return False

    # # If task timed out, log timeout message
    #     logging.info(f'Result for {f_name}, taskid {f_task_result["id"]}: '
    #                  f'TIMEOUT -> Exceeded defined timeout waiting for FMG task to complete')
    #     return False

    # If task got anything other than False, None or True then raise an Exception
    if f_task_status is not True:
        logging.info(f'Result for {f_name}, taskid {f_task_result["id"]}: UNKNOWN -> Task Status Not Recognized')
        raise Exception('task_status returned from monitor_task function is not recognized')

    # If task_status was True then we should attempt to install config changes to target_device
    logging.info(f'Result for {f_name}, taskid {f_task_result}: SUCCESS')
    return True


def fmg_cfg_replace(f_ip, f_session, f_device, f_config):
    # Execute the config-replace (device db only) with new config
    data = {
        "method": "exec",
        "params": [
            {
                "data": {
                    "config": f_config,
                    "device": f_device,
                    "flags": 0
                },
                "url": "deployment/import/config"
            }
        ],
        "session": f_session,
        "verbose": 1
    }

    response_json = fmg_exec_api(f_ip, data)
    logging.debug(response_json)
    return response_json


def install_dev_config(f_ip, f_session, f_device):
    # Install "DEVICE" config, should not need to securityconsole install here as policy set per device
    data = {
        "method": "exec",
        "params": [
            {
                "data": {
                    "scope": {"name": f_device},
                    "adom": 'root',
                },
                "url": "securityconsole/install/device"
            }
        ],
        "session": f_session,
    }
    response_json = fmg_exec_api(f_ip, data)
    logging.debug(response_json)
    return response_json


def do_dev_preview(f_ip, f_session, f_device):
    # Generate a preview of device install
    data = {
        "method": "exec",
        "params": [
            {
                "data": {
                    "device": f_device,
                    "adom": 'root',
                },
                "url": "securityconsole/install/preview"
            }
        ],
        "session": f_session,
    }
    response_json = fmg_exec_api(f_ip, data)
    logging.info(response_json)
    return response_json


def get_preview_result(f_ip, f_session, f_device):
    # Generate a preview of device install
    data = {
        "method": "exec",
        "params": [
            {
                "data": {
                    "device": f_device,
                    "adom": 'root',
                },
                "url": "securityconsole/preview/result"
            }
        ],
        "session": f_session,
    }
    response_json = fmg_exec_api(f_ip, data)
    logging.info(response_json)
    logging.info(response_json['result'][0]['data']['message'])
